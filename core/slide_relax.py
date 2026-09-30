"""Slide Relax: undo folds (like bevel overshoot) by sliding vertices along their own edges.

Each selected vertex moves only along the line of one of its edges (its rail), the
way Vertex Slide does, so it stays on the surface that edge describes. Bevel
vertices sit on the original edges, so sliding them back restores the shape the
bevel was meant to have.

Folds are judged against the vertex's umbrella: around an interior vertex the summed
vector area of its faces does not depend on where the vertex is, so its direction is
a reference normal that stays valid however far the vertex has overshot. What must
stay unfolded (the corner at the vertex for triangles and quads, the whole face for
n-gons) changes linearly as the vertex slides, so the part of a rail where nothing
is folded is an interval that can be found exactly. The vertex slides into it, and
`strength` pulls it toward the average of its neighbours within it.

Choosing the rail: a vertex that overshot travelled inside the planes of the faces
it folded, so the rail lying in those planes is the way back; among rails that
unfold equally well, the one that leaves those planes least wins. A vertex keeps
its rail afterwards and only switches when that rail can no longer unfold it, so
relaxing does not wander off the original edges. Only when no edge can open a fold
does it try sliding toward the middle of its neighbours instead.

Who moves: only vertices folded at the start unfold, worst first, and part of the
way per pass so neighbours that overshot together can open up together. The other
selected vertices hold still while a face of theirs is still folded (they were
dragged into it, and chasing it would pull them off the shape), and relax only once
it is open. A relax step is shortened until no face it touches is folded as seen
from any of that face's vertices, so relaxing never folds anything.

Guards: no slide leaves the box around the vertex and its neighbours, and a
connected group of moved vertices that ends up with more folds than it started
with is put back, so a patch is never left worse than it was.
"""
from mathutils import Vector

_MARGIN = 0.1          # folded faces are pushed until height / size reaches this
_FLAT = 1e-6           # faces flatter than this count as flat, not folded
_GIVE = 0.25           # share of its height an unfolded face keeps while a neighbour unfolds
_CORNER_MAX = 4        # faces with up to this many sides are judged by the corner at the vertex
_TILT = 4.0            # cost of leaving the folded faces' planes, relative to sliding within them
_UNFOLD_STEP = 0.5     # share of the way a folded vertex goes per pass, so neighbours can catch up
_NEAR = 0.05           # ...unless the rest of the way is shorter than this share of its reach
_RANGE = 2.0           # furthest slide, in multiples of the longest edge at the vertex at the start
_BOX = 0.1             # how far past the box around its neighbours a vertex may go (share of its size)
_BACKTRACK = 5         # halvings tried before a relax step that would fold something is dropped
_BISECT_STEPS = 48
_STILL = 1e-6          # a pass whose largest move is below this (relative) ends the loop


def _fan(v, pos):
    """Faces around v, measured from v's current position o.

    For every face: (face, area, test, e, size). area is the face's vector area and
    test the part of it that must stay unfolded; with v moved to p both change by
    0.5 * (p - o).cross(e)  (e runs from the previous to the next vertex). size is
    the face's shortest edge not touching v.

    For triangles and quads the test is the corner at v (prev, v, next): a vertex that
    slides past a neighbour turns a quad into a bow tie long before its total area
    flips. N-gons are tested whole, since L-shaped ones have inward corners by design.
    """
    o = pos[v]
    fan = []
    for l in v.link_loops:
        nxt, prv = l.link_loop_next, l.link_loop_prev
        area, size = Vector(), float('inf')
        loop = nxt
        while loop is not prv:
            a = pos[loop.vert] - o
            b = pos[loop.link_loop_next.vert] - o
            area += a.cross(b)
            size = min(size, (b - a).length)
            loop = loop.link_loop_next
        area *= 0.5
        if len(l.face.verts) <= _CORNER_MAX:
            test = (pos[nxt.vert] - o).cross(pos[prv.vert] - o) * 0.5
        else:
            test = area
        fan.append((l.face, area, test, pos[nxt.vert] - pos[prv.vert], size))
    return fan


class _Star:
    """The faces around one vertex as linear health functions of where it sits.

    health_f(p) = value_f + (p - o) . grad_f is the face's signed height along the
    umbrella normal divided by its size (see _fan for which part of the face is
    measured): below zero the face is folded over.
    """

    def __init__(self, v, pos, give=1.0):
        """give: share of an unfolded face's current height it has to keep (up to the margin).

        Sliding back along a rail has to narrow the faces along it, so unfolding
        passes a give below 1; relaxing keeps 1 so it never thins anything.
        """
        self.faces = []   # (face, value, grad, need)
        self.folded = []  # faces folded over now
        self.planes = []  # their unit normals
        fan = _fan(v, pos)
        total = sum((area for _f, area, _t, _e, _s in fan), Vector())
        if total.length_squared <= 0.0:
            return
        normal = total.normalized()
        floor = 1e-4 * max((e.length for _f, _a, _t, e, _s in fan), default=0.0)
        for face, area, test, e, size in fan:
            lever = e.cross(normal) * 0.5
            span = lever.length
            if span <= 1e-12:
                continue
            size = max(size, floor, 1e-12)
            value = normal.dot(test) / (span * size)
            if value < -_FLAT:
                need = _MARGIN  # folded: must open up to the margin
                self.folded.append(face)
                if area.length_squared > 0.0:
                    self.planes.append(area.normalized())
            else:
                need = max(min(value, _MARGIN) * give, _FLAT)  # unfolded: must keep its height
            self.faces.append((face, value, lever / (span * size), need))

    def health(self):
        """Worst face relative to what it needs: 1 or more when nothing has to move."""
        return min((value / need for _f, value, _g, need in self.faces), default=1.0)

    def tilt(self, d):
        """How far a slide along d leaves the planes of the folded faces, per unit of slide."""
        if not self.planes:
            return 0.0
        return sum(abs(d.dot(n)) for n in self.planes) / len(self.planes)

    def solve(self, d, t_min, t_max, target_t, level=1.0):
        """Best spot on the rail o + t*d with t in [t_min, t_max]: (t, fit), fit 1 when it works.

        Within the interval where every face reaches `level` (1: unfolded with margin)
        the spot nearest target_t wins; when the rail cannot get there, the spot
        nearest target_t among those where the worst face is least bad wins.
        """
        lines = [(value / need, grad.dot(d) / need) for _f, value, grad, need in self.faces]
        lo, hi = _interval(lines, level, t_min, t_max)
        if lo <= hi:
            return min(max(target_t, lo), hi), 1.0

        # Maximise the concave min(a + b*t): step toward the side the worst face improves on.
        lo, hi = t_min, t_max
        for _ in range(_BISECT_STEPS):
            mid = 0.5 * (lo + hi)
            _a, b = min(lines, key=lambda line: line[0] + line[1] * mid)
            if b > 0.0:
                lo = mid
            elif b < 0.0:
                hi = mid
            else:
                break  # a flat worst face: the whole plateau is as good
        peak_t = 0.5 * (lo + hi)
        peak = min(a + b * peak_t for a, b in lines)
        lo, hi = _interval(lines, peak - 1e-3 * max(1.0, abs(peak)), t_min, t_max)
        t = min(max(target_t, lo), hi) if lo <= hi else peak_t
        return t, min(min(a + b * t for a, b in lines), 1.0)


def _interval(lines, level, lo, hi):
    """(lo, hi) narrowed to the t where every a + b*t reaches level; lo > hi if there are none."""
    for a, b in lines:
        if b > 0.0:
            lo = max(lo, (level - a) / b)
        elif b < 0.0:
            hi = min(hi, (level - a) / b)
        elif a < level:
            return 1.0, 0.0
    return lo, hi


def _within(o, d, centre, radius):
    """(t_min, t_max) keeping o + t*d within radius of centre (o is inside already)."""
    f = o - centre
    b = d.dot(f)
    root = max(b * b - f.dot(f) + radius * radius, 0.0) ** 0.5
    return -b - root, -b + root


def _in_box(o, d, points, t_min, t_max):
    """Narrow [t_min, t_max] so o + t*d stays in the box around points and o, grown by _BOX."""
    lo = [min(o[i], *(p[i] for p in points)) for i in range(3)]
    hi = [max(o[i], *(p[i] for p in points)) for i in range(3)]
    grow = _BOX * max(hi[i] - lo[i] for i in range(3))
    for i in range(3):
        if abs(d[i]) < 1e-12:
            continue
        a = (lo[i] - grow - o[i]) / d[i]
        b = (hi[i] + grow - o[i]) / d[i]
        t_min, t_max = max(t_min, min(a, b)), min(t_max, max(a, b))
    return t_min, t_max


def _rails(v, pos):
    """Unit directions v can slide along: its edges, or only its border edges on an open border."""
    edges = [e for e in v.link_edges if e.is_boundary] if v.is_boundary else v.link_edges
    rails = []
    for e in edges:
        d = pos[e.other_vert(v)] - pos[v]
        if d.length_squared > 0.0:
            rails.append(d.normalized())
    return rails


def _target(v, pos):
    """Average of the neighbours (border neighbours only for a border vertex)."""
    if v.is_boundary:
        around = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
    else:
        around = [e.other_vert(v) for e in v.link_edges]
    return sum((pos[n] for n in around), Vector()) / len(around)


class _Positions(dict):
    """World positions, read from the mesh the first time a vertex is looked up."""

    def __init__(self, matrix_world):
        super().__init__()
        self.matrix_world = matrix_world

    def __missing__(self, v):
        p = self[v] = self.matrix_world @ v.co
        return p


def _area(f, pos):
    """Vector area of a face, measured from its first vertex for precision."""
    verts = f.verts
    o = pos[verts[0]]
    area, prev = Vector(), Vector()
    for v in verts[1:]:
        cur = pos[v] - o
        area += prev.cross(cur)
        prev = cur
    return area * 0.5


class _Umbrellas(dict):
    """Summed vector area of the faces around each vertex (its umbrella normal, unnormalised).

    Built on first use and kept current by _place, so checking a neighbour's view of
    a face does not mean rebuilding that neighbour's whole star.
    """

    def __init__(self, pos):
        super().__init__()
        self.pos = pos

    def __missing__(self, w):
        u = self[w] = sum((_area(f, self.pos) for f in w.link_faces), Vector())
        return u


def _place(v, p, pos, umbrellas):
    """Move v to p and update the umbrellas of every vertex on its faces."""
    faces = list(v.link_faces)
    before = [_area(f, pos) for f in faces]
    pos[v] = p
    for f, old in zip(faces, before):
        delta = _area(f, pos) - old
        for w in f.verts:
            if w in umbrellas:
                umbrellas[w] = umbrellas[w] + delta


def _folded_views(v, pos, umbrellas):
    """(viewer, face) for v's faces folded as seen from their other vertices (as in _Star)."""
    views = set()
    for f in v.link_faces:
        ring = [l.vert for l in f.loops]
        pts = [pos[w] for w in ring]
        n = len(pts)
        area = _area(f, pos) if n > _CORNER_MAX else None
        lengths = [(pts[(i + 1) % n] - pts[i]).length for i in range(n)]  # edge i runs i -> i+1
        for i, w in enumerate(ring):
            if w is v:
                continue
            normal = umbrellas[w]
            if normal.length_squared <= 0.0:
                continue
            normal = normal.normalized()
            span = (pts[(i + 1) % n] - pts[i - 1]).cross(normal).length * 0.5
            if span <= 1e-12:
                continue
            size = min((lengths[k] for k in range(n) if k != i and k != (i - 1) % n), default=1e-12)
            test = area if area is not None else (pts[(i + 1) % n] - pts[i]).cross(pts[i - 1] - pts[i]) * 0.5
            if normal.dot(test) / (span * max(size, 1e-12)) < -_FLAT:
                views.add((w, f))
    return views


def _badness(group, pos):
    """Folds around a group of vertices: faces folded as seen from any of their vertices,
    plus edges whose two faces point in opposite directions."""
    faces = {f for v in group for f in v.link_faces}
    folded = set()
    for w in {w for f in faces for w in f.verts}:
        folded.update(f for f in _Star(w, pos).folded if f in faces)
    normals = {f: _area(f, pos) for f in faces}
    flips = 0
    for e in {e for f in faces for e in f.edges}:
        pair = [f for f in e.link_faces if f in normals]
        if len(pair) == 2:
            a, b = normals[pair[0]], normals[pair[1]]
            if a.dot(b) < -0.5 * a.length * b.length:
                flips += 1
    return len(folded) + flips


def _groups(verts):
    """Split verts into groups that share faces."""
    remaining = set(verts)
    groups = []
    while remaining:
        group, stack = [], [remaining.pop()]
        while stack:
            v = stack.pop()
            group.append(v)
            for f in v.link_faces:
                for w in f.verts:
                    if w in remaining:
                        remaining.discard(w)
                        stack.append(w)
        groups.append(group)
    return groups


def _movable(v):
    return v.is_manifold and not v.is_wire and bool(v.link_faces)


def folded_faces(verts, pos):
    """Faces around `verts` that are folded over as seen from one of those vertices."""
    folded = set()
    for v in verts:
        folded.update(_Star(v, pos).folded)
    return folded


def slide_relax(verts, matrix_world, *, iterations=10, strength=0.5):
    """Slide `verts` along their edges until the faces around them are no longer folded.

    strength (0..1): how far each pass also moves a vertex toward the average of its
    neighbours, within the unfolded part of its rail. At 0 vertices move only as far
    as needed to unfold. Returns stats with 'moved', 'folded_before' and 'folded_after'.
    """
    verts = [v for v in verts if _movable(v)]
    inverse = matrix_world.inverted_safe()
    pos = _Positions(matrix_world)
    umbrellas = _Umbrellas(pos)
    start = {v: pos[v].copy() for v in verts}
    reach = {v: max(_RANGE * max((pos[e.other_vert(v)] - pos[v]).length for e in v.link_edges), 1e-9)
             for v in verts}
    # Only vertices folded at the start unfold. The others can be folded for a while by
    # a neighbour that is still sliding back; chasing that would drag them off the shape.
    culprits = {v for v in verts if _Star(v, pos).folded}
    folded_before = len(folded_faces(verts, pos))

    movable = set(verts)
    around = {v: {w for f in v.link_faces for w in f.verts if w is not v and w in movable} for v in verts}
    locked = {}
    stars = {}
    dirty = set(verts)  # vertices whose faces changed since they were last looked at
    for _ in range(max(iterations, 1)):
        for v in dirty:
            stars[v] = _Star(v, pos)
        still_folded = set()
        for v in culprits:
            still_folded.update(stars[v].folded)
        todo, dirty = sorted(dirty, key=lambda v: stars[v].health()), set()
        largest = 0.0
        for v in todo:
            if v not in culprits:
                if still_folded.intersection(v.link_faces):
                    continue  # hold still until the vertex that folded these faces has slid back
                star = _Star(v, pos)  # neighbours earlier in this pass may have moved
                unfolding, level = False, min(star.health(), 1.0)
            else:
                star = _Star(v, pos)
                unfolding, level = bool(star.folded), 1.0
                if unfolding:
                    star = _Star(v, pos, _GIVE)
            if not star.faces:
                continue
            if not unfolding and strength <= 0.0 and star.health() >= level:
                continue  # nothing to undo and nothing to relax
            o = pos[v]
            goal = o.lerp(_target(v, pos), strength)
            ring = [pos[w] for w in {w for f in v.link_faces for w in f.verts if w is not v}]

            fallback = []
            if unfolding:
                # When no edge line can open the fold, sliding toward the middle of the neighbours may.
                middle = sum(ring, Vector()) / len(ring) - o
                if middle.length_squared > 0.0:
                    fallback = [middle.normalized()]
            best = None
            for rails in ([locked[v]] if v in locked else [], _rails(v, pos), fallback):
                for d in rails:
                    t_min, t_max = _within(o, d, start[v], reach[v])
                    t_min, t_max = _in_box(o, d, ring, t_min, t_max)
                    t, fit = star.solve(d, t_min, t_max, (goal - o).dot(d), level)
                    cost = (o + d * t - goal).length + _TILT * abs(t) * star.tilt(d)
                    key = (-fit, cost)
                    if best is None or key < best[0]:
                        best = (key, d, t)
                if best is not None and best[0][0] <= -1.0:
                    break  # this set of rails already unfolds everything
            if best is None:
                continue
            _key, d, t = best
            locked[v] = d
            if abs(t) <= _STILL * reach[v]:
                continue
            if unfolding:
                if abs(t) > _NEAR * reach[v]:
                    t *= _UNFOLD_STEP
                _place(v, o + d * t, pos, umbrellas)
            else:
                # Relaxing must not fold anything, as seen from any vertex of the faces it moves.
                before = None
                for _ in range(_BACKTRACK):
                    _place(v, o + d * t, pos, umbrellas)
                    after = _folded_views(v, pos, umbrellas)
                    if after and before is None:
                        _place(v, o, pos, umbrellas)
                        before = _folded_views(v, pos, umbrellas)
                        _place(v, o + d * t, pos, umbrellas)
                    if not after or after <= before:
                        break
                    t *= 0.5
                else:
                    _place(v, o, pos, umbrellas)
                    continue
            largest = max(largest, abs(t) / reach[v])
            dirty.add(v)
            dirty.update(around[v])
        if largest < _STILL:
            break

    # Never leave a patch worse than it was: put back any connected group of moved
    # vertices that ends up with more folds than it started with.
    original = _Positions(matrix_world)
    moved = []
    for group in _groups([v for v in verts if (pos[v] - start[v]).length > 1e-9]):
        if _badness(group, pos) > _badness(group, original):
            for v in group:
                pos[v] = start[v]
        else:
            moved.extend(group)
    for v in moved:
        v.co = inverse @ pos[v]
    return {'moved': len(moved), 'folded_before': folded_before,
            'folded_after': len(folded_faces(verts, pos))}

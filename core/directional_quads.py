"""Directional quad rebuild for selected faces.

Vertices are never added, removed or moved. Ngons (and optionally existing quads)
are triangulated, then adjacent triangle pairs are joined into quads, preferring
quads whose edges run along a world axis or across it on the surface and that
continue the edge loops of quads already built next to them. Edges on
the selection boundary are never dissolved, so unselected geometry is untouched.
"""
import heapq
import math
from collections import defaultdict

import bmesh
from mathutils import Vector

AXIS_VECTORS = {
    'X': Vector((1.0, 0.0, 0.0)),
    'Y': Vector((0.0, 1.0, 0.0)),
    'Z': Vector((0.0, 0.0, 1.0)),
}

DEFAULT_DELIMIT = frozenset({'SEAM', 'SHARP', 'MATERIAL', 'UV'})

_HALF_PI = math.pi / 2.0
_EPS = 1e-12
_UV_EPS = 1e-10
_AUGMENT_ROUNDS = 3
_AUGMENT_BUDGET = 1500  # max triangles one path search may visit


def _smoothstep(edge0, edge1, x):
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def _surface_flow(direction, normal):
    """Project the world direction onto the surface plane.

    Returns (unit_flow, weight). Weight fades to 0 where the direction runs along
    the normal (e.g. Z on a flat top cap), since flow is undefined there.
    """
    proj = direction - normal * direction.dot(normal)
    length = proj.length
    if length < 1e-6:
        return None, 0.0
    return proj / length, _smoothstep(0.15, 0.5, length)


def _edge_alignment(vec, normal, flow):
    """Return (alignment, surface_length) for an edge vector.

    Alignment is 1.0 when the edge runs along the flow or across it, 0.0 at 45 degrees.
    """
    u = vec - normal * vec.dot(normal)
    length = u.length
    if length < 1e-9:
        return 0.0, 0.0
    c = u.dot(flow) / length
    return abs(2.0 * c * c - 1.0), length


def _quad_alignment(quad, normal, flow):
    total = weight = 0.0
    for i in range(4):
        a, length = _edge_alignment(quad[(i + 1) % 4] - quad[i], normal, flow)
        total += a * length
        weight += length
    return total / weight if weight > 0.0 else 0.0


def _is_convex(quad, normal):
    for i in range(4):
        e1 = quad[i] - quad[i - 1]
        e2 = quad[(i + 1) % 4] - quad[i]
        if e1.cross(e2).dot(normal) <= 0.0:
            return False
    return True


def _max_corner_deviation(quad):
    """Largest deviation of any corner angle from 90 degrees."""
    worst = 0.0
    for i in range(4):
        u = quad[i - 1] - quad[i]
        w = quad[(i + 1) % 4] - quad[i]
        if u.length_squared < _EPS or w.length_squared < _EPS:
            return math.pi
        worst = max(worst, abs(u.angle(w) - _HALF_PI))
    return worst


def _blend_score(quad, normal, deviation, face_angle, direction, strength):
    """Quad score in [0, 1]: shape quality blended with axis alignment."""
    shape = 0.8 * max(0.0, 1.0 - deviation / _HALF_PI) + 0.2 * max(0.0, 1.0 - face_angle / _HALF_PI)
    flow, weight = _surface_flow(direction, normal)
    k = strength * weight
    if k <= 0.0:
        return shape
    return (1.0 - k) * shape + k * _quad_alignment(quad, normal, flow)


def score_quad(quad, direction, strength, face_threshold, shape_threshold):
    """Score a candidate quad (4 world-space points in winding order), or None if it is not allowed."""
    p0, p1, p2, p3 = quad
    n1 = (p1 - p0).cross(p2 - p0)
    n2 = (p2 - p0).cross(p3 - p0)
    if n1.length_squared < _EPS or n2.length_squared < _EPS:
        return None
    n1.normalize()
    n2.normalize()
    normal = n1 + n2
    if normal.length_squared < _EPS:
        return None
    normal.normalize()
    face_angle = n1.angle(n2)
    if face_angle > face_threshold or not _is_convex(quad, normal):
        return None
    deviation = _max_corner_deviation(quad)
    if deviation > shape_threshold:
        return None
    return _blend_score(quad, normal, deviation, face_angle, direction, strength)


def _count_sides(faces):
    tris = quads = ngons = 0
    for f in faces:
        n = len(f.verts)
        if n == 3:
            tris += 1
        elif n == 4:
            quads += 1
        else:
            ngons += 1
    return tris, quads, ngons


def _triangulate(bm, faces, co, direction, reflow_quads):
    """Triangulate ngons (and quads when re-flowing).

    Quads are split along whichever diagonal best follows the flow, because that
    diagonal becomes an outer edge if its triangles pair with neighbours instead.
    Returns (work_faces, internal_edges, restore_edges):
    internal edges were created here and skip delimit checks; restore edges are
    old quad diagonals and may always be dissolved to give the original quad back.
    """
    ngons = []
    quads_02, quads_13, quads_beauty = [], [], []

    for f in faces:
        n_verts = len(f.verts)
        if n_verts > 4:
            ngons.append(f)
        elif n_verts == 4 and reflow_quads:
            pts = [co(v) for v in f.verts]
            normal = (pts[2] - pts[0]).cross(pts[3] - pts[1])
            if normal.length_squared < _EPS:
                quads_beauty.append(f)
                continue
            normal.normalize()
            flow, weight = _surface_flow(direction, normal)
            if weight < 0.05 or not _is_convex(pts, normal):
                quads_beauty.append(f)
                continue
            a02, _ = _edge_alignment(pts[2] - pts[0], normal, flow)
            a13, _ = _edge_alignment(pts[3] - pts[1], normal, flow)
            (quads_02 if a02 >= a13 else quads_13).append(f)

    work = dict.fromkeys(faces)  # ordered set, keeps results deterministic between redos
    internal, restore = set(), set()

    for group, quad_method in ((quads_02, 'FIXED'), (quads_13, 'ALTERNATE'), (quads_beauty, 'BEAUTY')):
        if group:
            res = bmesh.ops.triangulate(bm, faces=group, quad_method=quad_method, ngon_method='BEAUTY')
            restore.update(res['edges'])
            work.update(dict.fromkeys(res['faces']))

    if ngons:
        res = bmesh.ops.triangulate(bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
        internal.update(res['edges'])
        work.update(dict.fromkeys(res['faces']))

    internal |= restore
    return [f for f in work if f.is_valid], internal, restore


def _passes_delimit(edge, l1, l2, delimit, uv_layers):
    if 'SEAM' in delimit and edge.seam:
        return False
    if 'SHARP' in delimit and not edge.smooth:
        return False
    if 'MATERIAL' in delimit and l1.face.material_index != l2.face.material_index:
        return False
    # l1 runs A->B in its face, l2 runs B->A, so compare UVs vertex by vertex.
    for uv in uv_layers:
        if (l1[uv].uv - l2.link_loop_next[uv].uv).length_squared > _UV_EPS:
            return False
        if (l1.link_loop_next[uv].uv - l2[uv].uv).length_squared > _UV_EPS:
            return False
    return True


def _evaluate_pair(edge, tri_set, co, direction, settings, internal, restore, uv_layers):
    """Score joining the two triangles on this edge, or None if the join is not allowed.

    Returns (score, f1, f2, quad_verts, edge); quad_verts is the joined quad in winding order.
    """
    loops = edge.link_loops
    if len(loops) != 2:
        return None
    l1, l2 = loops
    f1, f2 = l1.face, l2.face
    if f1 not in tri_set or f2 not in tri_set:
        return None
    if l1.vert is l2.vert:
        return None  # flipped normals between the two triangles

    a, b, c = l1.vert, l1.link_loop_next.vert, l1.link_loop_prev.vert
    d = l2.link_loop_prev.vert
    if c is d:
        return None

    is_restore = edge in restore
    if edge not in internal and not _passes_delimit(edge, l1, l2, settings['delimit'], uv_layers):
        return None

    pa, pb, pc, pd = co(a), co(b), co(c), co(d)
    n1 = (pb - pa).cross(pc - pa)
    n2 = (pa - pb).cross(pd - pb)
    if n1.length_squared < _EPS or n2.length_squared < _EPS:
        return None
    n1.normalize()
    n2.normalize()
    normal = n1 + n2
    if normal.length_squared < _EPS:
        return None
    normal.normalize()

    face_angle = n1.angle(n2)
    quad = (pb, pc, pa, pd)
    deviation = _max_corner_deviation(quad)
    if not is_restore:
        if face_angle > settings['face_threshold']:
            return None
        if deviation > settings['shape_threshold'] or not _is_convex(quad, normal):
            return None

    score = _blend_score(quad, normal, deviation, face_angle, direction, settings['strength'])
    return score, f1, f2, (b, c, a, d), edge


def _loop_bonus(cand, mate, quad_of, co):
    """How straight the edge loops of already-built neighbour quads run on into this quad.

    Adds up to 1.0 per neighbour quad: at both ends of the shared edge, the quad's
    side edge should continue the neighbour's side edge in a straight line.
    """
    _score, f1, f2, quad, shared = cand
    outer = {}
    for f in (f1, f2):
        for e in f.edges:
            if e is not shared:
                outer[frozenset(e.verts)] = e
    bonus = 0.0
    for i in range(4):
        v, w = quad[i], quad[(i + 1) % 4]
        e = outer.get(frozenset((v, w)))
        if e is None:
            continue
        for g in e.link_faces:
            if g is f1 or g is f2 or g not in mate:
                continue
            neighbour = quad_of[g]
            straightness = 0.0
            for end, other, side in ((v, w, quad[i - 1]), (w, v, quad[(i + 2) % 4])):
                k = neighbour.index(end)
                n_side = neighbour[k - 1] if neighbour[k - 1] is not other else neighbour[(k + 1) % 4]
                a = co(side) - co(end)
                b = co(n_side) - co(end)
                if a.length_squared < _EPS or b.length_squared < _EPS:
                    continue
                straightness += max(0.0, -a.normalized().dot(b.normalized()))
            bonus += 0.5 * straightness
    return bonus


def _propagate_match(candidates, co, loop_weight):
    """Pair triangles best score first, growing coherent quad regions.

    Candidates must be sorted best-first. After each quad is built, the pairs next
    to it are re-scored with a bonus for continuing its edge loops, so neighbouring
    quads line up instead of forming poles. loop_weight 0 is plain greedy.
    """
    by_face = defaultdict(list)
    for i, cand in enumerate(candidates):
        by_face[cand[1]].append(i)
        by_face[cand[2]].append(i)
    base = [cand[0] for cand in candidates]
    current = list(base)
    heap = [(-score, i) for i, score in enumerate(base)]
    heapq.heapify(heap)

    mate, quad_of = {}, {}
    while heap:
        neg_score, i = heapq.heappop(heap)
        if -neg_score != current[i]:
            continue  # stale entry, re-scored since
        _score, f1, f2, quad, _edge = candidates[i]
        if f1 in mate or f2 in mate:
            continue
        mate[f1] = f2
        mate[f2] = f1
        quad_of[f1] = quad_of[f2] = quad
        if loop_weight <= 0.0:
            continue

        touched = set()
        for f in (f1, f2):
            for e in f.edges:
                for g in e.link_faces:
                    if g in mate:
                        continue
                    for j in by_face.get(g, ()):
                        if j in touched:
                            continue
                        touched.add(j)
                        cand = candidates[j]
                        if cand[1] in mate or cand[2] in mate:
                            continue
                        rescored = base[j] + loop_weight * _loop_bonus(cand, mate, quad_of, co)
                        if rescored != current[j]:
                            current[j] = rescored
                            heapq.heappush(heap, (-rescored, j))
    return mate


def _find_augmenting_path(start, adj, mate, score):
    """Alternating path from an unpaired triangle to another unpaired one.

    Searched best-first on score gained (new pairs minus broken pairs), so the
    repair reshuffles the pairs that cost the least flow quality. Returns the
    new pairs to apply, or None.
    """
    parent = {start: None}  # outer triangle -> (previous outer triangle, its new partner)
    seen = {start}
    heap = [(0.0, 0, start)]
    tick = 1
    while heap:
        neg_gain, _, u = heapq.heappop(heap)
        for v in adj[u]:
            if v in seen:
                continue
            w = mate.get(v)
            if w is None:
                pairs = [(u, v)]
                while parent[u] is not None:
                    prev, via = parent[u]
                    pairs.append((prev, via))
                    u = prev
                return pairs
            if w in seen:
                continue
            seen.add(v)
            seen.add(w)
            parent[w] = (u, v)
            gain = -neg_gain + score[u, v] - score[v, w]
            heapq.heappush(heap, (-gain, tick, w))
            tick += 1
        if len(seen) > _AUGMENT_BUDGET:
            return None
    return None


def _minimize_leftovers(tris, adj, mate, score):
    """Re-pair along alternating paths so fewer triangles stay unpaired."""
    for _ in range(_AUGMENT_ROUNDS):
        improved = False
        for f in tris:
            if f in mate or not adj.get(f):
                continue
            path = _find_augmenting_path(f, adj, mate, score)
            if path:
                for u, v in path:
                    mate[u] = v
                    mate[v] = u
                improved = True
        if not improved:
            break


def rebuild(bm, faces, matrix_world, direction, *, reflow_quads=True, strength=0.75,
            face_threshold=math.radians(40.0), shape_threshold=math.radians(60.0),
            loop_weight=0.35, minimize_tris=False, delimit=DEFAULT_DELIMIT):
    """Rebuild the given faces into quads that follow `direction` (world space).

    Returns (result_faces, stats) where stats holds before/after face counts.
    """
    faces = [f for f in faces if f.is_valid]
    direction = direction.normalized()
    before = _count_sides(faces)

    world = {}

    def co(v):
        p = world.get(v)
        if p is None:
            p = world[v] = matrix_world @ v.co
        return p

    work, internal, restore = _triangulate(bm, faces, co, direction, reflow_quads)
    tris = [f for f in work if len(f.verts) == 3]
    tri_set = set(tris)

    settings = {
        'strength': strength,
        'face_threshold': face_threshold,
        'shape_threshold': shape_threshold,
        'delimit': delimit,
    }
    uv_layers = list(bm.loops.layers.uv.values()) if 'UV' in delimit else []

    candidates = []
    seen = set()
    for f in tris:
        for e in f.edges:
            if e in seen:
                continue
            seen.add(e)
            cand = _evaluate_pair(e, tri_set, co, direction, settings, internal, restore, uv_layers)
            if cand:
                candidates.append(cand)

    candidates.sort(key=lambda c: c[0], reverse=True)
    mate = _propagate_match(candidates, co, loop_weight)

    if minimize_tris:
        adj = defaultdict(list)
        score = {}
        for pair_score, f1, f2, _quad, _edge in candidates:
            adj[f1].append(f2)
            adj[f2].append(f1)
            score[f1, f2] = score[f2, f1] = pair_score
        _minimize_leftovers(tris, adj, mate, score)

    joined = []
    done = set()
    for f1, f2 in mate.items():
        if f1 in done:
            continue
        done.add(f1)
        done.add(f2)
        try:
            new_face = bmesh.utils.face_join([f1, f2], True)
        except (ValueError, RuntimeError):
            new_face = None
        if new_face is not None:
            joined.append(new_face)

    result = [f for f in work if f.is_valid]
    result.extend(f for f in joined if f.is_valid)
    result = list(dict.fromkeys(result))

    stats = {
        'before': before,
        'after': _count_sides(result),
    }
    return result, stats

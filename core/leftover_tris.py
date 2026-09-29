"""Clean up triangles left over after directional quad pairing.

Fixes are applied to pairs of leftover triangles, cheapest first:

* Re-split (no vertex change): two triangles one quad apart form a hexagon with
  that quad, which is re-split into two quads along its best diagonal.
* Walk and join (removes vertices): collapsing the edge between a triangle and
  the next quad turns that quad into a triangle, so the triangle "walks" one step.
  After walking k quads it meets the other triangle and the two join into a quad.
  Costs k vertices. Two touching triangles that cannot join are removed by
  collapsing their shared edge (1 vertex).

Every collapse is simulated first: faces around it must keep their side count,
edges must stay manifold, no neighbour may flip or shrink badly, and the final
quad must pass the quad shape limits. Only geometry fully inside the region is
touched, so the region border (selection boundary), mesh borders and delimited
edges stay as they are.
"""
import itertools
from collections import defaultdict

import bmesh
from mathutils import Vector

from .directional_quads import _passes_delimit, score_quad

_EPS = 1e-12
_UV_EPS = 1e-10
_MIN_NORMAL_DOT = 0.5    # reject collapses that tilt a neighbour face by more than 60 degrees
_MIN_AREA_RATIO = 0.2    # ... or shrink it below 20% of its area
_FOLD_DOT = -0.2         # ... or fold two neighbours past ~100 degrees when they were not before
_MAX_PASSES = 4


def _polygon_normal(points):
    """Newell normal; its length is twice the polygon area."""
    n = Vector()
    count = len(points)
    for i in range(count):
        n += points[i].cross(points[(i + 1) % count])
    return n


def _other_face(edge, face):
    faces = edge.link_faces
    if len(faces) != 2:
        return None
    return faces[1] if faces[0] is face else faces[0]


def _edge_ok(edge, delimit, uv_layers):
    loops = edge.link_loops
    return len(loops) == 2 and _passes_delimit(edge, loops[0], loops[1], delimit, uv_layers)


# --- Re-split: tri + quad + tri -> two quads -----------------------------------

def _hexagon(t1, quad, t2, e1, e2):
    """Boundary of t1 + quad + t2 as 6 vertices in winding order, or None if not a simple hexagon."""
    nxt = {}
    for f in (t1, quad, t2):
        for loop in f.loops:
            if loop.edge is e1 or loop.edge is e2:
                continue
            if loop.vert in nxt:
                return None
            nxt[loop.vert] = loop.link_loop_next.vert
    if len(nxt) != 6:
        return None
    cycle = [next(iter(nxt))]
    for _ in range(5):
        cycle.append(nxt[cycle[-1]])
    if nxt[cycle[-1]] is not cycle[0] or len(set(cycle)) != 6:
        return None
    return cycle


def _resplit_options(tris, region, co, direction, settings, delimit, uv_layers):
    """Yield (score, t1, quad, t2, split_a, split_b) for triangle pairs one quad apart."""
    tri_set = set(tris)
    seen = set()
    for t1 in tris:
        for e1 in t1.edges:
            quad = _other_face(e1, t1)
            if quad is None or quad not in region or len(quad.verts) != 4:
                continue
            for e2 in quad.edges:
                if e2 is e1:
                    continue
                t2 = _other_face(e2, quad)
                if t2 is None or t2 is t1 or t2 not in tri_set:
                    continue
                key = (quad, frozenset((t1, t2)))
                if key in seen:
                    continue
                seen.add(key)
                if not (_edge_ok(e1, delimit, uv_layers) and _edge_ok(e2, delimit, uv_layers)):
                    continue
                cycle = _hexagon(t1, quad, t2, e1, e2)
                if cycle is None:
                    continue
                pts = [co(v) for v in cycle]
                best = None
                for i in range(3):
                    va, vb = cycle[i], cycle[i + 3]
                    if any(vb in e.verts for e in va.link_edges):
                        continue  # already connected elsewhere
                    sa = score_quad(pts[i:i + 4], direction, *settings)
                    sb = score_quad([pts[i + 3], pts[(i + 4) % 6], pts[(i + 5) % 6], pts[i]], direction, *settings)
                    if sa is None or sb is None:
                        continue
                    if best is None or sa + sb > best[0]:
                        best = (sa + sb, va, vb)
                if best is not None:
                    yield best[0], t1, quad, t2, best[1], best[2]


def _resplit_pass(region, co, direction, settings, delimit, uv_layers):
    """Re-split tri + quad + tri hexagons into two quads. Returns (region, fixed_pairs)."""
    tris = [f for f in region if len(f.verts) == 3]
    options = sorted(_resplit_options(tris, set(region), co, direction, settings, delimit, uv_layers),
                     key=lambda o: o[0], reverse=True)
    used, added, fixed = set(), [], 0
    for _score, t1, quad, t2, va, vb in options:
        if t1 in used or quad in used or t2 in used:
            continue
        try:
            hexagon = bmesh.utils.face_join([t1, quad, t2], True)
        except (ValueError, RuntimeError):
            hexagon = None
        if hexagon is None:
            continue
        used.update((t1, quad, t2))
        added.append(hexagon)
        try:
            new_face, _loop = bmesh.utils.face_split(hexagon, va, vb)
        except (ValueError, RuntimeError):
            continue
        if new_face is not None:
            added.append(new_face)
            fixed += 1
    region = [f for f in region if f.is_valid]
    region.extend(f for f in added if f.is_valid)
    return list(dict.fromkeys(region)), fixed


# --- Walk and join: collapse along a quad path between two triangles -----------

def _vertex_is_free(v, region, delimit, uv_layers):
    """True when moving this vertex cannot change anything outside the region or across a delimit."""
    if v.is_boundary:
        return False
    material = None
    for f in v.link_faces:
        if f not in region:
            return False
        if 'MATERIAL' in delimit:
            if material is None:
                material = f.material_index
            elif f.material_index != material:
                return False
    for e in v.link_edges:
        if not e.is_manifold:
            return False
        if 'SEAM' in delimit and e.seam:
            return False
        if 'SHARP' in delimit and not e.smooth:
            return False
    for uv in uv_layers:
        first = None
        for loop in v.link_loops:
            value = loop[uv].uv
            if first is None:
                first = value.copy()
            elif (value - first).length_squared > _UV_EPS:
                return False
    return True


def _find_paths(tris, region, max_quads):
    """Yield (faces, edges) for the shortest path from each leftover triangle through
    0..max_quads quads to another leftover triangle, once in each walking direction.
    faces = [t1, q1..qk, t2] and edges[i] is shared by faces[i] and faces[i + 1]."""
    tri_set = set(tris)
    seen = set()
    for start in tris:
        parent = {start: None}
        frontier = [start]
        for depth in range(max_quads + 1):
            next_frontier = []
            for f in frontier:
                for e in f.edges:
                    g = _other_face(e, f)
                    if g is None or g in parent or g not in region:
                        continue
                    if g in tri_set:
                        key = frozenset((start, g))
                        if key in seen:
                            continue
                        seen.add(key)
                        faces, edges = [g], [e]
                        cur = f
                        while parent[cur] is not None:
                            prev, via = parent[cur]
                            faces.append(cur)
                            edges.append(via)
                            cur = prev
                        faces.append(start)
                        yield faces[::-1], edges[::-1]
                        if len(faces) > 2:
                            yield faces, edges  # walking from the other end lands differently
                        continue
                    if len(g.verts) != 4 or depth == max_quads:
                        continue
                    parent[g] = (f, e)
                    next_frontier.append(g)
            frontier = next_frontier


def _neighbours_ok(neighbours, pos, co, raw_normal, dying, last_quad):
    """No neighbour may flip, shrink badly, or fold against the face next to it."""
    new_normals = {}
    for f in neighbours:
        n_old = raw_normal(f)
        n_new = _polygon_normal([pos[v] if v in pos else co(v) for v in f.verts])
        if (n_old.length_squared < _EPS or n_new.length < _MIN_AREA_RATIO * n_old.length
                or n_old.normalized().dot(n_new.normalized()) < _MIN_NORMAL_DOT):
            return False
        new_normals[f] = n_new.normalized()
    for f in neighbours:
        for e in f.edges:
            g = _other_face(e, f)
            if g is None or g in dying or g is last_quad:
                continue
            g_old = raw_normal(g).normalized()
            new_dot = new_normals[f].dot(new_normals.get(g) or g_old)
            if new_dot < _FOLD_DOT and new_dot < raw_normal(f).normalized().dot(g_old) - 0.05:
                return False
    return True


def _plan_walk(faces, edges, co, region, direction, settings, delimit, uv_layers):
    """Simulate walking faces[0] along the path to faces[-1].

    Each merged point may land on the group's centre or on one of its vertices;
    the landing that gives the best final quad wins. Returns
    (vertex_cost, quality, collapse_edges, targets, join_pair) or None when unsafe.
    targets are (vertices, local_position) to move before collapsing. join_pair is
    (last_quad, t2) to join afterwards, or None when the two triangles touch and
    simply collapse away together.
    """
    k = len(faces) - 2
    if len(set(faces)) != len(faces):
        return None
    if k == 0:
        collapse, dying, join = [edges[0]], set(faces), None
    else:
        collapse, dying, join = edges[:k], set(faces[:k]), (faces[k], faces[k + 1])
        if not _edge_ok(edges[k], delimit, uv_layers):
            return None

    # Merge groups: collapsed edges that share vertices merge into one point.
    rep = {}

    def find(v):
        while rep[v] is not v:
            v = rep[v]
        return v

    for e in collapse:
        for v in e.verts:
            rep.setdefault(v, v)
        a, b = find(e.verts[0]), find(e.verts[1])
        rep[b] = a
    if not all(_vertex_is_free(v, region, delimit, uv_layers) for v in rep):
        return None
    groups = defaultdict(list)
    for v in rep:
        groups[find(v)].append(v)
    groups = list(groups.values())
    merged = {v: members[0] for members in groups for v in members}

    def after(v):
        return merged.get(v, v)

    # Topology checks (independent of where the merged points land).
    # Every surviving edge must stay manifold once duplicates merge.
    live_faces = defaultdict(set)
    for v in rep:
        for e in v.link_edges:
            key = frozenset((after(e.verts[0]), after(e.verts[1])))
            if len(key) == 2:
                live_faces[key].update(f for f in e.link_faces if f not in dying)
    if any(len(fs) > 2 for fs in live_faces.values()):
        return None
    # Surviving faces keep their side count; the last quad becomes a triangle.
    last_quad = join[0] if join is not None else None
    neighbours = [f for f in dict.fromkeys(f for v in rep for f in v.link_faces) if f not in dying]
    for f in neighbours:
        expected = 3 if f is last_quad else len(f.verts)
        if len({after(v) for v in f.verts}) != expected:
            return None
    neighbours = [f for f in neighbours if f is not last_quad]
    if not neighbours:
        return None
    ring = [co(v) for f in neighbours for v in f.verts]
    ring_length = sum((ring[i] - ring[i - 1]).length for i in range(len(ring))) / len(ring)

    quad_verts = None
    if join is not None:
        shared = edges[k]
        if after(shared.verts[0]) is after(shared.verts[1]):
            return None
        loop = next(l for l in last_quad.loops if l.edge is shared)
        cycle, cur = [], loop.link_loop_next
        while cur is not loop:
            v = after(cur.vert)
            if not cycle or cycle[-1] is not v:
                cycle.append(v)
            cur = cur.link_loop_next
        end = after(loop.vert)
        if cycle[-1] is not end:
            cycle.append(end)
        if len(cycle) != 3:
            return None
        quad_verts = cycle + [loop.link_loop_radial_next.link_loop_prev.vert]  # + t2's free corner

    # Landing choices per group: centre, or on one of its vertices.
    choices = []
    for members in groups:
        centre_local = sum((v.co for v in members), Vector()) / len(members)
        centre_world = sum((co(v) for v in members), Vector()) / len(members)
        choices.append([(centre_world, centre_local)] + [(co(v), v.co.copy()) for v in members])
    combos = [[c[0] for c in choices]]
    if len(choices) <= 2:
        combos = [list(c) for c in itertools.product(*choices)]

    raw_normals = {}

    def raw_normal(f):
        n = raw_normals.get(f)
        if n is None:
            n = raw_normals[f] = _polygon_normal([co(v) for v in f.verts])
        return n

    # Rank landings by the cheap part (final quad, how far points move), then run
    # the neighbour checks in that order and keep the first landing that passes.
    ranked = []
    for combo in combos:
        pos = {v: world for members, (world, _local) in zip(groups, combo) for v in members}
        quality = 0.0
        if quad_verts is not None:
            quality = score_quad([pos.get(v, co(v)) for v in quad_verts], direction, *settings)
            if quality is None:
                continue
        moved = sum((pos[v] - co(v)).length for v in rep) / len(rep)
        ranked.append((quality - 0.25 * moved / ring_length, pos, combo))
    ranked.sort(key=lambda r: r[0], reverse=True)

    for quality, pos, combo in ranked:
        if _neighbours_ok(neighbours, pos, co, raw_normal, dying, last_quad):
            return max(k, 1), quality, collapse, [(members, local) for members, (_w, local) in zip(groups, combo)], join
    return None


def _walk_pass(bm, region, co, direction, settings, max_quads, delimit, uv_layers):
    """Walk-and-join leftover triangle pairs. Returns (region, changed_any)."""
    region_set = set(region)
    tris = [f for f in region if len(f.verts) == 3]
    if len(tris) < 2:
        return region, False

    options = []
    for faces, edges in _find_paths(tris, region_set, max_quads):
        plan = _plan_walk(faces, edges, co, region_set, direction, settings, delimit, uv_layers)
        if plan is not None:
            options.append((plan, faces))
    options.sort(key=lambda o: (o[0][0], -o[0][1]))

    locked, used, collapse, joins = set(), set(), [], []
    for (_cost, _quality, edges, targets, join), faces in options:
        ring = {x for e in edges for v in e.verts for f in v.link_faces for x in f.verts}
        ring.update(v for f in faces for v in f.verts)
        if ring & locked or any(f in used for f in faces):
            continue
        locked |= ring
        used.update(faces)
        for members, local in targets:
            for v in members:
                v.co = local
        collapse.extend(edges)
        if join is not None:
            joins.append(join)
    if not collapse:
        return region, False

    # Collapse edits faces in place and only removes the faces that degenerate.
    bmesh.ops.collapse(bm, edges=collapse, uvs=True)
    added = []
    for last_quad, t2 in joins:
        if last_quad.is_valid and t2.is_valid and len(last_quad.verts) == 3:
            try:
                joined = bmesh.utils.face_join([last_quad, t2], True)
            except (ValueError, RuntimeError):
                joined = None
            if joined is not None:
                added.append(joined)
    region = [f for f in region if f.is_valid]
    region.extend(f for f in added if f.is_valid)
    return list(dict.fromkeys(region)), True


def cleanup(bm, faces, matrix_world, direction, *, strength=0.75, face_threshold=0.698,
            shape_threshold=1.047, collapse=True, max_quads=3, delimit=frozenset()):
    """Fix leftover triangles inside `faces` (see module docstring).

    Returns (result_faces, stats) with stats 'resplit' (triangle pairs turned into
    quads without vertex changes) and 'removed_verts' (vertices removed by collapses).
    """
    direction = direction.normalized()
    settings = (strength, face_threshold, shape_threshold)
    uv_layers = list(bm.loops.layers.uv.values()) if 'UV' in delimit else []
    region = [f for f in faces if f.is_valid]
    verts_before = len(bm.verts)
    resplit = 0

    for _ in range(_MAX_PASSES):
        world = {}

        def co(v):
            p = world.get(v)
            if p is None:
                p = world[v] = matrix_world @ v.co
            return p

        region, fixed = _resplit_pass(region, co, direction, settings, delimit, uv_layers)
        resplit += fixed
        walked = False
        if collapse:
            region, walked = _walk_pass(bm, region, co, direction, settings, max_quads, delimit, uv_layers)
        if not fixed and not walked:
            break

    return region, {'resplit': resplit, 'removed_verts': verts_before - len(bm.verts)}

"""Quad Patch, part 1: read the patch border, pick corners, make opposite sides match.

The selected faces must form one patch without holes. Its border is cut into four
sides at the sharpest corners; corners may slide a little when that balances
opposite sides for free. When opposite sides still differ:

* collapse (tried first): a border edge of the longer side is collapsed to take
  one of the patch's triangles away, removing one vertex from the side. 'BORDER'
  uses triangles with that edge; 'INNER' also triangles further in, whose edge
  ring runs straight across quads to that edge (the reverse of splitting it).
  The face outside the edge, if any (the edge may be the mesh's open border),
  loses a corner: a triangle there goes away, a quad becomes a triangle. The
  merged vertex sits in the middle of the edge (or stays on the corner when the
  edge ends at one); UVs, vertex weights and shape keys are interpolated there,
  per UV island, so nothing around it stretches.
* cut_neighbours on (tried next): at a corner of the shorter side, the face just
  outside the next side is cut in two and its corner triangle joins the patch. The
  shorter side gains that face's vertex as its new end, the next side keeps its
  length, no border edge is split and the rest of that face stays, one corner
  smaller (a quad becomes a triangle). Each corner moves once at most.
* split_border on: the shorter side's border edges are split exactly where the
  longer side has vertices with no partner, so grid lines run straight across.
  Only that edge is split; the face outside the patch simply gains a vertex.
* split_border off: the border is left alone and extra grid lines are merged onto
  existing border vertices, which leaves one triangle next to the border for each
  missing vertex.
"""
import itertools
import math

import bmesh
from mathutils import geometry

_CANDIDATE_CORNERS = 16
_INF = float('inf')
_UV_EPS = 1e-8


class PatchError(Exception):
    """The selection cannot be turned into a patch. The message is shown to the user."""


def border_loop(faces):
    """Return (verts, edges) of the single border loop, walked with the patch on the left."""
    region = set(faces)
    nxt, order = {}, []
    for f in faces:
        for loop in f.loops:
            inside = sum(1 for g in loop.edge.link_faces if g in region)
            if inside > 2:
                raise PatchError("Selection has non-manifold edges")
            if inside == 1:
                if loop.vert in nxt:
                    raise PatchError("Selection border touches itself; select a simple patch")
                nxt[loop.vert] = (loop.link_loop_next.vert, loop.edge)
                order.append(loop.vert)
    if not nxt:
        raise PatchError("Selection has no border; select an open patch of faces")

    start = order[0]
    verts, edges = [start], []
    v = start
    while True:
        w, e = nxt[v]
        edges.append(e)
        if w is start:
            break
        if w not in nxt or len(verts) > len(nxt):
            raise PatchError("Could not follow the selection border")
        verts.append(w)
        v = w
    all_verts = {v for f in faces for v in f.verts}
    all_edges = {e for f in faces for e in f.edges}
    if len(verts) != len(nxt) or len(all_verts) - len(all_edges) + len(faces) != 1:
        raise PatchError("Select one connected patch without holes")
    if len(verts) < 4:
        raise PatchError("Patch border needs at least 4 vertices")
    return verts, edges


def turn_angles(verts, region, co):
    """How sharply the border turns at each vertex: pi minus the patch's interior angle."""
    turns = []
    for v in verts:
        inside = 0.0
        for loop in v.link_loops:
            if loop.face in region:
                a = co(loop.link_loop_prev.vert) - co(v)
                b = co(loop.link_loop_next.vert) - co(v)
                if a.length_squared > 0.0 and b.length_squared > 0.0:
                    inside += a.angle(b)
        turns.append(math.pi - inside)
    return turns


def choose_corners(verts, turns, mismatch_cost):
    """Pick 4 border indices (ascending) that turn sharply and balance opposite sides."""
    n = len(verts)
    candidates = sorted(sorted(range(n), key=lambda i: -turns[i])[:min(n, _CANDIDATE_CORNERS)])
    best = None
    for c in itertools.combinations(candidates, 4):
        counts = (c[1] - c[0], c[2] - c[1], c[3] - c[2], n - c[3] + c[0])
        mismatch = abs(counts[0] - counts[2]) + abs(counts[1] - counts[3])
        score = sum(turns[i] for i in c) - mismatch_cost * mismatch
        if best is None or score > best[0] + 1e-9:
            best = (score, c)
    return best[1]


def side_between(verts, a, b):
    """Border vertices from index a to b inclusive, walking forward (wrapping)."""
    n = len(verts)
    out, i = [verts[a]], a
    while i != b:
        i = (i + 1) % n
        out.append(verts[i])
    return out


def arc_params(side, co):
    """Normalised arc length (0..1) of each vertex along a side."""
    d = [0.0]
    for p, q in zip(side, side[1:]):
        d.append(d[-1] + (co(q) - co(p)).length)
    total = d[-1] or 1.0
    return [x / total for x in d]


def match_injective(x, t):
    """Give each x (the shorter side) its own t index, in order, ends fixed. Returns indices."""
    m, n = len(x) - 1, len(t) - 1
    dp = [[_INF] * (n + 1) for _ in range(m + 1)]
    back = [[-1] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = 0.0
    for a in range(1, m + 1):
        best, best_k = _INF, -1
        for k in range(1, n + 1):
            if dp[a - 1][k - 1] < best:
                best, best_k = dp[a - 1][k - 1], k - 1
            if best < _INF:
                dp[a][k] = best + abs(x[a] - t[k])
                back[a][k] = best_k
    ks, k = [n], n
    for a in range(m, 0, -1):
        k = back[a][k]
        ks.append(k)
    return ks[::-1]


def match_surjective(x, t):
    """Map each t index onto an x vertex, in order, every x used, ends fixed. Returns x indices."""
    m, n = len(x) - 1, len(t) - 1
    dp = [[_INF] * (m + 1) for _ in range(n + 1)]
    back = [[-1] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = abs(t[0] - x[0])
    for k in range(1, n + 1):
        for a in range(m + 1):
            stay = dp[k - 1][a]
            step = dp[k - 1][a - 1] if a > 0 else _INF
            prev, best = (a, stay) if stay <= step else (a - 1, step)
            if best < _INF:
                dp[k][a] = best + abs(t[k] - x[a])
                back[k][a] = prev
    phi, a = [m], m
    for k in range(n, 0, -1):
        a = back[k][a]
        phi.append(a)
    return phi[::-1]


def edge_between(a, b):
    for e in a.link_edges:
        if e.other_vert(a) is b:
            return e
    return None


def uv_continuous(edge, uv_layers):
    """False when the two faces of `edge` disagree on its UVs (a UV island border)."""
    loops = edge.link_loops
    if len(loops) != 2:
        return True
    l1, l2 = loops
    for uv in uv_layers:
        if ((l1[uv].uv - l2.link_loop_next[uv].uv).length_squared > _UV_EPS
                or (l1.link_loop_next[uv].uv - l2[uv].uv).length_squared > _UV_EPS):
            return False
    return True


def _loop_sides(faces, corners):
    """The border loop and its four sides in loop order: corner i to corner i + 1."""
    loop, _ = border_loop(faces)
    idx = [loop.index(c) for c in corners]
    return loop, [side_between(loop, idx[i], idx[(i + 1) % 4]) for i in range(4)]


def _corner_cut(corner, along, region, patch_verts, co, uv_layers):
    """Plan taking the corner triangle off the outside face across border edge corner-along.

    `new`, the face's other neighbour of `corner`, becomes the patch corner and the
    triangle corner-new-along joins the patch. Returns (face, new, score) or None
    when the face cannot be cut cleanly. Higher scores leave `corner` straighter and
    the new corner closer to square.
    """
    edge = edge_between(corner, along)
    if edge is None or edge.seam or len(edge.link_faces) != 2 or not uv_continuous(edge, uv_layers):
        return None
    face = next((f for f in edge.link_faces if f not in region), None)
    if face is None or face.hide:
        return None
    ring = list(face.verts)
    i = ring.index(corner)
    prev, nxt = ring[i - 1], ring[(i + 1) % len(ring)]
    new = nxt if prev is along else prev
    if new in patch_verts or (len(ring) > 3 and edge_between(new, along) is not None):
        return None
    # The cut must run inside the face: both parts face the same way as the whole face.
    normal = geometry.normal([v.co for v in ring])
    parts = [[prev.co, corner.co, nxt.co]]
    if len(ring) > 3:
        parts.append([v.co for v in ring[i + 1:] + ring[:i]])
    if any(geometry.normal(p).dot(normal) <= 0.0 for p in parts):
        return None
    a, b, c = co(corner), co(new), co(along)
    if min((b - a).length, (c - a).length, (c - b).length) <= 0.0:
        return None
    straight = abs(turn_angles([corner], region, co)[0] - (b - a).angle(c - a))
    square = abs((a - b).angle(c - b) - math.pi / 2)
    return face, new, -(straight + square)


def _cut(face, corner, new, along):
    """Split `face` along new-along and return the triangle holding `corner`."""
    if len(face.verts) == 3:
        return face
    other, _loop = bmesh.utils.face_split(face, new, along)
    return other if corner in other.verts else face


def _cut_corners(faces, corners, co, uv_layers, flip=False):
    """Balance opposite sides by taking corner triangles off the faces beside the shorter side.

    Each step cuts at whichever end of the side scores best, or worst with `flip`.
    Returns (faces, corners, cut faces) with the triangles added to the patch.
    """
    pick = min if flip else max
    faces, corners, cut, moved = list(faces), list(corners), [], set()
    for k in (0, 1):
        while True:
            _loop, s = _loop_sides(faces, corners)
            if len(s[k]) == len(s[k + 2]):
                break
            short = k if len(s[k]) < len(s[k + 2]) else k + 2
            end = (short + 1) % 4
            region = set(faces)
            patch_verts = {v for f in faces for v in f.verts}
            options = []
            # Its last corner moves along the next side, its first along the previous one.
            for index, corner, along in ((end, s[short][-1], s[end][1]),
                                         (short, s[short][0], s[short - 1][-2])):
                if index in moved:
                    continue
                found = _corner_cut(corner, along, region, patch_verts, co, uv_layers)
                if found:
                    face, new, score = found
                    options.append((score, index, face, corner, new, along))
            if not options:
                break
            _score, index, face, corner, new, along = pick(options, key=lambda o: o[0])
            cut.append(_cut(face, corner, new, along))
            faces.append(cut[-1])
            corners[index] = new
            moved.add(index)
    return faces, corners, cut


def _match_cost(t_short, t_long):
    """How far apart two sides' vertices sit when the shorter one is matched onto the longer."""
    ks = match_injective(t_short, t_long)
    return sum(abs(x - t_long[k]) for x, k in zip(t_short, ks))


def _tri_border_edges(faces, inner):
    """Border edges whose collapse takes one of the patch's triangles away: {edge: quads between}.

    A triangle's own border edges count (0 quads). With `inner`, so does the border
    edge reached from any triangle edge by walking straight across quads (its edge
    ring): collapsing that ring is the reverse of splitting the border edge.
    """
    region = set(faces)
    found = {}
    for tri in faces:
        if len(tri.verts) != 3:
            continue
        for edge in tri.edges:
            face, quads = tri, 0
            while True:
                across = [f for f in edge.link_faces if f in region and f is not face]
                if not across:
                    found[edge] = min(found.get(edge, quads), quads)
                    break
                face = across[0]
                if not inner or len(across) > 1 or len(face.verts) != 4 or quads >= len(faces):
                    break
                loop = next(l for l in face.loops if l.edge is edge)
                edge = loop.link_loop_next.link_loop_next.edge
                quads += 1
    return found


def _collapse_plan(a, b, corners, region, patch_verts):
    """How to collapse border edge a-b: (keep, gone, fraction toward gone), or None when
    the collapse would not stay clean."""
    if a in corners and b in corners:
        return None
    edge = edge_between(a, b)
    if edge is None or len(edge.link_faces) > 2:
        return None
    inside = next((f for f in edge.link_faces if f in region), None)
    outside = next((f for f in edge.link_faces if f not in region), None)  # None on the mesh's open edge
    if inside is None:
        return None
    around = set(a.link_faces) | set(b.link_faces)
    # Only the faces on the edge may hold both ends, and nothing hidden or in another patch is touched.
    if set(a.link_faces) & set(b.link_faces) != {inside, outside} - {None}:
        return None
    if any(f.hide or (f.select and f not in region) for f in around):
        return None
    shared = set()
    if len(inside.verts) == 3:  # the patch triangle goes away
        shared.add(next(v for v in inside.verts if v is not a and v is not b))
    if outside is not None and len(outside.verts) == 3:  # it goes away too; a bigger face loses a corner
        apex = next(v for v in outside.verts if v is not a and v is not b)
        if apex in patch_verts:
            return None
        shared.add(apex)
    if ({e.other_vert(a) for e in a.link_edges} & {e.other_vert(b) for e in b.link_edges}) - shared:
        return None

    keep, gone, fraction = (a, b, 0.0) if a in corners else (b, a, 0.0) if b in corners else (a, b, 0.5)
    # No face that stays may flip.
    point = keep.co.lerp(gone.co, fraction)
    for f in around:
        if len(f.verts) == 3 and (f is inside or f is outside):
            continue
        after = [point if v is a or v is b else v.co for v in f.verts]
        if geometry.normal(after).dot(geometry.normal([v.co for v in f.verts])) <= 0.0:
            return None
    return keep, gone, fraction


def _collapse(bm, faces, keep, gone, fraction, uv_layers):
    """Merge `gone` into `keep` at `fraction` along their edge; returns the patch faces after.

    UVs are interpolated per UV island: each corner of the merged vertex takes the
    UV that the collapsed edge had at that point on its own side (inside or outside
    the patch). Corners on neither side's island keep their UV. Vertex weights and
    shape keys are interpolated the same way.
    """
    region = set(faces)
    edge = edge_between(keep, gone)
    edge_faces = [f for f in edge.link_faces if f in region] + [f for f in edge.link_faces if f not in region]

    def edge_uvs(face, layer):
        uvs = {l.vert: l[layer].uv.copy() for l in face.loops}
        return uvs[keep], uvs[gone]

    islands = [[edge_uvs(f, layer) for f in edge_faces] for layer in uv_layers]
    deform = bm.verts.layers.deform.active
    weights = None
    if deform:
        wk, wg = dict(keep[deform].items()), dict(gone[deform].items())
        weights = {g: wk.get(g, 0.0) * (1.0 - fraction) + wg.get(g, 0.0) * fraction for g in set(wk) | set(wg)}
    shapes = list(bm.verts.layers.shape.values())
    shape_co = [keep[s].lerp(gone[s], fraction) for s in shapes]
    co = keep.co.lerp(gone.co, fraction)
    # Faces may be rebuilt by the weld, so find the patch again by corners.
    corner_sets = [{keep if v is gone else v for v in f.verts} for f in faces]

    bmesh.ops.weld_verts(bm, targetmap={gone: keep})

    keep.co = co
    for s, value in zip(shapes, shape_co):
        keep[s] = value
    if deform:
        dvert = keep[deform]
        dvert.clear()
        for group, w in weights.items():
            if w > 1e-6:
                dvert[group] = w
    for layer, pairs in zip(uv_layers, islands):
        for loop in keep.link_loops:
            uv = loop[layer].uv
            for uv_keep, uv_gone in pairs:
                if (uv - uv_keep).length_squared <= _UV_EPS or (uv - uv_gone).length_squared <= _UV_EPS:
                    loop[layer].uv = uv_keep.lerp(uv_gone, fraction)
                    break

    result = []
    for verts in corner_sets:
        if len(verts) < 3:
            continue
        face = next((f for f in next(iter(verts)).link_faces if set(f.verts) == verts), None)
        if face is not None:
            result.append(face)
    return result


def _collapse_tris(bm, faces, corners, co, uv_layers, inner):
    """Balance opposite sides by collapsing border edges of the longer side that take one
    of the patch's triangles away (see _tri_border_edges). Edges between two non-corner
    vertices go first, then the matching of the two sides decides, then the fewest
    quads in between. Only the border edge itself is collapsed: the patch interior is
    rebuilt anyway and keeps its shape for that. Returns (faces, number collapsed)."""
    collapsed = 0
    for k in (0, 1):
        while True:
            _loop, s = _loop_sides(faces, corners)
            a_side, b_side = s[k], s[k + 2][::-1]  # both running the same way
            if len(a_side) == len(b_side):
                break
            long_, short = (a_side, b_side) if len(a_side) > len(b_side) else (b_side, a_side)
            t_short = arc_params(short, co)
            region = set(faces)
            patch_verts = {v for f in faces for v in f.verts}
            candidates = _tri_border_edges(faces, inner)
            best = None
            for a, b in zip(long_, long_[1:]):
                quads = candidates.get(edge_between(a, b))
                if quads is None:
                    continue
                found = _collapse_plan(a, b, corners, region, patch_verts)
                if found is None:
                    continue
                keep, gone, fraction = found
                point = co(keep).lerp(co(gone), fraction)
                t_long = arc_params([v for v in long_ if v is not gone],
                                    lambda v, keep=keep, point=point: point if v is keep else co(v))
                rank = (keep in corners, _match_cost(t_short, t_long), quads)
                if best is None or rank < best[0]:
                    best = (rank, found)
            if best is None:
                break
            faces = _collapse(bm, faces, *best[1], uv_layers)
            collapsed += 1
    return faces, collapsed


def _split_plans(short_side, t_short, t_long):
    """Where to split the shorter side: [(vert_a, vert_b, [fractions from a])]."""
    ks = match_injective(t_short, t_long)
    plans = []
    for a in range(len(short_side) - 1):
        k0, k1 = ks[a], ks[a + 1]
        if k1 - k0 > 1:
            span = (t_long[k1] - t_long[k0]) or 1.0
            fractions = [(t_long[k] - t_long[k0]) / span for k in range(k0 + 1, k1)]
            plans.append((short_side[a], short_side[a + 1], fractions))
    return plans


def apply_split(va, vb, fractions):
    """Split the edge va-vb at the given fractions (measured from va, ascending)."""
    done = 0.0
    for f in fractions:
        edge = edge_between(va, vb)
        if edge is None:
            return
        local = (f - done) / (1.0 - done)
        _new_edge, new_vert = bmesh.utils.edge_split(edge, va, min(max(local, 0.01), 0.99))
        va, done = new_vert, f


def pick_corners(faces, co, split_border):
    """The four patch corners, in border loop order."""
    verts, _edges = border_loop(faces)
    turns = turn_angles(verts, set(faces), co)
    return [verts[i] for i in choose_corners(verts, turns, 0.35 if split_border else 0.6)]


def reshape(bm, faces, corners, matrix_world, uv_layers, *, collapse='NONE', cut_neighbours=False,
            flip_cut=False):
    """Balance opposite sides by changing the patch itself, before any border edge is split.

    Collapses triangles ('BORDER': only those on the border, 'INNER': also those
    further in), then cuts neighbouring faces (flip_cut: at the other end of a
    short side than the automatic pick). Returns (faces, corners, collapsed count,
    cut count).
    """
    def co(v):  # not cached: collapsing moves vertices
        return matrix_world @ v.co

    faces, collapsed, cut = list(faces), 0, []
    if collapse != 'NONE':
        faces, collapsed = _collapse_tris(bm, faces, corners, co, uv_layers, inner=collapse == 'INNER')
    if cut_neighbours:
        faces, corners, cut = _cut_corners(faces, corners, co, uv_layers, flip_cut)
    return faces, corners, collapsed, len(cut)


def plan(faces, co, split_border, corners=None):
    """Balance sides by splitting border edges when allowed and lay out the grid sides.

    corners: from pick_corners (and reshape); picked here when not given.
    Returns a dict with the border loop, the four grid sides as node lists
    ('bottom' and 'top' run along u, 'left' and 'right' along v), the node
    parameters used to place grid lines, and the number of border splits.
    Node lists may repeat a vertex when the sides still differ.
    """
    if corners is None:
        corners = pick_corners(faces, co, split_border)

    def sides():
        loop, s = _loop_sides(faces, corners)
        # bottom c0->c1 (+u), right c1->c2 (+v), top c2->c3 reversed (+u), left c3->c0 reversed (+v)
        return loop, s[0], s[1], s[2][::-1], s[3][::-1]

    loop, bottom, right, top, left = sides()
    splits = 0
    if split_border:
        plans = []
        for a, b in ((bottom, top), (left, right)):
            if len(a) != len(b):
                short, long_ = (a, b) if len(a) < len(b) else (b, a)
                plans += _split_plans(short, arc_params(short, co), arc_params(long_, co))
        for va, vb, fractions in plans:
            apply_split(va, vb, fractions)
            splits += len(fractions)
        if splits:
            loop, bottom, right, top, left = sides()

    result = {'border': loop, 'corners': corners, 'splits': splits}
    for name_a, name_b, a, b in (('bottom', 'top', bottom, top), ('left', 'right', left, right)):
        ta, tb = arc_params(a, co), arc_params(b, co)
        if len(a) == len(b):
            result[name_a], result[name_b] = a, b
            result[name_a + '_t'], result[name_b + '_t'] = ta, tb
            continue
        # Still unbalanced: merge the extra grid lines onto existing vertices.
        if len(a) < len(b):
            phi = match_surjective(ta, tb)
            result[name_a], result[name_b] = [a[i] for i in phi], b
            result[name_a + '_t'], result[name_b + '_t'] = tb, tb
        else:
            phi = match_surjective(tb, ta)
            result[name_a], result[name_b] = a, [b[i] for i in phi]
            result[name_a + '_t'], result[name_b + '_t'] = ta, ta
    return result

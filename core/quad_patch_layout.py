"""Quad Patch, part 1: read the patch border, pick corners, make opposite sides match.

The selected faces must form one patch without holes. Its border is cut into four
sides at the sharpest corners; corners may slide a little when that balances
opposite sides for free. When opposite sides still differ:

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

_CANDIDATE_CORNERS = 16
_INF = float('inf')


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


def plan(faces, co, split_border):
    """Choose corners and balance sides, splitting border edges when allowed.

    Returns a dict with the border loop, the four grid sides as node lists
    ('bottom' and 'top' run along u, 'left' and 'right' along v), the node
    parameters used to place grid lines, and the number of border splits.
    Node lists may repeat a vertex when splitting is off.
    """
    region = set(faces)
    verts, _edges = border_loop(faces)
    turns = turn_angles(verts, region, co)
    corners = [verts[i] for i in choose_corners(verts, turns, 0.35 if split_border else 0.6)]

    def sides():
        loop, _ = border_loop(faces)
        idx = [loop.index(c) for c in corners]
        s = [side_between(loop, idx[i], idx[(i + 1) % 4]) for i in range(4)]
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
        # Splitting off (or not possible): merge the extra grid lines onto existing vertices.
        if len(a) < len(b):
            phi = match_surjective(ta, tb)
            result[name_a], result[name_b] = [a[i] for i in phi], b
            result[name_a + '_t'], result[name_b + '_t'] = tb, tb
        else:
            phi = match_surjective(tb, ta)
            result[name_a], result[name_b] = a, [b[i] for i in phi]
            result[name_a + '_t'], result[name_b + '_t'] = ta, ta
    return result

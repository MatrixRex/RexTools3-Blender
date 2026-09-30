"""Edge Cleanup: merge the vertices that sit close to the selected edges into those edges.

A vertex is near an edge when it is within Distance of it (of the segment, not the
infinite line), measured in world space so object scale counts. Each near vertex is
merged into the closest point on its nearest edge:

- within Distance of an end of the edge: into that end vertex;
- anywhere else along the edge: the edge is split there and the vertex merged into the
  new vertex, so the faces around it close up onto the edge. Vertices that land within
  Distance of each other along the edge share one split.

An edge whose ends both end up on the selected edges folds onto them. Where it passes
a selected vertex it is split and merged into that vertex too, so a whole row of
vertices merged onto the selected edges closes up the thin faces between them instead
of leaving flat faces behind.

The selected edges' own vertices are what the others merge into and stay put. With
include_selected they are merged too: into another selected edge they come within
Distance of, or into the other end of a selected edge shorter than Distance.
"""
import bmesh
from mathutils.kdtree import KDTree


def _nearest(point, p0, p1):
    """(t, distance): where along p0-p1 the closest point to point lies (0 to 1), and how far it is."""
    d = p1 - p0
    length_sq = d.length_squared
    t = 0.0
    if length_sq > 0.0:
        t = min(max((point - p0).dot(d) / length_sq, 0.0), 1.0)
    return t, (p0 + d * t - point).length


def _tree(verts, co):
    tree = KDTree(len(verts))
    for k, v in enumerate(verts):
        tree.insert(co[v], k)
    tree.balance()
    return tree


def _root(target, v):
    while v in target:
        v = target[v]
    return v


def _link(target, v, t):
    """Merge v into t. Merges chain, so two vertices near each other's edges only merge once."""
    a, b = _root(target, v), _root(target, t)
    if a is not b:
        target[a] = b


def _split(bm, edge, v0, v1, ts):
    """Split edge (from v0 to v1) at each of the rising factors ts: the new vertices, in order."""
    new_verts = []
    start, rest, from_vert = 0.0, edge, v0
    for t in ts:
        _edge, new_vert = bmesh.utils.edge_split(rest, from_vert, (t - start) / (1.0 - start))
        rest = bm.edges.get((new_vert, v1))
        start, from_vert = t, new_vert
        new_verts.append(new_vert)
    return new_verts


def _hits(edges, candidates, co, distance):
    """{edge: [(t, vert)]}: every candidate within distance of a selected edge, on its nearest one."""
    tree = _tree(candidates, co)
    best = {}  # vert: (distance, edge, t)
    for e in edges:
        v0, v1 = e.verts
        p0, p1 = co[v0], co[v1]
        length = (p1 - p0).length
        for _co, k, _dist in tree.find_range((p0 + p1) * 0.5, length * 0.5 + distance):
            v = candidates[k]
            if v is v0 or v is v1:
                # A selected vertex is only near its own edge when the edge is shorter than distance
                if length > distance:
                    continue
                t, dist = (1.0 if v is v0 else 0.0), length
            else:
                t, dist = _nearest(co[v], p0, p1)
                if dist > distance:
                    continue
            if v not in best or dist < best[v][0]:
                best[v] = (dist, e, t)

    hits = {}
    for v, (_dist, e, t) in best.items():
        hits.setdefault(e, []).append((t, v))
    return hits


def _onto_edge(bm, edge, hits, co, distance, target):
    """Merge the hits on one selected edge into it, splitting it where they need a new vertex.

    Returns the new vertices, in order from the edge's first vertex to its last.
    """
    v0, v1 = edge.verts
    length = (co[v1] - co[v0]).length
    clusters = []
    for t, v in sorted(hits, key=lambda h: h[0]):
        along = t * length
        if along <= distance or length - along <= distance:
            _link(target, v, v0 if t < 0.5 else v1)
        elif clusters and along - clusters[-1][0][0] * length <= distance:
            clusters[-1].append((t, v))
        else:
            clusters.append([(t, v)])

    ts = [sum(h[0] for h in members) / len(members) for members in clusters]
    new_verts = _split(bm, edge, v0, v1, ts)
    for t, new_vert, members in zip(ts, new_verts, clusters):
        co[new_vert] = co[v0].lerp(co[v1], t)
        for _t, v in members:
            _link(target, v, new_vert)
    return new_verts


def _fold(bm, chain, co, distance, target):
    """Split every edge that folds onto the selected edges where it passes one of their vertices,
    and merge each split into the vertex it passes."""
    stay = [v for v in chain if v not in target]
    if not stay:
        return
    tree = _tree(stay, co)
    on_chain = chain.union(target)
    folding = {e for v in list(target) for e in v.link_edges
               if not e.hide and all(u in on_chain for u in e.verts)}

    for e in folding:
        a, b = e.verts
        ra, rb = _root(target, a), _root(target, b)
        if ra is rb:
            continue
        pa, pb = co[ra], co[rb]
        passes = []
        for _co, k, _dist in tree.find_range((pa + pb) * 0.5, (pb - pa).length * 0.5 + distance):
            c = stay[k]
            if c is ra or c is rb:
                continue
            t, dist = _nearest(co[c], pa, pb)
            if dist <= distance and 0.0 < t < 1.0:
                passes.append((t, c))
        if not passes:
            continue
        passes.sort(key=lambda p: p[0])
        for new_vert, (_t, c) in zip(_split(bm, e, a, b, [p[0] for p in passes]), passes):
            target[new_vert] = c


def merge(bm, matrix, distance, include_selected=False):
    """Merge the visible vertices near the selected edges of bm into those edges.

    distance is in world units (matrix: the object's world matrix). Returns
    {'edges': selected edges, 'merged': vertices merged away, 'splits': selected edges split}.
    """
    edges = [e for e in bm.edges if e.select and not e.hide]
    stats = {'edges': len(edges), 'merged': 0, 'splits': 0}
    if not edges:
        return stats

    co = {v: matrix @ v.co for v in bm.verts if not v.hide}
    candidates = [v for v in co if include_selected or not v.select]
    if not candidates:
        return stats

    target = {}  # vert: the vert it merges into
    chain = {v for e in edges for v in e.verts}
    for e, hits in _hits(edges, candidates, co, distance).items():
        v0, v1 = e.verts  # splitting changes which vertices e itself joins
        new_verts = _onto_edge(bm, e, hits, co, distance, target)
        stats['splits'] += len(new_verts)
        chain.update(new_verts)
        path = [v0, *new_verts, v1] if new_verts else ()
        for a, b in zip(path, path[1:]):
            a.select = b.select = True
            bm.edges.get((a, b)).select = True
    if not target:
        return stats

    stats['merged'] = len(target)
    _fold(bm, chain, co, distance, target)
    bmesh.ops.weld_verts(bm, targetmap={v: _root(target, v) for v in target})
    return stats

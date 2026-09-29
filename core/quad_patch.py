"""Quad Patch: rebuild a selected patch of faces as a clean quad grid.

Works where Grid Fill does not: corners are found automatically, opposite sides
with different vertex counts are balanced (see quad_patch_layout), and curved
patches keep their shape because the new grid is laid out on a flattened copy of
the patch and mapped back onto the original surface.

Steps: balance the border -> flatten the patch onto a unit square (Tutte embedding
with positive weights, which cannot fold) -> place grid lines between matching
border nodes -> map grid points back to 3D -> relax them along the surface ->
replace the patch faces, carrying over UVs, vertex weights and shape keys.
"""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import bmesh

from . import quad_patch_layout as layout
from .quad_patch_layout import PatchError

_UV_EPS = 1e-8
_CG_MAX_ITERATIONS = 4000
_CG_TOLERANCE = 1e-10


def _barycentric(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    d20, d21 = v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-30:
        return 1.0, 0.0, 0.0
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return 1.0 - v - w, v, w


class _Surface:
    """Snapshot of the original patch (triangulated) so it can be sampled after it is deleted."""

    def __init__(self, bm, faces, co):
        region = set(faces)
        self.verts = list(dict.fromkeys(v for f in faces for v in f.verts))
        index = {v: i for i, v in enumerate(self.verts)}
        self.world = [co(v) for v in self.verts]
        self.uv_layers = list(bm.loops.layers.uv.values())
        self.deform = bm.verts.layers.deform.active
        self.shapes = list(bm.verts.layers.shape.values())
        self.weights = [dict(v[self.deform].items()) for v in self.verts] if self.deform else None
        self.shape_co = [[v[s].copy() for s in self.shapes] for v in self.verts]

        self.tris, self.tri_uvs, self.tri_faces = [], [], []
        for tri in bm.calc_loop_triangles():
            face = tri[0].face
            if face not in region:
                continue
            self.tris.append(tuple(index[l.vert] for l in tri))
            self.tri_uvs.append([tuple(l[uv].uv.copy() for l in tri) for uv in self.uv_layers])
            self.tri_faces.append((face.material_index, face.smooth))
        self.bvh = BVHTree.FromPolygons(self.world, self.tris)

    def nearest(self, point):
        loc, _normal, tri, _dist = self.bvh.find_nearest(point)
        return loc, tri

    def sample(self, point):
        """(location, triangle, barycentric weights) of the closest point on the patch."""
        loc, tri = self.nearest(point)
        a, b, c = (self.world[i] for i in self.tris[tri])
        return loc, tri, _barycentric(loc, a, b, c)


def _check_uv_continuity(faces, border_edges, surface):
    border = set(border_edges)
    for f in faces:
        for e in f.edges:
            if e in border:
                continue
            if e.seam:
                raise PatchError("Selection crosses a UV seam; select up to the seam instead")
            loops = e.link_loops
            if len(loops) != 2:
                continue
            l1, l2 = loops
            for uv in surface.uv_layers:
                if ((l1[uv].uv - l2.link_loop_next[uv].uv).length_squared > _UV_EPS
                        or (l1.link_loop_next[uv].uv - l2[uv].uv).length_squared > _UV_EPS):
                    raise PatchError("Selection crosses a UV island border; select up to it instead")


def _border_uv(sides, co):
    """Place the border on the unit square: bottom (t,0), right (1,t), top (t,1), left (0,t)."""
    uv = {}
    for name, fixed in (('bottom', lambda t: (t, 0.0)), ('right', lambda t: (1.0, t)),
                        ('top', lambda t: (t, 1.0)), ('left', lambda t: (0.0, t))):
        side = list(dict.fromkeys(sides[name]))  # own vertices, without merged repeats
        for v, t in zip(side, layout.arc_params(side, co)):
            uv.setdefault(v, fixed(t))
    return uv


def _flatten(surface, fixed_uv):
    """Solve the harmonic (Tutte) embedding of the patch with the border held on the square."""
    uv = np.zeros((len(surface.verts), 2))
    free = []
    for i, v in enumerate(surface.verts):
        if v in fixed_uv:
            uv[i] = fixed_uv[v]
        else:
            free.append(i)
    if not free:
        return uv
    slot = {vi: k for k, vi in enumerate(free)}
    n = len(free)
    diag, rhs = np.zeros(n), np.zeros((n, 2))
    rows, cols, weights = [], [], []
    edges = {tuple(sorted((a, b))) for t in surface.tris for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))}
    for a, b in edges:
        w = 1.0 / max((surface.world[a] - surface.world[b]).length, 1e-9)
        for p, q in ((a, b), (b, a)):
            if p not in slot:
                continue
            diag[slot[p]] += w
            if q in slot:
                rows.append(slot[p])
                cols.append(slot[q])
                weights.append(w)
            else:
                rhs[slot[p]] += w * uv[q]
    rows, cols, weights = np.array(rows, dtype=np.int64), np.array(cols, dtype=np.int64), np.array(weights)

    def matvec(x):
        y = diag[:, None] * x
        for c in range(2):
            y[:, c] -= np.bincount(rows, weights=weights * x[cols, c], minlength=n)
        return y

    # Conjugate gradient (the system is symmetric positive definite), both columns at once.
    x = np.full((n, 2), 0.5)
    r = rhs - matvec(x)
    p = r.copy()
    rs = (r * r).sum(axis=0)
    limit = _CG_TOLERANCE * max(1.0, float((rhs * rhs).sum()))
    for _ in range(_CG_MAX_ITERATIONS):
        if rs.max() <= limit:
            break
        ap = matvec(p)
        alpha = rs / np.maximum((p * ap).sum(axis=0), 1e-300)
        x += alpha * p
        r -= alpha * ap
        rs_new = (r * r).sum(axis=0)
        p = r + (rs_new / np.maximum(rs, 1e-300)) * p
        rs = rs_new
    uv[free] = x
    return uv


def _grid_points(plan, n_cols, n_rows):
    """(u, v) of every interior grid node: where column line i meets row line j."""
    ub, ut, vl, vr = plan['bottom_t'], plan['top_t'], plan['left_t'], plan['right_t']
    points = {}
    for i in range(1, n_cols):
        du = ut[i] - ub[i]
        for j in range(1, n_rows):
            dv = vr[j] - vl[j]
            u = (ub[i] + du * vl[j]) / max(1.0 - du * dv, 1e-9)
            points[i, j] = (u, vl[j] + dv * u)
    return points


def _grid_lines(n_cols, n_rows):
    """Interior grid lines, the ones running along the patch's long direction last (they win)."""
    columns = [[(i, j) for j in range(n_rows + 1)] for i in range(1, n_cols)]
    rows = [[(i, j) for i in range(n_cols + 1)] for j in range(1, n_rows)]
    return rows + columns if n_rows >= n_cols else columns + rows


def _to_surface(points, uv, surface):
    """Map (u, v) points on the flattened patch back to world positions on the original."""
    flat = [Vector((p[0], p[1], 0.0)) for p in uv]
    bvh = BVHTree.FromPolygons(flat, surface.tris)
    world = {}
    for key, (u, v) in points.items():
        loc, _n, tri, _d = bvh.find_nearest(Vector((u, v, 0.0)))
        ia, ib, ic = surface.tris[tri]
        wa, wb, wc = _barycentric(loc, flat[ia], flat[ib], flat[ic])
        world[key] = surface.world[ia] * wa + surface.world[ib] * wb + surface.world[ic] * wc
    return world


def _even_out(pos, line, amount, fixed, surface):
    """Slide the free nodes of a grid line toward equal spacing along it (amount 0..1)."""
    pts = [pos[k] for k in line]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + (b - a).length)
    total, n = cum[-1], len(line) - 1
    if total <= 0.0:
        return
    seg = 0
    for idx in range(1, n):
        if line[idx] in fixed:
            continue
        target = cum[idx] + (total * idx / n - cum[idx]) * amount
        while seg < n - 1 and cum[seg + 1] < target:
            seg += 1
        while seg > 0 and cum[seg] > target:
            seg -= 1
        span = cum[seg + 1] - cum[seg]
        t = (target - cum[seg]) / span if span > 0.0 else 0.0
        pos[line[idx]] = surface.nearest(pts[seg].lerp(pts[seg + 1], min(max(t, 0.0), 1.0)))[0]


def _relax(pos, cells, fixed, surface, iterations, lines=(), evenness=0.0):
    """Even out spacing: move free nodes toward their neighbours, then back onto the surface.

    With evenness, every pass also slides nodes toward equal spacing along each of
    `lines` (applied in order, so the last lines win).
    """
    neighbours = {}
    for cell in cells:
        for a, b in zip(cell, cell[1:] + cell[:1]):
            neighbours.setdefault(a, set()).add(b)
            neighbours.setdefault(b, set()).add(a)
    free = [k for k in pos if k not in fixed and k in neighbours]
    passes = iterations if iterations > 0 else (3 if evenness > 0.0 and lines else 0)
    for _ in range(passes):
        if iterations > 0:
            for key in free:
                around = neighbours[key]
                avg = sum((pos[n] for n in around), Vector()) / len(around)
                pos[key] = surface.nearest(pos[key].lerp(avg, 0.5))[0]
        if evenness > 0.0:
            for line in lines:
                _even_out(pos, line, evenness, fixed, surface)


def _interpolate(values, weights):
    total = values[0] * weights[0]
    for value, w in zip(values[1:], weights[1:]):
        total = total + value * w
    return total


def connected_patches(faces):
    """Split selected faces into groups that share edges."""
    remaining = set(faces)
    patches = []
    for start in faces:
        if start not in remaining:
            continue
        remaining.discard(start)
        patch, stack = [start], [start]
        while stack:
            f = stack.pop()
            for e in f.edges:
                for g in e.link_faces:
                    if g in remaining:
                        remaining.discard(g)
                        patch.append(g)
                        stack.append(g)
        patches.append(patch)
    return patches


def prepare(bm, faces, matrix_world):
    """Validate the selection and snapshot its surface before anything is modified.

    Border splits change how non-flat faces triangulate, and a refused selection
    must stay untouched, so this runs first. Returns (faces, co, surface).
    """
    faces = [f for f in faces if f.is_valid]
    if not faces:
        raise PatchError("Select faces to rebuild")
    world_cache = {}

    def co(v):
        p = world_cache.get(v)
        if p is None:
            p = world_cache[v] = matrix_world @ v.co
        return p

    _border, border_edges = layout.border_loop(faces)
    surface = _Surface(bm, faces, co)
    _check_uv_continuity(faces, border_edges, surface)
    return faces, co, surface


def rebuild_patch(bm, faces, matrix_world, co, surface, sides, points, node_vert, cells, relax,
                  lines=(), evenness=0.0):
    """Replace the patch with new faces.

    sides: border vertex lists 'bottom', 'right', 'top', 'left' (see _border_uv).
    points: (u, v) on the unit square for every new node key.
    node_vert: existing border vertex for every border node key.
    cells: node key lists in winding order; repeated border vertices collapse, so a
    cell may come out as a triangle. lines: node key chains to space evenly by
    `evenness` (0..1) while relaxing. Returns (new_faces, triangle_count).
    """
    inverse = matrix_world.inverted_safe()
    uv = _flatten(surface, _border_uv(sides, co))
    pos = _to_surface(points, uv, surface)
    for key, v in node_vert.items():
        pos[key] = co(v)
    _relax(pos, cells, set(node_vert), surface, relax, lines, evenness)

    # Attributes of border vertices as seen from inside the patch.
    border, border_edges = layout.border_loop(faces)
    region = set(faces)
    border_uvs = {}
    for v in border:
        loop = next(l for l in v.link_loops if l.face in region)
        border_uvs[v] = [loop[uv_layer].uv.copy() for uv_layer in surface.uv_layers]

    # Remove the old patch interior, keeping the border.
    border_set, border_edge_set = set(border), set(border_edges)
    old_edges = [e for e in {e for f in faces for e in f.edges} if e not in border_edge_set]
    old_verts = [v for v in {v for f in faces for v in f.verts} if v not in border_set]
    bmesh.ops.delete(bm, geom=faces, context='FACES_ONLY')
    bmesh.ops.delete(bm, geom=[e for e in old_edges if e.is_valid], context='EDGES')
    leftover = [v for v in old_verts if v.is_valid]
    if leftover:
        bmesh.ops.delete(bm, geom=leftover, context='VERTS')

    # New interior vertices, with weights and shape keys sampled from the old surface.
    node_vert = dict(node_vert)
    node_uvs = {}
    for key, world in pos.items():
        if key in node_vert:
            continue
        _loc, tri, bary = surface.sample(world)
        corners = surface.tris[tri]
        v = bm.verts.new(inverse @ world)
        if surface.deform:
            mixed = {}
            for vi, w in zip(corners, bary):
                for group, value in surface.weights[vi].items():
                    mixed[group] = mixed.get(group, 0.0) + value * w
            for group, value in mixed.items():
                if value > 1e-6:
                    v[surface.deform][group] = value
        for s_index, shape in enumerate(surface.shapes):
            v[shape] = _interpolate([surface.shape_co[vi][s_index] for vi in corners], bary)
        node_uvs[key] = [_interpolate(list(surface.tri_uvs[tri][layer]), bary)
                         for layer in range(len(surface.uv_layers))]
        node_vert[key] = v

    new_faces, tris = [], 0
    for keys in cells:
        cell = []
        for key in keys:
            if not cell or node_vert[key] is not node_vert[cell[-1]]:
                cell.append(key)
        if len(cell) > 1 and node_vert[cell[0]] is node_vert[cell[-1]]:
            cell.pop()
        if len(cell) < 3:
            continue
        try:
            face = bm.faces.new([node_vert[k] for k in cell])
        except ValueError:
            continue
        centre = sum((pos[k] for k in cell), Vector()) / len(cell)
        _loc, tri = surface.nearest(centre)
        face.material_index, face.smooth = surface.tri_faces[tri]
        for loop, key in zip(face.loops, cell):
            values = node_uvs[key] if key in node_uvs else border_uvs[loop.vert]
            for uv_layer, value in zip(surface.uv_layers, values):
                loop[uv_layer].uv = value
        face.select_set(True)
        new_faces.append(face)
        tris += len(cell) == 3

    bm.normal_update()
    return new_faces, tris


def build_quad_patch(bm, faces, matrix_world, *, split_border=True, relax=10, evenness=0.0):
    """Replace `faces` (one patch without holes) with a quad grid.

    evenness (0..1) spaces the new vertices evenly along the grid lines, favouring
    the patch's long direction; border vertices stay where they are.
    Returns (new_faces, stats) with 'cols', 'rows', 'splits' (border edges split)
    and 'tris' (triangles left because the border could not be split).
    Raises PatchError with a user-facing message when the selection is unsuitable.
    """
    faces, co, surface = prepare(bm, faces, matrix_world)
    plan = layout.plan(faces, co, split_border)

    n_cols, n_rows = len(plan['bottom']) - 1, len(plan['left']) - 1
    node_vert = {}
    for i in range(n_cols + 1):
        node_vert[i, 0], node_vert[i, n_rows] = plan['bottom'][i], plan['top'][i]
    for j in range(n_rows + 1):
        node_vert[0, j], node_vert[n_cols, j] = plan['left'][j], plan['right'][j]
    cells = [[(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)] for i in range(n_cols) for j in range(n_rows)]

    new_faces, tris = rebuild_patch(bm, faces, matrix_world, co, surface, plan,
                                    _grid_points(plan, n_cols, n_rows), node_vert, cells, relax,
                                    _grid_lines(n_cols, n_rows), evenness)
    return new_faces, {'cols': n_cols, 'rows': n_rows, 'splits': plan['splits'], 'tris': tris}

"""Keep the artist's original polygon topology when Meshy returns a triangulated model.

Meshy's UV unwrap / retexture always returns triangles. The vertex positions are unchanged, so the
new UVs can be copied back onto the original quad/n-gon mesh. Polygons that Meshy cut with a seam
along a triangulation diagonal can't hold two UV sets in one face; only those are split into
triangles, following the exact diagonal Meshy used.
"""
from collections import defaultdict

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

UV_EPS = 1e-4          # UVs closer than this are treated as the same corner UV
MATCH_TOL_FACTOR = 2e-3  # position tolerance relative to the mesh bounding-box diagonal


class TopologyMatchError(Exception):
    """Raised when the Meshy result can't be mapped onto the original mesh."""


def _bbox(points):
    xs, ys, zs = zip(*points)
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def _read_imported_triangles(imp_obj):
    """Return [[(position, uv), x3], ...] for every triangle of the imported object."""
    bpy.context.view_layer.update()
    me = imp_obj.data
    uv_layer = me.uv_layers.active
    if uv_layer is None:
        raise TopologyMatchError("imported model has no UVs")
    me.calc_loop_triangles()
    mw = imp_obj.matrix_world
    world_co = [mw @ v.co for v in me.vertices]
    return [
        [(world_co[vi].copy(), uv_layer.data[li].uv.copy()) for li, vi in zip(lt.loops, lt.vertices)]
        for lt in me.loop_triangles
    ]


def _align_to_original(tris, src_min, src_max):
    """Undo any scale/offset Meshy applied by fitting the result's bounding box to the original."""
    imp_min, imp_max = _bbox([p for tri in tris for p, _ in tri])
    src_size, imp_size = src_max - src_min, imp_max - imp_min
    diag = max(src_size.length, 1e-9)
    scale = Vector([
        (src_size[i] / imp_size[i]) if imp_size[i] > 1e-9 and src_size[i] > 1e-9 else 1.0
        for i in range(3)
    ])
    if (imp_min - src_min).length < diag * 1e-4 and all(abs(s - 1.0) < 1e-4 for s in scale):
        return tris
    return [
        [(Vector([(p[i] - imp_min[i]) * scale[i] + src_min[i] for i in range(3)]), uv) for p, uv in tri]
        for tri in tris
    ]


def _uv_equal(a, b):
    return abs(a[0] - b[0]) < UV_EPS and abs(a[1] - b[1]) < UV_EPS


def rebuild_with_original_topology(orig_obj, imp_obj):
    """Give `imp_obj` a copy of `orig_obj`'s mesh carrying Meshy's UVs and material.

    Returns (kept_polygons, split_polygons). Raises TopologyMatchError (leaving `imp_obj`
    untouched) if the two meshes don't line up.
    """
    src = orig_obj.data
    if not src.polygons:
        raise TopologyMatchError("original mesh has no faces")

    src.calc_loop_triangles()
    src_co = [v.co.copy() for v in src.vertices]
    src_min, src_max = _bbox(src_co)
    tol = max((src_max - src_min).length, 1e-9) * MATCH_TOL_FACTOR

    imp_tris = _align_to_original(_read_imported_triangles(imp_obj), src_min, src_max)

    bvh = BVHTree.FromPolygons(src_co, [tuple(lt.vertices) for lt in src.loop_triangles])
    tri_poly = [lt.polygon_index for lt in src.loop_triangles]

    # Assign every imported triangle to the original polygon it lies on
    poly_tris = defaultdict(list)
    for tri in imp_tris:
        centroid = sum((p for p, _ in tri), Vector()) / 3.0
        hit = bvh.find_nearest(centroid)
        if hit[0] is None or hit[3] > tol:
            raise TopologyMatchError("imported geometry differs from the original mesh")
        poly_tris[tri_poly[hit[2]]].append(tri)

    bm = bmesh.new()
    try:
        bm.from_mesh(src)
        bm.faces.ensure_lookup_table()
        for layer in list(bm.loops.layers.uv):
            bm.loops.layers.uv.remove(layer)
        uv_layer = bm.loops.layers.uv.new("UVMap")

        kept, conflicts = 0, []
        for face in bm.faces:
            tris = poly_tris.get(face.index)
            if not tris:
                raise TopologyMatchError("a polygon received no triangles from Meshy")

            verts = list(face.verts)
            vert_uvs = defaultdict(list)
            resolved = []
            for tri in tris:
                spec = []
                for p, uv in tri:
                    v = min(verts, key=lambda vv: (vv.co - p).length_squared)
                    if (v.co - p).length > tol:
                        raise TopologyMatchError("imported vertices don't match the original mesh")
                    vert_uvs[v.index].append(uv)
                    spec.append((v, uv))
                if len({v.index for v, _ in spec}) != 3:
                    raise TopologyMatchError("degenerate triangle in imported model")
                resolved.append(spec)

            if len(vert_uvs) != len(verts):
                raise TopologyMatchError("a polygon corner has no UV in the imported model")

            consistent = all(_uv_equal(uvs[0], u) for uvs in vert_uvs.values() for u in uvs)
            if consistent:
                for loop in face.loops:
                    loop[uv_layer].uv = vert_uvs[loop.vert.index][0]
                kept += 1
            else:
                conflicts.append((face, resolved))

        # Seam through a diagonal: re-create the polygon as Meshy's own triangles
        for old_face, resolved in conflicts:
            new_faces = []
            for spec in resolved:
                try:
                    nf = bm.faces.new([v for v, _ in spec], old_face)
                except ValueError:
                    raise TopologyMatchError("could not split a polygon along a UV seam")
                nf.normal_update()
                if nf.normal.dot(old_face.normal) < 0.0:
                    nf.normal_flip()
                uv_by_vert = {v.index: uv for v, uv in spec}
                for loop in nf.loops:
                    loop[uv_layer].uv = uv_by_vert[loop.vert.index]
                new_faces.append(nf)
            bmesh.ops.delete(bm, geom=[old_face], context='FACES_ONLY')

        for face in bm.faces:
            face.material_index = 0

        new_me = src.copy()
        bm.to_mesh(new_me)
    finally:
        bm.free()

    new_me.update()
    new_me.materials.clear()
    for mat in imp_obj.data.materials:
        new_me.materials.append(mat)
    new_me.uv_layers.active = new_me.uv_layers["UVMap"]
    new_me.uv_layers["UVMap"].active_render = True

    old_data = imp_obj.data
    imp_obj.data = new_me
    if old_data.users == 0:
        bpy.data.meshes.remove(old_data)

    return kept, len(conflicts)

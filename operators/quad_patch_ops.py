import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator

from ..core import notify, quad_patch
from ..core.quad_patch_layout import PatchError


class REXTOOLS3_OT_quad_patch(Operator):
    """Rebuild each selected patch of faces as a clean quad grid.
Corners are found automatically, sides with different vertex counts are balanced, and the shape
is kept by laying the grid onto the original surface"""
    bl_idname = "rextools3.quad_patch"
    bl_label = "Quad Patch"
    bl_options = {'REGISTER', 'UNDO'}

    split_border: BoolProperty(
        name="Split Border",
        description="When opposite sides have different vertex counts, split border edges so a pure quad "
                    "grid fits (the face outside each split edge gains one vertex). "
                    "Off: the border is untouched and a triangle is left next to it for each missing vertex",
        default=True,
    )
    collapse: EnumProperty(
        name="Collapse",
        description="When a side has more vertices than the side opposite, first collapse one of its border "
                    "edges to take a selected triangle away. The face outside that edge, if any, loses a corner "
                    "(a triangle there goes away, a quad becomes a triangle). The merged vertex sits in the middle "
                    "of the edge (or stays on the corner), with UVs, vertex weights and shape keys interpolated "
                    "per UV island so nothing stretches. Anything still unbalanced is handled by Cut Neighbours "
                    "and Split Border",
        items=(
            ('NONE', "Off", "Don't collapse border edges"),
            ('BORDER', "Border Tris", "Collapse the border edge of a selected triangle on the longer side"),
            ('INNER', "Inner Tris",
             "Also use triangles further inside: collapse the triangle and the quads straight across from it "
             "up to the longer side, taking one border edge away (the reverse of Split Border). "
             "Includes Border Tris"),
        ),
        default='NONE',
    )
    cut_neighbours: BoolProperty(
        name="Cut Neighbours",
        description="When opposite sides have different vertex counts, first take in a corner triangle of the "
                    "face next to a corner of the shorter side instead of changing the border: that face is "
                    "cut in two and its other part stays (a quad becomes a triangle). One vertex per corner "
                    "at most; anything still missing is handled by Split Border",
        default=False,
    )
    flip_cut: BoolProperty(
        name="Flip Cut",
        description="Cut the neighbour at the other end of the shorter side than the one picked automatically. "
                    "No effect when both ends are cut or only one end can be",
        default=False,
    )
    relax: IntProperty(
        name="Relax",
        description="Smoothing passes that even out the grid spacing along the surface",
        default=10, min=0, max=100,
    )
    evenness: FloatProperty(
        name="Evenness",
        description="Space the new edges evenly along the grid lines, mainly along the patch's long "
                    "direction. Border vertices stay put, so faces next to an unevenly spaced border "
                    "absorb the difference",
        default=0.0, min=0.0, max=1.0, subtype='FACTOR',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'EDIT_MESH'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(self, "split_border")
        layout.row().prop(self, "collapse", expand=True)
        layout.prop(self, "cut_neighbours")
        row = layout.row()
        row.active = self.cut_neighbours
        row.prop(self, "flip_cut")
        layout.prop(self, "relax")
        layout.prop(self, "evenness")

    def execute(self, context):
        built, errors, collapsed, cuts, splits, tris, grids = 0, [], 0, 0, 0, 0, []

        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            selected = [f for f in bm.faces if f.select and not f.hide]
            if not selected:
                continue
            changed = False
            for patch in quad_patch.connected_patches(selected):
                try:
                    _faces, stats = quad_patch.build_quad_patch(
                        bm, patch, obj.matrix_world, split_border=self.split_border,
                        collapse=self.collapse, cut_neighbours=self.cut_neighbours,
                        flip_cut=self.flip_cut, relax=self.relax, evenness=self.evenness)
                except PatchError as e:
                    errors.append(str(e))
                    continue
                changed = True
                built += 1
                collapsed += stats['collapsed']
                cuts += stats['cuts']
                splits += stats['splits']
                tris += stats['tris']
                grids.append(f"{stats['cols']}x{stats['rows']}")
            if changed:
                bm.select_flush_mode()
                bmesh.update_edit_mesh(me, loop_triangles=True, destructive=True)

        if not built:
            notify.warning(errors[0] if errors else "Select a patch of faces to rebuild")
            return {'CANCELLED'}

        message = f"Quad Patch: {', '.join(grids)} grid"
        if collapsed:
            message += f", {collapsed} border edges collapsed"
        if cuts:
            message += f", {cuts} neighbour faces cut"
        if splits:
            message += f", {splits} border edges split"
        if tris:
            message += f", {tris} tris kept (border not split)"
        notify.success(message)
        if errors:
            notify.warning(f"{len(errors)} patch(es) skipped: {errors[0]}")
        return {'FINISHED'}

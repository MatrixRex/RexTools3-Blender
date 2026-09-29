import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
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

    def execute(self, context):
        built, errors, splits, tris, grids = 0, [], 0, 0, []

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
                        bm, patch, obj.matrix_world, split_border=self.split_border, relax=self.relax,
                        evenness=self.evenness)
                except PatchError as e:
                    errors.append(str(e))
                    continue
                changed = True
                built += 1
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
        if splits:
            message += f", {splits} border edges split"
        if tris:
            message += f", {tris} tris kept (border not split)"
        notify.success(message)
        if errors:
            notify.warning(f"{len(errors)} patch(es) skipped: {errors[0]}")
        return {'FINISHED'}

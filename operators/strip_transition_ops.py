import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
from bpy.types import Operator

from ..core import notify, quad_patch, strip_transition
from ..core.quad_patch_layout import PatchError


class REXTOOLS3_OT_strip_transition(Operator):
    """Rebuild the selected strip segment with quads so its width changes from one end to the other
(for example 4 faces across down to 2). Select from the wide part to the narrow part"""
    bl_idname = "rextools3.strip_transition"
    bl_label = "Strip Transition"
    bl_options = {'REGISTER', 'UNDO'}

    split_border: BoolProperty(
        name="Split Border",
        description="An odd width change (like 3 to 2) needs one extra vertex on a side rail to stay all "
                    "quads. On: split one rail edge (the face outside it gains a vertex). "
                    "Off: the border is untouched and one triangle is left instead",
        default=True,
    )
    position: FloatProperty(
        name="Position",
        description="Where the width changes: 0 at the wide end, 1 at the narrow end",
        default=0.5, min=0.0, max=1.0, subtype='FACTOR',
    )
    relax: IntProperty(
        name="Relax",
        description="Smoothing passes that even out the new faces along the surface",
        default=10, min=0, max=100,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'EDIT_MESH'

    def execute(self, context):
        built, errors, splits, tris, changes = 0, [], 0, 0, []

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
                    _faces, stats = strip_transition.build_strip_transition(
                        bm, patch, obj.matrix_world, split_border=self.split_border,
                        position=self.position, relax=self.relax)
                except PatchError as e:
                    errors.append(str(e))
                    continue
                changed = True
                built += 1
                splits += stats['splits']
                tris += stats['tris']
                changes.append(f"{stats['wide']} to {stats['narrow']}")
            if changed:
                bm.select_flush_mode()
                bmesh.update_edit_mesh(me, loop_triangles=True, destructive=True)

        if not built:
            notify.warning(errors[0] if errors else "Select a strip segment to rebuild")
            return {'CANCELLED'}

        message = f"Strip Transition: {', '.join(changes)} faces across"
        if splits:
            message += f", {splits} rail edge(s) split"
        if tris:
            message += f", {tris} triangle(s) kept (border not split)"
        notify.success(message)
        if errors:
            notify.warning(f"{len(errors)} patch(es) skipped: {errors[0]}")
        return {'FINISHED'}

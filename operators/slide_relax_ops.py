import bmesh
import bpy
from bpy.props import FloatProperty, IntProperty
from bpy.types import Operator

from ..core import notify, slide_relax


class REXTOOLS3_OT_slide_relax(Operator):
    """Fix folded, overlapping faces (like a bevel that overshot) by sliding the selected vertices
back along their own edges. Each folded vertex picks the edge it overshot along and slides just far
enough to open its faces up; Strength then relaxes the selection along those edges"""
    bl_idname = "rextools3.slide_relax"
    bl_label = "Slide Relax"
    bl_options = {'REGISTER', 'UNDO'}

    iterations: IntProperty(
        name="Iterations",
        description="Passes over the selection. Vertices that overshot together open up a little "
                    "each pass, and relaxing settles further with more passes",
        default=10, min=1, max=100,
    )
    strength: FloatProperty(
        name="Strength",
        description="How far each pass slides a vertex toward the average of its neighbours, "
                    "never folding anything. 0: only undo folds and leave everything else in place",
        default=0.5, min=0.0, max=1.0, subtype='FACTOR',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'EDIT_MESH'

    def execute(self, context):
        selected, moved, folded_before, folded_after = 0, 0, 0, 0

        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            verts = [v for v in bm.verts if v.select and not v.hide]
            if not verts:
                continue
            selected += len(verts)
            stats = slide_relax.slide_relax(verts, obj.matrix_world, iterations=self.iterations,
                                            strength=self.strength)
            moved += stats['moved']
            folded_before += stats['folded_before']
            folded_after += stats['folded_after']
            if stats['moved']:
                bm.normal_update()
                bmesh.update_edit_mesh(me, loop_triangles=True, destructive=False)

        if not selected:
            notify.warning("Select the vertices to relax")
            return {'CANCELLED'}

        if folded_after:
            notify.warning(f"Slide Relax: {folded_after} of {folded_before} folded faces left; "
                           f"try more Iterations or Strength, or select the vertices around them too")
        elif folded_before:
            notify.success(f"Slide Relax: unfolded {folded_before} faces, {moved} vertices moved")
        else:
            notify.success(f"Slide Relax: no folds found, {moved} vertices relaxed")
        return {'FINISHED'}

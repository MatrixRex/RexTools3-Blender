import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty
from bpy.types import Operator

from ..core import edge_cleanup, notify


def _length(context, value):
    """A world length in the scene's units, for messages."""
    units = context.scene.unit_settings
    if units.system == 'NONE':
        return f"{value:.3g}"
    return bpy.utils.units.to_string(units.system, 'LENGTH', value * units.scale_length, precision=3)


class REXTOOLS3_OT_edge_cleanup(Operator):
    """Merge the vertices close to the selected edges into those edges. A vertex near an end merges
into that end; one further along splits the edge and merges into the new vertex, closing up the
thin faces around it"""
    bl_idname = "rextools3.edge_cleanup"
    bl_label = "Edge Cleanup"
    bl_options = {'REGISTER', 'UNDO'}

    distance: FloatProperty(
        name="Distance",
        description="Vertices this close to a selected edge are merged into it, measured in world space",
        default=0.01, min=0.0, soft_max=1.0, precision=4, subtype='DISTANCE', unit='LENGTH',
    )
    include_selected: BoolProperty(
        name="Include Selected",
        description="Also merge the selected edges' own vertices: into another selected edge they come "
                    "close to, and across selected edges shorter than Distance. "
                    "Off: the selected edges keep all their vertices",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'EDIT_MESH'

    def execute(self, context):
        edges = merged = splits = 0

        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            stats = edge_cleanup.merge(bm, obj.matrix_world, self.distance, self.include_selected)
            edges += stats['edges']
            merged += stats['merged']
            splits += stats['splits']
            if stats['merged'] or stats['splits']:
                bm.select_flush_mode()
                bm.normal_update()
                bmesh.update_edit_mesh(me, loop_triangles=True, destructive=True)

        if not edges:
            notify.warning("Select the edges to clean up")
            return {'CANCELLED'}

        if not merged:
            notify.warning(f"Edge Cleanup: no vertices within {_length(context, self.distance)} of the "
                           f"selected edges. Raise Distance in the Adjust Last Operation panel")
            return {'FINISHED'}

        message = f"Edge Cleanup: {merged} vertices merged"
        if splits:
            message += f", {splits} edge split(s)"
        notify.success(message)
        return {'FINISHED'}

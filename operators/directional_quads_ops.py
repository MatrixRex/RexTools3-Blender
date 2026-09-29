import math

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator

from ..core import directional_quads, leftover_tris, notify


class REXTOOLS3_OT_directional_quads(Operator):
    """Rebuild selected faces into quads whose edge flow follows a world axis.
Ngons are triangulated first and the selection border is kept. Leftover triangle pairs can be
removed by collapsing a few vertices"""
    bl_idname = "rextools3.directional_quads"
    bl_label = "Directional Quads"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        items=[
            ('X', "X", "Edge flow follows world X"),
            ('Y', "Y", "Edge flow follows world Y"),
            ('Z', "Z", "Edge flow follows world Z"),
        ],
        default='Z',
    )
    strength: FloatProperty(
        name="Axis Strength",
        description="How strongly the axis wins over plain quad shape when picking triangle pairs",
        default=0.75, min=0.0, max=1.0, subtype='FACTOR',
    )
    reflow_quads: BoolProperty(
        name="Re-flow Quads",
        description="Also rebuild existing quads so they follow the axis. Off: only triangles and ngons are converted",
        default=True,
    )
    loop_continuity: FloatProperty(
        name="Loop Continuity",
        description="Favour quads that continue neighbouring edge loops in a straight line. "
                    "Higher gives fewer poles and stray triangles, but follows the axis less strictly",
        default=0.35, min=0.0, max=1.0, subtype='FACTOR',
    )
    minimize_tris: BoolProperty(
        name="Minimize Triangles",
        description="Re-pair neighbours so fewer triangles are left over, at a cost to flow",
        default=False,
    )
    collapse_leftovers: BoolProperty(
        name="Collapse Leftover Tris",
        description="Remove leftover triangle pairs by collapsing the quads between them. "
                    "Removes one vertex per quad crossed; off keeps the vertex count unchanged",
        default=True,
    )
    max_quads_between: IntProperty(
        name="Max Quads Between",
        description="How many quads apart two leftover triangles may be and still be merged",
        default=3, min=1, max=6,
    )
    face_threshold: FloatProperty(
        name="Max Face Angle",
        description="Largest bend between two triangles that may still become one quad",
        default=math.radians(40.0), min=0.0, max=math.pi, subtype='ANGLE',
    )
    shape_threshold: FloatProperty(
        name="Max Shape Angle",
        description="Largest deviation of any quad corner from 90 degrees",
        default=math.radians(60.0), min=0.0, max=math.pi / 2.0, subtype='ANGLE',
    )
    delimit: EnumProperty(
        name="Delimit",
        description="Never join triangles across these borders",
        items=[
            ('SEAM', "Seams", "Keep UV seams"),
            ('SHARP', "Sharp", "Keep sharp edges"),
            ('MATERIAL', "Materials", "Keep material borders"),
            ('UV', "UVs", "Keep UV island borders"),
        ],
        options={'ENUM_FLAG'},
        default={'SEAM', 'SHARP', 'MATERIAL', 'UV'},
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'EDIT_MESH'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.row().prop(self, "axis", expand=True)
        layout.prop(self, "strength", slider=True)
        layout.prop(self, "loop_continuity", slider=True)
        layout.prop(self, "reflow_quads")
        layout.prop(self, "minimize_tris")
        layout.prop(self, "collapse_leftovers")
        row = layout.row()
        row.active = self.collapse_leftovers
        row.prop(self, "max_quads_between")

        col = layout.column(align=True)
        col.prop(self, "face_threshold")
        col.prop(self, "shape_threshold")

        layout.prop(self, "delimit")

    def execute(self, context):
        direction = directional_quads.AXIS_VECTORS[self.axis]
        tris_left = quads_made = removed_verts = meshes = 0

        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            faces = [f for f in bm.faces if f.select and not f.hide]
            if not faces:
                continue

            result, _stats = directional_quads.rebuild(
                bm, faces, obj.matrix_world, direction,
                reflow_quads=self.reflow_quads,
                strength=self.strength,
                face_threshold=self.face_threshold,
                shape_threshold=self.shape_threshold,
                loop_weight=self.loop_continuity,
                minimize_tris=self.minimize_tris,
                delimit=set(self.delimit),
            )
            result, cleanup_stats = leftover_tris.cleanup(
                bm, result, obj.matrix_world, direction,
                strength=self.strength,
                face_threshold=self.face_threshold,
                shape_threshold=self.shape_threshold,
                collapse=self.collapse_leftovers,
                max_quads=self.max_quads_between,
                delimit=set(self.delimit),
            )
            for f in result:
                f.select_set(True)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(me, loop_triangles=True, destructive=True)

            tris_left += sum(1 for f in result if len(f.verts) == 3)
            quads_made += sum(1 for f in result if len(f.verts) == 4)
            removed_verts += cleanup_stats['removed_verts']
            meshes += 1

        if not meshes:
            notify.warning("Select faces to rebuild")
            return {'CANCELLED'}

        message = f"Directional Quads ({self.axis}): {quads_made} quads, {tris_left} tris left"
        if removed_verts:
            message += f", {removed_verts} verts removed"
        notify.success(message)
        return {'FINISHED'}

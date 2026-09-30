import math

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import Operator

from ..core import notify, thin_walls


def _length(context, value):
    """A world length in the scene's units, for messages."""
    units = context.scene.unit_settings
    if units.system == 'NONE':
        return f"{value:.3g}"
    return bpy.utils.units.to_string(units.system, 'LENGTH', value * units.scale_length, precision=3)


class REXTOOLS3_OT_select_thin_walls(Operator):
    """Find thin walls, where the two sides of a surface are closer than Max Thickness, and select their
inner side, outer side or both. Normals must point out of the mesh"""
    bl_idname = "rextools3.select_thin_walls"
    bl_label = "Select Thin Walls"
    bl_options = {'REGISTER', 'UNDO'}

    side: EnumProperty(
        name="Select",
        items=[
            ('INNER', "Inner", "Select the inner side of every thin wall"),
            ('OUTER', "Outer", "Select the outer side of every thin wall"),
            ('BOTH', "Both", "Select both sides of every thin wall"),
        ],
        default='INNER',
    )
    max_thickness: FloatProperty(
        name="Max Thickness",
        description="Walls thinner than this count, measured in world space. "
                    "Parts thin all the way round (rods, fingers) count too",
        default=0.05, min=0.0, soft_max=1.0, precision=4, subtype='DISTANCE', unit='LENGTH',
    )
    max_angle: FloatProperty(
        name="Max Angle",
        description="How far the two sides of a wall may turn from facing exactly opposite ways. "
                    "Higher also finds tapering walls, but can merge both sides across a rounded rim",
        default=math.radians(30.0), min=0.0, max=math.radians(89.0), subtype='ANGLE',
    )
    classify_by: EnumProperty(
        name="Outer Side",
        description="How to tell which side of a wall is the outer one",
        items=[
            ('OPEN', "Open Space",
             "The side that sees more open space is outer: the outside of a cup, the side of a jacket "
             "away from the body"),
            ('CENTER', "Mesh Center", "The side facing away from the centre of the mesh is outer"),
            ('CURSOR', "3D Cursor",
             "The side facing away from the 3D cursor is outer. Put the cursor inside the shape"),
        ],
        default='OPEN',
    )
    only_selected: BoolProperty(
        name="Only Selected",
        description="Keep the result inside the current face selection. The rest of the mesh still counts "
                    "when measuring walls",
        default=False,
        options={'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'EDIT_MESH'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.row().prop(self, "side", expand=True)
        layout.prop(self, "max_thickness")
        layout.prop(self, "max_angle")
        layout.prop(self, "classify_by")
        layout.prop(self, "only_selected")

    def execute(self, context):
        context.tool_settings.mesh_select_mode = (False, False, True)
        cursor = context.scene.cursor.location.copy()
        found = picked = undecided = 0
        thinnest, thickest = math.inf, 0.0

        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            limit = {f for f in bm.faces if f.select} if self.only_selected else None

            walls = thin_walls.find(bm, obj.matrix_world, self.max_thickness, self.max_angle,
                                    self.classify_by, cursor)
            if limit is not None:
                walls = {f: w for f, w in walls.items() if f in limit}

            for elems in (bm.verts, bm.edges, bm.faces):
                for elem in elems:
                    elem.select = False
            bm.select_history.clear()
            for f, (side, thickness) in walls.items():
                if self.side in ('BOTH', side):
                    f.select_set(True)
                    picked += 1
                undecided += side == thin_walls.UNDECIDED
                thinnest = min(thinnest, thickness)
                thickest = max(thickest, thickness)
            found += len(walls)
            bm.select_mode = {'FACE'}
            bm.select_flush_mode()
            bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)

        if not found:
            notify.warning(f"No walls thinner than {_length(context, self.max_thickness)} found. "
                           f"Raise Max Thickness in the Adjust Last Operation panel")
            return {'FINISHED'}

        span = _length(context, thinnest)
        if _length(context, thickest) != span:
            span += f" to {_length(context, thickest)}"
        which = "" if self.side == 'BOTH' else f" {self.side.lower()}"
        message = f"Thin Walls: {picked}{which} faces selected of {found} thin ({span})"
        if undecided and self.side != 'BOTH':
            notify.warning(f"{message}; {undecided} could not be told inner or outer. "
                           f"Try Outer Side: 3D Cursor")
        else:
            notify.success(message)
        return {'FINISHED'}

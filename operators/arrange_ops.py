from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import Operator

from ..core import arrange, notify


class REXTOOLS3_OT_arrange_grid(Operator):
    """Lay the selected objects out in a grid, sorted by bounding box size, with the column count
picked to make the grid square. Children move with their parent"""
    bl_idname = "rextools3.arrange_grid"
    bl_label = "Arrange in Grid"
    bl_options = {'REGISTER', 'UNDO'}

    spacing: FloatProperty(
        name="Spacing",
        description="Gap between neighbouring objects' bounding boxes, measured in world space",
        default=0.2, min=0.0, soft_max=10.0, precision=3, subtype='DISTANCE', unit='LENGTH',
    )
    largest_first: BoolProperty(
        name="Largest First",
        description="Start the grid with the biggest object. Off: with the smallest",
        default=True,
    )
    center_on: EnumProperty(
        name="Center On",
        items=[
            ('SELECTION', "Selection", "Centre the grid where the selected objects are now"),
            ('CURSOR', "3D Cursor", "Centre the grid on the 3D cursor"),
        ],
        default='SELECTION',
    )
    align_bottoms: BoolProperty(
        name="Align Bottoms",
        description="Rest every object's bottom at the same height: the lowest one among them, "
                    "or the 3D cursor's with Center On 3D Cursor. Off: heights stay as they are",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        items = arrange.measure(context.selected_objects, context.evaluated_depsgraph_get())
        if len(items) < 2:
            notify.warning("Select two or more objects to arrange. Children move with their parent")
            return {'CANCELLED'}

        if self.center_on == 'CURSOR':
            center = context.scene.cursor.location.copy()
            ground = center.z
        else:
            lo, hi = arrange.bounds(items)
            center = (lo + hi) * 0.5
            ground = lo.z

        arrange.sort_by_size(items, self.largest_first)
        columns, rows = arrange.grid(items, self.spacing, center, ground if self.align_bottoms else None)
        notify.success(f"Arranged {len(items)} objects in a {columns} x {rows} grid")
        return {'FINISHED'}

# operators/pbr_convert.py
"""
RexTools3 Easy PBR Material Conversion Operators

Provides operators to trace and convert regular or imported materials into the
RexTools3 Easy PBR standard graph system, with confirmation dialogs for partial
conversions and strict retention of complex/procedural nodes.
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty
from ..core import notify, pbr_converter


class PBR_OT_ConvertToEasyPBR(Operator):
    """Trace node graph and convert regular or imported material to Easy PBR"""
    bl_idname = "pbr.convert_to_easy_pbr"
    bl_label = "Convert to Easy PBR"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(default="")
    is_partial_confirmed: BoolProperty(default=False)

    # Class-level cache for analysis data during dialog invocation
    _cached_analysis = None

    @classmethod
    def poll(cls, context):
        mat = getattr(context, "material", None)
        if not mat and context.active_object and context.active_object.type == 'MESH':
            mat = context.active_object.active_material
        return mat is not None

    def _get_target_material(self, context):
        if self.material_name:
            mat = bpy.data.materials.get(self.material_name)
            if mat:
                return mat
        if getattr(context, "material", None):
            return context.material
        if context.active_object and context.active_object.type == 'MESH':
            return context.active_object.active_material
        return None

    def invoke(self, context, event):
        mat = self._get_target_material(context)
        if not mat:
            notify.warning("No active material to convert.")
            return {'CANCELLED'}

        analysis = pbr_converter.analyze_material_graph(mat)
        PBR_OT_ConvertToEasyPBR._cached_analysis = analysis

        if analysis['status'] == 'ALREADY_EASY_PBR':
            notify.info(f"'{mat.name}' is already formatted as an Easy PBR material.")
            # Trigger node arrangement to tidy up if user requested
            try:
                bpy.ops.pbr.arrange_nodes()
            except Exception:
                pass
            return {'FINISHED'}

        if analysis['status'] == 'UNCONVERTIBLE':
            reason = analysis['notes'][0] if analysis['notes'] else "Unsupported shader network."
            notify.error(f"Cannot convert '{mat.name}': {reason}")
            return {'CANCELLED'}

        if analysis['status'] == 'PARTIALLY_CONVERTIBLE':
            # Prompt user with confirmation dialog showing itemized breakdown
            self.is_partial_confirmed = True
            return context.window_manager.invoke_props_dialog(self, width=440)

        # Fully convertible: execute immediately without interruption
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        analysis = PBR_OT_ConvertToEasyPBR._cached_analysis
        mat = self._get_target_material(context)
        mat_name = mat.name if mat else "Active Material"

        # Notice Banner
        alert_box = layout.box()
        alert_box.alert = True
        row = alert_box.row()
        row.label(text=f"Partial Conversion: '{mat_name}'", icon='QUESTION')
        alert_box.label(text="This material contains nodes that cannot be fully automated.")

        layout.separator()

        # Convertible Components Box
        if analysis and analysis.get('convertible_slots'):
            c_box = layout.box()
            c_box.label(text="Convertible Components (Will become Easy PBR):", icon='CHECKMARK')
            col = c_box.column(align=True)
            for slot, info in analysis['convertible_slots'].items():
                row = col.row()
                if info.get('image'):
                    img_name = info['image'].name if hasattr(info['image'], 'name') else "Image"
                    row.label(text=f"• {slot}: Texture '{img_name}'")
                elif info.get('type') == 'CONSTANT':
                    row.label(text=f"• {slot}: Constant Value")
                else:
                    row.label(text=f"• {slot}: Configured")

        # Unconvertible Components Box
        if analysis and analysis.get('unconvertible_slots'):
            u_box = layout.box()
            u_box.alert = True
            u_box.label(text="Unconvertible Components (Will be RETAINED):", icon='ERROR')
            col = u_box.column(align=True)
            for slot, info in analysis['unconvertible_slots'].items():
                reason = info.get('reason', 'Complex network')
                row = col.row()
                row.label(text=f"• {slot}: {reason}")

        layout.separator()
        info_row = layout.row()
        info_row.label(text="Unconvertible nodes will stay intact in the graph for manual editing.", icon='INFO')

    def execute(self, context):
        mat = self._get_target_material(context)
        if not mat:
            notify.error("Target material not found.")
            return {'CANCELLED'}

        analysis = PBR_OT_ConvertToEasyPBR._cached_analysis
        if not analysis or analysis.get('material') != mat:
            analysis = pbr_converter.analyze_material_graph(mat)

        is_partial = (analysis['status'] == 'PARTIALLY_CONVERTIBLE')
        success = pbr_converter.convert_material_to_easy_pbr(mat, analysis, partial=is_partial)

        # Clear cached analysis
        PBR_OT_ConvertToEasyPBR._cached_analysis = None

        if success:
            if is_partial:
                notify.success(f"Partially converted '{mat.name}' to Easy PBR. Custom nodes retained.")
            else:
                notify.success(f"Successfully converted '{mat.name}' to Easy PBR.")
            return {'FINISHED'}

        notify.error(f"Failed to convert material '{mat.name}'.")
        return {'CANCELLED'}


class PBR_OT_BatchConvertToEasyPBR(Operator):
    """Batch convert all materials on selected mesh objects to Easy PBR"""
    bl_idname = "pbr.batch_convert_to_easy_pbr"
    bl_label = "Batch Convert to Easy PBR"
    bl_description = "Convert all unique materials across selected mesh objects into Easy PBR"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' and obj.material_slots for obj in context.selected_objects)

    def execute(self, context):
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_meshes:
            notify.warning("No mesh objects selected.")
            return {'CANCELLED'}

        unique_mats = set()
        for obj in selected_meshes:
            for slot in obj.material_slots:
                if slot.material:
                    unique_mats.add(slot.material)

        if not unique_mats:
            notify.warning("No materials found on selected objects.")
            return {'CANCELLED'}

        full_count = 0
        partial_count = 0
        skipped_count = 0

        for mat in unique_mats:
            analysis = pbr_converter.analyze_material_graph(mat)
            if analysis['status'] == 'ALREADY_EASY_PBR':
                skipped_count += 1
                continue
            elif analysis['status'] == 'FULLY_CONVERTIBLE':
                if pbr_converter.convert_material_to_easy_pbr(mat, analysis, partial=False):
                    full_count += 1
                else:
                    skipped_count += 1
            elif analysis['status'] == 'PARTIALLY_CONVERTIBLE':
                # Batch mode automatically preserves unconvertible nodes during partial conversion
                if pbr_converter.convert_material_to_easy_pbr(mat, analysis, partial=True):
                    partial_count += 1
                else:
                    skipped_count += 1
            else:
                skipped_count += 1

        total_converted = full_count + partial_count
        if total_converted > 0:
            msg = f"Converted {total_converted} materials to Easy PBR ({full_count} full, {partial_count} partial retained)."
            notify.success(msg)
        else:
            notify.info(f"No materials required conversion ({skipped_count} skipped or already Easy PBR).")

        return {'FINISHED'}

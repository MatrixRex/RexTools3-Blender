import bpy
from bpy.types import Panel

class PBR_PT_BatchMaterialPanel(Panel):
    bl_label = "Material Tools"
    bl_idname = "PBR_PT_batch_material_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "RexTools3"

    @classmethod
    def poll(cls, context):
        try:
            addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
            prefs = context.preferences.addons[addon_name].preferences
            if not prefs.enable_batch_material:
                return False
        except Exception:
            pass
        return True

    def draw(self, context):
        layout = self.layout
        props = context.scene.rex_batch_mat_props

        addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
        try:
            prefs = context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None

        # 1. Material Utilities Section
        utils_box = layout.box()
        utils_box.label(text="Material Utilities", icon='MATERIAL')
        utils_col = utils_box.column(align=True)
        
        if not prefs or prefs.enable_tool_extract_textures:
            utils_col.operator("rextools3.extract_textures", text="Extract Textures", icon='PACKAGE')
        if not prefs or prefs.enable_tool_replace_materials:
            utils_col.operator("rextools3.replace_materials", text="Replace Mats", icon='SHADING_TEXTURE')
        utils_col.operator("pbr.convert_to_easy_pbr", text="Convert to Easy PBR", icon='NODETREE')
        utils_col.operator("pbr.batch_convert_to_easy_pbr", text="Batch Convert to Easy PBR", icon='FILE_REFRESH')

        # 2. Batch Texture Assign Box
        if not prefs or prefs.enable_tool_batch_texture_assign:
            layout.separator()
            batch_box = layout.box()
            batch_box.label(text="Batch Texture Assign", icon='TEXTURE_DATA')
            
            col = batch_box.column(align=True)
            col.operator("pbr.batch_init", icon='FILE_REFRESH', text="Get Materials")
            
            if props.items:
                batch_box.separator()

                # Material List Section
                mat_box = batch_box.box()
                mat_box.label(text=f"Gathered Materials ({len(props.items)})", icon='MATERIAL')
                
                # Simple scrollable list via a column in a box
                mat_col = mat_box.column(align=True)
                for item in props.items:
                    row = mat_col.row(align=True)
                    # material name
                    row.label(text=item.material_name, icon='MATERIAL')
                    
                    # status
                    row.label(text=item.status)
                    
                    # Button to select the material as active
                    op = row.operator("pbr.select_material_from_batch", text="", icon='RESTRICT_SELECT_OFF')
                    op.material_name = item.material_name

                batch_box.separator()

                # Settings Section
                sbox = batch_box.box()
                sbox.label(text="Batch Settings", icon='SETTINGS')
                row = sbox.row(align=True)
                row.prop(props, "target_folder")
                op = row.operator("rextools3.pick_folder", text="", icon='FILE_FOLDER')
                op.target_path = "scene.rex_batch_mat_props.target_folder"
                sbox.prop(props, "recursive")

                # Custom Suffixes (Collapsible)
                suffix_box = sbox.box()
                suffix_row = suffix_box.row()
                suffix_row.prop(props, "show_custom_suffixes",
                                icon='TRIA_DOWN' if props.show_custom_suffixes else 'TRIA_RIGHT',
                                text="Custom Suffixes",
                                emboss=False)
                if props.show_custom_suffixes:
                    col = suffix_box.column(align=True)
                    col.prop(props, "suffix_base_color")
                    col.prop(props, "suffix_roughness")
                    col.prop(props, "suffix_metallic")
                    col.prop(props, "suffix_normal")
                    col.prop(props, "suffix_alpha")
                    col.prop(props, "suffix_ao")
                    col.prop(props, "suffix_emission")
                    col.prop(props, "suffix_height")

                batch_box.separator()

                # Execute Section
                row = batch_box.row()
                row.scale_y = 1.5
                row.operator("pbr.batch_assign_textures", icon='TEXTURE_DATA', text="Batch Assign Textures")


class PBR_OT_SelectMaterialFromBatch(bpy.types.Operator):
    """Helper to select a material from the batch list"""
    bl_idname = "pbr.select_material_from_batch"
    bl_label = "Select Material"
    
    material_name: bpy.props.StringProperty()
    
    def execute(self, context):
        mat = bpy.data.materials.get(self.material_name)
        if mat and context.active_object:
            # Find the slot with this material
            for i, slot in enumerate(context.active_object.material_slots):
                if slot.material == mat:
                    context.active_object.active_material_index = i
                    break
        return {'FINISHED'}

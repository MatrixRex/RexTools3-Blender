import bpy


class RexTools3ObjectToolsPanel(bpy.types.Panel):
    bl_label = "Object Tools"
    bl_idname = "VIEW3D_PT_rextools3_object_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'  # sidebar
    bl_category = "RexTools3"  # tab name
    
    @classmethod
    def poll(cls, context):
        try:
            addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
            prefs = context.preferences.addons[addon_name].preferences
            if not prefs.enable_object_tools:
                return False
        except Exception:
            pass
        # Only show in Object Mode
        return context.mode == 'OBJECT'
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.rex_common_settings

        addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
        try:
            prefs = context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None

        col = layout.column(align=True)
        col.operator("rextools3.apply_modifiers", text="Apply Modifiers", icon='MODIFIER')
        
        # Ignore List UI in the panel
        box = layout.box()
        row = box.row()
        row.label(text="Ignore List", icon='FILTER')
        row.operator("rextools3.apply_modifiers_add_ignore", text="", icon='ADD')
        
        col = box.column(align=True)
        for i, item in enumerate(settings.apply_modifiers_ignore_list):
            row = col.row(align=True)
            row.prop(item, "modifier_type", text="")
            op = row.operator("rextools3.apply_modifiers_remove_ignore", text="", icon='REMOVE')
            op.index = i

        if not prefs or prefs.enable_tool_arrange:
            box = layout.box()
            box.label(text="Arrange", icon='MOD_ARRAY')
            row = box.row(align=True)
            row.operator("rextools3.arrange_grid", text="Grid", icon='MESH_GRID')

import bpy
from ..ui import utils

class RexTools3CleanupToolsPanel(bpy.types.Panel):
    bl_label = "Cleanup Tools"
    bl_idname = "VIEW3D_PT_rextools3_cleanup_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'  # sidebar
    bl_category = "RexTools3"  # tab name

    @classmethod
    def poll(cls, context):
        try:
            addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
            prefs = context.preferences.addons[addon_name].preferences
            if not prefs.enable_cleanup_tools:
                return False
        except Exception:
            pass
        return context.mode in {'OBJECT', 'EDIT_MESH'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.rex_cleanup_props
        common = context.scene.rex_common_settings

        addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
        try:
            prefs = context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None

        # Clean Objects Box
        show_clean_box = (
            not prefs or 
            prefs.enable_tool_clean_objects or
            (context.mode == 'EDIT_MESH' and (prefs.enable_tool_checker_dissolve or prefs.enable_tool_directional_quads
                                              or prefs.enable_tool_quad_patch or prefs.enable_tool_strip_transition))
        )
        if show_clean_box:
            box = layout.box()
            if not prefs or prefs.enable_tool_clean_objects:
                box.operator("rextools3.clean_objects", text="Clean Objects", icon='BRUSH_DATA')
                grid = box.grid_flow(columns=2, align=True)
                grid.prop(props, "normals", text="Normals", toggle=True)
                grid.prop(props, "quad", text="Quad", toggle=True)
                grid.prop(props, "mats", text="Mats", toggle=True)
                grid.prop(props, "seams", text="Clear Seams", toggle=True)
            
            if context.mode == 'EDIT_MESH' and (not prefs or prefs.enable_tool_checker_dissolve):
                box.operator("mesh.checker_dissolve", text="Checker Dissolve", icon='MOD_DECIM')

            if context.mode == 'EDIT_MESH' and (not prefs or prefs.enable_tool_directional_quads):
                col = box.column(align=True)
                col.label(text="Directional Quads", icon='MESH_GRID')
                row = col.row(align=True)
                for axis in ('X', 'Y', 'Z'):
                    row.operator("rextools3.directional_quads", text=axis).axis = axis

            if context.mode == 'EDIT_MESH' and (not prefs or prefs.enable_tool_quad_patch):
                box.operator("rextools3.quad_patch", text="Quad Patch", icon='GRID')

            if context.mode == 'EDIT_MESH' and (not prefs or prefs.enable_tool_strip_transition):
                box.operator("rextools3.strip_transition", text="Strip Transition", icon='FULLSCREEN_EXIT')

        # Clean Modifiers Box
        if not prefs or prefs.enable_tool_clean_modifiers:
            if show_clean_box:
                layout.separator()
            box = layout.box()
            has_selected = bool(context.selected_objects)
            
            col_btn = box.column()
            col_btn.active = has_selected
            col_btn.operator("rextools3.clean_modifiers", text="Clean Modifiers", icon='MODIFIER')
            
            if has_selected:
                col = box.column(align=True)
                col.prop(common, "clean_modifiers_selection", text="Scope")
                col.prop(common, "clean_modifiers_validation", text="Validation")

        # Missing Textures Scanner
        if not prefs or prefs.enable_tool_missing_textures:
            layout.separator(factor=1.5)
            scanner = context.scene.rex_missing_texture_scanner
            col = utils.draw_section(layout, "Missing Textures", icon='IMAGE_DATA')
            
            # Scan Button
            col.operator("rextools3.scan_missing_textures", text="Scan Missing Textures", icon='VIEWZOOM')

            if scanner.has_scanned:
                col.separator()
                if not scanner.items:
                    row = col.row()
                    row.label(text="No missing textures found", icon='CHECKMARK')
                else:
                    utils.draw_call_to_action(col, "rextools3.clean_missing_textures", "Clean All Missing", icon='TRASH', type='PRIMARY')
                    col.separator()

                    # List each missing image
                    for item in scanner.items:
                        card = col.box()
                        
                        row = card.row(align=True)
                        row.label(text=item.image_name, icon='IMAGE_BACKGROUND')
                        
                        reassign_op = row.operator("rextools3.reassign_missing_texture", text="", icon='FILE_REFRESH')
                        reassign_op.image_name = item.image_name
                        
                        clean_op = row.operator("rextools3.clean_missing_texture", text="", icon='TRASH')
                        clean_op.image_name = item.image_name
                        
                        if item.materials:
                            mat_box = card.box()
                            for mat_name in item.materials.split(", "):
                                mat_box.label(text=mat_name, icon='MATERIAL')
                        else:
                            card.label(text="Not referenced in materials", icon='ERROR')

        # Purge Orphans
        if not prefs or prefs.enable_tool_purge_orphans:
            layout.separator(factor=1.5)
            layout.operator("outliner.orphans_purge", text="Purge Orphans", icon='ORPHAN_DATA')


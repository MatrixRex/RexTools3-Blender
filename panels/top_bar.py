import bpy
from ..ui import utils

class REXTOOLS3_PT_ExportSettingsPopup(bpy.types.Panel):
    bl_label = "Export Quick Settings"
    bl_idname = "REXTOOLS3_PT_export_settings_popup"
    bl_space_type = 'TOPBAR'
    bl_region_type = 'WINDOW'
    
    def draw(self, context):
        layout = self.layout
        layout.ui_units_x = 10
        
        settings = context.scene.rex_export_settings
        
        # --- ACTION ---
        col = layout.column()
        col.scale_y = 1.4
        col.operator("rextools3.export", text="Batch Export", icon='EXPORT')

        layout.separator()

        # --- GLOBAL CONFIGURATION ---
        col = utils.draw_section(layout, "Global Configuration", icon='WORLD')
        col.use_property_split = True
        col.use_property_decorate = False
        
        # Path selection
        col.prop(settings, "export_path", text="Path")
        
        col.prop(settings, "export_mode", text="Mode")
        col.separator()
        col.prop(settings, "export_limit", text="Limit")
        col.prop(settings, "export_format", text="Format")
        col.prop(settings, "export_preset", text="Preset")

        layout.separator()

        # --- ADDITIONAL SETTINGS ---
        abox = layout.box()
        arow = abox.row()
        arow.prop(settings, "show_additional_settings",
                 icon='TRIA_DOWN' if settings.show_additional_settings else 'TRIA_RIGHT',
                 text="Additional Settings",
                 emboss=False)

        if settings.show_additional_settings:
            acol = abox.column(align=True)
            acol.use_property_split = True
            acol.use_property_decorate = False

            if settings.export_format == 'FBX':
                acol.prop(settings, "fbx_remove_armature_root")

            acol.prop(settings, "reset_transform")
            acol.prop(settings, "pre_rotation")
            acol.prop(settings, "pre_scale")

        layout.separator()

        # --- EXPORT PREVIEW ---
        from ..operators.export_operators import get_export_groups
        groups = get_export_groups(context, settings)
        
        pbox = layout.box()
        prow = pbox.row()
        prow.prop(settings, "show_preview", 
                 icon='TRIA_DOWN' if settings.show_preview else 'TRIA_RIGHT', 
                 text=f"Export Preview ({len(groups)})",
                 emboss=False)
        
        if settings.show_preview:
            if groups:
                # Group by source
                by_source = {} # { source_name: [group_names] }
                source_objs = {} # { source_name: source_obj }
                for name, data in groups.items():
                    src = data['source']
                    src_name = src.name if hasattr(src, "name") else "Global Settings"
                    if src_name == "Scene": src_name = "Global Settings"
                    
                    if src_name not in by_source:
                        by_source[src_name] = []
                        source_objs[src_name] = src
                    by_source[src_name].append(name)

                p_col = pbox.column(align=True)
                for src_name in sorted(by_source.keys()):
                    # Source Header
                    src_obj = source_objs[src_name]
                    is_global = (src_name == "Global Settings")
                    
                    # Determine expansion state
                    if is_global:
                        expanded = settings.ui_expand_global_preview
                        expand_prop = "ui_expand_global_preview"
                        expand_target = settings
                    else:
                        overrides = src_obj.rex_export_overrides
                        expanded = overrides.ui_expand_preview
                        expand_prop = "ui_expand_preview"
                        expand_target = overrides

                    # Group Box
                    sbox = p_col.box()
                    s_row = sbox.row(align=True)
                    
                    s_row.prop(expand_target, expand_prop, 
                                icon='TRIA_DOWN' if expanded else 'TRIA_RIGHT', 
                                text="", emboss=False)
                    
                    if not is_global:
                        sel_op = s_row.operator("rextools3.select_by_name", text=src_name, icon='OUTLINER_COLLECTION', emboss=False)
                        sel_op.name = src_name
                        sel_op.type = 'COLLECTION'
                        
                        clear_op = s_row.operator("rextools3.clear_export_path", text="", icon='X')
                        clear_op.name = src_name
                        clear_op.type = 'COLLECTION'
                    else:
                        s_row.label(text=src_name, icon='WORLD')

                    if expanded:
                        item_col = sbox.column(align=True)
                        for g_name in sorted(by_source[src_name]):
                            i_row = item_col.row(align=True)
                            i_row.separator(factor=2.0)
                            
                            g_icon = 'OUTLINER_COLLECTION' if settings.export_mode == 'COLLECTIONS' else 'OBJECT_DATA'
                            
                            sel_op = i_row.operator("rextools3.select_by_name", text=g_name, icon=g_icon, emboss=False)
                            sel_op.name = g_name
                            sel_op.type = 'COLLECTION' if settings.export_mode == 'COLLECTIONS' else 'OBJECT'
                        
                    p_col.separator(factor=0.5)
            else:
                pbox.label(text="None", icon='ERROR')

        layout.separator()

def draw_topbar_export(self, context):
    layout = self.layout
    row = layout.row(align=True)
    row.operator("rextools3.export", text="Export", icon='EXPORT')
    row.popover(panel="REXTOOLS3_PT_export_settings_popup", text="", icon='SETTINGS')

def register():
    # Append the draw function to the top bar editor menus
    bpy.types.TOPBAR_MT_editor_menus.append(draw_topbar_export)

def unregister():
    # Remove the draw function when unregistering
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_topbar_export)

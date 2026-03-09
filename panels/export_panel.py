import bpy
from bpy.types import Panel
from ..ui import utils
from ..core.theme import Theme

class REXTOOLS3_PT_ExportManager(Panel):
    bl_label = "Export Manager"
    bl_idname = "REXTOOLS3_PT_export_manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "RexTools3"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.rex_export_settings
        
        # --- ACTION ---
        # Moving Batch Export to the very top and increasing height
        col = layout.column()
        col.scale_y = 1.6
        col.operator("rextools3.export", text="Batch Export", icon='EXPORT')

        layout.separator(factor=1.0)

        # --- GLOBAL CONFIGURATION ---
        col = utils.draw_section(layout, "Global Configuration", icon='WORLD')
        
        # Path selection
        col.prop(settings, "export_path", text="")
        
        col.separator()
        
        # Settings group
        scol = col.column(align=True)
        scol.use_property_split = True
        scol.use_property_decorate = False
        scol.prop(settings, "export_mode", text="Mode")
        scol.prop(settings, "export_limit", text="Limit")
        scol.prop(settings, "export_format", text="Format")
        scol.prop(settings, "export_preset", text="Preset")
        
        layout.separator(factor=1.5)

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

        layout.separator(factor=1.5)

        # --- MERGED EXPORT PREVIEW & OVERRIDES ---
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
                    # Source Header (The collection with the override or Global)
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
                    
                    # Collapse Toggle
                    s_row.prop(expand_target, expand_prop, 
                                icon='TRIA_DOWN' if expanded else 'TRIA_RIGHT', 
                                text="", emboss=False)
                    
                    if not is_global:
                        # Collection Override Header
                        sel_op = s_row.operator("rextools3.select_by_name", text=src_name, icon='OUTLINER_COLLECTION', emboss=False)
                        sel_op.name = src_name
                        sel_op.type = 'COLLECTION'
                        
                        clear_op = s_row.operator("rextools3.clear_export_path", text="", icon='X')
                        clear_op.name = src_name
                        clear_op.type = 'COLLECTION'
                    else:
                        s_row.label(text=src_name, icon='WORLD')

                    # List export items under this source if expanded
                    if expanded:
                        item_col = sbox.column(align=True)
                        for g_name in sorted(by_source[src_name]):
                            i_row = item_col.row(align=True)
                            i_row.separator(factor=2.0)
                            
                            # Icon based on mode
                            g_icon = 'OUTLINER_COLLECTION' if settings.export_mode == 'COLLECTIONS' else 'OBJECT_DATA'
                            
                            sel_op = i_row.operator("rextools3.select_by_name", text=g_name, icon=g_icon, emboss=False)
                            sel_op.name = g_name
                            sel_op.type = 'COLLECTION' if settings.export_mode == 'COLLECTIONS' else 'OBJECT'
                        
                    p_col.separator(factor=0.5)
            else:
                pbox.label(text="No items match criteria", icon='ERROR')


        layout.separator(factor=2.0)
        
        if settings.last_export_path:
            layout.operator("rextools3.open_export_folder", text="Open Last Export Folder", icon='FILE_FOLDER')

class REXTOOLS3_PT_GlobalExportSettings(Panel):
    bl_label = "RexTools Global Export"
    bl_idname = "REXTOOLS3_PT_global_export_settings"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.rex_export_settings
        
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        
        col.prop(settings, "export_path", text="Global Path")
        col.separator()
        col.prop(settings, "export_mode", text="Mode")
        col.prop(settings, "export_limit", text="Limit")
        col.prop(settings, "export_format", text="Format")
        col.prop(settings, "export_preset", text="Preset")

class REXTOOLS3_PT_CollectionExportPath(Panel):
    bl_label = "RexTools Export Settings"
    bl_idname = "REXTOOLS3_PT_collection_export_path"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "collection"
    
    def draw(self, context):
        layout = self.layout
        coll = context.collection
        if not coll:
            return
            
        overrides = coll.rex_export_overrides
        
        layout.prop(overrides, "use_overrides")
        
        if overrides.use_overrides:
            col = layout.column(align=True)
            col.use_property_split = True
            col.use_property_decorate = False
            
            col.prop(overrides, "export_path", text="Path")
            col.separator()
            col.prop(overrides, "export_format", text="Format")
            col.prop(overrides, "export_preset", text="Preset")
            
            col.separator()
            if overrides.export_format == 'FBX':
                col.prop(overrides, "fbx_remove_armature_root")
            
            col.prop(overrides, "reset_transform")
            col.prop(overrides, "pre_rotation")
            col.prop(overrides, "pre_scale")





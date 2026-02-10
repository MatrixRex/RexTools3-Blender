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
        
        # Path selection (removed redundant manual button as DIR_PATH has its own)
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
        
        if settings.export_format == 'FBX':
            scol.prop(settings, "fbx_remove_armature_root")
        
        layout.separator(factor=1.5)
        
        # --- EXPORT TARGETS & PREVIEW ---
        from ..operators.export_operators import get_export_groups
        groups = get_export_groups(context, settings)
        
        # Header acts as a toggle
        tbox = layout.box()
        trow = tbox.row()
        trow.prop(settings, "show_preview", 
                 icon='TRIA_DOWN' if settings.show_preview else 'TRIA_RIGHT', 
                 text=f"Export Targets ({len(groups)})",
                 emboss=False)
        
        if settings.show_preview:
            # We don't need a secondary label here
            if groups:
                p_col = tbox.column(align=True)
                for name in sorted(groups.keys()):
                    item_row = p_col.row()
                    item_row.label(text=name, icon='OBJECT_DATA')
            else:
                tbox.label(text="No items match criteria", icon='ERROR')

        layout.separator(factor=1.5)

        # --- PATH OVERRIDES ---
        obox = layout.box()
        orow = obox.row()
        orow.prop(settings, "show_custom_locations",
                 icon='TRIA_DOWN' if settings.show_custom_locations else 'TRIA_RIGHT',
                 text="Path Overrides",
                 emboss=False)
        
        if settings.show_custom_locations:
            # Quick add buttons (removed label)
            mode = settings.export_mode
            sel_count = len(context.selected_objects)
            
            if sel_count > 0:
                row = obox.row(align=True)
                if mode in {'OBJECTS', 'PARENTS'} and context.active_object:
                    op = row.operator("rextools3.browse_export_path", text="Add Object Override", icon='ADD')
                    op.target = 'OBJECT'
                    op.target_name = context.active_object.name
                
                elif mode == 'COLLECTIONS' and context.view_layer.active_layer_collection:
                    op = row.operator("rextools3.browse_export_path", text="Add Collection Override", icon='ADD')
                    op.target = 'COLLECTION'
                    op.target_name = context.view_layer.active_layer_collection.collection.name
            
            obox.separator()
            
            custom_items = []
            if mode == 'COLLECTIONS':
                for coll in bpy.data.collections:
                    if coll.export_location:
                        custom_items.append(('COLLECTION', coll))
            else:
                for obj in bpy.data.objects:
                    if obj.export_location:
                        custom_items.append(('OBJECT', obj))
            
            if custom_items:
                list_col = obox.column(align=True)
                for type, item in custom_items:
                    row = list_col.row(align=True)
                    row.label(text="", icon='OBJECT_DATA' if type == 'OBJECT' else 'OUTLINER_COLLECTION')
                    
                    # Select button
                    sel_op = row.operator("rextools3.select_by_name", text=item.name, icon='RESTRICT_SELECT_OFF', emboss=False)
                    sel_op.name = item.name
                    sel_op.type = type
                    
                    # Path prop (removed manual browse button)
                    row.prop(item, "export_location", text="")
                    
                    # Remove button
                    remove_op = row.operator("rextools3.clear_export_path", text="", icon='X')
                    remove_op.name = item.name
                    remove_op.type = type
            else:
                obox.label(text="No active overrides", icon='INFO')

        layout.separator(factor=2.0)
        
        if settings.last_export_path:
            layout.operator("rextools3.open_export_folder", text="Open Last Export Folder", icon='FILE_FOLDER')

class REXTOOLS3_PT_CollectionExportPath(Panel):
    bl_label = "RexTools Export Settings"
    bl_idname = "REXTOOLS3_PT_collection_export_path"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "collection"
    
    def draw(self, context):
        layout = self.layout
        coll = context.collection
        if coll:
            # Removed manual browse button as DIR_PATH property includes one
            layout.prop(coll, "export_location", text="Location")

class REXTOOLS3_PT_ObjectExportPath(Panel):
    bl_label = "RexTools Export Settings"
    bl_idname = "REXTOOLS3_PT_object_export_path"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    
    def draw(self, context):
        layout = self.layout
        obj = context.object
        if obj and obj.type == 'MESH':
            # Removed manual browse button as DIR_PATH property includes one
            layout.prop(obj, "export_location", text="Location")



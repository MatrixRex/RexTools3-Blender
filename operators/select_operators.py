import bpy
from bpy.types import Operator
from bpy.props import StringProperty

def find_layer_collection(layer_collection, collection_name):
    if layer_collection.collection.name == collection_name:
        return layer_collection
    for child in layer_collection.children:
        found = find_layer_collection(child, collection_name)
        if found:
            return found
    return None

class REXTOOLS3_OT_SelectByName(Operator):
    bl_idname = "rextools3.select_by_name"
    bl_label = "Select"
    bl_description = "Select the object by its name and open properties"
    
    name: StringProperty()
    type: StringProperty() # 'OBJECT' or 'COLLECTION'
    
    def execute(self, context):
        if self.type == 'OBJECT':
            obj = bpy.data.objects.get(self.name)
            if obj:
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                # Open object properties
                for area in context.screen.areas:
                    if area.type == 'PROPERTIES':
                        area.spaces.active.context = 'OBJECT'
        
        elif self.type == 'COLLECTION':
            coll = bpy.data.collections.get(self.name)
            if coll:
                # Activate in outliner
                layer_coll = find_layer_collection(context.view_layer.layer_collection, self.name)
                if layer_coll:
                    context.view_layer.active_layer_collection = layer_coll
                
                # Optionally select all objects in collection
                bpy.ops.object.select_all(action='DESELECT')
                for o in coll.all_objects:
                    try: o.select_set(True)
                    except: pass
                if coll.all_objects:
                    context.view_layer.objects.active = coll.all_objects[0]
                    
                # Switch to collection properties tab
                for area in context.screen.areas:
                    if area.type == 'PROPERTIES':
                        area.spaces.active.context = 'COLLECTION'
                    
        return {'FINISHED'}

class REXTOOLS3_OT_ClearExportPath(Operator):
    bl_idname = "rextools3.clear_export_path"
    bl_label = "Clear"
    bl_description = "Remove the custom export location override"
    
    name: StringProperty()
    type: StringProperty()
    
    def execute(self, context):
        if self.type == 'COLLECTION':
            coll = bpy.data.collections.get(self.name)
            if coll:
                coll.rex_export_overrides.use_overrides = False
        return {'FINISHED'}

import bpy

class REXTOOLS3_OT_init_weight_paint(bpy.types.Operator):
    """Go back to object mode, find armature modifier, select armature then mesh, and return to weight paint mode"""
    bl_idname = "rextools3.init_weight_paint"
    bl_label = "Init Weight Paint"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj:
            return False
        # Allow starting from Mesh (Object/Weight Paint) or Armature (Pose)
        return obj.type in {'MESH', 'ARMATURE'}

    def execute(self, context):
        obj = context.active_object
        
        # 1. Identify Target Armature and Target Mesh
        arm_obj = None
        mesh_obj = None
        
        if obj.type == 'MESH':
            mesh_obj = obj
            # Find armature modifier in the selected mesh
            for mod in mesh_obj.modifiers:
                if mod.type == 'ARMATURE' and mod.object:
                    arm_obj = mod.object
                    break
            if not arm_obj:
                self.report({'WARNING'}, "No armature modifier found on selected mesh")
                return {'CANCELLED'}
        
        elif obj.type == 'ARMATURE':
            arm_obj = obj
            # Find a mesh that is bound to this armature
            for scene_obj in context.scene.objects:
                if scene_obj.type == 'MESH':
                    for mod in scene_obj.modifiers:
                        if mod.type == 'ARMATURE' and mod.object == arm_obj:
                            mesh_obj = scene_obj
                            break
                    if mesh_obj:
                        break
            
            if not mesh_obj:
                self.report({'WARNING'}, f"No mesh found bound to armature '{arm_obj.name}'")
                return {'CANCELLED'}

        # 2. Go back to object mode to manage selection
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # 3. Deselect all
        bpy.ops.object.select_all(action='DESELECT')
        
        # 4. Select that armature
        arm_obj.select_set(True)
        
        # 5. Then select the mesh
        mesh_obj.select_set(True)
        # Ensure mesh is active for Weight Paint mode
        context.view_layer.objects.active = mesh_obj
        
        # 6. Go to weight paint mode
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        
        return {'FINISHED'}

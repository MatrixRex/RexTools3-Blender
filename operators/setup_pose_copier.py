import bpy
from bpy.types import Operator

class REXTOOLS3_OT_SetupPoseCopier(Operator):
    """Setup copy location and stretch to constraints from source armature matching bone"""
    bl_idname = "rextools3.setup_pose_copier"
    bl_label = "Setup Pose Copier"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'ARMATURE' and 
                context.mode == 'POSE' and 
                context.selected_pose_bones and
                context.scene.pose_tools_props.source_armature)

    def execute(self, context):
        target_arm = context.active_object
        source_arm = context.scene.pose_tools_props.source_armature
        selected_bones = context.selected_pose_bones
        
        count = 0
        missing_bones = []
        
        for pbone in selected_bones:
            source_bone_name = pbone.name
            
            if source_bone_name not in source_arm.data.bones:
                missing_bones.append(source_bone_name)
                continue
                
            # Get bone length from edit mode (rest length)
            bone_length = target_arm.data.bones[pbone.name].length
            
            # Remove existing Rex constraints if they exist to avoid duplicates
            for con in list(pbone.constraints):
                if con.name in ["Rex Copy Location", "Rex Stretch To"]:
                    pbone.constraints.remove(con)
            
            # Add Copy Location
            con_loc = pbone.constraints.new('COPY_LOCATION')
            con_loc.name = "Rex Copy Location"
            con_loc.target = source_arm
            con_loc.subtarget = source_bone_name
            
            # Add Stretch To
            con_str = pbone.constraints.new('STRETCH_TO')
            con_str.name = "Rex Stretch To"
            con_str.target = source_arm
            con_str.subtarget = source_bone_name
            con_str.head_tail = 1.0
            con_str.rest_length = bone_length
            
            count += 1
            
        if missing_bones:
            self.report({'WARNING'}, f"Missing {len(missing_bones)} bones in source: {', '.join(missing_bones[:5])}...")
            
        self.report({'INFO'}, f"Setup Pose Copier for {count} bones")
        
        return {'FINISHED'}

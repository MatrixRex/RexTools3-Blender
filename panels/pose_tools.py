import bpy

class RexTools3PoseToolsPanel(bpy.types.Panel):
    bl_label = "Pose Tools"
    bl_idname = "VIEW3D_PT_rextools3_pose_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "RexTools3"
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.pose_tools_props
        
        col = layout.column(align=True)
        col.prop(props, "source_armature", text="Source")
        
        layout.separator()
        
        col = layout.column()
        col.operator("rextools3.setup_pose_copier", text="Setup Pose Copier", icon='POSE_HLT')

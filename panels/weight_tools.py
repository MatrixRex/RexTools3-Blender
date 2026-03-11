import bpy

class REXTOOLS3_PT_weight_tools(bpy.types.Panel):
    bl_label = "Weight Tools"
    bl_idname = "VIEW3D_PT_rextools3_weight_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'  # sidebar
    bl_category = "RexTools3"  # tab name
    
    @classmethod
    def poll(cls, context):
        # Only visible in Weight Paint mode
        return context.mode == 'PAINT_WEIGHT'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.weight_tools_props
        
        layout.operator("rextools3.init_weight_paint", icon='WPAINT_HLT')
        layout.separator()
        
        layout.prop(props, "xray_brush", toggle=True, icon='XRAY')

import bpy
from bpy.types import Panel
from ..ui import utils
from ..operators.ai_web_bridge import BRIDGE_STATE


class RexTools3AIWebBridgePanel(Panel):
    bl_label = "AI 3D Web Bridge"
    bl_idname = "VIEW3D_PT_rextools3_ai_web_bridge"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "RexTools3"

    @classmethod
    def poll(cls, context):
        try:
            addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
            prefs = context.preferences.addons[addon_name].preferences
            if not getattr(prefs, "enable_ai_web_bridge", True):
                return False
        except Exception:
            pass
        return context.mode == 'OBJECT'

    def draw(self, context):
        layout = self.layout
        props = getattr(context.scene, "rex_ai_web_bridge_props", None)
        if not props:
            layout.label(text="Bridge properties not loaded.", icon='ERROR')
            return

        service_name = "Meshy" if props.target_service == "meshy" else "Tripo 3D"

        # 1. Target Service Selector & Main Action
        col_main = utils.draw_section(layout, "AI Generator Target", icon='WORLD')
        col_main.prop(props, "target_service", expand=True)

        col_main.separator(factor=0.5)

        # Primary Call to Action Button
        btn_col = col_main.column()
        btn_col.scale_y = 1.3
        btn_col.operator(
            "rextools3.ai_web_bridge_export",
            text=f"Send Selected to {service_name}",
            icon='URL'
        )

        layout.separator()

        # 2. Model Preparation & Export Options
        col_prep = utils.draw_section(layout, "Model Preparation", icon='TOOL_SETTINGS')
        col_prep.prop(props, "file_format", text="Format")
        col_prep.prop(props, "auto_center", text="Center at World Origin")
        col_prep.prop(props, "apply_transforms", text="Apply Transforms")
        col_prep.prop(props, "auto_open_browser", text="Auto Open Web Page")

        layout.separator()

        # 3. Companion Chrome Extension Setup
        col_ext = utils.draw_section(layout, "Browser Extension Bridge", icon='PLUGIN')
        port_num = BRIDGE_STATE.get("port", props.server_port)
        col_ext.label(text=f"Local Bridge: 127.0.0.1:{port_num}", icon='FILE_TICK')

        ext_row = col_ext.row(align=True)
        ext_row.scale_y = 1.1
        ext_row.operator(
            "rextools3.ai_web_bridge_open_extension_folder",
            text="Open Extension Folder",
            icon='PLUGIN'
        )

        sub_info = col_ext.column(align=True)
        sub_info.label(text="Load unpacked in chrome://extensions")

        layout.separator()

        # 4. Fallback utilities
        col_fb = utils.draw_section(layout, "Manual Export & Files", icon='OPTIONS')
        if props.last_model_name:
            col_fb.label(text=f"Last: {props.last_model_name} ({props.file_format})")

        fb_row = col_fb.row(align=True)
        fb_row.operator(
            "rextools3.ai_web_bridge_copy_file",
            text="Copy File",
            icon='COPY_ID'
        )
        fb_row.operator(
            "rextools3.ai_web_bridge_open_cache_folder",
            text="Open Folder",
            icon='FILEBROWSER'
        )

import bpy
from bpy.types import Panel
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

        # 1. Provider (Target Service Selector)
        row_svc = layout.row()
        row_svc.prop(props, "target_service", expand=True)

        layout.separator(factor=0.4)

        # 2. Primary Call to Action Button
        btn_col = layout.column()
        btn_col.scale_y = 1.35
        btn_col.operator(
            "rextools3.ai_web_bridge_export",
            text=f"Send Selected to {service_name}",
            icon='URL'
        )

        layout.separator(factor=0.6)

        # 3. Collapsible Settings Section
        box = layout.box()
        row_hdr = box.row()
        row_hdr.prop(
            props,
            "show_settings",
            icon='TRIA_DOWN' if props.show_settings else 'TRIA_RIGHT',
            text="Settings",
            emboss=False
        )

        if props.show_settings:
            col = box.column(align=True)
            col.use_property_split = True
            col.use_property_decorate = False

            col.prop(props, "file_format", text="Format")
            col.prop(props, "auto_center", text="Center Origin")
            col.prop(props, "apply_transforms", text="Apply Transforms")
            col.prop(props, "auto_open_browser", text="Auto Open Tab")

            box.separator(factor=0.5)

            # Extension & Bridge info
            port_num = BRIDGE_STATE.get("port", props.server_port)
            col_ext = box.column(align=True)
            col_ext.label(text=f"Bridge: 127.0.0.1:{port_num}", icon='PLUGIN')
            col_ext.operator(
                "rextools3.ai_web_bridge_open_extension_folder",
                text="Extension Folder",
                icon='FILE_FOLDER'
            )

            # Manual Fallback utilities
            if props.last_model_name:
                box.separator(factor=0.3)
                col_fb = box.column(align=True)
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

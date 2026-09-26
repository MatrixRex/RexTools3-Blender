import os
import bpy
from bpy.types import Panel
import bpy.utils.previews

# Module-level preview collection — persists between draws for performance
_preview_collections = {}


def _get_file_preview_icon(filepath: str) -> int:
    """Return an icon_value for a disk image file using bpy.utils.previews.
    Returns 0 if the file doesn't exist or can't be loaded.
    """
    if not filepath:
        return 0
    abs_path = bpy.path.abspath(filepath)
    if not os.path.isfile(abs_path):
        return 0

    if "meshy_refs" not in _preview_collections:
        _preview_collections["meshy_refs"] = bpy.utils.previews.new()

    pcoll = _preview_collections["meshy_refs"]

    # Use absolute path as key so different relative paths to the same file share one entry
    cache_key = abs_path
    if cache_key in pcoll:
        return pcoll[cache_key].icon_id

    try:
        thumb = pcoll.load(cache_key, abs_path, 'IMAGE')
        return thumb.icon_id
    except Exception:
        return 0


def _clear_preview_cache():
    """Remove the preview collection on unregister."""
    for pcoll in _preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    _preview_collections.clear()


class RexTools3MeshyPanel(Panel):
    bl_label = "Meshy AI Studio"
    bl_idname = "VIEW3D_PT_rextools3_meshy"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "RexTools3"

    @classmethod
    def poll(cls, context):
        try:
            addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
            prefs = context.preferences.addons[addon_name].preferences
            if not getattr(prefs, "enable_meshy_studio", True):
                return False
        except Exception:
            pass
        return True

    def draw(self, context):
        layout = self.layout
        props = getattr(context.scene, "rex_meshy_props", None)
        if not props:
            layout.label(text="Meshy properties not loaded.", icon='ERROR')
            return

        addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
        addon_entry = context.preferences.addons.get(addon_name)
        if not addon_entry:
            for k, v in context.preferences.addons.items():
                if "RexTools" in k:
                    addon_entry = v
                    break
        prefs = getattr(addon_entry, "preferences", None)
        if not prefs:
            layout.label(text="Preferences not available", icon='ERROR')
            return

        api_key = getattr(prefs, "meshy_api_key", "").strip()
        if not api_key:
            from ..core.meshy_client import get_persistent_api_key
            saved = get_persistent_api_key()
            if saved:
                try:
                    prefs.meshy_api_key = saved
                    api_key = saved
                except Exception:
                    api_key = saved

        # -------------------------------------------------------------------
        # 1. API Key & Credit Balance Header
        # -------------------------------------------------------------------
        box_hdr = layout.box()
        row_hdr = box_hdr.row(align=True)

        if not api_key:
            row_hdr.label(text="API Key Not Configured", icon='ERROR')
            row_key = box_hdr.row(align=True)
            row_key.prop(prefs, "meshy_api_key", text="API Key")
            return
        else:
            # Account toggle button — pressed state shows account pane inline
            row_hdr.prop(
                props, "show_account",
                text="",
                icon='COMMUNITY',
                toggle=True,
                emboss=True
            )

            if props.credit_balance >= 0:
                row_hdr.label(text=f"Credits: {props.credit_balance}")
            else:
                row_hdr.label(text="Connected")

            row_hdr.operator("rextools3.meshy_check_balance", text="", icon='FILE_REFRESH')

        # -------------------------------------------------------------------
        # 2. Live Task Progress / Queue List (when running)
        # -------------------------------------------------------------------
        from ..operators.meshy_ops import TASK_QUEUE
        active_tasks = [t for t in TASK_QUEUE if t.get("status") in ("RUNNING", "QUEUED")]
        if active_tasks:
            box_proc = layout.box()
            hdr_row = box_proc.row(align=True)
            hdr_row.label(text=f"Task Queue ({len(active_tasks)})", icon='TIME')
            hdr_row.operator("rextools3.meshy_cancel_task", text="Cancel All", icon='CANCEL')

            for t in active_tasks:
                row_t = box_proc.row(align=True)
                icon_name = 'MESH_DATA' if t.get("task_type") == 'IMAGE_TO_MESH' else ('UV' if t.get("task_type") == 'UV_UNWRAP_ONLY' else 'MATERIAL_DATA')
                t_title = t.get("title", "Task")
                if len(t_title) > 13:
                    t_title = t_title[:11] + ".."

                sp = row_t.split(factor=0.42, align=True)
                sp.label(text=t_title, icon=icon_name)

                right_row = sp.row(align=True)
                item = next((it for it in props.task_queue_items if it.task_id == t.get("id")), None)
                if t.get("status") == "RUNNING" and item:
                    right_row.prop(item, "progress", text="", slider=True)
                elif t.get("status") == "RUNNING":
                    right_row.label(text=f"{t.get('progress', 0)}%")
                else:
                    sub_q = right_row.row()
                    sub_q.alignment = 'RIGHT'
                    sub_q.label(text="Queued")

                cancel_op = right_row.operator("rextools3.meshy_cancel_task", text="", icon='CANCEL')
                cancel_op.task_id = t.get("id", "")
            layout.separator(factor=0.3)

        # -------------------------------------------------------------------
        # 3. Account panel — shown INSTEAD OF tab content when toggled
        # -------------------------------------------------------------------
        if props.show_account:
            self._draw_account(layout, context, props, prefs)
            return  # Don't show tabs when account is open

        # -------------------------------------------------------------------
        # 4. Main Navigation Tabs (only 2)
        # -------------------------------------------------------------------
        row_tabs = layout.row(align=True)
        row_tabs.prop(props, "active_tab", expand=True)
        layout.separator(factor=0.4)

        # ===================================================================
        # TAB 1: MODEL (Image to Mesh)
        # ===================================================================
        if props.active_tab == 'IMAGE_TO_MESH':
            box_src = layout.box()
            box_src.label(text="Source Image:", icon='IMAGE')
            row_src = box_src.row(align=True)
            row_src.prop(props, "image_source", expand=True)

            if props.image_source == 'FILE':
                box_src.prop(props, "image_filepath", text="")
                # Disk-file preview via bpy.utils.previews
                if props.image_filepath:
                    icon_id = _get_file_preview_icon(props.image_filepath)
                    if icon_id:
                        box_src.template_icon(icon_value=icon_id, scale=8.0)
            else:
                box_src.template_ID_preview(
                    props, "blender_image", open="image.open",
                    rows=3, cols=8, hide_buttons=False
                )

            layout.separator(factor=0.3)

            box_set = layout.box()
            box_set.label(text="Mesh Parameters:", icon='TOOL_SETTINGS')
            col_set = box_set.column(align=True)
            col_set.use_property_split = True
            col_set.use_property_decorate = False

            col_set.prop(props, "generation_mode", text="Mode")

            is_smart = props.generation_mode == "SMART_T2"
            if not is_smart:
                col_set.prop(props, "topology", text="Topology")
                if props.topology == "quad":
                    box_set.label(text="Quad topology imported via FBX", icon='INFO')
                col_set.prop(props, "polycount_standard", text="Polycount", slider=True)
            else:
                col_set.prop(props, "polycount_smart", text="Face Count", slider=True)

            col_set.prop(props, "symmetry_mode", text="Symmetry")
            col_set.prop(props, "should_texture", text="Texture")
            if props.should_texture:
                col_set.prop(props, "enable_pbr", text="PBR Maps")

            layout.separator(factor=0.5)

            btn_col = layout.column()
            btn_col.scale_y = 1.35
            btn_text = "+ Add to Queue (3D Mesh)" if props.is_processing else "Generate 3D Mesh"
            btn_col.operator(
                "rextools3.meshy_image_to_mesh",
                text=btn_text,
                icon='MESH_DATA'
            )

        # ===================================================================
        # TAB 2: UV+Tex (Retexture & UV Unwrap)
        # ===================================================================
        elif props.active_tab == 'RETEXTURE':
            active_obj = context.active_object
            is_mesh = bool(active_obj and active_obj.type == 'MESH')

            box_obj = layout.box()
            row_obj = box_obj.row(align=True)
            if is_mesh:
                face_count = len(active_obj.data.polygons)
                row_obj.label(text=f"Target: {active_obj.name} ({face_count:,} faces)", icon='CHECKMARK')
                if face_count > 40000:
                    box_obj.label(text="Warning: Mesh > 40k faces. Consider decimating.", icon='ERROR')
            else:
                row_obj.label(text="Select a Mesh Object in 3D View", icon='ERROR')

            box_obj.prop(props, "replace_selected", text="Replace Selected Mesh")

            layout.separator(factor=0.3)

            box_uv = layout.box()
            box_uv.label(text="Unwrap System:", icon='UV')
            box_uv.prop(props, "uv_mode", text="")

            if props.uv_mode == 'NEW_UNWRAP':
                row_uw_btn = box_uv.row()
                row_uw_btn.enabled = is_mesh
                btn_uw_text = "+ Queue UV Unwrap (5 cr)" if props.is_processing else "Unwrap UVs Only (5 cr)"
                row_uw_btn.operator(
                    "rextools3.meshy_uv_unwrap_only",
                    text=btn_uw_text,
                    icon='UV'
                )

            layout.separator(factor=0.3)

            box_style = layout.box()
            box_style.label(text="Texture Reference:", icon='IMAGE')
            row_rsrc = box_style.row(align=True)
            row_rsrc.prop(props, "retexture_image_source", expand=True)

            if props.retexture_image_source == 'FILE':
                box_style.prop(props, "retexture_image_filepath", text="")
                if props.retexture_image_filepath:
                    icon_id = _get_file_preview_icon(props.retexture_image_filepath)
                    if icon_id:
                        box_style.template_icon(icon_value=icon_id, scale=8.0)
            else:
                box_style.template_ID_preview(
                    props, "retexture_blender_image", open="image.open",
                    rows=3, cols=8, hide_buttons=False
                )

            box_style.prop(props, "text_style_prompt", text="Prompt")

            row_opt = box_style.row()
            row_opt.prop(props, "retexture_enable_pbr", text="PBR Maps")
            row_opt.prop(props, "remove_lighting", text="Delight")

            row_model = box_style.row()
            row_model.prop(props, "retexture_ai_model", text="AI Model")

            layout.separator(factor=0.5)

            btn_col = layout.column()
            btn_col.scale_y = 1.35
            btn_col.enabled = is_mesh
            if props.is_processing:
                btn_text = "+ Queue UV & Texture" if props.uv_mode == 'NEW_UNWRAP' else "+ Queue Textures"
            else:
                btn_text = "Unwrap & Texture" if props.uv_mode == 'NEW_UNWRAP' else "Generate PBR Textures"
            btn_col.operator(
                "rextools3.meshy_retexture",
                text=btn_text,
                icon='MATERIAL_DATA'
            )

    def _draw_account(self, layout, context, props, prefs):
        """Account & Cache settings — shown inline when the account button is toggled."""
        layout.label(text="Account & Settings", icon='PREFERENCES')

        box_acc = layout.box()
        box_acc.prop(prefs, "meshy_api_key", text="API Key")
        box_acc.prop(prefs, "meshy_use_local_cache", text="Local Blend Cache")
        if not getattr(prefs, "meshy_use_local_cache", True):
            box_acc.prop(prefs, "meshy_cache_dir", text="Custom Cache Dir")
        box_acc.label(text="Saved to ~/.rextools3/config.json", icon='CHECKMARK')

        layout.separator(factor=0.3)

        box_cache = layout.box()
        box_cache.label(text="Cache", icon='FILEBROWSER')

        if getattr(prefs, "meshy_use_local_cache", True):
            if bpy.data.is_saved and bpy.data.filepath:
                blend_dir = os.path.basename(os.path.dirname(bpy.data.filepath))
                box_cache.label(text=f"//rextools_meshy/ ({blend_dir})", icon='FILE_TICK')
            else:
                box_cache.label(text="Blend unsaved (using temp cache)", icon='HELP')
        else:
            box_cache.label(text="Using Custom/Global Cache", icon='FILE_TICK')

        row_cache = box_cache.row(align=True)
        row_cache.operator("rextools3.meshy_open_cache", text="Open Folder", icon='FILEBROWSER')
        row_cache.operator("rextools3.meshy_clear_cache", text="Clear Cache", icon='TRASH')

        # Last Result
        if props.last_result_filepath and os.path.isfile(props.last_result_filepath):
            layout.separator(factor=0.3)
            box_last = layout.box()
            box_last.label(text="Last Result:", icon='FILE_TICK')
            col_l = box_last.column(align=True)
            fname = os.path.basename(props.last_result_filepath)
            col_l.label(text=f"{fname} ({props.last_result_size})")

            if props.last_ref_image_filepath and os.path.isfile(props.last_ref_image_filepath):
                ref_fname = os.path.basename(props.last_ref_image_filepath)
                col_l.label(text=f"Ref: {ref_fname}", icon='IMAGE_DATA')

            row_lbtns = col_l.row(align=True)
            row_lbtns.operator("rextools3.meshy_replace_from_last", text="Replace Selected", icon='MESH_DATA')
            row_lbtns.operator("rextools3.meshy_import_last", text="Import at Cursor", icon='IMPORT')


def register():
    pass


def unregister():
    _clear_preview_cache()

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty, IntProperty, FloatProperty

PANEL_CATEGORY_MAPPINGS = [
    ("common_tools", "RexTools3CommonToolsPanel", "category_common_tools"),
    ("batch_material_panel", "PBR_PT_BatchMaterialPanel", "category_batch_material"),
    ("quick_asset_export", "REXTOOLS3_PT_QuickAssetExport", "category_quick_asset_export"),
    ("object_tools", "RexTools3ObjectToolsPanel", "category_object_tools"),
    ("rename_tools", "RexTools3RenameToolsPanel", "category_rename_tools"),
    ("uv_tools", "RexTools3UVToolsPanel", "category_uv_tools"),
    ("edit_tools", "RexTools3EditToolsPanel", "category_edit_tools"),
    ("uv_mesh_tools", "RexTools3UVMeshToolsPanel", "category_uv_mesh_tools"),
    ("cleanup_tools", "RexTools3CleanupToolsPanel", "category_cleanup_tools"),
    ("pose_tools", "RexTools3PoseToolsPanel", "category_pose_tools"),
    ("chain_constraints_panel", "RexTools3ChainConstraintsPanel", "category_chain_constraints"),
    ("animation_tools", "REXTOOLS3_PT_AnimationTools", "category_animation_tools"),
    ("sculpt_panel", "RexTools3SculptToolsPanel", "category_sculpt_tools"),
    ("weight_tools", "RexTools3WeightToolsPanel", "category_weight_tools"),
    ("node_helper_panel", "REXTOOLS3_PT_NodeHelper", "category_node_helper"),
    ("node_helper_panel", "REXTOOLS3_PT_NodeLayout", "category_node_helper"),
    ("export_panel", "REXTOOLS3_PT_ExportManager", "category_rexport"),
    ("texture_oven_panel", "REXTOOLS3_PT_TextureOvenPanel", "category_texture_oven"),
    ("engine_vertex_stats", "REXTOOLS3_PT_engine_vertex_stats", "category_engine_vertex_stats"),
    ("marmoset_bridge_panel", "RexTools3MarmosetBridgePanel", "category_marmoset_bridge"),
    ("ai_web_bridge_panel", "RexTools3AIWebBridgePanel", "category_ai_web_bridge"),
    ("meshy_panel", "RexTools3MeshyPanel", "category_meshy_studio")
]

def update_category_realtime(self, context):
    import importlib
    for module_name, class_name, pref_attr in PANEL_CATEGORY_MAPPINGS:
        try:
            module = importlib.import_module(f".panels.{module_name}", __package__)
            cls = getattr(module, class_name)
            default_val = "RExport" if pref_attr == "category_rexport" else ("Texture Oven" if pref_attr == "category_texture_oven" else "RexTools3")
            new_cat = getattr(self, pref_attr, default_val)
            if not new_cat:
                new_cat = default_val
                
            if cls.bl_category != new_cat:
                try:
                    bpy.utils.unregister_class(cls)
                except Exception:
                    pass
                cls.bl_category = new_cat
                try:
                    bpy.utils.register_class(cls)
                except Exception as re_ex:
                    print(f"[RexTools3] Error re-registering {class_name}: {re_ex}")
        except Exception as e:
            print(f"[RexTools3] Error in update_category_realtime for {class_name}: {e}")
            
    update_panel_redraw(self, context)

def pre_apply_panel_categories():
    import importlib
    try:
        addon_name = __package__ or "RexTools3"
        prefs = bpy.context.preferences.addons[addon_name].preferences
        for module_name, class_name, pref_attr in PANEL_CATEGORY_MAPPINGS:
            default_val = "RExport" if pref_attr == "category_rexport" else ("Texture Oven" if pref_attr == "category_texture_oven" else "RexTools3")
            custom_cat = getattr(prefs, pref_attr, default_val)
            if not custom_cat:
                custom_cat = default_val
            try:
                module = importlib.import_module(f".panels.{module_name}", __package__)
                cls = getattr(module, class_name)
                cls.bl_category = custom_cat
            except Exception as ex:
                print(f"[RexTools3] Failed to pre-set category for {class_name}: {ex}")
    except Exception as e:
        print(f"[RexTools3] Error pre-applying panel categories: {e}")

def update_keymap_active_states(self, context):
    try:
        from .operators import smart_join, rex_shading_pie, edit_delete_ops, context_aware_select, flip_paint_polarity
        
        if hasattr(smart_join, 'addon_keymaps'):
            for km, kmi in smart_join.addon_keymaps:
                kmi.active = self.enable_smart_join
                
        if hasattr(rex_shading_pie, 'addon_keymaps'):
            for km, kmi in rex_shading_pie.addon_keymaps:
                kmi.active = self.enable_shading_pie
                
        if hasattr(edit_delete_ops, 'addon_keymaps'):
            for km, kmi in edit_delete_ops.addon_keymaps:
                kmi.active = self.enable_quick_delete
                
        if hasattr(context_aware_select, 'addon_keymaps'):
            for km, kmi in context_aware_select.addon_keymaps:
                kmi.active = self.enable_context_select

        if hasattr(flip_paint_polarity, 'addon_keymaps'):
            for km, kmi in flip_paint_polarity.addon_keymaps:
                kmi.active = self.enable_paint_flip
    except Exception as e:
        print("[RexTools3] Error updating keymap active states:", e)

def update_panel_redraw(self, context):
    try:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in {'VIEW_3D', 'NODE_EDITOR'}:
                    area.tag_redraw()
    except Exception as e:
        print("[RexTools3] Error tagging redraw:", e)


def update_meshy_api_key(self, context):
    try:
        from .core.meshy_client import save_persistent_api_key
        save_persistent_api_key(self.meshy_api_key)
    except Exception as e:
        print(f"[RexTools3] Failed to persist Meshy API key: {e}")
    try:
        bpy.ops.wm.save_userpref()
    except Exception:
        pass
    update_panel_redraw(self, context)


def update_meshy_cache_dir(self, context):
    try:
        from .core.meshy_client import save_persistent_config
        save_persistent_config({"meshy_cache_dir": self.meshy_cache_dir})
    except Exception as e:
        print(f"[RexTools3] Failed to persist Meshy cache dir: {e}")
    update_panel_redraw(self, context)


def update_meshy_use_local_cache(self, context):
    try:
        from .core.meshy_client import save_persistent_config
        save_persistent_config({"meshy_use_local_cache": self.meshy_use_local_cache})
    except Exception as e:
        print(f"[RexTools3] Failed to persist Meshy local cache setting: {e}")
    update_panel_redraw(self, context)


def restore_persistent_preferences():
    """Load persistent settings from ~/.rextools3/config.json into preferences if empty."""
    try:
        from .core.meshy_client import load_persistent_config
        cfg = load_persistent_config()
        if not cfg:
            return

        addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
        addon_entry = bpy.context.preferences.addons.get(addon_name)
        if not addon_entry:
            for name, entry in bpy.context.preferences.addons.items():
                if "RexTools" in name:
                    addon_entry = entry
                    break
        if not addon_entry or not hasattr(addon_entry, "preferences"):
            return

        prefs = addon_entry.preferences
        saved_key = cfg.get("meshy_api_key", "").strip()
        if saved_key and not getattr(prefs, "meshy_api_key", "").strip():
            prefs.meshy_api_key = saved_key

        saved_cache = cfg.get("meshy_cache_dir", "").strip()
        if saved_cache and not getattr(prefs, "meshy_cache_dir", "").strip():
            prefs.meshy_cache_dir = saved_cache

        if "meshy_use_local_cache" in cfg:
            prefs.meshy_use_local_cache = bool(cfg["meshy_use_local_cache"])
    except Exception as e:
        print(f"[RexTools3] Error restoring persistent preferences: {e}")


class RexTools3Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or "RexTools3"

    active_tab: EnumProperty(
        name="Tab",
        items=[
            ('PANELS', "Panel Tools", "Enable or disable sidebar panel tools", 'PREFERENCES', 0),
            ('SHORTCUTS', "Shortcut Tools", "Manage shortcut tools and their hotkeys", 'TOOL_SETTINGS', 1),
            ('PIES', "Pie Menus", "Manage pie menus and their hotkeys", 'MENU_PANEL', 2),
        ],
        default='PANELS',
    )

    # Tool Category Toggles (Panels)
    enable_common_tools: BoolProperty(
        name="Common Tools",
        description="Enable/Disable the Common Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_cleanup_tools: BoolProperty(
        name="Cleanup Tools",
        description="Enable/Disable the Cleanup Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_pbr_tools: BoolProperty(
        name="EasyPBR",
        description="Enable/Disable the EasyPBR panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_batch_material: BoolProperty(
        name="Material Tools",
        description="Enable/Disable the Material Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_node_helper: BoolProperty(
        name="Node Helper & Layout",
        description="Enable/Disable the Node Helper and Node Layout panels",
        default=True,
        update=update_panel_redraw,
    )
    enable_object_tools: BoolProperty(
        name="Object Tools",
        description="Enable/Disable the Object Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_edit_tools: BoolProperty(
        name="Edit Tools",
        description="Enable/Disable the Edit Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_rexport: BoolProperty(
        name="RExport",
        description="Enable/Disable RExport and its sub-components",
        default=True,
        update=update_panel_redraw,
    )
    enable_quick_asset_export: BoolProperty(
        name="Quick Blender Assets",
        description="Enable/Disable the Quick Blender Assets panel",
        default=True,
        update=update_panel_redraw,
    )
    quick_asset_clear_after: BoolProperty(
        name="Keep working file clean",
        description="Remove the asset marking from the objects in your working file "
                    "after exporting, so your scene stays uncluttered",
        default=True,
    )
    quick_asset_preview_wait: FloatProperty(
        name="Preview wait (seconds)",
        description="How long to wait for thumbnails to render before writing the file. "
                    "If your asset thumbnails come out blank, increase this",
        default=1.5,
        min=0.1,
        max=10.0,
    )
    enable_pose_tools: BoolProperty(
        name="Pose Tools",
        description="Enable/Disable the Pose Tools panel",
        default=True,
        update=update_panel_redraw,
    )

    enable_chain_constraints: BoolProperty(
        name="Chain Constraints Adder",
        description="Enable/Disable the Chain Constraints Adder panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_animation_tools: BoolProperty(
        name="Animation Tools",
        description="Enable/Disable the Animation Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_sculpt_tools: BoolProperty(
        name="Sculpt Tools",
        description="Enable/Disable the Sculpt Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_uv_tools: BoolProperty(
        name="UV Tools",
        description="Enable/Disable the UV Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_uv_mesh_tools: BoolProperty(
        name="UV Mesh Tools",
        description="Enable/Disable the UV Mesh Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_weight_tools: BoolProperty(
        name="Weight Tools",
        description="Enable/Disable the Weight Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_rename_tools: BoolProperty(
        name="Rename Tools",
        description="Enable/Disable the Rename Tools panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_texture_oven: BoolProperty(
        name="Texture Oven",
        description="Enable/Disable the Texture Oven baking panel",
        default=True,
        update=update_panel_redraw,
    )
    enable_marmoset_bridge: BoolProperty(
        name="Marmoset Bridge",
        description="Enable/Disable the Marmoset Toolbag Bridge",
        default=True,
        update=update_panel_redraw,
    )
    enable_ai_web_bridge: BoolProperty(
        name="AI 3D Web Bridge",
        description="Enable/Disable AI 3D Web Bridge panel (Meshy / Tripo)",
        default=True,
        update=update_panel_redraw,
    )
    enable_meshy_studio: BoolProperty(
        name="Meshy AI Studio",
        description="Enable/Disable native Meshy AI panel",
        default=True,
        update=update_panel_redraw,
    )
    meshy_api_key: StringProperty(
        name="Meshy API Key",
        description="Meshy API key from https://meshy.ai/developer",
        default="",
        subtype='PASSWORD',
        update=update_meshy_api_key,
    )
    meshy_cache_dir: StringProperty(
        name="Meshy Cache Dir",
        description="Folder for downloaded Meshy models and textures (leave blank for system temp)",
        default="",
        subtype='DIR_PATH',
        update=update_meshy_cache_dir,
    )
    meshy_use_local_cache: BoolProperty(
        name="Use Local Blend Cache",
        description="Store Meshy models, textures, and reference images in a 'rextools_meshy' folder next to the saved .blend file",
        default=True,
        update=update_meshy_use_local_cache,
    )
    marmoset_path: StringProperty(
        name="Marmoset Toolbag Path",
        description="Path to the Marmoset Toolbag executable",
        default=r"C:\Program Files\Marmoset\Toolbag 5\Toolbag.exe",
        subtype='FILE_PATH'
    )
    enable_engine_vertex_stats: BoolProperty(
        name="Engine Vertex Stats",
        description="Enable/Disable the Engine Vertex Stats panel",
        default=True,
        update=update_panel_redraw,
    )
    evstat_use_uv: BoolProperty(
        name="UV seams",
        description="Split vertices across UV seams (Unity does this)",
        default=True,
        update=update_panel_redraw,
    )
    evstat_use_color: BoolProperty(
        name="Vertex color",
        description="Split vertices across vertex-color discontinuities",
        default=True,
        update=update_panel_redraw,
    )
    evstat_nrm_prec: IntProperty(
        name="Normal Precision",
        description="Rounding precision for normals (decimals)",
        default=5, min=1, max=8,
        update=update_panel_redraw,
    )
    evstat_uv_prec: IntProperty(
        name="UV Precision",
        description="Rounding precision for UVs (decimals)",
        default=6, min=1, max=8,
        update=update_panel_redraw,
    )
    evstat_col_prec: IntProperty(
        name="Color Precision",
        description="Rounding precision for colors (decimals)",
        default=4, min=1, max=8,
        update=update_panel_redraw,
    )
    evstat_auto_recalculate: BoolProperty(
        name="Auto Recalculate",
        description="Automatically recalculate stats when selection or active object changes",
        default=False,
        update=update_panel_redraw,
    )
    evstat_show_overlay: BoolProperty(
        name="Show Viewport Overlay",
        description="Show the Game Engine vertex count in the top-left corner of the 3D Viewport",
        default=False,
        update=update_panel_redraw,
    )

    category_common_tools: StringProperty(
        name="Common Tools Category",
        description="Sidebar tab category for the Common Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_batch_material: StringProperty(
        name="Material Tools Category",
        description="Sidebar tab category for the Material Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_quick_asset_export: StringProperty(
        name="Quick Blender Assets Category",
        description="Sidebar tab category for the Quick Blender Assets panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_object_tools: StringProperty(
        name="Object Tools Category",
        description="Sidebar tab category for the Object Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_rename_tools: StringProperty(
        name="Rename Tools Category",
        description="Sidebar tab category for the Rename Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_uv_tools: StringProperty(
        name="UV Tools Category",
        description="Sidebar tab category for the UV Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_edit_tools: StringProperty(
        name="Edit Tools Category",
        description="Sidebar tab category for the Edit Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_uv_mesh_tools: StringProperty(
        name="UV Mesh Tools Category",
        description="Sidebar tab category for the UV Mesh Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_cleanup_tools: StringProperty(
        name="Cleanup Tools Category",
        description="Sidebar tab category for the Cleanup Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_pose_tools: StringProperty(
        name="Pose Tools Category",
        description="Sidebar tab category for the Pose Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_chain_constraints: StringProperty(
        name="Chain Constraints Category",
        description="Sidebar tab category for the Chain Constraints panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_animation_tools: StringProperty(
        name="Animation Tools Category",
        description="Sidebar tab category for the Animation Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_sculpt_tools: StringProperty(
        name="Sculpt Tools Category",
        description="Sidebar tab category for the Sculpt Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_weight_tools: StringProperty(
        name="Weight Tools Category",
        description="Sidebar tab category for the Weight Tools panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_node_helper: StringProperty(
        name="Node Helper Category",
        description="Sidebar tab category for the Shader Editor Node Helper panels",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_rexport: StringProperty(
        name="RExport Category",
        description="Sidebar tab category for the RExport panel",
        default="RExport",
        update=update_category_realtime,
    )
    category_texture_oven: StringProperty(
        name="Texture Oven Category",
        description="Sidebar tab category for the Texture Oven panel",
        default="Texture Oven",
        update=update_category_realtime,
    )
    category_engine_vertex_stats: StringProperty(
        name="Engine Stats Category",
        description="Sidebar tab category for the Engine Vertex Stats panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_marmoset_bridge: StringProperty(
        name="Marmoset Bridge Category",
        description="Sidebar tab category for the Marmoset Bridge panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_ai_web_bridge: StringProperty(
        name="AI 3D Web Bridge Category",
        description="Sidebar tab category for the AI 3D Web Bridge panel",
        default="RexTools3",
        update=update_category_realtime,
    )
    category_meshy_studio: StringProperty(
        name="Meshy AI Category",
        description="Sidebar tab category for the Meshy AI Studio panel",
        default="RexTools3",
        update=update_category_realtime,
    )

    # Common Tools Sub-tools
    enable_tool_open_folder: BoolProperty(name="Open Folder", default=True, update=update_panel_redraw)
    enable_tool_object_transform: BoolProperty(name="Object Transform", default=True, update=update_panel_redraw)
    enable_tool_extract_textures: BoolProperty(name="Extract Textures", default=True, update=update_panel_redraw)
    enable_tool_replace_materials: BoolProperty(name="Replace Materials", default=True, update=update_panel_redraw)
    enable_tool_batch_texture_assign: BoolProperty(name="Batch Texture Assign", default=True, update=update_panel_redraw)
    enable_tool_bone_batch_rename: BoolProperty(name="Bone Batch Rename", default=True, update=update_panel_redraw)
    enable_tool_mesh_highlow_rename: BoolProperty(name="Mesh High/Low Rename", default=True, update=update_panel_redraw)

    # Cleanup Tools Sub-tools
    enable_tool_clean_objects: BoolProperty(name="Clean Objects", default=True, update=update_panel_redraw)
    enable_tool_checker_dissolve: BoolProperty(name="Checker Dissolve", default=True, update=update_panel_redraw)
    enable_tool_clean_modifiers: BoolProperty(name="Clean Modifiers", default=True, update=update_panel_redraw)
    enable_tool_missing_textures: BoolProperty(name="Missing Textures Scanner", default=True, update=update_panel_redraw)
    enable_tool_purge_orphans: BoolProperty(name="Purge Orphans", default=True, update=update_panel_redraw)

    # Edit Tools Sub-tools
    enable_tool_angle_loop_select: BoolProperty(name="Angle Loop Select", default=True, update=update_panel_redraw)
    enable_tool_subdivide_tube: BoolProperty(name="Subdivide Tube", default=True, update=update_panel_redraw)

    # Pose Tools Sub-tools
    enable_tool_pose_init_weight: BoolProperty(name="Init Weight Paint", default=True, update=update_panel_redraw)
    enable_tool_setup_pose_copier: BoolProperty(name="Setup Pose Copier", default=True, update=update_panel_redraw)
    enable_tool_mute_constraints: BoolProperty(name="Mute Constraints", default=True, update=update_panel_redraw)
    enable_tool_flipped_anim: BoolProperty(name="Flipped Anim", default=True, update=update_panel_redraw)

    # Sculpt Tools Sub-tools
    enable_tool_sculpt_navigation: BoolProperty(name="Pen Navigation", default=True, update=update_panel_redraw)
    enable_tool_sculpt_assets: BoolProperty(name="Sculpt Assets Previews", default=True, update=update_panel_redraw)

    # UV Mesh Tools Sub-tools
    enable_tool_uv_mesh_area_seam: BoolProperty(name="Area Seam", default=True, update=update_panel_redraw)
    enable_tool_uv_mesh_angle_loop_seam: BoolProperty(name="Angle Loop Seam", default=True, update=update_panel_redraw)
    enable_tool_uv_mesh_seam_island_sharp: BoolProperty(name="Seam From Island & Sharp", default=True, update=update_panel_redraw)
    enable_tool_uv_mesh_area_seam_angle: BoolProperty(name="Area Seam by Angle", default=True, update=update_panel_redraw)
    enable_tool_uv_mesh_unwrap_quad: BoolProperty(name="Live Unwrap & Quad Follow", default=True, update=update_panel_redraw)

    # Weight Tools Sub-tools
    enable_tool_weight_init_weight: BoolProperty(name="Init Weight Paint", default=True, update=update_panel_redraw)
    enable_tool_weight_xray_brush: BoolProperty(name="X-Ray Brush Toggle", default=True, update=update_panel_redraw)

    # Keymapped Operators Toggles
    enable_smart_join: BoolProperty(
        name="Smart Join",
        description="Enable/Disable Smart Join operator and shortcut",
        default=True,
        update=update_keymap_active_states,
    )
    enable_shading_pie: BoolProperty(
        name="Rex Shading & View Pies",
        description="Enable/Disable Shading and View pie menus and shortcuts",
        default=True,
        update=update_keymap_active_states,
    )
    enable_quick_delete: BoolProperty(
        name="Quick Delete Modal",
        description="Enable/Disable Quick Delete modal operator and shortcut",
        default=True,
        update=update_keymap_active_states,
    )
    quick_delete_mode: EnumProperty(
        name="Quick Delete Mode",
        description="Paradigms for keyboard-driven quick delete system",
        items=[
            ('NESTED', "Nested WASD (Double-Tap)", "Two-step menu where WASD selects category first, then action", 'MENU_PANEL', 0),
            ('GRID', "Keyboard Grid Layout (Direct)", "Visual QWERTY layout grid for single-key actions", 'GRID', 1),
            ('MODIFIER', "Hold-and-Press Modifiers (WASD)", "Modifier keys (Shift/Alt/Ctrl) modify WASD actions", 'TRACKING', 2),
        ],
        default='NESTED',
    )
    enable_context_select: BoolProperty(
        name="Context Aware Select",
        description="Enable/Disable Context Aware Select operator and double-click shortcut",
        default=True,
        update=update_keymap_active_states,
    )
    enable_paint_flip: BoolProperty(
        name="Paint Flip (Sculpt/Weight/Color)",
        description="Enable/Disable X key shortcut to flip weight, sculpt polarity, or colors in paint modes",
        default=True,
        update=update_keymap_active_states,
    )

    def draw(self, context):
        # Auto-restore persistent settings if currently empty
        if not self.meshy_api_key:
            try:
                from .core.meshy_client import get_persistent_api_key
                saved_key = get_persistent_api_key()
                if saved_key:
                    self.meshy_api_key = saved_key
            except Exception:
                pass
        if not self.meshy_cache_dir:
            try:
                from .core.meshy_client import load_persistent_config
                saved_cache = load_persistent_config().get("meshy_cache_dir", "").strip()
                if saved_cache:
                    self.meshy_cache_dir = saved_cache
            except Exception:
                pass

        layout = self.layout
        
        # Draw Tab Selector
        row = layout.row(align=True)
        row.prop(self, "active_tab", expand=True)
        layout.separator()

        if self.active_tab == 'PANELS':
            col = layout.column()
            col.label(text="Sidebar Panel Tools Visibility", icon='PREFERENCES')
            
            def draw_panel_category(layout, label, icon, enable_prop, sub_props=None, info_text=None, category_prop=None):
                box = layout.box()
                hdr = box.row()
                hdr.prop(self, enable_prop, text=label, icon=icon)
                
                if getattr(self, enable_prop):
                    if category_prop:
                        # Draw Sidebar Tab category input field
                        row = box.row(align=True)
                        row.prop(self, category_prop, text="Sidebar Tab")
                        box.separator()
                        
                    if info_text:
                        lines = info_text.split("\n")
                        box.label(text=lines[0], icon='INFO')
                        for line in lines[1:]:
                            box.label(text="    " + line)
                    if sub_props:
                        sub_col = box.column(align=True)
                        sub_col.separator(factor=0.5)
                        row = sub_col.row(align=True)
                        grid = row.grid_flow(columns=2, align=True)
                        for prop, name in sub_props:
                            grid.prop(self, prop, text=name)
            
            # --- Group 1: 3D Viewport Sidebar (RexTools3 Tab) ---
            box_3d = col.box()
            box_3d.label(text="3D Viewport Sidebar (RexTools3 Tab)", icon='VIEW3D')
            col_3d = box_3d.column()
            
            # Sub-group: Any Mode
            box_any = col_3d.box()
            box_any.label(text="Any Mode Tools", icon='WORLD')
            col_any = box_any.column()
            draw_panel_category(col_any, "Common Tools", 'SETTINGS', "enable_common_tools", [
                ("enable_tool_open_folder", "Open Folder"),
                ("enable_tool_object_transform", "Object Transform")
            ], category_prop="category_common_tools")
            draw_panel_category(col_any, "Material Tools", 'TEXTURE_DATA', "enable_batch_material", [
                ("enable_tool_extract_textures", "Extract Textures"),
                ("enable_tool_replace_materials", "Replace Materials"),
                ("enable_tool_batch_texture_assign", "Batch Texture Assign")
            ], category_prop="category_batch_material")
            draw_panel_category(col_any, "Quick Blender Assets", 'ASSET_MANAGER', "enable_quick_asset_export", sub_props=[
                ("quick_asset_clear_after", "Keep working file clean"),
                ("quick_asset_preview_wait", "Preview Wait (s)")
            ], category_prop="category_quick_asset_export")
 
            # Sub-group: Object Mode
            box_obj = col_3d.box()
            box_obj.label(text="Object Mode Tools", icon='OBJECT_DATA')
            col_obj = box_obj.column()
            draw_panel_category(col_obj, "Object Tools", 'OBJECT_DATA', "enable_object_tools", category_prop="category_object_tools")
            draw_panel_category(col_obj, "UV Tools", 'UV_DATA', "enable_uv_tools", category_prop="category_uv_tools")
            draw_panel_category(col_obj, "Rename Tools", 'FONT_DATA', "enable_rename_tools", [
                ("enable_tool_bone_batch_rename", "Bone Batch Rename"),
                ("enable_tool_mesh_highlow_rename", "Mesh High/Low Rename")
            ], category_prop="category_rename_tools")
            draw_panel_category(col_obj, "Texture Oven", 'TEXTURE', "enable_texture_oven", category_prop="category_texture_oven")
            draw_panel_category(col_obj, "Marmoset Bridge", 'LINKED', "enable_marmoset_bridge", [
                ("marmoset_path", "Marmoset Path")
            ], category_prop="category_marmoset_bridge")
            draw_panel_category(col_obj, "AI 3D Web Bridge", 'URL', "enable_ai_web_bridge", category_prop="category_ai_web_bridge")
            draw_panel_category(col_obj, "Meshy AI Studio", 'MESH_DATA', "enable_meshy_studio", [
                ("meshy_api_key", "API Key"),
                ("meshy_use_local_cache", "Local Blend Cache"),
                ("meshy_cache_dir", "Fallback/Custom Cache Dir")
            ], category_prop="category_meshy_studio")
            box_evstat = col_obj.box()
            hdr_evstat = box_evstat.row()
            hdr_evstat.prop(self, "enable_engine_vertex_stats", text="Engine Vertex Stats", icon='SNAP_VERTEX')
            if self.enable_engine_vertex_stats:
                row_evstat = box_evstat.row(align=True)
                row_evstat.prop(self, "category_engine_vertex_stats", text="Sidebar Tab")
                box_evstat.prop(self, "evstat_auto_recalculate", text="Auto Recalculate")
                box_evstat.prop(self, "evstat_show_overlay", text="Show Viewport Overlay")
                box_evstat.separator()
                
                # Split options
                sub_col_evstat = box_evstat.column(align=True)
                sub_col_evstat.label(text="Attributes that Split:")
                row_split_evstat = sub_col_evstat.row(align=True)
                row_split_evstat.prop(self, "evstat_use_uv", text="UV Seams")
                row_split_evstat.prop(self, "evstat_use_color", text="Vertex Colors")
                
                box_evstat.separator()
                
                # Precision settings
                sub_prec_evstat = box_evstat.column(align=True)
                sub_prec_evstat.label(text="Rounding Precision (Decimals):")
                row_prec_evstat = sub_prec_evstat.row(align=True)
                row_prec_evstat.prop(self, "evstat_nrm_prec", text="Normal")
                row_prec_evstat.prop(self, "evstat_uv_prec", text="UV")
                row_prec_evstat.prop(self, "evstat_col_prec", text="Color")
 
            # Sub-group: Edit Mode
            box_edit = col_3d.box()
            box_edit.label(text="Edit Mode Tools", icon='EDITMODE_HLT')
            col_edit = box_edit.column()
            draw_panel_category(col_edit, "Edit Tools", 'EDITMODE_HLT', "enable_edit_tools", [
                ("enable_tool_angle_loop_select", "Angle Loop Select"),
                ("enable_tool_subdivide_tube", "Subdivide Tube")
            ], category_prop="category_edit_tools")
            draw_panel_category(col_edit, "UV Mesh Tools", 'UV', "enable_uv_mesh_tools", [
                ("enable_tool_uv_mesh_area_seam", "Area Seam"),
                ("enable_tool_uv_mesh_angle_loop_seam", "Angle Loop Seam"),
                ("enable_tool_uv_mesh_seam_island_sharp", "Seam From Island & Sharp"),
                ("enable_tool_uv_mesh_area_seam_angle", "Area Seam by Angle"),
                ("enable_tool_uv_mesh_unwrap_quad", "Live Unwrap & Quad")
            ], category_prop="category_uv_mesh_tools")
 
            # Sub-group: Object & Edit Mode
            box_obj_edit = col_3d.box()
            box_obj_edit.label(text="Object & Edit Mode Tools", icon='LOOP_BACK')
            col_obj_edit = box_obj_edit.column()
            draw_panel_category(col_obj_edit, "Cleanup Tools", 'BRUSH_DATA', "enable_cleanup_tools", [
                ("enable_tool_clean_objects", "Clean Objects"),
                ("enable_tool_checker_dissolve", "Checker Dissolve"),
                ("enable_tool_clean_modifiers", "Clean Modifiers"),
                ("enable_tool_missing_textures", "Missing Textures Scanner"),
                ("enable_tool_purge_orphans", "Purge Orphans")
            ], category_prop="category_cleanup_tools")
 
            # Sub-group: Pose Mode
            box_pose = col_3d.box()
            box_pose.label(text="Pose Mode Tools", icon='POSE_HLT')
            col_pose = box_pose.column()
            draw_panel_category(col_pose, "Pose Tools", 'POSE_HLT', "enable_pose_tools", [
                ("enable_tool_pose_init_weight", "Init Weight Paint"),
                ("enable_tool_setup_pose_copier", "Setup Pose Copier"),
                ("enable_tool_mute_constraints", "Mute Constraints"),
                ("enable_tool_flipped_anim", "Flipped Anim")
            ], category_prop="category_pose_tools")
            draw_panel_category(col_pose, "Chain Constraints Adder", 'CONSTRAINT_BONE', "enable_chain_constraints", category_prop="category_chain_constraints")
            draw_panel_category(col_pose, "Animation Tools", 'ANIM', "enable_animation_tools", category_prop="category_animation_tools")
 
            # Sub-group: Paint & Sculpt Modes
            box_paint = col_3d.box()
            box_paint.label(text="Paint & Sculpt Mode Tools", icon='SCULPTMODE_HLT')
            col_paint = box_paint.column()
            draw_panel_category(col_paint, "Sculpt Tools", 'SCULPTMODE_HLT', "enable_sculpt_tools", [
                ("enable_tool_sculpt_navigation", "Pen Navigation"),
                ("enable_tool_sculpt_assets", "Sculpt Assets Previews")
            ], category_prop="category_sculpt_tools")
            draw_panel_category(col_paint, "Weight Tools", 'WPAINT_HLT', "enable_weight_tools", [
                ("enable_tool_weight_init_weight", "Init Weight Paint"),
                ("enable_tool_weight_xray_brush", "X-Ray Brush Toggle")
            ], category_prop="category_weight_tools")
            
            # --- Group 2: RExport Panel & Tools ---
            col.separator()
            box_rexport = col.box()
            box_rexport.label(text="RExport Panel & Tools", icon='EXPORT')
            col_rexport = box_rexport.column()
            
            draw_panel_category(col_rexport, "RExport", 'EXPORT', "enable_rexport",
                                info_text="Locations:\n1. 3D View > side panel > RExport\n2. TopBar header > RExport\n3. Collection properties > RExport\n4. Scene properties > RExport",
                                category_prop="category_rexport")
            
            # --- Group 3: EasyPBR Panel & Tools ---
            col.separator()
            box_pbr = col.box()
            box_pbr.label(text="EasyPBR Panel & Tools", icon='MATERIAL')
            col_pbr = box_pbr.column()
            
            draw_panel_category(col_pbr, "EasyPBR", 'MATERIAL', "enable_pbr_tools",
                                info_text="Location:\n1. Properties Editor > Material Properties > Easy PBR")
            
            # --- Group 4: Other Editors & Windows ---
            col.separator()
            box_other = col.box()
            box_other.label(text="Other Editors & Windows", icon='WINDOW')
            col_other = box_other.column()
            
            draw_panel_category(col_other, "Node Helper & Layout", 'NODETREE', "enable_node_helper",
                                info_text="Location:\n1. Shader Editor > Sidebar > RexTools3 Tab", category_prop="category_node_helper")
            
        elif self.active_tab == 'SHORTCUTS':
            # --- Shortcut Tools Section ---
            col = layout.column()
            col.label(text="Shortcut Tools Configuration", icon='TOOL_SETTINGS')
            
            from .operators import smart_join, edit_delete_ops, context_aware_select, flip_paint_polarity

            shortcut_tools = [
                (self.enable_smart_join, "enable_smart_join", smart_join, "Smart Join (Object Mode: Ctrl+J)"),
                (self.enable_quick_delete, "enable_quick_delete", edit_delete_ops, "Quick Delete Modal (3D View: X)"),
                (self.enable_context_select, "enable_context_select", context_aware_select, "Context Aware Select (Mesh/Curve: Double Click)"),
                (self.enable_paint_flip, "enable_paint_flip", flip_paint_polarity, "Paint Flip (Sculpt/Weight/Color Paint: X)"),
            ]

            wm = context.window_manager
            kc = wm.keyconfigs.user

            for enabled, toggle_prop_name, module, title in shortcut_tools:
                box = col.box()
                
                # Header row with enable/disable toggle
                hdr = box.row()
                hdr.prop(self, toggle_prop_name, text=title)
                
                if enabled and hasattr(module, 'addon_keymaps'):
                    if toggle_prop_name == "enable_quick_delete":
                        box.prop(self, "quick_delete_mode", text="Modal Mode")
                    keymap_col = box.column(align=True)
                    import rna_keymap_ui
                    for km, kmi in module.addon_keymaps:
                        row = keymap_col.row(align=True)
                        icon_name = 'MESH_DATA' if km.name == 'Mesh' else ('OUTLINER_OB_CURVE' if km.name == 'Curve' else 'INFO')
                        row.label(text=f"{km.name}:", icon=icon_name)
                        row.context_pointer_set("keymap", km)
                        rna_keymap_ui.draw_kmi(None, kc, km, kmi, row, 0)

        elif self.active_tab == 'PIES':
            # --- Pie Menus Section ---
            col = layout.column()
            col.label(text="Pie Menus Configuration", icon='MENU_PANEL')
            
            from .operators import rex_shading_pie

            pie_tools = [
                (self.enable_shading_pie, "enable_shading_pie", rex_shading_pie, "Rex Shading & View Pies (3D View: Z / W)"),
            ]

            wm = context.window_manager
            kc = wm.keyconfigs.user

            for enabled, toggle_prop_name, module, title in pie_tools:
                box = col.box()
                
                # Header row with enable/disable toggle
                hdr = box.row()
                hdr.prop(self, toggle_prop_name, text=title)
                
                if enabled and hasattr(module, 'addon_keymaps'):
                    keymap_col = box.column(align=True)
                    import rna_keymap_ui
                    for km, kmi in module.addon_keymaps:
                        row = keymap_col.row(align=True)
                        row.label(text=f"{km.name}:", icon='INFO')
                        row.context_pointer_set("keymap", km)
                        rna_keymap_ui.draw_kmi(None, kc, km, kmi, row, 0)

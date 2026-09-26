import os
import time
import shutil
import bpy

def _save_reference_image(source_type: str, filepath: str, blender_image: bpy.types.Image, cache_dir: str, prefix: str = "ref") -> str:
    """
    Save or copy the input reference image into the Meshy cache directory.
    Returns the absolute path to the saved reference image file in cache_dir, or "" on failure.
    """
    import shutil
    os.makedirs(cache_dir, exist_ok=True)
    target_path = ""

    try:
        if source_type == 'FILE':
            if filepath and os.path.isfile(filepath):
                base_name = os.path.basename(filepath)
                stem, ext = os.path.splitext(base_name)
                ext = ext.lower() if ext else ".png"
                clean_stem = "".join(c for c in stem if c.isalnum() or c in ('_', '-'))[:28] or "image"
                target_filename = f"{prefix}_{clean_stem}_{int(time.time())}{ext}"
                target_path = os.path.join(cache_dir, target_filename)

                # Avoid duplicate copying if already in destination
                if os.path.abspath(filepath) != os.path.abspath(target_path):
                    shutil.copy2(filepath, target_path)
                return target_path

        elif source_type == 'BLENDER' and blender_image:
            img_disk_path = bpy.path.abspath(blender_image.filepath) if blender_image.filepath else ""
            clean_stem = "".join(c for c in blender_image.name if c.isalnum() or c in ('_', '-'))[:28] or "image"

            if img_disk_path and os.path.isfile(img_disk_path):
                _, ext = os.path.splitext(img_disk_path)
                ext = ext.lower() if ext else ".png"
                target_filename = f"{prefix}_{clean_stem}_{int(time.time())}{ext}"
                target_path = os.path.join(cache_dir, target_filename)
                if os.path.abspath(img_disk_path) != os.path.abspath(target_path):
                    shutil.copy2(img_disk_path, target_path)
                return target_path
            else:
                target_filename = f"{prefix}_{clean_stem}_{int(time.time())}.png"
                target_path = os.path.join(cache_dir, target_filename)
                orig_format = blender_image.file_format
                try:
                    blender_image.file_format = 'PNG'
                    blender_image.save(filepath=target_path)
                finally:
                    blender_image.file_format = orig_format
                return target_path

    except Exception as e:
        print(f"[RexTools3] Warning: could not cache reference image: {e}")

    return target_path


def _export_temp_glb(obj, filepath: str):
    """Export the given Blender object to a temporary GLB file in clean local coordinate space.
    This prevents double-scaling or offset shifts when re-importing Meshy results.
    """
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    orig_selected = [o for o in bpy.context.selected_objects]
    orig_active = bpy.context.active_object

    temp_obj = None
    try:
        # Create a temp duplicate sharing mesh data to export in unscaled local space
        temp_obj = obj.copy()
        temp_obj.parent = None
        # Place at origin with 1.0 unit scale
        temp_obj.location = (0.0, 0.0, 0.0)
        temp_obj.rotation_euler = (0.0, 0.0, 0.0)
        temp_obj.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        temp_obj.scale = (1.0, 1.0, 1.0)

        bpy.context.scene.collection.objects.link(temp_obj)

        bpy.ops.object.select_all(action='DESELECT')
        temp_obj.select_set(True)
        bpy.context.view_layer.objects.active = temp_obj

        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format='GLB',
            use_selection=True,
            export_apply=True,
            export_yup=True,
            export_materials='EXPORT',
            export_image_format='AUTO',
            export_cameras=False,
            export_lights=False
        )
    finally:
        if temp_obj and temp_obj.name in bpy.data.objects:
            bpy.data.objects.remove(temp_obj, do_unlink=True)

        bpy.ops.object.select_all(action='DESELECT')
        for o in orig_selected:
            if o.name in bpy.data.objects:
                o.select_set(True)
        if orig_active and orig_active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = orig_active

def _set_material_shading():
    """Ensure at least one 3D Viewport is set to Material Preview shading so textures are immediately visible."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'


def _safe_import_gltf(filepath: str):
    """Import GLTF/GLB using temp_override so timer callbacks never fail with context errors."""
    existing_objs = set(bpy.context.scene.objects)
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    if win and hasattr(bpy.context, "temp_override"):
        with bpy.context.temp_override(window=win, screen=win.screen, view_layer=win.view_layer, scene=win.scene):
            bpy.ops.import_scene.gltf(filepath=filepath)
    else:
        bpy.ops.import_scene.gltf(filepath=filepath)
    return [o for o in bpy.context.scene.objects if o not in existing_objs]


def _safe_import_fbx(filepath: str):
    """Import FBX using temp_override so timer callbacks never fail with context errors.
    Used when quad topology is requested — FBX preserves quad faces; GLB always triangulates.
    """
    existing_objs = set(bpy.context.scene.objects)
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    if win and hasattr(bpy.context, "temp_override"):
        with bpy.context.temp_override(window=win, screen=win.screen, view_layer=win.view_layer, scene=win.scene):
            bpy.ops.import_scene.fbx(filepath=filepath)
    else:
        bpy.ops.import_scene.fbx(filepath=filepath)
    return [o for o in bpy.context.scene.objects if o not in existing_objs]


def _replace_or_import_mesh(result_path: str, target_obj_name: str = "", replace_selected: bool = True):
    """
    Imports the generated GLB model from Meshy.
    If replace_selected is True and target_obj exists, replaces the target object in-place:
    - Maintains exact world transform (location, rotation, scale)
    - Re-links into the same scene collection(s)
    - Adopts the original object name
    - Deletes the original object
    - Switches 3D Viewport shading to 'MATERIAL'
    """
    if not os.path.isfile(result_path) or os.path.getsize(result_path) == 0:
        raise FileNotFoundError(f"Result model file is empty or missing: {result_path}")

    target_obj = bpy.data.objects.get(target_obj_name) if target_obj_name else None

    # Route importer by file extension — FBX preserves quads, GLB triangulates
    ext = os.path.splitext(result_path)[1].lower()
    if ext == '.fbx':
        new_objs = _safe_import_fbx(result_path)
    else:
        new_objs = _safe_import_gltf(result_path)

    new_mesh = next((o for o in new_objs if o.type == 'MESH'), None)

    if not new_mesh:
        raise ValueError(f"Model was imported ({ext.upper()}), but no mesh object was found.")

    if replace_selected and target_obj and target_obj.type == 'MESH':
        orig_name = target_obj.name
        orig_matrix = target_obj.matrix_world.copy()
        orig_collections = list(target_obj.users_collection)

        # Apply exact position, rotation, and scale of the original mesh
        new_mesh.matrix_world = orig_matrix

        # Link to the original collections
        for col in orig_collections:
            if new_mesh.name not in col.objects:
                col.link(new_mesh)
        # Unlink from any other default collections created during import
        for col in list(new_mesh.users_collection):
            if col not in orig_collections:
                col.unlink(new_mesh)

        orig_parent = target_obj.parent
        orig_parent_type = target_obj.parent_type
        orig_parent_bone = target_obj.parent_bone

        # Remove the old object
        bpy.data.objects.remove(target_obj, do_unlink=True)

        # Inherit original name and parenting
        new_mesh.name = orig_name
        if orig_parent:
            new_mesh.parent = orig_parent
            new_mesh.parent_type = orig_parent_type
            if orig_parent_bone:
                new_mesh.parent_bone = orig_parent_bone
    else:
        # Place at 3D cursor position
        new_mesh.location = bpy.context.scene.cursor.location

    # Select and make active
    bpy.ops.object.select_all(action='DESELECT')
    new_mesh.select_set(True)
    bpy.context.view_layer.objects.active = new_mesh

    # Switch viewport shading so user immediately sees the textures/materials!
    _set_material_shading()

    return new_mesh


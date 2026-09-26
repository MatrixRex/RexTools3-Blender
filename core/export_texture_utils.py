import os
import bpy

FORMAT_EXTENSIONS = {
    'BMP': '.bmp',
    'PNG': '.png',
    'JPEG': '.jpg',
    'JPEG2000': '.jp2',
    'TARGA': '.tga',
    'TARGA_RAW': '.tga',
    'CINEON': '.cin',
    'DPX': '.dpx',
    'MULTILAYER': '.exr',
    'OPEN_EXR': '.exr',
    'OPEN_EXR_MULTILAYER': '.exr',
    'HDR': '.hdr',
    'TIFF': '.tif',
    'WEBP': '.webp',
}


def _get_image_filename(img):
    """Determine a safe and valid filename for the image datablock."""
    raw_name = ""
    ext = ""
    if img.filepath:
        basename = os.path.basename(img.filepath)
        if basename:
            raw_name, ext = os.path.splitext(basename)
            
    if not raw_name:
        raw_name = bpy.path.clean_name(img.name)
    if not raw_name:
        raw_name = "texture"
        
    if not ext:
        ext = FORMAT_EXTENSIONS.get(img.file_format, '.png')
        
    return f"{raw_name}{ext}"


def _collect_images_from_material(mat):
    """Recursively collect all image datablocks from a material's node tree, including node groups."""
    images = set()
    if not mat or not mat.use_nodes or not mat.node_tree:
        return images
        
    def _traverse(tree, visited):
        if not tree or tree in visited:
            return
        visited.add(tree)
        for node in tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                images.add(node.image)
            elif node.type == 'GROUP' and getattr(node, 'node_tree', None):
                _traverse(node.node_tree, visited)
                
    _traverse(mat.node_tree, set())
    return images


def _collect_images_from_object(obj):
    """Collect all unique images from all material slots and mesh data of an object."""
    images = set()
    if not obj:
        return images
        
    mats = set()
    if hasattr(obj, "material_slots"):
        for slot in obj.material_slots:
            if slot.material:
                mats.add(slot.material)
    if hasattr(obj, "data") and hasattr(obj.data, "materials"):
        for mat in obj.data.materials:
            if mat:
                mats.add(mat)
                
    for mat in mats:
        images.update(_collect_images_from_material(mat))
        
    return images


def _resolve_image_on_disk(img, filename):
    """Attempt to find the image on disk across original and local project candidate locations."""
    candidates = []
    
    # 1. Direct resolution via image.filepath
    if img.filepath:
        abs_path = bpy.path.abspath(img.filepath)
        if abs_path:
            candidates.append(abs_path)
        norm_path = os.path.normpath(img.filepath)
        if norm_path and norm_path not in candidates:
            candidates.append(norm_path)
            
    # 2. Blend file directory candidates (if blend is saved)
    if bpy.data.is_saved and bpy.data.filepath:
        blend_dir = os.path.dirname(bpy.data.filepath)
        candidates.append(os.path.join(blend_dir, "textures", filename))
        candidates.append(os.path.join(blend_dir, filename))
        candidates.append(os.path.join(blend_dir, "Textures", filename))
        
        if img.filepath:
            clean_rel = img.filepath.lstrip("/\\")
            candidates.append(os.path.join(blend_dir, clean_rel))
            
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)
            
    return None


def _save_memory_image_to_disk(img, target_path):
    """Save an in-memory, packed, or generated image datablock to disk at target_path."""
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # 1. If packed into .blend, write raw bytes directly (exact, lossless)
        if img.packed_file and hasattr(img.packed_file, "data") and img.packed_file.data:
            with open(target_path, "wb") as f:
                f.write(img.packed_file.data)
            return True
            
        # 2. Force pixel data load into memory if needed
        if not img.has_data:
            try:
                _ = img.pixels[0]
            except Exception:
                pass
                
        # 3. Try saving via filepath_raw
        orig_filepath = img.filepath_raw
        try:
            img.filepath_raw = target_path
            img.save()
            if os.path.isfile(target_path):
                return True
        except Exception:
            pass
        finally:
            img.filepath_raw = orig_filepath
            
        # 4. Fallback to save_render
        try:
            img.save_render(target_path)
            if os.path.isfile(target_path):
                return True
        except Exception as e:
            print(f"[RexTools3] save_render failed for {img.name}: {e}")
            
    except Exception as e:
        print(f"[RexTools3] Failed to save image {img.name} to {target_path}: {e}")
        
    return False


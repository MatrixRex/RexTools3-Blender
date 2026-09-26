import bpy
import os
from ..operators.object_auto_rename_low_high import MESH_OT_auto_rename_high_low

def ensure_image_on_disk(img, export_dir):
    if not img:
        return None
    
    path = bpy.path.abspath(img.filepath)
    if path and os.path.exists(path) and not img.packed_file:
        return path
        
    # If packed or missing, save to export directory
    safe_name = bpy.path.clean_name(img.name)
    ext = os.path.splitext(path)[1] if path else ".png"
    if not ext:
        ext = ".png"
        
    temp_path = os.path.normpath(os.path.join(export_dir, f"_temp_tex_{safe_name}{ext}"))
    try:
        # Temporarily redirect filepath to save the image data to disk, then restore it
        orig_filepath = img.filepath_raw
        try:
            img.filepath_raw = temp_path
            img.save()
        finally:
            img.filepath_raw = orig_filepath
        return temp_path
    except Exception as e:
        # Fallback to save_render if save fails
        try:
            img.save_render(temp_path)
            return temp_path
        except Exception as e2:
            print(f"RexTools3: Failed to save image {img.name} to disk: {e} | {e2}")
            return None

def find_material_textures(material, export_dir):
    textures = {}
    if not material or not material.use_nodes:
        return textures
    
    nodes = material.node_tree.nodes
    
    # 1. Easy PBR System Node Names (Highest priority)
    pbr_mapping = {
        'albedo': 'BaseTex',
        'normal': 'NormalTex',
        'roughness': 'RoughnessTex',
        'metallic': 'MetallicTex',
    }
    
    for key, node_name in pbr_mapping.items():
        node = nodes.get(node_name)
        if node and node.type == 'TEX_IMAGE' and node.image:
            path = ensure_image_on_disk(node.image, export_dir)
            if path:
                textures[key] = os.path.normpath(path).replace("\\", "/")
                
    # 2. Standard Principled BSDF Socket Tracing (Medium priority)
    principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if principled:
        def get_image_path(socket):
            if not socket.is_linked:
                return None
            
            # Follow the link back
            link = socket.links[0]
            node = link.from_node
            
            # If it is direct image node
            if node.type == 'TEX_IMAGE' and node.image:
                return ensure_image_on_disk(node.image, export_dir)
                
            # If it is a normal map node
            if node.type in {'NORMAL_MAP', 'BUMP'}:
                col_sock = node.inputs.get('Color')
                if col_sock and col_sock.is_linked:
                    tex_node = col_sock.links[0].from_node
                    if tex_node.type == 'TEX_IMAGE' and tex_node.image:
                        return ensure_image_on_disk(tex_node.image, export_dir)
                        
            # If it is a mix node
            if node.type in {'MIX', 'MIX_RGB'}:
                # Check inputs Color1 / Color2 (or A / B in newer blender versions)
                for sock_name in ('A', 'B', 'Color1', 'Color2'):
                    in_sock = node.inputs.get(sock_name)
                    if in_sock and in_sock.is_linked:
                        from_n = in_sock.links[0].from_node
                        if from_n.type == 'TEX_IMAGE' and from_n.image:
                            return ensure_image_on_disk(from_n.image, export_dir)
            return None

        # Map Principled BSDF inputs to map types
        mappings = {
            'Base Color': 'albedo',
            'Roughness': 'roughness',
            'Metallic': 'metallic',
            'Normal': 'normal',
        }
        
        for socket_name, key in mappings.items():
            if key in textures:
                continue # Already found via Easy PBR
            sock = principled.inputs.get(socket_name)
            if sock:
                path = get_image_path(sock)
                if path:
                    textures[key] = os.path.normpath(path).replace("\\", "/")

    # 3. Fallback/Supplementary scan: scan all Image Texture nodes in the material
    for node in nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            # Skip if we already found everything
            if all(k in textures for k in ['albedo', 'normal', 'roughness', 'metallic']):
                break
                
            img = node.image
            path = ensure_image_on_disk(img, export_dir)
            if not path:
                continue
                
            path_esc = os.path.normpath(path).replace("\\", "/")
            img_name_lower = img.name.lower()
            file_name_lower = os.path.basename(path).lower()
            
            # Helper to check if name matches pattern
            def matches(keywords):
                return any(kw in img_name_lower or kw in file_name_lower for kw in keywords)
                
            # Guess role if not already assigned by BSDF tracing
            if 'albedo' not in textures and matches(['albedo', 'diffuse', 'basecolor', 'base_color', 'color', 'diff']):
                textures['albedo'] = path_esc
            elif 'normal' not in textures and matches(['normal', 'nrm', 'nor_']):
                textures['normal'] = path_esc
            elif 'roughness' not in textures and matches(['roughness', 'rough', 'rgh']):
                textures['roughness'] = path_esc
            elif 'metallic' not in textures and matches(['metallic', 'metal', 'met_']):
                textures['metallic'] = path_esc
                
    return textures


def get_object_group_info(obj):
    import re
    name = obj.name
    clean_n = re.sub(r'\.\d{3,}$', '', name)
    
    # Check regex for _high, _hp, _highpoly
    high_match = re.search(r'^(.*?)(_high|_hp|_highpoly|\.high|-high)(.*)$', clean_n, re.IGNORECASE)
    if high_match:
        group = high_match.group(1).rstrip('_ .-')
        var = high_match.group(3).lstrip('_ .-')
        return (group if group else "Asset"), 'high', var

    low_match = re.search(r'^(.*?)(_low|_lp|_lowpoly|\.low|-low)(.*)$', clean_n, re.IGNORECASE)
    if low_match:
        group = low_match.group(1).rstrip('_ .-')
        var = low_match.group(3).lstrip('_ .-')
        return (group if group else "Asset"), 'low', var
        
    # Check collections
    for col in obj.users_collection:
        col_n = col.name.lower()
        if any(s in col_n for s in ["high", "hp", "highpoly"]):
            return MESH_OT_auto_rename_high_low.clean_base_name(clean_n), 'high', ""
        if any(s in col_n for s in ["low", "lp", "lowpoly"]):
            return MESH_OT_auto_rename_high_low.clean_base_name(clean_n), 'low', ""

    return None, 'none', ""


def populate_bake_groups(context, selection_only=True):
    props = context.scene.rex_marmoset_bridge_props
    
    selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
    if selection_only and selected_meshes:
        target_objs = selected_meshes
    else:
        target_objs = [o for o in context.scene.objects if o.type == 'MESH']
        
    if not target_objs:
        return
        
    # Build dictionary of groups: group_name -> {'low': [objs], 'high': [objs]}
    groups_dict = {}
    
    for obj in target_objs:
        group_name, mesh_type, _ = get_object_group_info(obj)
        if mesh_type == 'none' or not group_name:
            continue
            
        if group_name not in groups_dict:
            groups_dict[group_name] = {'low': [], 'high': []}
            
        if mesh_type == 'low':
            groups_dict[group_name]['low'].append(obj)
        elif mesh_type == 'high':
            groups_dict[group_name]['high'].append(obj)

    # Preserve locked groups while rebuilding/updating
    locked_group_names = {bg.group_name for bg in props.bake_groups if bg.is_locked}
    
    # Store previous lock states
    prev_locks = {bg.group_name: bg.is_locked for bg in props.bake_groups}
    prev_exp = {bg.group_name: bg.is_expanded for bg in props.bake_groups}
    
    # Clear unlocked entries
    i = len(props.bake_groups) - 1
    while i >= 0:
        if not props.bake_groups[i].is_locked:
            props.bake_groups.remove(i)
        i -= 1

    existing_group_names = {bg.group_name for bg in props.bake_groups}
    
    for g_name, mesh_data in groups_dict.items():
        if not mesh_data['low'] and not mesh_data['high']:
            continue
            
        if g_name in existing_group_names:
            continue # Keep locked version
            
        bg = props.bake_groups.add()
        bg.group_name = g_name
        bg.is_locked = prev_locks.get(g_name, False)
        bg.is_expanded = prev_exp.get(g_name, False)
        
        bg.low_meshes.clear()
        for o in mesh_data['low']:
            item = bg.low_meshes.add()
            item.obj = o
            item.name = o.name
            
        bg.high_meshes.clear()
        for o in mesh_data['high']:
            item = bg.high_meshes.add()
            item.obj = o
            item.name = o.name



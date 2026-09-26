import bpy
import os

def has_any_override(overrides):
    """Check if any individual override flag is enabled."""
    if not overrides: return False
    flags = [
        'override_path', 'override_texture_copy_path', 'override_format', 'override_preset', 
        'override_remove_armature_root', 'override_rename_armature', 
        'override_reset_transform', 'override_pre_rotation', 'override_pre_scale',
        'override_single_mesh'
    ]
    return any(getattr(overrides, f, False) for f in flags)

def get_resolved_val(coll, prop_name, global_settings):
    """Find the resolved value for a property by checking the collection and its parents."""
    mapping = {
        'export_path': 'override_path',
        'texture_copy_path': 'override_texture_copy_path',
        'export_format': 'override_format',
        'export_preset': 'override_preset',
        'fbx_remove_armature_root': 'override_remove_armature_root',
        'rename_armature': 'override_rename_armature',
        'reset_transform': 'override_reset_transform',
        'pre_rotation': 'override_pre_rotation',
        'pre_scale': 'override_pre_scale',
        'single_mesh': 'override_single_mesh',
    }
    
    flag = mapping.get(prop_name)
    if not flag:
        return getattr(global_settings, prop_name)

    # 1. Check current collection
    overrides = getattr(coll, "rex_export_overrides", None)
    if overrides and getattr(overrides, flag, False):
        return getattr(overrides, prop_name)
    
    # 2. Check parents recursively
    parents = [c for c in bpy.data.collections if coll.name in c.children]
    for parent in parents:
        if parent.name == "Scene Collection" or parent == bpy.context.scene.collection:
            continue
        val = _find_in_parents(parent, prop_name, flag)
        if val is not None:
            return val
            
    # 3. Fallback to global
    return getattr(global_settings, prop_name)

def _find_in_parents(coll, prop_name, flag):
    overrides = getattr(coll, "rex_export_overrides", None)
    if overrides and getattr(overrides, flag, False):
        return getattr(overrides, prop_name)
    
    parents = [c for c in bpy.data.collections if coll.name in c.children.keys()]
    for parent in parents:
        if parent.name == "Scene Collection" or parent == bpy.context.scene.collection:
            continue
        val = _find_in_parents(parent, prop_name, flag)
        if val is not None:
            return val
    return None

def get_effective_overrides(coll, global_settings):
    """Recursively find the first active override in the collection hierarchy and resolve all properties."""
    overrides = getattr(coll, "rex_export_overrides", None)
    
    # If this collection has any override enabled, it's our "source" and we resolve all props starting here
    if has_any_override(overrides):
        from types import SimpleNamespace
        res = SimpleNamespace()
        
        props = [
            'export_path', 'texture_copy_path', 'export_format', 'export_preset', 
            'fbx_remove_armature_root', 'rename_armature', 
            'reset_transform', 'pre_rotation', 'pre_scale', 'single_mesh'
        ]
        
        for p in props:
            setattr(res, p, get_resolved_val(coll, p, global_settings))
            
        return coll, res
    
    # Otherwise, check if any parent has overrides enabled
    parents = [c for c in bpy.data.collections if coll.name in c.children]
    for parent in parents:
        if parent.name == "Scene Collection" or parent == bpy.context.scene.collection:
            continue
        source, res = get_effective_overrides(parent, global_settings)
        if res != global_settings:
            return source, res
            
    return bpy.context.scene, global_settings

def get_export_groups(context, settings):
    mode = settings.export_mode
    limit = settings.export_limit
    global_path = bpy.path.abspath(settings.export_path)
    
    # Determine items based on limit
    objs_to_check = []
    if limit == 'VISIBLE':
        objs_to_check = [obj for obj in context.view_layer.objects if obj.visible_get()]
    elif limit == 'SELECTED':
        objs_to_check = [obj for obj in context.selected_objects]
    elif limit == 'RENDER':
        objs_to_check = [obj for obj in context.view_layer.objects if not obj.hide_render]
        
    if not objs_to_check:
        return {}

    # Filter by type early to avoid non-exportable objects (cameras, lights) triggering groups
    objs_to_check = [o for o in objs_to_check if o.type in {'MESH', 'ARMATURE', 'EMPTY'}]
    
    if not objs_to_check:
        return {}

    # Grouping
    export_groups = {} # { name: {'objects': [], 'settings': settings, 'source': source, 'path': path} }

    # Shared Armature Pre-check
    shared_armature_obj = None
    if settings.shared_armature:
        armatures = [o for o in objs_to_check if o.type == 'ARMATURE']
        if len(armatures) == 1:
            shared_armature_obj = armatures[0]
            # Remove the armature from main list so it doesn't create its own group
            objs_to_check = [o for o in objs_to_check if o != shared_armature_obj]
        else:
            # If 0 or >1 armatures, shared armature mode is effectively disabled
            # We could report here, but get_export_groups is usually called multiple times
            pass

    if mode == 'OBJECTS':
        for obj in objs_to_check:
            if obj.type not in {'MESH', 'ARMATURE', 'EMPTY'}: continue
            
            # Find effective settings from collections
            source = context.scene
            eff_settings = settings
            for coll in obj.users_collection:
                s, es = get_effective_overrides(coll, settings)
                if es != settings:
                    source = s
                    eff_settings = es
                    break
            
            path = bpy.path.abspath(eff_settings.export_path) if eff_settings.export_path else global_path
            if not path: continue
            
            export_groups[obj.name] = {'objects': [obj], 'settings': eff_settings, 'source': source, 'path': path}
            
    elif mode == 'PARENTS':
        for obj in objs_to_check:
            root = obj
            while root.parent:
                root = root.parent
            
            if root.name not in export_groups:
                # Find effective settings from root object's collections
                source = context.scene
                eff_settings = settings
                for coll in root.users_collection:
                    s, es = get_effective_overrides(coll, settings)
                    if es != settings:
                        source = s
                        eff_settings = es
                        break
                
                path = bpy.path.abspath(eff_settings.export_path) if eff_settings.export_path else global_path
                if not path: continue
                
                export_groups[root.name] = {'objects': [], 'settings': eff_settings, 'source': source, 'path': path}
            
            if obj not in export_groups[root.name]['objects']:
                export_groups[root.name]['objects'].append(obj)
        
        # Fill in the rest of the children for root groups
        for r_name in export_groups:
            root_obj = bpy.data.objects.get(r_name)
            if root_obj:
                for child in root_obj.children_recursive:
                    if child.type == 'MESH' and child not in export_groups[r_name]['objects']:
                         if child not in context.view_layer.objects.values(): continue
                         if limit == 'VISIBLE' and not child.visible_get(): continue
                         if limit == 'RENDER' and child.hide_render: continue
                         export_groups[r_name]['objects'].append(child)
                
                if root_obj.type in {'MESH', 'ARMATURE', 'EMPTY'} and root_obj not in export_groups[r_name]['objects']:
                    if root_obj in context.view_layer.objects.values():
                        if limit == 'VISIBLE' and not root_obj.visible_get(): pass
                        elif limit == 'RENDER' and root_obj.hide_render: pass
                        else:
                            export_groups[r_name]['objects'].append(root_obj)

    elif mode == 'COLLECTIONS':
        for obj in objs_to_check:
            colls = obj.users_collection
            for coll in colls:
                # Check collection level limits
                if coll.name == "Scene Collection": continue
                if limit == 'RENDER' and coll.hide_render: continue
                if limit == 'VISIBLE' and coll.hide_viewport: continue
                
                # Shared Armature Exclusion: Skip collections that contain the shared armature
                if shared_armature_obj and coll in shared_armature_obj.users_collection:
                    continue
                
                if coll.name not in export_groups:
                    # Determine effective settings using hierarchy
                    source, eff_settings = get_effective_overrides(coll, settings)
                    
                    path = bpy.path.abspath(eff_settings.export_path) if eff_settings.export_path else global_path
                    if not path: continue
                    
                    export_groups[coll.name] = {'objects': [], 'settings': eff_settings, 'source': source, 'path': path}
                
                if obj not in export_groups[coll.name]['objects']:
                    export_groups[coll.name]['objects'].append(obj)
        
        # Fill in the rest of collection items
        for c_name in export_groups:
            coll = bpy.data.collections.get(c_name)
            if coll:
                for c_obj in coll.all_objects:
                    if c_obj.type in {'MESH', 'ARMATURE', 'EMPTY'} and c_obj not in export_groups[c_name]['objects']:
                         if c_obj not in context.view_layer.objects.values(): continue
                         if limit == 'VISIBLE' and not c_obj.visible_get(): continue
                         if limit == 'RENDER' and c_obj.hide_render: continue
                         export_groups[c_name]['objects'].append(c_obj)
                         
    # Remove empty groups (e.g. empty collections or collections with no valid meshes)
    if settings.shared_armature and shared_armature_obj:
        # In shared armature mode, we only want to export groups that contain at least one mesh.
        # This prevents the armature's own collection or collections with only helper empties from triggering an export.
        export_groups = {k: v for k, v in export_groups.items() if any(o.type == 'MESH' for o in v['objects'])}
    else:
        export_groups = {k: v for k, v in export_groups.items() if v['objects']}

    # Inject Shared Armature into every remaining group
    if shared_armature_obj:
        for data in export_groups.values():
            if shared_armature_obj not in data['objects']:
                data['objects'].append(shared_armature_obj)
    
    return export_groups


"""
Utility for removing the Armature root node from FBX exports.

Uses module-level monkey-patching of Blender's internal FBX exporter functions
to skip the Armature container while preserving the full bone hierarchy.

Inspired by: https://github.com/A-Ribeiro/CustomBlenderFBXExporter
"""
import bpy


def _apply_fbx_patches():
    """
    Monkey-patch io_scene_fbx.export_fbx_bin to skip Armature Model nodes
    and redirect bone/mesh connections from the Armature to the scene root (0).
    Returns a dict of original functions for restoration.
    """
    import io_scene_fbx.export_fbx_bin as fbx_mod

    originals = {
        'fbx_data_object_elements': fbx_mod.fbx_data_object_elements,
        'fbx_data_empty_elements': fbx_mod.fbx_data_empty_elements,
        'fbx_connections_elements': fbx_mod.fbx_connections_elements,
    }

    # --- PATCH 1: Skip creating Model node for Armature objects ---
    _orig_object_elements = fbx_mod.fbx_data_object_elements

    def _patched_object_elements(root, ob_obj, scene_data):
        if ob_obj.is_object and ob_obj.type == 'ARMATURE':
            return  # Don't write a Model node for the Armature
        return _orig_object_elements(root, ob_obj, scene_data)

    fbx_mod.fbx_data_object_elements = _patched_object_elements

    # --- PATCH 2: Skip creating Null data node for Armature objects ---
    # Armatures are stored in data_empties and written as Null nodes.
    _orig_empty_elements = fbx_mod.fbx_data_empty_elements

    def _patched_empty_elements(root, empty, scene_data):
        if hasattr(empty, 'type') and empty.type == 'ARMATURE':
            return  # Don't write the Null data for the Armature
        return _orig_empty_elements(root, empty, scene_data)

    fbx_mod.fbx_data_empty_elements = _patched_empty_elements

    # --- PATCH 3: Filter connections to remove Armature and redirect children ---
    _orig_connections = fbx_mod.fbx_connections_elements

    def _patched_connections(root, scene_data):
        # Collect all Armature UUIDs
        armature_uuids = set()
        for ob_obj in scene_data.objects:
            if ob_obj.is_object and ob_obj.type == 'ARMATURE':
                armature_uuids.add(ob_obj.fbx_uuid)

        if armature_uuids:
            new_connections = []
            for conn in scene_data.connections:
                c_type, uid_src, uid_dst, prop = conn

                # Drop connections FROM the Armature (Armature -> parent)
                if uid_src in armature_uuids:
                    continue

                # Redirect children of the Armature to the Scene Root (0)
                # This promotes root bones and parented meshes to the top level.
                if uid_dst in armature_uuids:
                    new_connections.append((c_type, uid_src, 0, prop))
                    continue

                new_connections.append(conn)

            # Replace connections list in-place (works even inside namedtuple)
            scene_data.connections.clear()
            scene_data.connections.extend(new_connections)

        return _orig_connections(root, scene_data)

    fbx_mod.fbx_connections_elements = _patched_connections

    return originals


def _restore_fbx_patches(originals):
    """Restore original FBX export functions."""
    import io_scene_fbx.export_fbx_bin as fbx_mod
    for name, func in originals.items():
        setattr(fbx_mod, name, func)


def run_patched_fbx_export(context, **kwargs):
    """
    Run FBX export with armature root removal patches applied.
    Patches are applied before export and restored immediately after,
    so other exports are not affected.
    """
    originals = None
    try:
        originals = _apply_fbx_patches()
        print("RexTools3: FBX patches applied (Remove Armature Root)")
        bpy.ops.export_scene.fbx(**kwargs)
        print("RexTools3: FBX export completed with patches")
    except Exception as e:
        print(f"RexTools3 Error in patched FBX export: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to standard export
        print("RexTools3: Falling back to standard FBX export")
        if originals:
            _restore_fbx_patches(originals)
        bpy.ops.export_scene.fbx(**kwargs)
    finally:
        if originals:
            _restore_fbx_patches(originals)
            print("RexTools3: FBX patches restored")

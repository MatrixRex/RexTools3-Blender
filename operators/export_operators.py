import bpy
import os
from bpy.types import Operator
from bpy.props import StringProperty

from ..core import export_overrides as exp_core

# Forward helper names for compatibility
has_any_override = exp_core.has_any_override
get_resolved_val = exp_core.get_resolved_val
get_effective_overrides = exp_core.get_effective_overrides
get_export_groups = exp_core.get_export_groups

class REXTOOLS3_OT_Export(Operator):
    bl_idname = "rextools3.export"
    bl_label = "Export"
    bl_description = "Export objects based on settings"
    
    def execute(self, context):
        global_settings = context.scene.rex_export_settings
        export_mode = global_settings.export_mode
        export_groups = get_export_groups(context, global_settings)
            
        if not export_groups:
            self.report({'ERROR'}, "No objects found to export with current settings.")
            return {'CANCELLED'}

        # Execution
        orig_active = context.view_layer.objects.active
        orig_selection = context.selected_objects[:]
        orig_mode = context.active_object.mode if context.active_object else 'OBJECT'

        # Switch to object mode if needed
        if orig_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for name, data in export_groups.items():
            objs = data['objects']
            if not objs: continue
            
            # Use settings for this group (either global or override)
            item_settings = data['settings']
            fmt = item_settings.export_format
            preset_name = item_settings.export_preset
            
            # Fetch preset arguments
            preset_args = self.get_preset_args(fmt, preset_name)

            dest_dir = data.get('path') or bpy.path.abspath(item_settings.export_path)
            if not dest_dir:
                dest_dir = bpy.path.abspath(global_settings.export_path)
            
            if not dest_dir:
                self.report({'WARNING'}, f"Skipping {name}: No export path defined.")
                continue

            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)
            
            filepath = os.path.join(dest_dir, f"{name}.{fmt.lower()}")
            
            bpy.ops.object.select_all(action='DESELECT')
            valid_objs = []
            for o in objs:
                try:
                    o.select_set(True)
                    valid_objs.append(o)
                except Exception as e:
                    print(f"Skipping selection for {o.name}: {e}")
            
            if not valid_objs:
                continue
            
            # --- Single Mesh Option (Collections mode only) ---
            temp_single_mesh_objs = []
            if export_mode == 'COLLECTIONS' and getattr(item_settings, 'single_mesh', False):
                mesh_objs = [o for o in valid_objs if o.type == 'MESH']
                non_mesh_objs = [o for o in valid_objs if o.type != 'MESH']
                
                if mesh_objs:
                    dup_objs = []
                    for o in mesh_objs:
                        dup_o = o.copy()
                        dup_o.data = o.data.copy()
                        context.scene.collection.objects.link(dup_o)
                        dup_objs.append(dup_o)
                    
                    bpy.ops.object.select_all(action='DESELECT')
                    for dup_o in dup_objs:
                        context.view_layer.objects.active = dup_o
                        dup_o.select_set(True)
                        for mod in list(dup_o.modifiers):
                            if mod.type != 'ARMATURE':
                                try:
                                    bpy.ops.object.modifier_apply(modifier=mod.name)
                                except Exception as e:
                                    print(f"Could not apply modifier {mod.name} on {dup_o.name}: {e}")
                        dup_o.select_set(False)
                    
                    bpy.ops.object.select_all(action='DESELECT')
                    for dup_o in dup_objs:
                        dup_o.select_set(True)
                    context.view_layer.objects.active = dup_objs[0]
                    
                    if len(dup_objs) > 1:
                        bpy.ops.object.join()
                    
                    merged_obj = context.active_object
                    merged_obj.name = name
                    if merged_obj.data:
                        merged_obj.data.name = name
                    
                    temp_single_mesh_objs.append(merged_obj)
                    valid_objs = [merged_obj] + non_mesh_objs

                    # Refresh selection for updated valid_objs
                    bpy.ops.object.select_all(action='DESELECT')
                    for o in valid_objs:
                        try:
                            o.select_set(True)
                        except Exception as e:
                            print(f"Skipping selection for {o.name}: {e}")

            # Sort by hierarchy depth (root first) to ensure parents are reset before children
            def get_obj_depth(obj):
                depth = 0
                curr = obj
                while curr.parent:
                    curr = curr.parent
                    depth += 1
                return depth
            
            valid_objs.sort(key=get_obj_depth)
            
            context.view_layer.objects.active = valid_objs[0]
            
            # Prepare export arguments
            op_args = {'filepath': filepath, 'use_selection': True}
            if fmt == 'OBJ':
                op_args = {'filepath': filepath, 'export_selected': True}
            
            # Update with preset args
            op_args.update(preset_args)
            
            # Check for Modifiers + Shape Keys conflict
            for o in valid_objs:
                if (o.type == 'MESH' and o.data.shape_keys and 
                    any(m.show_viewport for m in o.modifiers)):
                    
                    from ..core import notify
                    notify.error("Shape keys won't be exported. Modifier found in object.")
                    break

            # --- Rename Armature ---
            saved_armature_names = {} # { armature_obj: (orig_obj_name, orig_data_name) }
            clash_backups = [] # [(object_or_data, original_name)]
            
            if item_settings.rename_armature:
                # 1. Clear the 'Armature' name slot by renaming existing clashing items
                # Objects
                for obj in bpy.data.objects:
                    if obj.name == "Armature":
                        clash_backups.append((obj, obj.name))
                        obj.name = "Armature_REX_TEMP"
                
                # Armature Data
                for arm in bpy.data.armatures:
                    if arm.name == "Armature":
                        clash_backups.append((arm, arm.name))
                        arm.name = "Armature_REX_TEMP"

                # 2. Rename our target armatures to 'Armature'
                for o in valid_objs:
                    if o.type == 'ARMATURE':
                        saved_armature_names[o] = (o.name, o.data.name)
                        o.data.name = "Armature"
                        o.name = "Armature"
            
            # --- Check Armature Rest Position ---
            saved_armature_pose_position = {} # { armature_obj: original_pose_position }
            for o in valid_objs:
                if o.type == 'ARMATURE' and o.data.pose_position == 'REST':
                    saved_armature_pose_position[o] = 'REST'
                    o.data.pose_position = 'POSE'

            # --- Reset Transform ---
            import mathutils
            saved_transforms = {}
            # In COLLECTIONS mode, we treat the entire collection as a single unit.
            # We find the first top-level object to use as a shared pivot, then move everything by that offset.
            # This prevents siblings from overlapping at the origin.
            export_mode = global_settings.export_mode
            source_coll = data['source'] if isinstance(data['source'], bpy.types.Collection) else None
            
            if item_settings.reset_transform:
                # In COLLECTIONS mode, the user wants to treat the collection as the root (always at center).
                # To center the model, we must move the "1st level children" (direct members of the collection) to the origin.
                # Deeper children (parented to these 1st level objects) should follow their parents and not be reset individually.
                if export_mode == 'COLLECTIONS' and source_coll:
                    for o in source_coll.objects:
                        # Safety: only process if the object is actually being exported
                        if o in valid_objs:
                            try:
                                saved_transforms[o] = o.matrix_world.copy()
                                _, _, scl = o.matrix_world.decompose()
                                # Move to world origin (0,0,0) with identity rotation, preserving scale
                                o.matrix_world = mathutils.Matrix.LocRotScale((0, 0, 0), mathutils.Quaternion((1, 0, 0, 0)), scl)
                            except Exception as e:
                                print(f"Failed to reset transform for collection member {o.name}: {e}")
                else:
                    # For OBJECTS or PARENTS mode, or if no collection is found:
                    # Move every root object in the group to origin individually.
                    for o in valid_objs:
                        # Only reset transform for "root" objects in this group (no parent in group).
                        if o.parent and o.parent in valid_objs:
                            continue
                            
                        try:
                            saved_transforms[o] = o.matrix_world.copy()
                            _, _, scl = o.matrix_world.decompose()
                            o.matrix_world = mathutils.Matrix.LocRotScale((0, 0, 0), mathutils.Quaternion((1, 0, 0, 0)), scl)
                        except Exception as e:
                            print(f"Failed to reset transform for {o.name}: {e}")
                
                # Ensure children transforms are updated based on moved parents before export
                context.view_layer.update()

            # --- Pre-export transforms ---
            pre_rot = item_settings.pre_rotation
            pre_scl = item_settings.pre_scale
            needs_pre_rotation = any(v != 0.0 for v in pre_rot)
            needs_pre_scale = pre_scl != 1.0

            if needs_pre_rotation or needs_pre_scale:
                # Select only valid objects for transform
                bpy.ops.object.select_all(action='DESELECT')
                for o in valid_objs:
                    try: o.select_set(True)
                    except: pass

                if needs_pre_rotation:
                    for o in valid_objs:
                        # Inverse Step: Subtract pre_rot to prepare for application
                        o.rotation_euler.x -= pre_rot[0]
                        o.rotation_euler.y -= pre_rot[1]
                        o.rotation_euler.z -= pre_rot[2]
                    # Freeze Step: Bake the inverse rotation into mesh/armature data
                    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
                    for o in valid_objs:
                        # Offset Step: Restore visual state by adding back pre_rot
                        # This leaves the rotation values in the fields for export
                        o.rotation_euler.x += pre_rot[0]
                        o.rotation_euler.y += pre_rot[1]
                        o.rotation_euler.z += pre_rot[2]

                if needs_pre_scale:
                    for o in valid_objs:
                        # Inverse Step: Divide by pre_scl to prepare for application
                        o.scale /= pre_scl
                    # Freeze Step: Bake the inverse scale into mesh/armature data
                    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                    for o in valid_objs:
                        # Offset Step: Restore visual state by multiplying back pre_scl
                        # This leaves the scale values in the fields for export
                        o.scale *= pre_scl

            try:
                if fmt == 'FBX':
                    if item_settings.fbx_remove_armature_root:
                        from ..core import fbx_utils
                        fbx_utils.run_patched_fbx_export(context, **op_args)
                    else:
                        bpy.ops.export_scene.fbx(**op_args)
                elif fmt == 'GLTF':
                    op_args['export_format'] = 'GLB'
                    bpy.ops.export_scene.gltf(**op_args)
                elif fmt == 'OBJ':
                    bpy.ops.wm.obj_export(**op_args)
                
                # Update last export path to this successfully used directory
                global_settings.last_export_path = dest_dir
            except Exception as e:
                self.report({'ERROR'}, f"Failed to export {name}: {e}")
            finally:
                # --- Restore pre-export transforms ---
                if needs_pre_rotation or needs_pre_scale:
                    bpy.ops.object.select_all(action='DESELECT')
                    for o in valid_objs:
                        try: o.select_set(True)
                        except: pass

                    if needs_pre_scale:
                        # Finalize Step: Bring the object back to 1.0 applied
                        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

                    if needs_pre_rotation:
                        # Finalize Step: Bring the object back to (0,0,0) applied
                        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
                
                # --- Restore Reset Transform ---
                if item_settings.reset_transform:
                    for o, mat in saved_transforms.items():
                        try:
                            o.matrix_world = mat
                        except Exception as e:
                            print(f"Failed to restore transform for {o.name}: {e}")
                    
                    # Ensure children transforms are updated after restoring parents
                    context.view_layer.update()

                # --- Restore Armature Names ---
                if item_settings.rename_armature:
                    # Restore our targets first
                    for o, (orig_obj_name, orig_data_name) in saved_armature_names.items():
                        try:
                            o.name = orig_obj_name
                            o.data.name = orig_data_name
                        except Exception as e:
                            print(f"Failed to restore armature name: {e}")
                    
                    # Restore clashing items (in reverse to avoid chain collisions)
                    for item, orig_name in reversed(clash_backups):
                        try:
                            item.name = orig_name
                        except Exception as e:
                            print(f"Failed to restore clashing name: {e}")
                
                # --- Restore Armature Pose Position ---
                for o, orig_pos in saved_armature_pose_position.items():
                    try:
                        o.data.pose_position = orig_pos
                    except Exception as e:
                        print(f"Failed to restore armature pose position: {e}")

                # --- Clean up Temporary Single Mesh Object ---
                if temp_single_mesh_objs:
                    for t_obj in temp_single_mesh_objs:
                        try:
                            t_mesh = t_obj.data
                            bpy.data.objects.remove(t_obj, do_unlink=True)
                            if t_mesh and t_mesh.users == 0:
                                bpy.data.meshes.remove(t_mesh)
                        except Exception as e:
                            print(f"Failed to remove temporary single mesh object: {e}")

        # Restore
        bpy.ops.object.select_all(action='DESELECT')
        for o in orig_selection:
            try: o.select_set(True)
            except: pass
        context.view_layer.objects.active = orig_active
        
        if orig_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode=orig_mode)
            except Exception as e:
                print(f"Failed to restore mode {orig_mode}: {e}")

        # Detailed console output
        print("\n--- RexTools3 Export Summary ---")
        for name, data in export_groups.items():
            objs_names = ", ".join([o.name for o in data['objects']])
            print(f"Exported: {name} -> {data['path']} (Objects: {objs_names})")
        print("--------------------------------\n")


        self.report({'INFO'}, f"Batch Export Finished. Exported {len(export_groups)} items.")
        return {'FINISHED'}

    def get_preset_args(self, fmt, preset_name):
        if preset_name == 'NONE':
            return {}
            
        import os
        import bpy
        
        fmt_folder = {
            'FBX': "export_scene.fbx",
            'GLTF': "export_scene.gltf",
            'OBJ': "export_scene.obj"
        }.get(fmt)
        
        if not fmt_folder:
            return {}
            
        paths = bpy.utils.preset_paths(os.path.join("operator", fmt_folder))
        preset_file = None
        for p in paths:
            potential = os.path.join(p, f"{preset_name}.py")
            if os.path.exists(potential):
                preset_file = potential
                break
        
        if not preset_file:
            return {}
            
        args = {}
        try:
            with open(preset_file, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if line.strip().startswith("op."):
                        parts = line.split("=")
                        if len(parts) == 2:
                            prop = parts[0].replace("op.", "").strip()
                            val_str = parts[1].strip()
                            
                            # Ignore path-related properties from presets
                            if prop in {'filepath', 'directory', 'filename'}:
                                continue
                                
                            try:
                                val = eval(val_str, {"__builtins__": None}, {})
                                args[prop] = val
                            except:
                                if val_str.startswith("'") or val_str.startswith('"'):
                                    args[prop] = val_str.strip("'\"")
        except Exception as e:
            print(f"Error parsing preset {preset_name}: {e}")
            
        return args

class REXTOOLS3_OT_BrowseExportPath(Operator):
    bl_idname = "rextools3.browse_export_path"
    bl_label = "Browse"
    
    directory: StringProperty(subtype='DIR_PATH')
    target: StringProperty() # 'SCENE', 'COLLECTION'
    target_name: StringProperty() # Name of the collection
    
    def execute(self, context):
        if self.target == 'SCENE':
            context.scene.rex_export_settings.export_path = self.directory
        elif self.target == 'COLLECTION':
            name = self.target_name
            coll = bpy.data.collections.get(name) or context.view_layer.active_layer_collection.collection
            if coll:
                coll.rex_export_overrides.export_path = self.directory
                coll.rex_export_overrides.override_path = True
            else:
                self.report({'ERROR'}, "No valid collection found.")
                return {'CANCELLED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class REXTOOLS3_OT_OpenExportFolder(Operator):
    bl_idname = "rextools3.open_export_folder"
    bl_label = "Open Export Folder"
    bl_description = "Open the folder containing the last exported file"

    def execute(self, context):
        import subprocess
        import sys
        
        path = context.scene.rex_export_settings.last_export_path
        if not path or not os.path.exists(path):
            self.report({'ERROR'}, "No valid export path found.")
            return {'CANCELLED'}

        if sys.platform.startswith('win'):
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])

        return {'FINISHED'}
class REXTOOLS3_OT_ClearAllOverrides(Operator):
    bl_idname = "rextools3.clear_all_overrides"
    bl_label = "Clear All Overrides"
    bl_description = "Disable all overrides and reset flags for this collection"
    
    @classmethod
    def poll(cls, context):
        return context.collection is not None

    def execute(self, context):
        coll = context.collection
        overrides = coll.rex_export_overrides
        
        overrides.override_path = False
        overrides.override_texture_copy_path = False
        overrides.override_format = False
        overrides.override_preset = False
        overrides.override_remove_armature_root = False
        overrides.override_rename_armature = False
        overrides.override_reset_transform = False
        overrides.override_pre_rotation = False
        overrides.override_pre_scale = False
        overrides.override_single_mesh = False
        
        self.report({'INFO'}, f"Cleared all overrides for {coll.name}")
        return {'FINISHED'}

from ..core import export_texture_utils as tex_utils

FORMAT_EXTENSIONS = tex_utils.FORMAT_EXTENSIONS
_get_image_filename = tex_utils._get_image_filename
_collect_images_from_material = tex_utils._collect_images_from_material
_collect_images_from_object = tex_utils._collect_images_from_object
_resolve_image_on_disk = tex_utils._resolve_image_on_disk
_save_memory_image_to_disk = tex_utils._save_memory_image_to_disk


class REXTOOLS3_OT_CopyTextures(Operator):
    bl_idname = "rextools3.copy_textures"
    bl_label = "Copy Textures"
    bl_description = "Copy textures used by materials on the current export targets to a specified folder"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        import shutil
        from ..core import notify
        
        settings = context.scene.rex_export_settings
        export_groups = get_export_groups(context, settings)
        if not export_groups:
            self.report({'ERROR'}, "No export targets found with current settings.")
            return {'CANCELLED'}
            
        # Collect textures per-destination directory
        # { resolved_dest_dir: set_of_images }
        dest_images = {}
        
        for name, data in export_groups.items():
            item_settings = data['settings']
            # Resolve destination directory, fallback to global scene-level setting if empty
            dest_dir = bpy.path.abspath(item_settings.texture_copy_path) if hasattr(item_settings, 'texture_copy_path') and item_settings.texture_copy_path else bpy.path.abspath(settings.texture_copy_path)
            
            if not dest_dir:
                self.report({'WARNING'}, f"Skipping texture copy for group '{name}': No copy path defined.")
                continue
                
            if dest_dir not in dest_images:
                dest_images[dest_dir] = set()
                
            # Collect all mesh/object textures for this group
            for obj in data['objects']:
                dest_images[dest_dir].update(_collect_images_from_object(obj))
                                        
        total_images = sum(len(imgs) for imgs in dest_images.values())
        if total_images == 0:
            self.report({'WARNING'}, "No textures found in export materials.")
            return {'FINISHED'}
            
        copied_count = 0
        skipped_count = 0
        missing_count = 0
        dest_dir_names = set()
        
        for dest_dir, images in dest_images.items():
            if not images:
                continue
                
            # Ensure destination directory exists
            if not os.path.exists(dest_dir):
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to create directory {dest_dir}: {str(e)}")
                    continue
                    
            dest_dir_names.add(os.path.basename(dest_dir) or dest_dir)
            
            for img in images:
                # Handle UDIM / Tiled images
                is_udim = (img.source == 'TILED') or (img.filepath and ("<UDIM>" in img.filepath or "<udim>" in img.filepath))
                
                if is_udim and hasattr(img, "tiles") and len(img.tiles) > 0:
                    base_filename = _get_image_filename(img)
                    for tile in img.tiles:
                        tile_str = str(tile.number)
                        tile_filename = base_filename.replace("<UDIM>", tile_str).replace("<udim>", tile_str)
                        if "<UDIM>" not in base_filename and "<udim>" not in base_filename:
                            name_part, ext_part = os.path.splitext(base_filename)
                            tile_filename = f"{name_part}_{tile_str}{ext_part}"
                            
                        # Look on disk
                        src_path = _resolve_image_on_disk(img, tile_filename)
                        if not src_path:
                            # Try resolving tile filepath directly
                            if img.filepath:
                                t_path = bpy.path.abspath(img.filepath).replace("<UDIM>", tile_str).replace("<udim>", tile_str)
                                if os.path.isfile(t_path):
                                    src_path = t_path
                                    
                        dest_path = os.path.join(dest_dir, tile_filename)
                        if src_path and os.path.isfile(src_path):
                            try:
                                should_copy = True
                                if os.path.exists(dest_path):
                                    try:
                                        if os.path.samefile(src_path, dest_path):
                                            should_copy = False
                                        elif os.path.getmtime(src_path) <= os.path.getmtime(dest_path):
                                            should_copy = False
                                    except Exception:
                                        if os.path.normcase(os.path.abspath(src_path)) == os.path.normcase(os.path.abspath(dest_path)):
                                            should_copy = False
                                        else:
                                            try:
                                                if os.path.getmtime(src_path) <= os.path.getmtime(dest_path):
                                                    should_copy = False
                                            except Exception:
                                                pass
                                if should_copy:
                                    shutil.copy2(src_path, dest_path)
                                    copied_count += 1
                                else:
                                    skipped_count += 1
                            except Exception as e:
                                self.report({'WARNING'}, f"Failed to copy tile {tile_filename}: {str(e)}")
                        else:
                            missing_count += 1
                    continue
                
                # Standard / Non-UDIM image handling
                filename = _get_image_filename(img)
                src_path = _resolve_image_on_disk(img, filename)
                
                # If not found on disk, attempt saving from memory/packed data
                if not src_path:
                    has_memory_data = (img.packed_file is not None) or img.has_data or img.is_dirty or (img.size[0] > 0 and img.size[1] > 0)
                    if has_memory_data:
                        if bpy.data.is_saved and bpy.data.filepath:
                            blend_dir = os.path.dirname(bpy.data.filepath)
                            local_textures_dir = os.path.join(blend_dir, "textures")
                            local_file_path = os.path.join(local_textures_dir, filename)
                            if _save_memory_image_to_disk(img, local_file_path):
                                src_path = local_file_path
                                # Link image to local textures folder
                                img.filepath = f"//textures/{filename}"
                        else:
                            # Blend file not saved: save directly to destination
                            dest_path = os.path.join(dest_dir, filename)
                            if _save_memory_image_to_disk(img, dest_path):
                                copied_count += 1
                                continue
                                
                if not src_path or not os.path.isfile(src_path):
                    print(f"[RexTools3] Texture could not be found or extracted: {img.name} ({img.filepath})")
                    missing_count += 1
                    continue
                    
                dest_path = os.path.join(dest_dir, filename)
                
                try:
                    should_copy = True
                    if os.path.exists(dest_path):
                        try:
                            if os.path.samefile(src_path, dest_path):
                                should_copy = False
                            elif os.path.getmtime(src_path) <= os.path.getmtime(dest_path):
                                should_copy = False
                        except Exception:
                            if os.path.normcase(os.path.abspath(src_path)) == os.path.normcase(os.path.abspath(dest_path)):
                                should_copy = False
                            else:
                                try:
                                    if os.path.getmtime(src_path) <= os.path.getmtime(dest_path):
                                        should_copy = False
                                except Exception:
                                    pass
                    if should_copy:
                        shutil.copy2(src_path, dest_path)
                        copied_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    self.report({'WARNING'}, f"Failed to copy {filename}: {str(e)}")
                    
        dest_desc = ", ".join(f"'{name}'" for name in dest_dir_names)
        msg = f"Copied {copied_count} texture(s)"
        if skipped_count > 0:
            msg += f", {skipped_count} already existed"
        if missing_count > 0:
            msg += f", {missing_count} missing"
        msg += f" in {dest_desc}."
        
        self.report({'INFO'}, msg)
        if copied_count > 0:
            notify.success(msg)
        elif skipped_count > 0:
            notify.info(msg)
        else:
            notify.warning(msg)
            
        return {'FINISHED'}


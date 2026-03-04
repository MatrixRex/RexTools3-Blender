import bpy
import os
from bpy.types import Operator
from bpy.props import StringProperty

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

    # Grouping
    export_groups = {} # { name: {'objects': [], 'path': ""} }

    if mode == 'OBJECTS':
        for obj in objs_to_check:
            if obj.type != 'MESH': continue
            path = bpy.path.abspath(obj.export_location) if obj.export_location else global_path
            if not path: continue
            export_groups[obj.name] = {'objects': [obj], 'path': path}
            
    elif mode == 'PARENTS':
        for obj in objs_to_check:
            root = obj
            while root.parent:
                root = root.parent
            
            if root.name not in export_groups:
                path = bpy.path.abspath(root.export_location) if root.export_location else global_path
                if not path: continue
                export_groups[root.name] = {'objects': [], 'path': path}
            
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
                
                if root_obj.type == 'MESH' and root_obj not in export_groups[r_name]['objects']:
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
                
                if coll.name not in export_groups:
                    path = bpy.path.abspath(coll.export_location) if coll.export_location else global_path
                    if not path: continue
                    export_groups[coll.name] = {'objects': [], 'path': path}
                
                if obj not in export_groups[coll.name]['objects']:
                    export_groups[coll.name]['objects'].append(obj)
        
        # Fill in the rest of collection items
        for c_name in export_groups:
            coll = bpy.data.collections.get(c_name)
            if coll:
                for c_obj in coll.all_objects:
                    if c_obj.type == 'MESH' and c_obj not in export_groups[c_name]['objects']:
                         if c_obj not in context.view_layer.objects.values(): continue
                         if limit == 'VISIBLE' and not c_obj.visible_get(): continue
                         if limit == 'RENDER' and c_obj.hide_render: continue
                         export_groups[c_name]['objects'].append(c_obj)
                         
    # Remove empty groups (e.g. empty collections or collections with no valid meshes)
    export_groups = {k: v for k, v in export_groups.items() if v['objects']}
    
    return export_groups

class REXTOOLS3_OT_Export(Operator):
    bl_idname = "rextools3.export"
    bl_label = "Export"
    bl_description = "Export objects based on settings"
    
    def execute(self, context):
        settings = context.scene.rex_export_settings
        fmt = settings.export_format
        preset_name = settings.export_preset
        
        export_groups = get_export_groups(context, settings)
            
        if not export_groups:
            self.report({'ERROR'}, "No objects found to export with current settings.")
            return {'CANCELLED'}

        # Fetch preset arguments
        preset_args = self.get_preset_args(fmt, preset_name)

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
            
            dest_dir = data['path']
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

            # --- Reset Transform ---
            import mathutils
            saved_transforms = {}
            if settings.reset_transform:
                for o in valid_objs:
                    try:
                        saved_transforms[o] = o.matrix_world.copy()
                        _, _, scl = o.matrix_world.decompose()
                        o.matrix_world = mathutils.Matrix.LocRotScale((0, 0, 0), mathutils.Quaternion((1, 0, 0, 0)), scl)
                    except Exception as e:
                        print(f"Failed to reset transform for {o.name}: {e}")

            # --- Pre-export transforms ---
            pre_rot = settings.pre_rotation
            pre_scl = settings.pre_scale
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
                    if settings.fbx_remove_armature_root:
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
                context.scene.rex_export_settings.last_export_path = dest_dir
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
                if settings.reset_transform:
                    for o, mat in saved_transforms.items():
                        try:
                            o.matrix_world = mat
                        except Exception as e:
                            print(f"Failed to restore transform for {o.name}: {e}")

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
    target: StringProperty() # 'SCENE', 'COLLECTION', 'OBJECT'
    target_name: StringProperty() # Name of the object or collection
    
    def execute(self, context):
        if self.target == 'SCENE':
            context.scene.rex_export_settings.export_path = self.directory
        elif self.target == 'COLLECTION':
            name = self.target_name
            coll = bpy.data.collections.get(name) or context.view_layer.active_layer_collection.collection
            if coll:
                coll.export_location = self.directory
            else:
                self.report({'ERROR'}, "No valid collection found.")
                return {'CANCELLED'}
        elif self.target == 'OBJECT':
            name = self.target_name
            obj = bpy.data.objects.get(name) or context.active_object
            if obj:
                obj.export_location = self.directory
            else:
                self.report({'ERROR'}, "No valid object found.")
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

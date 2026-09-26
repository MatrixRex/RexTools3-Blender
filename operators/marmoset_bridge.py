import bpy
import os
import tempfile
import subprocess
import glob
from bpy.types import Operator
from .object_auto_rename_low_high import MESH_OT_auto_rename_high_low
from .pbr_assign import PBR_OT_AssignTexture
from ..core import notify
from ..core import marmoset_utils as mset_core

# Forward helper names for compatibility
ensure_image_on_disk = mset_core.ensure_image_on_disk
find_material_textures = mset_core.find_material_textures
get_object_group_info = mset_core.get_object_group_info
populate_bake_groups = mset_core.populate_bake_groups


class REXTOOLS3_OT_marmoset_bridge_refresh_groups(Operator):
    bl_idname = "rextools3.marmoset_bridge_refresh_groups"
    bl_label = "Detect / Refresh Bake Groups"
    bl_description = "Auto-detect Bake Groups from selected or scene meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        populate_bake_groups(context, selection_only=bool(context.selected_objects))
        props = context.scene.rex_marmoset_bridge_props
        notify.success(f"Detected {len(props.bake_groups)} Bake Group(s)")
        return {'FINISHED'}


class REXTOOLS3_OT_marmoset_bridge_toggle_lock(Operator):
    bl_idname = "rextools3.marmoset_bridge_toggle_lock"
    bl_label = "Toggle Group Lock"
    bl_description = "Lock or unlock Bake Group(s) to persist export targets"
    bl_options = {'REGISTER', 'UNDO'}

    group_index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        props = context.scene.rex_marmoset_bridge_props
        if self.group_index == -1:
            props.global_lock = not props.global_lock
            for bg in props.bake_groups:
                bg.is_locked = props.global_lock
        elif 0 <= self.group_index < len(props.bake_groups):
            bg = props.bake_groups[self.group_index]
            bg.is_locked = not bg.is_locked
            props.global_lock = all(g.is_locked for g in props.bake_groups) if props.bake_groups else False
        return {'FINISHED'}


class REXTOOLS3_OT_marmoset_bridge_toggle_expand(Operator):
    bl_idname = "rextools3.marmoset_bridge_toggle_expand"
    bl_label = "Toggle Group Expand"
    bl_description = "Expand or collapse Bake Group sub-mesh list"
    bl_options = {'REGISTER'}

    group_index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        props = context.scene.rex_marmoset_bridge_props
        if 0 <= self.group_index < len(props.bake_groups):
            bg = props.bake_groups[self.group_index]
            bg.is_expanded = not bg.is_expanded
        return {'FINISHED'}


class REXTOOLS3_OT_marmoset_bridge_prep(Operator):
    bl_idname = "rextools3.marmoset_bridge_prep"
    bl_label = "Prepare Meshes & Materials"
    bl_description = "Auto rename high/low meshes and materials per Bake Group (Marmoset convention)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.rex_marmoset_bridge_props
        if props.bake_groups:
            return True
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        return len(selected_objects) >= 2

    def execute(self, context):
        props = context.scene.rex_marmoset_bridge_props
        renamer_props = context.scene.highlow_renamer_props
        
        populate_bake_groups(context, selection_only=bool(context.selected_objects) and not any(bg.is_locked for bg in props.bake_groups))
        
        if not props.bake_groups:
            selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
            if len(selected_meshes) >= 2:
                bpy.ops.mesh.auto_rename_high_low()
                populate_bake_groups(context, selection_only=True)

        if not props.bake_groups:
            self.report({'ERROR'}, "No Bake Groups found to prepare")
            return {'CANCELLED'}
            
        high_suffix = renamer_props.high_prefix if renamer_props.high_prefix else "_high"
        low_suffix = renamer_props.low_prefix if renamer_props.low_prefix else "_low"
        
        prepared_count = 0
        
        for bg in props.bake_groups:
            group_name = bg.group_name.strip()
            if not group_name:
                group_name = "Asset"
                
            low_objs = [ref.obj for ref in bg.low_meshes if ref.obj and ref.obj.name in context.scene.objects]
            high_objs = [ref.obj for ref in bg.high_meshes if ref.obj and ref.obj.name in context.scene.objects]
            
            if not low_objs and not high_objs:
                continue
                
            # Rename low meshes to Marmoset convention: group_name_low or group_name_low_1, group_name_low_2...
            for idx, low_obj in enumerate(low_objs):
                if len(low_objs) == 1:
                    target_name = f"{group_name}{low_suffix}"
                else:
                    target_name = f"{group_name}{low_suffix}_{idx + 1}"
                if low_obj.name != target_name:
                    existing = bpy.data.objects.get(target_name)
                    if existing and existing != low_obj:
                        existing.name += ".old"
                    low_obj.name = target_name
                    
            # Rename high meshes to Marmoset convention: group_name_high or group_name_high_1, group_name_high_2...
            for idx, high_obj in enumerate(high_objs):
                if len(high_objs) == 1:
                    target_name = f"{group_name}{high_suffix}"
                else:
                    target_name = f"{group_name}{high_suffix}_{idx + 1}"
                if high_obj.name != target_name:
                    existing = bpy.data.objects.get(target_name)
                    if existing and existing != high_obj:
                        existing.name += ".old"
                    high_obj.name = target_name
                    
            # Match materials between high and low objects in this group
            for high_obj in high_objs:
                for i, slot in enumerate(high_obj.material_slots):
                    high_mat = slot.material
                    if not high_mat:
                        continue
                    orig_name = high_mat.name
                    if orig_name.endswith(high_suffix):
                        base_name = orig_name[:-len(high_suffix)]
                    elif orig_name.endswith(low_suffix):
                        base_name = orig_name[:-len(low_suffix)]
                    else:
                        base_name = orig_name
                        
                    target_high_mat_name = base_name + high_suffix
                    target_low_mat_name = base_name
                    
                    if high_mat.name != target_high_mat_name:
                        high_mat.name = target_high_mat_name
                        
                    low_mat = bpy.data.materials.get(target_low_mat_name)
                    if not low_mat:
                        low_mat = bpy.data.materials.new(name=target_low_mat_name)
                        low_mat.use_nodes = True
                        
                    for low_obj in low_objs:
                        while len(low_obj.material_slots) < i + 1:
                            low_obj.data.materials.append(None)
                        low_obj.material_slots[i].material = low_mat
                        
            prepared_count += 1

        # Re-populate references to sync updated names
        populate_bake_groups(context, selection_only=False)
            
        notify.success(f"Prepared {prepared_count} Bake Group(s) & materials")
        return {'FINISHED'}


class REXTOOLS3_OT_marmoset_bridge_send(Operator):
    bl_idname = "rextools3.marmoset_bridge_send"
    bl_label = "Send to Marmoset"
    bl_description = "Export high/low poly meshes to FBX per Bake Group and launch Marmoset Toolbag"
    bl_options = {'REGISTER', 'UNDO'}

    group_name: bpy.props.StringProperty(default="")

    @classmethod
    def poll(cls, context):
        props = context.scene.rex_marmoset_bridge_props
        if props.bake_groups:
            return True
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        return len(selected_objects) >= 2

    def execute(self, context):
        props = context.scene.rex_marmoset_bridge_props
        renamer_props = context.scene.highlow_renamer_props
        
        # Check marmoset path in preferences
        addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
        prefs = context.preferences.addons[addon_name].preferences
        marmoset_path = bpy.path.abspath(prefs.marmoset_path)
        
        if not marmoset_path or not os.path.exists(marmoset_path):
            self.report({'ERROR'}, f"Marmoset Toolbag executable not found at: {marmoset_path}. Configure in Preferences.")
            return {'CANCELLED'}
            
        # Determine export directory
        export_dir = bpy.path.abspath(props.export_path)
        if not export_dir:
            if bpy.data.filepath:
                export_dir = os.path.dirname(bpy.data.filepath)
            else:
                self.report({'ERROR'}, "Save the blend file first, or specify a Bake Output Path.")
                return {'CANCELLED'}
                
        if not os.path.exists(export_dir):
            os.makedirs(export_dir, exist_ok=True)
            
        # Ensure bake groups are populated
        populate_bake_groups(context, selection_only=bool(context.selected_objects) and not any(bg.is_locked for bg in props.bake_groups))
        
        # Determine target bake groups to export
        if self.group_name:
            target_groups = [bg for bg in props.bake_groups if bg.group_name.lower() == self.group_name.lower()]
        else:
            locked_groups = [bg for bg in props.bake_groups if bg.is_locked]
            target_groups = locked_groups if locked_groups else list(props.bake_groups)
            
        if not target_groups:
            self.report({'ERROR'}, "No Bake Groups available to send")
            return {'CANCELLED'}
            
        # 1. Run prep logic if enabled
        if props.auto_rename:
            bpy.ops.rextools3.marmoset_bridge_prep()
            
        # Export individual FBX files for each target Bake Group
        active_obj = context.view_layer.objects.active
        selected_objs = list(context.selected_objects)
        
        exported_fbx_files = [] # list of (low_fbx_path, high_fbx_path, group_name)
        texture_assignments = {}
        expected_mats = []
        
        try:
            for bg in target_groups:
                g_name = bg.group_name.strip()
                if not g_name:
                    g_name = "Asset"
                    
                low_objs = [ref.obj for ref in bg.low_meshes if ref.obj and ref.obj.name in context.scene.objects]
                high_objs = [ref.obj for ref in bg.high_meshes if ref.obj and ref.obj.name in context.scene.objects]
                
                if not low_objs and not high_objs:
                    continue
                    
                asset_prefix = props.asset_name.strip()
                file_base = f"{asset_prefix}_{g_name}" if asset_prefix else g_name
                
                low_fbx_path = os.path.join(export_dir, f"{file_base}_low.fbx")
                high_fbx_path = os.path.join(export_dir, f"{file_base}_high.fbx")
                
                if low_objs:
                    bpy.ops.object.select_all(action='DESELECT')
                    for o in low_objs:
                        o.select_set(True)
                    context.view_layer.objects.active = low_objs[0]
                    bpy.ops.export_scene.fbx(
                        filepath=low_fbx_path,
                        use_selection=True,
                        object_types={'MESH'},
                        add_leaf_bones=False,
                        bake_anim=False
                    )
                    
                if high_objs:
                    bpy.ops.object.select_all(action='DESELECT')
                    for o in high_objs:
                        o.select_set(True)
                    context.view_layer.objects.active = high_objs[0]
                    bpy.ops.export_scene.fbx(
                        filepath=high_fbx_path,
                        use_selection=True,
                        object_types={'MESH'},
                        add_leaf_bones=False,
                        bake_anim=False
                    )
                    
                exported_fbx_files.append((low_fbx_path if low_objs else None, high_fbx_path if high_objs else None, g_name))
                
                # Scan high poly textures if enabled
                if props.send_textures:
                    for high_obj in high_objs:
                        for slot in high_obj.material_slots:
                            if slot.material and slot.material.name not in texture_assignments:
                                tex_dict = find_material_textures(slot.material, export_dir)
                                if tex_dict:
                                    texture_assignments[slot.material.name] = tex_dict
                                    expected_mats.append(slot.material.name)
        finally:
            # Restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for o in selected_objs:
                if o.name in context.scene.objects:
                    o.select_set(True)
            context.view_layer.objects.active = active_obj if active_obj and active_obj.name in context.scene.objects else None

        if not exported_fbx_files:
            self.report({'ERROR'}, "Failed to export FBX files for selected Bake Group(s)")
            return {'CANCELLED'}

        # Check if Marmoset is running
        marmoset_bin = os.path.basename(marmoset_path)
        is_running = False
        import sys
        if sys.platform == 'win32':
            try:
                cmd = f'tasklist /NH /FI "IMAGENAME eq {marmoset_bin}"'
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                output = subprocess.check_output(cmd, startupinfo=startupinfo, shell=True).decode('utf-8', errors='ignore')
                is_running = marmoset_bin.lower() in output.lower()
            except Exception:
                pass
        else:
            try:
                output = subprocess.check_output(["pgrep", "-f", marmoset_bin]).decode('utf-8')
                is_running = bool(output.strip())
            except Exception:
                pass

        if is_running:
            self.report({'INFO'}, f"Marmoset running. Exported {len(exported_fbx_files)} Bake Group FBX(s) (Auto-reloading in Toolbag).")
            notify.success(f"FBX exported for {len(exported_fbx_files)} group(s) & auto-reloading in Marmoset")
            return {'FINISHED'}
            
        # Generate Marmoset Script with multiple FBX model imports
        ext = props.file_format.lower()
        asset_base = props.asset_name.strip() if props.asset_name.strip() else "Bake"
        script_output_base = os.path.join(export_dir, f"{asset_base}.{ext}").replace("\\", "/")
        
        import json
        tex_assign_str = json.dumps(texture_assignments)
        expected_mats_str = json.dumps(expected_mats)
        
        fbx_import_lines = []
        for low_f, high_f, _ in exported_fbx_files:
            if low_f:
                clean_low = os.path.normpath(low_f).replace("\\", "/")
                fbx_import_lines.append(f'baker.importModel(r"{clean_low}")')
            if high_f:
                clean_high = os.path.normpath(high_f).replace("\\", "/")
                fbx_import_lines.append(f'baker.importModel(r"{clean_high}")')
                
        imports_block = "\n".join(fbx_import_lines)

        script_content = f"""import mset
import os
import time

mset.newScene()
baker = mset.BakerObject()
baker.outputPath = r"{script_output_base}"
baker.outputWidth = {props.resolution}
baker.outputHeight = {props.resolution}
baker.outputBits = 8
baker.outputSamples = 16

# Disable all default maps
for m in baker.getAllMaps():
    m.enabled = False

# Setup suffixes and enable selected maps
albedo_map = baker.getMap("Albedo")
if albedo_map:
    albedo_map.enabled = {props.bake_albedo}
    albedo_map.suffix = "_albedo"

normal_map = baker.getMap("Normals")
if normal_map:
    normal_map.enabled = {props.bake_normals}
    normal_map.suffix = "_normal"

roughness_map = baker.getMap("Roughness")
if roughness_map:
    roughness_map.enabled = {props.bake_roughness}
    roughness_map.suffix = "_roughness"

metalness_map = baker.getMap("Metalness")
if metalness_map:
    metalness_map.enabled = {props.bake_metallic}
    metalness_map.suffix = "_metallic"

ao_map = baker.getMap("Ambient Occlusion")
if ao_map:
    ao_map.enabled = {props.bake_ao}
    ao_map.suffix = "_ao"

# Import models via Quick Loader for each Bake Group
{imports_block}

# Asynchronous wait loop for FBX models to finish importing
expected_mats = {expected_mats_str}
start_time = time.time()
while time.time() - start_time < 8.0:
    current_mats = [m.name for m in mset.getAllMaterials()]
    matched_count = 0
    for exp_name in expected_mats:
        exp_clean = exp_name.lower().replace(" ", "").replace("_", "")
        for curr_name in current_mats:
            curr_clean = curr_name.lower().replace(" ", "").replace("_", "")
            if exp_clean == curr_clean or exp_clean in curr_clean or curr_clean in exp_clean:
                matched_count += 1
                break
    if matched_count >= len(expected_mats):
        break
    time.sleep(0.1)

# Assign high poly textures to materials
all_mats = {{m.name: m for m in mset.getAllMaterials()}}
texture_assignments = {tex_assign_str}

for mat_name, tex_dict in texture_assignments.items():
    mat = None
    if mat_name in all_mats:
        mat = all_mats[mat_name]
    else:
        target_clean = mat_name.lower().replace(" ", "").replace("_", "")
        for m_name, m_obj in all_mats.items():
            m_clean = m_name.lower().replace(" ", "").replace("_", "")
            if target_clean == m_clean or target_clean in m_clean or m_clean in target_clean:
                mat = m_obj
                break
                
    if mat:
        if 'albedo' in tex_dict and os.path.exists(tex_dict['albedo']):
            mat.setSubroutine("albedo", "Albedo")
            mat.albedo.setField("Albedo Map", mset.Texture(tex_dict['albedo']))
            f = mat.albedo.getField("Albedo Map")
            if f: f.sRGB = True
            
        if 'normal' in tex_dict and os.path.exists(tex_dict['normal']):
            mat.setSubroutine("surface", "Normals")
            mat.surface.setField("Normal Map", mset.Texture(tex_dict['normal']))
            f = mat.surface.getField("Normal Map")
            if f: f.sRGB = False
            
        if 'roughness' in tex_dict and os.path.exists(tex_dict['roughness']):
            mat.setSubroutine("microsurface", "Roughness")
            mat.microsurface.setField("Roughness Map", mset.Texture(tex_dict['roughness']))
            f = mat.microsurface.getField("Roughness Map")
            if f: f.sRGB = False
            
        if 'metallic' in tex_dict and os.path.exists(tex_dict['metallic']):
            mat.setSubroutine("reflectivity", "Metalness")
            mat.reflectivity.setField("Metalness Map", mset.Texture(tex_dict['metallic']))
            f = mat.reflectivity.getField("Metalness Map")
            if f: f.sRGB = False

print("Marmoset Toolbag 5 setup complete.")
"""
        
        # Write temporary script
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
        tmp_name = tmp.name
        tmp.close()
        try:
            with open(tmp_name, "w", encoding="utf-8") as f:
                f.write(script_content)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to write temp script: {e}")
            return {'CANCELLED'}
            
        # Launch Marmoset
        try:
            subprocess.Popen([marmoset_path, "-py", tmp_name])
            self.report({'INFO'}, f"Sent {len(exported_fbx_files)} Bake Group(s) to Marmoset Toolbag 5")
            notify.success(f"FBX exported & Marmoset launched for {len(exported_fbx_files)} group(s)")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to launch Marmoset Toolbag: {e}")
            return {'CANCELLED'}
            
        return {'FINISHED'}



class REXTOOLS3_OT_marmoset_bridge_get_textures(Operator):
    bl_idname = "rextools3.marmoset_bridge_get_textures"
    bl_label = "Import Baked Textures"
    bl_description = "Scan the export path for baked maps and assign them to the low-poly material nodes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        target_objects = [o for o in context.selected_objects if o.type == 'MESH']
        if not target_objects and context.active_object:
            target_objects = [context.active_object]
            
        if not target_objects:
            self.report({'ERROR'}, "No mesh selected")
            return {'CANCELLED'}
            
        props = context.scene.rex_marmoset_bridge_props
        
        # Determine export directory
        export_dir = bpy.path.abspath(props.export_path)
        if not export_dir:
            if bpy.data.filepath:
                export_dir = os.path.dirname(bpy.data.filepath)
            else:
                self.report({'ERROR'}, "Save the blend file first, or specify a Bake Output Path.")
                return {'CANCELLED'}
                
        # Resolve asset name
        asset_name = props.asset_name.strip()
        if not asset_name:
            asset_name = MESH_OT_auto_rename_high_low.clean_base_name(target_objects[0].name)
            if not asset_name:
                self.report({'ERROR'}, "Please specify the Asset Name.")
                return {'CANCELLED'}
                
        if not os.path.exists(export_dir):
            self.report({'ERROR'}, f"Bake Output Path does not exist: {export_dir}")
            return {'CANCELLED'}
            
        # Search for baked files
        pattern = os.path.join(export_dir, f"{asset_name}*")
        files = glob.glob(pattern)
        
        if not files:
            self.report({'WARNING'}, f"No baked files found starting with '{asset_name}' in: {export_dir}")
            return {'CANCELLED'}
            
        # Suffix matching lists mapping to Easy PBR input names
        map_types = {
            'Base Color': ['_albedo', '_basecolor', '_base_color', '_diffuse', '_color', '_col', '_bc', '_d', '_c'],
            'Normal': ['_normal', '_normals', '_normal_map'],
            'AO': ['_ao', '_ambient_occlusion', '_occlusion'],
            'Roughness': ['_roughness', '_rough', '_rgh'],
            'Metallic': ['_metallic', '_metal', '_met'],
            'Height': ['_height', '_displacement'],
            'Curvature': ['_curvature', '_curve'],
            'Thickness': ['_thickness'],
        }
        
        # Associate map types with found files and gather their modification times
        found_files = [] # list of (map_type, filepath, mtime)
        import time
        current_time = time.time()
        
        for filepath in files:
            filename = os.path.basename(filepath)
            name_no_ext, _ = os.path.splitext(filename)
            name_no_ext = name_no_ext.lower()
            
            for m_type, suffixes in map_types.items():
                matched = False
                for suffix in suffixes:
                    if name_no_ext.endswith(suffix):
                        mtime = os.path.getmtime(filepath)
                        found_files.append((m_type, filepath, mtime))
                        matched = True
                        break
                if matched:
                    break
                    
        if not found_files:
            self.report({'WARNING'}, f"No baked map matching suffixes (like _normal, _ao) found for '{asset_name}'")
            return {'CANCELLED'}
            
        # Filter files: check if any matched file was modified in the last 10 minutes (600s)
        recent_threshold = 600
        has_recent = any((current_time - mtime) < recent_threshold for _, _, mtime in found_files)
        
        # Collect maps to assign
        found_maps = {}
        for m_type, filepath, mtime in found_files:
            if has_recent:
                # If there are recent bakes, only import files updated recently
                if (current_time - mtime) < recent_threshold:
                    found_maps[m_type] = filepath
            else:
                # Otherwise fall back to importing all matching files
                found_maps[m_type] = filepath
                
        if not found_maps:
            self.report({'WARNING'}, f"No recently baked maps found for '{asset_name}'")
            return {'CANCELLED'}
            
        # Assign to all materials on the target low-poly objects
        assigned_mats_count = 0
        modified_materials = set()
        
        for obj in target_objects:
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or mat in modified_materials:
                    continue
                    
                for map_type, filepath in found_maps.items():
                    if map_type in {'Base Color', 'Normal', 'AO', 'Roughness', 'Metallic', 'Height', 'Alpha', 'Emission'}:
                        colorspace = 'sRGB' if map_type == 'Base Color' else 'Non-Color'
                        # Assign texture using Easy PBR system logic
                        ok = PBR_OT_AssignTexture.assign_texture_to_input(
                            context=context,
                            material=mat,
                            input_name=map_type,
                            image_path=filepath,
                            colorspace=colorspace
                        )
                        if not ok:
                            self.report({'WARNING'}, f"Failed to assign {map_type} to material {mat.name}")
                    else:
                        # Load texture into shader editor without connecting it to anything
                        mat.use_nodes = True
                        nodes = mat.node_tree.nodes
                        
                        img_name = os.path.basename(filepath)
                        img = bpy.data.images.get(img_name)
                        if img:
                            img.filepath = filepath
                            img.reload()
                        else:
                            img = bpy.data.images.load(filepath)
                        img.colorspace_settings.name = 'Non-Color'
                        
                        # Create/get texture node
                        tex_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.label == f"Baked {map_type}"), None)
                        if not tex_node:
                            tex_node = nodes.new('ShaderNodeTexImage')
                            tex_node.label = f"Baked {map_type}"
                        tex_node.image = img
                        
                        # Position it dynamically based on map type
                        y_offsets = {
                            'Curvature': -450,
                            'Thickness': -600
                        }
                        tex_node.location = (-600, y_offsets.get(map_type, -400))
                        
                assigned_mats_count += 1
                modified_materials.add(mat)
            
        # Auto-arrange nodes for modified materials to keep them clean
        for mat in modified_materials:
            if mat and mat.use_nodes:
                try:
                    orig_active = context.active_object.active_material if context.active_object else None
                    if context.active_object:
                        context.active_object.active_material = mat
                        bpy.ops.pbr.arrange_nodes()
                        if orig_active:
                            context.active_object.active_material = orig_active
                except Exception:
                    pass
            
        if assigned_mats_count > 0:
            assigned_names = ", ".join(found_maps.keys())
            notify.success(f"Imported {assigned_names} maps to {assigned_mats_count} material(s)")
        else:
            self.report({'WARNING'}, "No materials found on active object(s) to assign textures")
            return {'CANCELLED'}
            
        return {'FINISHED'}

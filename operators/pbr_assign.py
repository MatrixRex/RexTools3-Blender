import bpy
import os
import re
from pathlib import Path
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, EnumProperty
from ..core import notify
from .. import properties


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_principled_and_base_tex(material):
    """Return (principled_node, base_texture_node, base_image) or (None,None,None)."""
    if not material or not material.use_nodes:
        return None, None, None
    nodes = material.node_tree.nodes
    principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not principled:
        return None, None, None

    # 1. Easy check: Look for the named BaseTex directly
    base_tex = nodes.get("BaseTex")
    if base_tex and base_tex.type == 'TEX_IMAGE' and base_tex.image:
        return principled, base_tex, base_tex.image

    # 2. Fallback: Crawl back from BSDF
    base_inp = principled.inputs.get('Base Color')
    if not base_inp or not base_inp.is_linked:
        return principled, None, None

    curr = base_inp.links[0].from_node
    tex = None
    
    # Simple loop to step back through any Tint or AO mix nodes
    # We follow the 'A' or 'Color1' slot back
    while curr:
        if curr.type == 'TEX_IMAGE':
            tex = curr
            break
        
        # Follow the chain backwards
        next_node = None
        # Handle BaseTintMix, AOMix, or generic Mix nodes
        if curr.type in ('MIX', 'MIX_RGB'):
            # Slot A for 'MIX', Slot Color1 for 'MIX_RGB'
            a_sock = curr.inputs.get('A') or curr.inputs.get('Color1')
            if a_sock and a_sock.is_linked:
                next_node = a_sock.links[0].from_node
        
        if not next_node: break
        curr = next_node

    img = tex.image if tex else None
    return principled, tex, img


def _derive_stem_from_base(filename_no_ext_lower: str) -> str:
    """
    Try to peel off common base-color suffixes (and combos) from the end
    to derive a 'stem' for matching. Handles cases like:
      MCX_Mat_AlbedoTransparency -> mcx_mat
      bullet_albedo               -> bullet
      Model_D                     -> model
    """
    # allow compound endings like "albedotransparency"
    suffixes = [
        'albedo', 'basecolor', 'base_color', 'base-colour', 'basecolour', 'base',
        'diffuse', 'color', 'colour', 'col',
        'opacity', 'transparency',
        'alb', 'bc', 'diff', 'd', 'c' # short versions
    ]
    # Try compound endings first (albedo+opacity/transparency)
    patt_combo = r'(.+?)(?:[_\-]?(?:albedo|basecolor|base_color|base\-colour|basecolour|diffuse|color|colour|col))' \
                 r'(?:[_\-]?(?:opacity|transparency))$'
    m = re.match(patt_combo, filename_no_ext_lower, re.IGNORECASE)
    if m:
        return m.group(1)

    # Then single endings
    patt_single = r'(.+?)(?:[_\-](?:' + '|'.join(suffixes) + r'))$'
    m = re.match(patt_single, filename_no_ext_lower, re.IGNORECASE)
    if m:
        return m.group(1)

    return filename_no_ext_lower


def _find_matches_in_dir(stem_lower: str, folder: Path, mapping: dict) -> dict:
    """Return dict slot->Path for first found match per slot."""
    exts = {'.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr', '.bmp', '.webp'}
    results = {}
    if not folder.exists() or not folder.is_dir():
        return results

    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]
    names = [(p, p.stem.lower()) for p in files]

    for slot, suffixes in mapping.items():
        found = None
        # prefer longer suffix tokens
        for suf in sorted(suffixes, key=len, reverse=True):
            for p, n in names:
                # Must start with stem (or be exactly the stem if it's the base color)
                if not n.startswith(stem_lower):
                    continue
                
                # Check for suffix with common separators or as standalone if stem matches
                # We check for f"_{suf}" or f"-{suf}" to avoid partial matches inside the stem
                # but we also check if the suffix IS the rest of the string
                is_match = False
                for sep in ('_', '-'):
                    pattern = rf"{re.escape(stem_lower)}{re.escape(sep)}{re.escape(suf)}$"
                    if re.search(pattern, n):
                        is_match = True
                        break
                
                if is_match:
                    found = p
                    break
            if found: break
        if found:
            results[slot] = found
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Assign Texture Operator (existing)
# ─────────────────────────────────────────────────────────────────────────────

PACKED_ITEMS = [
    ('NONE', "None", ""),
    ('Roughness', "Roughness", ""),
    ('Metallic', "Metallic", ""),
    ('AO', "AO", ""),
    ('Alpha', "Alpha", ""),
    ('Emission', "Emission", ""),
    ('Normal', "Normal", ""),
    ('Base Color', "Base Color", ""),
]

class PBR_OT_AssignTexture(Operator):
    bl_idname = "pbr.assign_texture"
    bl_label = "Assign Texture"
    bl_options = {'REGISTER', 'UNDO'}

    input_name: StringProperty()
    colorspace: StringProperty(default='sRGB')
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.exr;*.bmp;*.webp', options={'HIDDEN'})
    filter_image: BoolProperty(default=True, options={'HIDDEN'})

    use_packed: BoolProperty(name="Packed Setup", default=False)
    packed_r: EnumProperty(name="R", items=PACKED_ITEMS, default='NONE')
    packed_g: EnumProperty(name="G", items=PACKED_ITEMS, default='NONE')
    packed_b: EnumProperty(name="B", items=PACKED_ITEMS, default='NONE')
    packed_a: EnumProperty(name="A", items=PACKED_ITEMS, default='NONE')

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "input_name")
        layout.prop(self, "colorspace")
        
        layout.separator()
        layout.prop(self, "use_packed")
        if self.use_packed:
            box = layout.box()
            # Making it look similar to the user's provided screenshot
            col = box.column(align=True)
            
            row = col.row()
            row.label(text="R", icon='COLOR_RED')
            row.prop(self, "packed_r", text="")
            
            row = col.row()
            row.label(text="G", icon='COLOR_GREEN')
            row.prop(self, "packed_g", text="")
            
            row = col.row()
            row.label(text="B", icon='COLOR_BLUE')
            row.prop(self, "packed_b", text="")
            
            row = col.row()
            row.label(text="A", icon='IMAGE_ALPHA')
            row.prop(self, "packed_a", text="")

    def execute(self, context):
        mat = context.active_object.active_material
        if not mat:
            self.report({'ERROR'}, "No active material")
            return {'CANCELLED'}

        if self.use_packed:
            maps = {
                'R': self.packed_r,
                'G': self.packed_g,
                'B': self.packed_b,
                'A': self.packed_a,
            }
            any_assigned = False
            for chan, slot in maps.items():
                if slot == 'NONE':
                    continue
                
                # Update the channel mapping in material settings if applicable
                # Note: 'Base Color' and 'Normal' don't use the channel property in properties.py loop currently
                slot_key = slot.lower().replace(" ", "_")
                prop_name = f"{slot_key}_channel"
                if hasattr(mat.pbr_settings, prop_name):
                    setattr(mat.pbr_settings, prop_name, chan)
                
                # For packed textures, we usually want Non-Color unless it's Base Color
                cspace = 'Non-Color' if slot != 'Base Color' else 'sRGB'
                
                ok = self.assign_texture_to_input(context, mat, slot, self.filepath, cspace)
                if ok:
                    any_assigned = True
            
            if any_assigned:
                notify.success(f"Packed textures assigned from {os.path.basename(self.filepath)}")
            else:
                self.report({'WARNING'}, "No slots assigned from packed texture")
                return {'CANCELLED'}
        else:
            ok = self.assign_texture_to_input(context, mat, self.input_name, self.filepath, self.colorspace)
            if not ok:
                self.report({'ERROR'}, "Failed to assign texture")
                return {'CANCELLED'}

        bpy.ops.pbr.arrange_nodes()
        return {'FINISHED'}

    def invoke(self, context, event):
        mat = context.active_object.active_material
        if mat and hasattr(mat, "pbr_settings"):
            # Default to the persistent material setting if not explicitly overridden
            # We check if it's set to the default (False) and then check the material
            # But the UI code in pbr_panel.py already passes it. This is a safety.
            if not self.use_packed:
                self.use_packed = mat.pbr_settings.use_packed_mode

        if self.input_name:
            self.bl_label = f"Assign {self.input_name}"
        self.filter_image = True
        self.filter_glob = '*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.exr;*.bmp;*.webp'
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    @staticmethod
    def assign_texture_to_input(context, material, input_name, image_path, colorspace='sRGB'):
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        principled = next((n for n in nodes if n.type=='BSDF_PRINCIPLED'), None)
        if not principled:
            return False

        try:
            image = bpy.data.images.load(image_path)
        except Exception:
            return False

        if input_name == 'Base Color':
            image.alpha_mode = 'CHANNEL_PACKED'
        image.colorspace_settings.name = colorspace

        # Capture current tint if we are assigning to Base Color, so we can preserve it
        current_tint = (1.0, 1.0, 1.0, 1.0)
        if input_name == 'Base Color':
            bc_inp = principled.inputs.get('Base Color')
            if bc_inp:
                if bc_inp.is_linked:
                    src = bc_inp.links[0].from_node
                    if src.type == 'MIX_RGB':
                        current_tint = src.inputs['Color2'].default_value[:]
                else:
                    current_tint = bc_inp.default_value[:]

        # remove old chain
        def gather(n, out):
            if n in out: return
            out.add(n)
            for i in n.inputs:
                if i.is_linked:
                    gather(i.links[0].from_node, out)

        if input_name == 'AO':
            # For AO, we check our specific Mix node instead of a BSDF socket
            ao_mix = nodes.get("PBR AO Mix")
            if ao_mix:
                to_del = set()
                # Gather everything behind Color2 (which is the AO side)
                ao_in = ao_mix.inputs.get('Color2')
                if ao_in and ao_in.is_linked:
                    gather(ao_in.links[0].from_node, to_del)
                # Note: we don't remove the ao_mix itself here because we recreate it below
                # or the logic below will handle it. Actually, easiest is to just delete if it exists.
                for n in to_del:
                    try: nodes.remove(n)
                    except: pass
                # Clean up the specific named helper nodes too
                for name in ["AOSplit", "AOMix", "AOAdd", "AOTex"]:
                    node = nodes.get(name)
                    if node:
                        try: nodes.remove(node)
                        except: pass
        elif input_name == 'Emission':
            # Emission is also special: Emission Color socket
            inp_sock = principled.inputs.get('Emission Color')
            if inp_sock and inp_sock.is_linked:
                to_del = set()
                gather(inp_sock.links[0].from_node, to_del)
                for l in list(inp_sock.links):
                    links.remove(l)
                for n in to_del:
                    try: nodes.remove(n)
                    except: pass
            # Clean up specifically named helper nodes
            for name in ["EmissionSplit", "EmissionTintMix", "EmissionTex"]:
                node = nodes.get(name)
                if node:
                    try: nodes.remove(node)
                    except: pass
        else:
            # Standard BSDF socket logic
            inp_sock = principled.inputs.get(input_name)
            if inp_sock and inp_sock.is_linked:
                to_del = set()
                gather(inp_sock.links[0].from_node, to_del)
                for l in list(inp_sock.links):
                    links.remove(l)
                for n in to_del:
                    try:
                        nodes.remove(n)
                    except Exception:
                        pass

        base_pos = {
            'Base Color': 200,
            'Metallic':   100,
            'Roughness':    0,
            'Normal':     -100,
            'Alpha':      -200,
            'AO':         250,
            'Emission':   350,
        }
        y = base_pos.get(input_name, 0)
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = image
        tex_node.location = (-400, y)
        if input_name == 'Base Color':
            tex_node.name = "BaseTex"
            tex_node.label = "Base Color Texture"
        elif input_name == 'AO':
            tex_node.name = "AOTex"
            tex_node.label = "AO Texture"
        else:
            tex_node.name = f"{input_name}Tex"
            tex_node.label = f"{input_name} Texture"
            
        settings = material.pbr_settings

        # Ensure Mapping link
        mapping = nodes.get("PBRMapping")
        if mapping:
            links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])

        settings = material.pbr_settings

        if input_name == 'Normal':
            nm = nodes.new('ShaderNodeNormalMap')
            nm.name = "NormalMap"
            nm.label = "Normal Map Node"
            nm.location = (-150, y)
            links.new(nm.outputs['Normal'], principled.inputs['Normal'])
            
            # Use the update function logic to link up the texture and apply Flip G if needed
            properties.update_flip_normal_g(settings, context)
            return True

        if input_name == 'Alpha' or (input_name == 'Base Color' and not settings.use_separate_alpha_map):
            # Alpha Strength/Math node
            math = nodes.get("AlphaMath") or nodes.new('ShaderNodeMath')
            math.name = "AlphaMath"
            math.label = "Alpha Strength"
            math.operation = 'MULTIPLY'
            math.use_clamp = True
            math.location = (-150, y if input_name == 'Alpha' else -200)
            
            # Source for Alpha
            if input_name == 'Alpha':
                src = tex_node.outputs['Color']
                # Apply channel mapping if needed
                chan = settings.alpha_channel
                if chan == 'A':
                    src = tex_node.outputs['Alpha']
                elif chan != 'FULL':
                    sep = nodes.get("AlphaSplit") or nodes.new('ShaderNodeSeparateRGB')
                    sep.name = "AlphaSplit"
                    sep.label = "Alpha Channel Split"
                    sep.location = (-350, y)
                    links.new(tex_node.outputs['Color'], sep.inputs['Image'])
                    src = sep.outputs[chan]
                links.new(src, math.inputs[0])
                material.blend_method = 'BLEND'
            else:
                # Coming from Base Color's alpha channel
                links.new(tex_node.outputs['Alpha'], math.inputs[0])
                material.blend_method = 'HASHED'

            math.inputs[1].default_value = settings.alpha_strength
            
            # Use the update function logic to handle Alpha Clip node
            properties.update_alpha_clip(settings, context)
            
            if input_name == 'Alpha':
                return True
        if input_name == 'Base Color':
            mix = nodes.new('ShaderNodeMix')
            mix.name = "BaseTintMix"
            mix.label = "Base Color Tint"
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs['Factor'].default_value = 1.0
            mix.location = (-150, y)
            links.new(tex_node.outputs['Color'], mix.inputs['A'])
            mix.inputs['B'].default_value = current_tint
            links.new(mix.outputs['Result'], principled.inputs['Base Color'])
            if not settings.use_separate_alpha_map:
                pass # Already handled by AlphaMath logic above
            return True

        if input_name == 'AO':
            # Create the AOMix node (Multiply)
            ao_mix = nodes.new('ShaderNodeMix')
            ao_mix.name = "AOMix"
            ao_mix.label = "AO Multiply"
            ao_mix.data_type = 'RGBA'
            ao_mix.blend_type = 'MULTIPLY'
            ao_mix.location = (0, y)
            ao_mix.inputs['Factor'].default_value = 1.0
            
            # Create the AOAdd node (Math ADD)
            ao_add = nodes.new('ShaderNodeMath')
            ao_add.name = "AOAdd"
            ao_add.label = "AO Strength"
            ao_add.operation = 'ADD'
            ao_add.use_clamp = True
            ao_add.location = (-180, y - 50)
            ao_add.inputs[1].default_value = 1.0 - getattr(settings, "ao_strength")

            # Link AOAdd to AOMix Slot B
            links.new(ao_add.outputs['Value'], ao_mix.inputs['B'])

            # Mix Setup: slot A (Base Color chain) * slot B (AO Result) -> BSDF
            bc_inp = principled.inputs['Base Color']
            if bc_inp.is_linked:
                old_out = bc_inp.links[0].from_socket
                links.new(old_out, ao_mix.inputs['A'])
            else:
                ao_mix.inputs['A'].default_value = bc_inp.default_value
                
            links.new(ao_mix.outputs['Result'], bc_inp)
            
            # Use property update logic for channel and inversion
            properties.update_channel_map(settings, context, 'AO')
            return True

        if input_name == 'Emission':
            # Create EmissionTintMix
            mix = nodes.new('ShaderNodeMix')
            mix.name = "EmissionTintMix"
            mix.label = "Emission Tint"
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs['Factor'].default_value = 1.0
            mix.location = (-150, y)
            
            # Emission source (channeled or full)
            chan = getattr(settings, "emission_channel")
            src = tex_node.outputs['Color']
            if chan == 'A':
                src = tex_node.outputs['Alpha']
            elif chan != 'FULL':
                sep = nodes.new('ShaderNodeSeparateRGB')
                sep.name = "EmissionSplit"
                sep.label = "Emission Channel Split"
                sep.location = (-350, y)
                links.new(tex_node.outputs['Color'], sep.inputs['Image'])
                src = sep.outputs[chan]
            
            links.new(src, mix.inputs['A'])
            mix.inputs['B'].default_value = (1.0, 1.0, 1.0, 1.0) # Emission Tint
            
            links.new(mix.outputs['Result'], principled.inputs['Emission Color'])
            principled.inputs['Emission Strength'].default_value = getattr(settings, "emission_strength")
            return True

        # Roughness / Metallic (always via Math node)
        math = nodes.new('ShaderNodeMath')
        math.operation = 'MULTIPLY'
        math.use_clamp = True  # keep outputs within 0..1
        math.location = (-150, y)
        math.name = f"{input_name}Math"
        math.label = f"{input_name} Strength"

        math.inputs[1].default_value = getattr(settings, f"{input_name.lower()}_strength")
        links.new(math.outputs['Value'], principled.inputs[input_name])
        
        # Use property update logic for channel and inversion
        properties.update_channel_map(settings, context, input_name)
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Auto Load Operator
# ─────────────────────────────────────────────────────────────────────────────

class PBR_OT_AutoLoadTextures(Operator):
    bl_idname = "pbr.auto_load_textures"
    bl_label = "Auto Load PBR Textures"
    bl_options = {'REGISTER', 'UNDO'}

    

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or not obj.active_material:
            return False
        mat = obj.active_material
        principled, tex_node, img = _get_principled_and_base_tex(mat)
        if not img:
            return False
        # Ensure it has a resolvable filepath (not purely packed)
        fp = bpy.path.abspath(img.filepath, library=img.library) if hasattr(img, 'library') else bpy.path.abspath(img.filepath)
        return bool(fp)

    def execute(self, context):
        obj = context.active_object
        mat = obj.active_material
        if not mat:
            self.report({'ERROR'}, "No active material")
            return {'CANCELLED'}

        principled, base_tex, base_img = _get_principled_and_base_tex(mat)
        if not base_img:
            self.report({'ERROR'}, "Assign Base Color first")
            return {'CANCELLED'}

        base_path = bpy.path.abspath(base_img.filepath, library=base_img.library) if hasattr(base_img, 'library') else bpy.path.abspath(base_img.filepath)
        if not base_path or not os.path.exists(base_path):
            self.report({'ERROR'}, "Base Color image path not found on disk")
            return {'CANCELLED'}

        base_path = Path(base_path)
        folder = base_path.parent
        # Read the toggle + custom name from the material settings, not the operator
        use_auto = getattr(mat.pbr_settings, "use_auto_common_name", True)
        custom  = (getattr(mat.pbr_settings, "common_name", "") or "").strip().lower()

        stem_lower = (
            _derive_stem_from_base(base_path.stem.lower())
            if use_auto
            else (custom if custom else base_path.stem.lower())
        )


        # Slot -> acceptable suffix tokens (lowercase)
        # We now use keywords only; matching logic handles separators like _ or -
        suffix_map = {
            'Roughness': ['roughness', 'rough', 'rgh', 'smoothness', 'gloss', 'glossiness', 'r'],
            'Metallic':  ['metallic', 'metal', 'metalness', 'mtl', 'metalsmoothness', 'm', 'met'],
            'Normal':    ['normal', 'norm', 'nrm', 'normalgl', 'normal_dx', 'normal_ogl', 'nmap', 'nm', 'bump', 'n'],
            'Alpha':     ['alpha', 'opacity', 'transparency', 'a'],
            'AO':        ['ao', 'ambientocclusion', 'ambient_occlusion', 'occ'],
            'Emission':  ['emissive', 'emission', 'emit', 'glow', 'e'],
        }

        matches = _find_matches_in_dir(stem_lower, folder, suffix_map)

        assigned_slots = []  # List to keep track of assigned texture slots

        # Assign found textures
        any_assigned = False
        for slot, file_path in matches.items():
            colorspace = 'Non-Color' if slot in ('Roughness', 'Metallic', 'Normal', 'Alpha') else 'sRGB'
            ok = PBR_OT_AssignTexture.assign_texture_to_input(context, mat, slot, str(file_path), colorspace)
            if ok:
                assigned_slots.append(f"{slot}")
                any_assigned = True

        if any_assigned:
            # Reporting which slots were filled
            notify.success(f"Textures assigned: {', '.join(assigned_slots)}")
            bpy.ops.pbr.arrange_nodes()
            return {'FINISHED'}
        else:
            notify.info("No matching textures found in folder.")
            return {'CANCELLED'}


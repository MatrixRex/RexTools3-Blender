# pyrefly: ignore [missing-import]
import bpy
# pyrefly: ignore [missing-import]
from bpy.props import (
    IntProperty, FloatProperty,
    BoolProperty, StringProperty,
    PointerProperty, EnumProperty,
    FloatVectorProperty, CollectionProperty
)
# pyrefly: ignore [missing-import]
from bpy.types import PropertyGroup
from .core import node_utils


def update_auto_frame_range(self, context):
    from .operators.auto_frame_range import update_frame_range
    update_frame_range(self)


def update_use_sep_alpha(self, context):
    mat = self.id_data
    if not mat.use_nodes:
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not principled:
        return

    alpha_inp = principled.inputs.get('Alpha')
    if not alpha_inp:
        return

    # Clear current Alpha links
    for link in list(alpha_inp.links):
        links.remove(link)

    if not self.use_separate_alpha_map:
        # Find BaseTex node (might be behind BaseTintMix or AOMix)
        base_tex = nodes.get("BaseTex")
        if not base_tex:
            # Fallback scan
            for n in nodes:
                if n.type == 'TEX_IMAGE' and "base" in n.name.lower():
                    base_tex = n
                    break
        
        if base_tex:
            # Use AlphaMath for strength if it exists
            math = nodes.get("AlphaMath")
            clip = nodes.get("AlphaClip")
            
            final_src = base_tex.outputs['Alpha']
            
            if math:
                if math.inputs[0].is_linked:
                    links.remove(math.inputs[0].links[0])
                links.new(base_tex.outputs['Alpha'], math.inputs[0])
                final_src = math.outputs['Value']
            
            if self.use_alpha_clip:
                if not clip:
                    clip = nodes.new('ShaderNodeMath')
                    clip.name = "AlphaClip"
                    clip.label = "Alpha Clip"
                    clip.operation = 'GREATER_THAN'
                    clip.inputs[1].default_value = self.alpha_threshold
                links.new(final_src, clip.inputs[0])
                links.new(clip.outputs['Value'], alpha_inp)
            else:
                if clip:
                    try: nodes.remove(clip)
                    except: pass
                links.new(final_src, alpha_inp)
            
            mat.blend_method = 'HASHED'
        
        # Cleanup Separate Alpha nodes if they exist
        for name in ["AlphaTex", "AlphaSplit"]:
            node = nodes.get(name)
            if node:
                try: nodes.remove(node)
                except: pass


# ─────────────────────────────────────────────────────────────────────────────
# Channel mapping updates
# ─────────────────────────────────────────────────────────────────────────────

def update_channel_map(self, context, input_name):
    mat = self.id_data
    if not mat.use_nodes:
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not principled:
        return

    # AO is not a direct socket on BSDF, so we skip the socket check for it
    if input_name not in ('AO', 'Emission'):
        inp = principled.inputs.get(input_name)
        if not inp or not inp.is_linked:
            return
    
    # Map input name to actual BSDF socket name
    socket_map = {
        'Emission': 'Emission Color',
    }
    actual_socket_name = socket_map.get(input_name, input_name)
    
    # Target socket for texture linking
    # For Roughness, Metallic, Alpha, AO, we link to a helper node first
    math_node = nodes.get(f"{input_name}Math")
    ao_add = nodes.get("AOAdd")
    em_mix = nodes.get("EmissionTintMix")
    
    target_sock = None
    if math_node:
        target_sock = math_node.inputs[0]
    elif input_name == 'AO' and ao_add:
        target_sock = ao_add.inputs[0]
    elif input_name == 'Emission' and em_mix:
        target_sock = em_mix.inputs.get('A') or em_mix.inputs[0]
    else:
        # Fallback to direct BSDF socket
        target_sock = principled.inputs.get(actual_socket_name)

    if not target_sock:
        return

    # Find relevant image texture node
    target_name = "BaseTex" if input_name == 'Base Color' else ("AOTex" if input_name == 'AO' else f"{input_name}Tex")
    tex_node = nodes.get(target_name)
    if not tex_node:
        return

    chan = getattr(self, f"{input_name.lower()}_channel")

    # 1) Clear existing links into target socket
    for link in list(target_sock.links):
        links.remove(link)

    # 2) Handle source and optional inversion
    invert = False
    if input_name in ('Roughness', 'Metallic', 'AO'):
        invert = getattr(self, f"invert_{input_name.lower()}", False)

    src_sock = None
    if chan in ('FULL', 'A'):
        # Cleanup split node
        sep = nodes.get(f"{input_name}Split")
        if sep: nodes.remove(sep)
        src_sock = tex_node.outputs['Color'] if chan == 'FULL' else tex_node.outputs['Alpha']
    else:
        sep = nodes.get(f"{input_name}Split") or node_utils.create_separate_node(nodes, f"{input_name}Split")
        sep.name = f"{input_name}Split"
        sep.location = (tex_node.location.x + 150, tex_node.location.y)
        sep_in = node_utils.get_separate_input_socket(sep)
        if sep_in and sep_in.is_linked:
            links.remove(sep_in.links[0])
        if sep_in:
            links.new(tex_node.outputs['Color'], sep_in)
        src_sock = node_utils.get_separate_output_socket(sep, chan)

    # Invert logic
    if invert:
        inv_node = nodes.get(f"{input_name}Invert") or node_utils.create_invert_node(nodes, f"{input_name}Invert")
        inv_node.name = f"{input_name}Invert"
        inv_node.label = f"Invert {input_name}"
        inv_node.location = (tex_node.location.x + 300, tex_node.location.y - 100)
        fac_inp = inv_node.inputs.get('Fac') or inv_node.inputs.get('Factor') or inv_node.inputs[0]
        if fac_inp:
            fac_inp.default_value = 1.0
        
        inv_in = node_utils.get_invert_input_socket(inv_node)
        inv_out = node_utils.get_invert_output_socket(inv_node)

        # Link source to Invert
        if inv_in and inv_in.is_linked:
            links.remove(inv_in.links[0])
        if inv_in and src_sock:
            links.new(src_sock, inv_in)
        
        # New source is the Invert output
        src_sock = inv_out
    else:
        # Cleanup Invert node if it exists
        inv_node = nodes.get(f"{input_name}Invert")
        if inv_node:
            try: nodes.remove(inv_node)
            except: pass

    links.new(src_sock, target_sock)

    if input_name == 'Alpha':
        mat.blend_method = 'BLEND'
    
    bpy.ops.pbr.arrange_nodes()
    return
    
    bpy.ops.pbr.arrange_nodes()


def update_roughness_channel(self, context):
    update_channel_map(self, context, 'Roughness')


def update_metallic_channel(self, context):
    update_channel_map(self, context, 'Metallic')


def update_alpha_channel(self, context):
    update_channel_map(self, context, 'Alpha')


def update_ao_channel(self, context):
    update_channel_map(self, context, 'AO')


def update_emission_channel(self, context):
    update_channel_map(self, context, 'Emission')


def update_alpha_clip(self, context):
    mat = self.id_data
    if not mat or not mat.use_nodes:
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not principled:
        return
        
    alpha_inp = principled.inputs.get('Alpha')
    if not alpha_inp:
        return

    # Find where the alpha chain currently ends (Strength math or Texture)
    math = nodes.get("AlphaMath")
    clip = nodes.get("AlphaClip")
    
    # 1. Determine Source
    src_sock = None
    if math:
        src_sock = math.outputs[0]
    else:
        # Try finding AlphaTex or BaseTex
        tex = nodes.get("AlphaTex") or nodes.get("BaseTex")
        if tex:
            if tex.name == "AlphaTex":
                # Need to handle Alpha channel mapping logic here ideally, 
                # but let's look at current links
                src_sock = tex.outputs['Color'] # Default
                # Re-check channel mapping? Simple version:
                if self.alpha_channel == 'A':
                    src_sock = tex.outputs['Alpha']
            else:
                src_sock = tex.outputs['Alpha']

    if not src_sock:
        # Hard fallback scan
        for n in nodes:
            if n.type == 'TEX_IMAGE' and ("base" in n.name.lower() or "alpha" in n.name.lower()):
                src_sock = n.outputs['Alpha'] if "base" in n.name.lower() else n.outputs['Color']
                break

    if not src_sock:
        return

    if self.use_alpha_clip:
        if not clip:
            clip = nodes.new('ShaderNodeMath')
            clip.name = "AlphaClip"
            clip.label = "Alpha Clip"
            clip.operation = 'GREATER_THAN'
        clip.inputs[1].default_value = self.alpha_threshold
        clip.location = (principled.location.x - 200, principled.location.y - 400)
        
        links.new(src_sock, clip.inputs[0])
        links.new(clip.outputs[0], alpha_inp)
    else:
        if clip:
            nodes.remove(clip)
        links.new(src_sock, alpha_inp)

    # Refresh debug preview if active to ensure it points to the correct node (Strength vs Clip)
    if self.debug_preview_slot == 'Alpha' and self.debug_preview_mode == 'MIXED':
        emission = nodes.get("DebugEmissionPreview")
        if emission:
            target_out = None
            if self.use_alpha_clip:
                clip = nodes.get("AlphaClip")
                if clip:
                    target_out = clip.outputs[0]
            else:
                math = nodes.get("AlphaMath")
                if math:
                    target_out = math.outputs[0]
                else:
                    target_out = src_sock
            
            if target_out:
                links.new(target_out, emission.inputs['Color'])

    bpy.ops.pbr.arrange_nodes()


def update_flip_normal_g(self, context):
    mat = self.id_data
    if not mat or not mat.use_nodes:
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    nm_node = nodes.get("NormalMap")
    tex_node = nodes.get("NormalTex")
    
    if not nm_node or not tex_node:
        return
        
    # Remove existing link to NormalMap Color input
    for link in list(nm_node.inputs['Color'].links):
        links.remove(link)
        
    if self.flip_normal_g:
        # Create helper nodes if they don't exist
        sep = nodes.get("NormalSplit") or node_utils.create_separate_node(nodes, "NormalSplit")
        sep.name = "NormalSplit"
        sep.label = "Normal Split"
        
        inv = nodes.get("NormalInvertG") or nodes.new('ShaderNodeMath')
        inv.name = "NormalInvertG"
        inv.label = "Invert G"
        inv.operation = 'SUBTRACT'
        inv.inputs[0].default_value = 1.0
        
        com = nodes.get("NormalCombine") or node_utils.create_combine_node(nodes, "NormalCombine")
        com.name = "NormalCombine"
        com.label = "Normal Combine"
        
        # Positions
        sep.location = (tex_node.location.x + 200, tex_node.location.y)
        inv.location = (sep.location.x + 200, sep.location.y - 100)
        com.location = (inv.location.x + 200, inv.location.y + 100)
        
        # Links
        sep_in = node_utils.get_separate_input_socket(sep)
        sep_r = node_utils.get_separate_output_socket(sep, 'R')
        sep_g = node_utils.get_separate_output_socket(sep, 'G')
        sep_b = node_utils.get_separate_output_socket(sep, 'B')

        com_r = node_utils.get_combine_input_socket(com, 'R')
        com_g = node_utils.get_combine_input_socket(com, 'G')
        com_b = node_utils.get_combine_input_socket(com, 'B')
        com_out = node_utils.get_combine_output_socket(com)

        if sep_in: links.new(tex_node.outputs['Color'], sep_in)
        if sep_r and com_r: links.new(sep_r, com_r)
        if sep_g: links.new(sep_g, inv.inputs[1])
        if com_g: links.new(inv.outputs['Value'], com_g)
        if sep_b and com_b: links.new(sep_b, com_b)
        if com_out: links.new(com_out, nm_node.inputs['Color'])
    else:
        # Clear helper nodes
        for name in ["NormalSplit", "NormalInvertG", "NormalCombine"]:
            node = nodes.get(name)
            if node:
                try: nodes.remove(node)
                except: pass
        
        # Link directly
        links.new(tex_node.outputs['Color'], nm_node.inputs['Color'])

    # Refresh debug preview if active to ensure it points to the correct node (Tex vs Combine)
    if self.debug_preview_slot == 'Normal' and self.debug_preview_mode == 'DIRECT':
        emission = nodes.get("DebugEmissionPreview")
        if emission:
            target_out = None
            if self.flip_normal_g:
                com = nodes.get("NormalCombine")
                if com:
                    target_out = node_utils.get_combine_output_socket(com)
            else:
                target_out = tex_node.outputs.get('Color') or tex_node.outputs[0]
            
            if target_out:
                links.new(target_out, emission.inputs['Color'])

    bpy.ops.pbr.arrange_nodes()


# ─────────────────────────────────────────────────────────────────────────────
# Strength updates (Roughness/Metallic)
# ─────────────────────────────────────────────────────────────────────────────

def update_strength(self, context, input_name):
    mat = self.id_data
    if not mat or not mat.use_nodes:
        return
    nodes = mat.node_tree.nodes

    if input_name == 'AO':
        node = nodes.get("AOAdd")
        if node:
            # Math node ADD: input[1] is the value to add
            node.inputs[1].default_value = 1.0 - float(getattr(self, "ao_strength", 1.0))
        return

    if input_name == 'Emission':
        # For Emission, strength often goes to the BSDF socket directly
        principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if principled:
            principled.inputs['Emission Strength'].default_value = float(getattr(self, "emission_strength", 1.0))
        return

    if input_name == 'Height':
        disp_node = nodes.get("HeightDisplace")
        if disp_node:
            disp_node.inputs['Scale'].default_value = float(getattr(self, "height_strength", 0.1))
        return

    # Check for both slot-named Math node and generic principled input fallback
    math = nodes.get(f"{input_name}Math")
    if math:
        value = getattr(self, f"{input_name.lower()}_strength", 1.0)
        try:
            math.inputs[1].default_value = float(value)
        except Exception:
            pass
    elif input_name == 'Alpha':
        # Fallback for Alpha if no node exists yet (direct BSDF input)
        principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if principled:
            principled.inputs['Alpha'].default_value = float(getattr(self, "alpha_strength", 1.0))


def update_tiling(self, context):
    mat = self.id_data
    if not mat or not mat.use_nodes:
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # 1. Ensure Mapping and Texture Coordinate nodes exist
    mapping = nodes.get("PBRMapping") or nodes.new('ShaderNodeMapping')
    mapping.name = "PBRMapping"
    mapping.label = "PBR Mapping"

    tex_coord = nodes.get("PBRTexCoord") or nodes.new('ShaderNodeTexCoord')
    tex_coord.name = "PBRTexCoord"
    tex_coord.label = "PBR Texture Coordinate"

    # 2. Update Scaling
    mapping.inputs['Scale'].default_value[0] = self.pbr_tiling[0]
    mapping.inputs['Scale'].default_value[1] = self.pbr_tiling[1]

    # 3. Link Coordinate to Mapping
    if not mapping.inputs['Vector'].is_linked:
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

    # 4. Ensure all image textures are linked to the mapping node
    for n in nodes:
        if n.type == 'TEX_IMAGE':
            # Check if this texture is part of the PBR chain (Base, Normal, etc.)
            # A simple way is to check if it's named with one of our suffixes or if it targets our BSDF
            if not n.inputs['Vector'].is_linked:
                links.new(mapping.outputs['Vector'], n.inputs['Vector'])

    bpy.ops.pbr.arrange_nodes()


class BoneRenameProperties(PropertyGroup):
    find_text: StringProperty(name="Find", default="")
    replace_text: StringProperty(name="Replace", default="")
    prefix_text: StringProperty(name="Prefix", default="")
    suffix_text: StringProperty(name="Suffix", default="")
    apply_prefix_suffix_to_matches_only: BoolProperty(default=False)
    show_in_panel: BoolProperty(default=True)


class HighLowRenamerProperties(PropertyGroup):
    obj_name: StringProperty(name="Object Name", default="")
    high_prefix: StringProperty(name="High Prefix", default="_high")
    low_prefix: StringProperty(name="Low Prefix", default="_low")
    show_in_panel: BoolProperty(default=True)


class Rextools3MarmosetMeshRef(PropertyGroup):
    obj: PointerProperty(name="Object", type=bpy.types.Object)
    name: StringProperty(name="Object Name", default="")


class Rextools3MarmosetBakeGroup(PropertyGroup):
    group_name: StringProperty(name="Group Name", default="")
    is_locked: BoolProperty(name="Locked", default=False)
    is_expanded: BoolProperty(name="Expanded", default=False)
    low_meshes: CollectionProperty(type=Rextools3MarmosetMeshRef)
    high_meshes: CollectionProperty(type=Rextools3MarmosetMeshRef)


class Rextools3MarmosetBridgeProperties(PropertyGroup):
    export_path: StringProperty(
        name="Bake Output Path",
        description="Folder to save FBX files and baked textures",
        default="//",
        subtype='NONE'
    )
    asset_name: StringProperty(
        name="Asset Name",
        description="Base name for meshes and textures",
        default=""
    )
    resolution: EnumProperty(
        name="Resolution",
        items=[
            ("512", "512 x 512", ""),
            ("1024", "1024 x 1024", ""),
            ("2048", "2048 x 2048", ""),
            ("4096", "4096 x 4096", "")
        ],
        default="2048"
    )
    file_format: EnumProperty(
        name="Format",
        items=[
            ("PNG", "PNG", ""),
            ("TGA", "TGA", ""),
            ("PSD", "PSD", "")
        ],
        default="PNG"
    )
    auto_rename: BoolProperty(
        name="Auto Rename",
        description="Auto rename meshes and materials when preparing/sending",
        default=True
    )
    send_textures: BoolProperty(
        name="Send High Textures",
        description="Send high poly material textures to Marmoset Toolbag",
        default=True
    )
    bake_albedo: BoolProperty(
        name="Bake Albedo",
        description="Enable baking of albedo/base color maps",
        default=True
    )
    bake_normals: BoolProperty(
        name="Bake Normals",
        description="Enable baking of normal maps",
        default=True
    )
    bake_roughness: BoolProperty(
        name="Bake Roughness",
        description="Enable baking of roughness maps",
        default=True
    )
    bake_metallic: BoolProperty(
        name="Bake Metallic",
        description="Enable baking of metallic maps",
        default=True
    )
    bake_ao: BoolProperty(
        name="Bake AO",
        description="Enable baking of ambient occlusion maps",
        default=True
    )
    show_in_panel: BoolProperty(default=True)
    bake_groups: CollectionProperty(type=Rextools3MarmosetBakeGroup)
    global_lock: BoolProperty(name="Lock All Groups", default=False)




class MaterialBatchItem(PropertyGroup):
    material_name: StringProperty(name="Material Name")
    status: StringProperty(name="Status", default="Pending")
    is_assigned: BoolProperty(name="Is Assigned", default=False)


class BatchMaterialProperties(PropertyGroup):
    target_folder: StringProperty(
        name="Texture Folder",
        description="Folder to search for textures",
        default="//",
        subtype='NONE'
    )
    recursive: BoolProperty(
        name="Recursive Search",
        description="Search for textures in subfolders",
        default=True
    )
    show_custom_suffixes: BoolProperty(
        name="Custom Suffixes",
        description="Show suffix settings for each map type",
        default=False
    )
    suffix_base_color: StringProperty(
        name="Base Color",
        description="Comma-separated suffixes/keywords for Base Color maps",
        default="albedo, basecolor, base_color, diffuse, color, col, bc, d, c"
    )
    suffix_roughness: StringProperty(
        name="Roughness",
        description="Comma-separated suffixes/keywords for Roughness maps",
        default="roughness, rough, rgh, smoothness, gloss, glossiness, r"
    )
    suffix_metallic: StringProperty(
        name="Metallic",
        description="Comma-separated suffixes/keywords for Metallic maps",
        default="metallic, metal, metalness, mtl, m, met"
    )
    suffix_normal: StringProperty(
        name="Normal",
        description="Comma-separated suffixes/keywords for Normal maps",
        default="normal, norm, nrm, nmap, nm, n"
    )
    suffix_alpha: StringProperty(
        name="Alpha",
        description="Comma-separated suffixes/keywords for Alpha maps",
        default="alpha, opacity, transparency, a"
    )
    suffix_ao: StringProperty(
        name="AO",
        description="Comma-separated suffixes/keywords for Ambient Occlusion maps",
        default="ao, ambientocclusion, occ"
    )
    suffix_emission: StringProperty(
        name="Emission",
        description="Comma-separated suffixes/keywords for Emission maps",
        default="emissive, emission, emit, glow, e"
    )
    suffix_height: StringProperty(
        name="Height",
        description="Comma-separated suffixes/keywords for Height maps",
        default="height, disp, displacement, h"
    )
    items: CollectionProperty(type=MaterialBatchItem)


class Rextools3AIWebBridgeProperties(PropertyGroup):
    target_service: EnumProperty(
        name="Target Service",
        description="Target AI 3D generator web platform",
        items=[
            ("meshy", "Meshy", "Send model to Meshy AI (meshy.ai/workspace)"),
            ("tripo", "Tripo 3D", "Send model to Tripo Studio (studio.tripo3d.ai)")
        ],
        default="meshy"
    )
    file_format: EnumProperty(
        name="Format",
        description="3D file format for bridge transfer",
        items=[
            ("GLB", "GLB (.glb)", "GLTF Binary (Recommended - preserves embedded textures & UVs)"),
            ("FBX", "FBX (.fbx)", "Autodesk FBX format"),
            ("OBJ", "OBJ (.obj)", "Wavefront OBJ format")
        ],
        default="GLB"
    )
    auto_center: BoolProperty(
        name="Auto Center Origin",
        description="Temporarily center model to world origin (0, 0, 0) for AI generator requirements",
        default=True
    )
    apply_transforms: BoolProperty(
        name="Apply Transforms",
        description="Apply Location, Rotation, and Scale to exported model",
        default=True
    )
    only_selected: BoolProperty(
        name="Selected Only",
        description="Export only selected objects",
        default=True
    )
    auto_open_browser: BoolProperty(
        name="Auto Open Browser",
        description="Automatically open or focus the AI generator website",
        default=True
    )
    server_port: IntProperty(
        name="Server Port",
        description="Local HTTP Bridge Server port",
        default=28394,
        min=1024,
        max=65535
    )
    last_exported_file: StringProperty(
        name="Last Exported File",
        default=""
    )
    last_model_name: StringProperty(
        name="Last Model Name",
        default=""
    )


class PBRMaterialSettings(PropertyGroup):
    show_texture_loader: BoolProperty(
        name="Show Texture Loader",
        default=True,
    )
    show_texture_utils: BoolProperty(
        name="Show Texture Utilities",
        default=True,
    )
    show_viewport_color: BoolProperty(
        name="Show Viewport Color",
        default=True,
    )
    use_auto_common_name: BoolProperty(
        name="Use Auto-Detected Name",
        default=True,
    )
    use_packed_mode: BoolProperty(
        name="Packing Mode",
        description="When enabled, assigning textures will default to packed setup",
        default=False,
    )
    common_name: StringProperty(
        name="Common Name",
        default="",
    )
    pbr_tiling: FloatVectorProperty(
        name="Tiling",
        size=2,
        default=(1.0, 1.0),
        update=update_tiling
    )
    use_separate_alpha_map: BoolProperty(
        name="Use Separate Alpha Map",
        default=False,
        update=update_use_sep_alpha
    )
    roughness_strength: FloatProperty(
        name="Roughness Strength",
        default=1.0, min=0.0, max=1.0,
        update=lambda self, ctx: update_strength(self, ctx, 'Roughness')
    )
    metallic_strength: FloatProperty(
        name="Metallic Strength",
        default=1.0, min=0.0, max=1.0,
        update=lambda self, ctx: update_strength(self, ctx, 'Metallic')
    )
    alpha_strength: FloatProperty(
        name="Alpha Strength",
        default=1.0, min=0.0, max=1.0,
        update=lambda self, ctx: update_strength(self, ctx, 'Alpha')
    )
    ao_strength: FloatProperty(
        name="AO Strength",
        default=1.0, min=0.0, max=1.0,
        update=lambda self, ctx: update_strength(self, ctx, 'AO')
    )
    height_strength: FloatProperty(
        name="Height Strength",
        description="Scale multiplier for the Displacement node",
        default=0.1, min=0.0, max=2.0,
        update=lambda self, ctx: update_strength(self, ctx, 'Height')
    )
    emission_strength: FloatProperty(
        name="Emission Strength",
        default=1.0, min=0.0, max=1000.0,
        update=lambda self, ctx: update_strength(self, ctx, 'Emission')
    )
    flip_normal_g: BoolProperty(
        name="Flip Normal G",
        description="Flipping the Green channel (Y) of the normal map for DirectX/OpenGL compatibility",
        default=False,
        update=update_flip_normal_g
    )
    use_alpha_clip: BoolProperty(
        name="Use Alpha Clip",
        default=False,
        update=update_alpha_clip
    )
    alpha_threshold: FloatProperty(
        name="Alpha Threshold",
        default=0.5, min=0.0, max=1.0,
        update=update_alpha_clip
    )
    invert_roughness: BoolProperty(
        name="Invert Roughness",
        default=False,
        update=lambda self, ctx: update_channel_map(self, ctx, 'Roughness')
    )
    invert_metallic: BoolProperty(
        name="Invert Metallic",
        default=False,
        update=lambda self, ctx: update_channel_map(self, ctx, 'Metallic')
    )
    invert_ao: BoolProperty(
        name="Invert AO",
        default=False,
        update=lambda self, ctx: update_channel_map(self, ctx, 'AO')
    )

    channel_items = [
        ('FULL', "Full", "Use full RGBA"),
        ('R',    "R",    "Use Red channel"),
        ('G',    "G",    "Use Green channel"),
        ('B',    "B",    "Use Blue channel"),
        ('A',    "A",    "Use Alpha channel"),
    ]
    roughness_channel: EnumProperty(
        name="Roughness Channel",
        items=channel_items,
        default='FULL',
        update=update_roughness_channel
    )
    metallic_channel: EnumProperty(
        name="Metallic Channel",
        items=channel_items,
        default='FULL',
        update=update_metallic_channel
    )
    alpha_channel: EnumProperty(
        name="Alpha Channel",
        items=channel_items,
        default='FULL',
        update=update_alpha_channel
    )
    ao_channel: EnumProperty(
        name="AO Channel",
        items=channel_items,
        default='FULL',
        update=update_ao_channel
    )
    emission_channel: EnumProperty(
        name="Emission Channel",
        items=channel_items,
        default='FULL',
        update=update_emission_channel
    )
    debug_preview_mode: EnumProperty(
        name="Debug Preview Mode",
        items=[
            ('OFF', "Off", ""),
            ('DIRECT', "Direct", ""),
            ('MIXED', "Mixed", ""),
        ],
        default='OFF'
    )
    debug_preview_slot: StringProperty(
        name="Debug Preview Slot",
        default=""
    )


def update_constraint_type(self, context):
    if not (context.active_object and context.active_object.type == 'ARMATURE' and context.mode == 'POSE'):
        return
    
    pb = context.active_pose_bone
    if not pb:
        return
        
    con_name = "REX_TEMPLATE"
    con = pb.constraints.get(con_name)
    
    if con:
        if con.type != self.constraint_type:
            # Replace existing template with new type
            pb.constraints.remove(con)
            con = pb.constraints.new(type=self.constraint_type)
            con.name = con_name
            con.mute = True


class ChainConstraintsAdderProperties(PropertyGroup):
    constraint_type: EnumProperty(
        name="Constraint Type",
        items=[
            ('COPY_LOCATION', "Copy Location", ""),
            ('COPY_ROTATION', "Copy Rotation", ""),
            ('COPY_SCALE', "Copy Scale", ""),
            ('COPY_TRANSFORMS', "Copy Transforms", ""),
            ('LIMIT_DISTANCE', "Limit Distance", ""),
            ('LIMIT_LOCATION', "Limit Location", ""),
            ('LIMIT_ROTATION', "Limit Rotation", ""),
            ('LIMIT_SCALE', "Limit Scale", ""),
            ('MAINTAIN_VOLUME', "Maintain Volume", ""),
            ('TRANSFORM_CACHE', "Transform Cache", ""),
            ('CLAMP_TO', "Clamp To", ""),
            ('DAMPED_TRACK', "Damped Track", ""),
            ('IK', "IK", ""),
            ('LOCKED_TRACK', "Locked Track", ""),
            ('SPLINE_IK', "Spline IK", ""),
            ('STRETCH_TO', "Stretch To", ""),
            ('TRACK_TO', "Track To", ""),
            ('ACTION', "Action", ""),
            ('ARMATURE', "Armature", ""),
            ('CHILD_OF', "Child Of", ""),
            ('FLOOR', "Floor", ""),
            ('FOLLOW_PATH', "Follow Path", ""),
            ('FOLLOW_TRACK', "Follow Track", ""),
            ('KINEMATIC', "Kinematic", ""),
            ('OBJECT_SOLVER', "Object Solver", ""),
            ('PIVOT', "Pivot", ""),
            ('SHRINKWRAP', "Shrinkwrap", ""),
        ],
        default='COPY_ROTATION',
        update=update_constraint_type
    )
    mode: EnumProperty(
        name="Mode",
        items=[
            ('INCREASE', "Increase", ""),
            ('DECREASE', "Decrease", ""),
            ('FROM_TO', "From and To", ""),
        ],
        default='DECREASE'
    )
    influence_value: FloatProperty(
        name="Value",
        default=0.1,
        min=0.0,
        max=1.0
    )
    influence_from: FloatProperty(
        name="From",
        default=0.0,
        min=0.0,
        max=1.0
    )
    influence_to: FloatProperty(
        name="To",
        default=1.0,
        min=0.0,
        max=1.0
    )
    direction: EnumProperty(
        name="Direction",
        items=[
            ('FROM_ROOT', "From Root", ""),
            ('FROM_TIP', "From Tip", ""),
        ],
        default='FROM_TIP'
    )


class Rextools3KeyframeOffsetProperties(PropertyGroup):
    direction: EnumProperty(
        name="Direction",
        items=[
            ('FROM_ROOT', "From Root", "Start offset from root towards tip"),
            ('FROM_TIP', "From Tip", "Start offset from tip towards root"),
        ],
        default='FROM_ROOT'
    )
    offset_value: FloatProperty(
        name="Offset Value",
        description="Number of frames to offset each bone's keyframes",
        default=1.0
    )


class CleanupProperties(PropertyGroup):
    normals: BoolProperty(name="Normals", default=True)
    quad: BoolProperty(name="Quad", default=True)
    mats: BoolProperty(name="Mats", default=True)
    seams: BoolProperty(name="Clear Seams", default=True)


class ModifierIgnoreItem(PropertyGroup):
    modifier_type: EnumProperty(
        name="Type",
        items=[
            ('ARMATURE', "Armature", ""),
            ('BOOLEAN', "Boolean", ""),
            ('BEVEL', "Bevel", ""),
            ('MIRROR', "Mirror", ""),
            ('SUBSURF', "Subdivision Surface", ""),
            ('SOLIDIFY', "Solidify", ""),
            ('ARRAY', "Array", ""),
            ('CURVE', "Curve", ""),
            ('DISPLACE', "Displace", ""),
            ('DECIMATE', "Decimate", ""),
            ('TRIANGULATE', "Triangulate", ""),
            ('WELD', "Weld", ""),
            ('SHRINKWRAP', "Shrinkwrap", ""),
        ],
        default='ARMATURE'
    )


class RexCommonSettings(PropertyGroup):
    clean_modifiers_selection: EnumProperty(
        name="Scope",
        description="Objects to check for cleaning modifiers",
        items=[
            ('SELECTED', "Selected", "Only selected mesh objects"),
            ('VISIBLE', "Visible", "All visible mesh objects in the scene"),
            ('ALL', "All", "All mesh objects in the scene, including hidden ones"),
        ],
        default='SELECTED'
    )
    clean_modifiers_validation: EnumProperty(
        name="Validation",
        description="Criteria for determining which modifiers to remove",
        items=[
            ('UNAFFECTED', "Unaffected", "Remove modifiers that are broken (missing targets) or useless (zero influence)"),
            ('HIDDEN', "Hidden Only", "Only remove modifiers that are hidden in the viewport"),
            ('ALL', "All", "Remove all modifiers, including valid and visible ones"),
        ],
        default='UNAFFECTED'
    )
    smart_join_apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply all modifiers before joining in Smart Join", 
        default=False
    )
    apply_modifiers_ignore_list: CollectionProperty(type=ModifierIgnoreItem)


def get_export_presets(format_str):
    import os
    import bpy
    
    presets = [('NONE', "No Preset", "")]
    
    # Determine preset folder based on format
    fmt = format_str.lower()
    if fmt == 'fbx':
        folder = "export_scene.fbx"
    elif fmt == 'gltf':
        folder = "export_scene.gltf"
    elif fmt == 'obj':
        folder = "export_scene.obj"
    else:
        return presets

    paths = bpy.utils.preset_paths(os.path.join("operator", folder))
    for p in paths:
        for f in os.listdir(p):
            if f.endswith(".py"):
                name = f[:-3]
                presets.append((name, name.replace("_", " ").title(), ""))
    
    return presets

def get_effective_export_format(coll):
    """Recursively find the effective export format for a collection."""
    import bpy
    overrides = getattr(coll, "rex_export_overrides", None)
    if overrides and overrides.override_format:
        return overrides.export_format
    
    # Find parent
    for c in bpy.data.collections:
        if coll.name in c.children.keys():
            if c.name == "Scene Collection" or c == bpy.context.scene.collection:
                continue
            return get_effective_export_format(c)
            
    # Fallback to scene
    return bpy.context.scene.rex_export_settings.export_format


class RexCollectionExportOverrides(PropertyGroup):
    # Override Flags
    override_path: BoolProperty(name="Override Path", default=False)
    override_texture_copy_path: BoolProperty(name="Override Texture Copy Path", default=False)
    override_format: BoolProperty(name="Override Format", default=False)
    override_preset: BoolProperty(name="Override Preset", default=False)
    override_remove_armature_root: BoolProperty(name="Override Remove Armature Root", default=False)
    override_reset_transform: BoolProperty(name="Override Reset Transform", default=False)
    override_pre_rotation: BoolProperty(name="Override Pre Rotation", default=False)
    override_pre_scale: BoolProperty(name="Override Pre Scale", default=False)
    override_rename_armature: BoolProperty(name="Override Rename Armature", default=False)
    override_single_mesh: BoolProperty(name="Override Single Mesh", default=False)


    export_path: StringProperty(
        name="Export Path",
        description="Custom directory for this collection's export",
        default="//",
        subtype='NONE'
    )
    texture_copy_path: StringProperty(
        name="Texture Copy Path",
        description="Custom directory for copying textures",
        default="//",
        subtype='NONE'
    )
    export_format: EnumProperty(
        name="Format",
        items=[
            ('FBX', "FBX", "Export as FBX"),
            ('GLTF', "GLTF", "Export as GLTF"),
            ('OBJ', "OBJ", "Export as OBJ"),
        ],
        default='FBX'
    )
    
    def get_presets(self, context):
        if not context:
            return get_export_presets(self.export_format)
            
        coll = getattr(context, "collection", None)
        if not coll:
            return get_export_presets(self.export_format)
            
        fmt = get_effective_export_format(coll)
        return get_export_presets(fmt)

    export_preset: EnumProperty(
        name="Preset",
        items=get_presets,
    )
    fbx_remove_armature_root: BoolProperty(
        name="Remove Armature Root",
        description="Removes the default Armature empty root when exporting FBX",
        default=False
    )
    reset_transform: BoolProperty(
        name="Reset Transform",
        description="Save object transforms, reset to origin (0,0,0 position/rotation), export, and restore",
        default=True
    )
    pre_rotation: FloatVectorProperty(
        name="Pre Rotation",
        description="Rotate objects by this amount before exporting, then restore after",
        size=3,
        default=(0.0, 0.0, 0.0),
        subtype='EULER'
    )
    pre_scale: FloatProperty(
        name="Pre Scale",
        description="Scale objects by this factor before exporting, then restore after",
        default=1.0,
        min=0.001,
    )
    ui_expand_preview: BoolProperty(
        name="Expand Preview",
        default=True
    )
    rename_armature: BoolProperty(
        name="Rename Armature to 'Armature'",
        description="Rename armature object and data to 'Armature' before export (useful for Unity root name)",
        default=False
    )
    single_mesh: BoolProperty(
        name="Single Mesh",
        description="Merge all mesh objects under a single collection into one mesh object with non-armature modifiers applied",
        default=False
    )


class RexExportSettings(PropertyGroup):
    export_path: StringProperty(
        name="Export Path",
        description="Global directory for exports",
        default="//",
        subtype='NONE'
    )
    texture_copy_path: StringProperty(
        name="Texture Copy Path",
        description="Folder where textures will be copied",
        default="//",
        subtype='NONE'
    )
    export_mode: EnumProperty(
        name="Export Mode",
        items=[
            ('OBJECTS', "Objects", "Each object as 1 mesh"),
            ('PARENTS', "Parents", "Each top most parent as 1 mesh"),
            ('COLLECTIONS', "Collections", "Each collection as 1 mesh"),
        ],
        default='OBJECTS'
    )
    export_limit: EnumProperty(
        name="Limit",
        items=[
            ('VISIBLE', "Visible", "All scene visible objects"),
            ('SELECTED', "Selected", "Only selected objects"),
            ('RENDER', "Render Visible", "Only objects visible for render"),
        ],
        default='SELECTED'
    )
    export_format: EnumProperty(
        name="Format",
        items=[
            ('FBX', "FBX", "Export as FBX"),
            ('GLTF', "GLTF", "Export as GLTF"),
            ('OBJ', "OBJ", "Export as OBJ"),
        ],
        default='FBX'
    )
    shared_armature: BoolProperty(
        name="Shared Armature",
        description="Every export target (Object/Collection) will include the single active armature. Only works if exactly one armature is selected/visible",
        default=False
    )
    
    def get_presets(self, context):
        return get_export_presets(self.export_format)

    export_preset: EnumProperty(
        name="Preset",
        items=get_presets,
    )
    last_export_path: StringProperty(
        name="Last Export Path",
        default="",
        subtype='DIR_PATH'
    )
    show_preview: BoolProperty(
        name="Show Export Preview",
        description="Show a list of unique models that will be exported",
        default=False
    )
    ui_expand_global_preview: BoolProperty(
        name="Expand Global Preview",
        default=True
    )
    fbx_remove_armature_root: BoolProperty(
        name="Remove Armature Root",
        description="Removes the default Armature empty root when exporting FBX",
        default=False
    )
    reset_transform: BoolProperty(
        name="Reset Transform",
        description="Save object transforms, reset to origin (0,0,0 position/rotation), export, and restore",
        default=True
    )
    show_additional_settings: BoolProperty(
        name="Show Additional Settings",
        description="Show additional export settings",
        default=False
    )
    pre_rotation: FloatVectorProperty(
        name="Pre Rotation",
        description="Rotate objects by this amount before exporting, then restore after",
        size=3,
        default=(0.0, 0.0, 0.0),
        subtype='EULER'
    )
    pre_scale: FloatProperty(
        name="Pre Scale",
        description="Scale objects by this factor before exporting, then restore after",
        default=1.0,
        min=0.001,
    )
    rename_armature: BoolProperty(
        name="Rename Armature to 'Armature'",
        description="Rename armature object and data to 'Armature' before export (useful for Unity root name)",
        default=False
    )
    single_mesh: BoolProperty(
        name="Single Mesh",
        description="Merge all mesh objects under a single collection into one mesh object with non-armature modifiers applied",
        default=False
    )


def update_xray_brush(self, context):
    try:
        # Weight paint brush settings are in context.tool_settings.weight_paint.brush
        if context.mode != 'PAINT_WEIGHT':
            return
            
        brush = context.tool_settings.weight_paint.brush
        if not brush:
            return

        if self.xray_brush:
            # Save original states
            self.orig_use_frontface = brush.use_frontface
            self.orig_falloff_shape = brush.falloff_shape
            self.orig_use_frontface_falloff = brush.use_frontface_falloff
            
            # Apply XRay settings
            brush.use_frontface = False
            brush.falloff_shape = 'PROJECTED'
            brush.use_frontface_falloff = False
        else:
            # Restore original states
            brush.use_frontface = self.orig_use_frontface
            brush.falloff_shape = self.orig_falloff_shape
            brush.use_frontface_falloff = self.orig_use_frontface_falloff
    except Exception as e:
        print(f"Error in update_xray_brush: {e}")


class WeightToolsProperties(bpy.types.PropertyGroup):
    xray_brush: BoolProperty(
        name="XRay Brush",
        description="Toggle XRay Brush settings (Front Face Only: False, Falloff: Projected, Front Face Falloff: False)",
        default=False,
        update=update_xray_brush
    )
    orig_use_frontface: BoolProperty()
    orig_falloff_shape: StringProperty()
    orig_use_frontface_falloff: BoolProperty()


def update_pen_nav(self, context):
    try:
        prefs = context.preferences
        inputs = prefs.inputs

        if self.pen_nav:
            # Back up current values before changing them
            self.orig_emulate_3_button_mouse = inputs.use_mouse_emulate_3_button
            self.orig_auto_depth = inputs.use_mouse_depth_navigate
            self.orig_zoom_to_mouse = inputs.use_zoom_to_mouse

            # Apply pen nav settings
            inputs.use_mouse_emulate_3_button = True
            inputs.use_mouse_depth_navigate = True
            inputs.use_zoom_to_mouse = True
        else:
            # Restore original values
            inputs.use_mouse_emulate_3_button = self.orig_emulate_3_button_mouse
            inputs.use_mouse_depth_navigate = self.orig_auto_depth
            inputs.use_zoom_to_mouse = self.orig_zoom_to_mouse
    except Exception as e:
        print(f"[RexTools3] Error in update_pen_nav: {e}")


class SculptToolsProperties(bpy.types.PropertyGroup):
    pen_nav: BoolProperty(
        name="Pen Nav",
        description=(
            "Toggle pen-friendly navigation settings.\n"
            "ON: Emulate 3 Button Mouse + Auto Depth + Zoom to Mouse\n"
            "OFF: Restores previous values"
        ),
        default=False,
        update=update_pen_nav
    )
    # Backup fields
    orig_emulate_3_button_mouse: BoolProperty()
    orig_auto_depth: BoolProperty()
    orig_zoom_to_mouse: BoolProperty()


def get_mute_constraint_items(self, context):
    items = [
        ('ALL', "All Constraints", "Mute or unmute all constraints on selected bone(s)")
    ]
    added_keys = {'ALL'}
    
    if context and hasattr(context, "active_pose_bone") and context.active_pose_bone:
        for con in context.active_pose_bone.constraints:
            key = f"NAME:{con.name}"
            if key not in added_keys:
                items.append((key, f"Constraint: {con.name}", f"Target constraint '{con.name}'"))
                added_keys.add(key)
                
    type_items = [
        ('COPY_LOCATION', "Copy Location", ""),
        ('COPY_ROTATION', "Copy Rotation", ""),
        ('COPY_SCALE', "Copy Scale", ""),
        ('COPY_TRANSFORMS', "Copy Transforms", ""),
        ('LIMIT_DISTANCE', "Limit Distance", ""),
        ('LIMIT_LOCATION', "Limit Location", ""),
        ('LIMIT_ROTATION', "Limit Rotation", ""),
        ('LIMIT_SCALE', "Limit Scale", ""),
        ('MAINTAIN_VOLUME', "Maintain Volume", ""),
        ('TRANSFORM_CACHE', "Transform Cache", ""),
        ('CLAMP_TO', "Clamp To", ""),
        ('DAMPED_TRACK', "Damped Track", ""),
        ('IK', "IK", ""),
        ('LOCKED_TRACK', "Locked Track", ""),
        ('SPLINE_IK', "Spline IK", ""),
        ('STRETCH_TO', "Stretch To", ""),
        ('TRACK_TO', "Track To", ""),
        ('ACTION', "Action", ""),
        ('ARMATURE', "Armature", ""),
    ]
    
    for identifier, name, desc in type_items:
        key = f"TYPE:{identifier}"
        if key not in added_keys:
            items.append((key, name, desc if desc else f"All {name} constraints"))
            added_keys.add(key)
            
    return items


class PoseToolsProperties(bpy.types.PropertyGroup):
    source_armature: PointerProperty(
        name="Source",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE'
    )
    chained_bone_base_name: StringProperty(
        name="Chained Name",
        description="Base name for the chained bone renaming",
        default="spine"
    )
    mute_constraint_target: EnumProperty(
        name="Constraint Picker",
        description="Select constraint or type to mute/unmute, or All Constraints",
        items=get_mute_constraint_items
    )



class Rextools3MissingTextureItem(bpy.types.PropertyGroup):
    image_name: StringProperty(name="Image Name", default="")
    filepath: StringProperty(name="File Path", default="")
    materials: StringProperty(name="Materials", default="")


class Rextools3MissingTextureScanner(bpy.types.PropertyGroup):
    items: CollectionProperty(type=Rextools3MissingTextureItem)
    has_scanned: BoolProperty(name="Has Scanned", default=False)


_library_enum_cache = []

def _library_items(self, context):
    """Build the dropdown of asset libraries configured in Preferences."""
    _library_enum_cache.clear()
    _library_enum_cache.append(("__CUSTOM__", "Custom Folder...", "Use the custom folder set below"))
    for lib in context.preferences.filepaths.asset_libraries:
        if lib.path:
            _library_enum_cache.append((lib.name, lib.name, lib.path))
    return _library_enum_cache


_catalog_enum_cache = []

def _catalog_items(self, context):
    """Build the dropdown of catalogs found in the selected asset library."""
    import os
    _catalog_enum_cache.clear()
    _catalog_enum_cache.append(("__CUSTOM__", "New Catalog...", "Enter a custom catalog path below"))
    
    if self.library == "__CUSTOM__":
        path = self.custom_path
    else:
        path = ""
        for lib in context.preferences.filepaths.asset_libraries:
            if lib.name == self.library:
                path = lib.path
                break
    
    target = bpy.path.abspath(path) if path else ""
    if target and os.path.isdir(target):
        cats_file = os.path.join(target, "blender_assets.cats.txt")
        if os.path.exists(cats_file):
            try:
                with open(cats_file, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                for line in lines:
                    s = line.strip()
                    if not s or s.startswith("#") or s.startswith("VERSION"):
                        continue
                    parts = s.split(":")
                    if len(parts) >= 2:
                        cat_path = parts[1].strip()
                        if cat_path:
                            if not any(item[0] == cat_path for item in _catalog_enum_cache):
                                _catalog_enum_cache.append((cat_path, cat_path, cat_path))
            except Exception as e:
                print("[Quick Blender Assets] Failed to read catalogs:", e)
                
    return _catalog_enum_cache


class RexAssetExportSettings(bpy.types.PropertyGroup):
    library: EnumProperty(
        name="Asset Library",
        description="Where to save the asset. Libraries come from "
                    "Preferences > File Paths > Asset Libraries",
        items=_library_items,
    )
    custom_path: StringProperty(
        name="Custom Folder",
        description="Folder to write asset .blend files into",
        subtype='DIR_PATH',
        default="",
    )
    catalog_selection: EnumProperty(
        name="Catalog",
        description="Select an existing catalog or create a new one",
        items=_catalog_items,
    )
    catalog: StringProperty(
        name="New Catalog Path",
        description="Optional catalog path, e.g. 'Props/Furniture'. "
                    "It is created automatically if it does not exist. Leave empty for none",
        default="",
    )
    separate_files: BoolProperty(
        name="One file per object",
        description="Write each selected object to its own .blend "
                    "(off = put them all into a single .blend)",
        default=True,
    )



def update_displacement_strength(self, context):
    target = self.target_object
    if target and target.type == 'MESH':
        for modifier in target.modifiers:
            if modifier.type == 'DISPLACE' and modifier.name == "Displacement_imposter":
                modifier.strength = self.displacement_strength


class TextureOvenProperties(PropertyGroup):
    target_object: PointerProperty(
        name="Target Mesh",
        description="Select the target/low-poly mesh",
        type=bpy.types.Object
    )
    source_object: PointerProperty(
        name="Source Mesh",
        description="Select the source/high-poly mesh",
        type=bpy.types.Object
    )
    displacement_strength: FloatProperty(
        name="Displacement Strength",
        description="Adjust displacement modifier strength to fix gaps",
        default=0.0,
        min=-10.0,
        max=10.0,
        update=update_displacement_strength
    )
    ao_sample_count: IntProperty(
        name="AO Sample Count",
        default=16,
        min=1,
        max=4096,
        description="Sample size for AO bake, more = less grain + more bake time"
    )
    resolution: EnumProperty(
        name="Image Size",
        items=[
            ("256", "256x256", "Set image size to 256x256"),
            ("512", "512x512", "Set image size to 512x512"),
            ("1024", "1024x1024", "Set image size to 1024x1024"),
            ("2048", "2048x2048", "Set image size to 2048x2048"),
        ],
        default="512"
    )
    save_directory: StringProperty(
        name="Save Folder",
        description="Select texture save directory",
        default="",
        subtype='DIR_PATH'
    )
    bake_mode: EnumProperty(
        name="Bake Mode",
        items=[
            ('IMPOSTER', "Imposter (Albedo + AO + Normal)", "Bake Albedo, AO, and Normal maps for imposter creation"),
        ],
        default='IMPOSTER'
    )


class WalkCycleProperties(PropertyGroup):
    walk_mode: EnumProperty(
        name="Mode",
        items=[
            ('BIPEDAL', "Bipedal", "Generate bipedal walk cycle"),
            ('QUADRUPEDAL', "Quadrupedal", "Generate quadrupedal walk cycle"),
        ],
        default='BIPEDAL'
    )
    bone_leg_l: StringProperty(name="Leg L")
    bone_leg_r: StringProperty(name="Leg R")
    bone_arm_l: StringProperty(name="Arm L (Front L)")
    bone_arm_r: StringProperty(name="Arm R (Front R)")
    bone_hip: StringProperty(name="Hip")
    bone_head: StringProperty(name="Head / Spine")

    cycle_length: IntProperty(name="Cycle Length", default=24, min=4)
    stride_length: FloatProperty(name="Stride Length", default=0.5, min=0.0)
    step_height: FloatProperty(name="Step Height", default=0.2, min=0.0)
    hip_sway: FloatProperty(name="Hip Sway", default=0.05, min=0.0)
    hip_bob: FloatProperty(name="Hip Bob", default=0.05, min=0.0)
    arm_swing: FloatProperty(name="Arm Swing", default=0.2, min=0.0)


class EngineVertexStatsProperties(PropertyGroup):
    blender_verts: IntProperty(default=0)
    engine_verts: IntProperty(default=0)
    tris: IntProperty(default=0)
    count: IntProperty(default=0)


def register_properties():
    wm = bpy.types.WindowManager
    wm.modal_x = IntProperty(name="Mouse X", default=0)
    wm.modal_y = IntProperty(name="Mouse Y", default=0)

    bpy.types.Scene.bone_rename_props     = PointerProperty(type=BoneRenameProperties)
    bpy.types.Scene.highlow_renamer_props = PointerProperty(type=HighLowRenamerProperties)
    bpy.types.Scene.rex_marmoset_bridge_props = PointerProperty(type=Rextools3MarmosetBridgeProperties)
    bpy.types.Scene.rex_ai_web_bridge_props   = PointerProperty(type=Rextools3AIWebBridgeProperties)

    wm.select_similar_threshold   = FloatProperty(name="Threshold", default=0.0, min=0.0, max=1.0)
    wm.clear_inner_uv_area_seam   = BoolProperty(name="Clear Inner", default=False)
    wm.reseam_uv_area_seam        = BoolProperty(name="Reseam", default=False)
    wm.stop_loop_at_seam          = BoolProperty(name="Stop at Seam", default=True)
    
    bpy.types.Material.pbr_settings = PointerProperty(type=PBRMaterialSettings)

    bpy.types.Scene.rex_export_settings = PointerProperty(type=RexExportSettings)
    bpy.types.Collection.rex_export_overrides = PointerProperty(type=RexCollectionExportOverrides)
    bpy.types.Scene.chain_constraints_props = PointerProperty(type=ChainConstraintsAdderProperties)
    bpy.types.Scene.rex_common_settings = PointerProperty(type=RexCommonSettings)
    bpy.types.Scene.rex_auto_frame_range = BoolProperty(
        name="Auto Frame Range",
        description="Auto calculate start and end frame based on active action or selected NLA strips",
        default=False,
        update=update_auto_frame_range
    )
    bpy.types.Scene.rex_cleanup_props = PointerProperty(type=CleanupProperties)
    bpy.types.Scene.weight_tools_props = PointerProperty(type=WeightToolsProperties)
    bpy.types.Scene.pose_tools_props = PointerProperty(type=PoseToolsProperties)
    bpy.types.Scene.sculpt_tools_props = PointerProperty(type=SculptToolsProperties)
    bpy.types.Scene.rex_batch_mat_props = PointerProperty(type=BatchMaterialProperties)
    bpy.types.Scene.rex_missing_texture_scanner = PointerProperty(type=Rextools3MissingTextureScanner)
    bpy.types.Scene.rex_asset_export_settings = PointerProperty(type=RexAssetExportSettings)
    bpy.types.Scene.rex_texture_oven_props = PointerProperty(type=TextureOvenProperties)
    bpy.types.Scene.rex_engine_vertex_stats = PointerProperty(type=EngineVertexStatsProperties)
    bpy.types.Scene.rextools3_keyframe_offset_props = PointerProperty(type=Rextools3KeyframeOffsetProperties)
    bpy.types.Scene.rextools3_walk_cycle_props = PointerProperty(type=WalkCycleProperties)


def unregister_properties():
    wm = bpy.types.WindowManager
    del wm.modal_x
    del wm.modal_y

    del bpy.types.Scene.bone_rename_props
    del bpy.types.Scene.highlow_renamer_props
    del bpy.types.Scene.rex_marmoset_bridge_props
    del bpy.types.Scene.rex_ai_web_bridge_props

    del wm.select_similar_threshold
    del wm.clear_inner_uv_area_seam
    del wm.reseam_uv_area_seam
    del wm.stop_loop_at_seam
    
    del bpy.types.Material.pbr_settings
    
    del bpy.types.Scene.rex_export_settings
    del bpy.types.Collection.rex_export_overrides
    del bpy.types.Scene.chain_constraints_props
    del bpy.types.Scene.rex_common_settings
    del bpy.types.Scene.rex_auto_frame_range
    del bpy.types.Scene.rex_cleanup_props
    del bpy.types.Scene.weight_tools_props
    del bpy.types.Scene.pose_tools_props
    del bpy.types.Scene.sculpt_tools_props
    del bpy.types.Scene.rex_batch_mat_props
    del bpy.types.Scene.rex_missing_texture_scanner
    del bpy.types.Scene.rex_asset_export_settings
    del bpy.types.Scene.rex_texture_oven_props
    del bpy.types.Scene.rex_engine_vertex_stats
    del bpy.types.Scene.rextools3_keyframe_offset_props
    del bpy.types.Scene.rextools3_walk_cycle_props

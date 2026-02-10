import bpy
from bpy.props import (
    IntProperty, FloatProperty,
    BoolProperty, StringProperty,
    PointerProperty, EnumProperty,
    FloatVectorProperty, CollectionProperty
)
from bpy.types import PropertyGroup


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
        sep = nodes.get(f"{input_name}Split") or nodes.new('ShaderNodeSeparateRGB')
        sep.name = f"{input_name}Split"
        sep.location = (tex_node.location.x + 150, tex_node.location.y)
        if sep.inputs['Image'].is_linked:
            links.remove(sep.inputs['Image'].links[0])
        links.new(tex_node.outputs['Color'], sep.inputs['Image'])
        src_sock = sep.outputs[chan]

    # Invert logic
    if invert:
        inv_node = nodes.get(f"{input_name}Invert") or nodes.new('ShaderNodeInvert')
        inv_node.name = f"{input_name}Invert"
        inv_node.label = f"Invert {input_name}"
        inv_node.location = (tex_node.location.x + 300, tex_node.location.y - 100)
        inv_node.inputs['Fac'].default_value = 1.0
        
        # Link source to Invert
        if inv_node.inputs['Color'].is_linked:
            links.remove(inv_node.inputs['Color'].links[0])
        links.new(src_sock, inv_node.inputs['Color'])
        
        # New source is the Invert output
        src_sock = inv_node.outputs['Color']
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
        sep = nodes.get("NormalSplit") or nodes.new('ShaderNodeSeparateRGB')
        sep.name = "NormalSplit"
        sep.label = "Normal Split"
        
        inv = nodes.get("NormalInvertG") or nodes.new('ShaderNodeMath')
        inv.name = "NormalInvertG"
        inv.label = "Invert G"
        inv.operation = 'SUBTRACT'
        inv.inputs[0].default_value = 1.0
        
        com = nodes.get("NormalCombine") or nodes.new('ShaderNodeCombineRGB')
        com.name = "NormalCombine"
        com.label = "Normal Combine"
        
        # Positions
        sep.location = (tex_node.location.x + 200, tex_node.location.y)
        inv.location = (sep.location.x + 200, sep.location.y - 100)
        com.location = (inv.location.x + 200, inv.location.y + 100)
        
        # Links
        links.new(tex_node.outputs['Color'], sep.inputs['Image'])
        links.new(sep.outputs['R'], com.inputs['R'])
        links.new(sep.outputs['G'], inv.inputs[1])
        links.new(inv.outputs['Value'], com.inputs['G'])
        links.new(sep.outputs['B'], com.inputs['B'])
        links.new(com.outputs['Image'], nm_node.inputs['Color'])
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
                    target_out = com.outputs.get('Image') or com.outputs[0]
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


class HighLowRenamerProperties(PropertyGroup):
    obj_name: StringProperty(name="Object Name", default="")
    high_prefix: StringProperty(name="High Prefix", default="_high")
    low_prefix: StringProperty(name="Low Prefix", default="_low")


class PBRMaterialSettings(PropertyGroup):
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


class CleanupProperties(PropertyGroup):
    normals: BoolProperty(name="Normals", default=True)
    quad: BoolProperty(name="Quad", default=True)
    mats: BoolProperty(name="Mats", default=True)


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
    clean_modifiers_all: BoolProperty(
        name="All",
        description="Operate on all visible objects, selected or not",
        default=False
    )
    clean_modifiers_hidden: BoolProperty(
        name="Hidden",
        description="Also remove modifiers that are hidden in the viewport",
        default=False
    )
    smart_join_apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply all modifiers before joining in Smart Join", 
        default=False
    )
    apply_modifiers_ignore_list: CollectionProperty(type=ModifierIgnoreItem)


class RexExportSettings(PropertyGroup):
    export_path: StringProperty(
        name="Export Path",
        description="Global directory for exports",
        default="",
        subtype='DIR_PATH'
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
    
    def get_presets(self, context):
        import os
        import bpy
        
        presets = [('NONE', "No Preset", "")]
        
        # Determine preset folder based on format
        fmt = self.export_format.lower()
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
    show_custom_locations: BoolProperty(
        name="Show Custom Locations",
        description="Show a list of objects/collections with custom export paths",
        default=False
    )
    fbx_remove_armature_root: BoolProperty(
        name="Remove Armature Root",
        description="Removes the default Armature empty root when exporting FBX",
        default=False
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


class PoseToolsProperties(bpy.types.PropertyGroup):
    source_armature: PointerProperty(
        name="Source",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE'
    )


def register_properties():
    wm = bpy.types.WindowManager
    wm.modal_x = IntProperty(name="Mouse X", default=0)
    wm.modal_y = IntProperty(name="Mouse Y", default=0)

    bpy.types.Scene.bone_rename_props     = PointerProperty(type=BoneRenameProperties)
    bpy.types.Scene.highlow_renamer_props = PointerProperty(type=HighLowRenamerProperties)

    wm.select_similar_threshold   = FloatProperty(name="Threshold", default=0.0, min=0.0, max=1.0)
    wm.clear_inner_uv_area_seam   = BoolProperty(name="Clear Inner", default=False)
    wm.reseam_uv_area_seam        = BoolProperty(name="Reseam", default=False)
    wm.stop_loop_at_seam          = BoolProperty(name="Stop at Seam", default=True)
    
    bpy.types.Material.pbr_settings = PointerProperty(type=PBRMaterialSettings)

    bpy.types.Scene.rex_export_settings = PointerProperty(type=RexExportSettings)
    bpy.types.Collection.export_location = StringProperty(
        name="Export Location",
        subtype='DIR_PATH'
    )
    bpy.types.Object.export_location = StringProperty(
        name="Export Location",
        subtype='DIR_PATH'
    )
    bpy.types.Scene.chain_constraints_props = PointerProperty(type=ChainConstraintsAdderProperties)
    bpy.types.Scene.rex_common_settings = PointerProperty(type=RexCommonSettings)
    bpy.types.Scene.rex_auto_frame_range = BoolProperty(
        name="Auto Frame Range",
        description="Auto calculate start and end frame based on active action",
        default=False
    )
    bpy.types.Scene.rex_cleanup_props = PointerProperty(type=CleanupProperties)
    bpy.types.Scene.weight_tools_props = PointerProperty(type=WeightToolsProperties)
    bpy.types.Scene.pose_tools_props = PointerProperty(type=PoseToolsProperties)


def unregister_properties():
    wm = bpy.types.WindowManager
    del wm.modal_x
    del wm.modal_y

    del bpy.types.Scene.bone_rename_props
    del bpy.types.Scene.highlow_renamer_props

    del wm.select_similar_threshold
    del wm.clear_inner_uv_area_seam
    del wm.reseam_uv_area_seam
    del wm.stop_loop_at_seam
    
    del bpy.types.Material.pbr_settings
    
    del bpy.types.Scene.rex_export_settings
    del bpy.types.Collection.export_location
    del bpy.types.Object.export_location
    del bpy.types.Scene.chain_constraints_props
    del bpy.types.Scene.rex_common_settings
    del bpy.types.Scene.rex_auto_frame_range
    del bpy.types.Scene.rex_cleanup_props
    del bpy.types.Scene.weight_tools_props
    del bpy.types.Scene.pose_tools_props

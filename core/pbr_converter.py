# core/pbr_converter.py
"""
RexTools3 Easy PBR Graph Tracer & Converter

Analyzes regular or imported material node graphs (FBX, OBJ, glTF, manual)
and converts them into the Easy PBR supported node graph system.
Supports full conversion, glTF packed ORM textures, DirectX normal flips,
and partial conversion with strict retention of complex/procedural nodes.
"""

import bpy
from . import node_utils

# Standard PBR node names used across RexTools3 Easy PBR
EASY_PBR_NODE_NAMES = {
    'PBRTexCoord', 'PBRMapping',
    'BaseTex', 'BaseTintMix',
    'AOTex', 'AOSplit', 'AOInvert', 'AOAdd', 'AOMix',
    'RoughnessTex', 'RoughnessSplit', 'RoughnessInvert', 'RoughnessMath',
    'MetallicTex', 'MetallicSplit', 'MetallicInvert', 'MetallicMath',
    'NormalTex', 'NormalSplit', 'NormalInvertG', 'NormalCombine', 'NormalMap',
    'EmissionTex', 'EmissionSplit', 'EmissionTintMix',
    'AlphaTex', 'AlphaSplit', 'AlphaMath', 'AlphaClip',
    'HeightTex', 'HeightDisplace',
}

PROCEDURAL_TEXTURE_TYPES = {
    'TEX_NOISE', 'TEX_VORONOI', 'TEX_WAVE', 'TEX_MUSGRAVE',
    'TEX_BRICK', 'TEX_MAGIC', 'TEX_CHECKER', 'TEX_GRADIENT', 'TEX_WHITE_NOISE'
}


def _get_upstream_nodes(socket, visited=None):
    """Recursively collect all upstream nodes feeding into a socket."""
    if visited is None:
        visited = set()
    if not socket or not socket.is_linked:
        return visited
    for link in socket.links:
        from_node = link.from_node
        if from_node not in visited:
            visited.add(from_node)
            for inp in from_node.inputs:
                if inp.is_linked:
                    _get_upstream_nodes(inp, visited)
    return visited


def is_easy_pbr_material(material) -> bool:
    """Check if material is already formatted and compliant with Easy PBR."""
    if not material or not material.use_nodes:
        return False
    nodes = material.node_tree.nodes
    principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not principled:
        return False

    tex_nodes = [n for n in nodes if n.type == 'TEX_IMAGE']
    if tex_nodes:
        if not nodes.get("PBRMapping"):
            return False

        # Check Base Color: if linked, should use BaseTex or BaseTintMix or AOMix
        bc = principled.inputs.get('Base Color')
        if bc and bc.is_linked:
            src = bc.links[0].from_node
            if src.name not in ('BaseTintMix', 'BaseTex', 'AOMix'):
                return False

        # Check Roughness: if linked, should use RoughnessMath
        rough = principled.inputs.get('Roughness')
        if rough and rough.is_linked:
            src = rough.links[0].from_node
            if src.name != 'RoughnessMath':
                return False

        # Check Metallic: if linked, should use MetallicMath
        metal = principled.inputs.get('Metallic')
        if metal and metal.is_linked:
            src = metal.links[0].from_node
            if src.name != 'MetallicMath':
                return False

        # Check Normal: if linked, should use NormalMap
        norm = principled.inputs.get('Normal')
        if norm and norm.is_linked:
            src = norm.links[0].from_node
            if src.name != 'NormalMap':
                return False

        return True
    else:
        # If no textures exist, must at least have PBRMapping or PBRTexCoord to be an Easy PBR setup
        return nodes.get("PBRMapping") is not None


def analyze_material_graph(material) -> dict:
    """
    Traces the material node graph and determines:
    - Overall status: 'ALREADY_EASY_PBR', 'FULLY_CONVERTIBLE', 'PARTIALLY_CONVERTIBLE', 'UNCONVERTIBLE'
    - Convertible slots with extracted textures, channels, strengths, tints
    - Unconvertible slots and their upstream nodes to retain
    - Reasons/notes for user dialog
    """
    analysis = {
        'status': 'UNCONVERTIBLE',
        'material': material,
        'principled': None,
        'output_node': None,
        'tiling': (1.0, 1.0),
        'convertible_slots': {},    # slot_name -> dict(info)
        'unconvertible_slots': {},  # slot_name -> dict(reason, nodes)
        'unconvertible_nodes': set(),
        'obsolete_nodes': set(),
        'notes': [],
        'has_procedural': False,
    }

    if not material:
        analysis['notes'].append("No material provided.")
        return analysis

    if not material.use_nodes:
        # Simple material with no nodes - fully convertible to basic Easy PBR
        analysis['status'] = 'FULLY_CONVERTIBLE'
        col = getattr(material, "diffuse_color", (0.8, 0.8, 0.8, 1.0))
        analysis['convertible_slots']['Base Color'] = {
            'type': 'CONSTANT',
            'value': tuple(col)[:4]
        }
        analysis['notes'].append("Material without nodes converted to basic Principled BSDF.")
        return analysis

    nodes = material.node_tree.nodes
    output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
    if not output_node:
        output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)

    if not output_node:
        analysis['notes'].append("No Material Output node found in tree.")
        return analysis
    analysis['output_node'] = output_node

    # Find surface shader
    surf_input = output_node.inputs.get('Surface')
    principled = None
    if surf_input and surf_input.is_linked:
        surf_node = surf_input.links[0].from_node
        if surf_node.type == 'BSDF_PRINCIPLED':
            principled = surf_node
        elif surf_node.type in ('MIX_SHADER', 'ADD_SHADER'):
            # Check if one input is Principled BSDF
            # Mark the other branches as unconvertible to retain
            for inp in surf_node.inputs:
                if inp.is_linked and inp.links[0].from_node.type == 'BSDF_PRINCIPLED':
                    principled = inp.links[0].from_node
                    break
            if principled:
                analysis['unconvertible_slots']['Secondary Shader'] = {
                    'reason': f"Material uses {surf_node.type.replace('_', ' ').title()}",
                    'nodes': _get_upstream_nodes(surf_input) - {principled}
                }
                analysis['unconvertible_nodes'].update(analysis['unconvertible_slots']['Secondary Shader']['nodes'])
            else:
                analysis['notes'].append(f"Surface is driven by unsupported {surf_node.type}.")
                return analysis
        elif surf_node.type == 'BSDF_DIFFUSE':
            # Simple diffuse shader that we can upgrade to Principled BSDF
            principled = surf_node
            analysis['upgrade_from_diffuse'] = True
        else:
            # Check if there is a BSDF_PRINCIPLED in the graph that we can wire
            alt_principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if alt_principled:
                principled = alt_principled
            else:
                analysis['notes'].append(f"Surface uses unsupported shader '{surf_node.type}'.")
                return analysis
    else:
        # Surface not linked, search for any Principled BSDF in tree
        principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not principled:
            analysis['notes'].append("No Principled BSDF found in material.")
            return analysis

    analysis['principled'] = principled

    # Check if already Easy PBR
    if is_easy_pbr_material(material):
        analysis['status'] = 'ALREADY_EASY_PBR'
        analysis['notes'].append("Material is already in Easy PBR format.")
        return analysis

    # 1. Trace Texture Coordinates & Tiling from any existing TexImage node
    tex_nodes = [n for n in nodes if n.type == 'TEX_IMAGE']
    for tn in tex_nodes:
        vec_in = tn.inputs.get('Vector')
        if vec_in and vec_in.is_linked:
            v_src = vec_in.links[0].from_node
            if v_src.type == 'MAPPING':
                scale_sock = v_src.inputs.get('Scale')
                if scale_sock:
                    try:
                        analysis['tiling'] = (scale_sock.default_value[0], scale_sock.default_value[1])
                    except Exception:
                        pass
                analysis['obsolete_nodes'].add(v_src)
                # Also collect any Texture Coordinate or UV Map node linked to it
                if v_src.inputs.get('Vector') and v_src.inputs['Vector'].is_linked:
                    coord_node = v_src.inputs['Vector'].links[0].from_node
                    if coord_node.type in ('TEX_COORD', 'UVMAP'):
                        analysis['obsolete_nodes'].add(coord_node)
                break

    # Helper function to inspect a scalar/color channel chain
    def trace_chain(socket):
        """
        Traces a socket upstream to detect:
        - Image Texture
        - Channel split (R, G, B, A, FULL)
        - Invert
        - Math multiply (Strength)
        - Mix (Tint)
        - Procedural / complex nodes
        """
        info = {
            'is_convertible': False,
            'image': None,
            'channel': 'FULL',
            'invert': False,
            'strength': 1.0,
            'tint': (1.0, 1.0, 1.0, 1.0),
            'nodes_in_chain': set(),
            'unconvertible_reason': '',
            'threshold': 0.5,
            'is_clip': False,
        }

        if not socket or not socket.is_linked:
            info['is_convertible'] = True
            info['type'] = 'CONSTANT'
            try:
                info['value'] = socket.default_value[:] if hasattr(socket.default_value, '__len__') else float(socket.default_value)
            except Exception:
                info['value'] = None
            return info

        curr_nodes = _get_upstream_nodes(socket)
        info['nodes_in_chain'] = curr_nodes

        # Check for procedural textures or unsupported nodes in chain
        procedurals = [n for n in curr_nodes if n.type in PROCEDURAL_TEXTURE_TYPES]
        if procedurals:
            info['is_convertible'] = False
            info['unconvertible_reason'] = f"Procedural texture ({procedurals[0].type.replace('TEX_', '').title()})"
            return info

        # Step back through recognized nodes: Math, Invert, Separate, Mix
        curr = socket.links[0].from_node
        curr_sock = socket.links[0].from_socket

        while curr:
            # 1. Image Texture
            if curr.type == 'TEX_IMAGE':
                info['image'] = curr.image
                # If output used is Alpha
                if curr_sock and curr_sock.name in ('Alpha', 'A'):
                    info['channel'] = 'A'
                info['is_convertible'] = True
                break

            # 2. Channel Split (SeparateColor / SeparateRGB)
            elif curr.type in ('SEPARATE_COLOR', 'SEPARATE_RGB'):
                out_name = curr_sock.name if curr_sock else ''
                if out_name in ('Red', 'R'):
                    info['channel'] = 'R'
                elif out_name in ('Green', 'G'):
                    info['channel'] = 'G'
                elif out_name in ('Blue', 'B'):
                    info['channel'] = 'B'
                elif out_name in ('Alpha', 'A'):
                    info['channel'] = 'A'
                
                col_in = node_utils.get_separate_input_socket(curr)
                if col_in and col_in.is_linked:
                    curr_sock = col_in.links[0].from_socket
                    curr = col_in.links[0].from_node
                    continue
                break

            # 3. Invert (InvertColor / Invert)
            elif curr.type in ('INVERT', 'INVERT_COLOR'):
                info['invert'] = True
                inv_in = node_utils.get_invert_input_socket(curr)
                if inv_in and inv_in.is_linked:
                    curr_sock = inv_in.links[0].from_socket
                    curr = inv_in.links[0].from_node
                    continue
                break

            # 4. Math Node (Multiply for strength, Greater Than for clip)
            elif curr.type == 'MATH':
                if curr.operation == 'MULTIPLY':
                    next_sock = None
                    next_node = None
                    for idx in (0, 1):
                        if not curr.inputs[idx].is_linked:
                            try:
                                info['strength'] = float(curr.inputs[idx].default_value)
                            except Exception:
                                pass
                        else:
                            next_sock = curr.inputs[idx].links[0].from_socket
                            next_node = curr.inputs[idx].links[0].from_node
                    if next_node:
                        curr_sock = next_sock
                        curr = next_node
                        continue
                elif curr.operation == 'GREATER_THAN':
                    info['is_clip'] = True
                    try:
                        info['threshold'] = float(curr.inputs[1].default_value)
                    except Exception:
                        pass
                    if curr.inputs[0].is_linked:
                        curr_sock = curr.inputs[0].links[0].from_socket
                        curr = curr.inputs[0].links[0].from_node
                        continue
                break

            # 5. Mix Node (RGBA Multiply for Tint or AO)
            elif curr.type in ('MIX', 'MIX_RGB'):
                if curr.blend_type == 'MULTIPLY':
                    b_in = curr.inputs.get('B') or curr.inputs.get('Color2')
                    if b_in and not b_in.is_linked:
                        try:
                            info['tint'] = tuple(b_in.default_value)[:4]
                        except Exception:
                            pass
                    a_in = curr.inputs.get('A') or curr.inputs.get('Color1')
                    if a_in and a_in.is_linked:
                        curr_sock = a_in.links[0].from_socket
                        curr = a_in.links[0].from_node
                        continue
                break

            # Unrecognized node in chain
            info['is_convertible'] = False
            info['unconvertible_reason'] = f"Complex node network ({curr.type.replace('_', ' ').title()})"
            break

        return info

    # 2. Trace Base Color & AO
    bc_sock = principled.inputs.get('Base Color')
    if bc_sock:
        if not bc_sock.is_linked:
            analysis['convertible_slots']['Base Color'] = {
                'type': 'CONSTANT',
                'value': tuple(bc_sock.default_value)[:4]
            }
        else:
            bc_info = trace_chain(bc_sock)
            if bc_info['is_convertible'] and bc_info['image']:
                analysis['convertible_slots']['Base Color'] = bc_info
                first_node = bc_sock.links[0].from_node
                if first_node.type in ('MIX', 'MIX_RGB') and first_node.blend_type == 'MULTIPLY':
                    b_in = first_node.inputs.get('B') or first_node.inputs.get('Color2')
                    if b_in and b_in.is_linked:
                        ao_info = trace_chain(b_in)
                        if ao_info['is_convertible'] and ao_info['image']:
                            analysis['convertible_slots']['AO'] = ao_info
            else:
                analysis['unconvertible_slots']['Base Color'] = {
                    'reason': bc_info['unconvertible_reason'] or "Non-standard Base Color chain",
                    'nodes': bc_info['nodes_in_chain']
                }
                analysis['unconvertible_nodes'].update(bc_info['nodes_in_chain'])

    # 3. Trace Roughness
    rough_sock = principled.inputs.get('Roughness')
    if rough_sock:
        if not rough_sock.is_linked:
            analysis['convertible_slots']['Roughness'] = {
                'type': 'CONSTANT',
                'strength': float(rough_sock.default_value)
            }
        else:
            r_info = trace_chain(rough_sock)
            if r_info['is_convertible'] and r_info['image']:
                analysis['convertible_slots']['Roughness'] = r_info
            else:
                analysis['unconvertible_slots']['Roughness'] = {
                    'reason': r_info['unconvertible_reason'] or "Complex Roughness graph",
                    'nodes': r_info['nodes_in_chain']
                }
                analysis['unconvertible_nodes'].update(r_info['nodes_in_chain'])

    # 4. Trace Metallic
    metal_sock = principled.inputs.get('Metallic')
    if metal_sock:
        if not metal_sock.is_linked:
            analysis['convertible_slots']['Metallic'] = {
                'type': 'CONSTANT',
                'strength': float(metal_sock.default_value)
            }
        else:
            m_info = trace_chain(metal_sock)
            if m_info['is_convertible'] and m_info['image']:
                analysis['convertible_slots']['Metallic'] = m_info
            else:
                analysis['unconvertible_slots']['Metallic'] = {
                    'reason': m_info['unconvertible_reason'] or "Complex Metallic graph",
                    'nodes': m_info['nodes_in_chain']
                }
                analysis['unconvertible_nodes'].update(m_info['nodes_in_chain'])

    # 5. Trace Normal
    norm_sock = principled.inputs.get('Normal')
    if norm_sock:
        if norm_sock.is_linked:
            n_node = norm_sock.links[0].from_node
            norm_nodes = _get_upstream_nodes(norm_sock)
            
            if n_node.type == 'NORMAL_MAP':
                col_in = n_node.inputs.get('Color')
                strength = float(n_node.inputs['Strength'].default_value) if 'Strength' in n_node.inputs else 1.0
                
                flip_g = False
                tex_found = None
                if col_in and col_in.is_linked:
                    src = col_in.links[0].from_node
                    if src.type == 'TEX_IMAGE':
                        tex_found = src
                    elif src.type in ('COMBINE_COLOR', 'COMBINE_RGB'):
                        g_in = node_utils.get_combine_input_socket(src, 'G')
                        if g_in and g_in.is_linked and g_in.links[0].from_node.type == 'MATH' and g_in.links[0].from_node.operation == 'SUBTRACT':
                            flip_g = True
                        r_in = node_utils.get_combine_input_socket(src, 'R')
                        if r_in and r_in.is_linked and r_in.links[0].from_node.type in ('SEPARATE_COLOR', 'SEPARATE_RGB'):
                            sep = r_in.links[0].from_node
                            sep_in = node_utils.get_separate_input_socket(sep)
                            if sep_in and sep_in.is_linked and sep_in.links[0].from_node.type == 'TEX_IMAGE':
                                tex_found = sep_in.links[0].from_node

                if tex_found and tex_found.image:
                    analysis['convertible_slots']['Normal'] = {
                        'image': tex_found.image,
                        'strength': strength,
                        'flip_normal_g': flip_g,
                        'nodes_in_chain': norm_nodes,
                    }
                else:
                    analysis['unconvertible_slots']['Normal'] = {
                        'reason': "Normal Map node missing valid Image Texture",
                        'nodes': norm_nodes
                    }
                    analysis['unconvertible_nodes'].update(norm_nodes)

            elif n_node.type == 'TEX_IMAGE':
                analysis['convertible_slots']['Normal'] = {
                    'image': n_node.image,
                    'strength': 1.0,
                    'flip_normal_g': False,
                    'nodes_in_chain': norm_nodes,
                }
            else:
                analysis['unconvertible_slots']['Normal'] = {
                    'reason': f"Non-standard Normal setup ({n_node.type.replace('_', ' ').title()})",
                    'nodes': norm_nodes
                }
                analysis['unconvertible_nodes'].update(norm_nodes)

    # 6. Trace Emission
    em_sock = principled.inputs.get('Emission Color') or principled.inputs.get('Emission')
    em_strength_sock = principled.inputs.get('Emission Strength')
    em_strength = float(em_strength_sock.default_value) if em_strength_sock else 1.0
    
    if em_sock:
        if not em_sock.is_linked:
            analysis['convertible_slots']['Emission'] = {
                'type': 'CONSTANT',
                'value': tuple(em_sock.default_value)[:4],
                'strength': em_strength
            }
        else:
            e_info = trace_chain(em_sock)
            if e_info['is_convertible'] and e_info['image']:
                e_info['strength'] = em_strength
                analysis['convertible_slots']['Emission'] = e_info
            else:
                analysis['unconvertible_slots']['Emission'] = {
                    'reason': e_info['unconvertible_reason'] or "Complex Emission graph",
                    'nodes': e_info['nodes_in_chain']
                }
                analysis['unconvertible_nodes'].update(e_info['nodes_in_chain'])

    # 7. Trace Alpha
    alpha_sock = principled.inputs.get('Alpha')
    if alpha_sock:
        if not alpha_sock.is_linked:
            analysis['convertible_slots']['Alpha'] = {
                'type': 'CONSTANT',
                'strength': float(alpha_sock.default_value)
            }
        else:
            a_info = trace_chain(alpha_sock)
            if a_info['is_convertible'] and a_info['image']:
                bc_slot = analysis['convertible_slots'].get('Base Color', {})
                is_separate = (bc_slot.get('image') != a_info['image'])
                a_info['use_separate_alpha'] = is_separate
                analysis['convertible_slots']['Alpha'] = a_info
            else:
                analysis['unconvertible_slots']['Alpha'] = {
                    'reason': a_info['unconvertible_reason'] or "Complex Alpha graph",
                    'nodes': a_info['nodes_in_chain']
                }
                analysis['unconvertible_nodes'].update(a_info['nodes_in_chain'])

    # 8. Trace Displacement / Height from Output node
    disp_sock = output_node.inputs.get('Displacement')
    if disp_sock and disp_sock.is_linked:
        d_node = disp_sock.links[0].from_node
        d_nodes = _get_upstream_nodes(disp_sock)
        if d_node.type == 'DISPLACEMENT':
            h_in = d_node.inputs.get('Height')
            h_scale = float(d_node.inputs['Scale'].default_value) if 'Scale' in d_node.inputs else 0.1
            if h_in and h_in.is_linked and h_in.links[0].from_node.type == 'TEX_IMAGE':
                analysis['convertible_slots']['Height'] = {
                    'image': h_in.links[0].from_node.image,
                    'strength': h_scale,
                    'nodes_in_chain': d_nodes
                }
            else:
                analysis['unconvertible_slots']['Height'] = {
                    'reason': "Displacement node missing valid height texture",
                    'nodes': d_nodes
                }
                analysis['unconvertible_nodes'].update(d_nodes)
        elif d_node.type == 'TEX_IMAGE':
            analysis['convertible_slots']['Height'] = {
                'image': d_node.image,
                'strength': 0.1,
                'nodes_in_chain': d_nodes
            }
        else:
            analysis['unconvertible_slots']['Height'] = {
                'reason': f"Non-standard Displacement setup ({d_node.type.replace('_', ' ').title()})",
                'nodes': d_nodes
            }
            analysis['unconvertible_nodes'].update(d_nodes)

    # Detect glTF Packed ORM texture if not already assigned to AO
    r_slot = analysis['convertible_slots'].get('Roughness', {})
    m_slot = analysis['convertible_slots'].get('Metallic', {})
    if 'AO' not in analysis['convertible_slots'] and r_slot.get('image') and m_slot.get('image'):
        if r_slot['image'] == m_slot['image'] and r_slot.get('channel') == 'G' and m_slot.get('channel') == 'B':
            analysis['convertible_slots']['AO'] = {
                'image': r_slot['image'],
                'channel': 'R',
                'strength': 1.0,
                'invert': False,
            }

    # Evaluate Final Status
    has_convertible = len(analysis['convertible_slots']) > 0
    has_unconvertible = len(analysis['unconvertible_slots']) > 0

    if has_convertible and not has_unconvertible:
        analysis['status'] = 'FULLY_CONVERTIBLE'
    elif has_convertible and has_unconvertible:
        analysis['status'] = 'PARTIALLY_CONVERTIBLE'
    else:
        analysis['status'] = 'UNCONVERTIBLE'

    return analysis


def convert_material_to_easy_pbr(material, analysis=None, partial: bool = False) -> bool:
    """
    Executes conversion of a regular/imported material into the Easy PBR graph system.
    If partial=True, all unconvertible nodes and their connections are strictly retained.
    """
    if not material:
        return False

    if not analysis:
        analysis = analyze_material_graph(material)

    if analysis['status'] == 'UNCONVERTIBLE':
        return False

    if analysis['status'] == 'ALREADY_EASY_PBR':
        try:
            bpy.ops.pbr.arrange_nodes()
        except Exception:
            pass
        return True

    material.use_nodes = True
    node_tree = material.node_tree
    nodes = node_tree.nodes
    links = node_tree.links
    settings = material.pbr_settings

    # 1. Output & Principled BSDF baseline
    output_node = analysis.get('output_node') or next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if not output_node:
        output_node = nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (400, 0)

    principled = analysis.get('principled')
    if not principled or principled.type != 'BSDF_PRINCIPLED':
        old_principled = principled
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 0)
        if old_principled and old_principled not in analysis['unconvertible_nodes']:
            try: nodes.remove(old_principled)
            except Exception: pass

    if 'Secondary Shader' not in analysis['unconvertible_slots']:
        links.new(principled.outputs['BSDF'], output_node.inputs['Surface'])

    # 2. PBR Texture Coordinate & Mapping
    tiling = analysis.get('tiling', (1.0, 1.0))
    settings.pbr_tiling = tiling

    tex_coord = nodes.get("PBRTexCoord") or nodes.new('ShaderNodeTexCoord')
    tex_coord.name = "PBRTexCoord"
    tex_coord.label = "PBR Texture Coordinate"
    tex_coord.location = (-950, 0)

    mapping = nodes.get("PBRMapping") or nodes.new('ShaderNodeMapping')
    mapping.name = "PBRMapping"
    mapping.label = "PBR Mapping"
    mapping.location = (-750, 0)
    mapping.inputs['Scale'].default_value[0] = tiling[0]
    mapping.inputs['Scale'].default_value[1] = tiling[1]
    if not mapping.inputs['Vector'].is_linked:
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

    conv = analysis['convertible_slots']
    unconv_nodes = analysis['unconvertible_nodes']

    def safe_remove_nodes(node_set):
        for n in node_set:
            if n not in unconv_nodes and n != principled and n != output_node and n not in (tex_coord, mapping):
                try:
                    nodes.remove(n)
                except Exception:
                    pass

    safe_remove_nodes(analysis.get('obsolete_nodes', set()))

    # 3. Base Color
    bc_sock = principled.inputs['Base Color']
    tint_out = None
    if 'Base Color' in conv:
        bc_info = conv['Base Color']
        for l in list(bc_sock.links):
            links.remove(l)

        if bc_info.get('type') == 'CONSTANT':
            if 'value' in bc_info and bc_info['value']:
                bc_sock.default_value = bc_info['value']
        elif bc_info.get('image'):
            base_tex = nodes.get("BaseTex") or nodes.new('ShaderNodeTexImage')
            base_tex.name = "BaseTex"
            base_tex.label = "Base Color Texture"
            base_tex.image = bc_info['image']
            base_tex.image.alpha_mode = 'CHANNEL_PACKED'
            base_tex.image.colorspace_settings.name = 'sRGB'
            base_tex.location = (-450, 250)
            links.new(mapping.outputs['Vector'], base_tex.inputs['Vector'])

            tint_mix = nodes.get("BaseTintMix") or node_utils.create_mix_rgba_node(nodes, "BaseTintMix", 'MULTIPLY')
            tint_mix.name = "BaseTintMix"
            tint_mix.label = "Base Color Tint"
            tint_mix.location = (-180, 250)
            if 'Factor' in tint_mix.inputs:
                tint_mix.inputs['Factor'].default_value = 1.0
            
            a_in = node_utils.get_mix_a_socket(tint_mix)
            b_in = node_utils.get_mix_b_socket(tint_mix)
            if a_in: links.new(base_tex.outputs['Color'], a_in)
            if b_in: b_in.default_value = bc_info.get('tint', (1.0, 1.0, 1.0, 1.0))

            tint_out = node_utils.get_mix_output_socket(tint_mix)
            links.new(tint_out, bc_sock)
            safe_remove_nodes(bc_info.get('nodes_in_chain', set()) - {base_tex})

    # 3b. Ambient Occlusion (AO)
    if 'AO' in conv and conv['AO'].get('image'):
        ao_info = conv['AO']
        ao_tex = nodes.get("AOTex") or nodes.new('ShaderNodeTexImage')
        ao_tex.name = "AOTex"
        ao_tex.label = "AO Texture"
        ao_tex.image = ao_info['image']
        ao_tex.image.colorspace_settings.name = 'Non-Color'
        ao_tex.location = (-450, 450)
        links.new(mapping.outputs['Vector'], ao_tex.inputs['Vector'])

        ao_chan = ao_info.get('channel', 'FULL')
        if settings:
            settings.ao_channel = ao_chan
            settings.ao_strength = ao_info.get('strength', 1.0)
            settings.invert_ao = ao_info.get('invert', False)

        src_ao = ao_tex.outputs['Color'] if ao_chan in ('FULL', 'A') else None
        if ao_chan not in ('FULL', 'A'):
            ao_sep = nodes.get("AOSplit") or node_utils.create_separate_node(nodes, "AOSplit")
            ao_sep.name = "AOSplit"
            ao_sep.location = (-300, 450)
            sep_in = node_utils.get_separate_input_socket(ao_sep)
            if sep_in: links.new(ao_tex.outputs['Color'], sep_in)
            src_ao = node_utils.get_separate_output_socket(ao_sep, ao_chan)

        ao_add = nodes.get("AOAdd") or nodes.new('ShaderNodeMath')
        ao_add.name = "AOAdd"
        ao_add.label = "AO Strength"
        ao_add.operation = 'ADD'
        ao_add.use_clamp = True
        ao_add.location = (-150, 450)
        str_val = settings.ao_strength if settings else 1.0
        ao_add.inputs[1].default_value = 1.0 - str_val
        if src_ao: links.new(src_ao, ao_add.inputs[0])

        ao_mix = nodes.get("AOMix") or node_utils.create_mix_rgba_node(nodes, "AOMix", 'MULTIPLY')
        ao_mix.name = "AOMix"
        ao_mix.label = "AO Multiply"
        ao_mix.location = (50, 350)
        if 'Factor' in ao_mix.inputs: ao_mix.inputs['Factor'].default_value = 1.0
        
        ao_a = node_utils.get_mix_a_socket(ao_mix)
        ao_b = node_utils.get_mix_b_socket(ao_mix)
        
        # Link A to Base Color source (tint mix or previous input)
        if bc_sock.is_linked:
            curr_link = bc_sock.links[0]
            curr_src = curr_link.from_socket
            links.remove(curr_link)
            if ao_a: links.new(curr_src, ao_a)
        else:
            if ao_a: ao_a.default_value = bc_sock.default_value

        if ao_b: links.new(ao_add.outputs['Value'], ao_b)
        
        ao_out = node_utils.get_mix_output_socket(ao_mix)
        if ao_out: links.new(ao_out, bc_sock)
        safe_remove_nodes(ao_info.get('nodes_in_chain', set()) - {ao_tex})

    # 4. Roughness
    if 'Roughness' in conv:
        r_info = conv['Roughness']
        r_sock = principled.inputs['Roughness']
        for l in list(r_sock.links): links.remove(l)

        if r_info.get('type') == 'CONSTANT':
            r_sock.default_value = r_info.get('strength', 0.5)
            settings.roughness_strength = r_info.get('strength', 0.5)
        elif r_info.get('image'):
            r_tex = nodes.get("RoughnessTex") or nodes.new('ShaderNodeTexImage')
            r_tex.name = "RoughnessTex"
            r_tex.label = "Roughness Texture"
            r_tex.image = r_info['image']
            r_tex.image.colorspace_settings.name = 'Non-Color'
            r_tex.location = (-450, 50)
            links.new(mapping.outputs['Vector'], r_tex.inputs['Vector'])

            chan = r_info.get('channel', 'FULL')
            settings.roughness_channel = chan
            settings.roughness_strength = r_info.get('strength', 1.0)
            settings.invert_roughness = r_info.get('invert', False)

            src_r = r_tex.outputs['Color'] if chan == 'FULL' else (r_tex.outputs['Alpha'] if chan == 'A' else None)
            if chan not in ('FULL', 'A'):
                r_sep = nodes.get("RoughnessSplit") or node_utils.create_separate_node(nodes, "RoughnessSplit")
                r_sep.name = "RoughnessSplit"
                r_sep.location = (-280, 50)
                sep_in = node_utils.get_separate_input_socket(r_sep)
                if sep_in: links.new(r_tex.outputs['Color'], sep_in)
                src_r = node_utils.get_separate_output_socket(r_sep, chan)

            if settings.invert_roughness:
                r_inv = nodes.get("RoughnessInvert") or node_utils.create_invert_node(nodes, "RoughnessInvert")
                r_inv.name = "RoughnessInvert"
                r_inv.location = (-150, 50)
                inv_in = node_utils.get_invert_input_socket(r_inv)
                if inv_in and src_r: links.new(src_r, inv_in)
                src_r = node_utils.get_invert_output_socket(r_inv)

            r_math = nodes.get("RoughnessMath") or nodes.new('ShaderNodeMath')
            r_math.name = "RoughnessMath"
            r_math.label = "Roughness Strength"
            r_math.operation = 'MULTIPLY'
            r_math.use_clamp = True
            r_math.location = (-20, 50)
            r_math.inputs[1].default_value = settings.roughness_strength
            if src_r: links.new(src_r, r_math.inputs[0])
            links.new(r_math.outputs['Value'], r_sock)

            safe_remove_nodes(r_info.get('nodes_in_chain', set()) - {r_tex})

    # 5. Metallic
    if 'Metallic' in conv:
        m_info = conv['Metallic']
        m_sock = principled.inputs['Metallic']
        for l in list(m_sock.links): links.remove(l)

        if m_info.get('type') == 'CONSTANT':
            m_sock.default_value = m_info.get('strength', 0.0)
            settings.metallic_strength = m_info.get('strength', 0.0)
        elif m_info.get('image'):
            m_tex = nodes.get("MetallicTex") or nodes.new('ShaderNodeTexImage')
            m_tex.name = "MetallicTex"
            m_tex.label = "Metallic Texture"
            m_tex.image = m_info['image']
            m_tex.image.colorspace_settings.name = 'Non-Color'
            m_tex.location = (-450, -150)
            links.new(mapping.outputs['Vector'], m_tex.inputs['Vector'])

            chan = m_info.get('channel', 'FULL')
            settings.metallic_channel = chan
            settings.metallic_strength = m_info.get('strength', 1.0)
            settings.invert_metallic = m_info.get('invert', False)

            src_m = m_tex.outputs['Color'] if chan == 'FULL' else (m_tex.outputs['Alpha'] if chan == 'A' else None)
            if chan not in ('FULL', 'A'):
                m_sep = nodes.get("MetallicSplit") or node_utils.create_separate_node(nodes, "MetallicSplit")
                m_sep.name = "MetallicSplit"
                m_sep.location = (-280, -150)
                sep_in = node_utils.get_separate_input_socket(m_sep)
                if sep_in: links.new(m_tex.outputs['Color'], sep_in)
                src_m = node_utils.get_separate_output_socket(m_sep, chan)

            if settings.invert_metallic:
                m_inv = nodes.get("MetallicInvert") or node_utils.create_invert_node(nodes, "MetallicInvert")
                m_inv.name = "MetallicInvert"
                m_inv.location = (-150, -150)
                inv_in = node_utils.get_invert_input_socket(m_inv)
                if inv_in and src_m: links.new(src_m, inv_in)
                src_m = node_utils.get_invert_output_socket(m_inv)

            m_math = nodes.get("MetallicMath") or nodes.new('ShaderNodeMath')
            m_math.name = "MetallicMath"
            m_math.label = "Metallic Strength"
            m_math.operation = 'MULTIPLY'
            m_math.use_clamp = True
            m_math.location = (-20, -150)
            m_math.inputs[1].default_value = settings.metallic_strength
            if src_m: links.new(src_m, m_math.inputs[0])
            links.new(m_math.outputs['Value'], m_sock)

            safe_remove_nodes(m_info.get('nodes_in_chain', set()) - {m_tex})

    # 6. Normal
    if 'Normal' in conv:
        n_info = conv['Normal']
        n_sock = principled.inputs['Normal']
        for l in list(n_sock.links): links.remove(l)

        n_tex = nodes.get("NormalTex") or nodes.new('ShaderNodeTexImage')
        n_tex.name = "NormalTex"
        n_tex.label = "Normal Texture"
        n_tex.image = n_info['image']
        n_tex.image.colorspace_settings.name = 'Non-Color'
        n_tex.location = (-450, -350)
        links.new(mapping.outputs['Vector'], n_tex.inputs['Vector'])

        nm_node = nodes.get("NormalMap") or nodes.new('ShaderNodeNormalMap')
        nm_node.name = "NormalMap"
        nm_node.label = "Normal Map Node"
        nm_node.location = (-150, -350)
        if 'Strength' in nm_node.inputs:
            nm_node.inputs['Strength'].default_value = n_info.get('strength', 1.0)
        links.new(nm_node.outputs['Normal'], n_sock)

        settings.flip_normal_g = n_info.get('flip_normal_g', False)
        if settings.flip_normal_g:
            sep = nodes.get("NormalSplit") or node_utils.create_separate_node(nodes, "NormalSplit")
            sep.name = "NormalSplit"
            sep.location = (-350, -350)
            inv = nodes.get("NormalInvertG") or nodes.new('ShaderNodeMath')
            inv.name = "NormalInvertG"
            inv.operation = 'SUBTRACT'
            inv.inputs[0].default_value = 1.0
            inv.location = (-250, -420)
            com = nodes.get("NormalCombine") or node_utils.create_combine_node(nodes, "NormalCombine")
            com.name = "NormalCombine"
            com.location = (-150, -350)

            sep_in = node_utils.get_separate_input_socket(sep)
            if sep_in: links.new(n_tex.outputs['Color'], sep_in)
            sep_r = node_utils.get_separate_output_socket(sep, 'R')
            sep_g = node_utils.get_separate_output_socket(sep, 'G')
            sep_b = node_utils.get_separate_output_socket(sep, 'B')
            com_r = node_utils.get_combine_input_socket(com, 'R')
            com_g = node_utils.get_combine_input_socket(com, 'G')
            com_b = node_utils.get_combine_input_socket(com, 'B')
            com_out = node_utils.get_combine_output_socket(com)
            if sep_r and com_r: links.new(sep_r, com_r)
            if sep_g: links.new(sep_g, inv.inputs[1])
            if com_g: links.new(inv.outputs['Value'], com_g)
            if sep_b and com_b: links.new(sep_b, com_b)
            if com_out: links.new(com_out, nm_node.inputs['Color'])
        else:
            links.new(n_tex.outputs['Color'], nm_node.inputs['Color'])

        safe_remove_nodes(n_info.get('nodes_in_chain', set()) - {n_tex, nm_node})

    # 7. Alpha
    if 'Alpha' in conv:
        a_info = conv['Alpha']
        a_sock = principled.inputs['Alpha']
        for l in list(a_sock.links): links.remove(l)

        if a_info.get('type') == 'CONSTANT':
            a_sock.default_value = a_info.get('strength', 1.0)
            settings.alpha_strength = a_info.get('strength', 1.0)
        elif a_info.get('image'):
            settings.use_separate_alpha_map = a_info.get('use_separate_alpha', False)
            settings.alpha_strength = a_info.get('strength', 1.0)
            settings.use_alpha_clip = a_info.get('is_clip', False)
            settings.alpha_threshold = a_info.get('threshold', 0.5)

            if settings.use_separate_alpha_map:
                a_tex = nodes.get("AlphaTex") or nodes.new('ShaderNodeTexImage')
                a_tex.name = "AlphaTex"
                a_tex.label = "Alpha Texture"
                a_tex.image = a_info['image']
                a_tex.image.colorspace_settings.name = 'Non-Color'
                a_tex.location = (-450, -550)
                links.new(mapping.outputs['Vector'], a_tex.inputs['Vector'])
                src_a = a_tex.outputs['Color']
                material.blend_method = 'BLEND'
            else:
                base_tex = nodes.get("BaseTex")
                src_a = base_tex.outputs['Alpha'] if base_tex else None
                material.blend_method = 'HASHED'

            if src_a:
                a_math = nodes.get("AlphaMath") or nodes.new('ShaderNodeMath')
                a_math.name = "AlphaMath"
                a_math.label = "Alpha Strength"
                a_math.operation = 'MULTIPLY'
                a_math.use_clamp = True
                a_math.location = (-200, -550)
                a_math.inputs[1].default_value = settings.alpha_strength
                links.new(src_a, a_math.inputs[0])

                if settings.use_alpha_clip:
                    a_clip = nodes.get("AlphaClip") or nodes.new('ShaderNodeMath')
                    a_clip.name = "AlphaClip"
                    a_clip.label = "Alpha Clip"
                    a_clip.operation = 'GREATER_THAN'
                    a_clip.location = (-50, -550)
                    a_clip.inputs[1].default_value = settings.alpha_threshold
                    links.new(a_math.outputs['Value'], a_clip.inputs[0])
                    links.new(a_clip.outputs['Value'], a_sock)
                else:
                    links.new(a_math.outputs['Value'], a_sock)

            safe_remove_nodes(a_info.get('nodes_in_chain', set()))

    # 8. Emission
    if 'Emission' in conv:
        em_info = conv['Emission']
        em_sock = principled.inputs.get('Emission Color') or principled.inputs.get('Emission')
        em_str_sock = principled.inputs.get('Emission Strength')
        
        if em_sock:
            for l in list(em_sock.links): links.remove(l)
            if em_info.get('type') == 'CONSTANT':
                if 'value' in em_info and em_info['value']:
                    em_sock.default_value = em_info['value']
                if em_str_sock:
                    em_str_sock.default_value = em_info.get('strength', 1.0)
                settings.emission_strength = em_info.get('strength', 1.0)
            elif em_info.get('image'):
                em_tex = nodes.get("EmissionTex") or nodes.new('ShaderNodeTexImage')
                em_tex.name = "EmissionTex"
                em_tex.label = "Emission Texture"
                em_tex.image = em_info['image']
                em_tex.image.colorspace_settings.name = 'sRGB'
                em_tex.location = (-450, 650)
                links.new(mapping.outputs['Vector'], em_tex.inputs['Vector'])

                em_mix = nodes.get("EmissionTintMix") or node_utils.create_mix_rgba_node(nodes, "EmissionTintMix", 'MULTIPLY')
                em_mix.name = "EmissionTintMix"
                em_mix.label = "Emission Tint"
                em_mix.location = (-180, 650)
                if 'Factor' in em_mix.inputs: em_mix.inputs['Factor'].default_value = 1.0
                
                em_a = node_utils.get_mix_a_socket(em_mix)
                em_b = node_utils.get_mix_b_socket(em_mix)
                if em_a: links.new(em_tex.outputs['Color'], em_a)
                if em_b: em_b.default_value = em_info.get('tint', (1.0, 1.0, 1.0, 1.0))
                
                em_out = node_utils.get_mix_output_socket(em_mix)
                if em_out: links.new(em_out, em_sock)
                if em_str_sock:
                    em_str_sock.default_value = em_info.get('strength', 1.0)
                settings.emission_strength = em_info.get('strength', 1.0)

                safe_remove_nodes(em_info.get('nodes_in_chain', set()) - {em_tex})

    # 9. Height / Displacement
    if 'Height' in conv:
        h_info = conv['Height']
        disp_sock = output_node.inputs.get('Displacement')
        if disp_sock:
            for l in list(disp_sock.links): links.remove(l)
            h_tex = nodes.get("HeightTex") or nodes.new('ShaderNodeTexImage')
            h_tex.name = "HeightTex"
            h_tex.label = "Height Texture"
            h_tex.image = h_info['image']
            h_tex.image.colorspace_settings.name = 'Non-Color'
            h_tex.location = (-450, -750)
            links.new(mapping.outputs['Vector'], h_tex.inputs['Vector'])

            h_disp = nodes.get("HeightDisplace") or nodes.new('ShaderNodeDisplacement')
            h_disp.name = "HeightDisplace"
            h_disp.label = "Height Displacement"
            h_disp.location = (-150, -750)
            h_disp.inputs['Scale'].default_value = h_info.get('strength', 0.1)
            settings.height_strength = h_info.get('strength', 0.1)
            links.new(h_tex.outputs['Color'], h_disp.inputs['Height'])
            links.new(h_disp.outputs['Displacement'], disp_sock)

            safe_remove_nodes(h_info.get('nodes_in_chain', set()) - {h_tex, h_disp})

    # 10. Unconvertible Nodes Retention (Partial Conversion)
    if unconv_nodes:
        for unode in unconv_nodes:
            if unode.location.y < 800 and unode.location.y > -800:
                unode.location.y += 850

    # 11. Run Auto Layout / Arrange Nodes
    try:
        bpy.ops.pbr.arrange_nodes()
    except Exception:
        pass

    return True

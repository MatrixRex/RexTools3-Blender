# core/node_utils.py
import bpy


def create_separate_node(nodes, name=None):
    """Create ShaderNodeSeparateColor (Blender 3.3+) or ShaderNodeSeparateRGB (Blender < 3.3)."""
    try:
        node = nodes.new('ShaderNodeSeparateColor')
    except (KeyError, RuntimeError):
        node = nodes.new('ShaderNodeSeparateRGB')
    if name:
        node.name = name
    return node


def create_combine_node(nodes, name=None):
    """Create ShaderNodeCombineColor (Blender 3.3+) or ShaderNodeCombineRGB (Blender < 3.3)."""
    try:
        node = nodes.new('ShaderNodeCombineColor')
    except (KeyError, RuntimeError):
        node = nodes.new('ShaderNodeCombineRGB')
    if name:
        node.name = name
    return node


def create_invert_node(nodes, name=None):
    """Create ShaderNodeInvertColor (Blender 4.0+) or ShaderNodeInvert (Blender < 4.0)."""
    try:
        node = nodes.new('ShaderNodeInvertColor')
    except (KeyError, RuntimeError):
        node = nodes.new('ShaderNodeInvert')
    if name:
        node.name = name
    return node


def get_separate_input_socket(sep_node):
    """Get the input image/color socket of a separate node across Blender versions."""
    if not sep_node:
        return None
    return sep_node.inputs.get('Color') or sep_node.inputs.get('Image') or (sep_node.inputs[0] if sep_node.inputs else None)


def get_separate_output_socket(sep_node, channel):
    """Get output socket (R, G, B, A) of a separate node across Blender versions."""
    if not sep_node:
        return None
    ch_upper = str(channel).upper()

    if ch_upper in ('R', 'RED'):
        return sep_node.outputs.get('Red') or sep_node.outputs.get('R') or (sep_node.outputs[0] if len(sep_node.outputs) > 0 else None)
    elif ch_upper in ('G', 'GREEN'):
        return sep_node.outputs.get('Green') or sep_node.outputs.get('G') or (sep_node.outputs[1] if len(sep_node.outputs) > 1 else None)
    elif ch_upper in ('B', 'BLUE'):
        return sep_node.outputs.get('Blue') or sep_node.outputs.get('B') or (sep_node.outputs[2] if len(sep_node.outputs) > 2 else None)
    elif ch_upper in ('A', 'ALPHA'):
        return sep_node.outputs.get('Alpha') or sep_node.outputs.get('A') or (sep_node.outputs[3] if len(sep_node.outputs) > 3 else None)

    idx = {'R': 0, 'G': 1, 'B': 2, 'A': 3}.get(ch_upper)
    if idx is not None and idx < len(sep_node.outputs):
        return sep_node.outputs[idx]
    return sep_node.outputs.get(channel) or (sep_node.outputs[0] if sep_node.outputs else None)


def get_combine_input_socket(com_node, channel):
    """Get input socket (R, G, B, A) of a combine node across Blender versions."""
    if not com_node:
        return None
    ch_upper = str(channel).upper()

    if ch_upper in ('R', 'RED'):
        return com_node.inputs.get('Red') or com_node.inputs.get('R') or (com_node.inputs[0] if len(com_node.inputs) > 0 else None)
    elif ch_upper in ('G', 'GREEN'):
        return com_node.inputs.get('Green') or com_node.inputs.get('G') or (com_node.inputs[1] if len(com_node.inputs) > 1 else None)
    elif ch_upper in ('B', 'BLUE'):
        return com_node.inputs.get('Blue') or com_node.inputs.get('B') or (com_node.inputs[2] if len(com_node.inputs) > 2 else None)
    elif ch_upper in ('A', 'ALPHA'):
        return com_node.inputs.get('Alpha') or com_node.inputs.get('A') or (com_node.inputs[3] if len(com_node.inputs) > 3 else None)

    idx = {'R': 0, 'G': 1, 'B': 2, 'A': 3}.get(ch_upper)
    if idx is not None and idx < len(com_node.inputs):
        return com_node.inputs[idx]
    return com_node.inputs.get(channel) or (com_node.inputs[0] if com_node.inputs else None)


def get_combine_output_socket(com_node):
    """Get output color socket of a combine node across Blender versions."""
    if not com_node:
        return None
    return com_node.outputs.get('Color') or com_node.outputs.get('Image') or (com_node.outputs[0] if com_node.outputs else None)


def get_invert_input_socket(inv_node):
    """Get color input socket of an invert node across Blender versions."""
    if not inv_node:
        return None
    return inv_node.inputs.get('Color') or inv_node.inputs.get('Image') or (inv_node.inputs[1] if len(inv_node.inputs) > 1 else inv_node.inputs[0])


def get_invert_output_socket(inv_node):
    """Get color output socket of an invert node across Blender versions."""
    if not inv_node:
        return None
    return inv_node.outputs.get('Color') or (inv_node.outputs[0] if inv_node.outputs else None)


def create_mix_rgba_node(nodes, name=None, blend_type='MULTIPLY'):
    """Create ShaderNodeMix with RGBA data_type (Blender 3.4+) or ShaderNodeMixRGB (older)."""
    try:
        node = nodes.new('ShaderNodeMix')
        node.data_type = 'RGBA'
    except Exception:
        node = nodes.new('ShaderNodeMixRGB')
    node.blend_type = blend_type
    if name:
        node.name = name
    return node


def get_mix_a_socket(node):
    """Get first input socket (A / Color1) of a mix node across Blender versions."""
    if not node:
        return None
    return node.inputs.get('A') or node.inputs.get('Color1') or (node.inputs[1] if len(node.inputs) > 1 else None)


def get_mix_b_socket(node):
    """Get second input socket (B / Color2) of a mix node across Blender versions."""
    if not node:
        return None
    return node.inputs.get('B') or node.inputs.get('Color2') or (node.inputs[2] if len(node.inputs) > 2 else None)


def get_mix_output_socket(node):
    """Get output socket (Result / Color) of a mix node across Blender versions."""
    if not node:
        return None
    return node.outputs.get('Result') or node.outputs.get('Color') or (node.outputs[0] if node.outputs else None)

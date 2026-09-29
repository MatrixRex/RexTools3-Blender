# operators/pbr_remove.py
import bpy
from bpy.types import Operator
from bpy.props import StringProperty

SHARED_PBR_NODES = {
    'PBRTexCoord', 'PBRMapping',
    'BaseTintMix', 'AOMix', 'EmissionTintMix',
    'RoughnessMath', 'MetallicMath', 'NormalMap', 'AlphaMath', 'AlphaClip', 'HeightDisplace'
}


def _is_protected_node(node, input_name=None):
    if not node:
        return True
    if node.type in ('BSDF_PRINCIPLED', 'OUTPUT_MATERIAL', 'MAPPING', 'TEX_COORD'):
        return True
    if node.name in ('PBRTexCoord', 'PBRMapping'):
        return True
    # If deleting a specific slot texture, don't cascade into mix/math nodes of other slots
    if input_name and node.name in SHARED_PBR_NODES:
        expected_prefix = input_name.replace(" ", "")
        if not node.name.startswith(expected_prefix) and node.name not in (f"{expected_prefix}Math", f"{expected_prefix}TintMix"):
            return True
    return False


class PBR_OT_RemoveTexture(Operator):
    bl_idname = "pbr.remove_texture"
    bl_label = "Remove Texture"
    bl_options = {'REGISTER', 'UNDO'}

    input_name: StringProperty()

    def execute(self, context):
        # Clear debug preview if active
        bpy.ops.pbr.clear_debug_preview()

        obj = context.active_object
        if not obj or not obj.active_material:
            self.report({'WARNING'}, "No active material")
            return {'CANCELLED'}

        mat = obj.active_material
        mat.use_nodes = True
        node_tree = mat.node_tree
        nodes = node_tree.nodes
        links = node_tree.links

        # Find Principled BSDF
        principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not principled:
            self.report({'WARNING'}, "No Principled BSDF found")
            return {'CANCELLED'}

        if self.input_name == 'AO':
            # AO is special: it's a Mix node in the Base Color chain
            ao_mix = nodes.get("AOMix")
            if ao_mix:
                # Modern Mix node: Output is 'Result', Input chain is 'A'
                out_sock = ao_mix.outputs.get('Result') or ao_mix.outputs[0]
                a_sock = ao_mix.inputs.get('A') or ao_mix.inputs[1] 
                b_sock = ao_mix.inputs.get('B') or ao_mix.inputs[2]
                
                out_links = list(out_sock.links) if out_sock else []
                a_links = list(a_sock.links) if a_sock else []
                
                # Reconnect A directly to the target (BSDF)
                if a_links and out_links:
                    upstream_socket = a_links[0].from_socket
                    for link in out_links:
                        links.new(upstream_socket, link.to_socket)
                
                # Now remove the AO chain (Mix node + anything behind B)
                to_remove = {ao_mix}
                if b_sock and b_sock.is_linked:
                    # Gather AO texture and helper nodes, protecting mapping/texcoord/bsdf
                    def gather_local(node, out):
                        if not node or node in out or _is_protected_node(node, 'AO'):
                            return
                        out.add(node)
                        for i in node.inputs:
                            if i.is_linked:
                                gather_local(i.links[0].from_node, out)
                    
                    gather_local(b_sock.links[0].from_node, to_remove)
                
                # Clean up specifically named helper nodes if they weren't caught
                for name in ["AOSplit", "AOAdd", "AOMath"]:
                    node = nodes.get(name)
                    if node: to_remove.add(node)

                for node in to_remove:
                    try: nodes.remove(node)
                    except: pass
            return {'FINISHED'}

        if self.input_name == 'Height':
            # Remove displacement setup
            mat_out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if mat_out:
                disp_inp = mat_out.inputs.get('Displacement')
                for link in list(disp_inp.links):
                    links.remove(link)
            for name in ["HeightDisplace", "HeightTex"]:
                node = nodes.get(name)
                if node:
                    try: nodes.remove(node)
                    except: pass
            return {'FINISHED'}

        if self.input_name == 'Emission':
            inp_socket = principled.inputs.get('Emission Color')
        else:
            inp_socket = principled.inputs.get(self.input_name)

        if not inp_socket or not inp_socket.is_linked:
            return {'FINISHED'}

        # Recursively gather all nodes feeding into this socket, protecting shared infrastructure
        to_del = set()
        def gather_rec(node):
            if not node or node in to_del or _is_protected_node(node, self.input_name):
                return
            to_del.add(node)
            for inp in node.inputs:
                if inp.is_linked:
                    upstream = inp.links[0].from_node
                    gather_rec(upstream)

        # Start gathering from the node linked into this socket
        first_node = inp_socket.links[0].from_node
        gather_rec(first_node)

        # Unlink the BSDF socket
        for link in list(inp_socket.links):
            links.remove(link)

        # Delete all gathered nodes, ignoring any that are gone already
        for node in to_del:
            try:
                nodes.remove(node)
            except RuntimeError:
                pass

        # ─── Cleanup any leftover channel-packing nodes ───────────────────
        # Remove our named SeparateRGB and Math nodes if they remain
        leftover_names = [f"{self.input_name}Split", f"{self.input_name}Math", "EmissionTintMix"]
        if self.input_name == 'Normal':
            leftover_names.extend(["NormalInvertG", "NormalCombine"])
        if self.input_name == 'Alpha':
            leftover_names.append("AlphaClip")
            
        for node_name in leftover_names:
            leftover = nodes.get(node_name)
            if leftover:
                try:
                    nodes.remove(leftover)
                except RuntimeError:
                    pass

        return {'FINISHED'}

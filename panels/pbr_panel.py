import bpy
from bpy.types import Panel

# Define the panel class
class PBR_PT_MaterialPanel(Panel):
    bl_label = "Easy PBR"
    bl_idname = "PBR_PT_material_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_category = "PBR Tools"  # This ensures the panel appears under the "PBR Tools" tab

    def find_texture_node(self, node):
        """Finds the first Image Texture node in the chain starting from node."""
        visited = set()
        current = node
        while current and current not in visited:
            visited.add(current)
            if current.type == 'TEX_IMAGE':
                return current
            
            # Follow the first linked input, prioritizing common texture inputs
            next_node = None
            for name in ['Color', 'Color1', 'Value', 'Image']:
                inp = current.inputs.get(name)
                if inp and inp.is_linked:
                    next_node = inp.links[0].from_node
                    break
            
            if not next_node:
                for inp in current.inputs:
                    if inp.is_linked:
                        next_node = inp.links[0].from_node
                        break
            current = next_node
        return None

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if not obj:
            layout.label(text="No active object")
            return

        mat = obj.active_material
        if not mat:
            layout.operator("pbr.create_material", icon='ADD')
            return

        # Header
        row = layout.row(align=True)
        row.prop(mat, "name", text="Material")
        row.prop(mat.pbr_settings, "use_packed_mode", text="Packing Mode", icon='PACKAGE', toggle=True)
        
        
        layout.separator()

        # Ensure nodes
        if not mat.use_nodes:
            layout.operator("pbr.create_material", text="Enable Nodes", icon='NODETREE')
            return

        nodes = mat.node_tree.nodes
        principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not principled:
            layout.label(text="No Principled BSDF found")
            layout.operator("pbr.create_material", text="Setup PBR Material", icon='MATERIAL')
            return

        # Auto Load Tools (Boxed)
        al_box = layout.box()
        al_box.label(text="Texture Auto Loader", icon='FILE_REFRESH')
        
        row = al_box.row(align=True)
        row.operator("pbr.auto_load_textures", text="Auto Load", icon='FILE_REFRESH')
        row.prop(mat.pbr_settings, "use_auto_common_name", text="Auto-Detect", toggle=True)
        
        if not mat.pbr_settings.use_auto_common_name:
            al_box.prop(mat.pbr_settings, "common_name", text="Common Name")

        layout.separator()

        # Packing Mode Active Alert
        if mat.pbr_settings.use_packed_mode:
            pbox = layout.box()
            pbox.prop(mat.pbr_settings, "use_packed_mode", text="PACKING MODE ACTIVE", icon='PACKAGE', toggle=True)
            layout.separator()

        # Debug Preview Active Alert
        if mat.pbr_settings.debug_preview_mode != 'OFF':
            box = layout.box()
            box.alert = True
            row = box.row()
            row.label(text=f"DEBUG PREVIEW: {mat.pbr_settings.debug_preview_slot} ({mat.pbr_settings.debug_preview_mode.title()})", icon='VIEWZOOM')
            row.operator("pbr.clear_debug_preview", text="Clear", icon='X')
            layout.separator()

        # Build our list of sockets
        inputs = [
            ("Base Color", "Base Color", "sRGB"),
            ("Normal",     "Normal",     "Non-Color"),
            ("Roughness",  "Roughness",  "Non-Color"),
            ("Metallic",   "Metallic",   "Non-Color"),
            ("Emission",   "Emission",   "sRGB"),
        ]
        if mat.pbr_settings.use_separate_alpha_map:
            inputs.append(("Alpha", "Alpha", "Non-Color"))
        
        # Add AO slot (custom logic since it's not a Principled BSDF input)
        # We append a special identifier to handle it in the draw loop
        inputs.append(("AO", "AO", "Non-Color"))

        # Draw each socket block
        for label, socket, colorspace in inputs:
            # Highlight active preview
            is_preview = (mat.pbr_settings.debug_preview_slot == label and mat.pbr_settings.debug_preview_mode != 'OFF')
            
            box = layout.box()
            if is_preview:
                box.alert = True
                
            # ─── Slot Header Row (Boxed) ───
            hdr_box = box.box()
            hdr = hdr_box.row(align=True)
            hdr.label(text=label)
            
            linked = False
            src_node = None
            
            # ... (AO and Emission logic remains same) ...
            if socket == "AO":
                # AO is special: check for AOMix node
                ao_mix = nodes.get("AOMix")
                bc_inp = principled.inputs.get("Base Color")
                if ao_mix and bc_inp and bc_inp.is_linked:
                    # Check if AOMix is in the chain starting from BSDF
                    curr = bc_inp.links[0].from_node
                    while curr:
                        if curr == ao_mix:
                            linked = True
                            # AO texture is connected to 'B'
                            b_sock = curr.inputs.get('B') or curr.inputs[2]
                            if b_sock and b_sock.is_linked:
                                src_node = b_sock.links[0].from_node
                            break
                        
                        # Move backwards through 'A' slot
                        a_sock = curr.inputs.get('A') or curr.inputs.get('Color1')
                        curr = a_sock.links[0].from_node if a_sock and a_sock.is_linked else None
            elif socket == "Emission":
                em_inp = principled.inputs.get("Emission Color")
                if em_inp and em_inp.is_linked:
                    linked = True
                    curr = em_inp.links[0].from_node
                    if curr.name == "EmissionTintMix":
                        # Texture is behind the tint mix
                        a_sock = curr.inputs.get('A') or curr.inputs.get('Color1')
                        if a_sock and a_sock.is_linked:
                            src_node = a_sock.links[0].from_node
                    else:
                        src_node = curr
            else:
                inp = principled.inputs.get(socket)
                if not inp:
                    continue
                if inp.is_linked:
                    # Specific check for Base Color to avoid picking up AO texture
                    if socket == "Base Color":
                        # Look for BaseTex or BaseTintMix
                        curr = inp.links[0].from_node
                        while curr:
                            if curr.name == "BaseTex":
                                linked = True
                                src_node = curr
                                break
                            if curr.name == "BaseTintMix":
                                a_sock = curr.inputs.get('A') or curr.inputs.get('Color1')
                                if a_sock and a_sock.is_linked:
                                    # Behind the tint is either another mix (AO) or the texture
                                    curr = a_sock.links[0].from_node
                                    continue
                            if curr.name == "AOMix":
                                a_sock = curr.inputs.get('A') or curr.inputs.get('Color1')
                                if a_sock and a_sock.is_linked:
                                    curr = a_sock.links[0].from_node
                                    continue
                            # Fallback if no names match but we have a direct TexImage
                            if curr.type == 'TEX_IMAGE' and curr.name != "AOTex":
                                linked = True
                                src_node = curr
                                break
                            break
                    else:
                        linked = True
                        src_node = inp.links[0].from_node

            # If already linked, show remove + controls
            if linked:
                # Reassign and Remove buttons (Anchored Right in Header)
                head_ops = hdr.row(align=True)
                head_ops.alignment = 'RIGHT'
                
                re_op = head_ops.operator("pbr.assign_texture", text="", icon='FILE_REFRESH')
                re_op.input_name = socket
                re_op.colorspace = colorspace
                
                head_ops.alert = True
                head_ops.operator("pbr.remove_texture", text="", icon='TRASH').input_name = socket
                
                name = "Unknown"
                if src_node:
                    tex_node = self.find_texture_node(src_node)
                    if tex_node and tex_node.type == 'TEX_IMAGE':
                        name = tex_node.image.name if tex_node.image else "No Image"
                    else:
                        name = src_node.type.replace('_', ' ').title()
                
                # ─── Consolidated Content Row (Name | Channel | Debug) ───
                split = box.row(align=True).split(factor=0.6)
                split.label(text=name, icon='IMAGE_DATA')
                
                right_row = split.row(align=True)
                right_row.alignment = 'RIGHT'
                
                if socket not in ("Base Color", "Normal"):
                    right_row.prop(mat.pbr_settings, f"{socket.lower()}_channel", text="")
                
                # Debug Buttons
                d_op = right_row.operator("pbr.debug_preview", text="", icon='FORCE_TEXTURE', depress=(is_preview and mat.pbr_settings.debug_preview_mode == 'DIRECT'))
                d_op.slot = label
                d_op.mode = 'DIRECT'
                
                if label in ("Base Color", "Normal", "Emission"):
                    m_op = right_row.operator("pbr.debug_preview", text="", icon='NODE_MATERIAL', depress=(is_preview and mat.pbr_settings.debug_preview_mode == 'MIXED'))
                    m_op.slot = label
                    m_op.mode = 'MIXED'
                
                if is_preview:
                    right_row.operator("pbr.clear_debug_preview", text="", icon='X')

                # Per-socket extra controls
                if socket == "Base Color":
                    tint_node = nodes.get("BaseTintMix")
                    if tint_node:
                        r = box.row(align=True)
                        tint_sock = tint_node.inputs.get('B') or tint_node.inputs.get('Color2')
                        if tint_sock:
                            r.prop(tint_sock, "default_value", text="Tint")
                            r.operator("pbr.reset_tint", text="", icon='FILE_REFRESH').mode = 'BASE'

                elif socket == "Normal":
                    nm_node = nodes.get("NormalMap")
                    if nm_node:
                        box.prop(nm_node.inputs['Strength'], "default_value", text="Strength")
                    box.prop(mat.pbr_settings, "flip_normal_g", text="Flip Green (DirectX)", toggle=True)
                elif socket == "Emission":
                    tint_node = nodes.get("EmissionTintMix")
                    if tint_node:
                        r = box.row(align=True)
                        tint_sock = tint_node.inputs.get('B') or tint_node.inputs.get('Color2')
                        if tint_sock:
                            r.prop(tint_sock, "default_value", text="Tint")
                            r.operator("pbr.reset_tint", text="", icon='FILE_REFRESH').mode = 'EMISSION'
                    box.prop(mat.pbr_settings, "emission_strength", text="Strength")
                elif socket in ("Roughness", "Metallic", "AO", "Alpha"):
                    key = socket.lower() + "_strength"
                    r = box.row(align=True)
                    r.prop(mat.pbr_settings, key, text="Strength", slider=True)
                    if socket in ("Roughness", "Metallic", "AO"):
                        r.prop(mat.pbr_settings, f"invert_{socket.lower()}", text="", icon='IMAGE_ALPHA', toggle=True)

            # If not linked, show assign UI
            else:
                p_mode = mat.pbr_settings.use_packed_mode
                assign_text = "Assign (Packed)" if p_mode else "Assign"
                assign_icon = 'PACKAGE' if p_mode else 'FILEBROWSER'
                
                op = hdr.operator("pbr.assign_texture", text=assign_text, icon=assign_icon)
                op.input_name = socket
                op.colorspace = colorspace
                op.use_packed = p_mode

                if socket not in ("Normal", "AO"):
                    if socket == "Base Color":
                        r = box.row(align=True)
                        r.prop(principled.inputs['Base Color'], "default_value", text="Color")
                        r.operator("pbr.reset_tint", text="", icon='FILE_REFRESH').mode = 'BASE'
                    elif socket == "Emission":
                        r = box.row(align=True)
                        r.prop(principled.inputs['Emission Color'], "default_value", text="Color")
                        r.operator("pbr.reset_tint", text="", icon='FILE_REFRESH').mode = 'EMISSION'
                    else:
                        box.prop(principled.inputs[socket], "default_value", text="Value")



        # Material settings footer
        layout.separator()
        ms = layout.box()
        ms.label(text="Material Properties", icon='MATERIAL')
        
        # Moved Separate Alpha here
        ms.prop(mat.pbr_settings, "pbr_tiling", text="Tiling")
        ms.prop(mat.pbr_settings, "use_separate_alpha_map", text="Use Separate Alpha Map")
        
        row = ms.row(align=True)
        row.prop(mat.pbr_settings, "use_alpha_clip", text="Alpha Clip", toggle=True)
        if mat.pbr_settings.use_alpha_clip:
            row.prop(mat.pbr_settings, "alpha_threshold", text="Threshold")
        
        row = ms.row(align=True)
        row.label(text="Blend Mode")
        row.prop_enum(mat, "blend_method", 'BLEND',  text="Blend")
        row.prop_enum(mat, "blend_method", 'HASHED', text="Hashed")
        
        ms.prop(mat, "use_backface_culling", text="Backface Culling", toggle=True)

        layout.separator()
        





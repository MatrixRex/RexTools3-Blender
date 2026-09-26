import bpy
import bmesh
from bpy.types import Operator

from ..core import bmesh_selection as sel_core

addon_keymaps = []

# Forward helper names for compatibility if referenced locally or dynamically
are_edges_parallel = sel_core.are_edges_parallel
get_neighbour_verts = sel_core.get_neighbour_verts
get_neighbour_faces = sel_core.get_neighbour_faces
get_neighbour_edges = sel_core.get_neighbour_edges
get_bounded_selection = sel_core.get_bounded_selection
full_loop_vert_manifold = sel_core.full_loop_vert_manifold
full_loop_vert_boundary = sel_core.full_loop_vert_boundary
full_loop_vert_wire = sel_core.full_loop_vert_wire
full_loop_face = sel_core.full_loop_face
full_loop_edge_manifold = sel_core.full_loop_edge_manifold
full_ring_edge_manifold = sel_core.full_ring_edge_manifold
full_loop_edge_boundary = sel_core.full_loop_edge_boundary
full_loop_edge_wire = sel_core.full_loop_edge_wire


# --- Operator Definition ---

class REXTOOLS3_OT_ContextAwareSelect(Operator):
    """Context-aware selection: Linked select or Loop/Ring select with advanced pathfinding, triggered on double-click"""
    bl_idname = "rextools3.context_aware_select"
    bl_label = "Context Aware Select"
    bl_description = "Double-click to select linked or loops/rings/paths between elements"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        try:
            addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
            prefs = context.preferences.addons[addon_name].preferences
            if not prefs.enable_context_select:
                return False
        except Exception:
            pass
        return True

    # --- Properties ---

    # Linked Selection Properties
    delimit: bpy.props.EnumProperty(
        name="Delimit",
        description="Limit selection boundaries",
        options={'ENUM_FLAG'},
        items=(
            ('NORMAL', "Normal", "Delimit by face directions"),
            ('MATERIAL', "Material", "Delimit by face material"),
            ('SEAM', "Seam", "Delimit by edge seams"),
            ('SHARP', "Sharp", "Delimit by sharp edges"),
            ('UV', "UV", "Delimit by UV coordinates"),
        ),
        default=set(),
    )
    
    select_linked_on_double_click: bpy.props.BoolProperty(
        name="Select Linked On Double Click",
        description="Double clicking on a face or a vertex (if not part of a loop selection) will select all components for that contiguous mesh piece",
        default=True,
        options={'HIDDEN'}
    )

    # Loop/Ring / Bounded Pathfinding Selection Properties
    ring: bpy.props.BoolProperty(
        name="Ring Select",
        description="Select an edge ring instead of a loop",
        default=False,
    )
    
    allow_non_quads_at_ends: bpy.props.BoolProperty(
        name="Allow Non-Quads at Start/End of Face Loops",
        description="If a loop of faces terminates at a triangle or n-gon, allow that non-quad face to be added to the final loop selection, and allow using that non-quad face to begin a loop selection",
        default=True
    )
    
    terminate_self_intersects: bpy.props.BoolProperty(
        name="Terminate Self-Intersects",
        description="If a loop or ring of vertices, edges, or faces circles around and crosses over itself, stop the selection at that location",
        default=False
    )
    
    ignore_boundary_wires: bpy.props.BoolProperty(
        name="Ignore Wire Edges on Boundaries",
        description="If wire edges are attached to a boundary vertex the selection will ignore it, pass through, and continue selecting the boundary loop",
        default=False
    )
    
    leave_edge_active: bpy.props.BoolProperty(
        name="Leave Edge Active",
        description="When selecting edge loops or edge rings, the active edge will remain active",
        default=False
    )
    
    ignore_hidden_geometry: bpy.props.BoolProperty(
        name="Ignore Hidden Geometry",
        description="Loop selections will ignore hidden components and continue through to the other side",
        default=False
    )
    
    return_single_loop: bpy.props.BoolProperty(
        name="Select Single Bounded Loop",
        description="For bounded selections, if there are multiple equal-length paths between the start and end component, select only one loop instead of all possible loops",
        default=False
    )

    # Hidden properties to store clicked element indices across invoke/execute (needed for Redo)
    start_element_index: bpy.props.IntProperty(options={'HIDDEN'}, default=-1)
    end_element_index: bpy.props.IntProperty(options={'HIDDEN'}, default=-1)
    selection_type: bpy.props.StringProperty(options={'HIDDEN'}, default="")
    extend_selection: bpy.props.BoolProperty(options={'HIDDEN'}, default=False)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH':
            select_mode = context.tool_settings.mesh_select_mode
            if select_mode[0] or select_mode[2]:
                # Vertex or Face selection mode
                layout.prop(self, "delimit")
                if self.end_element_index != -1:
                    layout.separator()
                    layout.prop(self, "allow_non_quads_at_ends")
                    layout.prop(self, "terminate_self_intersects")
                    layout.prop(self, "ignore_hidden_geometry")
                    layout.prop(self, "return_single_loop")
            elif select_mode[1]:
                # Edge selection mode
                layout.prop(self, "ring")
                layout.prop(self, "leave_edge_active")
                layout.prop(self, "terminate_self_intersects")
                layout.prop(self, "ignore_boundary_wires")
                layout.prop(self, "ignore_hidden_geometry")
                layout.prop(self, "return_single_loop")

    def execute(self, context):
        obj = context.active_object
        if not obj:
            return {'CANCELLED'}

        if obj.type == 'MESH' and context.mode == 'EDIT_MESH':
            me = obj.data
            bm = bmesh.from_edit_mesh(me)

            # Ensure BMesh lookup tables are up-to-date
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            # If we don't extend selection, deselect all first (except we'll re-select start element)
            if not self.extend_selection:
                bpy.ops.mesh.select_all(action='DESELECT')

            # Fetch start and end elements by index
            start_element = None
            end_element = None

            if self.selection_type == 'VERT':
                if 0 <= self.start_element_index < len(bm.verts):
                    start_element = bm.verts[self.start_element_index]
                if 0 <= self.end_element_index < len(bm.verts):
                    end_element = bm.verts[self.end_element_index]
            elif self.selection_type == 'EDGE':
                if 0 <= self.start_element_index < len(bm.edges):
                    start_element = bm.edges[self.start_element_index]
                if 0 <= self.end_element_index < len(bm.edges):
                    end_element = bm.edges[self.end_element_index]
            elif self.selection_type == 'FACE':
                if 0 <= self.start_element_index < len(bm.faces):
                    start_element = bm.faces[self.start_element_index]
                if 0 <= self.end_element_index < len(bm.faces):
                    end_element = bm.faces[self.end_element_index]

            if not start_element:
                return {'CANCELLED'}

            # Ensure start_element is selected
            start_element.select = True

            new_sel = None

            if self.selection_type == 'VERT':
                if end_element and start_element.index != end_element.index:
                    adjacent = end_element in get_neighbour_verts(start_element)
                    if adjacent:
                        # Adjacent vertices selection
                        active_edge = [e for e in start_element.link_edges if e in end_element.link_edges][0]
                        if not (active_edge.hide and not self.ignore_hidden_geometry):
                            if active_edge.is_manifold:
                                new_sel = full_loop_vert_manifold(self, start_element, active_edge)
                            elif active_edge.is_boundary:
                                if start_element.is_manifold:
                                    new_sel = full_loop_vert_boundary(self, start_element)
                                elif end_element.is_manifold:
                                    new_sel = full_loop_vert_boundary(self, end_element)
                                else:
                                    new_sel = full_loop_vert_boundary(self, start_element)
                            elif active_edge.is_wire:
                                if start_element.is_wire:
                                    new_sel = full_loop_vert_wire(self, start_element)
                                elif end_element.is_wire:
                                    new_sel = full_loop_vert_wire(self, end_element)
                    else:
                        # Bounded selection pathfinder
                        new_sel = get_bounded_selection(self, start_element, end_element, mode='VERT')
                
                # Apply selection
                if new_sel:
                    for v in new_sel:
                        v.select = True
                elif not new_sel and self.select_linked_on_double_click:
                    # Select linked based on start element (users can alter delimiters in redo panel)
                    bpy.ops.mesh.select_linked(delimit=self.delimit)

                bm.select_history.add(start_element)
                bm.select_flush_mode()
                bmesh.update_edit_mesh(me)
                return {'FINISHED'}

            elif self.selection_type == 'FACE':
                if end_element and start_element.index != end_element.index:
                    # Check quad compatibility
                    if len(start_element.verts) != 4 and len(end_element.verts) != 4:
                        quads = (0, 0)
                    elif len(start_element.verts) == 4 and len(end_element.verts) == 4:
                        quads = (1, 1)
                    elif len(start_element.verts) == 4 and len(end_element.verts) != 4:
                        quads = (1, 0)
                    elif len(start_element.verts) != 4 and len(end_element.verts) == 4:
                        quads = (0, 1)

                    adjacent = end_element in get_neighbour_faces(start_element)
                    if adjacent and (quads == (1, 1) or self.allow_non_quads_at_ends):
                        ring_edge = [e for e in start_element.edges if e in end_element.edges][0]
                        new_sel = full_loop_face(self, ring_edge, start_element)
                    elif not adjacent and (quads == (1, 1) or self.allow_non_quads_at_ends):
                        new_sel = get_bounded_selection(self, start_element, end_element, mode='FACE')

                if new_sel:
                    for f in new_sel:
                        f.select = True
                elif not new_sel and self.select_linked_on_double_click:
                    bpy.ops.mesh.select_linked(delimit=self.delimit)

                bm.select_history.add(start_element)
                bm.select_flush_mode()
                bmesh.update_edit_mesh(me)
                return {'FINISHED'}

            elif self.selection_type == 'EDGE':
                # Shift+Double Click loop/ring/path selection
                if end_element and start_element.index != end_element.index:
                    adjacent = end_element in get_neighbour_edges(self, start_element)
                    if adjacent:
                        if any([v for v in start_element.verts if v in end_element.verts]):
                            # Connected edges (Loop)
                            if start_element.is_manifold:
                                new_sel = full_loop_edge_manifold(self, start_element)
                            elif start_element.is_boundary:
                                new_sel = full_loop_edge_boundary(self, start_element)
                            elif start_element.is_wire:
                                new_sel = full_loop_edge_wire(self, start_element)
                        else:
                            # Parallel edges (Ring)
                            if start_element.is_manifold:
                                new_sel = full_ring_edge_manifold(self, start_element)
                            else:
                                new_sel = full_ring_edge_manifold(self, end_element)
                    else:
                        # Bounded pathfinder
                        new_sel = get_bounded_selection(self, start_element, end_element, mode='EDGE')
                        if not new_sel:
                            # Fallback to full loop if no bounded path is found
                            if start_element.is_manifold:
                                new_sel = full_loop_edge_manifold(self, start_element)
                            elif start_element.is_boundary:
                                new_sel = full_loop_edge_boundary(self, start_element)
                            elif start_element.is_wire:
                                new_sel = full_loop_edge_wire(self, start_element)
                else:
                    # Regular Double Click (Edge Loop selection)
                    if start_element.is_manifold:
                        new_sel = full_loop_edge_manifold(self, start_element)
                    elif start_element.is_boundary:
                        new_sel = full_loop_edge_boundary(self, start_element)
                    elif start_element.is_wire:
                        new_sel = full_loop_edge_wire(self, start_element)

                if new_sel:
                    for e in new_sel:
                        e.select = True

                bm.select_history.clear()
                if self.leave_edge_active:
                    bm.select_history.add(start_element)
                bm.select_flush_mode()
                bmesh.update_edit_mesh(me)
                return {'FINISHED'}

        elif obj.type == 'CURVE' and context.mode == 'EDIT_CURVE':
            bpy.ops.curve.select_linked()
            return {'FINISHED'}

        return {'CANCELLED'}

    def invoke(self, context, event):
        # Pass through if any other modifier keys are held
        if event.ctrl or event.alt or event.oskey:
            return {'PASS_THROUGH'}

        obj = context.active_object
        if not obj:
            return {'PASS_THROUGH'}

        if obj.type == 'MESH' and context.mode == 'EDIT_MESH':
            select_mode = context.tool_settings.mesh_select_mode
            bm = bmesh.from_edit_mesh(obj.data)

            # Store modifier
            self.extend_selection = event.shift

            has_selection = False
            hist = list(bm.select_history)
            
            if select_mode[0]: # Vertex Selection
                self.selection_type = 'VERT'
                has_selection = any(v.select for v in bm.verts)
                v_hist = [h for h in hist if isinstance(h, bmesh.types.BMVert)]
                if len(v_hist) >= 1:
                    self.start_element_index = v_hist[-1].index
                    if event.shift and len(v_hist) >= 2:
                        self.end_element_index = v_hist[-2].index
                    else:
                        self.end_element_index = -1
                else:
                    self.start_element_index = -1
                    self.end_element_index = -1
                    
            elif select_mode[1]: # Edge Selection
                self.selection_type = 'EDGE'
                has_selection = any(e.select for e in bm.edges)
                e_hist = [h for h in hist if isinstance(h, bmesh.types.BMEdge)]
                if len(e_hist) >= 1:
                    self.start_element_index = e_hist[-1].index
                    if event.shift and len(e_hist) >= 2:
                        self.end_element_index = e_hist[-2].index
                        # Detect if the edges are parallel to set ring selection default
                        edge1 = e_hist[-1]
                        edge2 = e_hist[-2]
                        self.ring = are_edges_parallel(edge1, edge2)
                    else:
                        self.end_element_index = -1
                else:
                    self.start_element_index = -1
                    self.end_element_index = -1

            elif select_mode[2]: # Face Selection
                self.selection_type = 'FACE'
                has_selection = any(f.select for f in bm.faces)
                f_hist = [h for h in hist if isinstance(h, bmesh.types.BMFace)]
                if len(f_hist) >= 1:
                    self.start_element_index = f_hist[-1].index
                    if event.shift and len(f_hist) >= 2:
                        self.end_element_index = f_hist[-2].index
                    else:
                        self.end_element_index = -1
                else:
                    self.start_element_index = -1
                    self.end_element_index = -1

            # If no elements are selected or start element is invalid, pass through
            if not has_selection or self.start_element_index == -1:
                return {'PASS_THROUGH'}

            return self.execute(context)

        elif obj.type == 'CURVE' and context.mode == 'EDIT_CURVE':
            has_selection = False
            for spline in obj.data.splines:
                if any(p.select_control_point for p in spline.bezier_points) or any(p.select for p in spline.points):
                    has_selection = True
                    break

            if not has_selection:
                return {'PASS_THROUGH'}

            if event.shift:
                obj = context.active_object
                curve = obj.data
                selected_any = False
                for spline in curve.splines:
                    if spline.type == 'BEZIER':
                        selected_indices = [idx for idx, pt in enumerate(spline.bezier_points) if pt.select_control_point]
                        if len(selected_indices) >= 2:
                            start_idx = min(selected_indices)
                            end_idx = max(selected_indices)
                            count = len(spline.bezier_points)
                            
                            # If cyclic, check which path is shorter
                            if spline.use_cyclic_u and (end_idx - start_idx) > count // 2:
                                for idx in range(count):
                                    if idx <= start_idx or idx >= end_idx:
                                        spline.bezier_points[idx].select_control_point = True
                            else:
                                for idx in range(start_idx, end_idx + 1):
                                    spline.bezier_points[idx].select_control_point = True
                            selected_any = True
                    else: # NURBS / POLY
                        selected_indices = [idx for idx, pt in enumerate(spline.points) if pt.select]
                        if len(selected_indices) >= 2:
                            start_idx = min(selected_indices)
                            end_idx = max(selected_indices)
                            count = len(spline.points)
                            
                            if spline.use_cyclic_u and (end_idx - start_idx) > count // 2:
                                for idx in range(count):
                                    if idx <= start_idx or idx >= end_idx:
                                        spline.points[idx].select = True
                            else:
                                for idx in range(start_idx, end_idx + 1):
                                    spline.points[idx].select = True
                            selected_any = True
                
                if selected_any:
                    obj.data.update_tag()
                    # Force redraw of the viewport to reflect curve selection changes
                    context.area.tag_redraw()
                    return {'FINISHED'}
                else:
                    bpy.ops.curve.select_linked_pick('INVOKE_DEFAULT', deselect=False)
                    return {'FINISHED'}

            self.selection_type = 'CURVE'
            return self.execute(context)

        return {'PASS_THROUGH'}


def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        active_state = True
        try:
            addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
            prefs = bpy.context.preferences.addons[addon_name].preferences
            active_state = prefs.enable_context_select
        except Exception:
            pass

        # 1. Mesh Edit Mode Keymap
        km_mesh = kc.keymaps.get('Mesh')
        if not km_mesh:
            km_mesh = kc.keymaps.new(name='Mesh', space_type='EMPTY')

        kmi_mesh = km_mesh.keymap_items.new(
            REXTOOLS3_OT_ContextAwareSelect.bl_idname,
            type='LEFTMOUSE',
            value='DOUBLE_CLICK',
            any=True
        )
        kmi_mesh.active = active_state
        addon_keymaps.append((km_mesh, kmi_mesh))

        # 2. Curve Edit Mode Keymap
        km_curve = kc.keymaps.get('Curve')
        if not km_curve:
            km_curve = kc.keymaps.new(name='Curve', space_type='EMPTY')

        kmi_curve = km_curve.keymap_items.new(
            REXTOOLS3_OT_ContextAwareSelect.bl_idname,
            type='LEFTMOUSE',
            value='DOUBLE_CLICK',
            any=True
        )
        kmi_curve.active = active_state
        addon_keymaps.append((km_curve, kmi_curve))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

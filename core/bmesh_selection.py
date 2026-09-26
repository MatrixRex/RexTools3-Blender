import bpy
import bmesh

# --- Helper Functions adapted from Context Select (GPL-2.0-or-later) ---

def are_edges_parallel(edge1, edge2):
    # If they share a vertex, they are connected, so not parallel
    if any(v in edge2.verts for v in edge1.verts):
        return False
        
    # Check if they share a quad face and are opposite
    shared_faces = [f for f in edge1.link_faces if f in edge2.link_faces]
    for f in shared_faces:
        if len(f.edges) == 4:
            return True
            
    # Geometric check fallback
    v1 = (edge1.verts[1].co - edge1.verts[0].co).normalized()
    v2 = (edge2.verts[1].co - edge2.verts[0].co).normalized()
    return abs(v1.dot(v2)) > 0.707

def get_neighbour_verts(vertex):
    edges = vertex.link_edges
    relevant_neighbour_verts = {v for e in edges for v in e.verts if v != vertex}
    return relevant_neighbour_verts

def get_neighbour_faces(face):
    face_edges = face.edges
    relevant_neighbour_faces = {f for e in face_edges for f in e.link_faces if f != face}
    return relevant_neighbour_faces

def get_neighbour_edges(prefs, edge, mode=''):
    edge_faces = edge.link_faces
    face_edges = {e for f in edge_faces for e in f.edges}

    ring_edges = []
    if len(edge_faces) > 0:
        for f in edge_faces:
            if len(f.verts) == 4:
                target_verts = [v for v in f.verts if v not in edge.verts]
                ring_edges.extend([e for e in f.edges if target_verts[0] in e.verts and target_verts[1] in e.verts])

    if edge.is_manifold:
        loop_edges = [e for v in edge.verts for e in v.link_edges
                     if len(v.link_edges) == 4 and e.is_manifold and e not in face_edges]
    elif edge.is_boundary:
        edge_verts = edge.verts
        if not prefs.ignore_boundary_wires:
            loop_edges = []
            for v in edge_verts:
                linked_edges = v.link_edges
                for e in linked_edges:
                    if not any([e for e in linked_edges if e.is_wire]):
                        if e.is_boundary and e is not edge:
                            loop_edges.append(e)
        elif prefs.ignore_boundary_wires:
            loop_edges = [e for v in edge_verts for e in v.link_edges
                         if e.is_boundary and e is not edge]
    elif edge.is_wire:
        loop_edges = []
        for vert in edge.verts:
            linked_edges = vert.link_edges
            if len(linked_edges) == 2:
                loop_edges.extend([e for e in linked_edges if e.is_wire and e is not edge])
    elif len(edge_faces) > 2:
        loop_edges = [e for v in edge.verts for e in v.link_edges
                     if not e.is_manifold and not e.is_wire and e not in face_edges]

    relevant_neighbour_edges = set(ring_edges + loop_edges)
    if mode == '':
        return relevant_neighbour_edges
    elif mode == 'LOOP':
        return loop_edges
    elif mode == 'RING':
        return ring_edges

def get_bounded_selection(prefs, component0, component1, mode):
    if not component0 or not component1 or component0.index == component1.index:
        return None
    if mode not in ['VERT', 'EDGE', 'FACE']:
        return None
    if type(component0) != type(component1):
        return None

    ends = [component0, component1]
    c0 = component0
    c1 = component1

    if mode == 'VERT':
        c0_edges = c0.link_edges
        c0_boundary = [e for e in c0_edges if e.is_boundary]
        c0_wire = [e for e in c0_edges if e.is_wire]

        c1_edges = c1.link_edges
        c1_boundary = [e for e in c1_edges if e.is_boundary]
        c1_wire = [e for e in c1_edges if e.is_wire]

        if len(c0_edges) == 0 or len(c1_edges) == 0:
            return None

        if (c0.is_manifold and not c0.is_boundary) or (c1.is_manifold and not c1.is_boundary):
            if c0.is_manifold and c1.is_manifold and not c0.is_boundary and not c1.is_boundary:
                if len(c0_edges) == 4:
                    starting_vert = c0
                elif len(c0_edges) != 4 and len(c1_edges) == 4:
                    starting_vert = c1
                elif len(c0_edges) != 4 and len(c1_edges) != 4:
                    return None
            elif c0.is_manifold and not c0.is_boundary:
                starting_vert = c0
            elif c1.is_manifold and not c1.is_boundary:
                starting_vert = c1
            connected_loops = bounded_loop_vert_manifold(prefs, starting_vert, ends)

        elif c0.is_boundary and c1.is_boundary:
            if c0.is_manifold:
                starting_vert = c0
            elif c1.is_manifold:
                starting_vert = c1
            elif len(c0_wire) > 0 and len(c0_boundary) == 2:
                starting_vert = c0
            elif len(c1_wire) > 0 and len(c1_boundary) == 2:
                starting_vert = c1
            else:
                starting_vert = c0
            connected_loops = bounded_loop_vert_boundary(prefs, starting_vert, ends)

        elif c0.is_wire or c1.is_wire:
            if c0.is_wire and c1.is_wire:
                if 0 < len(c0_wire) < 3:
                    starting_vert = c0
                elif 0 < len(c1_wire) < 3:
                    starting_vert = c1
                elif len(c0_wire) > 2 and len(c1_wire) > 2:
                    return None
            elif (c0.is_wire or c1.is_wire) and (not c0.is_wire or not c1.is_wire):
                return None
            connected_loops = bounded_loop_vert_wire(prefs, starting_vert, ends)

        elif not c0.is_manifold and not c1.is_manifold and not c0.is_boundary and not c1.is_boundary\
             and len(c0_wire) == 0 and len(c1_wire) == 0:
            return None

        elif (not c0.is_boundary and len(c0_wire) > 0) or (not c1.is_boundary and len(c1_wire) > 0):
            if not c0.is_boundary and len(c0_wire) > 0 and not c1.is_boundary and len(c1_wire) > 0:
                starting_vert = c0
            elif c0.is_boundary:
                starting_vert = c1
            elif c1.is_boundary:
                starting_vert = c0
            elif not c0.is_manifold and len(c0_wire) == 0 and not c1.is_boundary and len(c1_wire) > 0:
                starting_vert = c1
            elif not c1.is_manifold and len(c1_wire) == 0 and not c0.is_boundary and len(c0_wire) > 0:
                starting_vert = c0
            connected_loops = bounded_loop_vert_manifold(prefs, starting_vert, ends)
        else:
            return None

    if mode == 'EDGE':
        c0_faces = c0.link_faces
        c0_loop_dirs = get_neighbour_edges(prefs, c0, mode='LOOP')
        c0_ring_dirs = get_neighbour_edges(prefs, c0, mode='RING')

        c1_faces = c1.link_faces
        c1_loop_dirs = get_neighbour_edges(prefs, c1, mode='LOOP')
        c1_ring_dirs = get_neighbour_edges(prefs, c1, mode='RING')

        connected_loops = []
        if c0.is_manifold and c1.is_manifold:
            starting_edge = c0
            if len(c0_loop_dirs):
                connected_loops = bounded_loop_edge_manifold(prefs, starting_edge, ends)
            if len(connected_loops) > 0:
                pass
            elif len(c0_ring_dirs):
                if any(map(lambda x: len(x.verts) != 4, c0_faces)):
                    starting_edge = c1
                connected_loops = bounded_ring_edge_manifold(prefs, starting_edge, ends)

        elif c0.is_boundary and c1.is_boundary:
            connected_loops = bounded_loop_edge_boundary(prefs, c0, ends)

        elif c0.is_wire and c1.is_wire:
            connected_loops = bounded_loop_edge_wire(prefs, c0, ends)

        elif len(c0_faces) > 2 and len(c1_faces) > 2:
            return None

        elif c0.is_manifold and (c1.is_boundary or len(c1_faces) > 2):
            starting_edge = c0
            connected_loops = bounded_ring_edge_manifold(prefs, starting_edge, ends)

        elif c1.is_manifold and (c0.is_boundary or len(c0_faces) > 2):
            starting_edge = c1
            connected_loops = bounded_ring_edge_manifold(prefs, starting_edge, ends)

        elif (c0.is_wire and not c1.is_wire) or (c1.is_wire and not c0.is_wire):
            return None

    if mode == 'FACE':
        if not prefs.allow_non_quads_at_ends and (len(c0.verts) != 4 or len(c1.verts) != 4):
            return None
        if len(c0.verts) == 4:
            starting_face = c0
        elif len(c0.verts) != 4 and len(c1.verts) == 4:
            starting_face = c1
        else:
            return None

        connected_loops = bounded_loop_face(prefs, starting_face, ends)

    connected_loops.sort(key = lambda x: len(x))
    if len(connected_loops) == 0:
        return None
    elif len(connected_loops) == 1:
        return {i for i in connected_loops[0]}
    elif prefs.return_single_loop and len(connected_loops) > 1:
        return {i for i in connected_loops[0]}
    else:
        return {i for loop in connected_loops if len(loop) == len(connected_loops[0]) for i in loop}

# --- Bounded Selections ---

def bounded_loop_vert_manifold(prefs, starting_vert, ends):
    edges = [e for e in starting_vert.link_edges if not e.is_wire and not e.is_boundary]
    if len(edges) > 4:
        return []
    candidate_dirs = []
    for e in edges:
        loops = [loop for loop in e.link_loops]
        candidate_dirs.append(loops[0])
    connected_loops = []
    reference_list = set()

    for loop in candidate_dirs:
        if loop != "skip":
            if not prefs.ignore_hidden_geometry and loop.edge.hide:
                continue
            loop_edge = loop.edge
            reference_list.clear()
            partial_list = partial_loop_vert_manifold(prefs, loop, loop_edge, starting_vert, reference_list, ends)
            if "infinite" in partial_list:
                partial_list.discard("infinite")
                opposite_edge = get_opposite_edge(loop_edge, starting_vert)
                if opposite_edge is not None:
                    for l in opposite_edge.link_loops:
                        if l in candidate_dirs:
                            candidate_dirs[candidate_dirs.index(l)] = "skip"
            if ends[0] in partial_list and ends[1] in partial_list:
                connected_loops.append(partial_list)
    return connected_loops

def bounded_loop_vert_boundary(prefs, starting_vert, ends):
    connected_loops = []
    if prefs.ignore_hidden_geometry:
        edges = [e for e in starting_vert.link_edges if e.is_boundary]
    else:
        edges = [e for e in starting_vert.link_edges if e.is_boundary and not e.hide]

    for e in edges:
        partial_list = partial_loop_vert_boundary(prefs, starting_vert, e, ends)
        if "infinite" not in partial_list:
            if ends[0] in partial_list and ends[1] in partial_list:
                connected_loops.append([c for c in partial_list])
        else:
            break
    return connected_loops

def bounded_loop_vert_wire(prefs, starting_vert, ends):
    connected_loops = []
    if prefs.ignore_hidden_geometry:
        edges = [e for e in starting_vert.link_edges if e.is_wire]
    else:
        edges = [e for e in starting_vert.link_edges if e.is_wire and not e.hide]

    if len(edges) == 1 or len(edges) == 2:
        for e in edges:
            partial_list = partial_loop_vert_wire(prefs, starting_vert, e, ends)
            if "infinite" not in partial_list:
                if ends[0] in partial_list and ends[1] in partial_list:
                    connected_loops.append([c for c in partial_list])
            else:
                break
    else:
        return None
    return connected_loops

def bounded_loop_face(prefs, starting_face, ends):
    candidate_dirs = [loop for loop in starting_face.loops]
    connected_loops = []
    reference_list = set()

    for loop in candidate_dirs:
        if loop != "skip":
            reference_list.clear()
            partial_list = partial_loop_face(prefs, loop, starting_face, reference_list, ends)
            if "infinite" in partial_list:
                partial_list.discard("infinite")
                if len(starting_face.verts) == 4 and loop.link_loop_next.link_loop_next in candidate_dirs:
                    candidate_dirs[candidate_dirs.index(loop.link_loop_next.link_loop_next)] = "skip"
            if ends[0] in partial_list and ends[1] in partial_list:
                connected_loops.append([c for c in partial_list])
    return connected_loops

def bounded_loop_edge_manifold(prefs, starting_edge, ends):
    loop = starting_edge.link_loops[0]
    connected_loops = []
    reference_list = set()

    for v in starting_edge.verts:
        if len(v.link_loops) != 4:
            continue
        reference_list.clear()
        o_vert = starting_edge.other_vert(v)
        partial_list = partial_loop_edge_manifold(prefs, loop, starting_edge, o_vert, reference_list, ends)
        if "infinite" not in partial_list:
            if ends[0] in partial_list and ends[1] in partial_list:
                connected_loops.append([c for c in partial_list])
        else:
            break
    return connected_loops

def bounded_ring_edge_manifold(prefs, starting_edge, ends):
    starting_loop = starting_edge.link_loops[0]
    loops = [starting_loop, starting_loop.link_loop_radial_next]
    connected_loops = []
    reference_list = set()

    for loop in loops:
        reference_list.clear()
        partial_list = partial_ring_edge(prefs, loop, starting_edge, reference_list, ends)
        if "infinite" not in partial_list:
            if ends[0] in partial_list and ends[1] in partial_list:
                connected_loops.append([c for c in partial_list])
        else:
            break
    return connected_loops

def bounded_loop_edge_boundary(prefs, starting_edge, ends):
    connected_loops = []
    verts = starting_edge.verts

    for v in verts:
        partial_list = partial_loop_edge_boundary(prefs, starting_edge, v, ends)
        if "infinite" not in partial_list:
            if ends[0] in partial_list and ends[1] in partial_list:
                connected_loops.append([c for c in partial_list])
        else:
            break
    return connected_loops

def bounded_loop_edge_wire(prefs, starting_edge, ends):
    connected_loops = []
    verts = starting_edge.verts

    for v in verts:
        partial_list = partial_loop_edge_wire(prefs, starting_edge, v, ends)
        if "infinite" not in partial_list:
            if ends[0] in partial_list and ends[1] in partial_list:
                connected_loops.append([c for c in partial_list])
        else:
            break
    return connected_loops

# --- Full Loop Selections ---

def full_loop_vert_manifold(prefs, starting_vert, starting_edge):
    if not prefs.ignore_hidden_geometry and starting_edge.hide:
        return None
    if len(starting_vert.link_loops) != 4:
        starting_vert = starting_edge.other_vert(starting_vert)
        if len(starting_vert.link_loops) != 4:
            return None
    opposite_edge = get_opposite_edge(starting_edge, starting_vert)
    if opposite_edge is not None:
        loops = [starting_edge.link_loops[0], opposite_edge.link_loops[0]]
    else:
        loops = [starting_edge.link_loops[0]]
    vert_list = set()
    reference_list = set()

    for loop in loops:
        loop_edge = loop.edge
        if not prefs.ignore_hidden_geometry and loop_edge.hide:
            continue
        partial_list = partial_loop_vert_manifold(prefs, loop, loop_edge, starting_vert, reference_list)
        if "infinite" not in partial_list:
            vert_list.update(partial_list)
        else:
            partial_list.discard("infinite")
            vert_list.update(partial_list)
            break
    return vert_list

def full_loop_vert_boundary(prefs, starting_vert):
    if prefs.ignore_hidden_geometry:
        edges = [e for e in starting_vert.link_edges if e.is_boundary]
    else:
        edges = [e for e in starting_vert.link_edges if e.is_boundary and not e.hide]
    vert_list = set()

    for e in edges:
        partial_list = partial_loop_vert_boundary(prefs, starting_vert, e)
        if "infinite" not in partial_list:
            vert_list.update(partial_list)
        else:
            partial_list.discard("infinite")
            vert_list.update(partial_list)
            break
    return vert_list

def full_loop_vert_wire(prefs, starting_vert):
    if prefs.ignore_hidden_geometry:
        edges = [e for e in starting_vert.link_edges if e.is_wire]
    else:
        edges = [e for e in starting_vert.link_edges if e.is_wire and not e.hide]
    vert_list = set()

    if len(edges) == 1 or len(edges) == 2:
        for e in edges:
            partial_list = partial_loop_vert_wire(prefs, starting_vert, e)
            if "infinite" not in partial_list:
                vert_list.update(partial_list)
            else:
                partial_list.discard("infinite")
                vert_list.update(partial_list)
                break
    else:
        return None
    return vert_list

def full_loop_face(prefs, edge, face):
    if len(edge.link_loops) > 2:
        return None

    starting_loop = [loop for loop in edge.link_loops if loop in face.loops][0]
    loops = [starting_loop, starting_loop.link_loop_radial_next]
    face_list = set()
    reference_list = set()

    for loop in loops:
        starting_face = loop.face
        partial_list = partial_loop_face(prefs, loop, starting_face, reference_list)
        if "infinite" not in partial_list:
            face_list.update(partial_list)
        else:
            partial_list.discard("infinite")
            face_list.update(partial_list)
            break
    return face_list

def full_loop_edge_manifold(prefs, edge):
    starting_loop = edge.link_loops[0]
    if len(edge.verts[0].link_loops) == 4:
        starting_vert = edge.verts[0]
    elif len(edge.verts[1].link_loops) == 4:
        starting_vert = edge.verts[1]
    else:
        return []
    opposite_edge = get_opposite_edge(edge, starting_vert)
    if opposite_edge is not None:
        loops = [edge.link_loops[0], opposite_edge.link_loops[0]]
    else:
        loops = [edge.link_loops[0]]

    edge_list = set()
    reference_list = set()

    for loop in loops:
        new_edges = partial_loop_edge_manifold(prefs, loop, loop.edge, starting_vert, reference_list)
        if "infinite" not in new_edges:
            edge_list.update(new_edges)
        else:
            new_edges.discard("infinite")
            edge_list.update(new_edges)
            break
    return edge_list

def full_ring_edge_manifold(prefs, starting_edge):
    starting_loop = starting_edge.link_loops[0]
    loops = [starting_loop, starting_loop.link_loop_radial_next]
    edge_list = set()
    reference_list = set()

    for loop in loops:
        partial_list = partial_ring_edge(prefs, loop, starting_edge, reference_list)
        if "infinite" not in partial_list:
            edge_list.update(partial_list)
        else:
            partial_list.discard("infinite")
            edge_list.update(partial_list)
            break
    return edge_list

def full_loop_edge_boundary(prefs, edge):
    verts = edge.verts
    edge_list = set()

    for v in verts:
        new_edges = partial_loop_edge_boundary(prefs, edge, v)
        if "infinite" not in new_edges:
            edge_list.update(new_edges)
        else:
            new_edges.discard("infinite")
            edge_list.update(new_edges)
            break
    return edge_list

def full_loop_edge_wire(prefs, edge):
    verts = edge.verts
    edge_list = set()

    for v in verts:
        new_edges = partial_loop_edge_wire(prefs, edge, v)
        if "infinite" not in new_edges:
            edge_list.update(new_edges)
        else:
            new_edges.discard("infinite")
            edge_list.update(new_edges)
            break
    return edge_list

# --- Partial Loop (Fragment) Selections ---

def partial_loop_vert_manifold(prefs, loop, starting_edge, starting_vert, reference_list, ends=''):
    e_step = starting_edge
    pv = starting_vert
    cv = starting_edge.other_vert(starting_vert)
    partial_list = {pv}

    while True:
        if cv in loop.link_loop_prev.edge.verts:
            loop = loop.link_loop_prev
        elif cv in loop.link_loop_next.edge.verts:
            loop = loop.link_loop_next

        pv = cv
        next_loop = fan_loop_extension(e_step, loop, cv)

        if next_loop:
            e_step = next_loop.edge
            cv = e_step.other_vert(cv)
            loop = next_loop

            if not ends:
                dead_end = dead_end_vert_manifold(prefs, pv, e_step, starting_vert, partial_list, reference_list)
            else:
                dead_end = dead_end_vert_manifold(prefs, pv, e_step, starting_vert, partial_list, reference_list, ends)

            reference_list.add(pv)
            partial_list.add(pv)
            if dead_end:
                break
        else:
            partial_list.add(pv)
            break
    return partial_list

def partial_loop_vert_boundary(prefs, starting_vert, starting_edge, ends=''):
    cur_edges = [starting_edge]
    visited_edges = {starting_edge}
    visited_verts = {starting_vert}

    loop = 0
    while True:
        edge_verts = [v for e in cur_edges for v in e.verts if v not in visited_verts]
        new_edges = []
        for v in edge_verts:
            linked_edges = {e for e in v.link_edges if e.is_boundary or e.is_wire}
            for e in linked_edges:
                if not ends:
                    dead_end = dead_end_vert_boundary(prefs, v, e, starting_vert, linked_edges, visited_verts)
                else:
                    dead_end = dead_end_vert_boundary(prefs, v, e, starting_vert, linked_edges, visited_verts, ends)
                if dead_end:
                    visited_verts.add(v)
                else:
                    visited_verts.add(v)
                    if e not in visited_edges and not e.is_wire:
                        new_edges.append(e)

        if len(new_edges) == 0:
            break
        else:
            cur_edges = new_edges
            if loop == 1:
                visited_verts.discard(starting_vert)
            loop += 1
    return visited_verts

def partial_loop_vert_wire(prefs, starting_vert, starting_edge, ends=''):
    cur_vert = starting_vert
    cur_edge = starting_edge
    next_vert = cur_edge.other_vert(cur_vert)
    partial_list = {cur_vert}

    while True:
        partial_list.add(next_vert)
        linked_edges = next_vert.link_edges
        if len(linked_edges) < 2:
            break
        next_edge = [e for e in next_vert.link_edges if e is not cur_edge][0]

        if not ends:
            dead_end = dead_end_vert_wire(prefs, next_vert, next_edge, starting_vert, linked_edges, partial_list)
        else:
            dead_end = dead_end_vert_wire(prefs, next_vert, next_edge, starting_vert, linked_edges, partial_list, ends)

        if dead_end:
            break

        cur_vert = next_vert
        next_vert = next_edge.other_vert(cur_vert)
        cur_edge = next_edge
    return partial_list

def partial_loop_face(prefs, cur_loop, starting_face, reference_list, ends=''):
    partial_list = {starting_face}
    while True:
        next_loop = cur_loop.link_loop_radial_next.link_loop_next.link_loop_next
        next_face = next_loop.face

        if not ends:
            dead_end = dead_end_face(prefs, cur_loop, next_loop, next_face, starting_face, partial_list, reference_list)
        else:
            dead_end = dead_end_face(prefs, cur_loop, next_loop, next_face, starting_face, partial_list, reference_list, ends)

        if next_face not in partial_list:
            if len(next_face.verts) == 4:
                partial_list.add(next_face)
            elif prefs.allow_non_quads_at_ends:
                partial_list.add(next_face)
        reference_list.add(next_face)
        if dead_end:
            break
        cur_loop = next_loop
    return partial_list

def partial_loop_edge_manifold(prefs, loop, starting_edge, starting_vert, reference_list, ends=''):
    e_step = starting_edge
    pv = starting_vert
    cv = starting_edge.other_vert(starting_vert)
    partial_list = {e_step}

    while True:
        if cv in loop.link_loop_prev.edge.verts:
            loop = loop.link_loop_prev
        elif cv in loop.link_loop_next.edge.verts:
            loop = loop.link_loop_next

        pv = cv
        next_loop = fan_loop_extension(e_step, loop, cv)

        if next_loop:
            e_step = next_loop.edge
            cv = e_step.other_vert(cv)
            loop = next_loop

            if not ends:
                dead_end = dead_end_loop(prefs, e_step, cv, starting_edge, partial_list, reference_list)
            else:
                dead_end = dead_end_loop(prefs, e_step, cv, starting_edge, partial_list, reference_list, ends)

            reference_list.add(pv)
            partial_list.add(e_step)
            if dead_end:
                break
        else:
            partial_list.add(e_step)
            break
    return partial_list

def partial_ring_edge(prefs, starting_loop, starting_edge, reference_list, ends=''):
    cur_loop = starting_loop
    partial_list = {starting_edge}
    while True:
        next_loop = cur_loop.link_loop_radial_next.link_loop_next.link_loop_next
        if next_loop:
            next_edge = next_loop.edge
            next_face = next_loop.face

            if not ends:
                dead_end = dead_end_ring(prefs, next_edge, next_face, starting_edge, partial_list, reference_list)
            else:
                dead_end = dead_end_ring(prefs, next_edge, next_face, starting_edge, partial_list, reference_list, ends)

            if next_edge not in partial_list:
                if len(next_face.verts) == 4:
                    if not prefs.ignore_hidden_geometry and not next_face.hide:
                        partial_list.add(next_edge)
                    elif prefs.ignore_hidden_geometry:
                        partial_list.add(next_edge)
                reference_list.add(next_face)
            if dead_end:
                break
        else:
            break
        cur_loop = next_loop
    return partial_list

def partial_loop_edge_boundary(prefs, starting_edge, starting_vert, ends=''):
    cur_edges = [starting_edge]
    final_selection = set()
    visited_verts = {starting_vert}

    loop = 0
    while True:
        edge_verts = [v for e in cur_edges for v in e.verts if v not in visited_verts]
        new_edges = []
        for v in edge_verts:
            linked_edges = {e for e in v.link_edges if e.is_boundary or e.is_wire}
            for e in linked_edges:
                if not ends:
                    dead_end = dead_end_edge_boundary(prefs, e, v, starting_edge, linked_edges, final_selection)
                else:
                    dead_end = dead_end_edge_boundary(prefs, e, v, starting_edge, linked_edges, final_selection, ends)
                if dead_end:
                    visited_verts.add(v)
                else:
                    visited_verts.add(v)
                    if e not in final_selection and not e.is_wire:
                        new_edges.append(e)
        final_selection.update(new_edges)

        if len(new_edges) == 0:
            break
        else:
            cur_edges = new_edges
            if loop == 1:
                visited_verts.discard(starting_vert)
            loop += 1
    return final_selection

def partial_loop_edge_wire(prefs, starting_edge, starting_vert, ends=''):
    cur_vert = starting_vert
    cur_edge = starting_edge
    next_vert = cur_edge.other_vert(cur_vert)
    partial_list = {cur_edge}

    while True:
        linked_edges = next_vert.link_edges
        if len(linked_edges) < 2:
            break
        next_edge = [e for e in next_vert.link_edges if e is not cur_edge][0]
        if not len(linked_edges) > 2:
            partial_list.add(next_edge)
        if not ends:
            dead_end = dead_end_edge_wire(prefs, next_vert, next_edge, starting_edge, linked_edges, partial_list)
        else:
            dead_end = dead_end_edge_wire(prefs, next_vert, next_edge, starting_edge, linked_edges, partial_list, ends)

        if dead_end:
            break

        cur_vert = next_vert
        next_vert = next_edge.other_vert(cur_vert)
        cur_edge = next_edge
    return partial_list

# --- Dead End Conditions ---

def dead_end_vert_manifold(prefs, vert, edge, starting_vert, partial_list, reference_list, ends=''):
    if not ends:
        reached_end = vert == starting_vert
        if reached_end:
            partial_list.add("infinite")
    else:
        reached_end = vert == ends[0] or vert == ends[1]
        if reached_end:
            if vert == starting_vert:
                partial_list.add("infinite")
    is_intersect = prefs.terminate_self_intersects and vert in reference_list
    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    return reached_end or is_intersect or is_hidden

def dead_end_vert_boundary(prefs, vert, edge, starting_vert, linked_edges, partial_list, ends=''):
    if not ends:
        reached_end = starting_vert in partial_list and vert == starting_vert
        if reached_end:
            partial_list.add("infinite")
        is_intersect = prefs.terminate_self_intersects and len([e for e in linked_edges if e.is_boundary]) > 2
    else:
        reached_end = starting_vert in partial_list and vert == ends[0] or vert == ends[1]
        if reached_end:
            partial_list.add(vert)
            if starting_vert in partial_list and vert == starting_vert:
                partial_list.add("infinite")
        is_intersect = len([e for e in linked_edges if e.is_boundary]) > 2

    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    is_wire = not prefs.ignore_boundary_wires and any([e for e in linked_edges if e.is_wire])
    return reached_end or is_intersect or is_hidden or is_wire

def dead_end_vert_wire(prefs, vert, edge, starting_vert, linked_edges, partial_list, ends=''):
    if not ends:
        reached_end = vert == starting_vert
        if reached_end:
            partial_list.add("infinite")
    else:
        reached_end = vert == ends[0] or vert == ends[1]
        if reached_end:
            if vert == starting_vert:
                partial_list.add("infinite")
    cant_continue = len(linked_edges) != 2
    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    return reached_end or cant_continue or is_hidden

def dead_end_face(prefs, cur_loop, next_loop, next_face, starting_face, partial_list, reference_list, ends=''):
    if not ends:
        reached_end = next_face == starting_face
        if reached_end:
            partial_list.add("infinite")
    else:
        reached_end = next_face == ends[0] or next_face == ends[1]
        if reached_end and next_face == starting_face:
            partial_list.add("infinite")
    is_intersect = prefs.terminate_self_intersects and next_face in reference_list
    is_hidden = not prefs.ignore_hidden_geometry and next_face.hide
    is_non_quad = len(next_face.verts) != 4
    is_non_manifold = not cur_loop.edge.is_manifold or not next_loop.edge.is_manifold
    return reached_end or is_intersect or is_hidden or is_non_quad or is_non_manifold

def dead_end_loop(prefs, edge, vert, starting_edge, partial_list, reference_list, ends=''):
    if not ends:
        reached_end = edge == starting_edge
        if reached_end:
            partial_list.add("infinite")
    else:
        reached_end = edge == ends[0] or edge == ends[1]
        if reached_end:
            if edge == starting_edge:
                partial_list.add("infinite")
    is_intersect = prefs.terminate_self_intersects and vert in reference_list
    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    return reached_end or is_intersect or is_hidden

def dead_end_ring(prefs, edge, face, starting_edge, partial_list, reference_list, ends=''):
    if not ends:
        reached_end = edge == starting_edge
        if reached_end:
            partial_list.add("infinite")
    else:
        reached_end = edge == ends[0] or edge == ends[1]
        if reached_end:
            if edge == starting_edge:
                partial_list.add("infinite")
    is_intersect = prefs.terminate_self_intersects and face in reference_list
    is_hidden = not prefs.ignore_hidden_geometry and (face.hide or edge.hide)
    is_non_quad = len(face.verts) != 4
    is_non_manifold = not edge.is_manifold
    return reached_end or is_intersect or is_hidden or is_non_quad or is_non_manifold

def dead_end_edge_boundary(prefs, edge, vert, starting_edge, linked_edges, partial_list, ends=''):
    if not ends:
        reached_end = starting_edge in partial_list and edge == starting_edge
        if reached_end:
            partial_list.add("infinite")
        is_intersect = prefs.terminate_self_intersects and len([e for e in linked_edges if e.is_boundary]) > 2
    else:
        reached_end = starting_edge in partial_list and edge == ends[0] or edge == ends[1]
        if reached_end:
            partial_list.add(edge)
            if starting_edge in partial_list and edge == starting_edge:
                partial_list.add("infinite")
        is_intersect = len([e for e in linked_edges if e.is_boundary]) > 2

    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    is_wire = not prefs.ignore_boundary_wires and any([e for e in linked_edges if e.is_wire])
    return reached_end or is_intersect or is_hidden or is_wire

def dead_end_edge_wire(prefs, vert, edge, starting_edge, linked_edges, partial_list, ends=''):
    if not ends:
        reached_end = edge == starting_edge
        if reached_end:
            partial_list.add("infinite")
    else:
        reached_end = edge == ends[0] or edge == ends[1]
        if reached_end:
            if edge == starting_edge:
                partial_list.add("infinite")
    cant_continue = len(linked_edges) != 2
    is_hidden = not prefs.ignore_hidden_geometry and (vert.hide or edge.hide)
    return reached_end or cant_continue or is_hidden

# --- Walker Functions ---

def BM_vert_step_fan_loop(edge, loop, vert):
    if len(vert.link_loops) != 4:
        return None
    e_prev = edge
    if loop.edge == e_prev:
        e_next = loop.link_loop_prev.edge
    elif loop.link_loop_prev.edge == e_prev:
        e_next = loop.edge
    elif loop.link_loop_next.edge == e_prev:
        e_next = loop.edge
    else:
        return None

    if e_next.is_manifold:
        return BM_edge_other_loop(e_prev, e_next, loop)
    else:
        return None

def BM_edge_other_loop(e_prev, edge, loop):
    if loop.edge == edge:
        l_other = loop
    else:
        l_other = loop.link_loop_prev
    l_other = l_other.link_loop_radial_next

    if l_other.vert == loop.vert:
        if edge.other_vert(l_other.vert) == edge.other_vert(loop.vert):
            l_other = l_other.link_loop_next
            if l_other.vert not in e_prev.verts:
                l_other = l_other.link_loop_prev.link_loop_prev
        else:
            l_other = l_other.link_loop_prev
    elif l_other.link_loop_next.vert == loop.vert:
        if l_other.vert in e_prev.verts:
            l_other = l_other.link_loop_prev
        else:
            l_other = l_other.link_loop_next
    else:
        return None
    return l_other

def fan_loop_extension(edge, loop, vert):
    next_loop = BM_vert_step_fan_loop(edge, loop, vert)
    if not next_loop:
        loop = loop.link_loop_radial_next
        next_loop = BM_vert_step_fan_loop(edge, loop, vert)
    else:
        return next_loop
    return None

def get_opposite_edge(edge, vert):
    edges = [e for e in vert.link_edges]
    faces = [f for f in vert.link_faces]
    a_face = [f for f in faces if edge in f.edges][0]
    step_loop = [l for l in a_face.loops if l.edge in edges and l.edge != edge][0]
    opposite_loop = fan_loop_extension(edge, step_loop, vert)
    if opposite_loop is not None:
        opposite_edge = opposite_loop.edge
        return opposite_edge
    else:
        return None

# --- Operator Definition ---

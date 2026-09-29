"""Strip Transition: rebuild a strip segment whose width changes from one end to the other.

The selection is one patch: a wide end (W faces across), a narrow end (N faces
across) and two side rails. It is rebuilt with quads only, keeping its border:

* Width drops by 2 with a "3 to 1" unit: 3 faces below meet 1 face above through
  two small poles. 4->2 is one straight column plus one unit, 6->2 two units.
* Width drops by 1 with a "turn" unit: an edge loop bends out through the rail,
  which needs one extra vertex on that rail. If the rails already differ by one
  vertex that one is used; otherwise a rail edge is split (split_border on) or a
  single triangle is left instead (off). With equal rails an odd change can never
  be all quads: the border would have an odd number of edges.

Units sit in the row chosen by `position` (0 = wide end, 1 = narrow end), spilling
into neighbouring rows when one row cannot hold them all. The new faces are laid
onto the original surface by the Quad Patch engine.
"""
from . import quad_patch
from . import quad_patch_layout as layout
from .quad_patch_layout import PatchError


def _four_sides(faces, corners):
    loop, _ = layout.border_loop(faces)
    idx = [loop.index(c) for c in corners]
    return [layout.side_between(loop, idx[i], idx[(i + 1) % 4]) for i in range(4)]


def _arc_length(side, co):
    return sum((co(b) - co(a)).length for a, b in zip(side, side[1:]))


def _orient(faces, co):
    """Corners ordered so side 0 is the wide end and side 2 the narrow end."""
    loop, _ = layout.border_loop(faces)
    turns = layout.turn_angles(loop, set(faces), co)
    corners = [loop[i] for i in layout.choose_corners(loop, turns, 0.0)]
    sides = _four_sides(faces, corners)
    counts = [len(s) - 1 for s in sides]
    diff_a, diff_b = abs(counts[0] - counts[2]), abs(counts[1] - counts[3])
    if not diff_a and not diff_b:
        raise PatchError("Both ends already have the same width; use Quad Patch instead")
    if bool(diff_a) != bool(diff_b):
        ends_first = bool(diff_a)
    else:  # both pairs differ: the ends are the shorter pair
        ends_first = (_arc_length(sides[0], co) + _arc_length(sides[2], co)
                      <= _arc_length(sides[1], co) + _arc_length(sides[3], co))
    k = 0 if ends_first else 1
    if counts[k] < counts[k + 2]:
        k += 2
    return corners[k:] + corners[:k]


def _rail_splits(short, long_, co, keep_one, position):
    """Split plans giving the shorter rail the longer rail's unmatched vertices,
    optionally leaving the one nearest `position` unmatched."""
    t_short, t_long = layout.arc_params(short, co), layout.arc_params(long_, co)
    ks = layout.match_injective(t_short, t_long)
    unmatched = sorted(set(range(len(long_))) - set(ks))
    if keep_one and unmatched:
        unmatched.remove(min(unmatched, key=lambda k: abs(t_long[k] - position)))
    plans = {}
    for k in unmatched:
        a = max(i for i in range(len(ks)) if ks[i] < k)
        span = (t_long[ks[a + 1]] - t_long[ks[a]]) or 1.0
        plans.setdefault(a, []).append((t_long[k] - t_long[ks[a]]) / span)
    return [(short[a], short[a + 1], sorted(fr)) for a, fr in plans.items()]


def _plan_rows(width, rows, units, special, start_row, special_row):
    """Reductions per row: {row: (3->1 units, has_special)}; None if it does not fit.

    Prefers one unit per row (side-by-side units share a vertex and make a 6-edge
    pole), using the rows nearest start_row first.
    """
    order = sorted(range(rows), key=lambda j: (abs(j - start_row), j))
    for per_row in range(1, max(units, 1) + 1):
        for used in range(1, rows + 1):
            chosen = set(order[:used])
            if special and special_row not in chosen:
                continue
            plan, left, w = {}, units, width
            for j in range(rows):
                if j not in chosen:
                    continue
                has_special = special and j == special_row
                room = w - (2 if has_special else 0)
                if room < 0:
                    break
                take = min(left, room // 3, per_row)
                if take or has_special:
                    plan[j] = (take, has_special)
                left -= take
                w -= 2 * take + (1 if has_special else 0)
            else:
                if left == 0:
                    return plan
    return None


def _spread(n_units, n_straight):
    """Order of 'U' (3->1) and 'S' (straight) items with the units spread evenly."""
    total = n_units + n_straight
    # Slots are at least one apart because total >= n_units, so they never collide.
    slots = {int((k + 0.5) * total / n_units) for k in range(n_units)} if n_units else set()
    return ['U' if i in slots else 'S' for i in range(total)]


def build_strip_transition(bm, faces, matrix_world, *, split_border=True, position=0.5, relax=10):
    """Rebuild a strip segment so it changes width from one end to the other.

    Returns (new_faces, stats) with 'wide', 'narrow', 'rows', 'transition_rows',
    'splits' and 'tris'. Raises PatchError with a user-facing message.
    """
    faces, co, surface = quad_patch.prepare(bm, faces, matrix_world)
    corners = _orient(faces, co)
    bottom, right, top, left = (s if i < 2 else s[::-1] for i, s in enumerate(_four_sides(faces, corners)))
    wide, narrow = len(bottom) - 1, len(top) - 1
    drop = wide - narrow
    odd = drop % 2
    m_left, m_right = len(left) - 1, len(right) - 1
    rail_gap = m_right - m_left

    # Make the rails compatible: equal for an even change, one apart for an odd one.
    splits = 0
    if split_border and abs(rail_gap) != odd:
        if odd and rail_gap == 0:
            rows = m_left
            j = min(max(int(round(position * (rows - 1))), 0), rows - 1)
            plans = [(right[j], right[j + 1], [0.5])]
        else:
            short, long_ = (left, right) if rail_gap > 0 else (right, left)
            plans = _rail_splits(short, long_, co, odd, position)
        for va, vb, fractions in plans:
            layout.apply_split(va, vb, fractions)
            splits += len(fractions)
        bottom, right, top, left = (s if i < 2 else s[::-1] for i, s in enumerate(_four_sides(faces, corners)))
        m_left, m_right = len(left) - 1, len(right) - 1
        rail_gap = m_right - m_left

    t_left, t_right = layout.arc_params(left, co), layout.arc_params(right, co)
    rstar = rstar_side = None
    special_row = None
    if abs(rail_gap) == 1 and odd:
        # The longer rail's one unmatched vertex is where the loop turns out.
        short, long_, t_short, t_long = ((left, right, t_left, t_right) if rail_gap > 0
                                         else (right, left, t_right, t_left))
        ks = layout.match_injective(t_short, t_long)
        k_star = next(k for k in range(len(long_)) if k not in set(ks))
        rstar, rstar_side = long_[k_star], ('right' if rail_gap > 0 else 'left')
        special_row = max(a for a in range(len(ks)) if ks[a] < k_star)
        long_nodes = [v for k, v in enumerate(long_) if k != k_star]
        long_t = [t for k, t in enumerate(t_long) if k != k_star]
        if rail_gap > 0:
            left_nodes, vl, right_nodes, vr = left, t_left, long_nodes, long_t
        else:
            left_nodes, vl, right_nodes, vr = long_nodes, long_t, right, t_right
    elif rail_gap == 0:
        left_nodes, vl, right_nodes, vr = left, t_left, right, t_right
    else:
        # Border may not be split: merge the rails, leaving triangles against the shorter one.
        if rail_gap > 0:
            phi = layout.match_surjective(t_left, t_right)
            left_nodes, vl, right_nodes, vr = [left[i] for i in phi], t_right, right, t_right
        else:
            phi = layout.match_surjective(t_right, t_left)
            left_nodes, vl, right_nodes, vr = left, t_left, [right[i] for i in phi], t_left
    rows = len(left_nodes) - 1

    special = 'T' if rstar is not None else ('X' if odd else None)
    start_row = special_row if special_row is not None else min(max(int(round(position * (rows - 1))), 0), rows - 1)
    if special == 'X':
        special_row = start_row
    row_plan = _plan_rows(wide, rows, drop // 2, special is not None, start_row, special_row)
    if row_plan is None:
        raise PatchError(f"Not enough rows to go from {wide} to {narrow} faces across; select a longer strip")

    widths = [wide]
    for j in range(rows):
        take, has_special = row_plan.get(j, (0, False))
        widths.append(widths[-1] - 2 * take - (1 if has_special else 0))

    # Node keys ('n', row, column) on every row line; border nodes are existing vertices.
    ub, ut = layout.arc_params(bottom, co), layout.arc_params(top, co)
    first_t, last_t = min(row_plan), max(row_plan)
    node_vert, node_uv = {}, {}
    for j in range(rows + 1):
        w = widths[j]
        params = ub if j <= first_t else (ut if j > last_t else [i / w for i in range(w + 1)])
        for i in range(w + 1):
            key = ('n', j, i)
            if j == 0:
                node_vert[key] = bottom[i]
            elif j == rows:
                node_vert[key] = top[i]
            elif i == 0:
                node_vert[key] = left_nodes[j]
            elif i == w:
                node_vert[key] = right_nodes[j]
            u = params[i]
            node_uv[key] = (u, vl[j] + (vr[j] - vl[j]) * u)
    if rstar is not None:
        node_vert[('r*',)] = rstar

    cells, points = [], {}
    for j in range(rows):
        b = lambda i, j=j: ('n', j, i)
        t = lambda i, j=j: ('n', j + 1, i)
        take, has_special = row_plan.get(j, (0, False))
        if not take and not has_special:
            cells += [[b(i), b(i + 1), t(i + 1), t(i)] for i in range(widths[j])]
            continue
        straight = widths[j + 1] - take - (1 if has_special else 0)
        items = _spread(take, straight)
        if has_special:
            items = ['T'] + items if rstar_side == 'left' else items + [special]
        bi = tk = 0
        for n, item in enumerate(items):
            if item == 'S':
                cells.append([b(bi), b(bi + 1), t(tk + 1), t(tk)])
                bi, tk = bi + 1, tk + 1
            elif item == 'U':
                p, q = ('p', j, n), ('q', j, n)
                for key, lo, hi in ((p, b(bi + 1), t(tk)), (q, b(bi + 2), t(tk + 1))):
                    points[key] = tuple((node_uv[lo][c] + node_uv[hi][c]) * 0.5 for c in range(2))
                cells += [[b(bi), b(bi + 1), p, t(tk)], [b(bi + 1), b(bi + 2), q, p],
                          [b(bi + 2), b(bi + 3), t(tk + 1), q], [p, q, t(tk + 1), t(tk)]]
                bi, tk = bi + 3, tk + 1
            elif item == 'T' and rstar_side == 'left':
                cells += [[b(0), b(1), b(2), ('r*',)], [('r*',), b(2), t(1), t(0)]]
                bi, tk = bi + 2, tk + 1
            elif item == 'T':
                cells += [[b(bi), b(bi + 1), b(bi + 2), ('r*',)], [b(bi), ('r*',), t(tk + 1), t(tk)]]
                bi, tk = bi + 2, tk + 1
            else:  # 'X': one triangle where the rail could not be split
                cells += [[b(bi), b(bi + 1), t(tk)], [b(bi + 1), b(bi + 2), t(tk + 1), t(tk)]]
                bi, tk = bi + 2, tk + 1

    for key, uv in node_uv.items():
        if key not in node_vert:
            points[key] = uv
    sides = {'bottom': bottom, 'right': right, 'top': top, 'left': left}
    new_faces, tris = quad_patch.rebuild_patch(bm, faces, matrix_world, co, surface, sides,
                                               points, node_vert, cells, relax)
    return new_faces, {'wide': wide, 'narrow': narrow, 'rows': rows, 'transition_rows': len(row_plan),
                       'splits': splits, 'tris': tris}

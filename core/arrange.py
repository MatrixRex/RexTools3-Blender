"""Arrange: lay objects out side by side so none of them overlap.

Every object is measured by the world-space bounding box of its evaluated geometry,
together with everything parented under it, since that moves with it. A selected
object under another selected object is left to move with that one. Objects without
geometry (empties, lights, cameras) count as a point at their origin, except an
empty instancing a collection, which counts as the collection it shows.

Grid: objects go in rows and columns in list order, along +X and then row by row
towards -Y. Each column is as wide as its widest object and each row as deep as its
deepest, so small objects don't get cells sized for the biggest one, and each object
sits in the middle of its cell. The column count is picked so the whole grid comes
out as close to square as it can.
"""
import math

from mathutils import Matrix, Vector

# Object types whose bound_box is their geometry; the others are a point at their origin
_BOUNDED = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'LATTICE', 'ARMATURE',
            'GREASEPENCIL', 'VOLUME', 'POINTCLOUD', 'CURVES'}
_MAX_NESTING = 8  # collection instances followed inside collection instances


class Item:
    """An object to place, with the world-space bounds of it and everything under it."""

    def __init__(self, obj, lo, hi):
        self.obj = obj
        self.lo = lo
        self.hi = hi

    @property
    def size(self):
        return self.hi - self.lo

    @property
    def center(self):
        return (self.lo + self.hi) * 0.5

    def move(self, delta):
        self.obj.matrix_world = Matrix.Translation(delta) @ self.obj.matrix_world
        self.lo += delta
        self.hi += delta


def _points(obj, depsgraph, matrix, depth=0):
    """World-space corners of an object's bounds, with the object placed by `matrix`."""
    if obj.type in _BOUNDED:
        try:
            box = obj.evaluated_get(depsgraph).bound_box
        except RuntimeError:  # not in the depsgraph, like the insides of a collection instance
            box = obj.bound_box
        return [matrix @ Vector(corner) for corner in box]

    collection = obj.instance_collection if obj.instance_type == 'COLLECTION' else None
    if collection is None or depth >= _MAX_NESTING:
        return [matrix.translation.copy()]
    matrix = matrix @ Matrix.Translation(-collection.instance_offset)
    points = []
    for inner in collection.all_objects:
        points.extend(_points(inner, depsgraph, matrix @ inner.matrix_world, depth + 1))
    return points or [matrix.translation.copy()]


def roots(objects):
    """The objects not parented, at any depth, under another one of them."""
    chosen = set(objects)
    result = []
    for obj in objects:
        parent = obj.parent
        while parent is not None and parent not in chosen:
            parent = parent.parent
        if parent is None:
            result.append(obj)
    return result


def measure(objects, depsgraph):
    """An Item for each of the objects that isn't under another one of them."""
    items = []
    for obj in roots(objects):
        points = []
        for part in (obj, *obj.children_recursive):
            points.extend(_points(part, depsgraph, part.matrix_world))
        lo = Vector([min(p[i] for p in points) for i in range(3)])
        hi = Vector([max(p[i] for p in points) for i in range(3)])
        items.append(Item(obj, lo, hi))
    return items


def bounds(items):
    """The (lo, hi) corners of the box around all the items."""
    lo = Vector([min(item.lo[i] for item in items) for i in range(3)])
    hi = Vector([max(item.hi[i] for item in items) for i in range(3)])
    return lo, hi


def sort_by_size(items, largest_first=True):
    """Sort by the diagonal of the bounds, which still sizes flat objects. Ties go by name."""
    items.sort(key=lambda item: item.obj.name)
    items.sort(key=lambda item: item.size.length, reverse=largest_first)


def _grid(sizes, columns):
    """Column widths and row depths for (width, depth) sizes laid out `columns` to a row."""
    widths = [0.0] * columns
    depths = [0.0] * math.ceil(len(sizes) / columns)
    for i, (width, depth) in enumerate(sizes):
        row, column = divmod(i, columns)
        widths[column] = max(widths[column], width)
        depths[row] = max(depths[row], depth)
    return widths, depths


def _span(lengths, spacing):
    return sum(lengths) + spacing * (len(lengths) - 1)


def _columns(sizes, spacing):
    """The column count that makes the grid closest to square. Ties go to the smaller grid, then the wider."""
    best, best_key = 1, None
    for columns in range(1, len(sizes) + 1):
        widths, depths = _grid(sizes, columns)
        width, depth = _span(widths, spacing), _span(depths, spacing)
        long, short = max(width, depth), min(width, depth)
        aspect = long / short if short > 0.0 else (math.inf if long > 0.0 else 1.0)
        key = (aspect, width * depth)
        if best_key is None or key <= best_key:
            best, best_key = columns, key
        if width >= depth:
            break  # more columns only make it wider still
    return best


def grid(items, spacing, center, ground=None):
    """Move the items into a grid centred on `center` in X and Y.

    With `ground`, every item's bottom moves to that height; otherwise heights stay.
    Returns the (columns, rows) used.
    """
    sizes = [(item.size.x, item.size.y) for item in items]
    columns = _columns(sizes, spacing)
    widths, depths = _grid(sizes, columns)

    xs, x = [], center.x - _span(widths, spacing) * 0.5
    for width in widths:
        xs.append(x + width * 0.5)
        x += width + spacing
    ys, y = [], center.y + _span(depths, spacing) * 0.5
    for depth in depths:
        ys.append(y - depth * 0.5)
        y -= depth + spacing

    for i, item in enumerate(items):
        row, column = divmod(i, columns)
        now = item.center
        dz = ground - item.lo.z if ground is not None else 0.0
        item.move(Vector((xs[column] - now.x, ys[row] - now.y, dz)))
    return columns, len(depths)

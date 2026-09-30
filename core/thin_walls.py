"""Thin Walls: find the parts of a mesh that are only a thin wall, and tell the wall's two sides apart.

A face is one side of a thin wall when a ray shot from its centre straight into the
material (against its normal) comes out again within Max Thickness, through a face
that points the other way (within Max Angle of exactly opposite). That face is its
partner, the other side of the wall, and counts as thin too. Distances are measured
in world space, so object scale counts. Normals must point out of the mesh.

The two sides of a wall are usually separate patches of faces: the inside and the
outside of a cup only meet at the rim, which is not thin itself. Thin faces are
grouped into sides by growing across shared edges, never across a fold of 90 degrees
or more (a knife edge where both sides of a sheet meet). Each side gets a score:

- OPEN: how much open space it sees. Rays fanned out around each normal that leave
  the mesh without hitting it count as open; the inside of a cup or the body side of
  a jacket sees less than its outside.
- CENTER / CURSOR: how much its normals point away from the centre of the mesh's
  bounds or from the 3D cursor.

A side is outer when it scores higher than the side across the wall, inner when it
scores lower; every face votes, by area, against the side its partner is on. When
two scores are too close to call, the next test decides (OPEN falls back to CENTER,
the others to OPEN), and if that is too close as well the side stays undecided,
like the two faces of a flat plank. A side that is mostly its own partner (a rod,
thin all the way round) is decided face by face instead.
"""
import math

from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUTER, INNER, UNDECIDED = 'OUTER', 'INNER', 'UNDECIDED'

_OPEN_RAYS = 24        # rays fanned around a normal when measuring open space
_OPEN_SAMPLES = 48     # faces per side that measure open space, spread over the side
_TIE = 0.05            # scores closer than this are too close to call
_FOLD = 0.0            # sides don't grow across edges whose normals' dot is at or below this
_STEP_PAST = 4         # times a ray steps past the face it started on before giving up
_EPS = 1e-6            # ray start offset, relative to the size of the mesh

_TESTS = {
    'OPEN': ('OPEN', 'CENTER'),
    'CENTER': ('CENTER', 'OPEN'),
    'CURSOR': ('CURSOR', 'OPEN'),
}
_NAMES = {1: OUTER, -1: INNER, 0: UNDECIDED}


def _hemisphere(count):
    """Cosine-weighted directions around +Z on a golden-angle spiral, the same every run."""
    golden = math.pi * (3.0 - math.sqrt(5.0))
    dirs = []
    for k in range(count):
        r = math.sqrt((k + 0.5) / count)
        a = k * golden
        dirs.append(Vector((r * math.cos(a), r * math.sin(a), math.sqrt(1.0 - r * r))))
    return dirs


_RAYS = _hemisphere(_OPEN_RAYS)


class _Mesh:
    """World-space centres, normals and areas of the visible faces, with a BVH over them.

    Faces are referred to by their position in `faces`, which is also their BVH index.
    Degenerate faces have no normal (None) and are never thin.
    """

    def __init__(self, bm, matrix):
        bm.verts.index_update()
        co = [matrix @ v.co for v in bm.verts]
        # A mirrored object reverses the winding, which would turn every normal inward
        flip = -1.0 if matrix.to_3x3().determinant() < 0.0 else 1.0

        self.faces = [f for f in bm.faces if not f.hide]
        self.index = {f: i for i, f in enumerate(self.faces)}
        polys = [[v.index for v in f.verts] for f in self.faces]
        self.centers, self.normals, self.areas = [], [], []
        for poly in polys:
            pts = [co[k] for k in poly]
            c = sum(pts, Vector()) / len(pts)
            n = Vector()
            prev = pts[-1] - c
            for p in pts:
                p = p - c
                n += prev.cross(p)
                prev = p
            self.centers.append(c)
            self.areas.append(n.length * 0.5)
            self.normals.append(n.normalized() * flip if n.length_squared > 0.0 else None)

        visible = [co[v.index] for v in bm.verts if not v.hide] or co or [Vector()]
        lo = Vector(tuple(min(p[a] for p in visible) for a in range(3)))
        hi = Vector(tuple(max(p[a] for p in visible) for a in range(3)))
        self.center = (lo + hi) * 0.5
        self.eps = max((hi - lo).length * _EPS, 1e-9)
        self.bvh = BVHTree.FromPolygons(co, polys) if polys else None

    def cast(self, origin, direction, reach, skip):
        """First face along the ray within reach, stepping past face `skip`: (face, distance) or None."""
        travelled = 0.0
        for _ in range(_STEP_PAST):
            if reach - travelled <= 0.0:
                return None
            loc, _normal, j, dist = self.bvh.ray_cast(origin, direction, reach - travelled)
            if j is None:
                return None
            travelled += dist
            if j != skip:
                return j, travelled
            origin = loc + direction * self.eps
            travelled += self.eps
        return None


def _partners(mesh, max_thickness, max_angle):
    """{face: (partner, thickness)} for every face that is one side of a thin wall."""
    facing = math.cos(max_angle)
    partners = {}
    for i, n in enumerate(mesh.normals):
        if n is None:
            continue
        inward = -n
        hit = mesh.cast(mesh.centers[i] + inward * mesh.eps, inward, max_thickness, i)
        if hit is None:
            continue
        j, dist = hit
        m = mesh.normals[j]
        if m is not None and m.dot(inward) >= facing:
            partners[i] = (j, dist + mesh.eps)
    # The other side of a wall is thin too, even where a ray from its own centre misses
    for i, (j, dist) in list(partners.items()):
        partners.setdefault(j, (i, dist))
    return partners


def _sides(mesh, partners):
    """Group thin faces into sides: side id per face, and the faces of every side."""
    side_of, sides = {}, []
    for start in partners:
        if start in side_of:
            continue
        s = len(sides)
        side_of[start] = s
        members, stack = [start], [start]
        while stack:
            i = stack.pop()
            n = mesh.normals[i]
            for e in mesh.faces[i].edges:
                for g in e.link_faces:
                    j = mesh.index.get(g)
                    if j is None or j in side_of or j not in partners:
                        continue
                    if n.dot(mesh.normals[j]) <= _FOLD:
                        continue
                    side_of[j] = s
                    members.append(j)
                    stack.append(j)
        sides.append(members)
    return side_of, sides


class _Scores:
    """How outer faces and sides look to each test, worked out once and only when asked for."""

    def __init__(self, mesh, sides, tests, cursor):
        self.mesh, self.sides, self.tests = mesh, sides, tests
        self.points = {'CENTER': mesh.center, 'CURSOR': cursor}
        self._faces, self._sides = {}, {}

    def face(self, test, i):
        key = (test, i)
        if key not in self._faces:
            self._faces[key] = self._open(i) if test == 'OPEN' else self._facing(i, self.points[test])
        return self._faces[key]

    def side(self, test, s):
        key = (test, s)
        if key not in self._sides:
            members = self.sides[s]
            if test == 'OPEN' and len(members) > _OPEN_SAMPLES:
                step = len(members) / _OPEN_SAMPLES
                members = [members[int(k * step)] for k in range(_OPEN_SAMPLES)]
            areas = self.mesh.areas
            total = sum(areas[i] for i in members)
            if total > 0.0:
                score = sum(areas[i] * self.face(test, i) for i in members) / total
            else:
                score = sum(self.face(test, i) for i in members) / len(members)
            self._sides[key] = score
        return self._sides[key]

    def verdict(self, score, a, b):
        """1 when a scores higher than b on the first test that tells them apart, -1 when lower, 0 if none does."""
        for test in self.tests:
            diff = score(test, a) - score(test, b)
            if diff > _TIE:
                return 1
            if diff < -_TIE:
                return -1
        return 0

    def _open(self, i):
        mesh = self.mesh
        n = mesh.normals[i]
        turn = n.to_track_quat('Z', 'Y').to_matrix()
        origin = mesh.centers[i] + n * mesh.eps
        misses = sum(1 for d in _RAYS if mesh.bvh.ray_cast(origin, turn @ d)[2] is None)
        return misses / len(_RAYS)

    def _facing(self, i, point):
        away = self.mesh.centers[i] - point
        if away.length_squared == 0.0:
            return 0.0
        return self.mesh.normals[i].dot(away.normalized())


def find(bm, matrix, max_thickness, max_angle, classify_by='OPEN', cursor=None):
    """Thin-wall faces among the visible faces of bm.

    Returns {BMFace: (side, thickness)} with side OUTER, INNER or UNDECIDED and thickness
    in world units. classify_by is 'OPEN', 'CENTER' or 'CURSOR' (cursor: world position).
    """
    mesh = _Mesh(bm, matrix)
    if mesh.bvh is None:
        return {}
    partners = _partners(mesh, max_thickness, max_angle)
    side_of, sides = _sides(mesh, partners)
    scores = _Scores(mesh, sides, _TESTS[classify_by], cursor if cursor is not None else mesh.center)

    labels = {}
    for s, members in enumerate(sides):
        own, across = 0.0, {}
        for i in members:
            t = side_of[partners[i][0]]
            if t == s:
                own += mesh.areas[i]
            else:
                across[t] = across.get(t, 0.0) + mesh.areas[i]
        if own > sum(across.values()):
            for i in members:
                labels[i] = scores.verdict(scores.face, i, partners[i][0])
        else:
            vote = sum(w * scores.verdict(scores.side, s, t) for t, w in across.items())
            label = (vote > 0.0) - (vote < 0.0)
            for i in members:
                labels[i] = label

    return {mesh.faces[i]: (_NAMES[labels[i]], partners[i][1]) for i in partners}

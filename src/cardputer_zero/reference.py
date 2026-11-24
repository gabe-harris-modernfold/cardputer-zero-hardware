"""Load M5Stack's official CardputerZero STL into a canonical device frame.

The official file (reference/official/CardputerZero.stl) holds three copies of
the housing laid out along X: the assembled two-part shell, then the front
shell alone, then the back shell alone. Only the assembled copy is used here.
It is the plastic housing only: no keycaps, display, PCB or connectors.

Canonical device frame (millimetres):
    origin  centre of the 84 x 54 footprint, on the back face
    +X      right edge when looking at the screen
    +Y      top edge (EXT header side)
    +Z      out of the screen / keyboard face
so the device occupies X -42..42, Y -27..27, Z 0..23.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from . import REFERENCE_DIR

OFFICIAL_STL = REFERENCE_DIR / "CardputerZero.stl"

# Published by M5Stack (docs.m5stack.com/en/CardputerZero).
NOMINAL_SIZE = (84.0, 54.0, 23.1)

# Where the assembled copy sits in the raw file, and the shift that moves it
# into the canonical frame.
_ASSEMBLED_X_MAX = -10.0
_RAW_TO_CANONICAL = np.array([56.4, -32.0, 23.25])

# In the canonical frame the front shell starts at Z = 14.0 and the back shell
# at Z = 0, so any Z between the two separates them.
_SPLIT_Z = 7.0

# Connected pieces smaller than this are modelling debris (stray slivers).
_MIN_PART_FACES = 100


@dataclass(frozen=True)
class Repair:
    """What was changed to make a shell a clean closed manifold."""

    pinched_edges: int = 0  # edges shared by more than two triangles
    vertices_moved: int = 0
    surface_shift_mm: float = 0.0  # furthest a moved vertex ended up from the new surface
    volume_change_mm3: float = 0.0


@dataclass(frozen=True)
class ReferenceModel:
    """Official housing geometry in the canonical frame."""

    front_shell: trimesh.Trimesh  # keyboard / screen bezel half
    back_shell: trimesh.Trimesh  # battery / port half
    debris_faces: int = 0  # triangles dropped as stray slivers
    repairs: dict[str, Repair] = field(default_factory=dict)

    @property
    def parts(self) -> dict[str, trimesh.Trimesh]:
        return {"front_shell": self.front_shell, "back_shell": self.back_shell}

    @property
    def assembled(self) -> trimesh.Trimesh:
        return trimesh.util.concatenate([self.front_shell, self.back_shell])

    @property
    def size(self) -> np.ndarray:
        return self.assembled.extents


def _edge_use(faces: np.ndarray):
    edges = np.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    return np.unique(edges, axis=0, return_inverse=True, return_counts=True)


def is_manifold(mesh: trimesh.Trimesh) -> bool:
    """True when every edge is shared by exactly two triangles."""
    return bool((_edge_use(mesh.faces)[2] == 2).all())


def _point_to_triangles(p: np.ndarray, tri: np.ndarray) -> float:
    """Shortest distance from point p to any triangle in tri (n, 3, 3)."""
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    n = np.cross(b - a, c - a)
    nn = np.linalg.norm(n, axis=1)
    good = nn > 1e-12
    n[good] /= nn[good][:, None]
    plane = np.einsum("ij,ij->i", p - a, n)
    q = p - plane[:, None] * n
    inside = good.copy()
    for u, v in ((a, b), (b, c), (c, a)):
        inside &= np.einsum("ij,ij->i", np.cross(v - u, q - u), n) >= 0
    best = np.abs(plane[inside]).min() if inside.any() else np.inf
    for u, v in ((a, b), (b, c), (c, a)):
        e = v - u
        t = np.clip(np.einsum("ij,ij->i", p - u, e) / np.maximum(np.einsum("ij,ij->i", e, e), 1e-18), 0, 1)
        best = min(best, np.linalg.norm(p - (u + t[:, None] * e), axis=1).min())
    return float(best)


def _collapse_pinch_slivers(mesh: trimesh.Trimesh, max_area: float = 0.02):
    """Remove needle triangles that make edges non-manifold.

    The official back shell has a ~0.01 mm wide sliver that leaves two edges
    shared by four triangles. Folding each sliver's odd vertex onto the pinched
    edge deletes it and leaves a closed manifold, which CAD kernels need.
    """
    v = np.array(mesh.vertices)
    f = np.array(mesh.faces)
    pinched = int((_edge_use(f)[2] > 2).sum())
    moved: list[np.ndarray] = []
    for _ in range(8):
        uniq, inverse, count = _edge_use(f)
        bad = np.flatnonzero(count > 2)
        if len(bad) == 0:
            break
        tri = v[f]
        area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        remap = np.arange(len(v))
        for edge in bad:
            a, b = uniq[edge]
            for face in np.flatnonzero(inverse == edge) // 3:
                if area[face] >= max_area:
                    continue
                c = next(x for x in f[face] if x not in (a, b))
                remap[c] = a if np.linalg.norm(v[c] - v[a]) < np.linalg.norm(v[c] - v[b]) else b
                moved.append(v[c].copy())
        if (remap == np.arange(len(v))).all():
            break  # pinched edges without slivers: nothing safe to collapse
        f = remap[f]
        f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
        # A fold leaves two triangles on the same three vertices; drop both.
        _, inv, cnt = np.unique(np.sort(f, axis=1), axis=0, return_inverse=True, return_counts=True)
        f = f[cnt[inv] == 1]
    fixed = trimesh.Trimesh(v, f, process=False)
    fixed.remove_unreferenced_vertices()
    tri = fixed.vertices[fixed.faces]
    shift = max((_point_to_triangles(p, tri) for p in moved), default=0.0)
    return fixed, Repair(
        pinched_edges=pinched,
        vertices_moved=len(moved),
        surface_shift_mm=shift,
        volume_change_mm3=float(fixed.volume - mesh.volume),
    )


def load_reference(path: str | Path = OFFICIAL_STL, repair: bool = True) -> ReferenceModel:
    """Read the official STL and return its two shells in the canonical frame."""
    raw = trimesh.load_mesh(Path(path), process=True)
    found: dict[str, list[trimesh.Trimesh]] = {"front_shell": [], "back_shell": []}
    debris = 0
    for part in raw.split(only_watertight=False):
        if part.bounds[1][0] > _ASSEMBLED_X_MAX:
            continue  # one of the exploded copies
        if len(part.faces) < _MIN_PART_FACES:
            debris += len(part.faces)
            continue
        part.apply_translation(_RAW_TO_CANONICAL)
        found["front_shell" if part.bounds[0][2] > _SPLIT_Z else "back_shell"].append(part)
    if any(len(group) != 1 for group in found.values()):
        raise ValueError(
            f"expected one front and one back shell, found {len(found['front_shell'])} and "
            f"{len(found['back_shell'])}; the official STL layout may have changed"
        )
    shells = {name: group[0] for name, group in found.items()}
    repairs: dict[str, Repair] = {}
    if repair:
        for name, mesh in shells.items():
            if not is_manifold(mesh):
                shells[name], repairs[name] = _collapse_pinch_slivers(mesh)
    return ReferenceModel(shells["front_shell"], shells["back_shell"], debris, repairs)

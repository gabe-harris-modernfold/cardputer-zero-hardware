"""Small dependency-free (numpy + Pillow) orthographic renderer.

Good enough to eyeball meshes from a script without a GPU or a window:
z-buffered flat shading with dark outlines on creases and silhouettes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# Camera presets in the canonical device frame (+Z = keyboard/screen face,
# +Y = top edge, +X = right edge when looking at the screen).
# name -> (direction the camera sits in, up vector)
VIEWS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "front": ((0, 0, 1), (0, 1, 0)),
    "back": ((0, 0, -1), (0, 1, 0)),
    "top": ((0, 1, 0), (0, 0, -1)),
    "bottom": ((0, -1, 0), (0, 0, 1)),
    "left": ((-1, 0, 0), (0, 1, 0)),
    "right": ((1, 0, 0), (0, 1, 0)),
    "iso": ((-0.55, -0.75, 0.9), (0, 0, 1)),
    "iso_back": ((0.55, 0.75, -0.9), (0, 0, -1)),
}


def _camera_basis(direction, up):
    d = np.asarray(direction, float)
    d /= np.linalg.norm(d)
    u = np.asarray(up, float)
    right = np.cross(u, d)
    right /= np.linalg.norm(right)
    true_up = np.cross(d, right)
    return right, true_up, d


def view_frame(vertices: np.ndarray, view: str, margin_mm: float = 3.0):
    """(right, up, u_min, v_max) of the image that rasterize/render_mesh produce."""
    right, up, _ = _camera_basis(*VIEWS[view])
    v = np.asarray(vertices, float)
    return right, up, float((v @ right).min() - margin_mm), float((v @ up).max() + margin_mm)


@dataclass
class Raster:
    """Orthographic depth image of a mesh seen from one of VIEWS.

    depth[row, col] is the coordinate along the axis pointing at the camera of
    the nearest surface (-inf where nothing was hit); face_id is the triangle
    hit (-1 where nothing). Image columns run along `right`, rows run down
    against `up`; (u_min, v_max) is the top-left corner in mm.
    """

    depth: np.ndarray
    face_id: np.ndarray
    right: np.ndarray
    up: np.ndarray
    toward: np.ndarray
    u_min: float
    v_max: float
    px_per_mm: float

    def uv(self, col, row):
        """Pixel centre -> in-plane (u, v) in mm."""
        return (self.u_min + (np.asarray(col) + 0.5) / self.px_per_mm,
                self.v_max - (np.asarray(row) + 0.5) / self.px_per_mm)

    def pixel(self, u, v):
        """In-plane (u, v) in mm -> fractional (col, row)."""
        return ((np.asarray(u) - self.u_min) * self.px_per_mm,
                (self.v_max - np.asarray(v)) * self.px_per_mm)


def rasterize(
    vertices: np.ndarray,
    faces: np.ndarray,
    view: str,
    px_per_mm: float = 12.0,
    margin_mm: float = 3.0,
) -> Raster:
    """Z-buffer the triangles as seen from `view` (a key of VIEWS)."""
    right, up, toward = _camera_basis(*VIEWS[view])
    v = np.asarray(vertices, float)
    f = np.asarray(faces, int)

    uvd = np.stack([v @ right, v @ up, v @ toward], axis=1)
    lo = uvd[:, :2].min(axis=0) - margin_mm
    hi = uvd[:, :2].max(axis=0) + margin_mm
    w = int(np.ceil((hi[0] - lo[0]) * px_per_mm))
    h = int(np.ceil((hi[1] - lo[1]) * px_per_mm))
    px = (uvd[:, 0] - lo[0]) * px_per_mm
    py = (hi[1] - uvd[:, 1]) * px_per_mm
    depth = uvd[:, 2]

    zbuf = np.full((h, w), -np.inf)
    idbuf = np.full((h, w), -1, dtype=np.int64)
    for i in range(len(f)):
        a, b, c = f[i]
        x0, x1, x2 = px[a], px[b], px[c]
        y0, y1, y2 = py[a], py[b], py[c]
        xmin, xmax = int(max(np.floor(min(x0, x1, x2)), 0)), int(min(np.ceil(max(x0, x1, x2)), w - 1))
        ymin, ymax = int(max(np.floor(min(y0, y1, y2)), 0)), int(min(np.ceil(max(y0, y1, y2)), h - 1))
        if xmin > xmax or ymin > ymax:
            continue
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        xs = np.arange(xmin, xmax + 1) + 0.5
        ys = np.arange(ymin, ymax + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
        l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
        l2 = 1.0 - l0 - l1
        z = l0 * depth[a] + l1 * depth[b] + l2 * depth[c]
        sub_z = zbuf[ymin : ymax + 1, xmin : xmax + 1]
        sub_id = idbuf[ymin : ymax + 1, xmin : xmax + 1]
        hit = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6) & (z > sub_z)
        sub_z[hit] = z[hit]
        sub_id[hit] = i
    return Raster(zbuf, idbuf, right, up, toward, float(lo[0]), float(hi[1]), px_per_mm)


def render_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    view: str = "iso",
    px_per_mm: float = 12.0,
    margin_mm: float = 3.0,
    face_colors: np.ndarray | None = None,
    supersample: int = 2,
) -> Image.Image:
    """Render triangles orthographically and return a PIL image.

    face_colors: optional (n_faces, 3) floats in 0..1; default is light grey.
    """
    v = np.asarray(vertices, float)
    f = np.asarray(faces, int)
    raster = rasterize(v, f, view, px_per_mm * supersample, margin_mm)
    right, up, toward = raster.right, raster.up, raster.toward
    zbuf, idbuf = raster.depth, raster.face_id
    h, w = zbuf.shape

    tri = v[f]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lens = np.linalg.norm(normals, axis=1)
    ok = lens > 1e-12
    normals[ok] /= lens[ok][:, None]

    light = np.asarray([-0.35, 0.45, 0.82])
    light /= np.linalg.norm(light)
    cam_n = np.stack([normals @ right, normals @ up, normals @ toward], axis=1)
    shade = 0.38 + 0.62 * np.abs(cam_n @ light)
    if face_colors is None:
        face_colors = np.full((len(f), 3), 0.80)

    covered = idbuf >= 0
    img = np.ones((h, w, 3))
    ids = idbuf[covered]
    img[covered] = face_colors[ids] * shade[ids][:, None]

    # Outline creases (normal changes) and silhouettes (depth jumps).
    nbuf = np.zeros((h, w, 3))
    nbuf[covered] = cam_n[ids]
    zf = np.where(covered, zbuf, -1e6)
    edge = np.zeros((h, w), bool)
    for axis in (0, 1):
        dz = np.abs(np.diff(zf, axis=axis))
        dot = np.abs(np.sum(nbuf * np.roll(nbuf, -1, axis=axis), axis=2))
        dot = dot[:-1] if axis == 0 else dot[:, :-1]
        both = covered & np.roll(covered, -1, axis=axis)
        both = both[:-1] if axis == 0 else both[:, :-1]
        e = (dz > 0.35) | (both & (dot < 0.80))
        if axis == 0:
            edge[:-1] |= e
        else:
            edge[:, :-1] |= e
    img[edge] *= 0.25

    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    if supersample > 1:
        out = out.resize((w // supersample, h // supersample), Image.LANCZOS)
    return out


def contact_sheet(images: dict[str, Image.Image], columns: int = 3, pad: int = 16) -> Image.Image:
    """Tile labelled images into one sheet."""
    from PIL import ImageDraw

    items = list(images.items())
    label_h = 22
    rows = [items[i : i + columns] for i in range(0, len(items), columns)]
    cell_w = max(im.width for _, im in items)
    row_h = [max(im.height for _, im in row) + label_h for row in rows]
    sheet = Image.new(
        "RGB", (columns * (cell_w + pad) + pad, sum(row_h) + pad * (len(rows) + 1)), "white"
    )
    draw = ImageDraw.Draw(sheet)
    y = pad
    for row, height in zip(rows, row_h):
        for col, (name, im) in enumerate(row):
            x = pad + col * (cell_w + pad)
            draw.text((x, y), name, fill=(60, 60, 60))
            sheet.paste(im, (x + (cell_w - im.width) // 2, y + label_h))
        y += height + pad
    return sheet


def save(image: Image.Image, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path

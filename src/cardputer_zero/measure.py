"""Check the feature table against the official STL, and draw it.

Each housing face is turned into a recess map: how far the surface sits below
the housing's outermost plane on that side, at 0.05 mm per pixel, with
see-through pixels counted as infinitely deep. An "opening" is any pixel
recessed more than a feature's `recess` threshold.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

from .features import FACES, FEATURES, Feature
from .render import Raster, rasterize, render_mesh, view_frame

PX_PER_MM = 20
EDGE_TOLERANCE_MM = 0.1
_SCAN_MM = 0.5  # how far either side of a stated edge to look for the real one

KIND_COLORS = {
    "port": (220, 38, 38), "control": (234, 138, 0), "display": (37, 99, 235),
    "key": (22, 163, 74), "camera": (147, 51, 234), "audio": (8, 145, 178),
    "vent": (8, 145, 178), "mount": (120, 113, 108), "fastener": (120, 113, 108),
    "unknown": (219, 39, 119), "hidden": (120, 113, 108), "optical": (147, 51, 234),
    "indicator": (37, 99, 235), "cosmetic": (120, 113, 108),
}

# Sources that still deserve a look at a real unit, and how the sheet words them.
UNCONFIRMED = {
    "unknown": "purpose unknown",
    "inferred": "name is a guess",
    "reported": "reported by a reviewer, not seen directly",
}


@dataclass(frozen=True)
class RecessMap:
    raster: Raster
    recess: np.ndarray  # mm below the outer plane; inf where see-through

    def _uv(self, face: str, a, b):
        axes = FACES[face].axes
        right, up = self.raster.right, self.raster.up
        return (np.asarray(a) * right[axes[0]] + np.asarray(b) * right[axes[1]],
                np.asarray(a) * up[axes[0]] + np.asarray(b) * up[axes[1]])

    def window(self, face: str, a0: float, a1: float, b0: float, b1: float) -> np.ndarray:
        """Recess values inside an in-plane rectangle (at least one pixel)."""
        u, v = self._uv(face, [a0, a1], [b0, b1])
        cols, rows = self.raster.pixel(u, v)
        c0, c1 = sorted(int(round(c)) for c in cols)
        r0, r1 = sorted(int(round(r)) for r in rows)
        return self.recess[r0 : max(r1, r0 + 1), c0 : max(c1, c0 + 1)]

    def open_fraction(self, face: str, bounds, threshold: float) -> float:
        win = self.window(face, *bounds)
        return float((win > threshold).mean()) if win.size else 0.0

    def radial_fraction(self, face: str, center, r_in: float, r_out: float, threshold: float) -> float:
        """Open fraction of the ring r_in..r_out (a disc when r_in is 0)."""
        u, v = self._uv(face, center[0], center[1])
        col, row = self.raster.pixel(u, v)
        rows, cols = np.ogrid[: self.recess.shape[0], : self.recess.shape[1]]
        dist = np.hypot(cols + 0.5 - col, rows + 0.5 - row) / self.raster.px_per_mm
        ring = (dist >= r_in) & (dist <= r_out)
        return float((self.recess[ring] > threshold).mean())


def recess_maps(mesh: trimesh.Trimesh, faces=tuple(FACES)) -> dict[str, RecessMap]:
    maps = {}
    for face in faces:
        raster = rasterize(mesh.vertices, mesh.faces, face, px_per_mm=PX_PER_MM, margin_mm=1.0)
        hit = raster.face_id >= 0
        outer = raster.depth[hit].max()
        maps[face] = RecessMap(raster, np.where(hit, outer - raster.depth, np.inf))
    return maps


@dataclass(frozen=True)
class Check:
    feature: Feature
    ok: bool
    deviation_mm: float | None  # worst edge error, for edge-checked features
    detail: str


def _edge_error(rmap: RecessMap, f: Feature, axis: int, low_side: bool) -> float | None:
    """Signed distance from the stated edge to where the opening really starts."""
    a0, a1, b0, b1 = f.bounds
    lo, hi = (a0, a1) if axis == 0 else (b0, b1)
    t0, t1 = (b0, b1) if axis == 0 else (a0, a1)
    mid0, mid1 = t0 + 0.3 * (t1 - t0), t1 - 0.3 * (t1 - t0)  # middle 40 % of the side
    edge = lo if low_side else hi
    inward = 1.0 if low_side else -1.0
    step = 1.0 / PX_PER_MM
    previous = None
    for i in range(int(round(-_SCAN_MM / step)), int(round(_SCAN_MM / step)) + 1):
        p0 = edge + inward * i * step
        p1 = p0 + inward * step
        strip = (min(p0, p1), max(p0, p1), mid0, mid1) if axis == 0 else (mid0, mid1, min(p0, p1), max(p0, p1))
        is_open = rmap.open_fraction(f.face, strip, f.recess) >= 0.5
        if previous is None and is_open:
            return None  # already open well outside the stated edge
        if is_open:
            return i * step
        previous = is_open
    return None  # never opens


def check_feature(rmap: RecessMap, f: Feature) -> Check:
    if f.check == "edges":
        sides = {"a_min": (0, True), "a_max": (0, False), "b_min": (1, True), "b_max": (1, False)}
        errors = [_edge_error(rmap, f, *side) for name, side in sides.items() if name not in f.open_sides]
        if any(e is None for e in errors):
            return Check(f, False, None, "an edge of the opening was not found within 0.5 mm")
        worst = max(abs(e) for e in errors)
        return Check(f, worst <= EDGE_TOLERANCE_MM + 1e-9, worst, f"edges within {worst:.2f} mm")
    if f.check == "round":
        w, h = f.size
        inside = rmap.radial_fraction(f.face, f.center, 0.0, 0.7 * min(w, h) / 2, f.recess)
        rim = rmap.radial_fraction(f.face, f.center, 1.2 * max(w, h) / 2, 1.45 * max(w, h) / 2, f.recess)
        ok = inside >= 0.95 and rim <= 0.1
        return Check(f, ok, None, f"disc {inside:.0%} open, rim {rim:.0%} open")
    fraction = rmap.open_fraction(f.face, f.bounds, f.recess)
    return Check(f, fraction >= 0.1, None, f"{fraction:.0%} of the box is open")


def check_features(mesh: trimesh.Trimesh, features=FEATURES) -> list[Check]:
    maps = recess_maps(mesh, faces=tuple(dict.fromkeys(f.face for f in features)))
    return [check_feature(maps[f.face], f) for f in features]


def overlay_sheet(mesh: trimesh.Trimesh, face_colors: np.ndarray | None = None,
                  features=FEATURES, px_per_mm: float = 14.0) -> Image.Image:
    """Six face views with every feature box drawn and a numbered legend."""
    font = ImageFont.load_default(size=13)
    small = ImageFont.load_default(size=11)
    margin = 3.0
    panels = []
    for face, spec in FACES.items():
        img = render_mesh(mesh.vertices, mesh.faces, face, px_per_mm, margin, face_colors).convert("RGB")
        right, up, u_min, v_max = view_frame(mesh.vertices, face, margin)
        draw = ImageDraw.Draw(img)
        numbers: dict[str, int] = {}
        legend: list[tuple[int, Feature]] = []
        for f in (f for f in features if f.face == face):
            a0, a1, b0, b1 = f.bounds
            us = [a * right[spec.axes[0]] + b * right[spec.axes[1]] for a, b in ((a0, b0), (a1, b1))]
            vs = [a * up[spec.axes[0]] + b * up[spec.axes[1]] for a, b in ((a0, b0), (a1, b1))]
            x0, x1 = sorted((u - u_min) * px_per_mm for u in us)
            y0, y1 = sorted((v_max - v) * px_per_mm for v in vs)
            color = KIND_COLORS[f.kind]
            if f.shape == "rect":
                draw.rectangle((x0, y0, x1, y1), outline=color, width=2)
            elif f.shape == "round":
                draw.ellipse((x0, y0, x1, y1), outline=color, width=2)
            else:
                draw.rounded_rectangle((x0, y0, x1, y1), radius=min(x1 - x0, y1 - y0) / 2, outline=color, width=2)
            if f.kind == "key":
                continue
            if f.label not in numbers:
                numbers[f.label] = len(numbers) + 1
                legend.append((numbers[f.label], f))
                tag = str(numbers[f.label])
                tw = draw.textlength(tag, font=small)
                tx, ty = min(x0, img.width - tw - 4), max(y0 - 14, 0)
                draw.rectangle((tx - 1, ty, tx + tw + 2, ty + 13), fill="white")
                draw.text((tx + 1, ty), tag, fill=color, font=small)
        keys = sum(1 for f in features if f.face == face and f.kind == "key")
        lines = [f"{face.upper()}  (image axes: {spec.axis_names[0]}, {spec.axis_names[1]})"]
        if keys:
            lines.append(f"green outlines: {keys} key openings")
        lines += [f"{n}  {f.label}  [{f.source}]" for n, f in legend]
        panel = Image.new("RGB", (max(img.width, 520), img.height + 18 * len(lines) + 12), "white")
        panel.paste(img, (0, 0))
        text = ImageDraw.Draw(panel)
        for i, line in enumerate(lines):
            color = (30, 30, 30) if i == 0 or (keys and i == 1) else KIND_COLORS[legend[i - 1 - bool(keys)][1].kind]
            text.text((8, img.height + 4 + 18 * i), line, fill=color, font=font)
        panels.append(panel)

    order = [0, 1, 2, 3, 4, 5]  # front, back / top, bottom / left, right
    pad = 20
    col_w = [max(panels[i].width for i in order[c::2]) for c in (0, 1)]
    row_h = [max(panels[i].height for i in order[r * 2 : r * 2 + 2]) for r in range(3)]
    sheet = Image.new("RGB", (sum(col_w) + 3 * pad, sum(row_h) + 4 * pad), "white")
    y = pad
    for r in range(3):
        x = pad
        for c in range(2):
            sheet.paste(panels[order[r * 2 + c]], (x, y))
            x += col_w[c] + pad
        y += row_h[r] + pad
    return sheet


def confirm_sheet(mesh: trimesh.Trimesh, face_colors: np.ndarray | None = None,
                  features=FEATURES, px_per_mm: float = 20.0, pad_mm: float = 6.0) -> Image.Image | None:
    """Close-ups of every feature not yet confirmed against the real device, or None if there are none."""
    font = ImageFont.load_default(size=15)
    small = ImageFont.load_default(size=12)
    margin = 3.0
    groups: dict[tuple[str, str], list[Feature]] = {}
    for f in features:
        if f.source in UNCONFIRMED:
            groups.setdefault((f.face, f.label), []).append(f)
    if not groups:
        return None

    tile_w, tile_h, caption_h = 440, 300, 64
    tiles = []
    renders: dict[str, tuple] = {}
    for number, ((face, label), members) in enumerate(groups.items(), 1):
        if face not in renders:
            img = render_mesh(mesh.vertices, mesh.faces, face, px_per_mm, margin, face_colors).convert("RGB")
            renders[face] = (img, *view_frame(mesh.vertices, face, margin))
        img, right, up, u_min, v_max = renders[face]
        axes = FACES[face].axes

        def to_px(a, b):
            u = a * right[axes[0]] + b * right[axes[1]]
            v = a * up[axes[0]] + b * up[axes[1]]
            return (u - u_min) * px_per_mm, (v_max - v) * px_per_mm

        boxes = []
        for f in members:
            a0, a1, b0, b1 = f.bounds
            (x0, y0), (x1, y1) = to_px(a0, b0), to_px(a1, b1)
            boxes.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        pad = pad_mm * px_per_mm
        cx0 = max(min(b[0] for b in boxes) - pad, 0)
        cy0 = max(min(b[1] for b in boxes) - pad, 0)
        cx1 = min(max(b[2] for b in boxes) + pad, img.width)
        cy1 = min(max(b[3] for b in boxes) + pad, img.height)
        crop = img.crop((int(cx0), int(cy0), int(cx1), int(cy1)))
        scale = min(tile_w / crop.width, tile_h / crop.height)
        crop = crop.resize((max(int(crop.width * scale), 1), max(int(crop.height * scale), 1)), Image.LANCZOS)
        color = KIND_COLORS[members[0].kind]
        draw = ImageDraw.Draw(crop)
        for x0, y0, x1, y1 in boxes:
            draw.rectangle(((x0 - cx0) * scale, (y0 - cy0) * scale, (x1 - cx0) * scale, (y1 - cy0) * scale),
                           outline=color, width=3)

        tile = Image.new("RGB", (tile_w, tile_h + caption_h), "white")
        tile.paste(crop, ((tile_w - crop.width) // 2, (tile_h - crop.height) // 2))
        text = ImageDraw.Draw(tile)
        an, bn = FACES[face].axis_names
        a0 = min(f.bounds[0] for f in members); a1 = max(f.bounds[1] for f in members)
        b0 = min(f.bounds[2] for f in members); b1 = max(f.bounds[3] for f in members)
        count = f" (x{len(members)})" if len(members) > 1 else ""
        text.text((6, tile_h + 4), f"{number}. {label}{count}", fill=color, font=font)
        text.text((6, tile_h + 26), f"{face} face   {an} {a0:g}..{a1:g}   {bn} {b0:g}..{b1:g} mm", fill=(60, 60, 60), font=small)
        text.text((6, tile_h + 44), UNCONFIRMED[members[0].source], fill=(60, 60, 60), font=small)
        tiles.append(tile)

    columns, gap = 4, 16
    rows = -(-len(tiles) // columns)
    sheet = Image.new("RGB", (columns * (tile_w + gap) + gap, rows * (tile_h + caption_h + gap) + gap), "white")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (gap + (i % columns) * (tile_w + gap), gap + (i // columns) * (tile_h + caption_h + gap)))
    return sheet

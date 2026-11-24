"""Parametric keep-out model of the Cardputer Zero.

The keep-out is everything an enclosure must stay out of:
    body       the device itself (a chamfered box that contains the housing)
    keyboard   the key field, up to the keycap tops plus room for fingers
    access_*   a prism in front of each port, control, window and vent

Positions and sizes of the openings are measurements (features.py). The
margins and access depths below are design choices: change them to suit the
plugs, cables and fingers a particular enclosure has to clear.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from build123d import Axis, Box, Color, Compound, Cone, Pos, Rot, Solid, chamfer

from .features import (
    CORNER_CHAMFER,
    FEATURES,
    FRONT_FACE_Z,
    FRONT_RIB_Z,
    HALF_HEIGHT,
    HALF_WIDTH,
    KEY_TOP_Z,
    Feature,
)


@dataclass(frozen=True)
class Access:
    margin: float  # growth of the opening's footprint on every side, mm
    depth: float  # how far the clear volume extends out from the housing, mm


@dataclass(frozen=True)
class KeepoutParams:
    # Gap added around the device body on every side (fit clearance).
    body_clearance: float = 0.0
    corner_chamfer: float = CORNER_CHAMFER
    # Clear volume per kind of feature. Kinds left out get no volume.
    port: Access = Access(margin=1.5, depth=15.0)  # plug overmould and cable exit
    control: Access = Access(margin=1.0, depth=6.0)  # fingertip reach
    display: Access = Access(margin=1.0, depth=10.0)  # viewing
    # The camera's clear volume is a cone: it starts at the lens holder radius
    # plus the margin and widens by camera_half_angle_deg. 40 degrees covers the
    # stock IMX219 lens (about 77 degrees diagonal); a wide-angle lens needs more.
    camera: Access = Access(margin=0.5, depth=20.0)
    camera_half_angle_deg: float = 40.0
    optical: Access = Access(margin=1.0, depth=10.0)  # IR transmitter and receiver line of sight
    key: Access = Access(margin=1.0, depth=10.0)  # typing room above the keycaps
    indicator: Access = Access(margin=0.5, depth=3.0)  # status LEDs: keep them visible
    audio: Access = Access(margin=0.5, depth=3.0)  # speaker and microphone
    vent: Access = Access(margin=0.5, depth=3.0)
    unknown: Access = Access(margin=0.5, depth=3.0)  # unidentified openings: keep clear to be safe

    def access_for(self, kind: str) -> Access | None:
        return getattr(self, kind, None)


KIND_COLORS = {
    "body": (0.55, 0.58, 0.62), "port": (0.86, 0.15, 0.15), "control": (0.92, 0.54, 0.0),
    "display": (0.15, 0.39, 0.92), "key": (0.09, 0.64, 0.29), "camera": (0.58, 0.2, 0.92), "optical": (0.58, 0.2, 0.92),
    "audio": (0.03, 0.57, 0.70), "vent": (0.03, 0.57, 0.70), "unknown": (0.86, 0.15, 0.47),
    "indicator": (0.15, 0.39, 0.92),
}


def _box(lo, hi, label: str, kind: str) -> Solid:
    size = [h - l for l, h in zip(lo, hi)]
    center = [(l + h) / 2 for l, h in zip(lo, hi)]
    solid = (Pos(*center) * Box(*size)).solid()
    solid.label = label
    solid.color = Color(*KIND_COLORS[kind], 0.35)
    return solid


def body_solid(params: KeepoutParams = KeepoutParams()) -> Solid:
    c = params.body_clearance
    box = Pos(0, 0, FRONT_RIB_Z / 2) * Box(2 * HALF_WIDTH + 2 * c, 2 * HALF_HEIGHT + 2 * c, FRONT_RIB_Z + 2 * c)
    if params.corner_chamfer > 0:
        box = chamfer(box.edges().filter_by(Axis.Z), params.corner_chamfer)
    solid = box.solid()
    solid.label = "body"
    solid.color = Color(*KIND_COLORS["body"], 0.35)
    return solid


def body_contains(points: np.ndarray, params: KeepoutParams = KeepoutParams(), tol: float = 1e-3) -> np.ndarray:
    """Which points lie inside the body solid (same shape as body_solid, tested analytically)."""
    p = np.asarray(points, float)
    c = params.body_clearance + tol
    x, y = np.abs(p[:, 0]), np.abs(p[:, 1])
    return (
        (x <= HALF_WIDTH + c)
        & (y <= HALF_HEIGHT + c)
        & (p[:, 2] >= -c)
        & (p[:, 2] <= FRONT_RIB_Z + c)
        & (x + y <= HALF_WIDTH + HALF_HEIGHT + 2 * c - params.corner_chamfer)
    )


def keyboard_solid(params: KeepoutParams = KeepoutParams()) -> Solid | None:
    keys = [f for f in FEATURES if f.kind == "key"]
    access = params.access_for("key")
    if not keys or access is None:
        return None
    m = access.margin
    x0 = min(f.bounds[0] for f in keys) - m
    x1 = max(f.bounds[1] for f in keys) + m
    y0 = min(f.bounds[2] for f in keys) - m
    y1 = max(f.bounds[3] for f in keys) + m
    return _box((x0, y0, FRONT_FACE_Z), (x1, y1, KEY_TOP_Z + access.depth), "keyboard", "key")


def camera_cone(feature: Feature, params: KeepoutParams = KeepoutParams(), grow: float = 0.0) -> Solid:
    """Field-of-view cone of a camera on the back face, looking along -Z.

    Runs from 1 mm inside the back face out to the access depth. `grow`
    enlarges every radius, e.g. to make a shroud wall around the view.
    """
    if feature.face != "back":
        raise ValueError("camera_cone only handles a camera on the back face")
    access = params.camera
    cx, cy = feature.center
    r_near = max(feature.size) / 2 + access.margin + grow
    length = access.depth + 1.0
    r_far = r_near + length * math.tan(math.radians(params.camera_half_angle_deg))
    # The cone is turned so its seam line points down (-Y), into open space. With
    # the seam at the default +X it runs through a screw boss of the sensor pack
    # and the CAD kernel then returns a broken solid.
    solid = (Pos(cx, cy, 1.0 - length / 2) * Rot(0, 0, -90) * Cone(r_far, r_near, length)).solid()
    solid.label = f"access_{feature.name}"
    solid.color = Color(*KIND_COLORS["camera"], 0.35)
    return solid


def access_solid(feature: Feature, params: KeepoutParams = KeepoutParams()) -> Solid | None:
    """Clear volume in front of one feature, or None if its kind has none."""
    access = params.access_for(feature.kind)
    if access is None or feature.kind == "key":
        return None
    if feature.kind == "camera" and feature.face == "back":
        return camera_cone(feature, params)
    # Start 1 mm inside the outer plane so the volume overlaps the body.
    lo, hi = feature.world_box(outward=access.depth, inward=1.0, margin=access.margin)
    return _box(lo, hi, f"access_{feature.name}", feature.kind)


def keepout_parts(params: KeepoutParams = KeepoutParams()) -> dict[str, Solid]:
    parts = {"body": body_solid(params)}
    keyboard = keyboard_solid(params)
    if keyboard is not None:
        parts["keyboard"] = keyboard
    for feature in FEATURES:
        solid = access_solid(feature, params)
        if solid is not None:
            parts[solid.label] = solid
    return parts


def build_keepout(params: KeepoutParams = KeepoutParams()) -> Compound:
    """All keep-out solids as one labelled assembly."""
    return Compound(label="cardputer_zero_keepout", children=list(keepout_parts(params).values()))

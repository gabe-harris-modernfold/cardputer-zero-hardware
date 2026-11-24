"""Measured openings and external features of the Cardputer Zero housing.

Every box below was measured from M5Stack's official STL (depth maps at
0.05 mm resolution, see measure.py) in the canonical device frame, then named
by matching it against M5Stack's dimension drawing and product documentation.
`cz-build` re-checks each box against the STL on every run.

In-plane coordinates are world coordinates of the two axes that span the face:
    front, back   (X, Y)
    top, bottom   (X, Z)
    left, right   (Z, Y)
so bounds = (a_min, a_max, b_min, b_max) reads directly as world positions.

`source` says how sure the name is:
    drawing   shown and recognisable in the official dimension drawing
    docs      location stated in M5Stack's product documentation
    photo     confirmed from M5Stack product photos or the device's label artwork
    reported  stated by a third party (a reviewer), not seen directly
    inferred  named from its shape and size only; treat the name as a guess
    unknown   real opening in the housing, purpose not established
"""
from __future__ import annotations

from dataclasses import dataclass

# Housing levels on the front, from the STL and the dimension drawing.
FRONT_FACE_Z = 22.1  # main front surface
FRONT_RIB_Z = 23.1  # ribs beside the screen (the screen sits below them); published thickness
KEY_TOP_Z = 23.2  # keycap tops per the drawing (keycaps are not in the STL)

HALF_WIDTH = 42.0
HALF_HEIGHT = 27.0
# Largest chamfer on the four vertical corners that still clears the housing.
CORNER_CHAMFER = 1.75


@dataclass(frozen=True)
class Face:
    axes: tuple[int, int]  # world axis index of in-plane a and b
    normal_axis: int
    sign: int  # +1 if the face looks along the positive axis
    plane: float  # world coordinate of the housing's outermost point on that side

    @property
    def axis_names(self) -> tuple[str, str]:
        return ("XYZ"[self.axes[0]], "XYZ"[self.axes[1]])


FACES: dict[str, Face] = {
    "front": Face((0, 1), 2, +1, FRONT_RIB_Z),
    "back": Face((0, 1), 2, -1, 0.0),
    "top": Face((0, 2), 1, +1, HALF_HEIGHT),
    "bottom": Face((0, 2), 1, -1, -HALF_HEIGHT),
    "left": Face((2, 1), 0, -1, -HALF_WIDTH),
    "right": Face((2, 1), 0, +1, HALF_WIDTH),
}


@dataclass(frozen=True)
class Feature:
    name: str
    face: str
    bounds: tuple[float, float, float, float]  # a_min, a_max, b_min, b_max
    # port | control | display | key | indicator | camera | optical | audio | vent | mount |
    # fastener | hidden | cosmetic | unknown
    #   hidden    an opening in the bare housing that is covered on the finished device
    #   cosmetic  a recess with nothing behind it
    kind: str
    label: str
    source: str  # drawing | docs | photo | reported | inferred | unknown
    shape: str = "rect"  # rect | obround | round
    # How cz-build checks the box against the STL:
    #   edges    all four sides are opening edges
    #   round    open disc with a closed rim
    #   present  some opening lies inside the box (odd shapes, merged openings)
    check: str = "edges"
    recess: float = 3.0  # an "opening" is anything this far below the outer plane
    # Sides left out of the edge check because the opening runs into a
    # neighbouring one there: any of "a_min", "a_max", "b_min", "b_max".
    open_sides: tuple[str, ...] = ()
    note: str = ""

    @property
    def center(self) -> tuple[float, float]:
        a0, a1, b0, b1 = self.bounds
        return ((a0 + a1) / 2, (b0 + b1) / 2)

    @property
    def size(self) -> tuple[float, float]:
        a0, a1, b0, b1 = self.bounds
        return (a1 - a0, b1 - b0)

    def world_box(self, outward: float, inward: float = 0.0, margin: float = 0.0):
        """Axis-aligned box (min_xyz, max_xyz) standing on the face.

        outward/inward are measured from the housing's outer plane; margin
        grows the footprint on all four sides.
        """
        face = FACES[self.face]
        a0, a1, b0, b1 = self.bounds
        lo, hi = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        lo[face.axes[0]], hi[face.axes[0]] = a0 - margin, a1 + margin
        lo[face.axes[1]], hi[face.axes[1]] = b0 - margin, b1 + margin
        n0, n1 = sorted((face.plane - face.sign * inward, face.plane + face.sign * outward))
        lo[face.normal_axis], hi[face.normal_axis] = n0, n1
        return tuple(lo), tuple(hi)


def _centered(cx: float, cy: float, w: float, h: float):
    return (cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2)


# --- keyboard: 46 key holes, 4.8 x 2.8 mm, on a 7.5 x 6.5 mm grid -------------
KEY_SIZE = (4.8, 2.8)
KEY_PITCH = (7.5, 6.5)
KEY_COLUMNS_X = tuple(-37.5 + KEY_PITCH[0] * i for i in range(11))
KEY_ROWS_Y = (-4.0, -10.5, -17.0, -23.5)
KEY_EXTRA = ((-37.5, 2.5), (37.5, 2.5))  # the two keys beside the screen


def _keys() -> list[Feature]:
    keys = [
        Feature(f"key_r{r + 1}_c{c + 1}", "front", _centered(x, y, *KEY_SIZE), "key",
                "Key", "drawing", shape="obround")
        for r, y in enumerate(KEY_ROWS_Y) for c, x in enumerate(KEY_COLUMNS_X)
    ]
    keys += [
        Feature(f"key_top_{side}", "front", _centered(x, y, *KEY_SIZE), "key",
                "Key", "drawing", shape="obround")
        for side, (x, y) in zip(("left", "right"), KEY_EXTRA)
    ]
    return keys


FEATURES: tuple[Feature, ...] = (
    # ---- front -------------------------------------------------------------
    Feature("screen", "front", (-21.35, 21.35, 1.55, 24.25), "display",
            "Display window", "drawing", note="42.7 x 22.7, as dimensioned on the drawing"),
    *_keys(),
    Feature("power_switch", "front", (27.3, 31.7, 20.0, 24.0), "control",
            "Power slide switch", "photo",
            note="red slider under a POWER label, right of the screen; slides along X"),
    Feature("microphone", "front", (-33.5, -32.5, 1.0, 4.0), "audio",
            "Microphone port", "photo",
            note="1 x 3 slot beside the ESC key; a mic icon on the front label points at it"),
    *(Feature(f"led_{key}", "front", _centered(-39.0, y, 1.5, 1.5), "indicator",
              f"{key.capitalize()} indicator LED", "photo", shape="round", check="round",
              note="pinhole at the left end of the key legend strip")
      for key, y in (("sym", -7.25), ("shift", -13.75), ("fn", -20.25))),
    Feature("screw_left", "front", _centered(-29.0, 3.0, 3.9, 3.5), "fastener",
            "Housing screw", "drawing", shape="round", check="present",
            note="13.0 from the left edge, 24.0 from the top on the drawing"),
    Feature("screw_right", "front", _centered(28.0, 13.0, 3.9, 3.5), "fastener",
            "Housing screw", "drawing", shape="round", check="present",
            note="14.0 from the right edge, 14.0 from the top on the drawing"),
    # ---- back --------------------------------------------------------------
    Feature("camera", "back", _centered(0.0, 20.8, 7.3, 6.5), "camera",
            "Rear camera (IMX219, 8 MP)", "photo", shape="round", check="present",
            note="6.2 from the top edge on the drawing"),
    *(Feature(f"lego_back_{i + 1}", "back", _centered(x, 23.0, 4.8, 4.2), "mount",
              "Mounting hole, dia 4.9", "drawing", shape="round", check="round")
      for i, x in enumerate((-36.0, -20.0, 20.0, 36.0))),
    *(Feature(f"m2_insert_{i + 1}", "back", _centered(x, 23.0, 2.0, 2.0), "mount",
              "M2 threaded insert", "drawing", shape="round", check="present", recess=0.5,
              note="4-M2 on the drawing")
      for i, x in enumerate((-28.0, -14.0, 14.0, 28.0))),
    *(Feature(f"strap_slot_{side}", "back", (x - 2.3, x + 2.3, 21.3, 27.0), "mount",
              "Slot open to the top edge", "drawing", check="present", recess=0.5,
              note="4.6 wide, 11.7 deep from the back face, around an M2 insert")
      for side, x in (("left", -28.0), ("right", 28.0))),
    *(Feature(f"rear_pocket_{side}", "back", (x0, x1, 21.45, 25.55), "cosmetic",
              "Relief pocket behind a top mounting bore", "photo", check="present", recess=0.5,
              note="shallow 1 mm pocket beside the camera, in line with the top-face bore; no part behind it")
      for side, (x0, x1) in (("left", (-12.1, -5.15)), ("right", (5.15, 12.1)))),
    Feature("back_slot", "back", (-31.3, -18.7, -2.5, -1.5), "hidden",
            "Slot under the back label", "photo",
            note="12.6 x 1.0 through slot in the STL; the back label covers everything below the top strip"),
    *(Feature(f"corner_slot_back_{i + 1}", "back", (38.05, 42.0, y - 0.55, y + 0.55), "vent",
              "Corner slot near the speaker", "photo", open_sides=("a_max",),
              note="wraps round the edge onto the right side; keep open")
      for i, y in enumerate((-6.5, -9.5, -12.5))),
    # ---- top ---------------------------------------------------------------
    Feature("ext_header", "top", (-9.3, 9.3, 10.4, 16.1), "port",
            "EXT 2.54-14P expansion header", "photo",
            note="full width from Z 10.75; the centre 12 mm reaches down to Z 10.4; "
                 "pin order is in EXT_PINOUT"),
    Feature("microsd", "top", (-23.9, -12.0, 16.9, 18.9), "port",
            "microSD card slot", "photo", note="labelled microSD on the device"),
    Feature("ir_rx", "top", (-33.45, -27.55, 16.9, 20.1), "optical",
            "IR receiver window", "photo", shape="obround",
            note="black window at the -X end of the top edge"),
    Feature("top_slot", "top", (-4.2, 4.0, 18.45, 19.65), "hidden",
            "Slot under the pin-map label", "photo",
            note="8.2 x 1.2 slot in front of the EXT header, covered by the pin-map sticker"),
    Feature("ir_tx", "top", (33.25, 34.75, 16.9, 19.1), "optical",
            "IR transmitter LED", "photo", note="small hole at the +X end of the top edge"),
    *(Feature(f"lego_top_{i + 1}", "top", _centered(x, 4.0, 4.8, 4.2), "mount",
              "Mounting hole, dia 4.9", "drawing", shape="round", check="round")
      for i, x in enumerate((-8.0, 8.0))),
    *(Feature(f"top_vent_{i + 1}", "top", _centered(x, 8.55, 0.7, 2.8), "vent",
              "Vent slot", "drawing", shape="obround")
      for i, x in enumerate((-21.0, -18.0, -15.0, -12.0, 12.0, 15.0, 18.0, 21.0))),
    # ---- bottom ------------------------------------------------------------
    *(Feature(f"bottom_slot_{i + 1}", "bottom", _centered(-10.5 + 3.0 * i, 13.2, 0.7, 4.2), "audio",
              "Speaker grille slot", "reported", shape="obround",
              note="a reviewer places the speaker outlet on the bottom edge")
      for i in range(8)),
    Feature("bottom_recess", "bottom", (-7.95, 7.95, 3.4, 5.25), "cosmetic",
            "Shallow recess on the bottom edge", "photo", check="present", recess=0.3,
            note="15.9 x 1.85, 1 mm deep, sloped; not an opening"),
    # ---- left --------------------------------------------------------------
    Feature("usb_a", "left", (8.7, 14.8, 6.3, 19.75), "port", "USB-A 2.0", "photo",
            open_sides=("a_max",), note="runs into the USB switch notch on its front side"),
    Feature("usb_switch", "left", (14.8, 16.1, 11.0, 15.0), "control",
            "USB hub switch (USB-SW)", "photo", open_sides=("a_min",),
            note="small slider in a notch between USB-A and USB C1; the Host/Slave switch in the docs"),
    Feature("usb_c_left", "left", (16.9, 20.25, 8.5, 17.5), "port",
            "USB Type-C, USB C1", "photo", shape="obround"),
    Feature("ethernet", "left", (2.0, 15.8, -22.2, -5.8), "port",
            "RJ45 Ethernet 10/100M", "photo"),
    Feature("boot_button", "left", (13.4, 20.4, -3.05, 4.05), "control",
            "BOOT button", "photo", check="present",
            note="flexing tab; the USB-switch (green) and system-status (red) lights shine "
                 "through the gap at its two edges"),
    # ---- right -------------------------------------------------------------
    Feature("usb_c_right", "right", (16.9, 20.25, 8.5, 17.5), "port",
            "USB Type-C, USB C2 (OTG, charging)", "photo", shape="obround", check="present",
            note="merges with the PORT.X opening behind it"),
    Feature("grove", "right", (10.5, 16.0, 7.0, 19.0), "port",
            "PORT.X (HY2.0-4P)", "photo", check="present",
            note="stepped outline; bounds are its bounding box"),
    Feature("audio_jack", "right", (11.25, 16.25, -2.2, 3.1), "port",
            "3.5 mm audio in/out", "photo", shape="round", check="round"),
    Feature("hdmi", "right", (9.6, 15.5, -21.4, -6.2), "port",
            "HDMI display out", "photo",
            note="trapezoidal outline; bounds are its bounding box"),
    Feature("lanyard_loop", "right", (2.0, 5.5, 13.1, 19.1), "mount",
            "Lanyard loop (fixed)", "photo", check="present", recess=0.6,
            note="a fixed bar across a pocket, not a switch; gets no keep-clear volume by default"),
    *(Feature(f"corner_slot_right_{i + 1}", "right", (0.0, 4.35, y - 0.55, y + 0.55), "vent",
              "Corner slot near the speaker", "photo", open_sides=("a_min",),
              note="wraps round the edge onto the back; keep open")
      for i, y in enumerate((-6.5, -9.5, -12.5))),
)

# EXT header pin map, read from the label on the device. Each row runs from
# the +X end (device's right) to the -X end; "front" is the row nearer +Z.
EXT_PINOUT = {
    "front": ("G26 / USB D+", "G23 / USB D-", "G22", "G11 / SPI CLK", "G10 / SPI MOSI",
              "G9 / SPI MISO", "G7 / SPI CS1"),
    "back": ("5V IN", "GND", "5V OUT", "G2 / I2C SDA", "G3 / I2C SCL", "G14 / UART TX", "G15 / UART RX"),
}

FEATURES_BY_NAME: dict[str, Feature] = {f.name: f for f in FEATURES}


def by_kind(*kinds: str) -> list[Feature]:
    return [f for f in FEATURES if f.kind in kinds]

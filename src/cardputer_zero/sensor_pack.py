"""Sensor pack: a tray that extends the back of the Cardputer Zero.

The pack is one printed part. It is an open tray whose rim sits on the
device's back face, so the device's back closes the cavity:

    tray      84 x 54 footprint, `clear_depth` of free space, `wall` thick
    bosses    four M2 clearance holes over the back inserts, counterbored
              from the outside
    shroud    a conical tube that keeps the rear camera's view clear and
              keeps wiring out of it
    relief    a walled notch that leaves the three corner slots near the
              speaker open to the air
    root      a wiring duct on top of the tray's top wall, behind the
              device's top edge, with two chutes down into the cavity
    lip       an open channel lying on the device's top face that carries a
              2x7 pin header down into the EXT socket
    tripod    a boss on the bottom edge with a hole for a 1/4"-20 heat-set
              insert, on a small raised pad

Assembly: hold the pack against the back about 7 mm high, slide it down so
the header enters the EXT socket, then fit the screws. Because of that slide
nothing on the pack may reach forward of the back face (Z > 0) except the
lip, so the pack has no locating pegs.

All positions are in the canonical device frame; the pack occupies Z < 0.
"""
from __future__ import annotations

from dataclasses import dataclass

from build123d import Axis, Box, Cylinder, Part, Pos, Rot, chamfer

from .features import CORNER_CHAMFER, FEATURES_BY_NAME, HALF_HEIGHT, HALF_WIDTH
from .keepout import KeepoutParams, camera_cone


@dataclass(frozen=True)
class SensorPackParams:
    clear_depth: float = 10.0  # free depth inside the tray
    wall: float = 2.0  # outer wall and perimeter walls (FDM, 0.4 mm nozzle)
    fit_clearance: float = 0.3  # gap between the lip and the device's top face

    # M2 screws into the back inserts. The inner pair sits at the back face;
    # the outer pair sits about 11.7 mm down inside the strap slots.
    screw_xs: tuple[float, ...] = (-28.0, -14.0, 14.0, 28.0)
    screw_y: float = 23.0
    screw_clearance_d: float = 2.4
    screw_head_d: float = 4.4
    boss_d: float = 6.0
    screw_seat: float = 2.0  # material left under the screw head

    shroud_wall: float = 1.6  # wall of the camera shroud

    # Relief around the three corner slots (back face X 38..42, Y -13..-6).
    relief_x_min: float = 37.5
    relief_y: tuple[float, float] = (-13.6, -5.4)
    relief_depth: float = 3.5

    # EXT plug: a 2x7, 2.54 mm pin header (body 17.78 x 5.08 x 2.54).
    header_center_z: float = 13.4
    header_slot: tuple[float, float] = (18.0, 5.3)  # along X, along Z
    lip_half_width: float = 10.4  # limited by the microSD slot and the top vents
    lip_floor: float = 2.5  # header body height, so the header sits flush in the floor
    channel_half_width: float = 9.1
    channel_height: float = 4.5
    lip_end_wall: float = 1.5

    # Wiring duct behind the top edge, and the chutes down into the cavity.
    root_half_width: float = 24.5
    root_depth: float = 5.5
    root_channel_z: tuple[float, float] = (-3.5, -1.0)  # shallow enough to stay above the camera cone
    chute_x: tuple[float, float] = (17.5, 23.0)

    # Tripod mount: a heat-set insert pressed into the bottom edge, thread axis
    # along Y, centred in the pack's thickness. Defaults suit a standard
    # 1/4"-20 UNC insert, 12.7 mm long and about 8 mm across; the hole diameter
    # differs between makers, so set it from the insert's own datasheet.
    tripod_x: float = 0.0
    tripod_insert_hole_d: float = 8.0
    tripod_insert_length: float = 12.7
    # Free hole beyond the insert for displaced plastic. A 12.7 mm insert takes
    # a whole tripod screw; with a short insert raise this to about 3 mm.
    tripod_screw_runout: float = 1.0
    tripod_boss_wall: float = 3.0  # material either side of the hole, along X
    tripod_end_wall: float = 2.0  # material closing the hole inside the cavity
    # A raised pad round the insert, so a tripod plate stands off the device's
    # bottom edge instead of lying over the speaker grille. 0 makes it flush.
    tripod_pad_height: float = 1.5
    tripod_pad_half_width: float = 12.0

    @property
    def depth(self) -> float:
        """Total thickness the pack adds behind the device."""
        return self.clear_depth + self.wall

    @property
    def tripod_hole_depth(self) -> float:
        return self.tripod_insert_length + self.tripod_screw_runout

    @property
    def tripod_face_y(self) -> float:
        """Y of the surface the tripod plate seats on."""
        return -HALF_HEIGHT - self.tripod_pad_height

    @property
    def tripod_wall_z(self) -> float:
        """Material left between the insert hole and each face of the pack."""
        return (self.depth - self.tripod_insert_hole_d) / 2

    @property
    def top_y(self) -> float:
        """Highest point of the lip and root."""
        return HALF_HEIGHT + self.fit_clearance + self.lip_floor + self.channel_height


def _box(x, y, z) -> Part:
    (x0, x1), (y0, y1), (z0, z1) = x, y, z
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def _footprint(z0: float, z1: float, inset: float = 0.0, corner: float = CORNER_CHAMFER) -> Part:
    block = _box((-HALF_WIDTH + inset, HALF_WIDTH - inset), (-HALF_HEIGHT + inset, HALF_HEIGHT - inset), (z0, z1))
    return chamfer(block.edges().filter_by(Axis.Z), corner) if corner > 0 else block


def build_sensor_pack(p: SensorPackParams = SensorPackParams(),
                      keepout: KeepoutParams = KeepoutParams()) -> Part:
    back = -p.depth  # outer face of the pack
    floor = -p.clear_depth  # inside face of the outer wall
    camera = FEATURES_BY_NAME["camera"]
    top = HALF_HEIGHT
    lip_y0 = top + p.fit_clearance
    channel_y0 = lip_y0 + p.lip_floor
    top_y = p.top_y
    over = top_y + 1.0  # cut tools run past the open top of the channels

    # ---- tray ---------------------------------------------------------------
    outline = _footprint(back, 0.0)
    # An inward offset of the chamfered outline keeps the wall even at the corners.
    inner_corner = max(CORNER_CHAMFER - p.wall * (2 - 2**0.5), 0.0)
    pack = outline - _footprint(floor, 0.0, inset=p.wall, corner=inner_corner)

    # ---- things that stand in the cavity -------------------------------------
    for x in p.screw_xs:
        pack += Pos(x, p.screw_y, back / 2) * Cylinder(p.boss_d / 2, p.depth)
    pack += camera_cone(camera, keepout, grow=p.shroud_wall) & outline
    ry0, ry1 = p.relief_y
    pack += _box((p.relief_x_min - p.wall, HALF_WIDTH - p.wall), (ry0 - p.wall, ry1 + p.wall),
                 (-p.relief_depth - p.wall, 0.0))

    # ---- tripod boss on the bottom edge ---------------------------------------
    boss_half = p.tripod_insert_hole_d / 2 + p.tripod_boss_wall
    face_y = p.tripod_face_y
    boss_end_y = face_y + p.tripod_hole_depth + p.tripod_end_wall
    pack += _box((p.tripod_x - boss_half, p.tripod_x + boss_half), (-HALF_HEIGHT, boss_end_y), (back, 0.0))
    if p.tripod_pad_height > 0:
        pack += _box((p.tripod_x - p.tripod_pad_half_width, p.tripod_x + p.tripod_pad_half_width),
                     (face_y, -HALF_HEIGHT), (back, 0.0))

    # ---- wiring duct behind the top edge, and the lip over the top face ------
    cz0, cz1 = p.root_channel_z
    pack += _box((-p.root_half_width, p.root_half_width), (top - p.wall, top_y), (-p.root_depth, 0.0))
    lip_end = p.header_center_z + p.header_slot[1] / 2 + 0.4 + p.lip_end_wall
    pack += _box((-p.lip_half_width, p.lip_half_width), (lip_y0, top_y), (0.0, lip_end))

    duct_half = p.chute_x[1]
    pack -= _box((-duct_half, duct_half), (channel_y0, over), (cz0, cz1))  # cross duct
    pack -= _box((-p.channel_half_width, p.channel_half_width), (channel_y0, over),
                 (cz1 - 0.01, lip_end - p.lip_end_wall))  # lip channel, joined to the duct
    for sign in (-1, 1):
        x0, x1 = sorted((sign * p.chute_x[0], sign * p.chute_x[1]))
        pack -= _box((x0, x1), (top - p.wall - 0.1, channel_y0 + 0.01), (cz0, cz1))  # chute into the cavity
    sx, sz = p.header_slot
    pack -= _box((-sx / 2, sx / 2), (lip_y0 - 1.0, channel_y0 + 0.01),
                 (p.header_center_z - sz / 2, p.header_center_z + sz / 2))

    # ---- openings -------------------------------------------------------------
    pack -= camera_cone(camera, keepout)
    for x in p.screw_xs:
        pack -= Pos(x, p.screw_y, back / 2) * Cylinder(p.screw_clearance_d / 2, p.depth + 2)
        head_len = p.depth - p.screw_seat
        pack -= Pos(x, p.screw_y, back + head_len / 2 - 0.5) * Cylinder(p.screw_head_d / 2, head_len + 1.0)
    pack -= _box((p.relief_x_min, HALF_WIDTH + 1.0), (ry0, ry1), (-p.relief_depth, 1.0))
    # Insert hole: runs up (+Y) from the tripod face; the cylinder is turned onto the Y axis.
    hole_len = p.tripod_hole_depth + 1.0
    pack -= (Pos(p.tripod_x, face_y - 1.0 + hole_len / 2, back / 2) * Rot(90, 0, 0)
             * Cylinder(p.tripod_insert_hole_d / 2, hole_len))
    return pack

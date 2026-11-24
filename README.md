# Cardputer Zero Hardware

CAD workspace for designing and simulating enclosures for the M5Stack
Cardputer Zero (SKU C154). Code-first CAD with
[build123d](https://build123d.readthedocs.io) in a uv-managed environment.

## Quick start

```bash
uv run cz-build
```

This reads M5Stack's official housing model, checks it, checks the measured
openings against it, builds the keep-out model, and writes `out/`:

| File | What it is |
|---|---|
| `cardputer_zero_housing.step` | Two-part B-rep assembly (front + back shell) for any CAD tool |
| `cardputer_zero_keepout.step` | Keep-out model: body, keyboard zone and one access volume per opening |
| `sensor_pack.step`, `sensor_pack.stl` | The back extension (see Sensor pack below) |
| `sensor_pack.png` | The sensor pack on the device and on its own |
| `front_shell.stl`, `back_shell.stl` | Repaired meshes in the canonical frame |
| `features.csv` | Every measured opening: face, bounds, size, name, how it was identified |
| `openings.png` | The six faces with every measured opening drawn on and numbered |
| `to_confirm.png` | Close-ups of the openings not yet confirmed first-hand (absent when there are none) |
| `preview.png` | Eight-view contact sheet of the housing |
| `cardputer_zero.glb` | Housing + keep-out for the browser viewer |

To look at the model interactively, serve the project folder and open the viewer:

```bash
uv run python -m http.server 8123 --bind 127.0.0.1
```

then browse to <http://localhost:8123/viewer/>. The viewer loads three.js from
the jsDelivr CDN, so it needs internet access.

## Canonical device frame

All geometry is in millimetres with the origin at the centre of the
84 x 54 footprint, on the back face:

- `+X` right edge when looking at the screen
- `+Y` top edge (EXT header side)
- `+Z` out of the screen / keyboard face

The device occupies X -42..42, Y -27..27, Z 0..23.1.

## Layout

- `reference/official/` - files from M5Stack, unmodified
  - `CardputerZero.stl` from
    [m5stack/M5_Hardware](https://github.com/m5stack/M5_Hardware/tree/master/Products/C154_CardputerZero/Structures)
    (MIT, see `reference/official/LICENSE`)
  - `C154_CardputerZero_model_size.pdf` dimension drawing - not in the repo
    (no stated license); download it from
    [docs.m5stack.com](https://docs.m5stack.com/en/CardputerZero) into this
    folder if you want it alongside
- `src/cardputer_zero/`
  - `reference.py` - loads the official STL, splits it into shells, moves it
    to the canonical frame, repairs the mesh
  - `brep.py` - converts a closed mesh into a build123d solid
  - `features.py` - the table of measured openings (ports, screen, keys, ...)
  - `measure.py` - checks that table against the STL and draws `openings.png`
  - `keepout.py` - the parametric keep-out model
  - `sensor_pack.py` - the back extension that plugs into the EXT header
  - `render.py` - headless orthographic renderer for quick PNG previews
  - `build.py` - the `cz-build` command
- `viewer/index.html` - three.js viewer (part and keep-out toggles, explode, view presets)

## Measured openings

`features.py` holds 108 features: the display window, 46 key openings and 61
ports, controls, indicators, mounting points, vents and recesses. Each is a box in
world coordinates on one face (front/back use X,Y; top/bottom X,Z; left/right
Z,Y). `cz-build` re-measures the STL on every run and fails if a box no longer
matches; 82 boxes are checked edge by edge to 0.1 mm, the rest (round holes
and odd-shaped or merged openings) by a weaker open-area test.

The main ones:

| Feature | Face | Bounds (mm) | Size | Named from |
|---|---|---|---|---|
| Display window | front | X -21.35..21.35, Y 1.55..24.25 | 42.7 x 22.7 | drawing |
| Keys (46) | front | 11 columns from X -37.5, pitch 7.5; rows Y -4, -10.5, -17, -23.5; two more at (-37.5, 2.5) and (37.5, 2.5) | 4.8 x 2.8 each | drawing |
| Power slide switch | front | X 27.3..31.7, Y 20.0..24.0 | 4.4 x 4.0 | photo |
| Microphone port | front | X -33.5..-32.5, Y 1.0..4.0 | 1.0 x 3.0 | photo |
| Sym / Shift / Fn LEDs | front | X -39 at Y -7.25, -13.75, -20.25 | dia 1.5 | photo |
| USB-A | left | Z 8.7..14.8, Y 6.3..19.75 | 6.1 x 13.45 | photo |
| USB hub switch (USB-SW) | left | Z 14.8..16.1, Y 11.0..15.0 | 1.3 x 4.0 | photo |
| USB-C "C1" | left | Z 16.9..20.25, Y 8.5..17.5 | 3.35 x 9.0 | photo |
| BOOT button + two status lights | left | Z 13.4..20.4, Y -3.05..4.05 | 7.0 x 7.1 | photo |
| RJ45 Ethernet | left | Z 2.0..15.8, Y -22.2..-5.8 | 13.8 x 16.4 | photo |
| USB-C "C2" (OTG, charging) | right | Z 16.9..20.25, Y 8.5..17.5 | 3.35 x 9.0 | photo |
| PORT.X (HY2.0-4P) | right | Z 10.5..16.0, Y 7.0..19.0 | 5.5 x 12.0 | photo |
| 3.5 mm audio | right | Z 11.25..16.25, Y -2.2..3.1 | dia ~5.3 | photo |
| HDMI display out | right | Z 9.6..15.5, Y -21.4..-6.2 | 5.9 x 15.2 | photo |
| Corner slots near the speaker (3) | back + right | Y -6.5, -9.5, -12.5, each 1.1 wide; back X 38.05..42, right Z 0..4.35 | | photo |
| Lanyard loop (fixed) | right | Z 2.0..5.5, Y 13.1..19.1 | 3.5 x 6.0 | photo |
| EXT 2.54-14P header | top | X -9.3..9.3, Z 10.4..16.1 | 18.6 x 5.7 | photo |
| microSD slot | top | X -23.9..-12.0, Z 16.9..18.9 | 11.9 x 2.0 | photo |
| IR receiver window | top | X -33.45..-27.55, Z 16.9..20.1 | 5.9 x 3.2 | photo |
| IR transmitter LED | top | X 33.25..34.75, Z 16.9..19.1 | 1.5 x 2.2 | photo |
| Rear camera (full model only) | back | centre X 0, Y 20.8 | dia ~7 | photo |
| Speaker grille (8 slots) | bottom | X -10.5..10.5 pitch 3, Z 11.1..15.3 | 0.7 x 4.2 each | reported |
| Mounting holes dia 4.9 | back, top | back: X +-20, +-36 at Y 23; top: X +-8 at Z 4 | | drawing |
| M2 inserts | back | X +-14, +-28 at Y 23 | | drawing |

How far to trust the names:

- **photo** - matched to M5Stack's labelled product photos and label artwork
  (31 features).
- **drawing** - recognisable and dimensioned in the official dimension drawing
  (the display, keys, mounting holes, inserts, screws, top vents).
- **reported** - the eight bottom grille slots are the speaker outlet according
  to a reviewer; not seen directly.

Nothing is left unidentified. `out/to_confirm.png` lists whatever is not yet
confirmed first-hand, which is now only the speaker grille.

Three things in the bare housing get no keep-clear volume: a slot in front of
the EXT header (under the pin-map label), a slot in the back (under the back
label), and cosmetic recesses (two pockets beside the camera, one on the
bottom edge). The lanyard loop and the mounting points get none either; give
the lanyard room yourself if the enclosure should keep it usable.

`EXT_PINOUT` in `features.py` records the header's pin order as printed on
that label.

Front surface levels: main face Z 22.1, ribs beside the screen Z 23.1 (the
screen sits below the ribs), keycap tops Z 23.2 (from the drawing; keycaps are
not in the STL and this height has not been measured on a unit).

## Keep-out model

`keepout.py` turns the feature table into solids an enclosure must stay out of:

- `body` - an 84 x 54 x 23.1 box with 1.75 mm chamfers on the vertical corners;
  every vertex of the official housing lies inside it
- `keyboard` - the key field from the front face to the keycap tops plus typing room
- `access_<feature>` - a prism standing on each port, control, window and vent;
  the rear camera gets a field-of-view cone instead (40 degree half-angle by
  default, which covers the stock lens but not a wide-angle one)

```python
from build123d import Box, Pos
from cardputer_zero.keepout import Access, KeepoutParams, keepout_parts

params = KeepoutParams(
    body_clearance=0.3,                     # fit gap around the device
    port=Access(margin=2.0, depth=20.0),    # room for plugs and cables
)
case = Pos(0, 0, 11.55) * Box(90, 60, 29.1)   # 3 mm of material all round
for solid in keepout_parts(params).values():
    case -= solid
```

The opening positions are measurements. The margins and depths in
`KeepoutParams` are design defaults, not measurements: 15 mm deep with a
1.5 mm margin for ports, 6 mm for controls, 10 mm for the display, camera, IR
parts and keys, 3 mm for vents, the speaker, the microphone and the indicator LEDs. Mounting holes and screws get
no volume. Adjust them for the plugs your enclosure actually has to clear.

## Sensor pack (back extension)

`sensor_pack.py` builds a one-piece tray that screws onto the back of the
device and plugs into the EXT header, giving 10 mm of clear depth for sensors
and wiring. The device's back face closes the cavity.

| | |
|---|---|
| Added behind the device | 12.0 mm (10.0 clear + 2.0 outer wall) |
| Added above the top edge | 7.3 mm, over a 49 mm wide strip |
| Added below the bottom edge | 1.5 mm, over a 24 mm wide tripod pad |
| Overall | 84.0 x 62.8 x 30.0 mm |
| Material | 17.9 cm^3, about 22 g in PLA if printed solid |

What it consists of:

- **Tray** - the device's 84 x 54 footprint, 2 mm walls.
- **Four screw bosses** over the M2 inserts (X +-14 and +-28, Y 23), with
  2.4 mm clearance holes counterbored from the outside to leave 2 mm under
  the screw head.
- **Camera shroud** - a conical tube around the rear camera's field of view,
  so nothing in the cavity can get in front of the lens.
- **Corner slot relief** - a walled notch that leaves the three slots near
  the speaker open.
- **EXT lip** - an open channel on the device's top face with a slot for a
  2x7, 2.54 mm pin header; the header body sits flush in the 2.5 mm floor.
- **Wiring duct** - behind the top edge, running sideways from the lip to two
  5.5 x 2.5 mm chutes that drop into the cavity either side of the camera.

- **Tripod mount** - a boss in the middle of the bottom edge with a blind hole
  for a 1/4"-20 heat-set insert, thread axis pointing down. The hole is
  8.0 mm across and 13.7 mm deep (a standard 12.7 mm insert plus 1 mm for
  displaced plastic). It sits on a pad raised 1.5 mm so a tripod plate stands off the
  device's bottom edge instead of lying over the speaker grille. The boss
  takes a 14 x 12 mm bite out of the cavity floor area at the bottom centre.

Assembly is a slide: hold the pack against the back about 7 mm high, slide it
down so the header enters the EXT socket, then fit the screws. Because of the
slide the pack has no locating pegs; the header and screws locate it.

`cz-build` checks that the pack is one valid solid, does not overlap the
official housing, enters no keep-out volume except the EXT header's, and has
its full clear depth, and that the tripod hole is an open blind hole of the
stated depth.

Not yet verified, and worth checking before printing:

- **Outer screws.** The inserts at X +-28 sit about 11.7 mm down inside the
  strap slots, so those two need roughly M2x16; the inner two take about
  M2x5. Insert depths are read from the STL, not measured on a unit.
- **EXT socket height.** The STL has no socket, so how far the pins must
  reach is unknown; the header slot is open so the header can be set by hand.
- **Camera lens.** The shroud assumes the stock lens. It cuts into the two
  inner screw counterbores near the outer face, which is harmless.
- **Lip walls** are 1.3 mm, thinner than the rest, to clear the microSD slot.
- **One row of screws.** All four are along the top edge, so the bottom edge
  of the pack is held only by the tray's stiffness.
- **Tripod insert.** The length is set for a standard 12.7 mm 1/4"-20 insert.
  The 8.0 mm hole diameter is a default: it differs between makers and must
  be set from the datasheet of the insert you buy. The pack is 12 mm thick, so only
  2.0 mm of plastic remains in front of and behind an 8 mm hole; a larger
  insert leaves less. On a tripod the device hangs from the four top screws.
- The four 4.9 mm mounting holes on the back are covered by the pack.

Every dimension is a field of `SensorPackParams`.

## Using the model in a design script

```python
from cardputer_zero.reference import load_reference
from cardputer_zero.brep import mesh_to_solid

ref = load_reference()                     # trimesh meshes, canonical frame
back = mesh_to_solid(ref.back_shell)       # build123d Solid
```

Run scripts that read the downloaded reference files with `uv run python -I`.

## What the official model is, and is not

- It is the plastic housing only: front shell (Z 14.0..23.1) and back shell
  (Z 0..19.9). There are no keycaps, display, PCB, connectors or battery.
- Its overall size matches the published 84.0 x 54.0 x 23.1 mm exactly.
- The official back shell has a ~0.01 mm sliver that leaves two edges shared
  by four triangles. `reference.py` collapses it (five vertices moved, surface
  shift under 0.02 mm) so the CAD kernel accepts the shell as a valid solid.
- The B-rep solids are faceted: flat regions are merged into real planar
  faces, but curved surfaces stay as strips of small planes, which is why the
  STEP file is about 18 MB.

## License

MIT, see `LICENSE`. The files in `reference/official/` are M5Stack's and carry
their own MIT license, see `reference/official/LICENSE`.

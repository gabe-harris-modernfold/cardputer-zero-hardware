"""Build the reference device model and the keep-out model.

Run with:  uv run cz-build

Writes to out/:
    cardputer_zero_housing.step   two-part B-rep assembly (front + back shell)
    cardputer_zero_keepout.step   body, keyboard and access volumes (keepout.py)
    front_shell.stl, back_shell.stl   repaired meshes in the canonical frame
    cardputer_zero.glb            housing + keep-out, for viewer/index.html
    features.csv                  every measured opening
    sensor_pack.step, sensor_pack.stl   the back extension (sensor_pack.py)
    preview.png                   eight-view contact sheet of the housing
    openings.png                  six faces with the measured openings drawn on
    to_confirm.png                close-ups of the openings not yet confirmed first-hand
    sensor_pack.png               the sensor pack on the device and on its own
and checks the housing against M5Stack's published size, the feature table
against the housing, the keep-out body against the housing, and the sensor
pack against both the housing and the keep-out.
"""
from __future__ import annotations

import csv
import sys
import time

import numpy as np
import trimesh
from build123d import Box, Color, Compound, Cylinder, Pos, Rot, export_step, export_stl

from . import OUT_DIR
from .brep import is_valid, mesh_to_solid, volume_error
from .features import FACES, FEATURES
from .keepout import KeepoutParams, body_contains, build_keepout
from .measure import check_features, confirm_sheet, overlay_sheet
from .reference import NOMINAL_SIZE, is_manifold, load_reference
from .render import VIEWS, contact_sheet, render_mesh, save
from .sensor_pack import SensorPackParams, build_sensor_pack

PART_COLORS = {"front_shell": (0.86, 0.86, 0.84), "back_shell": (0.42, 0.45, 0.50)}
PACK_COLOR = (0.93, 0.55, 0.16)
SIZE_TOLERANCE_MM = 0.05
VOLUME_TOLERANCE = 1e-3
# Keep-out volumes the sensor pack is meant to occupy: it plugs into the EXT header.
PACK_ALLOWED_ACCESS = {"access_ext_header"}
PLA_DENSITY_G_PER_CM3 = 1.24


def _common_volume(a, b) -> float:
    common = a & b
    return 0.0 if common is None else sum(s.volume for s in common.solids())


def _material(name: str, rgb, alpha: float = 1.0):
    return trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            name=name, baseColorFactor=[*rgb, alpha], metallicFactor=0.0, roughnessFactor=0.75,
            alphaMode="BLEND" if alpha < 1 else "OPAQUE",
        )
    )


def _solid_to_mesh(solid) -> trimesh.Trimesh:
    vertices, triangles = solid.tessellate(0.05)
    return trimesh.Trimesh([tuple(v) for v in vertices], triangles, process=False)


def _write_features_csv(path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "face", "kind", "label", "source", "shape", "axis_a", "a_min", "a_max",
                         "axis_b", "b_min", "b_max", "width", "height", "note"])
        for f in FEATURES:
            a, b = FACES[f.face].axis_names
            a0, a1, b0, b1 = f.bounds
            writer.writerow([f.name, f.face, f.kind, f.label, f.source, f.shape, a, f"{a0:.2f}", f"{a1:.2f}",
                             b, f"{b0:.2f}", f"{b1:.2f}", f"{a1 - a0:.2f}", f"{b1 - b0:.2f}", f.note])


def main() -> int:
    started = time.time()
    OUT_DIR.mkdir(exist_ok=True)
    ref = load_reference()
    failures: list[str] = []

    # ---- housing -----------------------------------------------------------
    print("Official housing, canonical frame (mm)")
    size = ref.size
    print(f"  size      {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f}"
          f"   (published {NOMINAL_SIZE[0]} x {NOMINAL_SIZE[1]} x {NOMINAL_SIZE[2]})")
    if np.abs(size - NOMINAL_SIZE).max() > SIZE_TOLERANCE_MM:
        failures.append("overall size differs from the published dimensions")
    if ref.debris_faces:
        print(f"  dropped   {ref.debris_faces} stray sliver triangles")
    for name, fix in ref.repairs.items():
        print(f"  repaired  {name}: {fix.pinched_edges} pinched edges, {fix.vertices_moved} vertices "
              f"moved, surface shift {fix.surface_shift_mm:.3f} mm, volume {fix.volume_change_mm3:+.2f} mm^3")

    solids = []
    for name, mesh in ref.parts.items():
        solid = mesh_to_solid(mesh)
        solid.label = name
        solid.color = Color(*PART_COLORS[name])
        solids.append(solid)
        lo, hi = mesh.bounds
        valid = is_valid(solid)
        err = volume_error(solid, mesh)
        print(f"  {name:<12} Z {lo[2]:.2f}..{hi[2]:.2f}  {len(mesh.faces)} triangles -> "
              f"{len(solid.faces())} B-rep faces, volume {solid.volume:.1f} mm^3, "
              f"valid solid: {valid}")
        if not is_manifold(mesh):
            failures.append(f"{name} mesh is not a closed manifold")
        if not valid:
            failures.append(f"{name} B-rep solid failed the kernel validity check")
        if err > VOLUME_TOLERANCE:
            failures.append(f"{name} solid volume is off by {err:.2%} from the mesh")
        mesh.export(OUT_DIR / f"{name}.stl")
    export_step(Compound(label="cardputer_zero_housing", children=solids),
                OUT_DIR / "cardputer_zero_housing.step")

    # ---- measured openings ---------------------------------------------------
    whole = ref.assembled
    checks = check_features(whole)
    edge_checked = [c for c in checks if c.deviation_mm is not None]
    worst = max((c.deviation_mm for c in edge_checked), default=0.0)
    passed = sum(c.ok for c in checks)
    print(f"\nFeature table vs housing: {passed} of {len(checks)} features confirmed")
    print(f"  {len(edge_checked)} checked edge by edge, worst edge error {worst:.2f} mm")
    by_source: dict[str, int] = {}
    for f in FEATURES:
        if f.kind != "key":
            by_source[f.source] = by_source.get(f.source, 0) + 1
    print("  naming (excluding the 46 keys): " + ", ".join(f"{n} {s}" for s, n in sorted(by_source.items())))
    for c in checks:
        if not c.ok:
            failures.append(f"feature {c.feature.name} does not match the housing: {c.detail}")
    _write_features_csv(OUT_DIR / "features.csv")

    # ---- keep-out model ------------------------------------------------------
    params = KeepoutParams()
    keepout = build_keepout(params)
    outside = int((~body_contains(whole.vertices, params)).sum())
    invalid = [part.label for part in keepout.children if not is_valid(part)]
    print(f"\nKeep-out model: {len(keepout.children)} solids "
          f"(body, keyboard, {len(keepout.children) - 2} access volumes)")
    print(f"  housing vertices outside the body: {outside} of {len(whole.vertices)}")
    if outside:
        failures.append(f"{outside} housing vertices fall outside the keep-out body")
    if invalid:
        failures.append(f"invalid keep-out solids: {', '.join(invalid)}")
    export_step(keepout, OUT_DIR / "cardputer_zero_keepout.step")

    # ---- sensor pack ---------------------------------------------------------
    pack_params = SensorPackParams()
    pack = build_sensor_pack(pack_params, params)
    pack.label = "sensor_pack"
    pack.color = Color(*PACK_COLOR)
    pack_mesh = _solid_to_mesh(pack)
    box = pack.bounding_box()
    pack_solids = len(pack.solids())
    pack_valid = is_valid(pack)
    mesh_volume_error = abs(float(pack_mesh.volume) - pack.volume) / pack.volume
    housing_overlap = sum(_common_volume(pack, solid) for solid in solids)
    blocked = {part.label: _common_volume(pack, part) for part in keepout.children}
    blocked = {name: vol for name, vol in blocked.items() if vol > 1e-3}
    unexpected = sorted(set(blocked) - PACK_ALLOWED_ACCESS)
    # Probe the cavity: a block just under the clear depth must meet no material.
    probe_depth = pack_params.clear_depth - 0.02
    probes = [(0.0, 0.0), (-30.0, 0.0), (30.0, -20.0), (-20.0, -22.0), (33.0, 5.0)]
    cavity_hits = [xy for xy in probes
                   if _common_volume(pack, Pos(*xy, -pack_params.clear_depth / 2) * Box(4, 4, probe_depth)) > 1e-3]

    # Tripod insert hole: a pin just under the hole size must slide in to full
    # depth, and a longer one must hit the end wall (the hole is blind).
    def tripod_pin(length: float):
        return (Pos(pack_params.tripod_x, pack_params.tripod_face_y - 0.5 + length / 2, -pack_params.depth / 2)
                * Rot(90, 0, 0) * Cylinder(pack_params.tripod_insert_hole_d / 2 - 0.05, length))

    tripod_open = _common_volume(pack, tripod_pin(pack_params.tripod_hole_depth + 0.45)) < 1e-3
    tripod_blind = _common_volume(pack, tripod_pin(pack_params.tripod_hole_depth + 1.5)) > 1e-3
    print(f"\nSensor pack: {box.max.X - box.min.X:.1f} x {box.max.Y - box.min.Y:.1f} x "
          f"{box.max.Z - box.min.Z:.1f} mm overall, adds {pack_params.depth:.1f} mm behind the device "
          f"and {pack_params.top_y - 27.0:.1f} mm above its top edge")
    print(f"  clear depth inside {pack_params.clear_depth:.1f} mm, walls {pack_params.wall:.1f} mm, "
          f"material {pack.volume / 1000:.1f} cm^3 (about {pack.volume / 1000 * PLA_DENSITY_G_PER_CM3:.0f} g "
          f"in PLA if printed solid)")
    print(f"  one valid solid: {pack_solids == 1 and pack_valid}; overlap with the housing: "
          f"{housing_overlap:.3f} mm^3")
    print("  keep-out volumes it enters: " + (", ".join(sorted(blocked)) or "none")
          + "  (the EXT header is intended)")
    print(f"  tripod insert hole: dia {pack_params.tripod_insert_hole_d:.1f} x {pack_params.tripod_hole_depth:.1f} mm deep "
          f"in the bottom edge at X {pack_params.tripod_x:g}, {pack_params.tripod_wall_z:.1f} mm of wall front and back, "
          f"seat {pack_params.tripod_pad_height:.1f} mm below the device's bottom edge")
    if not (tripod_open and tripod_blind):
        failures.append("tripod insert hole is not an open blind hole of the stated depth")
    if pack_params.tripod_wall_z < 1.6:
        failures.append(f"only {pack_params.tripod_wall_z:.1f} mm of wall around the tripod insert")
    if pack_solids != 1 or not pack_valid:
        failures.append("sensor pack is not one valid solid")
    if mesh_volume_error > 5e-3:
        failures.append(f"sensor pack volume disagrees with its tessellation by {mesh_volume_error:.1%}")
    if housing_overlap > 0.5:
        failures.append(f"sensor pack overlaps the housing by {housing_overlap:.1f} mm^3")
    if unexpected:
        failures.append("sensor pack blocks: " + ", ".join(unexpected))
    if PACK_ALLOWED_ACCESS - set(blocked):
        failures.append("sensor pack no longer reaches the EXT header")
    if cavity_hits:
        failures.append(f"sensor pack cavity is not clear at {cavity_hits}")
    export_step(pack, OUT_DIR / "sensor_pack.step")
    export_stl(pack, OUT_DIR / "sensor_pack.stl")

    # ---- viewer model and images ---------------------------------------------
    scene = trimesh.Scene()
    for name, mesh in ref.parts.items():
        part = mesh.copy()
        part.visual = _material(name, PART_COLORS[name])
        scene.add_geometry(part, node_name=f"housing__{name}", geom_name=f"housing__{name}")
    for part in keepout.children:
        group = "keepout" if part.label in ("body", "keyboard") else "access"
        label = part.label.removeprefix("access_")
        mesh = _solid_to_mesh(part)
        mesh.visual = _material(part.label, tuple(part.color)[:3], 0.3)
        scene.add_geometry(mesh, node_name=f"{group}__{label}", geom_name=f"{group}__{label}")
    viewer_pack = pack_mesh.copy()
    viewer_pack.visual = _material("sensor_pack", PACK_COLOR)
    scene.add_geometry(viewer_pack, node_name="pack__sensor_pack", geom_name="pack__sensor_pack")
    scene.export(OUT_DIR / "cardputer_zero.glb")
    (OUT_DIR / "cardputer_zero_housing.glb").unlink(missing_ok=True)  # superseded

    colors = np.concatenate(
        [np.tile(PART_COLORS[name], (len(mesh.faces), 1)) for name, mesh in ref.parts.items()]
    )
    images = {view: render_mesh(whole.vertices, whole.faces, view, px_per_mm=9, face_colors=colors)
              for view in VIEWS}
    save(contact_sheet(images, columns=2), OUT_DIR / "preview.png")
    save(overlay_sheet(whole, colors), OUT_DIR / "openings.png")
    unconfirmed = confirm_sheet(whole, colors)
    if unconfirmed is not None:
        save(unconfirmed, OUT_DIR / "to_confirm.png")
    else:
        (OUT_DIR / "to_confirm.png").unlink(missing_ok=True)

    fitted_vertices = np.vstack([whole.vertices, pack_mesh.vertices])
    fitted_faces = np.vstack([whole.faces, pack_mesh.faces + len(whole.vertices)])
    pack_colors = np.tile(PACK_COLOR, (len(pack_mesh.faces), 1))
    fitted_colors = np.vstack([colors, pack_colors])
    pack_images = {f"fitted: {view}": render_mesh(fitted_vertices, fitted_faces, view, px_per_mm=8,
                                                  face_colors=fitted_colors)
                   for view in ("iso_back", "iso", "back", "top", "right", "bottom")}
    pack_images |= {f"pack alone: {view}": render_mesh(pack_mesh.vertices, pack_mesh.faces, view,
                                                       px_per_mm=8, face_colors=pack_colors)
                    for view in ("front", "iso")}
    save(contact_sheet(pack_images, columns=2), OUT_DIR / "sensor_pack.png")

    print(f"\nWrote {OUT_DIR} in {time.time() - started:.0f}s:")
    for path in sorted(OUT_DIR.iterdir()):
        if path.is_file():
            print(f"  {path.name:<32} {path.stat().st_size / 1024:8.0f} kB")
    if failures:
        print("\nFAILED checks:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

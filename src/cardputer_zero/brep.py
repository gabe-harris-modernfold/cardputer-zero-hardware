"""Turn a closed triangle mesh into a build123d B-rep solid.

Each triangle becomes a planar face, the faces are sewn into a shell, and
coplanar neighbours are merged so the result has real CAD faces (and a much
smaller STEP file) instead of thousands of triangles.
"""
from __future__ import annotations

import trimesh
from build123d import Shape, Solid
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt
from OCP.ShapeFix import ShapeFix_Solid
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


def _volume(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def mesh_to_solid(mesh: trimesh.Trimesh, sew_tolerance: float = 1e-4, unify: bool = True) -> Solid:
    """Convert a closed mesh to a Solid. Raises ValueError if it will not close."""
    pts = [gp_Pnt(*map(float, v)) for v in mesh.vertices]
    sewing = BRepBuilderAPI_Sewing(sew_tolerance)
    for (a, b, c), area in zip(mesh.faces, mesh.area_faces):
        if area < 1e-10:
            continue
        wire = BRepBuilderAPI_MakePolygon(pts[a], pts[b], pts[c], True).Wire()
        face = BRepBuilderAPI_MakeFace(wire, True)
        if face.IsDone():
            sewing.Add(face.Face())
    sewing.Perform()
    sewn = sewing.SewedShape()

    # Sewing returns one shell for a clean mesh; pick the largest if the mesh
    # had touching slivers that sewed into extra shells.
    shells = []
    explorer = TopExp_Explorer(sewn, TopAbs_SHELL)
    while explorer.More():
        shells.append(TopoDS.Shell(explorer.Current()))
        explorer.Next()
    if not shells:
        raise ValueError("sewing produced no closed shell")
    solids = []
    for shell in shells:
        fixer = ShapeFix_Solid(BRepBuilderAPI_MakeSolid(shell).Solid())
        fixer.Perform()
        solids.append(TopoDS.Solid(fixer.Solid()))
    solid = max(solids, key=lambda s: abs(_volume(s)))
    if _volume(solid) < 0:
        solid = TopoDS.Solid(solid.Reversed())

    if unify:
        unifier = ShapeUpgrade_UnifySameDomain(solid, True, True, True)
        unifier.Build()
        solid = TopoDS.Solid(unifier.Shape())
    return Solid(solid)


def is_valid(shape: Shape) -> bool:
    return BRepCheck_Analyzer(shape.wrapped).IsValid()


def volume_error(solid: Solid, mesh: trimesh.Trimesh) -> float:
    """Relative difference between the solid's volume and the source mesh's."""
    return abs(solid.volume - float(mesh.volume)) / float(mesh.volume)

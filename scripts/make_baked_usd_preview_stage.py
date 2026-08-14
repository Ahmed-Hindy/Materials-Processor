"""Create a Karma-ready grid preview stage for baked Blender material USD.

This only builds simple UV-mapped planes and binds the converted materials. Run
Houdini's ``husk`` against the resulting stage to validate that the downstream
renderer can resolve every baked texture and MaterialX shader.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdRender, UsdShade


def _create_plane(
    stage: Usd.Stage, path: Sdf.Path, center_x: float, center_y: float, material: UsdShade.Material
) -> None:
    """Create one UV-mapped plane and bind a material from the baked USD layer."""
    mesh = UsdGeom.Mesh.Define(stage, path)
    half_size = 1.0
    mesh.CreatePointsAttr(
        [
            (center_x - half_size, center_y - half_size, 0.0),
            (center_x + half_size, center_y - half_size, 0.0),
            (center_x + half_size, center_y + half_size, 0.0),
            (center_x - half_size, center_y + half_size, 0.0),
        ]
    )
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    mesh.CreateNormalsAttr([(0.0, 0.0, 1.0)] * 4)
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    primvars = UsdGeom.PrimvarsAPI(mesh)
    primvars.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying).Set(
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    )
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)


def _create_albedo_material(
    stage: Usd.Stage, material_path: Sdf.Path, source_material: UsdShade.Material
) -> UsdShade.Material:
    """Create a MaterialX emission material driven only by baked base color."""
    source_surface = source_material.GetSurfaceOutput("mtlx")
    source = source_surface.GetConnectedSource() if source_surface else None
    if not source:
        raise ValueError(f"Material has no connected MaterialX surface: {source_material.GetPath()}")
    source_shader = UsdShade.Shader(source[0].GetPrim())
    base_color = source_shader.GetInput("base_color")
    if not base_color or not base_color.HasConnectedSource():
        raise ValueError(f"Material has no connected baked base color: {source_material.GetPath()}")
    base_source = base_color.GetConnectedSource()

    material = UsdShade.Material.Define(stage, material_path)
    emission = UsdShade.Shader.Define(stage, material_path.AppendChild("emission"))
    emission.CreateIdAttr("ND_surface_unlit")
    emission.CreateInput("emission_color", Sdf.ValueTypeNames.Color3f).ConnectToSource(base_source[0], base_source[1])
    emission.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mtlx").ConnectToSource(emission.ConnectableAPI(), "out")
    material.CreateSurfaceOutput("kma").ConnectToSource(emission.ConnectableAPI(), "out")
    return material


def _create_normal_vector_material(
    stage: Usd.Stage, material_path: Sdf.Path, source_material: UsdShade.Material
) -> UsdShade.Material:
    """Visualize the raw encoded tangent-space normal texture."""
    source_surface = source_material.GetSurfaceOutput("mtlx")
    source = source_surface.GetConnectedSource() if source_surface else None
    if not source:
        raise ValueError(f"Material has no connected MaterialX surface: {source_material.GetPath()}")
    source_shader = UsdShade.Shader(source[0].GetPrim())
    normal = source_shader.GetInput("normal")
    if not normal or not normal.HasConnectedSource():
        raise ValueError(f"Material has no connected baked normal map: {source_material.GetPath()}")
    normal_source = normal.GetConnectedSource()
    normal_shader = UsdShade.Shader(normal_source[0].GetPrim())
    file_input = normal_shader.GetInput("file")
    texcoord_input = normal_shader.GetInput("texcoord")
    if not file_input or not texcoord_input or not texcoord_input.HasConnectedSource():
        raise ValueError(f"Material has no texture-backed baked normal map: {source_material.GetPath()}")

    material = UsdShade.Material.Define(stage, material_path)
    image = UsdShade.Shader.Define(stage, material_path.AppendChild("normal_raw_image"))
    image.CreateIdAttr("ND_image_color3")
    raw_file = image.CreateInput("file", Sdf.ValueTypeNames.Asset)
    raw_file.Set(file_input.Get())
    raw_file.GetAttr().SetColorSpace(file_input.GetAttr().GetColorSpace() or "raw")
    image.CreateInput("texcoord", Sdf.ValueTypeNames.Float2).ConnectToSource(
        texcoord_input.GetConnectedSource()[0], texcoord_input.GetConnectedSource()[1]
    )
    image.CreateOutput("out", Sdf.ValueTypeNames.Color3f)
    emission = UsdShade.Shader.Define(stage, material_path.AppendChild("emission"))
    emission.CreateIdAttr("ND_surface_unlit")
    emission.CreateInput("emission_color", Sdf.ValueTypeNames.Color3f).ConnectToSource(image.ConnectableAPI(), "out")
    emission.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mtlx").ConnectToSource(emission.ConnectableAPI(), "out")
    material.CreateSurfaceOutput("kma").ConnectToSource(emission.ConnectableAPI(), "out")
    return material


def create_preview_stage(
    materials_usd: Path,
    output_usd: Path,
    *,
    albedo_only: bool = False,
    normal_vectors: bool = False,
    geometry_usd: Path | None = None,
    material_name: str | None = None,
) -> list[str]:
    """Compose baked MaterialX USD with ten geometry previews and optional lights."""
    materials_usd = materials_usd.resolve()
    output_usd.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(output_usd))
    stage.GetRootLayer().subLayerPaths.append(str(materials_usd).replace("\\", "/"))
    if geometry_usd:
        stage.GetRootLayer().subLayerPaths.append(str(geometry_usd.resolve()).replace("\\", "/"))
    stage.SetMetadata("upAxis", "Y")
    stage.SetMetadata("metersPerUnit", 1.0)

    material_scope = stage.GetPrimAtPath("/materials")
    material_names = sorted(child.GetName() for child in material_scope.GetChildren() if child.IsA(UsdShade.Material))
    if not material_names:
        raise ValueError(f"No USD materials were found under /materials in {materials_usd}")
    if material_name:
        if material_name not in material_names:
            raise ValueError(f"Material {material_name!r} was not found in {materials_usd}")
        material_names = [material_name]

    if geometry_usd:
        mesh_paths = [prim.GetPath() for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)]
        camera_paths = [prim.GetPath() for prim in stage.Traverse() if prim.IsA(UsdGeom.Camera)]
        if len(mesh_paths) != 1:
            raise ValueError(f"Comparison geometry must contain exactly one mesh, found: {mesh_paths}")
        if len(camera_paths) != 1:
            raise ValueError(f"Comparison geometry must contain exactly one camera, found: {camera_paths}")
        material = UsdShade.Material(stage.GetPrimAtPath(f"/materials/{material_names[0]}"))
        if albedo_only:
            material = _create_albedo_material(stage, Sdf.Path(f"/albedo_materials/{material_names[0]}"), material)
        elif normal_vectors:
            material = _create_normal_vector_material(
                stage, Sdf.Path(f"/normal_materials/{material_names[0]}"), material
            )
        UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(mesh_paths[0])).Bind(material)
    else:
        UsdGeom.Xform.Define(stage, "/preview")
    for index, name in enumerate(material_names):
        if geometry_usd:
            break
        material = UsdShade.Material(stage.GetPrimAtPath(f"/materials/{name}"))
        if albedo_only:
            material = _create_albedo_material(stage, Sdf.Path(f"/albedo_materials/{name}"), material)
        elif normal_vectors:
            material = _create_normal_vector_material(stage, Sdf.Path(f"/normal_materials/{name}"), material)
        # A single material is a focused inspection render, not a one-item
        # five-column grid. Center it so the resulting beauty image is useful
        # for visual validation.
        center_x = 0.0 if len(material_names) == 1 else (index % 5) * 2.25 - 4.5
        center_y = 0.0 if len(material_names) == 1 else -(index // 5) * 2.25 + 1.125
        _create_plane(stage, Sdf.Path(f"/preview/{name}"), center_x, center_y, material)

    camera = (
        UsdGeom.Camera(stage.GetPrimAtPath(camera_paths[0]))
        if geometry_usd
        else UsdGeom.Camera.Define(stage, "/camera")
    )
    # Match the Blender reference grid camera: 50 mm focal length on a 36 mm
    # horizontal sensor rendered at 1000x420.  Without these apertures USD's
    # smaller default aperture crops the material grid, invalidating a
    # pixel-for-pixel albedo comparison.
    if not geometry_usd:
        camera.CreateHorizontalApertureAttr(36.0)
        camera.CreateVerticalApertureAttr(15.12)
        camera.CreateFocalLengthAttr(50.0)
        camera.AddTranslateOp().Set((0.0, 0.0, 13.0))

    render_settings = UsdRender.Settings.Define(stage, "/Render/Settings")
    render_settings.CreateCameraRel().SetTargets([camera.GetPath()])
    render_settings.CreateResolutionAttr(Gf.Vec2i(1000, 420))
    stage.SetMetadata(UsdRender.Tokens.renderSettingsPrimPath, render_settings.GetPath().pathString)

    if not geometry_usd and not albedo_only and not normal_vectors:
        key = UsdLux.RectLight.Define(stage, "/lights/key")
        key.CreateIntensityAttr(2.0)
        key.CreateWidthAttr(9.0)
        key.CreateHeightAttr(9.0)
        key.AddTranslateOp().Set((0.0, 0.0, 8.0))
        fill = UsdLux.RectLight.Define(stage, "/lights/fill")
        fill.CreateIntensityAttr(0.5)
        fill.CreateWidthAttr(6.0)
        fill.CreateHeightAttr(6.0)
        fill.AddTranslateOp().Set((-2.0, 2.0, 4.0))

    stage.SetDefaultPrim(
        stage.GetPrimAtPath("/preview") if not geometry_usd else stage.GetPrimAtPath(mesh_paths[0]).GetParent()
    )
    stage.GetRootLayer().Save()
    return material_names


def main() -> int:
    """Create the stage and print the material count for shell validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materials_usd", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--albedo-only", action="store_true")
    parser.add_argument("--normal-vectors", action="store_true")
    parser.add_argument(
        "--geometry", type=Path, help="USD geometry, camera, and lights exported from the Cycles comparison scene."
    )
    parser.add_argument("--material", help="Restrict the preview to one named material in the input USD.")
    args = parser.parse_args()
    if args.albedo_only and args.normal_vectors:
        parser.error("--albedo-only and --normal-vectors are mutually exclusive")
    materials = create_preview_stage(
        args.materials_usd,
        args.output.resolve(),
        albedo_only=args.albedo_only,
        normal_vectors=args.normal_vectors,
        geometry_usd=args.geometry,
        material_name=args.material,
    )
    print(f"Created preview stage with {len(materials)} materials: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

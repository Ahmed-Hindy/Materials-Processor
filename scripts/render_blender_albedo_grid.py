"""Render Blender material-property references through Cycles Shader AOVs.

The default captures the evaluated Principled Base Color stream. ``--mode
normal-vector`` captures the tangent-space normal encoded as ``normal * 0.5 +
0.5``. The source material's surface output remains untouched, preventing a
beauty/render-output setting from contaminating the diagnostic stream.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from materials_processor.dcc.blender.runtime import resolve_blender_runtime


def _script(
    scene_path: Path,
    output_path: Path,
    samples: int,
    mode: str,
    baked_normal_dir: Path | None = None,
    material_name: str | None = None,
    geometry_path: Path | None = None,
) -> str:
    """Return Blender Python that renders sorted material streams as emission."""
    return f"""
import bpy
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath={str(scene_path)!r})
scene = bpy.context.scene
BAKED_NORMAL_DIR = {str(baked_normal_dir) if baked_normal_dir else None!r}
MATERIAL_NAME = {material_name!r}
GEOMETRY_PATH = {str(geometry_path) if geometry_path else None!r}
scene.render.engine = "CYCLES"
scene.use_nodes = False
scene.cycles.samples = {samples!r}
scene.render.resolution_x = 1000
scene.render.resolution_y = 420
scene.render.resolution_percentage = 100
if {str(output_path).lower().endswith(".exr")!r}:
    # EXR preserves the Blender scene-linear result.  This is the format to use
    # when comparing against a Karma render; a PNG has already had a display
    # transform applied and is not a numerical albedo reference.
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "32"
else:
    scene.render.image_settings.file_format = "PNG"
# Some imported scenes carry an ACES display transform that Blender also
# applies to a render. Property diagnostics must bypass it: this applies to
# EXR numerical references and to normal-map PNGs intended for direct visual
# comparison against a Husk output saved with ``--ocio 0``.
if {mode!r} == "normal-vector" or {str(output_path).lower().endswith(".exr")!r}:
    for view_transform in ("Raw", "Standard"):
        try:
            scene.view_settings.view_transform = view_transform
            break
        except TypeError:
            continue
scene.render.filepath = {str(output_path)!r}
if scene.world:
    # Source files can use a node-based world, which overrides ``world.color``.
    # Disable it so source and USD preview renders share the same black backdrop.
    scene.world.use_nodes = False
    scene.world.color = (0.0, 0.0, 0.0)

objects = sorted(
    (obj for obj in scene.objects if obj.type == "MESH" and obj.data.materials and obj.data.materials[0]),
    key=lambda obj: obj.data.materials[0].name,
)
if MATERIAL_NAME:
    objects = [obj for obj in objects if obj.data.materials[0].name == MATERIAL_NAME]
if not objects:
    raise RuntimeError("No mesh-assigned material matched the requested source material")
if MATERIAL_NAME:
    # A focused comparison must not include a neighbouring mesh from the
    # source scene, even if it happens to fall within the camera frame.
    for obj in scene.objects:
        if obj.type == "MESH":
            obj.hide_render = obj not in objects
AOV_NAME = "materials_processor_reference"
view_layer = scene.view_layers[0]
for aov in list(view_layer.aovs):
    if aov.name == AOV_NAME:
        view_layer.aovs.remove(aov)
reference_aov = view_layer.aovs.add()
reference_aov.name = AOV_NAME
reference_aov.type = "COLOR"
if BAKED_NORMAL_DIR:
    from pathlib import Path
    import re

    for obj in objects:
        material = obj.data.materials[0]
        output = next(node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial" and node.is_active_output)
        shader = output.inputs["Surface"].links[0].from_node
        normal = shader.inputs["Normal"]
        normal_map = normal.links[0].from_node if normal.is_linked else None
        image_node = normal_map.inputs["Color"].links[0].from_node if normal_map and normal_map.inputs["Color"].is_linked else None
        path = Path(BAKED_NORMAL_DIR) / f"{{re.sub(r'[^A-Za-z0-9_.-]+', '_', material.name).strip('_') or 'material'}}_normal.exr"
        if image_node is None or image_node.bl_idname != "ShaderNodeTexImage" or not path.is_file():
            raise RuntimeError(f"Could not replace normal for {{material.name}} with {{path}}")
        image_node.image = bpy.data.images.load(str(path), check_existing=False)
        # The baked normal is already evaluated in the object's UV space. Do
        # not apply the source Mapping node a second time when validating it.
        vector_input = image_node.inputs["Vector"]
        mapping = vector_input.links[0].from_node if vector_input.is_linked else None
        if mapping and mapping.bl_idname == "ShaderNodeMapping" and mapping.inputs["Vector"].is_linked:
            source_vector = mapping.inputs["Vector"].links[0].from_socket
            material.node_tree.links.remove(vector_input.links[0])
            material.node_tree.links.new(source_vector, vector_input)
        for candidate in ("Utility - Raw", "Raw", "Non-Color"):
            try:
                image_node.image.colorspace_settings.name = candidate
                break
            except TypeError:
                pass
for index, obj in enumerate(objects):
    material = obj.data.materials[0]
    output_nodes = [node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial"]
    output = next((node for node in output_nodes if node.is_active_output), output_nodes[0])
    shader = output.inputs["Surface"].links[0].from_node
    if shader.bl_idname != "ShaderNodeBsdfPrincipled":
        raise RuntimeError(f"{{material.name}} does not have a directly connected Principled BSDF")
    aov = material.node_tree.nodes.new(type="ShaderNodeOutputAOV")
    aov.name = AOV_NAME
    aov.aov_name = AOV_NAME
    if {mode!r} == "albedo":
        base_color = shader.inputs["Base Color"]
        if base_color.is_linked:
            material.node_tree.links.new(base_color.links[0].from_socket, aov.inputs["Color"])
        else:
            aov.inputs["Color"].default_value = base_color.default_value
    else:
        normal = shader.inputs["Normal"]
        normal_map = normal.links[0].from_node if normal.is_linked else None
        # A direct Normal Map node has an already encoded tangent-space texture.
        # Capture that raw colour stream rather than its shading-space output:
        # it is the exact quantity written by the PBR normal bake and consumed
        # by MaterialX's glTF normal-map node.
        if normal_map and normal_map.bl_idname == "ShaderNodeNormalMap":
            normal_color = normal_map.inputs["Color"]
            if normal_color.is_linked:
                material.node_tree.links.new(normal_color.links[0].from_socket, aov.inputs["Color"])
            else:
                aov.inputs["Color"].default_value = normal_color.default_value
        else:
            # Procedural/Bump normal networks have no portable encoded texture
            # to inspect. This is only a visual fallback, not an acceptance
            # comparison against a tangent-space baked normal map.
            if normal.is_linked:
                normal_output = normal.links[0].from_socket
            else:
                normal_map = material.node_tree.nodes.new(type="ShaderNodeNormalMap")
                normal_map.inputs["Color"].default_value = (0.5, 0.5, 1.0, 1.0)
                normal_output = normal_map.outputs["Normal"]
            scale = material.node_tree.nodes.new(type="ShaderNodeVectorMath")
            scale.operation = "SCALE"
            scale.inputs[3].default_value = 0.5
            offset = material.node_tree.nodes.new(type="ShaderNodeVectorMath")
            offset.operation = "ADD"
            offset.inputs[1].default_value = (0.5, 0.5, 0.5)
            material.node_tree.links.new(normal_output, scale.inputs[0])
            material.node_tree.links.new(scale.outputs["Vector"], offset.inputs[0])
            material.node_tree.links.new(offset.outputs["Vector"], aov.inputs["Color"])
    if len(objects) != 1:
        obj.location = ((index % 5) * 2.25 - 4.5, -(index // 5) * 2.25 + 1.125, 0.0)

camera_data = bpy.data.cameras.new("materials_processor_albedo_camera")
camera = bpy.data.objects.new("materials_processor_albedo_camera", camera_data)
scene.collection.objects.link(camera)
if len(objects) == 1:
    # Do not move the source object: Object-coordinate procedural materials
    # would then evaluate differently from their bake. Frame the original
    # world-space mesh by moving the camera instead.
    bounds = [objects[0].matrix_world @ Vector(corner) for corner in objects[0].bound_box]
    center = sum(bounds, Vector()) / len(bounds)
    camera.location = (center.x, center.y, max(point.z for point in bounds) + 13.0)
else:
    camera.location = (0.0, 0.0, 13.0)
camera.data.lens = 50.0
scene.camera = camera
bpy.context.view_layer.update()
scene.use_nodes = True
compositor = scene.node_tree
compositor.nodes.clear()
render_layers = compositor.nodes.new(type="CompositorNodeRLayers")
render_layers.layer = view_layer.name
if AOV_NAME not in render_layers.outputs:
    raise RuntimeError(f"Cycles compositor has no Shader AOV output {{AOV_NAME!r}}")
composite = compositor.nodes.new(type="CompositorNodeComposite")
compositor.links.new(render_layers.outputs[AOV_NAME], composite.inputs["Image"])
bpy.ops.render.render(write_still=True)
if GEOMETRY_PATH:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    camera.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.wm.usd_export(
        filepath=GEOMETRY_PATH,
        selected_objects_only=True,
        export_uvmaps=True,
        rename_uvmaps=True,
        export_normals=True,
        export_materials=False,
        export_cameras=True,
    )
""".strip()


def main() -> int:
    """Render a source albedo reference image without modifying the input scene."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_scene", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--mode", choices=("albedo", "normal-vector"), default="albedo")
    parser.add_argument("--material", help="Render one named mesh-assigned material centered in frame.")
    parser.add_argument(
        "--geometry-usd",
        type=Path,
        help="Export the matching source mesh and camera for a baked USD comparison stage.",
    )
    parser.add_argument(
        "--baked-normal-dir",
        type=Path,
        help="Replace directly connected Blender Normal Map texture nodes with baked EXRs before rendering.",
    )
    args = parser.parse_args()

    scene_path = args.source_scene.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runtime = resolve_blender_runtime()
    script_path = output_path.with_suffix(".albedo_render.py")
    baked_normal_dir = args.baked_normal_dir.expanduser().resolve() if args.baked_normal_dir else None
    geometry_path = args.geometry_usd.expanduser().resolve() if args.geometry_usd else None
    if geometry_path:
        geometry_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        _script(
            scene_path,
            output_path,
            args.samples,
            args.mode,
            baked_normal_dir,
            args.material,
            geometry_path,
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [str(runtime.blender_exe), "--background", "--factory-startup", "--python", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if (
        completed.returncode
        or "Traceback (most recent call last):" in completed.stdout
        or "Traceback (most recent call last):" in completed.stderr
    ):
        raise RuntimeError(f"Cycles albedo render failed:\n{completed.stdout}\n{completed.stderr}")
    print(f"Rendered Cycles source {args.mode} reference: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Render one Blender material on its source mesh and export that comparison geometry.

The emitted USD preserves the generated bake UVs, source mesh, camera, and
controlled area lights. It can be passed to ``make_baked_usd_preview_stage.py
--geometry`` to compare a baked MaterialX/OpenPBR material in Karma against
the original Cycles beauty render on the same geometry.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from materials_processor.dcc.blender.runtime import resolve_blender_runtime


def _script(scene_path: Path, material_name: str, image_path: Path, geometry_path: Path, samples: int) -> str:
    """Return Blender Python for a controlled single-material beauty render."""
    return f"""
import bpy
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath={str(scene_path)!r})
scene = bpy.context.scene
material = bpy.data.materials.get({material_name!r})
if material is None:
    raise RuntimeError("material was not found: " + {material_name!r})
objects = [
    obj for obj in scene.objects
    if obj.type == "MESH" and len(obj.material_slots) == 1 and obj.material_slots[0].material == material
]
if not objects:
    raise RuntimeError("material requires a mesh assignment with one material slot: " + material.name)
obj = objects[0]
if not obj.data.uv_layers:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project()
    bpy.ops.object.mode_set(mode="OBJECT")

# This process is disposable: isolate the source object and use deterministic
# lighting so Cycles and Karma see the same mesh, UVs, camera, and light rig.
for other in scene.objects:
    other.hide_render = other is not obj
for light in list(bpy.data.lights):
    bpy.data.lights.remove(light)

corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
minimum = Vector((min(point[i] for point in corners) for i in range(3)))
maximum = Vector((max(point[i] for point in corners) for i in range(3)))
center = (minimum + maximum) * 0.5
extent = max((maximum - minimum).length, 0.001)

def point_at(node, target):
    node.rotation_euler = (target - node.location).to_track_quat("-Z", "Y").to_euler()

camera_data = bpy.data.cameras.new("materials_processor_comparison_camera")
camera = bpy.data.objects.new("materials_processor_comparison_camera", camera_data)
scene.collection.objects.link(camera)
camera.location = center + Vector((0.0, -extent * 0.15, extent * 1.8))
camera.data.lens = 50.0
point_at(camera, center)
scene.camera = camera

for name, offset, energy, size in (
    ("materials_processor_key", (0.7, -0.5, 1.2), 900.0, extent * 1.4),
    ("materials_processor_fill", (-0.8, -0.2, 0.7), 250.0, extent),
):
    light_data = bpy.data.lights.new(name, "AREA")
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    scene.collection.objects.link(light)
    light.location = center + Vector(offset) * extent
    point_at(light, center)

scene.render.engine = "CYCLES"
scene.cycles.samples = {samples!r}
scene.render.resolution_x = 768
scene.render.resolution_y = 768
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = {str(image_path)!r}
scene.world.color = (0.0, 0.0, 0.0)
bpy.ops.render.render(write_still=True)

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
camera.select_set(True)
for node in scene.objects:
    if node.type == "LIGHT" and node.name.startswith("materials_processor_"):
        node.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.wm.usd_export(
    filepath={str(geometry_path)!r},
    selected_objects_only=True,
    export_uvmaps=True,
    # MaterialX's ND_texcoord_vector2 reads the USD-standard ``st`` primvar.
    # The temporary Smart UV Project map may otherwise retain Blender's
    # arbitrary name, making a same-mesh comparison sample invalid UVs.
    rename_uvmaps=True,
    export_normals=True,
    export_materials=False,
    export_lights=True,
    export_cameras=True,
)
print("Rendered Cycles source beauty: " + {str(image_path)!r})
print("Exported comparison geometry: " + {str(geometry_path)!r})
""".strip()


def main() -> int:
    """
    Render the selected material and export matching comparison geometry.
    
    Parameters:
        Command-line arguments specify the source scene, material, image output,
        geometry USD output, and optional Cycles sample count.
    
    Raises:
        RuntimeError: If the Blender render or USD export fails.
    
    Returns:
        int: Zero after successful completion.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_scene", type=Path)
    parser.add_argument("--material", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--geometry-usd", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=64)
    args = parser.parse_args()

    scene = args.source_scene.expanduser().resolve()
    output = args.output.expanduser().resolve()
    geometry = args.geometry_usd.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    geometry.parent.mkdir(parents=True, exist_ok=True)
    script_path = output.with_suffix(".beauty_render.py")
    script_path.write_text(_script(scene, args.material, output, geometry, args.samples), encoding="utf-8")
    runtime = resolve_blender_runtime()
    completed = subprocess.run(
        [str(runtime.blender_exe), "--background", "--factory-startup", "--python", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode:
        raise RuntimeError(f"Cycles source beauty render failed:\n{completed.stdout}\n{completed.stderr}")
    print(completed.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

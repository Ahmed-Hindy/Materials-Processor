"""Generated Blender fixtures shared by bake integration tests."""

from __future__ import annotations

from pathlib import Path

from materials_processor.dcc.blender.runtime import BlenderRuntime, _run_blender_python


def build_bake_decision_fixture(scene_path: Path, runtime: BlenderRuntime, package_src: Path) -> None:
    """Create a small UV-mapped scene covering every bake-mode decision.

    Args:
        scene_path: Destination ``.blend`` file.
        runtime: Resolved Blender runtime used to create the scene.
        package_src: Project source directory passed into Blender's Python path.

    Raises:
        RuntimeError: If Blender cannot create the requested fixture scene.
    """
    code = f"""
import bpy


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for material in list(bpy.data.materials):
    bpy.data.materials.remove(material)


def make_plane(name, location, material):
    bpy.ops.mesh.primitive_plane_add(size=2, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def new_material(name):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    output = material.node_tree.nodes.new(type="ShaderNodeOutputMaterial")
    output.name = "Material Output"
    return material, output


direct, direct_output = new_material("Direct PBR")
direct_bsdf = direct.node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
direct_bsdf.name = "Direct Principled"
direct_bsdf.inputs["Base Color"].default_value = (0.12, 0.42, 0.8, 1.0)
direct_bsdf.inputs["Metallic"].default_value = 0.25
direct_bsdf.inputs["Roughness"].default_value = 0.35
direct.node_tree.links.new(direct_bsdf.outputs["BSDF"], direct_output.inputs["Surface"])
make_plane("Direct PBR Plane", (-3.0, 0.0, 0.0), direct)


normal, normal_output = new_material("Normal Map PBR")
normal_bsdf = normal.node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
normal_bsdf.name = "Normal Map Principled"
normal_bsdf.inputs["Base Color"].default_value = (0.35, 0.35, 0.35, 1.0)
normal_image = bpy.data.images.new("Fixture Nonflat Normal", width=2, height=2, alpha=False, float_buffer=True)
for color_space in ("Non-Color", "Utility - Raw", "Raw"):
    try:
        normal_image.colorspace_settings.name = color_space
        break
    except TypeError:
        continue
normal_image.pixels.foreach_set((
    0.20, 0.70, 0.90, 1.0,
    0.80, 0.50, 0.90, 1.0,
    0.50, 0.20, 0.90, 1.0,
    0.50, 0.50, 1.00, 1.0,
))
# Generated-image pixels are not retained by a reopened .blend unless the
# image has a source. Save and pack this tiny fixture map so the separate bake
# process sees the deliberately varying vectors.
normal_image.filepath_raw = {str(scene_path.with_name("fixture_nonflat_normal.exr"))!r}
normal_image.file_format = "OPEN_EXR"
normal_image.save()
normal_image.pack()
normal_texture = normal.node_tree.nodes.new(type="ShaderNodeTexImage")
normal_texture.image = normal_image
normal_map = normal.node_tree.nodes.new(type="ShaderNodeNormalMap")
normal_map.space = "TANGENT"
normal.node_tree.links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
normal.node_tree.links.new(normal_map.outputs["Normal"], normal_bsdf.inputs["Normal"])
normal.node_tree.links.new(normal_bsdf.outputs["BSDF"], normal_output.inputs["Surface"])
make_plane("Normal Map PBR Plane", (-1.5, 0.0, 0.0), normal)


group_tree = bpy.data.node_groups.new("Fixture Group Input Principled", "ShaderNodeTree")
group_tree.interface.new_socket(name="Color", in_out="INPUT", socket_type="NodeSocketColor")
group_tree.interface.new_socket(name="Roughness", in_out="INPUT", socket_type="NodeSocketFloat")
group_tree.interface.new_socket(name="Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
group_input = group_tree.nodes.new(type="NodeGroupInput")
group_output = group_tree.nodes.new(type="NodeGroupOutput")
group_output.is_active_output = True
group_bsdf = group_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
group_bsdf.name = "Internal Principled"
group_tree.links.new(group_input.outputs["Color"], group_bsdf.inputs["Base Color"])
group_tree.links.new(group_input.outputs["Roughness"], group_bsdf.inputs["Roughness"])
group_tree.links.new(group_bsdf.outputs["BSDF"], group_output.inputs["Shader"])

group_material, group_material_output = new_material("Group Input PBR")
group_node = group_material.node_tree.nodes.new(type="ShaderNodeGroup")
group_node.node_tree = group_tree
group_node.inputs["Color"].default_value = (0.75, 0.2, 0.1, 1.0)
group_node.inputs["Roughness"].default_value = 0.55
group_material.node_tree.links.new(group_node.outputs["Shader"], group_material_output.inputs["Surface"])
make_plane("Group Input PBR Plane", (0.0, 0.0, 0.0), group_material)


linked_group_material, linked_group_output = new_material("Group Input Linked PBR")
linked_group_node = linked_group_material.node_tree.nodes.new(type="ShaderNodeGroup")
linked_group_node.node_tree = group_tree
linked_group_node.inputs["Color"].default_value = (0.2, 0.85, 0.45, 1.0)
linked_roughness = linked_group_material.node_tree.nodes.new(type="ShaderNodeValue")
linked_roughness.name = "Outer Group Roughness"
linked_roughness.outputs["Value"].default_value = 0.23
linked_group_material.node_tree.links.new(linked_roughness.outputs["Value"], linked_group_node.inputs["Roughness"])
linked_group_material.node_tree.links.new(linked_group_node.outputs["Shader"], linked_group_output.inputs["Surface"])
make_plane("Group Input Linked PBR Plane", (1.5, 0.0, 0.0), linked_group_material)


complex_tree = bpy.data.node_groups.new("Fixture Complex Closure Group", "ShaderNodeTree")
complex_tree.interface.new_socket(name="Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
complex_output = complex_tree.nodes.new(type="NodeGroupOutput")
complex_output.is_active_output = True
diffuse = complex_tree.nodes.new(type="ShaderNodeBsdfDiffuse")
diffuse.inputs["Color"].default_value = (0.15, 0.7, 0.18, 1.0)
translucent = complex_tree.nodes.new(type="ShaderNodeBsdfTranslucent")
translucent.inputs["Color"].default_value = (0.95, 0.35, 0.08, 1.0)
mix = complex_tree.nodes.new(type="ShaderNodeMixShader")
mix.inputs[0].default_value = 0.35
complex_tree.links.new(diffuse.outputs["BSDF"], mix.inputs[1])
complex_tree.links.new(translucent.outputs["BSDF"], mix.inputs[2])
complex_tree.links.new(mix.outputs["Shader"], complex_output.inputs["Shader"])

complex_material, complex_material_output = new_material("Complex Closure")
complex_group = complex_material.node_tree.nodes.new(type="ShaderNodeGroup")
complex_group.node_tree = complex_tree
complex_material.node_tree.links.new(complex_group.outputs["Shader"], complex_material_output.inputs["Surface"])
make_plane("Complex Closure Plane", (4.0, 0.0, 0.0), complex_material)


world = bpy.context.scene.world or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.08, 0.08, 0.08, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
bpy.ops.object.light_add(type="AREA", location=(0.0, 0.0, 4.0))
light = bpy.context.active_object
light.data.energy = 600.0
light.data.shape = "DISK"
light.data.size = 5.0
bpy.context.scene.render.engine = "CYCLES"
bpy.ops.wm.save_as_mainfile(filepath={str(scene_path)!r})
""".strip()
    completed = _run_blender_python(runtime, code, package_src, timeout=120)
    if completed.returncode != 0:
        raise RuntimeError(
            "Blender bake fixture creation failed."
            f"\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

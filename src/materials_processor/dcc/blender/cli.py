"""Command line tools for Blender material workflows."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path, PureWindowsPath
from typing import Any

from materials_processor.core.graph import MaterialGraph, NodeConnection, NodeInfo, NodeParameter, OutputConnection
from materials_processor.dcc.blender.runtime import BlenderRuntime, _run_blender_python, resolve_blender_runtime

BLENDER_GRAPH_EXPORT_PREFIX = "MATERIALS_PROCESSOR_BLENDER_GRAPH_EXPORT="
DEFAULT_EXPORT_TARGETS = ("mtlx", "openpbr")
TARGET_ALIASES = {
    "materialx": "mtlx",
    "mtlx": "mtlx",
    "openpbr": "openpbr",
}
TARGET_FILE_LABELS = {
    "mtlx": "materialx",
    "openpbr": "openpbr",
}
MISSING_TEXTURE_POLICIES = ("warn", "error")
NATIVE_MATERIALX_EXPORT_PREFIX = "MATERIALS_PROCESSOR_BLENDER_NATIVE_MATERIALX="
BAKED_MATERIAL_EXPORT_PREFIX = "MATERIALS_PROCESSOR_BLENDER_BAKED_MATERIALS="
BAKE_STREAM_SPECS = (
    ("base_color", "Base Color", "color"),
    ("metalness", "Metallic", "scalar"),
    ("roughness", "Roughness", "scalar"),
    ("normal", "Normal", "normal"),
    ("opacity", "Alpha", "scalar"),
    ("emission_color", "Emission Color", "color"),
)
GROUP_BAKE_OUTPUT_NAMES = {
    "base_color": ("Color Bake", "Base Color Bake"),
    "metalness": ("Metallic Bake", "Metalness Bake"),
    "roughness": ("Roughness Bake",),
    "opacity": ("Opacity Bake", "Alpha Bake"),
    "emission_color": ("Emission Color Bake", "Emission Bake"),
}


def _default_package_src() -> Path:
    """Return the default package source directory."""
    return Path(__file__).resolve().parents[3]


def _nodeinfo_from_dict(data: dict[str, Any]) -> NodeInfo:
    """Rebuild a ``NodeInfo`` from JSON-compatible data."""
    return NodeInfo(
        node_type=data.get("node_type"),
        node_name=data["node_name"],
        node_path=data["node_path"],
        parameters=[NodeParameter(**param) for param in data.get("parameters") or []],
        connection_info={
            key: NodeConnection.from_mapping(value) for key, value in (data.get("connection_info") or {}).items()
        },
        children_list=[_nodeinfo_from_dict(child) for child in data.get("children_list") or []],
        is_output_node=data.get("is_output_node", False),
        output_type=data.get("output_type"),
        position=data.get("position"),
    )


def _material_graph_from_dict(data: dict[str, Any]) -> MaterialGraph:
    """Rebuild a material graph from JSON-compatible data."""
    return MaterialGraph(
        material_name=data["material_name"],
        material_path=data.get("material_path"),
        nodeinfo_list=[_nodeinfo_from_dict(node) for node in data.get("nodeinfo_list") or []],
        output_connections={
            key: OutputConnection.from_mapping(value) for key, value in (data.get("output_connections") or {}).items()
        },
    )


def _iter_nodeinfos(nodes: list[NodeInfo]):
    for node in nodes:
        yield node
        yield from _iter_nodeinfos(node.children_list)


def _texture_remaps_from_args(values: list[str] | None) -> tuple[tuple[str, str], ...]:
    """Parse ``OLD=NEW`` texture remap arguments."""
    remaps = []
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"Texture remap must be in OLD=NEW form: {value}")
        old, new = value.split("=", 1)
        if not old or not new:
            raise ValueError(f"Texture remap must include both OLD and NEW paths: {value}")
        remaps.append((old, new))
    return tuple(remaps)


def _apply_texture_remaps_to_path(
    texture_path: str,
    *,
    texture_root: str | Path | None = None,
    remap_prefixes: tuple[tuple[str, str], ...] = (),
) -> str:
    """Apply configured prefix or texture-root remappings to a texture path.
    
    Parameters:
    	texture_path (str): The original texture path.
    	texture_root (str | Path | None): Root directory to search for the texture filename when direct remapping does not apply.
    	remap_prefixes (tuple[tuple[str, str], ...]): Prefix replacement pairs applied to the path.
    
    Returns:
    	str: The remapped texture path, or the original path when no matching remap is found.
    """
    remapped = texture_path
    for old_prefix, new_prefix in remap_prefixes:
        old_norm = old_prefix.replace("\\", "/").rstrip("/")
        current_norm = remapped.replace("\\", "/")
        if current_norm == old_norm or current_norm.startswith(f"{old_norm}/"):
            suffix = current_norm[len(old_norm) :].lstrip("/")
            remapped = str(Path(new_prefix) / Path(suffix.replace("/", "\\")))
            break

    if texture_root is not None and remapped == texture_path and not Path(remapped.replace("<UDIM>", "1001")).exists():
        texture_name = PureWindowsPath(texture_path).name or Path(texture_path).name
        candidate = Path(texture_root) / texture_name
        if candidate.exists():
            remapped = str(candidate)
        else:
            recursive_match = next(Path(texture_root).rglob(texture_name), None)
            if recursive_match is not None:
                remapped = str(recursive_match)

    return remapped


def _apply_texture_remaps(
    graph_payload: dict[str, Any],
    *,
    texture_root: str | Path | None = None,
    remap_prefixes: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    """Apply texture remap options directly to extracted graph payload data."""
    if not texture_root and not remap_prefixes:
        return graph_payload

    remapped_textures = []
    for graph in graph_payload.get("graphs") or []:
        for node in _walk_node_dicts(graph.get("nodeinfo_list") or []):
            for parameter in node.get("parameters") or []:
                if parameter.get("generic_name") != "filename" or not parameter.get("value"):
                    continue
                original = str(parameter["value"])
                remapped = _apply_texture_remaps_to_path(
                    original,
                    texture_root=texture_root,
                    remap_prefixes=remap_prefixes,
                )
                if remapped != original:
                    parameter["value"] = remapped
                    remapped_textures.append(
                        {
                            "material": graph["material_name"],
                            "original": original,
                            "remapped": remapped,
                        }
                    )

    graph_payload["remapped_texture_paths"] = remapped_textures
    graph_payload["missing_texture_paths"] = _find_missing_texture_paths(graph_payload)
    return graph_payload


def _walk_node_dicts(nodes: list[dict[str, Any]]):
    """Yield node dictionaries recursively from JSON-compatible graph data."""
    for node in nodes:
        yield node
        yield from _walk_node_dicts(node.get("children_list") or [])


def _find_missing_texture_paths(graph_payload: dict[str, Any]) -> list[dict[str, str]]:
    """Return missing texture paths from JSON-compatible graph data."""
    missing = []
    for graph in graph_payload.get("graphs") or []:
        for node in _walk_node_dicts(graph.get("nodeinfo_list") or []):
            for parameter in node.get("parameters") or []:
                if parameter.get("generic_name") != "filename" or not parameter.get("value"):
                    continue
                texture_path = str(parameter["value"])
                normalized = texture_path.replace("<UDIM>", "1001")
                if "<UDIM>" not in texture_path and not Path(normalized).exists():
                    missing.append({"material": graph["material_name"], "path": texture_path})
    return missing


def _enforce_report_policies(
    report: dict[str, Any],
    *,
    fail_on_unsupported: bool = False,
    missing_textures: str = "warn",
) -> None:
    """
    Enforce configured failure policies for unsupported nodes and missing textures.
    
    Parameters:
        report (dict[str, Any]): Report containing unsupported node and missing texture entries.
        fail_on_unsupported (bool): Whether unsupported nodes should raise an error.
        missing_textures (str): Policy for missing textures; ``"error"`` raises an error.
    """
    if fail_on_unsupported and report.get("unsupported_nodes"):
        raise RuntimeError(
            f"Unsupported Blender nodes were found: {json.dumps(report['unsupported_nodes'], sort_keys=True)}"
        )
    if missing_textures == "error" and report.get("missing_texture_paths"):
        raise RuntimeError(
            f"Missing texture paths were found: {json.dumps(report['missing_texture_paths'], sort_keys=True)}"
        )


def _extract_code(scene_path: Path, graph_json_path: Path) -> str:
    """Return the Python script executed inside Blender to extract material graphs."""
    return f"""
import json
from dataclasses import asdict
from pathlib import Path

import bpy

from materials_processor.dcc.blender.adapters import BlenderMaterialReader

SCENE_PATH = {str(scene_path)!r}
GRAPH_JSON_PATH = {str(graph_json_path)!r}
PREFIX = {BLENDER_GRAPH_EXPORT_PREFIX!r}


def iter_nodeinfos(nodes):
    for node in nodes:
        yield node
        yield from iter_nodeinfos(node.children_list)


def node_summary(node):
    return {{
        "node_name": node.node_name,
        "node_path": node.node_path,
        "node_type": node.node_type,
    }}


bpy.ops.wm.open_mainfile(filepath=SCENE_PATH)
reader = BlenderMaterialReader()
materials = [
    material
    for material in bpy.data.materials
    if getattr(material, "use_nodes", False) and getattr(material, "node_tree", None)
]
result = {{
    "scene": SCENE_PATH,
    "material_count": len(bpy.data.materials),
    "node_material_count": len(materials),
    "graphs": [],
    "read_failures": [],
    "unsupported_nodes": {{}},
    "missing_texture_paths": [],
}}

for material in materials:
    try:
        graph = reader.read(material)
    except Exception as exc:
        result["read_failures"].append({{"material": material.name, "error": repr(exc)}})
        continue

    nodeinfos = list(iter_nodeinfos(graph.nodeinfo_list))
    unsupported = [node_summary(node) for node in nodeinfos if node.node_type is None]
    if unsupported:
        result["unsupported_nodes"][material.name] = unsupported

    for node in nodeinfos:
        for parameter in node.parameters or []:
            if parameter.generic_name != "filename" or not parameter.value:
                continue
            texture_path = str(parameter.value)
            normalized = texture_path.replace("<UDIM>", "1001")
            if "<UDIM>" not in texture_path and not Path(normalized).exists():
                result["missing_texture_paths"].append({{
                    "material": material.name,
                    "path": texture_path,
                }})

    result["graphs"].append(asdict(graph))

Path(GRAPH_JSON_PATH).write_text(json.dumps(result, indent=2), encoding="utf-8")
summary = {{key: value for key, value in result.items() if key != "graphs"}}
summary["graph_count"] = len(result["graphs"])
print(PREFIX + json.dumps(summary, sort_keys=True))
""".strip()


def _native_materialx_export_code(scene_path: Path, usd_path: Path) -> str:
    """Return the Blender script for its native MaterialX USD export."""
    return f"""
import json

import bpy

bpy.ops.wm.open_mainfile(filepath={str(scene_path)!r})
bpy.ops.wm.usd_export(
    filepath={str(usd_path)!r},
    export_materials=True,
    generate_preview_surface=False,
    generate_materialx_network=True,
    export_textures=False,
)
print({NATIVE_MATERIALX_EXPORT_PREFIX!r} + json.dumps({{"path": {str(usd_path)!r}}}))
""".strip()


def _bake_materials_code(
    scene_path: Path,
    texture_dir: Path,
    material_names: tuple[str, ...] | None,
    resolution: int,
    auto_unwrap: bool,
    bake_mode: str = "pbr",
    color_space: str = "lin_ap1",
) -> str:
    """Return the Blender script that bakes PBR material streams or evaluated beauty textures.
    
    Parameters:
    	scene_path (Path): Path to the Blender scene to open.
    	texture_dir (Path): Directory where baked texture files are written.
    	material_names (tuple[str, ...] | None): Materials to bake, or all eligible materials when omitted.
    	resolution (int): Width and height of each baked texture in pixels.
    	auto_unwrap (bool): Whether to generate UVs for meshes without a UV map.
    	bake_mode (str): Bake strategy, such as PBR, beauty, or automatic fallback.
    	color_space (str): Color space recorded for baked material streams.
    
    Returns:
    	str: A self-contained Blender Python script.
    """
    return f"""
import json
import re
from pathlib import Path

import bpy

SCENE_PATH = {str(scene_path)!r}
TEXTURE_DIR = Path({str(texture_dir)!r})
MATERIAL_NAMES = {list(material_names) if material_names is not None else None!r}
RESOLUTION = {resolution!r}
AUTO_UNWRAP = {auto_unwrap!r}
BAKE_MODE = {bake_mode!r}
COLOR_SPACE = {color_space!r}
BAKE_STREAM_SPECS = {BAKE_STREAM_SPECS!r}
GROUP_BAKE_OUTPUT_NAMES = {GROUP_BAKE_OUTPUT_NAMES!r}


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "material"


def bake_target(material):
    candidates = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or material.name not in [slot.name for slot in obj.data.materials if slot]:
            continue
        if len(obj.material_slots) == 1:
            candidates.append(obj)
    return candidates[0] if candidates else None


def group_closure_summary(group_node):
    group_tree = group_node.node_tree
    group_outputs = [node for node in group_tree.nodes if node.bl_idname == "NodeGroupOutput"] if group_tree else []
    group_output = next((node for node in group_outputs if node.is_active_output), group_outputs[0] if group_outputs else None)
    shader_input = next((socket for socket in group_output.inputs if socket.type == "SHADER" and socket.is_linked), None) if group_output else None
    if shader_input is None:
        return "no connected internal shader"
    closure_types = set()
    visited = set()

    def visit(node):
        key = (node.name, node.bl_idname)
        if key in visited:
            return
        visited.add(key)
        if node.bl_idname == "ShaderNodeMixShader" or node.bl_idname.startswith("ShaderNodeBsdf"):
            closure_types.add(node.bl_idname)
        for socket in node.inputs:
            if socket.is_linked:
                visit(socket.links[0].from_node)

    visit(shader_input.links[0].from_node)
    return ", ".join(sorted(closure_types)) or "an unsupported internal shader graph"


def active_bake_source(material):
    outputs = [node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial"]
    output = next((node for node in outputs if node.is_active_output), outputs[0] if outputs else None)
    if output is None or not output.inputs["Surface"].is_linked:
        return None, None, "material has no connected surface output"
    shader = output.inputs["Surface"].links[0].from_node
    if shader.bl_idname == "ShaderNodeBsdfPrincipled":
        return "principled", shader, None
    if shader.bl_idname != "ShaderNodeGroup":
        return None, None, f"surface is {{shader.bl_idname}}, not a directly connected Principled BSDF or a group with PBR bake outputs"
    active_group_output_name = output.inputs["Surface"].links[0].from_socket.name

    stream_outputs = {{}}
    for map_name, candidates in GROUP_BAKE_OUTPUT_NAMES.items():
        socket = next((shader.outputs.get(name) for name in candidates if shader.outputs.get(name) is not None), None)
        if socket is not None:
            stream_outputs[map_name] = socket.name
    if "base_color" not in stream_outputs:
        group_tree = shader.node_tree
        group_outputs = [node for node in group_tree.nodes if node.bl_idname == "NodeGroupOutput"] if group_tree else []
        group_output = next((node for node in group_outputs if node.is_active_output), group_outputs[0] if group_outputs else None)
        # Blender groups can expose independent Cycles and EEVEE closure
        # outputs. Follow the exact output socket connected to Material Output;
        # scanning the whole group can otherwise bake a different renderer
        # branch than the one Blender actually renders.
        shader_input = group_output.inputs.get(active_group_output_name) if group_output else None
        if shader_input is None or shader_input.type != "SHADER" or not shader_input.is_linked:
            shader_input = next((socket for socket in group_output.inputs if socket.type == "SHADER" and socket.is_linked), None) if group_output else None
        internal_shader = shader_input.links[0].from_node if shader_input else None
        if internal_shader and internal_shader.bl_idname == "ShaderNodeBsdfPrincipled":
            # A copied group can temporarily expose this node's evaluated
            # inputs. This preserves Group Input values and outer links.
            return "group_principled", (shader, internal_shader.name), None
        # Mixed closures are not portable PBR. Keep their evaluated look in
        # the explicit beauty route instead of relabelling lobe weights as PBR
        # parameters.
        closure_summary = group_closure_summary(shader)
        return None, None, f"complex group closure ({{closure_summary}}) is not a portable PBR material"
    return "group_streams", (shader, stream_outputs), None


def set_image_color_space(image, stream_kind):
    # Bake buffers contain scene-linear values. Colour textures are declared
    # lin_ap1 downstream; scalar and normal-vector textures remain Raw.
    candidates = ("Utility - Raw", "raw", "Non-Color")
    for candidate in candidates:
        try:
            image.colorspace_settings.name = candidate
            return
        except TypeError:
            continue


def add_stream_link(tree, source_input, stream_kind, emission):
    if source_input.is_linked:
        source_output = source_input.links[0].from_socket
        tree.links.new(source_output, emission.inputs["Color"])
        return
    if stream_kind == "scalar":
        constant = tree.nodes.new(type="ShaderNodeValue")
        constant.outputs[0].default_value = float(source_input.default_value)
        tree.links.new(constant.outputs[0], emission.inputs["Color"])
        return
    if stream_kind == "vector":
        constant = tree.nodes.new(type="ShaderNodeCombineXYZ")
        for index, value in enumerate(source_input.default_value):
            constant.inputs[index].default_value = value
        tree.links.new(constant.outputs["Vector"], emission.inputs["Color"])
        return
    constant = tree.nodes.new(type="ShaderNodeRGB")
    constant.outputs["Color"].default_value = source_input.default_value
    tree.links.new(constant.outputs["Color"], emission.inputs["Color"])


def bake_stream(material, obj, source_shader_name, map_name, socket_name, stream_kind):
    proxy = material.copy()
    proxy.name = f"materials_processor_bake_{{safe_name(material.name)}}_{{map_name}}"
    tree = proxy.node_tree
    source_shader = tree.nodes.get(source_shader_name)
    source_input = source_shader.inputs.get(socket_name) if source_shader else None
    if source_input is None:
        bpy.data.materials.remove(proxy)
        return None

    if stream_kind != "normal":
        output = next(node for node in tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial" and node.is_active_output)
        emission = tree.nodes.new(type="ShaderNodeEmission")
        for link in list(output.inputs["Surface"].links):
            tree.links.remove(link)
        tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        add_stream_link(tree, source_input, stream_kind, emission)
    image = bpy.data.images.new(
        name=f"materials_processor_{{safe_name(material.name)}}_{{map_name}}",
        width=RESOLUTION,
        height=RESOLUTION,
        alpha=False,
        float_buffer=True,
    )
    set_image_color_space(image, stream_kind)
    image_node = tree.nodes.new(type="ShaderNodeTexImage")
    image_node.image = image
    for node in tree.nodes:
        node.select = False
    image_node.select = True
    tree.nodes.active = image_node

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    original_material = obj.material_slots[0].material
    obj.material_slots[0].material = proxy
    try:
        if stream_kind == "normal":
            # Blender's tangent-space NORMAL bake preserves the evaluated
            # Principled normal, including a connected Normal Map or Bump node.
            scene.render.bake.normal_space = "TANGENT"
            bpy.ops.object.bake(type="NORMAL", use_clear=True, margin=16)
        else:
            bpy.ops.object.bake(type="EMIT", use_clear=True, margin=16)
    finally:
        obj.material_slots[0].material = original_material

    output_path = TEXTURE_DIR / f"{{safe_name(material.name)}}_{{map_name}}.exr"
    image.filepath_raw = str(output_path)
    image.file_format = "OPEN_EXR"
    image.save()
    tree.nodes.remove(image_node)
    bpy.data.images.remove(image)
    bpy.data.materials.remove(proxy)
    return str(output_path)


def bake_beauty(material, obj):
    # Combined is intentionally a final-appearance fallback.  It captures the
    # active Blender scene's lighting and is exported as an unlit material;
    # it is not presented as a portable PBR reconstruction.
    image = bpy.data.images.new(
        name=f"materials_processor_{{safe_name(material.name)}}_beauty",
        width=RESOLUTION,
        height=RESOLUTION,
        alpha=False,
        float_buffer=True,
    )
    set_image_color_space(image, "color")
    tree = material.node_tree
    image_node = tree.nodes.new(type="ShaderNodeTexImage")
    image_node.image = image
    for node in tree.nodes:
        node.select = False
    image_node.select = True
    tree.nodes.active = image_node
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.bake(type="COMBINED", use_clear=True, margin=16)
    finally:
        tree.nodes.remove(image_node)
    output_path = TEXTURE_DIR / f"{{safe_name(material.name)}}_beauty.exr"
    image.filepath_raw = str(output_path)
    image.file_format = "OPEN_EXR"
    image.save()
    bpy.data.images.remove(image)
    return str(output_path)


def bake_group_stream(material, obj, group_node_name, map_name, output_socket_name, stream_kind):
    proxy = material.copy()
    proxy.name = f"materials_processor_bake_{{safe_name(material.name)}}_{{map_name}}"
    tree = proxy.node_tree
    group = tree.nodes.get(group_node_name)
    output_socket = group.outputs.get(output_socket_name) if group else None
    if output_socket is None:
        bpy.data.materials.remove(proxy)
        return None

    output = next(node for node in tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial" and node.is_active_output)
    emission = tree.nodes.new(type="ShaderNodeEmission")
    for link in list(output.inputs["Surface"].links):
        tree.links.remove(link)
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    if stream_kind == "inverse_scalar":
        inverted = group_tree.nodes.new(type="ShaderNodeMath")
        inverted.operation = "SUBTRACT"
        inverted.inputs[0].default_value = 1.0
        group_tree.links.new(source_socket, inverted.inputs[1])
        group_tree.links.new(inverted.outputs[0], emission.inputs["Color"])
    else:
        tree.links.new(output_socket, emission.inputs["Color"])
    image = bpy.data.images.new(
        name=f"materials_processor_{{safe_name(material.name)}}_{{map_name}}",
        width=RESOLUTION,
        height=RESOLUTION,
        alpha=False,
        float_buffer=True,
    )
    set_image_color_space(image, stream_kind)
    image_node = tree.nodes.new(type="ShaderNodeTexImage")
    image_node.image = image
    for node in tree.nodes:
        node.select = False
    image_node.select = True
    tree.nodes.active = image_node

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    original_material = obj.material_slots[0].material
    obj.material_slots[0].material = proxy
    try:
        bpy.ops.object.bake(type="EMIT", use_clear=True, margin=16)
    finally:
        obj.material_slots[0].material = original_material

    output_path = TEXTURE_DIR / f"{{safe_name(material.name)}}_{{map_name}}.exr"
    image.filepath_raw = str(output_path)
    image.file_format = "OPEN_EXR"
    image.save()
    tree.nodes.remove(image_node)
    bpy.data.images.remove(image)
    bpy.data.materials.remove(proxy)
    return str(output_path)


def expose_group_principled_stream(group, internal_shader_name, map_name, socket_name, stream_kind):
    group.node_tree = group.node_tree.copy()
    group_tree = group.node_tree
    internal_shader = group_tree.nodes.get(internal_shader_name)
    source_input = internal_shader.inputs.get(socket_name) if internal_shader else None
    if source_input is None:
        return None

    exposed_name = f"__materials_processor_bake_{{map_name}}"
    socket_types = {{"color": "NodeSocketColor", "scalar": "NodeSocketFloat", "normal": "NodeSocketVector"}}
    group_tree.interface.new_socket(name=exposed_name, in_out="OUTPUT", socket_type=socket_types[stream_kind])
    group_outputs = [node for node in group_tree.nodes if node.bl_idname == "NodeGroupOutput"]
    group_output = next((node for node in group_outputs if node.is_active_output), group_outputs[0] if group_outputs else None)
    output_input = group_output.inputs.get(exposed_name) if group_output else None
    output_socket = group.outputs.get(exposed_name)
    if output_input is None or output_socket is None:
        return None

    if source_input.is_linked:
        group_tree.links.new(source_input.links[0].from_socket, output_input)
    elif stream_kind == "scalar":
        value = group_tree.nodes.new(type="ShaderNodeValue")
        value.outputs[0].default_value = float(source_input.default_value)
        group_tree.links.new(value.outputs[0], output_input)
    elif stream_kind == "normal":
        value = group_tree.nodes.new(type="ShaderNodeCombineXYZ")
        value.inputs[2].default_value = 1.0
        group_tree.links.new(value.outputs["Vector"], output_input)
    else:
        value = group_tree.nodes.new(type="ShaderNodeRGB")
        value.outputs["Color"].default_value = source_input.default_value
        group_tree.links.new(value.outputs["Color"], output_input)
    return output_socket


def bake_group_principled_stream(material, obj, group_node_name, internal_shader_name, map_name, socket_name, stream_kind):
    proxy = material.copy()
    proxy.name = f"materials_processor_bake_{{safe_name(material.name)}}_{{map_name}}"
    tree = proxy.node_tree
    group = tree.nodes.get(group_node_name)
    output_socket = expose_group_principled_stream(group, internal_shader_name, map_name, socket_name, stream_kind) if group else None
    if output_socket is None:
        bpy.data.materials.remove(proxy)
        return None

    if stream_kind != "normal":
        output = next(node for node in tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial" and node.is_active_output)
        emission = tree.nodes.new(type="ShaderNodeEmission")
        for link in list(output.inputs["Surface"].links):
            tree.links.remove(link)
        tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        tree.links.new(output_socket, emission.inputs["Color"])
    image = bpy.data.images.new(
        name=f"materials_processor_{{safe_name(material.name)}}_{{map_name}}",
        width=RESOLUTION,
        height=RESOLUTION,
        alpha=False,
        float_buffer=True,
    )
    set_image_color_space(image, stream_kind)
    image_node = tree.nodes.new(type="ShaderNodeTexImage")
    image_node.image = image
    for node in tree.nodes:
        node.select = False
    image_node.select = True
    tree.nodes.active = image_node

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    original_material = obj.material_slots[0].material
    obj.material_slots[0].material = proxy
    try:
        if stream_kind == "normal":
            scene.render.bake.normal_space = "TANGENT"
            bpy.ops.object.bake(type="NORMAL", use_clear=True, margin=16)
        else:
            bpy.ops.object.bake(type="EMIT", use_clear=True, margin=16)
    finally:
        obj.material_slots[0].material = original_material

    output_path = TEXTURE_DIR / f"{{safe_name(material.name)}}_{{map_name}}.exr"
    image.filepath_raw = str(output_path)
    image.file_format = "OPEN_EXR"
    image.save()
    tree.nodes.remove(image_node)
    bpy.data.images.remove(image)
    bpy.data.materials.remove(proxy)
    return str(output_path)


def write_constant_map(material, map_name, source_input, stream_kind):
    value = source_input.default_value
    if stream_kind == "scalar":
        values = (float(value),) * 3
    else:
        values = tuple(float(component) for component in value[:3])
    image = bpy.data.images.new(
        name=f"materials_processor_{{safe_name(material.name)}}_{{map_name}}_constant",
        width=1,
        height=1,
        alpha=False,
        float_buffer=True,
    )
    set_image_color_space(image, stream_kind)
    image.pixels.foreach_set((*values, 1.0))
    output_path = TEXTURE_DIR / f"{{safe_name(material.name)}}_{{map_name}}.exr"
    image.filepath_raw = str(output_path)
    image.file_format = "OPEN_EXR"
    image.save()
    bpy.data.images.remove(image)
    return str(output_path)


def create_bake_uv(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.03)
    bpy.ops.object.mode_set(mode="OBJECT")


bpy.ops.wm.open_mainfile(filepath=SCENE_PATH)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
TEXTURE_DIR.mkdir(parents=True, exist_ok=True)
requested = set(MATERIAL_NAMES or ())
bake_all = not requested or "all" in requested
result = {{
    "scene": SCENE_PATH,
    "texture_dir": str(TEXTURE_DIR),
    "baked_materials": [],
    "skipped_materials": [],
    "color_management": {{
        "baked_color_space": COLOR_SPACE,
        "display_device": scene.display_settings.display_device,
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": scene.view_settings.exposure,
        "gamma": scene.view_settings.gamma,
    }},
}}
available_material_names = {{material.name for material in bpy.data.materials}}
for missing_name in sorted(requested - {{"all"}} - available_material_names):
    result["skipped_materials"].append({{"material": missing_name, "reason": "material name was not found in the Blender scene"}})

for material in bpy.data.materials:
    if not material.use_nodes or not material.node_tree or (not bake_all and material.name not in requested):
        continue
    obj = bake_target(material)
    if obj is None:
        result["skipped_materials"].append({{
            "material": material.name,
            "reason": "requires a mesh assignment with no competing material slots",
        }})
        continue
    try:
        if BAKE_MODE == "beauty":
            bake_source_kind, bake_source, reason = "beauty", None, None
        else:
            bake_source_kind, bake_source, reason = active_bake_source(material)
            if bake_source is None:
                if BAKE_MODE == "auto":
                    bake_source_kind = "beauty"
                else:
                    result["skipped_materials"].append({{"material": material.name, "reason": reason}})
                    continue
    except Exception as exc:
        result["skipped_materials"].append({{"material": material.name, "reason": repr(exc)}})
        continue
    generated_uv = False
    if not obj.data.uv_layers:
        if not AUTO_UNWRAP:
            result["skipped_materials"].append({{"material": material.name, "reason": "mesh has no UV map"}})
            continue
        try:
            create_bake_uv(obj)
            generated_uv = True
        except Exception as exc:
            result["skipped_materials"].append({{"material": material.name, "reason": f"could not create bake UV map: {{exc!r}}"}})
            continue
    try:
        maps = {{}}
        missing_streams = []
        stream_specs = () if bake_source_kind == "beauty" else BAKE_STREAM_SPECS
        if bake_source_kind == "beauty":
            maps["beauty"] = bake_beauty(material, obj)
        for map_name, socket_name, stream_kind in stream_specs:
            if bake_source_kind == "principled":
                source_input = bake_source.inputs.get(socket_name)
                if source_input is None:
                    missing_streams.append(map_name)
                    continue
                if stream_kind != "normal" and not source_input.is_linked:
                    maps[map_name] = write_constant_map(material, map_name, source_input, stream_kind)
                    continue
                baked_path = bake_stream(material, obj, bake_source.name, map_name, socket_name, stream_kind)
            elif bake_source_kind == "group_streams":
                group, stream_outputs = bake_source
                output_socket_name = stream_outputs.get(map_name)
                if output_socket_name is None:
                    missing_streams.append(map_name)
                    continue
                baked_path = bake_group_stream(material, obj, group.name, map_name, output_socket_name, stream_kind)
            elif bake_source_kind == "group_principled":
                group, internal_shader_name = bake_source
                baked_path = bake_group_principled_stream(
                    material, obj, group.name, internal_shader_name, map_name, socket_name, stream_kind
                )
            if baked_path:
                maps[map_name] = baked_path
            else:
                missing_streams.append(map_name)
        baked_record = {{
            "material": material.name,
            "maps": maps,
            "generated_uv": generated_uv,
            "missing_streams": missing_streams,
            "stream_color_space": COLOR_SPACE,
            "normal_map_convention": "tangent-space glTF (ND_gltf_normalmap_vector3_1_0)",
            "bake_source": bake_source_kind,
            "bake_mode": "beauty" if bake_source_kind == "beauty" else "pbr",
        }}
        if bake_source_kind == "beauty":
            baked_record["pbr_rejection"] = reason
            baked_record["limitation"] = "Combined beauty bake is lighting-dependent and is exported as an unlit appearance texture, not PBR."
        result["baked_materials"].append(baked_record)
    except Exception as exc:
        result["skipped_materials"].append({{"material": material.name, "reason": repr(exc)}})

print({BAKED_MATERIAL_EXPORT_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()


def _baked_shader_id(target: str) -> str:
    """Return the material surface shader identifier for a baked target."""
    return "ND_standard_surface_surfaceshader" if target == "mtlx" else "ND_open_pbr_surface_surfaceshader"


def _write_baked_usd_material_file(
    baked_materials: list[dict[str, Any]],
    output_path: Path,
    target: str,
) -> dict[str, Any]:
    """
    Write a USD material file that connects baked textures to PBR or unlit beauty shaders.
    
    Parameters:
    	baked_materials (list[dict[str, Any]]): Baked material records containing material names, texture maps, and bake metadata.
    	output_path (Path): Destination path for the USD file.
    	target (str): Export target that determines the shader and input names.
    
    Returns:
    	dict[str, Any]: Export metadata containing the file path, material prim paths and count, and shader ID counts.
    """
    from pxr import Sdf, Tf, Usd, UsdShade

    stage = Usd.Stage.CreateNew(str(output_path))
    stage.SetDefaultPrim(stage.DefinePrim(Sdf.Path("/materials"), "Scope"))
    material_paths = []
    surface_input_names = {
        "base_color": "base_color",
        "base_weight": "base" if target == "mtlx" else "base_weight",
        "metalness": "metalness" if target == "mtlx" else "base_metalness",
        "roughness": "specular_roughness",
        "specular_color": "specular_color",
        "specular_roughness": "specular_roughness",
        "specular_weight": "specular" if target == "mtlx" else "specular_weight",
        "normal": "normal" if target == "mtlx" else "geometry_normal",
        "opacity": "opacity" if target == "mtlx" else "geometry_opacity",
        "emission_color": "emission_color",
        "sheen": "sheen" if target == "mtlx" else "fuzz_weight",
        "sheen_color": "sheen_color" if target == "mtlx" else "fuzz_color",
        "sheen_roughness": "sheen_roughness" if target == "mtlx" else "fuzz_roughness",
        "sheen_weight": "sheen" if target == "mtlx" else "fuzz_weight",
    }

    for baked in baked_materials:
        material_name = baked["material"]
        material_path = Sdf.Path("/materials").AppendChild(Tf.MakeValidIdentifier(material_name) or "material")
        material = UsdShade.Material.Define(stage, material_path)
        material_prim = material.GetPrim()
        material_prim.SetMetadata(
            "apiSchemas",
            Sdf.TokenListOp.Create(prependedItems=["MaterialXConfigAPI"]),
        )
        material_prim.CreateAttribute("config:mtlx:version", Sdf.ValueTypeNames.String).Set("1.39")
        surface = UsdShade.Shader.Define(stage, material_path.AppendChild("surface"))
        is_beauty = baked.get("bake_mode") == "beauty"
        surface.CreateIdAttr("ND_surface_unlit" if is_beauty else _baked_shader_id(target))
        # Author the PBR base weight explicitly rather than depending on a
        # renderer's interpretation of the MaterialX nodedef default.
        if not is_beauty:
            surface.CreateInput(
                "base" if target == "mtlx" else "base_weight",
                Sdf.ValueTypeNames.Float,
            ).Set(1.0)
        material.CreateOutput("mtlx:surface", Sdf.ValueTypeNames.Token).ConnectToSource(surface.ConnectableAPI(), "out")
        # Karma selects its renderer-context output rather than the generic
        # MaterialX context when rendering a USD stage headlessly.
        material.CreateOutput("kma:surface", Sdf.ValueTypeNames.Token).ConnectToSource(surface.ConnectableAPI(), "out")

        texcoord = UsdShade.Shader.Define(stage, material_path.AppendChild("texcoord"))
        texcoord.CreateIdAttr("ND_texcoord_vector2")
        texcoord.CreateOutput("out", Sdf.ValueTypeNames.Float2)

        if is_beauty:
            texture_path = baked["maps"].get("beauty")
            if texture_path:
                image = UsdShade.Shader.Define(stage, material_path.AppendChild("beauty_image"))
                image.CreateIdAttr("ND_image_color3")
                file_input = image.CreateInput("file", Sdf.ValueTypeNames.Asset)
                file_input.Set(Sdf.AssetPath(texture_path.replace("\\", "/")))
                file_input.GetAttr().SetColorSpace(baked.get("stream_color_space", "lin_ap1"))
                image.CreateInput("texcoord", Sdf.ValueTypeNames.Float2).ConnectToSource(
                    texcoord.ConnectableAPI(), "out"
                )
                image.CreateOutput("out", Sdf.ValueTypeNames.Color3f)
                surface.CreateInput("emission_color", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    image.ConnectableAPI(), "out"
                )
            material_paths.append(material_path.pathString)
            continue

        for map_name, texture_path in baked["maps"].items():
            is_normal = map_name == "normal"
            is_color = map_name in {"base_color", "emission_color", "sheen_color", "specular_color"}
            image = UsdShade.Shader.Define(stage, material_path.AppendChild(f"{map_name}_image"))
            image.CreateIdAttr(
                "ND_gltf_normalmap_vector3_1_0" if is_normal else "ND_image_color3" if is_color else "ND_image_float"
            )
            file_input = image.CreateInput("file", Sdf.ValueTypeNames.Asset)
            # Normalize Windows filenames to the portable USD asset form.
            file_input.Set(Sdf.AssetPath(texture_path.replace("\\", "/")))
            file_input.GetAttr().SetColorSpace(baked.get("stream_color_space", "lin_ap1") if is_color else "raw")
            image.CreateInput("texcoord", Sdf.ValueTypeNames.Float2).ConnectToSource(texcoord.ConnectableAPI(), "out")
            image.CreateOutput(
                "out",
                Sdf.ValueTypeNames.Float3
                if is_normal
                else Sdf.ValueTypeNames.Color3f
                if is_color
                else Sdf.ValueTypeNames.Float,
            )

            if is_normal:
                surface.CreateInput(surface_input_names[map_name], Sdf.ValueTypeNames.Float3).ConnectToSource(
                    image.ConnectableAPI(), "out"
                )
            else:
                value_type = Sdf.ValueTypeNames.Color3f if is_color else Sdf.ValueTypeNames.Float
                surface.CreateInput(surface_input_names[map_name], value_type).ConnectToSource(
                    image.ConnectableAPI(), "out"
                )
        material_paths.append(material_path.pathString)

    stage.GetRootLayer().Save()
    return {
        "path": str(output_path),
        "material_prim_count": len(material_paths),
        "material_prims": material_paths,
        "shader_ids": {
            shader_id: sum(
                1
                for baked in baked_materials
                if ("ND_surface_unlit" if baked.get("bake_mode") == "beauty" else _baked_shader_id(target)) == shader_id
            )
            for shader_id in {"ND_surface_unlit", _baked_shader_id(target)}
            if any(
                ("ND_surface_unlit" if baked.get("bake_mode") == "beauty" else _baked_shader_id(target)) == shader_id
                for baked in baked_materials
            )
        },
    }


def export_baked_blender_materials(
    scene_path: str | Path,
    out_dir: str | Path,
    *,
    material_names: tuple[str, ...] | None = None,
    resolution: int = 1024,
    auto_unwrap: bool = False,
    bake_mode: str = "pbr",
    color_space: str = "lin_ap1",
    targets: tuple[str, ...] = DEFAULT_EXPORT_TARGETS,
    runtime: BlenderRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Bake Blender materials into canonical PBR or unlit beauty textures and write target-specific USDA material files.
    
    Parameters:
    	material_names (tuple[str, ...] | None): Material names to bake, or all eligible materials when omitted.
    	resolution (int): Width and height of each baked texture in pixels.
    	auto_unwrap (bool): Whether to generate UVs automatically for objects without suitable UVs.
    	bake_mode (str): Bake mode: `"pbr"`, `"beauty"`, or `"auto"`.
    	color_space (str): MaterialX color-space name for baked textures.
    	targets (tuple[str, ...]): Material targets for generated USDA files.
    
    Returns:
    	dict[str, Any]: Bake report containing baked material metadata, the selected bake settings, and generated USD file paths.
    """
    if resolution < 1:
        raise ValueError("Bake resolution must be a positive integer.")
    if bake_mode not in {"pbr", "beauty", "auto"}:
        raise ValueError("Bake mode must be one of: pbr, beauty, auto.")
    if not color_space.strip():
        raise ValueError("Bake color space must be a non-empty MaterialX color-space name.")
    scene = Path(scene_path).expanduser().resolve()
    if not scene.is_file():
        raise FileNotFoundError(f"Blender scene was not found: {scene}")

    output_dir = Path(out_dir).expanduser().resolve()
    texture_dir = output_dir / "baked_textures"
    runtime = runtime or resolve_blender_runtime(version=None)
    package_src_path = Path(package_src).resolve() if package_src is not None else _default_package_src()
    completed = _run_blender_python(
        runtime,
        _bake_materials_code(scene, texture_dir, material_names, resolution, auto_unwrap, bake_mode, color_space),
        package_src_path,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Blender material baking failed.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
    bake_result = next(
        (
            json.loads(line[len(BAKED_MATERIAL_EXPORT_PREFIX) :])
            for line in completed.stdout.splitlines()
            if line.startswith(BAKED_MATERIAL_EXPORT_PREFIX)
        ),
        None,
    )
    if bake_result is None:
        raise RuntimeError(f"Blender material baking did not produce a result.\nstdout:\n{completed.stdout}")

    usd_files = {}
    for target in _targets_from_args(list(targets)):
        usd_path = output_dir / f"blender_baked_materials_{TARGET_FILE_LABELS[target]}.usda"
        usd_files[target] = _write_baked_usd_material_file(bake_result["baked_materials"], usd_path, target)

    bake_result.update(
        {"source": "blender-baked-materials", "bake_mode": bake_mode, "resolution": resolution, "usd_files": usd_files}
    )
    return bake_result


def _copy_native_materials(source_usd_path: Path, destination_usd_path: Path) -> dict[str, Any]:
    """
    Extract native Blender material prims into a material-only USD layer and report suspicious magenta base-color defaults.
    
    Parameters:
    	source_usd_path (Path): Path to the USD file exported by Blender.
    	destination_usd_path (Path): Path where the material-only USD layer is written.
    
    Returns:
    	dict[str, Any]: Report containing the destination path, copied material count and paths, and materials with suspicious magenta base colors.
    """
    from pxr import Sdf, Usd, UsdShade

    source_stage = Usd.Stage.Open(str(source_usd_path))
    if source_stage is None:
        raise RuntimeError(f"Blender native USD export could not be opened: {source_usd_path}")

    destination_stage = Usd.Stage.CreateNew(str(destination_usd_path))
    destination_stage.SetDefaultPrim(destination_stage.DefinePrim(Sdf.Path("/materials"), "Scope"))
    source_layer = source_stage.GetRootLayer()
    destination_layer = destination_stage.GetRootLayer()
    material_paths = []

    for material in (prim for prim in source_stage.Traverse() if prim.GetTypeName() == "Material"):
        destination_path = Sdf.Path("/materials").AppendChild(material.GetName())
        if not Sdf.CopySpec(source_layer, material.GetPath(), destination_layer, destination_path):
            raise RuntimeError(f"Could not copy native Blender material '{material.GetPath()}' to '{destination_path}'")
        material_paths.append(destination_path.pathString)

    destination_stage.GetRootLayer().Save()
    inspection_stage = Usd.Stage.Open(str(destination_usd_path))
    suspect_magenta_materials = []
    for material_path in material_paths:
        material = UsdShade.Material(inspection_stage.GetPrimAtPath(material_path))
        source = material.GetSurfaceOutput("mtlx").GetConnectedSource()
        if not source:
            continue

        surface_shader = UsdShade.Shader(source[0].GetPrim())
        base_color = surface_shader.GetInput("base_color")
        if not base_color or base_color.HasConnectedSource():
            continue
        base_color_value = base_color.Get()
        if base_color_value is not None and tuple(base_color_value) == (1.0, 0.0, 1.0):
            suspect_magenta_materials.append(material_path)

    return {
        "path": str(destination_usd_path),
        "material_prim_count": len(material_paths),
        "material_prims": material_paths,
        "suspect_magenta_materials": suspect_magenta_materials,
    }


def export_native_blender_materialx(
    scene_path: str | Path,
    out_dir: str | Path,
    *,
    runtime: BlenderRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Export Blender's native MaterialX conversion as a material-only USD file.
    
    Parameters:
        scene_path (str | Path): Path to the Blender scene.
        out_dir (str | Path): Directory where the exported USD file is written.
        runtime (BlenderRuntime | None): Blender runtime configuration.
        package_src (str | Path | None): Source path used by the Blender runtime.
        timeout (int): Maximum execution time in seconds.
    
    Returns:
        dict[str, Any]: Report describing the exported native MaterialX materials.
    
    Raises:
        FileNotFoundError: If the Blender scene does not exist.
        RuntimeError: If Blender fails to produce the native MaterialX export.
    """
    scene = Path(scene_path).expanduser().resolve()
    if not scene.is_file():
        raise FileNotFoundError(f"Blender scene was not found: {scene}")

    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = runtime or resolve_blender_runtime(version=None)
    package_src_path = Path(package_src).resolve() if package_src is not None else _default_package_src()
    material_usd_path = output_dir / "blender_native_materialx.usda"

    with tempfile.TemporaryDirectory(prefix="materials_processor_blender_native_materialx_") as temp_dir:
        native_scene_usd_path = Path(temp_dir) / "blender_native_scene.usda"
        completed = _run_blender_python(
            runtime,
            _native_materialx_export_code(scene, native_scene_usd_path),
            package_src_path,
            timeout=timeout,
        )
        if completed.returncode != 0 or not native_scene_usd_path.is_file():
            raise RuntimeError(
                f"Blender native MaterialX export failed.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        report = _copy_native_materials(native_scene_usd_path, material_usd_path)

    report["source"] = "blender-native-materialx"
    return report


def extract_blender_material_graphs(
    scene_path: str | Path,
    graph_json_path: str | Path,
    *,
    runtime: BlenderRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Extract standardized material graphs from a Blender scene into a JSON file.
    
    Parameters:
        scene_path (str | Path): Blender scene file to open.
        graph_json_path (str | Path): JSON file to write.
        runtime (BlenderRuntime | None): Optional resolved Blender runtime.
        package_src (str | Path | None): Source directory to expose to Blender.
        timeout (int): Maximum number of seconds to wait for Blender.
    
    Returns:
        dict[str, Any]: Summary of the extracted graphs, excluding the full graph payload.
    
    Raises:
        FileNotFoundError: If the Blender scene does not exist.
        RuntimeError: If extraction fails or Blender does not report a summary.
    """
    scene = Path(scene_path).expanduser().resolve()
    if not scene.is_file():
        raise FileNotFoundError(f"Blender scene was not found: {scene}")

    graph_json = Path(graph_json_path).expanduser().resolve()
    graph_json.parent.mkdir(parents=True, exist_ok=True)
    package_src_path = Path(package_src).resolve() if package_src is not None else _default_package_src()
    runtime = runtime or resolve_blender_runtime(version=None)

    completed = _run_blender_python(
        runtime,
        _extract_code(scene, graph_json),
        package_src_path,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Blender material graph extraction failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    for line in completed.stdout.splitlines():
        if line.startswith(BLENDER_GRAPH_EXPORT_PREFIX):
            return json.loads(line[len(BLENDER_GRAPH_EXPORT_PREFIX) :])

    raise RuntimeError(
        "Blender material graph extraction did not report a summary."
        f"\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def build_usd_material_files(
    graph_payload: dict[str, Any],
    out_dir: str | Path,
    *,
    targets: tuple[str, ...] = DEFAULT_EXPORT_TARGETS,
) -> dict[str, Any]:
    """Build USD material files from extracted Blender material graph data."""
    from pxr import Sdf, Usd

    from materials_processor.usd.recreator import USDMaterialRecreator

    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    graphs = [_material_graph_from_dict(graph) for graph in graph_payload.get("graphs") or []]
    report = {
        "scene": graph_payload.get("scene"),
        "output_dir": str(output_dir),
        "material_count": graph_payload.get("material_count", 0),
        "node_material_count": graph_payload.get("node_material_count", 0),
        "graph_count": len(graphs),
        "read_failures": graph_payload.get("read_failures", []),
        "unsupported_nodes": graph_payload.get("unsupported_nodes", {}),
        "missing_texture_paths": graph_payload.get("missing_texture_paths", []),
        "remapped_texture_paths": graph_payload.get("remapped_texture_paths", []),
        "usd_files": {},
    }

    for target in _targets_from_args(list(targets)):
        usd_path = output_dir / f"blender_scene_{TARGET_FILE_LABELS[target]}.usda"
        stage = Usd.Stage.CreateNew(str(usd_path))
        stage.SetDefaultPrim(stage.DefinePrim(Sdf.Path("/materials"), "Scope"))

        for graph in graphs:
            if not graph.nodeinfo_list or not graph.output_connections:
                continue
            USDMaterialRecreator(
                stage=stage,
                material_name=graph.material_name,
                nodeinfo_list=graph.nodeinfo_list,
                output_connections=graph.output_connections,
                parent_scope_path="/materials",
                target_renderer=target,
            ).run()

        stage.GetRootLayer().Save()
        opened_stage = Usd.Stage.Open(str(usd_path))
        if opened_stage is None:
            raise RuntimeError(f"USD file was written but could not be reopened: {usd_path}")

        shader_ids = {}
        materials = []
        for prim in opened_stage.Traverse():
            if prim.GetTypeName() == "Material":
                materials.append(prim.GetPath().pathString)
            attr = prim.GetAttribute("info:id")
            if attr and attr.Get():
                shader_id = attr.Get()
                shader_ids[shader_id] = shader_ids.get(shader_id, 0) + 1

        report["usd_files"][target] = {
            "path": str(usd_path),
            "material_prim_count": len(materials),
            "material_prims": materials,
            "shader_ids": shader_ids,
        }

    return report


def export_blender_scene_to_usd(
    scene_path: str | Path,
    out_dir: str | Path,
    *,
    targets: tuple[str, ...] = DEFAULT_EXPORT_TARGETS,
    runtime: BlenderRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
    texture_root: str | Path | None = None,
    remap_prefixes: tuple[tuple[str, str], ...] = (),
    missing_textures: str = "warn",
    fail_on_unsupported: bool = False,
    native_materialx: bool = False,
    bake_materials: tuple[str, ...] | None = None,
    bake_resolution: int = 1024,
    bake_auto_unwrap: bool = False,
    bake_mode: str = "pbr",
    bake_color_space: str = "lin_ap1",
    report_json: str | Path | None = None,
    graph_json: str | Path | None = None,
) -> dict[str, Any]:
    """
    Export Blender scene materials to USD MaterialX/OpenPBR files or baked-material outputs.
    
    Parameters:
        scene_path (str | Path): Path to the Blender scene.
        out_dir (str | Path): Directory for generated USD files and reports.
        targets (tuple[str, ...]): USD material targets to export.
        native_materialx (bool): Whether to include Blender's native MaterialX export.
        bake_materials (tuple[str, ...] | None): Material names to bake; when provided, uses the baking workflow instead of graph translation.
        bake_mode (str): Baking mode, such as ``"pbr"``, ``"beauty"``, or ``"auto"``.
        missing_textures (str): Policy for missing textures.
        fail_on_unsupported (bool): Whether unsupported material nodes cause the export to fail.
        report_json (str | Path | None): Optional path for the export report.
        graph_json (str | Path | None): Optional path for the extracted and remapped material graphs.
    
    Returns:
        dict[str, Any]: Report describing the generated files, materials, and export results.
    
    Raises:
        ValueError: If incompatible export options are selected or a configured report policy fails.
    """
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if bake_materials is not None:
        if native_materialx:
            raise ValueError("--bake and --native-materialx are alternative Blender export paths; choose one.")
        report = export_baked_blender_materials(
            scene_path,
            output_dir,
            material_names=bake_materials,
            resolution=bake_resolution,
            auto_unwrap=bake_auto_unwrap,
            bake_mode=bake_mode,
            color_space=bake_color_space,
            targets=targets,
            runtime=runtime,
            package_src=package_src,
            timeout=timeout,
        )
    else:
        graph_json_path = (
            Path(graph_json).expanduser().resolve() if graph_json else output_dir / "blender_material_graphs.json"
        )
        graph_json_path.parent.mkdir(parents=True, exist_ok=True)

        extract_blender_material_graphs(
            scene_path,
            graph_json_path,
            runtime=runtime,
            package_src=package_src,
            timeout=timeout,
        )
        graph_payload = json.loads(graph_json_path.read_text(encoding="utf-8"))
        graph_payload = _apply_texture_remaps(
            graph_payload,
            texture_root=texture_root,
            remap_prefixes=remap_prefixes,
        )
        graph_json_path.write_text(json.dumps(graph_payload, indent=2, sort_keys=True), encoding="utf-8")

        report = build_usd_material_files(graph_payload, output_dir, targets=targets)
        if native_materialx:
            report["native_materialx"] = export_native_blender_materialx(
                scene_path,
                output_dir,
                runtime=runtime,
                package_src=package_src,
                timeout=timeout,
            )
        report["graph_json"] = str(graph_json_path)

    report_json_path = Path(report_json).expanduser().resolve() if report_json else output_dir / "export_report.json"
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report["report_json"] = str(report_json_path)
    report_json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    _enforce_report_policies(
        report,
        fail_on_unsupported=fail_on_unsupported,
        missing_textures=missing_textures,
    )
    return report


def inspect_blender_scene(
    scene_path: str | Path,
    *,
    runtime: BlenderRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
    texture_root: str | Path | None = None,
    remap_prefixes: tuple[tuple[str, str], ...] = (),
    graph_json: str | Path | None = None,
    report_json: str | Path | None = None,
    missing_textures: str = "warn",
    fail_on_unsupported: bool = False,
) -> dict[str, Any]:
    """Inspect a Blender scene's materials without writing USD files."""
    if graph_json:
        graph_json_path = Path(graph_json).expanduser().resolve()
        graph_json_path.parent.mkdir(parents=True, exist_ok=True)
        cleanup_dir = None
    else:
        cleanup_dir = tempfile.TemporaryDirectory(prefix="materials_processor_blender_inspect_")
        graph_json_path = Path(cleanup_dir.name) / "blender_material_graphs.json"

    try:
        extract_blender_material_graphs(
            scene_path,
            graph_json_path,
            runtime=runtime,
            package_src=package_src,
            timeout=timeout,
        )
        graph_payload = json.loads(graph_json_path.read_text(encoding="utf-8"))
        graph_payload = _apply_texture_remaps(
            graph_payload,
            texture_root=texture_root,
            remap_prefixes=remap_prefixes,
        )
        if graph_json:
            graph_json_path.write_text(json.dumps(graph_payload, indent=2, sort_keys=True), encoding="utf-8")

        graphs = graph_payload.get("graphs") or []
        report = {
            "scene": graph_payload.get("scene"),
            "material_count": graph_payload.get("material_count", 0),
            "node_material_count": graph_payload.get("node_material_count", 0),
            "graph_count": len(graphs),
            "read_failures": graph_payload.get("read_failures", []),
            "unsupported_nodes": graph_payload.get("unsupported_nodes", {}),
            "missing_texture_paths": graph_payload.get("missing_texture_paths", []),
            "remapped_texture_paths": graph_payload.get("remapped_texture_paths", []),
        }
        if graph_json:
            report["graph_json"] = str(graph_json_path)
        if report_json:
            report_json_path = Path(report_json).expanduser().resolve()
            report_json_path.parent.mkdir(parents=True, exist_ok=True)
            report["report_json"] = str(report_json_path)
            report_json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        _enforce_report_policies(
            report,
            fail_on_unsupported=fail_on_unsupported,
            missing_textures=missing_textures,
        )
        return report
    finally:
        if cleanup_dir is not None:
            cleanup_dir.cleanup()


def _targets_from_args(values: list[str]) -> tuple[str, ...]:
    targets = []
    values = values or ["all"]
    for value in values:
        if value == "all":
            targets.extend(DEFAULT_EXPORT_TARGETS)
        else:
            targets.append(TARGET_ALIASES[value])
    return tuple(dict.fromkeys(targets))


def add_blender_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    """Add common Blender runtime options to an argument parser."""
    parser.add_argument("--blender-exe", help="Explicit path to blender.exe.")
    parser.add_argument("--blender-root", help="Explicit Blender install root.")
    parser.add_argument("--blender-version", help="Blender version to discover, e.g. 4.5.")
    parser.add_argument("--timeout", type=int, default=300, help="Headless Blender timeout in seconds.")
    parser.add_argument(
        "--package-src",
        default=None,
        help="Source directory to expose to Blender. Defaults to this checkout's src directory.",
    )


def add_texture_arguments(parser: argparse.ArgumentParser) -> None:
    """Add texture reporting/remap options to an argument parser."""
    parser.add_argument(
        "--texture-root",
        default=None,
        help="Directory to search by filename for missing texture paths.",
    )
    parser.add_argument(
        "--remap-prefix",
        action="append",
        default=None,
        metavar="OLD=NEW",
        help="Remap texture paths with the given prefix replacement. Can be passed more than once.",
    )
    parser.add_argument(
        "--missing-textures",
        choices=MISSING_TEXTURE_POLICIES,
        default="warn",
        help="Whether missing textures should warn in the report or fail the command.",
    )
    parser.add_argument(
        "--fail-on-unsupported",
        action="store_true",
        help="Fail when unsupported Blender nodes are found.",
    )


def add_blender_export_parser(subparsers) -> argparse.ArgumentParser:
    """Add the Blender ``export-usd`` subcommand to a subparser collection."""
    export_parser = subparsers.add_parser(
        "export-usd",
        help="Export node materials from a .blend scene to USD material files.",
    )
    export_parser.add_argument("scene", help="Path to the .blend scene.")
    export_parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to write USD files and reports. Defaults to a temp directory.",
    )
    export_parser.add_argument(
        "--target",
        choices=("materialx", "mtlx", "openpbr", "all"),
        action="append",
        default=None,
        help="USD material target to export. Can be passed more than once. Default: all.",
    )
    export_parser.add_argument("--report-json", default=None, help="Explicit path for the export report JSON.")
    export_parser.add_argument(
        "--graph-json", default=None, help="Explicit path for the extracted material graph JSON."
    )
    export_parser.add_argument(
        "--native-materialx",
        action="store_true",
        help="Also export Blender's native MaterialX graph as a material-only USD fallback.",
    )
    export_parser.add_argument(
        "--bake",
        action="append",
        nargs="?",
        const="all",
        metavar="MATERIAL",
        help="Bake materials instead of translating nodes. Omit MATERIAL to bake all assigned materials.",
    )
    export_parser.add_argument(
        "--bake-mode",
        choices=("pbr", "beauty", "auto"),
        default="pbr",
        help="pbr bakes only canonical PBR streams; beauty bakes the scene-lit appearance; auto falls back to beauty. Default: pbr.",
    )
    export_parser.add_argument(
        "--bake-resolution",
        type=int,
        default=1024,
        help="Square resolution for each baked texture map. Default: 1024.",
    )
    export_parser.add_argument(
        "--bake-auto-unwrap",
        action="store_true",
        help="Create a temporary Smart UV Project map when a baked mesh has no UVs.",
    )
    export_parser.add_argument(
        "--bake-color-space",
        default="lin_ap1",
        help="MaterialX color space to declare for baked color EXRs. Default: lin_ap1.",
    )
    add_blender_runtime_arguments(export_parser)
    add_texture_arguments(export_parser)
    return export_parser


def add_blender_inspect_parser(subparsers) -> argparse.ArgumentParser:
    """Add the Blender ``inspect`` subcommand to a subparser collection."""
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect node materials in a .blend scene without writing USD files.",
    )
    inspect_parser.add_argument("scene", help="Path to the .blend scene.")
    inspect_parser.add_argument("--report-json", default=None, help="Optional path for the inspection report JSON.")
    inspect_parser.add_argument(
        "--graph-json", default=None, help="Optional path for the extracted material graph JSON."
    )
    add_blender_runtime_arguments(inspect_parser)
    add_texture_arguments(inspect_parser)
    return inspect_parser


def _runtime_from_args(args) -> BlenderRuntime:
    """Resolve Blender runtime from parsed arguments."""
    return resolve_blender_runtime(
        version=args.blender_version,
        root=args.blender_root,
        blender_exe=args.blender_exe,
    )


def run_export_from_args(args) -> dict[str, Any]:
    """
    Run the Blender scene export using parsed command-line arguments.
    
    Parameters:
        args: Parsed command-line arguments containing scene, export, runtime, texture, baking, and report settings.
    
    Returns:
        dict[str, Any]: Export report.
    """
    out_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="materials_processor_blender_usd_"))
    return export_blender_scene_to_usd(
        args.scene,
        out_dir,
        targets=_targets_from_args(args.target),
        runtime=_runtime_from_args(args),
        package_src=args.package_src,
        timeout=args.timeout,
        texture_root=args.texture_root,
        remap_prefixes=_texture_remaps_from_args(args.remap_prefix),
        missing_textures=args.missing_textures,
        fail_on_unsupported=args.fail_on_unsupported,
        native_materialx=args.native_materialx,
        bake_materials=tuple(args.bake) if args.bake else None,
        bake_resolution=args.bake_resolution,
        bake_auto_unwrap=args.bake_auto_unwrap,
        bake_mode=args.bake_mode,
        bake_color_space=args.bake_color_space,
        report_json=args.report_json,
        graph_json=args.graph_json,
    )


def run_inspect_from_args(args) -> dict[str, Any]:
    """Run Blender material inspection from parsed CLI arguments."""
    return inspect_blender_scene(
        args.scene,
        runtime=_runtime_from_args(args),
        package_src=args.package_src,
        timeout=args.timeout,
        texture_root=args.texture_root,
        remap_prefixes=_texture_remaps_from_args(args.remap_prefix),
        graph_json=args.graph_json,
        report_json=args.report_json,
        missing_textures=args.missing_textures,
        fail_on_unsupported=args.fail_on_unsupported,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="materials-processor-blender")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_blender_export_parser(subparsers)
    add_blender_inspect_parser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Blender command line interface."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "export-usd":
            report = run_export_from_args(args)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        if args.command == "inspect":
            report = run_inspect_from_args(args)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Headless Blender integration coverage for bake-source selection."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pxr import Usd

from materials_processor.dcc.blender.cli import export_baked_blender_materials, export_blender_scene_to_usd
from materials_processor.dcc.blender.runtime import _run_blender_python, resolve_blender_runtime
from blender_bake_fixture import build_bake_decision_fixture


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HYTHON = Path(r"C:\Program Files\Side Effects Software\Houdini 21.0.631\bin\hython.exe")
DEFAULT_HUSK = DEFAULT_HYTHON.with_name("husk.exe")
SOLARIS_RESULT_PREFIX = "MATERIALS_PROCESSOR_SOLARIS_BAKE_FIXTURE="
RAW_NORMAL_RESULT_PREFIX = "MATERIALS_PROCESSOR_RAW_NORMAL="
RAW_EXR_COMPARISON_PREFIX = "MATERIALS_PROCESSOR_RAW_EXR_COMPARISON="


def _resolve_hython() -> str | None:
    """Locate Hython without requiring Houdini to be on PATH."""
    if configured_hython := os.environ.get("MATERIALS_PROCESSOR_HYTHON"):
        if Path(configured_hython).is_file():
            return configured_hython
    if path_hython := shutil.which("hython"):
        return path_hython
    if DEFAULT_HYTHON.is_file():
        return str(DEFAULT_HYTHON)
    return None


def _resolve_husk() -> str | None:
    """Locate Husk without requiring Houdini to be on PATH."""
    if configured_husk := os.environ.get("MATERIALS_PROCESSOR_HUSK"):
        if Path(configured_husk).is_file():
            return configured_husk
    if path_husk := shutil.which("husk"):
        return path_husk
    if DEFAULT_HUSK.is_file():
        return str(DEFAULT_HUSK)
    return None


def _load_baked_materials_in_solaris(hython: str, usd_path: Path) -> dict[str, list[str]]:
    """Load a baked material-only layer through Solaris and report shader ids."""
    code = f"""
import json
import hou

node = hou.node('/stage').createNode('sublayer', 'blender_bake_fixture')
node.parm('filepath1').set({str(usd_path)!r})
stage = node.stage()
materials = [prim for prim in stage.GetPrimAtPath('/materials').GetChildren() if prim.GetTypeName() == 'Material']
result = {{
    'material_names': sorted(prim.GetName() for prim in materials),
    'shader_ids': sorted(prim.GetChild('surface').GetAttribute('info:id').Get() for prim in materials),
}}
print({SOLARIS_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()
    completed = subprocess.run([hython, "-"], input=code, text=True, capture_output=True, timeout=120, check=False)
    if completed.returncode != 0:
        pytest.fail(f"Solaris bake-fixture import failed:\n{completed.stdout}\n{completed.stderr}")
    for line in completed.stdout.splitlines():
        if line.startswith(SOLARIS_RESULT_PREFIX):
            return json.loads(line[len(SOLARIS_RESULT_PREFIX):])
    pytest.fail(f"Solaris bake-fixture import did not return its result:\n{completed.stdout}\n{completed.stderr}")


def _load_material_in_solaris(hython: str, usd_path: Path, material_name: str) -> dict[str, object]:
    """Load one exported material through Solaris and return its surface id."""
    code = f"""
import json
import hou

node = hou.node('/stage').createNode('sublayer', 'blender_group_input_fixture')
node.parm('filepath1').set({str(usd_path)!r})
stage = node.stage()
material = stage.GetPrimAtPath('/materials/{material_name}')
surface = material.GetChild('Internal_Principled')
result = {{
    'material_is_valid': material.IsValid(),
    'surface_is_valid': surface.IsValid(),
    'shader_id': surface.GetAttribute('info:id').Get() if surface.IsValid() else None,
}}
print({SOLARIS_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()
    completed = subprocess.run([hython, "-"], input=code, text=True, capture_output=True, timeout=120, check=False)
    if completed.returncode != 0:
        pytest.fail(f"Solaris Group Input import failed:\n{completed.stdout}\n{completed.stderr}")
    for line in completed.stdout.splitlines():
        if line.startswith(SOLARIS_RESULT_PREFIX):
            return json.loads(line[len(SOLARIS_RESULT_PREFIX):])
    pytest.fail(f"Solaris Group Input import did not return its result:\n{completed.stdout}\n{completed.stderr}")


def _iter_graph_nodes(nodes):
    """Yield graph node dictionaries recursively."""
    for node in nodes:
        yield node
        yield from _iter_graph_nodes(node.get("children_list") or [])


def _inspect_raw_normal_texture(runtime, texture_path: Path) -> dict[str, list[float]]:
    """Read channel extrema in Blender without applying a display transform."""
    code = f"""
import json
import bpy

image = bpy.data.images.load({str(texture_path)!r}, check_existing=False)
for color_space in ("Utility - Raw", "raw", "Non-Color"):
    try:
        image.colorspace_settings.name = color_space
        break
    except TypeError:
        continue
pixels = image.pixels[:]
result = {{
    "min": [min(pixels[channel::4]) for channel in range(3)],
    "max": [max(pixels[channel::4]) for channel in range(3)],
}}
print({RAW_NORMAL_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()
    completed = _run_blender_python(runtime, code, ROOT / "src", timeout=120)
    if completed.returncode != 0 or "Traceback (most recent call last):" in completed.stdout:
        pytest.fail(f"Raw normal texture inspection failed:\n{completed.stdout}\n{completed.stderr}")
    for line in completed.stdout.splitlines():
        if line.startswith(RAW_NORMAL_RESULT_PREFIX):
            return json.loads(line[len(RAW_NORMAL_RESULT_PREFIX) :])
    pytest.fail(f"Raw normal texture inspection did not return its result:\n{completed.stdout}\n{completed.stderr}")


def _run_python_script(arguments: list[str], *, timeout: int = 240) -> None:
    """Run a project helper script and include its diagnostics on failure."""
    completed = subprocess.run(
        [sys.executable, *arguments],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        pytest.fail(f"Project helper script failed:\n{completed.stdout}\n{completed.stderr}")


def _render_karma_xpu(husk: str, stage_path: Path, output_path: Path) -> None:
    """Render a diagnostic stage to raw EXR through Karma XPU."""
    completed = subprocess.run(
        [
            husk,
            "-R",
            "BRAY_HdKarmaXPU",
            "--gpu",
            "-p",
            "16",
            "--ocio",
            "0",
            "--headlight",
            "none",
            "--make-output-path",
            "-o",
            str(output_path),
            str(stage_path),
        ],
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )
    if completed.returncode or not output_path.is_file():
        pytest.fail(f"Karma XPU albedo render failed:\n{completed.stdout}\n{completed.stderr}")


def _compare_raw_exr_images(runtime, source_path: Path, target_path: Path) -> dict[str, float | int]:
    """Compare the covered inner region of two raw EXRs in Blender."""
    code = f"""
import json
import bpy

def load_raw(path):
    image = bpy.data.images.load(path, check_existing=False)
    for color_space in ("Utility - Raw", "Raw", "Non-Color"):
        try:
            image.colorspace_settings.name = color_space
            break
        except TypeError:
            continue
    return image

source = load_raw({str(source_path)!r})
target = load_raw({str(target_path)!r})
if source.size[:] != target.size[:]:
    raise RuntimeError(f"image dimensions differ: {{source.size[:]}} versus {{target.size[:]}}")
width, height = source.size
source_pixels = source.pixels[:]
target_pixels = target.pixels[:]
covered = [
    (index % width, index // width)
    for index in range(width * height)
    if max(source_pixels[index * 4 : index * 4 + 3]) > 0.01
]
if not covered:
    raise RuntimeError("source image has no covered pixels")
minimum_x = min(point[0] for point in covered)
maximum_x = max(point[0] for point in covered)
minimum_y = min(point[1] for point in covered)
maximum_y = max(point[1] for point in covered)
margin = max(8, min(maximum_x - minimum_x, maximum_y - minimum_y) // 12)
errors = []
for y in range(minimum_y + margin, maximum_y - margin + 1):
    for x in range(minimum_x + margin, maximum_x - margin + 1):
        pixel = (y * width + x) * 4
        errors.extend(abs(source_pixels[pixel + channel] - target_pixels[pixel + channel]) for channel in range(3))
result = {{
    "mae": sum(errors) / len(errors),
    "max_abs": max(errors),
    "sample_count": len(errors),
}}
print({RAW_EXR_COMPARISON_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()
    completed = _run_blender_python(runtime, code, ROOT / "src", timeout=120)
    if completed.returncode != 0 or "Traceback (most recent call last):" in completed.stdout:
        pytest.fail(f"Raw EXR comparison failed:\n{completed.stdout}\n{completed.stderr}")
    for line in completed.stdout.splitlines():
        if line.startswith(RAW_EXR_COMPARISON_PREFIX):
            return json.loads(line[len(RAW_EXR_COMPARISON_PREFIX) :])
    pytest.fail(f"Raw EXR comparison did not return its result:\n{completed.stdout}\n{completed.stderr}")


@pytest.mark.blender
def test_auto_bake_uses_pbr_for_principled_and_beauty_for_mixed_closure(tmp_path):
    """Export a generated scene and verify the strict PBR/beauty decision."""
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    scene_path = tmp_path / "bake_decisions.blend"
    build_bake_decision_fixture(scene_path, runtime, ROOT / "src")
    report = export_baked_blender_materials(
        scene_path,
        tmp_path / "export",
        material_names=("all",),
        bake_mode="auto",
        resolution=64,
        runtime=runtime,
        package_src=ROOT / "src",
        timeout=180,
    )

    baked = {entry["material"]: entry for entry in report["baked_materials"]}
    assert set(baked) == {"Direct PBR", "Normal Map PBR", "Group Input PBR", "Group Input Linked PBR", "Complex Closure"}
    assert baked["Direct PBR"]["bake_mode"] == "pbr"
    assert baked["Normal Map PBR"]["bake_mode"] == "pbr"
    assert baked["Group Input PBR"]["bake_mode"] == "pbr"
    assert baked["Group Input Linked PBR"]["bake_mode"] == "pbr"
    assert baked["Complex Closure"]["bake_mode"] == "beauty"
    assert "ShaderNodeBsdfDiffuse" in baked["Complex Closure"]["pbr_rejection"]
    assert "ShaderNodeBsdfTranslucent" in baked["Complex Closure"]["pbr_rejection"]
    assert Path(baked["Complex Closure"]["maps"]["beauty"]).is_file()
    assert not report["skipped_materials"]
    assert report["usd_files"]["mtlx"]["material_prim_count"] == 5
    assert report["usd_files"]["openpbr"]["material_prim_count"] == 5


@pytest.mark.blender
def test_group_input_fixture_flattens_to_direct_usd_graphs(tmp_path):
    """Convert the generated Group Input material without requiring a bake."""
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    scene_path = tmp_path / "bake_decisions.blend"
    build_bake_decision_fixture(scene_path, runtime, ROOT / "src")
    report = export_blender_scene_to_usd(
        scene_path,
        tmp_path / "export",
        runtime=runtime,
        package_src=ROOT / "src",
        timeout=180,
    )
    graphs = json.loads(Path(report["graph_json"]).read_text(encoding="utf-8"))["graphs"]
    group_graph = next(graph for graph in graphs if graph["material_name"] == "Group Input PBR")
    linked_group_graph = next(graph for graph in graphs if graph["material_name"] == "Group Input Linked PBR")
    nodes = list(_iter_graph_nodes(group_graph["nodeinfo_list"]))
    principled = next(node for node in nodes if node["node_type"] == "GENERIC::standard_surface")
    parameters = {parameter["generic_name"]: parameter["value"] for parameter in principled["parameters"]}
    linked_nodes = list(_iter_graph_nodes(linked_group_graph["nodeinfo_list"]))
    linked_principled = next(node for node in linked_nodes if node["node_type"] == "GENERIC::standard_surface")
    linked_roughness = next(node for node in linked_nodes if node["node_name"] == "Outer Group Roughness")

    assert parameters["base_color"] == pytest.approx([0.75, 0.2, 0.1, 1.0])
    assert "roughness" not in {parameter["generic_name"] for parameter in linked_principled["parameters"]}
    assert linked_roughness["connection_info"]
    assert report["usd_files"]["mtlx"]["material_prim_count"] == 5
    assert report["usd_files"]["openpbr"]["material_prim_count"] == 5


@pytest.mark.blender
def test_nonflat_normal_bake_is_raw_and_uses_gltf_normalmap(tmp_path):
    """Preserve a varying tangent-space normal map through the PBR bake route."""
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    scene_path = tmp_path / "normal_map_fixture.blend"
    build_bake_decision_fixture(scene_path, runtime, ROOT / "src")
    report = export_baked_blender_materials(
        scene_path,
        tmp_path / "export",
        material_names=("Normal Map PBR",),
        bake_mode="pbr",
        resolution=64,
        runtime=runtime,
        package_src=ROOT / "src",
        timeout=180,
    )

    baked = report["baked_materials"]
    assert len(baked) == 1
    assert baked[0]["normal_map_convention"] == "tangent-space glTF (ND_gltf_normalmap_vector3_1_0)"
    normal_path = Path(baked[0]["maps"]["normal"])
    assert normal_path.is_file()
    extrema = _inspect_raw_normal_texture(runtime, normal_path)
    assert extrema["min"][0] < 0.35 and extrema["max"][0] > 0.65
    assert extrema["min"][1] < 0.35 and extrema["max"][1] > 0.65
    assert extrema["min"][2] > 0.80

    stage = Usd.Stage.Open(report["usd_files"]["mtlx"]["path"])
    normal_image = stage.GetPrimAtPath("/materials/Normal_Map_PBR/normal_image")
    assert normal_image.GetAttribute("info:id").Get() == "ND_gltf_normalmap_vector3_1_0"
    assert normal_image.GetAttribute("inputs:file").GetColorSpace() == "raw"


@pytest.mark.blender
@pytest.mark.hython
def test_calibrated_albedo_bake_matches_karma_xpu_raw_exr(tmp_path):
    """Keep the calibrated albedo bake within a raw cross-renderer tolerance."""
    husk = _resolve_husk()
    if not husk:
        pytest.skip("Husk is not available")
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    scene_path = tmp_path / "albedo_fixture.blend"
    bake_dir = tmp_path / "baked"
    source_exr = tmp_path / "cycles_albedo.exr"
    geometry_usd = tmp_path / "comparison_geometry.usda"
    preview_usd = tmp_path / "karma_albedo.usda"
    target_exr = tmp_path / "karma_albedo.exr"
    build_bake_decision_fixture(scene_path, runtime, ROOT / "src")
    report = export_baked_blender_materials(
        scene_path,
        bake_dir,
        material_names=("Direct PBR",),
        bake_mode="pbr",
        resolution=64,
        runtime=runtime,
        package_src=ROOT / "src",
        timeout=180,
    )
    materialx_path = Path(report["usd_files"]["mtlx"]["path"])
    _run_python_script(
        [
            str(ROOT / "scripts" / "render_blender_albedo_grid.py"),
            str(scene_path),
            "--material",
            "Direct PBR",
            "--output",
            str(source_exr),
            "--geometry-usd",
            str(geometry_usd),
        ]
    )
    _run_python_script(
        [
            str(ROOT / "scripts" / "make_baked_usd_preview_stage.py"),
            str(materialx_path),
            "--output",
            str(preview_usd),
            "--albedo-only",
            "--geometry",
            str(geometry_usd),
            "--material",
            "Direct_PBR",
        ]
    )
    _render_karma_xpu(husk, preview_usd, target_exr)
    comparison = _compare_raw_exr_images(runtime, source_exr, target_exr)

    assert comparison["sample_count"] > 1000
    assert comparison["mae"] < 0.005
    assert comparison["max_abs"] < 0.01


@pytest.mark.blender
@pytest.mark.hython
def test_group_input_fixture_direct_usd_exports_load_in_solaris(tmp_path):
    """Ensure direct conversion of Group Input values loads in both targets."""
    hython = _resolve_hython()
    if not hython:
        pytest.skip("Hython is not available")
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    scene_path = tmp_path / "bake_decisions.blend"
    build_bake_decision_fixture(scene_path, runtime, ROOT / "src")
    report = export_blender_scene_to_usd(
        scene_path,
        tmp_path / "export",
        runtime=runtime,
        package_src=ROOT / "src",
        timeout=180,
    )
    for target, expected_shader_id in (
        ("mtlx", "ND_standard_surface_surfaceshader"),
        ("openpbr", "ND_open_pbr_surface_surfaceshader"),
    ):
        loaded = _load_material_in_solaris(
            hython,
            Path(report["usd_files"][target]["path"]),
            "Group_Input_PBR",
        )
        assert loaded == {
            "material_is_valid": True,
            "surface_is_valid": True,
            "shader_id": expected_shader_id,
        }


@pytest.mark.blender
@pytest.mark.hython
def test_auto_bake_fixture_loads_pbr_and_beauty_materials_in_solaris(tmp_path):
    """Ensure Solaris can load the real Blender fixture's PBR and beauty materials."""
    hython = _resolve_hython()
    if not hython:
        pytest.skip("Hython is not available")
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    scene_path = tmp_path / "bake_decisions.blend"
    build_bake_decision_fixture(scene_path, runtime, ROOT / "src")
    report = export_baked_blender_materials(
        scene_path,
        tmp_path / "export",
        material_names=("all",),
        bake_mode="auto",
        resolution=64,
        runtime=runtime,
        package_src=ROOT / "src",
        timeout=180,
    )

    for target, expected_pbr_id in (
        ("mtlx", "ND_standard_surface_surfaceshader"),
        ("openpbr", "ND_open_pbr_surface_surfaceshader"),
    ):
        loaded = _load_baked_materials_in_solaris(hython, Path(report["usd_files"][target]["path"]))
        assert loaded["material_names"] == [
            "Complex_Closure",
            "Direct_PBR",
            "Group_Input_Linked_PBR",
            "Group_Input_PBR",
            "Normal_Map_PBR",
        ]
        assert loaded["shader_ids"] == [expected_pbr_id, expected_pbr_id, expected_pbr_id, expected_pbr_id, "ND_surface_unlit"]

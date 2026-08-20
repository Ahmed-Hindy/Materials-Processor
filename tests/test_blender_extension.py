"""Coverage for the installable Blender extension package."""

from __future__ import annotations

import importlib.util
import json
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from materials_processor.dcc.blender.runtime import (
    _parse_prefixed_output,
    _run_blender_python,
    resolve_blender_runtime,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "blender_extension" / "blender_manifest.toml"
EXTENSION_ENTRYPOINT = ROOT / "blender_extension" / "__init__.py"
INSTALL_SMOKE_RESULT_PREFIX = "MATERIALS_PROCESSOR_BLENDER_EXTENSION_SMOKE="


def _load_builder_module():
    """Load the standalone extension build script for direct unit coverage."""
    module_path = ROOT / "scripts" / "build_blender_extension.py"
    spec = importlib.util.spec_from_file_location("build_blender_extension", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Blender extension build script.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_blender_extension_manifest_declares_an_installable_addon():
    manifest = tomllib.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "1.0.0"
    assert manifest["id"] == "materials_processor"
    assert manifest["type"] == "add-on"
    assert manifest["blender_version_min"] == "5.0.0"
    assert manifest["license"] == ["SPDX:LicenseRef-Proprietary"]


def test_blender_extension_entrypoint_exposes_the_bundled_runtime_package():
    entrypoint = EXTENSION_ENTRYPOINT.read_text(encoding="utf-8")

    assert "from . import materials_processor as _materials_processor" in entrypoint
    assert 'sys.modules["materials_processor"] = _materials_processor' in entrypoint


def test_blender_extension_staging_includes_the_runtime_package(tmp_path):
    builder = _load_builder_module()
    stage_dir = tmp_path / "extension"

    builder._stage_extension(stage_dir)

    assert (stage_dir / "blender_manifest.toml").is_file()
    assert (stage_dir / "__init__.py").is_file()
    assert (stage_dir / "materials_processor" / "dcc" / "blender" / "addon.py").is_file()


@pytest.mark.blender
def test_blender_extension_builds_and_validates_an_installable_archive(tmp_path):
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    builder = _load_builder_module()
    archive = builder.build_extension(tmp_path / "materials_processor.zip", blender_exe=runtime.blender_exe)

    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
    assert "blender_manifest.toml" in names
    assert "__init__.py" in names
    assert "materials_processor/dcc/blender/addon.py" in names


@pytest.mark.blender
def test_blender_extension_installs_enables_and_runs_a_conversion_operator(tmp_path):
    """Verify the shipped archive works in a clean Blender extension profile."""
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    builder = _load_builder_module()
    archive = builder.build_extension(tmp_path / "materials_processor.zip", blender_exe=runtime.blender_exe)
    code = f"""
import json

import bpy


bpy.ops.extensions.package_install_files(
    filepath={str(archive)!r},
    repo="user_default",
    enable_on_install=True,
)

mesh = bpy.data.meshes.new("extension_smoke_mesh")
object_ = bpy.data.objects.new("extension_smoke_object", mesh)
bpy.context.collection.objects.link(object_)
bpy.context.view_layer.objects.active = object_
object_.select_set(True)

source = bpy.data.materials.new("extension_smoke_source")
source.use_nodes = True
source_tree = source.node_tree
source_tree.nodes.clear()
output = source_tree.nodes.new(type="ShaderNodeOutputMaterial")
principled = source_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
source_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
object_.data.materials.append(source)

operator_result = bpy.ops.node.matproc_convert_active_material()
result = {{
    "converted_name": object_.active_material.name,
    "operator_result": sorted(operator_result),
    "source_name": source.name,
}}
print({INSTALL_SMOKE_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()

    completed = _run_blender_python(runtime, code, ROOT / "src", timeout=120)
    if completed.returncode:
        raise RuntimeError(
            "Blender extension install smoke test failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    result = _parse_prefixed_output(
        completed.stdout,
        completed.stderr,
        INSTALL_SMOKE_RESULT_PREFIX,
        "extension install smoke test",
    )
    assert result["operator_result"] == ["FINISHED"]
    assert result["source_name"] == "extension_smoke_source"
    assert result["converted_name"].startswith("extension_smoke_source_converted")

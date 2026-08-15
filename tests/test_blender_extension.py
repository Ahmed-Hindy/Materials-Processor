"""Coverage for the installable Blender extension package."""

from __future__ import annotations

import importlib.util
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from materials_processor.dcc.blender.runtime import resolve_blender_runtime

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "blender_extension" / "blender_manifest.toml"
EXTENSION_ENTRYPOINT = ROOT / "blender_extension" / "__init__.py"


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

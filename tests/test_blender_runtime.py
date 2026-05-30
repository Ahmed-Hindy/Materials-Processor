import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from materials_processor.dcc.blender.runtime import (
    BLENDER_EXE_ENV_VAR,
    BLENDER_ROOT_ENV_VAR,
    MATERIAL_SMOKE_RESULT_PREFIX,
    VALIDATION_RESULT_PREFIX,
    BlenderRuntime,
    _default_package_src,
    _default_blender_root,
    resolve_blender_runtime,
    validate_blender_material_smoke,
    validate_blender_runtime,
)

ROOT = Path(__file__).resolve().parents[1]


def _fake_blender_root(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    blender_exe = tmp_path / "blender.exe"
    blender_exe.write_text("", encoding="utf-8")
    return tmp_path


def test_default_blender_root_uses_standard_windows_install_path():
    assert _default_blender_root("4.0") == Path("C:/Program Files/Blender Foundation/Blender 4.0")


def test_resolve_blender_runtime_uses_explicit_root(tmp_path):
    blender_root = _fake_blender_root(tmp_path / "Blender 4.0")

    runtime = resolve_blender_runtime(root=blender_root)

    assert runtime == BlenderRuntime(
        root=blender_root.resolve(),
        blender_exe=(blender_root / "blender.exe").resolve(),
        version="4.0",
        python_version="",
        api_version="",
    )


def test_resolve_blender_runtime_uses_env_executable_override(tmp_path, monkeypatch):
    blender_root = _fake_blender_root(tmp_path / "PortableBlender")
    monkeypatch.setenv(BLENDER_EXE_ENV_VAR, str(blender_root / "blender.exe"))

    runtime = resolve_blender_runtime()

    assert runtime.root == blender_root.resolve()
    assert runtime.blender_exe == (blender_root / "blender.exe").resolve()


def test_resolve_blender_runtime_uses_env_root_override(tmp_path, monkeypatch):
    blender_root = _fake_blender_root(tmp_path / "Blender 4.2")
    monkeypatch.setenv(BLENDER_ROOT_ENV_VAR, str(blender_root))

    runtime = resolve_blender_runtime(version=None)

    assert runtime.root == blender_root.resolve()
    assert runtime.blender_exe == (blender_root / "blender.exe").resolve()


def test_resolve_blender_runtime_reports_missing_executable(tmp_path):
    with pytest.raises(FileNotFoundError, match="Blender executable"):
        resolve_blender_runtime(root=tmp_path)


def test_validate_blender_runtime_uses_headless_blender_pythonpath_and_isolated_prefs(tmp_path, monkeypatch):
    blender_root = _fake_blender_root(tmp_path / "Blender 4.0")
    runtime = resolve_blender_runtime(root=blender_root)
    package_src = tmp_path / "src"
    package_src.mkdir()
    captured = {}

    def fake_run(command, check, capture_output, env, text, timeout):
        captured["command"] = command
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["env"] = env
        captured["text"] = text
        captured["timeout"] = timeout
        result = {
            "api_version": "4.0.0",
            "package_file": str(package_src / "materials_processor" / "__init__.py"),
            "python_version": "3.11.7",
            "version": "4.0.2",
        }
        return SimpleNamespace(
            returncode=0,
            stdout=f"{VALIDATION_RESULT_PREFIX}{json.dumps(result)}\n",
            stderr="",
        )

    monkeypatch.setattr("materials_processor.dcc.blender.runtime.subprocess.run", fake_run)

    validated = validate_blender_runtime(runtime=runtime, package_src=package_src, timeout=3)

    assert validated.version == "4.0.2"
    assert validated.python_version == "3.11.7"
    assert validated.api_version == "4.0.0"
    assert captured["command"][:3] == [str(runtime.blender_exe), "--background", "--factory-startup"]
    assert "--python" in captured["command"]
    assert captured["command"][-1].endswith("validate_materials_processor.py")
    assert captured["check"] is False
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["timeout"] == 3
    assert captured["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(package_src.resolve())
    assert "materials_processor_blender_user_" in captured["env"]["BLENDER_USER_CONFIG"]
    assert "materials_processor_blender_user_" in captured["env"]["BLENDER_USER_SCRIPTS"]
    assert "materials_processor_blender_user_" in captured["env"]["BLENDER_USER_DATAFILES"]


def test_validate_blender_material_smoke_parses_recreation_result(tmp_path, monkeypatch):
    blender_root = _fake_blender_root(tmp_path / "Blender 4.0")
    runtime = resolve_blender_runtime(root=blender_root)
    package_src = tmp_path / "src"
    package_src.mkdir()

    def fake_run(command, check, capture_output, env, text, timeout):
        result = {
            "node_count": 1,
            "output_count": 1,
            "recreated": True,
            "target_node_types": ["ShaderNodeBsdfPrincipled", "ShaderNodeOutputMaterial"],
        }
        return SimpleNamespace(
            returncode=0,
            stdout=f"{MATERIAL_SMOKE_RESULT_PREFIX}{json.dumps(result)}\n",
            stderr="",
        )

    monkeypatch.setattr("materials_processor.dcc.blender.runtime.subprocess.run", fake_run)

    result = validate_blender_material_smoke(runtime=runtime, package_src=package_src, timeout=3)

    assert result["recreated"] is True
    assert result["target_node_types"] == ["ShaderNodeBsdfPrincipled", "ShaderNodeOutputMaterial"]


def test_validate_blender_runtime_default_package_src_points_to_src():
    assert _default_package_src() == ROOT / "src"


@pytest.mark.blender
def test_validate_local_blender_runtime_when_available():
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    validated = validate_blender_runtime(runtime=runtime, package_src=ROOT / "src", timeout=120)
    smoke = validate_blender_material_smoke(runtime=validated, package_src=ROOT / "src", timeout=120)

    assert validated.version
    assert validated.python_version
    assert smoke["recreated"] is True
    assert "ShaderNodeBsdfPrincipled" in smoke["target_node_types"]

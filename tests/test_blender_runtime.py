import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from materials_processor.dcc.blender.runtime import (
    BLENDER_EXE_ENV_VAR,
    BLENDER_ROOT_ENV_VAR,
    MATERIAL_SMOKE_RESULT_PREFIX,
    MINIMUM_BLENDER_VERSION,
    TARGET_BLENDER_VERSION,
    VALIDATION_RESULT_PREFIX,
    BlenderRuntime,
    _default_package_src,
    _default_blender_root,
    _parse_prefixed_output,
    _run_blender_python,
    resolve_blender_runtime,
    validate_blender_material_smoke,
    validate_blender_runtime,
)

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TIE_DEFENDER_BLEND = Path(
    r"F:\Users\Ahmed Hindy\Downloads\vfx_tmp\X-Ripper Stuff\Tie Defender\Tie Defender.blend"
)
TIE_DEFENDER_RESULT_PREFIX = "MATERIALS_PROCESSOR_TIE_DEFENDER="


def _fake_blender_root(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    blender_exe = tmp_path / "blender.exe"
    blender_exe.write_text("", encoding="utf-8")
    return tmp_path


def test_default_blender_root_uses_standard_windows_install_path():
    assert TARGET_BLENDER_VERSION == "5.2"
    assert MINIMUM_BLENDER_VERSION == "5.0"
    assert _default_blender_root() == Path("C:/Program Files/Blender Foundation/Blender 5.2")


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


@pytest.mark.blender
def test_ingests_local_tie_defender_packed_material_when_available():
    if not LOCAL_TIE_DEFENDER_BLEND.is_file():
        pytest.skip(f"Tie Defender blend file is missing: {LOCAL_TIE_DEFENDER_BLEND}")
    try:
        runtime = resolve_blender_runtime(version=None)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    code = f"""
import json

import bpy

from materials_processor.dcc.blender.adapters import BlenderMaterialReader


def iter_nodes(nodes):
    for node in nodes:
        yield node
        yield from iter_nodes(node.children_list)


bpy.ops.wm.open_mainfile(filepath={str(LOCAL_TIE_DEFENDER_BLEND)!r})
material = bpy.data.materials["T_TieDefender_01_CS_Mat"]
graph = BlenderMaterialReader().read(material)
nodes = list(iter_nodes(graph.nodeinfo_list))
texture_paths = [
    parameter.value
    for node in nodes
    for parameter in (node.parameters or [])
    if parameter.generic_name == "filename"
]
result = {{
    "material_name": graph.material_name,
    "node_types": sorted(set(node.node_type for node in nodes)),
    "output_keys": sorted(graph.output_connections),
    "texture_paths": sorted(texture_paths),
}}
print({TIE_DEFENDER_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()

    completed = _run_blender_python(runtime, code, ROOT / "src", timeout=180)
    if completed.returncode != 0:
        raise RuntimeError(
            "Tie Defender Blender ingest failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    result = _parse_prefixed_output(
        completed.stdout,
        completed.stderr,
        TIE_DEFENDER_RESULT_PREFIX,
        "Tie Defender ingest",
    )
    assert result["material_name"] == "T_TieDefender_01_CS_Mat"
    assert "GENERIC::standard_surface" in result["node_types"]
    assert "GENERIC::image" in result["node_types"]
    assert "GENERIC::uvmap" in result["node_types"]
    assert "GENERIC::separate_color" in result["node_types"]
    assert "GENERIC::output_surface" in result["output_keys"]
    assert result["texture_paths"]
    assert all(not texture_path.startswith("//") for texture_path in result["texture_paths"])

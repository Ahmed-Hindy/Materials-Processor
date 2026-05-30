import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from materials_processor.dcc.maya.runtime import (
    EXPECTED_API_VERSIONS,
    VALIDATION_RESULT_PREFIX,
    MayaRuntime,
    _default_package_src,
    resolve_maya_runtime,
    validate_maya_runtime,
)

ROOT = Path(__file__).resolve().parents[1]
LOCAL_MAYAPY_2024 = Path(r"C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe")


def _fake_maya_root(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    maya_exe = bin_dir / "maya.exe"
    mayapy_exe = bin_dir / "mayapy.exe"
    maya_exe.write_text("", encoding="utf-8")
    mayapy_exe.write_text("", encoding="utf-8")
    return tmp_path


def test_resolve_maya_runtime_uses_explicit_root(tmp_path):
    maya_root = _fake_maya_root(tmp_path)

    runtime = resolve_maya_runtime(root=maya_root)

    assert runtime == MayaRuntime(
        root=maya_root.resolve(),
        maya_exe=(maya_root / "bin" / "maya.exe").resolve(),
        mayapy_exe=(maya_root / "bin" / "mayapy.exe").resolve(),
        version="2024",
        api_version=EXPECTED_API_VERSIONS["2024"],
    )


def test_resolve_maya_runtime_uses_versioned_env_override(tmp_path, monkeypatch):
    maya_root = _fake_maya_root(tmp_path)
    monkeypatch.setenv("MATERIALS_PROCESSOR_MAYA2024_ROOT", str(maya_root))

    runtime = resolve_maya_runtime()

    assert runtime.root == maya_root.resolve()


def test_resolve_maya_runtime_reports_missing_executable(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "maya.exe").write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Maya Python executable"):
        resolve_maya_runtime(root=tmp_path)


def test_validate_maya_runtime_uses_mayapy_pythonpath_and_isolated_prefs(tmp_path, monkeypatch):
    maya_root = _fake_maya_root(tmp_path / "Maya2024")
    runtime = resolve_maya_runtime(root=maya_root)
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
            "api_version": "20240000",
            "package_file": str(package_src / "materials_processor" / "__init__.py"),
            "version": "2024",
        }
        return SimpleNamespace(
            returncode=0,
            stdout=f"{VALIDATION_RESULT_PREFIX}{json.dumps(result)}\n",
            stderr="",
        )

    monkeypatch.setattr("materials_processor.dcc.maya.runtime.subprocess.run", fake_run)

    validated = validate_maya_runtime(runtime=runtime, package_src=package_src, timeout=3)

    assert validated.version == "2024"
    assert validated.api_version == "20240000"
    assert captured["command"][:2] == [str(runtime.mayapy_exe), "-c"]
    assert captured["check"] is False
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["timeout"] == 3
    assert captured["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(package_src.resolve())
    assert "MAYA_APP_DIR" in captured["env"]
    assert "materials_processor_maya_app_" in captured["env"]["MAYA_APP_DIR"]


def test_validate_maya_runtime_default_package_src_points_to_src():
    assert _default_package_src() == ROOT / "src"


@pytest.mark.maya
def test_validate_local_maya2024_runtime_when_available():
    if not LOCAL_MAYAPY_2024.is_file():
        pytest.skip(f"Maya 2024 mayapy not found: {LOCAL_MAYAPY_2024}")

    runtime = resolve_maya_runtime(root=LOCAL_MAYAPY_2024.parents[1])
    validated = validate_maya_runtime(runtime=runtime, package_src=ROOT / "src", timeout=120)

    assert validated.version == "2024"
    assert validated.api_version == "20240000"

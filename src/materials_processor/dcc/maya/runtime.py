"""Discover and validate the local Maya runtime."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAYA_VERSION = "2024"
EXPECTED_API_VERSIONS = {
    "2024": "20240000",
}

VALIDATION_RESULT_PREFIX = "MATERIALS_PROCESSOR_MAYA_RUNTIME="
MATERIAL_SMOKE_RESULT_PREFIX = "MATERIALS_PROCESSOR_MAYA_MATERIAL_SMOKE="


@dataclass(frozen=True)
class MayaRuntime:
    """Resolved Maya executables and version metadata."""

    root: Path
    maya_exe: Path
    mayapy_exe: Path
    version: str
    api_version: str


def _default_maya_root(version: str) -> Path:
    return Path("C:/Program Files/Autodesk") / f"Maya{version}"


def _env_var_for_version(version: str) -> str:
    return f"MATERIALS_PROCESSOR_MAYA{version}_ROOT"


def _resolve_root(version: str, root: str | os.PathLike[str] | None) -> Path:
    if root is not None:
        return Path(root).expanduser()

    env_root = os.environ.get(_env_var_for_version(version))
    if env_root:
        return Path(env_root).expanduser()

    return _default_maya_root(version)


def _require_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} was not found: {resolved}")
    return resolved


def resolve_maya_runtime(version: str = DEFAULT_MAYA_VERSION, root: str | os.PathLike[str] | None = None) -> MayaRuntime:
    """Resolve the Maya runtime executable paths.

    Args:
        version: Maya major version to resolve.
        root: Optional Maya installation root. When omitted, the version-specific
            ``MATERIALS_PROCESSOR_MAYA{version}_ROOT`` environment variable is
            checked before the standard Autodesk install location.

    Returns:
        Resolved Maya runtime metadata.

    Raises:
        FileNotFoundError: If ``maya.exe`` or ``mayapy.exe`` is missing.
    """
    install_root = _resolve_root(version, root).resolve()
    bin_dir = install_root / "bin"
    maya_exe = _require_file(bin_dir / "maya.exe", "Maya GUI executable")
    mayapy_exe = _require_file(bin_dir / "mayapy.exe", "Maya Python executable")

    return MayaRuntime(
        root=install_root,
        maya_exe=maya_exe,
        mayapy_exe=mayapy_exe,
        version=version,
        api_version=EXPECTED_API_VERSIONS.get(version, ""),
    )


def _validation_code() -> str:
    return f"""
import json
import materials_processor
import maya.standalone

maya.standalone.initialize(name="python")
try:
    import maya.cmds as cmds

    result = {{
        "api_version": str(cmds.about(apiVersion=True)),
        "package_file": materials_processor.__file__,
        "version": str(cmds.about(version=True)),
    }}
    print({VALIDATION_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
finally:
    try:
        maya.standalone.uninitialize()
    except Exception:
        pass
""".strip()


def _material_smoke_code() -> str:
    return f"""
import json

import maya.cmds as cmds
import maya.standalone

maya.standalone.initialize(name="python")
try:
    from materials_processor.core.conversion import ConversionService
    from materials_processor.dcc.maya.adapters import MayaMaterialReader, MayaMaterialWriter

    shader = cmds.shadingNode("standardSurface", asShader=True, name="materials_processor_smoke_surface")
    shading_engine = cmds.sets(
        renderable=True,
        noSurfaceShader=True,
        empty=True,
        name="materials_processor_smoke_SG",
    )
    texture = cmds.shadingNode("file", asTexture=True, name="materials_processor_smoke_file")
    placement = cmds.shadingNode("place2dTexture", asUtility=True, name="materials_processor_smoke_place2d")
    bump = cmds.shadingNode("bump2d", asUtility=True, name="materials_processor_smoke_bump")

    cmds.setAttr(shader + ".base", 1.0)
    cmds.setAttr(shader + ".baseColor", 0.8, 0.2, 0.1, type="double3")
    cmds.setAttr(texture + ".fileTextureName", "C:/textures/maya_smoke_basecolor.png", type="string")
    cmds.connectAttr(shader + ".outColor", shading_engine + ".surfaceShader", force=True)
    cmds.connectAttr(texture + ".outColor", shader + ".baseColor", force=True)
    cmds.connectAttr(texture + ".outAlpha", bump + ".bumpValue", force=True)
    cmds.connectAttr(bump + ".outNormal", shader + ".normalCamera", force=True)
    cmds.connectAttr(placement + ".outUV", texture + ".uvCoord", force=True)

    reader = MayaMaterialReader()
    graph = reader.read(shading_engine)
    converted_shading_engine = ConversionService(reader, MayaMaterialWriter()).convert(
        shading_engine,
        {{"material_name": "materials_processor_smoke_target"}},
    )
    target_connections = cmds.listConnections(
        converted_shading_engine + ".surfaceShader",
        source=True,
        destination=False,
        plugs=True,
    ) or []
    target_nodes = set([converted_shading_engine])
    pending = [plug.split(".", 1)[0] for plug in target_connections]
    while pending:
        node = pending.pop()
        if node in target_nodes:
            continue
        target_nodes.add(node)
        upstream = cmds.listConnections(node, source=True, destination=False) or []
        pending.extend(upstream)
    target_node_types = sorted(set(cmds.nodeType(node) for node in target_nodes))

    result = {{
        "converted_shading_engine": converted_shading_engine,
        "material_name": graph.material_name,
        "node_count": len(graph.nodeinfo_list),
        "output_count": len(graph.output_connections),
        "recreated": bool(target_connections),
        "target_node_types": target_node_types,
    }}
    print({MATERIAL_SMOKE_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
finally:
    try:
        maya.standalone.uninitialize()
    except Exception:
        pass
""".strip()


def _with_pythonpath(env: dict[str, str], package_src: Path) -> dict[str, str]:
    current_pythonpath = env.get("PYTHONPATH")
    src_path = str(package_src.resolve())
    env["PYTHONPATH"] = src_path if not current_pythonpath else f"{src_path}{os.pathsep}{current_pythonpath}"
    return env


def _parse_validation_output(stdout: str) -> dict[str, str]:
    for line in stdout.splitlines():
        if line.startswith(VALIDATION_RESULT_PREFIX):
            return json.loads(line[len(VALIDATION_RESULT_PREFIX):])
    raise RuntimeError(f"Maya validation did not produce a runtime result. stdout:\n{stdout}")


def _parse_prefixed_output(stdout: str, stderr: str, prefix: str, label: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return json.loads(line[len(prefix):])
    raise RuntimeError(f"Maya {label} did not produce a runtime result.\nstdout:\n{stdout}\nstderr:\n{stderr}")


def _default_package_src() -> Path:
    return Path(__file__).resolve().parents[3]


def validate_maya_runtime(
    runtime: MayaRuntime | None = None,
    package_src: str | os.PathLike[str] | None = None,
    timeout: int = 120,
) -> MayaRuntime:
    """Validate that Materials Processor imports inside Maya's mayapy runtime.

    Args:
        runtime: Optional pre-resolved Maya runtime.
        package_src: Source directory to prepend to ``PYTHONPATH`` for the
            validation process. Defaults to this checkout's ``src`` directory.
        timeout: Maximum seconds to wait for ``mayapy``.

    Returns:
        Runtime metadata populated from Maya itself.

    Raises:
        RuntimeError: If mayapy fails, times out, or reports an unexpected
            Maya version/API.
    """
    runtime = runtime or resolve_maya_runtime()
    package_src_path = Path(package_src) if package_src is not None else _default_package_src()

    env = _with_pythonpath(os.environ.copy(), package_src_path)
    with tempfile.TemporaryDirectory(prefix="materials_processor_maya_app_") as maya_app_dir:
        env["MAYA_APP_DIR"] = maya_app_dir
        try:
            completed = subprocess.run(
                [str(runtime.mayapy_exe), "-c", _validation_code()],
                check=False,
                capture_output=True,
                env=env,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Maya validation timed out after {timeout} seconds.") from exc

    if completed.returncode != 0:
        raise RuntimeError(
            "Maya validation failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    result = _parse_validation_output(completed.stdout)
    expected_api_version = EXPECTED_API_VERSIONS.get(runtime.version)
    if result["version"] != runtime.version:
        raise RuntimeError(f"Expected Maya {runtime.version}, but mayapy reported {result['version']}.")
    if expected_api_version and result["api_version"] != expected_api_version:
        raise RuntimeError(
            f"Expected Maya API {expected_api_version}, but mayapy reported {result['api_version']}."
        )

    return MayaRuntime(
        root=runtime.root,
        maya_exe=runtime.maya_exe,
        mayapy_exe=runtime.mayapy_exe,
        version=result["version"],
        api_version=result["api_version"],
    )


def _run_mayapy(runtime: MayaRuntime, code: str, package_src: Path, timeout: int) -> subprocess.CompletedProcess:
    env = _with_pythonpath(os.environ.copy(), package_src)
    with tempfile.TemporaryDirectory(prefix="materials_processor_maya_app_") as maya_app_dir:
        env["MAYA_APP_DIR"] = maya_app_dir
        try:
            return subprocess.run(
                [str(runtime.mayapy_exe), "-c", code],
                check=False,
                capture_output=True,
                env=env,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Maya validation timed out after {timeout} seconds.") from exc


def validate_maya_material_smoke(
    runtime: MayaRuntime | None = None,
    package_src: str | os.PathLike[str] | None = None,
    timeout: int = 120,
) -> dict:
    """Validate Maya traversal/standardization/recreation in mayapy.

    Args:
        runtime: Optional pre-resolved Maya runtime.
        package_src: Source directory to prepend to ``PYTHONPATH``.
        timeout: Maximum seconds to wait for ``mayapy``.

    Returns:
        Summary data from the material smoke validation.

    Raises:
        RuntimeError: If Maya fails, times out, or the material cannot be
            traversed and recreated.
    """
    runtime = runtime or resolve_maya_runtime()
    package_src_path = Path(package_src) if package_src is not None else _default_package_src()
    completed = _run_mayapy(runtime, _material_smoke_code(), package_src_path, timeout)
    if completed.returncode != 0:
        raise RuntimeError(
            "Maya material smoke validation failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    result = _parse_prefixed_output(
        completed.stdout,
        completed.stderr,
        MATERIAL_SMOKE_RESULT_PREFIX,
        "material smoke validation",
    )
    if not result["recreated"]:
        raise RuntimeError(f"Maya material smoke validation did not recreate the material: {result}")
    if "standardSurface" not in result["target_node_types"]:
        raise RuntimeError(f"Maya material smoke validation did not create a standardSurface: {result}")
    return result

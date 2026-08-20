"""Discover and validate the local Blender runtime."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

MINIMUM_BLENDER_VERSION = "5.0"
TARGET_BLENDER_VERSION = "5.2"
DEFAULT_BLENDER_VERSION = TARGET_BLENDER_VERSION
BLENDER_ROOT_ENV_VAR = "MATERIALS_PROCESSOR_BLENDER_ROOT"
BLENDER_EXE_ENV_VAR = "MATERIALS_PROCESSOR_BLENDER_EXE"
VALIDATION_RESULT_PREFIX = "MATERIALS_PROCESSOR_BLENDER_RUNTIME="
MATERIAL_SMOKE_RESULT_PREFIX = "MATERIALS_PROCESSOR_BLENDER_MATERIAL_SMOKE="


@dataclass(frozen=True)
class BlenderRuntime:
    """Resolved Blender executable and version metadata."""

    root: Path
    blender_exe: Path
    version: str
    python_version: str
    api_version: str


def _default_blender_root(version: str = DEFAULT_BLENDER_VERSION) -> Path:
    return Path("C:/Program Files/Blender Foundation") / f"Blender {version}"


def _version_from_root(root: Path) -> str:
    match = re.match(r"Blender\s+(.+)$", root.name)
    return match.group(1) if match else ""


def _version_sort_key(path: Path) -> tuple[int, ...]:
    version = _version_from_root(path)
    parts = []
    for part in re.split(r"[^0-9]+", version):
        if part:
            parts.append(int(part))
    return tuple(parts)


def _version_tuple(version: str) -> tuple[int, ...]:
    """Convert a Blender version string into comparable numeric components."""
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _require_minimum_blender_version(version: str) -> None:
    """Raise when a discovered Blender version is older than the supported minimum."""
    if version and _version_tuple(version) < _version_tuple(MINIMUM_BLENDER_VERSION):
        raise RuntimeError(
            f"Blender {version} is unsupported. Materials Processor requires Blender {MINIMUM_BLENDER_VERSION} or later."
        )


def _candidate_roots(version: str | None) -> list[Path]:
    if version:
        return [_default_blender_root(version)]

    blender_foundation = Path("C:/Program Files/Blender Foundation")
    if not blender_foundation.is_dir():
        return [_default_blender_root()]

    candidates = [path for path in blender_foundation.glob("Blender *") if path.is_dir()]
    sorted_candidates = sorted(candidates, key=_version_sort_key, reverse=True)
    target_candidate = [
        path for path in sorted_candidates if _version_from_root(path).startswith(f"{TARGET_BLENDER_VERSION}.")
        or _version_from_root(path) == TARGET_BLENDER_VERSION
    ]
    blender_5_candidates = [
        path
        for path in sorted_candidates
        if path not in target_candidate and _version_from_root(path).startswith("5.")
    ]
    other_candidates = [path for path in sorted_candidates if path not in target_candidate and path not in blender_5_candidates]
    return target_candidate + blender_5_candidates + other_candidates


def _require_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} was not found: {resolved}")
    return resolved


def _resolve_blender_exe(
    version: str | None,
    root: str | os.PathLike[str] | None,
    blender_exe: str | os.PathLike[str] | None,
) -> Path:
    if blender_exe is not None:
        return _require_file(Path(blender_exe), "Blender executable")

    env_exe = os.environ.get(BLENDER_EXE_ENV_VAR)
    if env_exe:
        return _require_file(Path(env_exe), "Blender executable")

    if root is not None:
        return _require_file(Path(root) / "blender.exe", "Blender executable")

    env_root = os.environ.get(BLENDER_ROOT_ENV_VAR)
    if env_root:
        return _require_file(Path(env_root) / "blender.exe", "Blender executable")

    for candidate_root in _candidate_roots(version):
        candidate_exe = candidate_root / "blender.exe"
        if candidate_exe.is_file():
            return candidate_exe.resolve()

    discovered = shutil.which("blender")
    if discovered:
        return _require_file(Path(discovered), "Blender executable")

    searched = ", ".join(str(path / "blender.exe") for path in _candidate_roots(version))
    raise FileNotFoundError(
        "Blender executable was not found. Set "
        f"{BLENDER_EXE_ENV_VAR}, {BLENDER_ROOT_ENV_VAR}, or install Blender in one of: {searched}"
    )


def resolve_blender_runtime(
    version: str | None = None,
    root: str | os.PathLike[str] | None = None,
    blender_exe: str | os.PathLike[str] | None = None,
) -> BlenderRuntime:
    """Resolve the Blender runtime executable path.

    Args:
        version: Optional Blender version used for the default Windows install
            path. Pass ``None`` to search installed ``Blender *`` directories
            and then ``PATH``.
        root: Optional Blender installation root. When omitted,
            ``MATERIALS_PROCESSOR_BLENDER_ROOT`` is checked.
        blender_exe: Optional direct path to ``blender.exe``. When omitted,
            ``MATERIALS_PROCESSOR_BLENDER_EXE`` is checked.

    Returns:
        Resolved Blender runtime metadata. Version fields are populated from
        the requested/root version until ``validate_blender_runtime`` can ask
        Blender itself.

    Raises:
        FileNotFoundError: If ``blender.exe`` is missing.
    """
    resolved_exe = _resolve_blender_exe(version, root, blender_exe)
    resolved_root = resolved_exe.parent.resolve()
    requested_version = version or _version_from_root(resolved_root)
    _require_minimum_blender_version(requested_version)

    return BlenderRuntime(
        root=resolved_root,
        blender_exe=resolved_exe,
        version=requested_version or "",
        python_version="",
        api_version="",
    )


def _runtime_validation_code() -> str:
    return f"""
import json
import sys

import bpy
import materials_processor

result = {{
    "api_version": ".".join(str(part) for part in bpy.app.version),
    "package_file": materials_processor.__file__,
    "python_version": ".".join(str(part) for part in sys.version_info[:3]),
    "version": bpy.app.version_string,
}}
print({VALIDATION_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()


def _material_smoke_code() -> str:
    return f"""
import json

import bpy

from materials_processor.core.conversion import ConversionService
from materials_processor.dcc.blender.adapters import BlenderMaterialReader, BlenderMaterialWriter


def socket(collection, name):
    return collection[name] if name in collection else collection[0]


source = bpy.data.materials.new("materials_processor_smoke_source")
source.use_nodes = True
source_tree = source.node_tree
source_tree.nodes.clear()

output_node = source_tree.nodes.new(type="ShaderNodeOutputMaterial")
output_node.name = "Material Output"
bsdf_node = source_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
bsdf_node.name = "Principled BSDF"
socket(bsdf_node.inputs, "Base Color").default_value = (0.8, 0.2, 0.1, 1.0)
source_tree.links.new(socket(bsdf_node.outputs, "BSDF"), socket(output_node.inputs, "Surface"))

target = bpy.data.materials.new("materials_processor_smoke_target")
target.use_nodes = True
graph = BlenderMaterialReader().read(source)
converted_material = ConversionService(BlenderMaterialReader(), BlenderMaterialWriter()).convert(source, target)

target_node_types = sorted(node.bl_idname for node in target.node_tree.nodes)
result = {{
    "material_name": graph.material_name,
    "node_count": len(graph.nodeinfo_list),
    "output_count": len(graph.output_connections),
    "recreated": converted_material == target,
    "target_node_types": target_node_types,
}}
print({MATERIAL_SMOKE_RESULT_PREFIX!r} + json.dumps(result, sort_keys=True))
""".strip()


def _with_pythonpath(env: dict[str, str], package_src: Path) -> dict[str, str]:
    current_pythonpath = env.get("PYTHONPATH")
    src_path = str(package_src.resolve())
    env["PYTHONPATH"] = src_path if not current_pythonpath else f"{src_path}{os.pathsep}{current_pythonpath}"
    return env


def _parse_prefixed_output(stdout: str, stderr: str, prefix: str, label: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return json.loads(line[len(prefix):])
    raise RuntimeError(f"Blender {label} did not produce a runtime result.\nstdout:\n{stdout}\nstderr:\n{stderr}")


def _default_package_src() -> Path:
    return Path(__file__).resolve().parents[3]


def _matches_requested_version(requested_version: str, reported_version: str) -> bool:
    if not requested_version:
        return True
    return reported_version == requested_version or reported_version.startswith(f"{requested_version}.")


def _run_blender_python(runtime: BlenderRuntime, code: str, package_src: Path, timeout: int) -> subprocess.CompletedProcess:
    env = _with_pythonpath(os.environ.copy(), package_src)
    with tempfile.TemporaryDirectory(prefix="materials_processor_blender_user_") as blender_user_dir:
        user_dir = Path(blender_user_dir)
        script_path = user_dir / "validate_materials_processor.py"
        script_path.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(package_src.resolve())!r})\n\n"
            "import bpy\n"
            f"if tuple(bpy.app.version[:2]) < {_version_tuple(MINIMUM_BLENDER_VERSION)!r}:\n"
            f"    raise RuntimeError({f'Materials Processor requires Blender {MINIMUM_BLENDER_VERSION} or later.'!r})\n\n"
            f"{code}\n",
            encoding="utf-8",
        )
        env["BLENDER_USER_CONFIG"] = str(user_dir / "config")
        env["BLENDER_USER_SCRIPTS"] = str(user_dir / "scripts")
        env["BLENDER_USER_DATAFILES"] = str(user_dir / "datafiles")
        try:
            return subprocess.run(
                [str(runtime.blender_exe), "--background", "--factory-startup", "--python", str(script_path)],
                check=False,
                capture_output=True,
                env=env,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Blender validation timed out after {timeout} seconds.") from exc


def validate_blender_runtime(
    runtime: BlenderRuntime | None = None,
    package_src: str | os.PathLike[str] | None = None,
    timeout: int = 120,
) -> BlenderRuntime:
    """Validate that Materials Processor imports inside Blender headless mode.

    Args:
        runtime: Optional pre-resolved Blender runtime.
        package_src: Source directory to prepend to ``PYTHONPATH`` for the
            validation process. Defaults to this checkout's ``src`` directory.
        timeout: Maximum seconds to wait for Blender.

    Returns:
        Runtime metadata populated from Blender itself.

    Raises:
        RuntimeError: If Blender fails, times out, or reports an unexpected
            version.
    """
    runtime = runtime or resolve_blender_runtime()
    package_src_path = Path(package_src) if package_src is not None else _default_package_src()

    completed = _run_blender_python(runtime, _runtime_validation_code(), package_src_path, timeout)
    if completed.returncode != 0:
        raise RuntimeError(
            "Blender validation failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    result = _parse_prefixed_output(completed.stdout, completed.stderr, VALIDATION_RESULT_PREFIX, "validation")
    if not _matches_requested_version(runtime.version, result["version"]):
        raise RuntimeError(f"Expected Blender {runtime.version}, but Blender reported {result['version']}.")

    return BlenderRuntime(
        root=runtime.root,
        blender_exe=runtime.blender_exe,
        version=result["version"],
        python_version=result["python_version"],
        api_version=result["api_version"],
    )


def validate_blender_material_smoke(
    runtime: BlenderRuntime | None = None,
    package_src: str | os.PathLike[str] | None = None,
    timeout: int = 120,
) -> dict:
    """Validate Blender traversal/standardization/recreation in headless mode.

    Args:
        runtime: Optional pre-resolved Blender runtime.
        package_src: Source directory to prepend to ``PYTHONPATH`` for the
            validation process. Defaults to this checkout's ``src`` directory.
        timeout: Maximum seconds to wait for Blender.

    Returns:
        Summary data from the material smoke test.

    Raises:
        RuntimeError: If Blender fails, times out, or the smoke graph cannot be
            traversed and recreated.
    """
    runtime = runtime or resolve_blender_runtime()
    package_src_path = Path(package_src) if package_src is not None else _default_package_src()

    completed = _run_blender_python(runtime, _material_smoke_code(), package_src_path, timeout)
    if completed.returncode != 0:
        raise RuntimeError(
            "Blender material smoke validation failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    result = _parse_prefixed_output(
        completed.stdout,
        completed.stderr,
        MATERIAL_SMOKE_RESULT_PREFIX,
        "material smoke validation",
    )
    if not result["recreated"]:
        raise RuntimeError(f"Blender material smoke validation did not recreate the material: {result}")
    if "ShaderNodeBsdfPrincipled" not in result["target_node_types"]:
        raise RuntimeError(f"Blender material smoke validation did not create a Principled BSDF: {result}")

    return result

"""Top-level command line interface for Materials Processor."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from materials_processor import __version__
from materials_processor.dcc.blender import cli as blender_cli
from materials_processor.dcc.maya import cli as maya_cli


def _default_package_src() -> Path:
    return Path(__file__).resolve().parents[1]


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _add_doctor_parser(subparsers) -> argparse.ArgumentParser:
    doctor_parser = subparsers.add_parser("doctor", help="Discover installed DCC runtimes.")
    doctor_parser.add_argument("--validate", action="store_true", help="Run DCC runtime validation when available.")
    doctor_parser.add_argument("--timeout", type=int, default=120, help="Validation timeout in seconds.")
    doctor_parser.add_argument(
        "--package-src",
        default=None,
        help="Source directory to expose to DCC runtimes. Defaults to this checkout's src directory.",
    )
    doctor_parser.add_argument("--material-smoke", action="store_true", help="Run DCC material smoke validation.")

    blender_group = doctor_parser.add_argument_group("Blender")
    blender_group.add_argument("--blender-exe", help="Explicit path to blender.exe.")
    blender_group.add_argument("--blender-root", help="Explicit Blender install root.")
    blender_group.add_argument("--blender-version", help="Blender version to discover, e.g. 4.5.")

    maya_group = doctor_parser.add_argument_group("Maya")
    maya_group.add_argument("--maya-root", help="Explicit Maya install root.")
    maya_group.add_argument("--maya-version", default="2024", help="Maya version to resolve. Default: 2024.")

    houdini_group = doctor_parser.add_argument_group("Houdini")
    houdini_group.add_argument("--hython", help="Explicit path to hython.exe.")

    return doctor_parser


def _add_runtime_parser(subparsers) -> argparse.ArgumentParser:
    runtime_parser = subparsers.add_parser("runtime", help="Runtime discovery and validation commands.")
    runtime_subparsers = runtime_parser.add_subparsers(dest="runtime_command", required=True)

    validate_parser = runtime_subparsers.add_parser("validate", help="Validate an installed DCC runtime.")
    validate_parser.add_argument(
        "--dcc",
        choices=("blender", "maya"),
        required=True,
        help="DCC runtime to validate.",
    )
    validate_parser.add_argument("--timeout", type=int, default=120, help="Validation timeout in seconds.")
    validate_parser.add_argument(
        "--package-src",
        default=None,
        help="Source directory to expose to the DCC. Defaults to this checkout's src directory.",
    )
    validate_parser.add_argument("--material-smoke", action="store_true", help="Run material traversal/recreation smoke.")

    blender_group = validate_parser.add_argument_group("Blender")
    blender_group.add_argument("--blender-exe", help="Explicit path to blender.exe.")
    blender_group.add_argument("--blender-root", help="Explicit Blender install root.")
    blender_group.add_argument("--blender-version", help="Blender version to discover, e.g. 4.5.")

    maya_group = validate_parser.add_argument_group("Maya")
    maya_group.add_argument("--maya-root", help="Explicit Maya install root.")
    maya_group.add_argument("--maya-version", default="2024", help="Maya version to resolve. Default: 2024.")

    return runtime_parser


def _add_blender_parser(subparsers) -> argparse.ArgumentParser:
    blender_parser = subparsers.add_parser("blender", help="Blender scene inspection and export commands.")
    blender_subparsers = blender_parser.add_subparsers(dest="blender_command", required=True)
    blender_cli.add_blender_export_parser(blender_subparsers)
    blender_cli.add_blender_inspect_parser(blender_subparsers)
    return blender_parser


def _add_maya_parser(subparsers) -> argparse.ArgumentParser:
    maya_parser = subparsers.add_parser("maya", help="Maya scene inspection and export commands.")
    maya_subparsers = maya_parser.add_subparsers(dest="maya_command", required=True)
    maya_cli.add_maya_export_parser(maya_subparsers)
    maya_cli.add_maya_inspect_parser(maya_subparsers)
    return maya_parser


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(prog="materials-processor")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_blender_parser(subparsers)
    _add_maya_parser(subparsers)
    _add_doctor_parser(subparsers)
    _add_runtime_parser(subparsers)
    return parser


def _validate_blender_runtime(args) -> dict:
    from materials_processor.dcc.blender.runtime import (
        resolve_blender_runtime,
        validate_blender_material_smoke,
        validate_blender_runtime,
    )

    runtime = resolve_blender_runtime(
        version=args.blender_version,
        root=args.blender_root,
        blender_exe=args.blender_exe,
    )
    package_src = args.package_src or _default_package_src()
    validated = validate_blender_runtime(runtime=runtime, package_src=package_src, timeout=args.timeout)
    result = {
        "dcc": "blender",
        "root": str(validated.root),
        "blender_exe": str(validated.blender_exe),
        "version": validated.version,
        "python_version": validated.python_version,
        "api_version": validated.api_version,
    }
    if args.material_smoke:
        result["material_smoke"] = validate_blender_material_smoke(
            runtime=validated,
            package_src=package_src,
            timeout=args.timeout,
        )
    return result


def _validate_maya_runtime(args) -> dict:
    from materials_processor.dcc.maya.runtime import (
        resolve_maya_runtime,
        validate_maya_material_smoke,
        validate_maya_runtime,
    )

    runtime = resolve_maya_runtime(version=args.maya_version, root=args.maya_root)
    package_src = args.package_src or _default_package_src()
    validated = validate_maya_runtime(runtime=runtime, package_src=package_src, timeout=args.timeout)
    result = {
        "dcc": "maya",
        "root": str(validated.root),
        "maya_exe": str(validated.maya_exe),
        "mayapy_exe": str(validated.mayapy_exe),
        "version": validated.version,
        "api_version": validated.api_version,
    }
    if args.material_smoke:
        result["material_smoke"] = validate_maya_material_smoke(
            runtime=validated,
            package_src=package_src,
            timeout=args.timeout,
        )
    return result


def _resolve_hython(explicit_hython: str | None = None) -> Path | None:
    if explicit_hython:
        path = Path(explicit_hython).expanduser().resolve()
        return path if path.is_file() else None

    env_hython = os.environ.get("MATERIALS_PROCESSOR_HYTHON")
    if env_hython:
        path = Path(env_hython).expanduser().resolve()
        if path.is_file():
            return path

    path_hython = shutil.which("hython") or shutil.which("hython.exe")
    if path_hython:
        return Path(path_hython).resolve()

    default_hython = Path("C:/Program Files/Side Effects Software/Houdini 21.0.631/bin/hython.exe")
    if default_hython.is_file():
        return default_hython.resolve()

    install_root = Path("C:/Program Files/Side Effects Software")
    if install_root.is_dir():
        candidates = sorted(install_root.glob("Houdini 21.0*/bin/hython.exe"), reverse=True)
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

    return None


def _validate_houdini_runtime(hython: Path, timeout: int) -> dict:
    code = (
        "import json\n"
        "import hou\n"
        "print('MATERIALS_PROCESSOR_HOUDINI_RUNTIME=' + json.dumps({"
        "'version': hou.applicationVersionString(), "
        "'hfs': hou.getenv('HFS')"
        "}, sort_keys=True))\n"
    )
    completed = subprocess.run(
        [str(hython), "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Houdini validation failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    for line in completed.stdout.splitlines():
        if line.startswith("MATERIALS_PROCESSOR_HOUDINI_RUNTIME="):
            return json.loads(line.split("=", 1)[1])
    raise RuntimeError(f"Houdini validation did not report a runtime result.\nstdout:\n{completed.stdout}")


def _doctor_entry(name: str, status: str, **extra) -> dict:
    return {"dcc": name, "status": status, **extra}


def _doctor_blender(args) -> dict:
    from materials_processor.dcc.blender.runtime import resolve_blender_runtime

    try:
        runtime = resolve_blender_runtime(
            version=args.blender_version,
            root=args.blender_root,
            blender_exe=args.blender_exe,
        )
        result = _doctor_entry(
            "blender",
            "found",
            root=str(runtime.root),
            blender_exe=str(runtime.blender_exe),
            version=runtime.version,
            python_version=runtime.python_version,
            api_version=runtime.api_version,
        )
        if args.validate:
            validation = _validate_blender_runtime(args)
            result.update(validation)
            result["status"] = "valid"
        return result
    except Exception as exc:
        return _doctor_entry("blender", "missing" if isinstance(exc, FileNotFoundError) else "error", error=str(exc))


def _doctor_maya(args) -> dict:
    from materials_processor.dcc.maya.runtime import resolve_maya_runtime

    try:
        runtime = resolve_maya_runtime(version=args.maya_version, root=args.maya_root)
        result = _doctor_entry(
            "maya",
            "found",
            root=str(runtime.root),
            maya_exe=str(runtime.maya_exe),
            mayapy_exe=str(runtime.mayapy_exe),
            version=runtime.version,
            api_version=runtime.api_version,
        )
        if args.validate:
            validation = _validate_maya_runtime(args)
            result.update(validation)
            result["status"] = "valid"
        return result
    except Exception as exc:
        return _doctor_entry("maya", "missing" if isinstance(exc, FileNotFoundError) else "error", error=str(exc))


def _doctor_houdini(args) -> dict:
    try:
        hython = _resolve_hython(args.hython)
        if hython is None:
            return _doctor_entry("houdini", "missing", error="hython was not found.")
        result = _doctor_entry("houdini", "found", hython=str(hython))
        if args.validate:
            result.update(_validate_houdini_runtime(hython, args.timeout))
            result["status"] = "valid"
        return result
    except Exception as exc:
        return _doctor_entry("houdini", "error", error=str(exc))


def _doctor(args) -> dict:
    return {
        "package": {
            "name": "materials-processor",
            "version": __version__,
            "package_src": str(Path(args.package_src).resolve() if args.package_src else _default_package_src()),
        },
        "runtimes": [
            _doctor_blender(args),
            _doctor_maya(args),
            _doctor_houdini(args),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Run the top-level command line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "blender":
            if args.blender_command == "export-usd":
                _print_json(blender_cli.run_export_from_args(args))
                return 0
            if args.blender_command == "inspect":
                _print_json(blender_cli.run_inspect_from_args(args))
                return 0

        if args.command == "maya":
            if args.maya_command == "export-usd":
                _print_json(maya_cli.run_export_from_args(args))
                return 0
            if args.maya_command == "inspect":
                _print_json(maya_cli.run_inspect_from_args(args))
                return 0

        if args.command == "doctor":
            _print_json(_doctor(args))
            return 0

        if args.command == "runtime" and args.runtime_command == "validate":
            if args.dcc == "blender":
                _print_json(_validate_blender_runtime(args))
                return 0
            if args.dcc == "maya":
                _print_json(_validate_maya_runtime(args))
                return 0

        parser.error("Unsupported command.")
        return 2
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

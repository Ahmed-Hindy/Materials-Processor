"""Build and validate the installable Blender extension archive."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from materials_processor.dcc.blender.runtime import resolve_blender_runtime

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_SOURCE = ROOT / "blender_extension"
PACKAGE_SOURCE = ROOT / "src" / "materials_processor"


def _stage_extension(stage_dir: Path) -> None:
    """Copy the extension entry point and runtime package into a build directory."""
    shutil.copytree(EXTENSION_SOURCE, stage_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(PACKAGE_SOURCE, stage_dir / "materials_processor", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _run_blender_command(blender_exe: Path, arguments: list[str]) -> None:
    """Run a factory-startup Blender command and preserve diagnostics on failure."""
    completed = subprocess.run(
        [str(blender_exe), "--factory-startup", "--command", "extension", *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Blender extension command failed:\n{completed.stdout}\n{completed.stderr}")


def build_extension(output_path: Path, *, blender_exe: Path | None = None) -> Path:
    """Build and validate an installable Blender extension archive.

    Args:
        output_path: Destination archive path, including the ``.zip`` suffix.
        blender_exe: Optional Blender executable override.

    Returns:
        The validated extension archive path.
    """
    runtime = None if blender_exe else resolve_blender_runtime(version=None)
    executable = blender_exe or runtime.blender_exe
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="materials_processor_blender_extension_") as temporary_dir:
        stage_dir = Path(temporary_dir) / "materials_processor"
        _stage_extension(stage_dir)
        _run_blender_command(
            executable,
            ["build", "--source-dir", str(stage_dir), "--output-filepath", str(output_path), "--valid-tags="],
        )
    if not output_path.is_file():
        raise RuntimeError(f"Blender did not create the extension archive: {output_path}")
    _run_blender_command(executable, ["validate", str(output_path), "--valid-tags="])
    return output_path


def main() -> int:
    """Build an installable Blender extension zip file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Destination extension .zip file.")
    parser.add_argument("--blender-exe", type=Path, help="Explicit Blender executable path.")
    args = parser.parse_args()
    archive = build_extension(args.output, blender_exe=args.blender_exe)
    print(f"Built Blender extension: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

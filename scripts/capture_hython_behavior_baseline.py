"""Capture Houdini material conversion behavior for a target checkout.

This script reuses the current hython conversion probe from
``tests/test_hython_material_networks.py`` while running the actual Houdini
runtime code from another checkout or worktree. That lets us capture a richer
baseline for an old commit before changing the runtime implementation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from materials_processor.dcc.houdini.runtime import resolve_hython


def _repo_root() -> Path:
    """Return the repository root for this script checkout."""
    return Path(__file__).resolve().parents[1]


def _load_probe_module(probe_root: Path):
    """Load the current hython matrix test module as a reusable probe."""
    probe_path = probe_root / "tests" / "test_hython_material_networks.py"
    if not probe_path.is_file():
        raise FileNotFoundError(f"Probe module not found: {probe_path}")

    sys.path.insert(0, str(probe_root / "src"))
    spec = importlib.util.spec_from_file_location("hython_behavior_probe", probe_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load probe module: {probe_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_revision(path: Path) -> str | None:
    """Return the HEAD revision for path when it is a git checkout."""
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _git_worktree_dirty(path: Path) -> bool | None:
    """Return whether path has tracked or untracked git changes."""
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return bool(completed.stdout.strip())


def _configure_probe(module, target_root: Path) -> None:
    """Point the loaded probe at the target checkout."""
    module.ROOT = target_root
    module.HIP_FILE = target_root / "examples" / "hip" / "example_file_v001.hip"
    module.SRC_DIR = target_root / "src"

    if not module.HIP_FILE.is_file():
        raise FileNotFoundError(f"Houdini example hip file not found: {module.HIP_FILE}")
    if not module.SRC_DIR.is_dir():
        raise FileNotFoundError(f"Target src directory not found: {module.SRC_DIR}")


def _run_hython_probe(module, hython: str | Path) -> dict:
    """Run the configured probe through hython and return the JSON payload."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(module.SRC_DIR)
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] += os.pathsep + os.environ["PYTHONPATH"]

    completed = subprocess.run(
        [hython, "-"],
        input=module._hython_script(),
        text=True,
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0:
        raise RuntimeError(f"hython exited with {completed.returncode}\n{output}")

    try:
        json_blob = output.split(module.JSON_START, 1)[1].split(module.JSON_END, 1)[0].strip()
    except IndexError as exc:
        raise RuntimeError(f"hython output did not include JSON sentinels\n{output}") from exc

    return json.loads(json_blob)


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    repo_root = _repo_root()
    default_output = repo_root / ".pytest_cache" / "materials_processor" / "hython_conversion_behavior_baseline.json"
    parser = argparse.ArgumentParser(
        description="Capture the hython material conversion behavior matrix for a target checkout.",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=repo_root,
        help="Checkout/worktree whose runtime behavior should be captured.",
    )
    parser.add_argument(
        "--probe-root",
        type=Path,
        default=repo_root,
        help="Checkout containing the widened hython matrix probe to reuse.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help="JSON file to write.",
    )
    parser.add_argument(
        "--hython",
        type=str,
        default=None,
        help="Explicit hython executable path. Defaults to standard Houdini discovery.",
    )
    return parser.parse_args()


def main() -> int:
    """Capture and write the behavior baseline."""
    args = _parse_args()
    target_root = args.target_root.resolve()
    probe_root = args.probe_root.resolve()
    output_path = args.output.resolve()

    module = _load_probe_module(probe_root)
    _configure_probe(module, target_root)

    hython = resolve_hython(args.hython)
    if not hython:
        raise RuntimeError("hython is not available. Set MATERIALS_PROCESSOR_HYTHON or pass --hython.")

    payload = _run_hython_probe(module, hython)
    payload["capture_metadata"] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "hython": str(hython),
        "probe_root": str(probe_root),
        "probe_revision": _git_revision(probe_root),
        "probe_worktree_dirty": _git_worktree_dirty(probe_root),
        "target_root": str(target_root),
        "target_revision": _git_revision(target_root),
        "target_worktree_dirty": _git_worktree_dirty(target_root),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {output_path}")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    if "output_fidelity" in payload:
        print(f"Captured {len(payload['output_fidelity'])} output-fidelity cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

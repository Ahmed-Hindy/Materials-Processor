"""Discover locally installed Houdini command-line runtimes."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

HFS_ENV_VAR = "HFS"
HYTHON_ENV_VAR = "MATERIALS_PROCESSOR_HYTHON"
HUSK_ENV_VAR = "MATERIALS_PROCESSOR_HUSK"
DEFAULT_INSTALL_ROOT = Path("C:/Program Files/Side Effects Software")
SUPPORTED_HOUDINI_VERSION_PREFIX = "21.0"


def _existing_file(path: str | Path) -> Path | None:
    """Return a resolved path only when it identifies a file."""
    candidate = Path(path).expanduser()
    return candidate.resolve() if candidate.is_file() else None


def _find_on_path(executable_names: tuple[str, ...]) -> Path | None:
    """Return the first matching executable found on PATH."""
    for executable_name in executable_names:
        if discovered := shutil.which(executable_name):
            if candidate := _existing_file(discovered):
                return candidate
    return None


def _find_in_hfs(executable_names: tuple[str, ...]) -> Path | None:
    """Return an executable from Houdini's active installation, when available."""
    if not (hfs := os.environ.get(HFS_ENV_VAR)):
        return None
    for executable_name in executable_names:
        if candidate := _existing_file(Path(hfs) / "bin" / executable_name):
            return candidate
    return None


def _find_in_default_install(executable_names: tuple[str, ...]) -> Path | None:
    """Find the newest supported Houdini 21.0 installation on Windows."""
    if not DEFAULT_INSTALL_ROOT.is_dir():
        return None
    installations = sorted(
        (
            candidate
            for candidate in DEFAULT_INSTALL_ROOT.glob(f"Houdini {SUPPORTED_HOUDINI_VERSION_PREFIX}*")
            if candidate.is_dir()
        ),
        key=_houdini_version_key,
        reverse=True,
    )
    for installation in installations:
        for executable_name in executable_names:
            if candidate := _existing_file(installation / "bin" / executable_name):
                return candidate
    return None


def _houdini_version_key(installation: Path) -> tuple[int, ...]:
    """Return a numeric sort key for a standard Houdini installation folder."""
    return tuple(int(part) for part in re.findall(r"\d+", installation.name))


def _resolve_houdini_executable(
    explicit_path: str | Path | None,
    environment_variable: str,
    executable_names: tuple[str, ...],
) -> Path | None:
    """Resolve a Houdini command-line executable from the standard locations."""
    if explicit_path is not None:
        return _existing_file(explicit_path)
    if configured_path := os.environ.get(environment_variable):
        if candidate := _existing_file(configured_path):
            return candidate
    return (
        _find_on_path(executable_names) or _find_in_hfs(executable_names) or _find_in_default_install(executable_names)
    )


def resolve_hython(explicit_hython: str | Path | None = None) -> Path | None:
    """Resolve Hython from an explicit path, configuration, PATH, HFS, or Houdini 21.0."""
    return _resolve_houdini_executable(
        explicit_hython,
        HYTHON_ENV_VAR,
        ("hython.exe", "hython"),
    )


def resolve_husk(explicit_husk: str | Path | None = None) -> Path | None:
    """Resolve Husk from an explicit path, configuration, PATH, HFS, or Houdini 21.0."""
    return _resolve_houdini_executable(
        explicit_husk,
        HUSK_ENV_VAR,
        ("husk.exe", "husk"),
    )

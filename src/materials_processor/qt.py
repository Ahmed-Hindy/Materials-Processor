"""Qt binding compatibility helpers for PySide6 and PySide2."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any

QT_BACKEND_ENV = "QT_BACKEND"
_BACKEND_ORDER = ("pyside6", "pyside2")
_BACKEND_MODULES = {
    "pyside6": "PySide6",
    "pyside2": "PySide2",
}


@dataclass(frozen=True)
class QtBinding:
    """Loaded Qt modules and binding metadata."""

    api: str
    core: Any
    widgets: Any


def binding_candidates(preferred: str | None = None) -> list[tuple[str, str]]:
    """Return Qt binding import candidates in preferred order."""
    requested = (preferred or "").lower().replace("-", "")
    env_requested = (os.environ.get(QT_BACKEND_ENV) or "").lower().replace("-", "")
    ordered: list[tuple[str, str]] = []
    if requested in _BACKEND_MODULES:
        ordered.append((_BACKEND_MODULES[requested], requested))
    elif env_requested in _BACKEND_MODULES:
        ordered.append((_BACKEND_MODULES[env_requested], env_requested))

    for backend in _BACKEND_ORDER:
        candidate = (_BACKEND_MODULES[backend], backend)
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered


def load_qt_binding(preferred: str | None = None) -> QtBinding:
    """Load PySide6 or PySide2 without making package import depend on Qt."""
    errors: list[str] = []
    for module_name, api in binding_candidates(preferred):
        try:
            qt_core = importlib.import_module(f"{module_name}.QtCore")
            qt_widgets = importlib.import_module(f"{module_name}.QtWidgets")
            return QtBinding(api=api, core=qt_core, widgets=qt_widgets)
        except ImportError as exc:
            errors.append(f"{module_name}: {exc}")

    raise RuntimeError(
        "Material Processor requires PySide6 or PySide2 to open Qt UI. "
        f"Tried: {'; '.join(errors)}"
    )


def enum_value(qt_core, enum_name: str, attr_name: str):
    """Return a Qt enum value across PySide2 and PySide6."""
    enum = getattr(qt_core.Qt, enum_name, None)
    if enum is not None and hasattr(enum, attr_name):
        return getattr(enum, attr_name)
    return getattr(qt_core.Qt, attr_name)

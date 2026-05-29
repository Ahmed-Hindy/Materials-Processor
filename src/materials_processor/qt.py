"""Qt binding compatibility helpers for PySide6 and PySide2."""

from __future__ import annotations

import importlib
import os

QT_BACKEND_ENV = "QT_BACKEND"
_BACKEND_ORDER = ("pyside6", "pyside2")
_BACKEND_MODULES = {
    "pyside6": "PySide6",
    "pyside2": "PySide2",
}

QT_BACKEND_NAME: str | None = None
_qt_core = None
_qt_widgets = None


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


def load_qt_modules(preferred: str | None = None):
    """Load PySide6 or PySide2 and cache QtCore/QtWidgets modules."""
    global QT_BACKEND_NAME, _qt_core, _qt_widgets

    requested = (preferred or "").lower().replace("-", "")
    if _qt_core is not None and _qt_widgets is not None:
        if not requested or requested == QT_BACKEND_NAME:
            return _qt_core, _qt_widgets

    errors: list[str] = []
    for module_name, api in binding_candidates(preferred):
        try:
            _qt_core = importlib.import_module(f"{module_name}.QtCore")
            _qt_widgets = importlib.import_module(f"{module_name}.QtWidgets")
            QT_BACKEND_NAME = api
            return _qt_core, _qt_widgets
        except ImportError as exc:
            errors.append(f"{module_name}: {exc}")

    raise RuntimeError(
        "Material Processor requires PySide6 or PySide2 to open Qt UI. "
        f"Tried: {'; '.join(errors)}"
    )


class _LazyQtModule:
    """Lazy proxy for a Qt module."""

    def __init__(self, module_name: str):
        self._module_name = module_name

    def _module(self):
        qt_core, qt_widgets = load_qt_modules()
        if self._module_name == "QtCore":
            return qt_core
        return qt_widgets

    def __getattr__(self, name: str):
        return getattr(self._module(), name)


QtCore = _LazyQtModule("QtCore")
QtWidgets = _LazyQtModule("QtWidgets")


def enum_value(enum_name: str, attr_name: str):
    """Return a Qt enum value across PySide2 and PySide6."""
    enum = getattr(QtCore.Qt, enum_name, None)
    if enum is not None and hasattr(enum, attr_name):
        return getattr(enum, attr_name)
    return getattr(QtCore.Qt, attr_name)


def get_qt_backend() -> str | None:
    """Return the active Qt backend name."""
    load_qt_modules()
    return QT_BACKEND_NAME

"""Test Qt shims used when PySide is not installed in CI."""

from __future__ import annotations

import sys
import types


def pytest_configure():
    """Install minimal PySide6 modules before test modules are imported."""
    pyside6 = sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
    qt_core = sys.modules.setdefault("PySide6.QtCore", types.ModuleType("PySide6.QtCore"))
    qt_widgets = sys.modules.setdefault("PySide6.QtWidgets", types.ModuleType("PySide6.QtWidgets"))
    pyside6.QtCore = qt_core
    pyside6.QtWidgets = qt_widgets

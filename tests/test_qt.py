import sys
import types

import pytest

from materials_processor import qt


def test_binding_candidates_prefers_requested_binding(monkeypatch):
    monkeypatch.delenv(qt.QT_BACKEND_ENV, raising=False)

    assert qt.binding_candidates("pyside2")[0] == ("PySide2", "pyside2")


def test_binding_candidates_honors_environment(monkeypatch):
    monkeypatch.setenv(qt.QT_BACKEND_ENV, "PySide2")

    assert qt.binding_candidates()[0] == ("PySide2", "pyside2")


def test_load_qt_binding_honors_requested_binding(monkeypatch):
    pyside2 = types.ModuleType("PySide2")
    qt_core = types.ModuleType("PySide2.QtCore")
    qt_widgets = types.ModuleType("PySide2.QtWidgets")
    monkeypatch.setitem(sys.modules, "PySide2", pyside2)
    monkeypatch.setitem(sys.modules, "PySide2.QtCore", qt_core)
    monkeypatch.setitem(sys.modules, "PySide2.QtWidgets", qt_widgets)

    binding = qt.load_qt_binding("pyside2")

    assert binding.api == "pyside2"
    assert binding.core is qt_core
    assert binding.widgets is qt_widgets


def test_load_qt_binding_raises_clear_error_when_no_binding_exists(monkeypatch):
    def fail_import(module_name):
        raise ImportError(f"No module named {module_name}")

    monkeypatch.setattr(qt.importlib, "import_module", fail_import)

    with pytest.raises(RuntimeError, match="requires PySide6 or PySide2"):
        qt.load_qt_binding("missing")


def test_enum_value_supports_qt6_scoped_enums():
    qt_core = types.SimpleNamespace(
        Qt=types.SimpleNamespace(Key=types.SimpleNamespace(Key_Delete=123))
    )

    assert qt.enum_value(qt_core, "Key", "Key_Delete") == 123


def test_enum_value_supports_qt2_flat_enums():
    qt_core = types.SimpleNamespace(Qt=types.SimpleNamespace(Key_Delete=456))

    assert qt.enum_value(qt_core, "Key", "Key_Delete") == 456

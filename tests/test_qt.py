import sys
import types

import pytest

from materials_processor import qt


@pytest.fixture(autouse=True)
def reset_qt_cache(monkeypatch):
    monkeypatch.setattr(qt, "_qt_core", None)
    monkeypatch.setattr(qt, "_qt_widgets", None)
    monkeypatch.setattr(qt, "QT_BACKEND_NAME", None)


def test_binding_candidates_prefers_requested_binding(monkeypatch):
    monkeypatch.delenv(qt.QT_BACKEND_ENV, raising=False)

    assert qt.binding_candidates("pyside2")[0] == ("PySide2", "pyside2")


def test_binding_candidates_honors_environment(monkeypatch):
    monkeypatch.setenv(qt.QT_BACKEND_ENV, "PySide2")

    assert qt.binding_candidates()[0] == ("PySide2", "pyside2")


def test_load_qt_modules_honors_requested_binding(monkeypatch):
    pyside2 = types.ModuleType("PySide2")
    qt_core = types.ModuleType("PySide2.QtCore")
    qt_core.QObject = object
    qt_widgets = types.ModuleType("PySide2.QtWidgets")
    qt_widgets.QWidget = object
    monkeypatch.setitem(sys.modules, "PySide2", pyside2)
    monkeypatch.setitem(sys.modules, "PySide2.QtCore", qt_core)
    monkeypatch.setitem(sys.modules, "PySide2.QtWidgets", qt_widgets)

    loaded_core, loaded_widgets = qt.load_qt_modules("pyside2")

    assert qt.QT_BACKEND_NAME == "pyside2"
    assert loaded_core is qt_core
    assert loaded_widgets is qt_widgets
    assert qt.QtCore.QObject is qt_core.QObject
    assert qt.QtWidgets.QWidget is qt_widgets.QWidget


def test_load_qt_modules_raises_clear_error_when_no_binding_exists(monkeypatch):
    def fail_import(module_name):
        raise ImportError(f"No module named {module_name}")

    monkeypatch.setattr(qt.importlib, "import_module", fail_import)

    with pytest.raises(RuntimeError, match="requires PySide6 or PySide2"):
        qt.load_qt_modules("missing")


def test_enum_value_supports_qt6_scoped_enums():
    qt_core = types.SimpleNamespace(Qt=types.SimpleNamespace(Key=types.SimpleNamespace(Key_Delete=123)))
    qt_widgets = types.SimpleNamespace()
    qt._qt_core = qt_core
    qt._qt_widgets = qt_widgets

    assert qt.enum_value("Key", "Key_Delete") == 123


def test_enum_value_supports_qt2_flat_enums():
    qt_core = types.SimpleNamespace(Qt=types.SimpleNamespace(Key_Delete=456))
    qt_widgets = types.SimpleNamespace()
    qt._qt_core = qt_core
    qt._qt_widgets = qt_widgets

    assert qt.enum_value("Key", "Key_Delete") == 456

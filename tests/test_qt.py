import os
import subprocess
import sys
import types
from pathlib import Path

from materials_processor import qt


def test_qt_exports_imported_modules():
    assert qt.QT_BACKEND_NAME == "pyside6"
    assert qt.QtCore is sys.modules["PySide6.QtCore"]
    assert qt.QtWidgets is sys.modules["PySide6.QtWidgets"]


def test_qt_falls_back_to_pyside2(tmp_path):
    pyside6 = tmp_path / "PySide6"
    pyside6.mkdir()
    (pyside6 / "__init__.py").write_text("raise ImportError('PySide6 unavailable')\n")

    pyside2 = tmp_path / "PySide2"
    pyside2.mkdir()
    (pyside2 / "__init__.py").write_text("")
    (pyside2 / "QtCore.py").write_text("class Qt:\n    pass\n")
    (pyside2 / "QtWidgets.py").write_text("")

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(Path.cwd() / "src")])
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from materials_processor import qt; assert qt.QT_BACKEND_NAME == 'pyside2'",
        ],
        capture_output=True,
        env=env,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_enum_value_supports_qt6_scoped_enums(monkeypatch):
    monkeypatch.setattr(
        qt.QtCore,
        "Qt",
        types.SimpleNamespace(Key=types.SimpleNamespace(Key_Delete=123)),
        raising=False,
    )

    assert qt.enum_value("Key", "Key_Delete") == 123


def test_enum_value_supports_qt2_flat_enums(monkeypatch):
    monkeypatch.setattr(qt.QtCore, "Qt", types.SimpleNamespace(Key_Delete=456), raising=False)

    assert qt.enum_value("Key", "Key_Delete") == 456

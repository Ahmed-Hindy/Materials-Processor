"""Qt imports shared by the UI modules."""

from __future__ import annotations

try:
    from PySide6 import QtCore, QtWidgets

    QT_BACKEND_NAME = "pyside6"
except ImportError:
    try:
        from PySide2 import QtCore, QtWidgets

        QT_BACKEND_NAME = "pyside2"
    except ImportError as pyside2_error:
        raise RuntimeError("Material Processor UI requires PySide6 or PySide2.") from pyside2_error


def enum_value(enum_name: str, attr_name: str):
    """Return a Qt enum value across PySide2 and PySide6."""
    enum = getattr(QtCore.Qt, enum_name, None)
    if enum is not None and hasattr(enum, attr_name):
        return getattr(enum, attr_name)
    return getattr(QtCore.Qt, attr_name)

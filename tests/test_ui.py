import importlib
import sys
import types

import pytest

from materials_processor import ui
from materials_processor import qt
from materials_processor.mappings import FORMAT_CHOICES
from materials_processor.ui import main_window
from materials_processor.ui.state import ConversionUiState
from materials_processor.ui.widgets import split_dropped_node_paths


class _Signal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class _Widget:
    def __init__(self, *args, **kwargs):
        self.visible_count = 0
        self.raised_count = 0
        self.activated_count = 0
        self.enabled = True
        self.title = ""

    def setWindowTitle(self, title):
        self.title = title

    def resize(self, *args):
        self.size = args

    def setMinimumSize(self, *args):
        self.minimum_size = args

    def show(self):
        self.visible_count += 1

    def raise_(self):
        self.raised_count += 1

    def activateWindow(self):
        self.activated_count += 1

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setToolTip(self, text):
        self.tooltip = text

    def close(self):
        self.closed = True

    def closeEvent(self, event):
        self.closed_event = event


class _Application:
    _instance = None

    def __init__(self, args):
        self.args = args
        self.__class__._instance = self

    @classmethod
    def instance(cls):
        return cls._instance


class _MainWindow(_Widget):
    def setCentralWidget(self, widget):
        self.central_widget = widget

    def menuBar(self):
        return _MenuBar()

    def statusBar(self):
        return _StatusBar()


class _MenuBar:
    def addMenu(self, name):
        return _Menu(name)


class _Menu:
    def __init__(self, name):
        self.name = name

    def addAction(self, name):
        return types.SimpleNamespace(name=name, triggered=_Signal())


class _StatusBar:
    def showMessage(self, message):
        self.message = message


class _Layout:
    def __init__(self, *args, **kwargs):
        self.items = []

    def addWidget(self, *args):
        self.items.append(args)

    def addLayout(self, *args):
        self.items.append(args)


class _ComboBox(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = []
        self.index = -1

    def addItems(self, items):
        self.items.extend(items)
        if self.items and self.index == -1:
            self.index = 0

    def clear(self):
        self.items.clear()
        self.index = -1

    def currentIndex(self):
        return self.index

    def setCurrentIndex(self, index):
        self.index = index


class _PushButton(_Widget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text
        self.clicked = _Signal()


class _TextEdit(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages = []

    def setReadOnly(self, value):
        self.read_only = value

    def append(self, message):
        self.messages.append(message)


class _ListWidget(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = []

    def setAcceptDrops(self, value):
        self.accept_drops = value

    def setDragEnabled(self, value):
        self.drag_enabled = value

    def setDefaultDropAction(self, action):
        self.default_drop_action = action

    def setSelectionMode(self, mode):
        self.selection_mode = mode

    def addItem(self, text):
        self.items.append(types.SimpleNamespace(text=lambda: text))

    def count(self):
        return len(self.items)

    def item(self, index):
        return self.items[index]

    def clear(self):
        self.items.clear()

    def findItems(self, text, flags):
        return [item for item in self.items if item.text() == text]

    def selectedItems(self):
        return []


class _DialogButtonBox(_Widget):
    class StandardButton:
        Ok = 1
        Cancel = 2

    def __init__(self, buttons, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buttons = buttons
        self.accepted = _Signal()
        self.rejected = _Signal()


def _install_fake_qt_and_hou(monkeypatch):
    qt_core = qt.QtCore
    qt_core.Qt = types.SimpleNamespace(
        Key=types.SimpleNamespace(Key_Delete=1),
        DropAction=types.SimpleNamespace(MoveAction=2),
        MatchFlag=types.SimpleNamespace(MatchExactly=3),
    )
    qt_widgets = qt.QtWidgets
    qt_widgets.QApplication = _Application
    qt_widgets.QMainWindow = _MainWindow
    qt_widgets.QWidget = _Widget
    qt_widgets.QVBoxLayout = _Layout
    qt_widgets.QHBoxLayout = _Layout
    qt_widgets.QLabel = _Widget
    qt_widgets.QListWidget = _ListWidget
    qt_widgets.QTextEdit = _TextEdit
    qt_widgets.QComboBox = _ComboBox
    qt_widgets.QPushButton = _PushButton
    qt_widgets.QCheckBox = _Widget
    qt_widgets.QDialog = _Widget
    qt_widgets.QDialogButtonBox = _DialogButtonBox
    qt_widgets.QAbstractItemView = types.SimpleNamespace(
        SelectionMode=types.SimpleNamespace(ExtendedSelection=4)
    )
    qt_widgets.QMessageBox = types.SimpleNamespace(about=lambda *args, **kwargs: None)

    hou = types.ModuleType("hou")
    hou.session = types.SimpleNamespace()
    hou.isUIAvailable = lambda: True
    hou.ui = types.SimpleNamespace(mainQtWindow=lambda: None)
    hou.node = lambda path: None

    monkeypatch.setitem(sys.modules, "hou", hou)
    monkeypatch.setattr(main_window, "hou", hou)
    _Application._instance = None
    return hou


def test_available_format_choices_filters_unavailable_renderer_plugins(monkeypatch):
    monkeypatch.delenv("HTOA", raising=False)
    monkeypatch.delenv("REDSHIFT_COREDATAPATH", raising=False)

    choices = ui.available_format_choices()

    assert choices == {
        key: value
        for key, value in FORMAT_CHOICES.items()
        if key not in {"arnold", "rs_usd_material_builder"}
    }


def test_available_format_choices_includes_renderers_when_env_is_present(monkeypatch):
    monkeypatch.setenv("HTOA", "1")
    monkeypatch.setenv("REDSHIFT_COREDATAPATH", "1")

    assert ui.available_format_choices() == FORMAT_CHOICES


def test_split_dropped_node_paths_accepts_tabs_newlines_and_deduplicates():
    text = "/mat/a\t/mat/b\n/mat/a\r\n  /mat/c  "

    assert split_dropped_node_paths(text) == ["/mat/a", "/mat/b", "/mat/c"]
    assert ui._split_dropped_node_paths(text) == ["/mat/a", "/mat/b", "/mat/c"]


def test_conversion_ui_state_defaults_are_empty():
    state = ConversionUiState()

    assert state.selected_node_paths == []
    assert state.target_format is None
    assert state.converted_paths == []
    assert state.failed_paths == []
    assert state.is_running is False


def test_show_my_main_window_reuses_houdini_session_singleton(monkeypatch):
    hou = _install_fake_qt_and_hou(monkeypatch)

    first_window = ui.show_my_main_window()
    second_window = ui.show_my_main_window()

    assert first_window is second_window
    assert getattr(hou.session, main_window.WINDOW_SESSION_NAME) is first_window
    assert getattr(hou.session, ui._WINDOW_SESSION_NAME) is first_window
    assert first_window.visible_count == 2
    assert first_window.raised_count == 1
    assert first_window.activated_count == 1


def test_commands_run_returns_false_when_ingest_fails(monkeypatch):
    commands = importlib.import_module("materials_processor.dcc.houdini.commands")
    monkeypatch.setattr(commands, "ingest_material", lambda node: (None, None, None))

    assert commands.run(object(), object()) is False

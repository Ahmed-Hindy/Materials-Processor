"""Main Material Processor Qt window."""

from __future__ import annotations

import importlib
import logging
import os
from importlib import reload

from materials_processor.logging_config import setup_file_logging
from materials_processor.mappings import FORMAT_CHOICES
from materials_processor.qt import QtBinding, load_qt_binding
from materials_processor.ui.logging_handler import TextEditLogger
from materials_processor.ui.state import ConversionUiState
from materials_processor.ui.widgets import (
    create_node_drop_list_class,
    dialog_button_namespace,
    extended_selection_mode,
)

logger = logging.getLogger(__name__)
setup_file_logging()

WINDOW_SESSION_NAME = "_materials_processor_window"


def load_hou(required: bool = True):
    """Import Houdini's hou module on demand."""
    try:
        return importlib.import_module("hou")
    except ImportError:
        if required:
            raise RuntimeError("Material Processor UI conversion requires Houdini's hou module.") from None
        return None


def _is_renderer_available(format_name: str) -> bool:
    """Return whether the target renderer is currently available."""
    if format_name == "arnold":
        return "HTOA" in os.environ
    if format_name == "rs_usd_material_builder":
        return "REDSHIFT_COREDATAPATH" in os.environ
    return True


def available_format_choices() -> dict[str, str]:
    """Return renderer choices that are usable in the current session."""
    return {
        format_name: label
        for format_name, label in FORMAT_CHOICES.items()
        if _is_renderer_available(format_name)
    }


def create_window_classes(qt: QtBinding, hou_module):
    """Create Qt classes after a binding has been loaded."""
    QtWidgets = qt.widgets
    NodeDropList = create_node_drop_list_class(qt)
    selection_mode = extended_selection_mode(qt)
    dialog_button = dialog_button_namespace(qt)

    class PreferencesDialog(QtWidgets.QDialog):
        """Small preferences dialog for session-local UI settings."""

        def __init__(self, parent=None, preferences=None):
            super().__init__(parent)
            self.setWindowTitle("Preferences")
            self.resize(340, 160)

            layout = QtWidgets.QVBoxLayout(self)
            self.replace_material_checkbox = QtWidgets.QCheckBox(
                "Replace material assignment on linked geometry"
            )
            self.replace_material_checkbox.setEnabled(False)
            self.replace_material_checkbox.setToolTip("Planned option; conversion currently creates new materials.")
            layout.addWidget(self.replace_material_checkbox)

            layout.addWidget(QtWidgets.QLabel("Log Level:"))
            self.log_level_combobox = QtWidgets.QComboBox()
            self.log_level_combobox.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
            layout.addWidget(self.log_level_combobox)

            buttons = QtWidgets.QDialogButtonBox(dialog_button.Ok | dialog_button.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

            if preferences:
                self.log_level_combobox.setCurrentText(preferences.get("log_level", "INFO"))

    class MaterialProcessorWindow(QtWidgets.QMainWindow):
        """Main Material Processor window."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Material Processor")
            self.resize(760, 520)
            self.setMinimumSize(520, 360)
            self._qt_handler = None
            self._commands = None
            self._format_names: list[str] = []
            self.preferences = {"log_level": "INFO"}
            self.state = ConversionUiState()

            self._build_ui()
            self._configure_logging()
            self._refresh_renderer_choices()

        def _build_ui(self):
            central = QtWidgets.QWidget(self)
            self.setCentralWidget(central)

            layout = QtWidgets.QVBoxLayout(central)

            drop_label = QtWidgets.QLabel("Selected Nodes")
            layout.addWidget(drop_label)

            self.node_list = NodeDropList(self)
            self.node_list.setSelectionMode(selection_mode)
            layout.addWidget(self.node_list, 3)

            controls = QtWidgets.QHBoxLayout()
            layout.addLayout(controls)

            controls.addWidget(QtWidgets.QLabel("Target Renderer:"))
            self.format_combobox = QtWidgets.QComboBox()
            controls.addWidget(self.format_combobox, 1)

            self.refresh_button = QtWidgets.QPushButton("Refresh")
            self.refresh_button.clicked.connect(self._refresh_renderer_choices)
            controls.addWidget(self.refresh_button)

            self.convert_button = QtWidgets.QPushButton("Convert")
            self.convert_button.clicked.connect(self.run)
            controls.addWidget(self.convert_button)

            self.clear_button = QtWidgets.QPushButton("Clear")
            self.clear_button.clicked.connect(self.node_list.clear)
            controls.addWidget(self.clear_button)

            logs_label = QtWidgets.QLabel("Logs")
            layout.addWidget(logs_label)
            self.log_area = QtWidgets.QTextEdit()
            self.log_area.setReadOnly(True)
            layout.addWidget(self.log_area, 2)

            app_menu = self.menuBar().addMenu("App")
            preferences_action = app_menu.addAction("Preferences")
            preferences_action.triggered.connect(self.show_preferences_dialog)
            close_action = app_menu.addAction("Close")
            close_action.triggered.connect(self.close)

            help_menu = self.menuBar().addMenu("Help")
            about_action = help_menu.addAction("About")
            about_action.triggered.connect(self.show_about_dialog)

            self.statusBar().showMessage(f"Qt binding: {qt.api}")

        def _configure_logging(self):
            self.logger = logging.getLogger("materials_processor")
            self.logger.setLevel(logging.INFO)

            self._qt_handler = TextEditLogger(self.log_area)
            self._qt_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            self.logger.addHandler(self._qt_handler)

        def _refresh_renderer_choices(self):
            current = self.current_target_format()
            choices = available_format_choices()
            self._format_names = list(choices)
            self.format_combobox.clear()
            self.format_combobox.addItems(list(choices.values()))
            if current in self._format_names:
                self.format_combobox.setCurrentIndex(self._format_names.index(current))
            self.convert_button.setEnabled(bool(self._format_names))
            if not self._format_names:
                self.logger.warning("No target renderers are available in this session.")

        def current_target_format(self) -> str | None:
            index = self.format_combobox.currentIndex()
            if index < 0 or index >= len(self._format_names):
                return None
            return self._format_names[index]

        def _load_commands(self):
            if self._commands is None:
                self._commands = importlib.import_module("materials_processor.houdini.commands")
            return reload(self._commands)

        def _node_from_path(self, node_path: str):
            node = hou_module.node(node_path)
            if node is None:
                self.logger.warning("Node not found: %s", node_path)
            return node

        def run(self):
            """Convert all listed materials to the selected renderer."""
            self.state.selected_node_paths = self.node_list.paths()
            self.state.target_format = self.current_target_format()
            self.state.converted_paths = []
            self.state.failed_paths = []

            if not self.state.selected_node_paths:
                self.logger.warning("No material nodes selected.")
                return

            if not self.state.target_format:
                self.logger.warning("No target renderer selected.")
                return

            commands = self._load_commands()
            self.state.is_running = True
            self.convert_button.setEnabled(False)

            self.logger.info(
                "Converting %d material(s) to %s.",
                len(self.state.selected_node_paths),
                self.state.target_format,
            )
            try:
                for node_path in self.state.selected_node_paths:
                    node = self._node_from_path(node_path)
                    if node is None:
                        self.state.failed_paths.append(node_path)
                        continue

                    try:
                        result = commands.run(node, node.parent(), target_format=self.state.target_format)
                    except Exception:
                        self.logger.exception("Error converting node %s to %s.", node_path, self.state.target_format)
                        self.state.failed_paths.append(node_path)
                        continue

                    if result is False:
                        self.logger.error("Conversion failed for node %s.", node_path)
                        self.state.failed_paths.append(node_path)
                        continue

                    self.state.converted_paths.append(node_path)
                    self.logger.info("Converted node %s to %s.", node_path, self.state.target_format)
            finally:
                self.state.is_running = False
                self.convert_button.setEnabled(bool(self._format_names))

            if self.state.converted_paths and not self.state.failed_paths:
                self.node_list.clear()
                self.statusBar().showMessage(f"Converted {len(self.state.converted_paths)} material(s).")
            else:
                self.statusBar().showMessage(
                    f"Converted {len(self.state.converted_paths)} material(s), "
                    f"{len(self.state.failed_paths)} failed."
                )

        def show_about_dialog(self):
            QtWidgets.QMessageBox.about(
                self,
                "About Material Processor",
                "Material Processor\n\nAuthor: Ahmed Hindy",
            )

        def show_preferences_dialog(self):
            dialog = PreferencesDialog(self, self.preferences)
            if dialog.exec_():
                log_level = dialog.log_level_combobox.currentText()
                self.preferences["log_level"] = log_level
                self.logger.setLevel(getattr(logging, log_level, logging.INFO))
                self.logger.info("Log level set to %s.", log_level)

        def closeEvent(self, event):
            if self._qt_handler is not None:
                self.logger.removeHandler(self._qt_handler)
                self._qt_handler.close()
                self._qt_handler = None
            session_window = getattr(hou_module.session, WINDOW_SESSION_NAME, None)
            if session_window is self:
                setattr(hou_module.session, WINDOW_SESSION_NAME, None)
            super().closeEvent(event)

    return MaterialProcessorWindow, NodeDropList, PreferencesDialog


def load_ui_classes(qt_binding: str | None = None, hou_module=None):
    """Load and return the Qt window classes."""
    qt = load_qt_binding(qt_binding)
    if hou_module is None:
        hou_module = load_hou(required=True)
    return create_window_classes(qt, hou_module)


def create_main_window(parent=None, qt_binding: str | None = None, hou_module=None):
    """Create a Material Processor window."""
    MaterialProcessorWindow, _, _ = load_ui_classes(qt_binding=qt_binding, hou_module=hou_module)
    return MaterialProcessorWindow(parent)


def show_my_main_window(qt_binding: str | None = None):
    """Show the Material Processor window inside Houdini."""
    qt = load_qt_binding(qt_binding)
    hou_module = load_hou(required=True)
    app = qt.widgets.QApplication.instance()
    if app is None:
        app = qt.widgets.QApplication([])

    existing = getattr(hou_module.session, WINDOW_SESSION_NAME, None)
    if existing is not None:
        existing.show()
        existing.raise_()
        existing.activateWindow()
        return existing

    parent = hou_module.ui.mainQtWindow() if hasattr(hou_module, "ui") else None
    window = create_main_window(parent=parent, qt_binding=qt.api, hou_module=hou_module)
    setattr(hou_module.session, WINDOW_SESSION_NAME, window)
    window.show()
    logger.info("Material Processor window displayed.")
    return window

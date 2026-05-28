"""Custom Qt widgets for the Material Processor UI."""

from __future__ import annotations

import logging

from materials_processor.qt import QtBinding, enum_value

logger = logging.getLogger(__name__)


def split_dropped_node_paths(text: str) -> list[str]:
    """Parse Houdini's dropped node path text into unique paths."""
    paths: list[str] = []
    for raw_path in text.replace("\r", "\n").replace("\t", "\n").split("\n"):
        path = raw_path.strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def create_node_drop_list_class(qt: QtBinding):
    """Create the node drop list class for the loaded Qt binding."""
    QtCore = qt.core
    QtWidgets = qt.widgets
    delete_key = enum_value(QtCore, "Key", "Key_Delete")
    move_action = enum_value(QtCore, "DropAction", "MoveAction")
    match_exactly = enum_value(QtCore, "MatchFlag", "MatchExactly")

    class NodeDropList(QtWidgets.QListWidget):
        """List widget that accepts Houdini node paths by drag and drop."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAcceptDrops(True)
            self.setDragEnabled(True)
            self.setDefaultDropAction(move_action)

        def dragEnterEvent(self, event):
            if event.mimeData().hasText():
                event.acceptProposedAction()
                return
            event.ignore()

        def dragMoveEvent(self, event):
            if event.mimeData().hasText():
                event.acceptProposedAction()
                return
            event.ignore()

        def dropEvent(self, event):
            mime = event.mimeData()
            if not mime.hasText():
                logger.warning("Unsupported drag payload: %s", mime.formats())
                event.ignore()
                return

            for node_path in split_dropped_node_paths(mime.text()):
                if self.findItems(node_path, match_exactly):
                    logger.info("Node already in list: %s", node_path)
                    continue
                self.addItem(node_path)
                logger.info("Node dropped: %s", node_path)
            event.acceptProposedAction()

        def keyPressEvent(self, event):
            if event.key() == delete_key:
                for item in self.selectedItems():
                    logger.info("Node deleted: %s", item.text())
                    self.takeItem(self.row(item))
                return
            super().keyPressEvent(event)

        def paths(self) -> list[str]:
            """Return all listed node paths."""
            return [self.item(index).text() for index in range(self.count())]

    return NodeDropList


def extended_selection_mode(qt: QtBinding):
    """Return the extended-selection enum for the loaded Qt binding."""
    abstract_item_view = qt.widgets.QAbstractItemView
    if hasattr(abstract_item_view, "SelectionMode"):
        return abstract_item_view.SelectionMode.ExtendedSelection
    return abstract_item_view.ExtendedSelection


def dialog_button_namespace(qt: QtBinding):
    """Return the dialog button enum namespace for the loaded Qt binding."""
    dialog_buttons = qt.widgets.QDialogButtonBox
    if hasattr(dialog_buttons, "StandardButton"):
        return dialog_buttons.StandardButton
    return dialog_buttons

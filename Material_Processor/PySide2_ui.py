import logging
from importlib import reload
from PySide2.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTextEdit, QListWidget, QMenuBar, QMenu, QAction, QMessageBox, QDialog, QCheckBox,
                               QComboBox)
from PySide2 import QtCore, QtGui

from Material_Processor import material_processor

import hou



class QTextEditLogger(logging.Handler):
    def __init__(self, log_area):
        super().__init__()
        self.log_area = log_area

    def emit(self, record):
        msg = self.format(record)
        self.log_area.append(msg)


# Define a custom QMainWindow
class MyMainWindow(QMainWindow):
    def __init__(self, parent=None):
        super(MyMainWindow, self).__init__(parent)
        self.setWindowTitle("Material Processor")
        self.setFixedSize(600, 400)  # Set fixed size (width, height)

        # Create a central widget and set it
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Add a layout and some widgets
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        label = QLabel("Selected Nodes list:")
        layout.addWidget(label)

        # Add a list widget to act as a drop area for Houdini nodes
        self.node_list = NodeListWidget(self)
        layout.addWidget(self.node_list)

        # Add a QTextEdit widget for logging
        logs_label = QLabel("Logs:")
        layout.addWidget(logs_label)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

        # Add the format selection combo box
        format_label = QLabel("Select Material Format:")
        layout.addWidget(format_label)
        self.format_combobox = QComboBox()
        self.format_combobox.addItems(["principled_shader", "arnold", "mtlx", "usdpreview"])  # Add your formats here
        layout.addWidget(self.format_combobox)

        # Add the convert materials button and close button at the bottom
        bottom_bar = QHBoxLayout()
        layout.addLayout(bottom_bar)
        convert_button = QPushButton("Convert Materials")
        convert_button.clicked.connect(self.run)
        bottom_bar.addWidget(convert_button)

        button_close = QPushButton("Close")
        button_close.clicked.connect(self.close)
        bottom_bar.addWidget(button_close)

        # Create menu bar
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        # Add App menu
        app_menu = QMenu("App", self)
        menu_bar.addMenu(app_menu)

        # Add Preferences subitem under App menu
        preferences_action = QAction("Preferences", self)
        preferences_action.triggered.connect(self.show_preferences_dialog)
        app_menu.addAction(preferences_action)

        # Add About menu
        about_menu = QMenu("About", self)
        menu_bar.addMenu(about_menu)

        # Add About action
        about_action = QAction("About This App", self)
        about_action.triggered.connect(self.show_about_dialog)
        about_menu.addAction(about_action)

        # Configure logger to use QTextEditLogger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        # Remove all handlers associated with the root logger object
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        text_edit_handler = QTextEditLogger(self.log_area)
        text_edit_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(text_edit_handler)

        # Store preferences
        self.preferences = {
            'log_level': 'DEBUG'
        }
    
    def convert_material(self, node, target_context, target_format):
        """
        runs on a single material. Method is called by convert_materials() for each selected material
        Args:
            
        """
        material_processor.run(node, target_context, target_format=target_format)


    def run(self):
        """
        main run method. Invoked by the "Convert Materials" button".
        :return: None
        """
        reload(material_processor)
        selected_nodes = [self.node_list.item(i).text() for i in range(self.node_list.count())]
        target_format = self.format_combobox.currentText()
        self.logger.info(f"Converting materials for nodes: '{selected_nodes}' to format: '{target_format}'")

        conversion_successful = True  # Assuming conversion is successful initially
        for node_path in selected_nodes:
            node = hou.node(node_path)
            if not node:
                self.logger.warning(f"Node not found: {node_path}, skipping...")
                continue
            try:
                self.convert_material(node, target_context=node.parent(), target_format=target_format)
                self.logger.info(f"Converted materials for node: {node_path} to format: '{target_format}'")
            except Exception as e:
                self.logger.exception(f"Error converting node {node_path} to format '{target_format}': {str(e)}")
                conversion_successful = False

        if conversion_successful:
            self.node_list.clear()
            self.logger.info("Cleared node list after successful conversion.\n\n")

    def show_about_dialog(self):
        QMessageBox.about(self, "About Material Processor",
                          "Material Processor\n\nAuthor: Ahmed Hindy\nEmail: ahmed.hindy96@gmail.com")
        self.logger.info("Displayed 'About' dialog.")

    def show_preferences_dialog(self):
        dialog = PreferencesDialog(self, self.preferences)
        if dialog.exec_():
            # Update preferences based on user selection
            log_level = dialog.log_level_combobox.currentText()
            numeric_level = getattr(logging, log_level, logging.INFO)
            self.logger.setLevel(numeric_level)
            self.preferences['log_level'] = log_level
            self.logger.info(f"Log level set to {log_level}")
        self.logger.info("Displayed 'Preferences' dialog.")


class PreferencesDialog(QDialog):
    def __init__(self, parent=None, preferences=None):
        super(PreferencesDialog, self).__init__(parent)
        self.setWindowTitle("Preferences")
        self.setGeometry(400, 400, 300, 200)

        layout = QVBoxLayout(self)

        self.replace_material_checkbox = QCheckBox("Replace material assignment on linked geometry")
        layout.addWidget(self.replace_material_checkbox)

        # Log level selection
        self.log_level_label = QLabel("Log Level:")
        layout.addWidget(self.log_level_label)

        self.log_level_combobox = QComboBox()
        self.log_level_combobox.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        layout.addWidget(self.log_level_combobox)

        button_box = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        button_box.addWidget(ok_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_box.addWidget(cancel_button)

        layout.addLayout(button_box)
        logger = logging.getLogger(__name__)
        logger.info("Initialized PreferencesDialog.")

        # Set current log level from preferences
        if preferences:
            self.log_level_combobox.setCurrentText(preferences['log_level'])


class NodeListWidget(QListWidget):
    def __init__(self, parent=None):
        super(NodeListWidget, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.parent = parent
        # logger = logging.getLogger(__name__)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            logger = logging.getLogger(__name__)
            logger.debug("Drag enter event accepted.")

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if not mime.hasText():
            logger = logging.getLogger(__name__)
            logger.warning(f'Unsupported object for drag and drop, {mime.formats()}\n')

        node_paths = mime.text().split('\t')  # Split the text on tab character
        logger = logging.getLogger(__name__)
        for node_path in node_paths:
            # Check if the node is already in the list
            if not self.findItems(node_path, QtCore.Qt.MatchExactly):
                self.addItem(node_path)
                logger.info(f"Node dropped: {node_path}")
            else:
                logger.info(f"Node already in list: {node_path}")

    def keyPressEvent(self, event):
        logger = logging.getLogger(__name__)
        if event.key() == QtCore.Qt.Key_Delete:
            for item in self.selectedItems():
                self.takeItem(self.row(item))
                logger.info(f"Node deleted: {item.text()}")
        else:
            super(NodeListWidget, self).keyPressEvent(event)


# Function to show the custom window
def show_my_main_window():
    # Ensure that the QApplication instance is created only once
    if not QApplication.instance():
        app = QApplication([])

    # Create and show the main window
    main_window = MyMainWindow(hou.ui.mainQtWindow())
    main_window.show()
    logger = logging.getLogger(__name__)
    logger.info("Main window displayed.")

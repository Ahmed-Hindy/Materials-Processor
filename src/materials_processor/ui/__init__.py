"""Material Processor Qt UI package."""

from materials_processor.ui.main_window import (
    WINDOW_SESSION_NAME,
    available_format_choices,
    create_main_window,
    load_ui_classes,
    show_my_main_window,
)
from materials_processor.ui.widgets import split_dropped_node_paths

_WINDOW_SESSION_NAME = WINDOW_SESSION_NAME
_split_dropped_node_paths = split_dropped_node_paths


def __getattr__(name: str):
    """Lazily expose historical Qt class names."""
    if name in {"MyMainWindow", "MaterialProcessorWindow", "NodeListWidget", "NodeDropList", "PreferencesDialog"}:
        MaterialProcessorWindow, NodeDropList, PreferencesDialog = load_ui_classes()
        aliases = {
            "MyMainWindow": MaterialProcessorWindow,
            "MaterialProcessorWindow": MaterialProcessorWindow,
            "NodeListWidget": NodeDropList,
            "NodeDropList": NodeDropList,
            "PreferencesDialog": PreferencesDialog,
        }
        return aliases[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "WINDOW_SESSION_NAME",
    "_WINDOW_SESSION_NAME",
    "_split_dropped_node_paths",
    "available_format_choices",
    "create_main_window",
    "load_ui_classes",
    "show_my_main_window",
    "split_dropped_node_paths",
]

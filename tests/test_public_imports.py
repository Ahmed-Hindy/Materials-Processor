import importlib

import pytest


def test_public_core_and_houdini_modules_import():
    modules = [
        "materials_processor",
        "materials_processor.io",
        "materials_processor.mappings",
        "materials_processor.models",
        "materials_processor.qt",
        "materials_processor.standardizer",
        "materials_processor.houdini.commands",
        "materials_processor.houdini.recreator",
        "materials_processor.houdini.traverser",
    ]

    for module_name in modules:
        importlib.import_module(module_name)


def test_usd_public_commands_import_when_pxr_is_available():
    pytest.importorskip("pxr")

    usd_commands = importlib.import_module("materials_processor.usd.commands")

    assert callable(usd_commands.test)
    assert callable(usd_commands.test2)


def test_ui_public_entrypoint_imports_without_houdini_or_qt():
    ui = importlib.import_module("materials_processor.ui")

    assert callable(ui.show_my_main_window)
    assert callable(ui.create_main_window)

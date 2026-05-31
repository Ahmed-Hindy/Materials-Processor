import importlib

import pytest


def test_public_core_and_houdini_modules_import():
    modules = [
        "materials_processor",
        "materials_processor.cli",
        "materials_processor.core",
        "materials_processor.core.adapters",
        "materials_processor.core.conversion",
        "materials_processor.core.graph",
        "materials_processor.dcc",
        "materials_processor.dcc.usd_cli",
        "materials_processor.dcc.blender",
        "materials_processor.dcc.blender.addon",
        "materials_processor.dcc.blender.adapters",
        "materials_processor.dcc.blender.cli",
        "materials_processor.dcc.blender.recreator",
        "materials_processor.dcc.blender.runtime",
        "materials_processor.dcc.blender.traverser",
        "materials_processor.dcc.houdini.commands",
        "materials_processor.dcc.houdini.recreator",
        "materials_processor.dcc.houdini.traverser",
        "materials_processor.dcc.maya",
        "materials_processor.dcc.maya.adapters",
        "materials_processor.dcc.maya.cli",
        "materials_processor.dcc.maya.recreator",
        "materials_processor.dcc.maya.runtime",
        "materials_processor.dcc.maya.traverser",
        "materials_processor.io",
        "materials_processor.mappings",
        "materials_processor.qt",
        "materials_processor.standardizer",
        "materials_processor.ui",
        "materials_processor.ui.logging_handler",
        "materials_processor.ui.main_window",
        "materials_processor.ui.state",
        "materials_processor.ui.widgets",
    ]

    for module_name in modules:
        importlib.import_module(module_name)


def test_usd_public_commands_import_when_pxr_is_available():
    pytest.importorskip("pxr")

    usd_commands = importlib.import_module("materials_processor.usd.commands")

    assert callable(usd_commands.test)
    assert callable(usd_commands.test2)


def test_ui_public_entrypoint_imports_with_qt_available():
    ui = importlib.import_module("materials_processor.ui")

    assert callable(ui.show_my_main_window)
    assert callable(ui.create_main_window)

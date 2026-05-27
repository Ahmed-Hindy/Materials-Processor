import copy

from materials_processor import io, mappings, standardizer
from materials_processor.houdini import commands, traverser
from materials_processor.houdini.recreator import NodeRecreator
from materials_processor.models import NodeConnection, OutputConnection


class FakeNodeType:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class FakeNode:
    def __init__(self, type_name, children=None, path="/mat/fake_material"):
        self._type = FakeNodeType(type_name)
        self._children = children or []
        self._path = path

    def children(self):
        return self._children

    def name(self):
        return self._path.rsplit("/", 1)[-1]

    def parent(self):
        return FakeNode("matnet", path="/mat")

    def path(self):
        return self._path

    def type(self):
        return self._type


def test_get_material_type_detects_supported_houdini_nodes():
    assert traverser.get_material_type(FakeNode("arnold_materialbuilder")) == "arnold"
    assert traverser.get_material_type(FakeNode("redshift_vopnet")) == "redshift_vopnet"
    assert traverser.get_material_type(FakeNode("rs_usd_material_builder")) == "rs_usd_material_builder"
    assert traverser.get_material_type(FakeNode("principledshader::2.0")) == "principledshader"


def test_get_material_type_detects_mtlx_subnet_from_children():
    material_node = FakeNode("subnet", children=[FakeNode("mtlxstandard_surface")])

    assert traverser.get_material_type(material_node) == "mtlx"


def test_material_processor_test_helper_uses_checked_in_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(standardizer, "TEMP_DIR", str(tmp_path))

    nodeinfo_list, output_connections = commands.test()

    assert nodeinfo_list
    assert {key: value.to_dict() for key, value in output_connections.items()} == {
        "GENERIC::output_surface": {
            "node_name": "surface_output",
            "node_path": "/mat/mtlxmaterial_full/surface_output",
            "connected_node_name": "mtlxstandard_surface",
            "connected_node_path": "/mat/mtlxmaterial_full/mtlxstandard_surface",
            "connected_input_index": 0,
            "connected_input_name": "suboutput",
            "connected_output_name": "out",
        },
        "GENERIC::output_displacement": {
            "node_name": "displacement_output",
            "node_path": "/mat/mtlxmaterial_full/displacement_output",
            "connected_node_name": "mtlxdisplacement",
            "connected_node_path": "/mat/mtlxmaterial_full/mtlxdisplacement",
            "connected_input_index": 0,
            "connected_input_name": "suboutput",
            "connected_output_name": "out",
        },
    }


def test_standardizer_preserves_runtime_connection_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr(standardizer, "TEMP_DIR", str(tmp_path))
    traversed_nodes = io.load_node_tree_json(
        "src/materials_processor/fixtures/houdini_mtlx_full_traversed_nodes.json"
    )
    output_nodes = io.load_node_tree_json(
        "src/materials_processor/fixtures/houdini_mtlx_full_output_nodes.json"
    )

    nodeinfo_list, output_connections = standardizer.NodeStandardizer(
        traversed_nodes_dict=traversed_nodes,
        output_nodes_dict=output_nodes,
        material_type="mtlx",
        source_type="hou_vop_nodes",
    ).run()

    assert [node.node_type for node in nodeinfo_list] == [
        "GENERIC::output_node",
        "GENERIC::output_node",
    ]
    assert isinstance(output_connections["GENERIC::output_surface"], OutputConnection)
    assert output_connections["GENERIC::output_surface"].connected_node_name == "mtlxstandard_surface"
    surface_children = nodeinfo_list[0].children_list
    assert any(child.node_type == "GENERIC::standard_surface" for child in surface_children)
    surface_connection = next(
        connection
        for child in surface_children
        for connection in child.connection_info.values()
        if isinstance(connection, NodeConnection)
    )
    assert surface_connection.input.node_path == "/mat/mtlxmaterial_full/mtlxstandard_surface"
    assert surface_connection.output.node_path == "/mat/mtlxmaterial_full/surface_output"
    assert surface_connection.to_dict()["input"]["parm_name"] == "surface"


def test_opmenu_renderer_filter_does_not_mutate_global_format_choices(monkeypatch):
    original_choices = copy.deepcopy(mappings.FORMAT_CHOICES)
    displayed_buttons = []
    created_renderers = []

    class FakeHou:
        class VopNode:
            pass

        class ui:
            @staticmethod
            def displayMessage(text, buttons, default_choice, close_choice, title):
                displayed_buttons.extend(buttons)
                return buttons.index("MTLX")

    class FakeInputNode(FakeHou.VopNode, FakeNode):
        pass

    class FakeRecreator:
        was_run = False

        def __init__(
            self,
            nodeinfo_list,
            output_connections,
            target_context,
            target_renderer,
            material_name,
        ):
            created_renderers.append(target_renderer)

        def run(self):
            self.__class__.was_run = True

    monkeypatch.delenv("HTOA", raising=False)
    monkeypatch.delenv("REDSHIFT_COREDATAPATH", raising=False)
    monkeypatch.setattr(commands, "hou", FakeHou)
    monkeypatch.setattr(
        commands,
        "ingest_material",
        lambda node: ("mtlx", [object()], {"GENERIC::output_surface": {}}),
    )
    monkeypatch.setattr(commands, "NodeRecreator", FakeRecreator)

    node = FakeInputNode("subnet", path="/mat/material1")
    commands.convert_material_from_opmenu({"items": [node], "node": node})

    assert displayed_buttons == ["Principled Shader", "MTLX", "Cancel"]
    assert created_renderers == ["mtlx"]
    assert FakeRecreator.was_run
    assert mappings.FORMAT_CHOICES == original_choices


def test_houdini_recreator_constructor_does_not_run():
    recreator = NodeRecreator(
        nodeinfo_list=[],
        output_connections={},
        target_context=object(),
        target_renderer="arnold",
    )

    assert recreator.material_node is None
    assert recreator.new_output_connections == {}


def test_setup_file_logging_configures_file_logger_safely(tmp_path):
    import logging
    from materials_processor.logging_config import setup_file_logging
    
    test_log_dir = tmp_path / "logs"
    test_logger_name = "test_materials_processor"
    
    handler = setup_file_logging(
        logger_name=test_logger_name,
        log_dir=str(test_log_dir),
        max_bytes=1024,
        backup_count=2,
    )
    
    assert handler is not None
    assert isinstance(handler, logging.FileHandler)
    assert handler.baseFilename.endswith("materials_processor.log")
    
    logger = logging.getLogger(test_logger_name)
    assert handler in logger.handlers
    
    handler.close()
    logger.removeHandler(handler)


def test_setup_file_logging_falls_back_on_permission_error(tmp_path, monkeypatch):
    import logging
    import os
    from materials_processor.logging_config import setup_file_logging

    test_log_dir = tmp_path / "inaccessible_logs"
    test_logger_name = "test_fallback_logger"

    original_makedirs = os.makedirs
    def mock_makedirs(path, *args, **kwargs):
        if str(test_log_dir) in str(path):
            raise PermissionError("Access denied")
        return original_makedirs(path, *args, **kwargs)

    monkeypatch.setattr(os, "makedirs", mock_makedirs)

    handler = setup_file_logging(
        logger_name=test_logger_name,
        log_dir=str(test_log_dir),
    )

    assert handler is not None
    assert handler.baseFilename != str(test_log_dir / "materials_processor.log")
    
    logger = logging.getLogger(test_logger_name)
    handler.close()
    logger.removeHandler(handler)


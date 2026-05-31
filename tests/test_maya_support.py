"""Unit tests for Maya material support traversal and recreation."""

from materials_processor import mappings, standardizer
from materials_processor.core.conversion import ConversionService
from materials_processor.core.graph import MaterialGraph, NodeInfo, NodeParameter, OutputConnection
from materials_processor.dcc.maya.adapters import MayaMaterialReader, MayaMaterialWriter
from materials_processor.dcc.maya.recreator import MayaNodeRecreator
from materials_processor.dcc.maya.traverser import MayaNodeTraverser


MAYA_NODE_ATTRS = {
    "shadingEngine": {"surfaceShader"},
    "standardSurface": {
        "base",
        "baseColor",
        "metalness",
        "specularRoughness",
        "normalCamera",
        "outColor",
    },
    "file": {"fileTextureName", "colorSpace", "uvCoord", "outColor", "outAlpha"},
    "place2dTexture": {"outUV", "outUvFilterSize", "coverage", "translateFrame", "repeatUV", "offset", "rotateUV"},
    "bump2d": {"bumpValue", "bumpDepth", "bumpInterp", "outNormal"},
}


class FakeMayaCmds:
    """Small Maya cmds fake for shader graph traversal tests."""

    def __init__(self):
        self.nodes = {
            "mayaSmokeSG": {
                "type": "shadingEngine",
                "attrs": {"surfaceShader": None},
            },
            "mayaSmokeSurface": {
                "type": "standardSurface",
                "attrs": {
                    "base": 1.0,
                    "baseColor": [(0.8, 0.2, 0.1)],
                    "metalness": 0.25,
                    "specularRoughness": 0.4,
                    "normalCamera": [(0.0, 0.0, 1.0)],
                    "outColor": None,
                },
            },
            "mayaSmokeFile": {
                "type": "file",
                "attrs": {
                    "fileTextureName": "C:/textures/basecolor.png",
                    "colorSpace": "sRGB",
                    "uvCoord": [(0.0, 0.0)],
                    "outColor": None,
                    "outAlpha": None,
                },
            },
            "mayaSmokePlace2d": {
                "type": "place2dTexture",
                "attrs": {
                    "coverage": [(1.0, 1.0)],
                    "translateFrame": [(0.0, 0.0)],
                    "repeatUV": [(1.0, 1.0)],
                    "offset": [(0.0, 0.0)],
                    "rotateUV": 0.0,
                    "outUV": None,
                    "outUvFilterSize": None,
                },
            },
            "mayaSmokeBump": {
                "type": "bump2d",
                "attrs": {
                    "bumpValue": 0.0,
                    "bumpDepth": 1.0,
                    "bumpInterp": 1,
                    "outNormal": None,
                },
            },
        }
        self.connections = {
            "mayaSmokeSG.surfaceShader": "mayaSmokeSurface.outColor",
            "mayaSmokeSurface.baseColor": "mayaSmokeFile.outColor",
            "mayaSmokeSurface.normalCamera": "mayaSmokeBump.outNormal",
            "mayaSmokeFile.uvCoord": "mayaSmokePlace2d.outUV",
            "mayaSmokeBump.bumpValue": "mayaSmokeFile.outAlpha",
        }

    def nodeType(self, node):
        return self.nodes[node]["type"]

    def objExists(self, name):
        if "." not in name:
            return name in self.nodes
        node, attr = name.split(".", 1)
        return node in self.nodes and attr in self.nodes[node]["attrs"]

    def attributeQuery(self, attr, node, exists):
        return bool(exists and node in self.nodes and attr in self.nodes[node]["attrs"])

    def getAttr(self, plug):
        node, attr = plug.split(".", 1)
        return self.nodes[node]["attrs"][attr]

    def listConnections(self, plug, source, destination, plugs=False, **kwargs):
        if source and not destination:
            source_plug = self.connections.get(plug)
            if not source_plug:
                return []
            return [source_plug if plugs else source_plug.split(".", 1)[0]]

        if destination and not source:
            destinations = [
                dest_plug if plugs else dest_plug.split(".", 1)[0]
                for dest_plug, source_plug in self.connections.items()
                if source_plug == plug
            ]
            node_type = kwargs.get("type")
            if node_type:
                destinations = [
                    destination_plug
                    for destination_plug in destinations
                    if self.nodeType(destination_plug.split(".", 1)[0]) == node_type
                ]
            return destinations
        return []


class FakeCreateMayaCmds(FakeMayaCmds):
    """Maya cmds fake for recreation tests."""

    def __init__(self):
        self.nodes = {}
        self.connections = {}
        self.set_attrs = {}

    def _attrs_for_type(self, node_type):
        return {attr: None for attr in MAYA_NODE_ATTRS[node_type]}

    def sets(self, renderable, noSurfaceShader, empty, name):
        self.nodes[name] = {"type": "shadingEngine", "attrs": self._attrs_for_type("shadingEngine")}
        return name

    def createNode(self, node_type, name):
        unique_name = name
        suffix = 1
        while unique_name in self.nodes:
            unique_name = f"{name}{suffix}"
            suffix += 1
        self.nodes[unique_name] = {"type": node_type, "attrs": self._attrs_for_type(node_type)}
        return unique_name

    def setAttr(self, plug, *values, type=None):
        self.set_attrs[plug] = values[0] if len(values) == 1 else values
        node, attr = plug.split(".", 1)
        self.nodes[node]["attrs"][attr] = self.set_attrs[plug]

    def connectAttr(self, src_plug, dest_plug, force):
        self.connections[dest_plug] = src_plug


def _iter_nodeinfos(nodeinfos):
    for nodeinfo in nodeinfos:
        yield nodeinfo
        yield from _iter_nodeinfos(nodeinfo.children_list)


def test_maya_profile_maps_generic_nodes_without_becoming_houdini_target():
    assert "maya_nodes" in mappings.STANDARDIZER_SUPPORTED_SOURCE_TYPES
    assert mappings.convert_generic(
        "GENERIC::standard_surface",
        "maya",
        profile="maya_nodes",
    ) == "standardSurface"
    assert mappings.convert_generic(
        "GENERIC::image",
        "maya",
        profile="maya_nodes",
    ) == "file"
    assert mappings.convert_generic(
        "GENERIC::uvmap",
        "maya",
        profile="maya_nodes",
    ) == "place2dTexture"
    assert "maya" not in mappings.FORMAT_CHOICES


def test_maya_traverser_preserves_texture_and_bump_graph(monkeypatch, caplog):
    fake_cmds = FakeMayaCmds()
    monkeypatch.setattr("materials_processor.dcc.maya.traverser.cmds", fake_cmds)

    nodes_dict, output_dict = MayaNodeTraverser("mayaSmokeSG").run()
    nodeinfo_list, output_connections = standardizer.NodeStandardizer(
        traversed_nodes_dict=nodes_dict,
        output_nodes_dict=output_dict,
        material_type="maya",
        source_type="maya_nodes",
    ).run()

    all_nodes = list(_iter_nodeinfos(nodeinfo_list))
    assert {node.node_type for node in all_nodes} >= {
        "GENERIC::standard_surface",
        "GENERIC::image",
        "GENERIC::uvmap",
        "GENERIC::displacement",
    }
    assert output_connections["GENERIC::output_surface"].connected_node_name == "mayaSmokeSurface"

    image_node = next(node for node in all_nodes if node.node_type == "GENERIC::image")
    image_params = {param.generic_name: param for param in image_node.parameters}
    assert image_params["filename"].value == "C:/textures/basecolor.png"
    assert image_params["colorspace"].value == "sRGB"

    connections = [
        connection
        for node in all_nodes
        for connection in node.connection_info.values()
    ]
    assert any(
        connection.input.parm_name == "rgb" and connection.output.parm_name == "base_color"
        for connection in connections
    )
    assert any(
        connection.input.parm_name == "alpha" and connection.output.parm_name == "displacement"
        for connection in connections
    )
    assert any(
        connection.input.parm_name == "vector" and connection.output.parm_name == "texcoord"
        for connection in connections
    )
    assert "No generic type was found for node type" not in caplog.text


def test_maya_material_reader_returns_material_graph(monkeypatch):
    monkeypatch.setattr("materials_processor.dcc.maya.traverser.cmds", FakeMayaCmds())

    graph = MayaMaterialReader().read("mayaSmokeSG")

    assert isinstance(graph, MaterialGraph)
    assert graph.material_name == "mayaSmokeSG"
    assert graph.material_path == "/maya/mayaSmokeSG"
    assert graph.nodeinfo_list[0].node_type == "GENERIC::standard_surface"
    assert graph.output_connections["GENERIC::output_surface"].connected_node_name == "mayaSmokeSurface"


def test_maya_recreator_simple(monkeypatch):
    fake_cmds = FakeCreateMayaCmds()
    monkeypatch.setattr("materials_processor.dcc.maya.recreator.cmds", fake_cmds)

    node_info = NodeInfo(
        node_type="GENERIC::standard_surface",
        node_name="mayaSurface",
        node_path="/maya/source/mayaSurface",
        parameters=[
            NodeParameter("base_color", "color3", "input", [0.2, 0.4, 0.8]),
        ],
        connection_info={},
        children_list=[],
    )
    output_connection = OutputConnection(
        node_name="sourceSG",
        node_path="/maya/source/sourceSG",
        connected_node_name="mayaSurface",
        connected_node_path="/maya/source/mayaSurface",
        connected_input_index=0,
        connected_input_name="surfaceShader",
        connected_output_name="surface",
    )

    shading_engine = MayaNodeRecreator(
        nodeinfo_list=[node_info],
        output_connections={"GENERIC::output_surface": output_connection},
        target_context={"material_name": "target"},
    ).run()

    assert shading_engine == "targetSG"
    assert fake_cmds.nodes["mayaSurface"]["type"] == "standardSurface"
    assert fake_cmds.set_attrs["mayaSurface.baseColor"] == (0.2, 0.4, 0.8)
    assert fake_cmds.connections["targetSG.surfaceShader"] == "mayaSurface.outColor"


def test_maya_conversion_service_round_trips_through_adapters(monkeypatch):
    read_cmds = FakeMayaCmds()
    write_cmds = FakeCreateMayaCmds()
    monkeypatch.setattr("materials_processor.dcc.maya.traverser.cmds", read_cmds)
    monkeypatch.setattr("materials_processor.dcc.maya.recreator.cmds", write_cmds)

    converted = ConversionService(MayaMaterialReader(), MayaMaterialWriter()).convert(
        "mayaSmokeSG",
        {"material_name": "converted"},
    )

    assert converted == "convertedSG"
    assert "convertedSG.surfaceShader" in write_cmds.connections
    assert any(node["type"] == "file" for node in write_cmds.nodes.values())
    assert any(node["type"] == "place2dTexture" for node in write_cmds.nodes.values())
    assert any(node["type"] == "bump2d" for node in write_cmds.nodes.values())

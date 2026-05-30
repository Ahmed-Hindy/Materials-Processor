"""Unit tests for Blender material support traversal and recreation."""

import pytest
from materials_processor import mappings, standardizer
from materials_processor.core.graph import (
    ConnectionEndpoint,
    NodeConnection,
    NodeInfo,
    NodeParameter,
    OutputConnection,
)
from materials_processor.dcc.blender.recreator import BlenderNodeRecreator
from materials_processor.dcc.blender.traverser import BlenderNodeTraverser


def test_blender_profile_maps_generic_nodes_without_becoming_houdini_target():
    assert "blender_shader_nodes" in mappings.STANDARDIZER_SUPPORTED_SOURCE_TYPES
    assert mappings.convert_generic(
        "GENERIC::standard_surface",
        "blender",
        profile="blender_shader_nodes",
    ) == "ShaderNodeBsdfPrincipled"
    assert "blender" not in mappings.FORMAT_CHOICES


class FakeSocket:
    """Mock socket representation for Blender."""

    def __init__(self, name, socket_type="VALUE", default_value=1.0, is_linked=False):
        self.name = name
        self.type = socket_type
        self.default_value = default_value
        self.is_linked = is_linked
        self.links = []
        self.node = None


class FakeLink:
    """Mock link representation for Blender."""

    def __init__(self, from_node, from_socket, to_node, to_socket):
        self.from_node = from_node
        self.from_socket = from_socket
        self.to_node = to_node
        self.to_socket = to_socket


class FakeNode:
    """Mock node representation for Blender."""

    def __init__(self, bl_idname, name, inputs=None, outputs=None):
        self.bl_idname = bl_idname
        self.name = name
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.location = type("Location", (), {"x": 100.0, "y": 200.0})()

        # Mock Image Texture image field
        if bl_idname == "ShaderNodeTexImage":
            self.image = type("Image", (), {"filepath": "C:/textures/diffuse.png"})()


class FakeNodeTree:
    """Mock node tree representation for Blender."""

    def __init__(self, nodes=None, links=None):
        self._nodes_list = nodes or []
        self._links_list = links or []

        class NodesCollection:
            def __init__(self, parent):
                self.parent = parent

            def __iter__(self):
                return iter(self.parent._nodes_list)

            def get(self, name):
                return next((node for node in self.parent._nodes_list if node.name == name), None)

            def new(self, type):
                new_node = FakeNode(type, f"{type}_new")
                self.parent._nodes_list.append(new_node)
                return new_node

        class LinksCollection:
            def __init__(self, parent):
                self.parent = parent

            def __iter__(self):
                return iter(self.parent._links_list)

            def new(self, from_socket, to_socket):
                new_link = FakeLink(from_socket.node, from_socket, to_socket.node, to_socket)
                self.parent._links_list.append(new_link)
                from_socket.links.append(new_link)
                to_socket.links.append(new_link)
                from_socket.is_linked = True
                to_socket.is_linked = True
                return new_link

            def remove(self, link):
                if link in self.parent._links_list:
                    self.parent._links_list.remove(link)
                if link in link.from_socket.links:
                    link.from_socket.links.remove(link)
                if link in link.to_socket.links:
                    link.to_socket.links.remove(link)
                link.from_socket.is_linked = bool(link.from_socket.links)
                link.to_socket.is_linked = bool(link.to_socket.links)

        self.nodes = NodesCollection(self)
        self.links = LinksCollection(self)


class FakeMaterial:
    """Mock material representation for Blender."""

    def __init__(self, name, node_tree):
        self.name = name
        self.node_tree = node_tree
        self.use_nodes = True


def test_blender_traverser_simple():
    """Test that BlenderNodeTraverser processes Cycles material trees correctly."""
    out_node = FakeNode("ShaderNodeOutputMaterial", "Material Output")
    bsdf_node = FakeNode("ShaderNodeBsdfPrincipled", "Principled BSDF")
    tex_node = FakeNode("ShaderNodeTexImage", "Image Texture")

    # Sockets setup
    out_surf_socket = FakeSocket("Surface", "SHADER", is_linked=True)
    bsdf_out_socket = FakeSocket("BSDF", "SHADER", is_linked=True)
    bsdf_base_socket = FakeSocket("Base Color", "RGBA", is_linked=True)
    tex_color_socket = FakeSocket("Color", "RGBA", is_linked=True)

    out_node.inputs = [out_surf_socket]
    bsdf_node.outputs = [bsdf_out_socket]
    bsdf_node.inputs = [bsdf_base_socket]
    tex_node.outputs = [tex_color_socket]

    # Establish link-parent linkages
    out_surf_socket.node = out_node
    bsdf_out_socket.node = bsdf_node
    bsdf_base_socket.node = bsdf_node
    tex_color_socket.node = tex_node

    # Build Links
    link1 = FakeLink(bsdf_node, bsdf_out_socket, out_node, out_surf_socket)
    link2 = FakeLink(tex_node, tex_color_socket, bsdf_node, bsdf_base_socket)

    out_surf_socket.links = [link1]
    bsdf_out_socket.links = [link1]
    bsdf_base_socket.links = [link2]
    tex_color_socket.links = [link2]

    node_tree = FakeNodeTree(
        nodes=[out_node, bsdf_node, tex_node],
        links=[link1, link2]
    )
    material = FakeMaterial("test_mat", node_tree)

    traverser = BlenderNodeTraverser(material)
    nodes_dict, output_dict = traverser.run()

    assert "surface" in output_dict
    assert output_dict["surface"]["connected_node_name"] == "Principled BSDF"

    target_path = "/mat/test_mat/Principled BSDF"
    assert target_path in nodes_dict
    assert len(nodes_dict[target_path]["children_list"]) == 1
    assert nodes_dict[target_path]["children_list"][0]["node_name"] == "Image Texture"

    nodeinfo_list, output_connections = standardizer.NodeStandardizer(
        traversed_nodes_dict=nodes_dict,
        output_nodes_dict=output_dict,
        material_type="blender",
        source_type="blender_shader_nodes",
    ).run()
    assert nodeinfo_list[0].node_type == "GENERIC::standard_surface"
    assert output_connections["GENERIC::output_surface"].connected_node_name == "Principled BSDF"


def test_blender_recreator_simple():
    """Test that BlenderNodeRecreator successfully reconstructs material nodes."""
    surface_param = NodeParameter(
        generic_name="base_color",
        generic_type="color3",
        direction="input",
        value=[0.8, 0.2, 0.2]
    )

    node_info = NodeInfo(
        node_type="GENERIC::standard_surface",
        node_name="Principled_BSDF",
        node_path="/mat/test_mat/Principled_BSDF",
        parameters=[surface_param],
        connection_info={},
        children_list=[],
        is_output_node=False,
        position=[150.0, 300.0]
    )

    output_connection = OutputConnection(
        node_name="Material Output",
        node_path="/mat/test_mat/Material Output",
        connected_node_name="Principled_BSDF",
        connected_node_path="/mat/test_mat/Principled_BSDF",
        connected_input_index=0,
        connected_input_name="Surface",
        connected_output_name="surface"
    )

    out_node = FakeNode("ShaderNodeOutputMaterial", "Material Output")
    node_tree = FakeNodeTree(nodes=[out_node], links=[])
    material = FakeMaterial("test_mat", node_tree)

    recreator = BlenderNodeRecreator(
        nodeinfo_list=[node_info],
        output_connections={"GENERIC::output_surface": output_connection},
        target_material=material
    )

    success = recreator.run()
    assert success

    created_nodes = list(material.node_tree.nodes)
    assert any(n.bl_idname == "ShaderNodeBsdfPrincipled" for n in created_nodes)

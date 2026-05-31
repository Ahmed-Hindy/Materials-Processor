"""Unit tests for Blender material support traversal and recreation."""

import pytest
from materials_processor import mappings, standardizer
from materials_processor.core.graph import (
    ConnectionEndpoint,
    MaterialGraph,
    NodeConnection,
    NodeInfo,
    NodeParameter,
    OutputConnection,
)
from materials_processor.core.conversion import ConversionService
from materials_processor.dcc.blender.adapters import BlenderMaterialReader, BlenderMaterialWriter
from materials_processor.dcc.blender.recreator import BlenderNodeRecreator
from materials_processor.dcc.blender.traverser import BlenderNodeTraverser


def test_blender_profile_maps_generic_nodes_without_becoming_houdini_target():
    assert "blender_shader_nodes" in mappings.STANDARDIZER_SUPPORTED_SOURCE_TYPES
    assert mappings.convert_generic(
        "GENERIC::standard_surface",
        "blender",
        profile="blender_shader_nodes",
    ) == "ShaderNodeBsdfPrincipled"
    assert mappings.convert_generic(
        "GENERIC::uvmap",
        "blender",
        profile="blender_shader_nodes",
    ) == "ShaderNodeUVMap"
    assert mappings.convert_generic(
        "GENERIC::mapping",
        "blender",
        profile="blender_shader_nodes",
    ) == "ShaderNodeMapping"
    assert mappings.convert_generic(
        "GENERIC::value",
        "blender",
        profile="blender_shader_nodes",
    ) == "ShaderNodeValue"
    assert mappings.convert_generic(
        "GENERIC::separate_color",
        "blender",
        profile="blender_shader_nodes",
    ) == "ShaderNodeSeparateColor"
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
        elif bl_idname == "ShaderNodeUVMap":
            self.uv_map = "UVMap"


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


def _make_simple_fake_blender_material(name="test_mat"):
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
    return FakeMaterial(name, node_tree)


def _link(from_node, from_socket, to_node, to_socket):
    from_socket.node = from_node
    to_socket.node = to_node
    from_socket.is_linked = True
    to_socket.is_linked = True
    link = FakeLink(from_node, from_socket, to_node, to_socket)
    from_socket.links.append(link)
    to_socket.links.append(link)
    return link


def _iter_nodeinfos(nodeinfos):
    for nodeinfo in nodeinfos:
        yield nodeinfo
        yield from _iter_nodeinfos(nodeinfo.children_list)


def _make_packed_texture_fake_blender_material(name="packed_mat"):
    out_node = FakeNode("ShaderNodeOutputMaterial", "Material Output")
    bsdf_node = FakeNode("ShaderNodeBsdfPrincipled", "Principled BSDF")
    tex_node = FakeNode("ShaderNodeTexImage", "Packed Texture")
    uv_node = FakeNode("ShaderNodeUVMap", "UV Map")
    separate_node = FakeNode("ShaderNodeSeparateColor", "Separate Color")

    out_surf_socket = FakeSocket("Surface", "SHADER")
    bsdf_out_socket = FakeSocket("BSDF", "SHADER")
    bsdf_base_socket = FakeSocket("Base Color", "RGBA")
    bsdf_metallic_socket = FakeSocket("Metallic", "VALUE")
    bsdf_roughness_socket = FakeSocket("Roughness", "VALUE")
    tex_vector_socket = FakeSocket("Vector", "VECTOR")
    tex_color_socket = FakeSocket("Color", "RGBA")
    tex_alpha_socket = FakeSocket("Alpha", "VALUE")
    uv_socket = FakeSocket("UV", "VECTOR")
    separate_color_socket = FakeSocket("Color", "RGBA")
    separate_green_socket = FakeSocket("Green", "VALUE")
    separate_blue_socket = FakeSocket("Blue", "VALUE")

    out_node.inputs = [out_surf_socket]
    bsdf_node.outputs = [bsdf_out_socket]
    bsdf_node.inputs = [bsdf_base_socket, bsdf_metallic_socket, bsdf_roughness_socket]
    tex_node.inputs = [tex_vector_socket]
    tex_node.outputs = [tex_color_socket, tex_alpha_socket]
    uv_node.outputs = [uv_socket]
    separate_node.inputs = [separate_color_socket]
    separate_node.outputs = [separate_green_socket, separate_blue_socket]

    links = [
        _link(bsdf_node, bsdf_out_socket, out_node, out_surf_socket),
        _link(tex_node, tex_color_socket, bsdf_node, bsdf_base_socket),
        _link(tex_node, tex_color_socket, separate_node, separate_color_socket),
        _link(uv_node, uv_socket, tex_node, tex_vector_socket),
        _link(separate_node, separate_blue_socket, bsdf_node, bsdf_metallic_socket),
        _link(separate_node, separate_green_socket, bsdf_node, bsdf_roughness_socket),
    ]

    node_tree = FakeNodeTree(
        nodes=[out_node, bsdf_node, tex_node, uv_node, separate_node],
        links=links,
    )
    return FakeMaterial(name, node_tree)


def _make_mapped_texture_fake_blender_material(name="mapped_mat"):
    out_node = FakeNode("ShaderNodeOutputMaterial", "Material Output")
    bsdf_node = FakeNode("ShaderNodeBsdfPrincipled", "Principled BSDF")
    tex_node = FakeNode("ShaderNodeTexImage", "Image Texture")
    texcoord_node = FakeNode("ShaderNodeTexCoord", "Texture Coordinate")
    mapping_node = FakeNode("ShaderNodeMapping", "Mapping")
    value_node = FakeNode("ShaderNodeValue", "Roughness Value")

    out_surf_socket = FakeSocket("Surface", "SHADER")
    bsdf_out_socket = FakeSocket("BSDF", "SHADER")
    bsdf_base_socket = FakeSocket("Base Color", "RGBA")
    bsdf_roughness_socket = FakeSocket("Roughness", "VALUE")
    tex_vector_socket = FakeSocket("Vector", "VECTOR")
    tex_color_socket = FakeSocket("Color", "RGBA")
    texcoord_uv_socket = FakeSocket("UV", "VECTOR", default_value=[0.0, 0.0, 0.0])
    mapping_vector_in_socket = FakeSocket("Vector", "VECTOR", default_value=[0.0, 0.0, 0.0])
    mapping_location_socket = FakeSocket("Location", "VECTOR", default_value=[0.25, 0.5, 0.0])
    mapping_rotation_socket = FakeSocket("Rotation", "VECTOR", default_value=[0.0, 0.0, 1.57079632679])
    mapping_scale_socket = FakeSocket("Scale", "VECTOR", default_value=[2.0, 3.0, 1.0])
    mapping_vector_out_socket = FakeSocket("Vector", "VECTOR")
    value_socket = FakeSocket("Value", "VALUE", default_value=0.42)

    out_node.inputs = [out_surf_socket]
    bsdf_node.outputs = [bsdf_out_socket]
    bsdf_node.inputs = [bsdf_base_socket, bsdf_roughness_socket]
    tex_node.inputs = [tex_vector_socket]
    tex_node.outputs = [tex_color_socket]
    texcoord_node.outputs = [texcoord_uv_socket]
    mapping_node.inputs = [mapping_vector_in_socket, mapping_location_socket, mapping_rotation_socket, mapping_scale_socket]
    mapping_node.outputs = [mapping_vector_out_socket]
    value_node.outputs = [value_socket]

    links = [
        _link(bsdf_node, bsdf_out_socket, out_node, out_surf_socket),
        _link(tex_node, tex_color_socket, bsdf_node, bsdf_base_socket),
        _link(texcoord_node, texcoord_uv_socket, mapping_node, mapping_vector_in_socket),
        _link(mapping_node, mapping_vector_out_socket, tex_node, tex_vector_socket),
        _link(value_node, value_socket, bsdf_node, bsdf_roughness_socket),
    ]

    return FakeMaterial(
        name,
        FakeNodeTree(
            nodes=[out_node, bsdf_node, tex_node, texcoord_node, mapping_node, value_node],
            links=links,
        ),
    )


def test_blender_traverser_simple():
    """Test that BlenderNodeTraverser processes Cycles material trees correctly."""
    material = _make_simple_fake_blender_material()

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


def test_blender_traverser_preserves_packed_texture_graph(caplog):
    """Test that texture coordinates and packed channel splits survive standardization."""
    material = _make_packed_texture_fake_blender_material()

    nodes_dict, output_dict = BlenderNodeTraverser(material).run()
    nodeinfo_list, _ = standardizer.NodeStandardizer(
        traversed_nodes_dict=nodes_dict,
        output_nodes_dict=output_dict,
        material_type="blender",
        source_type="blender_shader_nodes",
    ).run()

    all_nodes = list(_iter_nodeinfos(nodeinfo_list))
    assert {node.node_type for node in all_nodes} >= {
        "GENERIC::standard_surface",
        "GENERIC::image",
        "GENERIC::uvmap",
        "GENERIC::separate_color",
    }

    image_node = next(node for node in all_nodes if node.node_type == "GENERIC::image")
    image_params = {param.generic_name: param for param in image_node.parameters}
    assert image_params["filename"].value == "C:/textures/diffuse.png"
    assert {"rgb", "alpha"} <= {param.generic_name for param in image_node.parameters}

    uv_node = next(node for node in all_nodes if node.node_type == "GENERIC::uvmap")
    uv_params = {param.generic_name: param for param in uv_node.parameters}
    assert uv_params["uv_map"].value == "UVMap"
    assert uv_params["vector"].generic_type == "vector2"

    connections = [
        connection
        for node in all_nodes
        for connection in node.connection_info.values()
    ]
    assert any(
        connection.input.parm_name == "vector" and connection.output.parm_name == "texcoord"
        for connection in connections
    )
    assert any(
        connection.input.parm_name == "b" and connection.output.parm_name == "metalness"
        for connection in connections
    )
    assert any(
        connection.input.parm_name == "g" and connection.output.parm_name == "specular_roughness"
        for connection in connections
    )
    assert "No generic type was found for node type: 'ShaderNodeUVMap'" not in caplog.text
    assert "No generic type was found for node type: 'ShaderNodeSeparateColor'" not in caplog.text


def test_blender_traverser_preserves_texcoord_mapping_and_value_nodes(caplog):
    material = _make_mapped_texture_fake_blender_material()

    nodes_dict, output_dict = BlenderNodeTraverser(material).run()
    nodeinfo_list, _ = standardizer.NodeStandardizer(
        traversed_nodes_dict=nodes_dict,
        output_nodes_dict=output_dict,
        material_type="blender",
        source_type="blender_shader_nodes",
    ).run()

    all_nodes = list(_iter_nodeinfos(nodeinfo_list))
    assert {node.node_type for node in all_nodes} >= {
        "GENERIC::standard_surface",
        "GENERIC::image",
        "GENERIC::uvmap",
        "GENERIC::mapping",
        "GENERIC::value",
    }

    mapping_node = next(node for node in all_nodes if node.node_type == "GENERIC::mapping")
    mapping_params = {param.generic_name: param for param in mapping_node.parameters}
    assert mapping_params["offset"].value == [0.25, 0.5]
    assert mapping_params["scale"].value == [2.0, 3.0]
    assert mapping_params["rotate"].value == pytest.approx(90.0)
    assert mapping_params["out"].generic_type == "vector2"

    value_node = next(node for node in all_nodes if node.node_type == "GENERIC::value")
    value_params = {param.generic_name: param for param in value_node.parameters}
    assert value_params["value"].value == 0.42

    connections = [
        connection
        for node in all_nodes
        for connection in node.connection_info.values()
    ]
    assert any(
        connection.input.parm_name == "vector" and connection.output.parm_name == "texcoord"
        for connection in connections
    )
    assert any(
        connection.input.parm_name == "out" and connection.output.parm_name == "texcoord"
        for connection in connections
    )
    assert any(
        connection.input.parm_name == "out" and connection.output.parm_name == "specular_roughness"
        for connection in connections
    )
    assert "No generic type was found for node type: 'ShaderNodeTexCoord'" not in caplog.text
    assert "No generic type was found for node type: 'ShaderNodeMapping'" not in caplog.text
    assert "No generic type was found for node type: 'ShaderNodeValue'" not in caplog.text


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


def test_blender_material_reader_returns_material_graph():
    material = _make_simple_fake_blender_material("adapter_source")

    graph = BlenderMaterialReader().read(material)

    assert isinstance(graph, MaterialGraph)
    assert graph.material_name == "adapter_source"
    assert graph.material_path == "/mat/adapter_source"
    assert graph.nodeinfo_list[0].node_type == "GENERIC::standard_surface"
    assert graph.output_connections["GENERIC::output_surface"].connected_node_name == "Principled BSDF"


def test_blender_material_writer_recreates_graph_into_target_material():
    node_info = NodeInfo(
        node_type="GENERIC::standard_surface",
        node_name="Principled_BSDF",
        node_path="/mat/source/Principled_BSDF",
        parameters=[
            NodeParameter(
                generic_name="base_color",
                generic_type="color3",
                direction="input",
                value=[0.2, 0.4, 0.8],
            )
        ],
        connection_info={},
        children_list=[],
        is_output_node=False,
        position=[100.0, 200.0],
    )
    output_connection = OutputConnection(
        node_name="Material Output",
        node_path="/mat/source/Material Output",
        connected_node_name="Principled_BSDF",
        connected_node_path="/mat/source/Principled_BSDF",
        connected_input_index=0,
        connected_input_name="Surface",
        connected_output_name="surface",
    )
    graph = MaterialGraph(
        material_name="source",
        material_path="/mat/source",
        nodeinfo_list=[node_info],
        output_connections={"GENERIC::output_surface": output_connection},
    )
    out_node = FakeNode("ShaderNodeOutputMaterial", "Material Output")
    target = FakeMaterial("adapter_target", FakeNodeTree(nodes=[out_node], links=[]))

    written_material = BlenderMaterialWriter().write(graph, target)

    assert written_material is target
    assert any(node.bl_idname == "ShaderNodeBsdfPrincipled" for node in target.node_tree.nodes)


def test_blender_conversion_service_round_trips_through_adapters():
    source = _make_simple_fake_blender_material("conversion_source")
    target = FakeMaterial(
        "conversion_target",
        FakeNodeTree(nodes=[FakeNode("ShaderNodeOutputMaterial", "Material Output")], links=[]),
    )

    converted = ConversionService(BlenderMaterialReader(), BlenderMaterialWriter()).convert(source, target)

    assert converted is target
    assert any(node.bl_idname == "ShaderNodeBsdfPrincipled" for node in target.node_tree.nodes)


def test_blender_principled_mapping_covers_blender_4_inputs(caplog):
    principled_inputs = [
        "Weight",
        "Base Color",
        "Diffuse Roughness",
        "Metallic",
        "Roughness",
        "IOR",
        "Alpha",
        "Normal",
        "Subsurface Weight",
        "Subsurface Radius",
        "Subsurface Scale",
        "Subsurface IOR",
        "Subsurface Anisotropy",
        "Specular IOR Level",
        "Specular Tint",
        "Anisotropic",
        "Anisotropic Rotation",
        "Tangent",
        "Transmission Weight",
        "Emission Color",
        "Emission Strength",
        "Coat Weight",
        "Coat Roughness",
        "Coat IOR",
        "Coat Tint",
        "Coat Normal",
        "Sheen Weight",
        "Sheen Roughness",
        "Sheen Tint",
        "Thin Film Thickness",
        "Thin Film IOR",
    ]
    parms = {
        "input": [
            {
                "generic_name": name,
                "value": [0.25, 0.5, 0.75, 1.0] if name in {"Base Color", "Emission Color"} else 1.0,
                "type": "color4" if name in {"Base Color", "Emission Color"} else "float1",
                "direction": "input",
            }
            for name in principled_inputs
        ],
        "output": [
            {
                "generic_name": "BSDF",
                "value": None,
                "type": "float1",
                "direction": "output",
            }
        ],
    }

    parameters = standardizer.NodeStandardizer.standardize_shader_parameters("ShaderNodeBsdfPrincipled", parms)

    generic_names = {parameter.generic_name for parameter in parameters}
    assert {
        "base",
        "base_color",
        "diffuse_roughness",
        "metalness",
        "specular_roughness",
        "specular_IOR",
        "opacity",
        "normal",
        "subsurface",
        "subsurface_radius",
        "subsurface_scale",
        "subsurface_IOR",
        "subsurface_anisotropy",
        "specular",
        "specular_color",
        "specular_anisotropy",
        "specular_rotation",
        "tangent",
        "transmission",
        "emission_color",
        "emission",
        "coat",
        "coat_roughness",
        "coat_IOR",
        "coat_color",
        "coat_normal",
        "sheen",
        "sheen_roughness",
        "sheen_color",
        "thin_film_thickness",
        "thin_film_IOR",
        "surface",
    } <= generic_names
    assert "Unsupported parameters for node type 'ShaderNodeBsdfPrincipled'" not in caplog.text

from materials_processor import io as material_io
from materials_processor.standardizer import NodeStandardizer


def _standardize_principled_fixture():
    traversed_nodes = material_io.load_node_tree_json(
        "src/materials_processor/fixtures/houdini_principled_native_traversed_nodes.json"
    )
    output_nodes = material_io.load_node_tree_json(
        "src/materials_processor/fixtures/houdini_principled_native_output_nodes.json"
    )

    return NodeStandardizer(
        traversed_nodes_dict=traversed_nodes,
        output_nodes_dict=output_nodes,
        material_type="principledshader",
        source_type="hou_vop_nodes",
    ).run()


def test_principled_standardization_starts_from_native_single_node():
    nodeinfo_list, output_connections = _standardize_principled_fixture()

    assert [node.node_path for node in nodeinfo_list] == ["/mat/principledshader"]
    surface_node = nodeinfo_list[0]
    assert surface_node.node_name == "principledshader"
    assert surface_node.node_type == "GENERIC::standard_surface"
    assert set(output_connections) == {"GENERIC::output_surface"}


def test_principled_standardization_expands_enabled_textures_to_generic_children():
    nodeinfo_list, _ = _standardize_principled_fixture()
    surface_node = nodeinfo_list[0]

    child_nodes = {node.node_name: node for node in surface_node.children_list}
    assert {"image_base_color", "image_roughness", "normalmap_base"} <= set(child_nodes)
    assert child_nodes["image_base_color"].node_type == "GENERIC::image"
    assert child_nodes["image_roughness"].node_type == "GENERIC::image"
    assert child_nodes["normalmap_base"].node_type == "GENERIC::normalmap"

    base_color_connection = next(iter(child_nodes["image_base_color"].connection_info.values()))
    assert base_color_connection.output.parm_name == "base_color"
    roughness_connection = next(iter(child_nodes["image_roughness"].connection_info.values()))
    assert roughness_connection.output.parm_name == "specular_roughness"


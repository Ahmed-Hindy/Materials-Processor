from materials_processor import mappings, standardizer
from materials_processor.standardizer import NodeStandardizer


def test_openpbr_standardization_maps_surface_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr(standardizer, "TEMP_DIR", str(tmp_path))

    traversed_nodes = {
        "/mat/openpbr_material/surface_output": {
            "node_name": "surface_output",
            "node_path": "/mat/openpbr_material/surface_output",
            "node_type": "subnetconnector",
            "node_position": [0, 0],
            "node_parms": {
                "input": [],
                "output": [],
            },
            "connections_dict": {},
            "children_list": [
                {
                    "node_name": "mtlxopen_pbr_surface",
                    "node_path": "/mat/openpbr_material/mtlxopen_pbr_surface",
                    "node_type": "mtlxopen_pbr_surface",
                    "node_position": [0, 1],
                    "node_parms": {
                        "input": [
                            {
                                "generic_name": "base_color",
                                "value": [0.2, 0.4, 0.6],
                                "type": "color3",
                                "direction": "input",
                            },
                            {
                                "generic_name": "base_metalness",
                                "value": [0.75],
                                "type": "float1",
                                "direction": "input",
                            },
                            {
                                "generic_name": "specular_ior",
                                "value": [1.45],
                                "type": "float1",
                                "direction": "input",
                            },
                            {
                                "generic_name": "fuzz_weight",
                                "value": [0.3],
                                "type": "float1",
                                "direction": "input",
                            },
                        ],
                        "output": [
                            {
                                "generic_name": "out",
                                "value": None,
                                "type": "surface1",
                                "direction": "output",
                            }
                        ],
                    },
                    "connections_dict": {
                        "connection_0": {
                            "input": {
                                "node_name": "mtlxopen_pbr_surface",
                                "node_path": "/mat/openpbr_material/mtlxopen_pbr_surface",
                                "node_type": "mtlxopen_pbr_surface",
                                "node_index": 0,
                                "parm_name": "out",
                                "data_type": "surface",
                            },
                            "output": {
                                "node_name": "surface_output",
                                "node_path": "/mat/openpbr_material/surface_output",
                                "node_type": "subnetconnector",
                                "node_index": 0,
                                "parm_name": "suboutput",
                                "data_type": "surface",
                            },
                        }
                    },
                    "children_list": [],
                }
            ],
        }
    }
    output_nodes = {
        "surface": {
            "node_name": "surface_output",
            "node_path": "/mat/openpbr_material/surface_output",
            "connected_node_name": "mtlxopen_pbr_surface",
            "connected_node_path": "/mat/openpbr_material/mtlxopen_pbr_surface",
            "connected_input_index": 0,
            "connected_input_name": "suboutput",
            "connected_output_name": "out",
        }
    }

    nodeinfo_list, output_connections = NodeStandardizer(
        traversed_nodes_dict=traversed_nodes,
        output_nodes_dict=output_nodes,
        material_type="openpbr",
        source_type="hou_vop_nodes",
    ).run()

    surface_node = nodeinfo_list[0].children_list[0]
    parameters = {parameter.generic_name: parameter.value for parameter in surface_node.parameters}

    assert surface_node.node_type == "GENERIC::standard_surface"
    assert parameters["base_color"] == [0.2, 0.4, 0.6]
    assert parameters["metalness"] == 0.75
    assert parameters["specular_IOR"] == 1.45
    assert parameters["fuzz_weight"] == 0.3
    assert output_connections["GENERIC::output_surface"].connected_node_name == "mtlxopen_pbr_surface"


def test_openpbr_target_uses_openpbr_surface_without_changing_mtlx_target():
    assert mappings.convert_generic("GENERIC::standard_surface", "openpbr") == "mtlxopen_pbr_surface"
    assert mappings.convert_generic("GENERIC::standard_surface", "mtlx") == "mtlxstandard_surface"

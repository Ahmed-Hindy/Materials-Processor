"""Synthetic Houdini Principled Shader traversal adapter."""


def build_principled_entry(node, convert_parms):
    """Build the compatibility graph used for Principled Shader materials.

    Args:
        node: Houdini Principled Shader node to adapt.
        convert_parms: Callable matching
            :meth:`NodeTraverser._convert_parms_to_dict`.

    Returns:
        dict: Synthetic MaterialX-like traversal tree for the principled node.
    """
    convert_parms(node)

    entry = {
        f"{node.path()}/surface_output": {
            "node_name": "surface_output",
            "node_path": f"{node.path()}/surface_output",
            "node_type": "subnetconnector",
            "node_position": [0, 0],
            "node_parms": [],
            "connections_dict": {},
            "children_list": [
                {
                    "node_name": "mtlxstandard_surface",
                    "node_path": f"{node.path()}/mtlxstandard_surface",
                    "node_type": "mtlxstandard_surface",
                    "node_position": [-3, 0],
                    "node_parms": [],
                    "connections_dict": {
                        "connection_0": {
                            "input": {
                                "node_name": "mtlxstandard_surface",
                                "node_path": f"{node.path()}/mtlxstandard_surface",
                                "node_type": "mtlxstandard_surface",
                                "node_index": 0,
                                "parm_name": "out",
                            },
                            "output": {
                                "node_name": "surface_output",
                                "node_path": f"{node.path()}/surface_output",
                                "node_type": "subnetconnector",
                                "node_index": 0,
                                "parm_name": "suboutput",
                            },
                        }
                    },
                    "children_list": [],
                },
            ],
        },
        f"{node.path()}/displacement_output": {
            "node_name": "displacement_output",
            "node_path": f"{node.path()}/displacement_output",
            "node_type": "subnetconnector",
            "node_position": [-4, 1],
            "node_parms": [],
            "connections_dict": {},
            "children_list": [
                {
                    "node_name": "mtlxdisplacement",
                    "node_path": f"{node.path()}l/mtlxdisplacement",
                    "node_type": "mtlxdisplacement",
                    "node_position": [0, -3],
                    "node_parms": {},
                    "connections_dict": {
                        "connection_0": {
                            "input": {
                                "node_name": "mtlxdisplacement",
                                "node_path": f"{node.path()}/mtlxdisplacement",
                                "node_type": "mtlxdisplacement",
                                "node_index": 0,
                                "parm_name": "out",
                                "data_type": "displacement",
                            },
                            "output": {
                                "node_name": "displacement_output",
                                "node_path": f"{node.path()}l/displacement_output",
                                "node_type": "subnetconnector",
                                "node_index": 0,
                                "parm_name": "suboutput",
                                "data_type": "displacement",
                            },
                        }
                    },
                    "children_list": [],
                }
            ],
        },
    }

    if node.parm("basecolor_useTexture").eval():
        entry[f"{node.path()}/surface_output"]["children_list"][0]["children_list"].append(
            {
                "node_name": "image_diffuse",
                "node_path": f"{node.path()}/image_diffuse",
                "node_type": "mtlximage",
                "node_position": [-6, 0],
                "node_parms": {
                    "input": [
                        {
                            "generic_name": "file",
                            "value": node.parm("basecolor_texture").eval(),
                            "type": "string1",
                            "direction": "input",
                        },
                    ],
                    "output": [],
                },
                "connections_dict": {
                    "connection_0": {
                        "input": {
                            "node_name": "image_diffuse",
                            "node_path": f"{node.path()}/image_diffuse",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out",
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 1,
                            "parm_name": "base_color",
                        },
                    },
                },
            }
        )

    if node.parm("metallic_useTexture").eval():
        entry[f"{node.path()}/surface_output"]["children_list"][0]["children_list"].append(
            {
                "node_name": "image_metalness",
                "node_path": f"{node.path()}/image_metalness",
                "node_type": "mtlximage",
                "node_position": [-6, -3],
                "node_parms": {
                    "input": [
                        {
                            "generic_name": "file",
                            "value": node.parm("metallic_texture").eval(),
                            "type": "string1",
                            "direction": "input",
                        },
                    ],
                    "output": [],
                },
                "connections_dict": {
                    "connection_0": {
                        "input": {
                            "node_name": "image_metalness",
                            "node_path": f"{node.path()}/image_metalness",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out",
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 3,
                            "parm_name": "metalness",
                        },
                    },
                },
            }
        )

    if node.parm("rough_useTexture").eval():
        entry[f"{node.path()}/surface_output"]["children_list"][0]["children_list"].append(
            {
                "node_name": "image_roughness",
                "node_path": f"{node.path()}/image_roughness",
                "node_type": "mtlximage",
                "node_position": [-6, -6],
                "node_parms": {
                    "input": [
                        {
                            "generic_name": "file",
                            "value": node.parm("rough_texture").eval(),
                            "type": "string1",
                            "direction": "input",
                        },
                    ],
                    "output": [],
                },
                "connections_dict": {
                    "connection_0": {
                        "input": {
                            "node_name": "image_roughness",
                            "node_path": f"{node.path()}/image_roughness",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out",
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 6,
                            "parm_name": "specular_roughness",
                        },
                    },
                },
            }
        )

    if node.parm("sss_useTexture").eval():
        entry[f"{node.path()}/surface_output"]["children_list"][0]["children_list"].append(
            {
                "node_name": "image_sss",
                "node_path": f"{node.path()}/image_sss",
                "node_type": "mtlximage",
                "node_position": [-6, -9],
                "node_parms": {
                    "input": [
                        {
                            "generic_name": "file",
                            "value": node.parm("sss_texture").eval(),
                            "type": "string1",
                            "direction": "input",
                        },
                    ],
                    "output": [],
                },
                "connections_dict": {
                    "connection_0": {
                        "input": {
                            "node_name": "image_sss",
                            "node_path": f"{node.path()}/image_sss",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out",
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 30,
                            "parm_name": "subsurface_color",
                        },
                    },
                },
            }
        )

    if node.parm("baseBumpAndNormal_enable").eval() and node.parm("baseBumpAndNormal_type").eval() == "normal":
        entry[f"{node.path()}/surface_output"]["children_list"][0]["children_list"].append(
            {
                "node_name": "mtlxnormalmap1",
                "node_path": f"{node.path()}/mtlxnormalmap1",
                "node_type": "mtlxnormalmap::2.0",
                "node_position": [-6, -12],
                "node_parms": {
                    "input": [],
                    "output": [],
                },
                "connections_dict": {
                    "connection_0": {
                        "input": {
                            "node_name": "mtlxnormalmap1",
                            "node_path": f"{node.path()}/mtlxnormalmap1",
                            "node_type": "mtlxnormalmap::2.0",
                            "node_index": 0,
                            "parm_name": "out",
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 40,
                            "parm_name": "normal",
                        },
                    },
                },
                "children_list": [
                    {
                        "node_name": "image_normal",
                        "node_path": f"{node.path()}/image_normal",
                        "node_type": "mtlximage",
                        "node_position": [-9, -7],
                        "node_parms": {
                            "input": [
                                {
                                    "generic_name": "file",
                                    "value": node.parm("baseNormal_texture").eval(),
                                    "type": "string1",
                                    "direction": "input",
                                },
                            ],
                            "output": [
                                {
                                    "generic_name": "out",
                                    "value": None,
                                    "type": "xyzw3",
                                    "direction": "output",
                                }
                            ],
                        },
                        "connections_dict": {
                            "connection_0": {
                                "input": {
                                    "node_name": "image_normal",
                                    "node_path": f"{node.path()}/image_normal",
                                    "node_type": "mtlximage",
                                    "node_index": 0,
                                    "parm_name": "out",
                                    "data_type": "color",
                                },
                                "output": {
                                    "node_name": "mtlxnormalmap1",
                                    "node_path": f"{node.path()}/mtlxnormalmap1",
                                    "node_type": "mtlxnormalmap::2.0",
                                    "node_index": 0,
                                    "parm_name": "in",
                                    "data_type": "vector",
                                },
                            }
                        },
                        "children_list": [],
                    }
                ],
            }
        )

    if node.parm("dispTex_enable").eval():
        entry[f"{node.path()}/displacement_output"]["children_list"][0]["children_list"].append(
            {
                "node_name": "image_disp",
                "node_path": f"{node.path()}/image_disp",
                "node_type": "mtlximage",
                "node_position": [-3, -10],
                "node_parms": {
                    "input": [
                        {
                            "generic_name": "file",
                            "value": node.parm("dispTex_texture").eval(),
                            "type": "string1",
                            "direction": "input",
                        },
                    ],
                    "output": [],
                },
                "connections_dict": {
                    "connection_0": {
                        "input": {
                            "node_name": "image_disp",
                            "node_path": f"{node.path()}/image_disp",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out",
                            "data_type": "float",
                        },
                        "output": {
                            "node_name": "mtlxdisplacement",
                            "node_path": f"{node.path()}/mtlxdisplacement",
                            "node_type": "mtlxdisplacement",
                            "node_index": 0,
                            "parm_name": "displacement",
                            "data_type": "float",
                        },
                    }
                },
                "children_list": [],
            }
        )

    return entry

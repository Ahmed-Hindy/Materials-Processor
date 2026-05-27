import logging

logger = logging.getLogger(__name__)

try:
    import hou
except:
    # temp to make the module work with substance painter
    logger.warning("materialProcessor running outside of Houdini!")
    hou = None

from materials_processor.houdini.output_detector import detect_output_nodes

class NodeTraverser:
    """
    Class for traversing Houdini nodes to extract their connections and output nodes.
    """

    def __init__(self, material_node, material_type):
        """
        Initialize the NodeTraverser with the specified material type.

        Args:
            material_type (str): The type of material (e.g., 'arnold', 'mtlx', 'principledshader').
        """
        self.material_node = material_node
        self.material_type = material_type
        self.output_nodes = {}

    def create_output_dict(self, material_node, material_type: str):
        """
        Detect output nodes in the node tree based on the material type.

        Args:
            material_node (hou.VopNode): The Houdini material node.
            material_type (str): The type of material (e.g., 'arnold', 'mtlx', 'principledshader').

        Returns:
            Dict: A dictionary of detected output nodes.

        Examples:
            >>> output_dict = self.create_output_dict(material_node=hou.node('/mat/arnold_materialbuilder_basic'), material_type='arnold')
            >>> print(output_dict)
            {'surface':
                {'node_name': 'OUT_material',
                 'node_path': '/mat/arnold_materialbuilder_basic/OUT_material',
                 'connected_node_name': 'standard_surface',
                 'connected_node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
                 'connected_input_index': 0,
                 'connected_input_name': 'surface',
                 'connected_output_name': 'shader',
                 'generic_type': 'GENERIC::output_surface'
                 }
            }
        """
        logger.info("detect_output_nodes START for %s", material_node.path())
        return detect_output_nodes(material_node, material_type)


    @staticmethod
    def _detect_node_connections(node, parent_node):
        """
        Detect and extract the output connections of a given node, including input and output connections.

        Args:
            node (hou.Node): The Houdini node to analyze connections for.

        Returns:
            Dict[str, Dict[str, Dict[str, Any]]]: A dictionary containing the connection information with the following structure:
                {
                    "connection_<index>": {
                        "input": {
                            "node_name": str,  # Name of the input node
                            "node_path": str,  # Path of the input path
                            "node_index": int, # Index of the input connection
                            "parm_name": str   # Name of the input parameter
                        },
                        "output": {
                            "node_name": str,  # Name of the output node
                            "node_path": str,  # Path of the input path
                            "node_index": int, # Index of the output connection
                            "parm_name": str   # Name of the output parameter
                        }
                    }
                }
        """
        # print(f"DEBUG: parent_node.name(): {parent_node.name() if parent_node else 'None'},   node.name(): {node.name()}")
        # e.g. prints:
        # DEBUG: parent_node.name(): None,                  node.name(): 'surface_output'
        # DEBUG: parent_node.name(): surface_output,        node.name(): 'mtlxstandard_surface'
        # DEBUG: parent_node.name(): mtlxstandard_surface,  node.name(): 'image_diffuse'
        # DEBUG: parent_node.name(): mtlxstandard_surface,  node.name(): 'image_roughness'
        # DEBUG: parent_node.name(): None,                  node.name(): 'displacement_output'
        # DEBUG: parent_node.name(): displacement_output,   node.name(): 'mtlxdisplacement1'
        # DEBUG: parent_node.name(): mtlxdisplacement1,     node.name(): 'image_disp'


        connections_dict = {}
        for i, connection in enumerate(node.outputConnections()):
            # We only want to get the output connections of the parent node. We don't want all connections to all nodes
            if connection.outputNode().name() != parent_node.name():
                continue

            # print(f"DEBUG: -------------[{i}] input: '{input_conn.inputNode().name()}' index: '{input_conn.inputIndex()}', parm_name: '{input_conn.inputName()}'")
            # print(f"DEBUG: -------------[{i}] output: '{input_conn.outputNode().name()}' index: '{input_conn.outputIndex()}', parm_name: '{input_conn.outputName()}'")
            connections_dict.update({f"connection_{i}":
                {
                    "input": {
                        "node_name": connection.inputNode().name(),
                        "node_path": connection.inputNode().path(),
                        "node_type": connection.inputNode().type().name(),
                        "node_index": connection.outputIndex(),
                        "parm_name": connection.inputName(),
                        "data_type": connection.inputDataType(),
                    },
                    "output": {
                        "node_name": connection.outputNode().name(),
                        "node_path": connection.outputNode().path(),
                        "node_type": connection.outputNode().type().name(),
                        "node_index": connection.inputIndex(),
                        "parm_name": connection.outputName(),
                        "data_type": connection.outputDataType(),
                    }
                }
            })

        return connections_dict

    @staticmethod
    def _convert_parms_to_dict(node):
        """
        Convert all input‐tuple parms and actual output‐connections on a Houdini VOP node
        into two lists of {generic_name, value, type, direction}.
        """

        def strip_prefix(s: str, prefix: str) -> str:
            return s[len(prefix):] if s.startswith(prefix) else s

        def compute_datatype_and_components(tpl) -> tuple[str,int]:
            # e.g. tpl.dataType().name() -> "parmData.Float"
            raw_dt = tpl.dataType().name()
            dt = strip_prefix(raw_dt, "parmData.").lower()

            # if it’s a single‐float that really is a color/vector, pick its namingScheme
            if dt == "float":
                raw_scheme = tpl.namingScheme().name()  # e.g. "parmNamingScheme.RGBA"
                scheme = strip_prefix(raw_scheme, "parmNamingScheme.").lower().rstrip("1")
                if scheme in {"rgb","rgba","xyzw"}:
                    dt = scheme

            return dt, tpl.numComponents()

        parms = {"input": [], "output": []}

        # ——— Inputs ———
        for p in node.parmTuples():
            tpl = p.parmTemplate()
            # skip UI folder/label/separator types
            if tpl.type() in {
                hou.parmTemplateType.FolderSet,
                hou.parmTemplateType.Folder,
                hou.parmTemplateType.Label,
                hou.parmTemplateType.Separator
            }:
                continue
            val = p.eval()
            if val is None:
                continue

            dt, comps = compute_datatype_and_components(tpl)
            parms["input"].append({
                "generic_name": p.name(),
                "value": val,
                "type": f"{dt}{comps}",
                "direction": "input",
            })

        # ——— Outputs via actual connections ———
        for conn in node.outputConnections():
            in_name   = conn.inputName()
            out_node  = conn.outputNode()
            out_name  = conn.outputName()
            if not out_node.parmTuple(out_name):
                print(f"WARNING: Parm Not found {out_node.path()}/{out_name}, skipping.")
                continue

            tpl       = out_node.parmTuple(out_name).parmTemplate()
            dt, comps = compute_datatype_and_components(tpl)
            parms["output"].append({
                "generic_name": in_name,
                "value": None,
                "type": f"{dt}{comps}",
                "direction": "output",
            })
        return parms


    def _traverse_recursively_node_tree(self, node, parent_node=None):
        """
        Recursively traverse the node tree and return a dictionary of node connections with additional metadata,
        separating the input index and input node path as key-value pairs.

        Args:
            node (hou.Node): The current Houdini node.
            parent_node (hou.Node), optional): The traversal path.

        Returns:
            Dict[str, Dict]: A dictionary representing the node tree with additional metadata.
        """
        # get a dict with all input and output connections related to the node
        connections_dict = self._detect_node_connections(node, parent_node)

        # Initialize the node's dictionary with metadata
        node_dict = {
            'node_name': node.name(),
            'node_path': node.path(),
            'node_type': node.type().name(),
            'node_position': (node.position()[0], node.position()[1]),
            'node_parms': self._convert_parms_to_dict(node),
            'connections_dict': connections_dict,
            'children_list': []
        }

        if not node.inputs():
            return {node.path(): node_dict}

        for input_node in node.inputs():
            if not input_node:
                continue

            # Recursively get child nodes
            input_node_dict = self._traverse_recursively_node_tree(input_node, node)

            node_dict['children_list'].append(
                input_node_dict[input_node.path()]
            )

        return {node.path(): node_dict}


    def _build_principled_entry(self, node):
        """

        """
        # grab parameters + direct connections
        parms = self._convert_parms_to_dict(node)

        entry = {
            f"{node.path()}/surface_output": {
                "node_name": "surface_output",
                "node_path": f"{node.path()}/surface_output",
                "node_type": "subnetconnector",
                "node_position": [0,0],
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
                                    "parm_name": "out"
                                },
                                "output": {
                                    "node_name": "surface_output",
                                    "node_path": f"{node.path()}/surface_output",
                                    "node_type": "subnetconnector",
                                    "node_index": 0,
                                    "parm_name": "suboutput"
                                },
                            }
                        },
                        "children_list": [],
                    },
                ]
            },
            f"{node.path()}/displacement_output": {
                "node_name": "displacement_output",
                "node_path": f"{node.path()}/displacement_output",
                "node_type": "subnetconnector",
                "node_position": [-4,1],
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
                                    "data_type": "displacement"
                                },
                                "output": {
                                    "node_name": "displacement_output",
                                    "node_path": f"{node.path()}l/displacement_output",
                                    "node_type": "subnetconnector",
                                    "node_index": 0,
                                    "parm_name": "suboutput",
                                    "data_type": "displacement"
                                }
                            }
                        },
                        "children_list": []
                    }
                ]
            }
        }

        if node.parm('basecolor_useTexture').eval():
            entry[f"{node.path()}/surface_output"]['children_list'][0]['children_list'].append({
                "node_name": "image_diffuse",
                "node_path": f"{node.path()}/image_diffuse",
                "node_type": "mtlximage",
                "node_position": [-6, 0],
                'node_parms': {
                    'input': [
                        {'generic_name': 'file',
                         'value': node.parm('basecolor_texture').eval(),
                         "type": "string1",
                         "direction": "input"},
                    ],
                    'output': [],
                },
                'connections_dict': {
                    "connection_0": {
                        "input": {
                            "node_name": "image_diffuse",
                            "node_path": f"{node.path()}/image_diffuse",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out"
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 1,
                            "parm_name": "base_color"
                        }
                    },
                },

            })

        if node.parm('metallic_useTexture').eval():
            entry[f"{node.path()}/surface_output"]['children_list'][0]['children_list'].append({
                "node_name": "image_metalness",
                "node_path": f"{node.path()}/image_metalness",
                "node_type": "mtlximage",
                "node_position": [-6, -3],
                'node_parms': {
                    'input': [
                        {'generic_name': 'file',
                         'value': node.parm('metallic_texture').eval(),
                         "type": "string1",
                         "direction": "input"},
                    ],
                    'output': [],
                },
                'connections_dict': {
                    "connection_0": {
                        "input": {
                            "node_name": "image_metalness",
                            "node_path": f"{node.path()}/image_metalness",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out"
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 3,
                            "parm_name": "metalness"
                        }
                    },
                },

            })

        if node.parm('rough_useTexture').eval():
            entry[f"{node.path()}/surface_output"]['children_list'][0]['children_list'].append({
                "node_name": "image_roughness",
                "node_path": f"{node.path()}/image_roughness",
                "node_type": "mtlximage",
                "node_position": [-6, -6],
                'node_parms': {
                    'input': [
                        {'generic_name': 'file',
                         'value': node.parm('rough_texture').eval(),
                         "type": "string1",
                         "direction": "input"},
                    ],
                    'output': [],
                },
                'connections_dict': {
                    "connection_0": {
                        "input": {
                            "node_name": "image_roughness",
                            "node_path": f"{node.path()}/image_roughness",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out"
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 6,
                            "parm_name": "specular_roughness"
                        }
                    },
                },

            })

        if node.parm('sss_useTexture').eval():
            entry[f"{node.path()}/surface_output"]['children_list'][0]['children_list'].append({
                "node_name": "image_sss",
                "node_path": f"{node.path()}/image_sss",
                "node_type": "mtlximage",
                "node_position": [-6, -9],
                'node_parms': {
                    'input': [
                        {'generic_name': 'file',
                         'value': node.parm('sss_texture').eval(),
                         "type": "string1",
                         "direction": "input"},
                    ],
                    'output': [],
                },
                'connections_dict': {
                    "connection_0": {
                        "input": {
                            "node_name": "image_sss",
                            "node_path": f"{node.path()}/image_sss",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out"
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 30,
                            "parm_name": "subsurface_color"
                        }
                    },
                },

            })

        if node.parm('baseBumpAndNormal_enable').eval() and node.parm('baseBumpAndNormal_type').eval() == "normal":
            entry[f"{node.path()}/surface_output"]['children_list'][0]['children_list'].append({
                "node_name": "mtlxnormalmap1",
                "node_path": f"{node.path()}/mtlxnormalmap1",
                "node_type": "mtlxnormalmap::2.0",
                "node_position": [-6, -12],
                'node_parms': {
                    'input': [],
                    'output': [],
                },
                'connections_dict': {
                    "connection_0": {
                        "input": {
                            "node_name": "mtlxnormalmap1",
                            "node_path": f"{node.path()}/mtlxnormalmap1",
                            "node_type": "mtlxnormalmap::2.0",
                            "node_index": 0,
                            "parm_name": "out"
                        },
                        "output": {
                            "node_name": "mtlxstandard_surface",
                            "node_path": f"{node.path()}/mtlxstandard_surface",
                            "node_type": "mtlxstandard_surface",
                            "node_index": 40,
                            "parm_name": "normal"
                        }
                    },
                },
                        "children_list": [
                            {
                                "node_name": "image_normal",
                                "node_path": f"{node.path()}/image_normal",
                                "node_type": "mtlximage",
                                "node_position": [-9, -7],
                                "node_parms": {
                                    'input': [
                                        {'generic_name': 'file',
                                         'value': node.parm('baseNormal_texture').eval(),
                                         "type": "string1",
                                         "direction": "input"},
                                    ],
                                    "output": [
                                        {
                                            "generic_name": "out",
                                            "value": None,
                                            "type": "xyzw3",
                                            "direction": "output"}
                                    ]
                                },
                                "connections_dict": {
                                    "connection_0": {
                                        "input": {
                                            "node_name": "image_normal",
                                            "node_path": f"{node.path()}/image_normal",
                                            "node_type": "mtlximage",
                                            "node_index": 0,
                                            "parm_name": "out",
                                            "data_type": "color"
                                        },
                                        "output": {
                                            "node_name": "mtlxnormalmap1",
                                            "node_path": f"{node.path()}/mtlxnormalmap1",
                                            "node_type": "mtlxnormalmap::2.0",
                                            "node_index": 0,
                                            "parm_name": "in",
                                            "data_type": "vector"
                                        }
                                    }
                                },
                                "children_list": []
                            }
                        ]

            })

        if node.parm('dispTex_enable').eval():
            entry[f"{node.path()}/displacement_output"]['children_list'][0]['children_list'].append({
                "node_name": "image_disp",
                "node_path": f"{node.path()}/image_disp",
                "node_type": "mtlximage",
                "node_position": [-3, -10],
                'node_parms': {
                    'input': [
                        {'generic_name': 'file',
                         'value': node.parm('dispTex_texture').eval(),
                         "type": "string1",
                         "direction": "input"},
                    ],
                    'output': [],
                },
                "connections_dict": {
                    "connection_0": {
                        "input": {
                            "node_name": "image_disp",
                            "node_path": f"{node.path()}/image_disp",
                            "node_type": "mtlximage",
                            "node_index": 0,
                            "parm_name": "out",
                            "data_type": "float"
                        },
                        "output": {
                            "node_name": "mtlxdisplacement",
                            "node_path": f"{node.path()}/mtlxdisplacement",
                            "node_type": "mtlxdisplacement",
                            "node_index": 0,
                            "parm_name": "displacement",
                            "data_type": "float"
                        }
                    }
                },
                "children_list": []

            })


        return entry


    def run(self):
        """
        Traverse the children nodes of a parent node to extract the node tree and detect output nodes.
        For PrincipledShader, build a one-node tree instead of recursing.
        Returns:
            (Dict, Dict): 2 Dictionaries, First for the node dict and Second for the Output Dict.
        """
        # first, get an output_nodes_dict
        output_tree = self.create_output_dict(self.material_node, self.material_type)

        # for principled, short-circuit to produce a one-node tree + identical output map
        if self.material_type == 'principledshader':
            node_tree = self._build_principled_entry(self.material_node)
        else:
            node_tree = {}
            for output_type, output_dict in output_tree.items():
                node_tree.update(self._traverse_recursively_node_tree(hou.node(output_dict['node_path'])))

        return node_tree, output_tree




def get_material_type(materialbuilder_node):
    """
    Args:
        materialbuilder_node (hou.VopNode): input material shading network, e.g., arnold materialbuilder
    Returns:
        (str): material type.
    """
    material_type = None

    materialbuilder_type = materialbuilder_node.type().name()
    if materialbuilder_type == 'arnold_materialbuilder':
        material_type = 'arnold'
    elif materialbuilder_type == 'subnet':
        for child_node in materialbuilder_node.children():
            if 'mtlx' in child_node.type().name():
                material_type = 'mtlx'
                break
    elif materialbuilder_type == 'redshift_vopnet':
        material_type = 'redshift_vopnet'
    elif materialbuilder_type == 'rs_usd_material_builder':
        material_type = 'rs_usd_material_builder'

    elif materialbuilder_type == 'principledshader::2.0':
        material_type = 'principledshader'

    return material_type




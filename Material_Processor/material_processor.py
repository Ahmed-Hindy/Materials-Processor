"""
copyright Ahmed Hindy. Please mention the original author if you used any part of this code
This module processes material nodes in Houdini, extracting and converting shader parameters and textures.
"""
import traceback
import pprint
from typing import Dict, List
from importlib import reload, resources


from Material_Processor import material_classes, utils_io
from Material_Processor.material_classes import NodeInfo, NodeParameter
from Material_Processor import material_standardizer

reload(material_classes)
reload(utils_io)
reload(material_standardizer)


try:
    import hou
except:
    # temp to make the module work with substance painter
    print("materialProcessor running outside of Houdini!")
    hou = None




###################################### CONSTANTS ######################################


"""
Conversion_map is a dict of {'from_node_type': 'to_node_type'}
"""
GENERIC_NODE_TYPES_TO_REGULAR = {
            'arnold': {
                'GENERIC::standard_surface': 'arnold::standard_surface',
                'GENERIC::image': 'arnold::image',
                'GENERIC::color_correct': 'arnold::color_correct',
                'GENERIC::range': 'arnold::range',
                'GENERIC::curvature': 'arnold::curvature',
                'GENERIC::mix_rgba': 'arnold::mix_rgba',
                'GENERIC::mix_layer': 'arnold::mix_layer',
                'GENERIC::layer_rgba': 'arnold::layer_rgba',
                'GENERIC::displacement': 'null',
                'GENERIC::null': 'null',
            },
            'mtlx': {
                'GENERIC::standard_surface': 'mtlxstandard_surface',
                'GENERIC::image': 'mtlximage',
                'GENERIC::color_correct': 'mtlxcolorcorrect',
                'GENERIC::range': 'mtlxrange',
                # 'GENERIC::curvature': 'mtlxcurvature',  # not supported yet
                'GENERIC::mix_rgba': 'mtlxmix',
                'GENERIC::mix_layer': 'mtlxmix',
                'GENERIC::displacement': 'mtlxdisplacement',
                'GENERIC::null': 'null',
            },
            'redshift_vopnet': {
                'GENERIC::standard_surface': 'redshift::StandardMaterial',
                'GENERIC::image': 'redshift::TextureSampler',
                'GENERIC::color_correct': 'redshift::RSColorCorrection',
                'GENERIC::range': 'redshift::RSColorRange',
                'GENERIC::curvature': 'redshift::Curvature',
                'GENERIC::mix_rgba': 'redshift::RSColorMix',
                'GENERIC::mix_layer': 'redshift::RSColorLayer',
                'GENERIC::displacement': 'redshift::Displacement',
                'GENERIC::null': 'null',
            },
            'rs_usd_material_builder': {
                'GENERIC::standard_surface': 'redshift::StandardMaterial',
                'GENERIC::image': 'redshift::TextureSampler',
                'GENERIC::color_correct': 'redshift::RSColorCorrection',
                'GENERIC::range': 'redshift::RSColorRange',
                'GENERIC::curvature': 'redshift::Curvature',
                'GENERIC::mix_rgba': 'redshift::RSColorMix',
                'GENERIC::mix_layer': 'redshift::RSColorLayer',
                'GENERIC::displacement': 'redshift::Displacement',
                'GENERIC::null': 'null',
            },
        }

OUTPUT_CONNECTIONS_INDEX_MAP = {
    'arnold': {
        'GENERIC::output_surface': 0,
        'GENERIC::output_displacement': 1
    },
    'mtlx': {
        'GENERIC::output_surface': 0,
        'GENERIC::output_displacement': 0
    }
}

##########################################################################################



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


    @staticmethod
    def _detect_arnold_output_nodes(material_node):
        """
        Detect Arnold output nodes in the node tree.

        Args:
            material_node (hou.Node): The parent Houdini node.

        Returns:
            Dict: A dictionary of detected Arnold output nodes.
        """
        arnold_output = None
        for child in material_node.children():
            if child.type().name() == 'arnold_material':
                arnold_output = child
                break
        if not arnold_output:
            raise Exception(f"No Output Node detected for Arnold Material")

        output_nodes = {}
        connections = arnold_output.inputConnections()
        for connection in connections:
            connected_input = connection.inputNode()
            connected_input_index = connection.outputIndex()
            connected_input_name = connection.outputName()
            connected_output_index = connection.inputIndex()
            connected_output_name = connection.inputName()
            if connected_output_index == 0:
                output_nodes['surface'] = {
                    'node_name': arnold_output.name(),
                    'node_path': arnold_output.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_input_index': connected_input_index,
                    'connected_input_name': connected_input_name,
                    'connected_output_name': connected_output_name,
                    'generic_type': 'GENERIC::output_surface'
                }
            elif connected_output_index == 1:
                output_nodes['displacement'] = {
                    'node_name': arnold_output.name(),
                    'node_path': arnold_output.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_input_index': connected_input_index,
                    'connected_input_name': connected_input_name,
                    'connected_output_name': connected_output_name,
                    'generic_type': 'GENERIC::output_displacement'
                }
        return output_nodes

    @staticmethod
    def _detect_mtlx_output_nodes(material_node):
        """
        Detect MaterialX output nodes in the node tree.

        Args:
            material_node (hou.Node): The parent Houdini node.

        Returns:
            Dict: A dictionary of detected MaterialX output nodes.
        """
        output_nodes = {}
        output_nodes_list = [child for child in material_node.children() if child.type().name() == 'subnetconnector']

        for output_node in output_nodes_list:
            connections = output_node.inputConnections()
            for connection in connections:
                connected_input = connection.inputNode()
                connected_input_index = connection.outputIndex()
                connected_input_name = connection.outputName()
                connected_output_name = connection.inputName()
                connected_output_index = connection.inputIndex()
                output_type = output_node.parm('parmname').eval()
                if output_type not in ['surface', 'displacement']:
                    print(f"WARNING: Unknown MaterialX output type '{output_node.name()}/{output_type}' detected, skipping.")
                    continue

                output_nodes[output_type] = {
                    'node_name': output_node.name(),
                    'node_path': output_node.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_input_index': connected_input_index,
                    'connected_input_name': connected_input_name,
                    'connected_output_name': connected_output_name,
                }
        return output_nodes

    @staticmethod
    def _detect_redshift_vopnet_output_nodes(material_node):
        """
        Detect redshift_vopnet output nodes in the node tree.

        Args:
            material_node (hou.Node): The parent Houdini node.

        Returns:
            Dict: A dictionary of detected redshift_vopnet output nodes.
        """
        redshift_output = None
        for child in material_node.children():
            if child.type().name() == 'redshift_material':
                redshift_output = child
                break
        if not redshift_output:
            raise Exception(f"No Output Node detected for 'redshift_vopnet' Material")

        output_nodes = {}
        connections = redshift_output.inputConnections()
        for connection in connections:
            connected_input = connection.inputNode()
            connected_input_index = connection.outputIndex()
            connected_input_name = connection.outputName()
            connected_output_index = connection.inputIndex()
            connected_output_name = connection.inputName()
            if connected_output_index == 0:
                output_nodes['surface'] = {
                    'node_name': redshift_output.name(),
                    'node_path': redshift_output.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_input_index': connected_input_index,
                    'connected_input_name': connected_input_name,
                    'connected_output_name': connected_output_name,
                    'generic_type': 'GENERIC::output_surface'
                }
            elif connected_output_index == 1:
                output_nodes['displacement'] = {
                    'node_name': redshift_output.name(),
                    'node_path': redshift_output.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_input_index': connected_input_index,
                    'connected_input_name': connected_input_name,
                    'connected_output_name': connected_output_name,
                    'generic_type': 'GENERIC::output_displacement'
                }
        return output_nodes

    @staticmethod
    def _detect_RsUsdMaterialbuilder_output_nodes(material_node):
        """
        Detect rs usd materialbuilder output nodes in the node tree.

        Args:
            material_node (hou.Node): The parent Houdini node.

        Returns:
            Dict: A dictionary of detected redshift_vopnet output nodes.
        """
        redshift_output = None
        for child in material_node.children():
            if child.type().name() == 'suboutput':
                redshift_output = child
                break
        if not redshift_output:
            raise Exception(f"No Output Node detected for 'rs usd materialbuilder' Material")

        output_nodes = {}
        connections = redshift_output.inputConnections()
        for connection in connections:
            connected_input = connection.inputNode()
            connected_input_index = connection.outputIndex()
            connected_input_name = connection.outputName()
            connected_output_index = connection.inputIndex()
            connected_output_name = connection.inputName()
            if connected_output_index == 0:
                output_nodes['surface'] = {
                    'node_name': redshift_output.name(),
                    'node_path': redshift_output.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_input_index': connected_input_index,
                    'connected_input_name': connected_input_name,
                    'connected_output_name': connected_output_name,
                    'generic_type': 'GENERIC::output_surface'
                }
            elif connected_output_index == 1:
                output_nodes['displacement'] = {
                    'node_name': redshift_output.name(),
                    'node_path': redshift_output.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_input_index': connected_input_index,
                    'connected_input_name': connected_input_name,
                    'connected_output_name': connected_output_name,
                    'generic_type': 'GENERIC::output_displacement'
                }
        return output_nodes

    @staticmethod
    def _detect_principled_output_nodes(material_node):
        """
        Detect Principled Shader output nodes in the node tree.

        Returns:
            Dict: A dictionary with the single 'surface' output connection,
                  mirroring Arnold's structure so downstream code works unchanged.

        """
        return {
            "surface": {
                "node_name": "OUT_material",
                "node_path": f"{material_node.path()}/OUT_material",
                "connected_node_name": "standard_surface",
                "connected_node_path": f"{material_node.path()}/standard_surface",
                "connected_input_index": 0,
                "generic_type": "GENERIC::output_surface"
            }
        }

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
        print(f"detect_output_nodes START for {material_node.path()}")
        if material_type == 'arnold':
            output_nodes = self._detect_arnold_output_nodes(material_node)
        elif material_type == 'mtlx':
            output_nodes = self._detect_mtlx_output_nodes(material_node)
        elif material_type == 'redshift_vopnet':
            output_nodes = self._detect_redshift_vopnet_output_nodes(material_node)
        elif material_type == 'rs_usd_material_builder':
            output_nodes = self._detect_RsUsdMaterialbuilder_output_nodes(material_node)
        elif material_type == 'principledshader':
            output_nodes = self._detect_principled_output_nodes(material_node)
        else:
            raise KeyError(f"Unsupported renderer: {material_type=}")
        return output_nodes


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
                        "node_index": connection.outputIndex(),
                        "parm_name": connection.inputName(),
                    },
                    "output": {
                        "node_name": connection.outputNode().name(),
                        "node_path": connection.outputNode().path(),
                        "node_index": connection.inputIndex(),
                        "parm_name": connection.outputName(),
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
        Recursively walk all upstream connections into `node` and emit
        the same fields you use for Arnold.
        """
        # grab parameters + direct connections
        parms = self._convert_parms_to_dict(node)

        entry = {
            f"{node.path()}/OUT_material": {
                "node_name": "OUT_material",
                "node_path": f"{node.path()}/OUT_material",
                "node_type": "arnold_material",
                "node_position": (0,0),
                "node_parms": [],
                "connections_dict": {},
                "children_list": [
                    {
                        "node_name": "standard_surface",
                        "node_path": f"{node.path()}/standard_surface",
                        "node_type": "arnold::standard_surface",
                        "node_position": (-3, 0),
                        "node_parms": [],
                        "connections_dict": {
                            "connection_0": {
                                "input": {
                                    "node_name": "standard_surface",
                                    "node_path": "/mat/arnold_materialbuilder_basic/standard_surface",
                                    "node_index": 0,
                                    "parm_name": "shader"
                                },
                                "output": {
                                    "node_name": "OUT_material",
                                    "node_path": "/mat/arnold_materialbuilder_basic/OUT_material",
                                    "node_index": 0,
                                    "parm_name": "surface"
                                },
                            }
                        },
                        "children_list": [],
                    },
                ]
            }
        }

        if node.parm('basecolor_useTexture').eval():
            entry[f"{node.path()}/OUT_material"]['children_list'][0]['children_list'].append({
                "node_name": "image_diffuse",
                "node_path": f"{node.path()}/image_diffuse",
                "node_type": "arnold::image",
                "node_position": (-6, 0),
                'node_parms': {
                    'input': [
                        {'name': 'filename', 'value': node.parm('basecolor_texture').eval()},
                    ],
                },
                'connections_dict': {
                    "connection_0": {
                        "input": {
                            "node_name": "image_diffuse",
                            "node_path": f"{node.path()}/image_diffuse",
                            "node_index": 0,
                            "parm_name": "rgba"
                        },
                        "output": {
                            "node_name": "standard_surface",
                            "node_path": f"{node.path()}/standard_surface",
                            "node_index": 1,
                            "parm_name": "base_color"
                        }
                    },
                },

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


class NodeRecreator:
    """
    Class for recreating Houdini nodes in a target renderer context.
    """

    def __init__(self, nodeinfo_list, output_connections, target_context,
                 target_renderer='arnold'):
        """
        Initialize the NodeRecreator with the provided material data and target context.

        Args:
            nodeinfo_list (list[NodeInfo]): The standardized material data.
            output_connections (Dict): The output connections mapping.
            target_context (hou.Node): The target Houdini context node.
            target_renderer (str, optional): The target renderer (default is 'arnold').
        """
        self.nodeinfo_list = nodeinfo_list
        self.orig_output_connections = output_connections
        self.target_context = target_context
        self.target_renderer = target_renderer
        self.old_new_node_map = {}  # e.g., {old_node_path:str :
        #                                       'node_name': node.name(),
        #                                       'node_path': node.path()
        #                                   }
        self.reused_nodes = {}
        self.material_node = None
        self.new_output_connections = {}    # e.g., {'GENERIC::output_surface':{
        #                                                  'node': <hou.VopNode of type arnold_material at /mat/arnold_materialbuilder1/OUT_material>,
        #                                                  'node_name': 'OUT_material',
        #                                                  'node_path': '/mat/arnold_materialbuilder1/OUT_material',
        #                                                  },
        #                                               'GENERIC::output_displacement': {
        #                                                   'node': <hou.VopNode of type arnold_material at /mat/arnold_materialbuilder1/OUT_material>,
        #                                                   'node_name': 'OUT_material',
        #                                                   'node_path': '/mat/arnold_materialbuilder1/OUT_material',
        #                                                   }
        #                                               }

        self.run()


    @staticmethod
    def create_mtlx_init_shader(matnet=None):
        """
        Create an initial MaterialX shader in the specified network.

        Args:
            matnet (hou.Node, optional): The Houdini network node.

        Returns:
            Tuple[hou.Node, Dict]: The created MaterialX shader node and output nodes.
        """
        import voptoolutils
        UTILITY_NODES = 'parameter constant collect null genericshader'
        SUBNET_NODES = 'subnet subnetconnector suboutput subinput'
        MTLX_TAB_MASK = f'MaterialX {UTILITY_NODES} {SUBNET_NODES}'
        name = 'mtlxmaterial'
        folder_label = 'MaterialX Builder'
        render_context = 'mtlx'

        if not matnet:
            matnet = hou.node('/mat')

        subnet_node = matnet.createNode('subnet', name)
        subnet_node = voptoolutils._setupMtlXBuilderSubnet(subnet_node=subnet_node, name=name, mask=MTLX_TAB_MASK,
                                                           folder_label=folder_label, render_context=render_context)

        subnet_node.node('mtlxstandard_surface').destroy()

        output_nodes = {
            'GENERIC::output_surface': {'node': subnet_node.node('surface_output'),
                                        'node_name': subnet_node.node('surface_output').name(),
                                        'node_path': subnet_node.node('surface_output').path(),
                                        },
            'GENERIC::output_displacement': {'node': subnet_node.node('displacement_output'),
                                             'node_name': subnet_node.node('displacement_output').name(),
                                             'node_path': subnet_node.node('displacement_output').path(),
                                             }
        }
        return subnet_node, output_nodes


    def create_mtlx_vec3_split_node(self, src_node, dest_node, src_out_parm_name, dest_in_index):
        """
        Creates a vec3 split node to 3 floats between 2 nodes and connects them.
        This method is created for arnold images that have their out individual channels:r,g, or b connected to a node.
        Args:
            src_node: (hou.Node) e.g., a 'mtlximage' node
            src_out_parm_name: (str) parm name on output_node e.g., "r"
            dest_node: (hou.node) the 2nd node which will connect to the first node. e.g., mtlxstandardsurface
            dest_in_index: (int) input index on node
        Returns:
            bool: True if successful, False otherwise
        """
        if src_out_parm_name not in ['r', 'g', 'b']:
            print(f"WARNING: mtlx separate3c node currently only supports splitting of 'r','g','b' channels, "
                  f"but instead it got a '{src_out_parm_name}'")
            return False, None
        if dest_in_index is None:
            print(f"WARNING: dest_in_index is None '{dest_in_index}', but it should be an integer, src_node: '{src_node.name()}'")
            return False, None

        try:
            # create a vec3 split node
            vec3_split_node_name = f"{src_node.name()}_split_vec3"
            vec3_split_node = self.material_node.node(vec3_split_node_name)
            if not vec3_split_node:
                vec3_split_node = self.material_node.createNode('mtlxseparate3c', f"{src_node.name()}_split_vec3")

            # get which channel from the split node to connect to the output node
            out_index = vec3_split_node.outputIndex(f"out{src_out_parm_name}")
            if out_index == -1:
                out_index = vec3_split_node.outputIndex(f"out{src_out_parm_name}")

            vec3_split_node.setInput(0, src_node)
            dest_node.setInput(dest_in_index, vec3_split_node, out_index)
            print(f"INFO: created split node for '{src_node.name()}' to '{dest_node.name()}' for '{src_out_parm_name}' ")
            return True, vec3_split_node

        except Exception as e:
            print(f"ERROR: create_mtlx_vec3_split_node, {dest_in_index=}, {vec3_split_node=}, {out_index=}, error: {e}")
            return False, None

    @staticmethod
    def create_arnold_init_shader(matnet=None):
        """
        Create an initial Arnold shader in the specified network.

        Args:
            matnet (hou.Node, optional): The Houdini network node.

        Returns:
            Tuple[hou.Node, Dict]: The created Arnold shader node and output nodes.
        """
        if not matnet:
            matnet = hou.node('/mat')

        node_material_builder = matnet.createNode('arnold_materialbuilder')
        output_nodes = {
            'GENERIC::output_surface': {'node': node_material_builder.node('OUT_material'),
                                        'node_name': node_material_builder.node('OUT_material').name(),
                                        'node_path': node_material_builder.node('OUT_material').path(),
                                        },
            'GENERIC::output_displacement': {'node': node_material_builder.node('OUT_material'),
                                             'node_name': node_material_builder.node('OUT_material').name(),
                                             'node_path': node_material_builder.node('OUT_material').path(),
                                             }
        }
        return node_material_builder, output_nodes

    @staticmethod
    def create_principledshader_init_shader(matnet=None):
        """
        Create an initial principledshader shader in the specified network.

        Args:
            matnet (hou.Node, optional): The Houdini Material Network.

        Returns:
            Tuple[hou.Node, Dict]: The created Arnold shader node and output nodes.
        """
        if not matnet:
            matnet = hou.node('/mat')

        node_material_builder = matnet.createNode('principledshader::2.0')
        output_nodes = {
            'GENERIC::output_surface': {'node': None,
                                        'node_name': None,
                                        'node_path': None,
                                        },
            'GENERIC::output_displacement': {'node': None,
                                             'node_name': None,
                                             'node_path': None,
                                             }
        }
        return node_material_builder, output_nodes

    @staticmethod
    def create_rs_usd_material_builder_init_shader(matnet=None):
        """
        Create an initial rs_usd_material_builder shader in the specified network.

        Args:
            matnet (hou.Node, optional): The Houdini network node.

        Returns:
            Tuple[hou.Node, Dict]: The created rs_usd_material_builder shader node and output nodes.
        """
        if not matnet:
            matnet = hou.node('/mat')

        subnet_node = matnet.createNode('rs_usd_material_builder')

        subnet_node.node('StandardMaterial1').destroy()

        output_nodes = {
            'GENERIC::output_surface': {'node': subnet_node.node('surface_output'),
                                        'node_name': subnet_node.node('surface_output').name(),
                                        'node_path': subnet_node.node('surface_output').path(),
                                        },
            'GENERIC::output_displacement': {'node': subnet_node.node('displacement_output'),
                                             'node_name': subnet_node.node('displacement_output').name(),
                                             'node_path': subnet_node.node('displacement_output').path(),
                                             }
        }
        return subnet_node, output_nodes

    def create_init_shader(self, target_renderer):
        if target_renderer == 'mtlx':
            self.material_node, self.new_output_connections = self.create_mtlx_init_shader(self.target_context)
        elif target_renderer == 'arnold':
            self.material_node, self.new_output_connections = self.create_arnold_init_shader(self.target_context)
        elif target_renderer == 'principledshader':
            self.material_node, self.new_output_connections = self.create_principledshader_init_shader(self.target_context)
        elif target_renderer == 'create_rs_usd_material_builder_init_shader':
            self.material_node, self.new_output_connections = self.create_rs_usd_material_builder_init_shader(self.target_context)
        else:
            raise KeyError(f"Unsupported target renderer: {self.target_renderer}")

    def create_output_nodes(self):
        """
        Create or reuse output nodes in the target context.
        """
        if self.target_renderer not in ['arnold', 'mtlx', 'create_rs_usd_material_builder_init_shader']:
            return None

        for generic_output_type, output_info in self.orig_output_connections.items():
            # e.g. generic_output_type = "GENERIC::output_surface"
            # e.g. output_info         = {'node_path': '/mat/material_mtlx_ORIG/surface_output',
            #                             'node_name': 'surface_output', ???
            #                             'connected_node_name': 'surface_output',
            #                             'connected_input_index': 0}

            new_output_nodename = self.new_output_connections.get(generic_output_type, {}).get('node_name')
            new_output_nodepath = f"{self.material_node.path()}/{new_output_nodename}"

            created_output_node: hou.VopNode = hou.node(new_output_nodepath)


            self.old_new_node_map[output_info['node_path']] = {'node_name': created_output_node.name(),
                                                               'node_path': created_output_node.path(),
                                                               'is_output': True,
                                                               'output_type': generic_output_type,
                                                               }

            self.new_output_connections[generic_output_type] = {'node': created_output_node,
                                                                'node_name': created_output_node.name(),
                                                                'node_path': created_output_node.path(),
                                                                'connected_node_name': output_info['connected_node_name'],
                                                                'connected_input_index': output_info['connected_input_index'],
                                                                'connected_input_name': output_info['connected_input_name'],
                                                                'connected_output_name': output_info['connected_output_name'],
                                                                }
        return None

    @staticmethod
    def _convert_generic_node_type_to_renderer_node_type(node_type: str, target_renderer: str):
        """
        Convert a generic node type to a renderer-specific node type.

        Args:
            node_type (str): The generic node type.
            target_renderer (str): renderer type: e.g. 'arnold', 'mtlx'

        Returns:
            str: The renderer-specific node type.
        """
        if node_type in GENERIC_NODE_TYPES_TO_REGULAR[target_renderer]:
            return GENERIC_NODE_TYPES_TO_REGULAR[target_renderer][node_type]
        else:
            return GENERIC_NODE_TYPES_TO_REGULAR[target_renderer]['GENERIC::null']

    @staticmethod
    def _apply_parameters(node, parameters):
        """
        Apply parameters to a Houdini node.

        Args:
            node (hou.Node): The Houdini node.
            parameters (List[NodeParameter]): The list of parameters to apply.
        """
        if not parameters:
            print(f"No parameters to apply to '{node.path()}'.")
            return

        node_type = node.type().name()
        std_parm_map = material_standardizer.REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type.replace('::', ':'), {})
        if not std_parm_map:
            print(f"WARNING: No generic parameter mappings found for node type: '{node_type}'")
            return

        for param in parameters:
            if param.direction != 'input':
                print(f"WARNING: Parameter '{param.generic_name}' is not an input parameter for node type '{node_type}'. Skipping.")
                continue
            if not param.generic_name:
                print(f"WARNING: Parameter of value:'{param.value}' has no generic_name for node type '{node_type}'. Skipping.")
                continue

            # Find the renderer-specific parameter name
            parm_new_name = [key for key, val in std_parm_map.items() if val == param.generic_name]

            if not parm_new_name:
                print(f"WARNING: No renderer-specific parameter found for generic name '{param.generic_name}'"
                      f" for node type '{node_type}'. Skipping.")
                continue

            parm_new_name = parm_new_name[0]
            hou_parm = node.parmTuple(parm_new_name)
            # print(f"DEBUG: {hou_parm.name()=}, {param.value=}")
            if hou_parm is None:
                print(f"WARNING: Parm '{parm_new_name}' not found on node '{node.path()}'.")
                continue

            if not isinstance(param.value, tuple):
                param.value = (param.value,)

            try:
                hou_parm.set(param.value)
            except Exception as e:
                print(f"ERROR: Failed to set parameter '{param.generic_name}' for node '{node.path()}': {e}")
                continue
            # print(f"Set parameter '{renderer_specific_name}' on node '{node.path()}' to '{param.value}'")


    def _create_node(self, node_info):
        """
        Create a Houdini node from NodeInfo.

        Args:
            node_info (NodeInfo): The NodeInfo object containing node information.

        Returns:
            (hou.Node): The created Houdini node.
        """
        new_node_type = self._convert_generic_node_type_to_renderer_node_type(node_info.node_type,
                                                                              target_renderer=self.target_renderer)

        # Check for existing nodes of the same type to reuse
        existing_nodes = [node for node in self.material_node.children() if
                          node.type().name() == new_node_type and node not in self.reused_nodes.values()]
        if existing_nodes:
            node = existing_nodes[0]
            print(f"Using existing node: {node.path()} of type {node.type().name()}")
            self._apply_parameters(node, node_info.parameters)
            self.reused_nodes[node_info.node_path] = node
            self.old_new_node_map[node_info.node_path] = {'node_name': node.name(),
                                                          'node_path': node.path()}

            return node

        # Create new node if no reusable node is found
        new_node = self.material_node.createNode(new_node_type, node_info.node_name)
        self._apply_parameters(new_node, node_info.parameters)
        self.reused_nodes[node_info.node_path] = new_node
        self.old_new_node_map[node_info.node_path] = {'node_name': new_node.name(),
                                                      'node_path': new_node.path()}
        return new_node

    def _create_nodes_recursive(self, nested_nodes_info: List[NodeInfo], processed_nodes=None):
        """
        Recursively create nodes from NodeInfo objects.

        Args:
            nested_nodes_info (List[NodeInfo]): The list of NodeInfo objects.
            processed_nodes (set, optional): A set of processed node paths.
        Returns:
            None
        """
        if processed_nodes is None:
            processed_nodes = set()
        for node_info in nested_nodes_info:
            if node_info.node_path in processed_nodes:
                continue

            # Create the node if it's not an output node
            if node_info.node_type != 'GENERIC::output_node':
                newly_created_node = self._create_node(node_info)

                # move node to original position:
                if node_info.position:
                    newly_created_node.setPosition(node_info.position)

                self.old_new_node_map[node_info.node_path] = {'node_name': newly_created_node.name(),
                                                              'node_path': newly_created_node.path()}

            processed_nodes.add(node_info.node_path)

            # Recursively create child nodes
            self._create_nodes_recursive(node_info.children_list, processed_nodes)

    def create_shader_nodes(self, nested_nodes_info):
        """
        Create nodes in the target context.
        """
        if self.target_renderer not in ['arnold', 'mtlx']:
            raise ValueError(f"Can't Create Nodes for Unsupported target renderer: {self.target_renderer}")

        self._create_nodes_recursive(nested_nodes_info)
        return True


    def set_output_connections(self):
        """
        Set connections for the output nodes in the recreated material.
        """
        renderer_output_connections = OUTPUT_CONNECTIONS_INDEX_MAP.get(self.target_renderer)
        if not renderer_output_connections:
            raise KeyError(f"Unsupported renderer: {self.target_renderer}")
        if self.target_renderer not in ['arnold', 'mtlx']:
            raise KeyError(f"Unsupported renderer: {self.target_renderer}")

        # print(f"DEBUG: self.new_output_connections: {pprint.pformat(self.new_output_connections, sort_dicts=False)}")
        # print(f"DEBUG: self.orig_output_connections: {pprint.pformat(self.orig_output_connections, sort_dicts=False)}")

        # e.g. output_type = 'GENERIC::output_surface'
        #
        # e.g. self.new_output_connections = {'GENERIC::output_surface': {'node': <hou.VopNode of type arnold_material at /mat/arnold_materialbuilder2/OUT_material>,
        #                               'node_name': 'OUT_material'},
        #                               'node_path': '/mat/arnold_materialbuilder2/OUT_material'},
        #                               'GENERIC::output_displacement': {'node': <hou.VopNode of type arnold_material at /mat/arnold_materialbuilder2/OUT_material>,
        #                               'node_path': '/mat/arnold_materialbuilder2/OUT_material'}}
        #
        #
        # DEBUG: self.orig_output_connections: {'GENERIC::output_surface': {'node_path': '/mat/arnold_materialbuilder1/OUT_material',
        #                              'connected_node_name': 'standard_surface1',
        #                              'connected_node_path': '/mat/arnold_materialbuilder1/standard_surface1',
        #                              'connected_input_index': 0}}

        # print(f"DEBUG: self.old_new_node_map: {pprint.pformat(self.old_new_node_map, sort_dicts=False)}")
        # print(f"DEBUG: self.orig_output_connections: {pprint.pformat(self.orig_output_connections, sort_dicts=False)}")
        # print(f"DEBUG: self.new_output_connections: {pprint.pformat(self.new_output_connections, sort_dicts=False)}")

        for output_type, output_info in self.new_output_connections.items():
            output_index = renderer_output_connections[output_type]
            output_node = output_info['node']

            if output_type not in renderer_output_connections:
                raise KeyError(f"{output_type=} not found in {renderer_output_connections=}")

            # e.g. output_type= 'GENERIC::output_surface'
            # e.g. self.orig_output_connections: {'GENERIC::output_surface': {'node_name': 'principledshader',
            #                              'node_path': '/mat/principledshader',
            #                              'connected_node_name': '',
            #                              'connected_node_path': '',
            #                              'connected_input_index': 0}}

            # e.g. self.old_new_node_map: {'/mat/arnold_materialbuilder1/OUT_material': {'node_name': 'OUT_material',
            #                                                          'node_path': '/mat/arnold_materialbuilder2/OUT_material'},
            #       '/mat/arnold_materialbuilder1/standard_surface1': {'node_name': 'standard_surface1',
            #                                                          'node_path': '/mat/arnold_materialbuilder2/standard_surface1'},
            #       '/mat/arnold_materialbuilder1/curvature1': {'node_name': 'curvature1',
            #                                                   'node_path': '/mat/arnold_materialbuilder2/curvature1'},
            #       '/mat/arnold_materialbuilder1/mix_rgba1': {'node_name': 'mix_rgba1',
            #                                                  'node_path': '/mat/arnold_materialbuilder2/mix_rgba1'},
            #       '/mat/arnold_materialbuilder1/layer_rgba1': {'node_name': 'layer_rgba1',
            #                                                    'node_path': '/mat/arnold_materialbuilder2/layer_rgba1'},
            #       '/mat/arnold_materialbuilder1/image_diffuse': {'node_name': 'image_diffuse',
            #                                                      'node_path': '/mat/arnold_materialbuilder2/image_diffuse'},
            #       '/mat/arnold_materialbuilder1/color_correct2': {'node_name': 'color_correct2',
            #                                                       'node_path': '/mat/arnold_materialbuilder2/color_correct2'},
            #       '/mat/arnold_materialbuilder1/color_correct1': {'node_name': 'color_correct1',
            #                                                       'node_path': '/mat/arnold_materialbuilder2/color_correct1'},
            #       '/mat/arnold_materialbuilder1/range1': {'node_name': 'range1',
            #                                               'node_path': '/mat/arnold_materialbuilder2/range1'},
            #       '/mat/arnold_materialbuilder1/image_roughness': {'node_name': 'image_roughness',
            #                                                        'node_path': '/mat/arnold_materialbuilder2/image_roughness'}}

            # e.g. connected_node_info: {
            #       'node_name': 'OUT_material',
            #       'node_path': '/mat/arnold_materialbuilder1/OUT_material',
            #       'connected_node_name': 'standard_surface1',
            #       'connected_node_path': '/mat/arnold_materialbuilder1/standard_surface1',
            #       'connected_input_index': 0
            #       }

            # Find the connected node info from the nodeinfo_list output connections
            new_connected_node_info = self.new_output_connections[output_type]
            print(f"DEBUG: new_connected_node_info: {pprint.pformat(new_connected_node_info, sort_dicts=False)}")

            if new_connected_node_info:
                new_connected_node: hou.VopNode = self.material_node.node(new_connected_node_info.get('connected_node_name'))
                if not new_connected_node:
                    print(f"WARNING: Connections for node:'{new_connected_node_info['node_name']}' not found!")
                    continue

                print(f"INFO: Setting input for {output_node.path()}[{output_index}] "
                      f"to '{new_connected_node.path()}[0]' for output type: '{output_type}', ")
                output_node.setInput(output_index, new_connected_node)

            else:
                # This part of the code never runs. Probably safe to delete.
                # Ensure the existing output node is mapped correctly
                print(f"////////WARNING: no new_connected_node_info found for: '{output_type}'")
                existing_output_node = self.old_new_node_map.get(output_info['node_path'])
                if existing_output_node:
                    self.old_new_node_map[output_info['node_path']] = existing_output_node
                    print(f"DEBUG: Using newly created output node: '{existing_output_node.path()}' for "
                          f"generic output: '{output_type}'")
                else:
                    print(f"DEBUG: No connected node info found for {output_type=}")

        return True


    def _get_new_node_from_nodeinfo(self, node_info):
        """
        Find the newly-created Houdini node corresponding to node_info.
        """
        old_path = node_info.node_path
        mapping = self.old_new_node_map.get(old_path, {})
        new_path = mapping.get('node_path')
        if not new_path:
            print(f"WARNING: Couldn't find new node for '{old_path}'.")
            return None

        node = hou.node(new_path)
        if not node:
            print(f"WARNING: New node path '{new_path}' does not exist in the scene.")
            return None

        return node

    def _process_connections_for_node(self, src_nodeinfo, dest_node):
        """
        Iterate all connections for one node and wire them up (skipping output nodes).
        """
        for conn in src_nodeinfo.connection_info.values():
            # print(f"\nDEBUG: connecting src node: '{src_nodeinfo.node_name}[{conn['input']['node_index']}][{conn['input']['parm_name']}]' to "
            #       f"dest node: '{dest_node.name()}[{conn['output']['node_index']}][{conn['output']['parm_name']}]'")
            src_node_name = conn['input']['node_name']
            dest_node_name = conn['output']['node_name']

            # find the source (input) node
            src_node = self._get_input_node(src_node_name)
            if not src_node:
                continue

            # skip wiring if this is one of our designated outputs
            if self._is_output_node(dest_node.name()):
                print(f"WARNING: Skipping connection for '{dest_node_name} → {dest_node.name()}' (it's an output node).")
                continue

            # perform the actual wire
            self._connect_pair(
                src_node=src_node,
                dest_node=dest_node,
                src_parm=conn['input']['parm_name'],
                dest_parm=conn['output']['parm_name'],
                # src_idx=conn['input']['node_index'],
                # dest_idx=conn['output']['node_index'],
            )

    def _get_input_node(self, node_name):
        """
        Look up a child of material_node by name.

        Args:
            node_name (str): The name of the node to find in the material builder's children.

        Returns:
            hou.Node: The found child node, or None if not found.
        """
        path = f"{self.material_node.path()}/{node_name}"
        node = hou.node(path)
        if not node:
            print(f"WARNING: Input node '{node_name}' not found at '{path}'.")
        return node

    def _is_output_node(self, nodename):
        """
        Return True if `nodename` matches one of our created output nodes.
        """
        return any(info['node_name'] == nodename
                   for info in self.new_output_connections.values())

    def _connect_pair(self, src_node, dest_node, src_parm='', dest_parm='',
                      src_idx=None, dest_idx=None):
        """
        Wire src_node.output[src_idx] into dest_node.input[<resolved index>].

        Args:
            src_node (hou.node): The source node.
            dest_node (hou.node): The destination node.
            src_parm (str, Optional): The source parameter name that connects to the dest_node, if not provided then use src_idx
            dest_parm (str, Optional): The destination parameter name that will be connected to the src_node, if not provided then use dest_idx

        """
        # TODO: add a standardization parm names. e.g., 'RGBA' in arnold should be translated to 'out' in MTLX
        if not dest_idx:
            dest_idx = 0
            dest_idx_by_name = dest_node.inputIndex(dest_parm)
            if dest_idx_by_name != -1:
                # print(f"DEBUG: /////////////////// {dest_idx_by_name=}")
                dest_idx = dest_idx_by_name
            else:
                print(f"WARNING: dest: '{dest_node.name()}' has no parm: '{dest_parm}', using provided index: {dest_idx}.")

        if not src_idx:
            src_idx = 0
            src_idx_by_name = src_node.outputIndex(src_parm)
            if src_idx_by_name != -1:
                src_idx = src_idx_by_name
            else:
                print(f"WARNING: src: '{src_node.name()}' has no parm: '{src_parm}', using provided index: {src_idx}.")


        # if it's a node that needs splitting, we split the channels
        if src_node.type().name() in ['mtlximage', 'mtlxrange', 'mtlxcolorcorrect'] and src_parm not in ['rgb', 'rgba', 'out', 'outColor']:
            check, _ = self.create_mtlx_vec3_split_node(src_node=src_node, dest_node=dest_node,
                                                        src_out_parm_name=src_parm, dest_in_index=dest_idx)
            return check


        try:
            dest_node.setInput(dest_idx, src_node, src_idx)
            print(f"INFO: Connected '{src_node.name()}'[{src_idx}] → '{dest_node.name()}'[{dest_idx}].")
            return True
        except Exception as e:
            print(f"WARNING: Failed to connect '{src_node.name()}[{src_idx}]' → '{dest_node.name()}[{dest_idx}]': {e}")
            return False

    def set_node_connections(self, nodeinfo_list, parent_node=None):
        """
        Top-level entry: recurse over a list of NodeInfo and wire them up.
        """
        if not nodeinfo_list:
            print("WARNING: Empty node list, nothing to connect.")
            return

        for i, node_info in enumerate(nodeinfo_list):
            current_node = parent_node or self._get_new_node_from_nodeinfo(node_info)
            if not current_node:
                continue

            if not node_info.connection_info:
                print(f"WARNING: '{current_node.name()}': No Input Connections found. Skipping.")
            else:
                # actual connection logic:
                self._process_connections_for_node(node_info, current_node)
                # set current_node to be the parent (dest_node) for recursive iteration)
                current_node = self._get_new_node_from_nodeinfo(node_info)

            # recurse into *its* children, passing *that* new node
            if node_info.children_list:
                self.set_node_connections(node_info.children_list, current_node)

    def run(self):
        """
        Recreate the nodes in the target context based on the material data.
        """
        # create initial shader network:
        self.create_init_shader(self.target_renderer)
        # print(f"{self.material_node=}, {self.standardizer.output_nodes_dict=}, {self.new_output_connections=}")

        # Create output nodes first:
        print(f"INFO: STARTING create_output_nodes()....")
        self.create_output_nodes()
        print(f"INFO: DONE create_output_nodes()....\n\n\n")

        # Create Child nodes:
        print(f"INFO: STARTING create_shader_nodes()....")
        self.create_shader_nodes(self.nodeinfo_list)
        print(f"INFO: DONE create_shader_nodes()....")

        # connect child nodes to each other:
        print(f"INFO: STARTING _set_node_inputs()....")
        self.set_node_connections(self.nodeinfo_list)
        print(f"INFO: DONE _set_node_inputs()....\n\n\n")

        # connect output nodes to child nodes:
        print(f"INFO: STARTING _set_output_connections()....")
        self.set_output_connections()
        print(f"INFO: DONE _set_output_connections()....\n\n\n")







##############################################



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



def ingest_material(material_node):
    try:
        material_type = get_material_type(material_node)
        if not material_type:
            print(f"Couldn't determine Input material type, "
                  f"currently only Arnold, MTLX, Redshift Standard Material and Principled Shader are supported!")
            return None, None, None

        print("INFO: NodeTraverser() START----------------------")
        traverser = NodeTraverser(material_node, material_type=material_type)
        nested_nodes_dict, output_nodes_dict = traverser.run()
        # DEBUG: traverser.output_nodes_dict: {
        #     "surface": {
        #         "node_name": "OUT_material",
        #         "node_path": "/mat/arnold_materialbuilder_basic/OUT_material",
        #         "connected_node_name": "standard_surface",
        #         "connected_node_path": "/mat/arnold_materialbuilder_basic/standard_surface",
        #         "connected_input_index": 0,
        #         "connected_input_name": "surface",
        #         "connected_output_name": "shader",
        #         "generic_type": "GENERIC::output_surface"
        #     }
        # }
        # DEBUG: material_type: 'arnold'
        # DEBUG: material_node: 'arnold_materialbuilder_basic'
        print("INFO: NodeTraverser() Finished----------------------\n\n\n")


        print("INFO: NodeStandardizer() START----------------------")
        standardizer = material_standardizer.NodeStandardizer(
            traversed_nodes_dict=nested_nodes_dict,
            output_nodes_dict=output_nodes_dict,
            material_type=material_type,
        )
        nodeinfo_list, output_connections = standardizer.run()

        # for nodeinfo in nodeinfo_list:
        #     print(f"DEBUG: nodeinfo: {nodeinfo=}\n")

        # DEBUG: output_connections:        {'GENERIC::output_surface':
        #                                       {'node_name': 'OUT_material',
        #                                           'node_path': '/mat/arnold_materialbuilder_basic/OUT_material',
        #                                           'connected_node_name': 'standard_surface',
        #                                           'connected_node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
        #                                           'connected_input_index': 0
        #                                       }
        #                                   }
        # DEBUG: target_context.path()='/mat'
        # DEBUG: target_format='mtlx'
        print("INFO: NodeStandardizer() Finished----------------------\n\n\n")

        return material_type, nodeinfo_list, output_connections

    except:
        traceback.print_exc()
        return None, None, None


def run(input_material_builder_node, target_context, target_format='mtlx'):
    """
    Run the material conversion process for the selected node.

    Args:
        input_material_builder_node (hou.Node): The selected Houdini shading network,
                                                e.g., arnold materialbuilder or mtlx materialbuilder.
        target_context (hou.Node): The target Houdini context node.
        target_format (str, optional): The target renderer (default is 'mtlx').
    """
    material_type, nodeinfo_list, output_connections = ingest_material(input_material_builder_node)
    if not (material_type and nodeinfo_list and output_connections):
        return

    try:
        print("NodeRecreator() START----------------------")
        recreator = NodeRecreator(
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
            target_context=target_context,
            target_renderer=target_format
        )
        print("NodeRecreator() Finished----------------------\n\n\n")
        print(f"Material conversion complete. Converted material from '{material_type}' to '{target_format}'.")
    except Exception:
        traceback.print_exc()
        return









def test():
    """
    Test function to validate the node traversal, standardization, and recreation process.
    """
    target_renderer = 'mtlx'
    material_type = 'arnold'

    node_tree = utils_io.load_node_tree_json(resources.files("Material_Processor.tests") / "example_node_tree.json")
    output_nodes = utils_io.load_node_tree_json(resources.files("Material_Processor.tests") / "example_output_tree.json")
    # output_nodes_dict = utils_io.load_node_tree_json("example_output_nodes.json")  # if stored separately

    standardizer = material_standardizer.NodeStandardizer(
        traversed_nodes_dict=node_tree,
        output_nodes_dict=output_nodes,
        material_type=material_type,
    )
    nodeinfo_list, output_connections = standardizer.run()

    # print(f"DEBUG: {standardizer.node_info_list=}")
    return nodeinfo_list, output_connections




def test_hou():
    target_context = hou.node('/mat')
    target_renderer = 'arnold'
    material_type = 'arnold'
    try:
        nodeinfo_list, output_connections = test()

        recreator = NodeRecreator(
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
            target_context=target_context,
            target_renderer=target_renderer
        )
    except Exception:
        traceback.print_exc()
        return


"""
how to run from houdini shelf tool:
1 - copy this block of code into a new shelf tool
2 - select a material node inside a material context
3 - run the shelf tool
4 - new mats are created in '/mat'

##########
from importlib import reload
import hou
from Material_Processor import material_processor
reload(material_processor)

target_context = hou.node('/mat')
selected_nodes = hou.selectedNodes()
if selected_nodes:
    for node in selected_nodes:
        parent = node.parent()
        material_processor.run(node, parent)
    
###################


"""





if __name__ == "__main__":
    test()



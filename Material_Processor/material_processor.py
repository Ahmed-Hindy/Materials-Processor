"""
copyright Ahmed Hindy. Please mention the original author if you used any part of this code
This module processes material nodes in Houdini, extracting and converting shader parameters and textures.
"""

import json
import logging
from typing import Dict, List
import pprint
from importlib import reload


import Material_Processor.material_classes
reload(Material_Processor.material_classes)
from Material_Processor.material_classes import MaterialData, NodeInfo, NodeParameter


try:
    import hou
except:
    # temp to make the module work with substance painter
    print("materialProcessor running outside of Houdini!")
    hou = None




###################################### CONSTANTS ######################################

GENERIC_NODE_TYPES = {
    'arnold::standard_surface': 'GENERIC::standard_surface',
    'arnold::image': 'GENERIC::image',
    'arnold::range': 'GENERIC::range',
    'arnold::color_correct': 'GENERIC::color_correct',
    'arnold_material': 'GENERIC::output_node',

    'mtlxstandard_surface': 'GENERIC::standard_surface',
    'mtlximage': 'GENERIC::image',
    'mtlxrange': 'GENERIC::range',
    'mtlxcolorcorrect': 'GENERIC::color_correct',
    'mtlxdisplacement': 'GENERIC::displacement',
    'subnetconnector': 'GENERIC::output_node',
    'null': 'GENERIC::null'
}



"""
Conversion_map is a dict of 'from_node_type' : 'to_node_type'
"""
CONVERSION_MAP = {
            'arnold': {
                'GENERIC::standard_surface': 'arnold::standard_surface',
                'GENERIC::image': 'arnold::image',
                'GENERIC::color_correct': 'arnold::color_correct',
                'GENERIC::range': 'arnold::range',
                'GENERIC::null': 'null'
            },
            'mtlx': {
                'GENERIC::standard_surface': 'mtlxstandard_surface',
                'GENERIC::image': 'mtlximage',
                'GENERIC::color_correct': 'mtlxcolorcorrect',
                'GENERIC::range': 'mtlxrange',
                'GENERIC::displacement': 'mtlxdisplacement',
                'GENERIC::null': 'null'
            }
        }

OUTPUT_NODE_MAP = {
    'arnold': 'arnold_material',
    'mtlx': 'subnetconnector'
}


"""
names of parameters on specific node which is supported in this module. Any other node type will be filtered out.
"""
STANDARDIZED_PARAM_NAMES = {
    'mtlxstandard_surface': {
        'base': 'base',
        'base_colorr': 'base_colorr',
        'base_colorg': 'base_colorg',
        'base_colorb': 'base_colorb',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'specular': 'specular',
        'specular_colorr': 'specular_colorr',
        'specular_colorg': 'specular_colorg',
        'specular_colorb': 'specular_colorb',
        'specular_roughness': 'specular_roughness',
        'specular_IOR': 'specular_IOR',
        'transmission': 'transmission',
        'transmission_colorr': 'transmission_colorr',
        'transmission_colorg': 'transmission_colorg',
        'transmission_colorb': 'transmission_colorb',
        'subsurface': 'subsurface',
        'subsurface_color': 'subsurface_color',
        'emission': 'emission',
        'emission_colorr': 'emission_colorr',
        'emission_colorg': 'emission_colorg',
        'emission_colorb': 'emission_colorb',
        'opacity': 'opacity'
    },
    'mtlximage': {
        'signature': 'signature',
        'file': 'filename',
    },
    'mtlxcolorcorrect': {
        'hue': 'hue',
        'saturation': 'saturation',
        'gamma': 'gamma',
        'gain': 'gain',
        'contrast': 'contrast',
        'exposure': 'exposure',
    },
    'mtlxrange': {
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outlow': 'outlow',
        'outhigh': 'outhigh',
    },
    'mtlxdisplacement': {
        'displacement': 'displacement',
        'scale': 'scale',
    },

    'arnold::standard_surface': {
        'base': 'base',
        'base_colorr': 'base_colorr',
        'base_colorg': 'base_colorg',
        'base_colorb': 'base_colorb',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'specular': 'specular',
        'specular_colorr': 'specular_colorr',
        'specular_colorg': 'specular_colorg',
        'specular_colorb': 'specular_colorb',
        'specular_roughness': 'specular_roughness',
        'specular_IOR': 'specular_IOR',
        'transmission': 'transmission',
        'transmission_colorr': 'transmission_colorr',
        'transmission_colorg': 'transmission_colorg',
        'transmission_colorb': 'transmission_colorb',
        'subsurface': 'subsurface',
        'subsurface_color': 'subsurface_color',
        'emission': 'emission',
        'emission_colorr': 'emission_colorr',
        'emission_colorg': 'emission_colorg',
        'emission_colorb': 'emission_colorb',
        'opacity': 'opacity'
    },
    'arnold::image': {
        'filename': 'filename'
    },
    'arnold::color_correct': {
        'gamma': 'gamma',
        'hue_shift': 'hue',
        'saturation': 'saturation',
        'contrast': 'contrast',
        'exposure': 'exposure',
    },
    'arnold::range': {
        'input_min': 'inlow',
        'input_max': 'inhigh',
        'gamma': 'gamma',
        'output_min': 'outlow',
        'output_max': 'outhigh',
    },

    'principledshader::2.0': {
        'basecolor': 'base_color',
        'metallic': 'metalness',
        'rough': 'specular_roughness',
        'ior': 'specular_IOR',
        'reflect': 'specular',
        'difftrans': 'transmission',
        'emission': 'emission',
        'opaccolor': 'opacity',
        'subsurface': 'subsurface',
        'subtint': 'subsurface_color',
        'basecolorr': 'base_colorr',
        'basecolorg': 'base_colorg',
        'basecolorb': 'base_colorb',
        'sheen': 'sheen',
        'sheencolor': 'sheen_color',
        'coat': 'coat',
        'coatrough': 'coat_roughness',
        'coatior': 'coat_IOR',
        'coatcolorr': 'coat_colorr',
        'coatcolorg': 'coat_colorg',
        'coatcolorb': 'coat_colorb'
    }
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

def _convert_to_serializable(obj):
    """
    [TEMP FOR DEBUG ONLY] Convert non-serializable objects to a string for JSON dumping.
    """
    if not obj:
        return 'None'
    elif isinstance(obj, hou.VopNode):
        return obj.path()
    elif isinstance(obj, tuple):
        return 'tuple'
    elif isinstance(obj, hou.Parm):
        return obj.name()
    try:
        return str(obj)
    except:
        return "None2"  # Handle cases where conversion fails



class NodeTraverser:
    """
    Class for traversing Houdini nodes to extract their connections and output nodes.
    """

    def __init__(self, material_type: str) -> None:
        """
        Initialize the NodeTraverser with the specified material type.

        Args:
            material_type (str): The type of material (e.g., 'arnold', 'mtlx', 'principledshader').
        """
        self.material_type = material_type
        self.output_nodes = {}

    def traverse_node_tree(self, node, path=None):
        """
        Recursively traverse the node tree and return a dictionary of node connections with additional metadata,
        separating the input index and input node path as key-value pairs.

        Args:
            node (hou.Node): The current Houdini node.
            path (list[hou.Node], optional): The traversal path.

        Returns:
            Dict[str, Dict]: A dictionary representing the node tree with additional metadata.
        """
        if path is None:
            path = []

        # Check if this node is an output node
        is_output_node = False
        output_type = None
        for output_name, output_data in self.output_nodes.items():
            output_data_node = hou.node(output_data['node_path'])
            if output_data_node == node:
                is_output_node = True
                output_type = output_name
                break

        # Initialize the node's dictionary with metadata
        node_dict = {
            'node_name': node.name(),
            'node_path': node.path(),
            'node_type': node.type().name(),
            'node_parms': self.convert_parms_to_dict(node.parms()),
            'is_output_node': is_output_node,
            'output_type': output_type,
            'children': []
        }

        if not node.inputs():
            return {node.path(): node_dict}

        for input_node in node.inputs():
            if not input_node:
                continue

            input_index = None
            for input_conn in node.inputConnections():
                if input_conn.inputNode() == input_node:
                    input_index = input_conn.inputIndex()
                    break

            # Recursively get child nodes
            input_node_dict = self.traverse_node_tree(input_node, path + [node])

            # Store the input index and node path as separate key-value pairs in the children list
            child_data = {
                'input_node_path': input_node.path(),
                'input_index': input_index,
                'child_node': input_node_dict[input_node.path()]
            }

            node_dict['children'].append(child_data)

        return {node.path(): node_dict}


    @staticmethod
    def _detect_arnold_output_nodes(parent_node):
        """
        Detect Arnold output nodes in the node tree.

        Args:
            parent_node (hou.Node): The parent Houdini node.

        Returns:
            Dict: A dictionary of detected Arnold output nodes.
        """
        arnold_output = None
        for child in parent_node.children():
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
            connected_output_index = connection.inputIndex()
            if connected_output_index == 0:
                output_nodes['surface'] = {
                    # 'node': arnold_output,
                    'node_name': arnold_output.name(),
                    'node_path': arnold_output.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_node_index': connected_input_index,
                    'generic_type': 'GENERIC::output_surface'
                }
            elif connected_output_index == 1:
                output_nodes['displacement'] = {
                    # 'node': arnold_output,
                    'node_name': arnold_output.name(),
                    'node_path': arnold_output.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_node_index': connected_input_index,
                    'generic_type': 'GENERIC::output_displacement'
                }
        return output_nodes

    @staticmethod
    def _detect_mtlx_output_nodes(parent_node):
        """
        Detect MaterialX output nodes in the node tree.

        Args:
            parent_node (hou.Node): The parent Houdini node.

        Returns:
            Dict: A dictionary of detected MaterialX output nodes.
        """
        output_nodes = {}
        output_nodes_list = [child for child in parent_node.children() if child.type().name() == 'subnetconnector']

        for output_node in output_nodes_list:
            connections = output_node.inputConnections()
            for connection in connections:
                connected_input = connection.inputNode()
                connected_input_index = connection.outputIndex()
                connected_output_index = connection.inputIndex()
            parmname = output_node.parm('parmname').eval()
            if parmname in ['surface', 'displacement']:
                output_nodes[parmname] = {
                    # 'node': arnold_output,
                    'node_name': output_node.name(),
                    'node_path': output_node.path(),
                    'connected_node_name': connected_input.name(),
                    'connected_node_path': connected_input.path(),
                    'connected_node_index': connected_input_index
                }
        return output_nodes

    @staticmethod
    def _detect_principled_output_nodes(parent_node):
        """
        Detect Principled Shader output nodes in the node tree.

        Args:
            parent_node (hou.Node): The parent Houdini node.

        Returns:
            Dict: A dictionary of detected Principled Shader output nodes.
        """
        output_nodes = {}
        for child in parent_node.children():
            if child.type().name() == 'principledshader::2.0':
                output_nodes['surface'] = {
                    'node_name': child.name(),
                    'node_path': child.path(),
                    'generic_type': 'GENERIC::output_surface'
                }
            elif child.type().name() == 'displacement':
                output_nodes['displacement'] = {
                    'node_name': child.name(),
                    'node_path': child.path(),
                    'generic_type': 'GENERIC::output_displacement'
                }
        return output_nodes

    @staticmethod
    def detect_output_nodes(parent_node, material_type: str):
        """
        Detect output nodes in the node tree based on the material type.

        Args:
            parent_node (hou.Node): The parent Houdini node.
            material_type (str): The type of material (e.g., 'arnold', 'mtlx', 'principledshader').

        Returns:
            Dict: A dictionary of detected output nodes.
        """
        print(f"detect_output_nodes START for {parent_node.path()}")
        if material_type == 'arnold':
            output_nodes = NodeTraverser._detect_arnold_output_nodes(parent_node)
        elif material_type == 'mtlx':
            output_nodes = NodeTraverser._detect_mtlx_output_nodes(parent_node)
        elif material_type == 'principledshader':
            output_nodes = NodeTraverser._detect_principled_output_nodes(parent_node)
        else:
            raise KeyError(f"Unsupported renderer: {material_type=}")

        return output_nodes

    def traverse_principled_shader(self, node):
        """
        Traverse the Principled Shader node to extract its parameters.

        Args:
            node (hou.Node): The Principled Shader Houdini node.

        Returns:
            Dict: A dictionary representing the node tree of the Principled Shader node.
        """
        parameters = self.extract_principled_parameters(node)
        print(f"{parameters=}")

        node_dict = {
            node: {
                'parameters': parameters,
                'children': {}
            }
        }
        return node_dict

    @staticmethod
    def extract_principled_parameters(node):
        """
        Extract parameters from a Principled Shader node.

        Args:
            node (hou.Node): The Principled Shader Houdini node.

        Returns:
            List[NodeParameter]: A list of extracted node parameters.
        """
        node_type = node.type().name()
        filtered_param_names = []
        standardized_names = STANDARDIZED_PARAM_NAMES.get(node_type, {})
        try:
            filtered_param_names = list(STANDARDIZED_PARAM_NAMES.get(node_type).keys())
        except AttributeError:
            print(f"WARNING: node_type: {node_type} not in STANDARDIZED_PARAM_NAMES dict")

        node_parameters = [NodeParameter(name=p.name(), value=p.eval(),
                                         standardized_name=standardized_names.get(p.name(), p.name()))
                           for p in node.parms() if p.name() in filtered_param_names
                           ]
        return node_parameters

    @staticmethod
    def convert_parms_to_dict(parms_list):
        """
        Convert a list of hou.Parm objects to a list of dictionaries with name and value.

        Args:
            parms_list (List[hou.Parm]): The list of hou.Parm objects.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries with parameter names and values.
        """
        return [{'name': p.name(), 'value': p.eval()} for p in parms_list]

    def traverse_children_nodes(self, parent_node):
        """
        Traverse the children nodes of a parent node to extract the node tree and detect output nodes.

        Args:
            parent_node (hou.Node): The parent Houdini node.

        Returns:
            Dict: A dictionary representing the node tree of the children nodes.
        """
        # Detect output nodes before starting traversal
        self.output_nodes = self.detect_output_nodes(parent_node, material_type=self.material_type)
        print(f"Output nodes detected: {pprint.pformat(self.output_nodes)}\n")

        output_nodes = []
        for child in parent_node.children():
            is_output = True
            for other_node in parent_node.children():
                if child in other_node.inputs():
                    is_output = False
                    break
            if is_output:
                output_nodes.append(child)

        all_branches = {}
        for output_node in output_nodes:
            branch_dict = self.traverse_node_tree(output_node, [])
            all_branches.update(branch_dict)

        # print('traverse_children_nodes()-----all_branches:')
        # pprint.pprint(all_branches, indent=1, compact=True, width=10)
        # print(f'Done\n')

        # temp: dump all of this into a temp json file
        json_str = json.dumps(all_branches, default=_convert_to_serializable, indent=4)
        import tempfile
        with open(f"{tempfile.gettempdir()}/houdini_temp/json_dump.json", "w") as json_file:
            json_file.write(json_str)

        return all_branches



class NodeStandardizer:
    """
    Class for standardizing Shader nodes and creating MaterialData Class.
    """

    def __init__(self, traverse_tree: Dict, output_nodes: Dict, material_type: str,
                 input_material_builder_node):
        """
        Initialize the NodeStandardizer with the traverse tree and output nodes.

        Args:
            traverse_tree (Dict): The nested node dictionary from NodeTraverser.
            output_nodes (Dict): The detected output nodes from NodeTraverser.
            material_type (str): The type of material (e.g., 'arnold', 'mtlx', 'principledshader').
            input_material_builder_node (hou.Node): The input material builder node.
        """
        self.traverse_tree = traverse_tree
        self.output_nodes = output_nodes
        self.material_type = material_type
        self.input_material_builder_node = input_material_builder_node
        self.standardized_output_nodes = self.standardize_output_nodes(self.output_nodes)

        self.node_info_list = self.traverse_node_tree(self.traverse_tree)



    @staticmethod
    def convert_parms_to_dict(parms_list):
        """
        Convert a list of hou.Parm objects to a list of dictionaries with name and value.

        Args:
            parms_list (List[hou.Parm]): The list of hou.Parm objects.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries with parameter names and values.
        """
        return [{'name': p.name(), 'value': p.eval()} for p in parms_list]

    @staticmethod
    def standardize_output_nodes(output_nodes_dict) -> Dict:
        standardized_output_nodes = {}
        for key, value in output_nodes_dict.items():
            standardized_key = f"GENERIC::output_{key}"
            standardized_output_nodes[standardized_key] = {
                'node_path': value['node_path'],
                'connected_node_name': value['connected_node_name'],
                'connected_node_path': value['connected_node_path'],
                'connected_node_index': value['connected_node_index']
            }
        return standardized_output_nodes

    @staticmethod
    def standardize_shader_node(node_path, node_children_dict):
        """
        Create a NodeInfo object from a node.

        Args:
            node_path (str): The Houdini node path.
            node_children_dict (dict): The Houdini node path.
        Returns:
            NodeInfo: The created NodeInfo object.
        """
        is_output_node = node_children_dict.get('is_output_node', False)
        output_type = node_children_dict.get('output_type', None)

        connected_input_index = node_children_dict.get('connected_node_index', None)

        node_name: str = node_children_dict['node_name']
        node_type: str = node_children_dict['node_type']
        child_node_parms: list = node_children_dict.get('node_parms')
        print(f"DEBUG: parms for node: '{node_path}': {child_node_parms}")

        parameters = None
        if child_node_parms:
            parameters = NodeStandardizer.standardize_shader_parameters(node_type, child_node_parms)

        generic_node_type = GENERIC_NODE_TYPES.get(node_type)

        return NodeInfo(
            node_type=generic_node_type,
            node_name=node_name,
            node_path=node_path,
            parameters=parameters,
            connected_input_index=connected_input_index,
            child_nodes=[],
            is_output_node=is_output_node,
            output_type=output_type if is_output_node else generic_node_type
        )

    def traverse_node_tree(self, node_dict: Dict) -> List[NodeInfo]:
        """
        Recursively traverse the node dictionary and create a list of NodeInfo objects.

        Args:
            node_dict (Dict): The node dictionary to traverse.

        Returns:
            List[NodeInfo]: A list of NodeInfo objects.
        """
        local_nodes_info = []

        for node_path, node_info in node_dict.items():
            node_info_obj = self.standardize_shader_node(node_path, node_info)

            # Process children
            children = node_info.get('children', [])
            for child_entry in children:
                child_node_info = child_entry.get('child_node')
                child_node_path = child_entry.get('input_node_path')
                child_input_index = child_entry.get('input_index')

                # Recursively traverse child nodes
                child_nodes_info = self.traverse_node_tree({child_node_path: child_node_info})

                # Assign the input index to each child node
                for child_node in child_nodes_info:
                    child_node.connected_input_index = child_input_index

                node_info_obj.child_nodes.extend(child_nodes_info)

            local_nodes_info.append(node_info_obj)

        return local_nodes_info


    @staticmethod
    def standardize_custom_tree(custom_node_tree, material_name):
        """
        Manually create a standardized tree from custom tree dict with node names, paths, generic types, and parameters.

        Args:
            custom_node_tree (Dict): The custom tree provided by the user with node names, generic types, parameters, and connections.
            material_name (str): The name of the material.

        Returns:
            MaterialData: The created MaterialData object.
        """

        def traverse_tree(tree: Dict, parent_input_index=None) -> List[NodeInfo]:
            """
            Recursively traverse the custom node tree and return a list of NodeInfo objects.

            Args:
                tree (Dict): Custom node tree as a dictionary with node names, generic types, parameters, and connections.
                parent_input_index (int, optional): The index of the connected input node, if any.

            Returns:
                List[NodeInfo]: A list of NodeInfo objects representing the standardized tree.
            """
            node_info_list = []

            for node_name, node_data in tree.items():
                # Extract generic node type and parameters
                generic_node_type = node_data['generic_type']
                is_output_node = 'output' in generic_node_type
                parameters = NodeStandardizer.standardize_shader_parameters(generic_node_type,
                                                                            node_data.get('parameters', []))
                connections = node_data.get('connections', {})
                input_index = node_data.get('input_index', None)

                print(f"Processing node: {node_name}, type: {generic_node_type}, input_index: {input_index}")

                # Create NodeInfo for the current node
                node_info = NodeInfo(
                    node_type=generic_node_type,
                    node_name=node_name,
                    node_path=node_name,  # Assuming node_name is used as the path here
                    connected_input_index=parent_input_index,
                    is_output_node=is_output_node,
                    output_type=generic_node_type if is_output_node else None,
                    parameters=parameters,
                    child_nodes=[]
                )

                # Recursively process child nodes (connections)
                child_nodes_info = traverse_tree(connections, parent_input_index=input_index)
                node_info.child_nodes.extend(child_nodes_info)
                node_info_list.append(node_info)

            return node_info_list

        # Start traversing the custom tree to generate the nodes info list
        nodes_info_list = traverse_tree(custom_node_tree)

        # For simplicity, output_connections can be derived from output nodes
        output_connections = {}
        for node in nodes_info_list:
            if node.is_output_node:
                output_connections[node.output_type] = node

        # Create and return the MaterialData object with the processed nodes
        return MaterialData(
            material_name=material_name,
            nodeinfo_list=nodes_info_list,
            output_connections=output_connections
        )

    @staticmethod
    def standardize_shader_parameters(node_type, parms):
        """
        Filter and standardize parameters for a given node.

        Args:
            node_type (str): The type of the Houdini node.
            parms (List[Dict[str, Any]]): The list of parameter dictionaries to be standardized.

        Returns:
            List[NodeParameter]: A list of filtered and standardized node parameters.
        """
        standardized_names = STANDARDIZED_PARAM_NAMES.get(node_type, {})

        if not standardized_names:
            print(f"WARNING: node_type: {node_type} not in STANDARDIZED_PARAM_NAMES dict")
            return []

        node_parameters = [
            NodeParameter(
                name=param['name'],
                value=param['value'],
                standardized_name=standardized_names.get(param['name'])
            )
            for param in parms if param['name'] in standardized_names
        ]
        return node_parameters



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
        self.output_connections = output_connections
        self.target_context = target_context
        self.target_renderer = target_renderer
        self.old_new_node_map = {}  # a dict of {old_node_path:str  :  new_node_path:str}
        self.reused_nodes = {}
        self.material_builder = None
        self.created_output_nodes_dict = None  # e.g.: {'GENERIC::output_surface':{
        #                                                  'node': <hou.VopNode of type arnold_material at /mat/arnold_materialbuilder1/OUT_material>,
        #                                                  'node_path': '/mat/arnold_materialbuilder1/OUT_material'
        #                                                                          },
        #                                               'GENERIC::output_displacement': {
        #                                                   'node': <hou.VopNode of type arnold_material at /mat/arnold_materialbuilder1/OUT_material>,
        #                                                   'node_path': '/mat/arnold_materialbuilder1/OUT_material'
        #                                                                                }
        #                                               }

        self.run()


    @staticmethod
    def create_init_mtlx_shader(matnet=None):
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
        MTLX_TAB_MASK = 'MaterialX {} {}'.format(UTILITY_NODES, SUBNET_NODES)
        name = 'mtlxmaterial'
        folder_label = 'MaterialX Builder'
        render_context = 'mtlx'

        if not matnet:
            matnet = hou.node('/mat')
        subnet_node = matnet.createNode('subnet', name)
        subnet_node = voptoolutils._setupMtlXBuilderSubnet(subnet_node=subnet_node, name=name, mask=MTLX_TAB_MASK,
                                                           folder_label=folder_label, render_context=render_context)
        output_nodes = {
            'GENERIC::output_surface': {'node': subnet_node.node('surface_output'),
                                        'node_path': subnet_node.node('surface_output').path()},
            'GENERIC::output_displacement': {'node': subnet_node.node('displacement_output'),
                                             'node_path': subnet_node.node('displacement_output').path()}
        }
        return subnet_node, output_nodes

    @staticmethod
    def create_init_arnold_shader(matnet=None):
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
                                        'node_path': node_material_builder.node('OUT_material').path()},
            'GENERIC::output_displacement': {'node': node_material_builder.node('OUT_material'),
                                             'node_path': node_material_builder.node('OUT_material').path()}
        }
        return node_material_builder, output_nodes

    def create_output_nodes(self):
        """
        Create or reuse output nodes in the target context.
        """
        output_node_type = OUTPUT_NODE_MAP[self.target_renderer]  # e.g. 'arnold_material' or 'subnetconnector'

        for generic_output_type, output_info in self.output_connections.items():
            # e.g. output_type = "GENERIC::output_surface"
            # e.g. output_info = {'node_path': '/mat/material_mtlx_ORIG/surface_output',
            #                     'connected_node_name': 'surface_output',
            #                     'connected_node_index': 0}
            created_output_node_dict: dict = self.created_output_nodes_dict.get(generic_output_type, {})
            created_output_node: hou.VopNode = created_output_node_dict.get('node')
            created_output_node_path: hou.VopNode = created_output_node_dict.get('node_path')
            if not created_output_node:
                raise Exception(f"This part of code is never tested!, rewrite it!")

            print(f"Reusing existing output node: '{created_output_node_path}' of type: '{output_node_type}' "
                  f"for output generic type: {generic_output_type}")


            print(f"DEBUG: {output_info=}")
            # print(f"DEBUG: {output_info['node_path']=}")  # '/mat/material_mtlx_ORIG/mtlxstandard_surface' TODO: THIS IS WRONG. IT SHOULD BE THE OUTPUT NODE
            self.old_new_node_map[output_info['node_path']] = created_output_node.path()

            self.created_output_nodes_dict[generic_output_type]['node'] = created_output_node
        print(f"DEBUG: {self.old_new_node_map=}")


    def _create_nodes_recursive(self, nested_nodes_info: List[NodeInfo], processed_nodes=None):
        """
        Recursively create nodes from NodeInfo objects.

        Args:
            nested_nodes_info (List[NodeInfo]): The list of NodeInfo objects.
            processed_nodes (set, optional): A set of processed node paths.
        """
        if processed_nodes is None:
            processed_nodes = set()
        for node_info in nested_nodes_info:
            if node_info.node_path in processed_nodes:
                continue

            # Create the node if it's not an output node
            if node_info.node_type != 'GENERIC::output_node':
                newly_created_node = self._create_node(node_info)
                self.old_new_node_map[node_info.node_path] = newly_created_node.path()

            processed_nodes.add(node_info.node_path)

            # Recursively create child nodes
            self._create_nodes_recursive(node_info.child_nodes, processed_nodes)


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
        existing_nodes = [node for node in self.material_builder.children() if
                          node.type().name() == new_node_type and node not in self.reused_nodes.values()]
        if existing_nodes:
            node = existing_nodes[0]
            print(f"Using existing node: {node.path()} of type {node.type().name()}")
            self.apply_parameters(node, node_info.parameters)
            self.reused_nodes[node_info.node_path] = node
            self.old_new_node_map[node_info.node_path] = node.path()  # Ensure all nodes are mapped

            return node

        # Create new node if no reusable node is found
        new_node = self.material_builder.createNode(new_node_type, node_info.node_name)
        self.apply_parameters(new_node, node_info.parameters)
        self.reused_nodes[node_info.node_path] = new_node
        self.old_new_node_map[node_info.node_path] = new_node.path()  # Ensure all nodes are mapped
        return new_node


    def _set_node_inputs(self, nested_nodes_info: List[NodeInfo]):
        """
        Set the inputs for the created nodes.

        Args:
            nested_nodes_info (List[NodeInfo]): Nested nodes info as a list of NodeInfo objects.
        """

        print(f"\nDEBUG: {self.old_new_node_map=}")

        for node_info in nested_nodes_info:
            print(f"DEBUG: {node_info.node_path=}")
            new_node_path = self.old_new_node_map.get(node_info.node_path)
            new_node = hou.node(new_node_path)

            if not new_node:
                continue

            for child in node_info.child_nodes:
                # Access the node_path and connected_input_index attributes directly
                connected_node_path = child.node_path
                input_index = child.connected_input_index

                # Retrieve the corresponding new node from the map
                child_node_path = self.old_new_node_map.get(connected_node_path)
                child_node = hou.node(child_node_path)

                if child_node and input_index is not None:
                    try:
                        new_node.setInput(input_index, child_node)
                        print(f"Set input {input_index} of {new_node.path()} to {child_node.path()}")
                    except Exception as e:
                        print(f"Failed to set input {input_index} of {new_node.path()} to {child_node.path()}: {e}")

            # Recursively set inputs for child nodes
            self._set_node_inputs(node_info.child_nodes)

    def _set_inputs_recursive(self, node_info, new_node):
        """
        Recursively set inputs for nodes.

        Args:
            node_info (NodeInfo): Information about the current node.
            new_node (hou.Node): The newly created node corresponding to node_info.
        """
        if new_node is None:
            print(f"DEBUG: new_node is None for {node_info.node_path}, skipping.")
            return

        for child_info in node_info.child_nodes:
            print(f"DEBUG: {child_info.node_type=}, {child_info.node_path=}")
            child_node: hou.VopNode = self.old_new_node_map.get(child_info.node_path)

            if not child_node:
                print(f"DEBUG: child_node is None for {child_info.node_path}.")
                continue

            if new_node.type().name() not in OUTPUT_NODE_MAP[self.target_renderer]:
                print(f"DEBUG: {child_info.node_type=} found in output nodes, skipping direct connection.")

                if child_info.connected_input_index is not None:
                    print(f"DEBUG: Setting input {child_info.connected_input_index} of {new_node.path()} to {child_node.path()}.")
                    new_node.setInput(child_info.connected_input_index, child_node)
                else:
                    print(f"DEBUG: connected_input_index is None for child node {child_info.node_path}.")

            self._set_inputs_recursive(child_info, child_node)

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
        # print(f"DEBUG: Generic node {node_type}, converted to: {CONVERSION_MAP[self.target_renderer][node_type]}")
        if node_type in CONVERSION_MAP[target_renderer]:
            return CONVERSION_MAP[target_renderer][node_type]
        else:
            return CONVERSION_MAP[target_renderer]['GENERIC::null']



    @staticmethod
    def apply_parameters(node, parameters):
        """
        Apply parameters to a Houdini node.

        Args:
            node (hou.Node): The Houdini node.
            parameters (List[NodeParameter]): The list of parameters to apply.
        """
        node_type = node.type().name()
        node_specific_dict = STANDARDIZED_PARAM_NAMES.get(node_type, {})
        if not node_specific_dict:
            print(f"WARNING: No parameter mappings found for node type: {node_type}")
            return

        for param in parameters:
            standardized_name = param.standardized_name
            if not standardized_name:
                print(
                    f"WARNING: Parameter '{param.name}' has no standardized name for node type '{node_type}'. Skipping.")
                continue

            # Find the renderer-specific parameter name
            renderer_specific_name = None
            for key, value in node_specific_dict.items():
                if value == standardized_name:
                    renderer_specific_name = key
                    break

            if not renderer_specific_name:
                print(
                    f"WARNING: No renderer-specific parameter found for standardized name '{standardized_name}' in node type '{node_type}'. Skipping.")
                continue

            hou_parm = node.parm(renderer_specific_name)
            if hou_parm is not None:
                hou_parm.set(param.value)
                # print(f"Set parameter '{renderer_specific_name}' on node '{node.path()}' to '{param.value}'")
            else:
                print(f"WARNING: Parm '{renderer_specific_name}' not found on node '{node.path()}'.")

    def _set_output_connections(self):
        """
        Set connections for the output nodes in the recreated material.
        """
        renderer_output_connections = OUTPUT_CONNECTIONS_INDEX_MAP.get(self.target_renderer)
        if not renderer_output_connections:
            raise KeyError(f"Unsupported renderer: {self.target_renderer}")

        for output_type, output_info in self.created_output_nodes_dict.items():
            # e.g. output_type = 'GENERIC::output_surface'
            # e.g. output_info = {'node': <hou.VopNode of type arnold_material at /mat/arnold_materialbuilder4/OUT_material>,
            #                     'node_path': '/mat/arnold_materialbuilder4/OUT_material'}

            output_index = renderer_output_connections[output_type]
            output_node = output_info['node']

            if output_type not in renderer_output_connections:
                raise KeyError(f"{output_type=} not found in {renderer_output_connections=}")

            # Find the connected node info from the nodeinfo_list output connections
            connected_node_info = self.output_connections.get(output_type)
            # e.g. self.output_connections= {'GENERIC::output_surface':
            #                                   {'node_path': '/mat/material_mtlx_ORIG/surface_output',
            #                                    'connected_node_name': ???,
            #                                    'connected_node_index': 0},
            #                                    'GENERIC::output_displacement':
            #                                        {'node_path': '/mat/material_mtlx_ORIG/displacement_output',
            #                                         'connected_node_name': ???,
            #                                         'connected_node_index': 0}}

            if connected_node_info:
                # print(f"DEBUG: connected_node_info:    \n{pprint.pformat(connected_node_info, indent=6)}")
                old_connected_node_path = connected_node_info.get('connected_node_path')
                new_connected_node_path = self.old_new_node_map[old_connected_node_path]
                print(f"DEBUG: {old_connected_node_path=}")
                print(f"DEBUG: {new_connected_node_path=}")

                if new_connected_node_path and new_connected_node_path != output_node:
                    print(f"DEBUG: {output_type=}, Setting input {output_index} of {output_node.path()} "
                          f"to {new_connected_node_path}")
                    output_node.setInput(output_index, hou.node(new_connected_node_path))
                else:
                    print(f"DEBUG: New node for '{output_type}' not found in old_new_node_map or is the same as the"
                          f" output node.")
                    print(f"DEBUG: {new_connected_node_path=} {output_node.path()=}")
            else:
                # Ensure the existing output node is mapped correctly
                existing_output_node = self.old_new_node_map.get(output_info['node_path'])
                if existing_output_node:
                    self.old_new_node_map[output_info['node_path']] = existing_output_node
                    print(f"DEBUG: Using newly created output node: '{existing_output_node.path()}' for "
                          f"generic output: '{output_type}'")
                else:
                    print(f"DEBUG: No connected node info found for {output_type=}")

    def run(self):
        """
        Recreate the nodes in the target context based on the material data.
        """
        # Create the initial shader network based on the target renderer
        if self.target_renderer == 'mtlx':
            self.material_builder, self.created_output_nodes_dict = self.create_init_mtlx_shader(self.target_context)
        elif self.target_renderer == 'arnold':
            self.material_builder, self.created_output_nodes_dict = self.create_init_arnold_shader(self.target_context)
        else:
            raise Exception(f"Unsupported target renderer: {self.target_renderer}")

        # print(f"{self.material_builder=}, {self.standardizer.output_nodes=}, {self.created_output_nodes_dict=}")

        # Create output nodes first
        print(f"DEBUG: STARTING create_output_nodes()....")
        self.create_output_nodes()

        # Proceed with node creation and input setting
        print(f"\n\n\nDEBUG: STARTING _create_all_nodes()....")
        self._create_nodes_recursive(self.nodeinfo_list)
        print(f"DEBUG: {self.old_new_node_map=}")

        print(f"\n\n\nDEBUG: STARTING _set_node_inputs()....")
        print(f"DEBUG: {len(self.nodeinfo_list)=}, {type(self.nodeinfo_list)=}")
        self._set_node_inputs(self.nodeinfo_list)

        print(f"\n\n\nDEBUG: STARTING _set_output_connections()....")
        self._set_output_connections()



##############################################



def get_material_type(materialbuilder_node):
    """
    Args:
        materialbuilder_node (hou.VopNode): input material shading network, e.g., arnold materialbuilder
    Returns:
        (str): material type.
    """
    material_type = None

    if materialbuilder_node.type().name() == 'arnold_materialbuilder':
        material_type = 'arnold'
    elif materialbuilder_node.type().name() == 'subnet':
        for child_node in materialbuilder_node.children():
            if 'mtlx' in child_node.type().name():
                material_type = 'mtlx'
                break
    elif materialbuilder_node.type().name() == 'principledshader::2.0':
        material_type = 'principledshader'

    return material_type


def run(input_material_builder_node, target_context, target_renderer='mtlx'):
    """
    Run the material conversion process for the selected node.

    Args:
        input_material_builder_node (hou.Node): The selected Houdini shading network,
                                                e.g. arnold materialbuilder or mtlx materialbuilder.
        target_context (hou.Node): The target Houdini context node.
        target_renderer (str, optional): The target renderer (default is 'mtlx').
    """
    material_type = get_material_type(input_material_builder_node)
    if not material_type:
        raise Exception(f"Couldn't determine Input material type, currently only Arnold and MTLX supported!")

    print("NodeTraverser() START----------------------")
    traverser = NodeTraverser(material_type=material_type)
    nested_nodes_dict = traverser.traverse_children_nodes(input_material_builder_node)
    # print(f"DEBUG: nested_nodes_dict: ", pprint.pformat(nested_nodes_dict))
    print(f"DEBUG: traverser.output_nodes: ", pprint.pformat(traverser.output_nodes))
    print(f"DEBUG: material_type: ", material_type)
    print(f"DEBUG: input_material_builder_node: ", input_material_builder_node)
    print("NodeTraverser() Finished----------------------\n\n\n")


    print("NodeStandardizer() START----------------------")
    standardizer = NodeStandardizer(
        traverse_tree=nested_nodes_dict,
        output_nodes=traverser.output_nodes,
        material_type=material_type,
        input_material_builder_node=input_material_builder_node
    )
    print(f"DEBUG: {standardizer.node_info_list=}")
    print(f"DEBUG: {standardizer.standardized_output_nodes=}")
    print(f"DEBUG: {target_context=}")
    print(f"DEBUG: {target_renderer=}")
    print("NodeStandardizer() Finished----------------------\n\n\n")


    print("NodeRecreator() START----------------------")
    recreator = NodeRecreator(
        nodeinfo_list=standardizer.node_info_list,
        output_connections=standardizer.standardized_output_nodes,
        target_context=target_context,
        target_renderer=target_renderer
    )
    print("NodeRecreator() Finished----------------------\n\n\n")
    print(f"Material conversion complete. Converted material from '{material_type}' to '{target_renderer}'.")

    """
    TODO:
        - newly created mtlximage nodes need to have correct signature      [DONE]
        - mtlxrange isn't supported yet                                     [DONE]
    
    """









def test():
    """
    Test function to validate the node traversal, standardization, and recreation process.
    """
    # target_context = hou.node('/mat')
    target_renderer = 'mtlx'
    material_type = 'arnold'
    input_material_builder_node = 'arnold_materialbuilder1'

    output_nodes = {
        'surface':
            {'connected_node_index': 0,
             'connected_node_name': 'standard_surface1',
             'connected_node_path': '/mat/arnold_materialbuilder1/standard_surface1',
             'generic_type': 'GENERIC::output_surface',
             'node_name': 'OUT_material',
             'node_path': '/mat/arnold_materialbuilder1/OUT_material'
             }
    }

    node_tree = {'/mat/arnold_materialbuilder1/OUT_material': {'children': [{'child_node': {'children': [],
                                                                            'is_output_node': False,
                                                                            'node_name': 'standard_surface1',
                                                                            'node_path': '/mat/arnold_materialbuilder1/standard_surface1',
                                                                            'node_type': 'arnold::standard_surface',
                                                                            'output_type': None},
                                                             'input_index': 0,
                                                             'input_node_path': '/mat/arnold_materialbuilder1/standard_surface1'}],
                                               'is_output_node': True,
                                               'node_name': 'OUT_material',
                                               'node_path': '/mat/arnold_materialbuilder1/OUT_material',
                                               'node_type': 'arnold_material',
                                               'output_type': 'surface'}}

    standardizer = NodeStandardizer(
        traverse_tree=node_tree,
        output_nodes=output_nodes,
        material_type=material_type,
        input_material_builder_node=input_material_builder_node
    )
    print(f"DEBUG: {standardizer=}")





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



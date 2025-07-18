import tempfile
import pprint
from typing import Dict

from Material_Processor import utils_io
from Material_Processor.material_classes import NodeParameter, NodeInfo

###################################### CONSTANTS ######################################

TEMP_DIR = f"{tempfile.gettempdir()}/MaterialProcessorTemp"

REGULAR_NODE_TYPES_TO_GENERIC = {
    'arnold': {
        'nodes': {
            # arnold nodes:
            'arnold:standard_surface': 'GENERIC::standard_surface',
            'arnold:image': 'GENERIC::image',
            'arnold:range': 'GENERIC::range',
            'arnold:color_correct': 'GENERIC::color_correct',
            'arnold:curvature': 'GENERIC::curvature',
            'arnold:mix_rgba': 'GENERIC::mix_rgba',
            'arnold:mix_layer': 'GENERIC::mix_layer',
            'arnold:layer_rgba': 'GENERIC::layer_rgba',
            'arnold:ramp_rgb::2': 'GENERIC::ramp_rgb',
            'arnold:ramp_float::2': 'GENERIC::ramp_float',
            'arnold_material': 'GENERIC::output_node',
            'null': 'GENERIC::null',
        },
        'usd': {
            # arnold nodes:
            'arnold:standard_surface': 'GENERIC::standard_surface',
            'arnold:image': 'GENERIC::image',
            'arnold:range': 'GENERIC::range',
            'arnold:color_correct': 'GENERIC::color_correct',
            'arnold:curvature': 'GENERIC::curvature',
            'arnold:mix_rgba': 'GENERIC::mix_rgba',
            'arnold:mix_layer': 'GENERIC::mix_layer',
            'arnold:layer_rgba': 'GENERIC::layer_rgba',
            'arnold:ramp_rgb::2': 'GENERIC::ramp_rgb',
            'arnold:ramp_float::2': 'GENERIC::ramp_float',
            'arnold_material': 'GENERIC::output_node',
            'null': 'GENERIC::null',
        },
    },

    'mtlx': {
        'nodes': {
            'mtlxstandard_surface': 'GENERIC::standard_surface',
            'mtlximage': 'GENERIC::image',
            'mtlxrange': 'GENERIC::range',
            'mtlxcolorcorrect': 'GENERIC::color_correct',
            'mtlxmix': 'GENERIC::mix_rgba',  # it can be mix layer or mix RGBA, need specific methods to handle those niche cases.
            'mtlxdisplacement': 'GENERIC::displacement',
            'subnetconnector': 'GENERIC::output_node',
            'null': 'GENERIC::null',
        },
        'usd': {
            # mtlx usd prims infoId:
            'ND_standard_surface_surfaceshader': 'GENERIC::standard_surface',
            'ND_image_float': 'GENERIC::image',
            'ND_image_color3': 'GENERIC::image',
            'ND_colorcorrect_color3': 'GENERIC::color_correct',
            'ND_range_float': 'GENERIC::range',
            'ND_displacement_float': 'GENERIC::displacement',
        },
    },

    'rs_usd_material_builder': {
        'nodes': {
            'redshift::StandardMaterial': 'GENERIC::standard_surface',
            'redshift::TextureSampler': 'GENERIC::image',
            'redshift::Displacement': 'GENERIC::displacement',
            'redshift_material': 'GENERIC::output_node',
            'redshift_usd_material': 'GENERIC::shader_node',
            'null': 'GENERIC::null',
        },
        'usd': {
            'redshift::StandardMaterial': 'GENERIC::standard_surface',
            'redshift::TextureSampler': 'GENERIC::image',
            'redshift::Displacement': 'GENERIC::displacement',
            'redshift_material': 'GENERIC::output_node',
            'redshift_usd_material': 'GENERIC::shader_node',
            'null': 'GENERIC::null',
        },
    },

}


# 2) build *both* reverse maps automatically in one sweep
GENERIC_TO_RENDERER = {}
for renderer, profiles in REGULAR_NODE_TYPES_TO_GENERIC.items():
    GENERIC_TO_RENDERER[renderer] = {
        'nodes': { generic:specific
                   for specific, generic in profiles.get('nodes',{}).items() },
        'usd':   { generic:specific
                   for specific, generic in profiles.get('usd',{}).items() },
    }

# 3) a single little helper to pick which map you want:
def convert_generic(node_type: str,
                    target_renderer: str,
                    profile: str = 'nodes') -> str:
    """
    profile == 'nodes'  → VOP node‐type mapping
    profile == 'usd'    → USD‐prim info:id mapping
    """
    lookup = GENERIC_TO_RENDERER[target_renderer].get(profile, {})
    return lookup.get(node_type,
           lookup.get('GENERIC::null',''))


"""
standardization dict for parameters. {<orig_parm_name>: <generic_name>}. Any other node type will be filtered out.
"""
REGULAR_PARAM_NAMES_TO_GENERIC = {
    # mtlx parms
    'mtlxstandard_surface': {
        'base': 'base',
        'base_color': 'base_color',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'specular': 'specular',
        'specular_color': 'specular_color',
        'specular_roughness': 'specular_roughness',
        'specular_IOR': 'specular_IOR',
        'specular_anisotropy': 'specular_anisotropy',
        'specular_rotation': 'specular_rotation',
        'coat': 'coat',
        'coat_color':  'coat_color',
        'coat_roughness': 'coat_roughness',
        'transmission': 'transmission',
        'transmission_color': 'transmission_color',
        'transmission_extra_roughness': 'transmission_extra_roughness',
        'subsurface': 'subsurface',
        'subsurface_color': 'subsurface_color',
        'emission': 'emission',
        'emission_color': 'emission_color',
        'opacity': 'opacity',
        'normal': 'normal',
        'thin_walled': 'thin_walled',
    },
    'mtlximage': {
        'signature': 'signature',
        'file': 'filename',
    },
    'mtlxcolorcorrect': {
        'hue': 'hue',
        'saturation': 'saturation',
        'gamma': 'gamma',
        'lift': 'lift',
        'gain': 'gain',
        'contrast': 'contrast',
        'contrastpivot': 'contrastpivot',
        'exposure': 'exposure',
    },
    'mtlxrange': {
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outlow': 'outlow',
        'outhigh': 'outhigh',
    },
    'mtlxmix': {
        'signature': 'signature',
        'fg_color3r': 'fg_color3r',
        'fg_color3g': 'fg_color3g',
        'fg_color3b': 'fg_color3b',
        'bg_color3r': 'bg_color3r',
        'bg_color3g': 'bg_color3g',
        'bg_color3b': 'bg_color3b',
        'mix': 'mix',
    },
    'mtlxdisplacement': {
        'displacement': 'displacement',
        'scale': 'scale',
    },

    # mtlx prims infoId:
    'ND_standard_surface_surfaceshader': {
        'base': 'base',
        'base_color': 'base_color',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'specular': 'specular',
        'specular_color': 'specular_color',
        'specular_roughness': 'specular_roughness',
        'specular_IOR': 'specular_IOR',
        'specular_anisotropy': 'specular_anisotropy',
        'specular_rotation': 'specular_rotation',
        'coat': 'coat',
        'coat_color': 'coat_color',
        'coat_roughness': 'coat_roughness',
        'transmission': 'transmission',
        'transmission_color': 'transmission_color',
        'transmission_extra_roughness': 'transmission_extra_roughness',
        'subsurface': 'subsurface',
        'subsurface_color': 'subsurface_color',
        'emission': 'emission',
        'emission_color': 'emission_color',
        'opacity': 'opacity',
        'normal': 'normal',
        'thin_walled': 'thin_walled',
    },
    'ND_image_float': {
        'signature': 'signature',
        'file': 'filename',
    },
    'ND_range_float': {
        'in': 'in',
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outhigh': 'outhigh',
        'outlow': 'outlow',
    },
    'ND_range_color3': {
        'in': 'in',
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outhigh': 'outhigh',
        'outlow': 'outlow',
    },
    'ND_image_color3': {
        'signature': 'signature',
        'file': 'filename',
    },
    'ND_colorcorrect_color3': {
        'contrast': 'contrast',
        'contrastpivot': 'contrastpivot',
        'exposure': 'exposure',
        'gain': 'gain',
        'gamma': 'gamma',
        'hue': 'hue',
        'in': 'in',
        'lift': 'lift',
        'saturation': 'saturation',
    },
    'ND_displacement_float': {
        'displacement': 'displacement',
        'scale': 'scale',
    },



    # redshiftvopnet parms:
    'redshift:StandardMaterial': {
        'base_color_weight': 'base',
        'base_color': 'base_color',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'refl_weight': 'specular',
        'refl_color': 'specular_color',
        'refl_roughness': 'specular_roughness',
        'refl_ior': 'specular_IOR',
        'refl_aniso': 'specular_anisotropy',
        'refl_aniso_rotation': 'specular_rotation',
        'coat': 'coat',
        'coat_color': 'coat_color',
        'coat_roughness': 'coat_roughness',
        'refr_weight': 'transmission',
        'refr_color': 'transmission_color',
        'refr_roughness': 'transmission_extra_roughness',
        'ms_amount': 'subsurface',
        'ms_color': 'subsurface_color',
        'emission_weight': 'emission',
        'emission_color': 'emission_color',
        'opacity_color': 'opacity',
        # 'normal': 'normal',  # unsupported
        'refr_thin_walled': 'thin_walled',
    },
    'redshift:TextureSampler': {
        'tex0': 'filename',
    },
    'redshift:RSMathRange': {
        'in': 'in',
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outhigh': 'outhigh',
        'outlow': 'outlow',
    },
    'redshift:RSColorRange': {
        'in': 'in',
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outhigh': 'outhigh',
        'outlow': 'outlow',
    },
    'redshift:RSColorCorrection': {
        'contrast': 'contrast',
        'contrastpivot': 'contrastpivot',
        'exposure': 'exposure',
        'gain': 'gain',
        'gamma': 'gamma',
        'hue': 'hue',
        'in': 'in',
        'lift': 'lift',
        'saturation': 'saturation',
    },
    'redshift:Displacement': {
        # 'displacement': 'displacement',
        'scale': 'scale',
    },



    # arnold parms:
    'arnold:standard_surface': {
        'base': 'base',
        'base_color': 'base_color',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'specular': 'specular',
        'specular_color': 'specular_color',
        'specular_roughness': 'specular_roughness',
        'specular_IOR': 'specular_IOR',
        'specular_anisotropy': 'specular_anisotropy',
        'specular_rotation': 'specular_rotation',
        'transmission': 'transmission',
        'transmission_color': 'transmission_color',
        'transmission_extra_roughness': 'transmission_extra_roughness',
        'coat': 'coat',
        'coat_color': 'coat_color',
        'coat_roughness': 'coat_roughness',
        'subsurface': 'subsurface',
        'subsurface_color': 'subsurface_color',
        'emission': 'emission',
        'emission_color': 'emission_color',
        'opacity': 'opacity'
    },
    'arnold:image': {
        'filename': 'filename'
    },
    'arnold:color_correct': {
        'gamma': 'gamma',
        'hue_shift': 'hue',
        'saturation': 'saturation',
        'contrast': 'contrast',
        'contrast_pivot': 'contrastpivot',
        'exposure': 'exposure',
        'multiply': 'multiply',
        'add': 'add',
    },
    'arnold:range': {
        'input_min': 'inlow',
        'input_max': 'inhigh',
        'output_min': 'outlow',
        'output_max': 'outhigh',
        'contrast': 'contrast',
        'contrast_pivot': 'contrastpivot',
        'bias': 'bias',
        'gain': 'gain',
    },
    'arnold:mix_rgba': {
        # 'signature': 'signature',
        'input1r': 'fg_color3r',
        'input1g': 'fg_color3g',
        'input1b': 'fg_color3b',
        'input2r': 'bg_color3r',
        'input2g': 'bg_color3g',
        'input2b': 'bg_color3b',
        'mix': 'mix',
    },
    'arnold:curvature': {
        'output': 'output',
        'radius': 'radius',
        'spread': 'spread',
        'threshold': 'threshold',
        'bias': 'bias',
    },




    # principled shader 2.0:
    'principledshader:2.0': {
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
        'coatcolor': 'coat_color',
    }
}






class NodeStandardizer:
    """
    Class for standardizing Shader nodes and creating MaterialData Class.
    """

    def __init__(self, traversed_nodes_dict, output_nodes_dict, material_type):
        """
        Initialize the NodeStandardizer with the traverse tree and output nodes.

        Args:
            traversed_nodes_dict (Dict): The nested node dictionary from NodeTraverser.
            output_nodes_dict (Dict): The detected output nodes from NodeTraverser.
            material_type (str): The type of material (e.g., 'arnold', 'mtlx', 'principledshader').
        """
        self.traversed_nodes_dict = traversed_nodes_dict
        self.output_nodes_dict = output_nodes_dict
        self.material_type = material_type

        utils_io.dump_dict_to_json(self.traversed_nodes_dict, f"{TEMP_DIR}/traversed_nodes_dict.json")
        utils_io.dump_dict_to_json(self.output_nodes_dict, f"{TEMP_DIR}/output_nodes_dict.json")

        # self.run()



    @staticmethod
    def standardize_output_dict(output_nodes_dict):
        """
        Standardize a dictionary of output node connection metadata.

        Args:
            output_nodes_dict (Dict[str, Dict[str, Any]]): A dictionary where each key is an output identifier and its value is a dictionary containing connection details:
                - 'node_path': The path to the node.
                - 'connected_node_name': The name of the connected node.
                - 'connected_node_path': The path to the connected node.
                - 'connected_input_index': The input index for the connection.

        Returns:
            Dict[str, Dict[str, Any]]: A new dictionary with each output identifier prefixed with "GENERIC::output_", preserving the original connection details.
        """
        output_connections = {}
        for key, value in output_nodes_dict.items():
            standardized_key = f"GENERIC::output_{key}"
            output_connections[standardized_key] = {
                'node_name': value['node_name'],
                'node_path': value['node_path'],
                'connected_node_name': value['connected_node_name'],
                'connected_node_path': value['connected_node_path'],
                'connected_input_index': value.get('connected_input_index'),
                'connected_input_name': value['connected_input_name'],
                'connected_output_name': value['connected_output_name'],
            }
        return output_connections


    @staticmethod
    def standardize_shader_parameters(node_type, parms):
        """
        Filter and standardize parameters for a given node.

        Args:
            node_type (str): The type of the Houdini node.
            parms (Dict(List[Dict[str, Any]])): The Parameter Dictionary to be standardized.

        Returns:
            List[NodeParameter]: A list of filtered and standardized node parameters.
        """
        _unsupported_parms_list = []
        _parms_with_no_generic_name_list = []
        _parms_with_no_mapping = []
        generic_parm_names_dict = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type.replace('::', ':'))
        if not generic_parm_names_dict:
            print(f"WARNING: No generic parameters mapping was found for nodetype: '{node_type}'.")
            _parms_with_no_mapping.append(node_type)
            return []

        nodeParameter_list = []
        for param in parms['input']:
            generic_name = generic_parm_names_dict.get(param['generic_name'], None)
            if not generic_name:
                # print(f"WARNING: No generic name was found for parameter: '{param['generic_name']}' for node_type: '{node_type}'")
                _unsupported_parms_list.append(param['generic_name'])
                _parms_with_no_generic_name_list.append(param['generic_name'])
                # print(f"DEBUG: generic_parm_names_dict: {pprint.pformat(generic_parm_names_dict, sort_dicts=False)}")
                continue

            value = param['value']
            if isinstance(value, tuple) and len(value) == 1:
                value = value[0]

            nodeParameter_list.append(NodeParameter(
                generic_name=generic_name,
                generic_type=param['type'],
                direction=param['direction'],
                value=value,
            ))

        for param in parms['output']:
            generic_name = generic_parm_names_dict.get(param['generic_name'], None)
            if not generic_name:
                # print(f"WARNING: No generic name was found for parameter: '{param['generic_name']}' for node_type: '{node_type}'")
                _unsupported_parms_list.append(param['generic_name'])
                _parms_with_no_generic_name_list.append(param['generic_name'])
                continue

            value = param['value']
            if isinstance(value, tuple) and len(value) == 1:
                value = value[0]

            nodeParameter_list.append(NodeParameter(
                generic_name=generic_name,
                generic_type=param['type'],
                direction=param['direction'],
                value=value,
            ))

        if _unsupported_parms_list:
            print(f"WARNING: Unsupported parameters for node type '{node_type}': {_unsupported_parms_list}")
        if _parms_with_no_generic_name_list:
            print(f"WARNING: Parameters with no generic name mapping for node type '{node_type}': {_parms_with_no_generic_name_list}\n")

        return nodeParameter_list

    def create_nodeinfo_object(self, node_path, child_dict):
        """
        Create a NodeInfo object from a NodeTraverser dictionary.

        Args:
            node_path (str): The Houdini node path.
            child_dict (dict): The Houdini node path.
        Returns:
            NodeInfo: The created NodeInfo object.

        Example:
            >>> node_path='/mat/arnold_materialbuilder_basic/OUT_material'
            >>> child_dict={
                     'node_name': 'image_roughness',
                     'node_path': '/mat/arnold_materialbuilder_basic/image_roughness',
                     'node_type': 'arnold::image',
                     'node_parms': []
                                 }

            >>> node_info_obj = self.create_nodeinfo_object(node_path='/mat/arnold_materialbuilder_basic/OUT_material', child_dict=child_dict)

        """
        is_output_node = child_dict.get('is_output_node', False)
        output_type = child_dict.get('output_type', None)

        connection_info = child_dict.get('connections_dict', {})

        child_node_name: str = child_dict['node_name']
        child_node_type: str = child_dict['node_type']
        child_node_parms: list = child_dict.get('node_parms')
        child_node_pos: list[float, float] = child_dict.get('node_position')
        # print(f"DEBUG: parms for node: '{node_path}': {child_node_parms}")

        parameters = None
        if child_node_parms:
            parameters = self.standardize_shader_parameters(child_node_type, child_node_parms)

        generic_node_type = REGULAR_NODE_TYPES_TO_GENERIC[self.material_type]['nodes'].get(child_node_type)
        if not generic_node_type:
            generic_node_type = REGULAR_NODE_TYPES_TO_GENERIC[self.material_type]['usd'].get(child_node_type)
        if not generic_node_type:
            print(f"WARNING: No generic type was found for node type: '{child_node_type}'")

        return NodeInfo(
            node_type=generic_node_type,
            node_name=child_node_name,
            node_path=node_path,
            parameters=parameters,
            connection_info=connection_info,
            children_list=[],
            is_output_node=is_output_node,
            output_type=output_type if is_output_node else generic_node_type,
            position=child_node_pos
        )

    def standardize_node_dict(self, node_dict: Dict):
        """
        Recursively traverse the node dictionary and create a list of NodeInfo objects.

        Args:
            node_dict (Dict): The node dictionary to traverse.

        Returns:
            List[NodeInfo]: A list of NodeInfo objects.
        """
        nodeinfo_list = []

        for node_path, node_dict in node_dict.items():
            nodeinfo = self.create_nodeinfo_object(node_path, node_dict)
            # print(f"DEBUG: node_info_obj connections: {nodeinfo.print_connections()}")

            # Process children
            children_list = node_dict.get('children_list', [])
            for child_entry in children_list:
                child_node_path: str = child_entry['node_path']

                # Recursively traverse child nodes
                child_nodes_info = self.standardize_node_dict({child_node_path: child_entry})

                nodeinfo.children_list.extend(child_nodes_info)

            nodeinfo_list.append(nodeinfo)
        # print(f"DEBUG: {len(nodeinfo_list)=}")
        return nodeinfo_list

    def run(self):
        """
        Standardizes output nodes and processes node information list based on a tree traversal.
        This method performs the following:
            1. Standardizes the given output nodes.
            2. Processes the node information list by standardizing node data based on traversal
               logic.
            3. Returns a tuple containing the standardized output nodes and the standardized
               node information list.

        Returns:
            ([NodeInfo], dict): A tuple containing the standardized output nodes and the standardized
                 node information list.


        """
        nodeinfo_list = self.standardize_node_dict(self.traversed_nodes_dict)
        standardized_output_nodes_dict = self.standardize_output_dict(self.output_nodes_dict)
        return nodeinfo_list, standardized_output_nodes_dict

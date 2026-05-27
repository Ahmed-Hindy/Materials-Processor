"""Recreate generic material graphs as Houdini shader networks."""

import logging
from typing import List

from materials_processor.mappings import REGULAR_PARAM_NAMES_TO_GENERIC, convert_generic
from materials_processor.models import NodeInfo, NodeParameter
from materials_processor.houdini.traverser import hou

logger = logging.getLogger(__name__)

###################################### CONSTANTS ######################################
OUTPUT_CONNECTIONS_INDEX_MAP = {
    'arnold': {
        'GENERIC::output_surface': 0,
        'GENERIC::output_displacement': 1
    },
    'mtlx': {
        'GENERIC::output_surface': 0,
        'GENERIC::output_displacement': 0
    },
    'rs_usd_material_builder': {
        'GENERIC::output_surface': 0,
        'GENERIC::output_displacement': 1
    },
}

##########################################################################################

class NodeRecreator:
    """
    Class for recreating Houdini nodes in a target renderer context.
    """

    def __init__(self, nodeinfo_list, output_connections, target_context,
                 target_renderer='arnold', material_name=None):
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
        self.material_name = material_name
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

    @staticmethod
    def create_mtlx_init_shader(matnet=None, material_name=None):
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
        if not material_name:
            material_name = 'mtlxmaterial'
        folder_label = 'MaterialX Builder'
        render_context = 'mtlx'

        if not matnet:
            matnet = hou.node('/mat')

        subnet_node = matnet.createNode('subnet', material_name)
        subnet_node = voptoolutils._setupMtlXBuilderSubnet(subnet_node=subnet_node, name=material_name, mask=MTLX_TAB_MASK,
                                                           folder_label=folder_label, render_context=render_context)

        subnet_node.node('mtlxstandard_surface').destroy()
        subnet_node.node('inputs').destroy()

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
            logger.warning("mtlx separate3c node currently only supports splitting of 'r','g','b' channels, "
                           "but instead it got a '%s'", src_out_parm_name)
            return False, None
        if dest_in_index is None:
            logger.warning("dest_in_index is None '%s', but it should be an integer, src_node: '%s'", dest_in_index, src_node.name())
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
            logger.info("created split node for '%s' to '%s' for '%s'", src_node.name(), dest_node.name(), src_out_parm_name)
            return True, vec3_split_node

        except Exception as e:
            logger.error("create_mtlx_vec3_split_node, dest_in_index=%s, vec3_split_node=%s, out_index=%s, error: %s", dest_in_index, vec3_split_node, out_index, e)
            return False, None

    @staticmethod
    def create_arnold_init_shader(matnet=None, material_name=None):
        """
        Create an initial Arnold shader in the specified network.

        Args:
            matnet (hou.Node, optional): The Houdini network node.

        Returns:
            Tuple[hou.Node, Dict]: The created Arnold shader node and output nodes.
        """
        if not matnet:
            matnet = hou.node('/mat')
        if not material_name:
            material_name = 'arnold_materialbuilder'

        node_material_builder = matnet.createNode('arnold_materialbuilder', material_name)
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
    def create_principledshader_init_shader(matnet=None, material_name=None):
        """
        Create an initial principledshader shader in the specified network.

        Args:
            matnet (hou.Node, optional): The Houdini Material Network.

        Returns:
            Tuple[hou.Node, Dict]: The created Arnold shader node and output nodes.
        """
        if not matnet:
            matnet = hou.node('/mat')
        if not material_name:
            material_name = 'principledshader::2.0'

        node_material_builder = matnet.createNode('principledshader::2.0', material_name)
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
    def create_rs_usd_material_builder_init_shader(matnet=None, material_name=None):
        """
        Create an initial rs_usd_material_builder shader in the specified network.

        Args:
            matnet (hou.Node, optional): The Houdini network node.

        Returns:
            Tuple[hou.Node, Dict]: The created rs_usd_material_builder shader node and output nodes.
        """
        if not matnet:
            matnet = hou.node('/mat')
        if not material_name:
            material_name = 'rs_usd_material_builder'

        subnet_node = matnet.createNode('rs_usd_material_builder', material_name)

        subnet_node.node('StandardMaterial1').destroy()
        subnet_node.node('subinput1').destroy()

        output_nodes = {
            'GENERIC::output_surface': {'node': subnet_node.node('redshift_usd_material1'),
                                        'node_name': subnet_node.node('redshift_usd_material1').name(),
                                        'node_path': subnet_node.node('redshift_usd_material1').path(),
                                        },
            'GENERIC::output_displacement': {'node': subnet_node.node('redshift_usd_material1'),
                                             'node_name': subnet_node.node('redshift_usd_material1').name(),
                                             'node_path': subnet_node.node('redshift_usd_material1').path(),
                                             },
        }
        return subnet_node, output_nodes

    def create_init_shader(self, material_name=None):
        if not material_name:
            material_name = 'convertedMaterial'

        if self.target_renderer == 'mtlx':
            self.material_node, self.new_output_connections = self.create_mtlx_init_shader(self.target_context, material_name)
        elif self.target_renderer == 'arnold':
            self.material_node, self.new_output_connections = self.create_arnold_init_shader(self.target_context, material_name)
        elif self.target_renderer == 'principledshader':
            self.material_node, self.new_output_connections = self.create_principledshader_init_shader(self.target_context, material_name)
        elif self.target_renderer == 'rs_usd_material_builder':
            self.material_node, self.new_output_connections = self.create_rs_usd_material_builder_init_shader(self.target_context, material_name)
        else:
            raise KeyError(f"Unsupported target renderer: {self.target_renderer}")

        self.material_node.moveToGoodPosition()


    def create_output_nodes(self):
        """
        Create or reuse output nodes in the target context.
        """
        if self.target_renderer == 'principledshader':
            logger.debug("PrincipledShader does not require explicit output nodes. Skipping creation.")
            return

        for generic_output_type, output_connection in self.orig_output_connections.items():
            # e.g. generic_output_type = "GENERIC::output_surface"
            # e.g. output_info         = {'node_path': '/mat/material_mtlx_ORIG/surface_output',
            #                             'node_name': 'surface_output', ???
            #                             'connected_node_name': 'surface_output',
            #                             'connected_input_index': 0}

            new_output_nodename = self.new_output_connections.get(generic_output_type, {}).get('node_name')
            new_output_nodepath = f"{self.material_node.path()}/{new_output_nodename}"

            created_output_node: hou.VopNode = hou.node(new_output_nodepath)


            self.old_new_node_map[output_connection.node_path] = {'node_name': created_output_node.name(),
                                                                  'node_path': created_output_node.path(),
                                                                  'is_output': True,
                                                                  'output_type': generic_output_type,
                                                                  }

            self.new_output_connections[generic_output_type] = {'node': created_output_node,
                                                                'node_name': created_output_node.name(),
                                                                'node_path': created_output_node.path(),
                                                                'connected_node_name': output_connection.connected_node_name,
                                                                'connected_input_index': output_connection.connected_input_index,
                                                                'connected_input_name': output_connection.connected_input_name,
                                                                'connected_output_name': output_connection.connected_output_name,
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
        if not node_type:
            node_type = 'GENERIC::null'

        new_node_type = convert_generic(
            node_type=node_type,
            target_renderer=target_renderer,
            profile='hou_vop_nodes'
        )

        return new_node_type

    @staticmethod
    def _apply_parameters(node, parameters):
        """
        Apply parameters to a Houdini node.

        Args:
            node (hou.Node): The Houdini node.
            parameters (List[NodeParameter]): The list of parameters to apply.
        """
        if not parameters:
            logger.info("No parameters to apply to '%s'.", node.path())
            return

        node_type = node.type().name()
        std_parm_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type.replace('::', ':'), {})
        if not std_parm_map:
            logger.warning("No generic parameter mappings found for node type: '%s'", node_type)
            return

        for param in parameters:
            if param.direction != 'input':
                logger.warning("Parameter '%s' is not an input parameter for node type '%s'. Skipping.", param.generic_name, node_type)
                continue
            if not param.generic_name:
                logger.warning("Parameter of value:'%s' has no generic_name for node type '%s'. Skipping.", param.value, node_type)
                continue

            # Find the renderer-specific parameter name
            parm_new_name = [key for key, val in std_parm_map.items() if val == param.generic_name]

            if not parm_new_name:
                logger.warning("No renderer-specific parameter found for generic name '%s' for node type '%s'. Skipping.", param.generic_name, node_type)
                continue

            parm_new_name = parm_new_name[0]
            hou_parm = node.parmTuple(parm_new_name)
            # print(f"DEBUG: {hou_parm.name()=}, {param.value=}")
            if hou_parm is None:
                logger.warning("Parm '%s' not found on node '%s'.", parm_new_name, node.path())
                continue

            if not isinstance(param.value, tuple):
                param.value = (param.value,)

            try:
                hou_parm.set(param.value)
            except Exception as e:
                logger.error("Failed to set parameter '%s' for node '%s': %s", param.generic_name, node.path(), e)
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
        new_node_type = self._convert_generic_node_type_to_renderer_node_type(node_type=node_info.node_type,
                                                                              target_renderer=self.target_renderer)

        # Check for existing nodes of the same type to reuse
        existing_nodes = [node for node in self.material_node.children() if
                          node.type().name() == new_node_type and node not in self.reused_nodes.values()]
        if existing_nodes:
            node = existing_nodes[0]
            logger.info("Using existing node: %s of type %s", node.path(), node.type().name())
            self._apply_parameters(node, node_info.parameters)
            self.reused_nodes[node_info.node_path] = node
            self.old_new_node_map[node_info.node_path] = {'node_name': node.name(),
                                                          'node_path': node.path()}

            return node

        # Create new node if no reusable node is found
        logger.debug("Creating node: new_node_type=%s, node_name=%s", new_node_type, node_info.node_name)
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
        if self.target_renderer == 'principledshader':
            logger.debug("PrincipledShader does not require explicit output nodes. Skipping creation.")
            return

        self._create_nodes_recursive(nested_nodes_info)
        return True


    def set_output_connections(self):
        """
        Set connections for the output nodes in the recreated material.
        """
        if self.target_renderer == 'principledshader':
            logger.debug("PrincipledShader does not require explicit output nodes. Skipping creation.")
            return

        renderer_output_connections = OUTPUT_CONNECTIONS_INDEX_MAP.get(self.target_renderer)
        if not renderer_output_connections:
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

        for generic_output_type, output_info in self.new_output_connections.items():
            output_index = renderer_output_connections[generic_output_type]
            output_node = output_info['node']

            if generic_output_type not in renderer_output_connections:
                raise KeyError(f"{generic_output_type=} not found in {renderer_output_connections=}")

            # e.g. generic_output_type= 'GENERIC::output_surface'
            # e.g. self.orig_output_connections: {'GENERIC::output_surface': {'node_name': 'principledshader',
            #                              'node_path': '/mat/principledshader',
            #                              'connected_node_name': '',
            #                              'connected_node_path': '',
            #                              'connected_input_index': 0}}

            # e.g. self.old_new_node_map: {'/mat/arnold_materialbuilder1/OUT_material': {'node_name': 'OUT_material',
            #                                                          'node_path': '/mat/arnold_materialbuilder2/OUT_material'},
            #       '/mat/arnold_materialbuilder1/standard_surface1': {'node_name': 'standard_surface1',
            #                                                          'node_path': '/mat/arnold_materialbuilder2/standard_surface1'},
            #       '/mat/arnold_materialbuilder1/image_diffuse': {'node_name': 'image_diffuse',
            #                                                      'node_path': '/mat/arnold_materialbuilder2/image_diffuse'}}

            # e.g. connected_node_info: {
            #       'node_name': 'OUT_material',
            #       'node_path': '/mat/arnold_materialbuilder1/OUT_material',
            #       'connected_node_name': 'standard_surface1',
            #       'connected_node_path': '/mat/arnold_materialbuilder1/standard_surface1',
            #       'connected_input_index': 0
            #       }

            # Find the connected node info from the nodeinfo_list output connections
            new_connected_node_info = self.new_output_connections[generic_output_type]
            # print(f"DEBUG: new_connected_node_info: {pprint.pformat(new_connected_node_info, sort_dicts=False)}")

            if not new_connected_node_info:
                continue

            new_connected_node: hou.VopNode = self.material_node.node(new_connected_node_info.get('connected_node_name'))
            if not new_connected_node:
                logger.warning("Connections for node:'%s' not found!", new_connected_node_info['node_name'])
                continue
            if new_connected_node.type().name() == 'null':
                logger.warning("Ignoring Output connections from input null node: '%s'", new_connected_node_info['node_name'])
                continue

            logger.info("Setting input for %s[%s] to '%s[0]' for output type: '%s'", output_node.path(), output_index, new_connected_node.path(), generic_output_type)
            output_node.setInput(output_index, new_connected_node)

        return True


    def _get_new_node_from_nodeinfo(self, node_info):
        """
        Find the newly-created Houdini node corresponding to node_info.
        """
        old_path = node_info.node_path
        mapping = self.old_new_node_map.get(old_path, {})
        new_path = mapping.get('node_path')
        if not new_path:
            logger.warning("Couldn't find new node for '%s'.", old_path)
            return None

        node = hou.node(new_path)
        if not node:
            logger.warning("New node path '%s' does not exist in the scene.", new_path)
            return None

        return node

    def _process_connections_for_node(self, src_nodeinfo, dest_node):
        """
        Iterate all connections for one node and wire them up (skipping output nodes).
        """
        for conn in src_nodeinfo.connection_info.values():
            # print(f"DEBUG: ///conn: {pprint.pformat(conn, sort_dicts=False)}")
            logger.debug("connecting src node: '%s[%s][%s]' to dest node: '%s[%s][%s]'", src_nodeinfo.node_name, conn.input.node_index, conn.input.parm_name, dest_node.name(), conn.output.node_index, conn.output.parm_name)
            src_node_name = conn.input.node_name
            src_parm_name = conn.input.parm_name
            dest_node_name = conn.output.node_name
            dest_parm_name = conn.output.parm_name
            dest_node_type = dest_node.type().name()
            src_node_type = conn.input.node_type

            # find the source (input) node
            src_node = self._get_input_node(src_node_name)
            if not src_node:
                continue

            # skip wiring if this is one of our designated outputs
            if self._is_output_node(dest_node.name()):
                logger.warning("Skipping connection for '%s -> %s' (it's an output node).", dest_node_name, dest_node.name())
                continue

            # look up the standardized parameter names to use for the connection:
            src_std_parm_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(src_node_type.replace('::', ':'), {})
            dest_std_parm_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(dest_node_type.replace('::', ':'), {})

            src_parm_new_name = [key for key, val in src_std_parm_map.items() if val == src_parm_name]
            src_parm_new_name: str = src_parm_new_name[0] if src_parm_new_name else src_parm_name
            dest_parm_new_name = [key for key, val in dest_std_parm_map.items() if val == dest_parm_name]
            dest_parm_new_name: str = dest_parm_new_name[0] if dest_parm_new_name else dest_parm_name

            # print(f"DEBUG: // {src_node_type=}, {dest_node_type=}")
            # print(f"DEBUG: // src_std_parm_map: {pprint.pformat(src_std_parm_map, sort_dicts=False)}")
            # print(f"DEBUG: // dest_std_parm_map: {pprint.pformat(dest_std_parm_map, sort_dicts=False)}")
            # print(f"DEBUG: // {src_parm_name=}, {dest_parm_name=}")
            # print(f"DEBUG: // {src_parm_new_name=}, {dest_parm_new_name=}")


            # perform the actual wire
            self._connect_pair(
                src_node=src_node,
                dest_node=dest_node,
                src_parm=src_parm_new_name,
                dest_parm=dest_parm_new_name,
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
            logger.warning("Input node '%s' not found at '%s'.", node_name, path)
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
        if not dest_idx:
            dest_idx = 0
            dest_idx_by_name = dest_node.inputIndex(dest_parm)
            if dest_idx_by_name not in [-1, -999]:
                dest_idx = dest_idx_by_name
            else:
                logger.warning("dest: '%s' has no parm: '%s', using provided index: %s.", dest_node.name(), dest_parm, dest_idx)

        if not src_idx:
            src_idx = 0
            src_idx_by_name = src_node.outputIndex(src_parm)
            if src_idx_by_name not in [-1, -999]:
                src_idx = src_idx_by_name
            else:
                logger.warning("src: '%s' has no parm: '%s', using provided index: %s.", src_node.name(), src_parm, src_idx)


        # if it's a node that needs splitting, we split the channels
        if src_node.type().name() in ['mtlximage', 'mtlxrange', 'mtlxcolorcorrect'] and src_parm not in ['rgb', 'rgba', 'out', 'outColor']:
            check, _ = self.create_mtlx_vec3_split_node(src_node=src_node, dest_node=dest_node,
                                                        src_out_parm_name=src_parm, dest_in_index=dest_idx)
            return check


        try:
            dest_node.setInput(dest_idx, src_node, src_idx)
            logger.info("Connected '%s'[%s] -> '%s'[%s].", src_node.name(), src_idx, dest_node.name(), dest_idx)
            return True
        except Exception as e:
            logger.warning("Failed to connect '%s[%s]' -> '%s[%s]': %s", src_node.name(), src_idx, dest_node.name(), dest_idx, e)
            return False

    def set_node_connections(self, nodeinfo_list, parent_node=None):
        """
        Top-level entry: recurse over a list of NodeInfo and wire them up.
        """
        if not nodeinfo_list:
            logger.warning("Empty node list, nothing to connect.")
            return

        for i, node_info in enumerate(nodeinfo_list):
            current_node = parent_node or self._get_new_node_from_nodeinfo(node_info)
            if not current_node:
                continue

            if not node_info.connection_info:
                logger.warning("'%s': No Input Connections found. Skipping.", current_node.name())
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
        self.create_init_shader(self.material_name)
        # print(f"{self.material_node=}, {self.standardizer.output_nodes_dict=}, {self.new_output_connections=}")

        # Create output nodes first:
        logger.info("STARTING create_output_nodes()....")
        self.create_output_nodes()
        logger.info("DONE create_output_nodes()....")

        # Create Child nodes:
        logger.info("STARTING create_shader_nodes()....")
        self.create_shader_nodes(self.nodeinfo_list)
        logger.info("DONE create_shader_nodes()....")

        # connect child nodes to each other:
        logger.info("STARTING _set_node_inputs()....")
        self.set_node_connections(self.nodeinfo_list)
        logger.info("DONE _set_node_inputs()....")

        # connect output nodes to child nodes:
        logger.info("STARTING _set_output_connections()....")
        self.set_output_connections()
        logger.info("DONE _set_output_connections()....")







##############################################




"""Standardize traversed material graphs into generic node descriptions."""

import logging
import pprint
import tempfile
from dataclasses import replace
from typing import Dict

from materials_processor import io
from materials_processor.mappings import (
    PRINCIPLED_DISPLACEMENT_INPUT,
    PRINCIPLED_NATIVE_NODE_TYPE,
    PRINCIPLED_NORMAL_INPUT,
    PRINCIPLED_TEXTURE_INPUTS,
    REGULAR_NODE_TYPES_TO_GENERIC,
    REGULAR_PARAM_NAMES_TO_GENERIC,
    STANDARDIZER_SUPPORTED_SOURCE_TYPES,
)
from materials_processor.core.graph import ConnectionEndpoint, NodeConnection, NodeInfo, NodeParameter, OutputConnection

logger = logging.getLogger(__name__)

TEMP_DIR = f"{tempfile.gettempdir()}/MaterialProcessorTemp"


def _is_truthy(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return bool(value)


def _as_scalar(value):
    """
    Convert a single-element list or tuple to its contained value.
    
    Parameters:
        value: The value to convert.
    
    Returns:
        The contained element for a single-element list or tuple; otherwise, the original value.
    """
    if isinstance(value, (list, tuple)) and len(value) == 1:
        return value[0]
    return value


class NodeStandardizer:
    """
    Class for standardizing Shader nodes and creating MaterialData Class.
    """

    def __init__(self, traversed_nodes_dict, output_nodes_dict, material_type, source_type):
        """
        Initialize a standardizer for traversed material nodes and detected output nodes.
        
        Parameters:
            traversed_nodes_dict (dict): Nested node data produced by node traversal.
            output_nodes_dict (dict): Detected output node data produced by node traversal.
            material_type (str): Material type being standardized.
            source_type (str): Source type of the traversed nodes.
        
        Raises:
            ValueError: If `source_type` is not supported.
        """
        self.traversed_nodes_dict = traversed_nodes_dict
        self.output_nodes_dict = output_nodes_dict
        self.material_type = material_type
        self.source_type = source_type
        if source_type not in STANDARDIZER_SUPPORTED_SOURCE_TYPES:
            raise ValueError(
                f"Unsupported source_type: {source_type}. Supported types are {STANDARDIZER_SUPPORTED_SOURCE_TYPES}."
            )

        io.dump_dict_to_json(self.traversed_nodes_dict, f"{TEMP_DIR}/traversed_nodes_dict.json")
        io.dump_dict_to_json(self.output_nodes_dict, f"{TEMP_DIR}/output_nodes_dict.json")

        # self.run()

    @staticmethod
    def standardize_output_dict(output_nodes_dict):
        """
        Standardize output node connection metadata.
        
        Parameters:
        	output_nodes_dict (dict): Mapping of output identifiers to connection metadata.
        
        Returns:
        	dict: Mapping of prefixed output identifiers to `OutputConnection` objects.
        """
        output_connections = {}
        for key, value in output_nodes_dict.items():
            standardized_key = f"GENERIC::output_{key}"
            output_connections[standardized_key] = OutputConnection.from_mapping(value)
        return output_connections

    @staticmethod
    def standardize_shader_parameters(node_type, parms):
        """
        Standardize a node's input and output parameters using its generic parameter mapping.
        
        Parameters:
            node_type (str): The node type whose parameter mapping should be applied.
            parms (dict): Mappings containing the node's input and output parameters.
        
        Returns:
            list[NodeParameter]: The supported parameters with generic names and scalar values.
        """
        _unsupported_parms_list = []
        _parms_with_no_generic_name_list = []
        _parms_with_no_mapping = []
        generic_parm_names_dict = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type.replace("::", ":"))
        preserve_unmapped = node_type == PRINCIPLED_NATIVE_NODE_TYPE
        if not generic_parm_names_dict:
            logger.warning("No generic parameters mapping was found for nodetype: '%s'.", node_type)
            _parms_with_no_mapping.append(node_type)
            if not preserve_unmapped:
                return []
            generic_parm_names_dict = {}

        nodeParameter_list = []
        for param in parms["input"]:
            generic_name = generic_parm_names_dict.get(param["generic_name"], None)
            if not generic_name and preserve_unmapped:
                generic_name = param["generic_name"]
            if not generic_name:
                # print(f"WARNING: No generic name was found for parameter: '{param['generic_name']}' for node_type: '{node_type}'")
                _unsupported_parms_list.append(param["generic_name"])
                _parms_with_no_generic_name_list.append(param["generic_name"])
                # print(f"DEBUG: generic_parm_names_dict: {pprint.pformat(generic_parm_names_dict, sort_dicts=False)}")
                continue

            value = param["value"]
            if isinstance(value, (list, tuple)) and len(value) == 1:
                value = value[0]

            nodeParameter_list.append(
                NodeParameter(
                    generic_name=generic_name,
                    generic_type=param["type"],
                    direction=param["direction"],
                    value=value,
                )
            )

        for param in parms["output"]:
            generic_name = generic_parm_names_dict.get(param["generic_name"], None)
            if not generic_name and preserve_unmapped:
                generic_name = param["generic_name"]
            if not generic_name:
                # print(f"WARNING: No generic name was found for parameter: '{param['generic_name']}' for node_type: '{node_type}'")
                _unsupported_parms_list.append(param["generic_name"])
                _parms_with_no_generic_name_list.append(param["generic_name"])
                continue

            value = param["value"]
            if isinstance(value, (list, tuple)) and len(value) == 1:
                value = value[0]

            nodeParameter_list.append(
                NodeParameter(
                    generic_name=generic_name,
                    generic_type=param["type"],
                    direction=param["direction"],
                    value=value,
                )
            )

        if _unsupported_parms_list:
            logger.warning("Unsupported parameters for node type '%s': %s", node_type, _unsupported_parms_list)
        if _parms_with_no_generic_name_list:
            logger.warning(
                "Parameters with no generic name mapping for node type '%s': %s",
                node_type,
                _parms_with_no_generic_name_list,
            )

        return nodeParameter_list

    def standardize_connection_info(self, connections_dict):
        """
        Standardize connection endpoints by mapping source parameter names to generic names.
        
        Parameters:
            connections_dict (dict): Connection mappings keyed by connection identifier.
        
        Returns:
            dict: Connection mappings containing standardized endpoint parameter names. Endpoints without a node-type or parameter mapping retain their original names.
        """
        if not connections_dict:
            return {}

        # logger.debug("connections_dict: %s", pprint.pformat(connections_dict, sort_dicts=False))
        _unsupported_parms_list = []
        _parms_with_no_generic_name_list = []
        _parms_with_no_mapping = []
        nodeParameter_list = []
        new_connections_dict = {}

        for i, connection_dict in connections_dict.items():
            connection = NodeConnection.from_mapping(connection_dict)
            endpoints = {}
            for direction in connection:
                endpoint: ConnectionEndpoint = connection[direction]

                node_type = endpoint.node_type
                generic_parm_names_dict = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type.replace("::", ":"))
                if not generic_parm_names_dict:
                    logger.warning("No generic parameters mapping was found for nodetype: '%s'.", node_type)
                    _parms_with_no_mapping.append(node_type)
                    endpoints[direction] = endpoint
                    continue

                param = endpoint.parm_name
                generic_name = generic_parm_names_dict.get(param, None)
                if not generic_name:
                    logger.warning(
                        "No generic name was found for parameter: '%s' for node_type: '%s'", param, node_type
                    )
                    _unsupported_parms_list.append(param)
                    _parms_with_no_generic_name_list.append(param)
                    # logger.debug("generic_parm_names_dict: %s", pprint.pformat(generic_parm_names_dict, sort_dicts=False))
                    endpoints[direction] = endpoint
                    continue
                endpoints[direction] = endpoint.with_parm_name(generic_name)

            new_connections_dict[i] = NodeConnection(
                input=endpoints["input"],
                output=endpoints["output"],
            )

        return new_connections_dict

    def create_nodeinfo_object(self, node_path, child_dict):
        """
        Create a standardized NodeInfo object from traversed node data.
        
        Args:
            node_path (str): Path of the node in the source graph.
            child_dict (dict): Traversed node data, including its type, name, parameters, connections, and output status.
        
        Returns:
            NodeInfo: Standardized node information.
        """
        is_output_node = child_dict.get("is_output_node", False)
        output_type = child_dict.get("output_type", None)

        connection_info = child_dict.get("connections_dict", {})
        standardized_connection_info = self.standardize_connection_info(connection_info)

        child_node_name: str = child_dict["node_name"]
        child_node_type: str = child_dict["node_type"]
        child_node_parms: list = child_dict.get("node_parms")
        child_node_pos: list[float, float] = child_dict.get("node_position")
        # print(f"DEBUG: parms for node: '{node_path}': {child_node_parms}")

        parameters = None
        if child_node_parms:
            parameters = self.standardize_shader_parameters(child_node_type, child_node_parms)

        generic_node_type = REGULAR_NODE_TYPES_TO_GENERIC[self.material_type][self.source_type].get(child_node_type)
        if not generic_node_type:
            logger.warning("No generic type was found for node type: '%s'", child_node_type)

        return NodeInfo(
            node_type=generic_node_type,
            node_name=child_node_name,
            node_path=node_path,
            parameters=parameters,
            connection_info=standardized_connection_info,
            children_list=[],
            is_output_node=is_output_node,
            output_type=output_type if is_output_node else generic_node_type,
            position=child_node_pos,
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
            # logger.debug("node_info_obj connections: %s", nodeinfo.print_connections())

            # Process children
            children_list = node_dict.get("children_list", [])
            for child_entry in children_list:
                child_node_path: str = child_entry["node_path"]

                # Recursively traverse child nodes
                child_nodes_info = self.standardize_node_dict({child_node_path: child_entry})

                nodeinfo.children_list.extend(child_nodes_info)

            nodeinfo_list.append(nodeinfo)
        # logger.debug("nodeinfo_list length = %d", len(nodeinfo_list))
        return nodeinfo_list

    @staticmethod
    def _parameter_by_name(nodeinfo):
        return {parameter.generic_name: parameter for parameter in nodeinfo.parameters or []}

    @staticmethod
    def _parameter_value(parameters_by_name, name, default=None):
        parameter = parameters_by_name.get(name)
        if parameter is None:
            return default
        return _as_scalar(parameter.value)

    @staticmethod
    def _image_node(node_path, node_name, filename, signature):
        """
        Create a generic image node with filename and signature parameters.
        
        Parameters:
        	node_path (str): Parent path for the image node.
        	node_name (str): Name of the image node.
        	filename (str): Image file path or name.
        	signature (str): Image signature identifying its content or format.
        
        Returns:
        	NodeInfo: A generic image node configured with the supplied parameters.
        """
        return NodeInfo(
            node_type="GENERIC::image",
            node_name=node_name,
            node_path=f"{node_path}/{node_name}",
            parameters=[
                NodeParameter(
                    generic_name="filename",
                    generic_type="string1",
                    direction="input",
                    value=filename,
                ),
                NodeParameter(
                    generic_name="signature",
                    generic_type="string1",
                    direction="input",
                    value=signature,
                ),
            ],
            connection_info={},
            children_list=[],
            position=None,
        )

    @staticmethod
    def _connection(
        src_nodeinfo,
        dest_nodeinfo,
        src_parm,
        dest_parm,
        src_type=None,
        dest_type=None,
        src_node_type=None,
        dest_node_type=None,
    ):
        return NodeConnection(
            input=ConnectionEndpoint(
                node_name=src_nodeinfo.node_name,
                node_path=src_nodeinfo.node_path,
                node_type=src_node_type or src_nodeinfo.node_type,
                node_index=0,
                parm_name=src_parm,
                data_type=src_type,
            ),
            output=ConnectionEndpoint(
                node_name=dest_nodeinfo.node_name,
                node_path=dest_nodeinfo.node_path,
                node_type=dest_node_type or dest_nodeinfo.node_type,
                node_index=0,
                parm_name=dest_parm,
                data_type=dest_type,
            ),
        )

    def _add_principled_texture_children(self, surface_nodeinfo, parameters_by_name):
        """Add image-texture child nodes and connect them to the corresponding surface inputs when configured."""
        for surface_input, texture_info in PRINCIPLED_TEXTURE_INPUTS.items():
            enabled = self._parameter_value(parameters_by_name, texture_info["use_parm"], False)
            filename = self._parameter_value(parameters_by_name, texture_info["texture_parm"], "")
            if not (_is_truthy(enabled) and filename):
                continue

            image_nodeinfo = self._image_node(
                node_path=surface_nodeinfo.node_path,
                node_name=texture_info["image_name"],
                filename=filename,
                signature=texture_info["signature"],
            )
            image_nodeinfo.connection_info["connection_0"] = self._connection(
                src_nodeinfo=image_nodeinfo,
                dest_nodeinfo=surface_nodeinfo,
                src_parm="rgb",
                dest_parm=surface_input,
                src_node_type="mtlximage",
                dest_node_type="mtlxstandard_surface",
            )
            surface_nodeinfo.children_list.append(image_nodeinfo)

    def _add_principled_normal_child(self, surface_nodeinfo, parameters_by_name):
        """
        Adds image and normal-map child nodes for an enabled normal texture configured with a normal-map type.
        """
        enabled = self._parameter_value(parameters_by_name, PRINCIPLED_NORMAL_INPUT["enable_parm"], False)
        normal_type = self._parameter_value(parameters_by_name, PRINCIPLED_NORMAL_INPUT["type_parm"], "")
        filename = self._parameter_value(parameters_by_name, PRINCIPLED_NORMAL_INPUT["texture_parm"], "")
        if not (_is_truthy(enabled) and normal_type == "normal" and filename):
            return

        normalmap_nodeinfo = NodeInfo(
            node_type="GENERIC::normalmap",
            node_name=PRINCIPLED_NORMAL_INPUT["normalmap_name"],
            node_path=f"{surface_nodeinfo.node_path}/{PRINCIPLED_NORMAL_INPUT['normalmap_name']}",
            parameters=[],
            connection_info={},
            children_list=[],
            position=None,
        )
        normalmap_nodeinfo.connection_info["connection_0"] = self._connection(
            src_nodeinfo=normalmap_nodeinfo,
            dest_nodeinfo=surface_nodeinfo,
            src_parm="out",
            dest_parm="normal",
            src_type="vector",
            dest_type="vector",
            src_node_type="mtlxnormalmap::2.0",
            dest_node_type="mtlxstandard_surface",
        )

        image_nodeinfo = self._image_node(
            node_path=surface_nodeinfo.node_path,
            node_name=PRINCIPLED_NORMAL_INPUT["image_name"],
            filename=filename,
            signature="color3",
        )
        image_nodeinfo.connection_info["connection_0"] = self._connection(
            src_nodeinfo=image_nodeinfo,
            dest_nodeinfo=normalmap_nodeinfo,
            src_parm="rgb",
            dest_parm="in",
            src_type="color",
            dest_type="vector",
            src_node_type="mtlximage",
            dest_node_type="mtlxnormalmap::2.0",
        )
        normalmap_nodeinfo.children_list.append(image_nodeinfo)
        surface_nodeinfo.children_list.append(normalmap_nodeinfo)

    def _principled_displacement_node(self, surface_nodeinfo, parameters_by_name):
        """
        Create a displacement node and its connected float image child when displacement is enabled and configured with a texture.
        
        Parameters:
        	surface_nodeinfo (NodeInfo): Surface node to which the displacement node belongs.
        	parameters_by_name (dict): Principled shader parameters keyed by generic name.
        
        Returns:
        	NodeInfo or None: The generated displacement node, or `None` when displacement is disabled or has no texture filename.
        """
        enabled = self._parameter_value(parameters_by_name, PRINCIPLED_DISPLACEMENT_INPUT["enable_parm"], False)
        filename = self._parameter_value(parameters_by_name, PRINCIPLED_DISPLACEMENT_INPUT["texture_parm"], "")
        if not (_is_truthy(enabled) and filename):
            return None

        scale = self._parameter_value(parameters_by_name, PRINCIPLED_DISPLACEMENT_INPUT["scale_parm"], 1.0)
        displacement_nodeinfo = NodeInfo(
            node_type="GENERIC::displacement",
            node_name=PRINCIPLED_DISPLACEMENT_INPUT["displacement_name"],
            node_path=f"{surface_nodeinfo.node_path}/{PRINCIPLED_DISPLACEMENT_INPUT['displacement_name']}",
            parameters=[
                NodeParameter(
                    generic_name="scale",
                    generic_type="float1",
                    direction="input",
                    value=scale,
                ),
            ],
            connection_info={},
            children_list=[],
            position=None,
        )

        image_nodeinfo = self._image_node(
            node_path=surface_nodeinfo.node_path,
            node_name=PRINCIPLED_DISPLACEMENT_INPUT["image_name"],
            filename=filename,
            signature="float",
        )
        image_nodeinfo.connection_info["connection_0"] = self._connection(
            src_nodeinfo=image_nodeinfo,
            dest_nodeinfo=displacement_nodeinfo,
            src_parm="rgb",
            dest_parm="displacement",
            src_type="float",
            dest_type="float",
            src_node_type="mtlximage",
            dest_node_type="mtlxdisplacement",
        )
        displacement_nodeinfo.children_list.append(image_nodeinfo)
        return displacement_nodeinfo

    def _expand_principled_standardization(self, nodeinfo_list, output_connections):
        """
        Expand a generic standard-surface node with configured texture, normal, and displacement nodes.
        
        Parameters:
            nodeinfo_list (list): Node information objects to expand.
            output_connections (dict): Output connections associated with the standardized nodes.
        
        Returns:
            tuple: The expanded node information list and updated output connections.
        """
        if not nodeinfo_list:
            return nodeinfo_list, output_connections

        surface_nodeinfo = nodeinfo_list[0]
        if surface_nodeinfo.node_type != "GENERIC::standard_surface":
            return nodeinfo_list, output_connections

        parameters_by_name = self._parameter_by_name(surface_nodeinfo)
        self._add_principled_texture_children(surface_nodeinfo, parameters_by_name)
        self._add_principled_normal_child(surface_nodeinfo, parameters_by_name)

        displacement_nodeinfo = self._principled_displacement_node(surface_nodeinfo, parameters_by_name)
        if displacement_nodeinfo is None:
            output_connections.pop("GENERIC::output_displacement", None)
            return nodeinfo_list, output_connections

        nodeinfo_list.append(displacement_nodeinfo)
        displacement_output = output_connections.get("GENERIC::output_displacement")
        if displacement_output:
            output_connections["GENERIC::output_displacement"] = replace(
                displacement_output,
                connected_node_name=displacement_nodeinfo.node_name,
                connected_node_path=displacement_nodeinfo.node_path,
                connected_input_name="displacement",
                connected_output_name="out",
            )
        return nodeinfo_list, output_connections

    def run(self):
        """
        Standardize traversed nodes and output connections into generic graph objects.
        
        For Principled shaders from Houdini VOP nodes, expands configured textures,
        normal maps, and displacement nodes.
        
        Returns:
            tuple: A tuple containing the standardized node list and output mapping.
        """
        nodeinfo_list = self.standardize_node_dict(self.traversed_nodes_dict)
        standardized_output_nodes_dict = self.standardize_output_dict(self.output_nodes_dict)
        if self.material_type == "principledshader" and self.source_type == "hou_vop_nodes":
            nodeinfo_list, standardized_output_nodes_dict = self._expand_principled_standardization(
                nodeinfo_list,
                standardized_output_nodes_dict,
            )
        return nodeinfo_list, standardized_output_nodes_dict

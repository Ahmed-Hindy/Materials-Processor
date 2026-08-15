"""Recreate generic material graphs as Blender shader networks."""

import logging
import math
from typing import List

from materials_processor.core.graph import NodeInfo
from materials_processor.mappings import (
    REGULAR_PARAM_NAMES_TO_GENERIC,
    convert_generic,
)

logger = logging.getLogger(__name__)

try:
    import bpy
except ImportError:
    # Safe fallback when running outside Blender
    logger.warning("materialProcessor running outside of Blender!")
    bpy = None


class BlenderNodeRecreator:
    """Class for recreating Blender node trees from standardized NodeInfo descriptions."""

    def __init__(self, nodeinfo_list, output_connections, target_material, material_name=None):
        """Initialize the BlenderNodeRecreator.

        Args:
            nodeinfo_list (list[NodeInfo]): The standardized material data.
            output_connections (Dict): The output connections mapping.
            target_material: The target Blender material (bpy.types.Material).
            material_name (str, optional): Name of the material.
        """
        self.nodeinfo_list = nodeinfo_list
        self.orig_output_connections = output_connections
        self.target_material = target_material
        self.material_name = material_name or (target_material.name if target_material else "convertedMaterial")
        self.old_new_node_map = {}
        self.reused_nodes = {}
        self.new_output_connections = {}

    def _convert_generic_node_type_to_blender_type(self, node_type: str):
        """Convert a generic node type to a Blender node type ID.

        Args:
            node_type (str): The generic node type.

        Returns:
            str: The Blender node type ID.
        """
        if not node_type:
            return "NodeReroute"

        new_node_type = convert_generic(node_type=node_type, target_renderer="blender", profile="blender_shader_nodes")
        return new_node_type

    def _apply_parameters(self, node, parameters):
        """
        Apply standardized input parameters to a Blender shader node, including node-specific values such as images, mapping transforms, and normal-map strength.
        
        Parameters:
            node: The Blender shader node to configure.
            parameters (List[NodeParameter]): Standardized parameters whose input values should be applied.
        """
        if not parameters:
            return

        node_type = node.bl_idname
        std_parm_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type, {})

        for param in parameters:
            if param.direction != "input":
                continue
            if not param.generic_name:
                continue

            # Find Blender-specific name
            blender_names = [key for key, val in std_parm_map.items() if val == param.generic_name]
            if not blender_names:
                continue

            blender_name = blender_names[0]
            val = param.value

            # Handle texture image loading
            if node_type == "ShaderNodeTexImage" and blender_name == "image" and val:
                if bpy:
                    try:
                        img = bpy.data.images.get(val) or bpy.data.images.load(val)
                        node.image = img
                    except Exception as exc:
                        logger.warning("Failed to load image file '%s': %s", val, exc)
                continue

            # Handle normal map Strength property
            if node_type == "ShaderNodeNormalMap" and blender_name == "Strength":
                if hasattr(node, "inputs") and "Strength" in node.inputs:
                    node.inputs["Strength"].default_value = float(val) if isinstance(val, (int, float)) else 1.0
                continue

            if node_type == "ShaderNodeValue" and blender_name == "value":
                value_socket = next((socket for socket in node.outputs if socket.name == "Value"), None)
                if value_socket and hasattr(value_socket, "default_value"):
                    value_socket.default_value = float(val) if isinstance(val, (int, float)) else 0.0
                continue

            if node_type == "ShaderNodeMapping" and blender_name in {"Location", "Rotation", "Scale"}:
                if hasattr(node, "inputs") and blender_name in node.inputs:
                    socket = node.inputs[blender_name]
                    try:
                        if blender_name == "Rotation":
                            socket.default_value = (0.0, 0.0, math.radians(float(val)))
                        else:
                            values = list(val) if isinstance(val, list) else [val]
                            z_default = 1.0 if blender_name == "Scale" else 0.0
                            socket.default_value = tuple((values + [z_default])[:3])
                    except Exception as exc:
                        logger.warning(
                            "Failed to set mapping parameter '%s' on node '%s': %s", blender_name, node.name, exc
                        )
                continue

            # Default socket value assignment
            if hasattr(node, "inputs") and blender_name in node.inputs:
                socket = node.inputs[blender_name]
                try:
                    if isinstance(val, list):
                        expected_len = len(socket.default_value) if hasattr(socket.default_value, "__len__") else 1
                        if expected_len > 1:
                            padded_val = (val + [1.0] * expected_len)[:expected_len]
                            socket.default_value = tuple(padded_val)
                        else:
                            socket.default_value = val[0]
                    else:
                        socket.default_value = val
                except Exception as e:
                    logger.warning("Failed to set parameter '%s' on node '%s': %s", blender_name, node.name, e)

    def _create_node(self, node_info):
        """
        Create or reuse a Blender node for the specified node description.
        
        Args:
            node_info (NodeInfo): Standardized node description used to identify and configure the node.
        
        Returns:
            The reused or newly created Blender node, or `None` if the target material has no node tree.
        """
        blender_type = self._convert_generic_node_type_to_blender_type(node_info.node_type)
        if not self.target_material or not getattr(self.target_material, "node_tree", None):
            return None

        node_tree = self.target_material.node_tree
        existing_nodes = [
            node
            for node in node_tree.nodes
            if node.bl_idname == blender_type and node not in self.reused_nodes.values()
        ]

        if existing_nodes:
            node = existing_nodes[0]
            self._apply_parameters(node, node_info.parameters)
            self.reused_nodes[node_info.node_path] = node
            self.old_new_node_map[node_info.node_path] = {
                "node_name": node.name,
                "node_path": f"/mat/{self.material_name}/{node.name}",
            }
            return node

        # Create new node
        node = node_tree.nodes.new(type=blender_type)
        node.name = node_info.node_name
        if hasattr(node, "location") and node_info.position:
            node.location.x, node.location.y = node_info.position[0], node_info.position[1]

        self._apply_parameters(node, node_info.parameters)
        self.reused_nodes[node_info.node_path] = node
        self.old_new_node_map[node_info.node_path] = {
            "node_name": node.name,
            "node_path": f"/mat/{self.material_name}/{node.name}",
        }
        return node

    def _create_nodes_recursive(self, nested_nodes_info: List[NodeInfo], processed_nodes=None):
        """
        Recursively creates Blender nodes from nested node descriptions while skipping already processed paths and generic output nodes.
        
        Parameters:
        	nested_nodes_info (List[NodeInfo]): Node descriptions to process.
        	processed_nodes (set, optional): Node paths that have already been processed.
        """
        if processed_nodes is None:
            processed_nodes = set()

        for node_info in nested_nodes_info:
            if node_info.node_path in processed_nodes:
                continue

            if node_info.node_type != "GENERIC::output_node":
                self._create_node(node_info)

            processed_nodes.add(node_info.node_path)
            self._create_nodes_recursive(node_info.children_list, processed_nodes)

    def _connect_pair(self, src_node, dest_node, src_socket_name, dest_socket_name):
        """Create a link between two Blender nodes.

        Args:
            src_node: Source node.
            dest_node: Destination node.
            src_socket_name: Source socket name.
            dest_socket_name: Destination socket name.

        Returns:
            bool: True if connected successfully.
        """
        if not self.target_material or not getattr(self.target_material, "node_tree", None):
            return False

        node_tree = self.target_material.node_tree

        # Find output socket
        from_socket = next((s for s in src_node.outputs if s.name == src_socket_name), None)
        if not from_socket and src_node.outputs:
            from_socket = src_node.outputs[0]

        # Find input socket
        to_socket = next((s for s in dest_node.inputs if s.name == dest_socket_name), None)
        if not to_socket and dest_node.inputs:
            std_parm_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(dest_node.bl_idname, {})
            to_socket = next((s for s in dest_node.inputs if std_parm_map.get(s.name) == dest_socket_name), None)

        if from_socket and to_socket:
            node_tree.links.new(from_socket, to_socket)
            return True

        return False

    def _connect_nodes_recursive(self, nested_nodes_info: List[NodeInfo], processed_connections=None):
        """
        Recreate connections between the specified nodes and their nested child nodes.
        
        Parameters:
            nested_nodes_info (List[NodeInfo]): Node descriptions containing connection information.
            processed_connections (set, optional): Connection identifiers already handled.
        """
        if processed_connections is None:
            processed_connections = set()

        for node_info in nested_nodes_info:
            for _, connection in node_info.connection_info.items():
                connection_key = f"{connection.input.node_path}->{connection.output.node_path}"
                if connection_key in processed_connections:
                    continue

                src_info = self.old_new_node_map.get(connection.input.node_path)
                dest_info = self.old_new_node_map.get(connection.output.node_path)

                if src_info and dest_info:
                    node_tree = self.target_material.node_tree
                    src_node = node_tree.nodes.get(src_info["node_name"])
                    dest_node = node_tree.nodes.get(dest_info["node_name"])

                    if src_node and dest_node:
                        src_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(src_node.bl_idname, {})
                        dest_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(dest_node.bl_idname, {})

                        src_socket_names = [k for k, v in src_map.items() if v == connection.input.parm_name]
                        src_socket_name = src_socket_names[0] if src_socket_names else connection.input.parm_name

                        dest_socket_names = [k for k, v in dest_map.items() if v == connection.output.parm_name]
                        dest_socket_name = dest_socket_names[0] if dest_socket_names else connection.output.parm_name

                        self._connect_pair(src_node, dest_node, src_socket_name, dest_socket_name)

                processed_connections.add(connection_key)

            self._connect_nodes_recursive(node_info.children_list, processed_connections)

    def run(self):
        """
        Recreate shader nodes and establish their connections in the target material.
        
        Returns:
            bool: `True` if recreation completes, `False` if no target material is provided.
        """
        if not self.target_material:
            logger.warning("No target material provided to BlenderNodeRecreator. Skipping recreation.")
            return False

        if not getattr(self.target_material, "use_nodes", False):
            self.target_material.use_nodes = True

        node_tree = self.target_material.node_tree
        # Clear existing nodes except active Output Node (or recreate it)
        output_node = next((node for node in node_tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial"), None)
        if not output_node:
            output_node = node_tree.nodes.new(type="ShaderNodeOutputMaterial")
        else:
            # Clear links connected to the output node
            for input_socket in output_node.inputs:
                for link in list(input_socket.links):
                    node_tree.links.remove(link)

        # Register output nodes in map
        for generic_output_type, output_connection in self.orig_output_connections.items():
            self.old_new_node_map[output_connection.node_path] = {
                "node_name": output_node.name,
                "node_path": f"/mat/{self.material_name}/{output_node.name}",
                "is_output": True,
                "output_type": generic_output_type,
            }

        # Step 1: Recreate all shader nodes recursively
        self._create_nodes_recursive(self.nodeinfo_list)

        # Step 2: Establish connection links recursively
        self._connect_nodes_recursive(self.nodeinfo_list)

        # Step 3: Wire final outputs to output_node
        for generic_output_type, output_connection in self.orig_output_connections.items():
            connected_node_info = self.old_new_node_map.get(output_connection.connected_node_path)
            if connected_node_info:
                src_node = node_tree.nodes.get(connected_node_info["node_name"])
                if src_node:
                    dest_socket_name = "Surface" if "surface" in generic_output_type.lower() else "Displacement"

                    src_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(src_node.bl_idname, {})
                    src_socket_names = [k for k, v in src_map.items() if v == output_connection.connected_output_name]
                    src_socket_name = (
                        src_socket_names[0] if src_socket_names else output_connection.connected_output_name
                    )

                    self._connect_pair(src_node, output_node, src_socket_name, dest_socket_name)

        return True

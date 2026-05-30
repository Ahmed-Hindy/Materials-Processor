"""Traverse Blender shader node networks."""

import logging

logger = logging.getLogger(__name__)

try:
    import bpy
except ImportError:
    # Safe fallback when running outside Blender
    logger.warning("materialProcessor running outside of Blender!")
    bpy = None


class BlenderNodeTraverser:
    """Class for traversing Blender material node trees to extract their connections and output nodes."""

    def __init__(self, material, material_type="blender"):
        """Initialize the BlenderNodeTraverser.

        Args:
            material: The Blender material object (bpy.types.Material).
            material_type (str): The material type (default is 'blender').
        """
        self.material = material
        self.material_type = material_type
        self.output_nodes = {}

    def create_output_dict(self, material):
        """Detect output nodes in the material's node tree.

        Args:
            material: The Blender material object.

        Returns:
            Dict: A dictionary of detected output nodes mapped by output slot.
        """
        if not material or not getattr(material, "node_tree", None):
            return {}

        output_dict = {}
        # Find active material output node
        output_node = None
        for node in material.node_tree.nodes:
            if node.bl_idname == "ShaderNodeOutputMaterial" and getattr(node, "is_active_output", True):
                output_node = node
                break

        if not output_node and material.node_tree.nodes:
            # Fallback to any output node if active flag is not set
            for node in material.node_tree.nodes:
                if node.bl_idname == "ShaderNodeOutputMaterial":
                    output_node = node
                    break

        if not output_node:
            logger.warning("No material output node found in material '%s'", material.name)
            return {}

        # Scan connections to find what is driving the output
        for input_socket in output_node.inputs:
            if not input_socket.is_linked:
                continue

            link = input_socket.links[0]
            from_node = link.from_node

            # Translate socket name to target index/name
            # For 'Surface' socket -> generic_type: 'GENERIC::output_surface'
            # For 'Displacement' socket -> generic_type: 'GENERIC::output_displacement'
            socket_name = input_socket.name.lower()
            if socket_name == "surface":
                output_key = "surface"
            elif socket_name == "displacement":
                output_key = "displacement"
            else:
                continue

            output_dict[output_key] = {
                "node_name": output_node.name,
                "node_path": f"/mat/{material.name}/{output_node.name}",
                "connected_node_name": from_node.name,
                "connected_node_path": f"/mat/{material.name}/{from_node.name}",
                "connected_input_index": 0,  # Default index
                "connected_input_name": input_socket.name,
                "connected_output_name": link.from_socket.name,
                "generic_type": f"GENERIC::output_{output_key}"
            }

        return output_dict

    @staticmethod
    def _detect_node_connections(node, parent_node, material_name):
        """Detect connections for a node going to its parent node (downstream).

        Args:
            node: The current node.
            parent_node: The parent node.
            material_name: The name of the material.

        Returns:
            Dict: Node connections dictionary.
        """
        connections_dict = {}
        if parent_node is None:
            return connections_dict

        # In Blender, links go from outputs to inputs.
        connection_idx = 0
        for output_socket in node.outputs:
            for link in output_socket.links:
                if link.to_node.name != parent_node.name:
                    continue

                connections_dict[f"connection_{connection_idx}"] = {
                    "input": {
                        "node_name": node.name,
                        "node_path": f"/mat/{material_name}/{node.name}",
                        "node_type": node.bl_idname,
                        "node_index": 0,
                        "parm_name": output_socket.name,
                        "data_type": output_socket.type,
                    },
                    "output": {
                        "node_name": parent_node.name,
                        "node_path": f"/mat/{material_name}/{parent_node.name}",
                        "node_type": parent_node.bl_idname,
                        "node_index": 0,
                        "parm_name": link.to_socket.name,
                        "data_type": link.to_socket.type,
                    }
                }
                connection_idx += 1

        return connections_dict

    @staticmethod
    def _convert_parms_to_dict(node):
        """Convert Blender node input socket default values and internal attributes into standard dictionaries.

        Args:
            node: The Blender node.

        Returns:
            Dict: Parameters dictionary.
        """
        parms = {"input": [], "output": []}

        # Sockets inputs representing parameters
        for socket in node.inputs:
            # If linked, the value is driven by connection, not parameter
            if socket.is_linked:
                continue

            # Check if default_value exists
            if not hasattr(socket, "default_value"):
                continue

            val = socket.default_value
            # Convert math-types like Vector, Color, RGBA, and Blender arrays to standard lists.
            if hasattr(val, "copy") or isinstance(val, (list, tuple, bytes, set)):
                val = list(val)
            elif type(val).__name__ in ("Vector", "Color", "bpy_prop_array"):
                val = list(val)
            elif not isinstance(val, str) and hasattr(val, "__iter__"):
                val = list(val)

            # Map Blender socket type names to generic types
            socket_type = socket.type.lower()
            if socket_type == "value":
                generic_type = "float1"
            elif socket_type == "vector":
                generic_type = "vector3"
            elif socket_type == "rgba":
                generic_type = "color4"
            else:
                generic_type = "float1"

            parms["input"].append({
                "generic_name": socket.name,
                "value": val,
                "type": generic_type,
                "direction": "input",
            })

        # Internal node properties (e.g. image file path for ShaderNodeTexImage)
        if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None):
            parms["input"].append({
                "generic_name": "image",
                "value": node.image.filepath,
                "type": "string1",
                "direction": "input"
            })
        elif node.bl_idname == "ShaderNodeNormalMap":
            strength_val = 1.0
            if hasattr(node, "inputs") and "Strength" in node.inputs:
                strength_val = node.inputs["Strength"].default_value
            parms["input"].append({
                "generic_name": "Strength",
                "value": strength_val,
                "type": "float1",
                "direction": "input"
            })

        # Node outputs mapped as output parameters
        for socket in node.outputs:
            parms["output"].append({
                "generic_name": socket.name,
                "value": None,
                "type": "color3" if socket.type == "RGBA" else "float1",
                "direction": "output",
            })

        return parms

    def _traverse_recursively_node_tree(self, node, parent_node=None, active_paths=None):
        """Recursively traverse the node tree.

        Args:
            node: The current Blender node.
            parent_node: The parent node.
            active_paths: Set of traversed paths to prevent cycles.

        Returns:
            Dict: Dictionary representation of the node tree.
        """
        if active_paths is None:
            active_paths = set()

        node_path = f"/mat/{self.material.name}/{node.name}"
        if node_path in active_paths:
            logger.warning("Skipping recursive material traversal cycle at '%s'.", node_path)
            return {}

        active_paths = active_paths | {node_path}

        connections_dict = self._detect_node_connections(node, parent_node, self.material.name)

        # Initialize the node's dictionary with metadata
        node_dict = {
            'node_name': node.name,
            'node_path': node_path,
            'node_type': node.bl_idname,
            'node_position': (node.location.x, node.location.y) if hasattr(node, 'location') else (0.0, 0.0),
            'node_parms': self._convert_parms_to_dict(node),
            'connections_dict': connections_dict,
            'children_list': []
        }

        # Traverse inputs (upstream links)
        for input_socket in node.inputs:
            if not input_socket.is_linked:
                continue

            for link in input_socket.links:
                input_node = link.from_node
                input_node_path = f"/mat/{self.material.name}/{input_node.name}"

                input_node_dict = self._traverse_recursively_node_tree(input_node, node, active_paths)
                input_node_entry = input_node_dict.get(input_node_path)
                if input_node_entry is None:
                    continue

                node_dict['children_list'].append(input_node_entry)

        return {node_path: node_dict}

    def run(self):
        """Traverse the Blender shader node tree.

        Returns:
            Tuple[Dict, Dict]: Node tree dictionary and output tree dictionary.
        """
        output_tree = self.create_output_dict(self.material)
        node_tree = {}

        for _, output_dict in output_tree.items():
            if not self.material or not getattr(self.material, "node_tree", None):
                continue

            connected_node_name = output_dict['connected_node_name']
            connected_node = self.material.node_tree.nodes.get(connected_node_name)
            if connected_node:
                node_tree.update(self._traverse_recursively_node_tree(connected_node))

        return node_tree, output_tree

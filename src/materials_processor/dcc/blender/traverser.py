"""Traverse Blender shader node networks."""

import logging
import math

logger = logging.getLogger(__name__)

try:
    import bpy
except ImportError:
    # Safe fallback when running outside Blender
    logger.warning("materialProcessor running outside of Blender!")
    bpy = None


def _socket_parameter_name(socket, *, is_output=False, node=None):
    """Return a stable Blender parameter key for sockets with ambiguous names."""
    node_type = getattr(node, "bl_idname", None)
    if is_output and node_type == "ShaderNodeMapping" and socket.name == "Vector":
        return "Vector Output"
    return socket.name


def _socket_generic_type(socket, *, is_output=False, node=None):
    """Return the closest generic parameter type for a Blender socket."""
    node_type = getattr(node, "bl_idname", None)
    if node_type == "ShaderNodeMapping":
        if socket.name in {"Vector", "Location", "Scale"}:
            return "vector2"
        if socket.name == "Rotation":
            return "float1"
    if is_output and node_type == "ShaderNodeTexCoord" and socket.name == "UV":
        return "vector2"

    socket_type = socket.type.lower()
    if socket_type == "value":
        return "float1"
    if socket_type == "vector":
        if is_output and node_type == "ShaderNodeUVMap":
            return "vector2"
        return "vector3"
    if socket_type == "rgba":
        return "color3" if is_output else "color4"
    if socket_type == "shader":
        return "shader"
    return "float1"


def _socket_default_value(socket, node):
    """Return a JSON-friendly socket value, normalizing Blender mapping semantics."""
    val = socket.default_value
    node_type = getattr(node, "bl_idname", None)
    if node_type == "ShaderNodeMapping":
        if socket.name in {"Vector", "Location", "Scale"}:
            return list(val)[:2]
        if socket.name == "Rotation":
            try:
                rotation_values = list(val)
            except TypeError:
                try:
                    rotation_values = [val[0], val[1], val[2]]
                except (TypeError, IndexError):
                    rotation_values = [0.0, 0.0, val]
            z_rotation = rotation_values[2] if len(rotation_values) > 2 else 0.0
            return math.degrees(z_rotation)

    # Convert math-types like Vector, Color, RGBA, and Blender arrays to standard lists.
    if hasattr(val, "copy") or isinstance(val, (list, tuple, bytes, set)):
        return list(val)
    if type(val).__name__ in ("Vector", "Color", "bpy_prop_array"):
        return list(val)
    if not isinstance(val, str) and hasattr(val, "__iter__"):
        return list(val)
    return val


def _resolve_blender_image_path(image):
    """Resolve Blender image paths relative to the current blend file when possible."""
    filepath = getattr(image, "filepath", "")
    if not filepath:
        return filepath
    if bpy is None:
        return filepath
    try:
        return bpy.path.abspath(filepath)
    except Exception as exc:
        logger.warning("Failed to resolve Blender image path '%s': %s", filepath, exc)
        return filepath


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
        self._output_sources = {}

    def _node_path(self, node, group_chain=()):
        """Return a unique material-relative path for a flattened group node."""
        path_parts = ["/mat", self.material.name, *group_chain, node.name]
        return "/".join(path_parts)

    @staticmethod
    def _active_group_output(node_tree):
        """Return the active group output node, when a group has one."""
        outputs = [node for node in node_tree.nodes if node.bl_idname == "NodeGroupOutput"]
        return next((node for node in outputs if getattr(node, "is_active_output", True)), outputs[0] if outputs else None)

    def _group_output_source(self, group_node, output_socket):
        """Resolve a group output to its internal source node and socket."""
        node_tree = getattr(group_node, "node_tree", None)
        if not node_tree or not output_socket:
            return None

        group_output = self._active_group_output(node_tree)
        if group_output is None:
            return None
        output_input = next((socket for socket in group_output.inputs if socket.name == output_socket.name), None)
        if not output_input or not output_input.is_linked:
            return None

        link = output_input.links[0]
        return link.from_node, link.from_socket

    def _flattened_source(self, node, output_socket, group_chain=(), group_instances=()):
        """Resolve nested group nodes into their concrete source.

        ``group_instances`` parallels ``group_chain`` and retains the outer
        group nodes needed to evaluate Group Input sockets while traversing an
        otherwise supported internal graph.
        """
        if node.bl_idname != "ShaderNodeGroup":
            return node, output_socket, group_chain, group_instances
        resolved = self._group_output_source(node, output_socket)
        if resolved is None:
            return None
        source_node, source_socket = resolved
        return self._flattened_source(
            source_node,
            source_socket,
            (*group_chain, node.name),
            (*group_instances, node),
        )

    @staticmethod
    def _group_input_socket(link, group_instances):
        """Resolve an internal Group Input link to its outer instance socket."""
        if link.from_node.bl_idname != "NodeGroupInput" or not group_instances:
            return None
        group_node = group_instances[-1]
        socket_name = link.from_socket.name
        return group_node.inputs.get(socket_name) if hasattr(group_node.inputs, "get") else next(
            (socket for socket in group_node.inputs if socket.name == socket_name), None
        )

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

            resolved = self._flattened_source(from_node, link.from_socket)
            if resolved is not None:
                from_node, from_socket, group_chain, group_instances = resolved
                connected_node_path = self._node_path(from_node, group_chain)
                connected_node_name = from_node.name
            else:
                from_socket = link.from_socket
                connected_node_path = self._node_path(from_node)
                connected_node_name = from_node.name
                group_chain = ()
                group_instances = ()

            output_dict[output_key] = {
                "node_name": output_node.name,
                "node_path": f"/mat/{material.name}/{output_node.name}",
                "connected_node_name": connected_node_name,
                "connected_node_path": connected_node_path,
                "connected_input_index": 0,  # Default index
                "connected_input_name": input_socket.name,
                "connected_output_name": from_socket.name,
                "generic_type": f"GENERIC::output_{output_key}",
            }
            self._output_sources[output_key] = (
                from_node,
                group_chain if resolved is not None else (),
                group_instances if resolved is not None else (),
            )

        return output_dict

    @staticmethod
    def _detect_node_connections(
        node,
        parent_node,
        material_name,
        *,
        node_path=None,
        parent_node_path=None,
        source_socket=None,
        parent_socket=None,
    ):
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

        node_path = node_path or f"/mat/{material_name}/{node.name}"
        parent_node_path = parent_node_path or f"/mat/{material_name}/{parent_node.name}"
        if source_socket is not None and parent_socket is not None:
            return {
                "connection_0": {
                    "input": {
                        "node_name": node.name,
                        "node_path": node_path,
                        "node_type": node.bl_idname,
                        "node_index": 0,
                        "parm_name": _socket_parameter_name(source_socket, is_output=True, node=node),
                        "data_type": source_socket.type,
                    },
                    "output": {
                        "node_name": parent_node.name,
                        "node_path": parent_node_path,
                        "node_type": parent_node.bl_idname,
                        "node_index": 0,
                        "parm_name": _socket_parameter_name(parent_socket, node=parent_node),
                        "data_type": parent_socket.type,
                    },
                }
            }

        # In Blender, links go from outputs to inputs.
        connection_idx = 0
        for output_socket in node.outputs:
            for link in output_socket.links:
                if link.to_node.name != parent_node.name:
                    continue

                connections_dict[f"connection_{connection_idx}"] = {
                    "input": {
                        "node_name": node.name,
                        "node_path": node_path,
                        "node_type": node.bl_idname,
                        "node_index": 0,
                        "parm_name": _socket_parameter_name(output_socket, is_output=True, node=node),
                        "data_type": output_socket.type,
                    },
                    "output": {
                        "node_name": parent_node.name,
                        "node_path": parent_node_path,
                        "node_type": parent_node.bl_idname,
                        "node_index": 0,
                        "parm_name": _socket_parameter_name(link.to_socket, node=parent_node),
                        "data_type": link.to_socket.type,
                    }
                }
                connection_idx += 1

        return connections_dict

    @staticmethod
    def _convert_parms_to_dict(node, input_overrides=None):
        """Convert Blender node input socket default values and internal attributes into standard dictionaries.

        Args:
            node: The Blender node.

        Returns:
            Dict: Parameters dictionary.
        """
        parms = {"input": [], "output": []}
        input_overrides = input_overrides or {}

        # Sockets inputs representing parameters
        for socket in node.inputs:
            parameter_name = _socket_parameter_name(socket, node=node)
            override = input_overrides.get(parameter_name)
            # If linked, the value is driven by connection, except where an
            # internal Group Input resolves to an unlinked outer default.
            if socket.is_linked and override is None:
                continue

            # Check if default_value exists
            if not hasattr(socket, "default_value"):
                continue

            val = override["value"] if override is not None else _socket_default_value(socket, node)

            parms["input"].append({
                "generic_name": parameter_name,
                "value": val,
                "type": override["type"] if override is not None else _socket_generic_type(socket, node=node),
                "direction": "input",
            })

        # Internal node properties (e.g. image file path for ShaderNodeTexImage)
        if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None):
            parms["input"].append({
                "generic_name": "image",
                "value": _resolve_blender_image_path(node.image),
                "type": "string1",
                "direction": "input"
            })
        elif node.bl_idname == "ShaderNodeUVMap":
            parms["input"].append({
                "generic_name": "uv_map",
                "value": getattr(node, "uv_map", ""),
                "type": "string1",
                "direction": "input"
            })
        elif node.bl_idname == "ShaderNodeTexCoord":
            parms["input"].append({
                "generic_name": "uv_map",
                "value": "",
                "type": "string1",
                "direction": "input"
            })
        elif node.bl_idname == "ShaderNodeValue":
            value_socket = next((socket for socket in node.outputs if socket.name == "Value"), None)
            parms["input"].append({
                "generic_name": "value",
                "value": getattr(value_socket, "default_value", 0.0),
                "type": "float1",
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
                "generic_name": _socket_parameter_name(socket, is_output=True, node=node),
                "value": None,
                "type": _socket_generic_type(socket, is_output=True, node=node),
                "direction": "output",
            })

        return parms

    def _traverse_recursively_node_tree(
        self,
        node,
        parent_node=None,
        active_paths=None,
        *,
        group_chain=(),
        group_instances=(),
        parent_node_path=None,
        source_socket=None,
        parent_socket=None,
    ):
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

        node_path = self._node_path(node, group_chain)
        if node_path in active_paths:
            logger.warning("Skipping recursive material traversal cycle at '%s'.", node_path)
            return {}

        active_paths = active_paths | {node_path}

        connections_dict = self._detect_node_connections(
            node,
            parent_node,
            self.material.name,
            node_path=node_path,
            parent_node_path=parent_node_path,
            source_socket=source_socket,
            parent_socket=parent_socket,
        )

        input_overrides = {}
        for input_socket in node.inputs:
            for link in input_socket.links if input_socket.is_linked else ():
                outer_socket = self._group_input_socket(link, group_instances)
                if outer_socket is None or outer_socket.is_linked or not hasattr(outer_socket, "default_value"):
                    continue
                input_overrides[_socket_parameter_name(input_socket, node=node)] = {
                    "value": _socket_default_value(outer_socket, node),
                    "type": _socket_generic_type(outer_socket, node=node),
                }

        # Initialize the node's dictionary with metadata
        node_dict = {
            'node_name': node.name,
            'node_path': node_path,
            'node_type': node.bl_idname,
            'node_position': (node.location.x, node.location.y) if hasattr(node, 'location') else (0.0, 0.0),
            'node_parms': self._convert_parms_to_dict(node, input_overrides),
            'connections_dict': connections_dict,
            'children_list': []
        }

        # Traverse inputs (upstream links)
        for input_socket in node.inputs:
            if not input_socket.is_linked:
                continue

            for link in input_socket.links:
                input_node = link.from_node
                outer_socket = self._group_input_socket(link, group_instances)
                if outer_socket is not None:
                    if not outer_socket.is_linked:
                        continue
                    outer_link = outer_socket.links[0]
                    resolved = self._flattened_source(
                        outer_link.from_node,
                        outer_link.from_socket,
                        group_chain=group_chain[:-1],
                        group_instances=group_instances[:-1],
                    )
                    absolute_group_chain = True
                else:
                    resolved = self._flattened_source(input_node, link.from_socket)
                    absolute_group_chain = False
                if resolved is not None:
                    input_node, source_socket, input_group_chain, input_group_instances = resolved
                    if absolute_group_chain:
                        child_group_chain = input_group_chain
                        child_group_instances = input_group_instances
                    else:
                        child_group_chain = (*group_chain, *input_group_chain)
                        child_group_instances = (*group_instances, *input_group_instances)
                else:
                    source_socket = None
                    child_group_chain = group_chain
                    child_group_instances = group_instances
                input_node_path = self._node_path(input_node, child_group_chain)

                input_node_dict = self._traverse_recursively_node_tree(
                    input_node,
                    node,
                    active_paths,
                    group_chain=child_group_chain,
                    group_instances=child_group_instances,
                    parent_node_path=node_path,
                    source_socket=source_socket,
                    parent_socket=input_socket if source_socket is not None else None,
                )
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
        self._output_sources = {}
        output_tree = self.create_output_dict(self.material)
        node_tree = {}

        for output_key, output_dict in output_tree.items():
            if not self.material or not getattr(self.material, "node_tree", None):
                continue

            source = self._output_sources.get(output_key)
            if source:
                connected_node, group_chain, group_instances = source
                node_tree.update(
                    self._traverse_recursively_node_tree(
                        connected_node,
                        group_chain=group_chain,
                        group_instances=group_instances,
                    )
                )

        return node_tree, output_tree

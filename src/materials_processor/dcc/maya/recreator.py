"""Recreate neutral material graphs as Maya shading networks."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from materials_processor.core.graph import NodeInfo
from materials_processor.mappings import REGULAR_PARAM_NAMES_TO_GENERIC, convert_generic

logger = logging.getLogger(__name__)

try:
    import maya.cmds as cmds
except ImportError:
    logger.warning("materials_processor running outside of Maya.")
    cmds = None


def _require_cmds():
    if cmds is None:
        raise RuntimeError("Maya commands are only available inside Maya or mayapy.")
    return cmds


def _node_path(material_name: str, node_name: str) -> str:
    return f"/maya/{material_name}/{node_name}"


class MayaNodeRecreator:
    """Recreate a standardized material graph as Maya DG shader nodes."""

    def __init__(self, nodeinfo_list, output_connections, target_context=None, material_name=None):
        """Initialize the Maya recreator.

        Args:
            nodeinfo_list: Standardized node descriptions.
            output_connections: Standardized output connection mapping.
            target_context: Existing shadingEngine node, material name string,
                mapping with ``shading_engine`` or ``material_name``, or ``None``.
            material_name: Optional fallback material name.
        """
        self.nodeinfo_list = nodeinfo_list
        self.orig_output_connections = output_connections
        self.target_context = target_context
        self.material_name = material_name or self._material_name_from_context(target_context) or "convertedMaterial"
        self.cmds = _require_cmds()
        self.old_new_node_map = {}
        self.created_shading_engine = None

    @staticmethod
    def _material_name_from_context(target_context: Any) -> str | None:
        if isinstance(target_context, Mapping):
            return target_context.get("material_name") or target_context.get("name")
        if isinstance(target_context, str):
            return target_context
        return None

    def _target_shading_engine(self):
        if isinstance(self.target_context, Mapping):
            shading_engine = self.target_context.get("shading_engine")
            if shading_engine and self.cmds.objExists(shading_engine):
                return shading_engine

        if isinstance(self.target_context, str) and self.cmds.objExists(self.target_context):
            if self.cmds.nodeType(self.target_context) == "shadingEngine":
                return self.target_context

        shading_engine_name = f"{self.material_name}SG"
        return self.cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=shading_engine_name,
        )

    @staticmethod
    def _maya_node_type(node_type: str) -> str:
        if not node_type:
            return "network"
        return convert_generic(node_type, "maya", profile="maya_nodes") or "network"

    def _create_node(self, node_info: NodeInfo):
        maya_type = self._maya_node_type(node_info.node_type)
        node = self.cmds.createNode(maya_type, name=node_info.node_name)
        self._apply_parameters(node, node_info.parameters)
        self.old_new_node_map[node_info.node_path] = {
            "node_name": node,
            "node_path": _node_path(self.material_name, node),
        }
        return node

    def _attr_exists(self, node: str, attr: str) -> bool:
        try:
            return bool(self.cmds.attributeQuery(attr, node=node, exists=True))
        except Exception:
            return bool(self.cmds.objExists(f"{node}.{attr}"))

    def _set_attr(self, node: str, attr: str, value):
        if value is None or not self._attr_exists(node, attr):
            return

        plug = f"{node}.{attr}"
        try:
            if isinstance(value, str):
                self.cmds.setAttr(plug, value, type="string")
            elif isinstance(value, (list, tuple)):
                self.cmds.setAttr(plug, *value)
            else:
                self.cmds.setAttr(plug, value)
        except Exception as exc:
            logger.warning("Failed to set Maya attribute '%s' on node '%s': %s", attr, node, exc)

    def _apply_parameters(self, node: str, parameters):
        if not parameters:
            return

        node_type = self.cmds.nodeType(node)
        std_parm_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type, {})
        for param in parameters:
            if param.direction != "input" or not param.generic_name:
                continue
            maya_names = [key for key, val in std_parm_map.items() if val == param.generic_name]
            if not maya_names:
                continue
            self._set_attr(node, maya_names[0], param.value)

    def _create_nodes_recursive(self, nested_nodes_info, processed_nodes=None):
        if processed_nodes is None:
            processed_nodes = set()

        for node_info in nested_nodes_info:
            if node_info.node_path in processed_nodes:
                continue
            if node_info.node_type != "GENERIC::output_node":
                self._create_node(node_info)
            processed_nodes.add(node_info.node_path)
            self._create_nodes_recursive(node_info.children_list, processed_nodes)

    def _connection_attr(self, node: str, generic_attr: str) -> str:
        node_type = self.cmds.nodeType(node)
        std_parm_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type, {})
        attr_names = [key for key, val in std_parm_map.items() if val == generic_attr]
        return attr_names[0] if attr_names else generic_attr

    def _connect_pair(self, src_node: str, dest_node: str, src_attr: str, dest_attr: str) -> bool:
        src_plug = f"{src_node}.{src_attr}"
        dest_plug = f"{dest_node}.{dest_attr}"
        if not (self.cmds.objExists(src_plug) and self.cmds.objExists(dest_plug)):
            logger.warning("Skipping missing Maya connection plug: %s -> %s", src_plug, dest_plug)
            return False
        try:
            self.cmds.connectAttr(src_plug, dest_plug, force=True)
            return True
        except Exception as exc:
            logger.warning("Failed to connect Maya plugs '%s' -> '%s': %s", src_plug, dest_plug, exc)
            return False

    def _connect_nodes_recursive(self, nested_nodes_info, processed_connections=None):
        if processed_connections is None:
            processed_connections = set()

        for node_info in nested_nodes_info:
            for connection in node_info.connection_info.values():
                connection_key = f"{connection.input.node_path}->{connection.output.node_path}:{connection.output.parm_name}"
                if connection_key in processed_connections:
                    continue

                src_info = self.old_new_node_map.get(connection.input.node_path)
                dest_info = self.old_new_node_map.get(connection.output.node_path)
                if src_info and dest_info:
                    src_node = src_info["node_name"]
                    dest_node = dest_info["node_name"]
                    src_attr = self._connection_attr(src_node, connection.input.parm_name)
                    dest_attr = self._connection_attr(dest_node, connection.output.parm_name)
                    self._connect_pair(src_node, dest_node, src_attr, dest_attr)

                processed_connections.add(connection_key)

            self._connect_nodes_recursive(node_info.children_list, processed_connections)

    def _register_output_node(self, shading_engine: str):
        for output_connection in self.orig_output_connections.values():
            self.old_new_node_map[output_connection.node_path] = {
                "node_name": shading_engine,
                "node_path": _node_path(self.material_name, shading_engine),
                "is_output": True,
            }

    def _wire_outputs(self):
        for generic_output_type, output_connection in self.orig_output_connections.items():
            if generic_output_type != "GENERIC::output_surface":
                continue
            src_info = self.old_new_node_map.get(output_connection.connected_node_path)
            if not src_info:
                continue
            src_node = src_info["node_name"]
            src_attr = self._connection_attr(src_node, output_connection.connected_output_name)
            self._connect_pair(src_node, self.created_shading_engine, src_attr, "surfaceShader")

    def run(self):
        """Recreate Maya shader nodes and connect them to a shadingEngine."""
        self.created_shading_engine = self._target_shading_engine()
        self._register_output_node(self.created_shading_engine)
        self._create_nodes_recursive(self.nodeinfo_list)
        self._connect_nodes_recursive(self.nodeinfo_list)
        self._wire_outputs()
        return self.created_shading_engine

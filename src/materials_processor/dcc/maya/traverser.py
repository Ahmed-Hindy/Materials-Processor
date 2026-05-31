"""Traverse Maya shading networks into dictionaries for standardization."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import maya.cmds as cmds
except ImportError:
    logger.warning("materials_processor running outside of Maya.")
    cmds = None


MAYA_INPUT_ATTRS = {
    "standardSurface": [
        "base",
        "baseColor",
        "diffuseRoughness",
        "metalness",
        "specular",
        "specularColor",
        "specularRoughness",
        "specularIOR",
        "specularAnisotropy",
        "specularRotation",
        "transmission",
        "transmissionColor",
        "transmissionExtraRoughness",
        "subsurface",
        "subsurfaceColor",
        "subsurfaceScale",
        "emission",
        "emissionColor",
        "coat",
        "coatColor",
        "coatRoughness",
        "coatIOR",
        "coatNormal",
        "opacity",
        "normalCamera",
    ],
    "aiStandardSurface": [
        "base",
        "baseColor",
        "diffuseRoughness",
        "metalness",
        "specular",
        "specularColor",
        "specularRoughness",
        "specularIOR",
        "specularAnisotropy",
        "specularRotation",
        "transmission",
        "transmissionColor",
        "transmissionExtraRoughness",
        "subsurface",
        "subsurfaceColor",
        "subsurfaceScale",
        "emission",
        "emissionColor",
        "coat",
        "coatColor",
        "coatRoughness",
        "coatIOR",
        "coatNormal",
        "opacity",
        "normalCamera",
    ],
    "file": ["fileTextureName", "colorSpace", "uvCoord"],
    "place2dTexture": ["coverage", "translateFrame", "repeatUV", "offset", "rotateUV"],
    "bump2d": ["bumpValue", "bumpDepth", "bumpInterp"],
}

MAYA_OUTPUT_ATTRS = {
    "standardSurface": ["outColor"],
    "aiStandardSurface": ["outColor"],
    "file": ["outColor", "outAlpha"],
    "place2dTexture": ["outUV", "outUvFilterSize"],
    "bump2d": ["outNormal"],
}

MAYA_COLOR_ATTRS = {
    "baseColor",
    "specularColor",
    "transmissionColor",
    "subsurfaceColor",
    "emissionColor",
    "coatColor",
    "opacity",
}
MAYA_VECTOR_ATTRS = {"normalCamera", "coatNormal", "outNormal"}
MAYA_VECTOR2_ATTRS = {"uvCoord", "coverage", "translateFrame", "repeatUV", "offset", "outUV", "outUvFilterSize"}
MAYA_STRING_ATTRS = {"fileTextureName", "colorSpace"}


def _require_cmds():
    if cmds is None:
        raise RuntimeError("Maya commands are only available inside Maya or mayapy.")
    return cmds


def _node_path(material_name: str, node_name: str) -> str:
    return f"/maya/{material_name}/{node_name}"


def _split_plug(plug: str) -> tuple[str, str]:
    node_name, attr_name = plug.split(".", 1)
    return node_name, attr_name


def _plug(node: str, attr: str) -> str:
    return f"{node}.{attr}"


def _maya_attr_type(attr_name: str, value=None) -> str:
    if attr_name in MAYA_STRING_ATTRS:
        return "string1"
    if attr_name in MAYA_COLOR_ATTRS:
        return "color3"
    if attr_name in MAYA_VECTOR2_ATTRS:
        return "vector2"
    if attr_name in MAYA_VECTOR_ATTRS:
        return "vector3"
    if isinstance(value, bool):
        return "bool1"
    if isinstance(value, int):
        return "int1"
    return "float1"


def _normalize_value(value):
    if isinstance(value, (list, tuple)):
        if len(value) == 1 and isinstance(value[0], (list, tuple)):
            return list(value[0])
        return list(value)
    return value


class MayaNodeTraverser:
    """Traverse Maya surface shader DG networks."""

    def __init__(self, material_node: str, material_type: str = "maya"):
        """Initialize a Maya graph traverser.

        Args:
            material_node: Maya shader or shadingEngine node name.
            material_type: Standard material type label.
        """
        self.material_node = material_node
        self.material_type = material_type
        self.cmds = _require_cmds()

    def _attr_exists(self, node: str, attr: str) -> bool:
        try:
            return bool(self.cmds.attributeQuery(attr, node=node, exists=True))
        except Exception:
            return bool(self.cmds.objExists(_plug(node, attr)))

    def _surface_shader_from_shading_engine(self, shading_engine: str) -> tuple[str | None, str | None]:
        sources = self.cmds.listConnections(
            _plug(shading_engine, "surfaceShader"),
            source=True,
            destination=False,
            plugs=True,
        ) or []
        if not sources:
            return None, None
        source_node, source_attr = _split_plug(sources[0])
        return source_node, source_attr

    def _shading_engine_from_shader(self, shader_node: str) -> tuple[str | None, str]:
        node_type = self.cmds.nodeType(shader_node)
        output_attrs = MAYA_OUTPUT_ATTRS.get(node_type, ["outColor"])
        for output_attr in output_attrs:
            if not self._attr_exists(shader_node, output_attr):
                continue
            destinations = self.cmds.listConnections(
                _plug(shader_node, output_attr),
                source=False,
                destination=True,
                plugs=True,
            ) or []
            for destination in destinations:
                dest_node, dest_attr = _split_plug(destination)
                if dest_attr == "surfaceShader" and self.cmds.nodeType(dest_node) == "shadingEngine":
                    return dest_node, output_attr
        return None, output_attrs[0]

    def _resolve_surface(self) -> tuple[str, str, str]:
        node_type = self.cmds.nodeType(self.material_node)
        if node_type == "shadingEngine":
            shader_node, shader_attr = self._surface_shader_from_shading_engine(self.material_node)
            if not shader_node:
                raise ValueError(f"Shading engine '{self.material_node}' has no surface shader connection.")
            return self.material_node, shader_node, shader_attr or "outColor"

        shading_engine, shader_attr = self._shading_engine_from_shader(self.material_node)
        return shading_engine or f"{self.material_node}SG", self.material_node, shader_attr

    def create_output_dict(self) -> dict:
        """Detect Maya shadingEngine surface output metadata."""
        shading_engine, shader_node, shader_output_attr = self._resolve_surface()
        return {
            "surface": {
                "node_name": shading_engine,
                "node_path": _node_path(shading_engine, shading_engine),
                "connected_node_name": shader_node,
                "connected_node_path": _node_path(shading_engine, shader_node),
                "connected_input_index": 0,
                "connected_input_name": "surfaceShader",
                "connected_output_name": shader_output_attr,
                "generic_type": "GENERIC::output_surface",
            }
        }

    def _connection_to_parent(self, node: str, parent_node: str, material_name: str) -> dict:
        connections_dict = {}
        node_type = self.cmds.nodeType(node)
        connection_idx = 0
        for output_attr in MAYA_OUTPUT_ATTRS.get(node_type, []):
            if not self._attr_exists(node, output_attr):
                continue
            destinations = self.cmds.listConnections(
                _plug(node, output_attr),
                source=False,
                destination=True,
                plugs=True,
            ) or []
            for destination in destinations:
                dest_node, dest_attr = _split_plug(destination)
                if dest_node != parent_node:
                    continue
                connections_dict[f"connection_{connection_idx}"] = {
                    "input": {
                        "node_name": node,
                        "node_path": _node_path(material_name, node),
                        "node_type": node_type,
                        "node_index": 0,
                        "parm_name": output_attr,
                        "data_type": _maya_attr_type(output_attr),
                    },
                    "output": {
                        "node_name": parent_node,
                        "node_path": _node_path(material_name, parent_node),
                        "node_type": self.cmds.nodeType(parent_node),
                        "node_index": 0,
                        "parm_name": dest_attr,
                        "data_type": _maya_attr_type(dest_attr),
                    },
                }
                connection_idx += 1
        return connections_dict

    def _input_source_plug(self, node: str, attr: str) -> str | None:
        sources = self.cmds.listConnections(
            _plug(node, attr),
            source=True,
            destination=False,
            plugs=True,
        ) or []
        return sources[0] if sources else None

    def _convert_parms_to_dict(self, node: str) -> dict:
        parms = {"input": [], "output": []}
        node_type = self.cmds.nodeType(node)

        for attr in MAYA_INPUT_ATTRS.get(node_type, []):
            if not self._attr_exists(node, attr):
                continue
            if self._input_source_plug(node, attr):
                continue

            try:
                value = self.cmds.getAttr(_plug(node, attr))
            except Exception:
                continue
            value = _normalize_value(value)
            parms["input"].append(
                {
                    "generic_name": attr,
                    "value": value,
                    "type": _maya_attr_type(attr, value),
                    "direction": "input",
                }
            )

        for attr in MAYA_OUTPUT_ATTRS.get(node_type, []):
            if not self._attr_exists(node, attr):
                continue
            parms["output"].append(
                {
                    "generic_name": attr,
                    "value": None,
                    "type": _maya_attr_type(attr),
                    "direction": "output",
                }
            )
        return parms

    def _traverse_recursively(self, node: str, material_name: str, parent_node: str | None = None, active_paths=None):
        if active_paths is None:
            active_paths = set()

        node_path = _node_path(material_name, node)
        if node_path in active_paths:
            logger.warning("Skipping recursive Maya material traversal cycle at '%s'.", node_path)
            return {}

        active_paths = active_paths | {node_path}
        node_type = self.cmds.nodeType(node)
        node_dict = {
            "node_name": node,
            "node_path": node_path,
            "node_type": node_type,
            "node_position": (0.0, 0.0),
            "node_parms": self._convert_parms_to_dict(node),
            "connections_dict": self._connection_to_parent(node, parent_node, material_name) if parent_node else {},
            "children_list": [],
        }

        for input_attr in MAYA_INPUT_ATTRS.get(node_type, []):
            if not self._attr_exists(node, input_attr):
                continue
            source_plug = self._input_source_plug(node, input_attr)
            if not source_plug:
                continue
            source_node, _ = _split_plug(source_plug)
            child_dict = self._traverse_recursively(source_node, material_name, node, active_paths)
            child_entry = child_dict.get(_node_path(material_name, source_node))
            if child_entry is not None:
                node_dict["children_list"].append(child_entry)

        return {node_path: node_dict}

    def run(self):
        """Traverse the Maya material graph.

        Returns:
            Tuple[Dict, Dict]: Node tree dictionary and output tree dictionary.
        """
        output_tree = self.create_output_dict()
        shader_node = output_tree["surface"]["connected_node_name"]
        material_name = output_tree["surface"]["node_name"]
        return self._traverse_recursively(shader_node, material_name), output_tree

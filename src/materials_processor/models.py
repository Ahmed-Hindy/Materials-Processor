"""
copyright Ahmed Hindy. Please mention the original author if you used any part of this code
This module processes material nodes in Houdini, standardizing shader nodes and parameters.
"""
import pprint
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ConnectionEndpoint(Mapping):
    """Identifies one side of a node-to-node connection."""

    node_name: str
    node_path: str
    node_type: str
    node_index: Optional[int]
    parm_name: str
    data_type: Optional[str] = None

    @classmethod
    def from_mapping(cls, endpoint: Mapping[str, Any]) -> "ConnectionEndpoint":
        """Create a typed endpoint from traverser dictionary data."""
        return cls(
            node_name=endpoint["node_name"],
            node_path=endpoint["node_path"],
            node_type=endpoint["node_type"],
            node_index=endpoint.get("node_index"),
            parm_name=endpoint["parm_name"],
            data_type=endpoint.get("data_type"),
        )

    def with_parm_name(self, parm_name: str) -> "ConnectionEndpoint":
        """Return a copy of this endpoint with a standardized parameter name."""
        return ConnectionEndpoint(
            node_name=self.node_name,
            node_path=self.node_path,
            node_type=self.node_type,
            node_index=self.node_index,
            parm_name=parm_name,
            data_type=self.data_type,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the legacy JSON-compatible endpoint representation."""
        endpoint = {
            "node_name": self.node_name,
            "node_path": self.node_path,
            "node_type": self.node_type,
            "node_index": self.node_index,
            "parm_name": self.parm_name,
        }
        if self.data_type is not None:
            endpoint["data_type"] = self.data_type
        return endpoint

    def __getitem__(self, key):
        return self.to_dict()[key]

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self):
        return len(self.to_dict())

    def __eq__(self, other):
        if isinstance(other, ConnectionEndpoint):
            return self.to_dict() == other.to_dict()
        if isinstance(other, Mapping):
            return self.to_dict() == dict(other)
        return super().__eq__(other)


@dataclass(frozen=True)
class NodeConnection(Mapping):
    """A typed connection between an upstream input endpoint and downstream output endpoint."""

    input: ConnectionEndpoint
    output: ConnectionEndpoint

    @classmethod
    def from_mapping(cls, connection: Mapping[str, Mapping[str, Any]]) -> "NodeConnection":
        """Create a typed node connection from traverser dictionary data."""
        return cls(
            input=ConnectionEndpoint.from_mapping(connection["input"]),
            output=ConnectionEndpoint.from_mapping(connection["output"]),
        )

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Return the legacy JSON-compatible connection representation."""
        return {
            "input": self.input.to_dict(),
            "output": self.output.to_dict(),
        }

    def __getitem__(self, key):
        if key == "input":
            return self.input
        if key == "output":
            return self.output
        raise KeyError(key)

    def __iter__(self):
        return iter(("input", "output"))

    def __len__(self):
        return 2

    def __eq__(self, other):
        if isinstance(other, NodeConnection):
            return self.to_dict() == other.to_dict()
        if isinstance(other, Mapping):
            return self.to_dict() == dict(other)
        return super().__eq__(other)


@dataclass(frozen=True)
class OutputConnection(Mapping):
    """Connection metadata for one material output slot."""

    node_name: str
    node_path: str
    connected_node_name: str
    connected_node_path: str
    connected_input_index: Optional[int]
    connected_input_name: str
    connected_output_name: str

    @classmethod
    def from_mapping(cls, output_connection: Mapping[str, Any]) -> "OutputConnection":
        """Create a typed output connection from traverser dictionary data."""
        return cls(
            node_name=output_connection["node_name"],
            node_path=output_connection["node_path"],
            connected_node_name=output_connection["connected_node_name"],
            connected_node_path=output_connection["connected_node_path"],
            connected_input_index=output_connection.get("connected_input_index"),
            connected_input_name=output_connection["connected_input_name"],
            connected_output_name=output_connection["connected_output_name"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the legacy JSON-compatible output connection representation."""
        return {
            "node_name": self.node_name,
            "node_path": self.node_path,
            "connected_node_name": self.connected_node_name,
            "connected_node_path": self.connected_node_path,
            "connected_input_index": self.connected_input_index,
            "connected_input_name": self.connected_input_name,
            "connected_output_name": self.connected_output_name,
        }

    def __getitem__(self, key):
        return self.to_dict()[key]

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self):
        return len(self.to_dict())

    def __eq__(self, other):
        if isinstance(other, OutputConnection):
            return self.to_dict() == other.to_dict()
        if isinstance(other, Mapping):
            return self.to_dict() == dict(other)
        return super().__eq__(other)


@dataclass
class NodeParameter:
    """
    Represents a parameter of a node in a material network.

    Attributes:
        generic_name (Optional[str]): A standardized name for the parameter, if applicable.
        value (Optional[str]): The value of the parameter.
    """
    generic_name: Optional[str] = None
    generic_type: Optional[str] = None
    direction: Optional[str] = None  # 'input' or 'output'
    value: Optional[Any] = None

    def __repr__(self):
        return f"NodeParameter(generic_name={self.generic_name}, value={self.value})"


@dataclass
class NodeInfo:
    """
    Represents a node in a material network.

    Attributes:
        node_type (str): The type of the node.
        node_name (str): The name of the node.
        node_path (str): The path for the node.
        parameters (List[NodeParameter]): A list of parameters associated with the node.
        connection_info (dict[str, NodeConnection]): Node connection information keyed by connection id.
        children_list (List['NodeInfo']): A list of child nodes connected to this node.
        is_output_node (bool): Whether this node is an output node.
        output_type (Optional[str]): The type of output, e.g., 'surface', 'displacement', etc.
        position (Optional[int, int]): Position of the node in the material network.
    """
    node_type: str
    node_name: str
    node_path: str
    parameters: List[NodeParameter]
    connection_info: dict[str, NodeConnection] = field(default_factory=dict)
    children_list: list['NodeInfo'] = field(default_factory=list)
    is_output_node: bool = False
    output_type: Optional[str] = None
    position: Optional[list[float, float]] = None


    def __repr__(self):
        output_print = ""
        if self.is_output_node:
            output_print = f", IS_OUTPUT_NODE = {self.is_output_node}, output_type = {self.output_type}),"

        child_nodes_print = ""
        if self.children_list:
            child_nodes_print = f", children_list={self.children_list} -->"

        return (f"\n    NodeInfo(node_type='{self.node_type}', node_name='{self.node_name}', "
                f"node_path='{self.node_path}',"
                f"{output_print}{child_nodes_print})")

    def print_connections(self):
        return pprint.pformat(self.connection_info, sort_dicts=False)


@dataclass
class MaterialData:
    """
    Represents the data for a material, including its textures and nodes.

    Attributes:
        material_name (str): The name of the material.
        material_path (Optional[str]): The path to the material within the network.
        nodeinfo_list (List[NodeInfo]): A list of nodes that make up the material network.
        output_connections (Dict[str, OutputConnection]): A dictionary of output connections for the material.
    """
    material_name: str
    material_path: Optional[str] = None
    nodeinfo_list: List[NodeInfo] = field(default_factory=list)
    output_connections: Dict[str, OutputConnection] = field(default_factory=dict)

    def __str__(self):
        return self._pretty_print()

    def __repr__(self):
        return self._pretty_print()

    def _pretty_print(self):
        return f"MaterialData(material_name={self.material_name}, nodes={self.nodeinfo_list})"

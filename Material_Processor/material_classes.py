"""
copyright Ahmed Hindy. Please mention the original author if you used any part of this code
This module processes material nodes in Houdini, extracting and converting shader parameters and textures.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import pprint


@dataclass
class NodeParameter:
    """
    Represents a parameter of a node in a material network.

    Attributes:
        name (str): The name of the parameter.
        value (any): The value of the parameter.
        generic_name (Optional[str]): A standardized name for the parameter, if applicable.
    """
    name: str
    value: any
    generic_name: Optional[str] = None  # Add a standardized name attribute

    def __str__(self):
        return f""
        # return f"NodeParameter(name={self.name}, value={self.value}, generic_name={self.generic_name})"

@dataclass
class NodeInfo:
    """
    Represents a node in a material network.

    Attributes:
        node_type (str): The type of the node.
        node_name (str): The name of the node.
        parameters (List[NodeParameter]): A list of parameters associated with the node.
        node_path (str): The path to the node within the network.
        # connected_input_index (Optional[int]): The index of the input this node is connected to, if any.
        children_list (List['NodeInfo']): A list of child nodes connected to this node.
        is_output_node (bool): Whether this node is an output node.
        output_type (Optional[str]): The type of output, e.g., 'surface', 'displacement', etc.
        position (Optional[int, int]): Position of the node in the material network.
    """
    node_type: str
    node_name: str
    node_path: str
    parameters: List[NodeParameter]
    connection_info: dict[str, dict[str, Any]] = field(default_factory=dict)  # {"input": {"index": int, "parm": str}, "output": {...}}
    children_list: list['NodeInfo'] = field(default_factory=list)
    is_output_node: bool = False
    output_type: Optional[str] = None
    position: Optional[list[float, float]] = None



    # def __str__(self):
    #     output_print = "Not Output"
    #     if self.is_output_node:
    #         output_print = f"IS_OUTPUT_NODE = {self.is_output_node}, output_type = {self.output_type})"
    #
    #     return(f"NodeInfo(node_type={self.node_type}, node_name={self.node_name}, "
    #            f"node_path={self.node_path}, connected_input_index={self.connected_input_index}, "
    #            f"{output_print}, children_list=\n        {self.children_list} -->\n")

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
        textures (Dict[str, TextureInfo]): A dictionary of texture information associated with the material.
        nodeinfo_list (List[NodeInfo]): A list of nodes that make up the material network.
        output_connections (Dict[str, Optional[NodeInfo]]): A dictionary of output connections for the material.
    """
    material_name: str
    material_path: Optional[str] = None
    nodeinfo_list: List[NodeInfo] = field(default_factory=list)
    output_connections: Dict[str, NodeInfo] = field(default_factory=dict)  # Add this line

    def __str__(self):
        return self._pretty_print()

    def __repr__(self):
        return self._pretty_print()

    def _pretty_print(self):
        return f"MaterialData(material_name={self.material_name}, nodes={self.nodeinfo_list})"

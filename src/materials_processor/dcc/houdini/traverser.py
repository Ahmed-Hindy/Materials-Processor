import logging

logger = logging.getLogger(__name__)

try:
    import hou
except:
    # temp to make the module work with substance painter
    logger.warning("materialProcessor running outside of Houdini!")
    hou = None

from materials_processor.dcc.houdini.output_detector import detect_output_nodes  # noqa: E402
from materials_processor.mappings import OPENPBR_NODE_TYPE  # noqa: E402


class NodeTraverser:
    """
    Class for traversing Houdini nodes to extract their connections and output nodes.
    """

    def __init__(self, material_node, material_type):
        """
        Initialize the NodeTraverser with the specified material type.

        Args:
            material_type (str): The type of material (e.g., 'arnold', 'mtlx', 'principledshader').
        """
        self.material_node = material_node
        self.material_type = material_type
        self.output_nodes = {}

    def create_output_dict(self, material_node, material_type: str):
        """
        Detect output nodes for a material node.
        
        Parameters:
            material_node (hou.VopNode): The material node whose outputs are detected.
            material_type (str): The material type used to identify its output nodes.
        
        Returns:
            dict: A dictionary describing the detected output nodes.
        """
        logger.info("detect_output_nodes START for %s", material_node.path())
        return detect_output_nodes(material_node, material_type)

    @staticmethod
    def _detect_node_connections(node, parent_node):
        """
        Collect connections from a node to its specified parent node.
        
        Parameters:
        	node (hou.Node): The node whose outgoing connections are examined.
        	parent_node (hou.Node): The parent node used to filter relevant connections.
        
        Returns:
        	Dict[str, Dict[str, Dict[str, Any]]]: Connection metadata keyed by connection index. Each entry contains input and output node names, paths, types, indices, parameter names, and data types.
        """
        # print(f"DEBUG: parent_node.name(): {parent_node.name() if parent_node else 'None'},   node.name(): {node.name()}")
        # e.g. prints:
        # DEBUG: parent_node.name(): None,                  node.name(): 'surface_output'
        # DEBUG: parent_node.name(): surface_output,        node.name(): 'mtlxstandard_surface'
        # DEBUG: parent_node.name(): mtlxstandard_surface,  node.name(): 'image_diffuse'
        # DEBUG: parent_node.name(): mtlxstandard_surface,  node.name(): 'image_roughness'
        # DEBUG: parent_node.name(): None,                  node.name(): 'displacement_output'
        # DEBUG: parent_node.name(): displacement_output,   node.name(): 'mtlxdisplacement1'
        # DEBUG: parent_node.name(): mtlxdisplacement1,     node.name(): 'image_disp'

        connections_dict = {}
        if parent_node is None:
            return connections_dict

        for i, connection in enumerate(node.outputConnections()):
            # We only want to get the output connections of the parent node. We don't want all connections to all nodes
            if connection.outputNode().name() != parent_node.name():
                continue

            # print(f"DEBUG: -------------[{i}] input: '{input_conn.inputNode().name()}' index: '{input_conn.inputIndex()}', parm_name: '{input_conn.inputName()}'")
            # print(f"DEBUG: -------------[{i}] output: '{input_conn.outputNode().name()}' index: '{input_conn.outputIndex()}', parm_name: '{input_conn.outputName()}'")
            connections_dict.update(
                {
                    f"connection_{i}": {
                        "input": {
                            "node_name": connection.inputNode().name(),
                            "node_path": connection.inputNode().path(),
                            "node_type": connection.inputNode().type().name(),
                            "node_index": connection.outputIndex(),
                            "parm_name": connection.inputName(),
                            "data_type": connection.inputDataType(),
                        },
                        "output": {
                            "node_name": connection.outputNode().name(),
                            "node_path": connection.outputNode().path(),
                            "node_type": connection.outputNode().type().name(),
                            "node_index": connection.inputIndex(),
                            "parm_name": connection.outputName(),
                            "data_type": connection.outputDataType(),
                        },
                    }
                }
            )

        return connections_dict

    @staticmethod
    def _convert_parms_to_dict(node):
        """
        Convert a Houdini VOP node's parameters and outgoing connections into input and output metadata.
        
        Parameters:
            node: Houdini VOP node to inspect.
        
        Returns:
            A dictionary with ``input`` and ``output`` lists containing parameter names,
            values, data types, and directions.
        """

        def strip_prefix(s: str, prefix: str) -> str:
            """Remove the specified prefix from a string when it is present.
            
            Parameters:
            	s (str): The string to process.
            	prefix (str): The prefix to remove.
            
            Returns:
            	str: The string without the prefix when present; otherwise, the original string.
            """
            return s[len(prefix) :] if s.startswith(prefix) else s

        def compute_datatype_and_components(tpl) -> tuple[str, int]:
            # e.g. tpl.dataType().name() -> "parmData.Float"
            """
            Determine a parameter's normalized data type and component count.
            
            Parameters:
                tpl: Parameter template providing data type, naming scheme, and component count.
            
            Returns:
                tuple[str, int]: The normalized data type and number of components.
            """
            raw_dt = tpl.dataType().name()
            dt = strip_prefix(raw_dt, "parmData.").lower()

            # if it’s a single‐float that really is a color/vector, pick its namingScheme
            if dt == "float":
                raw_scheme = tpl.namingScheme().name()  # e.g. "parmNamingScheme.RGBA"
                scheme = strip_prefix(raw_scheme, "parmNamingScheme.").lower().rstrip("1")
                if scheme in {"rgb", "rgba", "xyzw"}:
                    dt = scheme

            return dt, tpl.numComponents()

        parms = {"input": [], "output": []}

        # ——— Inputs ———
        for p in node.parmTuples():
            tpl = p.parmTemplate()
            # skip UI folder/label/separator types
            if tpl.type() in {
                hou.parmTemplateType.FolderSet,
                hou.parmTemplateType.Folder,
                hou.parmTemplateType.Label,
                hou.parmTemplateType.Separator,
            }:
                continue
            val = p.eval()
            if val is None:
                continue

            dt, comps = compute_datatype_and_components(tpl)
            parms["input"].append(
                {
                    "generic_name": p.name(),
                    "value": val,
                    "type": f"{dt}{comps}",
                    "direction": "input",
                }
            )

        # ——— Outputs via actual connections ———
        for conn in node.outputConnections():
            in_name = conn.inputName()
            out_node = conn.outputNode()
            out_name = conn.outputName()
            if not out_node.parmTuple(out_name):
                print(f"WARNING: Parm Not found {out_node.path()}/{out_name}, skipping.")
                continue

            tpl = out_node.parmTuple(out_name).parmTemplate()
            dt, comps = compute_datatype_and_components(tpl)
            parms["output"].append(
                {
                    "generic_name": in_name,
                    "value": None,
                    "type": f"{dt}{comps}",
                    "direction": "output",
                }
            )
        return parms

    def _traverse_recursively_node_tree(self, node, parent_node=None, active_paths=None):
        """
        Build a dictionary representation of a node and its input hierarchy.
        
        Parameters:
            node (hou.Node): The node to traverse.
            parent_node (hou.Node, optional): The parent node used to describe connections to the current node.
            active_paths (set, optional): Node paths currently being traversed, used to skip recursive cycles.
        
        Returns:
            dict: A dictionary keyed by node path containing node metadata, connections, parameters, and child nodes.
        """
        if active_paths is None:
            active_paths = set()
        if node.path() in active_paths:
            logger.warning("Skipping recursive material traversal cycle at '%s'.", node.path())
            return {}

        active_paths = active_paths | {node.path()}

        # get a dict with all input and output connections related to the node
        connections_dict = self._detect_node_connections(node, parent_node)

        # Initialize the node's dictionary with metadata
        node_dict = {
            "node_name": node.name(),
            "node_path": node.path(),
            "node_type": node.type().name(),
            "node_position": (node.position()[0], node.position()[1]),
            "node_parms": self._convert_parms_to_dict(node),
            "connections_dict": connections_dict,
            "children_list": [],
        }

        if not node.inputs():
            return {node.path(): node_dict}

        for input_node in node.inputs():
            if not input_node:
                continue

            # Recursively get child nodes
            input_node_dict = self._traverse_recursively_node_tree(input_node, node, active_paths)
            input_node_entry = input_node_dict.get(input_node.path())
            if input_node_entry is None:
                continue

            node_dict["children_list"].append(input_node_entry)

        return {node.path(): node_dict}

    def run(self):
        """
        Builds the material node tree and identifies its output nodes.
        
        Returns:
            tuple: The node tree dictionary and output-node dictionary.
        """
        # first, get an output_nodes_dict
        output_tree = self.create_output_dict(self.material_node, self.material_type)

        if self.material_type == "principledshader":
            node_tree = self._traverse_recursively_node_tree(self.material_node)
        else:
            node_tree = {}
            for output_type, output_dict in output_tree.items():
                node_tree.update(self._traverse_recursively_node_tree(hou.node(output_dict["node_path"])))

        return node_tree, output_tree


def _subnet_has_node_type(materialbuilder_node, node_type):
    """Determine whether a material builder contains a child node of the specified type.
    
    Parameters:
    	materialbuilder_node: The material builder node whose children are inspected.
    	node_type: The node type name to find.
    
    Returns:
    	bool: `true` if a child has the specified type, `false` otherwise.
    """
    return any(child.type().name() == node_type for child in materialbuilder_node.children())


def _subnet_surface_output_node_type(materialbuilder_node):
    """Return the node type connected to the subnet's surface output connector.
    
    Parameters:
    	materialbuilder_node: The subnet node whose surface output connection is inspected.
    
    Returns:
    	str or None: The connected node type, or `None` when no surface output connection is available.
    """
    for child in materialbuilder_node.children():
        if child.type().name() != "subnetconnector":
            continue

        parm = child.parm("parmname")
        if parm is not None and parm.eval() != "surface":
            continue

        for connection in child.inputConnections():
            input_node = connection.inputNode()
            if input_node:
                return input_node.type().name()
    return None


def get_material_type(materialbuilder_node):
    """
    Determine the material type represented by a material-builder node.
    
    Parameters:
    	materialbuilder_node (hou.VopNode): Material shading network node to classify.
    
    Returns:
    	str or None: Normalized material type, or `None` when the node type is unsupported.
    """
    material_type = None

    materialbuilder_type = materialbuilder_node.type().name()
    if materialbuilder_type == "arnold_materialbuilder":
        material_type = "arnold"
    elif materialbuilder_type == "subnet":
        surface_output_type = _subnet_surface_output_node_type(materialbuilder_node)
        has_output_connectors = _subnet_has_node_type(materialbuilder_node, "subnetconnector")
        if surface_output_type == OPENPBR_NODE_TYPE or (
            surface_output_type is None
            and not has_output_connectors
            and _subnet_has_node_type(materialbuilder_node, OPENPBR_NODE_TYPE)
        ):
            material_type = "openpbr"
        else:
            for child_node in materialbuilder_node.children():
                if "mtlx" in child_node.type().name():
                    material_type = "mtlx"
                    break
    elif materialbuilder_type == "redshift_vopnet":
        material_type = "redshift_vopnet"
    elif materialbuilder_type == "rs_usd_material_builder":
        material_type = "rs_usd_material_builder"

    elif materialbuilder_type == "principledshader::2.0":
        material_type = "principledshader"

    return material_type

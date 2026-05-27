import logging

logger = logging.getLogger(__name__)

try:
    import hou
except:
    # temp to make the module work with substance painter
    logger.warning("materialProcessor running outside of Houdini!")
    hou = None


def _detect_arnold_output_nodes(material_node):
    """
    Detect Arnold output nodes in the node tree.

    Args:
        material_node (hou.Node): The parent Houdini node.

    Returns:
        Dict: A dictionary of detected Arnold output nodes.
    """
    arnold_output = None
    for child in material_node.children():
        if child.type().name() == 'arnold_material':
            arnold_output = child
            break
    if not arnold_output:
        raise Exception("No Output Node detected for Arnold Material")

    output_nodes = {}
    connections = arnold_output.inputConnections()
    for connection in connections:
        connected_input = connection.inputNode()
        connected_input_index = connection.outputIndex()
        connected_input_name = connection.outputName()
        connected_input_datatype = connection.inputDataType()
        connected_output_index = connection.inputIndex()
        connected_output_name = connection.inputName()
        connected_output_datatype = connection.outputDataType()
        if connected_output_index == 0:
            output_nodes['surface'] = {
                'node_name': arnold_output.name(),
                'node_path': arnold_output.path(),
                'connected_node_name': connected_input.name(),
                'connected_node_path': connected_input.path(),
                'connected_input_index': connected_input_index,
                'connected_input_name': connected_input_name,
                'connected_input_datatype': connected_input_datatype,
                'connected_output_index': connected_output_index,
                'connected_output_name': connected_output_name,
                'connected_output_datatype': connected_output_datatype,
                'generic_type': 'GENERIC::output_surface'
            }
        elif connected_output_index == 1:
            output_nodes['displacement'] = {
                'node_name': arnold_output.name(),
                'node_path': arnold_output.path(),
                'connected_node_name': connected_input.name(),
                'connected_node_path': connected_input.path(),
                'connected_input_index': connected_input_index,
                'connected_input_name': connected_input_name,
                'connected_input_datatype': connected_input_datatype,
                'connected_output_index': connected_output_index,
                'connected_output_name': connected_output_name,
                'connected_output_datatype': connected_output_datatype,
                'generic_type': 'GENERIC::output_displacement'
            }
    return output_nodes


def _detect_mtlx_output_nodes(material_node):
    """
    Detect MaterialX output nodes in the node tree.

    Args:
        material_node (hou.Node): The parent Houdini node.

    Returns:
        Dict: A dictionary of detected MaterialX output nodes.
    """
    output_nodes = {}
    output_nodes_list = [child for child in material_node.children() if child.type().name() == 'subnetconnector']

    for output_node in output_nodes_list:
        connections = output_node.inputConnections()
        for connection in connections:
            connected_input = connection.inputNode()
            connected_input_index = connection.outputIndex()
            connected_input_name = connection.outputName()
            connected_input_datatype = connection.inputDataType()
            connected_output_index = connection.inputIndex()
            connected_output_name = connection.inputName()
            connected_output_datatype = connection.outputDataType()
            output_type = output_node.parm('parmname').eval()
            if output_type not in ['surface', 'displacement']:
                logger.warning("Unknown MaterialX output type '%s/%s' detected, skipping.", output_node.name(), output_type)
                continue

            output_nodes[output_type] = {
                'node_name': output_node.name(),
                'node_path': output_node.path(),
                'connected_node_name': connected_input.name(),
                'connected_node_path': connected_input.path(),
                'connected_input_index': connected_input_index,
                'connected_input_name': connected_input_name,
                'connected_input_datatype': connected_input_datatype,
                'connected_output_index': connected_output_index,
                'connected_output_name': connected_output_name,
                'connected_output_datatype': connected_output_datatype,
            }
    return output_nodes


def _detect_redshift_vopnet_output_nodes(material_node):
    """
    Detect redshift_vopnet output nodes in the node tree.

    Args:
        material_node (hou.Node): The parent Houdini node.

    Returns:
        Dict: A dictionary of detected redshift_vopnet output nodes.
    """
    redshift_output = None
    for child in material_node.children():
        if child.type().name() == 'redshift_material':
            redshift_output = child
            break
    if not redshift_output:
        raise Exception("No Output Node detected for 'redshift_vopnet' Material")

    output_nodes = {}
    connections = redshift_output.inputConnections()
    for connection in connections:
        connected_input = connection.inputNode()
        connected_input_index = connection.outputIndex()
        connected_input_name = connection.outputName()
        connected_input_datatype = connection.inputDataType()
        connected_output_index = connection.inputIndex()
        connected_output_name = connection.inputName()
        connected_output_datatype = connection.outputDataType()
        if connected_output_index == 0:
            output_nodes['surface'] = {
                'node_name': redshift_output.name(),
                'node_path': redshift_output.path(),
                'connected_node_name': connected_input.name(),
                'connected_node_path': connected_input.path(),
                'connected_input_index': connected_input_index,
                'connected_input_name': connected_input_name,
                'connected_input_datatype': connected_input_datatype,
                'connected_output_index': connected_output_index,
                'connected_output_name': connected_output_name,
                'connected_output_datatype': connected_output_datatype,

                'generic_type': 'GENERIC::output_surface'
            }
        elif connected_output_index == 1:
            output_nodes['displacement'] = {
                'node_name': redshift_output.name(),
                'node_path': redshift_output.path(),
                'connected_node_name': connected_input.name(),
                'connected_node_path': connected_input.path(),
                'connected_input_index': connected_input_index,
                'connected_input_name': connected_input_name,
                'connected_input_datatype': connected_input_datatype,
                'connected_output_index': connected_output_index,
                'connected_output_name': connected_output_name,
                'connected_output_datatype': connected_output_datatype,
                'generic_type': 'GENERIC::output_displacement'
            }
    return output_nodes


def _detect_RsUsdMaterialbuilder_output_nodes(material_node):
    """
    Detect rs usd materialbuilder output nodes in the node tree.

    Args:
        material_node (hou.Node): The parent Houdini node.

    Returns:
        Dict: A dictionary of detected redshift_vopnet output nodes.
    """
    redshift_output = None
    for child in material_node.children():
        if child.type().name() == 'suboutput':
            redshift_output = child
            break
    if not redshift_output:
        raise Exception("No Output Node detected for 'rs usd materialbuilder' Material")

    output_nodes = {}
    connections = redshift_output.inputConnections()
    for connection in connections:
        connected_input = connection.inputNode()
        connected_input_index = connection.outputIndex()
        connected_input_name = connection.outputName()
        connected_input_datatype = connection.inputDataType()
        connected_output_index = connection.inputIndex()
        connected_output_name = connection.inputName()
        connected_output_datatype = connection.outputDataType()
        if connected_output_index == 0:
            output_nodes['surface'] = {
                'node_name': redshift_output.name(),
                'node_path': redshift_output.path(),
                'connected_node_name': connected_input.name(),
                'connected_node_path': connected_input.path(),
                'connected_input_index': connected_input_index,
                'connected_input_name': connected_input_name,
                'connected_input_datatype': connected_input_datatype,
                'connected_output_name': connected_output_name,
                'connected_output_index': connected_output_index,
                'connected_output_datatype': connected_output_datatype,
                'generic_type': 'GENERIC::output_surface'
            }
        elif connected_output_index == 1:
            output_nodes['displacement'] = {
                'node_name': redshift_output.name(),
                'node_path': redshift_output.path(),
                'connected_node_name': connected_input.name(),
                'connected_node_path': connected_input.path(),
                'connected_input_index': connected_input_index,
                'connected_input_name': connected_input_name,
                'connected_input_datatype': connected_input_datatype,
                'connected_output_name': connected_output_name,
                'connected_output_index': connected_output_index,
                'connected_output_datatype': connected_output_datatype,
                'generic_type': 'GENERIC::output_displacement'
            }
    return output_nodes


def _detect_principled_output_nodes(material_node):
    """
    Detect Principled Shader output nodes in the node tree.

    Returns:
        Dict: A dictionary with the single 'surface' output connection,
              mirroring Arnold's structure so downstream code works unchanged.

    """
    return {
        "surface": {
            "node_name": "surface_output",
            "node_path": f"{material_node.path()}/surface_output",
            "connected_node_name": "mtlxstandard_surface",
            "connected_node_path": f"{material_node.path()}/mtlxstandard_surface",
            "connected_input_index": 0,
            "connected_input_name": "suboutput",
            "connected_input_datatype": "surface",
            "connected_output_index": 0,
            "connected_output_name": "out",
            "connected_output_datatype": "surface"
        },
        "displacement": {
            "node_name": "displacement_output",
            "node_path": f"{material_node.path()}/displacement_output",
            "connected_node_name": "mtlxdisplacement",
            "connected_node_path": f"{material_node.path()}/mtlxdisplacement",
            "connected_input_index": 0,
            "connected_input_name": "suboutput",
            "connected_input_datatype": "displacement",
            "connected_output_index": 0,
            "connected_output_name": "out",
            "connected_output_datatype": "displacement"
        },
    }


def detect_output_nodes(material_node, material_type: str):
    """Route to the correct renderer-specific detector."""
    if material_type == 'arnold':
        return _detect_arnold_output_nodes(material_node)
    elif material_type == 'mtlx':
        return _detect_mtlx_output_nodes(material_node)
    elif material_type == 'redshift_vopnet':
        return _detect_redshift_vopnet_output_nodes(material_node)
    elif material_type == 'rs_usd_material_builder':
        return _detect_RsUsdMaterialbuilder_output_nodes(material_node)
    elif material_type == 'principledshader':
        return _detect_principled_output_nodes(material_node)
    else:
        raise KeyError(f"Unsupported renderer: {material_type=}")
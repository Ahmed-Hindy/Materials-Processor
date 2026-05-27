"""Public Houdini command entrypoints for shelf and menu tools."""

import logging
import os
import traceback
from importlib import resources

from materials_processor.houdini.recreator import NodeRecreator
from materials_processor.houdini.traverser import NodeTraverser, get_material_type, hou
from materials_processor import io
from materials_processor.mappings import FORMAT_CHOICES
from materials_processor.standardizer import NodeStandardizer
from materials_processor.logging_config import setup_file_logging

logger = logging.getLogger(__name__)
setup_file_logging()

def ingest_material(material_node):
    try:
        material_type = get_material_type(material_node)
        if not material_type:
            logger.warning("Couldn't determine Input material type, "
                           "currently only Arnold, MTLX, Redshift Standard Material and Principled Shader are supported!")
            return None, None, None

        logger.info("NodeTraverser() START----------------------")
        traverser = NodeTraverser(material_node, material_type=material_type)
        nested_nodes_dict, output_nodes_dict = traverser.run()
        # logger.debug("nested_nodes_dict: %s", pprint.pformat(nested_nodes_dict, sort_dicts=False))
        # print(f"DEBUG: output_nodes_dict: {pprint.pformat(output_nodes_dict, sort_dicts=False)}")
        # DEBUG: traverser.output_nodes_dict: {
        #     "surface": {
        #         "node_name": "OUT_material",
        #         "node_path": "/mat/arnold_materialbuilder_basic/OUT_material",
        #         "connected_node_name": "standard_surface",
        #         "connected_node_path": "/mat/arnold_materialbuilder_basic/standard_surface",
        #         "connected_input_index": 0,
        #         "connected_input_name": "surface",
        #         "connected_output_name": "shader",
        #         "generic_type": "GENERIC::output_surface"
        #     }
        # }
        # DEBUG: material_type: 'arnold'
        # DEBUG: material_node: 'arnold_materialbuilder_basic'
        logger.info("NodeTraverser() Finished----------------------")


        logger.info("NodeStandardizer() START----------------------")
        standardizer = NodeStandardizer(
            traversed_nodes_dict=nested_nodes_dict,
            output_nodes_dict=output_nodes_dict,
            material_type=material_type,
            source_type='hou_vop_nodes',
        )
        nodeinfo_list, output_connections = standardizer.run()

        # for nodeinfo in nodeinfo_list:
        #     print(f"DEBUG: nodeinfo: {nodeinfo=}\n")

        # DEBUG: output_connections:        {'GENERIC::output_surface':
        #                                       {'node_name': 'OUT_material',
        #                                           'node_path': '/mat/arnold_materialbuilder_basic/OUT_material',
        #                                           'connected_node_name': 'standard_surface',
        #                                           'connected_node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
        #                                           'connected_input_index': 0
        #                                       }
        #                                   }
        # DEBUG: target_context.path()='/mat'
        # DEBUG: target_format='mtlx'
        logger.info("NodeStandardizer() Finished----------------------")

        return material_type, nodeinfo_list, output_connections

    except Exception:
        logger.exception("Exception in ingest_material")
        return None, None, None


def run(input_material_builder_node, target_context, target_format='arnold'):
    """
    Run the material conversion process for the selected node.

    Args:
        input_material_builder_node (hou.Node): The selected Houdini shading network,
                                                e.g., arnold materialbuilder or mtlx materialbuilder.
        target_context (hou.Node): The target Houdini context node.
        target_format (str, optional): The target renderer (default is 'mtlx').
    """
    material_type, nodeinfo_list, output_connections = ingest_material(input_material_builder_node)
    if not (material_type and nodeinfo_list and output_connections):
        return

    try:
        logger.info("NodeRecreator() START----------------------")
        recreator = NodeRecreator(
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
            target_context=target_context,
            target_renderer=target_format
        )
        recreator.run()
        logger.info("NodeRecreator() Finished----------------------")
        logger.info("Material conversion complete. Converted material from '%s' to '%s'.", material_type, target_format)
    except Exception:
        logger.exception("Exception in run")
        return


def convert_material_from_opmenu(kwargs):
    """
    Houdini op-menu / shelf tool entry to convert selected material builder(s)
    into the given target_format (e.g. 'mtlx', 'arnold', 'rs_usd_material_builder').

    Example:
         kwargs={
         'items': [<hou.VopNode of type subnet at /mat/mtlxmaterial_basic>],
         'node': <hou.VopNode of type subnet at /mat/mtlxmaterial_basic>,
         'networkeditorpos': (6.704338180657215, 3.538853007111061),
         'commonparent': True,
         'networkeditor': <hou.NetworkEditor panetab10>,
         'toolname': 'h.pane.wsheet.axe_convert_material',
         'altclick': False,
         'ctrlclick': False,
         'shiftclick': False,
         'cmdclick': False
         }
    """

    if not kwargs.get('items'):
        return

    node = kwargs["node"]

    # display a choice dialog for the user to select the target renderer
    allowed_types = FORMAT_CHOICES.copy()
    if 'HTOA' not in os.environ:
        allowed_types.pop('arnold', None)
    if 'REDSHIFT_COREDATAPATH' not in os.environ:
        allowed_types.pop('rs_usd_material_builder', None)

    allowed_types['cancel'] = 'Cancel'
    names, labels = zip(*allowed_types.items(), strict=False)

    choice = hou.ui.displayMessage(
        text="Select Target Renderer",
        buttons=list(labels),
        default_choice=0,
        close_choice=len(labels)-1,
        title='Material Conversion',
    )
    if choice < 0 or choice >= len(names) or choice == len(labels)-1:
        return
    target_format = names[choice]


    for input_material_builder_node in kwargs['items']:
        # Check if the selected nodes are VOP nodes
        if not isinstance(input_material_builder_node, hou.VopNode):
            logger.warning("Selected node '%s' is not a VOP node. Skipping.", input_material_builder_node.path())
            continue

        # Ingest the material and get the node info and output connections
        material_type, nodeinfo_list, output_connections = ingest_material(input_material_builder_node)
        if not (material_type and nodeinfo_list and output_connections):
            continue

        target_context = input_material_builder_node.parent()
        try:
            logger.info("NodeRecreator() START----------------------")
            recreator = NodeRecreator(
                nodeinfo_list=nodeinfo_list,
                output_connections=output_connections,
                target_context=target_context,
                target_renderer=target_format,
                material_name=input_material_builder_node.name(),
            )
            recreator.run()
            logger.info("NodeRecreator() Finished----------------------")
            logger.info("Material conversion complete. Converted material from '%s' to '%s'.", material_type, target_format)
        except Exception:
            logger.exception("Exception in convert_material_from_opmenu for node %s", input_material_builder_node.name())
            continue









def test():
    """
    Test function to validate the node traversal, standardization, and recreation process.
    """
    target_renderer = 'mtlx'
    material_type = 'mtlx'

    node_tree = io.load_node_tree_json(resources.files("materials_processor.fixtures") / "houdini_mtlx_full_traversed_nodes.json")
    output_nodes = io.load_node_tree_json(resources.files("materials_processor.fixtures") / "houdini_mtlx_full_output_nodes.json")

    standardizer = NodeStandardizer(
        traversed_nodes_dict=node_tree,
        output_nodes_dict=output_nodes,
        material_type=material_type,
        source_type='hou_vop_nodes',
    )
    nodeinfo_list, output_connections = standardizer.run()

    # print(f"DEBUG: {standardizer.node_info_list=}")
    return nodeinfo_list, output_connections




def test_hou():
    target_context = hou.node('/mat')
    target_renderer = 'arnold'
    material_type = 'arnold'
    try:
        nodeinfo_list, output_connections = test()

        recreator = NodeRecreator(
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
            target_context=target_context,
            target_renderer=target_renderer
        )
        recreator.run()
    except Exception:
        traceback.print_exc()
        return


"""
how to run from houdini shelf tool:
1 - copy this block of code into a new shelf tool
2 - select a material node inside a material context
3 - run the shelf tool
4 - new mats are created in '/mat'

##########
from importlib import reload
import hou
from materials_processor.houdini import commands
reload(commands)

target_context = hou.node('/mat')
selected_nodes = hou.selectedNodes()
if selected_nodes:
    for node in selected_nodes:
        parent = node.parent()
        commands.run(node, parent)
    
###################


"""





if __name__ == "__main__":
    test()



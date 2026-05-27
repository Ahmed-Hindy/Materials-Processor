import logging
import traceback

from materials_processor.houdini import commands as houdini_commands
from materials_processor.standardizer import NodeStandardizer
from materials_processor.usd.recreator import USDMaterialRecreator
from materials_processor.usd.traverser import USDTraverser

logger = logging.getLogger(__name__)

def get_material_type(usd_material):
    """
    Args:
        usd_material (Usd.Material): input material prim, e.g., arnold materialbuilder
    Returns:
        (str): material type.
    """
    material_list = []
    infoId_list = []
    for x in usd_material.GetPrim().GetChildren():
        infoId_list.append(x.GetAttribute('info:id').Get())

    if 'arnold:standard_surface' in infoId_list:
        material_list.append('arnold')
    if 'ND_standard_surface_surfaceshader' in infoId_list:
        material_list.append('mtlx')
    if 'redshift::StandardMaterial' in infoId_list:
        material_list.append('rs_usd_material_builder')

    material_list = tuple(material_list)
    if len(material_list) > 1:
        raise NotImplementedError(f"ERROR: multiple material types found: '{material_list}', Script only supports one material type at a time.")
    if len(material_list) == 0:
        raise NotImplementedError("ERROR: Couldn't determine Input material type.")

    material_type = material_list[0]

    return material_type



def test(stage, mat_node, target_renderer="mtlx"):
    import hou


    material_type, nodeinfo_list, output_connections = houdini_commands.ingest_material(mat_node)
    if not (material_type and nodeinfo_list and output_connections):
        return

    logger.info("Starting USDMaterialRecreator test")
    """
    DEBUG: material_type='arnold'
    DEBUG: node_info_list=[
        NodeInfo(node_type='GENERIC::output_node', node_name='OUT_material', node_path='/mat/arnold_materialbuilder_basic/OUT_material',, children_list=[
        NodeInfo(node_type='GENERIC::standard_surface', node_name='standard_surface', node_path='/mat/arnold_materialbuilder_basic/standard_surface',, children_list=[
        NodeInfo(node_type='GENERIC::image', node_name='image_diffuse', node_path='/mat/arnold_materialbuilder_basic/image_diffuse',), 
        NodeInfo(node_type='GENERIC::image', node_name='image_roughness', node_path='/mat/arnold_materialbuilder_basic/image_roughness',)] -->)] -->)]
    DEBUG: orig_output_connections={'GENERIC::output_surface': {'node_name': 'OUT_material', 'node_path': '/mat/arnold_materialbuilder_basic/OUT_material', 'connected_node_name': 'standard_surface', 'connected_node_path': '/mat/arnold_materialbuilder_basic/standard_surface', 'connected_input_index': 0}}
    """

    try:
        USDMaterialRecreator(stage, mat_node.name(), nodeinfo_list, output_connections, target_renderer=target_renderer)
    except Exception:
        logger.exception("Exception in test")


def test2(stage, usd_material, target_renderer="arnold"):
    """
    Args:
        stage (Usd.Stage): USD stage
        usd_material (Usd.Material): USD material
        target_renderer (str): target renderer to convert to ['arnold', 'mtlx']
    Returns:
        None
    """
    import hou

    mat_prim = usd_material.GetPrim()
    mat_name = mat_prim.GetName()

    material_type = get_material_type(usd_material)
    if not material_type :
        logger.error("Couldn't determine Input material type.")
        return None

    nested_nodes_dict, output_nodes_dict  = USDTraverser(stage, mat_prim, material_type).run()
    # print(f"DEBUG: nested: {pprint.pformat(nested, sort_dicts=False)}")
    # print(f"DEBUG: outputs: {pprint.pformat(outputs, sort_dicts=False)}")
    # DEBUG: nested: {'/materials/arnold_materialbuilder_basic': {
    #                                              'node_name': 'arnold_materialbuilder_basic',
    #                                              'node_path': '/materials/arnold_materialbuilder_basic',
    #                                              'node_type': 'Material',
    #                                              'node_parms': [],
    #                                              'connections_dict': {},
    #                                              'children_list': [{'node_name': 'standard_surface',
    #                                                                 'node_path': '/materials/arnold_materialbuilder_basic/standard_surface',
    #                                                                 'node_type': 'arnold:standard_surface',
    #                                                                 'node_parms': [],
    #                                                                 'connections_dict': {'connection_0': {'input': {'node_name': 'standard_surface',
    #                                                                                                                 'node_path': '/materials/arnold_materialbuilder_basic/standard_surface',
    #                                                                                                                 'node_index': 0,
    #                                                                                                                 'parm_name': 'base_color'},
    #                                                                                                       'output': {'node_name': 'image_diffuse',
    #                                                                                                                  'node_path': '/materials/arnold_materialbuilder_basic/image_diffuse',
    #                                                                                                                  'node_index': 0,
    #                                                                                                                  'parm_name': 'rgba'}},
    #                                                                                      'connection_1': {'input': {'node_name': 'standard_surface',
    #                                                                                                                 'node_path': '/materials/arnold_materialbuilder_basic/standard_surface',
    #                                                                                                                 'node_index': 0,
    #                                                                                                                 'parm_name': 'specular_roughness'},
    #                                                                                                       'output': {'node_name': 'image_roughness',
    #                                                                                                                  'node_path': '/materials/arnold_materialbuilder_basic/image_roughness',
    #                                                                                                                  'node_index': 0,
    #                                                                                                                  'parm_name': 'r'}}},
    #                                                                 'children_list': [{'node_name': 'image_diffuse',
    #                                                                                    'node_path': '/materials/arnold_materialbuilder_basic/image_diffuse',
    #                                                                                    'node_type': 'arnold:image',
    #                                                                                    'node_parms': [],
    #                                                                                    'connections_dict': {},
    #                                                                                    'children_list': []},
    #                                                                                   {'node_name': 'image_roughness',
    #                                                                                    'node_path': '/materials/arnold_materialbuilder_basic/image_roughness',
    #                                                                                    'node_type': 'arnold:image',
    #                                                                                    'node_parms': [],
    #                                                                                    'connections_dict': {},
    #                                                                                    'children_list': []}]}]}}
    # DEBUG: outputs: {'surface': {'node_name': 'arnold_materialbuilder_basic',
    #              'node_path': '/materials/arnold_materialbuilder_basic',
    #              'connected_node_name': 'standard_surface',
    #              'connected_node_path': '/materials/arnold_materialbuilder_basic/standard_surface',
    #              'connected_input_index': 0,
    #              'connected_input_name': 'surface',
    #              'connected_output_name': 'shader',
    #              'generic_type': 'GENERIC::output_surface'}}
    if not (nested_nodes_dict and output_nodes_dict):
        return None

    standardizer = NodeStandardizer(
        traversed_nodes_dict=nested_nodes_dict,
        output_nodes_dict=output_nodes_dict,
        material_type=material_type,
        source_type='usd_prims',
    )
    nodeinfo_list, output_connections = standardizer.run()

    try:
        USDMaterialRecreator(stage, "__material", nodeinfo_list, output_connections,
                             target_renderer=target_renderer)
    except Exception:
        logger.exception("Exception in test2")


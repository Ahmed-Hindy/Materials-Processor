"""USD material graph traversal."""

import logging
import re

from pxr import Gf, Sdf, UsdShade

from materials_processor.usd.mappings import (
    GENERIC_OUTPUT_TYPES,
    OUT_PRIMS_TYPES,
    SKIPPED_ATTRIBS,
)

logger = logging.getLogger(__name__)

def split_trailing_number(s: str):
    try:
        m = re.match(r'^(.*?)(\d+)$', s)
        if m:
            base, num = m.groups()
            return base, int(num)
        else:
            return s, 1
    except Exception as e:
        logger.error("%s, %s, %s", s, type(s), e)






class USDTraverser:
    """
    Traverse a UsdShade.Material prim to extract its shading network
    in a nested dict format matching the Houdini NodeTraverser JSON.

    Attributes:
        stage (Usd.Stage): The USD stage containing the material.
        material_prim
        material_type (UsdShade.Material): The material to traverse.
        nested_nodes (Dict[str, dict]): Nested shader-graph per material.
    """

    def __init__(self, stage, material_prim, material_type):
        """
        Initialize the USDTraverser.

        Args:
            stage (Usd.Stage): The stage containing the material.
            material_type (UsdShade.Material): The material prim to traverse.
        """
        self.stage = stage
        self.material_prim = material_prim
        self.material_type = material_type
        self.nested_nodes = {}

    def create_output_dict(self, material_prim, material_type):
        """
        Detect all outputs on the material and record connected shader info.

        Returns:
            Dict[str, dict]: Mapping each generic output name ('surface', 'displacement')
            to a dict containing:
                node_name (str): The material prim name.
                node_path (str): The material prim path.
                connected_node_name (str): The downstream shader prim name.
                connected_node_path (str): The downstream shader prim path.
                connected_input_index (int): Always -1 for now.
                connected_input_name (str): The generic output slot ('surface' etc).
                connected_output_name (str): The shader parameter name driving it.
                generic_type (str): One of GENERIC::output_surface/displacement.
        """
        mat_prim = material_prim.GetPrim()
        mat_name = mat_prim.GetName()
        mat_path = mat_prim.GetPath().pathString
        mat_shader = UsdShade.Shader(mat_prim)
        output_nodes = {}

        for out in mat_shader.GetOutputs():
            # baseName may include renderer prefix, e.g. "arnold:surface"
            out_basename = out.GetBaseName()
            base = out_basename.split(':')[-1]
            sources: tuple[list[UsdShade.ConnectionSourceInfo]] = out.GetConnectedSources()

            for source in sources:
                for srcInfo in source:
                    srcInfo                       # type: UsdShade.ConnectionSourceInfo
                    srcAPI  = srcInfo.source      # type: UsdShade.ConnectableAPI
                    srcName = srcInfo.sourceName  # type: str               # e.g. "shader"
                    srcType = srcInfo.sourceType  # type: UsdShade.AttributeType  # e.g. pxr.UsdShade.AttributeType.Output
                    src_prim = srcAPI.GetPrim()
                    # print(f"DEBUG: connection from: '{src_prim.GetName()}[{srcName}]' -> "
                    #       f"'{mat_name}[{base}]'")

                    output_nodes[base] = {
                        "node_name": mat_prim.GetName(),
                        "node_path": mat_prim.GetPath().pathString,
                        "connected_node_name": src_prim.GetPrim().GetName(),
                        "connected_node_path": src_prim.GetPath().pathString,
                        "connected_input_index": -1,
                        "connected_input_name":  srcName,
                        "connected_output_name": out_basename,
                        "generic_type":     GENERIC_OUTPUT_TYPES.get(base)
                    }

        # print(f"DEBUG: output_nodes: {pprint.pformat(output_nodes, sort_dicts=False)}")
        # DEBUG: output_nodes: {'surface': {'node_name': 'arnold_materialbuilder_basic',
        #              'node_path': '/materials/arnold_materialbuilder_basic',
        #              'connected_node_name': 'standard_surface',
        #              'connected_node_path': '/materials/arnold_materialbuilder_basic/standard_surface',
        #              'connected_input_name': 'shader',
        #              'connected_output_name': 'surface',
        #              'generic_type': 'GENERIC::output_surface'}}
        return output_nodes


    def _detect_node_connections(self, srcInfo, shader, dest_param, count):
        """
        Args:


        Returns:
            dict: Mapping of GENERIC outputs to upstream info.

        """
        srcAPI = srcInfo.source  # type: UsdShade.ConnectableAPI
        srcName = srcInfo.sourceName  # type: str                     # e.g. "shader"
        srcType = srcInfo.sourceType  # type: UsdShade.AttributeType  # e.g. pxr.UsdShade.AttributeType.Output
        src_prim = srcAPI.GetPrim()
        src_shader = UsdShade.Shader(src_prim)

        shader_prim = shader.GetPrim()

        connections_dict = {}

        connections_dict.update({f"connection_{count}": {
                "input": {
                    "node_name": src_prim.GetName(),
                    "node_path": src_prim.GetPath().pathString,
                    "node_type": self._get_shader_infoId_attrib(src_prim),
                    "node_index": -1,
                    "parm_name": srcName,
                },
                "output": {
                    "node_name": shader_prim.GetName(),
                    "node_path": shader_prim.GetPath().pathString,
                    "node_type": self._get_shader_infoId_attrib(shader_prim),
                    "node_index": -1,
                    "parm_name": dest_param,
                }
            }
        })
        return connections_dict


    def _get_shader_infoId_attrib(self, shader):
        """
        Args:
            shader (UsdShade.Shader): The shader we want to get the info:id of.
        Returns:
            str: attribute 'info:id'
        """
        shader_prim = shader.GetPrim()
        shader_infoId = shader_prim.GetAttribute('info:id').Get()
        if shader_infoId:
            return shader_infoId

        return OUT_PRIMS_TYPES[self.material_type]

    def _normalize_attribute_names(self, attribute_name, node_type):
        """

        """
        leading_strs = ['arnold:', 'inputs:']
        for leading_str in leading_strs:
            if attribute_name.startswith(leading_str):
                attribute_name = attribute_name.split(leading_str, 1)[1]

        return attribute_name

    def _normalize_attribute_values(self, attribute_val):
        """
        Turn Gf vectors, AssetPaths, Vt.Arrays, etc. into plain Python types.
        """
        if attribute_val is None:
            return None
        elif isinstance(attribute_val, (Gf.Vec2f, Gf.Vec2d, Gf.Vec3f, Gf.Vec3d, Gf.Vec4f, Gf.Vec4d)):
            return list(attribute_val)
        elif isinstance(attribute_val, Sdf.AssetPath):
            # you could also use attribute_val.resolvedPath if you prefer
            return attribute_val.path
        elif isinstance(attribute_val, (bool, int, float, str)):
            return attribute_val
        # 5) Anything else → fallback to str()
        return str(attribute_val)

    def _normalize_attribute_types(self, attribute_val):
        """
        """
        if attribute_val is None:
            return None
        elif isinstance(attribute_val, (Gf.Vec2f, Gf.Vec2d)):
            return 'float2'
        elif isinstance(attribute_val, (Gf.Vec3f, Gf.Vec3d)):
            return 'float3'
        elif isinstance(attribute_val, (Gf.Vec4f, Gf.Vec4d)):
            return 'float4'

        else:
            p_value_type = type(attribute_val).__name__
            if p_value_type == 'tuple':
                p_value_type = type(attribute_val[0]).__name__
                p_value_length = len(attribute_val)
                p_value_type += str(p_value_length)


        # 5) Anything else → fallback to str()
        return p_value_type

    def _convert_parms_to_dict(self, attribute_list, node_type):
        """
        Args:
            attribute_list (List[pxr.Usd.Attribute]): list of Usd Attributes
        Returns:
            (Dict[str, List[dict]]): A dict with 'input' and 'output' keys,
        """
        parms = {"input": [], "output": []}

        if node_type == OUT_PRIMS_TYPES[self.material_type]:
            parms["input"].append({
                "generic_name": None,
                "value": None,
                "type": None,
                "direction": "input",
            })
            return parms


        for attrib in attribute_list:
            attrib_name = attrib.GetName()

            # skip attributes that don't need to be captured.
            if attrib_name in SKIPPED_ATTRIBS:
                continue

            # TODO: parameter names should be standardized? Need to think about this.
            parms["input"].append({
                'generic_name': self._normalize_attribute_names(attrib_name, node_type),
                'value': self._normalize_attribute_values(attrib.Get()),
                'type': self._normalize_attribute_types(attrib.Get()),
                'direction': 'input',
            })


        return parms




    def _traverse_recursively_node_tree(self, shader, parent_shader=None, is_root=True):
        """
        Recursively build a nested dict for a shader and its upstream connections.

        Args:
            shader (UsdShade.Shader): The shader to traverse.
            parent_shader (UsdShade.Shader): The parent shader.

        Returns:
            dict: {
                prim_path (str),
                node_name (str),
                node_type (str),
                node_parms (List[dict{'name','value'}]),
                connections_dict (Dict[str,dict]),
                children_list (List[dict])  # same structure for upstream shaders
            }
        """
        shader_prim = shader.GetPrim()
        shader_name = shader_prim.GetName()
        node_type = self._get_shader_infoId_attrib(shader)

        node_dict = {
            'node_name': shader_name,
            'node_path': shader_prim.GetPath().pathString,
            'node_type': node_type,
            'node_position': None,
            'node_parms': self._convert_parms_to_dict(shader_prim.GetAttributes(), node_type),
            'connections_dict': {},
            'children_list': [],
        }
        if parent_shader is not None:
            shader_connections = shader.GetInputs()
            logger.debug("Getting Inputs!")
        else:
            shader_connections = shader.GetOutputs()
            logger.debug("Getting Outputs!")

        if not shader_connections:
            logger.warning("No Outputs!, shader_prim=%s", shader_prim)
            return {shader_prim.GetPath().pathString: node_dict}

        count = 0
        for out in shader_connections:
            sources: tuple[list[UsdShade.ConnectionSourceInfo]] = out.GetConnectedSources()
            for source in sources:
                if not source:
                    continue

                for srcInfo in source:
                    dest_param = out.GetBaseName()
                    srcAPI = srcInfo.source  # type: UsdShade.ConnectableAPI
                    srcName = srcInfo.sourceName  # type: str                     # e.g. "shader"
                    srcType = srcInfo.sourceType  # type: UsdShade.AttributeType  # e.g. pxr.UsdShade.AttributeType.Output
                    src_prim = srcAPI.GetPrim()
                    src_shader = UsdShade.Shader(src_prim)

                    # print(f"DEBUG: {shader_name=}, {parent_shader=}, {src_prim.GetName()=}")

                    # Recursively get child nodes
                    input_node_dict = self._traverse_recursively_node_tree(src_shader, parent_shader=shader, is_root=False)
                    input_node_dict[src_prim.GetPath().pathString]['connections_dict'] = self._detect_node_connections(srcInfo, shader, dest_param, count)
                    node_dict['children_list'].append(
                        input_node_dict[src_prim.GetPath().pathString]
                    )
                    count += 1

        return {shader_prim.GetPath().pathString: node_dict}

    def run(self):
        """
        Perform a full traversal of the material.

        1. Detect outputs
        2. For each connected shader, build its nested graph

        Returns:
            Tuple[
              Dict[str, dict], # nested_nodes_dict keyed by material path
              Dict[str, dict]  # output_nodes_dict
            ]
        """
        # 1) find all outputs
        output_tree = self.create_output_dict(self.material_prim, self.material_type)

        node_tree = {}
        for output_type, output_dict in output_tree.items():
            output_prim = self.stage.GetPrimAtPath(output_dict['node_path'])
            output_shader = UsdShade.Shader(output_prim)
            node_tree.update(self._traverse_recursively_node_tree(output_shader))

        return node_tree, output_tree




        # # 2) walk each shader network and collect children
        # root_path = self.material_type.GetPath().pathString
        # tree = {
        #     "node_name":        self.material_type.GetPrim().GetName(),
        #     "node_path":        root_path,
        #     "node_type":        self.material_type.GetPrim().GetTypeName(),
        #     "node_parms":       [],
        #     "connections_dict": {},
        #     "children_list":    []
        # }
        #
        # for out_info in output_tree.values():
        #     conn_shader_path = out_info["connected_node_path"]
        #     conn_shader_prim = self.stage.GetPrimAtPath(Sdf.Path(conn_shader_path))
        #     conn_shader = UsdShade.Shader(conn_shader_prim)
        #
        #     # attach the entire sub-tree under the material
        #     print(f"DEBUG: out_info: {pprint.pformat(out_info, sort_dicts=False)}")
        #     child_tree = self._traverse_recursively_node_tree(conn_shader, out_info)
        #     if child_tree:
        #         tree["children_list"].append(child_tree)
        #
        # self.nested_nodes = {root_path: tree}
        # return self.nested_nodes, output_tree





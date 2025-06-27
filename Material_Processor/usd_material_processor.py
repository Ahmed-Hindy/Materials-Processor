"""
Copyright Ahmed Hindy. Please mention the author if you found any part of this code useful.

"""
import os
import traceback
import json
import pprint
from typing import List, Optional
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt

from Material_Processor.material_classes import MaterialData
from Material_Processor import material_processor



GENERIC_NODE_TYPES_TO_REGULAR_USD = {
    'GENERIC::standard_surface': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:standard_surface',
            'mtlx': 'ND_standard_surface_surfaceshader',
            'usdpreview': 'UsdPreviewSurface',
        },
    },
    'GENERIC::image': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:image',
            'mtlx': 'ND_image_color3',
            'usdpreview': 'UsdUVTexture',
        },
    },
    'GENERIC::range': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:range',
            'mtlx': 'ND_range_color3',
        },
    },
    'GENERIC::color_correct': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:color_correct',
            'mtlx': 'ND_colorcorrect_color3',
        },
    },
    'GENERIC::curvature': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:curvature',
        },
    },
    'GENERIC::mix_rgba': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:mix_rgba',
        },
    },
    'GENERIC::mix_layer': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:mix_layer',
        },
    },
    'GENERIC::layer_rgba': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:layer_rgba',
        },
    },
    'GENERIC::ramp_rgb': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:ramp_rgb::2',
        },
    },
    'GENERIC::ramp_float': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:ramp_float::2',
        },
    },
    'GENERIC::displacement': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:bump2d',
            'mtlx':   'ND_bump_vector3',
        },
    },
    'GENERIC::output_node': {
        'prim_type': 'Material',
        # output nodes themselves become UsdShade.Material, no info:id needed
    },
    'GENERIC::null': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:standard_surface',  # fallback to standard_surface
            'mtlx':   'ND_standard_surface_surfaceshader',
        },
    },
}

# for connections from material prim to stdsurface prim
OUT_PRIM_DICT = {
    'arnold': {
        'GENERIC::output_surface': {
            'src': 'shader',
            'dest': 'arnold:surface',
        },
        'GENERIC::output_displacement': {
            'src': 'displacement',
            'dest': 'arnold:displacement',
        },

    },
    'mtlx': {
        'GENERIC::output_surface': {
            'src': 'out',
            'dest': 'mtlx:surface',
        },
        'GENERIC::output_displacement': {
            'src': 'out',
            'dest': 'mtlx:displacement',
        },
    }
}


# map USD material outputs back to GENERIC types
GENERIC_OUTPUT_TYPES = {
    'surface': 'GENERIC::output_surface',
    'displacement': 'GENERIC::output_displacement',
}







class USDTraverser:
    """
    Traverse a UsdShade.Material prim to extract its shading network
    in a nested dict format matching the Houdini NodeTraverser JSON.

    Attributes:
        stage (Usd.Stage): The USD stage containing the material.
        material_type (UsdShade.Material): The material to traverse.
        nested_nodes (Dict[str, dict]): Nested shader-graph per material.
        output_nodes (Dict[str, dict]): Info on each material output.
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

    @staticmethod
    def _detect_node_connections(shader, parent_node):
        """
        """
        shader_prim = shader.GetPrim()
        shader_primname = shader_prim.GetName()
        print(f"DEBUG: shader: {shader_primname}, parent_node: {parent_node.GetName() if parent_node else None}")

        connections_dict = {}
        for out in shader.GetOutputs():
            # baseName may include renderer prefix, e.g. "arnold:surface"
            out_basename = out.GetBaseName()
            base = out.GetBaseName().split(':')[-1]
            sources: tuple[list[UsdShade.ConnectionSourceInfo]] = out.GetConnectedSources()
            for i, source in enumerate(sources):
                for ii, srcInfo in enumerate(source):
                    # print(f"DEBUG: {len(sources)=}, {len(source)=}, [{i}][{ii}]")
                    srcInfo  # type: UsdShade.ConnectionSourceInfo
                    srcAPI = srcInfo.source  # type: UsdShade.ConnectableAPI
                    srcName = srcInfo.sourceName  # type: str               # e.g. "shader"
                    srcType = srcInfo.sourceType  # type: UsdShade.AttributeType  # e.g. pxr.UsdShade.AttributeType.Output
                    src_prim = srcAPI.GetPrim()
                    # print(f"DEBUG: connection from: '{src_prim.GetName()}[{srcName}]' -> "
                    #       f"'{mat_name}[{base}]'\n")

                    connections_dict.update({f"connection_{i}": {
                            "input": {
                                "node_name": src_prim.GetPrim().GetName(),
                                "node_path": src_prim.GetPath().pathString,
                                "node_index": -1,
                                "parm_name": srcName,
                            },
                            "output": {
                                "node_name": shader_prim.GetName(),
                                "node_path": shader_prim.GetPath().pathString,
                                "node_index": -1,
                                "parm_name": out_basename,
                            }
                        }
                    })

        print(f"DEBUG: connections_dict: {pprint.pformat(connections_dict, sort_dicts=False)}\n")
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

        conv_dict = {
            'mtlx': 'subnetconnector',
            'arnold': 'arnold_shader',
        }
        return conv_dict[self.material_type]

    def _normalize_attribute_names(self, attribute_name):
        """

        """
        leading_strs = ['arnold:', 'inputs:']
        for leading_str in leading_strs:
            if attribute_name.startswith(leading_str):
                return attribute_name.split(leading_str, 1)[1]

        return attribute_name

    def _normalize_attribute_values(self, attribute_val):
        """
        Turn Gf vectors, AssetPaths, Vt.Arrays, etc. into plain Python types.
        """
        # 1) Gf vectors → tuple of floats
        if isinstance(attribute_val, (Gf.Vec2f, Gf.Vec2d, Gf.Vec3f, Gf.Vec3d, Gf.Vec4f, Gf.Vec4d)):
            return tuple(attribute_val)
        # 2) Asset paths → the string path
        if isinstance(attribute_val, Sdf.AssetPath):
            # you could also use attribute_val.resolvedPath if you prefer
            return attribute_val.path
        # # 3) Vt.Arrays (and any other sequence) → list
        # if isinstance(attribute_val, Vt.Array):
        #     return [self._normalize_attribute_types(v) for v in list(attribute_val)]
        # 4) Any builtin number or bool or str → leave as is
        if isinstance(attribute_val, (bool, int, float, str)):
            return attribute_val
        # 5) Anything else → fallback to str()
        return str(attribute_val)

    def _convert_parms_to_dict(self, attribute_list):
        """
        Args:
            attribute_list (List[pxr.Usd.Attribute]): list of Usd Attributes
        Returns:
            (Dict[str: str])
        """

        out = [{'name': self._normalize_attribute_names(attrib.GetName()),
                'value': self._normalize_attribute_values(attrib.Get())} for attrib in attribute_list]
        # print(f"DEBUG: out: {pprint.pformat(out, sort_dicts=False)}")

        return out




    def _traverse_recursively_node_tree(self, shader, parent_shader=None):
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
        # get a dict with all input and output connections related to the node
        connections_dict = self._detect_node_connections(shader, parent_shader)

        # Initialize the node's dictionary with metadata
        print(f"DEBUG: shader_primpath: {shader_prim.GetPath().pathString}, id: {shader_prim.GetAttribute('info:id').Get()}")
        node_dict = {
            'node_name': shader_prim.GetName(),
            'node_path': shader_prim.GetPath().pathString,
            'node_type': self._get_shader_infoId_attrib(shader),
            'node_position': None,
            'node_parms': self._convert_parms_to_dict(shader_prim.GetAttributes()),
            'connections_dict': connections_dict,
            'children_list': []
        }

        shader_outputs = shader.GetOutputs()
        if not shader_outputs:
            return {shader_prim.path(): node_dict}

        for out in shader_outputs:
            sources: tuple[list[UsdShade.ConnectionSourceInfo]] = out.GetConnectedSources()
            for i, source in enumerate(sources):
                for ii, srcInfo in enumerate(source):
                    # print(f"DEBUG: {len(sources)=}, {len(source)=}, [{i}][{ii}]")
                    srcAPI = srcInfo.source  # type: UsdShade.ConnectableAPI
                    srcName = srcInfo.sourceName  # type: str               # e.g. "shader"
                    srcType = srcInfo.sourceType  # type: UsdShade.AttributeType  # e.g. pxr.UsdShade.AttributeType.Output
                    src_prim = srcAPI.GetPrim()
                    src_shader = UsdShade.Shader(src_prim)

                    # Recursively get child nodes
                    print(f"DEBUG: recursing into: '{src_prim.GetName()}'")
                    input_node_dict = self._traverse_recursively_node_tree(src_shader, shader_prim)
                    node_dict['children_list'].append(
                        input_node_dict[src_prim.GetPath().pathString]
                    )

        return {shader_prim.GetPath().pathString: node_dict}

    def run(self):
        """
        Perform a full traversal of the material.

        1. Detect outputs
        2. For each connected shader, build its nested graph

        Returns:
            Tuple[
              Dict[str, dict],  # nested_nodes_dict keyed by material path
              Dict[str, dict]   # output_nodes_dict
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




class USDMaterialRecreator:
    """
    Recreate Houdini-style material networks as UsdShade primitives.

    This mimics Houdini’s node-builder flow:
      1. Create a UsdShade.Material prim for each output node.
      2. Create all intermediate UsdShade.Shader prims.
      3. Wire up their parameters.
      4. Connect outputs into the collect-material prim.
      5. Connect inter-shader links.

    Attributes:
        stage (Usd.Stage): The USD stage to write into.
        material_name (str): Name of the collect-material prim.
        nodeinfo_list (List[NodeInfo]): Generic network description.
        orig_output_connections (Dict): Mapping of GENERIC outputs to upstream info.
        parent_scope_path (str): Root scope for new materials.
        target_renderer (str): One of ['arnold', 'mtlx', 'usdpreview'].
        old_new_map (Dict[str,str]): Map old Houdini node paths to new Usd prim paths.
        connection_tasks (List): Pending inter-shader connection tuples.
    """

    def __init__(self, stage: Usd.Stage, material_name, nodeinfo_list, output_connections,
                 parent_scope_path: str = "/materials", target_renderer: str = "arnold"):
        """
        Initialize and immediately run the network rebuild.

        Args:
            stage (Usd.Stage): The USD stage to populate.
            material_name (str): The Houdini builder’s name.
            nodeinfo_list (List[NodeInfo]): Flattened generic node descriptions.
            output_connections (Dict): Output-to-upstream mapping from ingest.
            parent_scope_path (str): Root scope path for new materials.
            target_renderer (str): 'arnold', 'mtlx', or 'usdpreview'.
        """
        self.stage = stage
        self.material_name = material_name
        self.nodeinfo_list = nodeinfo_list
        self.orig_output_connections = output_connections
        self.parent_scope_path = parent_scope_path
        self.target_renderer = target_renderer

        # maps generic output to UsdShade.Material
        self.material_map = {}
        # maps old node paths to new prim paths
        self.old_new_map = {}
        # will hold connections for final wiring
        self.connection_tasks = []

        self.run()


    def _create_shader_id(self, shader, generic_type):
        """
        Assign the correct USD info:id on a shader prim.

        Args:
            shader (UsdShade.Shader): The shader prim to tag.
            generic_type (str): A GENERIC:: type key.

        Returns:
            bool: True if an ID was found and set, False otherwise.
        """
        mapping = GENERIC_NODE_TYPES_TO_REGULAR_USD.get(generic_type, {})
        # print(f"DEBUG: {shader=} {generic_type=}")
        shader_id = mapping['info_id'][self.target_renderer]
        if shader_id:
            shader.CreateIdAttr(shader_id)
            return True
        return False

    def _set_shader_parameters(self, shader: UsdShade.Shader, node_type: str, parameters):
        """
        Map generic parameters over to renderer-specific USD inputs.

        This:
          1) Uses REGULAR_PARAM_NAMES_TO_GENERIC to canonicalize incoming names.
          2) Finds the USD input names in GENERIC_NODE_TYPES_TO_REGULAR_USD[node_type]['info_id'].
          3) Creates and sets each UsdShade.Input with the proper Sdf.ValueTypeNames.

        Args:
            shader (UsdShade.Shader): The USD shader prim.
            node_type (str): The renderer node type key (e.g. 'arnold::image').
            parameters (List[NodeParameter]): List of standardized Parameter objects.

        Raises:
            KeyError: If node_type is not found in the parameter-name mapping.
        """
        if not parameters:
            print(f"WARNING: No parameters found for shader: {shader.GetPath().pathString}")
            return

        # look up standardized mapping for this node type
        std_parm_map: dict = material_processor.REGULAR_PARAM_NAMES_TO_GENERIC[node_type.replace('::', ':')]

        for param in parameters:
            # we have the generic parm name stored in: 'param.generic_name',
            # now let's find the new parm name suitable for the shader prim.
            parm_new_name = [key for key, val in std_parm_map.items() if val == param.generic_name]

            if not parm_new_name:
                print(f"WARNING: Skipping parm: '{node_type=}'.'{param.generic_name=}'")
                continue  # skip unsupported params

            parm_new_name = parm_new_name[0]

            # determine the proper type
            val = param.value

            if isinstance(val, tuple) and len(val) == 1:
                val = val[0]

            if isinstance(val, tuple):
                length = len(val)
                if all(isinstance(x, float) for x in val):
                    type_name = getattr(Sdf.ValueTypeNames, f"Float{length}", Sdf.ValueTypeNames.Float)
                elif all(isinstance(x, int) for x in val):
                    type_name = getattr(Sdf.ValueTypeNames, f"Int{length}", Sdf.ValueTypeNames.Int)
                else:
                    print(f"WARNING: {parm_new_name}.{val=} is not a tuple of all floats or ints, but {type(val)=}")
                    type_name = Sdf.ValueTypeNames.Token
            elif isinstance(val, bool):
                type_name = Sdf.ValueTypeNames.Bool
            elif isinstance(val, int):
                type_name = Sdf.ValueTypeNames.Int
            elif isinstance(val, float):
                type_name = Sdf.ValueTypeNames.Float
            elif isinstance(val, str):
                type_name = Sdf.ValueTypeNames.String
            else:
                print(f"WARNING: {parm_new_name}.{val=} is unknown, {type(val)=}")
                type_name = Sdf.ValueTypeNames.Token

            inp = shader.CreateInput(parm_new_name, type_name)
            # print(f"DEBUG: {parm_new_name=}, {val=}")

            try:
                inp.Set(val)
            except Exception as e:
                print(f"ERROR: failed to set input '{parm_new_name}' to '{val}', {e=}")


    def create_material_prim(self):
        """
        Define the collect-Material prim(s) at `<parent_scope>/<material_name>`.

        Populates self.old_new_map for each Houdini output node.
        """
        self.created_out_primpaths = []
        for generic_output, out_dict in self.orig_output_connections.items():
            # DEBUG: generic_output='GENERIC::output_surface'
            # DEBUG: out_dict: {'node_name': 'OUT_material',
            #                       'node_path': '/mat/arnold_materialbuilder_basic/OUT_material',
            #                       'connected_node_name': 'standard_surface',
            #                       'connected_node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
            #                       'connected_input_index': -1
            #                  }
            # DEBUG: self.material_name = 'arnold_materialbuilder_basic'


            mat_primname = self.material_name
            mat_primpath = Sdf.Path(f"{self.parent_scope_path}/{mat_primname}")
            mat = UsdShade.Material.Define(self.stage, Sdf.Path(mat_primpath))

            self.created_out_primpaths.append(mat_primpath)
            self.old_new_map[out_dict['node_path']] = mat_primpath.pathString


    def create_child_shaders(self, nodeinfo_list):
        """
        Recursively define all intermediate UsdShade.Shader prims.

        Args:
            nodeinfo_list (List[NodeInfo]): Generic node info hierarchy.
        """
        # DEBUG: self.created_out_primpaths=[Sdf.Path('/Materials/OUT_material')]
        for nodeinfo in nodeinfo_list:
            if nodeinfo.node_type == 'GENERIC::output_node':
                # still recurse into children of output nodes
                if nodeinfo.children_list:
                    self.create_child_shaders(nodeinfo.children_list)
                print(f"Continue 1")
                continue
            elif nodeinfo.node_type == None:
                # why this is always invoked. why always none?
                if nodeinfo.children_list:
                    self.create_child_shaders(nodeinfo.children_list)
                print(f"Continue 2")
                continue


            new_prim_path = nodeinfo.node_name.replace('/', '_')
            # DEBUG: self.created_out_primpaths[0].pathString='/Materials/OUT_material'
            shader_primpath = f"{self.created_out_primpaths[0].pathString}/{new_prim_path}"
            shader = UsdShade.Shader.Define(self.stage, Sdf.Path(shader_primpath))
            self._create_shader_id(shader, nodeinfo.node_type)


            # set parameters
            regular_node_type: str = material_processor.GENERIC_NODE_TYPES_TO_REGULAR[self.target_renderer].get(nodeinfo.node_type, {})
            self._set_shader_parameters(shader, regular_node_type, nodeinfo.parameters)

            self.old_new_map[nodeinfo.node_path] = shader.GetPath().pathString

            # DEBUG: node_info.node_path = '/mat/arnold_materialbuilder_basic/standard_surface'

            for conn_index, conn in nodeinfo.connection_info.items():
                self.connection_tasks.append((conn, nodeinfo.node_path))

                # DEBUG: conn_index = 'connection_1
                # DEBUG: conn: {'input':
                #                  {'node_name': 'standard_surface',
                #                   'node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
                #                   'node_index': 0,
                #                   'parm_name': 'shader'},
                #               'output':
                #                   {'node_name': 'OUT_material',
                #                    'node_path': '/mat/arnold_materialbuilder_basic/OUT_material',
                #                    'node_index': 0,
                #                    'parm_name': 'surface'}
                #              }

            if nodeinfo.children_list:
                self.create_child_shaders(nodeinfo.children_list)

            # print(f"DEBUG: self.connection_tasks: {pprint.pformat(self.connection_tasks, sort_dicts=False)}")
            # DEBUG: self.connection_tasks: [({'input': {'node_name': 'standard_surface',
            #              'node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
            #              'node_index': 0,
            #              'parm_name': 'shader'},
            #    'output': {'node_name': 'OUT_material',
            #               'node_path': '/mat/arnold_materialbuilder_basic/OUT_material',
            #               'node_index': 0,
            #               'parm_name': 'surface'}},
            #   '/mat/arnold_materialbuilder_basic/standard_surface'),
            #  ({'input': {'node_name': 'image_diffuse',
            #              'node_path': '/mat/arnold_materialbuilder_basic/image_diffuse',
            #              'node_index': 0,
            #              'parm_name': 'rgba'},
            #    'output': {'node_name': 'standard_surface',
            #               'node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
            #               'node_index': 1,
            #               'parm_name': 'base_color'}},
            #   '/mat/arnold_materialbuilder_basic/image_diffuse')]


    def set_output_connections(self):
        """
        Wire core shaders to output material surface slots.
        """
        mat_primpath = Sdf.Path(f"{self.parent_scope_path}/{self.material_name}")
        mat_usdshade = UsdShade.Material.Get(self.stage, mat_primpath)

        for generic_output, out_dict in self.orig_output_connections.items():
            # DEBUG: generic_output='GENERIC::output_surface'
            # DEBUG: out_dict: {'node_name': 'OUT_material',
            #                       'node_path': '/mat/arnold_materialbuilder_basic/OUT_material',
            #                       'connected_node_name': 'standard_surface',
            #                       'connected_node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
            #                       'connected_input_index': 0,
            #                       'connected_input_name': 'surface',
            #                       'connected_output_name': 'shader',
            #                  }
            # DEBUG: self.material_name = 'arnold_materialbuilder_basic'
            src_path = self.old_new_map[out_dict['connected_node_path']]
            dst_path = self.old_new_map[out_dict['node_path']]
            src_parm = out_dict['connected_output_name']
            dst_parm = out_dict['connected_input_name']
            if dst_path not in [x.pathString for x in self.created_out_primpaths]:
                continue

            src_api = UsdShade.Shader(self.stage.GetPrimAtPath(Sdf.Path(src_path)))
            mat_usdshade.CreateOutput(OUT_PRIM_DICT[self.target_renderer][generic_output]['dest'], Sdf.ValueTypeNames.Token).ConnectToSource(
                src_api.ConnectableAPI(), OUT_PRIM_DICT[self.target_renderer][generic_output]['src'])


    def set_shader_connections(self):
        """
        Connect child shader prims based on stored connection_tasks.
        """
        # print(f"DEBUG: {self.orig_output_connections=}")
        # print(f"DEBUG: {self.created_out_primpaths=}")
        for conn, parent_path in self.connection_tasks:
            # conn has input and output entries
            src_path = self.old_new_map[conn['input']['node_path']]
            dst_path = self.old_new_map[conn['output']['node_path']]
            src_parm = conn['input']['parm_name']
            dst_parm = conn['output']['parm_name']
            if dst_path in [x.pathString for x in self.created_out_primpaths]:
                # print(f"WARNING:  Output detected: '{dst_path}' ")
                continue

            # print(f"DEBUG: self.old_new_map: {pprint.pformat(self.old_new_map, sort_dicts=False)}")
            # print(f"DEBUG: conn: {pprint.pformat(conn, sort_dicts=False)}")
            # print(f"DEBUG: {parent_path=}")
            # print(f"DEBUG: {src_path=}")
            # print(f"DEBUG: {dst_path=}///\n")
            # print(f"Connecting prims: src: '{src_path}[{src_parm}]' to dest: '{dst_path}[{dst_parm}]'")

            src_api = UsdShade.Shader(self.stage.GetPrimAtPath(Sdf.Path(src_path)))
            dst_api = UsdShade.Shader(self.stage.GetPrimAtPath(Sdf.Path(dst_path)))
            dst_api.CreateInput(dst_parm, Sdf.ValueTypeNames.Token)
            dst_api.GetInput(dst_parm).ConnectToSource(src_api.ConnectableAPI(), conn['input']['parm_name'])


    def detect_if_transmissive(self, material_name):
        """
        Heuristically detect if a material should enable transmission.

        Args:
            material_name (str): The name of the material (e.g. contains 'glass').

        Returns:
            bool: True if transmissive keywords are present.
        """
        transmissive_matnames_list = ['glass', 'glas']
        is_transmissive = any(substring in material_name.lower() for substring in transmissive_matnames_list)
        if is_transmissive:
            print(f"DEBUG:  Detected Transmissive Material: '{material_name}'")

        return is_transmissive


    ###  usd_preview ###
    def _create_usd_preview_material(self, parent_path, usd_preview_format):
        material_path = f'{parent_path}/UsdPreviewMaterial'
        material = UsdShade.Material.Define(self.stage, material_path)

        nodegraph_path = f'{material_path}/UsdPreviewNodeGraph'
        nodegraph = self.stage.DefinePrim(nodegraph_path, 'NodeGraph')

        shader_path = f'{nodegraph_path}/UsdPreviewSurface'
        shader = UsdShade.Shader.Define(self.stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")

        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

        # Create textures for USD Preview Shader
        texture_types_to_inputs = {
            'basecolor': 'diffuseColor',
            'metalness': 'metallic',
            'roughness': 'roughness',
            'normal': 'normal',
            'opacity': 'opacity',
            'height': 'displacement'
        }

        for tex_type, tex_dict in self.material_dict.items():
            tex_filepath = tex_dict['path']
            tex_type = tex_type.lower()  # assume all lowercase
            if tex_type not in texture_types_to_inputs:
                print(f"WARNING:  tex_type: '{tex_type}' not supported yet for usdpreview")
                continue

            if usd_preview_format:
                file_format = os.path.splitext(tex_filepath)[1].rsplit('.', 1)[1]  # e.g. 'exr'
                tex_filepath = tex_filepath.replace(file_format, usd_preview_format)

            # print(f"DEBUG:  tex_filepath: {tex_filepath}")
            input_name = texture_types_to_inputs[tex_type]
            texture_prim_path = f'{nodegraph_path}/{tex_type}Texture'
            texture_prim = UsdShade.Shader.Define(self.stage, texture_prim_path)
            texture_prim.CreateIdAttr("UsdUVTexture")
            file_input = texture_prim.CreateInput("file", Sdf.ValueTypeNames.Asset)
            file_input.Set(tex_filepath)
            # print(f"DEBUG: texture_prim_path: {texture_prim_path}")
            # print(f"DEBUG: tex_filepath: {tex_filepath}")

            wrapS = texture_prim.CreateInput("wrapS", Sdf.ValueTypeNames.Token)
            wrapT = texture_prim.CreateInput("wrapT", Sdf.ValueTypeNames.Token)
            wrapS.Set('repeat')
            wrapT.Set('repeat')

            # Create Primvar Reader for ST coordinates
            st_reader_path = f'{nodegraph_path}/TexCoordReader'  # TODO: remove it from the for loop.
            st_reader = UsdShade.Shader.Define(self.stage, st_reader_path)
            st_reader.CreateIdAttr("UsdPrimvarReader_float2")
            st_input = st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token)
            st_input.Set("st")
            texture_prim.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_reader.ConnectableAPI(), "result")

            if tex_type in ['opacity', 'metallic', 'roughness']:
                shader.CreateInput(input_name, Sdf.ValueTypeNames.Float3).ConnectToSource(texture_prim.ConnectableAPI(),
                                                                                          "r")
            else:
                shader.CreateInput(input_name, Sdf.ValueTypeNames.Float3).ConnectToSource(texture_prim.ConnectableAPI(),
                                                                                          "rgb")

        return material


    ###  arnold ###
    def _arnold_create_material(self, parent_path, enable_transmission=False):
        """
        example prints for variables created by the script:
            shader: UsdShade.Shader(Usd.Prim(</root/material/mat_hello_world_collect/standard_surface1>))
            material_prim: Usd.Prim(</root/material/mat_hello_world_collect>)
            material_usdshade: UsdShade.Material(Usd.Prim(</root/material/mat_hello_world_collect>))
        """
        shader_path = f'{parent_path}/arnold_standard_surface1'
        stdsurf_usdshade = UsdShade.Shader.Define(self.stage, shader_path)
        stdsurf_usdshade.CreateIdAttr("arnold:standard_surface")
        material_prim = self.stage.GetPrimAtPath(parent_path)

        material_usdshade = UsdShade.Material.Define(self.stage, material_prim.GetPath())
        material_usdshade.CreateOutput("arnold:surface", Sdf.ValueTypeNames.Token).ConnectToSource(stdsurf_usdshade.ConnectableAPI(), "surface")
        # print(f"DEBUG: shader: {shader}\n")

        self._arnold_initialize_standard_surface_shader(stdsurf_usdshade)
        self._arnold_fill_texture_file_paths(material_prim, stdsurf_usdshade)

        if enable_transmission:
            self._arnold_enable_transmission(stdsurf_usdshade)

        return material_usdshade

    def _arnold_initialize_standard_surface_shader(self, shader_usdshade):
        """
        initializes Arnold Standard Surface inputs
        """
        shader_usdshade.CreateInput('aov_id1', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('aov_id2', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('aov_id3', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('aov_id4', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('aov_id5', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('aov_id6', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('aov_id7', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('aov_id8', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('base', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('base_color', Sdf.ValueTypeNames.Float3).Set((0.8, 0.8, 0.8))
        shader_usdshade.CreateInput('metalness', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('specular', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('specular_color', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('specular_roughness', Sdf.ValueTypeNames.Float).Set(0.2)
        shader_usdshade.CreateInput('specular_IOR', Sdf.ValueTypeNames.Float).Set(1.5)
        shader_usdshade.CreateInput('specular_anisotropy', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('specular_rotation', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('caustics', Sdf.ValueTypeNames.Bool).Set(False)
        shader_usdshade.CreateInput('coat', Sdf.ValueTypeNames.Float).Set(0.0)
        shader_usdshade.CreateInput('coat_color', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('coat_roughness', Sdf.ValueTypeNames.Float).Set(0.1)
        shader_usdshade.CreateInput('coat_IOR', Sdf.ValueTypeNames.Float).Set(1.5)
        shader_usdshade.CreateInput('coat_normal', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('coat_affect_color', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('coat_affect_roughness', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('indirect_diffuse', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('indirect_specular', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('indirect_reflections', Sdf.ValueTypeNames.Bool).Set(True)
        shader_usdshade.CreateInput('subsurface', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('subsurface_anisotropy', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('subsurface_color', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('subsurface_radius', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('subsurface_scale', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('subsurface_type', Sdf.ValueTypeNames.String).Set("randomwalk")
        shader_usdshade.CreateInput('emission', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('emission_color', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('normal', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('opacity', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('sheen', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('sheen_color', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('sheen_roughness', Sdf.ValueTypeNames.Float).Set(0.3)
        shader_usdshade.CreateInput('indirect_diffuse', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('indirect_specular', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('internal_reflections', Sdf.ValueTypeNames.Bool).Set(True)
        shader_usdshade.CreateInput('caustics', Sdf.ValueTypeNames.Bool).Set(False)
        shader_usdshade.CreateInput('exit_to_background', Sdf.ValueTypeNames.Bool).Set(False)
        shader_usdshade.CreateInput('tangent', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('transmission', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('transmission_color', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('transmission_depth', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('transmission_scatter', Sdf.ValueTypeNames.Float3).Set((0, 0, 0))
        shader_usdshade.CreateInput('transmission_scatter_anisotropy', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('transmission_dispersion', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('transmission_extra_roughness', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('thin_film_IOR', Sdf.ValueTypeNames.Float).Set(1.5)
        shader_usdshade.CreateInput('thin_film_thickness', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('thin_walled', Sdf.ValueTypeNames.Bool).Set(False)
        shader_usdshade.CreateInput('transmit_aovs', Sdf.ValueTypeNames.Bool).Set(False)

    def _arnold_initialize_image_shader(self, image_path: str):
        image_shader = UsdShade.Shader.Define(self.stage, image_path)
        image_shader.CreateIdAttr("arnold:image")

        color_space = image_shader.CreateInput("color_space", Sdf.ValueTypeNames.String)
        color_space.Set("auto")
        file_input = image_shader.CreateInput("filename", Sdf.ValueTypeNames.Asset)
        filter = image_shader.CreateInput("filter", Sdf.ValueTypeNames.String)
        filter.Set("smart_bicubic")
        ignore_missing_textures = image_shader.CreateInput("ignore_missing_textures", Sdf.ValueTypeNames.Bool)
        ignore_missing_textures.Set(False)
        mipmap_bias = image_shader.CreateInput("mipmap_bias", Sdf.ValueTypeNames.Int)
        mipmap_bias.Set(0)
        missing_texture_color = image_shader.CreateInput("missing_texture_color", Sdf.ValueTypeNames.Float4)
        missing_texture_color.Set((0,0,0,0))
        multiply = image_shader.CreateInput("multiply", Sdf.ValueTypeNames.Float3)
        multiply.Set((1,1,1))
        offset = image_shader.CreateInput("offset", Sdf.ValueTypeNames.Float3)
        offset.Set((0,0,0))
        sflip = image_shader.CreateInput("sflip", Sdf.ValueTypeNames.Bool)
        sflip.Set(False)
        single_channel = image_shader.CreateInput("single_channel", Sdf.ValueTypeNames.Bool)
        single_channel.Set(False)
        soffset = image_shader.CreateInput("soffset", Sdf.ValueTypeNames.Float)
        soffset.Set(0)
        sscale = image_shader.CreateInput("sscale", Sdf.ValueTypeNames.Float)
        sscale.Set(1)
        start_channel = image_shader.CreateInput("start_channel", Sdf.ValueTypeNames.Int)
        start_channel.Set(0)
        swap_st = image_shader.CreateInput("swap_st", Sdf.ValueTypeNames.Bool)
        swap_st.Set(False)
        swrap = image_shader.CreateInput("swrap", Sdf.ValueTypeNames.String)
        swrap.Set("periodic")
        tflip = image_shader.CreateInput("tflip", Sdf.ValueTypeNames.Bool)
        tflip.Set(False)
        toffset = image_shader.CreateInput("toffset", Sdf.ValueTypeNames.Float)
        toffset.Set(0)
        tscale = image_shader.CreateInput("tscale", Sdf.ValueTypeNames.Float)
        tscale.Set(1)
        twrap = image_shader.CreateInput("twrap", Sdf.ValueTypeNames.String)
        twrap.Set("periodic")
        uvcoords = image_shader.CreateInput("uvcoords", Sdf.ValueTypeNames.Float2)
        uvcoords.Set((0,0))
        uvset = image_shader.CreateInput("uvset", Sdf.ValueTypeNames.String)
        uvset.Set("")

        return image_shader

    def _arnold_initialize_color_correct_shader(self, color_correct_path: str):
        color_correct_shader = UsdShade.Shader.Define(self.stage, color_correct_path)
        color_correct_shader.CreateIdAttr("arnold:color_correct")
        cc_add_input = color_correct_shader.CreateInput("add", Sdf.ValueTypeNames.Float3)
        cc_add_input.Set((0, 0, 0))
        cc_contrast_input = color_correct_shader.CreateInput("contrast", Sdf.ValueTypeNames.Float)
        cc_contrast_input.Set(1)
        cc_exposure_input = color_correct_shader.CreateInput("exposure", Sdf.ValueTypeNames.Float)
        cc_exposure_input.Set(0)
        cc_gamma_input = color_correct_shader.CreateInput("gamma", Sdf.ValueTypeNames.Float)
        cc_gamma_input.Set(1)
        cc_hue_shift_input = color_correct_shader.CreateInput("hue_shift", Sdf.ValueTypeNames.Float)
        cc_hue_shift_input.Set(0)

        return color_correct_shader

    def _arnold_initialize_range_shader(self, range_path: str):
        range_shader = UsdShade.Shader.Define(self.stage, range_path)
        range_shader.CreateIdAttr("arnold:range")

        bias_input = range_shader.CreateInput("bias", Sdf.ValueTypeNames.Float)
        bias_input.Set(0.5)
        contrast_input = range_shader.CreateInput("contrast", Sdf.ValueTypeNames.Float)
        contrast_input.Set(1)
        contrast_pivot_input = range_shader.CreateInput("contrast_pivot", Sdf.ValueTypeNames.Float)
        contrast_pivot_input.Set(0.5)
        gain_input = range_shader.CreateInput("gain", Sdf.ValueTypeNames.Float)
        gain_input.Set(0.5)
        input_min_input = range_shader.CreateInput("input_min", Sdf.ValueTypeNames.Float)
        input_min_input.Set(0)
        input_max_input = range_shader.CreateInput("input_max", Sdf.ValueTypeNames.Float)
        input_max_input.Set(1)
        output_min_input = range_shader.CreateInput("output_min", Sdf.ValueTypeNames.Float)
        output_min_input.Set(0)
        output_max_input = range_shader.CreateInput("output_max", Sdf.ValueTypeNames.Float)
        output_max_input.Set(1)
        output_max_input = range_shader.CreateInput("smoothstep", Sdf.ValueTypeNames.Bool)
        output_max_input.Set(False)

        return range_shader


    def _arnold_initialize_normal_map_shader(self, normal_map_path: str):
        normal_map_shader = UsdShade.Shader.Define(self.stage, normal_map_path)
        normal_map_shader.CreateIdAttr("arnold:normal_map")

        color_to_signed_input = normal_map_shader.CreateInput("color_to_signed", Sdf.ValueTypeNames.Bool)
        color_to_signed_input.Set(True)
        input_input = normal_map_shader.CreateInput("input", Sdf.ValueTypeNames.Float3)
        input_input.Set((0, 0, 0))
        invert_x_input = normal_map_shader.CreateInput("invert_x", Sdf.ValueTypeNames.Bool)
        invert_x_input.Set(False)
        invert_y_input = normal_map_shader.CreateInput("invert_y", Sdf.ValueTypeNames.Bool)
        invert_y_input.Set(False)
        invert_z_input = normal_map_shader.CreateInput("invert_z", Sdf.ValueTypeNames.Bool)
        invert_z_input.Set(False)
        normal_input = normal_map_shader.CreateInput("normal", Sdf.ValueTypeNames.Float3)
        normal_input.Set((0, 0, 0))
        order_input = normal_map_shader.CreateInput("order", Sdf.ValueTypeNames.String)
        order_input.Set('XYZ')
        strength_input = normal_map_shader.CreateInput("strength", Sdf.ValueTypeNames.Float)
        strength_input.Set(1)
        tangent_input = normal_map_shader.CreateInput("tangent", Sdf.ValueTypeNames.Float3)
        tangent_input.Set((0, 0, 0))
        tangent_space_input = normal_map_shader.CreateInput("tangent_space", Sdf.ValueTypeNames.Bool)
        tangent_space_input.Set(True)

        return normal_map_shader

    def _arnold_initialize_bump2d_shader(self, bump2d_path: str):
        bump2d_shader = UsdShade.Shader.Define(self.stage, bump2d_path)
        bump2d_shader.CreateIdAttr("arnold:bump2d")

        bump_height_input = bump2d_shader.CreateInput("bump_height", Sdf.ValueTypeNames.Float)
        bump_height_input.Set(1)
        bump_map_input = bump2d_shader.CreateInput("bump_map", Sdf.ValueTypeNames.Float)
        bump_map_input.Set(0)
        normal_input = bump2d_shader.CreateInput("normal", Sdf.ValueTypeNames.Float3)
        normal_input.Set((0, 0, 0))

        return bump2d_shader


    def _arnold_enable_transmission(self, shader_usdshade):
        """
        given the mtlx standard surface, will set input primvar 'transmission' to value '0.9'
        """
        shader_usdshade.GetInput('transmission').Set(0.9)
        shader_usdshade.GetInput('thin_walled').Set(True)


    def _arnold_fill_texture_file_paths(self, material_prim, std_surf_shader):
        """
        Fills the texture file paths for the given shader using the material_data.
        """
        # map of tex_type to it's name on an Arnold Standard Surface shader.
        texture_types_to_inputs = {
            'basecolor': 'base_color',
            'metalness': 'metalness',
            'roughness': 'specular_roughness',
            'normal': 'normal',
            'opacity': 'opacity',
            'height': 'height',
        }

        bump2d_path = f"{material_prim.GetPath()}/arnold_Bump2d"
        bump2d_shader = None

        for tex_type, tex_dict in self.material_dict.items():
            tex_filepath = tex_dict['path']
            tex_type = tex_type.lower()  # assume all lowercase
            if tex_type not in texture_types_to_inputs:
                print(f"WARNING:  tex_type: '{tex_type}' not supported yet for arnold")
                continue

            input_name = texture_types_to_inputs[tex_type]

            # create arnold::image prim
            texture_prim_path = f'{material_prim.GetPath()}/arnold_{tex_type}Texture'
            texture_shader = self._arnold_initialize_image_shader(texture_prim_path)
            texture_shader.GetInput("filename").Set(tex_filepath)

            if tex_type in ['basecolor']:
                color_correct_path = f"{material_prim.GetPath()}/arnold_{tex_type}ColorCorrect"
                color_correct_shader = self._arnold_initialize_color_correct_shader(color_correct_path)
                color_correct_shader.CreateInput("input", Sdf.ValueTypeNames.Float4).ConnectToSource(texture_shader.ConnectableAPI(), "rgba")
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Float3).ConnectToSource(color_correct_shader.ConnectableAPI(), "rgb")

            elif tex_type in ['metalness']:
                # disable metalness if material is transmissive like glass:
                if self.is_transmissive:
                    continue
                range_path = f"{material_prim.GetPath()}/arnold_{tex_type}Range"
                range_shader = self._arnold_initialize_range_shader(range_path)
                range_shader.CreateInput("input", Sdf.ValueTypeNames.Float4).ConnectToSource(texture_shader.ConnectableAPI(), "rgba")
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Float3).ConnectToSource(range_shader.ConnectableAPI(), "r")

            elif tex_type in ['roughness']:
                range_path = f"{material_prim.GetPath()}/arnold_{tex_type}Range"
                range_shader = self._arnold_initialize_range_shader(range_path)
                range_shader.CreateInput("input", Sdf.ValueTypeNames.Float4).ConnectToSource(texture_shader.ConnectableAPI(), "rgba")
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Float3).ConnectToSource(range_shader.ConnectableAPI(), "r")

            elif tex_type in ['height']:
                range_path = f"{material_prim.GetPath()}/arnold_{tex_type}Range"
                range_shader = self._arnold_initialize_range_shader(range_path)
                range_shader.CreateInput("input", Sdf.ValueTypeNames.Float4).ConnectToSource(texture_shader.ConnectableAPI(), "rgba")
                if not bump2d_shader:
                    bump2d_shader = self._arnold_initialize_bump2d_shader(bump2d_path)
                bump2d_shader.CreateInput("bump_map", Sdf.ValueTypeNames.Float).ConnectToSource(range_shader.ConnectableAPI(), "r")

            elif tex_type in ['normal']:
                normal_map_path = f"{material_prim.GetPath()}/arnold_NormalMap"
                normal_map_shader = self._arnold_initialize_normal_map_shader(normal_map_path)
                normal_map_shader.CreateInput("input", Sdf.ValueTypeNames.Float3).ConnectToSource(texture_shader.ConnectableAPI(), "vector")
                if not bump2d_shader:
                    bump2d_shader = self._arnold_initialize_bump2d_shader(bump2d_path)
                bump2d_shader.CreateInput("normal", Sdf.ValueTypeNames.Float4).ConnectToSource(normal_map_shader.ConnectableAPI(), "vector")

        if bump2d_shader:
            std_surf_shader.CreateInput('normal', Sdf.ValueTypeNames.Float3).ConnectToSource(bump2d_shader.ConnectableAPI(), "vector")


    ###  mtlx ###
    def _mtlx_create_material(self, parent_path, enable_transmission=False):
        shader_path = f'{parent_path}/mtlx_mtlxstandard_surface1'
        shader_usdshade = UsdShade.Shader.Define(self.stage, shader_path)
        material_prim = self.stage.GetPrimAtPath(parent_path)
        material_usdshade = UsdShade.Material.Define(self.stage, material_prim.GetPath())
        material_usdshade.CreateOutput("mtlx:surface", Sdf.ValueTypeNames.Token).ConnectToSource(shader_usdshade.ConnectableAPI(), "surface")

        self._mtlx_initialize_standard_surface_shader(shader_usdshade)
        self._mtlx_fill_texture_file_paths(material_prim, shader_usdshade)
        if enable_transmission:
            self._mtlx_enable_transmission(shader_usdshade)

        return material_usdshade


    def _mtlx_initialize_standard_surface_shader(self, shader_usdshade):
        shader_usdshade.CreateIdAttr("ND_standard_surface_surfaceshader")

        shader_usdshade.CreateInput('base', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('base_color', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.8, 0.8, 0.8))
        shader_usdshade.CreateInput('coat', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('coat_roughness', Sdf.ValueTypeNames.Float).Set(0.1)
        shader_usdshade.CreateInput('emission', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('emission_color', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('metalness', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('specular', Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput('specular_color', Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput('specular_IOR', Sdf.ValueTypeNames.Float).Set(1.5)
        shader_usdshade.CreateInput('specular_roughness', Sdf.ValueTypeNames.Float).Set(0.2)
        shader_usdshade.CreateInput('transmission', Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput('thin_walled', Sdf.ValueTypeNames.Int).Set(0)
        shader_usdshade.CreateInput('opacity',  Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1, 1, 1))


    def _mtlx_initialize_image_shader(self, image_path: str, signature="color3"):
        image_shader = UsdShade.Shader.Define(self.stage, image_path)
        image_shader.CreateIdAttr(f"ND_image_{signature}")
        image_shader.CreateInput("file", Sdf.ValueTypeNames.Asset)
        return image_shader


    def _mtlx_initialize_color_correct_shader(self, color_correct_path: str, signature="color3"):
        color_correct_shader = UsdShade.Shader.Define(self.stage, color_correct_path)
        color_correct_shader.CreateIdAttr(f"ND_colorcorrect_{signature}")

        return color_correct_shader

    def _mtlx_initialize_range_shader(self, range_path: str, signature="color3"):
        range_shader = UsdShade.Shader.Define(self.stage, range_path)
        range_shader.CreateIdAttr(f"ND_range_{signature}")
        return range_shader


    def _mtlx_initialize_normal_map_shader(self, normal_map_path: str):
        normal_map_shader = UsdShade.Shader.Define(self.stage, normal_map_path)
        normal_map_shader.CreateIdAttr("ND_normalmap")

        return normal_map_shader

    def _mtlx_initialize_bump2d_shader(self, bump2d_path: str):
        bump2d_shader = UsdShade.Shader.Define(self.stage, bump2d_path)
        bump2d_shader.CreateIdAttr("ND_bump_vector3")

        bump_height_input = bump2d_shader.CreateInput("bump_height", Sdf.ValueTypeNames.Float)
        bump_height_input.Set(1)
        bump_map_input = bump2d_shader.CreateInput("bump_map", Sdf.ValueTypeNames.Float)
        bump_map_input.Set(0)
        normal_input = bump2d_shader.CreateInput("normal", Sdf.ValueTypeNames.Float3)
        normal_input.Set((0, 0, 0))

        return bump2d_shader


    def _mtlx_enable_transmission(self, shader_usdshade):
        """
        given the mtlx standard surface, will set input primvar 'transmission' to value '0.9'
        """
        shader_usdshade.GetInput('transmission').Set(0.9)
        shader_usdshade.GetInput('thin_walled').Set(1)


    def _mtlx_fill_texture_file_paths(self, material_prim, std_surf_shader):
        """
        Fills the texture file paths for the given shader using the material_data.
        """
        texture_types_to_inputs = {
            'basecolor': 'base_color',
            'metalness': 'metalness',
            'roughness': 'specular_roughness',
            'opacity': 'opacity',
            'normal': 'normal',
            # 'height': '',  # disabled height for now
        }
        mtlx_image_signature = {
            'basecolor': "color3",
            'normal': "vector3",
            'metalness': "float",
            'opacity': "float",
            'roughness': "float",
            'height': "float",
        }

        bump2d_path = f"{material_prim.GetPath()}/mtlx_Bump2d"
        bump2d_shader = None

        for tex_type, tex_dict in self.material_dict.items():
            tex_filepath = tex_dict['path']
            tex_type = tex_type.lower()  # assume all lowercase
            if tex_type not in texture_types_to_inputs:
                print(f"WARNING:  tex_type: '{tex_type}' not supported yet for MTLX")
                continue

            input_name = texture_types_to_inputs[tex_type]

            # create 'ND_image_<signature>' prim
            texture_prim_path = f'{material_prim.GetPath()}/mtlx_{tex_type}Texture'
            texture_shader = self._mtlx_initialize_image_shader(texture_prim_path, signature=mtlx_image_signature[tex_type])
            texture_shader.GetInput("file").Set(tex_filepath)

            if tex_type in ['basecolor']:
                color_correct_path = f"{material_prim.GetPath()}/mtlx_{tex_type}ColorCorrect"
                color_correct_shader = self._mtlx_initialize_color_correct_shader(color_correct_path)
                color_correct_shader.CreateInput("in", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    texture_shader.ConnectableAPI(), "out")
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    color_correct_shader.ConnectableAPI(), "out")

            elif tex_type in ['metalness']:
                # disable metalness if material is transmissive like glass:
                if self.is_transmissive:
                    continue
                range_path = f"{material_prim.GetPath()}/mtlx_{tex_type}Range"
                range_shader = self._mtlx_initialize_range_shader(range_path)
                range_shader.CreateInput("in", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    texture_shader.ConnectableAPI(), "out")
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Float).ConnectToSource(
                    range_shader.ConnectableAPI(), "out")

            elif tex_type in ['roughness']:
                range_path = f"{material_prim.GetPath()}/mtlx_{tex_type}Range"
                range_shader = self._mtlx_initialize_range_shader(range_path)
                range_shader.CreateInput("in", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    texture_shader.ConnectableAPI(), "out")
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Float).ConnectToSource(
                    range_shader.ConnectableAPI(), "out")

            ###### BUMP MAP + NORMAL MAPS AREN'T SUPPORTED IN MTLX
            # elif tex_type in ['height']:
            #     range_path = f"{material_prim.GetPath()}/{tex_type}Range"
            #     range_shader = self._mtlx_initialize_range_shader(range_path)
            #     range_shader.CreateInput("in", Sdf.ValueTypeNames.Float4).ConnectToSource(
            #         texture_shader.ConnectableAPI(), "out")
            #     if not bump2d_shader:
            #         bump2d_shader = self._mtlx_initialize_bump2d_shader(bump2d_path)
            #     bump2d_shader.CreateInput("height", Sdf.ValueTypeNames.Float).ConnectToSource(
            #         range_shader.ConnectableAPI(), "out")

            elif tex_type in ['normal']:
                normal_map_path = f"{material_prim.GetPath()}/mtlx_NormalMap"
                normal_map_shader = self._mtlx_initialize_normal_map_shader(normal_map_path)
                normal_map_shader.CreateInput("in", Sdf.ValueTypeNames.Float3).ConnectToSource(
                    texture_shader.ConnectableAPI(), "out")
                # if not bump2d_shader:
                #     bump2d_shader = self._mtlx_initialize_bump2d_shader(bump2d_path)
                std_surf_shader.CreateInput("normal", Sdf.ValueTypeNames.Float4).ConnectToSource(
                    normal_map_shader.ConnectableAPI(), "out")

        if bump2d_shader:
            std_surf_shader.CreateInput('normal', Sdf.ValueTypeNames.Float3).ConnectToSource(
                bump2d_shader.ConnectableAPI(), "out")


    def _create_collect_prim(self, parent_prim_path: str, create_usd_preview=False, usd_preview_format=None,
                             create_arnold=False, create_mtlx=False, enable_transmission=False):
        """
        creates a collect material prim on stage
        :return: collect prim
        :rtype: UsdShade.Material
        """
        parent_prim_sdf = Sdf.Path(parent_prim_path)
        parent_prim = UsdGeom.Scope.Define(self.stage, parent_prim_sdf)
        collect_prim_path = f'{parent_prim_path}/mat_{self.material_name}_collect'
        collect_usd_material = UsdShade.Material.Define(self.stage, collect_prim_path)
        collect_usd_material.CreateInput("inputnum", Sdf.ValueTypeNames.Int).Set(2)

        if create_usd_preview:
            # Create the USD Preview Shader under the collect material
            usd_preview_material = self._create_usd_preview_material(collect_prim_path, usd_preview_format=usd_preview_format)
            usd_preview_shader = usd_preview_material.GetSurfaceOutput().GetConnectedSource()[0]
            collect_usd_material.CreateOutput("surface", Sdf.ValueTypeNames.Token).ConnectToSource(usd_preview_shader, "surface")

        if create_arnold:
            # Create the Arnold Shader under the collect material
            arnold_material = self._arnold_create_material(collect_prim_path, enable_transmission=enable_transmission)
            arnold_shader = arnold_material.GetOutput("arnold:surface").GetConnectedSource()[0]
            collect_usd_material.CreateOutput("arnold:surface", Sdf.ValueTypeNames.Token).ConnectToSource(arnold_shader, "surface")

        if create_mtlx:
            # Create the mtlx Shader under the collect material
            mtlx_material = self._mtlx_create_material(collect_prim_path, enable_transmission=enable_transmission)
            mtlx_shader = mtlx_material.GetOutput("mtlx:surface").GetConnectedSource()[0]
            collect_usd_material.CreateOutput("mtlx:surface", Sdf.ValueTypeNames.Token).ConnectToSource(mtlx_shader, "surface")

        return collect_usd_material



    def run(self):
        """
        Main entry: replicate Houdini NodeRecreator.run() flow:

          1. Ensure parent scope exists.
          2. Create collect-Material prim(s).
          3. Create all child shader prims.
          4. Wire outputs into the collect-Material.
          5. Wire inter-shader connections.
        """
        # 1. create parent scope exists
        UsdGeom.Scope.Define(self.stage, Sdf.Path(self.parent_scope_path))

        # 2. create output material prims
        self.create_material_prim()
        print(f"FINISHED _create_output_materials()")

        # 3. create child shader prims
        self.create_child_shaders(self.nodeinfo_list)
        print(f"FINISHED _create_child_shaders()")

        # 4. set up output connections
        self.set_output_connections()
        print(f"FINISHED _set_output_connections()")

        # 5. set up inter-shader connections
        self.set_shader_connections()
        print(f"FINISHED _set_shader_connections()")




def get_material_type(usd_material):
    """
    Args:
        usd_material (Usd.Material): input material prim, e.g., arnold materialbuilder
    Returns:
        (str): material type.
    """
    material_type = None
    material_list = []
    infoId_list = []
    for x in usd_material.GetPrim().GetChildren():
        infoId_list.append(x.GetAttribute('info:id').Get())

    if 'arnold:standard_surface' in infoId_list:
        material_list.append('arnold')
    if 'ND_standard_surface_surfaceshader' in infoId_list:
        material_list.append('mtlx')

    material_list = tuple(material_list)
    if len(material_list) > 1:
        raise Exception(f"ERROR: multiple material types found: '{material_list}', Script only supports one material type at a time.")

    material_type = material_list[0]

    return material_type



def test(stage, mat_node, target_renderer="mtlx"):
    import hou


    material_type, nodeinfo_list, output_connections = material_processor.ingest_material(mat_node)
    if not (material_type and nodeinfo_list and output_connections):
        return

    print("/////////////////////////////////////////////")
    print("/////////////////////////////////////////////")
    print("/////////////////////////////////////////////")
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
    except:
        traceback.print_exc()


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
    if not material_type or material_type not in ['arnold', 'mtlx']:
        print(f"Couldn't determine Input material type, "
              f"currently only Arnold, MTLX and Principled Shader are supported!")
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

    standardizer = material_processor.NodeStandardizer(
        traversed_nodes_dict=nested_nodes_dict,
        output_nodes_dict=output_nodes_dict,
        material_type='arnold',
    )
    nodeinfo_list, output_connections = standardizer.run()

    try:
        USDMaterialRecreator(stage, f"{mat_name}_new", nodeinfo_list, output_connections, target_renderer=target_renderer)
    except:
        traceback.print_exc()


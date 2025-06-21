"""
Copyright Ahmed Hindy. Please mention the author if you found any part of this code useful.

"""
import os
import json
from importlib import reload
import pprint
from typing import List, Optional

from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf

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

# for connections frommaterial prim to stdsurface prim
OUT_PRIM_DICT = {
    'arnold': {
        'GENERIC::output_surface': {
            'src': 'arnold:surface',
            'dest': 'surface'
        },
        'GENERIC::output_displacement': {
            'src': 'arnold:displacement',
            'dest': 'displacement'
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



class USDShadersIngest:
    """
    [WIP] this will ingest usd stage, traverse it for all usdPreview materials.
    """
    import hou
    def __init__(self, stage=None, mat_context=None):
        self.stage = stage or (hou.selectedNodes()[0].stage() if hou.selectedNodes() else None)
        if not self.stage:
            raise ValueError("Please select a LOP node.")

        self.mat_context = mat_context or hou.node('/mat')
        self.all_materials_names = set()
        self.materials_found_in_stage = []

        self.found_usdpreview_mats = None
        self.materialdata_list = []
        self.run()

    def _get_connected_file_path(self, shader_input):
        """
        Recursively follow shader input connections to find the actual file path.
        :param shader_input: <pxr.UsdShade.Input object>. which we get from <UsdShade.Shader object>.GetInput('file')
        """
        connection = shader_input.GetConnectedSource()
        while connection:
            connected_shader_api, connected_input_name, _ = connection
            connected_shader = UsdShade.Shader(connected_shader_api.GetPrim())
            connected_input = connected_shader.GetInput(connected_input_name)

            if connected_input and connected_input.HasConnectedSource():
                connection = connected_input.GetConnectedSource()
            else:
                return connected_input.Get()

    def _collect_texture_data(self, shader, material_data: MaterialData, path: List[str], connected_param: str):
        """
        Collects texture data from a given shader.
        :param shader: <UsdShade.Shader object> e.g. Usd.Prim(</scene/material/_03_Base/UsdPreviewSurface/ShaderUsdPreviewSurface>)
        :param material_data: MaterialData object containing material name and textures
        :param path: list representing the traversal path.
        :param connected_param: connected parameter name.
        """
        shader_prim = shader.GetPrim()
        shader_info_id = shader_prim.GetAttribute('info:id').Get()
        path.append(shader_info_id or shader_prim.GetName())

        if shader_info_id != 'UsdUVTexture':
            path.pop()
            return

        file_path_attr = shader.GetInput('file')
        if not file_path_attr or not isinstance(file_path_attr, UsdShade.Input):
            print(f'File path attribute is not found or not connected for {shader_prim}')
            path.pop()
            return

        attr_value = file_path_attr.Get() or self._get_connected_file_path(file_path_attr)
        if not isinstance(attr_value, Sdf.AssetPath):
            print(f'Invalid asset path type: {type(attr_value)}')
            path.pop()
            return

        file_path = attr_value.resolvedPath or attr_value.path
        if not file_path:
            print(f'Empty file path for asset: {attr_value}')
            path.pop()
            return

        material_data.textures[connected_param] = TextureInfo(
            file_path=file_path,
            traversal_path=' -> '.join(path),
            connected_input=connected_param
        )

        path.pop()

    def _traverse_shader_network(self, shader, material_data: MaterialData, path=None, connected_param="") -> None:
        """
        Main traversal function. Will modify passed 'material'.
        :param shader: <UsdShade.Shader object> e.g. Usd.Prim(</root/material/_03_Base/UsdPreviewSurface/ShaderUsdPreviewSurface>)
        :param material_data: MaterialData object containing material name and textures
        :param path: left empty when run from outside.
        :param connected_param: left empty when run from outside.
        """
        if path is None:
            path = []
        if shader is None:
            return

        self._collect_texture_data(shader, material_data, path, connected_param)

        shader_prim = shader.GetPrim()
        shader_id = shader_prim.GetAttribute('info:id').Get()

        # Recursive traversal for UsdPreviewSurface
        for input in shader.GetInputs():
            connection_info = input.GetConnectedSource()
            if connection_info:
                connected_shader_api, source_name, _ = connection_info
                connected_shader = UsdShade.Shader(connected_shader_api.GetPrim())

                # If it's connected to a UsdPreviewSurface, track the input name
                if shader_id == 'UsdPreviewSurface':
                    connected_param = input.GetBaseName()

                # Call the method recursively
                self._traverse_shader_network(connected_shader, material_data, path, connected_param)

    def _find_usd_preview_surface_shader(self, usdshade_material: UsdShade.Material) -> Optional[UsdShade.Shader]:
        """
        :param usdshade_material: UsdShade.Material prim
        :return: UsdShade.Shader prim of type 'UsdPreviewSurface' inside the material if found.
        """
        for shader_output in usdshade_material.GetOutputs():
            connection = shader_output.GetConnectedSource()
            if not connection:
                continue
            connected_shader_api, _, _ = connection
            connected_shader = UsdShade.Shader(connected_shader_api.GetPrim())
            shader_id = connected_shader.GetPrim().GetAttribute('info:id').Get()
            if shader_id == 'UsdPreviewSurface':
                return connected_shader
        return None

    def _get_all_materials_from_stage(self, stage) -> List[UsdShade.Material]:
        """
        :param stage: Usd.Stage object
        :return: list of UsdShade.Material of all found material prims in stage.
        """
        for prim in stage.Traverse():
            if not prim.IsA(UsdShade.Material):
                continue
            material = UsdShade.Material(prim)
            self.materials_found_in_stage.append(material)
        return self.materials_found_in_stage

    @staticmethod
    def _get_primitives_assigned_to_material(stage, usdshade_material:  UsdShade.Material, material_data: MaterialData) -> None:
        """
        Adds all primitives that have the given material assigned to them into the nodeinfo_list.

        :param stage: Usd.Stage object
        :param usdshade_material: UsdShade.Material type primitive on stage
        :param material_data: MaterialData instance containing the material name and textures
        """
        if not isinstance(material_data, MaterialData):
            raise ValueError(f"nodeinfo_list is not a <MaterialData> object, instead it's a {type(material_data)}.")

        if not usdshade_material or not isinstance(usdshade_material, UsdShade.Material):
            raise ValueError(
                f"Material at path {material_data.material_name} is not a <UsdShade.Material> object, instead it's a {type(usdshade_material)}.")

        material_path = usdshade_material.GetPath()
        bound_prims = []

        for prim in stage.Traverse():
            material_binding_api = UsdShade.MaterialBindingAPI(prim)
            bound_material, _ = material_binding_api.ComputeBoundMaterial()
            if bound_material and bound_material.GetPath() == material_path:
                bound_prims.append(prim)

        material_data.prims_assigned_to_material = bound_prims


    def create_materialdata_object(self, usdshade_material: UsdShade.Material) -> MaterialData:
        """
        Find the UsdPreviewSurface shader and start traversal from its inputs
        :return: MaterialData object with collected texture data
        """
        material_name = usdshade_material.GetPath().name
        material_path = usdshade_material.GetPrim().GetPath().pathString

        self.all_materials_names.add(material_name)
        material_data = MaterialData(usd_material=usdshade_material, material_name=material_name, material_path=material_path)
        return material_data

    def _standardize_textures_format(self, material_data: MaterialData) -> None:
        """
        Standardizes nodeinfo_list.textures dictionary variable.
        :param material_data: MaterialData object.
        """
        standardized_textures = {}
        for texture_type, texture_info in material_data.textures.items():
            if texture_type == 'diffuseColor':
                standardized_textures['albedo'] = texture_info
            elif texture_type == 'roughness':
                standardized_textures['roughness'] = texture_info
            elif texture_type == 'metallic':
                standardized_textures['metallness'] = texture_info
            elif texture_type == 'normal':
                standardized_textures['normal'] = texture_info
            elif texture_type == 'opacity':
                standardized_textures['opacity'] = texture_info
            elif texture_type == 'occlusion':
                standardized_textures['occlusion'] = texture_info
            else:
                print(f"Unknown texture type: {texture_type}")

        material_data.textures = standardized_textures

    def _save_textures_to_file(self, materials: List[MaterialData], file_path: str):
        """Pretty print the texture data list to a text file."""
        with open(file_path, 'w') as file:
            json.dump([material.__dict__ for material in materials], file, indent=4, default=lambda o: o.__dict__)
            print(f"Texture data successfully written to {file_path}")

    def run(self):
        """
        ingests usd stage finding all usdPreview materials.
        """
        ## INGESTING:
        self.found_usdpreview_mats = self._get_all_materials_from_stage(self.stage)
        print(f"...{self.found_usdpreview_mats=}\n")
        for usdshade_material in self.found_usdpreview_mats:
            material_data = self.create_materialdata_object(usdshade_material)
            if not material_data:
                print("continuing")
                continue

            usd_preview_surface = self._find_usd_preview_surface_shader(usdshade_material)
            if not usd_preview_surface:
                print(f"WARNING: No UsdPreviewSurface Shader found for material: {material_data.material_name}")
            self._traverse_shader_network(usd_preview_surface, material_data)
            self._standardize_textures_format(material_data)

            self._get_primitives_assigned_to_material(self.stage, usdshade_material, material_data)
            print(f"{material_data.usd_material=}")
            self.materialdata_list.append(material_data)



class USDMaterialRecreator:
    """
       Recreate material networks as USD ShadeMaterial primitives on a USD stage.

       Mimics Houdini NodeRecreator.run():
         - initialize a builder (UsdShade.Material)
         - create output shaders
         - create child shader prims
         - wire up output connections
         - wire up inter-shader connections
       """

    def __init__(self, stage: Usd.Stage, material_name, nodeinfo_list, output_connections,
                 parent_scope_path: str = "/materials", target_renderer: str = "arnold"):
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
        mapping = GENERIC_NODE_TYPES_TO_REGULAR_USD.get(generic_type, {})
        # print(f"DEBUG: {shader=} {generic_type=}")
        shader_id = mapping['info_id'][self.target_renderer]
        if shader_id:
            shader.CreateIdAttr(shader_id)
            return True
        return False

    def _set_shader_parameters(self, shader: UsdShade.Shader, node_type: str, parameters):
        """
        Apply standardized parameters to a USD shader prim for the target renderer.
        Uses REGULAR_PARAM_NAMES_TO_GENERIC to map original Hou/MTLX/Ai parm names to generic names,
        then maps generic names to renderer-specific USD input names via GENERIC_NODE_TYPES_TO_REGULAR_USD.
        """
        # if not parameters:
        #     return

        # look up standardized mapping for this node type
        std_parm_map = material_processor.REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type, {})

        for param in parameters:
            parm_orig_name: str    = param.name
            parm_generic_name: str = std_parm_map.get(parm_orig_name)
            parm_new_name = [key for key, val in std_parm_map.items() if val == parm_generic_name][0]
            # print(f"DEBUG: {node_type=}, {parm_orig_name=}, {parm_generic_name=}, {parm_new_name=}")
            if not parm_generic_name:
                continue  # skip unsupported params

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
                    print(f"///WARNING: {parm_new_name}.{val=} is not a tuple of all floats or ints, but {type(val)=}")
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
                print(f"///WARNING: {parm_new_name}.{val=} is unknown, {type(val)=}")
                type_name = Sdf.ValueTypeNames.Token

            inp = shader.CreateInput(parm_new_name, type_name)
            # print(f"DEBUG: {parm_new_name=}, {val=}")

            try:
                inp.Set(val)
            except Exception as e:
                print(f"ERROR: failed to set input '{parm_new_name}' to '{val}', {e=}")


    def create_material_prim(self):
        """
        Define a UsdShade.Material for each generic output.
        """
        self.created_out_primpaths = []
        for generic_output, out_dict in self.orig_output_connections.items():
            # DEBUG: generic_output='GENERIC::output_surface'
            # DEBUG: out_dict: {'node_name': 'OUT_material',
            #                       'node_path': '/mat/arnold_materialbuilder_basic/OUT_material',
            #                       'connected_node_name': 'standard_surface',
            #                       'connected_node_path': '/mat/arnold_materialbuilder_basic/standard_surface',
            #                       'connected_input_index': 0
            #                  }
            # DEBUG: self.material_name = 'arnold_materialbuilder_basic'


            mat_primname = self.material_name
            mat_primpath = Sdf.Path(f"{self.parent_scope_path}/{mat_primname}")
            mat_usdshade = UsdShade.Material.Define(self.stage, Sdf.Path(mat_primpath))

            self.created_out_primpaths.append(mat_primpath)
            self.old_new_map[out_dict['node_path']] = mat_primpath.pathString


    def create_child_shaders(self, nodeinfo_list):
        """
        Recursively define shader prims for each nodeinfo (excluding output nodes).
        """
        # DEBUG: self.created_out_primpaths=[Sdf.Path('/Materials/OUT_material')]
        for nodeinfo in nodeinfo_list:
            if nodeinfo.node_type == 'GENERIC::output_node':
                # still recurse into children of output nodes
                if nodeinfo.children_list:
                    self.create_child_shaders(nodeinfo.children_list)
                continue
            elif nodeinfo.node_type == None:
                if nodeinfo.children_list:
                    self.create_child_shaders(nodeinfo.children_list)
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

            # print(f"INFO:  Output detected: '{dst_path}' ")
            # print(f"Connecting prims: src: '{src_path}[{src_parm}]' to dest: '{dst_path}[{dst_parm}]'")

            src_api = UsdShade.Shader(self.stage.GetPrimAtPath(Sdf.Path(src_path)))

            mat_usdshade.CreateOutput(OUT_PRIM_DICT[self.target_renderer][generic_output]['dest'], Sdf.ValueTypeNames.Token).ConnectToSource(
                src_api.ConnectableAPI(), OUT_PRIM_DICT[self.target_renderer][generic_output]['src'])


    def set_shader_connections(self):
        """
        Connect child shader prims based on stored connection_tasks.
        """
        print(f"DEBUG: {self.orig_output_connections=}")
        print(f"DEBUG: {self.created_out_primpaths=}")
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
        detects if a material should have transmission or not based on material name,
        if a material has "glass" in its name, then transmission should be on!
        :rtype: bool
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
        Main entry: replicate NodeRecreator.run() flow
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





def test(stage, mat_node, target_renderer="mtlx"):
    import hou


    material_type, nodeinfo_list, output_connections = material_processor.ingest_material(mat_node)
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


    USDMaterialRecreator(stage, mat_node.name(), nodeinfo_list, output_connections, target_renderer=material_type)



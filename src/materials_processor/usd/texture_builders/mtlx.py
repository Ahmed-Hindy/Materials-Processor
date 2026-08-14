"""MaterialX texture material builder helpers."""

import logging

from pxr import Gf, Sdf, UsdShade

logger = logging.getLogger(__name__)


class MaterialXTextureMaterialMixin:
    """Create MaterialX texture shader networks."""

    ###  mtlx ###
    def _mtlx_create_material(self, parent_path, enable_transmission=False):
        shader_path = f"{parent_path}/mtlx_mtlxstandard_surface1"
        shader_usdshade = UsdShade.Shader.Define(self.stage, shader_path)
        material_prim = self.stage.GetPrimAtPath(parent_path)
        material_usdshade = UsdShade.Material.Define(self.stage, material_prim.GetPath())
        material_usdshade.CreateOutput("mtlx:surface", Sdf.ValueTypeNames.Token).ConnectToSource(
            shader_usdshade.ConnectableAPI(), "surface"
        )

        self._mtlx_initialize_standard_surface_shader(shader_usdshade)
        self._mtlx_fill_texture_file_paths(material_prim, shader_usdshade)
        if enable_transmission:
            self._mtlx_enable_transmission(shader_usdshade)

        return material_usdshade

    def _mtlx_initialize_standard_surface_shader(self, shader_usdshade):
        shader_usdshade.CreateIdAttr("ND_standard_surface_surfaceshader")

        shader_usdshade.CreateInput("base", Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput("base_color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.8, 0.8, 0.8))
        shader_usdshade.CreateInput("coat", Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput("coat_roughness", Sdf.ValueTypeNames.Float).Set(0.1)
        shader_usdshade.CreateInput("emission", Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput("emission_color", Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput("metalness", Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput("specular", Sdf.ValueTypeNames.Float).Set(1)
        shader_usdshade.CreateInput("specular_color", Sdf.ValueTypeNames.Float3).Set((1, 1, 1))
        shader_usdshade.CreateInput("specular_IOR", Sdf.ValueTypeNames.Float).Set(1.5)
        shader_usdshade.CreateInput("specular_roughness", Sdf.ValueTypeNames.Float).Set(0.2)
        shader_usdshade.CreateInput("transmission", Sdf.ValueTypeNames.Float).Set(0)
        shader_usdshade.CreateInput("thin_walled", Sdf.ValueTypeNames.Int).Set(0)
        shader_usdshade.CreateInput("opacity", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1, 1, 1))

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
        shader_usdshade.GetInput("transmission").Set(0.9)
        shader_usdshade.GetInput("thin_walled").Set(1)

    def _mtlx_fill_texture_file_paths(self, material_prim, std_surf_shader):
        """
        Fills the texture file paths for the given shader using the material_data.
        """
        texture_types_to_inputs = {
            "basecolor": "base_color",
            "metalness": "metalness",
            "roughness": "specular_roughness",
            "opacity": "opacity",
            "normal": "normal",
            # 'height': '',  # disabled height for now
        }
        mtlx_image_signature = {
            "basecolor": "color3",
            "normal": "vector3",
            "metalness": "float",
            "opacity": "float",
            "roughness": "float",
            "height": "float",
        }

        bump2d_path = f"{material_prim.GetPath()}/mtlx_Bump2d"
        bump2d_shader = None

        for tex_type, tex_dict in self.material_dict.items():
            tex_filepath = tex_dict["path"]
            tex_type = tex_type.lower()  # assume all lowercase
            if tex_type not in texture_types_to_inputs:
                logger.warning("tex_type: '%s' not supported yet for MTLX", tex_type)
                continue

            input_name = texture_types_to_inputs[tex_type]

            # create 'ND_image_<signature>' prim
            texture_prim_path = f"{material_prim.GetPath()}/mtlx_{tex_type}Texture"
            texture_shader = self._mtlx_initialize_image_shader(
                texture_prim_path, signature=mtlx_image_signature[tex_type]
            )
            texture_shader.GetInput("file").Set(tex_filepath)

            if tex_type in ["basecolor"]:
                color_correct_path = f"{material_prim.GetPath()}/mtlx_{tex_type}ColorCorrect"
                color_correct_shader = self._mtlx_initialize_color_correct_shader(color_correct_path)
                color_correct_shader.CreateInput("in", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    texture_shader.ConnectableAPI(), "out"
                )
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    color_correct_shader.ConnectableAPI(), "out"
                )

            elif tex_type in ["metalness"]:
                # disable metalness if material is transmissive like glass:
                if self.is_transmissive:
                    continue
                range_path = f"{material_prim.GetPath()}/mtlx_{tex_type}Range"
                range_shader = self._mtlx_initialize_range_shader(range_path)
                range_shader.CreateInput("in", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    texture_shader.ConnectableAPI(), "out"
                )
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Float).ConnectToSource(
                    range_shader.ConnectableAPI(), "out"
                )

            elif tex_type in ["roughness"]:
                range_path = f"{material_prim.GetPath()}/mtlx_{tex_type}Range"
                range_shader = self._mtlx_initialize_range_shader(range_path)
                range_shader.CreateInput("in", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    texture_shader.ConnectableAPI(), "out"
                )
                std_surf_shader.CreateInput(input_name, Sdf.ValueTypeNames.Float).ConnectToSource(
                    range_shader.ConnectableAPI(), "out"
                )

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

            elif tex_type in ["normal"]:
                normal_map_path = f"{material_prim.GetPath()}/mtlx_NormalMap"
                normal_map_shader = self._mtlx_initialize_normal_map_shader(normal_map_path)
                normal_map_shader.CreateInput("in", Sdf.ValueTypeNames.Float3).ConnectToSource(
                    texture_shader.ConnectableAPI(), "out"
                )
                # if not bump2d_shader:
                #     bump2d_shader = self._mtlx_initialize_bump2d_shader(bump2d_path)
                std_surf_shader.CreateInput("normal", Sdf.ValueTypeNames.Float4).ConnectToSource(
                    normal_map_shader.ConnectableAPI(), "out"
                )

        if bump2d_shader:
            std_surf_shader.CreateInput("normal", Sdf.ValueTypeNames.Float3).ConnectToSource(
                bump2d_shader.ConnectableAPI(), "out"
            )

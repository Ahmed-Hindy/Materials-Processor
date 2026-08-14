"""USD Preview texture material builder helpers."""

import logging
import os

from pxr import Sdf, UsdShade

logger = logging.getLogger(__name__)


class USDPreviewTextureMaterialMixin:
    """Create USD Preview texture shader networks."""

    ###  usd_preview ###
    def _create_usd_preview_material(self, parent_path, usd_preview_format):
        material_path = f"{parent_path}/UsdPreviewMaterial"
        material = UsdShade.Material.Define(self.stage, material_path)

        nodegraph_path = f"{material_path}/UsdPreviewNodeGraph"
        self.stage.DefinePrim(nodegraph_path, "NodeGraph")

        shader_path = f"{nodegraph_path}/UsdPreviewSurface"
        shader = UsdShade.Shader.Define(self.stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")

        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

        # Create textures for USD Preview Shader
        texture_types_to_inputs = {
            "basecolor": "diffuseColor",
            "metalness": "metallic",
            "roughness": "roughness",
            "normal": "normal",
            "opacity": "opacity",
            "height": "displacement",
        }

        for tex_type, tex_dict in self.material_dict.items():
            tex_filepath = tex_dict["path"]
            tex_type = tex_type.lower()  # assume all lowercase
            if tex_type not in texture_types_to_inputs:
                logger.warning("tex_type: '%s' not supported yet for usdpreview", tex_type)
                continue

            if usd_preview_format:
                file_format = os.path.splitext(tex_filepath)[1].rsplit(".", 1)[1]  # e.g. 'exr'
                tex_filepath = tex_filepath.replace(file_format, usd_preview_format)

            input_name = texture_types_to_inputs[tex_type]
            texture_prim_path = f"{nodegraph_path}/{tex_type}Texture"
            texture_prim = UsdShade.Shader.Define(self.stage, texture_prim_path)
            texture_prim.CreateIdAttr("UsdUVTexture")
            file_input = texture_prim.CreateInput("file", Sdf.ValueTypeNames.Asset)
            file_input.Set(tex_filepath)

            wrapS = texture_prim.CreateInput("wrapS", Sdf.ValueTypeNames.Token)
            wrapT = texture_prim.CreateInput("wrapT", Sdf.ValueTypeNames.Token)
            wrapS.Set("repeat")
            wrapT.Set("repeat")

            # Create Primvar Reader for ST coordinates
            st_reader_path = f"{nodegraph_path}/TexCoordReader"  # TODO: remove it from the for loop.
            st_reader = UsdShade.Shader.Define(self.stage, st_reader_path)
            st_reader.CreateIdAttr("UsdPrimvarReader_float2")
            st_input = st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token)
            st_input.Set("st")
            texture_prim.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
                st_reader.ConnectableAPI(), "result"
            )

            if tex_type in ["opacity", "metallic", "roughness"]:
                shader.CreateInput(input_name, Sdf.ValueTypeNames.Float3).ConnectToSource(
                    texture_prim.ConnectableAPI(), "r"
                )
            else:
                shader.CreateInput(input_name, Sdf.ValueTypeNames.Float3).ConnectToSource(
                    texture_prim.ConnectableAPI(), "rgb"
                )

        return material

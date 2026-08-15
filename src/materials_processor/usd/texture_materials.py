"""Helpers for building texture-driven USD material variants."""

import logging

from pxr import Sdf, UsdGeom, UsdShade

from materials_processor.usd.texture_builders import (
    ArnoldTextureMaterialMixin,
    MaterialXTextureMaterialMixin,
    USDPreviewTextureMaterialMixin,
)

logger = logging.getLogger(__name__)


def detect_if_transmissive(material_name):
    """
    Determine whether a material name indicates a transmissive material.
    
    Parameters:
    	material_name (str): Material name checked for case-insensitive occurrences of "glass" or "glas".
    
    Returns:
    	bool: `True` if the material name contains a transmissive keyword, `False` otherwise.
    """
    transmissive_matnames_list = ["glass", "glas"]
    is_transmissive = any(substring in material_name.lower() for substring in transmissive_matnames_list)
    if is_transmissive:
        logger.debug("Detected Transmissive Material: '%s'", material_name)

    return is_transmissive


class TextureMaterialFactory(
    USDPreviewTextureMaterialMixin,
    ArnoldTextureMaterialMixin,
    MaterialXTextureMaterialMixin,
):
    """Create collect materials and renderer-specific texture shader networks."""

    def __init__(self, stage, material_name, material_dict=None, is_transmissive=False):
        """Store material texture context used by the factory helpers."""
        self.stage = stage
        self.material_name = material_name
        self.material_dict = material_dict or {}
        self.is_transmissive = is_transmissive

    def _create_collect_prim(
        self,
        parent_prim_path: str,
        create_usd_preview=False,
        usd_preview_format=None,
        create_arnold=False,
        create_mtlx=False,
        enable_transmission=False,
    ):
        """
        Create a collect material at a path derived from the parent prim path and material name.
        
        Parameters:
            parent_prim_path (str): Path under which to create the collect material.
            usd_preview_format: Optional format for the USD Preview material.
            enable_transmission (bool): Whether to enable transmission for Arnold and MaterialX materials.
        
        Returns:
            UsdShade.Material: The created collect material.
        """
        parent_prim_sdf = Sdf.Path(parent_prim_path)
        UsdGeom.Scope.Define(self.stage, parent_prim_sdf)
        collect_prim_path = f"{parent_prim_path}/mat_{self.material_name}_collect"
        collect_usd_material = UsdShade.Material.Define(self.stage, collect_prim_path)
        collect_usd_material.CreateInput("inputnum", Sdf.ValueTypeNames.Int).Set(2)

        if create_usd_preview:
            # Create the USD Preview Shader under the collect material
            usd_preview_material = self._create_usd_preview_material(
                collect_prim_path, usd_preview_format=usd_preview_format
            )
            usd_preview_shader = usd_preview_material.GetSurfaceOutput().GetConnectedSource()[0]
            collect_usd_material.CreateOutput("surface", Sdf.ValueTypeNames.Token).ConnectToSource(
                usd_preview_shader, "surface"
            )

        if create_arnold:
            # Create the Arnold Shader under the collect material
            arnold_material = self._arnold_create_material(collect_prim_path, enable_transmission=enable_transmission)
            arnold_shader = arnold_material.GetOutput("arnold:surface").GetConnectedSource()[0]
            collect_usd_material.CreateOutput("arnold:surface", Sdf.ValueTypeNames.Token).ConnectToSource(
                arnold_shader, "surface"
            )

        if create_mtlx:
            # Create the mtlx Shader under the collect material
            mtlx_material = self._mtlx_create_material(collect_prim_path, enable_transmission=enable_transmission)
            mtlx_shader = mtlx_material.GetOutput("mtlx:surface").GetConnectedSource()[0]
            collect_usd_material.CreateOutput("mtlx:surface", Sdf.ValueTypeNames.Token).ConnectToSource(
                mtlx_shader, "surface"
            )

        return collect_usd_material

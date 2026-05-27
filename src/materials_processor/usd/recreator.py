"""Recreate generic material graphs as USD material networks."""

from pxr import Usd

from materials_processor.usd.graph_builder import USDGraphBuilder
from materials_processor.usd.texture_materials import TextureMaterialFactory, detect_if_transmissive


class USDMaterialRecreator:
    """Facade for rebuilding standardized material data on a USD stage."""

    def __init__(
        self,
        stage: Usd.Stage,
        material_name,
        nodeinfo_list,
        output_connections,
        parent_scope_path: str = "/materials",
        target_renderer: str = "arnold",
    ):
        """Initialize the recreator with material data and target stage."""
        self.stage = stage
        self.material_name = material_name
        self.nodeinfo_list = nodeinfo_list
        self.orig_output_connections = output_connections
        self.parent_scope_path = parent_scope_path
        self.target_renderer = target_renderer
        self.graph_builder = USDGraphBuilder(
            stage=stage,
            material_name=material_name,
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
            parent_scope_path=parent_scope_path,
            target_renderer=target_renderer,
        )
        self.material_map = self.graph_builder.material_map
        self.old_new_map = self.graph_builder.old_new_map
        self.created_out_primpaths = self.graph_builder.created_out_primpaths

    def create_material_prim(self):
        """Define output material prims for the standardized graph."""
        self._sync_graph_builder_state()
        return self.graph_builder.create_material_prim()

    def create_child_shaders(self, nodeinfo_list):
        """Define child shader prims for the standardized graph."""
        self._sync_graph_builder_state()
        return self.graph_builder.create_child_shaders(nodeinfo_list)

    def set_output_connections(self):
        """Connect root shaders to material outputs."""
        self._sync_graph_builder_state()
        return self.graph_builder.set_output_connections()

    def _find_valid_src(self, nodeinfo, parent_nodeinfo=None):
        self._sync_graph_builder_state()
        return self.graph_builder._find_valid_src(nodeinfo, parent_nodeinfo=parent_nodeinfo)

    def _connect_pair(self, src_prim, dst_prim, src_parm, dst_parm):
        self._sync_graph_builder_state()
        return self.graph_builder._connect_pair(src_prim, dst_prim, src_parm, dst_parm)

    def set_shader_connections(self, nodeinfo_list, parent_node=None):
        """Connect child shader prims for the standardized graph."""
        self._sync_graph_builder_state()
        return self.graph_builder.set_shader_connections(nodeinfo_list, parent_node=parent_node)

    def _sync_graph_builder_state(self):
        """Keep delegated graph operations compatible with mutable facade state."""
        self.graph_builder.stage = self.stage
        self.graph_builder.material_name = self.material_name
        self.graph_builder.nodeinfo_list = self.nodeinfo_list
        self.graph_builder.orig_output_connections = self.orig_output_connections
        self.graph_builder.parent_scope_path = self.parent_scope_path
        self.graph_builder.target_renderer = self.target_renderer
        self.graph_builder.material_map = self.material_map
        self.graph_builder.old_new_map = self.old_new_map
        self.graph_builder.created_out_primpaths = self.created_out_primpaths

    def _texture_factory(self):
        return TextureMaterialFactory(
            stage=self.stage,
            material_name=self.material_name,
            material_dict=getattr(self, "material_dict", {}),
            is_transmissive=getattr(self, "is_transmissive", False),
        )

    def _create_collect_prim(self, *args, **kwargs):
        """Create a texture-driven collect material using the legacy helper flow."""
        return self._texture_factory()._create_collect_prim(*args, **kwargs)

    def __getattr__(self, name):
        if name.startswith(("_arnold_", "_mtlx_")) or name == "_create_usd_preview_material":
            return getattr(self._texture_factory(), name)
        raise AttributeError(name)

    @staticmethod
    def detect_if_transmissive(material_name):
        """Return whether a material name should enable transmission defaults."""
        return detect_if_transmissive(material_name)

    def run(self):
        """Create USD materials, shaders, output links, and inter-shader links."""
        self._sync_graph_builder_state()
        return self.graph_builder.run()

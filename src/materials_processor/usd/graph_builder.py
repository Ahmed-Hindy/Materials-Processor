"""Build generic material graphs as USD shade networks."""

import logging
import pprint

from pxr import Sdf, UsdGeom, UsdShade

from materials_processor.mappings import REGULAR_PARAM_NAMES_TO_GENERIC, convert_generic
from materials_processor.usd.mappings import GENERIC_NODE_TYPES_TO_REGULAR_USD, OUT_PRIM_DICT, _ATTRIB_TYPE_CASTERS

logger = logging.getLogger(__name__)


class USDGraphBuilder:
    """Create and connect USD primitives from standardized generic node data."""

    def __init__(self, stage, material_name, nodeinfo_list, output_connections, parent_scope_path, target_renderer):
        """Store USD graph build inputs without mutating the stage."""
        self.stage = stage
        self.material_name = material_name
        self.nodeinfo_list = nodeinfo_list
        self.orig_output_connections = output_connections
        self.parent_scope_path = parent_scope_path
        self.target_renderer = target_renderer
        self.material_map = {}
        self.old_new_map = {}
        self.created_out_primpaths = []

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
        shader_id = mapping.get('info_id', {}).get(self.target_renderer)
        if shader_id:
            shader.CreateIdAttr(shader_id)
            return True
        return False

    def _apply_parameters(self, shader, node_type, parameters):
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
            logger.warning("No parameters found for shader: '%s'", shader.GetPath().pathString)
            return

        # look up standardized mapping for this node type
        std_parm_map: dict = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type.replace('::', ':'))
        if not std_parm_map:
            logger.warning("No generic parameter mappings found for node type: '%s'", node_type)
            return

        for param in parameters:
            if param.direction != 'input':
                logger.warning("Parameter '%s' is not an input parameter for node type '%s'. Skipping.", param.generic_name, node_type)
                continue
            if not param.generic_name:
                logger.warning("Parameter of value:'%s' has no generic_name for node type '%s'. Skipping.", param.value, node_type)
                continue

            parm_new_name = [key for key, val in std_parm_map.items() if val == param.generic_name]

            if not parm_new_name:
                logger.warning("No renderer-specific parameter found for generic name '%s' for node type '%s'. Skipping.", param.generic_name, node_type)
                continue  # skip unsupported params

            parm_new_name = parm_new_name[0]
            val = param.value
            if not val:
                continue

            val_type = _ATTRIB_TYPE_CASTERS.get(param.generic_type)
            if not val_type:
                logger.warning("parm: '%s' has no type!, val_type=%s", parm_new_name, val_type)
                continue

            inp = shader.CreateInput(parm_new_name, val_type)
            try:
                inp.Set(val)
            except Exception as e:
                logger.error("failed to set input '%s' to '%s[%s]' for value_type: %s->%s, error: %s", parm_new_name, val, type(val), param.generic_type, val_type, e)


    def create_material_prim(self):
        """
        Define the collect-Material prim(s) at `<parent_scope>/<material_name>`.

        Populates self.old_new_map for each Houdini output node.
        """
        for out_dict in self.orig_output_connections.values():
            mat_primname = self.material_name
            mat_primpath = Sdf.Path(f"{self.parent_scope_path}/{mat_primname}")
            UsdShade.Material.Define(self.stage, Sdf.Path(mat_primpath))

            self.created_out_primpaths.append(mat_primpath)
            self.old_new_map[out_dict['node_path']] = mat_primpath.pathString


    def create_child_shaders(self, nodeinfo_list):
        """
        Recursively define all intermediate UsdShade.Shader prims.

        Args:
            nodeinfo_list (List[NodeInfo]): Generic node info hierarchy.
        """

        for nodeinfo in nodeinfo_list:
            if not self.old_new_map.get(nodeinfo.node_path):
                new_prim_path = nodeinfo.node_name.replace('/', '_')
                shader_primpath = f"{self.created_out_primpaths[0].pathString}/{new_prim_path}"
                shader = UsdShade.Shader.Define(self.stage, Sdf.Path(shader_primpath))
                self._create_shader_id(shader, nodeinfo.node_type)

                regular_node_type = convert_generic(
                    node_type=nodeinfo.node_type,
                    target_renderer=self.target_renderer,
                    profile='usd_prims'
                )
                self._apply_parameters(shader, regular_node_type, nodeinfo.parameters)

                # store it in the 'old_new_map' dict
                self.old_new_map[nodeinfo.node_path] = shader.GetPath().pathString

            # recurse into children:
            if nodeinfo.children_list:
                self.create_child_shaders(nodeinfo.children_list)


    def set_output_connections(self):
        """
        Wire core shaders to output material surface slots.
        """
        mat_primpath = Sdf.Path(f"{self.parent_scope_path}/{self.material_name}")
        mat_usdshade = UsdShade.Material.Get(self.stage, mat_primpath)

        logger.debug("self.created_out_primpaths: %s", pprint.pformat(self.created_out_primpaths, sort_dicts=False))
        for generic_output, out_dict in self.orig_output_connections.items():
            src_path = self.old_new_map[out_dict['connected_node_path']]
            dst_path = self.old_new_map[out_dict['node_path']]
            if dst_path not in [x.pathString for x in self.created_out_primpaths]:
                continue


            src_api = UsdShade.Shader(self.stage.GetPrimAtPath(Sdf.Path(src_path)))
            mat_usdshade.CreateOutput(OUT_PRIM_DICT[self.target_renderer][generic_output]['dest'], Sdf.ValueTypeNames.Token).ConnectToSource(
                src_api.ConnectableAPI(), OUT_PRIM_DICT[self.target_renderer][generic_output]['src'])


    def _find_valid_src(self, nodeinfo, parent_nodeinfo=None):
        """
        Recursively walk nodeinfo.children_list looking for the
        first child whose prim has a non‐empty info:id.
        Returns (dst_prim, dst_nodeinfo) or (None, None).
        """
        logger.debug("prim: '%s': children_list: %s", nodeinfo.node_path, nodeinfo.children_list)
        if parent_nodeinfo:
            logger.debug("parent: '%s'", parent_nodeinfo.node_path)
        for conn_index, conn in nodeinfo.connection_info.items():
            logger.debug("node: parent node_path: '%s'", conn['output']['node_path'])
            if parent_nodeinfo and conn['output']['node_path'] != parent_nodeinfo.node_path:
                logger.debug("Invalid parent, skipping connection!")
                continue

            logger.debug("node: %s -> %s", conn['input']['parm_name'], conn['output']['parm_name'])
            for child_nodeinfo in nodeinfo.children_list:
                child_path = self.old_new_map[child_nodeinfo.node_path]
                prim = self.stage.GetPrimAtPath(Sdf.Path(child_path))
                logger.debug("child prim: '%s'", child_path)
                if prim and prim.GetAttribute('info:id').Get():
                    for c_conn_index, c_conn in child_nodeinfo.connection_info.items():
                        logger.debug("child: %s -> %s", c_conn['input']['parm_name'], c_conn['output']['parm_name'])
                        if nodeinfo and c_conn['output']['node_path'] != nodeinfo.node_path:
                            logger.debug("Invalid node, skipping connection!")
                            continue

                        return prim, c_conn

                # recurse deeper
                deeper_prim, deeper_conn = self._find_valid_src(child_nodeinfo, nodeinfo)
                if deeper_prim:
                    return deeper_prim, deeper_conn
        return None, None

    def _connect_pair(self, src_prim, dst_prim, src_parm, dst_parm):
        try:
            src_api = UsdShade.Shader(src_prim)
            dst_api = UsdShade.Shader(dst_prim)
            logger.info("Connecting prims: %s[%s] -> %s[%s]", src_prim.GetPath().pathString, src_parm, dst_prim.GetPath().pathString, dst_parm)
            inp = dst_api.CreateInput(dst_parm, Sdf.ValueTypeNames.Token)
            inp.ConnectToSource(src_api.ConnectableAPI(), src_parm)
        except Exception as e:
            logger.error("FAILED to connect %s[%s] -> %s[%s]: %s", src_prim.GetPath(), src_parm, dst_prim.GetPath().pathString, dst_parm, e)

    def set_shader_connections(self, nodeinfo_list, parent_node=None):
        """
        Connect child shader prims based on stored connection_tasks.
        """
        for nodeinfo in nodeinfo_list:
            for conn_index, conn in nodeinfo.connection_info.items():
                src_path = self.old_new_map.get(conn['input']['node_path'])
                dst_path = self.old_new_map.get(conn['output']['node_path'])
                src_parm = conn['input']['parm_name']
                dst_parm = conn['output']['parm_name']
                src_prim = self.stage.GetPrimAtPath(Sdf.Path(src_path)) if src_path else None
                dst_prim = self.stage.GetPrimAtPath(Sdf.Path(dst_path)) if dst_path else None

                logger.debug("Iteration: '%s', '%s[%s] -> %s[%s]'", conn_index, src_path, src_parm, dst_path, dst_parm)
                if not (src_prim and dst_prim and src_prim.IsValid() and dst_prim.IsValid()):
                    logger.warning("SKIPPING connection, invalid prims found src:%s, dst:%s", src_prim, dst_prim)
                    continue
                if not src_prim.GetAttribute('info:id').Get() and not dst_prim.GetAttribute('info:id').Get():
                    logger.warning("SKIPPING connection, both missing 'info:id'")
                    continue
                if dst_prim.GetTypeName() == 'Material':
                    logger.warning("SKIPPING connection, dst_prim's primitive type is a Material not a Shader!")
                    continue

                if not src_prim.GetAttribute('info:id').Get():
                    logger.debug("No info:id found, searching children...")
                    new_src_prim, new_conn = self._find_valid_src(nodeinfo)
                    if not new_src_prim:
                        logger.warning("SKIPPING child connection '%s -> %s': _find_valid_src() didn't find anything!", src_path, dst_path)
                        continue

                    logger.debug("new_src_prim=%s", new_src_prim)
                    logger.debug("new_conn: %s", pprint.pformat(new_conn, sort_dicts=False))
                    self._connect_pair(new_src_prim, dst_prim, new_conn['input']['parm_name'], dst_parm)
                    continue


                self._connect_pair(src_prim, dst_prim, src_parm, dst_parm)

            # recurse into children:
            if nodeinfo.children_list:
                self.set_shader_connections(nodeinfo.children_list)


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
        logger.info("STARTING create_material_prim()....")
        self.create_material_prim()
        logger.info("FINISHED create_material_prim()")

        logger.debug("self.created_out_primpaths=%s", self.created_out_primpaths)
        logger.debug("1 self.old_new_map=%s", self.old_new_map)

        # 3. create child shader prims
        logger.info("STARTING create_child_shaders()....")
        self.create_child_shaders(self.nodeinfo_list)
        logger.info("FINISHED _create_child_shaders()")

        # 4. set up output connections
        logger.info("STARTING set_output_connections()....")
        self.set_output_connections()
        logger.info("FINISHED _set_output_connections()")

        logger.debug("2 self.old_new_map=%s", self.old_new_map)

        # 5. set up inter-shader connections
        logger.info("STARTING set_shader_connections()....")
        self.set_shader_connections(self.nodeinfo_list)
        logger.info("FINISHED set_shader_connections()")

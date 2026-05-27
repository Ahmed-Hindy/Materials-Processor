import json
from importlib import resources

from materials_processor.houdini.principled_adapter import build_principled_entry


class FakeParm:
    def __init__(self, value):
        self._value = value

    def eval(self):
        return self._value


class FakePrincipledNode:
    def __init__(self):
        self.converted = False
        self._parms = {
            "basecolor_useTexture": True,
            "basecolor_texture": "F:/Assets 3D/Textures/Wood Planks dirt/wood_planks_dirt_diff_2k.jpg",
            "metallic_useTexture": False,
            "rough_useTexture": True,
            "rough_texture": "F:/Assets 3D/Textures/Wood Planks dirt/wood_planks_dirt_rough_2k.jpg",
            "sss_useTexture": False,
            "baseBumpAndNormal_enable": True,
            "baseBumpAndNormal_type": "normal",
            "baseNormal_texture": "F:/Assets 3D/Textures/Wood Planks dirt/wood_planks_dirt_nor_2k.jpg",
            "dispTex_enable": False,
        }

    def parm(self, name):
        return FakeParm(self._parms[name])

    def path(self):
        return "/mat/principledshader"


def _convert_parms(node):
    node.converted = True
    return {"input": [], "output": []}


def test_principled_adapter_matches_existing_xfailed_fixture():
    node = FakePrincipledNode()
    fixture_path = resources.files("materials_processor.fixtures") / "houdini_principled_to_mtlx_traversed_nodes.json"

    expected = json.loads(fixture_path.read_text())

    assert build_principled_entry(node, _convert_parms) == expected
    assert node.converted


def test_principled_adapter_preserves_legacy_displacement_path_mismatch():
    node = FakePrincipledNode()

    entry = build_principled_entry(node, _convert_parms)

    displacement = entry["/mat/principledshader/displacement_output"]["children_list"][0]
    assert displacement["node_path"] == "/mat/principledshaderl/mtlxdisplacement"
    assert displacement["connections_dict"]["connection_0"]["input"]["node_path"] == (
        "/mat/principledshader/mtlxdisplacement"
    )
    assert displacement["connections_dict"]["connection_0"]["output"]["node_path"] == (
        "/mat/principledshaderl/displacement_output"
    )

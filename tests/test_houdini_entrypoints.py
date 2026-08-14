from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_houdini_entrypoints_use_new_package_name():
    text = (ROOT / "houdini" / "OPmenu.xml").read_text(encoding="utf-8")
    text += (ROOT / "houdini" / "toolbar" / "MaterialProcessor.shelf").read_text(encoding="utf-8")
    assert "materials_processor" in text
    assert "Material_Processor" not in text


def test_houdini_package_points_to_src_and_houdini_folder():
    text = (ROOT / "Axe_Material_Processor.json").read_text(encoding="utf-8")
    assert "Materials-Processor/src" in text
    assert "Materials-Processor/houdini" in text

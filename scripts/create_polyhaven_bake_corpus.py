"""Build a small real-world Blender baking corpus from Poly Haven CC0 textures.

The corpus is intentionally opt-in: it queries Poly Haven's public API and only
downloads the selected 1K source maps.  It creates a Blender scene whose materials
exercise image textures, UV coordinates, Mapping, scalar channels, and normal maps
without committing third-party texture data to this repository.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from materials_processor.dcc.blender.runtime import resolve_blender_runtime

API_ROOT = "https://api.polyhaven.com"
USER_AGENT = "MaterialsProcessor/2.0-beta (local real-world bake validation)"
DEFAULT_ASSETS = (
    "aerial_asphalt_01",
    "anti_slip_concrete",
    "wood_planks_grey",
    "blue_metal_plate",
    "fabric_pattern_05",
    "rocky_terrain_02",
    "floor_tiles_02",
    "brown_leather",
    "brick_wall_001",
    "marble_01",
)
METALLIC_ASSETS = {"blue_metal_plate"}
COLOR_MAP_NAMES = ("Diffuse", "col_01", "col_02", "col_03")
ROUGHNESS_MAP_NAMES = ("Rough", "rough")
NORMAL_MAP_NAMES = ("nor_gl", "nor_dx")


def _read_json(url: str) -> dict[str, Any]:
    """Read JSON from Poly Haven with its requested identifiable user agent."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS API root.
        return json.loads(response.read().decode("utf-8"))


def _map_download(files: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any] | None:
    """Return the first available 1K JPG map matching ``names``."""
    for name in names:
        candidate = files.get(name, {}).get("1k", {}).get("jpg")
        if candidate:
            return candidate
    return None


def _download(url: str, destination: Path) -> None:
    """Download one previously size-budgeted source texture."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:  # noqa: S310 - fixed HTTPS URLs from API.
        destination.write_bytes(response.read())


def _collect_assets(asset_ids: tuple[str, ...], budget_bytes: int) -> list[dict[str, Any]]:
    """Resolve source maps and reject the corpus before downloads exceed its budget."""
    catalog = _read_json(f"{API_ROOT}/assets")
    collected: list[dict[str, Any]] = []
    total_size = 0
    for asset_id in asset_ids:
        asset = catalog.get(asset_id)
        if asset is None or asset.get("type") != 1:
            raise ValueError(f"Poly Haven texture asset was not found: {asset_id}")
        files = _read_json(f"{API_ROOT}/files/{asset_id}")
        maps = {
            "base_color": _map_download(files, COLOR_MAP_NAMES),
            "roughness": _map_download(files, ROUGHNESS_MAP_NAMES),
            "normal": _map_download(files, NORMAL_MAP_NAMES),
        }
        if asset_id in METALLIC_ASSETS:
            maps["arm"] = _map_download(files, ("arm",))
        missing = [name for name in ("base_color", "roughness") if maps[name] is None]
        if missing:
            raise ValueError(f"{asset_id} has no usable 1K JPG {'/'.join(missing)} map")
        map_entries = {name: entry for name, entry in maps.items() if entry is not None}
        size = sum(int(entry["size"]) for entry in map_entries.values())
        total_size += size
        if total_size > budget_bytes:
            raise ValueError(
                f"Selected source maps total {total_size / 1024 / 1024:.1f} MiB, "
                f"above the {budget_bytes / 1024 / 1024:.1f} MiB safety budget."
            )
        collected.append(
            {
                "id": asset_id,
                "name": asset["name"],
                "maps": map_entries,
                "expected_bytes": size,
                "metallic_from_arm": asset_id in METALLIC_ASSETS,
            }
        )
    return collected


def _write_builder_script(path: Path) -> None:
    """Write the Blender-only scene builder used by this independent corpus."""
    path.write_text(
        '''import json
import sys
from pathlib import Path

import bpy

manifest_path = Path(sys.argv[sys.argv.index("--") + 1])
scene_path = Path(sys.argv[sys.argv.index("--") + 2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))


def load_image(tree, filepath, label, non_color=False):
    node = tree.nodes.new(type="ShaderNodeTexImage")
    node.name = label
    node.label = label
    node.image = bpy.data.images.load(filepath, check_existing=True)
    if non_color:
        for color_space in ("Non-Color", "Raw"):
            try:
                node.image.colorspace_settings.name = color_space
                break
            except TypeError:
                pass
    else:
        # Poly Haven's JPG base-color maps are sRGB textures. Blender's ACES
        # configuration otherwise guesses ACES2065-1 from the file extension,
        # which is wrong and invalidates a scene-linear bake comparison.
        for color_space in ("Utility - sRGB - Texture", "sRGB"):
            try:
                node.image.colorspace_settings.name = color_space
                break
            except TypeError:
                pass
    return node


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for material in list(bpy.data.materials):
    bpy.data.materials.remove(material)

for index, entry in enumerate(manifest["assets"]):
    bpy.ops.mesh.primitive_plane_add(size=2, location=((index % 5) * 2.5, -(index // 5) * 2.5, 0))
    obj = bpy.context.active_object
    obj.name = entry["id"]
    material = bpy.data.materials.new(name=entry["name"])
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new(type="ShaderNodeOutputMaterial")
    principled = tree.nodes.new(type="ShaderNodeBsdfPrincipled")
    texcoord = tree.nodes.new(type="ShaderNodeTexCoord")
    mapping = tree.nodes.new(type="ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.25, 1.25, 1.0)
    tree.links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])
    tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    base = load_image(tree, entry["local_maps"]["base_color"], "Poly Haven Base Color")
    tree.links.new(mapping.outputs["Vector"], base.inputs["Vector"])
    tree.links.new(base.outputs["Color"], principled.inputs["Base Color"])

    rough = load_image(tree, entry["local_maps"]["roughness"], "Poly Haven Roughness", non_color=True)
    tree.links.new(mapping.outputs["Vector"], rough.inputs["Vector"])
    tree.links.new(rough.outputs["Color"], principled.inputs["Roughness"])

    normal_path = entry["local_maps"].get("normal")
    if normal_path:
        normal = load_image(tree, normal_path, "Poly Haven Normal", non_color=True)
        normal_map = tree.nodes.new(type="ShaderNodeNormalMap")
        tree.links.new(mapping.outputs["Vector"], normal.inputs["Vector"])
        tree.links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    arm_path = entry["local_maps"].get("arm")
    if arm_path:
        arm = load_image(tree, arm_path, "Poly Haven ARM", non_color=True)
        split = tree.nodes.new(type="ShaderNodeSeparateRGB")
        tree.links.new(mapping.outputs["Vector"], arm.inputs["Vector"])
        tree.links.new(arm.outputs["Color"], split.inputs["Image"])
        tree.links.new(split.outputs["B"], principled.inputs["Metallic"])

    obj.data.materials.append(material)

bpy.context.scene.render.engine = "CYCLES"
bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
''',
        encoding="utf-8",
    )


def _build_blender_scene(output_dir: Path, manifest: dict[str, Any]) -> Path:
    """Create a single-UV-mesh-per-material Blender scene for the corpus."""
    manifest_path = output_dir / "corpus_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    builder_path = output_dir / "build_polyhaven_corpus.py"
    _write_builder_script(builder_path)
    scene_path = output_dir / "polyhaven_real_world_materials.blend"
    runtime = resolve_blender_runtime()
    subprocess.run(
        [str(runtime.blender_exe), "--background", "--python", str(builder_path), "--", str(manifest_path), str(scene_path)],
        check=True,
    )
    return scene_path


def main() -> int:
    """Build the downloadable corpus and print the follow-up bake command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--budget-mib", type=float, default=64.0)
    parser.add_argument("--assets", nargs="+", default=DEFAULT_ASSETS)
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    collected = _collect_assets(tuple(args.assets), int(args.budget_mib * 1024 * 1024))
    texture_root = output_dir / "source_textures"
    for entry in collected:
        material_dir = texture_root / entry["id"]
        material_dir.mkdir(parents=True, exist_ok=True)
        local_maps: dict[str, str] = {}
        for map_name, download in entry["maps"].items():
            destination = material_dir / Path(download["url"]).name
            if not destination.exists() or destination.stat().st_size != int(download["size"]):
                _download(download["url"], destination)
            local_maps[map_name] = str(destination)
        entry["local_maps"] = local_maps

    manifest = {
        "source": "Poly Haven CC0",
        "source_api": API_ROOT,
        "resolution": "1k",
        "assets": collected,
        "total_expected_bytes": sum(entry["expected_bytes"] for entry in collected),
    }
    scene_path = _build_blender_scene(output_dir, manifest)
    print(f"Built {len(collected)} real-world materials: {scene_path}")
    print(
        "Bake with: uv --system-certs run materials-processor blender export-usd "
        f'"{scene_path}" --out-dir "{output_dir / "baked_usd"}" '
        "--bake all --bake-mode auto --bake-resolution 512 --target materialx --target openpbr"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

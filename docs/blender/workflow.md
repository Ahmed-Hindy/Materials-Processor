# Blender Material Workflow Guide

This guide covers the Blender command-line workflow in Materials Processor: inspecting a `.blend`, converting supported graphs to USD MaterialX and OpenPBR, preserving Blender-native MaterialX where possible, baking portable PBR streams, and using the explicit non-PBR beauty fallback.

The Blender integration is a beta workflow. Treat each exported material as a deliverable that needs validation in its intended renderer, especially for production node groups and procedural assets.

## What the workflow produces

The command reads Blender materials headlessly and writes material-only USD layers. It does not export a complete scene or mesh assembly.

| Workflow | Purpose | Main output |
| --- | --- | --- |
| Inspect | Audit materials, unsupported nodes, and texture paths without creating USD materials. | Report JSON; optional graph JSON |
| Graph conversion | Convert supported Blender node graphs to neutral MaterialX and OpenPBR USD materials. | `blender_scene_materialx.usda`, `blender_scene_openpbr.usda` |
| Native MaterialX | Ask Blender to make its own MaterialX graph, then extract its materials. | `blender_native_materialx.usda` |
| PBR bake | Bake known PBR streams to textures and rebuild texture-driven USD materials. | `baked_textures/`, `blender_baked_materials_*.usda` |
| Beauty bake | Capture Blender's final, scene-lit appearance for a non-PBR graph as an unlit texture material. | `baked_textures/*_beauty.exr`, `blender_baked_materials_*.usda` |

The normal conversion and baking paths write both MaterialX (`mtlx`) and OpenPBR targets by default. Native Blender MaterialX is MaterialX-only. A beauty bake writes an `ND_surface_unlit` surface in each selected USD target file; it deliberately is not an OpenPBR reconstruction.

## Prerequisites and runtime discovery

Use the project environment:

```powershell
uv --native-tls sync
uv --native-tls run materials-processor doctor
uv --native-tls run materials-processor runtime validate --dcc blender --material-smoke
```

On Windows, runtime discovery checks these sources in order:

1. `--blender-exe C:\path\to\blender.exe`
2. `MATERIALS_PROCESSOR_BLENDER_EXE`
3. `--blender-root C:\path\to\Blender`
4. `MATERIALS_PROCESSOR_BLENDER_ROOT`
5. Installed Blender directories under `C:\Program Files\Blender Foundation`, preferring Blender 4.x candidates
6. `blender` on `PATH`

Useful per-command overrides are `--blender-exe`, `--blender-root`, `--blender-version`, `--timeout`, and `--package-src`. The default headless timeout is 300 seconds. Use an explicit executable when a production scene requires a particular Blender version.

## Inspect before exporting

Inspection is read-only with respect to the source scene. It writes a JSON report only if requested.

```powershell
uv --native-tls run materials-processor blender inspect "C:\assets\chair.blend" `
  --report-json "C:\temp\chair_inspect.json" `
  --graph-json "C:\temp\chair_graphs.json"
```

The report includes material counts, graph read failures, unsupported Blender node types, missing texture paths, and applied texture remaps. Inspect this before deciding whether to convert, use native MaterialX, or bake.

To make unsupported nodes or unresolved texture paths fail the command:

```powershell
uv --native-tls run materials-processor blender inspect "C:\assets\chair.blend" `
  --fail-on-unsupported --missing-textures error
```

## Convert supported graphs

For supported Blender graphs, export both targets:

```powershell
uv --native-tls run materials-processor blender export-usd "C:\assets\chair.blend" `
  --out-dir "C:\temp\chair_materials"
```

Use `--target materialx`, `--target openpbr`, or repeat `--target` to select targets. `--target all` is equivalent to the default. The output directory contains:

```text
blender_material_graphs.json
blender_scene_materialx.usda
blender_scene_openpbr.usda
export_report.json
```

The graph JSON is the extracted neutral intermediate form. The export report records the USD material prims and shader identifiers, and should travel with validation results when a material is handed downstream.

### Texture-path repair

Graph conversion and inspection can repair texture references before USD is written:

```powershell
uv --native-tls run materials-processor blender export-usd "C:\assets\chair.blend" `
  --out-dir "C:\temp\chair_materials" `
  --remap-prefix "C:\old_library=D:\textures" `
  --texture-root "D:\textures" `
  --missing-textures error
```

`--remap-prefix OLD=NEW` replaces a matching path prefix. `--texture-root` searches that directory by texture filename when no prefix rule applies. These options operate on extracted graph texture paths; they are not a substitute for making source textures available to Blender during a Blender bake.

## Native Blender MaterialX fallback

When graph conversion cannot represent a Blender-specific procedural graph or group, export Blender's own MaterialX graph:

```powershell
uv --native-tls run materials-processor blender export-usd "C:\assets\complex_asset.blend" `
  --out-dir "C:\temp\complex_materials" --native-materialx
```

This creates `blender_native_materialx.usda` alongside the normal graph-conversion output. It is an additional fallback, not an OpenPBR equivalent.

Check `native_materialx.suspect_magenta_materials` in `export_report.json`. Blender can represent an unsupported group as an unconnected MaterialX base colour of `(1, 0, 1)`. That is a failed translation, not a valid bright-magenta material; use a bake or correct the source graph instead.

`--native-materialx` and `--bake` are alternative export paths and cannot be combined in one command.

## Baking decision guide

Use baking when the destination needs textures instead of a node graph, or when a graph cannot be converted faithfully.

| Mode | Best for | Result | Important limitation |
| --- | --- | --- | --- |
| `pbr` (default) | Direct Principled materials and groups that explicitly expose PBR streams. | Relightable texture-driven MaterialX/OpenPBR material. | Complex closures are skipped rather than approximated. |
| `beauty` | Non-PBR or renderer-specific materials where a captured appearance is acceptable. | Blender `COMBINED` bake attached to `ND_surface_unlit`. | Depends on the Blender scene lighting and is not view-dependent or relightable. |
| `auto` | Mixed asset libraries where valid PBR materials should stay PBR. | PBR for qualifying materials; beauty fallback for the rest. | One output set can contain both PBR and unlit materials. |

### PBR bake

```powershell
uv --native-tls run materials-processor blender export-usd "C:\assets\chair.blend" `
  --out-dir "C:\temp\chair_baked" `
  --bake leather --bake-mode pbr --bake-resolution 2048
```

Omit the material name to bake all eligible mesh-assigned materials:

```powershell
uv --native-tls run materials-processor blender export-usd "C:\assets\chair.blend" `
  --out-dir "C:\temp\chair_baked" --bake --bake-mode pbr
```

PBR mode supports these sources:

- A Principled BSDF directly connected to Material Output.
- A group whose active branch contains a directly connected internal Principled BSDF.
- A group exposing named PBR outputs: `Color Bake` or `Base Color Bake`, plus optional `Metallic Bake` or `Metalness Bake`, `Roughness Bake`, `Opacity Bake` or `Alpha Bake`, and `Emission Color Bake` or `Emission Bake`.

The baked canonical streams are base color, metallic, roughness, tangent-space normal, opacity, and emission color. Missing optional streams are recorded in the report. Mixed closure graphs, such as diffuse/sheen/glossy/translucent mixes, are intentionally not relabelled as PBR. In `pbr` mode they are skipped with a specific reason.

### Beauty bake and automatic fallback

```powershell
uv --native-tls run materials-processor blender export-usd "C:\assets\fabric.blend" `
  --out-dir "C:\temp\fabric_baked" `
  --bake fabric_material --bake-mode auto --bake-resolution 2048
```

`beauty` invokes Blender's `COMBINED` bake on the material's assigned mesh. The resulting `*_beauty.exr` is connected as `emission_color` on `ND_surface_unlit`. This preserves the captured texture appearance without claiming that it can be correctly relit in another renderer.

The report marks each material as `bake_mode: "pbr"` or `bake_mode: "beauty"`. Beauty records also include `pbr_rejection` when `auto` selected the fallback and a `limitation` field explaining the scene-lighting dependency.

### UVs and material assignment

Every bake mode needs an assigned mesh with exactly one material slot. Existing UVs are retained. If an eligible mesh has no UV map, opt in to a temporary Smart UV Project:

```powershell
uv --native-tls run materials-processor blender export-usd "C:\assets\asset.blend" `
  --out-dir "C:\temp\asset_baked" --bake material_name --bake-mode auto --bake-auto-unwrap
```

The report records `generated_uv: true` for such a bake. Review generated UV seams and texel distribution before treating the result as final.

### Bake outputs and color management

The bake directory contains OpenEXR maps and the USD layers:

```text
baked_textures/
  material_base_color.exr
  material_metalness.exr
  material_roughness.exr
  material_normal.exr
  material_beauty.exr
blender_baked_materials_materialx.usda
blender_baked_materials_openpbr.usda
export_report.json
```

Not every material produces every file. PBR color maps are written scene-linear and declared `lin_ap1` by default; scalar and normal maps are declared `raw`. The bake report records Blender's display/view settings and the declared color space. If the intended USD renderer uses a different scene-linear space, set `--bake-color-space <MaterialX-space>` explicitly and validate it with the property workflow below. Normal maps use Blender's evaluated `NORMAL` bake in tangent space, so connected Normal Map and Bump nodes are captured without a display transform. The report identifies this as the tangent-space glTF normal-map contract, and the generated MaterialX graph uses `ND_gltf_normalmap_vector3_1_0`.

## Fidelity validation

Validate the property being transferred, not just a beauty image from two different renderers.

### Albedo

For a PBR bake, compare the Blender Base Color Shader AOV and the MaterialX baked-base-color stage as an unlit render. The Blender reference tool captures the evaluated stream without changing the source material's surface output. Render both to scene-linear EXR and compare the EXRs only after normalizing them to the same OCIO working space. Blender and Karma can both write linear EXRs while using different scene-linear spaces, so unconverted pixel values are not an acceptance criterion. The bake report records the Blender display/view settings and declared MaterialX color space; use `--bake-color-space` only when the target pipeline requires another named space. Do not use display-transformed PNGs or beauty renders as the acceptance criterion: renderer lighting, BSDF implementations, sampling, and display transforms legitimately differ.

```powershell
uv --native-tls run python scripts/render_blender_albedo_grid.py "C:\assets\chair.blend" `
  --output "C:\temp\blender_albedo.exr"
uv --native-tls run python scripts/make_baked_usd_preview_stage.py `
  "C:\temp\chair_baked\blender_baked_materials_materialx.usda" `
  --output "C:\temp\baked_albedo.usda" --albedo-only
```

The preview-stage script creates a Karma-ready stage. Render it with the locally installed Houdini tools, then compare linear output. The script retains the Blender reference camera and resolution for the matching preview route.

### Normals

Use the same property-based approach for normals:

```powershell
uv --native-tls run python scripts/render_blender_albedo_grid.py "C:\assets\chair.blend" `
  --mode normal-vector --output "C:\temp\blender_normals.exr"
uv --native-tls run python scripts/make_baked_usd_preview_stage.py `
  "C:\temp\chair_baked\blender_baked_materials_materialx.usda" `
  --output "C:\temp\baked_normals.usda" --normal-vectors
```

For a directly connected Blender Normal Map node, both diagnostic views show the same raw, encoded tangent-space texture, rather than displaying the renderer-specific shading-space normal. The Blender source is captured through a Shader AOV, so it leaves the original surface graph intact. Treat rendered normal colors as a visual diagnostic only unless both renderers use the same raw transform; the authoritative checks are the raw EXR map and its `ND_gltf_normalmap_vector3_1_0` MaterialX connection. `scripts/render_blender_albedo_grid.py --baked-normal-dir baked_textures` can replace source normal textures for the strict Blender-side comparison.

For a cross-renderer normal-image check, write both diagnostics as EXR, save the Husk image with `--ocio 0`, then apply one common display transform to copies of those EXRs. Do not compare two PNGs written independently by Blender and Husk: their values can be equivalent while their display encoding differs. The checked-in non-flat normal fixture verifies the raw EXR range and MaterialX raw-file connection; its Cycles and Karma XPU EXR samples matched within 0.0005 per channel.

### Beauty fallback

For beauty bakes, compare under the same camera, geometry, UVs, scene lighting, color management, and bake resolution. A beauty fallback is a captured appearance, so a downstream relighting comparison is not meaningful. Inspect the unlit USD texture output for file resolution, seams, color space, and texture resolution; then decide whether the asset needs a more capable native graph translation instead.

### Reproducible CC0 corpus

`scripts/create_polyhaven_bake_corpus.py` builds an opt-in Blender validation scene from ten 1K CC0 Poly Haven texture sets. It covers base color, roughness, normal maps, UV coordinates, Mapping, scalar-channel extraction, and one metallic ARM texture. Third-party textures are downloaded locally and are not repository fixtures.

```powershell
uv --system-certs run python scripts/create_polyhaven_bake_corpus.py `
  --output-dir "C:\temp\polyhaven_bake_corpus" --budget-mib 64
uv --system-certs run materials-processor blender export-usd `
  "C:\temp\polyhaven_bake_corpus\polyhaven_real_world_materials.blend" `
  --out-dir "C:\temp\polyhaven_bake_corpus\baked_usd" `
  --bake all --bake-mode auto --bake-resolution 512 `
  --target materialx --target openpbr
```

The builder queries Poly Haven metadata before downloads and fails if the selected maps exceed the budget. The default corpus was run locally with Blender 4.5 and the 64 MiB limit: all ten materials qualified as direct Principled PBR, none were skipped, and each produced the six canonical streams. Solaris successfully loaded the generated MaterialX and OpenPBR USD layers. Repeat the run when changing bake colour handling, texture nodes, normal handling, or USD material authoring.

For externally authored procedural graphs and non-PBR closures, see the separate [free Blender procedural corpus record](free-procedural-corpus.md). It uses six hash-pinned, MIT-licensed source `.blend` files under a 16 MiB cap. The four procedural Principled materials bake to PBR streams; the two Glass BSDF materials are conservatively emitted as beauty/unlit fallbacks rather than mislabelled as portable PBR.

## Troubleshooting

| Symptom | Check | Likely action |
| --- | --- | --- |
| Blender is not found | Run `materials-processor doctor`; verify the executable path. | Pass `--blender-exe` or set `MATERIALS_PROCESSOR_BLENDER_EXE`. |
| Export times out | Scene load, texture access, and bake resolution. | Increase `--timeout`; test one material at lower resolution first. |
| A material is skipped in PBR mode | `skipped_materials` in the report. | Use named group PBR outputs, simplify to Principled, use native MaterialX, or choose `--bake-mode auto`. |
| Native result is magenta | `native_materialx.suspect_magenta_materials`. | Treat it as a failed native translation; do not publish it as valid. |
| Baked material is black or unexpected | Source mesh assignment, UVs, and Blender scene lights. | Check one-slot assignment and UVs; beauty baking captures the current scene lighting. |
| Texture cannot be found after graph export | `missing_texture_paths`. | Use `--remap-prefix` or `--texture-root`; retry with `--missing-textures error`. |
| Normal looks inverted or weak | Linear normal-vector comparison. | Use the normal diagnostic workflow before changing downstream material settings. |

## Known limits

- The graph converter flattens supported node groups, including Group Input defaults and links from supported outer nodes. An outer source that has no neutral graph mapping remains unsupported and is reported as such.
- PBR baking supports direct or explicitly exposed PBR inputs, not arbitrary mixed closures.
- Beauty baking does not preserve view-dependent effects, transmission depth, geometry-dependent scattering, or relightability.
- Native MaterialX remains Blender-version-dependent and requires downstream renderer validation.
- The USD output is material-only; it does not assemble full asset or shot USD scenes.

## Automated coverage

The test suite creates its Blender bake fixture at runtime, rather than storing a binary `.blend` in the repository. It exercises direct Principled PBR, a non-flat Normal Map PBR material, internal group Principled materials driven by both a Group Input value and a Group Input connection, and a mixed diffuse/translucent group. The integration test asserts that `auto` produces four PBR materials and one beauty fallback, checks the baked normal EXR and raw MaterialX connection, then verifies that Solaris can load the corresponding MaterialX and OpenPBR USD layers. Run it locally with:

```powershell
uv --system-certs run pytest tests/test_blender_bake_integration.py -vv
```

It is marked `blender` and `hython`, and skips cleanly where either DCC runtime is unavailable.

## Recommended production sequence

1. Inspect the source and resolve missing textures.
2. Use graph conversion for a supported, portable graph.
3. For a complex graph, test Blender native MaterialX and inspect for magenta fallback.
4. If portable PBR is needed, use `--bake-mode pbr` and validate albedo and normal streams independently.
5. If the graph is non-PBR and a captured look is acceptable, use `--bake-mode auto` or `beauty`, label it as unlit/lighting-dependent, and validate it in the intended downstream renderer.

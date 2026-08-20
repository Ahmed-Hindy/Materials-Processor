# Free Blender Procedural Corpus Result

This is a reproducibility record for a small third-party procedural-material
corpus. It intentionally contains no downloaded `.blend` files, textures, or
render outputs.

## Source and boundary

- Date: 2026-08-14
- Blender: 4.5.0
- Houdini: 21.0.631
- Source: [Infinitode Material Library](https://github.com/Infinitode/Material-Library)
- License: MIT
- Pinned source revision: `d5982c248b42c32c2cf65f5b5ec542b196ee3483`
- Download boundary: six direct `.blend` files, 12.35 MiB total, with declared
  size and SHA-256 verified before use.
- Bake: `--bake all --bake-mode auto --bake-resolution 256 --bake-auto-unwrap`

The corpus deliberately mixes four procedural Principled materials with two
non-PBR Glass BSDF materials. It therefore tests the decision between portable
PBR streams and the explicitly limited beauty fallback, rather than measuring
only texture-map PBR assets.

## Source files and inspection

| Source file | Material | Blender nodes reported as unsupported by direct conversion | `auto` result |
| --- | --- | --- | --- |
| `deformed-metal-1.blend` | Enchanted Shimmer Metal.005 | ColorRamp, Voronoi Texture | PBR |
| `experimental-1.blend` | Enchanted Radiance Experimental | ColorRamp, Noise Texture | PBR |
| `experimental-17.blend` | Cosmic Spark Experimental | ColorRamp, Noise Texture | PBR |
| `glass-1.blend` | Ethereal Spark Glass | Glass BSDF, ColorRamp | beauty |
| `glass-7.blend` | Dreamy Ember Glass.001 | Glass BSDF, ColorRamp | beauty |
| `metal-1.blend` | Ethereal Ember Metal | ColorRamp, Musgrave Texture | PBR |

Every source file loaded, had one node material assigned to a mesh, and had no
missing texture paths or graph-read failures.

## Results

| Check | Result |
| --- | --- |
| Direct graph inspection | Six graphs read successfully; every graph reported its unsupported procedural nodes. |
| Direct graph USD | The four Principled graphs authored MaterialX/OpenPBR surface shaders, but their unsupported procedural inputs were not represented. The two Glass BSDF graphs authored no surface shader. Direct output is therefore not a faithful delivery path for this corpus. |
| Auto bake | 4 PBR bakes, 2 beauty fallbacks, 0 skipped. |
| PBR streams | 24 canonical EXR maps (six streams for each Principled material). |
| Beauty streams | 2 scene-lit beauty EXRs, attached to `ND_surface_unlit`. |
| Solaris import | All 12 baked target layers loaded: PBR items used `ND_standard_surface_surfaceshader`/`ND_open_pbr_surface_surfaceshader`; Glass items used `ND_surface_unlit`. |

This establishes that a free, externally authored, nontrivial Blender corpus
is classified conservatively and produces loadable downstream material layers.
It does **not** claim that direct conversion preserves the procedural patterns,
nor that a Glass BSDF beauty bake is relightable, transmissive, or
view-dependent in Karma.

## Repeat

Download only the verified, pinned corpus:

```powershell
uv --system-certs run python scripts/download_free_blender_material_corpus.py `
  --output-dir "C:\temp\free_blender_material_corpus" --budget-mib 16
```

Inspect one source, then bake it:

```powershell
uv --system-certs run materials-processor-blender inspect `
  "C:\temp\free_blender_material_corpus\glass-1.blend"
uv --system-certs run materials-processor-blender export-usd `
  "C:\temp\free_blender_material_corpus\glass-1.blend" `
  --out-dir "C:\temp\free_blender_material_corpus\glass-1-baked" `
  --bake all --bake-mode auto --bake-resolution 256 --bake-auto-unwrap `
  --target materialx --target openpbr
```

Use a temporary folder and remove its external source files and generated
outputs after validation.

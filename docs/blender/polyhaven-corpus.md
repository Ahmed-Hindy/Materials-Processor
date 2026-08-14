# Blender Poly Haven Corpus Result

This is a compact reproducibility record for the opt-in CC0 baking corpus. It intentionally contains no downloaded textures or `.blend` files.

## Run

- Date: 2026-08-13
- Blender: 4.5.0
- Houdini: 21.0.631
- Source: ten 1K CC0 Poly Haven texture assets
- Download cap: 64 MiB, checked from API metadata before download
- Bake: `--bake all --bake-mode auto --bake-resolution 512 --target materialx --target openpbr`

## Result

| Check | Result |
| --- | --- |
| Corpus materials | 10 |
| PBR bakes | 10 |
| Beauty fallbacks | 0 |
| Skipped materials | 0 |
| Generated UV maps | 0 |
| Canonical EXR streams | 60 (6 per material) |
| MaterialX USD materials | 10 |
| OpenPBR USD materials | 10 |
| Solaris import | Passed for both target layers |

The assets were Aerial Asphalt 01, Anti Slip Concrete, Blue Metal Plate, Brick Wall 001, Brown Leather, Fabric Pattern 05, Floor Tiles 02, Marble 01, Rocky Terrain 02, and Wood Planks Grey.

## Scope

This confirms that the normal direct-Principled PBR bake path handles real image textures, UV/Mappings, scalar roughness/metalness inputs, and normal maps. It does not establish beauty-bake relightability, fidelity of non-PBR closures, or equivalence of renderer beauty renders. See [the Blender workflow guide](workflow.md#reproducible-cc0-corpus) for repeat commands and property-level validation.

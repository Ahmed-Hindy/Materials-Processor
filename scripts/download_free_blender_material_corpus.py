"""Download a small, hash-pinned corpus of free procedural Blender materials.

The corpus is for manual or CI-adjacent validation only.  It downloads no more
than the configured budget, records the original source metadata, and never
places third-party ``.blend`` files in the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_REPOSITORY = "https://github.com/Infinitode/Material-Library"
SOURCE_LICENSE = "MIT"
SOURCE_REVISION = "d5982c248b42c32c2cf65f5b5ec542b196ee3483"
SOURCE_ROOT = f"https://raw.githubusercontent.com/Infinitode/Material-Library/{SOURCE_REVISION}/blend-files"
USER_AGENT = "MaterialsProcessor/2.0-beta (local free Blender material validation)"
DEFAULT_BUDGET_MIB = 16.0
CORPUS = (
    {
        "filename": "glass-1.blend",
        "family": "glass",
        "expected_bytes": 2_143_112,
        "sha256": "62829D6B7399CC542AC2356C039A1D1BBFEB46908F6EE8A6D539629C020C195D",
    },
    {
        "filename": "glass-7.blend",
        "family": "glass",
        "expected_bytes": 2_143_112,
        "sha256": "EF64BC17D58A558E027A45D0A9006EE73E5DA254CCE1A39621B3B04AD8AC38E8",
    },
    {
        "filename": "experimental-1.blend",
        "family": "experimental",
        "expected_bytes": 2_164_864,
        "sha256": "EBF58FE830B05D6CEB7601B5E36F4D40A97B6EF2B06639E7DE80C7BDDA28C788",
    },
    {
        "filename": "experimental-17.blend",
        "family": "experimental",
        "expected_bytes": 2_164_864,
        "sha256": "C7F422401D6EC5E954F0256CF0749877B047A0F4D0E400CA133CD33D0B534A18",
    },
    {
        "filename": "deformed-metal-1.blend",
        "family": "deformed-metal",
        "expected_bytes": 2_172_800,
        "sha256": "6599015CC0DA9D6069C18A98893DAD1CBBF8D94A1EBF3B721AFAB58608F6689A",
    },
    {
        "filename": "metal-1.blend",
        "family": "metal",
        "expected_bytes": 2_165_200,
        "sha256": "C6EF6DF043F806B37C4799F034E44A63055FB2F729782C898B66CC749F8578B3",
    },
)


def _digest(path: Path) -> str:
    """Return the uppercase SHA-256 digest for ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _verify(path: Path, entry: dict[str, object]) -> bool:
    """Return whether a local corpus file matches its pinned size and digest."""
    return (
        path.is_file()
        and path.stat().st_size == entry["expected_bytes"]
        and _digest(path) == entry["sha256"]
    )


def _download(destination: Path, entry: dict[str, object]) -> None:
    """Download one known-size source file and reject an unexpected response."""
    filename = str(entry["filename"])
    request = Request(f"{SOURCE_ROOT}/{filename}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:  # noqa: S310 - fixed GitHub HTTPS source.
        declared_size = response.headers.get("Content-Length")
        if declared_size and int(declared_size) != entry["expected_bytes"]:
            raise ValueError(f"{filename} declares unexpected size {declared_size}")
        data = response.read(int(entry["expected_bytes"]) + 1)
    if len(data) != entry["expected_bytes"]:
        raise ValueError(f"{filename} downloaded {len(data)} bytes, expected {entry['expected_bytes']}")
    destination.write_bytes(data)
    if not _verify(destination, entry):
        raise ValueError(f"{filename} did not match its pinned SHA-256")


def main() -> int:
    """Download the corpus only after validating the aggregate size budget."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--budget-mib", type=float, default=DEFAULT_BUDGET_MIB)
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    budget = int(args.budget_mib * 1024 * 1024)
    total_bytes = sum(int(entry["expected_bytes"]) for entry in CORPUS)
    if total_bytes > budget:
        raise ValueError(
            f"Corpus requires {total_bytes / 1024 / 1024:.2f} MiB, above the "
            f"{args.budget_mib:.2f} MiB safety budget."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict[str, object]] = []
    for entry in CORPUS:
        destination = output_dir / str(entry["filename"])
        if not _verify(destination, entry):
            _download(destination, entry)
        manifest_entries.append({**entry, "path": str(destination), "url": f"{SOURCE_ROOT}/{entry['filename']}"})

    manifest = {
        "source_repository": SOURCE_REPOSITORY,
        "source_license": SOURCE_LICENSE,
        "source_revision": SOURCE_REVISION,
        "total_expected_bytes": total_bytes,
        "entries": manifest_entries,
    }
    (output_dir / "free_blender_material_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Downloaded {len(CORPUS)} verified materials ({total_bytes / 1024 / 1024:.2f} MiB) to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

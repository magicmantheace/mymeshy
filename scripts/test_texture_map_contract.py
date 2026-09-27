"""GPU-free contract test for every texture-map name the pipeline can publish."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import store  # noqa: E402
from app.config import get_settings  # noqa: E402

EXPECTED = {
    "albedo",
    "normal",
    "roughness",
    "metallic",
    "ao",
    "metallic_roughness",
    "occlusion",
}


def main() -> None:
    assert set(store.TEXTURE_MAPS) == EXPECTED

    previous_data_dir = os.environ.get("MYMESHY_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="assetforge-texture-contract-") as td:
            os.environ["MYMESHY_DATA_DIR"] = td
            get_settings.cache_clear()
            asset_id, asset_path = store.new_asset("texture contract")
            for name in EXPECTED:
                (asset_path / "textures" / f"{name}.png").write_bytes(b"png-placeholder")

            discovered = set(store.texture_names(asset_id))
            assert discovered == EXPECTED

            # /api/assets/{id}/textures/{map_name}.png uses this same allowlist,
            # so membership here is the backend endpoint contract.
            assert "metallic_roughness" in store.TEXTURE_MAPS
            assert "occlusion" in store.TEXTURE_MAPS
    finally:
        if previous_data_dir is None:
            os.environ.pop("MYMESHY_DATA_DIR", None)
        else:
            os.environ["MYMESHY_DATA_DIR"] = previous_data_dir
        get_settings.cache_clear()

    print("PASS: fallback and native PBR texture maps share one API allowlist")


if __name__ == "__main__":
    main()

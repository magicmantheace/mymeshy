"""GPU-free round-trip test for durable generation checkpoints."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline.base import GenOptions, MeshResult  # noqa: E402
from app.pipeline.checkpoint import load_generation_checkpoint, save_generation_checkpoint  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetforge-checkpoint-") as td:
        root = Path(td)
        mesh = trimesh.creation.box()
        image = Image.new("RGB", (32, 16), (20, 40, 60))
        result = MeshResult(
            mesh=mesh,
            albedo=image,
            textured=True,
            extras={"path": Path("worker/result.glb"), "score": np.float32(0.5)},
        )
        opts = GenOptions(target_polycount=1234, texture_size=512)
        save_generation_checkpoint(root, result, opts, {"name": "checkpoint test"})

        loaded, loaded_opts, meta = load_generation_checkpoint(root)
        assert len(loaded.faces) == len(mesh.faces)
        assert loaded.albedo is not None and loaded.albedo.size == image.size
        assert loaded.textured
        assert loaded.extras["path"] == "worker/result.glb"
        assert loaded.extras["score"] == 0.5
        assert loaded_opts.target_polycount == 1234
        assert loaded_opts.texture_size == 512
        assert meta["name"] == "checkpoint test"

    print("PASS: generation checkpoint round-trip is valid")


if __name__ == "__main__":
    main()

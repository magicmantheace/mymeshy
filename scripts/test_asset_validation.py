"""GPU-free checks for the finished-asset validation gate."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import trimesh
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline.validation import validate_finished_asset  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetforge-validation-") as td:
        root = Path(td)
        (root / "textures").mkdir()
        mesh = trimesh.creation.box()
        mesh.visual = trimesh.visual.TextureVisuals(
            uv=[[0.0, 0.0]] * len(mesh.vertices)
        )
        Image.new("RGB", (32, 16)).save(root / "textures" / "albedo.png")
        mesh.export(root / "model.glb")
        report = validate_finished_asset(mesh, root, ["albedo"])
        assert report["passed"]
        assert report["triangles"] == len(mesh.faces)
        assert report["texture_sizes"]["albedo"] == [32, 16]
        assert report["exported_geometry"]["triangles"] > 0
        assert report["exported_geometry"]["meshes"] >= 1

        (root / "model.glb").write_bytes(b"not a glb but definitely longer than twenty bytes")
        try:
            validate_finished_asset(mesh, root, ["albedo"])
        except ValueError as exc:
            assert "could not be reloaded" in str(exc) or "no triangle geometry" in str(exc)
        else:
            raise AssertionError("corrupt GLB was not rejected")

        (root / "model.glb").unlink()
        try:
            validate_finished_asset(mesh, root, ["albedo"])
        except ValueError as exc:
            assert "model.glb" in str(exc)
        else:
            raise AssertionError("missing GLB was not rejected")

    print("PASS: finished-asset validation rejects structurally unusable output")


if __name__ == "__main__":
    main()

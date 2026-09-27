"""Deterministic validation for finished AssetForge assets."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


def validate_finished_asset(mesh: trimesh.Trimesh, asset_path: Path, textures: list[str]) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if len(mesh.vertices) < 3 or len(mesh.faces) < 1:
        errors.append("mesh has no usable triangles")
    if not np.isfinite(np.asarray(mesh.vertices)).all():
        errors.append("mesh contains non-finite vertex coordinates")
    faces = np.asarray(mesh.faces)
    if faces.size and (faces.min() < 0 or faces.max() >= len(mesh.vertices)):
        errors.append("mesh contains out-of-range face indices")

    uvs = getattr(getattr(mesh, "visual", None), "uv", None)
    if uvs is None:
        errors.append("mesh has no UV coordinates")
    else:
        uv = np.asarray(uvs)
        if len(uv) != len(mesh.vertices):
            errors.append("UV count does not match vertex count")
        elif not np.isfinite(uv).all():
            errors.append("UV coordinates contain non-finite values")
        elif ((uv < -0.01) | (uv > 1.01)).any():
            warnings.append("UV coordinates extend outside the 0..1 tile")

    tex_dir = asset_path / "textures"
    texture_sizes: dict[str, list[int]] = {}
    for name in textures:
        path = tex_dir / f"{name}.png"
        if not path.is_file():
            errors.append(f"missing texture: {name}.png")
            continue
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                texture_sizes[name] = [image.width, image.height]
                if image.width <= 0 or image.height <= 0:
                    errors.append(f"invalid texture dimensions: {name}.png")
        except Exception as exc:
            errors.append(f"invalid texture {name}.png: {exc}")

    model = asset_path / "model.glb"
    exported_geometry = None
    if not model.is_file() or model.stat().st_size < 20:
        errors.append("model.glb was not exported or is empty")
    else:
        try:
            loaded = trimesh.load(model, force="scene")
            geometries = list(loaded.geometry.values()) if isinstance(loaded, trimesh.Scene) else [loaded]
            valid = [g for g in geometries if isinstance(g, trimesh.Trimesh) and len(g.faces) > 0]
            if not valid:
                errors.append("exported model.glb contains no triangle geometry")
            elif not all(np.isfinite(np.asarray(g.vertices)).all() for g in valid):
                errors.append("exported model.glb contains non-finite vertex coordinates")
            else:
                exported_geometry = {
                    "meshes": len(valid),
                    "vertices": int(sum(len(g.vertices) for g in valid)),
                    "triangles": int(sum(len(g.faces) for g in valid)),
                }
        except Exception as exc:
            errors.append(f"exported model.glb could not be reloaded: {exc}")

    report = {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.faces)),
        "texture_sizes": texture_sizes,
        "exported_geometry": exported_geometry,
    }
    if errors:
        raise ValueError("asset validation failed: " + "; ".join(errors))
    return report

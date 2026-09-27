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
    areas = np.asarray(mesh.area_faces)
    if areas.size and (not np.isfinite(areas).all() or (areas <= 1e-12).any()):
        errors.append("mesh contains degenerate or non-finite triangle areas")
    normals = np.asarray(mesh.face_normals)
    if normals.size and not np.isfinite(normals).all():
        errors.append("mesh contains non-finite face normals")
    components = mesh.split(only_watertight=False)
    if len(components) > 1:
        warnings.append(f"mesh contains {len(components)} disconnected components")
    if not mesh.is_watertight:
        warnings.append("mesh is not watertight")
    extents = np.asarray(mesh.bounding_box.extents)
    if not np.isfinite(extents).all() or (extents <= 1e-9).any():
        errors.append("mesh has a collapsed or invalid bounding box")

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
    if not model.is_file() or model.stat().st_size < 20:
        errors.append("model.glb was not exported or is empty")

    report = {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.faces)),
        "components": int(len(components)),
        "watertight": bool(mesh.is_watertight),
        "bounds_extents": [float(v) for v in extents],
        "texture_sizes": texture_sizes,
    }
    if errors:
        raise ValueError("asset validation failed: " + "; ".join(errors))
    return report

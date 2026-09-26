"""Durable generation checkpoints used to resume post-processing without rerunning AI models."""
from __future__ import annotations

import json
from pathlib import Path

import trimesh
from PIL import Image

from .base import GenOptions, MeshResult

CHECKPOINT_FILE = "generation_checkpoint.json"
RAW_MESH_FILE = "source/generated_raw.glb"
RAW_ALBEDO_FILE = "source/generated_albedo.png"


def save_generation_checkpoint(
    asset_path: Path, result: MeshResult, opts: GenOptions, meta: dict
) -> None:
    """Persist the expensive model output before CPU/post-processing stages."""
    mesh_path = asset_path / RAW_MESH_FILE
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    result.mesh.export(mesh_path)

    albedo_path = None
    if result.albedo is not None:
        albedo_path = asset_path / RAW_ALBEDO_FILE
        result.albedo.convert("RGB").save(albedo_path)

    payload = {
        "version": 1,
        "mesh": RAW_MESH_FILE,
        "albedo": RAW_ALBEDO_FILE if albedo_path else None,
        "textured": bool(result.textured),
        "extras": result.extras,
        "options": opts.__dict__,
        "meta": meta,
    }
    (asset_path / CHECKPOINT_FILE).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_generation_checkpoint(asset_path: Path) -> tuple[MeshResult, GenOptions, dict]:
    """Load a generation checkpoint and validate its required artifacts."""
    checkpoint = asset_path / CHECKPOINT_FILE
    if not checkpoint.is_file():
        raise FileNotFoundError("generation checkpoint not found")
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError(f"unsupported generation checkpoint version: {payload.get('version')}")

    mesh_path = asset_path / payload["mesh"]
    if not mesh_path.is_file():
        raise FileNotFoundError(f"checkpoint mesh is missing: {mesh_path.name}")
    mesh = trimesh.load(mesh_path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError("checkpoint does not contain a valid triangle mesh")

    albedo = None
    if payload.get("albedo"):
        albedo_path = asset_path / payload["albedo"]
        if not albedo_path.is_file():
            raise FileNotFoundError(f"checkpoint albedo is missing: {albedo_path.name}")
        with Image.open(albedo_path) as image:
            albedo = image.convert("RGB").copy()

    result = MeshResult(
        mesh=mesh,
        albedo=albedo,
        textured=bool(payload.get("textured")) and albedo is not None,
        extras=payload.get("extras") or {},
    )
    return result, GenOptions.from_dict(payload.get("options")), dict(payload.get("meta") or {})

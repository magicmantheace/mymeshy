"""Short-lived TripoSR GPU worker.

This module intentionally avoids importing the parent adapter registry. It can
run under its own virtual environment as long as the worker dependencies and
the TripoSR repository are available on PYTHONPATH.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


def _install_torchmcubes_shim() -> None:
    if importlib.util.find_spec("torchmcubes") is not None:
        return

    import types

    import numpy as np
    import torch
    from skimage import measure

    def marching_cubes(vol, thresh=0.0):
        values = vol.detach().cpu().numpy()
        verts, faces, _normals, _vals = measure.marching_cubes(
            values, level=float(thresh)
        )
        verts = np.ascontiguousarray(verts[:, ::-1])
        return (
            torch.from_numpy(verts.astype(np.float32)),
            torch.from_numpy(faces.astype(np.int64)),
        )

    shim = types.ModuleType("torchmcubes")
    shim.marching_cubes = marching_cubes
    sys.modules["torchmcubes"] = shim


def _probe() -> tuple[bool, str]:
    try:
        import torch
    except ImportError:
        return False, "PyTorch is not installed in the TripoSR worker environment"
    if not torch.cuda.is_available():
        return False, "CUDA is not available in the TripoSR worker environment"
    if importlib.util.find_spec("tsr") is None:
        return False, "TripoSR (tsr) is not importable in the worker environment"
    return True, ""


def _apply_hard_cap(hard_cap_gb: float) -> None:
    if hard_cap_gb <= 0:
        return
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    import torch

    total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    allocator_gb = max(min(hard_cap_gb, total_gb) - 0.9, 1.0)
    torch.cuda.set_per_process_memory_fraction(
        min(allocator_gb / total_gb, 1.0), 0
    )


def _run(request_path: Path, result_path: Path) -> None:
    import numpy as np
    import torch
    import trimesh
    from PIL import Image

    ok, reason = _probe()
    if not ok:
        raise RuntimeError(reason)

    request = json.loads(request_path.read_text(encoding="utf-8"))
    _apply_hard_cap(float(request.get("hard_cap_gb") or 0))

    _install_torchmcubes_shim()
    from tsr.system import TSR

    model = TSR.from_pretrained(
        "stabilityai/TripoSR",
        config_name="config.yaml",
        weight_name="model.ckpt",
    )
    model.renderer.set_chunk_size(int(request["chunk_size"]))
    model.to("cuda")

    image = Image.open(request["images"][0]).convert("RGB")
    seed = request.get("seed")
    if seed is not None:
        torch.manual_seed(int(seed))
        torch.cuda.manual_seed_all(int(seed))

    with torch.no_grad():
        scene_codes = model([image], device="cuda")
        meshes = model.extract_mesh(
            scene_codes,
            has_vertex_color=True,
            resolution=int(request["resolution"]),
        )

    generated = meshes[0]
    raw_colors = None
    visual = getattr(generated, "visual", None)
    if visual is not None and hasattr(visual, "vertex_colors"):
        raw_colors = np.asarray(visual.vertex_colors)
    elif hasattr(generated, "vertex_colors"):
        raw_colors = np.asarray(generated.vertex_colors)

    mesh = trimesh.Trimesh(
        vertices=np.asarray(generated.vertices),
        faces=np.asarray(generated.faces),
        vertex_colors=(
            np.clip(raw_colors, 0, 255).astype(np.uint8)
            if raw_colors is not None
            else None
        ),
        process=True,
    )
    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
    )

    output_mesh = Path(request["output_mesh"])
    output_mesh.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(output_mesh)

    result_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "pid": os.getpid(),
                "mesh_path": str(output_mesh),
                "vertices": int(len(mesh.vertices)),
                "triangles": int(len(mesh.faces)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--request")
    parser.add_argument("--result")
    args = parser.parse_args()

    if args.probe:
        ok, reason = _probe()
        if ok:
            print(json.dumps({"status": "ok", "worker": "triposr"}))
            return 0
        print(reason, file=sys.stderr)
        return 1

    if not args.request or not args.result:
        parser.error("--request and --result are required unless --probe is used")

    result_path = Path(args.result)
    try:
        _run(Path(args.request), result_path)
        return 0
    except Exception as exc:
        try:
            result_path.write_text(
                json.dumps(
                    {
                        "status": "error",
                        "pid": os.getpid(),
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Short-lived Hunyuan3D shape-generation worker.

The process owns the shape model and exits after exporting an intermediate GLB,
so Hunyuan Paint can start later with a fresh CUDA context.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


def _probe() -> tuple[bool, str]:
    try:
        import torch
    except ImportError:
        return False, "PyTorch is not installed in the Hunyuan shape worker environment"
    if not torch.cuda.is_available():
        return False, "CUDA is not available in the Hunyuan shape worker environment"
    if importlib.util.find_spec("hy3dgen") is None:
        return False, "hy3dgen is not importable in the Hunyuan shape worker environment"
    return True, ""


def _configure_cuda(hard_cap_gb: float) -> None:
    if hard_cap_gb > 0:
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    if hard_cap_gb <= 0:
        return
    total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    allocator_gb = max(min(hard_cap_gb, total_gb) - 0.9, 1.0)
    torch.cuda.set_per_process_memory_fraction(min(allocator_gb / total_gb, 1.0), 0)


def _run(request_path: Path, result_path: Path) -> None:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    _configure_cuda(float(request.get("hard_cap_gb") or 0))

    import torch
    import trimesh
    from PIL import Image
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    model_name = request["shape_model"]
    subfolder = request["shape_subfolder"]
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        model_name, subfolder=subfolder
    )
    if request.get("low_vram"):
        try:
            pipeline.enable_flashvdm(mc_algo="mc")
        except Exception:
            pass

    image = Image.open(request["image"]).convert("RGBA")
    seed = request.get("seed")
    generator = torch.Generator().manual_seed(int(seed)) if seed is not None else None
    kwargs = {}
    if request.get("low_vram"):
        kwargs = {"octree_resolution": 256, "num_chunks": 4000}

    generated = pipeline(image=image, generator=generator, **kwargs)[0]
    if isinstance(generated, trimesh.Trimesh):
        mesh = generated
    else:
        vertices = getattr(generated, "vertices", getattr(generated, "mesh_v", None))
        faces = getattr(generated, "faces", getattr(generated, "mesh_f", None))
        if vertices is None or faces is None:
            raise RuntimeError(f"unsupported Hunyuan mesh type: {type(generated).__name__}")
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)

    try:
        from hy3dgen.shapegen import DegenerateFaceRemover, FaceReducer, FloaterRemover

        mesh = FloaterRemover()(mesh)
        mesh = DegenerateFaceRemover()(mesh)
        mesh = FaceReducer()(
            mesh,
            max_facenum=max(int(request.get("target_polycount") or 30000), 40000),
        )
    except Exception:
        pass

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
                "model": model_name,
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
            print(json.dumps({"status": "ok", "worker": "hunyuan_shape"}))
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

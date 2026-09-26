"""Short-lived Hunyuan3D Paint worker.

Consumes an intermediate mesh and reference image, writes a textured GLB plus
an explicit albedo image, then exits so all paint-model CUDA state disappears.
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
        return False, "PyTorch is not installed in the Hunyuan paint worker environment"
    if not torch.cuda.is_available():
        return False, "CUDA is not available in the Hunyuan paint worker environment"
    if importlib.util.find_spec("hy3dgen") is None:
        return False, "hy3dgen is not importable in the Hunyuan paint worker environment"
    if importlib.util.find_spec("custom_rasterizer") is None:
        return False, "custom_rasterizer is not compiled in the Hunyuan paint worker environment"
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

    import trimesh
    from PIL import Image
    from hy3dgen.texgen import Hunyuan3DPaintPipeline

    loaded = trimesh.load(request["mesh"], force="mesh")
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise RuntimeError("input does not contain a valid triangle mesh")

    image = Image.open(request["image"]).convert("RGBA")
    model_name = request["paint_model"]
    pipeline = Hunyuan3DPaintPipeline.from_pretrained(model_name)
    painted = pipeline(loaded, image=image)

    if not isinstance(painted, trimesh.Trimesh):
        raise RuntimeError(f"unsupported painted mesh type: {type(painted).__name__}")

    output_mesh = Path(request["output_mesh"])
    output_mesh.parent.mkdir(parents=True, exist_ok=True)
    painted.export(output_mesh)

    albedo_path = output_mesh.with_name("albedo.png")
    material = getattr(getattr(painted, "visual", None), "material", None)
    albedo = None
    if material is not None:
        albedo = getattr(material, "baseColorTexture", None)
        if albedo is None:
            albedo = getattr(material, "image", None)
    if albedo is not None:
        if not isinstance(albedo, Image.Image):
            albedo = Image.fromarray(albedo)
        albedo.convert("RGB").save(albedo_path)

    result_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "pid": os.getpid(),
                "mesh_path": str(output_mesh),
                "albedo_path": str(albedo_path) if albedo_path.is_file() else None,
                "vertices": int(len(painted.vertices)),
                "triangles": int(len(painted.faces)),
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
            print(json.dumps({"status": "ok", "worker": "hunyuan_paint"}))
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

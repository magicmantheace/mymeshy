"""Tencent Hunyuan3D-2 adapters: shape generation + texture painting.

On the RTX 3060 reference profile, Shape and Paint run in separate short-lived
worker processes so they never share a CUDA context or dependency lifetime.
The original in-process implementation remains available when isolation is
disabled.
"""
from __future__ import annotations

import importlib.util
import os
from typing import Optional, Sequence

import trimesh
from PIL import Image

from ..base import (
    GenOptions,
    ImageTo3DAdapter,
    MeshResult,
    ProgressFn,
    TexturingAdapter,
    _torch_cuda_probe,
    apply_vram_budget,
    free_cuda_memory,
    low_vram,
    should_unload_between_stages,
)

# Overridable for the bigger model: tencent/Hunyuan3D-2
SHAPE_MODEL = os.environ.get("MYMESHY_HUNYUAN_SHAPE_MODEL", "tencent/Hunyuan3D-2mini")
PAINT_MODEL = os.environ.get("MYMESHY_HUNYUAN_PAINT_MODEL", "tencent/Hunyuan3D-2")

# Each HF repo nests its DiT weights in a differently named subfolder.
_SHAPE_SUBFOLDERS = {
    "Hunyuan3D-2": "hunyuan3d-dit-v2-0",
    "Hunyuan3D-2mini": "hunyuan3d-dit-v2-mini",
    "Hunyuan3D-2mv": "hunyuan3d-dit-v2-mv",
}
SHAPE_SUBFOLDER = os.environ.get(
    "MYMESHY_HUNYUAN_SHAPE_SUBFOLDER",
    _SHAPE_SUBFOLDERS.get(SHAPE_MODEL.split("/")[-1], "hunyuan3d-dit-v2-0"),
)


def _hy3dgen_probe() -> tuple[bool, str]:
    ok, reason = _torch_cuda_probe()
    if not ok:
        return False, reason
    if importlib.util.find_spec("hy3dgen") is None:
        return False, "hy3dgen not installed (see README: Installing real models)"
    return True, ""


def _paint_available() -> tuple[bool, str]:
    """In-process paint availability check."""
    if importlib.util.find_spec("custom_rasterizer") is None:
        return False, "custom_rasterizer not compiled (needs CUDA toolkit; see README)"
    if low_vram():
        return False, "paint pipeline does not fit the configured VRAM budget (needs ~10-12GB)"
    return True, ""


def _isolated_enabled() -> bool:
    from ...workers.launch import isolated_workers_enabled

    return isolated_workers_enabled()


class Hunyuan3DImageTo3D(ImageTo3DAdapter):
    name = "hunyuan3d"
    description = "Tencent Hunyuan3D-2 (isolated shape + paint on RTX 3060)"

    def __init__(self) -> None:
        self._shape = None
        self._paint = None

    def probe(self) -> tuple[bool, str]:
        if _isolated_enabled():
            from ...workers.launch import probe_worker

            return probe_worker("hunyuan_shape")
        return _hy3dgen_probe()

    def _load_shape(self, progress: ProgressFn):
        if self._shape is None:
            from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

            apply_vram_budget()
            progress(0.02, f"Loading Hunyuan3D shape model ({SHAPE_MODEL})")
            self._shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
                SHAPE_MODEL, subfolder=SHAPE_SUBFOLDER
            )
            if low_vram():
                try:
                    self._shape.enable_flashvdm(mc_algo="mc")
                except Exception:
                    pass
        return self._shape

    def _load_paint(self, progress: ProgressFn):
        if self._paint is None:
            from hy3dgen.texgen import Hunyuan3DPaintPipeline

            apply_vram_budget()
            progress(0.5, f"Loading Hunyuan3D paint model ({PAINT_MODEL})")
            self._paint = Hunyuan3DPaintPipeline.from_pretrained(PAINT_MODEL)
        return self._paint

    def _unload_shape(self) -> None:
        self._shape = None
        free_cuda_memory()

    def generate(
        self, images: Sequence[Image.Image], opts: GenOptions, progress: ProgressFn
    ) -> MeshResult:
        image = images[0].convert("RGBA")

        if _isolated_enabled():
            from ...workers.launch import (
                probe_worker,
                run_hunyuan_paint_worker,
                run_hunyuan_shape_worker,
            )

            shape = run_hunyuan_shape_worker(
                images,
                opts,
                lambda p, m: progress(p * 0.58, m),
            )
            paint_ok, paint_reason = probe_worker("hunyuan_paint")
            if not paint_ok:
                progress(1.0, f"Shape ready (paint worker unavailable: {paint_reason})")
                return shape

            painted = run_hunyuan_paint_worker(
                shape.mesh,
                image,
                opts,
                lambda p, m: progress(0.58 + p * 0.42, m),
            )
            painted.extras["shape_worker_pid"] = shape.extras.get("worker_pid")
            painted.extras["shape_model"] = shape.extras.get("shape_model")
            return painted

        import torch

        shape = self._load_shape(progress)
        progress(0.1, "Generating shape (flow-matching diffusion)")
        generator = (
            torch.Generator().manual_seed(opts.seed) if opts.seed is not None else None
        )
        kwargs = {}
        if low_vram():
            kwargs = {"octree_resolution": 256, "num_chunks": 4000}
        mesh = shape(image=image, generator=generator, **kwargs)[0]
        if not isinstance(mesh, trimesh.Trimesh):
            mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=True)

        try:
            from hy3dgen.shapegen import FaceReducer, FloaterRemover, DegenerateFaceRemover

            progress(0.4, "Hunyuan mesh cleanup")
            mesh = FloaterRemover()(mesh)
            mesh = DegenerateFaceRemover()(mesh)
            mesh = FaceReducer()(mesh, max_facenum=max(opts.target_polycount, 40000))
        except Exception:
            pass

        paint_ok, paint_reason = _paint_available()
        if not paint_ok:
            progress(1.0, f"Shape ready (paint skipped: {paint_reason})")
            return MeshResult(mesh=mesh, textured=False)

        if should_unload_between_stages():
            del shape
            self._unload_shape()

        paint = self._load_paint(progress)
        progress(0.6, "Painting texture from reference image")
        mesh = paint(mesh, image=image)

        albedo = None
        material = getattr(getattr(mesh, "visual", None), "material", None)
        if material is not None:
            albedo = getattr(material, "baseColorTexture", None)
            if albedo is None:
                albedo = getattr(material, "image", None)
        progress(1.0, "Hunyuan3D mesh ready")
        return MeshResult(mesh=mesh, albedo=albedo, textured=albedo is not None)

    def unload(self) -> None:
        # Isolated workers already exited; these fields only matter for the
        # explicitly selected in-process fallback.
        self._shape = None
        self._paint = None
        free_cuda_memory()


class HunyuanPaintTexturing(TexturingAdapter):
    name = "hunyuan_paint"
    description = "Hunyuan3D-2 paint pipeline (isolated worker on RTX 3060)"

    def __init__(self) -> None:
        self._paint = None
        self._t2i = None

    def probe(self) -> tuple[bool, str]:
        if _isolated_enabled():
            from ...workers.launch import probe_worker

            return probe_worker("hunyuan_paint")
        ok, reason = _hy3dgen_probe()
        if not ok:
            return False, reason
        return _paint_available()

    def generate(
        self,
        mesh: trimesh.Trimesh,
        prompt: Optional[str],
        image: Optional[Image.Image],
        opts: GenOptions,
        progress: ProgressFn,
    ) -> MeshResult:
        if image is None:
            if not prompt:
                raise ValueError("Texturing needs a prompt or a reference image")
            from .sdxl_turbo import SdxlTurboTextToImage

            if self._t2i is None:
                self._t2i = SdxlTurboTextToImage()
            ok, reason = self._t2i.probe()
            if not ok:
                raise RuntimeError(f"Text-conditioned texturing needs SDXL-Turbo: {reason}")
            image = self._t2i.generate(prompt, opts, lambda p, m: progress(p * 0.3, m))
            if should_unload_between_stages():
                self._t2i.unload()

        if _isolated_enabled():
            from ...workers.launch import run_hunyuan_paint_worker

            return run_hunyuan_paint_worker(mesh, image, opts, progress)

        if self._paint is None:
            from hy3dgen.texgen import Hunyuan3DPaintPipeline

            apply_vram_budget()
            progress(0.35, f"Loading Hunyuan3D paint model ({PAINT_MODEL})")
            self._paint = Hunyuan3DPaintPipeline.from_pretrained(PAINT_MODEL)

        progress(0.5, "Painting texture")
        painted = self._paint(mesh, image=image.convert("RGBA"))
        albedo = None
        material = getattr(getattr(painted, "visual", None), "material", None)
        if material is not None:
            albedo = getattr(material, "baseColorTexture", None)
            if albedo is None:
                albedo = getattr(material, "image", None)
        progress(1.0, "Texture ready")
        return MeshResult(mesh=painted, albedo=albedo, textured=albedo is not None)

    def unload(self) -> None:
        self._paint = None
        self._t2i = None
        free_cuda_memory()

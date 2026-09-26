"""Legacy Microsoft TRELLIS image-to-3D adapter.

This in-process Python backend is experimental on the RTX 3060 12 GB reference
profile and is never auto-selected there. It remains available for explicit
opt-in on installations that satisfy its runtime requirements. See
``docs/TRELLIS2_RTX3060.md`` for the separate TRELLIS.2 validation plan.
"""
from __future__ import annotations

import importlib.util
from typing import Sequence

import trimesh
from PIL import Image

from ..base import GenOptions, ImageTo3DAdapter, MeshResult, ProgressFn, _torch_cuda_probe

MODEL_ID = "microsoft/TRELLIS-image-large"


class TrellisImageTo3D(ImageTo3DAdapter):
    name = "trellis"
    description = "Legacy Microsoft TRELLIS image-large (experimental; explicit opt-in on RTX 3060 12GB)"

    def __init__(self) -> None:
        self._pipe = None

    def probe(self) -> tuple[bool, str]:
        ok, reason = _torch_cuda_probe()
        if not ok:
            return False, reason
        if importlib.util.find_spec("trellis") is None:
            return False, "TRELLIS repo not installed (see README: Installing real models)"
        return True, ""

    def _load(self, progress: ProgressFn):
        if self._pipe is None:
            from trellis.pipelines import TrellisImageTo3DPipeline

            progress(0.02, "Loading TRELLIS (first run downloads several GB)")
            self._pipe = TrellisImageTo3DPipeline.from_pretrained(MODEL_ID)
            self._pipe.cuda()
        return self._pipe

    def generate(
        self, images: Sequence[Image.Image], opts: GenOptions, progress: ProgressFn
    ) -> MeshResult:
        import torch

        pipe = self._load(progress)
        progress(0.15, "Running TRELLIS sparse-structure + SLAT sampling")
        seed = opts.seed if opts.seed is not None else int(torch.seed() % 2**31)

        imgs = [im.convert("RGBA") for im in images]
        kwargs = dict(
            seed=seed,
            sparse_structure_sampler_params={"steps": 12, "cfg_strength": 7.5},
            slat_sampler_params={"steps": 12, "cfg_strength": 3.0},
            formats=["gaussian", "mesh"],
        )
        if len(imgs) > 1:
            outputs = pipe.run_multi_image(imgs, **kwargs)
        else:
            outputs = pipe.run(imgs[0], **kwargs)

        progress(0.7, "Baking gaussian appearance onto mesh (GLB extraction)")
        from trellis.utils import postprocessing_utils

        glb = postprocessing_utils.to_glb(
            outputs["gaussian"][0],
            outputs["mesh"][0],
            simplify=0.0,  # our own pipeline handles decimation
            texture_size=opts.texture_size,
        )
        # to_glb returns a trimesh.Trimesh with TextureVisuals
        mesh = glb if isinstance(glb, trimesh.Trimesh) else glb.dump(concatenate=True)
        albedo = None
        visual = getattr(mesh, "visual", None)
        material = getattr(visual, "material", None)
        if material is not None:
            albedo = getattr(material, "baseColorTexture", None) or getattr(material, "image", None)
        progress(1.0, "TRELLIS mesh ready")
        return MeshResult(mesh=mesh, albedo=albedo, textured=albedo is not None)

    def unload(self) -> None:
        if self._pipe is not None:
            self._pipe = None
            import torch

            torch.cuda.empty_cache()

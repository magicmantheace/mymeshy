"""Adapter interfaces for the generation pipeline.

Every AI model is wrapped in an adapter with a uniform interface so models can
be swapped or upgraded independently:

* ``TextToImageAdapter``  — prompt -> reference image (stage 1 of text-to-3D)
* ``ImageTo3DAdapter``    — image(s) -> raw 3D mesh (possibly textured)
* ``TexturingAdapter``    — mesh + prompt/image -> textured mesh

Adapters declare availability via :meth:`probe` so the registry can fall back
gracefully (e.g. to the mock pipeline when no GPU stack is installed) and the
UI can show what is installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import trimesh
from PIL import Image

# progress(fraction_0_to_1, message)
ProgressFn = Callable[[float, str], None]


@dataclass
class GenOptions:
    adapter: Optional[str] = None
    target_polycount: int = 30000
    texture_size: int = 1024
    generate_pbr: bool = True
    seed: Optional[int] = None
    # Skip decimation when the raw mesh is already below target.
    decimate: bool = True

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "GenOptions":
        d = d or {}
        known = {f for f in cls.__dataclass_fields__}  # noqa: F841
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__ and v is not None})


@dataclass
class MeshResult:
    """Raw output of an image-to-3D adapter, before post-processing."""
    mesh: trimesh.Trimesh
    # Albedo texture if the model produced one (mesh.visual should reference it
    # too, but keeping an explicit handle survives processing steps).
    albedo: Optional[Image.Image] = None
    # True if mesh.visual has usable UVs + texture already.
    textured: bool = False
    extras: dict = field(default_factory=dict)


class Adapter:
    name: str = "base"
    description: str = ""

    def probe(self) -> tuple[bool, str]:
        """Return (available, reason). Must be cheap — no model loading."""
        raise NotImplementedError

    def unload(self) -> None:
        """Free GPU memory if the adapter keeps a loaded model."""


class TextToImageAdapter(Adapter):
    def generate(self, prompt: str, opts: GenOptions, progress: ProgressFn) -> Image.Image:
        raise NotImplementedError


class ImageTo3DAdapter(Adapter):
    def generate(
        self, images: Sequence[Image.Image], opts: GenOptions, progress: ProgressFn
    ) -> MeshResult:
        raise NotImplementedError


class TexturingAdapter(Adapter):
    def generate(
        self,
        mesh: trimesh.Trimesh,
        prompt: Optional[str],
        image: Optional[Image.Image],
        opts: GenOptions,
        progress: ProgressFn,
    ) -> MeshResult:
        raise NotImplementedError


def _torch_cuda_probe() -> tuple[bool, str]:
    """Shared helper: is a CUDA-enabled torch importable?"""
    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "PyTorch not installed (see requirements-ml.txt)"
    import torch
    if not torch.cuda.is_available():
        return False, "PyTorch installed but CUDA is not available"
    return True, ""


# --------------------------------------------------------------------------
# VRAM and hardware policy
# --------------------------------------------------------------------------

def vram_budget_gb() -> float:
    """Configured hard allocator budget (0 = no explicit hard cap)."""
    from ..config import get_settings

    return float(get_settings().vram_budget_gb or 0)


def runtime_vram_gb() -> float:
    """Effective VRAM for scheduling decisions.

    An explicit allocator budget can reduce usable VRAM but can never make a
    physical GPU larger. Without a hard cap, scheduling uses physical VRAM
    reported by nvidia-smi. Detection never changes torch's allocator by itself.
    """
    configured = vram_budget_gb()

    from ..config import detect_gpu

    gpu = detect_gpu()
    physical = float(gpu["vram_mb"]) / 1024.0 if gpu else 0.0
    if configured > 0 and physical > 0:
        return min(configured, physical)
    if configured > 0:
        return configured
    return physical


def hardware_profile_name() -> str:
    """Resolve the active hardware profile."""
    from ..config import detect_gpu, get_settings

    requested = (get_settings().hardware_profile or "auto").strip().lower()
    if requested not in ("", "auto"):
        return requested

    gpu = detect_gpu()
    if not gpu:
        return "generic"

    name = str(gpu.get("name", "")).lower()
    physical_gb = float(gpu.get("vram_mb", 0)) / 1024.0
    if "rtx 3060" in name and 10.5 <= physical_gb <= 12.5:
        return "rtx3060_12gb"
    return "generic"


def low_vram() -> bool:
    """Aggressive low-memory mode for <=8GB effective VRAM."""
    b = runtime_vram_gb()
    return 0 < b <= 8


def constrained_vram() -> bool:
    """Moderate-memory mode for the <=12GB class.

    A 12GB 3060 gets stage isolation and moderate chunks without being forced
    down to the quality settings intended for 8GB cards.
    """
    b = runtime_vram_gb()
    return hardware_profile_name() == "rtx3060_12gb" or (0 < b <= 12.5)


def should_unload_between_stages() -> bool:
    """Whether completed heavyweight model stages must release their model."""
    from ..config import get_settings

    override = get_settings().force_stage_unload
    if override is not None:
        return bool(override)
    return constrained_vram()


def runtime_vram_policy() -> dict:
    """Serializable policy summary for diagnostics and the system endpoint."""
    return {
        "hardware_profile": hardware_profile_name(),
        "runtime_vram_gb": round(runtime_vram_gb(), 2),
        "hard_cap_gb": vram_budget_gb(),
        "low_vram": low_vram(),
        "constrained_vram": constrained_vram(),
        "stage_unload": should_unload_between_stages(),
    }


# CUDA context + cuDNN workspace etc. live outside torch's allocator but
# still count against real GPU memory — reserve room for them in the budget.
_CUDA_OVERHEAD_GB = 0.9


def apply_vram_budget() -> None:
    """Hard-cap torch CUDA allocations when an explicit budget is configured."""
    budget = vram_budget_gb()
    if budget <= 0:
        return
    import os

    # Must be set before CUDA init; reduces fragmentation so the capped
    # allocator can actually use its full budget.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    import torch

    if not torch.cuda.is_available():
        return
    total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    allocator_budget = max(budget - _CUDA_OVERHEAD_GB, 1.0)
    fraction = min(allocator_budget / total_gb, 1.0)
    torch.cuda.set_per_process_memory_fraction(fraction, 0)


def free_cuda_memory() -> None:
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass

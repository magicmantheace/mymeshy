"""Hardware-aware scheduling policy for local generation.

This module deliberately separates *scheduling* from torch's hard allocator
cap. A 12GB card should be allowed to use most of its VRAM while still forcing
heavy models to leave memory between stages.
"""
from __future__ import annotations

from .config import detect_gpu, get_settings


def physical_vram_gb() -> float:
    gpu = detect_gpu()
    if not gpu:
        return 0.0
    return float(gpu.get("vram_mb", 0)) / 1024.0


def effective_vram_gb() -> float:
    """VRAM available to the scheduling policy.

    An explicit hard budget wins. Otherwise use detected physical VRAM.
    """
    budget = float(get_settings().vram_budget_gb or 0)
    return budget if budget > 0 else physical_vram_gb()


def profile_name() -> str:
    settings = get_settings()
    requested = (settings.hardware_profile or "auto").strip().lower()
    if requested not in ("", "auto"):
        return requested

    gpu = detect_gpu()
    if not gpu:
        return "generic"

    name = str(gpu.get("name", "")).lower()
    vram = physical_vram_gb()
    if "rtx 3060" in name and 10.5 <= vram <= 12.5:
        return "rtx3060_12gb"
    return "generic"


def low_vram() -> bool:
    vram = effective_vram_gb()
    return 0 < vram <= 8.0


def constrained_vram() -> bool:
    """Moderate-memory class where sequential heavy-model residency is safer."""
    vram = effective_vram_gb()
    return profile_name() == "rtx3060_12gb" or (0 < vram <= 12.5)


def should_unload_between_stages() -> bool:
    override = get_settings().force_stage_unload
    if override is not None:
        return bool(override)
    return constrained_vram()


def triposr_chunk_size() -> int:
    if low_vram():
        return 2048
    if constrained_vram():
        return 4096
    return 8192


def triposr_resolution() -> int:
    if low_vram():
        return 192
    if constrained_vram():
        return 224
    return 256


def auto_image_to_3d_order() -> tuple[str, ...]:
    """Preferred adapter order for the detected hardware.

    On the RTX 3060 12GB, legacy TRELLIS is deliberately not the automatic
    first choice. Hunyuan mini is the balanced path and TripoSR is the safe
    fast fallback. TRELLIS remains available when explicitly requested.
    """
    if profile_name() == "rtx3060_12gb":
        return ("hunyuan3d", "triposr", "trellis", "mock")
    return ("trellis", "hunyuan3d", "triposr", "mock")


def runtime_policy() -> dict:
    gpu = detect_gpu()
    return {
        "profile": profile_name(),
        "gpu": gpu,
        "physical_vram_gb": round(physical_vram_gb(), 2),
        "effective_vram_gb": round(effective_vram_gb(), 2),
        "hard_cap_gb": float(get_settings().vram_budget_gb or 0),
        "low_vram": low_vram(),
        "constrained_vram": constrained_vram(),
        "stage_unload": should_unload_between_stages(),
        "triposr_chunk_size": triposr_chunk_size(),
        "triposr_resolution": triposr_resolution(),
        "auto_image_to_3d_order": list(auto_image_to_3d_order()),
    }

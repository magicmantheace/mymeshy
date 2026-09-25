"""Adapter registry: discovers what is installed and resolves the active
adapter per pipeline stage, falling back to the mock implementations so the
app always works."""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ..config import REPO_ROOT, get_settings


def _add_external_repos() -> None:
    """Model repos cloned into external/ (TripoSR, Hunyuan3D-2, TRELLIS, ...)
    are made importable without a pip install."""
    ext = REPO_ROOT / "external"
    if ext.is_dir():
        for repo in ext.iterdir():
            if repo.is_dir() and str(repo) not in sys.path:
                sys.path.insert(0, str(repo))


_add_external_repos()
from .adapters.hunyuan3d import Hunyuan3DImageTo3D, HunyuanPaintTexturing
from .adapters.mock import MockImageTo3D, MockTextToImage, MockTexturing
from .adapters.sdxl_turbo import SdxlTurboTextToImage
from .adapters.trellis import TrellisImageTo3D
from .adapters.triposr import TripoSRImageTo3D
from .base import Adapter, ImageTo3DAdapter, TextToImageAdapter, TexturingAdapter, hardware_profile_name

# Base preference order for generic hardware (mock always last).
_I23D: list[ImageTo3DAdapter] = [
    TrellisImageTo3D(),
    Hunyuan3DImageTo3D(),
    TripoSRImageTo3D(),
    MockImageTo3D(),
]
_T2I: list[TextToImageAdapter] = [SdxlTurboTextToImage(), MockTextToImage()]
_TEX: list[TexturingAdapter] = [HunyuanPaintTexturing(), MockTexturing()]

_POOLS: dict[str, list[Adapter]] = {
    "image_to_3d": _I23D,
    "text_to_image": _T2I,
    "texturing": _TEX,
}


def _auto_pool(stage: str, pool: list[Adapter]) -> list[Adapter]:
    """Return hardware-aware auto ordering without changing explicit choices."""
    if stage == "image_to_3d" and hardware_profile_name() == "rtx3060_12gb":
        # Legacy TRELLIS commonly wants more than 12GB. Hunyuan mini is the
        # balanced default; TripoSR is the safe/fast fallback. TRELLIS remains
        # available when explicitly requested and will later be replaced by a
        # dedicated TRELLIS.2 low-VRAM worker.
        rank = {"hunyuan3d": 0, "triposr": 1, "trellis": 2, "mock": 99}
        return sorted(pool, key=lambda a: rank.get(a.name, 50))
    return pool


@lru_cache
def _probe(adapter_key: tuple[str, str]) -> tuple[bool, str]:
    stage, name = adapter_key
    for a in _POOLS[stage]:
        if a.name == name:
            try:
                return a.probe()
            except Exception as exc:  # a broken install must not kill the app
                return False, f"probe failed: {exc}"
    return False, "unknown adapter"


def describe(stage: str) -> list[dict]:
    out = []
    for a in _POOLS[stage]:
        ok, reason = _probe((stage, a.name))
        entry = {"name": a.name, "available": ok, "description": a.description}
        if not ok:
            entry["reason"] = reason
        out.append(entry)
    return out


def resolve(stage: str, requested: Optional[str] = None) -> Adapter:
    """Pick an adapter for a stage. ``requested`` (job option) wins over the
    configured default; "auto" walks the hardware-aware preference order."""
    settings = get_settings()
    configured = {
        "image_to_3d": settings.i23d_adapter,
        "text_to_image": settings.t2i_adapter,
        "texturing": settings.texture_adapter,
    }[stage]
    want = (requested or configured or "auto").lower()

    pool = _POOLS[stage]
    if want != "auto":
        for a in pool:
            if a.name == want:
                ok, reason = _probe((stage, a.name))
                if not ok:
                    raise RuntimeError(f"Adapter '{want}' is not available: {reason}")
                return a
        raise RuntimeError(f"Unknown {stage} adapter '{want}'")

    for a in _auto_pool(stage, pool):
        ok, _ = _probe((stage, a.name))
        if ok:
            return a
    raise RuntimeError(f"No {stage} adapter available")  # unreachable: mock always probes True


def active_names() -> dict[str, str]:
    return {stage: resolve(stage).name for stage in _POOLS}

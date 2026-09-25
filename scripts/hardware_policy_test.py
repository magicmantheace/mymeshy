"""Deterministic tests for AssetForge hardware scheduling policy.

No NVIDIA GPU is required: detect_gpu/get_settings are patched with synthetic
hardware so profile behavior can be checked before running real-model tests.

Run from repo root:
    .venv\Scripts\python.exe scripts\hardware_policy_test.py
or:
    .venv/bin/python scripts/hardware_policy_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import hardware  # noqa: E402


def settings(*, budget=0.0, profile="auto", unload=None):
    return SimpleNamespace(
        vram_budget_gb=budget,
        hardware_profile=profile,
        force_stage_unload=unload,
    )


def check_rtx3060() -> None:
    gpu = {"name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288}
    with patch.object(hardware, "detect_gpu", return_value=gpu), patch.object(
        hardware, "get_settings", return_value=settings()
    ):
        assert hardware.profile_name() == "rtx3060_12gb"
        assert hardware.physical_vram_gb() == 12.0
        assert hardware.effective_vram_gb() == 12.0
        assert hardware.low_vram() is False
        assert hardware.constrained_vram() is True
        assert hardware.should_unload_between_stages() is True
        assert hardware.triposr_chunk_size() == 4096
        assert hardware.triposr_resolution() == 224
        assert hardware.auto_image_to_3d_order() == (
            "hunyuan3d", "triposr", "trellis", "mock"
        )


def check_small_gpu() -> None:
    gpu = {"name": "NVIDIA GeForce RTX 2060", "vram_mb": 6144}
    with patch.object(hardware, "detect_gpu", return_value=gpu), patch.object(
        hardware, "get_settings", return_value=settings()
    ):
        assert hardware.profile_name() == "generic"
        assert hardware.low_vram() is True
        assert hardware.constrained_vram() is True
        assert hardware.should_unload_between_stages() is True
        assert hardware.triposr_chunk_size() == 2048
        assert hardware.triposr_resolution() == 192


def check_large_gpu() -> None:
    gpu = {"name": "NVIDIA GeForce RTX 3090", "vram_mb": 24576}
    with patch.object(hardware, "detect_gpu", return_value=gpu), patch.object(
        hardware, "get_settings", return_value=settings()
    ):
        assert hardware.profile_name() == "generic"
        assert hardware.low_vram() is False
        assert hardware.constrained_vram() is False
        assert hardware.should_unload_between_stages() is False
        assert hardware.triposr_chunk_size() == 8192
        assert hardware.triposr_resolution() == 256
        assert hardware.auto_image_to_3d_order()[0] == "trellis"


def check_overrides() -> None:
    gpu = {"name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288}
    with patch.object(hardware, "detect_gpu", return_value=gpu), patch.object(
        hardware, "get_settings", return_value=settings(budget=7.0, unload=False)
    ):
        assert hardware.effective_vram_gb() == 7.0
        assert hardware.low_vram() is True
        assert hardware.should_unload_between_stages() is False


if __name__ == "__main__":
    check_rtx3060()
    check_small_gpu()
    check_large_gpu()
    check_overrides()
    print("hardware policy tests passed")

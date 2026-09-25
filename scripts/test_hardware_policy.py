"""Deterministic tests for AssetForge hardware scheduling policy.

Run from the repository root:

    python scripts/test_hardware_policy.py

No NVIDIA GPU or ML model installation is required; GPU detection is mocked.
"""
from __future__ import annotations

import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.pipeline import base  # noqa: E402

_ENV_KEYS = (
    "MYMESHY_HARDWARE_PROFILE",
    "MYMESHY_VRAM_BUDGET_GB",
    "MYMESHY_FORCE_STAGE_UNLOAD",
)


@contextmanager
def settings_env(**values):
    old = {k: os.environ.get(k) for k in _ENV_KEYS}
    try:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in values.items():
            if value is not None:
                os.environ[key] = str(value)
        config.get_settings.cache_clear()
        yield
    finally:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in old.items():
            if value is not None:
                os.environ[key] = value
        config.get_settings.cache_clear()


class HardwarePolicyTests(unittest.TestCase):
    def test_rtx3060_12gb_uses_constrained_profile_not_low_vram(self):
        with settings_env(MYMESHY_HARDWARE_PROFILE="auto", MYMESHY_VRAM_BUDGET_GB="0"):
            with patch.object(
                config,
                "detect_gpu",
                return_value={"name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288},
            ):
                self.assertEqual(base.hardware_profile_name(), "rtx3060_12gb")
                self.assertAlmostEqual(base.runtime_vram_gb(), 12.0)
                self.assertFalse(base.low_vram())
                self.assertTrue(base.constrained_vram())
                self.assertTrue(base.should_unload_between_stages())

    def test_hard_cap_can_intentionally_enable_low_vram_mode(self):
        with settings_env(MYMESHY_HARDWARE_PROFILE="auto", MYMESHY_VRAM_BUDGET_GB="6"):
            with patch.object(
                config,
                "detect_gpu",
                return_value={"name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288},
            ):
                self.assertEqual(base.runtime_vram_gb(), 6.0)
                self.assertTrue(base.low_vram())
                self.assertTrue(base.constrained_vram())
                self.assertTrue(base.should_unload_between_stages())

    def test_budget_cannot_make_physical_gpu_larger(self):
        with settings_env(MYMESHY_HARDWARE_PROFILE="auto", MYMESHY_VRAM_BUDGET_GB="16"):
            with patch.object(
                config,
                "detect_gpu",
                return_value={"name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288},
            ):
                self.assertEqual(base.runtime_vram_gb(), 12.0)
                self.assertTrue(base.constrained_vram())

    def test_generic_24gb_gpu_does_not_force_stage_unload(self):
        with settings_env(MYMESHY_HARDWARE_PROFILE="auto", MYMESHY_VRAM_BUDGET_GB="0"):
            with patch.object(
                config,
                "detect_gpu",
                return_value={"name": "NVIDIA GeForce RTX 4090", "vram_mb": 24564},
            ):
                self.assertEqual(base.hardware_profile_name(), "generic")
                self.assertFalse(base.low_vram())
                self.assertFalse(base.constrained_vram())
                self.assertFalse(base.should_unload_between_stages())

    def test_stage_unload_override_wins(self):
        with settings_env(
            MYMESHY_HARDWARE_PROFILE="auto",
            MYMESHY_VRAM_BUDGET_GB="0",
            MYMESHY_FORCE_STAGE_UNLOAD="false",
        ):
            with patch.object(
                config,
                "detect_gpu",
                return_value={"name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288},
            ):
                self.assertTrue(base.constrained_vram())
                self.assertFalse(base.should_unload_between_stages())


if __name__ == "__main__":
    unittest.main(verbosity=2)

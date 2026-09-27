"""GPU-free source contract for /api/system fields consumed by the frontend."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPES = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
TOPBAR = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text(encoding="utf-8")
DIAGNOSTICS = (ROOT / "frontend" / "src" / "components" / "SystemDiagnostics.tsx").read_text(
    encoding="utf-8"
)
BASE = (ROOT / "backend" / "app" / "pipeline" / "base.py").read_text(encoding="utf-8")
API = (ROOT / "backend" / "app" / "api.py").read_text(encoding="utf-8")


def main() -> None:
    for field in (
        "runtime: RuntimeInfo",
        "memory_policy: MemoryPolicy",
        "workers: WorkerSystemInfo",
        "hardware_profile: string",
        "runtime_vram_gb: number",
        "hunyuan_shape: WorkerInfo",
        "hunyuan_paint: WorkerInfo",
    ):
        assert field in TYPES, field

    assert '"hardware_profile": hardware_profile_name()' in BASE
    assert '"memory_policy": runtime_vram_policy()' in API
    assert '"runtime": runtime_versions()' in API
    assert '"workers": workers' in API

    assert "system.memory_policy.hardware_profile" in TOPBAR
    assert "<SystemDiagnostics" in TOPBAR
    assert "system.workers.triposr" in DIAGNOSTICS
    assert "system.workers.hunyuan_shape" in DIAGNOSTICS
    assert "system.workers.hunyuan_paint" in DIAGNOSTICS
    assert "system.adapters.image_to_3d" in DIAGNOSTICS
    assert "system.generation_presets" in DIAGNOSTICS

    print("PASS: frontend system diagnostics consume the backend /api/system contract")


if __name__ == "__main__":
    main()

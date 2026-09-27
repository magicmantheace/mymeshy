"""GPU-free source contract for frontend generation option forwarding."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
TYPES = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
OPTIONS = (ROOT / "frontend" / "src" / "components" / "panels" / "OptionsFields.tsx").read_text(
    encoding="utf-8"
)


def main() -> None:
    # Backend-native preset identity must survive the frontend sanitization step
    # so jobs/checkpoints/assets retain named preset provenance.
    assert "if (options.preset) out.preset = options.preset;" in API
    assert "preset?: 'fast' | 'balanced' | 'quality';" in TYPES
    assert "preset: o.preset || undefined" in OPTIONS

    # Keep the complete boolean generation-option contract forwardable. A UI
    # control is not required for every field, but API callers must not lose it.
    assert "decimate?: boolean;" in TYPES
    assert "if (typeof options.decimate === 'boolean') out.decimate = options.decimate;" in API
    assert "if (typeof options.generate_pbr === 'boolean') out.generate_pbr = options.generate_pbr;" in API

    print("PASS: frontend forwards named preset identity and backend generation overrides")


if __name__ == "__main__":
    main()

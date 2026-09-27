"""GPU-free checks for backend-native generation presets."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline import presets  # noqa: E402


def main() -> None:
    fast = presets.resolve("fast")
    balanced = presets.resolve("balanced")
    quality = presets.resolve("quality")
    assert fast.adapter == "triposr" and fast.target_polycount == 20_000
    assert balanced.adapter is None and balanced.target_polycount == 30_000
    assert quality.adapter == "hunyuan3d" and quality.texture_size == 2048

    status = [{"name": "triposr", "available": True}, {"name": "hunyuan3d", "available": False}]
    public = {row["name"]: row for row in presets.public(status)}
    assert public["fast"]["available"] is True
    assert public["balanced"]["available"] is True
    assert public["quality"]["available"] is False

    try:
        presets.resolve("turbo")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown preset was accepted")

    print("PASS: backend generation presets are deterministic and readiness-aware")


if __name__ == "__main__":
    main()

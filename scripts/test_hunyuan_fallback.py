"""GPU-free contract test for Hunyuan shape salvage after Paint worker failure."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import trimesh
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline.adapters import hunyuan3d  # noqa: E402
from app.pipeline.base import GenOptions, MeshResult  # noqa: E402
from app.workers import launch  # noqa: E402


def main() -> None:
    shape = MeshResult(
        mesh=trimesh.creation.box(),
        textured=False,
        extras={
            "worker": "hunyuan_shape",
            "worker_pid": 123,
            "shape_model": "test-shape-model",
        },
    )
    failure = launch.WorkerFailure("hunyuan_paint", "CUDA out of memory")
    progress_messages: list[str] = []

    with patch.object(hunyuan3d, "_isolated_enabled", return_value=True), \
         patch.object(hunyuan3d, "low_vram", return_value=False), \
         patch.object(launch, "run_hunyuan_shape_worker", return_value=shape), \
         patch.object(launch, "probe_worker", return_value=(True, "")), \
         patch.object(launch, "run_hunyuan_paint_worker", side_effect=failure):
        result = hunyuan3d.Hunyuan3DImageTo3D().generate(
            [Image.new("RGBA", (32, 32), (255, 255, 255, 255))],
            GenOptions(),
            lambda _p, message: progress_messages.append(message),
        )

    assert result is shape
    assert result.textured is False
    fallback = result.extras["paint_fallback"]
    assert fallback["worker"] == "hunyuan_paint"
    assert fallback["category"] == "cuda_oom"
    assert "CUDA out of memory" in fallback["error"]
    assert any("using reference projection" in message for message in progress_messages)

    # A non-worker programming/runtime error must still fail loudly rather than
    # silently converting every Paint bug into a lower-quality success.
    with patch.object(hunyuan3d, "_isolated_enabled", return_value=True), \
         patch.object(hunyuan3d, "low_vram", return_value=False), \
         patch.object(launch, "run_hunyuan_shape_worker", return_value=shape), \
         patch.object(launch, "probe_worker", return_value=(True, "")), \
         patch.object(launch, "run_hunyuan_paint_worker", side_effect=ValueError("bad API contract")):
        try:
            hunyuan3d.Hunyuan3DImageTo3D().generate(
                [Image.new("RGBA", (32, 32), (255, 255, 255, 255))],
                GenOptions(),
                lambda _p, _m: None,
            )
        except ValueError as exc:
            assert "bad API contract" in str(exc)
        else:
            raise AssertionError("non-worker Paint error was incorrectly swallowed")

    print("PASS: Hunyuan isolated Paint worker failures salvage Shape without hiding other errors")


if __name__ == "__main__":
    main()

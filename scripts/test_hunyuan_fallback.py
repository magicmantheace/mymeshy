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


def _shape() -> MeshResult:
    return MeshResult(
        mesh=trimesh.creation.box(),
        textured=False,
        extras={
            "worker": "hunyuan_shape",
            "worker_pid": 123,
            "shape_model": "test-shape-model",
        },
    )


def _generate_with_paint_failure(exc: Exception, progress_messages=None):
    shape = _shape()
    messages = progress_messages if progress_messages is not None else []
    with patch.object(hunyuan3d, "_isolated_enabled", return_value=True), \
         patch.object(hunyuan3d, "low_vram", return_value=False), \
         patch.object(launch, "run_hunyuan_shape_worker", return_value=shape), \
         patch.object(launch, "probe_worker", return_value=(True, "")), \
         patch.object(launch, "run_hunyuan_paint_worker", side_effect=exc):
        result = hunyuan3d.Hunyuan3DImageTo3D().generate(
            [Image.new("RGBA", (32, 32), (255, 255, 255, 255))],
            GenOptions(),
            lambda _p, message: messages.append(message),
        )
    return result


def _assert_propagates(exc: Exception) -> None:
    try:
        _generate_with_paint_failure(exc)
    except type(exc) as caught:
        assert str(exc) in str(caught)
    else:
        raise AssertionError(f"{type(exc).__name__} was incorrectly swallowed")


def main() -> None:
    progress_messages: list[str] = []
    failure = launch.WorkerFailure("hunyuan_paint", "CUDA out of memory")
    result = _generate_with_paint_failure(failure, progress_messages)

    assert result.textured is False
    fallback = result.extras["paint_fallback"]
    assert fallback["worker"] == "hunyuan_paint"
    assert fallback["category"] == "cuda_oom"
    assert "CUDA out of memory" in fallback["error"]
    assert any("using reference projection" in message for message in progress_messages)

    # Operational failures can degrade gracefully because the completed Shape
    # result remains valid.
    timeout = launch.WorkerFailure(
        "hunyuan_paint", "worker exceeded the 900s timeout and was terminated"
    )
    assert _generate_with_paint_failure(timeout).extras["paint_fallback"]["category"] == "timeout"

    # Protocol/output corruption and generic child bugs must stay hard failures;
    # silently turning these into a lower-quality success would hide defects.
    _assert_propagates(
        launch.WorkerFailure("hunyuan_paint", "worker produced an invalid triangle mesh")
    )
    _assert_propagates(launch.WorkerFailure("hunyuan_paint", "unexpected model API failure"))

    # Parent-side programming/runtime errors also remain hard failures.
    _assert_propagates(ValueError("bad API contract"))

    print("PASS: Hunyuan Paint salvage is limited to known operational failures")


if __name__ == "__main__":
    main()

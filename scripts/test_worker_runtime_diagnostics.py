"""GPU-free contract checks for isolated worker runtime provenance."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.workers.diagnostics import _python_runtime, worker_runtime_summary  # noqa: E402


def main() -> None:
    runtime = _python_runtime(sys.executable)
    assert runtime["python_version"]
    assert isinstance(runtime["cuda_available"], bool)
    assert "torch_version" in runtime
    assert "cuda_runtime" in runtime
    assert "error" in runtime

    summary = worker_runtime_summary()
    expected = {"triposr", "hunyuan_shape", "hunyuan_paint"}
    assert expected <= set(summary)
    for name in expected:
        row = summary[name]
        assert row["python"]
        assert "python_version" in row
        assert "torch_version" in row
        assert "cuda_runtime" in row
        assert isinstance(row["cuda_available"], bool)
        assert "source_revision" in row

    print("PASS: isolated worker runtime provenance has a stable serializable contract")


if __name__ == "__main__":
    main()

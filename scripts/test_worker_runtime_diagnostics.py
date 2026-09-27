"""GPU-free contract checks for isolated worker runtime provenance."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.workers.diagnostics import _python_runtime, _source_locks, worker_runtime_summary  # noqa: E402


def main() -> None:
    runtime = _python_runtime(sys.executable)
    assert runtime["python_version"]
    assert isinstance(runtime["cuda_available"], bool)
    assert "torch_version" in runtime
    assert "cuda_runtime" in runtime
    assert "error" in runtime

    locks = _source_locks()
    assert set(locks) == {"triposr", "hunyuan3d_2"}
    for revision in locks.values():
        assert re.fullmatch(r"[0-9a-f]{40}", revision)

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
        assert re.fullmatch(r"[0-9a-f]{40}", row["expected_source_revision"])
        assert isinstance(row["source_matches_lock"], bool)

    assert summary["triposr"]["expected_source_revision"] == locks["triposr"]
    assert summary["hunyuan_shape"]["expected_source_revision"] == locks["hunyuan3d_2"]
    assert summary["hunyuan_paint"]["expected_source_revision"] == locks["hunyuan3d_2"]

    print("PASS: worker runtime provenance includes stable source-lock expectations")


if __name__ == "__main__":
    main()

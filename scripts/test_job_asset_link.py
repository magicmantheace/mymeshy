"""GPU-free test that resumable asset IDs survive real job failure persistence."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.jobs import JobManager  # noqa: E402


def main() -> None:
    previous_data_dir = os.environ.get("MYMESHY_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="assetforge-jobs-") as td:
            os.environ["MYMESHY_DATA_DIR"] = td
            get_settings.cache_clear()

            release = threading.Event()

            def work(job, progress, cancelled):
                release.wait(5)
                raise RuntimeError("simulated downstream failure")

            manager = JobManager()
            job = manager.submit("text_to_3d", {}, work)
            manager.link_asset(job.id, "resumable-asset")

            asset_path = Path(td) / "assets" / "resumable-asset"
            (asset_path / "source").mkdir(parents=True)
            (asset_path / "generation_checkpoint.json").write_text("{}", encoding="utf-8")
            (asset_path / "source" / "generated_raw.glb").write_bytes(b"checkpoint")

            release.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                current = manager.get(job.id)
                if current is not None and current.status in {"done", "error", "cancelled"}:
                    break
                time.sleep(0.01)
            else:
                raise AssertionError("job worker did not reach a terminal state")

            current = manager.get(job.id)
            assert current is not None
            assert current.status == "error"
            assert current.asset_id == "resumable-asset"
            assert "simulated downstream failure" in (current.error or "")
            assert current.public()["resumable"] is True

            saved = json.loads((Path(td) / "jobs.json").read_text(encoding="utf-8"))
            record = next(item for item in saved if item["id"] == job.id)
            assert record["status"] == "error"
            assert record["asset_id"] == "resumable-asset"
            assert record["resumable"] is True
    finally:
        if previous_data_dir is None:
            os.environ.pop("MYMESHY_DATA_DIR", None)
        else:
            os.environ["MYMESHY_DATA_DIR"] = previous_data_dir
        get_settings.cache_clear()

    print("PASS: asset link and resumable checkpoint survive actual downstream job failure")


if __name__ == "__main__":
    main()

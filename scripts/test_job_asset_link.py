"""GPU-free test that resumable asset IDs survive job persistence."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.jobs import JobManager  # noqa: E402


def main() -> None:
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

        saved = json.loads((Path(td) / "jobs.json").read_text(encoding="utf-8"))
        record = next(item for item in saved if item["id"] == job.id)
        assert record["asset_id"] == "resumable-asset"

        release.set()

    print("PASS: job asset links are persisted before downstream completion")


if __name__ == "__main__":
    main()

"""GPU-free test for durable restart normalization and checkpoint discovery."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.jobs import JobManager  # noqa: E402


def main() -> None:
    previous_data_dir = os.environ.get("MYMESHY_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="assetforge-restart-") as td:
            os.environ["MYMESHY_DATA_DIR"] = td
            get_settings.cache_clear()
            root = Path(td)

            asset_id = "restart-asset"
            source = root / "assets" / asset_id / "source"
            source.mkdir(parents=True)
            (source.parent / "generation_checkpoint.json").write_text("{}", encoding="utf-8")
            (source / "generated_raw.glb").write_bytes(b"checkpoint")

            history = [
                {
                    "id": "job-running",
                    "type": "text_to_3d",
                    "params": {"prompt": "crate"},
                    "status": "running",
                    "stage": "mesh_cleanup",
                    "progress": 0.6,
                    "message": "Cleaning mesh",
                    "error": None,
                    "error_category": None,
                    "asset_id": asset_id,
                    "created_at": "2026-09-27T12:00:00",
                },
                {
                    "id": "job-done",
                    "type": "image_to_3d",
                    "params": {},
                    "status": "done",
                    "stage": "done",
                    "progress": 1.0,
                    "message": "Asset ready",
                    "error": None,
                    "error_category": None,
                    "asset_id": "finished-asset",
                    "created_at": "2026-09-27T11:00:00",
                },
            ]
            (root / "jobs.json").write_text(json.dumps(history), encoding="utf-8")

            manager = JobManager()
            interrupted = manager.get("job-running")
            assert interrupted is not None
            assert interrupted.status == "error"
            assert interrupted.error_category == "backend_restart"
            assert interrupted.stage == "interrupted"
            assert interrupted.message == "Interrupted by backend restart"
            assert "was running" in (interrupted.error or "")
            assert interrupted.public()["resumable"] is True

            done = manager.get("job-done")
            assert done is not None and done.status == "done"

            persisted = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
            restored = next(row for row in persisted if row["id"] == "job-running")
            assert restored["status"] == "error"
            assert restored["error_category"] == "backend_restart"
            assert restored["resumable"] is True
            assert next(row for row in persisted if row["id"] == "job-done")["status"] == "done"
    finally:
        if previous_data_dir is None:
            os.environ.pop("MYMESHY_DATA_DIR", None)
        else:
            os.environ["MYMESHY_DATA_DIR"] = previous_data_dir
        get_settings.cache_clear()

    print("PASS: backend restart state is persisted and checkpoint recovery remains discoverable")


if __name__ == "__main__":
    main()

"""GPU-free checks for benchmark report aggregation."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_summary import summarize_reports, write_summary  # noqa: E402


def _report(status: str, adapter: str, case_id: str) -> dict:
    return {
        "timestamp": "2026-09-27T00:00:00+00:00",
        "status": status,
        "error_category": None if status == "passed" else "cuda_oom",
        "adapter": adapter,
        "pipeline_adapters": {
            "text_to_image": "sdxl_turbo" if case_id.startswith("text_") else None,
            "image_to_3d": adapter,
        },
        "case_id": case_id,
        "case_fingerprint": "abc123",
        "runtime_seconds": 12.5,
        "gpu": {"peak_delta_mib": 4321},
        "settings": {"texture_size": 1024, "target_polycount": 20000},
        "stats": {"triangles": 18000},
        "validation": {"passed": status == "passed"},
        "asset_id": "asset-1" if status == "passed" else None,
        "source_revisions": {"assetforge": "deadbeef"},
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetforge-benchmark-summary-") as td:
        root = Path(td)
        (root / "real-model-triposr-text_crate.json").write_text(
            json.dumps(_report("passed", "triposr", "text_crate")), encoding="utf-8"
        )
        (root / "real-model-hunyuan3d-image_potion.json").write_text(
            json.dumps(_report("failed", "hunyuan3d", "image_potion")), encoding="utf-8"
        )
        (root / "real-model-corrupt.json").write_text("{not json", encoding="utf-8")

        summary = summarize_reports(list(root.glob("real-model-*.json")))
        assert summary["reports"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert len(summary["malformed_reports"]) == 1
        failed = next(row for row in summary["rows"] if row["status"] == "failed")
        assert failed["error_category"] == "cuda_oom"
        assert failed["peak_delta_mib"] == 4321
        assert failed["image_to_3d_adapter"] == "hunyuan3d"
        passed = next(row for row in summary["rows"] if row["status"] == "passed")
        assert passed["text_to_image_adapter"] == "sdxl_turbo"
        assert passed["image_to_3d_adapter"] == "triposr"

        json_path, csv_path = write_summary(root)
        assert json_path.is_file() and csv_path.is_file()
        csv_text = csv_path.read_text(encoding="utf-8")
        assert "text_crate" in csv_text
        assert "sdxl_turbo" in csv_text

    print("PASS: benchmark reports aggregate to deterministic JSON/CSV summaries")


if __name__ == "__main__":
    main()

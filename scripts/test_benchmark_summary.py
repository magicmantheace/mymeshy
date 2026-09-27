"""GPU-free checks for benchmark report aggregation."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_summary import summarize_reports, write_summary  # noqa: E402


def _report(status: str, adapter: str, case_id: str, *, degraded: bool = False) -> dict:
    report = {
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
    if degraded:
        degradation = {
            "worker": "hunyuan_paint",
            "category": "cuda_oom",
            "error": "simulated paint OOM",
        }
        report["degraded"] = True
        report["degradation"] = degradation
        report["adapter_extras"] = {"paint_fallback": degradation}
    return report


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetforge-benchmark-summary-") as td:
        root = Path(td)
        (root / "real-model-triposr-text_crate.json").write_text(
            json.dumps(_report("passed", "triposr", "text_crate")), encoding="utf-8"
        )
        (root / "real-model-hunyuan3d-image_chair.json").write_text(
            json.dumps(_report("passed", "hunyuan3d", "image_chair", degraded=True)), encoding="utf-8"
        )
        (root / "real-model-hunyuan3d-image_potion.json").write_text(
            json.dumps(_report("failed", "hunyuan3d", "image_potion")), encoding="utf-8"
        )
        (root / "real-model-corrupt.json").write_text("{not json", encoding="utf-8")

        summary = summarize_reports(list(root.glob("real-model-*.json")))
        assert summary["schema_version"] == 2
        assert summary["reports"] == 3
        assert summary["passed"] == 2
        assert summary["clean_passed"] == 1
        assert summary["degraded_passed"] == 1
        assert summary["failed"] == 1
        assert len(summary["malformed_reports"]) == 1

        failed = next(row for row in summary["rows"] if row["status"] == "failed")
        assert failed["error_category"] == "cuda_oom"
        assert failed["peak_delta_mib"] == 4321
        assert failed["image_to_3d_adapter"] == "hunyuan3d"

        triposr = next(row for row in summary["rows"] if row["case_id"] == "text_crate")
        assert triposr["text_to_image_adapter"] == "sdxl_turbo"
        assert triposr["image_to_3d_adapter"] == "triposr"
        assert triposr["degraded"] is False

        degraded = next(row for row in summary["rows"] if row["case_id"] == "image_chair")
        assert degraded["status"] == "passed"
        assert degraded["degraded"] is True
        assert degraded["degradation_category"] == "cuda_oom"

        json_path, csv_path = write_summary(root)
        assert json_path.is_file() and csv_path.is_file()
        csv_text = csv_path.read_text(encoding="utf-8")
        assert "text_crate" in csv_text
        assert "sdxl_turbo" in csv_text
        assert "image_chair" in csv_text
        assert "cuda_oom" in csv_text

    print("PASS: benchmark summaries separate clean, degraded, and failed runs")


if __name__ == "__main__":
    main()

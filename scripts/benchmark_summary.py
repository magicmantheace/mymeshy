"""Aggregate real-model benchmark reports into compact JSON and CSV summaries."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _row(report: dict, source: Path) -> dict:
    stats = report.get("stats") or {}
    validation = report.get("validation") or {}
    gpu = report.get("gpu") or {}
    settings = report.get("settings") or {}
    pipeline_adapters = report.get("pipeline_adapters") or {}
    adapter_extras = report.get("adapter_extras") or {}
    degradation = adapter_extras.get("paint_fallback") or adapter_extras.get("paint_skipped")
    if not isinstance(degradation, dict):
        degradation = None
    return {
        "file": source.name,
        "timestamp": report.get("timestamp"),
        "adapter": report.get("adapter"),
        "text_to_image_adapter": pipeline_adapters.get("text_to_image"),
        "image_to_3d_adapter": pipeline_adapters.get("image_to_3d"),
        "texturing_adapter": pipeline_adapters.get("texturing"),
        "case_id": report.get("case_id"),
        "status": report.get("status"),
        "degraded": degradation is not None,
        "degradation_category": degradation.get("category") if degradation else None,
        "error_category": report.get("error_category"),
        "runtime_seconds": report.get("runtime_seconds"),
        "peak_delta_mib": gpu.get("peak_delta_mib"),
        "triangles": stats.get("triangles"),
        "texture_size": settings.get("texture_size"),
        "target_polycount": settings.get("target_polycount"),
        "validation_passed": validation.get("passed") if validation else None,
        "asset_id": report.get("asset_id"),
        "case_fingerprint": report.get("case_fingerprint"),
        "assetforge_revision": (report.get("source_revisions") or {}).get("assetforge"),
    }


def summarize_reports(paths: list[Path]) -> dict:
    rows = []
    malformed = []
    for path in sorted(paths):
        try:
            report = json.loads(path.read_text(encoding="utf-8-sig"))
            rows.append(_row(report, path))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            malformed.append({"file": path.name, "error": str(exc)})

    passed = sum(row["status"] == "passed" for row in rows)
    failed = sum(row["status"] != "passed" for row in rows)
    degraded = sum(bool(row["degraded"]) for row in rows)
    return {
        "schema_version": 1,
        "reports": len(rows),
        "passed": passed,
        "failed": failed,
        "degraded": degraded,
        "malformed_reports": malformed,
        "rows": rows,
    }


def write_summary(directory: Path) -> tuple[Path, Path]:
    summary = summarize_reports(list(directory.glob("real-model-*.json")))
    json_path = directory / "benchmark-summary.json"
    csv_path = directory / "benchmark-summary.csv"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    fields = [
        "file", "timestamp", "adapter", "text_to_image_adapter", "image_to_3d_adapter",
        "texturing_adapter", "case_id", "status", "degraded", "degradation_category",
        "error_category", "runtime_seconds", "peak_delta_mib", "triangles", "texture_size",
        "target_polycount", "validation_passed", "asset_id", "case_fingerprint",
        "assetforge_revision",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary["rows"])
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", type=Path, default=Path("data/benchmarks"))
    args = parser.parse_args()
    json_path, csv_path = write_summary(args.directory)
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    print(f"Benchmark summary: {json_path}")
    print(f"CSV summary: {csv_path}")
    print(
        f"Reports: {summary['reports']} | passed: {summary['passed']} | "
        f"failed: {summary['failed']} | degraded: {summary['degraded']}"
    )
    if summary["malformed_reports"]:
        print(f"Malformed reports: {len(summary['malformed_reports'])}")


if __name__ == "__main__":
    main()

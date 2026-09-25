"""Benchmark MyMeshy/AssetForge generation on the reference RTX 3060 12GB.

This is intentionally a real-hardware benchmark, not a synthetic CUDA test.
It runs one image-to-3D job per requested adapter, samples nvidia-smi while the
job executes, and writes a JSON report under data/benchmarks/.

Examples:
    .venv\Scripts\python.exe scripts\rtx3060_benchmark.py
    .venv\Scripts\python.exe scripts\rtx3060_benchmark.py --adapters triposr hunyuan3d

Unavailable adapters are skipped rather than treated as failures.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image, ImageDraw  # noqa: E402

from app.config import detect_gpu, get_settings  # noqa: E402
from app.hardware import runtime_policy  # noqa: E402
from app.pipeline import registry  # noqa: E402
from app.pipeline.base import GenOptions, free_cuda_memory  # noqa: E402
from app.pipeline.runner import run_image_to_3d  # noqa: E402


def gpu_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return int(out.stdout.strip().splitlines()[0])


def monitor_gpu(stop: threading.Event, stats: dict) -> None:
    while not stop.is_set():
        try:
            used = gpu_used_mib()
            stats["peak_total_mib"] = max(stats["peak_total_mib"], used)
        except Exception:
            pass
        stop.wait(0.5)


def make_reference(path: Path) -> None:
    """Create a deterministic single-object reference image."""
    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([196, 55, 316, 145], radius=18, fill=(143, 101, 58, 255))
    draw.ellipse([125, 125, 387, 435], fill=(87, 40, 132, 255))
    draw.ellipse([175, 178, 282, 290], fill=(143, 82, 193, 255))
    img.save(path)


def adapter_availability() -> dict[str, dict]:
    return {entry["name"]: entry for entry in registry.describe("image_to_3d")}


def run_one(adapter: str, reference: Path, polycount: int, texture_size: int) -> dict:
    free_cuda_memory()
    time.sleep(1.0)

    try:
        baseline = gpu_used_mib()
    except Exception:
        baseline = 0

    stats = {"peak_total_mib": baseline}
    stop = threading.Event()
    monitor = threading.Thread(target=monitor_gpu, args=(stop, stats), daemon=True)
    monitor.start()

    t0 = time.perf_counter()
    last_stage = {"name": ""}

    def progress(p: float, stage: str, message: str) -> None:
        if stage != last_stage["name"]:
            last_stage["name"] = stage
            print(f"  [{adapter}] {p:5.1%} {stage}: {message}", flush=True)

    opts = GenOptions(
        adapter=adapter,
        target_polycount=polycount,
        texture_size=texture_size,
        generate_pbr=True,
    )

    result: dict = {
        "adapter": adapter,
        "baseline_vram_mib": baseline,
        "target_polycount": polycount,
        "texture_size": texture_size,
    }

    try:
        meta = run_image_to_3d([reference], opts, progress, lambda: False)
        result.update(
            {
                "status": "pass",
                "asset_id": meta.get("id"),
                "stats": meta.get("stats"),
                "textures": meta.get("textures"),
                "albedo_source": meta.get("albedo_source"),
            }
        )
    except Exception as exc:
        result.update(
            {
                "status": "fail",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    finally:
        result["elapsed_seconds"] = round(time.perf_counter() - t0, 2)
        stop.set()
        monitor.join(timeout=2)
        result["peak_total_vram_mib"] = stats["peak_total_mib"]
        result["peak_job_vram_mib"] = max(stats["peak_total_mib"] - baseline, 0)
        free_cuda_memory()

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adapters",
        nargs="+",
        default=["triposr", "hunyuan3d", "trellis"],
        help="Adapters to benchmark in order.",
    )
    parser.add_argument("--polycount", type=int, default=20000)
    parser.add_argument("--texture-size", type=int, default=1024)
    args = parser.parse_args()

    settings = get_settings()
    bench_dir = settings.data_dir / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)
    reference = settings.uploads_dir / "rtx3060_benchmark_reference.png"
    make_reference(reference)

    availability = adapter_availability()
    report = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "gpu": detect_gpu(),
        "hardware_policy": runtime_policy(),
        "reference_image": str(reference),
        "results": [],
    }

    print("GPU:", report["gpu"])
    print("Policy:", report["hardware_policy"])

    for adapter in args.adapters:
        entry = availability.get(adapter)
        if not entry:
            report["results"].append(
                {"adapter": adapter, "status": "skip", "reason": "unknown adapter"}
            )
            continue
        if not entry.get("available"):
            reason = entry.get("reason", "not installed")
            print(f"SKIP {adapter}: {reason}")
            report["results"].append(
                {"adapter": adapter, "status": "skip", "reason": reason}
            )
            continue

        print(f"\n== {adapter} ==")
        result = run_one(adapter, reference, args.polycount, args.texture_size)
        report["results"].append(result)
        print(json.dumps(result, indent=2))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = bench_dir / f"rtx3060-{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {out}")

    failures = [r for r in report["results"] if r.get("status") == "fail"]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

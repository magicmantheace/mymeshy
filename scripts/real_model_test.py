"""Direct pipeline validation for real GPU adapters with VRAM monitoring.

    python scripts/real_model_test.py triposr|hunyuan3d [case_id]

Case IDs are defined in benchmarks/corpus.json. If omitted, image_potion is used.
This harness records evidence; it does not decide tuned thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings, runtime_versions  # noqa: E402

settings = get_settings()
peak = {"used": 0, "baseline": 0}
stop = threading.Event()


def _gpu_used() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError((out.stderr or "nvidia-smi returned no memory data").strip())
    return int(out.stdout.strip().splitlines()[0])


def _git_revision(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def monitor() -> None:
    while not stop.is_set():
        try:
            peak["used"] = max(peak["used"], _gpu_used())
        except Exception:
            pass
        stop.wait(1.0)


def _load_corpus() -> dict:
    return json.loads((ROOT / "benchmarks" / "corpus.json").read_text(encoding="utf-8"))


def _load_case(case_id: str) -> tuple[int, dict]:
    corpus = _load_corpus()
    for case in corpus["cases"]:
        if case["id"] == case_id:
            return int(corpus["version"]), case
    known = ", ".join(case["id"] for case in corpus["cases"])
    raise ValueError(f"unknown benchmark case {case_id!r}; choose one of: {known}")


def _case_fingerprint(case: dict) -> str:
    payload = json.dumps(case, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _synthetic_image(generator: str):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if generator == "potion":
        d.rounded_rectangle([196, 60, 316, 150], radius=20, fill=(160, 120, 70, 255))
        d.ellipse([130, 130, 382, 430], fill=(90, 40, 130, 255))
        d.ellipse([180, 180, 280, 280], fill=(140, 80, 190, 255))
    elif generator == "chair":
        d.rectangle([155, 210, 357, 290], fill=(130, 90, 55, 255))
        d.rectangle([165, 80, 347, 220], fill=(145, 100, 60, 255))
        d.rectangle([170, 285, 205, 455], fill=(110, 75, 45, 255))
        d.rectangle([307, 285, 342, 455], fill=(110, 75, 45, 255))
    elif generator == "lamp":
        d.polygon([(256, 70), (150, 250), (362, 250)], fill=(210, 180, 90, 255))
        d.rectangle([238, 250, 274, 410], fill=(90, 90, 90, 255))
        d.ellipse([170, 390, 342, 455], fill=(80, 80, 80, 255))
    else:
        raise ValueError(f"unknown synthetic image generator: {generator}")
    return img


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("adapter", nargs="?", default="triposr")
    parser.add_argument("case_id", nargs="?", default="image_potion")
    parser.add_argument("--target-polycount", type=int, default=20_000)
    parser.add_argument("--texture-size", type=int, default=1024)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    corpus_version, case = _load_case(args.case_id)
    mode = case["mode"]

    from app.pipeline.base import GenOptions
    from app.pipeline.runner import run_image_to_3d, run_text_to_3d

    peak["used"] = 0
    peak["baseline"] = 0
    stop.clear()
    try:
        peak["baseline"] = _gpu_used()
    except Exception:
        peak["baseline"] = 0
    peak["used"] = peak["baseline"]
    print(f"VRAM budget: {settings.vram_budget_gb} GB")
    print(f"GPU baseline (other processes): {peak['baseline']} MiB")

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    t0 = time.time()
    status = "failed"
    error = None
    error_category = None
    meta = None
    stages: dict[str, float] = {}
    active_stage: str | None = None
    active_stage_started = t0

    def finish_stage(now: float) -> None:
        nonlocal active_stage, active_stage_started
        if active_stage is not None:
            stages[active_stage] = round(stages.get(active_stage, 0.0) + (now - active_stage_started), 3)

    def cb(p, stage, msg):
        nonlocal active_stage, active_stage_started
        now = time.time()
        if stage != active_stage:
            finish_stage(now)
            active_stage = stage
            active_stage_started = now
            print(f"  [{now-t0:6.0f}s] [{p:4.2f}] {stage}: {msg}", flush=True)

    opts = GenOptions(
        adapter=args.adapter,
        target_polycount=args.target_polycount,
        texture_size=args.texture_size,
        seed=args.seed,
    )

    try:
        if mode == "text":
            meta = run_text_to_3d(case["prompt"], opts, cb, lambda: False)
        else:
            img = _synthetic_image(case["generator"])
            p = settings.uploads_dir / f"benchmark_{args.case_id}.png"
            img.save(p)
            meta = run_image_to_3d([p], opts, cb, lambda: False)
        status = "passed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        error_category = getattr(exc, "category", None)
        raise
    finally:
        now = time.time()
        finish_stage(now)
        stop.set()
        monitor_thread.join(timeout=2)
        elapsed = now - t0
        ours = max(0, peak["used"] - peak["baseline"])
        report = {
            "schema_version": 2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "error": error,
            "error_category": error_category,
            "adapter": args.adapter,
            "case_id": args.case_id,
            "corpus_version": corpus_version,
            "case_fingerprint": _case_fingerprint(case),
            "case": case,
            "mode": mode,
            "runtime": runtime_versions(),
            "source_revisions": {
                "assetforge": _git_revision(ROOT),
                "triposr": _git_revision(ROOT / "external" / "TripoSR"),
                "hunyuan3d_2": _git_revision(ROOT / "external" / "Hunyuan3D-2"),
            },
            "settings": {
                "target_polycount": opts.target_polycount,
                "texture_size": opts.texture_size,
                "seed": opts.seed,
                "vram_budget_gb": settings.vram_budget_gb,
            },
            "runtime_seconds": round(elapsed, 3),
            "stage_timings_seconds": stages,
            "gpu": {
                "baseline_mib": peak["baseline"],
                "peak_total_mib": peak["used"],
                "peak_delta_mib": ours,
            },
            "asset_id": meta.get("id") if meta else None,
            "stats": meta.get("stats") if meta else None,
            "textures": meta.get("textures") if meta else None,
            "validation": meta.get("validation") if meta else None,
        }
        out_dir = settings.data_dir / "benchmarks"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = args.output or out_dir / f"real-model-{args.adapter}-{args.case_id}-{stamp}.json"
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nBenchmark report: {out}")
        print(f"Runtime: {elapsed:.0f}s | peak GPU: {peak['used']} MiB total, ~{ours} MiB delta")
        if meta:
            print(f"Asset: {meta['id']} | stats: {meta['stats']} | textures: {meta['textures']}")


if __name__ == "__main__":
    main()

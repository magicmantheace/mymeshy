"""Direct pipeline test for the real (GPU) adapters, with VRAM monitoring.

    python scripts/real_model_test.py triposr|hunyuan3d [image|text]

Peaks above the configured budget mean offloading isn't holding.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

sys.path.insert(0, "backend")

from app.config import get_settings  # noqa: E402  (sets HF_HOME etc.)

settings = get_settings()
print(f"VRAM budget: {settings.vram_budget_gb} GB")

peak = {"used": 0, "baseline": 0}
stop = threading.Event()


def _gpu_used() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5,
    )
    return int(out.stdout.strip().splitlines()[0])


def monitor():
    while not stop.is_set():
        try:
            peak["used"] = max(peak["used"], _gpu_used())
        except Exception:
            pass
        time.sleep(1)


def main():
    adapter = sys.argv[1] if len(sys.argv) > 1 else "triposr"
    mode = sys.argv[2] if len(sys.argv) > 2 else "image"

    from PIL import Image, ImageDraw

    from app.pipeline.base import GenOptions
    from app.pipeline.runner import run_image_to_3d, run_text_to_3d

    try:
        peak["baseline"] = _gpu_used()
    except Exception:
        pass
    print(f"GPU baseline (other processes): {peak['baseline']} MiB")
    threading.Thread(target=monitor, daemon=True).start()
    t0 = time.time()
    status = "failed"
    error = None
    meta = None

    last = {"stage": None}

    def cb(p, stage, msg):
        if stage != last["stage"]:
            last["stage"] = stage
            print(f"  [{time.time()-t0:6.0f}s] [{p:4.2f}] {stage}: {msg}", flush=True)

    opts = GenOptions(adapter=adapter, target_polycount=20000, texture_size=1024)

    try:
        if mode == "text":
            meta = run_text_to_3d("a wooden treasure chest with brass fittings", opts, cb, lambda: False)
        else:
            # synthetic test subject: a simple potion-bottle silhouette
            img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([196, 60, 316, 150], radius=20, fill=(160, 120, 70, 255))
            d.ellipse([130, 130, 382, 430], fill=(90, 40, 130, 255))
            d.ellipse([180, 180, 280, 280], fill=(140, 80, 190, 255))
            p = settings.uploads_dir / "test_potion.png"
            img.save(p)
            meta = run_image_to_3d([p], opts, cb, lambda: False)
        status = "passed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        stop.set()
        elapsed = time.time() - t0
        ours = max(0, peak["used"] - peak["baseline"])
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "error": error,
            "adapter": adapter,
            "mode": mode,
            "settings": {
                "target_polycount": opts.target_polycount,
                "texture_size": opts.texture_size,
                "vram_budget_gb": settings.vram_budget_gb,
            },
            "runtime_seconds": round(elapsed, 3),
            "gpu": {
                "baseline_mib": peak["baseline"],
                "peak_total_mib": peak["used"],
                "peak_delta_mib": ours,
            },
            "asset_id": meta.get("id") if meta else None,
            "stats": meta.get("stats") if meta else None,
            "textures": meta.get("textures") if meta else None,
        }
        out_dir = settings.data_dir / "benchmarks"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = out_dir / f"real-model-{adapter}-{mode}-{stamp}.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nBenchmark report: {out}")
        print(f"Runtime: {elapsed:.0f}s | peak GPU: {peak['used']} MiB total, ~{ours} MiB delta")
        if meta:
            print(f"Asset: {meta['id']} | stats: {meta['stats']} | textures: {meta['textures']}")



if __name__ == "__main__":
    main()

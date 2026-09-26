"""GPU-free smoke test for AssetForge worker process isolation.

Run from the repo root with the normal backend venv:
    .venv\Scripts\python.exe scripts\test_worker_framework.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.workers.launch import (  # noqa: E402
    _WORKER_MODULES,
    _worker_env,
    worker_policy_summary,
)


def main() -> None:
    expected = {"triposr", "hunyuan_shape", "hunyuan_paint"}
    missing = expected.difference(_WORKER_MODULES)
    if missing:
        raise SystemExit(f"missing worker registrations: {sorted(missing)}")

    summary = worker_policy_summary()
    for name in expected:
        assert name in summary, f"{name} missing from worker policy summary"
        assert summary[name]["python"], f"{name} has no Python executable"

    with tempfile.TemporaryDirectory(prefix="assetforge-worker-test-") as td:
        work = Path(td)
        request = work / "request.json"
        result = work / "result.json"
        payload = {"hello": "worker", "parent_pid": os.getpid()}
        request.write_text(json.dumps(payload), encoding="utf-8")

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.workers.echo_worker",
                "--request",
                str(request),
                "--result",
                str(result),
            ],
            cwd=ROOT,
            env=_worker_env("echo"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise SystemExit(f"worker failed: {proc.stderr or proc.stdout}")
        if not result.is_file():
            raise SystemExit("worker did not create result.json")

        response = json.loads(result.read_text(encoding="utf-8"))
        assert response["status"] == "ok"
        assert response["payload"] == payload
        assert response["pid"] != os.getpid(), "worker did not run in a child process"

    print("PASS: worker registry + isolated JSON/file IPC are valid")


if __name__ == "__main__":
    main()

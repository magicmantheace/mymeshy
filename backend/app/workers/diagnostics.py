"""Lightweight runtime/source provenance for isolated worker environments."""
from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

from ..config import REPO_ROOT
from .launch import _EXTERNAL_REPOS, resolve_worker_python

_WORKERS = ("triposr", "hunyuan_shape", "hunyuan_paint")


def _git_revision(path: Path | None) -> str | None:
    if path is None or not (path / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=8)
def _python_runtime(python_executable: str) -> dict:
    path = Path(python_executable)
    if not path.is_file():
        return {
            "python_version": None,
            "torch_version": None,
            "cuda_runtime": None,
            "cuda_available": False,
            "error": f"Python executable not found: {python_executable}",
        }

    code = r'''
import json, sys
info = {
    "python_version": sys.version.split()[0],
    "torch_version": None,
    "cuda_runtime": None,
    "cuda_available": False,
    "error": None,
}
try:
    import torch
    info["torch_version"] = getattr(torch, "__version__", None)
    info["cuda_runtime"] = getattr(getattr(torch, "version", None), "cuda", None)
    info["cuda_available"] = bool(torch.cuda.is_available())
except Exception as exc:
    info["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(info))
'''
    try:
        proc = subprocess.run(
            [python_executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "python_version": None,
            "torch_version": None,
            "cuda_runtime": None,
            "cuda_available": False,
            "error": f"runtime probe failed: {exc}",
        }

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "runtime probe failed").strip()
        return {
            "python_version": None,
            "torch_version": None,
            "cuda_runtime": None,
            "cuda_available": False,
            "error": detail[-500:],
        }
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        return {
            "python_version": None,
            "torch_version": None,
            "cuda_runtime": None,
            "cuda_available": False,
            "error": f"invalid runtime probe output: {exc}",
        }


def worker_runtime_summary() -> dict[str, dict]:
    """Return runtime versions without loading any generation model weights."""
    result: dict[str, dict] = {}
    for name in _WORKERS:
        python_executable = resolve_worker_python(name)
        runtime = dict(_python_runtime(python_executable))
        external = _EXTERNAL_REPOS.get(name)
        runtime.update(
            {
                "python": python_executable,
                "source_revision": _git_revision(external),
            }
        )
        result[name] = runtime
    return result

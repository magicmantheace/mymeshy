"""Subprocess launcher for isolated model workers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

import trimesh
from PIL import Image

from ..config import REPO_ROOT, get_settings
from ..pipeline.base import (
    GenOptions,
    MeshResult,
    constrained_vram,
    hardware_profile_name,
    low_vram,
    runtime_vram_gb,
    vram_budget_gb,
)

_WORKER_MODULES = {
    "triposr": "app.workers.triposr_worker",
}

_EXTERNAL_REPOS = {
    "triposr": REPO_ROOT / "external" / "TripoSR",
}


def isolated_workers_enabled() -> bool:
    """Resolve whether heavy model stages should run in subprocesses."""
    configured = get_settings().isolated_workers
    if configured is not None:
        return bool(configured)
    return hardware_profile_name() == "rtx3060_12gb"


def resolve_worker_python(name: str) -> str:
    """Return the interpreter for a worker, supporting per-model virtualenvs."""
    settings = get_settings()
    raw = {
        "triposr": settings.triposr_worker_python,
    }.get(name, "")
    if not raw:
        return sys.executable
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return str(path)


def _worker_env(name: str, extra_paths: Iterable[Path] = ()) -> dict[str, str]:
    env = os.environ.copy()
    paths = [REPO_ROOT / "backend"]
    external = _EXTERNAL_REPOS.get(name)
    if external is not None:
        paths.append(external)
    paths.extend(extra_paths)
    current = env.get("PYTHONPATH")
    if current:
        env["PYTHONPATH"] = os.pathsep.join([*(str(p) for p in paths), current])
    else:
        env["PYTHONPATH"] = os.pathsep.join(str(p) for p in paths)
    env["MYMESHY_WORKER_CHILD"] = "1"
    return env


def _invoke_worker(
    name: str,
    request_path: Path,
    result_path: Path,
    *,
    python_executable: str | None = None,
    timeout_s: int | None = None,
) -> subprocess.CompletedProcess[str]:
    module = _WORKER_MODULES[name]
    python_executable = python_executable or resolve_worker_python(name)
    python_path = Path(python_executable)
    if not python_path.is_file():
        raise RuntimeError(
            f"{name} worker Python does not exist: {python_executable}. "
            "Run scripts/setup-workers.ps1 or update the matching .env setting."
        )

    timeout_s = timeout_s or get_settings().worker_timeout_sec
    try:
        return subprocess.run(
            [
                python_executable,
                "-m",
                module,
                "--request",
                str(request_path),
                "--result",
                str(result_path),
            ],
            cwd=REPO_ROOT,
            env=_worker_env(name),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{name} worker exceeded the {timeout_s}s timeout and was terminated"
        ) from exc


def probe_worker(name: str) -> tuple[bool, str]:
    """Ask a worker environment whether CUDA and its model runtime are usable."""
    if not isolated_workers_enabled():
        return False, "isolated workers are disabled"

    module = _WORKER_MODULES.get(name)
    if module is None:
        return False, f"no isolated worker registered for {name}"

    python_executable = resolve_worker_python(name)
    if not Path(python_executable).is_file():
        return False, f"worker Python not found: {python_executable}"

    try:
        proc = subprocess.run(
            [python_executable, "-m", module, "--probe"],
            cwd=REPO_ROOT,
            env=_worker_env(name),
            capture_output=True,
            text=True,
            timeout=min(get_settings().worker_timeout_sec, 30),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"worker probe failed: {exc}"

    if proc.returncode == 0:
        return True, ""

    detail = (proc.stderr or proc.stdout or "worker probe failed").strip()
    return False, detail[-500:]


def run_triposr_worker(
    images: Sequence[Image.Image],
    opts: GenOptions,
    progress,
) -> MeshResult:
    """Run TripoSR in a short-lived child process and rehydrate its mesh."""
    settings = get_settings()
    settings.workers_dir.mkdir(parents=True, exist_ok=True)

    progress(0.03, "Starting isolated TripoSR worker")
    with tempfile.TemporaryDirectory(prefix="triposr-", dir=settings.workers_dir) as td:
        workspace = Path(td)
        input_paths: list[str] = []
        for index, image in enumerate(images):
            path = workspace / f"input_{index}.png"
            image.convert("RGBA").save(path)
            input_paths.append(str(path))

        if low_vram():
            chunk_size, resolution = 2048, 192
        elif constrained_vram():
            chunk_size, resolution = 4096, 224
        else:
            chunk_size, resolution = 8192, 256

        request = {
            "images": input_paths,
            "seed": opts.seed,
            "chunk_size": chunk_size,
            "resolution": resolution,
            "hard_cap_gb": vram_budget_gb(),
            "runtime_vram_gb": runtime_vram_gb(),
            "output_mesh": str(workspace / "mesh.glb"),
        }
        request_path = workspace / "request.json"
        result_path = workspace / "result.json"
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

        progress(0.08, f"TripoSR worker running ({resolution} extraction)")
        proc = _invoke_worker("triposr", request_path, result_path)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "no worker output").strip()
            raise RuntimeError(f"TripoSR worker failed: {detail[-2000:]}")

        if not result_path.is_file():
            raise RuntimeError("TripoSR worker exited without writing result.json")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "ok":
            raise RuntimeError(
                f"TripoSR worker failed: {result.get('error', 'unknown error')}"
            )

        mesh_path = Path(result["mesh_path"])
        if not mesh_path.is_file():
            raise RuntimeError(f"TripoSR worker mesh is missing: {mesh_path}")

        loaded = trimesh.load(mesh_path, force="mesh")
        if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
            raise RuntimeError("TripoSR worker produced an invalid triangle mesh")

        progress(1.0, "Isolated TripoSR worker complete")
        return MeshResult(
            mesh=loaded,
            textured=False,
            extras={
                "worker": "triposr",
                "isolated": True,
                "worker_pid": result.get("pid"),
                "chunk_size": chunk_size,
                "resolution": resolution,
            },
        )


def worker_policy_summary() -> dict:
    """Serializable worker policy for /api/system."""
    settings = get_settings()
    python_executable = resolve_worker_python("triposr")
    try:
        separate = Path(python_executable).resolve() != Path(sys.executable).resolve()
    except OSError:
        separate = python_executable != sys.executable
    return {
        "enabled": isolated_workers_enabled(),
        "timeout_sec": settings.worker_timeout_sec,
        "triposr": {
            "python": python_executable,
            "separate_environment": separate,
        },
    }

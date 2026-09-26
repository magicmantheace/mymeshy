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
    "hunyuan_shape": "app.workers.hunyuan_shape_worker",
    "hunyuan_paint": "app.workers.hunyuan_paint_worker",
}

_EXTERNAL_REPOS = {
    "triposr": REPO_ROOT / "external" / "TripoSR",
    "hunyuan_shape": REPO_ROOT / "external" / "Hunyuan3D-2",
    "hunyuan_paint": REPO_ROOT / "external" / "Hunyuan3D-2",
}

_SHAPE_SUBFOLDERS = {
    "Hunyuan3D-2": "hunyuan3d-dit-v2-0",
    "Hunyuan3D-2mini": "hunyuan3d-dit-v2-mini",
    "Hunyuan3D-2mv": "hunyuan3d-dit-v2-mv",
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
        "hunyuan_shape": settings.hunyuan_shape_worker_python,
        "hunyuan_paint": settings.hunyuan_paint_worker_python,
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


def _read_worker_result(
    name: str,
    proc: subprocess.CompletedProcess[str],
    result_path: Path,
) -> dict:
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "no worker output").strip()
        raise RuntimeError(f"{name} worker failed: {detail[-2000:]}")
    if not result_path.is_file():
        raise RuntimeError(f"{name} worker exited without writing result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "ok":
        raise RuntimeError(f"{name} worker failed: {result.get('error', 'unknown error')}")
    return result


def _load_mesh_result(
    mesh_path: Path,
    *,
    textured: bool,
    extras: dict,
    albedo_path: Path | None = None,
) -> MeshResult:
    if not mesh_path.is_file():
        raise RuntimeError(f"worker mesh is missing: {mesh_path}")
    loaded = trimesh.load(mesh_path, force="mesh")
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise RuntimeError("worker produced an invalid triangle mesh")

    albedo = None
    if textured and albedo_path is not None and albedo_path.is_file():
        with Image.open(albedo_path) as image:
            albedo = image.convert("RGB").copy()
    elif textured:
        material = getattr(getattr(loaded, "visual", None), "material", None)
        if material is not None:
            albedo = getattr(material, "baseColorTexture", None)
            if albedo is None:
                albedo = getattr(material, "image", None)
    return MeshResult(
        mesh=loaded,
        albedo=albedo,
        textured=textured and albedo is not None,
        extras=extras,
    )


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
        result = _read_worker_result("triposr", proc, result_path)

        progress(1.0, "Isolated TripoSR worker complete")
        return _load_mesh_result(
            Path(result["mesh_path"]),
            textured=False,
            extras={
                "worker": "triposr",
                "isolated": True,
                "worker_pid": result.get("pid"),
                "chunk_size": chunk_size,
                "resolution": resolution,
            },
        )


def run_hunyuan_shape_worker(
    images: Sequence[Image.Image],
    opts: GenOptions,
    progress,
) -> MeshResult:
    """Run Hunyuan shape generation in a process that exits before paint starts."""
    settings = get_settings()
    settings.workers_dir.mkdir(parents=True, exist_ok=True)

    shape_model = os.environ.get("MYMESHY_HUNYUAN_SHAPE_MODEL", "tencent/Hunyuan3D-2mini")
    shape_subfolder = os.environ.get(
        "MYMESHY_HUNYUAN_SHAPE_SUBFOLDER",
        _SHAPE_SUBFOLDERS.get(shape_model.split("/")[-1], "hunyuan3d-dit-v2-0"),
    )

    progress(0.02, "Starting isolated Hunyuan shape worker")
    with tempfile.TemporaryDirectory(prefix="hunyuan-shape-", dir=settings.workers_dir) as td:
        workspace = Path(td)
        image_path = workspace / "reference.png"
        images[0].convert("RGBA").save(image_path)
        output_mesh = workspace / "shape.glb"
        request = {
            "image": str(image_path),
            "seed": opts.seed,
            "shape_model": shape_model,
            "shape_subfolder": shape_subfolder,
            "target_polycount": opts.target_polycount,
            "low_vram": low_vram(),
            "hard_cap_gb": vram_budget_gb(),
            "runtime_vram_gb": runtime_vram_gb(),
            "output_mesh": str(output_mesh),
        }
        request_path = workspace / "request.json"
        result_path = workspace / "result.json"
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

        progress(0.08, f"Hunyuan shape worker loading {shape_model}")
        proc = _invoke_worker("hunyuan_shape", request_path, result_path)
        result = _read_worker_result("hunyuan_shape", proc, result_path)
        progress(1.0, "Isolated Hunyuan shape worker complete")
        return _load_mesh_result(
            Path(result["mesh_path"]),
            textured=False,
            extras={
                "worker": "hunyuan_shape",
                "isolated": True,
                "worker_pid": result.get("pid"),
                "shape_model": shape_model,
            },
        )


def run_hunyuan_paint_worker(
    mesh: trimesh.Trimesh,
    image: Image.Image,
    opts: GenOptions,
    progress,
) -> MeshResult:
    """Paint a mesh in a fresh process after the shape process has exited."""
    settings = get_settings()
    settings.workers_dir.mkdir(parents=True, exist_ok=True)
    paint_model = os.environ.get("MYMESHY_HUNYUAN_PAINT_MODEL", "tencent/Hunyuan3D-2")

    progress(0.02, "Starting isolated Hunyuan paint worker")
    with tempfile.TemporaryDirectory(prefix="hunyuan-paint-", dir=settings.workers_dir) as td:
        workspace = Path(td)
        input_mesh = workspace / "input.glb"
        reference = workspace / "reference.png"
        output_mesh = workspace / "painted.glb"
        mesh.export(input_mesh)
        image.convert("RGBA").save(reference)
        request = {
            "mesh": str(input_mesh),
            "image": str(reference),
            "paint_model": paint_model,
            "hard_cap_gb": vram_budget_gb(),
            "runtime_vram_gb": runtime_vram_gb(),
            "output_mesh": str(output_mesh),
        }
        request_path = workspace / "request.json"
        result_path = workspace / "result.json"
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

        progress(0.08, f"Hunyuan paint worker loading {paint_model}")
        proc = _invoke_worker("hunyuan_paint", request_path, result_path)
        result = _read_worker_result("hunyuan_paint", proc, result_path)
        progress(1.0, "Isolated Hunyuan paint worker complete")
        albedo_raw = result.get("albedo_path")
        return _load_mesh_result(
            Path(result["mesh_path"]),
            textured=True,
            albedo_path=Path(albedo_raw) if albedo_raw else None,
            extras={
                "worker": "hunyuan_paint",
                "isolated": True,
                "worker_pid": result.get("pid"),
                "paint_model": paint_model,
            },
        )


def worker_policy_summary() -> dict:
    """Serializable worker policy for /api/system."""
    settings = get_settings()
    workers: dict[str, dict] = {}
    for name in ("triposr", "hunyuan_shape", "hunyuan_paint"):
        python_executable = resolve_worker_python(name)
        try:
            separate = Path(python_executable).resolve() != Path(sys.executable).resolve()
        except OSError:
            separate = python_executable != sys.executable
        workers[name] = {
            "python": python_executable,
            "separate_environment": separate,
        }
    return {
        "enabled": isolated_workers_enabled(),
        "timeout_sec": settings.worker_timeout_sec,
        **workers,
    }

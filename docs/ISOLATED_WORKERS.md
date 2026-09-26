# Isolated model workers

AssetForge can run heavyweight AI backends in short-lived subprocesses instead of loading every model into the FastAPI process.

## Why

On the RTX 3060 12GB reference profile, releasing a Python model object does not always return every CUDA allocation immediately. A subprocess has a stronger boundary: when it exits, its CUDA context, allocator state, and model imports disappear with it.

This also lets model backends use separate virtual environments when their PyTorch, CUDA-extension, or package requirements conflict.

## v1 scope

The first migrated backend is **TripoSR**.

Parent process:

1. prepares input PNGs and a JSON request in `data/workers/`
2. launches the configured TripoSR worker Python
3. waits for the child to generate a GLB and `result.json`
4. reloads the GLB as a normal `MeshResult`
5. continues the existing cleanup/UV/PBR/export pipeline

Child process:

1. probes CUDA + `tsr`
2. loads TripoSR
3. generates and extracts the mesh
4. writes a GLB
5. exits, releasing its CUDA context

## RTX 3060 defaults

When `MYMESHY_ISOLATED_WORKERS` is unset, the `rtx3060_12gb` hardware profile enables isolated workers automatically.

TripoSR keeps the existing 12GB tuning:

- renderer chunk size: `4096`
- extraction resolution: `224`

The <=8GB tier remains `2048 / 192`, while larger cards retain `8192 / 256`.

## Dedicated TripoSR environment

Windows:

```powershell
.\scripts\setup-workers.ps1
```

Then add to `.env`:

```text
MYMESHY_ISOLATED_WORKERS=true
MYMESHY_TRIPOSR_WORKER_PYTHON=.workers\triposr\Scripts\python.exe
```

If `MYMESHY_TRIPOSR_WORKER_PYTHON` is unset, the child uses the backend's current Python interpreter. This still isolates the process/CUDA context, but not package dependencies.

## Tests

The subprocess IPC contract can be verified without a GPU:

```powershell
.venv\Scripts\python.exe scripts\test_worker_framework.py
```

The test sends JSON through files to a child process and verifies that the child PID differs from the backend/test PID.

A real GPU validation should then run the existing real-model test with TripoSR selected and watch `nvidia-smi` after the image-to-3D stage to confirm worker VRAM disappears after process exit.

## Next migrations

1. Hunyuan shape worker
2. Hunyuan Paint worker
3. SDXL concept worker if measured VRAM pressure justifies it
4. TRELLIS.2 low-VRAM worker in its own environment

Each worker should preserve the same request/result boundary rather than importing one model environment into another.

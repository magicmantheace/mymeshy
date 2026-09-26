# Isolated model workers

AssetForge can run heavyweight AI backends in short-lived subprocesses instead of loading every model into the FastAPI process.

## Why

On the RTX 3060 12GB reference profile, releasing a Python model object does not always return every CUDA allocation immediately. A subprocess has a stronger boundary: when it exits, its CUDA context, allocator state, and model imports disappear with it.

This also lets model backends use separate virtual environments when their PyTorch, CUDA-extension, or package requirements conflict.

## Current scope

Three heavy stages now support isolated execution:

- **TripoSR** image-to-3D
- **Hunyuan Shape** image-to-geometry
- **Hunyuan Paint** mesh + reference image to textured mesh

The Hunyuan image-to-3D sequence is deliberately split into two different processes:

```text
reference image
    -> Hunyuan Shape worker
    -> intermediate GLB
    -> Shape worker exits (CUDA context destroyed)
    -> Hunyuan Paint worker
    -> textured GLB + albedo
    -> Paint worker exits (CUDA context destroyed)
    -> normal AssetForge post-processing
```

Shape and Paint may share the same `.workers/hunyuan` virtualenv, but they never share a Python process or CUDA context.

If the Paint worker is unavailable (for example because `custom_rasterizer` has not been compiled), Hunyuan Shape still works and AssetForge falls back to the existing geometry-only/reference-projection path.

## Parent/child contract

The parent process:

1. prepares input files and a JSON request under `data/workers/`
2. launches the configured worker Python
3. waits for `result.json` plus an intermediate GLB
4. reloads the GLB as a normal `MeshResult`
5. continues the existing pipeline

A model child process:

1. configures its allocator before model loading
2. probes CUDA + its model runtime
3. loads exactly one heavy model stage
4. produces its intermediate result
5. exits, releasing the complete CUDA context

## RTX 3060 defaults

When `MYMESHY_ISOLATED_WORKERS` is unset, the `rtx3060_12gb` hardware profile enables isolated workers automatically.

TripoSR keeps the existing 12GB tuning:

- renderer chunk size: `4096`
- extraction resolution: `224`

The <=8GB tier remains `2048 / 192`, while larger cards retain `8192 / 256`.

Hunyuan uses the mini shape model by default. Shape and Paint are never resident at the same time on the isolated path.

## Windows setup

Run:

```powershell
.\scripts\setup-workers.ps1
```

This creates:

```text
.workers\triposr\
.workers\hunyuan\
```

Add to `.env`:

```text
MYMESHY_ISOLATED_WORKERS=true
MYMESHY_TRIPOSR_WORKER_PYTHON=.workers\triposr\Scripts\python.exe
MYMESHY_HUNYUAN_SHAPE_WORKER_PYTHON=.workers\hunyuan\Scripts\python.exe
MYMESHY_HUNYUAN_PAINT_WORKER_PYTHON=.workers\hunyuan\Scripts\python.exe
```

### Enabling Hunyuan Paint

Shape generation does not require Hunyuan Paint's compiled renderer. Paint does.

After installing the NVIDIA CUDA toolkit and Visual Studio C++ build tools, run:

```powershell
.\scripts\setup-workers.ps1 -CompileHunyuanPaint
```

That builds Hunyuan's `custom_rasterizer` and `differentiable_renderer` inside the Hunyuan worker environment. If they are absent, `/api/system` will show Hunyuan Paint as unavailable while Shape remains usable.

## Runtime inspection

`GET /api/system` now includes a `workers` object showing:

- whether isolation is enabled
- worker timeout
- Python executable for TripoSR
- Python executable for Hunyuan Shape
- Python executable for Hunyuan Paint
- whether each executable is separate from the backend interpreter

This should be checked before GPU benchmarking.

## Tests

The subprocess IPC contract can be verified without a GPU:

```powershell
.venv\Scripts\python.exe scripts\test_worker_framework.py
```

A real RTX 3060 validation should then monitor `nvidia-smi` across these boundaries:

1. baseline
2. Hunyuan Shape running
3. Shape process exit / return to baseline
4. Hunyuan Paint running
5. Paint process exit / return to baseline

The most important success criterion is that Shape VRAM is gone before Paint starts.

## Next migrations

1. benchmark Hunyuan Shape/Paint on the RTX 3060 and tune settings
2. add the TRELLIS.2 low-VRAM worker in its own environment
3. isolate SDXL concept generation only if measurements show it is useful
4. replace placeholder texture rebaking with proper material preservation / texel-space baking

Each worker should preserve the same file + JSON boundary rather than importing one model environment into another.

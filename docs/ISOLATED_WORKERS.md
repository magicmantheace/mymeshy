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

The setup requires both `uv` and Git. It is safe to rerun: existing shallow
TripoSR and Hunyuan3D-2 checkouts are fetched and reset to their current
upstream default branch, while non-Git directories at those paths are rejected
instead of silently reused. The script prints the exact source commit installed
for each model so a benchmark can be tied to the code that produced it.

The setup script writes the isolation flag and worker Python paths into `.env`
automatically. Existing unrelated settings are preserved, and rerunning setup
updates each worker key in place instead of appending duplicates.

### Enabling Hunyuan Paint

Shape generation does not require Hunyuan Paint's compiled renderer. Paint does.

After installing the NVIDIA CUDA toolkit and Visual Studio C++ build tools, run:

```powershell
.\scripts\setup-workers.ps1 -CompileHunyuanPaint
```

That builds Hunyuan's `custom_rasterizer` and `differentiable_renderer` inside the Hunyuan worker environment. If they are absent, `/api/system` will show Hunyuan Paint as unavailable while Shape remains usable.

## Runtime inspection

`GET /api/system` includes a `workers` object showing:

- whether isolation is enabled
- worker timeout
- Python executable for TripoSR, Hunyuan Shape, and Hunyuan Paint
- whether each executable is separate from the backend interpreter
- whether the configured Python executable exists
- whether the required external model source checkout exists
- a `configured` summary combining those static checks
- lightweight worker runtime provenance: Python version, Torch version, Torch
  CUDA runtime, CUDA visibility, and external source revision

The runtime provenance probe does **not** load generation model weights. It only
starts the configured worker Python and imports Torch. Model/runtime availability
is still determined by each worker's dedicated `--probe` path and is exposed in
the adapter availability section of `/api/system`.

This distinction matters: a worker can have a valid Python/Torch/CUDA environment
while a model-specific dependency or compiled extension is still missing.

The same lightweight provenance can be written directly with:

```powershell
.venv\Scripts\python.exe scripts\worker-runtime-info.py
```

The Windows doctor uses this information before benchmarking and the benchmark
suite stores it once per run in `worker-runtimes.json`.

## Tests

The subprocess IPC and runtime-provenance contracts can be verified without
loading generation models:

```powershell
.venv\Scripts\python.exe scripts\test_worker_framework.py
.venv\Scripts\python.exe scripts\test_worker_runtime_diagnostics.py
```

A real RTX 3060 validation should then monitor `nvidia-smi` across these boundaries:

1. baseline
2. Hunyuan Shape running
3. Shape process exit / return to baseline
4. Hunyuan Paint running
5. Paint process exit / return to baseline

The most important success criterion is that Shape VRAM is gone before Paint starts.

## Remaining worker work

1. benchmark Hunyuan Shape/Paint and TripoSR on the target RTX 3060
2. add a TRELLIS.2 quality worker only if upstream/runtime validation supports a practical 12GB configuration
3. isolate SDXL concept generation only if measurements show it materially improves VRAM recovery

Native adapter albedo + UV layouts and native normal, metallic-roughness, and
occlusion channels are now preserved when available. Missing material channels
continue through the deterministic fallback path.

Each future worker should preserve the same file + JSON boundary rather than importing one model environment into another.

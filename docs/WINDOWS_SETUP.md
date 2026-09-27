# Windows fresh setup and first real-model validation

This is the preferred setup path for a fresh Windows machine, including the RTX
3060 12 GB reference configuration. It separates the lightweight backend from
heavy image-to-3D model environments and deliberately stops short of claiming
that a real model fits or performs well until the validation scripts are run on
the target GPU.

## 1. Prerequisites

Install:

- current NVIDIA driver
- Git for Windows
- Node.js 18 or newer with npm
- PowerShell

`uv` and Python 3.11 are provisioned by the repository setup script, so a system
Python install is not required.

Hunyuan Shape and TripoSR do not require a local CUDA toolkit merely to use the
PyTorch CUDA wheels. **Hunyuan Paint compilation** additionally requires a
compatible NVIDIA CUDA toolkit and Visual Studio C++ build tools.

## 2. Base application setup

From the repository root:

```powershell
.\scripts\setup.ps1
```

This creates `.venv`, installs the FastAPI/backend and MCP dependencies, and
installs the frontend packages with `npm ci`. At this point the application can
run in mock mode without model downloads.

## 3. Real-model software setup

Run:

```powershell
.\scripts\install-models.ps1
```

The script installs the backend CUDA/ML packages needed by SDXL-Turbo, then
calls `setup-workers.ps1` to create isolated environments for:

- `.workers\triposr`
- `.workers\hunyuan`

TripoSR and Hunyuan3D-2 source are installed at the exact revisions committed in
`backend\model-sources.json`. Rerunning setup keeps those source revisions fixed
unless that lock file is intentionally changed. The setup verifies the checked
out SHA, prints it, and runtime diagnostics compare the installed revision with
the expected lock so accidental source drift is visible before benchmarking.

The locks make setup reproducible; they are **not** evidence that a revision has
met an RTX 3060 performance target. Any intentional source-lock update should be
followed by the same real-model validation/benchmark process before tuned
defaults are changed.

The setup also writes the worker Python paths plus
`MYMESHY_ISOLATED_WORKERS=true` into `.env` without replacing unrelated values.

Do not manually install TripoSR/Hunyuan requirements into the backend venv on
the RTX 3060 path. The isolated worker boundary is intentional: each heavy
model stage gets a fresh process/CUDA context and can use its own dependencies.

### Optional Hunyuan Paint compilation

After installing the CUDA toolkit and Visual Studio C++ build tools:

```powershell
.\scripts\install-models.ps1 -CompileHunyuanPaint
```

Without those compiled extensions, Hunyuan Shape can still generate geometry.
If Paint is unavailable, the image-to-3D path records the degradation and uses
the existing reference-projection fallback rather than pretending Paint ran.

## 4. Readiness checks

Before attempting a real generation:

```powershell
.\scripts\doctor.ps1
.\scripts\test-control-plane.ps1
```

The doctor checks the machine/runtime configuration, including NVIDIA visibility,
isolated-worker Python/Torch/CUDA provenance, and external source revisions. The
control-plane suite checks repository contracts without loading generation models.

Neither command is a substitute for a physical real-model run.

## 5. Start the app

```powershell
.\scripts\dev.ps1
```

Then inspect:

```powershell
irm http://127.0.0.1:8420/api/system | ConvertTo-Json -Depth 8
```

Confirm the detected hardware profile, worker configuration/runtime details,
source-lock status, adapter readiness, and generation-preset availability before
the first run.

## 6. First real-model evidence

For a single controlled case:

```powershell
.venv\Scripts\python.exe scripts\real_model_test.py triposr image_potion
```

For the committed pre-tuning matrix:

```powershell
.\scripts\run-benchmark-suite.ps1
```

The suite records hardware/runtime/source provenance, stage timings, VRAM,
validation results, structured failures, and clean versus degraded passes. Use
those reports to tune the RTX 3060 defaults; do not change thresholds based on
assumptions before the baseline evidence exists.

## Repair path

The setup scripts are intended to be safe to rerun. If readiness checks fail:

1. rerun `setup.ps1` for the base app/frontend,
2. rerun `install-models.ps1` for base ML + isolated workers at the committed source locks,
3. rerun `doctor.ps1`,
4. only then investigate the specific remaining failure reported by the doctor
   or `/api/system`.

Keep both the expected lock and actual source revision shown by diagnostics and
benchmark reports when comparing results across setup changes.

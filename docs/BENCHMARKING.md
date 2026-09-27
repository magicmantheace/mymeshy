# Reproducible benchmark workflow

This repository separates **benchmark infrastructure** from **benchmark evidence**.
The scripts below are committed before tuning so later settings changes can be
based on recorded RTX 3060 results rather than assumptions.

## Before any real-model run

From the repository root on Windows:

```powershell
.\scripts\doctor.ps1
.\scripts\test-control-plane.ps1
```

The doctor checks machine/setup readiness. The control-plane suite is GPU-free.
Neither command proves that a real model fits in 12 GB.

## Stable inputs

`benchmarks/corpus.json` defines stable case IDs. The current corpus contains
three text prompts and three deterministic synthetic image references.

`benchmarks/suite.json` defines the default matrix of adapters, cases, seed,
target polycount, and texture size. These values are deliberately **untuned
starting points**. Do not change them merely to make a failed run pass; collect
the baseline evidence first and introduce a new suite version when comparing a
new policy.

Each case has a fingerprint in its report so accidental input drift is visible.

## One-command suite

```powershell
.\scripts\run-benchmark-suite.ps1
```

A run creates a timestamped directory under `data/benchmarks/` containing:

- `hardware.json` — GPU, driver, `/api/system`, and source revisions
- `worker-runtimes.json` — configured worker Python, Python/Torch/CUDA versions,
  CUDA visibility, and external source revision for TripoSR and Hunyuan workers
- one `real-model-<adapter>-<case>.json` report per matrix entry
- `benchmark-summary.json`
- `benchmark-summary.csv`

Individual model reports include:

- exact corpus case and fingerprint
- adapter and settings
- source revisions
- backend Python, Torch, and CUDA runtime provenance
- total runtime
- per-stage timings
- GPU baseline, total peak, and peak delta
- structured failure category when available
- finished-asset stats and validation result

Worker-environment runtime versions are captured once per suite instead of once
per case so the provenance probe does not add repeated setup overhead to the
matrix. `/api/system` exposes the same worker runtime information when the
backend is running.

The suite continues after an individual model failure so OOMs, dependency
failures, and malformed outputs are retained as evidence rather than aborting
the entire matrix.

## Single-case investigation

```powershell
.venv\Scripts\python.exe scripts\real_model_test.py triposr image_potion
.venv\Scripts\python.exe scripts\real_model_test.py hunyuan3d image_chair
```

Use explicit overrides only when intentionally testing a hypothesis:

```powershell
.venv\Scripts\python.exe scripts\real_model_test.py triposr image_potion `
  --target-polycount 20000 --texture-size 1024 --seed 12345
```

To inspect isolated worker versions without running generation models:

```powershell
.venv\Scripts\python.exe scripts\worker-runtime-info.py
```

## Rebuild a summary

```powershell
.venv\Scripts\python.exe scripts\benchmark_summary.py data\benchmarks\suite-YYYYMMDD-HHMMSS
```

The aggregator does not rank adapters or select tuning values. It produces a
compact evidence table that can later be compared deliberately.

## Evidence rule

Do not describe a preset as validated, change RTX 3060 defaults from measured
performance, or promote a new quality backend until real reports from the target
machine exist. Repository-side tests prove contracts and failure handling; they
are not substitutes for physical CUDA execution.

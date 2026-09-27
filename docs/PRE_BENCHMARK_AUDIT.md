# Pre-benchmark readiness audit

This document defines when AssetForge/MyMeshy is ready to stop speculative
software tuning and move to physical RTX 3060 evidence. It intentionally does
not claim model speed, VRAM fit, or output quality until those measurements
exist on the target machine.

## Ready in repository architecture

The following are implemented and should not be retuned merely from assumptions:

- isolated TripoSR, Hunyuan Shape, and Hunyuan Paint worker processes
- RTX 3060 hardware profile with heavyweight stage unloading
- legacy TRELLIS excluded from RTX 3060 Auto while remaining explicit opt-in
- backend-native Fast / Balanced / Quality workload presets
- named preset and effective-option provenance across frontend, REST, and MCP
- generation-boundary checkpoints and post-processing resume
- failed/restarted job discovery with durable resumable asset links
- structured worker failure categories
- Hunyuan Shape salvage when Paint has a known operational failure, with
  degraded-result provenance instead of a false clean success
- native albedo/UV preservation and native normal/metallic-roughness/occlusion
  preservation when supplied by an adapter
- deterministic fallback texture/PBR paths when native channels are missing
- finished-asset structural validation plus serialized GLB reload validation
- API/UI/MCP access to every texture-map name the pipeline can publish
- runtime/system diagnostics for backend and isolated worker Python/Torch/CUDA
- exact external TripoSR/Hunyuan source revision locks and drift detection
- consolidated Windows base + real-model setup flow and readiness doctor
- stable benchmark corpus, versioned suite, per-stage timing, VRAM monitoring,
  JSON/CSV summaries, source/runtime provenance, and clean/degraded/failure counts
- end-to-end smoke coverage for validation and checkpoint resume
- GPU-free control-plane contracts covering hardware policy, presets, workers,
  checkpoint/restart recovery, asset validation, frontend/MCP contracts, and
  Windows install structure

## Execution verification still required

These are software checks, not GPU benchmarks. They should be green before the
first real-model evidence run:

1. Windows GPU-free control-plane suite:

   ```powershell
   .\scripts\test-control-plane.ps1
   ```

2. Frontend TypeScript/Vite production build:

   ```powershell
   cd frontend
   npm ci
   npm run build
   ```

3. Fresh/repaired Windows setup path:

   ```powershell
   .\scripts\setup.ps1
   .\scripts\install-models.ps1
   .\scripts\doctor.ps1
   ```

4. Optional Hunyuan Paint compilation path, when the CUDA toolkit and Visual
   Studio C++ build tools are present:

   ```powershell
   .\scripts\install-models.ps1 -CompileHunyuanPaint
   .\scripts\doctor.ps1
   ```

A passing software verification run proves repository/setup contracts execute on
Windows. It still does not prove that a real generation model fits in 12 GB.

## Physical RTX 3060 evidence required

These items cannot be closed honestly from repository-side inspection alone:

- actual TripoSR startup/generation success on the target RTX 3060 12 GB
- actual Hunyuan Shape startup/generation success
- actual Hunyuan Paint startup/generation success when compiled
- confirmation that Shape CUDA memory is released before Paint starts
- wall-clock runtime by stable benchmark case and stage
- baseline/peak/delta GPU memory per run
- host RAM behavior and any paging pressure worth acting on
- observed CUDA OOM/fallback frequency
- output quality differences between adapters/presets
- whether current Fast/Balanced/Quality values should be changed
- whether SDXL text-to-image isolation materially improves memory recovery
- whether any practical TRELLIS.2 configuration is supportable on this machine

No preset should be described as RTX-3060 validated until this evidence exists.

## Physical validation sequence

On the target Windows machine, from a clean/current checkout:

```powershell
.\scripts\setup.ps1
.\scripts\install-models.ps1
.\scripts\doctor.ps1
.\scripts\test-control-plane.ps1
.\scripts\dev.ps1
```

Inspect the running system contract:

```powershell
irm http://127.0.0.1:8420/api/system | ConvertTo-Json -Depth 8
```

Then run one controlled real-model case before the whole matrix:

```powershell
.venv\Scripts\python.exe scripts\real_model_test.py triposr image_potion
```

If that produces a valid evidence report, execute the committed pre-tuning suite:

```powershell
.\scripts\run-benchmark-suite.ps1
```

Do not modify benchmark defaults halfway through the baseline run merely to make
a failing case pass. Preserve the failure as evidence, then create an intentional
new configuration/suite version for the hypothesis being tested.

## Tuning phase starts only after baseline evidence

After the first complete evidence set exists, tuning work may include:

- choose evidence-backed TripoSR resolution/chunk settings
- choose evidence-backed Hunyuan low-memory/offload behavior
- revise Fast/Balanced/Quality workload values
- decide whether automatic fallbacks should change
- compare cold versus warm behavior where meaningful
- identify regressions after model-source or dependency changes

Every tuning change should retain the benchmark corpus, case fingerprints,
runtime/source revisions, and validation reports needed to compare before/after.

## Optional enhancements that do not block first benchmarks

Useful future work, but not required to begin evidence collection:

- optional headless Blender deep QA beyond deterministic GLB validation
- richer post-processing transformation provenance in benchmark summaries
- first-class multi-material preservation through post-processing/export
- additional asset-library provenance/validation presentation
- broader benchmark corpus after the initial engineering matrix is stable
- a validated TRELLIS.2 quality worker if upstream/runtime evidence makes a
  12 GB path practical

## Stop condition

Pre-benchmark software work is complete enough to begin physical validation when:

- the Windows control-plane suite executes successfully,
- the frontend production build succeeds,
- the documented Windows install/doctor path is coherent,
- no normal-use software blocker is known in text/image-to-3D generation,
  checkpoint recovery, validation, or export,
- and all remaining required questions are measurements that need the target
  RTX 3060 rather than more speculative code changes.

At that point, prefer collecting evidence over adding new tuning logic.

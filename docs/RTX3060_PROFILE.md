# AssetForge RTX 3060 12GB profile

This fork treats the RTX 3060 12GB as a reference GPU instead of an accidental middle tier between generic and <=8GB modes.

## Goals

- Use most of the available 12GB VRAM when one model is active.
- Never keep heavyweight pipeline stages resident together when avoidable.
- Preserve better quality settings than the <=8GB fallback.
- Prefer adapters that are realistic on a 12GB card when `auto` is selected.
- Keep explicit adapter selection available for benchmarking and experimentation.

## Current policy

When `MYMESHY_HARDWARE_PROFILE=auto`, an NVIDIA GPU whose name contains `RTX 3060` and whose detected VRAM is approximately 12GB resolves to `rtx3060_12gb`.

That profile currently:

1. Forces heavyweight adapters to unload after their stage.
2. Unloads Hunyuan shape before Hunyuan Paint is loaded.
3. Uses a middle TripoSR renderer chunk size of 4096 instead of the generic 8192 or <=8GB 2048 value.
4. Uses TripoSR extraction resolution 224 instead of generic 256 or <=8GB 192.
5. Changes `auto` image-to-3D preference to Hunyuan3D -> TripoSR -> legacy TRELLIS -> mock.

Legacy TRELLIS remains available when explicitly requested. It is intentionally not the automatic first choice for this hardware profile because the current in-process TRELLIS adapter is not designed around 12GB operation. Official TRELLIS.2 is also not promoted on this profile: upstream currently documents Linux-only testing and a 24GB minimum. See `TRELLIS2_RTX3060.md` for the evidence gate.

## Important distinction: scheduling vs hard cap

`MYMESHY_VRAM_BUDGET_GB` remains an optional hard cap on torch allocations. It is **not** required to enable the RTX 3060 scheduling profile.

This lets a 12GB card use most of its memory for the active stage while still releasing that stage before the next large model is loaded.

## Overrides

```env
MYMESHY_HARDWARE_PROFILE=rtx3060_12gb
MYMESHY_FORCE_STAGE_UNLOAD=true
MYMESHY_VRAM_BUDGET_GB=0
```

Use `MYMESHY_HARDWARE_PROFILE=generic` to disable automatic RTX 3060 behavior for comparison testing.

## Current implementation status

Implemented for the RTX 3060 reference profile:

- isolated TripoSR, Hunyuan Shape, and Hunyuan Paint worker processes
- generation-boundary checkpoints with post-processing resume
- structured real-model/hardware benchmark reports with source revisions
- one-shot TripoSR CUDA-OOM fallback to the 192 / 2048 low-memory preset
- finished-asset structural validation before jobs are marked successful
- native albedo/UV plus normal, metallic-roughness, and occlusion preservation when adapters supply them
- user-facing Fast / Balanced / Quality workload presets that stay within the currently supported adapter set
- failed-job discovery and UI retry for generation checkpoints
- Windows isolated-worker setup that persists its worker paths into `.env`

Still requires repository work or physical validation:

- benchmark Hunyuan Shape/Paint and TripoSR on the target RTX 3060 and tune from evidence
- add a validated TRELLIS.2 quality worker if upstream/runtime testing proves 12GB practical
- add deeper Blender geometry/material QA where it catches issues the deterministic validator cannot
- isolate SDXL concept generation only if measurements show process isolation materially helps

## TripoSR OOM recovery

The RTX 3060 profile normally runs isolated TripoSR at extraction resolution
`224` with renderer chunk size `4096`. If that short-lived worker reports an
explicit CUDA allocation OOM, AssetForge retries the stage **once** at the
existing low-memory preset: resolution `192`, chunk size `2048`.

The retry happens in a fresh worker process, so the failed CUDA context has
already exited. Non-OOM errors are never retried by this policy, and a second
OOM is surfaced normally. This is a safety fallback, not evidence that either
preset has been benchmarked successfully on the reference machine; record real
hardware results with the repository validation tooling before further tuning.

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

Legacy TRELLIS remains available when explicitly requested. It is intentionally not the automatic first choice for this hardware profile because the current in-process TRELLIS adapter is not designed around 12GB operation. A separate TRELLIS.2 low-VRAM worker is planned.

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

## Next work

- Move heavyweight model backends into isolated worker processes/environments.
- Add measured per-stage peak VRAM and execution-time telemetry.
- Add a TRELLIS.2 low-VRAM worker.
- Replace heuristic texture/PBR reconstruction with native or proper baked material data.
- Add checkpoint/resume between generation stages.
- Add Blender geometry and multi-view visual QA.


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

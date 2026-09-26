# TRELLIS.2 on the RTX 3060 12 GB reference machine

## Current decision

Do **not** install or auto-select official TRELLIS.2 on the Windows RTX 3060
reference profile yet.

As checked against Microsoft's upstream repository on 2026-09-26, TRELLIS.2 is
documented as tested only on Linux and requires an NVIDIA GPU with **at least
24 GB VRAM**. Windows support work exists upstream but is not part of the
documented supported installation path. That is materially outside this
project's Windows 11 / RTX 3060 12 GB target.

This is a compatibility gate, not a claim that community modifications can
never run TRELLIS.2 in 12 GB. AssetForge will not present an unverified
community configuration as its production quality backend.

## Current RTX 3060 paths

- **Fast:** isolated TripoSR.
- **Balanced/default:** isolated Hunyuan3D-2 mini shape, with isolated Hunyuan
  Paint when that worker is available.
- **Quality:** no TRELLIS.2-backed production preset is advertised yet. Use
  explicit Hunyuan settings until a higher-quality backend passes the gate
  below.

The pipeline now preserves native albedo/UV layouts and native normal,
metallic-roughness, and occlusion maps when a backend supplies them, so a future
TRELLIS.2 worker does not need destructive PBR rebaking.

## Promotion gate for TRELLIS.2

A TRELLIS.2 backend may enter the supported RTX 3060 quality path only after all
of these are demonstrated on the target machine:

1. runs in an isolated process/environment and exits cleanly after generation;
2. completes 512-resolution image-to-3D without exceeding physical VRAM or
   destabilizing the desktop;
3. produces a usable GLB with native PBR material channels preserved;
4. records wall time, peak VRAM, selected resolution/settings, source revisions,
   and failures in `data/benchmarks`;
5. survives at least the repository hardware-validation and finished-asset
   validation gates;
6. has repeatable Windows installation instructions from a known source
   revision.

Do not infer success from another GPU, Linux-only instructions, or a community
fork. Commit the actual RTX 3060 benchmark evidence before changing automatic
selection.

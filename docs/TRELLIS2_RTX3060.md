# TRELLIS.2 RTX 3060 plan

The upstream TRELLIS.2 runtime is not yet validated for this repo's Windows RTX 3060 12 GB reference profile. Keep Hunyuan mini as the balanced default and TripoSR as the fast fallback until a real-device benchmark is recorded.

The quality integration should run out of process, start at 512 resolution, return GLB to AssetForge, preserve native PBR materials, and record wall time plus peak VRAM before being promoted into auto selection.

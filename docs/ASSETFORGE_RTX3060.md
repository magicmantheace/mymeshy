# AssetForge RTX 3060 12GB plan

This fork is being evolved into **AssetForge**, a local-first game asset worker
optimized around an NVIDIA RTX 3060 12GB as the reference GPU.

## Reference hardware

- GPU: RTX 3060 12GB
- System RAM: 32GB
- Goal: maximize asset quality without requiring a 16-24GB GPU
- Workload model: one heavyweight AI stage at a time

## Phase 1 — hardware-aware runtime policy

Implemented on `assetforge-rtx3060`:

- Detect RTX 3060 12GB automatically.
- Keep hardware scheduling separate from torch's hard VRAM cap.
- Allow one stage to use the card's available VRAM instead of forcing a <=8GB
  mode globally.
- Unload SDXL, Hunyuan, TripoSR and legacy TRELLIS after a heavy stage on the
  constrained-VRAM profile.
- Never keep Hunyuan shape and Hunyuan paint resident together on the RTX 3060
  profile.
- Tune TripoSR to a 4096 render chunk and 224 extraction resolution on the
  12GB profile; 8GB mode remains more conservative.
- Change `auto` image-to-3D priority on RTX 3060 to:
  1. Hunyuan3D-2mini
  2. TripoSR
  3. legacy TRELLIS
  4. mock
- Expose `/api/hardware` for the resolved profile and scheduling policy.

## Current quality modes

These names are architectural targets; UI wiring comes later.

| Mode | Backend | Intended use |
| --- | --- | --- |
| Draft | TripoSR | fast candidates and blockouts |
| Standard | Hunyuan3D-2mini | balanced geometry on 12GB |
| Quality | TRELLIS.2 low-VRAM | highest-quality static assets once integrated |
| Max | TRELLIS.2 aggressive offload | slow overnight/batch generation |

## Phase 2 — benchmark the actual machine

Do not guess at generic Internet limits. Record for each backend/preset:

- wall-clock generation time
- peak VRAM
- peak system RAM
- triangle count
- texture resolution
- success/OOM result
- model/repository revision

The resulting benchmark data becomes the source of truth for automatic preset
selection on this exact machine.

## Phase 3 — isolate model environments

The long-term architecture should not force SDXL, Hunyuan, TripoSR and
TRELLIS.2 to share one Python/CUDA dependency environment.

Target:

```text
AssetForge Core (FastAPI + MCP)
        |
        +-- concept worker     (own venv/process)
        +-- TripoSR worker     (own venv/process)
        +-- Hunyuan worker     (own venv/process)
        +-- TRELLIS.2 worker   (own venv/process)
        +-- Blender worker
```

A heavyweight worker may exit after each job. Process exit is the most reliable
way to release its CUDA context and avoid fragmentation or hidden residency.

## Phase 4 — replace weak asset processing

Do not treat the current pipeline as production-ready in these areas:

1. **Texture rebaking** — current nearest-vertex transfer can destroy detail.
   Replace with proper texel-space surface baking or preserve native UVs and
   materials when possible.
2. **PBR derivation** — current normal/roughness/metallic maps are heuristic
   derivatives of albedo. Keep them only as `derived_preview` materials.
3. **Retopology naming** — current quadric decimation is simplification, not
   animation-quality retopology.
4. **Multi-image capability** — adapters must explicitly advertise whether
   they support one image or true multi-view input.

## Phase 5 — TRELLIS.2 quality backend

Replace the legacy TRELLIS adapter with a TRELLIS.2 worker using its low-VRAM
path. Preserve native material information instead of converting it into
heuristic maps.

TRELLIS.2 remains experimental on the RTX 3060 profile until real measurements
prove stable presets.

## Phase 6 — checkpoints and provenance

Each accepted asset should eventually preserve intermediate stages such as:

```text
source/reference.png
raw_geometry.glb
clean_geometry.glb
simplified.glb
final.glb
textures/
qa/front.png
qa/back.png
qa/left.png
qa/right.png
qa/top.png
qa/perspective.png
```

Metadata should record:

- prompt and seed
- concept/geometry/texture model and revision
- generation preset
- native vs derived material channels
- generation time and peak VRAM/RAM
- source images
- license profile
- QA state

## Phase 7 — automated QA

Add Blender headless renders and programmatic checks for:

- degenerate/non-manifold geometry
- disconnected floaters
- normals
- scale/bounds
- triangle budget
- UV presence/coverage
- material channels
- texture resolution
- file validity

Visual QA can then compare six rendered views to the requested asset and either
accept, repair or regenerate it.

## Phase 8 — game-engine output

After static assets are reliable:

- LOD generation
- collision meshes
- Unreal import automation
- Git placement/metadata

Rigging and animation are intentionally later phases. Static props are the v1
production target.

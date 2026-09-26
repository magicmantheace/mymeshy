# MyMeshy

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?logo=react&logoColor=black)
![runs locally](https://img.shields.io/badge/runs-100%25%20local-success)

Local-first AI 3D asset generation — a Meshy-style workflow that runs entirely on
your own hardware. Text → 3D, image → 3D, and AI texturing of existing meshes,
with automatic mesh cleanup, retopology/decimation, UV unwrapping, PBR texture
baking, a real-time viewer, multi-format export, and an MCP server so coding
agents (Claude Code, Cursor) can generate game assets for you on demand.

No cloud, no API keys, no per-generation cost — your GPU does the work and the
assets never leave your machine.

> **See real output:** [`examples/scimitar.glb`](examples/scimitar.glb) is a
> sample weapon generated locally by the text-to-3D pipeline — drop it into any
> glTF viewer.

```
Text prompt ─► text-to-image ─► background ─► image-to-3D ─► cleanup ─► decimate
Image(s)  ──────────────────►  removal    ─►   (adapter)     │
Existing mesh ─► texturing adapter ──────────────────────────┤
                                                             ▼
            GLB/GLTF/OBJ/FBX ◄─ export ◄─ PBR maps ◄─ texture bake ◄─ UV unwrap
```

## Platform support

Developed and tested on **Windows + NVIDIA**, but the backend (Python/FastAPI),
frontend (React), mesh pipeline, PBR baking, exports, viewer and MCP server are
all OS-portable. Only **real AI generation** is platform-sensitive — every model
adapter requires CUDA.

| Platform | Real AI generation | Everything else |
|---|---|---|
| **Windows + NVIDIA** | ✅ Tested (primary platform) — use the `.ps1` scripts | ✅ |
| **Linux + NVIDIA** | ✅ Supported — first-class for these models (CUDA extensions like the Hunyuan paint rasterizer often build *more* easily than on Windows). Use the `.sh` scripts. | ✅ |
| **macOS** (Intel / Apple Silicon) | ❌ Not supported — the image→3D models (TRELLIS, Hunyuan3D-2, TripoSR) and SDXL are CUDA-only, and macOS has no CUDA (no Metal/MPS path). | ✅ runs in **mock mode** |
| **Any OS, no NVIDIA GPU** | ❌ falls back to mock mode | ✅ |

**Mock mode** runs the entire pipeline (UV unwrap, PBR baking, viewer, exports,
MCP) with procedural placeholder meshes — no GPU, no downloads. macOS users and
anyone without an NVIDIA card get a fully working app for development; just not
real generated geometry.

FBX export uses Blender on every platform — install it and make sure `blender`
is on your `PATH` (or set `MYMESHY_BLENDER_PATH`). Steam installs are
auto-detected on Windows.

## Features

- **Text to 3D** — describe a prop/creature/vehicle/building; get a complete,
  textured, UV-mapped, exportable mesh.
- **Image to 3D** — upload one or more reference images; reconstruct a textured
  model preserving shape and look.
- **Texturing** — texture brand-new meshes, re-texture generated assets, or
  texture your own uploaded meshes (GLB/OBJ/PLY/STL) from a prompt or image.
- **PBR outputs** — albedo, normal, roughness, metallic, ambient occlusion
  (plus a packed ORM used inside the GLB).
- **Mesh processing** — cleanup (degenerate faces, floaters), quadric
  decimation to a target polycount, xatlas UV unwrapping, texture baking,
  voxel-based AO baking, normalization to a game-friendly scale.
- **Viewer** — orbit/pan/zoom, wireframe, clay mode, per-channel texture
  inspection, procedural environment lighting (no CDN fetches), mesh stats.
- **Export** — GLB, GLTF (+textures, zipped), OBJ (+MTL+textures, zipped),
  FBX (via headless Blender — Steam installs are auto-detected).
- **MCP server** — ask your coding agent for "a low-poly barrel for my game,
  exported to ./assets" and it happens locally.

## Architecture

| Layer | Tech | Where |
|---|---|---|
| Backend API | Python 3.11, FastAPI, single GPU-job worker | `backend/` |
| AI adapters | Swappable modules per stage | `backend/app/pipeline/adapters/` |
| Mesh processing | trimesh, xatlas, fast-simplification, scipy | `backend/app/pipeline/meshproc.py` |
| PBR derivation | numpy/scipy image ops | `backend/app/pipeline/pbr.py` |
| Frontend | React + TypeScript + react-three-fiber | `frontend/` |
| MCP server | Python `mcp` (stdio) → backend HTTP | `mcp/server.py` |

Every AI model sits behind an adapter interface (`pipeline/base.py`), selected
at runtime via config with graceful fallback — swap or upgrade models without
touching the rest of the app.

### Adapters

| Stage | Adapter | Model | VRAM | Notes |
|---|---|---|---|---|
| image→3D | `trellis` | microsoft/TRELLIS-image-large | >12 GB typical | **legacy/experimental on RTX 3060 12 GB; explicit opt-in only** |
| image→3D | `hunyuan3d` | tencent/Hunyuan3D-2 (mini) | ~6–12 GB | **recommended on 12 GB**, shape + painted texture |
| image→3D | `triposr` | stabilityai/TripoSR | ~6 GB | fastest, blockout quality |
| image→3D | `mock` | — (procedural) | none | works out of the box, placeholder quality |
| text→image | `sdxl_turbo` | stabilityai/sdxl-turbo | ~7 GB | 4-step generation |
| text→image | `mock` | — | none | procedural reference image |
| texturing | `hunyuan_paint` | Hunyuan3D-2 paint | ~10 GB | textures arbitrary meshes |
| texturing | `mock` | — | none | procedural albedo |

Select adapters with env vars (or `.env` in the repo root):

```
MYMESHY_I23D_ADAPTER=hunyuan3d   # trellis | hunyuan3d | triposr | mock | auto
MYMESHY_T2I_ADAPTER=auto
MYMESHY_TEXTURE_ADAPTER=auto
MYMESHY_BLENDER_PATH=C:\...\blender.exe   # only if auto-detection misses it
MYMESHY_VRAM_BUDGET_GB=6         # hard cap on GPU memory (0 = unlimited)
```

### VRAM budget

`MYMESHY_VRAM_BUDGET_GB` hard-caps torch allocations to that amount. Budgets
of 8GB or less also switch the pipeline into low-VRAM mode: SDXL streams
weights through the GPU layer-by-layer (sequential CPU offload, <3GB), TripoSR
uses smaller chunks, and models are loaded one stage at a time and unloaded
between stages. Slower, but the GPU stays half-free for everything else.

With a ≤8GB budget the Hunyuan paint pipeline (needs ~10-12GB) is skipped;
geometry-only results automatically get their albedo by **projecting the
reference image onto the mesh** instead — real colors from the input,
placeholder-grade shading on the sides/back.

`auto` picks the best installed adapter and falls back to `mock`, so the app
always runs. Per-job override is available in the UI and the API (`options.adapter`).

## Quickstart

Prereqs: Node 18+, [uv](https://docs.astral.sh/uv/) (the setup script installs
it if missing). Your system Python version doesn't matter — uv provisions 3.11.

**Windows:**

```powershell
.\scripts\setup.ps1     # one-time: venv + deps + npm install
.\scripts\dev.ps1       # starts backend (8420) + frontend (5173)
```

**Linux / macOS:**

```bash
./scripts/setup.sh      # one-time: venv + deps + npm install
./scripts/dev.sh        # starts backend (8420) + frontend (5173)
```

Open http://localhost:5173. Without ML models installed the app runs in **mock
mode** — the full pipeline (UVs, PBR baking, viewer, exports, MCP) works with
procedural placeholder meshes, so you can validate everything before
downloading gigabytes.

## Installing real models

All models run locally; weights download from Hugging Face on first use. This
needs an **NVIDIA GPU with CUDA** (Windows or Linux) — macOS has no CUDA path.

> The commands below use the Windows venv path `\.venv\Scripts\python.exe`. On
> **Linux**, substitute `.venv/bin/python` everywhere (and `git clone ... external/<repo>`).

First install the CUDA PyTorch stack into the venv:

```powershell
uv pip install --python .venv\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu124
uv pip install --python .venv\Scripts\python.exe -r backend\requirements-ml.txt
```

That alone enables **SDXL-Turbo** (text→image). Then install at least one
image-to-3D model:

### Hunyuan3D-2 (recommended on 12 GB)

```powershell
git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2 external\Hunyuan3D-2
uv pip install --python .venv\Scripts\python.exe ninja pybind11 opencv-python pymeshlab pygltflib
```

Shape generation works as-is. The **paint pipeline** (true AI texturing,
including texturing arbitrary existing meshes) additionally needs its
`custom_rasterizer` CUDA extension compiled — that requires the CUDA toolkit
plus MSVC and ~10-12GB of VRAM at runtime, so it is skipped under a low VRAM
budget. To enable it later:

```powershell
# with CUDA toolkit + VS build tools installed:
cd external\Hunyuan3D-2\hy3dgen\texgen\custom_rasterizer
& ..\..\..\..\..\.venv\Scripts\python.exe setup.py install
cd ..\differentiable_renderer
& ..\..\..\..\..\.venv\Scripts\python.exe setup.py install
```

Uses `tencent/Hunyuan3D-2mini` for shape by default; set
`MYMESHY_HUNYUAN_SHAPE_MODEL=tencent/Hunyuan3D-2` for the full model.

### Legacy TRELLIS (experimental on RTX 3060 12 GB)

The in-process `microsoft/TRELLIS-image-large` adapter is retained for explicit
opt-in, but it is **not auto-selected on the RTX 3060 12 GB reference profile**
and is not considered a validated quality path for that card. Do not treat its
presence in the adapter list as a claim that it will fit reliably in 12 GB.

For the separate TRELLIS.2 quality-backend validation plan and the measurements
required before enabling it automatically, see
[`docs/TRELLIS2_RTX3060.md`](docs/TRELLIS2_RTX3060.md). Until real hardware
results justify a change, Hunyuan3D-2 mini remains the balanced RTX 3060 path
and TripoSR the fast fallback.

### TripoSR (fastest)

```powershell
git clone https://github.com/VAST-AI-Research/TripoSR external\TripoSR
uv pip install --python .venv\Scripts\python.exe omegaconf einops imageio moderngl
```

Anything cloned into `external/` is auto-importable — no pip install of the
repo needed. Do **not** install `external\TripoSR\requirements.txt` directly:
it pins old package versions and `torchmcubes` (a CUDA extension that needs
the full CUDA toolkit to build on Windows). MyMeshy ships a scikit-image-based
drop-in for `torchmcubes`, so TripoSR runs without any native compilation.

Restart the backend after installing; `GET /api/system` (or the top bar in the
UI) shows what was detected.

## MCP — generate assets from Claude Code / Cursor

Register the MCP server (backend must be running):

```powershell
claude mcp add mymeshy -- "D:\Game DEV\mymeshy\.venv\Scripts\python.exe" "D:\Game DEV\mymeshy\mcp\server.py"
```

Cursor (`.cursor/mcp.json`) or Claude Code (`.mcp.json`) JSON equivalent:

```json
{
  "mcpServers": {
    "mymeshy": {
      "command": "D:\\Game DEV\\mymeshy\\.venv\\Scripts\\python.exe",
      "args": ["D:\\Game DEV\\mymeshy\\mcp\\server.py"],
      "env": { "MYMESHY_URL": "http://127.0.0.1:8420" }
    }
  }
}
```

Tools exposed: `text_to_3d`, `image_to_3d`, `texture_mesh`, `get_job`,
`wait_for_job`, `list_assets`, `export_asset`, `get_texture_maps`,
`system_status`. Example, from inside a game project:

> "We need a stylized wooden treasure chest matching the props in
> ./concept/props.png — generate it and export GLB + texture maps into
> ./Assets/Models/Chest"

## Generation checkpoints and post-processing retry

Text-to-3D and image-to-3D jobs save the expensive raw model output before mesh
cleanup, UV work, PBR generation, and export. If one of those downstream stages
fails, retry it without running the AI model again:

`POST /api/assets/{asset_id}/resume`

The retry uses the generation options saved with the checkpoint. It does not
rerun text-to-image, background removal, or image-to-3D. Checkpoints are also
kept after successful jobs so post-processing can be retried later. Run the
GPU-free checkpoint contract test with:

```powershell
.venv\Scripts\python.exe scripts\test_checkpoint_resume.py
```

## API

Interactive docs at http://127.0.0.1:8420/docs. Highlights:

- `POST /api/jobs/text-to-3d` `{prompt, options}` / `POST /api/jobs/image-to-3d` (multipart) / `POST /api/jobs/texture` (multipart)
- `GET /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`
- `GET /api/assets`, `GET /api/assets/{id}/model.glb`, `GET /api/assets/{id}/textures/{map}.png`
- `GET /api/assets/{id}/export?format=glb|gltf|obj|fbx`

Options accepted by all generation jobs: `adapter`, `target_polycount`
(default 30000), `texture_size` (256–4096, default 1024), `generate_pbr`
(default true), `seed`, `decimate`.

## Data layout

```
data/
  assets/{asset-id}/
    meta.json          # name, source, stats, texture list
    model.glb          # PBR-textured, ready to use
    textures/          # albedo/normal/roughness/metallic/ao PNGs
    source/            # input images / prompt
  uploads/             # raw uploaded files
  jobs.json            # job history
```

## Notes & limitations

- One GPU job runs at a time (the worker serializes jobs) — by design for 12 GB cards.
- FBX export shells out to Blender (`-b --python`); Steam and standard installs
  are auto-detected, override with `MYMESHY_BLENDER_PATH`.
- Normal/roughness/metallic maps are derived from the baked albedo with
  classic image-processing heuristics (Materialize-style); AO is geometry-based
  (voxel ray marching) multiplied with albedo cavity. Hunyuan3D-2.1's PBR paint
  pipeline can replace this wholesale by adding an adapter.
- Mock mode is intentionally simple (silhouette inflation) — it validates the
  entire pipeline without any downloads.

## License

[MIT](LICENSE) © 2026 Felippe. Model weights downloaded from Hugging Face
(TRELLIS, Hunyuan3D-2, TripoSR, SDXL-Turbo) carry their own upstream licenses —
review them before commercial use.

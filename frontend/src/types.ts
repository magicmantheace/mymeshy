// ---- Backend API contract -------------------------------------------------

export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled';
export type JobType = 'text_to_3d' | 'image_to_3d' | 'texture' | 'resume_postprocess';

export interface JobRecord {
  id: string;
  type: JobType;
  status: JobStatus;
  stage: string;
  progress: number; // 0..1
  message?: string;
  error?: string;
  error_category?: string;
  asset_id?: string;
  resumable?: boolean;
  created_at: string;
  params: Record<string, unknown>;
}

export type TextureMap =
  | 'albedo'
  | 'normal'
  | 'roughness'
  | 'metallic'
  | 'ao'
  | 'metallic_roughness'
  | 'occlusion';

export interface AssetMeta {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  source: {
    type: 'text' | 'image' | 'texture';
    prompt?: string;
    image_names?: string[];
  };
  stats: {
    vertices: number;
    triangles: number;
    materials: number;
    texture_size?: number;
    has_uv: boolean;
  };
  textures: TextureMap[];
  adapter: string;
  pipeline_adapters?: {
    text_to_image?: string;
    image_to_3d?: string;
    texturing?: string;
  };
}

export interface AdapterInfo {
  name: string;
  available: boolean;
  reason?: string;
  description?: string;
}

export interface GenerationPreset {
  name: 'fast' | 'balanced' | 'quality';
  available: boolean;
  required_adapter?: string | null;
  settings: GenOptions;
}

export interface RuntimeInfo {
  python: string;
  executable: string;
  torch?: string | null;
  cuda_runtime?: string | null;
  cuda_available: boolean;
  torch_error?: string;
  source_revision?: string | null;
}

export interface MemoryPolicy {
  hardware_profile: string;
  runtime_vram_gb: number;
  hard_cap_gb: number;
  low_vram: boolean;
  constrained_vram: boolean;
  stage_unload: boolean;
}

export interface WorkerRuntimeInfo {
  python: string;
  python_version?: string | null;
  torch_version?: string | null;
  cuda_runtime?: string | null;
  cuda_available: boolean;
  source_revision?: string | null;
  expected_source_revision?: string | null;
  source_matches_lock: boolean;
  error?: string | null;
}

export interface WorkerInfo {
  python: string;
  python_exists: boolean;
  external_source_exists: boolean;
  configured: boolean;
  separate_environment: boolean;
  runtime?: WorkerRuntimeInfo;
}

export interface WorkerSystemInfo {
  enabled: boolean;
  timeout_sec: number;
  triposr: WorkerInfo;
  hunyuan_shape: WorkerInfo;
  hunyuan_paint: WorkerInfo;
}

export interface SystemInfo {
  version: string;
  runtime: RuntimeInfo;
  gpu: { name: string; vram_mb: number } | null;
  memory_policy: MemoryPolicy;
  workers: WorkerSystemInfo;
  blender: boolean;
  generation_presets: GenerationPreset[];
  adapters: {
    image_to_3d: AdapterInfo[];
    text_to_image: AdapterInfo[];
    texturing: AdapterInfo[];
  };
  active: {
    image_to_3d: string;
    text_to_image: string;
    texturing: string;
  };
  mock_mode: boolean;
}

// ---- Frontend-only types --------------------------------------------------

export interface GenOptions {
  preset?: 'fast' | 'balanced' | 'quality';
  adapter?: string;
  target_polycount?: number;
  texture_size?: number;
  generate_pbr?: boolean;
  seed?: number;
  decimate?: boolean;
}

export type ExportFormat = 'glb' | 'gltf' | 'obj' | 'fbx';

export type ShadingMode =
  | 'lit'
  | 'wireframe'
  | 'solid'
  | 'albedo'
  | 'normal'
  | 'roughness'
  | 'metallic'
  | 'ao';

export type EnvPreset = 'studio' | 'soft' | 'night';
export type ViewportBg = 'dark' | 'gray' | 'light';

export interface LiveModelStats {
  vertices: number;
  triangles: number;
  materials: number;
  textures: number;
  drawCalls: number;
  hasUv: boolean;
}

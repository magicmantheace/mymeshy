import type { AdapterInfo, SystemInfo, WorkerInfo } from '../types';
import { formatVram } from '../utils';
import { Modal } from './Modal';

function Row({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="meta-row" title={title}>
      <span className="meta-row__key">{label}</span>
      <span className="meta-row__val mono">{value}</span>
    </div>
  );
}

function shortRevision(value?: string | null): string {
  return value ? value.slice(0, 12) : 'unknown';
}

function workerState(worker: WorkerInfo): string {
  if (!worker.configured) return 'not configured';
  if (worker.runtime?.error) return 'runtime error';
  if (worker.runtime && !worker.runtime.cuda_available) return 'CUDA unavailable';
  if (worker.runtime && !worker.runtime.source_matches_lock) return 'source lock mismatch';
  return worker.runtime ? 'runtime ready' : 'configured';
}

function AdapterRows({ label, adapters }: { label: string; adapters: AdapterInfo[] }) {
  return (
    <section className="panel-section">
      <header className="panel-subhead">
        <span>{label}</span>
        <span className="panel-subhead__count">
          {adapters.filter((adapter) => adapter.available).length}/{adapters.length}
        </span>
      </header>
      <div className="meta-rows">
        {adapters.map((adapter) => (
          <Row
            key={adapter.name}
            label={adapter.name}
            value={adapter.available ? 'available' : 'unavailable'}
            title={adapter.reason || adapter.description}
          />
        ))}
      </div>
    </section>
  );
}

export function SystemDiagnostics({ system, onClose }: { system: SystemInfo; onClose: () => void }) {
  const workerEntries: Array<[string, WorkerInfo]> = [
    ['TripoSR', system.workers.triposr],
    ['Hunyuan Shape', system.workers.hunyuan_shape],
    ['Hunyuan Paint', system.workers.hunyuan_paint],
  ];

  return (
    <Modal title="System diagnostics" onClose={onClose}>
      <section className="panel-section">
        <header className="panel-subhead">
          <span>Hardware policy</span>
        </header>
        <div className="meta-rows">
          <Row label="GPU" value={system.gpu ? `${system.gpu.name} · ${formatVram(system.gpu.vram_mb)}` : 'none'} />
          <Row label="Profile" value={system.memory_policy.hardware_profile} />
          <Row label="Effective VRAM" value={`${system.memory_policy.runtime_vram_gb} GB`} />
          <Row
            label="Hard cap"
            value={system.memory_policy.hard_cap_gb > 0 ? `${system.memory_policy.hard_cap_gb} GB` : 'none'}
          />
          <Row label="Stage unload" value={system.memory_policy.stage_unload ? 'enabled' : 'disabled'} />
          <Row label="Blender" value={system.blender ? 'available' : 'not detected'} />
        </div>
      </section>

      <section className="panel-section">
        <header className="panel-subhead">
          <span>Backend runtime</span>
        </header>
        <div className="meta-rows">
          <Row label="Python" value={system.runtime.python} title={system.runtime.executable} />
          <Row label="Torch" value={system.runtime.torch || 'not installed'} title={system.runtime.torch_error} />
          <Row label="CUDA runtime" value={system.runtime.cuda_runtime || 'none'} />
          <Row label="CUDA visible" value={system.runtime.cuda_available ? 'yes' : 'no'} />
          <Row label="Source" value={shortRevision(system.runtime.source_revision)} title={system.runtime.source_revision || undefined} />
        </div>
      </section>

      <section className="panel-section">
        <header className="panel-subhead">
          <span>Isolated workers</span>
          <span className="panel-subhead__count">{system.workers.enabled ? 'enabled' : 'disabled'}</span>
        </header>
        <div className="meta-rows">
          {workerEntries.map(([name, worker]) => {
            const runtime = worker.runtime;
            const lockTitle = runtime
              ? `actual ${runtime.source_revision || 'unknown'}; expected ${runtime.expected_source_revision || 'unknown'}`
              : worker.python;
            return (
              <div key={name} className="meta-row" title={runtime?.error || lockTitle}>
                <span className="meta-row__key">{name}</span>
                <span className="meta-row__val mono">
                  {workerState(worker)}
                  {runtime?.torch_version ? ` · torch ${runtime.torch_version}` : ''}
                  {runtime?.cuda_runtime ? ` · CUDA ${runtime.cuda_runtime}` : ''}
                  {runtime?.source_revision ? ` · ${shortRevision(runtime.source_revision)}` : ''}
                  {runtime ? ` · lock ${runtime.source_matches_lock ? 'ok' : 'mismatch'}` : ''}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <AdapterRows label="Image → 3D adapters" adapters={system.adapters.image_to_3d} />
      <AdapterRows label="Text → image adapters" adapters={system.adapters.text_to_image} />
      <AdapterRows label="Texturing adapters" adapters={system.adapters.texturing} />

      <section className="panel-section">
        <header className="panel-subhead">
          <span>Generation presets</span>
        </header>
        <div className="meta-rows">
          {system.generation_presets.map((preset) => (
            <Row
              key={preset.name}
              label={preset.name}
              value={preset.available ? 'available' : 'unavailable'}
              title={preset.required_adapter ? `requires ${preset.required_adapter}` : 'hardware-aware auto'}
            />
          ))}
        </div>
      </section>
    </Modal>
  );
}

import { useStore } from '../../store';

export interface OptionsState {
  adapter: string; // '' = auto (backend default)
  target_polycount: string;
  texture_size: number;
  generate_pbr: boolean;
  seed: string;
}

export const DEFAULT_OPTIONS: OptionsState = {
  adapter: '',
  target_polycount: '30000',
  texture_size: 1024,
  generate_pbr: true,
  seed: '',
};

type PresetName = 'fast' | 'balanced' | 'quality';

const GENERATION_PRESETS: Record<PresetName, Pick<OptionsState, 'adapter' | 'target_polycount' | 'texture_size' | 'generate_pbr'>> = {
  fast: { adapter: 'triposr', target_polycount: '20000', texture_size: 1024, generate_pbr: true },
  balanced: { adapter: '', target_polycount: '30000', texture_size: 1024, generate_pbr: true },
  quality: { adapter: 'hunyuan3d', target_polycount: '50000', texture_size: 2048, generate_pbr: true },
};

export function optionsToPayload(o: OptionsState) {
  const polycount = parseInt(o.target_polycount, 10);
  const seed = parseInt(o.seed, 10);
  return {
    adapter: o.adapter || undefined,
    target_polycount: Number.isFinite(polycount) && polycount > 0 ? polycount : undefined,
    texture_size: o.texture_size,
    generate_pbr: o.generate_pbr,
    seed: Number.isFinite(seed) ? seed : undefined,
  };
}

interface Props {
  value: OptionsState;
  onChange: (next: OptionsState) => void;
  /** Hide mesh-generation options (polycount/pbr/seed) for the texture tab. */
  meshOptions?: boolean;
  adapterKind?: 'image_to_3d' | 'texturing';
}

export function OptionsFields({
  value,
  onChange,
  meshOptions = true,
  adapterKind = 'image_to_3d',
}: Props) {
  const system = useStore((s) => s.system);
  const adapters = system?.adapters[adapterKind] ?? [];

  const patch = (p: Partial<OptionsState>) => onChange({ ...value, ...p });
  const available = new Set(adapters.filter((a) => a.available).map((a) => a.name));
  const applyPreset = (name: PresetName) => onChange({ ...value, ...GENERATION_PRESETS[name] });
  const activePreset = (Object.keys(GENERATION_PRESETS) as PresetName[]).find((name) => {
    const preset = GENERATION_PRESETS[name];
    return value.adapter === preset.adapter
      && value.target_polycount === preset.target_polycount
      && value.texture_size === preset.texture_size
      && value.generate_pbr === preset.generate_pbr;
  });

  return (
    <div className="opt-grid">
      {meshOptions && adapterKind === 'image_to_3d' && (
        <div className="opt-field opt-field--full">
          <span className="opt-field__label">Generation preset</span>
          <div className="gen-presets">
            {(['fast', 'balanced', 'quality'] as PresetName[]).map((name) => {
              const required = GENERATION_PRESETS[name].adapter;
              const disabled = Boolean(required) && !available.has(required);
              return (
                <button
                  key={name}
                  type="button"
                  className={`gen-presets__button ${activePreset === name ? 'gen-presets__button--active' : ''}`}
                  disabled={disabled}
                  title={disabled ? `${required} is not available` : `Use the ${name} workload preset`}
                  onClick={() => applyPreset(name)}
                >
                  {name[0].toUpperCase() + name.slice(1)}
                </button>
              );
            })}
          </div>
          <span className="opt-field__hint">
            Fast: TripoSR · Balanced: hardware-aware Auto · Quality: Hunyuan3D
          </span>
        </div>
      )}
      <label className="opt-field opt-field--full">
        <span className="opt-field__label">Adapter</span>
        <select
          className="input"
          value={value.adapter}
          onChange={(e) => patch({ adapter: e.target.value })}
        >
          <option value="">
            Auto{system ? ` (${system.active[adapterKind]})` : ''}
          </option>
          {adapters.map((a) => (
            <option key={a.name} value={a.name} disabled={!a.available}>
              {a.name}
              {!a.available ? ` — unavailable${a.reason ? `: ${a.reason}` : ''}` : ''}
            </option>
          ))}
        </select>
      </label>

      {meshOptions && (
        <label className="opt-field">
          <span className="opt-field__label">Target polycount</span>
          <input
            className="input"
            type="number"
            min={100}
            step={1000}
            value={value.target_polycount}
            onChange={(e) => patch({ target_polycount: e.target.value })}
          />
        </label>
      )}

      <label className="opt-field">
        <span className="opt-field__label">Texture size</span>
        <select
          className="input"
          value={value.texture_size}
          onChange={(e) => patch({ texture_size: Number(e.target.value) })}
        >
          <option value={1024}>1024 px</option>
          <option value={2048}>2048 px</option>
        </select>
      </label>

      {meshOptions && (
        <label className="opt-field">
          <span className="opt-field__label">
            Seed <span className="opt-field__hint">(optional)</span>
          </span>
          <input
            className="input"
            type="number"
            placeholder="random"
            value={value.seed}
            onChange={(e) => patch({ seed: e.target.value })}
          />
        </label>
      )}

      {meshOptions && (
        <label className="opt-check opt-field--full">
          <input
            type="checkbox"
            checked={value.generate_pbr}
            onChange={(e) => patch({ generate_pbr: e.target.checked })}
          />
          <span>Generate PBR maps (normal / roughness / metallic / AO)</span>
        </label>
      )}
    </div>
  );
}

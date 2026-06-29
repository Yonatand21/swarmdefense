import type { ReactNode } from "react";
import type { Catalog, EffectorSpec, Scenario, ThreatSpec } from "../types/config";

interface Props {
  catalog: Catalog;
  scenario: Scenario;
  runs: number;
  advanced: boolean;
  onChange: (s: Scenario) => void;
  onRunsChange: (n: number) => void;
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

export function MissionBuilder({
  catalog,
  scenario,
  runs,
  advanced,
  onChange,
  onRunsChange,
}: Props) {
  const edit = (mut: (s: Scenario) => void) => {
    const next = clone(scenario);
    mut(next);
    onChange(next);
  };

  return (
    <div className="builder">
      <Section title="Swarm" subtitle="what is inbound">
        {scenario.swarm.map((entry, i) => (
          <div className="row" key={i}>
            <div className="row-main">
              <select
                value={entry.spec.id}
                onChange={(e) =>
                  edit((s) => {
                    const found = catalog.threats.find((t) => t.id === e.target.value);
                    if (found) s.swarm[i].spec = clone(found);
                  })
                }
              >
                {catalog.threats.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.id}
                  </option>
                ))}
              </select>
              <Num
                label="count"
                value={entry.count}
                min={1}
                step={1}
                onChange={(v) => edit((s) => (s.swarm[i].count = Math.max(1, Math.round(v))))}
              />
              <button className="x" onClick={() => edit((s) => s.swarm.splice(i, 1))}>
                x
              </button>
            </div>
            {advanced && <ThreatAdvanced entry={entry.spec} onField={(k, v) => edit((s) => assign(s.swarm[i].spec, k, v))} />}
          </div>
        ))}
        <button
          className="add"
          onClick={() =>
            edit((s) => s.swarm.push({ spec: clone(catalog.threats[0]), count: 5 }))
          }
        >
          + threat
        </button>
      </Section>

      <Section title="Defense" subtitle="your posture">
        {scenario.defense.effectors.map((eff, i) => (
          <div className="row" key={i}>
            <div className="row-main">
              <select
                value={eff.id}
                onChange={(e) =>
                  edit((s) => {
                    const found = catalog.effectors.find((x) => x.id === e.target.value);
                    if (found) s.defense.effectors[i] = clone(found);
                  })
                }
              >
                {catalog.effectors.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.id}
                  </option>
                ))}
              </select>
              <Num
                label="mag"
                value={eff.magazine}
                min={1}
                step={1}
                onChange={(v) =>
                  edit((s) => (s.defense.effectors[i].magazine = Math.max(1, Math.round(v))))
                }
              />
              <button className="x" onClick={() => edit((s) => s.defense.effectors.splice(i, 1))}>
                x
              </button>
            </div>
            {advanced && (
              <EffectorAdvanced eff={eff} onField={(k, v) => edit((s) => assign(s.defense.effectors[i], k, v))} />
            )}
          </div>
        ))}
        <button
          className="add"
          onClick={() =>
            edit((s) => s.defense.effectors.push(clone(catalog.effectors[0])))
          }
        >
          + effector
        </button>
        {advanced && (
          <div className="advanced-grid">
            <Num
              label="sensor p_track"
              value={scenario.defense.sensor.p_track}
              min={0}
              step={0.05}
              onChange={(v) => edit((s) => (s.defense.sensor.p_track = clamp01(v)))}
            />
            <Num
              label="sensor p_identify"
              value={scenario.defense.sensor.p_identify}
              min={0}
              step={0.05}
              onChange={(v) => edit((s) => (s.defense.sensor.p_identify = clamp01(v)))}
            />
          </div>
        )}
      </Section>

      <Section title="Mission" subtitle="run settings">
        <div className="advanced-grid">
          <Num
            label="approach distance"
            value={scenario.approach_distance}
            min={1}
            step={5}
            onChange={(v) => edit((s) => (s.approach_distance = Math.max(1, v)))}
          />
          <label className="field">
            <span>runs</span>
            <select value={runs} onChange={(e) => onRunsChange(Number(e.target.value))}>
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
            </select>
          </label>
          {advanced && (
            <>
              <Num
                label="seed"
                value={scenario.seed}
                min={0}
                step={1}
                onChange={(v) => edit((s) => (s.seed = Math.max(0, Math.round(v))))}
              />
              <Num
                label="detection x"
                value={scenario.environment.detection_modifier}
                min={0.1}
                step={0.1}
                onChange={(v) => edit((s) => (s.environment.detection_modifier = Math.max(0.1, v)))}
              />
            </>
          )}
        </div>
      </Section>
    </div>
  );
}

function ThreatAdvanced({
  entry,
  onField,
}: {
  entry: ThreatSpec;
  onField: (k: keyof ThreatSpec, v: number | boolean) => void;
}) {
  return (
    <div className="advanced-grid sub">
      <Num label="cost" value={entry.cost} min={0} step={1000} onChange={(v) => onField("cost", v)} />
      <Num label="speed" value={entry.speed} min={0.1} step={0.1} onChange={(v) => onField("speed", v)} />
      <Num
        label="detect range"
        value={entry.detection_range}
        min={1}
        step={1}
        onChange={(v) => onField("detection_range", v)}
      />
      <Num label="warhead" value={entry.warhead} min={0} step={0.5} onChange={(v) => onField("warhead", v)} />
      <Check label="EW-immune" checked={entry.soft_kill_immune} onChange={(v) => onField("soft_kill_immune", v)} />
      <Check label="decoy" checked={entry.is_decoy} onChange={(v) => onField("is_decoy", v)} />
    </div>
  );
}

function EffectorAdvanced({
  eff,
  onField,
}: {
  eff: EffectorSpec;
  onField: (k: keyof EffectorSpec, v: number) => void;
}) {
  return (
    <div className="advanced-grid sub">
      <Num
        label="cost/shot"
        value={eff.cost_per_shot}
        min={0}
        step={1000}
        onChange={(v) => onField("cost_per_shot", v)}
      />
      <Num label="range" value={eff.range} min={1} step={1} onChange={(v) => onField("range", v)} />
      <Num
        label="reload"
        value={eff.reload_time}
        min={0}
        step={1}
        onChange={(v) => onField("reload_time", Math.round(v))}
      />
      <Num label="p_kill" value={eff.p_kill} min={0} step={0.05} onChange={(v) => onField("p_kill", clamp01(v))} />
      <Num
        label="simul."
        value={eff.max_simultaneous}
        min={1}
        step={1}
        onChange={(v) => onField("max_simultaneous", Math.max(1, Math.round(v)))}
      />
      <Num
        label="max tgt speed"
        value={eff.max_target_speed ?? 0}
        min={0}
        step={0.1}
        onChange={(v) => onField("max_target_speed", v)}
      />
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="builder-section">
      <div className="builder-section-head">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
      {children}
    </div>
  );
}

function Num({
  label,
  value,
  onChange,
  step,
  min,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
      />
    </label>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="field check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

// Field assignment helper (keeps the edit() closures terse across heterogeneous field types).
function assign<T extends object>(obj: T, key: keyof T, value: unknown): void {
  (obj as Record<string, unknown>)[key as string] = value;
}

import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { getCatalog, runScenario } from "./api";
import { MissionBuilder } from "./components/MissionBuilder";
import { ScenarioView } from "./components/ScenarioView";
import type { Catalog, Scenario } from "./types/config";
import type { MonteCarloResult } from "./types/result";

const COLOR_A = "#5b9cff";
const COLOR_B = "#ff7b72";

interface ColumnState {
  presetName: string;
  scenario: Scenario;
  runs: number;
  result: MonteCarloResult | null;
  loading: boolean;
  error: string | null;
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

function columnFromPreset(catalog: Catalog, idx: number): ColumnState {
  const preset = catalog.presets[Math.min(idx, catalog.presets.length - 1)];
  return {
    presetName: preset.name,
    scenario: clone(preset),
    runs: 200,
    result: null,
    loading: false,
    error: null,
  };
}

export function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [compare, setCompare] = useState(false);
  const [a, setA] = useState<ColumnState | null>(null);
  const [b, setB] = useState<ColumnState | null>(null);
  const initRan = useRef(false);

  useEffect(() => {
    getCatalog()
      .then((cat) => {
        setCatalog(cat);
        setA(columnFromPreset(cat, 0));
        setB(columnFromPreset(cat, 1));
      })
      .catch((e) => setFatal(String(e)));
  }, []);

  const run = async (
    state: ColumnState,
    setState: Dispatch<SetStateAction<ColumnState | null>>
  ) => {
    setState((s) => (s ? { ...s, loading: true, error: null } : s));
    try {
      const result = await runScenario(state.scenario, state.runs);
      setState((s) => (s ? { ...s, result, loading: false } : s));
    } catch (e) {
      setState((s) => (s ? { ...s, loading: false, error: String(e) } : s));
    }
  };

  // Auto-run column A once after the catalog loads, so there is content immediately.
  useEffect(() => {
    if (a && !initRan.current) {
      initRan.current = true;
      run(a, setA);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a]);

  // Auto-run B the first time compare is enabled.
  useEffect(() => {
    if (compare && b && !b.result && !b.loading) run(b, setB);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compare]);

  if (fatal) {
    return (
      <div className="app">
        <h1>Counter-Swarm Sandbox</h1>
        <div className="error">
          <p>{fatal}</p>
          <p className="muted">
            Start the engine bridge from the repo root: <code>python server.py</code>
          </p>
        </div>
      </div>
    );
  }

  if (!catalog || !a) return <div className="app loading">Loading catalog…</div>;

  return (
    <div className="app">
      <header className="app-head">
        <div>
          <h1>Counter-Swarm Sandbox</h1>
          <p className="subtitle">
            Compose a swarm and a defense. Run it 100s of times. See what actually decides the fight.
          </p>
        </div>
        <div className="head-controls">
          <label className="toggle">
            <input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} />
            Advanced
          </label>
          <label className="toggle">
            <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} />
            A / B compare
          </label>
        </div>
      </header>

      <div className={compare ? "columns two" : "columns one"}>
        <Column
          catalog={catalog}
          state={a}
          setState={setA}
          advanced={advanced}
          color={COLOR_A}
          accent="A"
          onRun={() => run(a, setA)}
        />
        {compare && b && (
          <Column
            catalog={catalog}
            state={b}
            setState={setB}
            advanced={advanced}
            color={COLOR_B}
            accent="B"
            onRun={() => run(b, setB)}
          />
        )}
      </div>
    </div>
  );
}

function Column({
  catalog,
  state,
  setState,
  advanced,
  color,
  accent,
  onRun,
}: {
  catalog: Catalog;
  state: ColumnState;
  setState: Dispatch<SetStateAction<ColumnState | null>>;
  advanced: boolean;
  color: string;
  accent: "A" | "B";
  onRun: () => void;
}) {
  return (
    <div className="column">
      <div className="picker">
        <span className="pill" style={{ background: color }}>
          {accent}
        </span>
        <select
          value={state.presetName}
          onChange={(e) => {
            const preset = catalog.presets.find((p) => p.name === e.target.value);
            if (preset)
              setState((s) =>
                s ? { ...s, presetName: preset.name, scenario: clone(preset), result: s.result } : s
              );
          }}
        >
          {catalog.presets.map((p) => (
            <option key={p.name} value={p.name}>
              load preset: {p.name}
            </option>
          ))}
        </select>
        <button className="run" style={{ background: color }} onClick={onRun} disabled={state.loading}>
          {state.loading ? "Running…" : `Run ${state.runs}x`}
        </button>
      </div>

      <MissionBuilder
        catalog={catalog}
        scenario={state.scenario}
        runs={state.runs}
        advanced={advanced}
        onChange={(scenario) => setState((s) => (s ? { ...s, scenario } : s))}
        onRunsChange={(runs) => setState((s) => (s ? { ...s, runs } : s))}
      />

      {state.error && <div className="error small">{state.error}</div>}
      {state.result ? (
        <ScenarioView mc={state.result} scenario={state.scenario} color={color} />
      ) : state.loading ? (
        <div className="loading">Running {state.runs} simulations…</div>
      ) : (
        <div className="loading">Adjust the mission, then press Run.</div>
      )}
    </div>
  );
}

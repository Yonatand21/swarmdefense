# Counter-Swarm Sandbox

A simulation sandbox that demonstrates *cost and saturation* -- not lethality -- decide the modern
counter-drone fight. See [`ARCHITECTURE_AND_PLAN.md`](ARCHITECTURE_AND_PLAN.md) for the full thesis,
design, and roadmap.

> Status: **Phase 2 + interactive mission builder.** The headless analysis core, a React + TypeScript
> dashboard (cost-exchange headline, leaker distribution, attrition curve, magazine timeline, A/B
> compare), and a thin localhost FastAPI bridge so an operator can *compose* a swarm and a defense
> loadout, run it live, and compare postures. 2D engagement replay is Phase 3.

## Quickstart (engine only)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python cli.py --list                  # show the canonical scenarios
python cli.py layered_mix             # one deterministic run, print the summary
python cli.py layered_mix --runs 500  # Monte Carlo: distributions + curves + representative run
python cli.py layered_mix --runs 500 --emit   # also write outputs/<name>.montecarlo.json

pytest                                # determinism, conservation, canonical + API tests
```

## Interactive dashboard (engine bridge + UI)

Two processes: the engine bridge (Python) and the dashboard (Vite). Run each in its own terminal.

```bash
# terminal 1 - the engine bridge (compose -> run -> result)
pip install -e ".[dev,server]"
python server.py                      # serves http://127.0.0.1:8000 (GET /api/catalog, POST /api/run)

# terminal 2 - the dashboard
cd frontend
npm install
npm run dev                           # open http://localhost:5173
```

In the UI: pick a preset or compose your own swarm + defense, toggle **Advanced** for every numeric
field, hit **Run**, and use **A/B compare** to put two postures side by side. (A static export path
also exists for a server-free dashboard: `python cli.py --all` writes `frontend/public/data/`.)

## Layout

```
engine/      pure simulation library (models, rng, assignment policy, step loop, Monte Carlo)
schema/      the engine<->consumer contract (result.py) and the YAML loader (supports overrides)
scenarios/   data-driven threats / effectors / scenarios
cli.py       run a scenario, print/emit; --all exports dashboard data
server.py    thin localhost FastAPI bridge: GET /api/catalog, POST /api/run
tests/       determinism + sanity + canonical validation + API
frontend/    React + TypeScript + Vite dashboard & mission builder (a pure consumer of the contract)
```

The engine is the protected core: it has no I/O or rendering, emits a validated `Result`, and every
consumer (CLI, dashboard, the bridge) only ever reads that contract.

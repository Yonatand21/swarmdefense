# Counter-Swarm Sandbox

A simulation sandbox that demonstrates *cost and saturation* -- not lethality -- decide the modern
counter-drone fight. See [`ARCHITECTURE_AND_PLAN.md`](ARCHITECTURE_AND_PLAN.md) for the full thesis,
design, and roadmap.

> Status: **Phase 1 (analysis core)** -- headless deterministic engine plus Monte Carlo
> aggregation, distribution metrics, attrition curve, and magazine timeline. The three canonical
> scenarios are validated numerically. No UI yet (Phase 3).

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python cli.py --list                  # show the canonical scenarios
python cli.py layered_mix             # one deterministic run, print the summary
python cli.py layered_mix --runs 500  # Monte Carlo: distributions + curves + representative run
python cli.py layered_mix --runs 500 --emit   # also write outputs/<name>.montecarlo.json

pytest                                # determinism, conservation, canonical validation
```

## Layout

```
engine/      pure simulation library (models, rng, assignment policy, the step loop)
schema/      the engine<->consumer contract (result.py) and the YAML loader
scenarios/   data-driven threats / effectors / scenarios
cli.py       run a scenario, print/emit the Result
tests/       determinism + sanity checks
```

The engine is the protected core: it has no I/O or rendering, emits a validated `Result`, and every
consumer (metrics, animation, future API) only ever reads that artifact.

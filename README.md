# Counter-Swarm Sandbox

A simulation sandbox that demonstrates *cost and saturation* -- not lethality -- decide the modern
counter-drone fight. See [`ARCHITECTURE_AND_PLAN.md`](ARCHITECTURE_AND_PLAN.md) for the full thesis,
design, and roadmap.

> Status: **Phase 0 (walking skeleton)** -- the headless deterministic engine runs end-to-end and
> emits the result contract. No UI yet (Phase 3).

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python cli.py --list                  # show the canonical scenarios
python cli.py layered_mix             # run one deterministically, print the summary
python cli.py layered_mix --emit      # also write outputs/<name>.result.json (the contract)

pytest                                # determinism + conservation checks
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

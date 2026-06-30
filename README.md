# Counter-Swarm Sandbox

A simulation sandbox that demonstrates a single thesis: **cost, saturation, and the speed of the
kill chain — not lethality — decide the modern counter-drone fight.** Configure a layered defense,
throw a heterogeneous drone swarm at it, and measure what actually matters: leakers, cost-exchange,
attrition, and how many waves your magazines can sustain.

Full design rationale and roadmap: [`ARCHITECTURE_AND_PLAN.md`](ARCHITECTURE_AND_PLAN.md).

---

## 1. Why this — the problem

Open-source reporting from Ukraine, the Red Sea, and Poland converges on a counter-intuitive lesson:
**defenders can intercept drones and still lose.** The failure modes are structural, not technical:

- **The cost-exchange trap.** A ~$20–30k attack drone draws an interceptor costing orders of
  magnitude more. You can stop the swarm and still lose the economic exchange.
- **Saturation / magazine depth.** Mass is the weapon. The decisive moment is the magazine running
  dry mid-wave, after which the rest of the swarm walks through.
- **The kill chain is a probability stack.** detect → track → identify → defeat, each < 1. Multiply
  realistic values and leakers are arithmetic, not bugs.
- **The GPS-denied / autonomous threat.** Drones on visual-inertial navigation ignore EW and emit no
  RF, so they're detected late and your cheap first line of defense does nothing.
- **Heterogeneity & decoys.** Real waves mix cheap mass, decoys (no warhead, but they still draw a
  shot), and hardened autonomous drones.

A spec sheet can't express any of these. A *model* can. This sandbox lets you feel "stack your
defense on EW and a GPS-denied swarm renders half your investment useless and arrives before you can
react" — and then reason about which posture actually survives.

---

## 2. What it does

One deterministic simulation engine behind a validated contract, with several consumers:

- **Engine** (`engine/`) — a seeded, discrete-time engagement loop: threats close on an asset,
  sensors detect them (a range gate), the defender allocates shots via a swappable policy, the
  kill-chain stack decides outcomes, magazines deplete and reload, leakers are counted. Same seed →
  byte-identical run.
- **Monte Carlo** (`engine/montecarlo.py`) — one run lies; the distribution tells the truth. Runs a
  scenario hundreds of times and aggregates leakers, cost-exchange, attrition, magazine timeline, and
  per-effector consumption, plus the median-leaker run for replay.
- **Metrics dashboard** (`frontend/`) — React + TypeScript: cost-exchange headline + verdict, leaker
  distribution, attrition curve, magazine timeline, and A/B scenario compare.
- **Interactive mission builder** — compose a swarm and a defense loadout (simple knobs + an Advanced
  panel for every field), hit **Run**, compare two postures. This is the operator loop.
- **2D engagement replay** — a radar-scope animation of the representative run: threats closing,
  detection waking up, shots, kills, leakers crossing the line.
- **Requirements solver** (`engine/requirements.py`) — inverse design (see §4).
- **Bridge** (`server.py`) — a thin localhost FastAPI process so the UI can compose and run live.
  A stateless consumer of the same contract — no database, no deployment.

---

## 3. The argument — three canonical scenarios

These three runs *are* the thesis. (500× Monte Carlo, seed 0.)

| Scenario | Median leakers | Armed | Cost-exchange | The lesson |
|----------|---------------:|------:|--------------:|------------|
| `all_ew_vs_autonomous` | 30 / 30 | 30 | **0.00x** | Cheap but useless vs GPS-denied: a "perfect" ratio while everything leaks. Cost-exchange alone is gameable. |
| `kinetic_vs_mass_and_decoys` | 29 | 17 | **23.15x** | You win shots and lose the bank; the magazine runs dry and the back half of the wave walks through. |
| `layered_mix` | 0 | 0 | **0.50x** | The sustainable answer: cheap layers absorb mass, expensive shots reserved for what needs them. |

The all-EW row is the teaching moment: **the metrics only mean something as a set** — cost-exchange
answers "at what price," leakers answer "did it work," neither is a verdict alone.

---

## 4. The requirements solver + logistics ledger

The simulator answers the *forward* question ("this defense vs this swarm → what happens?"). A
planner works it *backwards*: **"given this threat picture and a required outcome, what's the
cheapest posture that meets it — and how long can it sustain?"**

`solve()` brute-forces a **pre-registered** grid of procurable postures and returns the cheapest one
meeting a leak tolerance, a **cost-vs-protection frontier**, and — when nothing works — the
**best-achievable posture + the gap** (a dead end becomes a requirement).

The headline is the **logistics ledger — waves-until-black**: `magazine ÷ rounds-burned-per-wave` =
how many waves you survive before resupply. Cost-exchange is the snapshot; sustainment is the
integral (the Red Sea / Ukraine lesson).

Run it: `python cli.py layered_mix --requirements --max-leakers 2 --runs 500`. With the reservation
trick *withheld* from the search, it independently rediscovers the layered posture (~$480k) — and
shows it burns ~its whole magazine each wave (**waves-until-black ≈ 1.0**: adequate for one wave, on
the edge of sustainment). The frontier ends near **$24M for the last leaker** — the cost-exchange
trap, quantified.

---

## 5. What we cut, and why (the conscious trades)

Articulating the cut is part of the work. Each is a trade, not an omission:

- **No sensor physics** (no RCS, clutter, RF/IR). Detection is an abstract range. *It's the fidelity
  black hole and adds nothing to a thesis about economics.*
- **No 3D / terrain / aerodynamics.** A 2D plane and simple kinematics. *Dimensionality multiplies
  effort without changing the cost/saturation conclusions.*
- **No learned agents (RL).** Scripted swarm + a simple, swappable defender policy. *A 48-hour black
  hole; the seam makes it a clean next-week add.*
- **No EW signal modeling.** Soft-kill is a probability + an immunity flag. *Model the outcome, not
  the waveform.*
- **No database / auth / deployment.** A thin local bridge was added deliberately for the operator
  loop; persistence and scale are deferred.
- **Numbers are order-of-magnitude from open sources** — illustrative, not precise or classified.

---

## 6. Where it goes — scalability

The discipline: **design the seams, defer the scale.**

- **Baked in now:** the engine⇄consumer contract (swap/add frontends freely), data-driven
  threats/effectors/scenarios, seeded determinism, a separated assignment policy, and the solver's
  injectable evaluator + inventory.
- **The roadmap (falls straight out of the cuts):** provenance/versioning on every parameter (source,
  confidence, as-of) so an analyst knows what they're working with; war-stock / reprocurement-rate
  modeling on top of the ledger; smarter shot allocation under saturation; decision-latency modeling;
  adaptive swarm tactics; ingesting an authoritative inventory feed so the solver's recommendations
  become real.

The line this earns: *the engine is a standalone library behind a validated schema; every consumer
(CLI, dashboard, bridge) only reads that contract; scaling means adding consumers or running the
engine as a service — without ever touching the simulation logic.*

---

## 7. Run it

> Paste one command at a time. (Avoid trailing `# comments` — some shells treat `#` literally.)

Setup:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,server]"
```

Tests (fast: determinism, conservation, canonical, API, solver search logic — expect 45 passed, 3 skipped):

```bash
pytest -q
```

Explore the engine:

```bash
python cli.py --list
python cli.py layered_mix --runs 500
for s in all_ew_vs_autonomous kinetic_vs_mass_and_decoys layered_mix; do python cli.py "$s" --runs 500; echo; done
```

Inverse design — cheapest posture meeting a leak tolerance, plus the logistics ledger:

```bash
python cli.py layered_mix --requirements --max-leakers 2 --runs 500
```

### Interactive dashboard — one command

```bash
./run.sh
```

This sets up the venv + deps on first run, starts the engine bridge and the dashboard together, and
opens on `http://localhost:5173`. Press Ctrl+C once to stop both.

### Interactive dashboard — manual (two terminals)

Terminal 1 — the engine bridge (serves `http://127.0.0.1:8000`):

```bash
source .venv/bin/activate
python server.py
```

Terminal 2 — the dashboard (opens `http://localhost:5173`):

```bash
cd frontend
npm install
npm run dev
```

In the UI: pick a preset or compose your own swarm + defense, toggle **Advanced**, hit **Run**, use
**A/B compare**, and play the **Engagement replay**.

---

## 8. Demo walkthrough (the 3-minute narrative)

1. **The trap.** Open `all_ew_vs_autonomous`. Headline: cost-exchange `0.00x` (green!) but verdict
   "Defense overwhelmed", 30 armed leakers. *"A great ratio and a total loss — cost-exchange alone
   lies."*
2. **The bankruptcy.** A/B against `kinetic_vs_mass_and_decoys`: `23.15x`, magazine runs dry. *"You
   win the shots and lose the war economically."*
3. **The answer.** Switch A to `layered_mix`: 0 armed leakers at `0.50x`, "Sustainable". Play the
   engagement replay — EW thins the mass, interceptors hold the autonomous cluster.
4. **The planner's question.** `python cli.py layered_mix --requirements --max-leakers 2 --runs 500`.
   It rediscovers the layered posture from a pre-registered grid, prices it, and exposes
   **waves-until-black ≈ 1.0** — adequate for one wave, not a campaign.

---

## 9. Layout

```
engine/      pure simulation library (models, rng, assignment policy, step loop, Monte Carlo, requirements solver)
schema/      the engine<->consumer contract (result.py) + YAML loader (with overrides) + solver re-exports
scenarios/   data-driven threats / effectors / scenarios
cli.py       run a scenario / Monte Carlo / requirements solve; --all exports dashboard data
server.py    thin localhost FastAPI bridge: /api/catalog, /api/run, /api/requirements
tests/       determinism, conservation, canonical validation, API, and the solver test spine
frontend/    React + TypeScript + Vite dashboard, mission builder, and engagement replay
```

The engine is the protected core: no I/O, no rendering, emits a validated result, and every consumer
only ever reads that contract.

# Counter-Swarm Sandbox — Architecture & Direction

> A simulation sandbox that demonstrates *cost and saturation* — not lethality — decide the
> modern counter-drone fight. Configure a layered defense, throw a heterogeneous drone swarm at
> it, and measure what actually matters: leakers, attrition, and cost-exchange.

This document is the plan of record. It defines **what** we're solving, **why** it's worth
building, and **how** the system is designed — before any code is written. It is structured so
that sections 2, 11, and 12 map directly onto the three questions the submission writeup must
answer (why this / what we cut / what's next).

---

## 1. The one-line thesis

Counter-swarm defense is not a problem of *killing a drone* — that's solved. It's a problem of
**economics, saturation, and the speed of the kill chain**. This sandbox makes those forces
visible and tunable, so you can reason about *which defensive posture survives contact* with a
modern swarm rather than which one looks impressive on a spec sheet.

---

## 2. The problem — what we're solving, and why it's worth it

Open-source reporting from the Ukraine, Red Sea, and Poland theaters converges on a single,
counter-intuitive lesson: defenders can intercept drones and still lose. The failure modes are
structural, not technical.

**The cost-exchange trap.** A one-way attack drone costs on the order of $20–30k. The interceptors
fired at them run into the millions — a high-end surface-to-air shot against a cheap drone is a
cost ratio in the hundreds-to-one. Even when interception works most of the time, the attacker
wins the economic exchange. *Stopping the swarm is not the same as winning.*

**Saturation and magazine depth.** Launchers carry a finite number of ready interceptors. Mass —
throwing more cheap threats than you have shots — is itself the weapon. The decisive moment is
often the magazine running dry mid-wave, after which the rest of the swarm walks through untouched.

**The kill chain is a probability stack.** A successful engagement requires detect → track →
identify → defeat, each with its own probability. Multiply realistic per-stage values and the
combined success drops fast — high single-digit "stops" before one threat leaks. Leakers are not a
bug in the defense; they are the arithmetic.

**The GPS-denied / autonomous threat.** The sharpest emerging problem: drones using visual-inertial
or optical-flow navigation carry no command link and ignore GPS. Electronic warfare — the cheap
first line of defense — does nothing to them, and with no RF emissions they're invisible to
RF-based sensing, so they're detected late (only by radar / EO-IR, at short range against small,
terrain-hugging targets). The operational nightmare is "you only see them once it's too late."

**Heterogeneity and decoys.** Real waves mix cheap mass, decoys (no warhead, but they still consume
an interceptor if engaged), and hardened/autonomous drones, often from multiple axes. Target
prioritization under saturation is where defenses break.

**Why this is worth 48 hours:** every one of these is a force a *model* can express cleanly and a
spec sheet cannot. A sandbox that lets a practitioner feel "stack your defense on EW and a GPS-denied
swarm renders half your investment useless and arrives before you can react" is genuinely useful for
reasoning about posture — and it's built by the person who actually works in the space, which is the
honesty clause of the brief.

---

## 3. What we're building — the sharp slice

A configurable, deterministic **engagement sandbox**:

- You define a **scenario**: a swarm (mix of threat archetypes, size, approach) and a **layered
  defense** (a loadout of effectors with cost, range, magazine, kill probability, and what each
  works against).
- The **engine** simulates the engagement step by step: threats close on a defended asset, sensors
  detect them at type-dependent ranges, the defender allocates shots, the kill-chain probability
  stack decides outcomes, magazines deplete and reload, leakers reach the asset.
- It runs **once for the story** (an animated representative run) and **hundreds of times for the
  truth** (Monte Carlo aggregation), reporting leakers, cost-exchange ratio, attrition over time,
  and when each layer ran dry.

The full vision (3D, real sensors, learned tactics, networked C2) is explicitly *not* the slice —
see §11. The slice is the part that proves the thesis and actually works.

---

## 4. Design principles (the non-negotiables)

1. **Model outcomes, not physics.** Sensors are abstract detection functions (range + probability),
   not radar returns or rendered imagery. This single decision is the project's most important cut
   (§11) — it's what keeps the build inside 48 hours.
2. **One engine, decoupled.** A single authoritative simulation core. Presentation (metrics,
   animation) reads the engine's *output*, never reimplements its logic. The seam between them is an
   explicit data contract.
3. **Deterministic and seeded.** Same seed → same run, every time. Required for reproducibility,
   testing, and honest Monte Carlo.
4. **Data-driven.** Threats, effectors, and scenarios are *data*, not code. Adding a new drone type
   or interceptor is a new entry, not surgery on the loop. This is the primary extensibility axis.
5. **Analysis-first.** The headless engine + metrics is the protected core and ships first. The
   visualization is a second skin layered on a proven engine — it cannot be hollow because the
   numbers underneath are already real.

---

## 5. System architecture

The system is one engine behind a contract, with multiple independent consumers. The engine never
knows who is reading; consumers never simulate anything.

```
  scenario (data)
        │
        ▼
┌───────────────────┐        ┌──────────────────┐        ┌─────────────────────────┐
│  Simulation engine│  emit  │  Result contract │  read  │  Consumers              │
│  (Python, pure)   │ ─────► │  (validated)     │ ─────► │  • Metrics & charts     │
│  sim loop,        │        │  • metrics       │        │  • 2D animation (replay)│
│  kill-chain, cost │        │  • run trace     │        │  • future: API, web …   │
└───────────────────┘        └──────────────────┘        └─────────────────────────┘
```

**Why this shape:** decoupling the engine from presentation behind an explicit schema is what makes
the system both *correct* (logic exists in exactly one place, so it can't drift) and *scalable* (you
add consumers, or run the engine as a service, without touching the simulation). The frontend
replays a recorded trace — it is a dumb renderer, not a second simulator.

**Data flow:**

- **Input:** a scenario (swarm + defense + environment), defined as data.
- **Engine:** runs the engagement. For metrics it runs N times (Monte Carlo); for the animation it
  records one *representative* run's per-timestep state (the *trace*). "Representative" is defined,
  not cherry-picked: it is the run whose leaker count is the median of the Monte Carlo batch (ties
  broken by lowest seed), and the chosen seed is recorded in the trace so the run is reproducible and
  the choice is auditable.
- **Output (the contract):** `metrics.json` (aggregate outcomes + distributions) and `trace.json`
  (per-step state of one run). These two artifacts are the entire interface.
- **Consumers:** the metrics view renders `metrics.json`; the animation frontend replays
  `trace.json`. Both are replaceable; neither contains simulation logic.

---

## 6. Domain model

Every field exists because a §2 force requires it.

**Threat (a drone)**
- `cost` — feeds cost-exchange.
- `speed` — closing rate; sets how long the engagement window is.
- `detection_range` — how close before it's tracked. Small for GPS-denied (the "seen too late"
  mechanic); large for RF-emitting types.
- `soft_kill_immune` — autonomous/GPS-denied drones ignore the EW layer entirely.
- `is_decoy` — no warhead, but consumes a shot if engaged (the economic-rational decoy).
- `warhead` / value — damage dealt if it leaks.

*Archetypes:* cheap-mass (Shahed-like), decoy, autonomous/GPS-denied (the nightmare), optionally a
fast low-RCS terrain-hugger.

**Effector (a defensive layer)**
- `type` — soft-kill (EW), kinetic interceptor, interceptor drone, directed energy.
- `cost_per_shot` — feeds cost-exchange (this is where the trap lives).
- `range` — how far out it can engage.
- `magazine` + `reload_time` — finite capacity; the saturation mechanic.
- `p_kill` — the *defeat* stage probability only (one factor in the kill-chain stack; see Sensor for
  the track/identify factors and §7 step 4 for how they combine).
- `engages` — the set of threat types it actually works against (EW does nothing vs `soft_kill_immune`).
- optional `max_simultaneous` — e.g. directed energy engages one target at a time.
- optional `max_target_speed` — speed ceiling above which the effector cannot engage (this is how
  "directed energy only kills slow targets" is expressed; the `engages` set filters by type, this
  filters by closing rate).

*Archetypes:* EW/jammer (~$0/shot, useless vs autonomous), kinetic interceptor (expensive, high
p_kill, shallow magazine — the cost-exchange villain), interceptor drone ($10–50k, inverts the
ratio), directed energy (near-zero per shot, short range, slow targets, one at a time).

**Sensor** — deliberately abstract. Detection is a hard *gate*: a threat becomes `tracked` when
inside its effective `detection_range` for the defense's sensor suite. Past that gate, the remaining
non-defeat stages of the kill chain are modeled as two probabilities the sensor/C2 suite owns:
- `p_track` — probability of holding a stable track once detected.
- `p_identify` — probability of correctly classifying the track. This is the field that makes
  **decoys economically dangerous**: the defender does *not* read `is_decoy` directly, so a decoy
  passes `p_identify` as a real threat and draws a shot. (See the information model in §7.)

No signal modeling. This is the §4 principle 1 (model outcomes, not physics) in code.

**Information model (important).** The defender has *imperfect information*. The assignment policy
(§7 step 3) sees only what the sensor exposes — position, track state, and a (possibly wrong)
classification — never the ground-truth `is_decoy` / `warhead` fields. Decoys drain interceptors
precisely because the policy cannot tell them apart; if it could, decoys would be inert and the §2
saturation-by-decoy force would vanish.

**Scenario** — a named bundle: swarm composition + size + approach, defense loadout, environment
(detection modifiers, seed). This is the unit the user configures and the engine consumes.

---

## 7. The simulation core — how it works

**Units & timestep.** The sim is dimensionless by design: one step = one tick, and all distances
(`range`, `detection_range`, the asset standoff) share a single abstract length unit. `speed` is
length-per-tick, `reload_time` is counted in ticks, `magazine` is a raw shot count. Numbers are
chosen so a tick reads as "about a second" and a unit as "about a kilometer," but nothing in the
engine depends on that mapping — it exists only to keep the canonical scenarios legible.

A discrete-time loop. Each step:

1. **Move** — threats advance toward the asset by `speed`.
2. **Detect** — a threat becomes `tracked` when within its effective detection range. (GPS-denied
   types get a short range here → detected late → little time to engage.)
3. **Assign** — the defender allocates available effectors to tracked threats via a *policy*
   (v1: simple priority — nearest / highest-value; the policy is a swappable module so a smarter
   optimizer can replace it later without touching the loop).
4. **Engage** — the kill chain is a probability stack, with the *detect* stage already realized as
   the §7 step 2 range gate (no double-counting). For each assigned shot, roll the remaining stack —
   `p_track × p_identify × p_kill` — as a single combined success probability. On success the threat
   is removed; either way the shot consumes ammo and adds `cost_per_shot` to the defender's tally.
   Because the policy acts on the (possibly wrong) `p_identify` outcome rather than ground truth, a
   shot can be spent on a decoy. EW shots are skipped against `soft_kill_immune` threats.
5. **Deplete & reload** — effectors out of ammo are unavailable until `reload_time` elapses.
6. **Leak** — threats reaching the asset are removed and counted as leakers (armed vs decoy
   tracked separately; armed leakers deal damage).

Run until every threat is resolved (defeated or leaked). Leakers emerge naturally from the math —
they are never scripted.

---

## 8. Metrics & outputs — what "winning" means

The headline is deliberately *not* "did you stop the swarm."

- **Cost-exchange ratio** — defender $ spent ÷ attacker $ spent. You can stop everything and still
  lose this. *But it is only meaningful alongside leakers:* a do-nothing defense (e.g. all-EW vs an
  autonomous swarm, §9.1) spends almost nothing and so posts a "great" cost-exchange while every
  threat leaks. The metrics are a set — cost-exchange answers "at what price," leakers answer "did it
  work," and neither is a verdict alone.
- **Leakers** — count, split armed vs decoy; armed leakers = damage to the asset.
- **Attrition curve** — threats alive over time; shows where the defense holds and where it breaks.
- **Magazine timeline** — when each layer ran dry. The dramatic failure point.
- **Monte Carlo distribution** — leakers across hundreds of seeded runs. One run lies (leakers are
  probabilistic); the distribution tells the truth, including the tail where the defense fails.

---

## 9. Canonical scenarios (the argument, and the demo's spine)

Three pre-built scenarios that *are* the thesis, in order:

1. **All-EW vs an autonomous swarm** → catastrophic leak. Proves the GPS-denied point: soft-kill
   immunity + late detection means your cheap defense does almost nothing.
2. **Kinetic-heavy vs cheap mass + decoys** → you "win" tactically but lose on cost-exchange and run
   the magazine dry, leaking the back half of the wave. (The ratio scales with the effector class:
   tens-to-one for a mid-tier kinetic interceptor here, climbing toward the hundreds-to-one of a
   high-end surface-to-air shot in §2 — same trap, different magnitude.)
3. **Layered mix (EW + interceptor drones + directed energy) vs a heterogeneous wave** → the
   sustainable answer: cheap layers absorb mass, expensive shots are reserved for what needs them.

These give the demo a narrative arc and the writeup its evidence.

---

## 10. Build pathway (phased — analysis-first)

- **Phase 0 — Walking skeleton.** Repo, engine package, domain models, seeded RNG, one deterministic
  run printing a result object. No UI.
- **Phase 1 — Engine + analysis core (protected floor).** Full sim loop, Monte Carlo aggregation,
  the three canonical scenarios validated numerically. *If everything else fails, this alone is a
  shippable sharp slice.*
- **Phase 2 — Config + metrics.** Configure/tweak a scenario, run 500×, render metrics so they land
  (cost-exchange front and center, attrition curve, leaker distribution, magazine timeline, A-vs-B
  compare). Complete, demoable analysis tool.
- **Phase 3 — 2D visualization (second skin).** Frontend replays one seeded trace: inbound threats,
  detection waking up, shots, kills, leakers crossing the line. Same engine, just rendered.
- **Phase 4 — Writeup + demo.** README (thesis / the cut / next week), record the walkthrough around
  the three scenarios.

Protect the headless deterministic engine above all else; everything else is replaceable.

---

## 11. The cut — what we deliberately are NOT building, and why

Articulating this is explicitly graded. Each cut is a conscious trade, not an omission.

- **No sensor physics** (no RCS, clutter, IR rendering, RF signal). Detection is an abstract range.
  *Why:* it's the fidelity black hole; it would consume the whole budget and add nothing to the
  thesis, which is about economics, not perception.
- **No 3D, terrain, or real geography.** 2D plane. *Why:* dimensionality multiplies effort without
  changing the cost/saturation conclusions.
- **No aerodynamics / flight dynamics.** Simple kinematics. *Why:* the insight lives in the
  engagement economics, not in how a rotor behaves.
- **No learned / adaptive agents (no RL).** Scripted swarm behaviors + a simple defender policy.
  *Why:* a 48-hour black hole; the swappable-policy seam makes it a clean next-week add.
- **No EW signal modeling.** Soft-kill is a probability + an immunity flag. *Why:* same as sensors —
  model the outcome, not the waveform.
- **No networked C2 / operator-latency modeling.** Assume instantaneous assignment. *Why:* real and
  important (decision speed is a documented bottleneck), but a clean knob to add later, not core to
  the proof.
- **No server / database / accounts / multiplayer.** Local, single session, file-based contract.
  *Why:* infrastructure is scale, and scale is deferred (§12).
- **Numbers are order-of-magnitude from open sources**, illustrative, not precise or classified.

---

## 12. Direction & scalability — where this goes

The goal is to ship a slice that *scales cleanly over time* without over-engineering now. The
discipline: **design the seams, defer the scale.**

**Baked in now (cheap, and these are the scalability):**
- The engine ⇄ consumer **contract** — a validated result schema (pydantic). Swap or add frontends
  freely.
- **Data-driven** threats / effectors / scenarios — extend by adding data, not editing the loop.
- **Seeded determinism** — reproducible scaling, regression testing.
- A separated **assignment-policy module** — swap the simple policy for an optimizer later, untouched
  engine.

**Explicitly deferred (the over-engineering trap — not now):**
- Web server / message queue / database / auth / multiplayer.
- Plugin architecture, distributed compute.
- Live re-run interactivity (replay-from-trace first; live tweak-and-rerun is next-week).

**The "another week" roadmap (falls straight out of the cuts):**
- Smarter shot-allocation under saturation (the real C2 optimization problem).
- Adaptive swarm tactics / light learning.
- Decision-latency modeling (operators saturated, timelines stretch).
- Parameter auto-sweep to find defense breakpoints (where does a posture fail?).
- More archetypes; directed-energy recharge/thermal modeling; 3D multi-axis attacks.

**The writeup line this earns:** *the engine is a standalone library behind a validated result
schema; the frontend is just one consumer; scaling means adding consumers or running the engine as a
service — without ever touching the simulation logic.*

---

## 13. Tech stack & repository layout

**Stack:** Python 3.11+ engine (chosen for analysis fit and integration with existing tooling);
pydantic v2 for the result contract and config validation; a thin CLI to run scenarios and emit
JSON. The frontend is **React + TypeScript + Vite**: React owns the application shell (scenario
config, metrics dashboard, A/B comparison, controls) for its component model and growing-state
scalability; the result contract is mirrored as shared TS types so the seam is type-checked on the
consumer side. The 2D animation is a single `<EngagementCanvas>` component that drops to imperative
`requestAnimationFrame` canvas drawing internally (behind a `ref`) — React owns the app *around* the
animation, not the per-frame loop. Metric charts render in the frontend (light lib, e.g. Recharts or
uPlot), since standing up React makes a single rendering surface the coherent choice. Determinism
via a single seeded RNG. Keep dependencies minimal — the repo should read as clean enough to build
on.

**Deliverable floor (the conscious trade):** going React makes the frontend part of the *core*
deliverable, which raises the "it actually works" bar and costs more of the 48 hours. This is
accepted deliberately. The mitigation is the protected floor: the Python engine plus its validated
emitted `metrics.json` stands alone as a complete, demoable analysis core. **If the React app slips,
the engine is still a finished, defensible submission** — because the engine is the thesis and the
frontend is how it's shown, not the thing being proven.

```
swarm-sandbox/
  engine/                  # pure simulation library — no I/O, no rendering
    models.py              # Threat, Effector, Sensor, Scenario
    simulation.py          # the discrete-time step loop
    assignment.py          # defender shot-allocation policy (swappable)
    metrics.py             # aggregate outcomes across runs
    rng.py                 # seeded RNG
  schema/
    result.py              # pydantic: RunTrace, Metrics, Result (the contract)
    loader.py              # YAML -> pydantic: parse/validate threats, effectors, scenarios
  scenarios/               # data-driven definitions
    threats.yaml
    effectors.yaml
    scenarios.yaml         # the three canonical scenarios
  cli.py                   # run one scenario / run Monte Carlo / emit JSON
  pyproject.toml           # packaging + pinned deps (pydantic v2, pyyaml, ...)
  outputs/                 # emitted metrics.json + trace.json (gitignored)
  frontend/                # React + TypeScript + Vite consumer
    index.html
    src/
      types/result.ts      # TS mirror of the pydantic contract
      App.tsx              # application shell
      panels/              # scenario config, metrics dashboard, A/B compare
      EngagementCanvas.tsx # imperative rAF canvas replay, behind a ref
    package.json
  tests/                   # determinism + sanity checks
  README.md                # thesis / the cut / next week (seeded by this doc)
```

---

## 14. Risks & mitigations

- **Metrics underwhelm in a demo (wall of numbers).** → Design the output: lead with the
  cost-exchange figure and the attrition curve; make the magazine-empty moment legible.
- **The frontend eats the clock (React is now core).** → Accepted trade. The Python engine +
  validated `metrics.json` is the protected floor and stands alone as a complete submission; the
  React app is ambition on the presentation layer, not the proof. If it slips, the engine still
  answers the problem.
- **Scope creep toward fidelity.** → §11 is the contract with yourself; re-read it whenever a
  "what if we also modeled…" appears.
- **Over-engineering for scale.** → §12: design seams, defer scale. No infrastructure in the slice.
- **The engine fights you (the one-engine risk).** → Phase 0 walking skeleton first; if the core is
  shaky, the analysis floor (Phase 1) is still a complete, defensible submission.

---

*This document is the spine of the build and the seed of the README. Sections 2, 11, and 12 answer
the three writeup questions directly.*

// TS mirror of the pydantic result contract (schema/result.py).
// This is the consumer side of the engine<->consumer seam (ARCHITECTURE_AND_PLAN.md §5, §13).
// Keep in sync with schema/result.py; the dashboard only ever reads these shapes.

export interface Distribution {
  values: number[];
  mean: number;
  median: number;
  std: number;
  min: number;
  max: number;
  p10: number;
  p90: number;
}

export interface MonteCarloMetrics {
  leakers_total: Distribution;
  leakers_armed: Distribution;
  leakers_decoy: Distribution;
  defeated: Distribution;
  cost_exchange_ratio: Distribution;
  defender_cost: Distribution;
  damage_to_asset: Distribution;
  shots_fired: Distribution;
}

export interface AttritionPoint {
  tick: number;
  mean_alive: number;
}

export interface MagazineStat {
  effector_id: string;
  dry_fraction: number;
  mean_first_dry_tick: number | null;
}

export interface ThreatFrame {
  uid: number;
  category: string;
  position: number;
  alive: boolean;
  tracked: boolean;
}

export interface EffectorFrame {
  effector_id: string;
  ammo: number;
  reloading: boolean;
}

export interface ShotRecord {
  effector_id: string;
  target_uid: number;
  hit: boolean;
  cost: number;
}

export interface Frame {
  tick: number;
  threats: ThreatFrame[];
  effectors: EffectorFrame[];
  shots: ShotRecord[];
  kills: number[];
  leaks: number[];
}

export interface RunTrace {
  seed: number;
  ticks: number;
  frames: Frame[];
}

export interface MonteCarloResult {
  scenario_name: string;
  runs: number;
  base_seed: number;
  total_threats: number;
  armed_threats: number;
  metrics: MonteCarloMetrics;
  attrition_curve: AttritionPoint[];
  magazine_timeline: MagazineStat[];
  representative_seed: number;
  representative: RunTrace;
}

export interface ManifestEntry {
  name: string;
  description: string;
  file: string;
  runs: number;
}

export interface Manifest {
  scenarios: ManifestEntry[];
}

// TS mirror of the config side of the contract (engine/models.py).
// These are the shapes an operator composes and POSTs to /api/run.

export interface ThreatSpec {
  id: string;
  category: string;
  cost: number;
  speed: number;
  detection_range: number;
  soft_kill_immune: boolean;
  is_decoy: boolean;
  warhead: number;
}

export interface EffectorSpec {
  id: string;
  type: string;
  cost_per_shot: number;
  range: number;
  magazine: number;
  reload_time: number;
  p_kill: number;
  engages: string[] | null;
  max_simultaneous: number;
  max_target_speed: number | null;
}

export interface SensorSpec {
  p_track: number;
  p_identify: number;
}

export interface SwarmEntry {
  spec: ThreatSpec;
  count: number;
}

export interface DefenseSpec {
  sensor: SensorSpec;
  effectors: EffectorSpec[];
}

export interface Environment {
  detection_modifier: number;
}

export interface Scenario {
  name: string;
  description?: string;
  seed: number;
  approach_distance: number;
  swarm: SwarmEntry[];
  defense: DefenseSpec;
  environment: Environment;
}

export interface Catalog {
  threats: ThreatSpec[];
  effectors: EffectorSpec[];
  presets: Scenario[];
}

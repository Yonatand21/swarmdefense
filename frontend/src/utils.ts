import type { Distribution } from "./types/result";

export function fmtMoney(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}k`;
  return `$${value.toFixed(0)}`;
}

export function fmtRatio(value: number): string {
  return `${value.toFixed(2)}x`;
}

export interface HistBin {
  label: string;
  count: number;
}

// Integer-valued histogram (leaker counts are integers): one bar per observed value in range.
export function histogram(values: number[]): HistBin[] {
  if (values.length === 0) return [];
  const min = Math.floor(Math.min(...values));
  const max = Math.ceil(Math.max(...values));
  const counts = new Map<number, number>();
  for (let v = min; v <= max; v++) counts.set(v, 0);
  for (const v of values) {
    const k = Math.round(v);
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  return Array.from(counts.entries()).map(([k, count]) => ({ label: String(k), count }));
}

// A qualitative verdict for the headline, from the median outcomes.
// Proportional to the mission so it stays meaningful for any operator-built swarm size.
export function verdict(
  costExchange: Distribution,
  armedLeakers: Distribution,
  armedThreats: number
): {
  label: string;
  tone: "good" | "warn" | "bad";
} {
  const ce = costExchange.median;
  const armed = armedLeakers.median;
  const leakFrac = armedThreats > 0 ? armed / armedThreats : 0;
  if (leakFrac > 0.2) return { label: "Defense overwhelmed", tone: "bad" };
  if (ce > 5) return { label: "Wins shots, loses the bank", tone: "warn" };
  if (armed > 0) return { label: "Holds, but leaks", tone: "warn" };
  return { label: "Sustainable", tone: "good" };
}

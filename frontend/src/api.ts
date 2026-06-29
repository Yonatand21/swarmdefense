// Client for the localhost engine bridge (server.py).
// The dashboard composes a Scenario and POSTs it; the engine returns the Monte Carlo distribution.

import type { Catalog, Scenario } from "./types/config";
import type { MonteCarloResult } from "./types/result";

const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

export async function getCatalog(): Promise<Catalog> {
  const res = await fetch(`${API}/catalog`);
  if (!res.ok) throw new Error(await describeError(res));
  return res.json();
}

export async function runScenario(scenario: Scenario, runs: number): Promise<MonteCarloResult> {
  const res = await fetch(`${API}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario, runs }),
  });
  if (!res.ok) throw new Error(await describeError(res));
  return res.json();
}

async function describeError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body?.detail) {
      const detail = Array.isArray(body.detail)
        ? body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ")
        : body.detail;
      return `${res.status}: ${detail}`;
    }
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status}). Is the engine bridge running?  python server.py`;
}

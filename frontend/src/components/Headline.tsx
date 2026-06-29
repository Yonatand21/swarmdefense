import type { MonteCarloResult } from "../types/result";
import { fmtMoney, fmtRatio, verdict } from "../utils";

export function Headline({ mc }: { mc: MonteCarloResult }) {
  const m = mc.metrics;
  const v = verdict(m.cost_exchange_ratio, m.leakers_armed, mc.armed_threats);
  return (
    <div className="headline">
      <div className={`verdict verdict-${v.tone}`}>{v.label}</div>
      <div className="headline-grid">
        <Stat
          label="Cost-exchange (median)"
          value={fmtRatio(m.cost_exchange_ratio.median)}
          sub="defender $ / attacker $ - lower is better"
          tone={m.cost_exchange_ratio.median > 5 ? "bad" : "good"}
        />
        <Stat
          label="Armed leakers (median)"
          value={`${m.leakers_armed.median}`}
          sub={`of ${mc.armed_threats} armed (${mc.total_threats} total) - damage that lands`}
          tone={
            mc.armed_threats > 0 && m.leakers_armed.median / mc.armed_threats > 0.2
              ? "bad"
              : m.leakers_armed.median > 0
                ? "warn"
                : "good"
          }
        />
        <Stat
          label="Defender spend (mean)"
          value={fmtMoney(m.defender_cost.mean)}
          sub={`${m.shots_fired.mean.toFixed(0)} shots fired`}
        />
      </div>
      <p className="caveat">
        Read together: cost-exchange answers "at what price", leakers answer "did it work". Neither
        is a verdict alone - a do-nothing defense posts a great ratio while everything leaks.
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "good" | "warn" | "bad";
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone ? `tone-${tone}` : ""}`}>{value}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  );
}

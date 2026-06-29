import type { MagazineStat } from "../types/result";

export function MagazineTimeline({ stats }: { stats: MagazineStat[] }) {
  const anyDry = stats.some((s) => s.dry_fraction > 0);
  if (!anyDry) {
    return <p className="muted">No layer ran dry - magazine depth never became the bottleneck.</p>;
  }
  return (
    <ul className="magazine">
      {stats.map((s) => {
        const dry = s.dry_fraction > 0;
        return (
          <li key={s.effector_id} className={dry ? "mag-dry" : "mag-ok"}>
            <span className="mag-name">{s.effector_id}</span>
            {dry ? (
              <span className="mag-detail">
                ran dry ~tick {s.mean_first_dry_tick?.toFixed(0)}{" "}
                <em>({Math.round(s.dry_fraction * 100)}% of runs)</em>
              </span>
            ) : (
              <span className="mag-detail muted">held the line</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

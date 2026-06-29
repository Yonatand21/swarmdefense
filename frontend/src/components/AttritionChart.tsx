import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AttritionPoint } from "../types/result";

export function AttritionChart({ curve, color }: { curve: AttritionPoint[]; color: string }) {
  const data = curve.map((p) => ({ tick: p.tick, alive: Number(p.mean_alive.toFixed(2)) }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#23314a" />
        <XAxis dataKey="tick" stroke="#7c8aa5" fontSize={12} />
        <YAxis stroke="#7c8aa5" fontSize={12} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "#0f1726", border: "1px solid #23314a", borderRadius: 8 }}
          labelFormatter={(l) => `tick ${l}`}
          formatter={(val) => [`${val}`, "mean alive"]}
        />
        <Line type="monotone" dataKey="alive" stroke={color} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

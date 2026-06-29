import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Distribution } from "../types/result";
import { histogram } from "../utils";

export function LeakerHistogram({ dist, color }: { dist: Distribution; color: string }) {
  const data = histogram(dist.values);
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#23314a" />
        <XAxis dataKey="label" stroke="#7c8aa5" fontSize={12} />
        <YAxis stroke="#7c8aa5" fontSize={12} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "#0f1726", border: "1px solid #23314a", borderRadius: 8 }}
          labelFormatter={(l) => `${l} leakers`}
          formatter={(val) => [`${val} runs`, "frequency"]}
        />
        <ReferenceLine
          x={String(Math.round(dist.median))}
          stroke="#e8b84b"
          strokeDasharray="4 2"
          label={{ value: "median", fill: "#e8b84b", fontSize: 11, position: "top" }}
        />
        <Bar dataKey="count" fill={color} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

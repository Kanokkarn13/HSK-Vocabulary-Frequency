import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TopWordRow } from "../api/types";

const BAR_COLOR = "#7d2740";
const BAR_COLOR_UNOFFICIAL = "#c9bfb4";

export function TopWordsChart({ items }: { items: TopWordRow[] }) {
  const data = [...items].slice(0, 15).map((it) => ({ ...it, label: it.word }));
  const maxWordLength = Math.max(...data.map((it) => it.label.length), 1);
  const yAxisWidth = Math.min(140, Math.max(56, maxWordLength * 22 + 16));

  return (
    <div className="h-[540px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="currentColor" className="text-ink-200 dark:text-ink-800" />
          <XAxis type="number" tick={{ fontSize: 12 }} stroke="currentColor" className="text-ink-400" />
          <YAxis
            type="category"
            dataKey="label"
            width={yAxisWidth}
            interval={0}
            tick={{ fontSize: 18, fontFamily: "var(--font-zh)" }}
            stroke="currentColor"
            className="text-ink-600 dark:text-ink-300"
          />
          <Tooltip
            formatter={(value, _name, entry) => [
              `${Number(value).toLocaleString()} ครั้ง`,
              entry?.payload?.in_official_wordlist ? "อยู่ใน HSK wordlist" : "ไม่อยู่ใน HSK wordlist",
            ]}
            contentStyle={{
              borderRadius: 12,
              border: "1px solid #ded7cf",
              fontSize: 13,
              fontFamily: "var(--font-zh)",
              background: "#ffffff",
            }}
            labelStyle={{ color: "#23201d", fontWeight: 600 }}
            itemStyle={{ color: "#7d2740" }}
          />
          <Bar dataKey="total_frequency" radius={[0, 6, 6, 0]} barSize={16}>
            {data.map((entry, idx) => (
              <Cell
                key={idx}
                fill={entry.in_official_wordlist ? BAR_COLOR : BAR_COLOR_UNOFFICIAL}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

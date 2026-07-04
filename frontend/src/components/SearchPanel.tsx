import { useState } from "react";
import { searchWord } from "../api/client";
import type { SearchWordResponse } from "../api/types";
import { toErrorMessage } from "../hooks/useAsync";
import { HskBadge } from "./HskBadge";
import { ErrorPanel, LoadingPanel } from "./StatusPanel";

export function SearchPanel() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<
    | { status: "idle" }
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "success"; data: SearchWordResponse }
  >({ status: "idle" });

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const word = query.trim();
    if (!word) return;
    setState({ status: "loading" });
    try {
      const data = await searchWord(word);
      setState({ status: "success", data });
    } catch (err: unknown) {
      console.error(err);
      setState({ status: "error", message: toErrorMessage(err) });
    }
  }

  return (
    <div className="rounded-2xl border border-ink-200 bg-white p-5 shadow-sm dark:border-ink-800 dark:bg-ink-900">
      <h3 className="mb-3 text-sm font-semibold text-ink-700 dark:text-ink-200">
        ค้นหาคำศัพท์เฉพาะคำ
      </h3>
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="เช่น 你好, 学习, 但是"
          className="font-zh flex-1 rounded-xl border border-ink-200 bg-ink-50 px-4 py-2.5 text-lg outline-none ring-brand-500 transition focus:ring-2 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-100"
        />
        <button
          type="submit"
          className="rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
          disabled={!query.trim()}
        >
          ค้นหา
        </button>
      </form>

      <div className="mt-4">
        {state.status === "loading" && <LoadingPanel label="กำลังค้นหา..." />}
        {state.status === "error" && <ErrorPanel message={state.message} />}
        {state.status === "success" && (
          <SearchResult data={state.data} />
        )}
      </div>
    </div>
  );
}

function SearchResult({ data }: { data: SearchWordResponse }) {
  if (data.aggregates.length === 0 && data.occurrences.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-ink-400">
        ไม่พบคำว่า “{data.word}” ในข้อมูลข้อสอบที่วิเคราะห์
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 rounded-xl bg-ink-50 p-4 dark:bg-ink-800/60">
        <span className="font-zh text-3xl font-semibold text-ink-900 dark:text-ink-50">
          {data.word}
        </span>
        {data.aggregates.map((agg) => (
          <div
            key={agg.source_type}
            className="flex items-center gap-2 rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs dark:border-ink-700 dark:bg-ink-900"
          >
            <span className="font-medium capitalize text-ink-500 dark:text-ink-400">
              {agg.source_type}
            </span>
            <HskBadge level={agg.hsk_level} />
            <span className="font-semibold text-ink-700 dark:text-ink-200">
              {agg.total_frequency.toLocaleString()} ครั้ง
            </span>
          </div>
        ))}
      </div>

      {data.occurrences.length > 0 && (
        <div className="max-h-64 overflow-y-auto rounded-xl border border-ink-100 dark:border-ink-800">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-ink-50 uppercase tracking-wide text-ink-400 dark:bg-ink-900">
              <tr>
                <th className="px-3 py-2">ข้อสอบ</th>
                <th className="px-3 py-2">ประเภท</th>
                <th className="px-3 py-2">ปี</th>
                <th className="px-3 py-2 text-right">จำนวน</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
              {data.occurrences.map((occ, i) => (
                <tr key={i} className="bg-white dark:bg-ink-950">
                  <td className="px-3 py-2 text-ink-600 dark:text-ink-300">
                    {occ.filename ?? occ.exam_id}
                  </td>
                  <td className="px-3 py-2 capitalize text-ink-500 dark:text-ink-400">
                    {occ.source_type}
                  </td>
                  <td className="px-3 py-2 text-ink-500 dark:text-ink-400">
                    {occ.year ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-medium text-ink-700 dark:text-ink-200">
                    {occ.frequency}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

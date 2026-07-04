import { useMemo, useState } from "react";
import type { TopWordRow } from "../api/types";
import { HskBadge } from "./HskBadge";
import { ChevronLeftIcon, ChevronRightIcon, SearchIcon } from "./icons";
import { EmptyPanel } from "./StatusPanel";

const PAGE_SIZE = 50;

function getPageNumbers(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

  const pages = new Set([1, total, current - 1, current, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);

  const result: (number | "ellipsis")[] = [];
  let prev = 0;
  for (const p of sorted) {
    if (prev && p - prev > 1) result.push("ellipsis");
    result.push(p);
    prev = p;
  }
  return result;
}

export function TopWordsTable({ items }: { items: TopWordRow[] }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const matchedItems = useMemo(() => items.filter((row) => row.hsk_level != null), [items]);

  const filtered = useMemo(() => {
    const q = query.trim();
    return q ? matchedItems.filter((row) => row.word.includes(q)) : matchedItems;
  }, [matchedItems, query]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return (
    <div>
      <div className="relative mb-3">
        <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
          placeholder="ค้นหาคำศัพท์ในตารางนี้"
          className="font-zh w-full rounded-xl border border-ink-200 bg-ink-50 py-2.5 pl-9 pr-4 text-sm outline-none ring-brand-500 transition focus:ring-2 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-100"
        />
      </div>

      <p className="mb-2 text-xs text-ink-400 dark:text-ink-500">
        แสดง {visible.length.toLocaleString()} จาก {filtered.length.toLocaleString()} คำ
      </p>

      {filtered.length === 0 ? (
        <EmptyPanel
          title="ไม่พบคำศัพท์ที่ค้นหา"
          description={`ไม่มีคำในรายการนี้ที่ตรงกับ "${query}"`}
        />
      ) : (
        <>
          <div className="overflow-hidden rounded-2xl border border-ink-200 dark:border-ink-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-400 dark:bg-ink-900 dark:text-ink-500">
                <tr>
                  <th className="px-4 py-3 font-medium">#</th>
                  <th className="px-4 py-3 font-medium">คำศัพท์</th>
                  <th className="px-4 py-3 font-medium">ระดับ</th>
                  <th className="px-4 py-3 font-medium text-right">ความถี่</th>
                  <th className="px-4 py-3 font-medium text-right">จำนวนข้อสอบ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                {visible.map((row, idx) => (
                  <tr
                    key={`${row.word}-${row.source_type}`}
                    className="bg-white transition hover:bg-ink-50 dark:bg-ink-950 dark:hover:bg-ink-900"
                  >
                    <td className="px-4 py-3 tabular-nums text-ink-400">
                      {(currentPage - 1) * PAGE_SIZE + idx + 1}
                    </td>
                    <td className="font-zh px-4 py-3 text-lg font-medium text-ink-900 dark:text-ink-50">
                      {row.word}
                    </td>
                    <td className="px-4 py-3">
                      <HskBadge level={row.hsk_level} />
                    </td>
                    <td className="px-4 py-3 text-right font-semibold tabular-nums text-ink-700 dark:text-ink-200">
                      {row.total_frequency.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-ink-500 dark:text-ink-400">
                      {row.exam_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                aria-label="หน้าก่อนหน้า"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-ink-200 text-ink-500 transition hover:bg-ink-50 disabled:opacity-40 disabled:hover:bg-transparent dark:border-ink-700 dark:text-ink-400 dark:hover:bg-ink-800"
              >
                <ChevronLeftIcon className="h-4 w-4" />
              </button>

              {getPageNumbers(currentPage, totalPages).map((p, i) =>
                p === "ellipsis" ? (
                  <span key={`e${i}`} className="px-1.5 text-sm text-ink-400">
                    …
                  </span>
                ) : (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={`h-8 min-w-8 rounded-lg px-2 text-sm font-medium tabular-nums transition ${
                      p === currentPage
                        ? "bg-brand-600 text-white"
                        : "text-ink-600 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800"
                    }`}
                  >
                    {p}
                  </button>
                ),
              )}

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                aria-label="หน้าถัดไป"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-ink-200 text-ink-500 transition hover:bg-ink-50 disabled:opacity-40 disabled:hover:bg-transparent dark:border-ink-700 dark:text-ink-400 dark:hover:bg-ink-800"
              >
                <ChevronRightIcon className="h-4 w-4" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

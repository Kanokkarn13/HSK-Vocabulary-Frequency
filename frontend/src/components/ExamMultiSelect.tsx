import { useEffect, useMemo, useRef, useState } from "react";
import type { ExamRow } from "../api/types";
import { LEVEL_STYLES } from "./HskBadge";

interface ExamMultiSelectProps {
  exams: ExamRow[];
  selected: string[];
  onChange: (examIds: string[]) => void;
}

const NO_LEVEL_STYLE =
  "bg-ink-100 text-ink-700 dark:bg-ink-500/15 dark:text-ink-300";

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="h-3 w-3 text-white">
      <path
        d="M3 8.2l3.2 3.2L13 4.6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function ExamMultiSelect({ exams, selected, onChange }: ExamMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  useEffect(() => {
    if (open) searchRef.current?.focus();
    else setQuery("");
  }, [open]);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const map = new Map<number | null, ExamRow[]>();
    for (const exam of exams) {
      if (q && !exam.exam_id.toLowerCase().includes(q)) continue;
      const list = map.get(exam.hsk_level) ?? [];
      list.push(exam);
      map.set(exam.hsk_level, list);
    }
    return [...map.entries()].sort(([a], [b]) => (a ?? 99) - (b ?? 99));
  }, [exams, query]);

  const toggleExam = (examId: string) => {
    onChange(
      selected.includes(examId)
        ? selected.filter((id) => id !== examId)
        : [...selected, examId],
    );
  };

  const buttonLabel =
    selected.length === 0
      ? "ทุกข้อสอบ"
      : selected.length === 1
        ? selected[0]
        : `เลือกแล้ว ${selected.length} ชุด`;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 rounded-lg border bg-ink-50 px-3 py-1.5 text-sm outline-none ring-brand-500 transition focus:ring-2 dark:bg-ink-800 dark:text-ink-100 ${
          open
            ? "border-brand-400 shadow-sm dark:border-brand-500"
            : "border-ink-200 dark:border-ink-700"
        }`}
      >
        <span
          className={`max-w-[10rem] truncate ${selected.length > 0 ? "font-medium text-brand-700 dark:text-brand-400" : ""}`}
        >
          {buttonLabel}
        </span>
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`h-4 w-4 shrink-0 text-ink-400 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.148l3.71-3.918a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      <div
        className={`absolute left-0 top-full z-20 mt-2 w-72 origin-top-left rounded-xl border border-ink-200 bg-white shadow-xl transition duration-150 ease-out dark:border-ink-700 dark:bg-ink-900 ${
          open
            ? "pointer-events-auto scale-100 opacity-100"
            : "pointer-events-none scale-95 opacity-0"
        }`}
      >
        <div className="border-b border-ink-100 p-2 dark:border-ink-800">
          <div className="relative">
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-300 dark:text-ink-600"
            >
              <path
                fillRule="evenodd"
                d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
                clipRule="evenodd"
              />
            </svg>
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="ค้นหาไฟล์ข้อสอบ..."
              className="w-full rounded-lg border border-ink-200 bg-ink-50 py-1.5 pl-8 pr-2 text-sm outline-none ring-brand-500 transition focus:ring-2 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-100"
            />
          </div>
          <div className="mt-2 flex items-center justify-between px-0.5">
            <span className="text-xs text-ink-400">เลือกแล้ว {selected.length} ชุด</span>
            {selected.length > 0 && (
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
              >
                ล้างทั้งหมด
              </button>
            )}
          </div>
        </div>

        <div className="max-h-64 overflow-y-auto p-2">
          {groups.length === 0 && (
            <p className="px-2 py-4 text-center text-sm text-ink-400">ไม่พบไฟล์ข้อสอบ</p>
          )}
          {groups.map(([level, examsInGroup]) => (
            <div key={level ?? "none"} className="mb-1">
              <div
                className={`sticky top-0 z-10 mb-1 rounded-md px-2 py-1 text-xs font-semibold ${
                  level != null ? (LEVEL_STYLES[level] ?? NO_LEVEL_STYLE) : NO_LEVEL_STYLE
                }`}
              >
                {level != null ? `HSK ${level}` : "ไม่พบระดับ"}
              </div>
              {examsInGroup.map((exam) => {
                const isChecked = selected.includes(exam.exam_id);
                return (
                  <label
                    key={exam.exam_id}
                    className={`flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition ${
                      isChecked
                        ? "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300"
                        : "text-ink-700 hover:bg-ink-50 dark:text-ink-200 dark:hover:bg-ink-800"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleExam(exam.exam_id)}
                      className="sr-only"
                    />
                    <span
                      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition ${
                        isChecked
                          ? "border-brand-600 bg-brand-600"
                          : "border-ink-300 dark:border-ink-600"
                      }`}
                    >
                      {isChecked && <CheckIcon />}
                    </span>
                    {exam.exam_id}
                  </label>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

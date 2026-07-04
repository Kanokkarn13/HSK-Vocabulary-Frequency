import { useEffect, useRef, useState } from "react";
import type { ExamRow } from "../api/types";
import { LEVEL_STYLES } from "./HskBadge";

interface ExamMultiSelectProps {
  exams: ExamRow[];
  selected: string[];
  onChange: (examIds: string[]) => void;
}

const NO_LEVEL_STYLE =
  "bg-ink-100 text-ink-700 dark:bg-ink-500/15 dark:text-ink-300";

export function ExamMultiSelect({ exams, selected, onChange }: ExamMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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

  const groups = new Map<number | null, ExamRow[]>();
  for (const exam of exams) {
    const key = exam.hsk_level;
    const list = groups.get(key) ?? [];
    list.push(exam);
    groups.set(key, list);
  }
  const groupKeys = [...groups.keys()].sort((a, b) => (a ?? 99) - (b ?? 99));

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
        className="flex items-center gap-2 rounded-lg border border-ink-200 bg-ink-50 px-3 py-1.5 text-sm outline-none ring-brand-500 transition focus:ring-2 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-100"
      >
        <span className="max-w-[10rem] truncate">{buttonLabel}</span>
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`h-4 w-4 shrink-0 text-ink-400 transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.148l3.71-3.918a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-2 max-h-80 w-72 overflow-y-auto rounded-xl border border-ink-200 bg-white p-2 shadow-lg dark:border-ink-700 dark:bg-ink-900">
          <div className="mb-1 flex items-center justify-between gap-2 border-b border-ink-100 px-1 pb-2 dark:border-ink-800">
            <span className="text-xs text-ink-400">
              เลือกแล้ว {selected.length} ชุด
            </span>
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

          {groupKeys.map((level) => (
            <div key={level ?? "none"} className="mb-1">
              <div
                className={`sticky top-0 mb-1 rounded-md px-2 py-1 text-xs font-semibold ${
                  level != null ? (LEVEL_STYLES[level] ?? NO_LEVEL_STYLE) : NO_LEVEL_STYLE
                }`}
              >
                {level != null ? `HSK ${level}` : "ไม่พบระดับ"}
              </div>
              {groups.get(level)!.map((exam) => (
                <label
                  key={exam.exam_id}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink-700 hover:bg-ink-50 dark:text-ink-200 dark:hover:bg-ink-800"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(exam.exam_id)}
                    onChange={() => toggleExam(exam.exam_id)}
                    className="h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500 dark:border-ink-600"
                  />
                  {exam.exam_id}
                </label>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

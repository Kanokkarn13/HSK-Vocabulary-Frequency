import type { ExamRow, SourceType } from "../api/types";
import { ExamMultiSelect } from "./ExamMultiSelect";

interface FilterBarProps {
  hskLevel: number | null;
  onHskLevelChange: (level: number | null) => void;
  sourceType: SourceType;
  onSourceTypeChange: (type: SourceType) => void;
  examLevel: number | null;
  onExamLevelChange: (level: number | null) => void;
  examIds: string[];
  onExamIdsChange: (examIds: string[]) => void;
  exams: ExamRow[];
}

const SOURCE_OPTIONS: { value: SourceType; label: string }[] = [
  { value: "all", label: "ทั้งหมด" },
  { value: "reading", label: "การอ่าน" },
  { value: "listening", label: "การฟัง" },
];

export function FilterBar({
  hskLevel,
  onHskLevelChange,
  sourceType,
  onSourceTypeChange,
  examLevel,
  onExamLevelChange,
  examIds,
  onExamIdsChange,
  exams,
}: FilterBarProps) {
  const examLevels = [...new Set(exams.map((e) => e.hsk_level).filter((l): l is number => l != null))].sort();
  const examOptions = exams.filter((e) => examLevel == null || e.hsk_level === examLevel);

  return (
    <div className="space-y-4 rounded-2xl border border-ink-200 bg-white p-4 shadow-sm dark:border-ink-800 dark:bg-ink-900">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="no-scrollbar flex items-center gap-2 overflow-x-auto">
          <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-ink-400">
            ระดับ HSK ของคำศัพท์
          </span>
          <div className="flex gap-1.5">
            <button
              onClick={() => onHskLevelChange(null)}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                hskLevel === null
                  ? "bg-brand-600 text-white shadow-sm"
                  : "bg-ink-100 text-ink-600 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
              }`}
            >
              ทั้งหมด
            </button>
            {[1, 2, 3, 4, 5, 6].map((lvl) => (
              <button
                key={lvl}
                onClick={() => onHskLevelChange(lvl)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                  hskLevel === lvl
                    ? "bg-brand-600 text-white shadow-sm"
                    : "bg-ink-100 text-ink-600 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-ink-400">
            ประเภทข้อสอบ
          </span>
          <div className="flex rounded-full bg-ink-100 p-1 dark:bg-ink-800">
            {SOURCE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => onSourceTypeChange(opt.value)}
                className={`rounded-full px-3 py-1 text-sm font-medium transition ${
                  sourceType === opt.value
                    ? "bg-white text-brand-600 shadow-sm dark:bg-ink-950 dark:text-brand-400"
                    : "text-ink-500 dark:text-ink-400"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-4 border-t border-ink-100 pt-4 sm:flex-row sm:items-center sm:justify-between dark:border-ink-800">
        <div className="no-scrollbar flex items-center gap-2 overflow-x-auto">
          <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-ink-400">
            ระดับข้อสอบ (HSK ของชุดข้อสอบ)
          </span>
          <div className="flex gap-1.5">
            <button
              onClick={() => {
                onExamLevelChange(null);
                onExamIdsChange([]);
              }}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                examLevel === null
                  ? "bg-brand-600 text-white shadow-sm"
                  : "bg-ink-100 text-ink-600 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
              }`}
            >
              ทั้งหมด
            </button>
            {examLevels.map((lvl) => (
              <button
                key={lvl}
                onClick={() => {
                  onExamLevelChange(lvl);
                  onExamIdsChange([]);
                }}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                  examLevel === lvl
                    ? "bg-brand-600 text-white shadow-sm"
                    : "bg-ink-100 text-ink-600 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
                }`}
              >
                HSK {lvl}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-ink-400">
            ไฟล์ข้อสอบ
          </span>
          <ExamMultiSelect exams={examOptions} selected={examIds} onChange={onExamIdsChange} />
        </div>
      </div>
    </div>
  );
}

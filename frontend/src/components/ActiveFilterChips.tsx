import type { SourceType } from "../api/types";
import { XIcon } from "./icons";

interface ActiveFilterChipsProps {
  hskLevel: number | null;
  onHskLevelChange: (level: number | null) => void;
  sourceType: SourceType;
  onSourceTypeChange: (type: SourceType) => void;
  examLevel: number | null;
  onExamLevelChange: (level: number | null) => void;
  examIds: string[];
  onExamIdsChange: (examIds: string[]) => void;
}

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 py-1 pl-3 pr-1.5 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200 dark:bg-brand-500/10 dark:text-brand-300 dark:ring-brand-500/30">
      {label}
      <button
        onClick={onRemove}
        aria-label={`ลบตัวกรอง ${label}`}
        className="flex h-4 w-4 items-center justify-center rounded-full transition hover:bg-brand-100 dark:hover:bg-brand-500/20"
      >
        <XIcon className="h-3 w-3" />
      </button>
    </span>
  );
}

/** Compact summary of active filters so users can see and adjust the current
 * scope from anywhere on the page without scrolling back to the FilterBar. */
export function ActiveFilterChips({
  hskLevel,
  onHskLevelChange,
  sourceType,
  onSourceTypeChange,
  examLevel,
  onExamLevelChange,
  examIds,
  onExamIdsChange,
}: ActiveFilterChipsProps) {
  const hasAny =
    hskLevel != null || sourceType !== "all" || examLevel != null || examIds.length > 0;
  if (!hasAny) return null;

  return (
    <div className="mb-3 flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-ink-400 dark:text-ink-500">กรองอยู่:</span>
      {hskLevel != null && (
        <Chip label={`คำศัพท์ HSK ${hskLevel}`} onRemove={() => onHskLevelChange(null)} />
      )}
      {sourceType !== "all" && (
        <Chip
          label={sourceType === "reading" ? "การอ่าน" : "การฟัง"}
          onRemove={() => onSourceTypeChange("all")}
        />
      )}
      {examLevel != null && (
        <Chip label={`ข้อสอบ HSK ${examLevel}`} onRemove={() => onExamLevelChange(null)} />
      )}
      {examIds.length > 0 &&
        (examIds.length <= 2 ? (
          examIds.map((id) => (
            <Chip
              key={id}
              label={id}
              onRemove={() => onExamIdsChange(examIds.filter((e) => e !== id))}
            />
          ))
        ) : (
          <Chip
            label={`ไฟล์ข้อสอบ ${examIds.length} ชุด`}
            onRemove={() => onExamIdsChange([])}
          />
        ))}
      <button
        onClick={() => {
          onHskLevelChange(null);
          onSourceTypeChange("all");
          onExamLevelChange(null);
          onExamIdsChange([]);
        }}
        className="ml-1 text-xs font-medium text-ink-400 underline-offset-2 transition hover:text-ink-600 hover:underline dark:text-ink-500 dark:hover:text-ink-300"
      >
        ล้างทั้งหมด
      </button>
    </div>
  );
}

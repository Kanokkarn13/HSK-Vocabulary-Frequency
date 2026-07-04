const LEVEL_STYLES: Record<number, string> = {
  1: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  2: "bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-400",
  3: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-400",
  4: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400",
  5: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  6: "bg-lime-100 text-lime-700 dark:bg-lime-500/15 dark:text-lime-400",
};

export function HskBadge({ level }: { level: number | null }) {
  if (level == null) {
    return (
      <span className="inline-flex items-center rounded-full bg-ink-100 px-2.5 py-0.5 text-xs font-medium text-ink-500 dark:bg-ink-500/15 dark:text-ink-400">
        ไม่พบระดับ
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        LEVEL_STYLES[level] ??
        "bg-ink-100 text-ink-700 dark:bg-ink-500/15 dark:text-ink-300"
      }`}
    >
      HSK {level}
    </span>
  );
}

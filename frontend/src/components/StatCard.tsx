interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
}

export function StatCard({ label, value, hint, accent }: StatCardProps) {
  return (
    <div className="p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-400 dark:text-ink-500">
        {label}
      </p>
      <p
        className={`font-display mt-2 text-3xl font-semibold tracking-tight tabular-nums ${
          accent ? "text-brand-600 dark:text-brand-400" : "text-ink-900 dark:text-ink-50"
        }`}
      >
        {value}
      </p>
      {hint && (
        <p className="mt-1 text-xs text-ink-400 dark:text-ink-500">{hint}</p>
      )}
    </div>
  );
}

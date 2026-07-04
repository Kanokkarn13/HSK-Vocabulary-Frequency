const LOADING_CHARS = ["学", "习", "汉", "语"];

export function LoadingPanel({ label = "กำลังโหลดข้อมูล..." }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-ink-200 bg-white/60 py-16 text-ink-400 dark:border-ink-800 dark:bg-ink-900/40">
      <div className="flex gap-2 text-4xl font-bold" aria-hidden="true">
        {LOADING_CHARS.map((char, i) => (
          <span
            key={char}
            className="inline-block animate-bounce text-brand-500"
            style={{ animationDelay: `${i * 120}ms` }}
          >
            {char}
          </span>
        ))}
      </div>
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
      <p className="font-semibold">โหลดข้อมูลไม่สำเร็จ</p>
      <p className="mt-1 text-red-600/90 dark:text-red-400/80">{message}</p>
    </div>
  );
}

export function EmptyPanel({
  title = "ยังไม่มีข้อมูล",
  description,
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-ink-200 bg-white/60 py-16 text-center dark:border-ink-800 dark:bg-ink-900/40">
      <p className="font-medium text-ink-500 dark:text-ink-400">{title}</p>
      {description && (
        <p className="max-w-sm text-sm text-ink-400 dark:text-ink-500">
          {description}
        </p>
      )}
    </div>
  );
}

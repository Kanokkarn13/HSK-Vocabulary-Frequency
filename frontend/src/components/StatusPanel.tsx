const LOADING_CHARS = [
  { char: "学", pinyin: "xué" },
  { char: "习", pinyin: "xí" },
  { char: "汉", pinyin: "hàn" },
  { char: "语", pinyin: "yǔ" },
];

export function LoadingPanel({ label = "กำลังโหลดข้อมูล..." }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-5 py-16 text-ink-400">
      <div className="flex gap-3" aria-hidden="true">
        {LOADING_CHARS.map((item, i) => (
          <div key={item.char} className="flex flex-col items-center gap-1">
            <span
              className="inline-block animate-bounce text-5xl font-bold text-brand-500 drop-shadow-[0_0_16px_rgba(168,63,92,0.55)] dark:drop-shadow-[0_0_16px_rgba(237,189,201,0.45)]"
              style={{ animationDelay: `${i * 130}ms` }}
            >
              {item.char}
            </span>
            <span
              className="animate-pulse text-xs font-medium text-brand-400"
              style={{ animationDelay: `${i * 130}ms` }}
            >
              {item.pinyin}
            </span>
          </div>
        ))}
      </div>
      <p className="animate-pulse text-sm">{label}</p>
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

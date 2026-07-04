import { MoonIcon, SunIcon } from "./icons";

interface NavbarProps {
  dark: boolean;
  onToggleDark: () => void;
  examCount?: number;
}

export function Navbar({ dark, onToggleDark, examCount }: NavbarProps) {
  return (
    <header className="relative overflow-hidden bg-ink-950 text-ink-50">
      <div
        className="pointer-events-none absolute -top-32 right-[-4rem] h-80 w-80 rounded-full opacity-25 blur-3xl"
        style={{ background: "radial-gradient(circle, var(--color-brand-500), transparent 70%)" }}
      />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(135deg, currentColor 0, currentColor 1px, transparent 1px, transparent 12px)",
        }}
      />

      <div className="relative mx-auto max-w-6xl px-4 pt-3 sm:px-6">
        <div className="flex items-center justify-between border-b border-ink-800/80 pb-3 text-xs text-ink-300">
          <span className="font-display font-medium uppercase tracking-[0.24em] text-ink-400">
            HSK Vocabulary Lab
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={onToggleDark}
              className="flex h-7 w-7 items-center justify-center rounded-full border border-ink-700 text-ink-300 transition hover:border-ink-500 hover:bg-ink-800 hover:text-white"
              aria-label="Toggle dark mode"
            >
              {dark ? <SunIcon className="h-3.5 w-3.5" /> : <MoonIcon className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-5 py-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-start gap-4">
            <span className="font-zh select-none text-4xl font-semibold text-brand-400 sm:text-5xl">
              词频
            </span>
            <div>
              <h1 className="font-display text-2xl font-semibold leading-tight text-white sm:text-[28px]">
                คำศัพท์ที่ข้อสอบ HSK ใช้จริง
              </h1>
              <p className="mt-1.5 max-w-md text-sm leading-relaxed text-ink-300">
                วิเคราะห์ความถี่คำจากข้อสอบ HSK ของจริง แล้วเทียบกับ wordlist ทางการ
                ว่าคำไหนคุ้มค่าแก่การท่องมากที่สุด
              </p>
            </div>
          </div>

          {examCount != null && (
            <div className="flex items-baseline gap-2 self-start rounded-xl border border-ink-800 bg-ink-900/60 px-4 py-2.5 sm:self-auto">
              <span className="font-display tabular-nums text-2xl font-semibold text-white">
                {examCount}
              </span>
              <span className="text-xs text-ink-400">ชุดข้อสอบที่วิเคราะห์แล้ว</span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

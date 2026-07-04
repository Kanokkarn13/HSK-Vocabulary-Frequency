import { useEffect, useRef, useState } from "react";
import { fetchExams, fetchHealth, fetchTopWords } from "./api/client";
import type { SourceType } from "./api/types";
import { ActiveFilterChips } from "./components/ActiveFilterChips";
import { FilterBar } from "./components/FilterBar";
import { FilterIcon, XIcon } from "./components/icons";
import { Navbar } from "./components/Navbar";
import { StatCard } from "./components/StatCard";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "./components/StatusPanel";
import { TopWordsChart } from "./components/TopWordsChart";
import { TopWordsTable } from "./components/TopWordsTable";
import { useAsync } from "./hooks/useAsync";

const FULL_LIST_LIMIT = 10000;

function useDarkMode() {
  const [dark, setDark] = useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
  );
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="mb-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand-600 dark:text-brand-400">
        {eyebrow}
      </p>
      <h3 className="font-display mt-0.5 text-lg font-semibold text-ink-900 dark:text-ink-50">
        {title}
      </h3>
    </div>
  );
}

export default function App() {
  const { dark, toggle } = useDarkMode();
  const [hskLevel, setHskLevel] = useState<number | null>(null);
  const [sourceType, setSourceType] = useState<SourceType>("all");
  const [examLevel, setExamLevel] = useState<number | null>(null);
  const [examIds, setExamIds] = useState<string[]>([]);
  const [apiOk, setApiOk] = useState<boolean | null>(null);

  // Floating filter button: appears once the main FilterBar scrolls out of
  // view, so users deep in the table never have to scroll back up.
  const filterBarRef = useRef<HTMLDivElement>(null);
  const [filterBarVisible, setFilterBarVisible] = useState(true);
  const [filterSheetOpen, setFilterSheetOpen] = useState(false);

  useEffect(() => {
    const el = filterBarRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) =>
      setFilterBarVisible(entry.isIntersecting),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!filterSheetOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFilterSheetOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [filterSheetOpen]);

  const activeFilterCount =
    (hskLevel != null ? 1 : 0) +
    (sourceType !== "all" ? 1 : 0) +
    (examLevel != null ? 1 : 0) +
    (examIds.length > 0 ? 1 : 0);

  useEffect(() => {
    fetchHealth()
      .then(() => setApiOk(true))
      .catch((err: unknown) => {
        console.error(err);
        setApiOk(false);
      });
  }, []);

  const exams = useAsync(() => fetchExams(), []);

  // FilterBar is rendered twice (inline + inside the filter sheet below) so
  // the same controls are reachable whether or not the inline bar is
  // scrolled into view — shared here so the two call sites can't drift.
  const filterBarProps = {
    hskLevel,
    onHskLevelChange: setHskLevel,
    sourceType,
    onSourceTypeChange: setSourceType,
    examLevel,
    onExamLevelChange: setExamLevel,
    examIds,
    onExamIdsChange: setExamIds,
    exams: exams.status === "success" ? exams.data.items : [],
  };

  const topWords = useAsync(
    () => fetchTopWords({ hskLevel, sourceType, examLevel, examIds, limit: FULL_LIST_LIMIT }),
    [hskLevel, sourceType, examLevel, examIds],
  );

  const totalOccurrences =
    topWords.status === "success"
      ? topWords.data.items.reduce((sum, r) => sum + r.total_frequency, 0)
      : null;
  const officialCount =
    topWords.status === "success"
      ? topWords.data.items.filter((r) => r.in_official_wordlist).length
      : null;
  const maxExamCount =
    topWords.status === "success" && topWords.data.items.length > 0
      ? Math.max(...topWords.data.items.map((r) => r.exam_count))
      : null;
  const notInHskCount =
    topWords.status === "success" ? topWords.data.items.length - officialCount! : null;

  return (
    <div className="min-h-screen bg-[#faf8f6] dark:bg-ink-950">
      <Navbar
        dark={dark}
        onToggleDark={toggle}
        examCount={exams.status === "success" ? exams.data.count : undefined}
      />

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
        {apiOk === false && (
          <ErrorPanel message="ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้ในขณะนี้ กรุณาลองใหม่อีกครั้งในภายหลัง" />
        )}

        <div ref={filterBarRef}>
          <FilterBar {...filterBarProps} />
        </div>

        <section className="grid grid-cols-2 divide-y divide-ink-200 overflow-hidden rounded-2xl border border-ink-200 bg-white sm:grid-cols-4 sm:divide-x sm:divide-y-0 dark:divide-ink-800 dark:border-ink-800 dark:bg-ink-900">
          <StatCard
            label="คำศัพท์ที่พบทั้งหมด"
            value={topWords.status === "success" ? topWords.data.total_count.toLocaleString() : "—"}
            hint="ในขอบเขตที่กรองไว้ตอนนี้"
          />
          <StatCard
            label="ความถี่รวม"
            value={totalOccurrences != null ? totalOccurrences.toLocaleString() : "—"}
            hint="ครั้งที่พบในข้อสอบทั้งหมด"
          />
          <StatCard
            label="ชุดข้อสอบสูงสุดที่เจอคำเดียวกัน"
            value={maxExamCount != null ? `${maxExamCount} ชุด` : "—"}
            hint="คำที่พบในข้อสอบหลายชุดที่สุดในตัวกรองนี้"
            accent
          />
          <StatCard
            label="ไม่อยู่ใน HSK"
            value={notInHskCount != null ? notInHskCount.toLocaleString() : "—"}
            hint="คำนอกเหนือคำศัพท์ HSK ทางการ"
          />
        </section>

        <section className="rounded-2xl border border-ink-200 bg-white p-5 shadow-sm dark:border-ink-800 dark:bg-ink-900">
          <SectionHeading eyebrow="ภาพรวม" title="คำศัพท์ที่พบบ่อยที่สุด 15 อันดับ" />
          {topWords.status === "loading" && <LoadingPanel />}
          {topWords.status === "error" && <ErrorPanel message={topWords.error} />}
          {topWords.status === "success" &&
            (topWords.data.items.length > 0 ? (
              <TopWordsChart items={topWords.data.items} />
            ) : (
              <EmptyPanel description="ไม่พบคำศัพท์ที่ตรงกับตัวกรองนี้ ลองเปลี่ยนตัวกรองด้านบน" />
            ))}
        </section>

        <section className="rounded-2xl border border-ink-200 bg-white p-5 shadow-sm dark:border-ink-800 dark:bg-ink-900">
          <SectionHeading eyebrow="รายละเอียด" title="ตารางคำศัพท์ทั้งหมด" />
          <ActiveFilterChips
            hskLevel={hskLevel}
            onHskLevelChange={setHskLevel}
            sourceType={sourceType}
            onSourceTypeChange={setSourceType}
            examLevel={examLevel}
            onExamLevelChange={setExamLevel}
            examIds={examIds}
            onExamIdsChange={setExamIds}
          />
          {topWords.status === "loading" && <LoadingPanel />}
          {topWords.status === "error" && <ErrorPanel message={topWords.error} />}
          {topWords.status === "success" &&
            (topWords.data.items.length > 0 ? (
              <TopWordsTable items={topWords.data.items} />
            ) : (
              <EmptyPanel />
            ))}
        </section>

        <footer className="flex flex-col items-center gap-1 py-8 text-center text-xs text-ink-400 dark:text-ink-600">
          <span className="font-zh text-base text-ink-300 dark:text-ink-700">词汇 · 频率 · 分析</span>
          <span>HSK Vocabulary Frequency Analyzer — Data Engineering project</span>
        </footer>
      </main>

      {!filterBarVisible && !filterSheetOpen && (
        <button
          onClick={() => setFilterSheetOpen(true)}
          className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full bg-brand-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-600/30 transition hover:bg-brand-700"
        >
          <FilterIcon className="h-4 w-4" />
          ตัวกรอง
          {activeFilterCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-white px-1 text-xs font-bold text-brand-700">
              {activeFilterCount}
            </span>
          )}
        </button>
      )}

      {filterSheetOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 backdrop-blur-sm sm:items-center sm:p-4"
          onClick={() => setFilterSheetOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="ตัวกรอง"
        >
          <div
            className="max-h-[85vh] w-full overflow-y-auto overflow-x-hidden rounded-t-2xl bg-[#faf8f6] p-4 pb-6 shadow-xl sm:max-w-2xl sm:rounded-2xl dark:bg-ink-950"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-700 dark:text-ink-200">ตัวกรอง</h3>
              <button
                onClick={() => setFilterSheetOpen(false)}
                aria-label="ปิด"
                className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-400 transition hover:bg-ink-100 hover:text-ink-600 dark:hover:bg-ink-800 dark:hover:text-ink-300"
              >
                <XIcon className="h-4 w-4" />
              </button>
            </div>
            <FilterBar {...filterBarProps} />
            <button
              onClick={() => setFilterSheetOpen(false)}
              className="mt-4 w-full rounded-xl bg-brand-600 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
            >
              ดูผลลัพธ์
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

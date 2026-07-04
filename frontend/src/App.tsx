import { useEffect, useState } from "react";
import { fetchExams, fetchHealth, fetchTopWords } from "./api/client";
import type { SourceType } from "./api/types";
import { FilterBar } from "./components/FilterBar";
import { Navbar } from "./components/Navbar";
import { SearchPanel } from "./components/SearchPanel";
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
  const [examId, setExamId] = useState<string | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(() => setApiOk(true))
      .catch((err: unknown) => {
        console.error(err);
        setApiOk(false);
      });
  }, []);

  const exams = useAsync(() => fetchExams(), []);

  const topWords = useAsync(
    () => fetchTopWords({ hskLevel, sourceType, examLevel, examId, limit: FULL_LIST_LIMIT }),
    [hskLevel, sourceType, examLevel, examId],
  );

  const totalOccurrences =
    topWords.status === "success"
      ? topWords.data.items.reduce((sum, r) => sum + r.total_frequency, 0)
      : null;
  const officialCount =
    topWords.status === "success"
      ? topWords.data.items.filter((r) => r.in_official_wordlist).length
      : null;
  const matchRate =
    topWords.status === "success" && topWords.data.items.length > 0
      ? Math.round((officialCount! / topWords.data.items.length) * 100)
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

        <FilterBar
          hskLevel={hskLevel}
          onHskLevelChange={setHskLevel}
          sourceType={sourceType}
          onSourceTypeChange={setSourceType}
          examLevel={examLevel}
          onExamLevelChange={setExamLevel}
          examId={examId}
          onExamIdChange={setExamId}
          exams={exams.status === "success" ? exams.data.items : []}
        />

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
            label="อัตราตรงกับ HSK"
            value={matchRate != null ? `${matchRate}%` : "—"}
            hint="สัดส่วนคำที่อยู่ใน wordlist"
            accent
          />
          <StatCard
            label="ไม่อยู่ใน HSK"
            value={notInHskCount != null ? notInHskCount.toLocaleString() : "—"}
            hint="คำนอกเหนือ wordlist ทางการ"
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

        <SearchPanel />

        <section className="rounded-2xl border border-ink-200 bg-white p-5 shadow-sm dark:border-ink-800 dark:bg-ink-900">
          <SectionHeading eyebrow="รายละเอียด" title="ตารางคำศัพท์ทั้งหมด" />
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
          <span>HSK Vocabulary Frequency Analyzer — Data Engineering portfolio project</span>
        </footer>
      </main>
    </div>
  );
}

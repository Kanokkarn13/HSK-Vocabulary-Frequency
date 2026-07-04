import { useEffect } from "react";
import { fetchWordDetail } from "../api/client";
import type { ExampleSentence } from "../api/types";
import { useAsync } from "../hooks/useAsync";
import { HskBadge } from "./HskBadge";
import { XIcon } from "./icons";
import { ErrorPanel, LoadingPanel } from "./StatusPanel";

/** Render a sentence with every occurrence of `word` highlighted. */
function HighlightedSentence({ sentence, word }: { sentence: string; word: string }) {
  const parts = sentence.split(word);
  return (
    <span className="font-zh text-base leading-relaxed text-ink-800 dark:text-ink-100">
      {parts.map((part, i) => (
        <span key={i}>
          {part}
          {i < parts.length - 1 && (
            <span className="rounded bg-brand-100 px-0.5 font-semibold text-brand-700 dark:bg-brand-500/20 dark:text-brand-300">
              {word}
            </span>
          )}
        </span>
      ))}
    </span>
  );
}

function SourceChip({ s }: { s: ExampleSentence }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-400 dark:text-ink-500">
      <span
        className={`rounded px-1.5 py-0.5 font-medium ${
          s.source_type === "listening"
            ? "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-400"
            : "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-400"
        }`}
      >
        {s.source_type === "listening" ? "การฟัง" : "การอ่าน"}
      </span>
      <span className="truncate" title={s.filename ?? s.exam_id}>
        {s.filename ?? s.exam_id}
      </span>
    </span>
  );
}

export function WordDetailModal({ word, onClose }: { word: string; onClose: () => void }) {
  const detail = useAsync(() => fetchWordDetail(word), [word]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`รายละเอียดคำว่า ${word}`}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-xl dark:border-ink-700 dark:bg-ink-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-ink-100 p-5 dark:border-ink-800">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-zh text-4xl font-semibold text-ink-900 dark:text-ink-50">
                {word}
              </span>
              {detail.status === "success" && (
                <>
                  {detail.data.pinyin && (
                    <span className="text-lg text-brand-600 dark:text-brand-400">
                      {detail.data.pinyin}
                    </span>
                  )}
                  <HskBadge level={detail.data.hsk_level} />
                </>
              )}
            </div>
            {detail.status === "success" && detail.data.definition && (
              <p className="mt-2 text-sm text-ink-700 dark:text-ink-200">
                {detail.data.definition}
              </p>
            )}
            {detail.status === "success" && detail.data.definition_th && (
              <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
                {detail.data.definition_th}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="ปิด"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-ink-400 transition hover:bg-ink-100 hover:text-ink-600 dark:hover:bg-ink-800 dark:hover:text-ink-300"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="overflow-y-auto p-5">
          {detail.status === "loading" && <LoadingPanel label="กำลังโหลดรายละเอียด..." />}
          {detail.status === "error" && <ErrorPanel message={detail.error} />}
          {detail.status === "success" && (
            <>
              {!detail.data.in_wordlist && (
                <p className="mb-3 rounded-xl bg-ink-50 p-3 text-xs text-ink-500 dark:bg-ink-800/60 dark:text-ink-400">
                  คำนี้ไม่อยู่ในคำศัพท์ HSK ทางการ จึงไม่มีข้อมูลพินอิน/คำแปล
                </p>
              )}

              {detail.data.sentences.length > 0 ? (
                <>
                  <div className="mb-3 flex items-baseline justify-between gap-2">
                    <h4 className="text-sm font-semibold text-ink-700 dark:text-ink-200">
                      ประโยคตัวอย่างจากข้อสอบจริง
                    </h4>
                    <span className="text-xs text-ink-400 dark:text-ink-500">
                      แสดง {detail.data.sentences.length} จาก{" "}
                      {detail.data.sentence_total.toLocaleString()} ประโยค (
                      {detail.data.file_total.toLocaleString()} ไฟล์)
                    </span>
                  </div>
                  <ul className="space-y-3">
                    {detail.data.sentences.map((s, i) => (
                      <li
                        key={i}
                        className="rounded-xl border border-ink-100 bg-ink-50/60 p-3 dark:border-ink-800 dark:bg-ink-800/40"
                      >
                        <HighlightedSentence sentence={s.sentence} word={word} />
                        <div className="mt-1.5">
                          <SourceChip s={s} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="py-6 text-center text-sm text-ink-400">
                  ไม่พบประโยคตัวอย่างของคำนี้ในข้อสอบที่วิเคราะห์
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

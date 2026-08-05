import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExamRow, TopWordRow } from "../api/types";
import { fetchWordDetail } from "../api/client";
import { ExamMultiSelect } from "./ExamMultiSelect";
import { FilterBar } from "./FilterBar";
import { ActiveFilterChips } from "./ActiveFilterChips";
import { TopWordsTable } from "./TopWordsTable";
import { WordDetailModal } from "./WordDetailModal";

vi.mock("../api/client", () => ({ fetchWordDetail: vi.fn() }));

const exams: ExamRow[] = [
  { exam_id: "2020-01", hsk_level: 3, year: 2020, source_types: ["reading"] },
  { exam_id: "2021-02", hsk_level: 4, year: 2021, source_types: ["listening"] },
  { exam_id: "legacy", hsk_level: null, year: null, source_types: ["reading"] },
];

afterEach(cleanup);

function ExamHarness() {
  const [selected, setSelected] = useState<string[]>([]);
  return <ExamMultiSelect exams={exams} selected={selected} onChange={setSelected} />;
}

function sampleWords(count = 12): TopWordRow[] {
  return Array.from({ length: count }, (_, i) => ({
    word: i === 0 ? "学习" : `词${i}`,
    hsk_level: 1,
    source_type: "all",
    total_frequency: count - i,
    exam_count: 1,
    in_official_wordlist: true,
    pinyin: i === 0 ? "xué xí" : null,
  }));
}

describe("filter controls", () => {
  it("searches, toggles, clears, and closes the exam menu", async () => {
    const user = userEvent.setup();
    render(<ExamHarness />);

    await user.click(screen.getByRole("button", { name: "ทุกข้อสอบ" }));
    expect(screen.getByRole("checkbox", { name: "2020-01" })).toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "2021");
    expect(screen.getByRole("checkbox", { name: "2021-02" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "2020-01" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "2021-02" }));
    fireEvent.mouseDown(document.body);
    expect(screen.getByRole("textbox").closest("div.absolute")).toHaveClass("pointer-events-none");
  });

  it("emits changes from HSK and exam-level filters", async () => {
    const user = userEvent.setup();
    const onHskLevelChange = vi.fn();
    const onSourceTypeChange = vi.fn();
    const onExamLevelChange = vi.fn();
    const onExamIdsChange = vi.fn();
    render(
      <FilterBar
        hskLevel={null}
        onHskLevelChange={onHskLevelChange}
        sourceType="all"
        onSourceTypeChange={onSourceTypeChange}
        examLevel={null}
        onExamLevelChange={onExamLevelChange}
        examIds={["old"]}
        onExamIdsChange={onExamIdsChange}
        exams={exams}
      />,
    );
    await user.click(screen.getByRole("button", { name: "1" }));
    expect(onHskLevelChange).toHaveBeenCalledWith(1);
    await user.click(screen.getByRole("button", { name: "HSK 4" }));
    expect(onExamLevelChange).toHaveBeenCalledWith(4);
    expect(onExamIdsChange).toHaveBeenCalledWith([]);
  });

  it("renders active chips and clears every scope", async () => {
    const user = userEvent.setup();
    const onHskLevelChange = vi.fn();
    const onSourceTypeChange = vi.fn();
    const onExamLevelChange = vi.fn();
    const onExamIdsChange = vi.fn();
    render(
      <ActiveFilterChips
        hskLevel={2}
        onHskLevelChange={onHskLevelChange}
        sourceType="reading"
        onSourceTypeChange={onSourceTypeChange}
        examLevel={3}
        onExamLevelChange={onExamLevelChange}
        examIds={["2020-01", "2020-02", "2020-03"]}
        onExamIdsChange={onExamIdsChange}
      />,
    );
    const buttons = screen.getAllByRole("button");
    await user.click(buttons[buttons.length - 1]);
    expect(onHskLevelChange).toHaveBeenCalledWith(null);
    expect(onSourceTypeChange).toHaveBeenCalledWith("all");
    expect(onExamLevelChange).toHaveBeenCalledWith(null);
    expect(onExamIdsChange).toHaveBeenCalledWith([]);
  });
});

describe("top words table", () => {
  it("filters by normalized pinyin and paginates results", async () => {
    const user = userEvent.setup();
    render(<TopWordsTable items={sampleWords()} />);
    const search = screen.getByPlaceholderText("ค้นหาคำศัพท์หรือพินอิน เช่น 学习, xuexi");
    await user.type(search, "xuexi");
    expect(screen.getByText("学习")).toBeInTheDocument();
    await user.clear(search);
    await user.click(screen.getByRole("button", { name: "2" }));
    expect(screen.getByText("词10")).toBeInTheDocument();
  });
});

describe("word detail modal", () => {
  it("renders fetched metadata, highlighted examples, and closes on Escape", async () => {
    vi.mocked(fetchWordDetail).mockResolvedValue({
      word: "学习",
      pinyin: "xué xí",
      hsk_level: 2,
      definition: "to learn",
      definition_th: "เรียน",
      in_wordlist: false,
      sentences: [
        {
          sentence: "我喜欢学习中文。",
          source_type: "reading",
          filename: "reading.pdf",
          exam_id: "2024-01",
        },
      ],
      sentence_total: 1,
      file_total: 1,
    });
    const onClose = vi.fn();
    render(<WordDetailModal word="学习" onClose={onClose} />);

    expect(await screen.findByText("to learn")).toBeInTheDocument();
    expect(screen.getByText("xué xí")).toBeInTheDocument();
    expect(screen.getByText("reading.pdf")).toBeInTheDocument();
    expect(screen.getByText("我喜欢")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.setup().click(screen.getByRole("button", { name: "ปิด" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

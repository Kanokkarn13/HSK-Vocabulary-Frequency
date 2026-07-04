export type SourceType = "reading" | "listening" | "all";

export interface TopWordRow {
  word: string;
  hsk_level: number | null;
  source_type: SourceType;
  total_frequency: number;
  exam_count: number;
  in_official_wordlist: boolean;
  pinyin: string | null;
}

export interface TopWordsResponse {
  items: TopWordRow[];
  count: number;
  total_count: number;
}

export interface WordOccurrence {
  word: string;
  hsk_level: number | null;
  source_type: Exclude<SourceType, "all">;
  exam_id: string;
  frequency: number;
  in_official_wordlist: boolean;
  year: number | null;
  filename: string | null;
}

export interface WordAggregate {
  word: string;
  hsk_level: number | null;
  source_type: SourceType;
  total_frequency: number;
  exam_count: number;
  in_official_wordlist: boolean;
}

export interface SearchWordResponse {
  word: string;
  aggregates: WordAggregate[];
  occurrences: WordOccurrence[];
}

export interface ExampleSentence {
  sentence: string;
  exam_id: string;
  source_type: Exclude<SourceType, "all">;
  filename: string | null;
  exam_hsk_level: number | null;
}

export interface WordDetailResponse {
  word: string;
  in_wordlist: boolean;
  pinyin: string | null;
  hsk_level: number | null;
  definition: string | null;
  definition_th: string | null;
  sentence_total: number;
  file_total: number;
  sentences: ExampleSentence[];
}

export interface ExamRow {
  exam_id: string;
  hsk_level: number | null;
  year: number | null;
  source_types: ("reading" | "listening")[];
}

export interface ExamsResponse {
  items: ExamRow[];
  count: number;
}

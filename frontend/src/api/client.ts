import axios from "axios";
import type {
  ExamsResponse,
  SearchWordResponse,
  SourceType,
  TopWordsResponse,
} from "./types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10_000,
  // FastAPI's list[str] query params expect repeated "key=a&key=b", not
  // axios's default bracket notation "key[]=a&key[]=b".
  paramsSerializer: { indexes: null },
});

export async function fetchHealth(): Promise<{ status: string }> {
  const { data } = await client.get("/health");
  return data;
}

export async function fetchExams(): Promise<ExamsResponse> {
  const { data } = await client.get<ExamsResponse>("/api/frequency/exams");
  return data;
}

interface ScopeParams {
  hskLevel?: number | null;
  sourceType: SourceType;
  examLevel?: number | null;
  examIds?: string[];
  limit?: number;
}

export async function fetchTopWords(params: ScopeParams): Promise<TopWordsResponse> {
  const { data } = await client.get<TopWordsResponse>("/api/frequency/top", {
    params: {
      hsk_level: params.hskLevel ?? undefined,
      source_type: params.sourceType,
      exam_level: params.examLevel ?? undefined,
      exam_id: params.examIds?.length ? params.examIds : undefined,
      limit: params.limit ?? 50,
    },
  });
  return data;
}

export async function searchWord(word: string): Promise<SearchWordResponse> {
  const { data } = await client.get<SearchWordResponse>("/api/search/word", {
    params: { q: word },
  });
  return data;
}

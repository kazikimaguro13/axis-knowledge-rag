"use client";

import { useState } from "react";
import AnswerPanel from "@/components/AnswerPanel";
import AxisFilter from "@/components/AxisFilter";
import ResultCard from "@/components/ResultCard";
import SearchBar from "@/components/SearchBar";
import { api, AnswerResponse, SearchResultPayload } from "@/lib/api";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string | number>>({});
  const [results, setResults] = useState<SearchResultPayload[]>([]);
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [withRag, setWithRag] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!query && Object.keys(filters).length === 0) {
      return;
    }
    setIsLoading(true);
    setError(null);
    setAnswer(null);
    try {
      if (withRag && query) {
        const ans = await api.answer({ question: query, filters, top_k: 5 });
        setAnswer(ans);
        setResults(ans.sources);
      } else {
        const r = await api.search({ query: query || null, filters, top_k: 10 });
        setResults(r.results);
      }
    } catch (e) {
      setError(String(e));
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
      <AxisFilter filters={filters} onChange={setFilters} />
      <section className="space-y-4">
        <h1 className="text-2xl font-bold">検索</h1>
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={handleSearch}
          isLoading={isLoading}
        />

        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={withRag}
            onChange={(e) => setWithRag(e.target.checked)}
          />
          RAG 回答も生成する (<code>/api/answer</code>)
        </label>

        <AnswerPanel
          text={answer?.text ?? ""}
          citedIds={answer?.cited_ids ?? []}
          isLoading={isLoading && withRag && !!query}
          isDummy={answer?.is_dummy ?? false}
          model={answer?.model ?? null}
          error={error}
        />

        {results.length > 0 && (
          <p className="text-sm text-slate-500">📚 関連資料 {results.length} 件</p>
        )}
        <div className="space-y-3">
          {results.map((r) => (
            <ResultCard
              key={r.id}
              result={r}
              cited={answer?.cited_ids?.includes(r.id) ?? false}
            />
          ))}
        </div>
        {!isLoading && results.length === 0 && !error && (
          <p className="text-sm text-slate-400">
            左のフィルタを設定して検索バーから問い合わせてください。
          </p>
        )}
      </section>
    </div>
  );
}

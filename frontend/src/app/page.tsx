"use client";

import { useState } from "react";
import AxisFilter from "@/components/AxisFilter";
import ResultCard from "@/components/ResultCard";
import SearchBar from "@/components/SearchBar";
import { api, SearchResultPayload } from "@/lib/api";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string | number>>({});
  const [results, setResults] = useState<SearchResultPayload[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!query && Object.keys(filters).length === 0) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const r = await api.search({ query: query || null, filters, top_k: 10 });
      setResults(r.results);
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
        {error && <div className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</div>}
        {results.length > 0 && (
          <p className="text-sm text-slate-500">{results.length} 件の結果</p>
        )}
        <div className="space-y-3">
          {results.map((r) => (
            <ResultCard key={r.id} result={r} />
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

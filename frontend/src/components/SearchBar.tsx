"use client";

import { FormEvent } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
}

export default function SearchBar({ value, onChange, onSubmit, isLoading }: Props) {
  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit();
  }
  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="例: RAG アーキテクチャの設計判断は?"
        aria-label="検索クエリ"
        className="flex-1 rounded border border-slate-300 bg-white px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
      />
      <button
        type="submit"
        disabled={isLoading}
        aria-busy={isLoading}
        className="rounded bg-blue-600 px-4 py-2 font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
      >
        {isLoading ? "検索中..." : "検索"}
      </button>
    </form>
  );
}

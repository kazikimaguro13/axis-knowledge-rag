"use client";

import type { GraphStats } from "@/lib/graphClient";

type Props = {
  onChange: (f: { category?: string; level?: string }) => void;
  stats?: GraphStats;
};

const CATEGORIES = ["技術記事", "メモ", "議事録", "ToDo"];
const LEVELS = ["初級", "中級", "上級"];

export function GraphFilterBar({ onChange, stats }: Props) {
  return (
    <div className="absolute left-3 top-3 z-10 w-56 rounded-lg bg-white/90 p-3 text-xs shadow backdrop-blur">
      <h3 className="mb-2 font-semibold">🕸️ Knowledge Graph</h3>
      {stats && (
        <p className="mb-2 text-slate-600">
          {stats.nodes} nodes, {stats.edges} edges
          <br />
          {stats.isolated} isolated, {stats.weakly_connected_components} components
        </p>
      )}
      <label className="mb-1 block text-slate-700">category</label>
      <select
        onChange={(e) => onChange({ category: e.target.value || undefined })}
        className="mb-2 w-full rounded border px-1 py-0.5"
      >
        <option value="">(指定なし)</option>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      <label className="mb-1 block text-slate-700">level</label>
      <select
        onChange={(e) => onChange({ level: e.target.value || undefined })}
        className="w-full rounded border px-1 py-0.5"
      >
        <option value="">(指定なし)</option>
        {LEVELS.map((l) => (
          <option key={l} value={l}>
            {l}
          </option>
        ))}
      </select>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { api, AxisDef } from "@/lib/api";

interface Props {
  filters: Record<string, string | number>;
  onChange: (filters: Record<string, string | number>) => void;
}

export default function AxisFilter({ filters, onChange }: Props) {
  const [axes, setAxes] = useState<AxisDef[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .axes()
      .then((r) => setAxes(r.axes))
      .catch((e) => setError(String(e)));
  }, []);

  function set(key: string, value: string | number | undefined) {
    const next = { ...filters };
    if (value === undefined || value === "" || value === 0) {
      delete next[key];
    } else {
      next[key] = value;
    }
    onChange(next);
  }

  if (error) {
    return <div className="text-sm text-red-600">軸の取得に失敗: {error}</div>;
  }

  return (
    <aside className="space-y-3">
      <h2 className="text-sm font-semibold text-slate-700">軸フィルタ</h2>
      {axes.map((a) => {
        if (a.type === "enum" && a.values) {
          return (
            <label key={a.name} className="block text-sm">
              <span className="mb-1 block text-slate-600">{a.name}</span>
              <select
                value={(filters[a.name] as string) ?? ""}
                onChange={(e) => set(a.name, e.target.value)}
                className="w-full rounded border border-slate-300 bg-white px-2 py-1"
              >
                <option value="">(指定なし)</option>
                {a.values.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        if (a.type === "integer") {
          return (
            <label key={a.name} className="block text-sm">
              <span className="mb-1 block text-slate-600">{a.name}</span>
              <input
                type="number"
                value={(filters[a.name] as number) ?? ""}
                onChange={(e) => set(a.name, parseInt(e.target.value, 10) || 0)}
                className="w-full rounded border border-slate-300 bg-white px-2 py-1"
              />
            </label>
          );
        }
        return (
          <label key={a.name} className="block text-sm">
            <span className="mb-1 block text-slate-600">{a.name}</span>
            <input
              type="text"
              value={(filters[a.name] as string) ?? ""}
              onChange={(e) => set(a.name, e.target.value)}
              className="w-full rounded border border-slate-300 bg-white px-2 py-1"
            />
          </label>
        );
      })}
    </aside>
  );
}

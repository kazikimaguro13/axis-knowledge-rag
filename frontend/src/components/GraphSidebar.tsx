"use client";

import { useEffect, useState } from "react";
import { fetchNeighbors, type NeighborPayload } from "@/lib/graphClient";

type Props = { docId: string | null; onClose: () => void };

export function GraphSidebar({ docId, onClose }: Props) {
  const [data, setData] = useState<NeighborPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!docId) {
      setData(null);
      setError(null);
      return;
    }
    setData(null);
    setError(null);
    let cancelled = false;
    fetchNeighbors(docId, 1, 20)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [docId]);

  if (!docId) {
    return (
      <aside className="border-l bg-slate-50 p-4 text-sm text-slate-500">
        ノードをクリックすると詳細と隣接ドキュメントが表示されます。
      </aside>
    );
  }

  return (
    <aside className="overflow-y-auto border-l bg-white p-4 text-sm">
      <button
        onClick={onClose}
        className="mb-2 text-xs text-slate-500 hover:underline"
      >
        ✕ 閉じる
      </button>
      {error && <p className="text-xs text-red-500">取得失敗: {error}</p>}
      {!error && !data && <p className="text-slate-400">Loading...</p>}
      {data && (
        <>
          <h3 className="text-base font-semibold">{data.center.title || data.center.id}</h3>
          <p className="mb-3 text-xs text-slate-500">
            <code>{data.center.id}</code> · in_degree {data.center.in_degree} / out_degree{" "}
            {data.center.out_degree}
          </p>
          <div className="mb-4 flex flex-wrap gap-1">
            {Object.entries(data.center.axes).map(([k, v]) => (
              <span
                key={k}
                className="inline-block rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-900"
              >
                {k}: {String(v)}
              </span>
            ))}
          </div>
          <h4 className="mb-2 text-sm font-semibold">
            🔗 隣接 ({data.neighbors.length})
          </h4>
          {data.neighbors.length === 0 ? (
            <p className="text-xs text-slate-400">
              hop=1 で到達できるドキュメントはありません。
            </p>
          ) : (
            <ul className="space-y-1">
              {data.neighbors.map((n) => (
                <li key={n.id} className="text-xs">
                  <span className="font-medium">{n.title || n.id}</span>
                  <span className="ml-1 text-slate-400">({n.id})</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </aside>
  );
}

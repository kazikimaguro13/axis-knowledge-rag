"use client";

import { useEffect, useState } from "react";
import {
  fetchNeighborsBidirectional,
  type GraphNode,
  type NeighborSet,
} from "@/lib/graphClient";

type Props = { docId: string | null; onClose: () => void };

export function GraphSidebar({ docId, onClose }: Props) {
  const [data, setData] = useState<NeighborSet | null>(null);
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
    fetchNeighborsBidirectional(docId, 1, 20)
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
      <aside className="border-l-2 border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">
        <div className="flex flex-col items-start gap-2">
          <span className="text-base">🕸️</span>
          <p>
            ノードを<strong>クリック</strong>すると、その doc の詳細と
            <strong>参照グラフの隣接ノード</strong>が表示されます。
          </p>
          <p className="text-xs text-slate-400">
            ドラッグで視点回転、スクロールでズーム。
          </p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="overflow-y-auto border-l-2 border-slate-200 bg-white p-4 text-sm shadow-sm">
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
          <h3 className="text-base font-semibold">
            {data.center.title || data.center.id}
          </h3>
          <p className="mb-3 text-xs text-slate-500">
            <code>{data.center.id}</code> · in_degree {data.center.in_degree} /
            out_degree {data.center.out_degree}
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

          {data.forwardlinks.length > 0 && (
            <NeighborSection
              heading={`→ 参照している (${data.forwardlinks.length})`}
              ariaLabel="このドキュメントが参照しているドキュメント"
              nodes={data.forwardlinks}
            />
          )}

          {data.backlinks.length > 0 && (
            <NeighborSection
              heading={`← 参照されている (${data.backlinks.length})`}
              ariaLabel="このドキュメントを参照しているドキュメント"
              nodes={data.backlinks}
            />
          )}

          {data.forwardlinks.length === 0 && data.backlinks.length === 0 && (
            <p className="text-xs text-slate-400">
              このドキュメントは独立ノードです (リンク無し)。
            </p>
          )}
        </>
      )}
    </aside>
  );
}

function NeighborSection({
  heading,
  ariaLabel,
  nodes,
}: {
  heading: string;
  ariaLabel: string;
  nodes: GraphNode[];
}) {
  return (
    <section className="mb-4" aria-label={ariaLabel}>
      <h4 className="mb-2 text-sm font-semibold">{heading}</h4>
      <ul className="space-y-1">
        {nodes.map((n) => (
          <li key={n.id} className="text-xs">
            <span className="font-medium">{n.title || n.id}</span>
            <span className="ml-1 text-slate-400">({n.id})</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

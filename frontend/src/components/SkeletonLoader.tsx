"use client";

export default function SkeletonLoader() {
  return (
    <div className="animate-pulse space-y-2 rounded border border-slate-200 bg-white p-4">
      <div className="h-3 w-1/4 rounded bg-slate-200" />
      <div className="h-3 w-full rounded bg-slate-200" />
      <div className="h-3 w-5/6 rounded bg-slate-200" />
      <div className="h-3 w-3/4 rounded bg-slate-200" />
    </div>
  );
}

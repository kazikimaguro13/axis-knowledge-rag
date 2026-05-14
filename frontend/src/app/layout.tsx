import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "axis-knowledge-rag",
  description: "軸検索 + RAG over YAML frontmatter Markdown",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-slate-50 text-slate-900">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="text-lg font-semibold">
              🔍 axis-knowledge-rag
            </Link>
            <nav className="flex gap-4 text-sm">
              <Link href="/" className="hover:underline">
                検索
              </Link>
              <Link href="/chat" className="hover:underline">
                💬 Chat
              </Link>
              <Link href="/graph" className="hover:underline">
                🕸️ Graph
              </Link>
              <Link href="/settings" className="hover:underline">
                設定
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}

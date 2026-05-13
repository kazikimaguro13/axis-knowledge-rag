---
id: "doc_008"
title: "LangChain / LlamaIndex / 自前実装の使い分け"
axes:
  category: "議事録"
  topic: "ツール比較"
  level: "初級"
  author: "Nakashima"
  year: 2026
tags: ["langchain", "llamaindex", "framework"]
refs: []
created: 2026-05-12
updated: 2026-05-12
---

# LangChain / LlamaIndex / 自前実装の使い分け

RAG を作るときの選択肢は大きく 3 つ。LangChain、LlamaIndex、そして自前実装。それぞれ前提と適性が違う。

LangChain は「LLM 周辺の部品を一通り揃えた汎用フレームワーク」で、エージェント・ツール・メモリなど幅広い領域をカバーする。便利な反面、抽象化が厚く、内部で何が起きているか追いづらい。プロトタイプを高速に立ち上げる用途には向くが、長期保守や挙動の細かいチューニングを要求するプロダクトでは負債化しやすい。

LlamaIndex は「データインデックスと検索」に焦点を当てた設計で、ドキュメントローダや query engine の語彙が充実している。RAG 専用に近い使い勝手で、LangChain より見通しがよい。ただし依存ツリーは依然大きい。

自前実装は、薄いラッパで Embedder と VectorStore と LLM を直接呼ぶ方針。本プロジェクトはこちら。利点はデバッグ容易さと依存の少なさで、欠点は便利機能を都度書く必要があること。学習・OSS ポートフォリオ・local-first 用途では合理的な選択になる。3 択は宗教論争ではなく、運用期間と必要機能と読み手のスキルセットの関数だ。

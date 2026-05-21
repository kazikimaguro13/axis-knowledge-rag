---
id: "doc_004"
title: "Claude API と Skills の使い分け"
axes:
  category: "技術記事"
  topic: "Claude"
  level: "中級"
  author: "Nakashima"
  year: 2026
tags: ["claude", "llm", "skills"]
refs: ["doc_001", "doc_003"]
created: 2026-05-12
updated: 2026-05-12
---

# Claude API と Skills の使い分け

Claude API は、テキスト生成・推論・ツール呼び出しといった LLM 機能を直接叩くインターフェース。Skills は、特定のタスク向けに事前定義された手順・知識・サンプルをパッケージ化した「再利用可能な能力」だ。両者は競合ではなく、レイヤーが違う。

実装観点では、ワンショットの生成や要約は API を直接呼ぶのが軽量で予測可能。一方、複数ステップにわたる定型ワークフロー (例: コードレビュー、テスト生成) は Skills 側に手順を集約しておくと再現性と保守性が上がる。本プロジェクトの RAG 機能 (doc_001 参照) は前者寄りで、最小限のラッパで Claude API を叩く。

メタデータ駆動という観点 (doc_003 参照) では、Skills の定義自体が一種のメタデータと見なせる。YAML frontmatter で記述された Skill 定義から、必要なツール・対象モデル・前提知識を機械可読に取り出せる構造になっている。

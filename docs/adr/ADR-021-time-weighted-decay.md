# ADR-021: Time-Weighted Decay for Search Scores

- **Date**: 2026-05-14
- **Status**: Accepted
- **Deciders**: 中島
- **Spec**: spec_035

---

## Context

axis-knowledge-rag のナレッジ Markdown は YAML frontmatter に `updated` / `created` フィールドを持つ。
現状の検索スコアはベクトル類似度と BM25 の融合値のみで、**文書の鮮度を一切考慮しない**。

同じ関連性スコアを持つ文書が複数あるとき、ユーザーは直感的に「新しい方が正確・最新の情報を持つ」と期待する。
例えば、同じトピックの 3 年前の技術記事と 1 週間前の技術記事が同点になった場合、後者を上位に出す方が体験が良い。

ただし、**鮮度だけで関連性を完全に上書きしてはならない**。
古い良 doc を捨てることは情報の欠落につながる。
「軽い recency boost」として、関連性への影響を `weight` パラメータで調整可能にする必要がある。

---

## Decision

指数関数ベースの half-life decay を採用し、最終スコアに乗算する。

```
decay  = exp(-ln(2) * age_days / half_life_days)
final  = base * (1 - w * (1 - decay))
       = base * (1 - w) + (base * decay) * w
```

- `decay` は `(0, 1]` の範囲。age=0 で 1.0、age=half_life で 0.5、age=2×half_life で 0.25
- `weight` はブレンド比率。`w=0` で base そのまま、`w=1` で decay を全面適用
- **default: `enabled: false`** — opt-in 方式。既存挙動への影響はゼロ
- `updated` フィールドが存在しない / パース失敗時は `decay=1.0`（ペナルティなし）

### 設定値の根拠

| パラメータ | 値 | 根拠 |
|---|---|---|
| `half_life_days` | 180 | 半年で「古くなった感」が出始める経験則。社内ナレッジなら 365 も検討 |
| `weight` | 0.15 | 最大 15% のスコアを鮮度由来に。RAGAS (spec_033) で faithfulness が下がらないことを確認後に確定 |
| `date_field` | `"updated"` | `examples/knowledge/*.md` 全件が `updated:` を持つ (`updated_at:` は未使用) |

---

## Alternatives

### (a) Linear decay

```
decay = max(0, 1 - age_days / max_age_days)
```

- 却下: `max_age_days` を超えると decay=0 になり、古い良 doc のスコアが 0 に達してしまう

### (b) Step function (閾値で切り替え)

```
decay = 1.0 if age_days <= threshold else 0.5
```

- 却下: 閾値をまたぐ前後でスコアが不連続に跳ね、ランキングが突然変化する

### (c) Hard filter (古い doc を非表示)

```
where age_days <= 365
```

- 却下: 古い良 doc を完全に隠す。情報の欠落リスクが大きい

### (d) 指数減衰 (採用)

- 単調減少・連続・`[0, 1]` に収まる・`weight` でブレンド可能
- `updated` が無い doc を罰しない (decay=1.0 フォールバック)
- 関連性スコアを outright 上書きしない

---

## Consequences

### Positive

- 「同じ関連性の doc なら新しい方が上位に来る」という直感的な体験を実現
- `enabled: false` default なので既存テスト・RAGAS 評価に影響なし
- `weight` / `half_life_days` / `date_field` はすべて `config.yml` で調整可能
- `updated` が無い doc を安全側に倒す (Penalty なし) → frontmatter 不備の doc も正常動作

### Negative / Risks

- `weight=0.15` は経験則。RAGAS (spec_033) を `enabled: true` で nightly run し、
  faithfulness が著しく下がる場合は `0.05` まで段階的に引き下げる予定
- ユーザーが `enabled: true` にし忘れると機能しない (意図的な opt-in 設計)

---

## Future Work

- spec_036 候補: doc 種別 (`category`) ごとに異なる `half_life_days` を設定
  (議事録は短く、技術記事は長く)
- spec_037 候補: query 時の「now」をユーザー指定に — 「3 ヶ月前の自分のコンテキスト」シミュレーション
- spec_038 候補: クリックログから `weight` を自動チューン

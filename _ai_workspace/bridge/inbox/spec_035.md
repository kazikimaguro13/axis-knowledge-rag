# spec_035: Time-Weighted Decay (新しい文書を上位に出す係数追加)

- **Author**: Cowork (中島)
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-b` or `dev-d`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: v0.7 サブ (リリース直前)。Gemini 案 ⑭
- **Depends on**: spec_031 (search.py の融合関数を modify する箇所が被るので spec_031 マージ後に着手)
- **Recommended dispatch after**: spec_031 が main にマージ済みであること

## 1. 目的

ナレッジ MD ファイルには YAML frontmatter で `updated_at` (or `created_at`) を持つ。検索スコアに **時間減衰係数** を掛けて、**新しい文書を僅かに優遇** する。

「軽い recency boost」程度に留め、関連性スコアを **outright 上書きはしない**。重みは config で調整可。

```
[現状 v0.6 (+ spec_031 後)]
- final_score = fuse(vector_score, bm25_score, axis_score)
- 文書の作成日 / 更新日は無視

[変更後 v0.7 (spec_035)]
- decay = exp(-age_days / half_life_days)   (0.0..1.0)
- final_score = fuse(...) * (1 - w) + decay * w   (w ∈ [0.0, 1.0])
- default は w=0.0 (= 無効、回帰なし)。config.yml で opt-in
- half_life_days=180 (=半年で 1/e に減衰) を default
- doc に updated_at が無い場合は decay=1.0 (= 無効化、Penalty なし)
```

## 2. 制約

### 触ってよいファイル

- `backend/src/_decay.py` — **新規** (時間減衰係数の関数)
- `backend/src/search.py` — 融合スコア計算 (spec_031 で `parent` 単位に集約済み前提) に decay を掛ける
- `backend/src/config.py` — `retrieval.time_decay.{enabled, half_life_days, weight, date_field}`
- `config.yml` — 上記キーを default 値で追加 (enabled=false)
- `backend/tests/test_decay.py` — **新規**
- `backend/tests/test_search.py` — time_decay 有効時の順序テスト追加
- `docs/adr/ADR-021-time-weighted-decay.md` — **新規**
- `docs/configuration.md` (or README configuration セクション) — config 項目を追記
- `README.md` — Features に 1 行 (oct-in 機能なので控えめに)
- `CHANGELOG.md` — Day 35 追記

### 触ってはいけないもの

- `backend/src/{chunker,vector_store,loader,bm25*,rag,normalizer,integrity,marker,ingester}.py`
- frontend / streamlit / mcp_server — UI に影響しない
- `_ai_workspace/`

### コーディングルール

- 純粋関数 (副作用なし) で実装
- 新規依存追加なし (math.exp 使用)
- default 値で **既存挙動が変わらない** (enabled=false なので)
- updated_at が無い doc を罰しない (= 1.0 で乗算)
- 日時パース失敗時は warning ログ + decay=1.0 にフォールバック

### デプロイ

- 本 spec は v0.7.0 直前のリリーススライドイン

## 3. やってほしいこと

### 3-1. Decay 関数 (`backend/src/_decay.py`)

```python
"""Time-weighted decay factor for search score adjustment."""

from __future__ import annotations
import logging
import math
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger(__name__)


def decay_factor(
    updated_at: Any,
    *,
    now: datetime | None = None,
    half_life_days: float = 180.0,
) -> float:
    """Return decay coefficient in (0.0, 1.0].

    - decay = exp(-ln(2) * age_days / half_life_days)
    - half_life_days で 0.5, 2x で 0.25
    - updated_at = None / 不正 → 1.0 (= no penalty)
    """
    if not updated_at:
        return 1.0
    now = now or datetime.now(timezone.utc)
    try:
        dt = _parse_datetime(updated_at)
    except Exception:  # noqa: BLE001
        _log.warning("time_decay: failed to parse updated_at=%r, using 1.0", updated_at)
        return 1.0
    age_seconds = (now - dt).total_seconds()
    if age_seconds < 0:
        return 1.0  # future-dated doc → no penalty
    age_days = age_seconds / 86400.0
    return math.exp(-math.log(2) * age_days / half_life_days)


def blend_score(base_score: float, decay: float, weight: float) -> float:
    """final = base * (1 - w) + (base * decay) * w
              = base * (1 - w * (1 - decay))
    """
    w = max(0.0, min(1.0, weight))
    return base_score * (1.0 - w * (1.0 - decay))


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        # ISO 8601 with or without Z
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    raise TypeError(f"unsupported updated_at type: {type(value).__name__}")
```

### 3-2. search.py への統合

spec_031 が `search()` を parent_doc.enabled 分岐に変えた前提で、最終スコア計算ポイントに inject:

```python
from backend.src._decay import decay_factor, blend_score

def search(query: str, axes: dict | None = None, *, k: int = 5) -> list[SearchHit]:
    cfg = get_config()
    hits = _execute_search(query, axes, k=k * 2)  # over-fetch
    if cfg.retrieval.time_decay.enabled and cfg.retrieval.time_decay.weight > 0:
        hits = _apply_time_decay(hits, cfg)
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]


def _apply_time_decay(hits: list[SearchHit], cfg) -> list[SearchHit]:
    field = cfg.retrieval.time_decay.date_field  # "updated_at" | "created_at"
    half_life = cfg.retrieval.time_decay.half_life_days
    weight = cfg.retrieval.time_decay.weight
    out = []
    for h in hits:
        updated = (h.metadata or {}).get(field)
        d = decay_factor(updated, half_life_days=half_life)
        new_score = blend_score(h.score, d, weight)
        out.append(h.with_score(new_score))  # immutable copy
    return out
```

(`SearchHit.with_score(...)` がまだ無ければ dataclass の `replace` で対応)

### 3-3. config.yml

```yaml
retrieval:
  parent_doc:
    # (spec_031 で追加済み)
  bm25:
    # (v0.6 で既出)
  time_decay:
    enabled: false              # default off (opt-in)
    half_life_days: 180         # 半年で 1/e
    weight: 0.15                # 最大 15% を decay 由来に
    date_field: "updated_at"    # "created_at" でも可
```

`backend/src/config.py` の `RetrievalConfig` 直下に `TimeDecayConfig` を追加。

### 3-4. テスト (`backend/tests/test_decay.py`)

```python
from datetime import datetime, timedelta, timezone
from backend.src._decay import decay_factor, blend_score


def test_no_updated_at_returns_one():
    assert decay_factor(None) == 1.0
    assert decay_factor("") == 1.0


def test_today_returns_one():
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    assert decay_factor(now, now=now) == 1.0


def test_half_life():
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    past = now - timedelta(days=180)
    d = decay_factor(past, now=now, half_life_days=180)
    assert abs(d - 0.5) < 1e-6


def test_double_half_life():
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    past = now - timedelta(days=360)
    d = decay_factor(past, now=now, half_life_days=180)
    assert abs(d - 0.25) < 1e-6


def test_future_dated_no_penalty():
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    future = now + timedelta(days=30)
    assert decay_factor(future, now=now) == 1.0


def test_iso_string_with_z():
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    d = decay_factor("2025-11-15T00:00:00Z", now=now, half_life_days=180)
    assert 0.4 < d < 0.6


def test_invalid_string_logs_and_returns_one(caplog):
    assert decay_factor("not-a-date") == 1.0
    assert any("failed to parse" in r.message for r in caplog.records)


def test_blend_weight_zero_is_passthrough():
    assert blend_score(1.0, 0.5, weight=0.0) == 1.0


def test_blend_weight_one_full_decay():
    assert blend_score(1.0, 0.5, weight=1.0) == 0.5


def test_blend_weight_half():
    # base=1.0, decay=0.5, w=0.5 → 1.0 * (1 - 0.5*0.5) = 0.75
    assert abs(blend_score(1.0, 0.5, weight=0.5) - 0.75) < 1e-6


def test_blend_clamps_weight():
    assert blend_score(1.0, 0.5, weight=2.0) == blend_score(1.0, 0.5, weight=1.0)
    assert blend_score(1.0, 0.5, weight=-1.0) == 1.0
```

`backend/tests/test_search.py` 追加 (fixture で sample docs に updated_at を持たせ、enabled=true で順序が変わることを確認):

```python
def test_time_decay_promotes_recent(monkeypatch, sample_docs_with_dates):
    """新しい doc が同じ関連スコアでも上位に来ることを確認。"""
    monkeypatch.setattr(cfg, "retrieval.time_decay.enabled", True)
    monkeypatch.setattr(cfg, "retrieval.time_decay.weight", 0.3)
    hits = search("rag", k=3)
    # 関連性同じ doc では新しい方が前に来るはず
    assert hits[0].metadata["updated_at"] > hits[-1].metadata["updated_at"]


def test_time_decay_disabled_keeps_old_order(monkeypatch, sample_docs_with_dates):
    monkeypatch.setattr(cfg, "retrieval.time_decay.enabled", False)
    hits = search("rag", k=3)
    # 元のスコア順 (関連度純粋) のまま
    assert hits == _expected_relevance_only_order()
```

### 3-5. ADR-021

`docs/adr/ADR-021-time-weighted-decay.md`:

- Context: 古い記事と新しい記事が同じ関連度を取ると、ユーザーは新しい方を期待しがち。検索体験を「フレッシュ」にしたい
- Decision: exp ベース half-life decay + weight ブレンド、opt-in
- Alternatives:
  - (a) Linear decay → 却下: いつまでも 0 にならず古い doc を残す
  - (b) Step function (1y 以内 vs 以上) → 却下: 不連続でランキングが跳ねる
  - (c) Hard filter (1y 以内のみ表示) → 却下: 古い良 doc を捨てる
  - (d) exp decay (採用) → 良 doc も古ければゆるやかに後退
- Consequences:
  - default off。weight=0.15 は経験則。RAGAS で AB 比較 (spec_033 後) 結果を見て調整
  - updated_at が無い doc を **罰しない** ので、frontmatter 不備の doc が安全側に倒れる
  - half_life=180 は「半年でフォーカス対象から外れる」感覚値、長すぎず短すぎず

### 3-6. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
git checkout -b feat/spec_035-time-decay

# Unit test
ruff check backend/src/_decay.py
python3 -m pytest -q backend/tests/test_decay.py -v

# 既存 search テスト (回帰なし)
python3 -m pytest -q backend/tests/test_search.py

# 全テスト
python3 -m pytest -q --cov=backend/src --cov-report=term-missing | tail -20

# Manual: config を編集して enabled=true、API で順序確認
sed -i 's/enabled: false/enabled: true/' config.yml
uvicorn backend.src.api:app --port 8000 &
sleep 3
curl -s -X POST http://localhost:8000/api/search -H 'Content-Type: application/json' \
  -d '{"query":"RAG","top_k":5}' | jq '.hits | map({title, updated_at: .metadata.updated_at})'
kill %1
git checkout config.yml  # 戻す (default off)
```

### 3-7. コミット粒度

1. `feat(decay): exp half-life decay function + blend_score helper`
2. `test(decay): cover half-life, future-dated, invalid input, weight clamping`
3. `feat(config): retrieval.time_decay.{enabled,half_life_days,weight,date_field}`
4. `feat(search): apply time decay to final scores when enabled`
5. `test(search): time_decay reorders results when enabled, no-op when disabled`
6. `docs: ADR-021 + configuration.md + README features line`
7. `chore: CHANGELOG Day 35`

`git push -u origin feat/spec_035-time-decay`

### 3-8. result_035.md に書くこと

- 同じクエリで enabled=false vs true の順序比較サンプル
- half_life_days を 30 / 180 / 365 に変えた時の上位 5 件比較 (1 クエリ分)
- 新規テスト数、coverage 変動
- ruff / pytest 全緑

## 4. 成功条件

- [ ] `_decay.py` の純粋関数化、副作用なし
- [ ] enabled=false default で既存挙動と完全同一 (regression なし)
- [ ] enabled=true で新しい doc が同関連スコア時に優先される
- [ ] updated_at 不在 / パース失敗で safety (decay=1.0)
- [ ] 新規 tests >=10 件 (decay 9 + search reorder 2)
- [ ] ADR-021 / docs / CHANGELOG 更新
- [ ] git push 完了

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_035.md`

## 6. 質問があるとき

- **date_field の default**: `updated_at` vs `created_at` のどちらが妥当か。リポジトリの examples/knowledge/*.md frontmatter を `grep "updated_at\|created_at"` して多い方を default に
- **weight=0.15 の妥当性**: 経験則。spec_033 (RAGAS) を main マージ後、`enabled=true` 版で nightly run → faithfulness が極端に下がらなければ default を 0.15 で確定、下がるなら 0.05 まで段階的に下げる。本 spec 範囲外 (Open questions 記録のみ)
- **half_life=180** vs **365**: 個人ナレッジなら 180 で良いと判断。社内ナレッジ等の場合 365 推奨

迷ったら Open questions に書いて `status: blocked` で終了。

## 7. 補足

### 設計の意図

- 1 関数で済む小さな改善だが、ポートフォリオで「ユーザー体験を継続改善している」を示す材料になる
- `enabled=false` を default にして「機能を入れたが慎重に運用」というスタンスを示す

### 将来の拡張余地

- spec_036 候補 (v0.8): doc 種別ごとに別 half_life (議事録は短く、技術記事は長く)
- spec_037 候補 (v0.8): query 時の現在時刻を user-supplied にして「3 ヶ月前の自分」シミュレーション
- spec_038 候補 (v0.8): クリックログから decay weight を自動チューン (案 ①「Auto-Tuning Hybrid Search」と組合せ)

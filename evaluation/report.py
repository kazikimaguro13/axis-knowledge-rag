"""Generate markdown PR comments for RAGAS / A/B runs."""

from __future__ import annotations

import json
from pathlib import Path


def generate_ragas_report(run_path: Path, baseline_path: Path | None = None) -> str:
    run = json.loads(run_path.read_text())
    base = json.loads(baseline_path.read_text()) if baseline_path and baseline_path.exists() else None
    lines = ["## RAGAS Scores", ""]
    if base:
        lines.append("| metric | this run | baseline | Δ | regression? |")
        lines.append("|---|---|---|---|---|")
        for k, v in run["scores"].items():
            b = base["scores"].get(k, 0)
            delta = v - b
            regression = "⚠️" if delta < -0.05 * b else ""
            lines.append(f"| {k} | {v:.4f} | {b:.4f} | {delta:+.4f} | {regression} |")
    else:
        lines.append("| metric | score |")
        lines.append("|---|---|")
        for k, v in run["scores"].items():
            lines.append(f"| {k} | {v:.4f} |")
    return "\n".join(lines)


def generate_abtest_report(abtest_path: Path) -> str:
    rec = json.loads(abtest_path.read_text())
    lines = [
        f"## A/B Test: `{rec['flag']}`",
        f"- **A**: {rec['config_a']}",
        f"- **B**: {rec['config_b']}",
        "",
        "| metric | mean A | mean B | Δ | p | significant | direction |",
        "|---|---|---|---|---|---|---|",
    ]
    for m, t in rec["ttests"].items():
        sig = "✅" if t["significant"] else "—"
        lines.append(
            f"| {m} | {t['mean_a']:.4f} | {t['mean_b']:.4f} | "
            f"{t['diff']:+.4f} | {t['p']:.4f} | {sig} | {t['direction']} |"
        )
    lines.append("")
    lines.append(f"**判定**: p < 0.05 で有意。すべて非有意 → flag {rec['flag']} の影響なし。")
    return "\n".join(lines)

import json

from evaluation.report import generate_abtest_report, generate_ragas_report


def test_ragas_report_with_baseline(tmp_path):
    run = tmp_path / "run.json"
    base = tmp_path / "base.json"
    run.write_text(json.dumps({"scores": {"faithfulness": 0.85}}))
    base.write_text(json.dumps({"scores": {"faithfulness": 0.80}}))
    md = generate_ragas_report(run, base)
    assert "this run" in md
    assert "0.8500" in md and "0.8000" in md
    assert "+0.0500" in md


def test_ragas_report_without_baseline(tmp_path):
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"scores": {"faithfulness": 0.85}}))
    md = generate_ragas_report(run, None)
    assert "baseline" not in md.lower()


def test_abtest_report(tmp_path):
    abtest = tmp_path / "abtest.json"
    abtest.write_text(
        json.dumps(
            {
                "flag": "time_decay.enabled",
                "config_a": "time_decay.enabled=false",
                "config_b": "time_decay.enabled=true",
                "ttests": {
                    "faithfulness": {
                        "mean_a": 0.85,
                        "mean_b": 0.84,
                        "diff": -0.01,
                        "p": 0.6,
                        "significant": False,
                        "direction": "tie",
                    },
                },
            }
        )
    )
    md = generate_abtest_report(abtest)
    assert "A/B Test" in md
    assert "time_decay.enabled" in md

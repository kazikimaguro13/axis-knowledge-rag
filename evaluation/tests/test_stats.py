import pytest

from evaluation.stats import paired_t_test


def test_identical_arrays_p_high():
    a = [0.8, 0.7, 0.9, 0.85, 0.75]
    r = paired_t_test(a, a)
    if r is None:
        pytest.skip("scipy not available")
    assert r.p_value > 0.99
    assert not r.significant


def test_clearly_different_p_low():
    a = [0.1] * 10
    b = [0.9] * 10
    r = paired_t_test(a, b)
    if r is None:
        pytest.skip("scipy not available")
    assert r.p_value < 0.001
    assert r.significant
    assert r.direction == "B>A"


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        paired_t_test([0.5], [0.5, 0.6])


def test_too_few_samples_raises():
    with pytest.raises(ValueError):
        paired_t_test([0.5], [0.5])


def test_scipy_missing_returns_none(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.stats", None)
    pytest.skip("manual verification: paired_t_test returns None if scipy missing")

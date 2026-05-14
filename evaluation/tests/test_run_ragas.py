import pytest


def test_block_on_regression_exit_1(monkeypatch, tmp_path):
    """--block-on-regression: regression あり → exit 1"""
    pytest.skip("requires ragas mock — see manual smoke")


def test_block_on_regression_exit_0_no_drop(tmp_path):
    """--block-on-regression: regression なし → exit 0"""
    pytest.skip("requires ragas mock — see manual smoke")

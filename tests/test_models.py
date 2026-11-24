"""Pure-Python models on data with a known answer."""

from __future__ import annotations

import pytest

from dbx_ds import models


def test_solve_and_ols_recover_a_line() -> None:
    assert models.solve([[2.0, 0.0], [0.0, 4.0]], [2.0, 8.0]) == pytest.approx([1.0, 2.0])
    rows = [[1.0], [2.0], [3.0], [4.0]]
    y = [3.0, 5.0, 7.0, 9.0]
    coefs = models.ols(rows, y)
    assert coefs == pytest.approx([1.0, 2.0])
    assert models.predict_linear(coefs, [5.0]) == pytest.approx(11.0)
    assert models.residuals(coefs, rows, y) == pytest.approx([0.0] * 4)
    assert models.r_squared(coefs, rows, y) == pytest.approx(1.0)


def test_scaler_standardises_columns() -> None:
    rows = [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]]
    scaler = models.fit_scaler(rows)
    scaled = scaler.apply(rows)
    assert scaled[1] == [0.0, 0.0] and scaled[0] == [-1.0, -1.0]


def test_softmax_sums_to_one() -> None:
    probs = models.softmax([1.0, 2.0, 3.0])
    assert sum(probs) == pytest.approx(1.0) and probs[2] > probs[1] > probs[0]


def test_logistic_learns_a_separable_rule() -> None:
    rows = [[-2.0], [-1.0], [0.0], [1.0], [2.0]]
    labels = [0, 0, 1, 2, 2]
    model = models.fit_logistic(rows, labels, steps=300, rate=1.0)
    assert [model.predict(r) for r in rows] == labels
    assert sum(model.proba([0.5])) == pytest.approx(1.0)


def test_scores() -> None:
    assert models.accuracy([0, 1, 1], [0, 1, 0]) == pytest.approx(2 / 3)
    assert models.log_loss([[0.5, 0.5], [1.0, 0.0]], [0, 1]) > 0
    assert models.log_loss([[0.5, 0.5]], [0]) == pytest.approx(0.6931, abs=1e-4)
    assert models.class_shares([0, 0, 1, 2]) == [0.5, 0.25, 0.25]


def test_calibration_bins() -> None:
    rows = models.calibration([0.05, 0.07, 0.95], [0, 1, 1], bins=10)
    assert [r[3] for r in rows] == [2, 1]
    assert rows[0][2] == 0.5

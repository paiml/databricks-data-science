"""Small, deterministic models for course 3: least squares, multinomial logistic regression, metrics.

Pure Python on lists, so a result never depends on a BLAS build. Logistic regression is batch
gradient descent from zero weights with a fixed step and iteration count: same data, same answer.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from dbx_ds import stats

Matrix = list[list[float]]


def solve(a: Matrix, b: list[float]) -> list[float]:
    """Solve a x = b by Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def ols(rows: Sequence[Sequence[float]], y: Sequence[float]) -> list[float]:
    """Least-squares coefficients [intercept, b1, b2, ...] from the normal equations."""
    k = len(rows[0]) + 1
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for row, target in zip(rows, y, strict=True):
        x = [1.0, *row]
        for i in range(k):
            xty[i] += x[i] * target
            for j in range(i, k):
                xtx[i][j] += x[i] * x[j]
    for i in range(k):
        for j in range(i):
            xtx[i][j] = xtx[j][i]
    return solve(xtx, xty)


def predict_linear(coefs: Sequence[float], row: Sequence[float]) -> float:
    return coefs[0] + sum(c * v for c, v in zip(coefs[1:], row, strict=True))


def residuals(coefs: Sequence[float], rows: Sequence[Sequence[float]], y: Sequence[float]) -> list[float]:
    """actual - predicted, per row."""
    return [t - predict_linear(coefs, r) for r, t in zip(rows, y, strict=True)]


def r_squared(coefs: Sequence[float], rows: Sequence[Sequence[float]], y: Sequence[float]) -> float:
    resid = residuals(coefs, rows, y)
    centre = stats.mean(y)
    return 1.0 - math.fsum(r * r for r in resid) / math.fsum((t - centre) ** 2 for t in y)


@dataclass(frozen=True)
class Scaler:
    """Column means and standard deviations learned on the training rows."""

    centres: list[float]
    spreads: list[float]

    def apply(self, rows: Sequence[Sequence[float]]) -> list[list[float]]:
        return [[(v - c) / s for v, c, s in zip(row, self.centres, self.spreads, strict=True)] for row in rows]


def fit_scaler(rows: Sequence[Sequence[float]]) -> Scaler:
    cols = list(zip(*rows, strict=True))
    return Scaler([stats.mean(c) for c in cols], [stats.stdev(c) for c in cols])


def softmax(scores: Sequence[float]) -> list[float]:
    top = max(scores)
    exps = [math.exp(s - top) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]


@dataclass(frozen=True)
class Logistic:
    """Multinomial logistic regression: weights[class] = [bias, w1, w2, ...]."""

    weights: list[list[float]]

    def proba(self, row: Sequence[float]) -> list[float]:
        return softmax(_scores(self.weights, row))

    def predict(self, row: Sequence[float]) -> int:
        probs = self.proba(row)
        return probs.index(max(probs))


def _scores(weights: list[list[float]], row: Sequence[float]) -> list[float]:
    return [w[0] + sum(a * b for a, b in zip(w[1:], row, strict=True)) for w in weights]


def _gradient(weights: list[list[float]], rows: Sequence[Sequence[float]], labels: Sequence[int]) -> list[list[float]]:
    """Summed log-loss gradient for every class: error times the row (bias first)."""
    grad = [[0.0] * len(weights[0]) for _ in weights]
    for row, label in zip(rows, labels, strict=True):
        probs = softmax(_scores(weights, row))
        for c, g in enumerate(grad):
            err = probs[c] - (1.0 if c == label else 0.0)
            g[0] += err
            for j, v in enumerate(row, start=1):
                g[j] += err * v
    return grad


def fit_logistic(
    rows: Sequence[Sequence[float]], labels: Sequence[int], classes: int = 3, steps: int = 150, rate: float = 0.5
) -> Logistic:
    """Batch gradient descent on log loss from zero weights. Inputs should be standardised."""
    weights = [[0.0] * (len(rows[0]) + 1) for _ in range(classes)]
    n = len(rows)
    for _ in range(steps):
        grad = _gradient(weights, rows, labels)
        weights = [
            [w - rate * g / n for w, g in zip(ws, gs, strict=True)] for ws, gs in zip(weights, grad, strict=True)
        ]
    return Logistic(weights)


def accuracy(predicted: Sequence[int], actual: Sequence[int]) -> float:
    return sum(1 for p, a in zip(predicted, actual, strict=True) if p == a) / len(actual)


def log_loss(probs: Sequence[Sequence[float]], actual: Sequence[int], eps: float = 1e-15) -> float:
    """Mean negative log of the probability given to what happened (any number of classes)."""
    total = math.fsum(-math.log(max(p[a], eps)) for p, a in zip(probs, actual, strict=True))
    return total / len(actual)


def class_shares(labels: Sequence[int], classes: int = 3) -> list[float]:
    """The baseline model: always give each class its training share."""
    return [sum(1 for v in labels if v == c) / len(labels) for c in range(classes)]


def calibration(probs: Sequence[float], hits: Sequence[int], bins: int = 10) -> list[tuple[float, float, float, int]]:
    """Per probability bin: (bin start, mean predicted, observed rate, count); empty bins are left out."""
    grouped: dict[int, list[tuple[float, int]]] = {}
    for p, h in zip(probs, hits, strict=True):
        grouped.setdefault(min(int(p * bins), bins - 1), []).append((p, h))
    return [
        (b / bins, stats.mean([p for p, _ in g]), stats.mean([h for _, h in g]), len(g))
        for b, g in sorted(grouped.items())
    ]

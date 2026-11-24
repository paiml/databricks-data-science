"""Plain descriptive statistics, probability and Poisson helpers for courses 2 and 3.

Everything is pure Python on lists of numbers, deterministic, and mirrored by a DuckDB query
in sql/demo_stats.sql where course 5 needs the same example. Spread uses the sample
standard deviation (n - 1) unless a function says otherwise.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Sequence

Number = float | int


def mean(values: Sequence[Number]) -> float:
    return math.fsum(values) / len(values)


def median(values: Sequence[Number]) -> float:
    return percentile(values, 50.0)


def variance(values: Sequence[Number]) -> float:
    """Sample variance (n - 1)."""
    centre = mean(values)
    return math.fsum((v - centre) ** 2 for v in values) / (len(values) - 1)


def stdev(values: Sequence[Number]) -> float:
    return math.sqrt(variance(values))


def population_stdev(values: Sequence[Number]) -> float:
    centre = mean(values)
    return math.sqrt(math.fsum((v - centre) ** 2 for v in values) / len(values))


def percentile(values: Sequence[Number], q: float) -> float:
    """The q-th percentile (0..100), linear interpolation between closest ranks."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100.0
    low = math.floor(position)
    high = math.ceil(position)
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def percentiles(values: Sequence[Number], qs: Sequence[float] = (25, 50, 75, 95, 99)) -> dict[float, float]:
    return {q: percentile(values, q) for q in qs}


def iqr(values: Sequence[Number]) -> float:
    """Interquartile range: the width of the middle half."""
    return percentile(values, 75.0) - percentile(values, 25.0)


def pearson(xs: Sequence[Number], ys: Sequence[Number]) -> float:
    """Pearson correlation of two equal-length columns."""
    mx, my = mean(xs), mean(ys)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy)


def z_score(value: Number, centre: Number, spread: Number) -> float:
    return float((value - centre) / spread)


def z_scores(values: Sequence[Number]) -> list[float]:
    """Each value as (value - mean) / sample sd. With no spread (one value, or all equal) every z is 0."""
    if len(values) < 2 or len(set(values)) == 1:
        return [0.0] * len(values)
    centre, spread = mean(values), stdev(values)
    return [z_score(v, centre, spread) for v in values]


def value_counts(values: Sequence[int]) -> dict[int, int]:
    """Counts per whole-number value, keys ascending."""
    return dict(sorted(Counter(values).items()))


def shares(counts: dict[int, int]) -> dict[int, float]:
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()}


def text_bars(items: Sequence[tuple[str, Number]], width: int = 40) -> list[str]:
    """One line per (label, value); the longest bar is `width` characters. Chart stand-in for a terminal."""
    top = max(value for _, value in items)
    label_width = max(len(label) for label, _ in items)
    lines = []
    for label, value in items:
        bar = "#" * (round(width * value / top) if top > 0 else 0)
        lines.append(f"{label:<{label_width}}  {bar} {value:g}")
    return lines


def standard_error_rate(rate: float, n: int) -> float:
    """Typical error of a rate measured on n matches: sqrt(p (1 - p) / n)."""
    return math.sqrt(rate * (1.0 - rate) / n)


def two_sigma_range(rate: float, n: int) -> tuple[float, float]:
    """Rate plus or minus two standard errors."""
    margin = 2.0 * standard_error_rate(rate, n)
    return rate - margin, rate + margin


def resample_rates(outcomes: Sequence[int], n: int, trials: int, seed: int) -> list[float]:
    """Mean of `n` draws (with replacement) from a 0/1 column, `trials` times, from a fixed seed."""
    rng = random.Random(seed)
    return [sum(rng.choices(outcomes, k=n)) / n for _ in range(trials)]


def fair_odds(probability: float) -> float:
    """Decimal odds with no margin: 1 / probability."""
    return 1.0 / probability


def poisson_pmf(k: int, lam: float) -> float:
    """Probability of exactly k events at average rate lam."""
    return math.exp(-lam) * lam**k / math.factorial(k)


def poisson_table(lam: float, k_max: int = 7) -> list[tuple[int, float]]:
    return [(k, poisson_pmf(k, lam)) for k in range(k_max + 1)]


def poisson_draw(rng: random.Random, lam: float) -> int:
    """One Poisson draw by inverse CDF from a single uniform number, so a seed fixes the stream."""
    u = rng.random()
    k = 0
    cumulative = poisson_pmf(0, lam)
    while u > cumulative:
        k += 1
        cumulative += poisson_pmf(k, lam)
    return k


def simulate_season(
    lam_home: float, lam_away: float, matches: int = 380, seed: int = 2016
) -> tuple[list[tuple[int, int]], tuple[int, int, int]]:
    """Seeded season: (home, away) goals per match and (home wins, draws, away wins)."""
    rng = random.Random(seed)
    results = [(poisson_draw(rng, lam_home), poisson_draw(rng, lam_away)) for _ in range(matches)]
    home_wins = sum(1 for h, a in results if h > a)
    draws = sum(1 for h, a in results if h == a)
    return results, (home_wins, draws, matches - home_wins - draws)

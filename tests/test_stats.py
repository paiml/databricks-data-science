"""Pure statistics helpers: tiny inputs with answers worked by hand."""

from __future__ import annotations

import math
import random

import pytest

from dbx_ds import stats


def test_centre_and_spread() -> None:
    assert stats.mean([1, 2, 3, 6]) == 3
    assert stats.median([1, 2, 3, 6]) == 2.5
    assert stats.variance([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(32 / 7)
    assert stats.stdev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(math.sqrt(32 / 7))
    assert stats.population_stdev([2, 4, 4, 4, 5, 5, 7, 9]) == 2.0


def test_percentiles_interpolate() -> None:
    values = [1, 2, 3, 4, 5]
    assert stats.percentile(values, 25) == 2
    assert stats.percentile(values, 90) == pytest.approx(4.6)
    assert stats.percentiles(values, (50,)) == {50: 3}
    assert stats.iqr(values) == 2


def test_pearson_and_z() -> None:
    assert stats.pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert stats.pearson([1, 2, 3], [6, 4, 2]) == pytest.approx(-1.0)
    assert stats.z_score(84, 69, 7.5) == 2.0
    assert stats.z_scores([1, 2, 3]) == [-1.0, 0.0, 1.0]


def test_z_scores_with_no_spread_are_zero() -> None:
    assert stats.z_scores([5.0]) == [0.0]
    assert stats.z_scores([2.0, 2.0, 2.0]) == [0.0, 0.0, 0.0]
    assert stats.z_scores([]) == []


def test_counts_shares_and_bars() -> None:
    counts = stats.value_counts([2, 0, 0, 1, 0])
    assert counts == {0: 3, 1: 1, 2: 1}
    assert list(counts) == [0, 1, 2]
    assert stats.shares(counts) == {0: 0.6, 1: 0.2, 2: 0.2}
    bars = stats.text_bars([("a", 4), ("b", 2)], width=8)
    assert bars[0].count("#") == 8 and bars[1].count("#") == 4


def test_standard_error_and_range() -> None:
    assert stats.standard_error_rate(0.5, 100) == 0.05
    low, high = stats.two_sigma_range(0.5, 100)
    assert (round(low, 6), round(high, 6)) == (0.4, 0.6)


def test_resample_is_seeded() -> None:
    a = stats.resample_rates([0, 1, 1, 0], 4, 5, seed=3)
    assert a == stats.resample_rates([0, 1, 1, 0], 4, 5, seed=3)
    assert a != stats.resample_rates([0, 1, 1, 0], 4, 5, seed=4)


def test_odds_and_poisson() -> None:
    assert stats.fair_odds(0.25) == 4.0
    assert stats.poisson_pmf(0, 1.5) == pytest.approx(math.exp(-1.5))
    table = stats.poisson_table(1.5, 3)
    assert [k for k, _ in table] == [0, 1, 2, 3]
    assert sum(p for _, p in stats.poisson_table(1.5, 30)) == pytest.approx(1.0)


def test_poisson_draw_and_season_are_seeded() -> None:
    assert stats.poisson_draw(random.Random(1), 1.5) == stats.poisson_draw(random.Random(1), 1.5)
    results, (h, d, a) = stats.simulate_season(1.5, 1.1, matches=50, seed=9)
    assert len(results) == 50 and h + d + a == 50
    assert (results, (h, d, a)) == stats.simulate_season(1.5, 1.1, matches=50, seed=9)

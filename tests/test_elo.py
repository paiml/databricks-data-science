from __future__ import annotations

import random

import pytest

from dbx_ds import elo


def result(
    mid: int,
    home: int,
    away: int,
    hg: int,
    ag: int,
    season: str = "2014/2015",
    date: str = "2014-09-01",
) -> elo.Result:
    return elo.Result(mid, season, date, home, away, hg, ag)


def test_expected_home_equal_teams_favours_home() -> None:
    assert elo.expected_home(1500.0, 1500.0) == pytest.approx(1 / (1 + 10 ** (-100 / 400)))
    assert elo.expected_home(1500.0, 1500.0) > 0.5


def test_expected_home_even_when_away_is_home_advantage_better() -> None:
    assert elo.expected_home(1500.0, 1600.0) == pytest.approx(0.5)


def test_actual_home_win_draw_loss() -> None:
    assert elo.actual_home(2, 1) == 1.0
    assert elo.actual_home(1, 1) == 0.5
    assert elo.actual_home(0, 3) == 0.0


def test_single_home_win_by_hand() -> None:
    out = elo.season_ratings([result(1, 1, 2, 1, 0)])
    e = 1 / (1 + 10 ** (-100 / 400))
    assert out[("2014/2015", 1)] == pytest.approx(1500 + 20 * (1 - e))
    assert out[("2014/2015", 2)] == pytest.approx(1500 - 20 * (1 - e))


def test_draw_moves_rating_towards_the_away_side() -> None:
    out = elo.season_ratings([result(1, 1, 2, 0, 0)])
    assert out[("2014/2015", 1)] < 1500.0 < out[("2014/2015", 2)]


def test_rating_points_are_conserved() -> None:
    matches = [
        result(i, 1 + i % 4, 1 + (i + 1) % 4, i % 3, (i * 7) % 3, date=f"2014-09-{i + 1:02d}") for i in range(20)
    ]
    out = elo.season_ratings(matches)
    latest = {team: r for (_, team), r in out.items()}
    assert sum(latest.values()) == pytest.approx(1500.0 * len(latest))


def test_input_order_never_matters() -> None:
    matches = [
        result(i, 1 + i % 5, 1 + (i + 2) % 5, i % 4, (i * 3) % 4, date=f"2014-09-{i // 2 + 1:02d}") for i in range(30)
    ]
    shuffled = matches[:]
    random.Random(1).shuffle(shuffled)
    assert elo.season_ratings(matches) == elo.season_ratings(shuffled)


def test_same_day_matches_break_ties_on_match_api_id() -> None:
    first = result(1, 1, 2, 1, 0)
    second = result(2, 2, 3, 3, 0)
    assert elo.season_ratings([second, first]) == elo.season_ratings([first, second])


def test_ratings_carry_across_seasons() -> None:
    out = elo.season_ratings([result(1, 1, 2, 1, 0), result(2, 1, 2, 1, 0, season="2015/2016", date="2015-09-01")])
    assert out[("2015/2016", 1)] > out[("2014/2015", 1)] > 1500.0


def test_current_table_uses_latest_season_and_breaks_ties_on_id() -> None:
    table = elo.current_table(
        {
            ("2014/2015", 1): 1600.0,
            ("2015/2016", 1): 1400.0,
            ("2014/2015", 2): 1500.0,
            ("2015/2016", 3): 1500.0,
        }
    )
    assert table == [(2, 1500.0), (3, 1500.0), (1, 1400.0)]


def test_current_table_ignores_an_older_season_seen_later() -> None:
    table = elo.current_table({("2015/2016", 1): 1500.0, ("2014/2015", 1): 1000.0})
    assert table == [(1, 1500.0)]

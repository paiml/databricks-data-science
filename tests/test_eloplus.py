"""Elo extras: parameterised replay, tuning, home advantage, league filters, standings check."""

from __future__ import annotations

import pytest

from dbx_ds import data, elo, eloplus, queries
from tests.conftest import FIXTURE
from tests.synth_league import league_connection


def result(i: int, home: int, away: int, hg: int, ag: int, season: str = "2014/2015") -> elo.Result:
    return elo.Result(i, season, f"2014-09-{i:02d} 00:00:00", home, away, hg, ag)


@pytest.fixture(scope="module")
def fixture_games() -> list[eloplus.Game]:
    return eloplus.load_games(data.connect(FIXTURE))


@pytest.fixture(scope="module")
def synth_games() -> list[eloplus.Game]:
    return eloplus.load_games(league_connection())


def test_load_games_skips_unscored_matches() -> None:
    con = league_connection()
    scored = con.execute("SELECT count(*) FROM Match WHERE home_team_goal IS NOT NULL").fetchone()
    unscored = con.execute("SELECT count(*) FROM Match WHERE home_team_goal IS NULL").fetchone()
    assert unscored and unscored[0] > 0
    games = eloplus.load_games(con)
    assert scored and len(games) == scored[0]
    assert len(games[0].home_xi) == len(games[0].away_xi) == 11


@pytest.mark.parametrize("name", ["fixture_games", "synth_games"])
def test_default_replay_equals_the_elo_module(name: str, request: pytest.FixtureRequest) -> None:
    games: list[eloplus.Game] = request.getfixturevalue(name)
    results = [g.result for g in games]
    assert eloplus.replay(results).ratings == elo.season_ratings(results)


def test_prematch_forecast_of_the_first_match() -> None:
    replayed = eloplus.replay([result(1, 10, 20, 2, 0)])
    (first,) = replayed.prematch
    assert (first.home_rating, first.away_rating, first.actual_home) == (1500.0, 1500.0, 1.0)
    assert first.expected_home == pytest.approx(0.6400649998)
    assert replayed.ratings[("2014/2015", 10)] == pytest.approx(1500 + 20 * (1 - 0.6400649998))


def test_replay_is_independent_of_input_order() -> None:
    results = [result(1, 10, 20, 2, 0), result(2, 20, 10, 1, 1), result(3, 10, 30, 0, 1)]
    assert eloplus.replay(results).ratings == eloplus.replay(results[::-1]).ratings


def test_tune_runs_the_grid_in_order_and_picks_the_lowest_error(fixture_games: list[eloplus.Game]) -> None:
    results = [g.result for g in fixture_games]
    grid = eloplus.tune(results, [10.0, 20.0], [0.0, 100.0])
    assert [(t.k_factor, t.home_advantage) for t in grid] == [(10.0, 0.0), (10.0, 100.0), (20.0, 0.0), (20.0, 100.0)]
    default = next(t for t in grid if (t.k_factor, t.home_advantage) == (20.0, 100.0))
    assert default.mse == pytest.approx(eloplus.mean_squared_error(eloplus.replay(results).prematch))
    assert eloplus.best(grid).mse == min(t.mse for t in grid)


def test_home_stats_by_hand() -> None:
    stats = eloplus.home_stats(
        [result(1, 1, 2, 3, 0), result(2, 1, 2, 1, 1), result(3, 1, 2, 0, 2), result(4, 1, 2, 2, 0)]
    )
    assert (stats.home_pct, stats.draw_pct, stats.away_pct) == (50.0, 25.0, 25.0)
    assert (stats.home_goals, stats.away_goals) == (1.5, 0.75)


def test_elo_table_filters_by_league_and_season(synth_games: list[eloplus.Game]) -> None:
    ratings = eloplus.replay(g.result for g in synth_games).ratings
    everything = eloplus.elo_table(synth_games, ratings)
    assert len(everything) == len(ratings)
    league_rows = eloplus.elo_table(synth_games, ratings, league_id=20)
    assert {row[1] for row in league_rows} == {20} and len(league_rows) == 6 * 4
    one = eloplus.elo_table(synth_games, ratings, league_id=20, season="2009/2010")
    assert len(one) == 6 and [r[3] for r in one] == sorted((r[3] for r in one), reverse=True)
    assert len(eloplus.elo_table(synth_games, ratings, season="2009/2010")) == 6 * 3 + 2


def test_points_table_orders_by_points_then_goal_difference() -> None:
    games = [result(1, 1, 2, 2, 0), result(2, 3, 4, 1, 0), result(3, 2, 3, 1, 1)]
    table = eloplus.points_table(games)
    assert table == [(3, 4, 1, 2), (1, 3, 2, 2), (2, 1, -2, 1), (4, 0, -1, 0)]


def test_spearman_is_one_for_equal_and_minus_one_for_reversed_rankings() -> None:
    assert eloplus.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert eloplus.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0


def test_standings_check_on_the_fixture_premier_league(fixture_games: list[eloplus.Game]) -> None:
    ratings = eloplus.replay(g.result for g in fixture_games).ratings
    rows, rho = eloplus.standings_check(fixture_games, ratings, 1729, "2015/2016")
    assert len(rows) == 20
    assert (rows[0].points, rows[0].points_rank, rows[0].elo_rank) == (81, 1, 1)
    assert rho == pytest.approx(0.9699248120300752)


def test_load_results_agree_with_load_games(fixture_games: list[eloplus.Game]) -> None:
    assert [g.result for g in fixture_games] == queries.load_results(data.connect(FIXTURE))

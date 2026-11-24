"""Course 2 and 3 demo code on a seeded synthetic database (3 leagues, 8 seasons), with SQL parity."""

from __future__ import annotations

import duckdb
import pytest

from dbx_ds import course2, course3, features, load, sqldemo, stats
from dbx_ds.changelog import ChangeLog
from tests.synth import synth_connection


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    return synth_connection()


@pytest.fixture(scope="module")
def matches(con: duckdb.DuckDBPyConnection) -> list[load.MatchRow]:
    return load.load_matches(con)


def one(con: duckdb.DuckDBPyConnection, label: str, name: str = "demo_stats.sql") -> tuple[object, ...]:
    sql = dict((lab, s) for lab, s in sqldemo.load(name))[label]
    row = con.execute(sql).fetchone()
    assert row is not None
    return row


def rows(con: duckdb.DuckDBPyConnection, label: str, name: str = "demo_stats.sql") -> list[tuple[object, ...]]:
    sql = dict((lab, s) for lab, s in sqldemo.load(name))[label]
    return con.execute(sql).fetchall()


def test_synthetic_database_shape(matches: list[load.MatchRow]) -> None:
    assert len(matches) == 3 * 8 * 40


# ---- course 2: shapes ----


def test_percentiles_and_distributions(con: duckdb.DuckDBPyConnection, matches: list[load.MatchRow]) -> None:
    p = course2.rating_percentiles(con)
    assert p["p25"] <= p["p50"] <= p["p75"] <= p["p99"]
    assert p["iqr"] == pytest.approx(p["p75"] - p["p25"])
    d = course2.goal_distribution(matches)
    assert d.n == len(matches) and sum(v for _, v in d.bars) == d.n
    assert course2.goal_distribution(matches, "away").mean < d.mean
    r = course2.rating_distribution(con)
    assert sum(v for _, v in r.bars) == r.n
    assert len(course2.top_home_goal_matches(con)) == 5
    effect = course2.outlier_effect(matches)
    assert effect["mean_all"] > effect["mean_without"] and effect["n_max"] >= 1


def test_cleaning_logs_every_change(con: duckdb.DuckDBPyConnection) -> None:
    quality = course2.rating_quality(con)
    kept, log = course2.clean_ratings(con)
    assert isinstance(log, ChangeLog)
    assert len(kept) == quality["rows"] - quality["nulls"]
    assert log.rows() and log.columns()


def test_league_and_result_summaries(con: duckdb.DuckDBPyConnection, matches: list[load.MatchRow]) -> None:
    leagues = course2.league_goals(con)
    assert [n for n, _, _ in leagues] == sorted(
        {m.league for m in matches}, key=lambda n: -dict((a, c) for a, _, c in leagues)[n]
    )
    assert all(n == 320 for _, n, _ in leagues)
    home, draw, away = course2.result_counts(matches)
    assert home + draw + away == len(matches)
    assert sum(course2.result_shares(matches)) == pytest.approx(1.0)
    mh, ma = course2.mean_goals(matches)
    assert mh > ma
    assert len(course2.league_home_win_rates(matches)) == 3


def test_sampling_demos(matches: list[load.MatchRow]) -> None:
    small = course2.small_sample_demo(matches)
    assert [n for n, _, _ in small] == [10, 380, len(matches)]
    assert small[0][1] > small[1][1] > small[2][1]
    running = course2.running_home_win_rate(matches)
    assert running[-1][0] == len(matches)
    assert course2.running_home_win_rate(matches[:7], points=10)[-1][0] == 7


def test_probability_demos(matches: list[load.MatchRow]) -> None:
    ind = course2.independence(matches)
    assert ind["product"] == pytest.approx(ind["p_home0"] * ind["p_away0"])
    cond = course2.conditional_home_win(matches)
    assert cond["p_win_given_scored"] == pytest.approx(cond["p_win"] / cond["p_scored"])
    table = course2.fair_odds_table(matches)
    assert [o for o, *_ in table] == ["home win", "draw", "away win"]
    for _, rate, fair, priced in table:
        assert fair == pytest.approx(1 / rate) and priced == pytest.approx(fair / 1.05)
    tables = course2.poisson_tables(matches)
    assert set(tables) == {"home", "away"} and len(tables["home"]) == 8
    fit = course2.poisson_fit(matches)
    assert [k for k, _, _ in fit] == list(range(8))
    variance, mean = course2.variance_vs_mean(matches)
    assert variance > 0 and mean > 0


def test_simulation_is_seeded(matches: list[load.MatchRow]) -> None:
    a = course2.simulate(matches)
    assert a == course2.simulate(matches)
    assert a != course2.simulate(matches, seed=course2.SIMULATION_SEED + 1)


def test_the_script_season_is_reproduced() -> None:
    lam_home, lam_away = 1.5445937103044767, 1.1609376804341969
    _, counts = stats.simulate_season(lam_home, lam_away, course2.SEASON_LENGTH, course2.SIMULATION_SEED)
    assert counts == (175, 96, 109)


def test_player_demos(con: duckdb.DuckDBPyConnection) -> None:
    corr = course2.attribute_correlations(con)
    assert [(x, y) for x, y, _ in corr][0] == ("overall_rating", "potential")
    points = course2.scatter_sample(con, "potential", "overall_rating")
    assert points == course2.scatter_sample(con, "potential", "overall_rating")
    mean_rating, mean_potential = course2.rating_potential_means(con)
    assert mean_potential > mean_rating
    z = course2.rating_z(con)
    assert z["z_84"] > 0 > z["z_64"] or z["z_84"] > z["z_64"]
    assert len(course2.league_goal_z(con)) == 3
    assert len(course2.latest_player_rows(con)) == 60
    ranked = course2.rank_players(con)
    assert len(ranked) == 10 and ranked[0][3] >= ranked[-1][3]
    unc = course2.uncertainty(load.load_matches(con))
    assert all(low < rate < high for _, rate, low, high in unc)


# ---- course 3 ----


def test_cleaning_checks(con: duckdb.DuckDBPyConnection) -> None:
    most, repeated = course3.duplicate_check(con)
    assert (most, repeated) == (1, 0)
    bad, first, last = features.date_check(course3.match_dates(con))
    assert bad == 0 and first < last
    checks = {name: (lo, hi) for name, lo, hi in course3.range_checks(con)}
    assert checks["distinct seasons"] == (8.0, 8.0)
    assert checks["home_team_goal"][0] >= 0


def test_date_check_counts_bad_dates() -> None:
    bad, first, last = features.date_check(["2010-01-02 00:00:00", "not a date", "2010-03-04 00:00:00"])
    assert (bad, str(first), str(last)) == (1, "2010-01-02", "2010-03-04")


def test_features_have_no_future_data(matches: list[load.MatchRow]) -> None:
    feats = features.build_features(matches)
    assert len(feats) == len(matches)
    seen: set[tuple[str, str]] = set()
    for m, f in zip(matches, feats, strict=True):
        assert f.match_api_id == m.match_api_id
        # a team's first match of a season has no form yet
        assert (f.home_form is None) == ((m.season, m.home) not in seen)
        assert (f.away_form is None) == ((m.season, m.away) not in seen)
        seen |= {(m.season, m.home), (m.season, m.away)}
    assert all(1 <= f.home_rest <= features.REST_CAP for f in feats)


def test_features_do_not_change_when_the_future_changes(matches: list[load.MatchRow]) -> None:
    cut = 400
    head = features.build_features(matches[:cut])
    altered = [load.MatchRow(**{**m.__dict__, "home_goals": m.home_goals + 3}) for m in matches[cut:]]
    again = features.build_features(matches[:cut] + altered)
    assert [(f.home_form, f.away_form, f.elo_gap, f.home_rest) for f in head] == [
        (f.home_form, f.away_form, f.elo_gap, f.home_rest) for f in again[:cut]
    ]


def test_target_and_splits(matches: list[load.MatchRow]) -> None:
    rows_, ones, share = features.target_summary(matches)
    assert rows_ == len(matches) and share == ones / rows_
    feats = features.build_features(matches)
    train, test = features.time_split(feats)
    assert len(train) == 6 * 120 and len(test) == 2 * 120
    assert max(f.season for f in train) < min(f.season for f in test)
    assert features.split_cutoff(feats) == "2013/2014"
    assert features.split_cutoff(feats, "1999/2000") == "2008/2009"


def test_leakage_and_importance(matches: list[load.MatchRow]) -> None:
    feats = features.build_features(matches)
    leak = features.leakage_demo(feats)
    assert leak["leaky"] == 1.0 and leak["clean"] < 1.0
    importance = features.feature_importance(feats)
    assert importance[0][0] == "goal_diff (leak)"
    rest = features.rest_vs_home_win(feats)
    assert sum(n for _, n, _ in rest) == len(feats)


def test_rating_regression(con: duckdb.DuckDBPyConnection) -> None:
    players = course3.player_rows(con)
    fit = course3.fit_rating(players)
    assert fit.n == len(players) and 0 < fit.r_squared <= 1
    assert fit.names == course3.RATING_INPUTS and len(fit.coefs) == 5 and len(fit.z_coefs) == 5
    spread = course3.residual_spread(players, fit)
    assert abs(spread["mean"]) < 1e-6 and spread["min"] < 0 < spread["max"]
    assert sum(v for _, v in course3.residual_histogram(players, fit)) == len(players)
    under = course3.underrated(players, fit)
    assert len(under) == course3.UNDERRATED_TOP
    assert [r[3] for r in under] == sorted(r[3] for r in under)


def test_plan_markdown_names_the_four_parts() -> None:
    text = course3.plan_markdown("Q?", "M", "B", "S")
    for part in ("Q?", "M", "B", "S"):
        assert part in text


def test_capstone_is_deterministic_and_beats_nothing_it_should_not(matches: list[load.MatchRow]) -> None:
    feats = features.build_features(matches)
    a = course3.capstone(feats)
    assert a == course3.capstone(feats)
    assert (a.n_train, a.n_test) == (720, 240)
    assert [n for n, _ in a.coefficients] == list(course3.INPUT_NAMES)
    assert sum(c for *_, c in a.calibration) == a.n_test


# ---- SQL parity: every Python demo against its SQL twin ----


def test_parity_percentiles(con: duckdb.DuckDBPyConnection) -> None:
    n, p25, p50, p75, p95, p99, iqr = one(con, "1.1.5 percentiles of overall_rating")
    p = course2.rating_percentiles(con)
    assert (n, p25, p50, p75, p95, p99, iqr) == pytest.approx(
        (p["n"], p["p25"], p["p50"], p["p75"], p["p95"], p["p99"], p["iqr"])
    )


def test_parity_league_tables(con: duckdb.DuckDBPyConnection, matches: list[load.MatchRow]) -> None:
    sql_rows = rows(con, "1.3.2 leagues side by side")
    py_rows = course2.league_goals(con)
    assert [(a, b) for a, b, _ in sql_rows] == [(a, b) for a, b, _ in py_rows]
    assert [c for *_, c in sql_rows] == pytest.approx([c for *_, c in py_rows])
    sql_rate = rows(con, "1.3.3 home win rate per league")
    assert [(a, round(b, 9)) for a, b in sql_rate] == [
        (a, round(b, 9)) for a, b in course2.league_home_win_rates(matches)
    ]
    assert one(con, "1.3.3 home, draw and away shares") == pytest.approx(course2.result_shares(matches))


def test_parity_probability(con: duckdb.DuckDBPyConnection, matches: list[load.MatchRow]) -> None:
    ind = course2.independence(matches)
    assert one(con, "2.1.3 independent events") == pytest.approx(
        (ind["p_home0"], ind["p_away0"], ind["p_0_0"], ind["corr"])
    )
    cond = course2.conditional_home_win(matches)
    assert one(con, "2.1.4 conditional probability") == pytest.approx(
        (cond["p_win"], cond["p_scored"], cond["p_win_given_scored"])
    )
    fair = course2.fair_odds_table(matches)
    sql_fair = rows(con, "2.1.5 fair decimal odds")
    assert [(a, round(b, 9), round(c, 9)) for a, b, c in sql_fair] == [
        (a, round(b, 9), round(c, 9)) for a, b, c, _ in sorted(fair, key=lambda r: -r[1])
    ]
    assert [p for _, p in rows(con, "2.2.3 Poisson probabilities for k = 0 to 7 home goals")] == pytest.approx(
        [p for _, p in course2.poisson_tables(matches)["home"]]
    )
    sql_obs = [o for _, o in rows(con, "2.2.4 observed share of home goals by k, 0 to 7")]
    assert sql_obs == pytest.approx([real for _, real, _ in course2.poisson_fit(matches)])


def test_parity_players_and_z(con: duckdb.DuckDBPyConnection, matches: list[load.MatchRow]) -> None:
    corr = {(x, y): c for x, y, c in course2.attribute_correlations(con)}
    assert one(con, "2.3.2 correlations") == pytest.approx(
        (
            corr[("overall_rating", "potential")],
            corr[("overall_rating", "sprint_speed")],
            corr[("overall_rating", "finishing")],
        )
    )
    z = course2.rating_z(con)
    assert one(con, "2.3.4 z-score of a rating of 84") == pytest.approx((z["mean"], z["sd"], z["z_84"]))
    sql_z = rows(con, "3.1.3 league mean goals with z")
    py_z = course2.league_goal_z(con)
    assert [a for a, *_ in sql_z] == [a for a, *_ in py_z]
    assert [v for _, *rest in sql_z for v in rest] == pytest.approx([v for _, *rest in py_z for v in rest])
    n, rate, err = one(con, "3.1.4 typical error of the home win rate")
    py_rate = sum(1 for m in matches if m.home_goals > m.away_goals) / len(matches)
    assert (n, rate, err) == pytest.approx((len(matches), py_rate, stats.standard_error_rate(py_rate, len(matches))))


def test_parity_features(con: duckdb.DuckDBPyConnection, matches: list[load.MatchRow]) -> None:
    feats = features.build_features(matches)
    total, wins = one(con, "1.1.3 the target: home_win = home goals > away goals", "demo_features.sql")
    assert (total, wins) == features.target_summary(matches)[:2]
    form = {
        (mid, side): f
        for mid, side, f in rows(
            con,
            "1.3.2 form: points per game over the last 5 earlier matches of the team in the season (NULL at season start)",  # noqa: E501
            "demo_features.sql",
        )
    }
    rest = {
        (mid, side): r
        for mid, side, r in rows(
            con, "1.3.4 rest days since the team's previous match, capped at 10", "demo_features.sql"
        )
    }
    for f in feats:
        for side, py_form, py_rest in (("home", f.home_form, f.home_rest), ("away", f.away_form, f.away_rest)):
            sql_form = form[(f.match_api_id, side)]
            assert (sql_form is None and py_form is None) or sql_form == pytest.approx(py_form)
            assert rest[(f.match_api_id, side)] == py_rest
    parts = dict(rows(con, "2.1.3 time-based split: train up to 2013/2014, test after", "demo_features.sql"))
    train, test = features.time_split(feats)
    assert parts == {"train": len(train), "test": len(test)}


def test_baseline_log_losses_names_both_methods() -> None:
    feats = features.build_features(load.load_matches(synth_connection()))
    losses = course3.baseline_log_losses(feats)
    assert set(losses) == {"train rates, test rows", "all rates, all rows"}
    assert all(1.0 < v < 1.2 for v in losses.values())

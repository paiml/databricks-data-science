"""Numbers the course 4 and 5 scripts quote, measured on the full database (run on `intel`, never on lambda).

Skipped when the parquet export is absent. Python and SQL must agree on the full data as well.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import duckdb
import pytest

from dbx_ds import course3, course4, data, eloplus, features, load, mvpplus, queries, sqldemo
from tests.conftest import REPO

FULL = Path(os.environ.get("DBX_DS_FULL", REPO / "data" / "parquet"))

pytestmark = [
    pytest.mark.full_data,
    pytest.mark.skipif(not (FULL / "Match.parquet").exists(), reason="full database not built (run `make data`)"),
]


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    return data.connect(FULL)


@pytest.fixture(scope="module")
def analysis(con: duckdb.DuckDBPyConnection) -> course4.Analysis:
    return course4.analyse(con)


def test_elo_headline_numbers(con: duckdb.DuckDBPyConnection, analysis: course4.Analysis) -> None:
    assert len(analysis.games) == 25979 and len(analysis.ratings) == 1481
    league = course4.league_id(con)
    top = eloplus.elo_table(analysis.games, analysis.ratings, league, "2008/2009")[:2]
    assert [(analysis.teams[t], round(r, 1)) for _, _, t, r in top] == [
        ("Manchester United", 1656.4),
        ("Liverpool", 1649.9),
    ]


def test_home_advantage_and_tuning_grid(analysis: course4.Analysis) -> None:
    results = [g.result for g in analysis.games]
    stats = eloplus.home_stats(results)
    assert (round(stats.home_pct, 2), round(stats.draw_pct, 2), round(stats.away_pct, 2)) == (45.87, 25.39, 28.74)
    assert (round(stats.home_goals, 3), round(stats.away_goals, 3)) == (1.545, 1.161)
    grid = {(t.k_factor, t.home_advantage): t.mse for t in eloplus.tune(results, course4.GRID_KS, [100.0])}
    assert {k: round(v, 4) for (k, _), v in grid.items()} == {
        5.0: 0.1647, 10.0: 0.1608, 20.0: 0.1591, 30.0: 0.1595, 40.0: 0.1605, 60.0: 0.1634,
    }  # fmt: skip


def test_standings_check_values(con: duckdb.DuckDBPyConnection, analysis: course4.Analysis) -> None:
    rows, _ = eloplus.standings_check(analysis.games, analysis.ratings, course4.league_id(con), "2015/2016")
    by_name = {analysis.teams[r.team_api_id]: r for r in rows}
    leicester, arsenal = by_name["Leicester City"], by_name["Arsenal"]
    assert (leicester.points, round(leicester.elo, 1), leicester.elo_rank) == (81, 1665.9, 3)
    assert (arsenal.points, round(arsenal.elo, 1), arsenal.elo_rank) == (71, 1695.8, 1)


def test_all_league_player_counts_and_per_league_mvp(
    con: duckdb.DuckDBPyConnection, analysis: course4.Analysis
) -> None:
    counts = sorted(Counter(r.season for r in queries.python_mvp(con)).items())
    assert counts[0] == ("2008/2009", 2199) and counts[-1] == ("2015/2016", 3003)
    spain = course4.league_id(con, "Spain LIGA BBVA")
    mvps = {s.season: s.player_name for s in mvpplus.mvp_per_season(analysis.scores, spain)}
    assert mvps["2015/2016"] == "Lionel Messi"
    messi = next(s for s in analysis.scores if s.league_id == spain and s.season == "2015/2016" and s.score_rank == 1)
    assert round(messi.score, 2) == 89.35


def test_baseline_log_loss_is_1_0715_not_1_06(con: duckdb.DuckDBPyConnection) -> None:
    losses = course3.baseline_log_losses(features.build_features(load.load_matches(con)))
    assert round(losses["train rates, test rows"], 4) == 1.0715
    assert round(losses["all rates, all rows"], 3) == 1.064


def test_sql_equals_python_on_the_full_data(con: duckdb.DuckDBPyConnection, analysis: course4.Analysis) -> None:
    course4.create_views(con)
    course4.register_python_tables(con, analysis)
    assert course4.parity_differences(con) == [0, 0]


def test_current_elo_top_is_benfica_in_python_and_sql(
    con: duckdb.DuckDBPyConnection, analysis: course4.Analysis
) -> None:
    """The course 4 and course 5 headline: Benfica is #1 at 1868.8, and both languages print the same table."""
    top = course4.current_top(analysis)
    assert top[0] == (1, "SL Benfica", 1868.8)
    assert [t[1] for t in top[:3]] == ["SL Benfica", "FC Bayern Munich", "Juventus"]
    course4.create_views(con)
    sql = next(s for lbl, s in sqldemo.load("demo_elo.sql") if lbl.startswith("3.1.1 all leagues"))
    assert [(p, n, r) for p, n, r in con.execute(sql).fetchall()] == top


def test_report_mvp_and_adjacent_agree_across_languages(
    con: duckdb.DuckDBPyConnection, analysis: course4.Analysis
) -> None:
    course4.create_views(con)
    sql = next(s for lbl, s in sqldemo.load("demo_mvp.sql") if lbl.startswith("3.1.4"))
    rows = con.execute(sql).fetchall()
    league = course4.league_id(con)
    card = course4.card_lines(analysis, league, "2015/2016")
    assert [n for sec, _, n, _ in rows if sec == "mvp"][0] == card[0].split("MVP: ", 1)[1].split(" (")[0]
    assert [n for sec, _, n, _ in rows if sec == "shortlist"] == [
        ln.split(". ", 1)[1].split("  score rank")[0] for ln in card[1:]
    ]

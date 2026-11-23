"""Numbers the course 1 to 3 scripts quote, measured on the full database.

Skipped when `make data` has not been run (the fixture-only CI run stays green). Locally:
`make data && pytest -m full_data`. Set DBX_DS_FULL to point at another parquet export.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

from dbx_ds import course2, course3, data, features, load, sqldemo
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
def matches(con: duckdb.DuckDBPyConnection) -> list[load.MatchRow]:
    return load.load_matches(con)


def test_course1_headline_numbers(con: duckdb.DuckDBPyConnection) -> None:
    assert con.execute("SELECT count(*) FROM Match").fetchone() == (25979,)
    assert con.execute("SELECT sum(home_team_goal + away_team_goal) FROM Match").fetchone() == (70287,)
    rows = {
        name: (n, goals)
        for name, n, goals in con.execute(
            "SELECT l.name, count(*), sum(m.home_team_goal + m.away_team_goal) "
            "FROM Match m JOIN League l ON m.league_id = l.id GROUP BY l.name"
        ).fetchall()
    }
    n, goals = rows["Netherlands Eredivisie"]
    assert round(goals / n, 2) == 3.08


def test_course1_notebook_queries_run(con: duckdb.DuckDBPyConnection) -> None:
    for _, sql in sqldemo.load("demo_course1.sql"):
        con.execute(sql).fetchall()


def test_course2_numbers(con: duckdb.DuckDBPyConnection, matches: list[load.MatchRow]) -> None:
    p = course2.rating_percentiles(con)
    assert (p["n"], p["p25"], p["p50"], p["p75"], p["p95"], p["p99"], p["iqr"]) == (183142, 64, 69, 73, 80, 84, 9)
    assert [round(s * 100, 1) for s in course2.result_shares(matches)] == [45.9, 25.4, 28.7]
    assert course2.result_counts(matches) == (11917, 6596, 7466)
    assert round(course2.rating_z(con)["z_84"], 2) == 2.19
    low, high = (round(v * 100) for v in course2.uncertainty(matches)[0][2:])
    assert (low, high) == (41, 51)


def test_course2_simulated_season_matches_the_script(matches: list[load.MatchRow]) -> None:
    sim = course2.simulate(matches)
    assert (sim["home_wins"], sim["draws"], sim["away_wins"]) == (175, 96, 109)


def test_course3_split_and_checks(con: duckdb.DuckDBPyConnection, matches: list[load.MatchRow]) -> None:
    assert features.target_summary(matches)[:2] == (25979, 11917)
    assert course3.duplicate_check(con) == (1, 0)
    assert features.date_check(course3.match_dates(con))[0] == 0
    ranges = {name: (lo, hi) for name, lo, hi in course3.range_checks(con)}
    assert ranges["home_team_goal"] == (0.0, 10.0)
    assert ranges["overall_rating"] == (33.0, 94.0)
    assert ranges["distinct seasons"] == (8.0, 8.0)
    train, test = features.time_split(features.build_features(matches))
    assert (len(train), len(test)) == (19328, 6651)


def test_course3_capstone_beats_the_baseline(matches: list[load.MatchRow]) -> None:
    result = course3.capstone(features.build_features(matches))
    assert (result.n_train, result.n_test) == (19328, 6651)
    assert round(result.baseline_log_loss, 2) == 1.07
    assert result.log_loss < result.baseline_log_loss
    assert result.accuracy > result.baseline_accuracy

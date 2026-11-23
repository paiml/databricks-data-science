"""Course 5 SQL against the Python twins: Elo, tuning grid, MVP tables, the demo files and the parity query."""

from __future__ import annotations

import duckdb
import pytest

from dbx_ds import course4, data, eloplus, mvpplus, sqldemo
from tests.conftest import FIXTURE, REPO
from tests.synth_league import league_connection


@pytest.fixture(scope="module", params=["fixture", "synthetic"])
def world(request: pytest.FixtureRequest) -> tuple[duckdb.DuckDBPyConnection, course4.Analysis]:
    con = data.connect(FIXTURE) if request.param == "fixture" else league_connection()
    analysis = course4.analyse(con)
    course4.create_views(con)
    course4.register_python_tables(con, analysis)
    return con, analysis


def test_view_script_creates_every_view() -> None:
    con = data.connect(FIXTURE)
    assert course4.create_views(con) == 7


def test_python_and_sql_tables_agree(world: tuple[duckdb.DuckDBPyConnection, course4.Analysis]) -> None:
    con, _ = world
    assert course4.parity_differences(con) == [0, 0]


def test_the_parity_query_sees_a_difference(world: tuple[duckdb.DuckDBPyConnection, course4.Analysis]) -> None:
    con, analysis = world
    other = con.cursor()
    other.execute("UPDATE py_elo SET rating = rating + 1 WHERE rowid = 0")
    other.execute("UPDATE py_mvp SET score = score + 1 WHERE rowid = 0")
    assert course4.parity_differences(con) == [1, 1]
    course4.register_python_tables(con, analysis)
    assert course4.parity_differences(con) == [0, 0]


def test_standalone_elo_equals_python(world: tuple[duckdb.DuckDBPyConnection, course4.Analysis]) -> None:
    con, analysis = world
    sql = (REPO / "sql" / "elo_dbx.sql").read_text()
    rows = con.execute(sql).fetchall()
    expected = {(s, t): r for (s, _, t, r) in course4.python_elo_rows(analysis)}
    assert len(rows) == len(expected)
    for season, team, rating in rows:
        assert rating == pytest.approx(expected[(season, team)], abs=1e-9)


def test_sql_tuning_grid_equals_python(world: tuple[duckdb.DuckDBPyConnection, course4.Analysis]) -> None:
    con, analysis = world
    labelled = dict(sqldemo.load("demo_elo.sql"))
    for label, sql in sqldemo.load("demo_elo.sql"):
        rows = con.execute(sql).fetchall() if not label.startswith("1.3.4 tuning, step 2") else None
        if rows is None:
            grid = con.execute(sql).fetchall()
    assert labelled
    python = {
        (t.k_factor, t.home_advantage): t.mse
        for t in eloplus.tune([g.result for g in analysis.games], course4.GRID_KS, course4.GRID_BONUSES)
    }
    assert len(grid) == len(python) == 24
    for k, bonus, mse in grid:
        assert mse == pytest.approx(python[(k, bonus)], abs=1e-9)


def test_demo_mvp_statements_run() -> None:
    con = data.connect(FIXTURE)
    course4.create_views(con)
    statements = sqldemo.load("demo_mvp.sql")
    assert len(statements) == 10
    for label, sql in statements:
        assert label
        assert con.execute(sql).fetchall(), label


def test_sql_sweep_equals_python(world: tuple[duckdb.DuckDBPyConnection, course4.Analysis]) -> None:
    con, analysis = world
    league, name = con.execute("SELECT id, name FROM League ORDER BY id LIMIT 1").fetchone() or (0, "")
    (sweep_sql,) = [sql for label, sql in sqldemo.load("demo_mvp.sql") if label.startswith("2.2.5")]
    rows = con.execute(sweep_sql.replace("England Premier League", name)).fetchall()
    python = {
        (s.quality_weight, s.min_starts): (len(s.mvps), s.changed)
        for s in mvpplus.sweep(
            analysis.games, analysis.player_ratings, analysis.names, league, [0.9, 0.7, 0.5], course4.SWEEP_STARTS
        )
    }
    assert len(rows) == sum(1 for seasons, _ in python.values() if seasons)
    assert rows
    for quality, minimum, seasons, changed in rows:
        assert python[(quality, minimum)] == (seasons, changed)


def test_sweep_counts_only_seasons_that_still_have_an_mvp() -> None:
    analysis = course4.analyse(league_connection())
    settings = mvpplus.sweep(analysis.games, analysis.player_ratings, analysis.names, 40, [0.7], [10, 1000])
    assert [len(s.mvps) for s in settings] == [4, 0]
    assert settings[1].changed == 0


def test_league_id_by_name_and_missing_name() -> None:
    con = league_connection()
    assert course4.league_id(con, "Beta League") == 20
    with pytest.raises(KeyError, match="no league called"):
        course4.league_id(con, "Nowhere League")

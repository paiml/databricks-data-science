"""The demo .sql files parse, run, and the course 1 notebook carries every statement."""

from __future__ import annotations

import duckdb
import pytest

from dbx_ds import cli, data, dbxapi, report, sqldemo, sqlinline
from tests.conftest import FIXTURE, REPO


def test_parse_splits_sections_and_drops_comments() -> None:
    text = "-- header\n-- 1.2.3 first\nSELECT 1 -- note\n;\n-- capstone wrap\nSELECT 2;\n"
    assert sqldemo.parse(text) == [("1.2.3 first", "SELECT 1"), ("capstone wrap", "SELECT 2")]


def test_normalise_collapses_whitespace() -> None:
    assert sqldemo.normalise("SELECT  a,\n   b") == "SELECT a, b"


@pytest.mark.parametrize("name", ["demo_course1.sql", "demo_stats.sql", "demo_features.sql"])
def test_every_statement_runs_on_the_fixture(name: str) -> None:
    con = data.connect(FIXTURE)
    statements = sqldemo.load(name)
    assert statements
    for label, sql in statements:
        assert label
        con.execute(sql).fetchall()


def test_course1_notebook_has_every_statement(monkeypatch: pytest.MonkeyPatch) -> None:
    text = (REPO / "notebooks" / "course1_databricks_from_zero.py").read_text()
    flat = sqldemo.normalise(text)
    for label, sql in sqldemo.load("demo_course1.sql"):
        assert f"# Lesson {label}" in text
        assert sqldemo.normalise(sql) in flat


def test_report_show_truncates(capsys: pytest.CaptureFixture[str]) -> None:
    con = data.connect(FIXTURE)
    report.show(con, "SELECT * FROM generate_series(1, 30) AS t(n)", limit=5)
    out = capsys.readouterr().out
    assert "... 25 more rows" in out
    report.show(con, "SELECT 1 AS one")
    assert "more rows" not in capsys.readouterr().out


def _stable(row: tuple[object, ...]) -> str:
    """Row text with floats cut to 9 places: a parallel sum may differ in the last bits between runs."""
    return repr(tuple(round(v, 9) if isinstance(v, float) else v for v in row))


STANDALONE = ["demo_elo.sql", "demo_mvp.sql", "demo_course1.sql", "demo_stats.sql", "demo_features.sql"]


@pytest.mark.parametrize("name", STANDALONE)
def test_every_captured_statement_runs_alone_and_matches_the_session(name: str) -> None:
    """Each statement the capture sends works on a fresh connection (no view from another call) and agrees
    with the same statement run in one session that created the views."""
    sql_dir = REPO / "sql"
    setup = dbxapi.split_statements((sql_dir / "c5_views.sql").read_text())
    statements = dbxapi.split_statements((sql_dir / name).read_text())
    session = data.connect(FIXTURE)
    for stmt in setup:
        session.execute(stmt)
    checked = rows = 0
    for stmt, alone in zip(statements, sqlinline.standalone(statements, setup), strict=True):
        expected = session.execute(stmt).fetchall()
        if alone is None:
            continue
        got = data.connect(FIXTURE).execute(alone).fetchall()
        assert sorted(map(_stable, got)) == sorted(map(_stable, expected)), alone[:200]
        checked += 1
        rows += len(expected)
    assert checked and rows


def test_parity_is_the_only_demo_file_left_out_of_capture() -> None:
    demos = {p.name for p in (REPO / "sql").glob("demo_*.sql")}
    assert demos - set(STANDALONE) == cli.NOT_ON_DATABRICKS == {"demo_parity.sql"}


def test_fresh_connection_has_no_views() -> None:
    """The premise of the standalone test: nothing but the base tables exists until a statement brings its own."""
    with pytest.raises(duckdb.CatalogException):
        data.connect(FIXTURE).execute("SELECT * FROM elo_season")

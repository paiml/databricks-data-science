"""The demo .sql files parse, run, and the course 1 notebook carries every statement."""

from __future__ import annotations

import pytest

from dbx_ds import data, report, sqldemo
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

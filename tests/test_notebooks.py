"""Every notebook runs on the committed fixture."""

from __future__ import annotations

import re
import runpy
from pathlib import Path

import pytest

from dbx_ds import course4, data, sqldemo
from tests.conftest import FIXTURE, REPO

NOTEBOOKS = sorted((REPO / "notebooks").glob("course[1-4]_*.py"))


def test_there_is_one_notebook_per_course() -> None:
    names = sorted(p.name[:7] for p in (REPO / "notebooks").iterdir())
    assert names == [f"course{i}" for i in range(1, 6)]


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
def test_python_notebook_runs(path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("DBX_DS_ROOT", str(REPO))
    monkeypatch.setenv("DBX_DS_DATA", str(FIXTURE))
    runpy.run_path(str(path))
    assert capsys.readouterr().out.strip()


def test_sql_notebook_cells_run() -> None:
    text = (REPO / "notebooks" / "course5_sports_analytics_sql.sql").read_text()
    cells = [c.strip() for c in text.split("-- COMMAND ----------")[1:]]
    con = data.connect(FIXTURE)
    course4.register_python_tables(con, course4.analyse(con))
    ran = 0
    for cell in cells:
        if cell.startswith("-- databricks-only") or cell.startswith("-- MAGIC"):
            continue
        rows = con.execute(cell).fetchall()
        if re.match(r"(--[^\n]*\n)*\s*(SELECT|WITH)\b(?!.*CREATE)", cell) and "CREATE OR REPLACE TEMP VIEW" not in cell:
            assert rows, cell[:80]
        ran += 1
    assert ran == 37
    assert con.execute("SELECT count(*) FROM mvp_scores").fetchone() == (649,)


def test_sql_notebook_carries_the_standalone_elo_query() -> None:
    flat = sqldemo.normalise((REPO / "notebooks" / "course5_sports_analytics_sql.sql").read_text())
    ((_, standalone),) = sqldemo.parse((REPO / "sql" / "elo_dbx.sql").read_text())
    assert sqldemo.normalise(standalone) in flat


def test_sql_notebook_carries_every_demo_statement() -> None:
    flat = sqldemo.normalise((REPO / "notebooks" / "course5_sports_analytics_sql.sql").read_text())
    for name in ("c5_views.sql", "demo_elo.sql", "demo_mvp.sql", "demo_parity.sql"):
        for label, sql in sqldemo.load(name):
            assert sqldemo.normalise(sql) in flat, label


CHART_COUNTS = {"course2_statistics_from_zero": 6, "course3_data_science_from_zero": 2}


@pytest.mark.parametrize("name", sorted(CHART_COUNTS))
def test_chart_cells_are_deterministic(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DBX_DS_ROOT", str(REPO))
    monkeypatch.setenv("DBX_DS_DATA", str(FIXTURE))
    runs = []
    for _ in range(2):
        runpy.run_path(str(REPO / "notebooks" / f"{name}.py"))
        runs.append(re.findall(r"^chart .* sha256:[0-9a-f]{12}$", capsys.readouterr().out, re.M))
    assert len(runs[0]) == CHART_COUNTS[name]
    assert runs[0] == runs[1]

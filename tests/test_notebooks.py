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
    assert ran == 36
    assert con.execute("SELECT count(*) FROM mvp_scores").fetchone() == (649,)


def test_sql_notebook_carries_every_demo_statement() -> None:
    flat = sqldemo.normalise((REPO / "notebooks" / "course5_sports_analytics_sql.sql").read_text())
    for name in ("c5_views.sql", "demo_elo.sql", "demo_mvp.sql", "demo_parity.sql"):
        for label, sql in sqldemo.load(name):
            assert sqldemo.normalise(sql) in flat, label

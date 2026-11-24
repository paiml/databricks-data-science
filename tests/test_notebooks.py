"""Every notebook runs on the committed fixture."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from dbx_ds import data
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
    ran = 0
    for cell in cells:
        if cell.startswith("-- databricks-only"):
            continue
        assert con.execute(cell).fetchall()
        ran += 1
    assert ran == 2

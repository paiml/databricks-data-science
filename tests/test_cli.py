from __future__ import annotations

from pathlib import Path

import pytest

from dbx_ds import cli, data
from tests.conftest import FIXTURE


def test_elo_prints_the_top_teams(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["elo", "--data-dir", str(FIXTURE), "--top", "3"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 3
    assert float(lines[0].split()[0]) >= float(lines[2].split()[0])


def test_mvp_prints_mvp_and_adjacent_rows(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["mvp", "--data-dir", str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert "MVP  Eden Hazard" in out
    assert "  adj  " in out


def test_data_and_fixture_commands_use_the_default_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(data, "fetch", lambda dest: calls.append(("fetch", dest)))
    monkeypatch.setattr(
        data,
        "export_tables",
        lambda db, out, queries: calls.append(("export", (db, out, sorted(queries)))),
    )
    assert cli.main(["data"]) == 0
    assert cli.main(["fixture"]) == 0
    assert calls[0] == ("fetch", cli.DEFAULT_RAW)
    assert calls[1][1] == (cli.DEFAULT_RAW, cli.DEFAULT_PARQUET, sorted(data.full_queries()))
    assert calls[2][1] == (cli.DEFAULT_RAW, cli.DEFAULT_FIXTURE, sorted(data.fixture_queries()))
    assert "fixture written" in capsys.readouterr().out


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_paths_are_relative() -> None:
    assert not Path(cli.DEFAULT_RAW).is_absolute()

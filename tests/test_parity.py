"""The SQL and the Python must give the same answer on the same data."""

from __future__ import annotations

import re

import pytest

from dbx_ds import data, elo, mvp, queries
from tests.conftest import FIXTURE


@pytest.fixture(scope="module")
def con():  # type: ignore[no-untyped-def]
    return data.connect(FIXTURE)


def test_fixture_is_two_premier_league_seasons(con) -> None:  # type: ignore[no-untyped-def]
    assert con.execute("SELECT count(*) FROM Match").fetchone() == (760,)
    assert con.execute("SELECT name FROM League").fetchall() == [("England Premier League",)]


def test_elo_sql_equals_python(con) -> None:  # type: ignore[no-untyped-def]
    py, sql = queries.python_elo(con), queries.sql_elo(con)
    assert len(py) == len(sql) == 40
    for (s1, t1, r1), (s2, t2, r2) in zip(py, sql, strict=True):
        assert (s1, t1) == (s2, t2)
        assert r1 == pytest.approx(r2, abs=1e-9)


def test_mvp_sql_equals_python(con) -> None:  # type: ignore[no-untyped-def]
    py, sql = queries.python_mvp(con), queries.sql_mvp(con)
    assert len(py) == len(sql) > 0
    for a, b in zip(py, sql, strict=True):
        assert (a.season, a.player_api_id, a.player_name) == (
            b.season,
            b.player_api_id,
            b.player_name,
        )
        assert (a.appearances, a.score_rank, a.rating_rank) == (
            b.appearances,
            b.score_rank,
            b.rating_rank,
        )
        assert (a.is_mvp, a.is_adjacent) == (b.is_mvp, b.is_adjacent)
        assert a.overall_rating == pytest.approx(b.overall_rating)
        assert a.win_share == pytest.approx(b.win_share, abs=1e-9)
        assert a.score == pytest.approx(b.score, abs=1e-9)


def test_one_mvp_per_season_and_adjacent_exist(con) -> None:  # type: ignore[no-untyped-def]
    rows = queries.python_mvp(con)
    assert sorted(r.player_name for r in rows if r.is_mvp) == ["Eden Hazard", "Mesut Oezil"]
    assert any(r.is_adjacent for r in rows)


def test_sql_constants_equal_python_constants() -> None:
    elo_sql = (queries.SQL_DIR / "elo.sql").read_text()
    for name, value in {
        "initial_rating": elo.INITIAL_RATING,
        "k_factor": elo.K_FACTOR,
        "home_advantage": elo.HOME_ADVANTAGE,
        "scale": elo.SCALE,
    }.items():
        assert re.search(rf"{re.escape(str(value))}[^,]*AS {name}\b", elo_sql), name
    mvp_sql = (queries.SQL_DIR / "mvp.sql").read_text()
    for name, value in {
        "quality_weight": mvp.QUALITY_WEIGHT,
        "impact_weight": mvp.IMPACT_WEIGHT,
        "min_appearances": mvp.MIN_APPEARANCES,
        "few_appearances": mvp.FEW_APPEARANCES,
        "top_score_rank": mvp.TOP_SCORE_RANK,
        "rank_gap": mvp.RANK_GAP,
        "season_start_month": mvp.SEASON_START_MONTH,
        "score_scale": 10.0**mvp.SCORE_DECIMALS,
    }.items():
        assert re.search(rf"{re.escape(str(value))}[^,]*AS {name}\b", mvp_sql), name

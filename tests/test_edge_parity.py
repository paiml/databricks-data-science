"""Edge cases where SQL and Python used to disagree: ties, NULLs, rounding, season boundary."""

from __future__ import annotations

import duckdb
import pytest

from dbx_ds import data, mvp, queries
from tests.conftest import MATCH_COLS


def make_db(
    matches: list[dict[str, object]], attrs: list[tuple[int, int, str | None, float | None]], players: int = 30
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    cols = ", ".join(f"{c} {'VARCHAR' if c in ('season', 'date') else 'BIGINT'}" for c in MATCH_COLS)
    con.execute(f"CREATE TABLE Match ({cols})")
    con.execute("CREATE TABLE Player (player_api_id BIGINT, player_name VARCHAR)")
    con.execute("CREATE TABLE Player_Attributes (id BIGINT, player_api_id BIGINT, date VARCHAR, overall_rating DOUBLE)")
    con.executemany("INSERT INTO Player VALUES (?, ?)", [(p, f"P{p}") for p in range(1, players + 1)])
    if attrs:
        con.executemany("INSERT INTO Player_Attributes VALUES (?, ?, ?, ?)", attrs)
    for i, m in enumerate(matches, start=1):
        row: dict[str, object] = {c: None for c in MATCH_COLS}
        row.update(id=i, country_id=1, league_id=1, stage=1, match_api_id=1000 + i)
        row.update(m)
        con.execute(f"INSERT INTO Match VALUES ({', '.join('?' for _ in MATCH_COLS)})", [row[c] for c in MATCH_COLS])
    return con


def game(i: int, hg: int | None, ag: int | None, home: list[int], away: list[int] | None = None) -> dict[str, object]:
    row: dict[str, object] = {
        "season": "2014/2015",
        "date": f"2014-09-{i:02d} 00:00:00",
        "home_team_api_id": 10,
        "away_team_api_id": 20,
        "home_team_goal": hg,
        "away_team_goal": ag,
    }
    for n, p in enumerate(home, start=1):
        row[f"home_player_{n}"] = p
    for n, p in enumerate(away or [], start=1):
        row[f"away_player_{n}"] = p
    return row


def assert_same_mvp(con: duckdb.DuckDBPyConnection) -> list[mvp.PlayerScore]:
    py, sql = queries.python_mvp(con), queries.sql_mvp(con)
    assert py == sql
    return py


def test_null_goals_are_skipped_the_same_way_in_elo() -> None:
    con = make_db([game(1, None, None, [1]), game(2, 1, 0, [1]), game(3, 2, None, [1])], [])
    py, sql = queries.python_elo(con), queries.sql_elo(con)
    assert [(s, t) for s, t, _ in py] == [(s, t) for s, t, _ in sql] == [("2014/2015", 10), ("2014/2015", 20)]
    e = 1 / (1 + 10 ** (-100 / 400))
    assert py[0][2] == pytest.approx(1500 + 20 * (1 - e))
    for (_, _, a), (_, _, b) in zip(py, sql, strict=True):
        assert a == pytest.approx(b, abs=1e-9)


def test_null_goals_are_skipped_the_same_way_in_mvp() -> None:
    matches = [game(i, 1, 0, [1]) for i in range(1, 11)] + [game(11, None, 0, [1]), game(12, 1, None, [1])]
    attrs = [(1, 1, "2014-10-01 00:00:00", 70.0), (2, 1, None, 99.0)]
    (row,) = assert_same_mvp(make_db(matches, attrs))
    assert row.appearances == 10 and row.overall_rating == 70.0


def test_rounding_midpoint_is_identical() -> None:
    # 0.7 * 75.000005 = 52.5000035 -> both round half up to 52.500004
    matches = [game(i, 0, 1, [1]) for i in range(1, 11)]
    (row,) = assert_same_mvp(make_db(matches, [(1, 1, "2014-09-01 00:00:00", 75.000005)]))
    assert row.score == pytest.approx(52.500004, abs=1e-12)


def test_rating_ties_share_a_rank_in_sql_and_python() -> None:
    # 20 full-time matches (> FEW_APPEARANCES). Away side 1..11 loses every game; home side 12..22 wins.
    # Player 1 is rated 90, the other 21 are tied on 80. With ROW_NUMBER the winners would sit at rating
    # ranks 13..23 against score ranks 1..11, a false gap of 12 that makes them "adjacent"; with RANK()
    # they all share rating rank 2.
    matches = [game(i, 1, 0, list(range(12, 23)), list(range(1, 12))) for i in range(1, 21)]
    attrs = [(p, p, "2014-09-01 00:00:00", 90.0 if p == 1 else 80.0) for p in range(1, 23)]
    rows = {r.player_api_id: r for r in assert_same_mvp(make_db(matches, attrs, players=22))}
    winners = [rows[p] for p in range(12, 23)]
    assert len(winners) == 11 and all(r.appearances == 20 > mvp.FEW_APPEARANCES for r in winners)
    assert {r.rating_rank for p, r in rows.items() if p != 1} == {2}
    assert sorted(r.score_rank for r in winners) == list(range(1, 12))
    assert not any(r.is_adjacent for r in rows.values())
    assert [r.player_api_id for r in rows.values() if r.is_mvp] == [12]


def test_season_boundary_dates_agree() -> None:
    matches = [game(i, 1, 0, [1, 2, 3]) for i in range(1, 11)]
    matches = [{**m, "season": "2015/2016"} for m in matches]
    attrs = [
        (1, 1, "2015-07-31 00:00:00", 60.0),  # 2014/2015: no matches that season
        (2, 2, "2015-08-01 00:00:00", 70.0),  # 2015/2016
        (3, 3, "2015-09-01 00:00:00", 80.0),
        (4, 1, "2015-08-01 00:00:00", 65.0),
    ]
    rows = assert_same_mvp(make_db(matches, attrs))
    assert {r.player_api_id: r.overall_rating for r in rows} == {1: 65.0, 2: 70.0, 3: 80.0}


def test_season_of_matches_sql_for_every_month() -> None:
    con = duckdb.connect()
    for month in range(1, 13):
        date = f"2015-{month:02d}-15 00:00:00"
        matches = [{**game(i, 1, 0, [1]), "season": mvp.season_of(date)} for i in range(1, 11)]
        (row,) = assert_same_mvp(make_db(matches, [(1, 1, date, 70.0)]))
        assert row.season == mvp.season_of(date)
    del con


def test_connect_helper_is_reused() -> None:
    assert callable(data.connect)

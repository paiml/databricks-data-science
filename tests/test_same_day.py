"""A team that plays twice on one date: every Elo SQL must replay in (date, match_api_id) order, like Python."""

from __future__ import annotations

import duckdb
import pytest

from dbx_ds import elo, queries, sqldemo
from tests.conftest import MATCH_COLS, REPO

# (match_api_id, date, home, away, home goals, away goals). Team 1 plays three times on 2020-01-01 and the ids
# are out of insert order, so only the (date, match_api_id) tiebreak gives the right answer. Matches 7 and 8
# share team 2 and team 3 with later matches, so the replay needs more than one extra step on that date.
CASES = [
    (9, "2020-01-01 00:00:00", 1, 4, 0, 0),
    (5, "2020-01-01 00:00:00", 1, 2, 3, 0),
    (7, "2020-01-01 00:00:00", 3, 1, 0, 1),
    (8, "2020-01-01 00:00:00", 2, 3, 1, 1),
    (6, "2020-01-02 00:00:00", 4, 2, 2, 0),
    (4, "2019-12-31 00:00:00", 5, 6, 1, 0),
    (10, "2020-01-01 00:00:00", 5, 6, 0, 2),  # a second same-day pair that shares no team with the others
]


def double_header_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    ddl = ", ".join(c + (" VARCHAR" if c in ("season", "date") else " BIGINT") for c in MATCH_COLS)
    con.execute(f"CREATE TABLE Match ({ddl})")
    for i, (match_id, day, home, away, hg, ag) in enumerate(CASES, start=1):
        row = dict.fromkeys(MATCH_COLS)
        row.update(
            id=i,
            league_id=1,
            season="2019/2020",
            date=day,
            match_api_id=match_id,
            home_team_api_id=home,
            away_team_api_id=away,
            home_team_goal=hg,
            away_team_goal=ag,
        )
        con.execute(
            f"INSERT INTO Match VALUES ({', '.join('?' for _ in MATCH_COLS)})",
            [row[c] for c in MATCH_COLS],
        )
    return con


def check(rows: list[tuple[object, ...]], expected: list[tuple[str, int, float]]) -> None:
    assert len(rows) == len(expected)
    for (season, team, rating), (s, t, r) in zip(rows, expected, strict=True):
        assert (str(season), int(team)) == (s, t)  # type: ignore[call-overload]
        assert float(rating) == pytest.approx(r, abs=1e-9)  # type: ignore[arg-type]


def test_the_case_really_has_a_team_twice_on_one_date() -> None:
    con = double_header_connection()
    (twice,) = con.execute(
        "SELECT count(*) FROM (SELECT team, date FROM (SELECT home_team_api_id AS team, date FROM Match "
        "UNION ALL SELECT away_team_api_id, date FROM Match) GROUP BY team, date HAVING count(*) > 1)"
    ).fetchone() or (0,)
    assert twice >= 3


def test_map_elo_equals_python_on_double_headers() -> None:
    con = double_header_connection()
    check(queries.sql_elo(con), queries.python_elo(con))


def test_standalone_databricks_elo_equals_python_on_double_headers() -> None:
    con = double_header_connection()
    rows = con.execute((REPO / "sql" / "elo_dbx.sql").read_text()).fetchall()
    check(rows, queries.python_elo(con))


def test_view_elo_season_equals_python_on_double_headers() -> None:
    con = double_header_connection()
    for label, sql in sqldemo.load("c5_views.sql"):
        if label.startswith("3.1.2 view elo_"):
            con.execute(sql)
    rows = con.execute("SELECT season, team_api_id, rating FROM elo_season ORDER BY season, team_api_id").fetchall()
    check(rows, queries.python_elo(con))


def test_python_order_is_date_then_match_id() -> None:
    con = double_header_connection()
    ratings = elo.season_ratings(queries.load_results(con))
    shuffled = elo.season_ratings(list(reversed(queries.load_results(con))))
    assert ratings == shuffled

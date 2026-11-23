from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dbx_ds import data

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "data" / "fixture"

MATCH_COLS = [c.strip() for c in data.MATCH_COLUMNS.split(",")]


def _insert_match(db: sqlite3.Connection, row_id: int, league: int, season: str, home: int, away: int) -> None:
    values = {c: None for c in MATCH_COLS}
    values.update(
        id=row_id,
        country_id=league,
        league_id=league,
        season=season,
        stage=1,
        date=f"{season[:4]}-09-01 00:00:00",
        match_api_id=1000 + row_id,
        home_team_api_id=home,
        away_team_api_id=away,
        home_team_goal=1,
        away_team_goal=0,
        home_player_1=100 + league,
        away_player_1=200 + row_id,
    )
    db.execute(
        f"INSERT INTO Match ({', '.join(MATCH_COLS)}) VALUES ({', '.join('?' for _ in MATCH_COLS)})",
        [values[c] for c in MATCH_COLS],
    )


@pytest.fixture()
def tiny_sqlite(tmp_path: Path) -> Path:
    """A synthetic stand-in for database.sqlite: two leagues, three seasons."""
    path = tmp_path / "tiny.sqlite"
    db = sqlite3.connect(path)
    match_ddl = ", ".join(c + (" TEXT" if c in ("season", "date") else " INTEGER") for c in MATCH_COLS)
    db.executescript(
        """
        CREATE TABLE Country (id INTEGER, name TEXT);
        CREATE TABLE League (id INTEGER, country_id INTEGER, name TEXT);
        CREATE TABLE Team (team_api_id INTEGER, team_long_name TEXT, weight NUMERIC);
        CREATE TABLE Team_Attributes (id INTEGER, team_api_id INTEGER);
        CREATE TABLE Player (player_api_id INTEGER, player_name TEXT);
        CREATE TABLE Player_Attributes (
            id INTEGER, player_api_id INTEGER, date TEXT, overall_rating INTEGER,
            potential INTEGER, player_fifa_api_id INTEGER, extra INTEGER,
            finishing INTEGER, sprint_speed INTEGER, reactions INTEGER);
        """
        + f"CREATE TABLE Match ({match_ddl});"
    )
    db.executemany("INSERT INTO Country VALUES (?, ?)", [(1, "Alpha"), (2, "Beta")])
    db.executemany("INSERT INTO League VALUES (?, ?, ?)", [(1, 1, "O'Hara League"), (2, 2, "Other")])
    db.executemany(
        "INSERT INTO Team VALUES (?, ?, ?)",
        [(10, "Ten", 1.5), (11, "Eleven", 2.5), (12, "Twelve", 3.5)],
    )
    db.execute("INSERT INTO Team_Attributes VALUES (1, 10)")
    db.executemany(
        "INSERT INTO Player VALUES (?, ?)",
        [(101, "In League"), (201, "Away A"), (202, "Away B"), (102, "Other League")],
    )
    db.executemany(
        "INSERT INTO Player_Attributes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 101, "2014-10-01 00:00:00", 70, 75, 9, 1, 60, 61, 62),
            (2, 101, "2013-10-01 00:00:00", 60, 65, 9, 1, 50, 51, 52),
            (3, 101, "2016-09-01 00:00:00", 80, 85, 9, 1, 70, 71, 72),
            (4, 102, "2014-10-01 00:00:00", 50, 55, 9, 1, 40, 41, 42),
        ],
    )
    _insert_match(db, 1, 1, "2014/2015", 10, 11)
    _insert_match(db, 2, 1, "2015/2016", 11, 10)
    _insert_match(db, 3, 1, "2013/2014", 10, 12)
    _insert_match(db, 4, 2, "2014/2015", 12, 10)
    db.commit()
    db.close()
    return path

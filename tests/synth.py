"""A seeded synthetic soccer database: 3 leagues, 8 seasons, enough rows to hit every code path.

Same table and column names as the real database, so the notebooks and SQL run on it unchanged.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import duckdb

SEASONS = [f"{y}/{y + 1}" for y in range(2008, 2016)]
LEAGUES = [(1, "Alpha League"), (2, "Beta League"), (3, "Gamma League")]
TEAMS_PER_LEAGUE = 6
MATCHES_PER_LEAGUE_SEASON = 40


def _create_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE TABLE Country (id BIGINT, name VARCHAR)")
    con.execute("CREATE TABLE League (id BIGINT, country_id BIGINT, name VARCHAR)")
    con.execute("CREATE TABLE Team (team_api_id BIGINT, team_long_name VARCHAR)")
    con.execute(
        "CREATE TABLE Match (id BIGINT, country_id BIGINT, league_id BIGINT, season VARCHAR, date VARCHAR, "
        "match_api_id BIGINT, home_team_api_id BIGINT, away_team_api_id BIGINT, home_team_goal BIGINT, "
        "away_team_goal BIGINT)"
    )
    con.execute("CREATE TABLE Player (player_api_id BIGINT, player_name VARCHAR, height DOUBLE, weight DOUBLE)")
    con.execute(
        "CREATE TABLE Player_Attributes (id BIGINT, player_api_id BIGINT, date VARCHAR, overall_rating BIGINT, "
        "potential BIGINT, finishing BIGINT, sprint_speed BIGINT, reactions BIGINT)"
    )


def _add_season(
    con: duckdb.DuckDBPyConnection, rng: random.Random, league_id: int, season: str, teams: list[int], row_id: int
) -> int:
    start = date(int(season[:4]), 8, 1)
    for i in range(MATCHES_PER_LEAGUE_SEASON):
        home, away = rng.sample(teams, 2)
        day = start + timedelta(days=4 * i + rng.randint(0, 2))
        goals = (rng.choice([0, 0, 1, 1, 1, 2, 2, 3, 4]), rng.choice([0, 0, 1, 1, 2, 2, 3]))
        row_id += 1
        con.execute(
            "INSERT INTO Match VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [row_id, league_id, league_id, season, f"{day} 00:00:00", 9000 + row_id, home, away, *goals],
        )
    return row_id


def _add_matches(con: duckdb.DuckDBPyConnection, rng: random.Random) -> None:
    row_id = 0
    for league_id, name in LEAGUES:
        con.execute("INSERT INTO Country VALUES (?, ?)", [league_id, f"Country {league_id}"])
        con.execute("INSERT INTO League VALUES (?, ?, ?)", [league_id, league_id, name])
        teams = [league_id * 100 + t for t in range(TEAMS_PER_LEAGUE)]
        for team in teams:
            con.execute("INSERT INTO Team VALUES (?, ?)", [team, f"Team {team}"])
        for season in SEASONS:
            row_id = _add_season(con, rng, league_id, season, teams, row_id)


def _add_player(con: duckdb.DuckDBPyConnection, rng: random.Random, p: int, attr_id: int) -> int:
    height = 165.0 + rng.randint(0, 30)
    con.execute(
        "INSERT INTO Player VALUES (?, ?, ?, ?)", [p, f"Player {p:02d}", height, height * 0.4 + rng.randint(0, 9)]
    )
    base = rng.randint(45, 85)
    for year in (2010, 2012, 2014, 2016):
        attr_id += 1
        rating = None if (p + year) % 17 == 0 else base + rng.randint(-3, 3)
        con.execute(
            "INSERT INTO Player_Attributes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                attr_id,
                p,
                f"{year}-02-01 00:00:00",
                rating,
                base + rng.randint(0, 8),
                base + rng.randint(-15, 10),
                rng.randint(30, 90),
                base + rng.randint(-8, 8),
            ],
        )
    return attr_id


def synth_connection(seed: int = 5) -> duckdb.DuckDBPyConnection:
    rng = random.Random(seed)
    con = duckdb.connect()
    _create_tables(con)
    _add_matches(con, rng)
    attr_id = 0
    for p in range(1, 61):
        attr_id = _add_player(con, rng, p, attr_id)
    return con

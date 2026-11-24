"""A seeded synthetic database with lineups: 4 leagues, 4 seasons, every column the MVP and Elo code reads.

League 40 is the odd one: two teams whose players all share one rating and rotate through the lineup slots,
so position z-scores have zero spread and position groups tie.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import duckdb

from tests.conftest import MATCH_COLS

SEASONS = ["2008/2009", "2009/2010", "2010/2011", "2011/2012"]
LEAGUES = {10: "Alpha League", 20: "Beta League", 30: "Gamma League", 40: "Delta League"}
SQUAD = 14


def _teams(league: int) -> list[int]:
    return [league * 100 + t for t in range(2 if league == 40 else 6)]


def _lineup(rng: random.Random, team: int, league: int, round_no: int) -> list[int | None]:
    squad = [team * 100 + j for j in range(1, SQUAD + 1)]
    if league == 40:
        return [squad[(slot + round_no) % 12] for slot in range(11)]
    chosen = rng.sample(squad, 11)
    if rng.random() < 0.05:
        chosen[rng.randrange(11)] = None  # type: ignore[call-overload]
    return chosen  # type: ignore[return-value]


def _insert_matches(con: duckdb.DuckDBPyConnection, rows: list[dict[str, object]]) -> None:
    con.executemany(
        f"INSERT INTO Match VALUES ({', '.join('?' for _ in MATCH_COLS)})",
        [[r.get(c) for c in MATCH_COLS] for r in rows],
    )


def _add_rounds(rows: list[dict[str, object]], rng: random.Random, league: int, season: str, match_id: int) -> int:
    start = date(int(season[:4]), 8, 15)
    teams = _teams(league)
    for round_no in range(14):
        day = start + timedelta(days=7 * round_no)
        order = rng.sample(teams, len(teams))
        for i in range(0, len(order), 2):
            home, away = order[i], order[i + 1]
            match_id += 1
            goals: tuple[int | None, int | None] = (rng.choice([0, 1, 1, 2, 3]), rng.choice([0, 0, 1, 2]))
            if match_id % 97 == 0:
                goals = (None, None)  # an unscored match, skipped by every query
            row: dict[str, object] = dict(
                id=match_id,
                country_id=league,
                league_id=league,
                season=season,
                stage=round_no + 1,
                date=f"{day} 00:00:00",
                match_api_id=5000 + match_id,
                home_team_api_id=home,
                away_team_api_id=away,
                home_team_goal=goals[0],
                away_team_goal=goals[1],
            )
            for n, p in enumerate(_lineup(rng, home, league, round_no), start=1):
                row[f"home_player_{n}"] = p
            for n, p in enumerate(_lineup(rng, away, league, round_no), start=1):
                row[f"away_player_{n}"] = p
            rows.append(row)
    return match_id


def _rating(rng: random.Random, league: int, base: int, player: int, season: str, month: int) -> int | None:
    if player % 59 == 0 and season == SEASONS[1] and month == 2:
        return None
    return base + (0 if league == 40 else rng.choice([-5, 0, 0, 5]))


def _player_rows(rng: random.Random, league: int, player: int, first_id: int) -> list[list[object]]:
    """Two dated ratings per season; now and then a second row on the same date (the larger id must win)."""
    base = 70 if league == 40 else rng.choice([60, 65, 70, 70, 75, 80, 85])
    rows: list[list[object]] = []
    attr_id = first_id
    for season in SEASONS:
        for month in (10, 2):
            date_text = f"{int(season[:4]) + (1 if month < 8 else 0)}-{month:02d}-01 00:00:00"
            attr_id += 1
            rows.append([attr_id, player, date_text, _rating(rng, league, base, player, season, month)])
            if month == 2 and attr_id % 11 == 0:
                attr_id += 1
                rows.append([attr_id, player, date_text, base])
    return rows


def _add_players(con: duckdb.DuckDBPyConnection, rng: random.Random) -> None:
    attrs: list[list[object]] = []
    people: list[list[object]] = []
    squad = [(lg, team * 100 + j) for lg in LEAGUES for team in _teams(lg) for j in range(1, SQUAD + 1)]
    for league, player in squad:
        people.extend([[player, f"Player {player}"]] if player % 53 else [])  # a few players have no name row
        attrs.extend(_player_rows(rng, league, player, len(attrs)))
    con.executemany("INSERT INTO Player VALUES (?, ?)", people)
    con.executemany("INSERT INTO Player_Attributes VALUES (?, ?, ?, ?)", attrs)


def league_connection(seed: int = 11) -> duckdb.DuckDBPyConnection:
    rng = random.Random(seed)
    con = duckdb.connect()
    cols = ", ".join(f"{c} {'VARCHAR' if c in ('season', 'date') else 'BIGINT'}" for c in MATCH_COLS)
    con.execute(f"CREATE TABLE Match ({cols})")
    con.execute("CREATE TABLE League (id BIGINT, country_id BIGINT, name VARCHAR)")
    con.execute("CREATE TABLE Team (team_api_id BIGINT, team_long_name VARCHAR)")
    con.execute("CREATE TABLE Player (player_api_id BIGINT, player_name VARCHAR)")
    con.execute("CREATE TABLE Player_Attributes (id BIGINT, player_api_id BIGINT, date VARCHAR, overall_rating DOUBLE)")
    match_id = 0
    rows: list[dict[str, object]] = []
    for league, name in LEAGUES.items():
        con.execute("INSERT INTO League VALUES (?, ?, ?)", [league, league, name])
        for team in _teams(league):
            con.execute("INSERT INTO Team VALUES (?, ?)", [team, f"Team {team}"])
        for season in SEASONS:
            match_id = _add_rounds(rows, rng, league, season, match_id)
    _insert_matches(con, rows)
    _add_players(con, rng)
    return con

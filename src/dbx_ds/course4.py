"""Course 4 and 5 glue: one analysis object, the report card, and the Python tables the SQL parity query reads."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import astuple, dataclass, fields

import duckdb

from dbx_ds import elo, eloplus, mvp, mvpplus, report, sqldemo

PREMIER_LEAGUE = "England Premier League"
GRID_KS = (5.0, 10.0, 20.0, 30.0, 40.0, 60.0)
GRID_BONUSES = (0.0, 50.0, 100.0, 150.0)
SWEEP_WEIGHTS = (0.9, 0.8, 0.7, 0.6, 0.5)
SWEEP_STARTS = (10, 20, 25)


@dataclass(frozen=True)
class Analysis:
    """Everything the course 4 cells need, computed once."""

    games: list[eloplus.Game]
    ratings: dict[tuple[str, int], float]
    names: dict[int, str]
    teams: dict[int, str]
    scores: list[mvpplus.PlusScore]
    player_ratings: dict[tuple[str, int], float]


def league_id(con: duckdb.DuckDBPyConnection, name: str = PREMIER_LEAGUE) -> int:
    """Id of a league by name."""
    (row,) = con.execute("SELECT id FROM League WHERE name = ?", [name]).fetchone() or (None,)
    if row is None:
        raise KeyError(f"no league called {name!r}")
    return int(row)


def analyse(con: duckdb.DuckDBPyConnection) -> Analysis:
    """Load matches and players once; run the Elo replay and the league-by-league MVP scoring."""
    games = eloplus.load_games(con)
    ratings = eloplus.replay(g.result for g in games).ratings
    attrs = con.execute(
        "SELECT player_api_id, date, id, overall_rating FROM Player_Attributes "
        "WHERE overall_rating IS NOT NULL AND date IS NOT NULL"
    ).fetchall()
    player_ratings = mvp.latest_ratings(attrs)
    names = dict(con.execute("SELECT player_api_id, player_name FROM Player").fetchall())
    teams = dict(con.execute("SELECT team_api_id, team_long_name FROM Team").fetchall())
    scores = mvpplus.score_leagues(games, player_ratings, names)
    return Analysis(games, ratings, names, teams, scores, player_ratings)


def elo_lines(a: Analysis, league: int, season: str, top: int = 5) -> list[str]:
    """The Elo top teams of one league-season, as text lines."""
    rows = eloplus.elo_table(a.games, a.ratings, league, season)[:top]
    return [f"{i}. {a.teams[team]}  {rating:.1f}" for i, (_, _, team, rating) in enumerate(rows, start=1)]


def current_top(a: Analysis, n: int = 5) -> list[tuple[int, str, float]]:
    """(place, team, rating) of the current Elo table over every league: each team at its latest season.

    SQL twin: the "all leagues together" query in sql/demo_elo.sql.
    """
    table = elo.current_table(a.ratings)[:n]
    return [(i, a.teams[team], round(rating, 1)) for i, (team, rating) in enumerate(table, start=1)]


def current_lines(a: Analysis, n: int = 5) -> list[str]:
    """current_top as text lines."""
    return [f"{i}. {team}  {rating}" for i, team, rating in current_top(a, n)]


def card_lines(a: Analysis, league: int, season: str, n: int = 5) -> list[str]:
    """MVP card plus the n-name shortlist (biggest gap first), as text lines."""
    mvps = mvpplus.mvp_per_season(a.scores, league)
    card = next(s for s in mvps if s.season == season)
    lines = [f"MVP: {card.player_name} ({card.position}, {a.teams[card.team_api_id]}) score {card.score:.2f}"]
    for i, s in enumerate(mvpplus.shortlist_by_gap(a.scores, league, season, n), start=1):
        lines.append(f"{i}. {s.player_name}  score rank {s.score_rank}, rating rank {s.rating_rank}, gap {s.gap}")
    return lines


def print_report(a: Analysis, league: int, season: str) -> None:
    """3.1.4: the Elo top teams, the MVP card and the five-name shortlist, in one cell."""
    print(f"Elo top teams, {season}")
    print("\n".join(elo_lines(a, league, season)))
    print()
    print(f"MVP and shortlist, {season}")
    print("\n".join(card_lines(a, league, season)))


def print_table(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    """Print a text table (thin wrapper so notebook cells stay short)."""
    print("\n".join(report.table_lines(columns, rows)))


def python_elo_rows(a: Analysis) -> list[tuple[str, int, int, float]]:
    """(season, league, team, rating) for every team-season, sorted: the Python twin of elo_season."""
    rows = eloplus.elo_table(a.games, a.ratings)
    return sorted(((s, lg, t, r) for s, lg, t, r in rows), key=lambda r: (r[0], r[2]))


def register_python_tables(con: duckdb.DuckDBPyConnection, a: Analysis) -> None:
    """Create py_elo and py_mvp so sql/demo_parity.sql can full-join them to the SQL views."""
    con.execute("CREATE OR REPLACE TABLE py_elo (season VARCHAR, league_id BIGINT, team_api_id BIGINT, rating DOUBLE)")
    con.executemany("INSERT INTO py_elo VALUES (?, ?, ?, ?)", python_elo_rows(a))
    cols = [f.name for f in fields(mvpplus.PlusScore)]
    ddl = {
        "season": "VARCHAR",
        "player_name": "VARCHAR",
        "position": "VARCHAR",
        "is_mvp": "BOOLEAN",
        "is_adjacent": "BOOLEAN",
    }
    con.execute(
        "CREATE OR REPLACE TABLE py_mvp ("
        + ", ".join(
            f"{c} {ddl.get(c, 'BIGINT' if c.endswith(('_id', 'rank', 'appearances')) else 'DOUBLE')}" for c in cols
        )
        + ")"
    )
    con.executemany(f"INSERT INTO py_mvp VALUES ({', '.join('?' for _ in cols)})", [astuple(s) for s in a.scores])


def parity_differences(con: duckdb.DuckDBPyConnection) -> list[int]:
    """Run sql/demo_parity.sql; each number is a count of differing rows and must be 0."""
    return [int(con.execute(sql).fetchone()[0]) for _, sql in sqldemo.load("demo_parity.sql")]  # type: ignore[index]


def create_views(con: duckdb.DuckDBPyConnection) -> int:
    """Run sql/c5_views.sql; returns how many views were created."""
    statements = sqldemo.load("c5_views.sql")
    for _, sql in statements:
        con.execute(sql)
    return len(statements)

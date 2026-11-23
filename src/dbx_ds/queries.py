"""Run the Python and SQL versions of Elo and MVP against a DuckDB connection."""

from __future__ import annotations

from pathlib import Path

import duckdb

from dbx_ds import elo, mvp

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def load_results(con: duckdb.DuckDBPyConnection) -> list[elo.Result]:
    rows = con.execute(
        "SELECT match_api_id, season, date, home_team_api_id, away_team_api_id, "
        "home_team_goal, away_team_goal FROM Match"
    ).fetchall()
    return [elo.Result(*row) for row in rows]


def python_elo(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, float]]:
    """Season-end ratings from the Python code, sorted by season then team."""
    ratings = elo.season_ratings(load_results(con))
    return [(season, team, rating) for (season, team), rating in sorted(ratings.items())]


def sql_elo(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, float]]:
    """Season-end ratings from sql/elo.sql."""
    rows = con.execute((SQL_DIR / "elo.sql").read_text()).fetchall()
    return [(str(s), int(t), float(r)) for s, t, r in rows]


def python_mvp(con: duckdb.DuckDBPyConnection) -> list[mvp.PlayerScore]:
    attrs = con.execute(
        "SELECT player_api_id, date, id, overall_rating FROM Player_Attributes WHERE overall_rating IS NOT NULL"
    ).fetchall()
    lineup_cols = [f"{s}_player_{i}" for s in ("home", "away") for i in range(1, 12)]
    matches = con.execute(
        "SELECT season, home_team_goal, away_team_goal, " + ", ".join(lineup_cols) + " FROM Match"
    ).fetchall()
    shaped = [(m[0], m[1], m[2], m[3:14], m[14:25]) for m in matches]
    names = dict(con.execute("SELECT player_api_id, player_name FROM Player").fetchall())
    return mvp.score_players(mvp.latest_ratings(attrs), mvp.involvement(shaped), names)


def sql_mvp(con: duckdb.DuckDBPyConnection) -> list[mvp.PlayerScore]:
    """The same table from sql/mvp.sql."""
    rows = con.execute((SQL_DIR / "mvp.sql").read_text()).fetchall()
    return [mvp.PlayerScore(*row) for row in rows]

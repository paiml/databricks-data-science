"""Typed readers over the DuckDB views from `data.connect`, shared by the course 1 to 3 demos."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb


@dataclass(frozen=True)
class MatchRow:
    """One finished match with its league name, ordered for replay by (date, match_api_id)."""

    match_api_id: int
    season: str
    date: str
    league: str
    home: int
    away: int
    home_goals: int
    away_goals: int


def load_matches(con: duckdb.DuckDBPyConnection) -> list[MatchRow]:
    """Every match with both goal counts, oldest first."""
    rows = con.execute(
        "SELECT m.match_api_id, m.season, CAST(m.date AS VARCHAR), l.name, m.home_team_api_id, "
        "m.away_team_api_id, m.home_team_goal, m.away_team_goal "
        "FROM Match m JOIN League l ON m.league_id = l.id "
        "WHERE m.home_team_goal IS NOT NULL AND m.away_team_goal IS NOT NULL "
        "ORDER BY m.date, m.match_api_id"
    ).fetchall()
    return [MatchRow(*row) for row in rows]


def column(con: duckdb.DuckDBPyConnection, sql: str) -> list[float]:
    """First column of a query as a list, dropping NULLs."""
    return [row[0] for row in con.execute(sql).fetchall() if row[0] is not None]

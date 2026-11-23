"""Elo team ranking from match results.

Every team starts at INITIAL_RATING. Matches are replayed in order of date, then
match_api_id, so the answer never depends on input order. The home side gets
HOME_ADVANTAGE extra points when we work out who was expected to win. A win scores
1.0, a draw 0.5, a loss 0.0. The rating moves by K_FACTOR times (actual - expected).
Ratings carry over from one season to the next.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

INITIAL_RATING = 1500.0
K_FACTOR = 20.0
HOME_ADVANTAGE = 100.0
SCALE = 400.0


@dataclass(frozen=True)
class Result:
    """One finished match."""

    match_api_id: int
    season: str
    date: str
    home: int
    away: int
    home_goals: int
    away_goals: int


def expected_home(home_rating: float, away_rating: float) -> float:
    """Chance (0..1) that the home side scores a win, draws counting half."""
    gap = away_rating - (home_rating + HOME_ADVANTAGE)
    return float(1.0 / (1.0 + 10.0 ** (gap / SCALE)))


def actual_home(home_goals: int, away_goals: int) -> float:
    """1.0 for a home win, 0.5 for a draw, 0.0 for an away win."""
    if home_goals > away_goals:
        return 1.0
    if home_goals == away_goals:
        return 0.5
    return 0.0


def season_ratings(results: Iterable[Result]) -> dict[tuple[str, int], float]:
    """End-of-season rating for every (season, team) that played."""
    ratings: dict[int, float] = {}
    out: dict[tuple[str, int], float] = {}
    for r in sorted(results, key=lambda m: (m.date, m.match_api_id)):
        home = ratings.get(r.home, INITIAL_RATING)
        away = ratings.get(r.away, INITIAL_RATING)
        delta = K_FACTOR * (actual_home(r.home_goals, r.away_goals) - expected_home(home, away))
        ratings[r.home] = home + delta
        ratings[r.away] = away - delta
        out[(r.season, r.home)] = ratings[r.home]
        out[(r.season, r.away)] = ratings[r.away]
    return out


def current_table(by_season: dict[tuple[str, int], float]) -> list[tuple[int, float]]:
    """Latest rating per team, best first (ties broken by team id)."""
    latest: dict[int, tuple[str, float]] = {}
    for (season, team), rating in by_season.items():
        if team not in latest or season >= latest[team][0]:
            latest[team] = (season, rating)
    table = [(team, rating) for team, (_, rating) in latest.items()]
    return sorted(table, key=lambda row: (-row[1], row[0]))

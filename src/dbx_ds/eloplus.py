"""Course 4 Elo extras: tuning, home advantage, standings check, league and season filters.

Everything here reuses the rules of elo.py (initial 1500, scale 400, draws count half, replay by
date then match_api_id). The only new thing is that K and the home bonus are arguments, so a
tuning loop can try many values. With the default arguments replay() gives exactly
elo.season_ratings(); tests/test_eloplus.py checks that, and checks the SQL twins in
sql/elo_dbx.sql and sql/c5_views.sql against these functions.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import duckdb

from dbx_ds import elo

Slots = tuple[int | None, ...]


@dataclass(frozen=True)
class Game:
    """One finished match with its league and the two starting elevens (11 slots each)."""

    result: elo.Result
    league_id: int
    home_xi: Slots
    away_xi: Slots


@dataclass(frozen=True)
class Prematch:
    """What the ratings said before a match was played."""

    match_api_id: int
    home_rating: float
    away_rating: float
    expected_home: float
    actual_home: float


@dataclass(frozen=True)
class Replay:
    """Season-end ratings and the pre-match forecast of every match."""

    ratings: dict[tuple[str, int], float]
    prematch: list[Prematch]


@dataclass(frozen=True)
class HomeStats:
    """Home / draw / away shares (percent) and mean goals per side."""

    home_pct: float
    draw_pct: float
    away_pct: float
    home_goals: float
    away_goals: float


@dataclass(frozen=True)
class Tuned:
    """Mean squared forecast error for one (K, home bonus) pair."""

    k_factor: float
    home_advantage: float
    mse: float


@dataclass(frozen=True)
class StandingRow:
    """One team in a league-season: points table position against Elo position."""

    team_api_id: int
    points: int
    goal_difference: int
    elo: float
    points_rank: int
    elo_rank: int


def load_games(con: duckdb.DuckDBPyConnection) -> list[Game]:
    """Every scored match with league and lineups. Unscored matches are skipped, as in queries.py."""
    lineup = [f"{side}_player_{i}" for side in ("home", "away") for i in range(1, 12)]
    rows = con.execute(
        "SELECT match_api_id, season, date, home_team_api_id, away_team_api_id, home_team_goal, away_team_goal, "
        "league_id, " + ", ".join(lineup) + " FROM Match "
        "WHERE home_team_goal IS NOT NULL AND away_team_goal IS NOT NULL"
    ).fetchall()
    return [Game(elo.Result(*r[:7]), r[7], tuple(r[8:19]), tuple(r[19:30])) for r in rows]


def replay(
    results: Iterable[elo.Result],
    k_factor: float = elo.K_FACTOR,
    home_advantage: float = elo.HOME_ADVANTAGE,
) -> Replay:
    """Replay every match once, keeping season-end ratings and each match's pre-match forecast."""
    ratings: dict[int, float] = {}
    out: dict[tuple[str, int], float] = {}
    prematch: list[Prematch] = []
    for r in sorted(results, key=lambda m: (m.date, m.match_api_id)):
        home = ratings.get(r.home, elo.INITIAL_RATING)
        away = ratings.get(r.away, elo.INITIAL_RATING)
        expected = float(1.0 / (1.0 + 10.0 ** ((away - (home + home_advantage)) / elo.SCALE)))
        actual = elo.actual_home(r.home_goals, r.away_goals)
        prematch.append(Prematch(r.match_api_id, home, away, expected, actual))
        delta = k_factor * (actual - expected)
        ratings[r.home] = home + delta
        ratings[r.away] = away - delta
        out[(r.season, r.home)] = ratings[r.home]
        out[(r.season, r.away)] = ratings[r.away]
    return Replay(out, prematch)


def mean_squared_error(prematch: Sequence[Prematch]) -> float:
    """Mean of (forecast - actual)^2 over every match; lower is a better forecast."""
    return sum((p.expected_home - p.actual_home) ** 2 for p in prematch) / len(prematch)


def tune(results: Sequence[elo.Result], ks: Sequence[float], bonuses: Sequence[float]) -> list[Tuned]:
    """Try every (K, home bonus) pair, in grid order (K outer, bonus inner)."""
    return [Tuned(k, bonus, mean_squared_error(replay(results, k, bonus).prematch)) for k in ks for bonus in bonuses]


def best(tuned: Sequence[Tuned]) -> Tuned:
    """The pair with the lowest error (ties: the first in grid order)."""
    return min(tuned, key=lambda t: t.mse)


def home_stats(results: Iterable[elo.Result]) -> HomeStats:
    """Home advantage in one line: result shares and goals per side."""
    rows = list(results)
    n = len(rows)
    wins = sum(r.home_goals > r.away_goals for r in rows)
    draws = sum(r.home_goals == r.away_goals for r in rows)
    return HomeStats(
        100.0 * wins / n,
        100.0 * draws / n,
        100.0 * (n - wins - draws) / n,
        sum(r.home_goals for r in rows) / n,
        sum(r.away_goals for r in rows) / n,
    )


def team_leagues(games: Iterable[Game]) -> dict[tuple[str, int], int]:
    """League of every (season, team) that played."""
    out: dict[tuple[str, int], int] = {}
    for g in games:
        out[(g.result.season, g.result.home)] = g.league_id
        out[(g.result.season, g.result.away)] = g.league_id
    return out


def elo_table(
    games: Sequence[Game],
    ratings: dict[tuple[str, int], float],
    league_id: int | None = None,
    season: str | None = None,
) -> list[tuple[str, int, int, float]]:
    """(season, league, team, rating), best first inside each season, filtered by league and/or season.

    The replay itself always runs over every league, because a rating carries over between seasons;
    the filter only picks which rows to show.
    """
    leagues = team_leagues(games)
    rows = [
        (s, leagues[(s, t)], t, rating)
        for (s, t), rating in ratings.items()
        if (league_id is None or leagues[(s, t)] == league_id) and (season is None or s == season)
    ]
    return sorted(rows, key=lambda r: (r[0], -r[3], r[2]))


def points_table(results: Iterable[elo.Result]) -> list[tuple[int, int, int, int]]:
    """(team, points, goal difference, goals for), league order: points, goal difference, goals for, team id."""
    acc: dict[int, list[int]] = {}
    for r in results:
        for team, own, other in ((r.home, r.home_goals, r.away_goals), (r.away, r.away_goals, r.home_goals)):
            row = acc.setdefault(team, [0, 0, 0])
            row[0] += 3 if own > other else 1 if own == other else 0
            row[1] += own - other
            row[2] += own
    table = [(team, p, gd, gf) for team, (p, gd, gf) in acc.items()]
    return sorted(table, key=lambda t: (-t[1], -t[2], -t[3], t[0]))


def spearman(ranks_a: Sequence[int], ranks_b: Sequence[int]) -> float:
    """Spearman rank correlation of two strict rankings of the same n items: 1 - 6 sum(d^2) / (n (n^2 - 1))."""
    n = len(ranks_a)
    d2 = sum((a - b) ** 2 for a, b in zip(ranks_a, ranks_b, strict=True))
    return 1.0 - 6.0 * d2 / (n * (n * n - 1))


def standings_check(
    games: Sequence[Game], ratings: dict[tuple[str, int], float], league_id: int, season: str
) -> tuple[list[StandingRow], float]:
    """Points table of one league-season against the season-end Elo table, and their Spearman correlation."""
    chosen = [g.result for g in games if g.league_id == league_id and g.result.season == season]
    table = points_table(chosen)
    by_elo = sorted(((t[0], ratings[(season, t[0])]) for t in table), key=lambda x: (-x[1], x[0]))
    elo_rank = {team: i for i, (team, _) in enumerate(by_elo, start=1)}
    rows = [
        StandingRow(team, pts, gd, ratings[(season, team)], i, elo_rank[team])
        for i, (team, pts, gd, _) in enumerate(table, start=1)
    ]
    return rows, spearman([r.points_rank for r in rows], [r.elo_rank for r in rows])

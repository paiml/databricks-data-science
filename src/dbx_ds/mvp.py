"""MVP and "MVP-adjacent" scoring.

Score = QUALITY_WEIGHT * rating + IMPACT_WEIGHT * win_share, per player per season, rounded
half-up to SCORE_DECIMALS by round_score() so floating-point dust never decides a tie. The SQL
uses the same rule (floor(x * 10^6 + 0.5) / 10^6), so Python and SQL round identically.

* rating: the player's newest overall_rating (0-100) inside the season.
* win_share: points the team won while the player started, as a percent of the
  most it could have won (3 per match). 100 means the team won every match.
* Only players who started at least MIN_APPEARANCES matches are scored.

MVP: rank 1 on score in the season (score ties go to the lower player_api_id).
MVP-adjacent: in the top TOP_SCORE_RANK on score, not the MVP, and either under-rated
(the overall_rating rank is at least RANK_GAP places worse than the score rank; equal
ratings share a rank, like SQL RANK()) or a
part-timer (at most FEW_APPEARANCES starts). High value, quietly so.

A season runs 1 August to 31 July, the same as the Match.season labels.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

QUALITY_WEIGHT = 0.7
IMPACT_WEIGHT = 0.3
MIN_APPEARANCES = 10
FEW_APPEARANCES = 15
TOP_SCORE_RANK = 20
RANK_GAP = 10
SEASON_START_MONTH = 8
SCORE_DECIMALS = 6


@dataclass(frozen=True)
class PlayerScore:
    """One scored player-season."""

    season: str
    player_api_id: int
    player_name: str
    overall_rating: float
    appearances: int
    win_share: float
    score: float
    score_rank: int
    rating_rank: int
    is_mvp: bool
    is_adjacent: bool


def season_of(date: str) -> str:
    """Season label for a 'YYYY-MM-DD ...' string, e.g. 2015-09-21 -> 2015/2016."""
    year = int(date[0:4])
    month = int(date[5:7])
    if month >= SEASON_START_MONTH:
        return f"{year}/{year + 1}"
    return f"{year - 1}/{year}"


def latest_ratings(
    rows: Iterable[tuple[int, str, int, float]],
) -> dict[tuple[str, int], float]:
    """Newest overall_rating per (season, player). Rows: (player, date, row id, rating)."""
    newest: dict[tuple[str, int], tuple[str, int, float]] = {}
    for player, date, row_id, rating in rows:
        key = (season_of(date), player)
        if key not in newest or (date, row_id) > newest[key][:2]:
            newest[key] = (date, row_id, rating)
    return {key: value[2] for key, value in newest.items()}


def round_score(value: float) -> float:
    """Round half up to SCORE_DECIMALS. One rule, mirrored in sql/mvp.sql."""
    factor = 10.0**SCORE_DECIMALS
    return math.floor(value * factor + 0.5) / factor


def points(own_goals: int, other_goals: int) -> int:
    """League points for one side: 3 win, 1 draw, 0 loss."""
    if own_goals > other_goals:
        return 3
    if own_goals == other_goals:
        return 1
    return 0


def involvement(
    matches: Iterable[tuple[str, int, int, Sequence[int | None], Sequence[int | None]]],
) -> dict[tuple[str, int], tuple[int, int]]:
    """(starts, points) per (season, player). Rows: (season, home goals, away goals, home XI, away XI)."""
    out: dict[tuple[str, int], tuple[int, int]] = {}
    for season, home_goals, away_goals, home_xi, away_xi in matches:
        for xi, pts in (
            (home_xi, points(home_goals, away_goals)),
            (away_xi, points(away_goals, home_goals)),
        ):
            for player in xi:
                if player is None:
                    continue
                starts, total = out.get((season, player), (0, 0))
                out[(season, player)] = (starts + 1, total + pts)
    return out


Row = tuple[int, float, int, float, float]  # player, rating, starts, win_share, score


def _qualified(
    ratings: dict[tuple[str, int], float],
    played: dict[tuple[str, int], tuple[int, int]],
    names: dict[int, str],
) -> dict[str, list[Row]]:
    """Group the players who rated, started enough matches and have a name by season."""
    by_season: dict[str, list[Row]] = {}
    for (season, player), rating in ratings.items():
        if (season, player) not in played or player not in names:
            continue
        starts, pts = played[(season, player)]
        if starts < MIN_APPEARANCES:
            continue
        win_share = 100.0 * pts / (3.0 * starts)
        score = round_score(QUALITY_WEIGHT * rating + IMPACT_WEIGHT * win_share)
        by_season.setdefault(season, []).append((player, rating, starts, win_share, score))
    return by_season


def _is_adjacent(score_rank: int, rating_rank: int, starts: int) -> bool:
    """High value, quietly so: see the module docstring."""
    if score_rank == 1 or score_rank > TOP_SCORE_RANK:
        return False
    return rating_rank - score_rank >= RANK_GAP or starts <= FEW_APPEARANCES


def _rank_season(season: str, rows: list[Row], names: dict[int, str]) -> list[PlayerScore]:
    by_score = sorted(rows, key=lambda r: (-r[4], r[0]))
    by_rating = sorted(rows, key=lambda r: (-r[1], r[0]))
    rating_rank: dict[int, int] = {}
    for i, r in enumerate(by_rating, start=1):
        # RANK(): players on equal ratings share the first position of their group.
        same_as_previous = i > 1 and r[1] == by_rating[i - 2][1]
        rating_rank[r[0]] = rating_rank[by_rating[i - 2][0]] if same_as_previous else i
    return [
        PlayerScore(
            season,
            player,
            names[player],
            rating,
            starts,
            win_share,
            score,
            rank,
            rating_rank[player],
            rank == 1,
            _is_adjacent(rank, rating_rank[player], starts),
        )
        for rank, (player, rating, starts, win_share, score) in enumerate(by_score, start=1)
    ]


def score_players(
    ratings: dict[tuple[str, int], float],
    played: dict[tuple[str, int], tuple[int, int]],
    names: dict[int, str],
) -> list[PlayerScore]:
    """Score, rank and flag every qualified player, ordered by season then score rank."""
    by_season = _qualified(ratings, played, names)
    out: list[PlayerScore] = []
    for season in sorted(by_season):
        out.extend(_rank_season(season, by_season[season], names))
    return out

"""Course 4 MVP extras: per-league tables, position z-scores, Elo-adjusted win share, sweeps, shortlists.

Built on mvp.py (scoring rules, rounding, ranks) and eloplus.py (pre-match Elo forecasts). Decisions,
all flagged in the README:

* League filter: players are ranked inside their (league, season), using only matches of that league.
  A rating is the player's newest overall_rating in the season, whatever the league.
* Position: the database has no position column, so a start in lineup slot 1 counts as GK, 2-5 DEF,
  6-8 MID, 9-11 FWD. A player-season takes the group he started in most (ties: GK, DEF, MID, FWD order).
  z_rating = (rating - mean) / population stddev over the qualified players of the same league,
  season and position (0 when every one has the same rating).
* Elo-adjusted win share = 50 + 100 * mean(actual - expected) over the player's starts, where actual is
  the team's score in the match (1, 0.5, 0) and expected is the team's pre-match Elo forecast (home side
  with the home bonus). 50 means "did exactly as well as Elo expected".
* score_adj uses adj_win_share in place of win_share; score_z uses 50 + 10 * z_rating in place of rating.
  Both keep the 0.7 / 0.3 weights and the half-up rounding of mvp.round_score().
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from dbx_ds import elo, eloplus, mvp

POSITIONS = ("GK", "DEF", "MID", "FWD")
Z_SCALE = 10.0
Z_CENTRE = 50.0
ADJ_CENTRE = 50.0


@dataclass(frozen=True)
class Start:
    """One player starting one match."""

    league_id: int
    season: str
    team: int
    slot: int
    player: int
    points: int
    actual: float
    expected: float


@dataclass(frozen=True)
class PlusScore:
    """mvp.PlayerScore plus league, team, position and the two adjusted views of the same season."""

    season: str
    league_id: int
    player_api_id: int
    player_name: str
    team_api_id: int
    position: str
    overall_rating: float
    appearances: int
    win_share: float
    adj_win_share: float
    z_rating: float
    score: float
    score_rank: int
    rating_rank: int
    is_mvp: bool
    is_adjacent: bool
    score_adj: float
    adj_rank: int
    score_z: float
    z_rank: int

    @property
    def gap(self) -> int:
        """rating_rank minus score_rank: how far under-rated the player is (positive) or over-rated (negative)."""
        return self.rating_rank - self.score_rank


@dataclass(frozen=True)
class Setting:
    """One cell of the weight / minimum-starts sweep."""

    quality_weight: float
    min_starts: int
    mvps: dict[str, int]
    changed: int


_SLOT_POSITION = {1: "GK", **dict.fromkeys(range(2, 6), "DEF"), **dict.fromkeys(range(6, 9), "MID")} | dict.fromkeys(
    range(9, 12), "FWD"
)


def position_of(slot: int) -> str:
    """Lineup slot to position group: 1 GK, 2-5 DEF, 6-8 MID, 9-11 FWD."""
    return _SLOT_POSITION[slot]


def _sides(g: eloplus.Game, e_home: float) -> tuple[tuple[int, eloplus.Slots, int, float, float], ...]:
    r = g.result
    actual = elo.actual_home(r.home_goals, r.away_goals)
    return (
        (r.home, g.home_xi, mvp.points(r.home_goals, r.away_goals), actual, e_home),
        (r.away, g.away_xi, mvp.points(r.away_goals, r.home_goals), 1.0 - actual, 1.0 - e_home),
    )


def _side_starts(g: eloplus.Game, side: tuple[int, eloplus.Slots, int, float, float]) -> list[Start]:
    team, xi, pts, actual, expected = side
    starts = [(slot, player) for slot, player in enumerate(xi, start=1) if player is not None]
    return [Start(g.league_id, g.result.season, team, slot, player, pts, actual, expected) for slot, player in starts]


def build_starts(games: Sequence[eloplus.Game]) -> list[Start]:
    """Every start in every scored match, with the team's pre-match Elo forecast."""
    forecast = {p.match_api_id: p.expected_home for p in eloplus.replay(g.result for g in games).prematch}
    out: list[Start] = []
    for g in games:
        for side in _sides(g, forecast[g.result.match_api_id]):
            out.extend(_side_starts(g, side))
    return out


Key = tuple[int, str, int]
Ratings = dict[tuple[str, int], float]
Names = dict[int, str]
Games = Sequence[eloplus.Game]
Floats = Sequence[float]
Ints = Sequence[int]
Scores = Sequence[PlusScore]
TopRow = tuple[PlusScore, float, int]


@dataclass
class _Tally:
    starts: int = 0
    points: int = 0
    surplus: float = 0.0


def _tally(starts: Sequence[Start]) -> tuple[dict[Key, _Tally], dict[Key, Counter[int]], dict[Key, Counter[str]]]:
    tallies: dict[tuple[int, str, int], _Tally] = {}
    teams: dict[tuple[int, str, int], Counter[int]] = {}
    groups: dict[tuple[int, str, int], Counter[str]] = {}
    for s in starts:
        key = (s.league_id, s.season, s.player)
        t = tallies.setdefault(key, _Tally())
        t.starts += 1
        t.points += s.points
        t.surplus += s.actual - s.expected
        teams.setdefault(key, Counter())[s.team] += 1
        groups.setdefault(key, Counter())[position_of(s.slot)] += 1
    return tallies, teams, groups


def _modal_team(counter: Counter[int]) -> int:
    return min(counter, key=lambda team: (-counter[team], team))


def _modal_position(counter: Counter[str]) -> str:
    return min(counter, key=lambda pos: (-counter[pos], POSITIONS.index(pos)))


def _group_z(members: list[mvp.PlayerScore]) -> dict[int, float]:
    ratings = [m.overall_rating for m in members]
    mean, spread = statistics.fmean(ratings), statistics.pstdev(ratings)
    return {m.player_api_id: 0.0 if spread == 0 else (m.overall_rating - mean) / spread for m in members}


def _z_by_position(rows: list[mvp.PlayerScore], positions: dict[int, str]) -> dict[int, float]:
    by_pos: dict[str, list[mvp.PlayerScore]] = {}
    for row in rows:
        by_pos.setdefault(positions[row.player_api_id], []).append(row)
    return {pid: z for members in by_pos.values() for pid, z in _group_z(members).items()}


def _ranked(values: dict[int, float]) -> dict[int, int]:
    order = sorted(values, key=lambda p: (-values[p], p))
    return {player: i for i, player in enumerate(order, start=1)}


def _season_scores(
    league: int,
    season: str,
    rows: list[mvp.PlayerScore],
    tallies: dict[Key, _Tally],
    teams: dict[Key, Counter[int]],
    groups: dict[Key, Counter[str]],
) -> list[PlusScore]:
    positions = {r.player_api_id: _modal_position(groups[(league, season, r.player_api_id)]) for r in rows}
    z = _z_by_position(rows, positions)
    adj = {
        r.player_api_id: ADJ_CENTRE + 100.0 * tallies[(league, season, r.player_api_id)].surplus / r.appearances
        for r in rows
    }
    quality, impact = mvp.QUALITY_WEIGHT, mvp.IMPACT_WEIGHT
    score_adj = {
        r.player_api_id: mvp.round_score(quality * r.overall_rating + impact * adj[r.player_api_id]) for r in rows
    }
    score_z = {
        r.player_api_id: mvp.round_score(quality * (Z_CENTRE + Z_SCALE * z[r.player_api_id]) + impact * r.win_share)
        for r in rows
    }
    adj_rank, z_rank = _ranked(score_adj), _ranked(score_z)
    return [
        PlusScore(
            season,
            league,
            r.player_api_id,
            r.player_name,
            _modal_team(teams[(league, season, r.player_api_id)]),
            positions[r.player_api_id],
            r.overall_rating,
            r.appearances,
            r.win_share,
            adj[r.player_api_id],
            z[r.player_api_id],
            r.score,
            r.score_rank,
            r.rating_rank,
            r.is_mvp,
            r.is_adjacent,
            score_adj[r.player_api_id],
            adj_rank[r.player_api_id],
            score_z[r.player_api_id],
            z_rank[r.player_api_id],
        )
        for r in rows
    ]


def score_leagues(games: Sequence[eloplus.Game], ratings: Ratings, names: Names) -> list[PlusScore]:
    """Every qualified player-season, ranked inside its league-season, ordered by league, season, score rank."""
    tallies, teams, groups = _tally(build_starts(games))
    out: list[PlusScore] = []
    for league in sorted({k[0] for k in tallies}):
        played = {(s, p): (t.starts, t.points) for (lg, s, p), t in tallies.items() if lg == league}
        base = mvp.score_players(ratings, played, names)
        for season in sorted({row.season for row in base}):
            rows = [row for row in base if row.season == season]
            out.extend(_season_scores(league, season, rows, tallies, teams, groups))
    return out


def qualified_counts(scores: Sequence[PlusScore]) -> list[tuple[str, int]]:
    """Qualified players per season (all leagues together)."""
    counts = Counter(s.season for s in scores)
    return sorted(counts.items())


def mvp_per_season(scores: Sequence[PlusScore], league_id: int | None = None) -> list[PlusScore]:
    """The rank-1 player of every season (of every league, or of one league)."""
    return [s for s in scores if s.is_mvp and (league_id is None or s.league_id == league_id)]


def shortlist(scores: Sequence[PlusScore], league_id: int, season: str) -> list[PlusScore]:
    """The 'MVP-adjacent' names of one league-season, best score first (each carries .gap)."""
    rows = [s for s in scores if s.league_id == league_id and s.season == season and s.is_adjacent]
    return sorted(rows, key=lambda s: s.score_rank)


def shortlist_by_gap(scores: Sequence[PlusScore], league_id: int, season: str, n: int = 5) -> list[PlusScore]:
    """Capstone alternative: the n adjacent players with the biggest gap (ties: better score rank)."""
    return sorted(shortlist(scores, league_id, season), key=lambda s: (-s.gap, s.score_rank))[:n]


def top_with_team_elo(scores: Scores, ratings: Ratings, league_id: int, season: str, n: int = 6) -> list[TopRow]:
    """Top n by score with their team's season-end Elo and that Elo's rank inside the league-season."""
    in_league = {s.team_api_id for s in scores if s.league_id == league_id and s.season == season}
    table = sorted(
        ((team, ratings[(season, team)]) for team in in_league if (season, team) in ratings),
        key=lambda x: (-x[1], x[0]),
    )
    rank = {team: i for i, (team, _) in enumerate(table, start=1)}
    top = [s for s in scores if s.league_id == league_id and s.season == season and s.score_rank <= n]
    return [(s, ratings[(season, s.team_api_id)], rank[s.team_api_id]) for s in sorted(top, key=lambda s: s.score_rank)]


def _score_at(t: _Tally, quality: float, rating: float) -> float:
    return mvp.round_score(quality * rating + (1.0 - quality) * 100.0 * t.points / (3.0 * t.starts))


def _winners(
    tallies: dict[Key, _Tally], ratings: Ratings, names: Names, quality: float, minimum: int
) -> dict[str, int]:
    """The best player of every season under one setting (score desc, then player id), as season -> player."""
    best: dict[str, tuple[float, int]] = {}
    for (_, season, player), t in tallies.items():
        if t.starts < minimum or player not in names or (season, player) not in ratings:
            continue
        entry = (-_score_at(t, quality, ratings[(season, player)]), player)
        best[season] = min(best.get(season, entry), entry)
    return {season: v[1] for season, v in sorted(best.items())}


def sweep(games: Games, ratings: Ratings, names: Names, league_id: int, weights: Floats, starts: Ints) -> list[Setting]:
    """MVP of every season of one league under each weight and minimum-starts setting.

    `changed` counts the seasons whose MVP differs from the baseline setting (0.7 / 0.3, 10 starts); a season with
    no qualified player under a setting is not counted (the SQL join drops it the same way).
    """
    tallies, _, _ = _tally([s for s in build_starts(games) if s.league_id == league_id])
    baseline = _winners(tallies, ratings, names, mvp.QUALITY_WEIGHT, mvp.MIN_APPEARANCES)
    out: list[Setting] = []
    for quality in weights:
        for minimum in starts:
            won = _winners(tallies, ratings, names, quality, minimum)
            out.append(Setting(quality, minimum, won, sum(won[s] != baseline[s] for s in baseline if s in won)))
    return out

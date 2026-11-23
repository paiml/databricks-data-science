"""Course 3 features: target, form, home/away splits, rest days, Elo gap, leakage and time splits.

Every feature at match time uses only matches that kicked off earlier (ordered by date, then
match_api_id), so none of them can see the result it is trying to predict.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date

from dbx_ds import elo, stats
from dbx_ds.load import MatchRow
from dbx_ds.mvp import points

FORM_WINDOW = 5
REST_CAP = 10
LAST_TRAIN_SEASON = "2013/2014"
HOME, DRAW, AWAY = 0, 1, 2


def outcome(match: MatchRow) -> int:
    """0 home win, 1 draw, 2 away win."""
    if match.home_goals > match.away_goals:
        return HOME
    return DRAW if match.home_goals == match.away_goals else AWAY


def home_win_target(matches: list[MatchRow]) -> list[int]:
    """1.1.3: home_win = home_team_goal > away_team_goal, as 1 or 0."""
    return [1 if m.home_goals > m.away_goals else 0 for m in matches]


def target_summary(matches: list[MatchRow]) -> tuple[int, int, float]:
    """1.1.3: (rows, ones, share of ones)."""
    target = home_win_target(matches)
    return len(target), sum(target), sum(target) / len(target)


def parse_day(text: str) -> date:
    """The calendar day of a 'YYYY-MM-DD ...' string."""
    return date.fromisoformat(text[0:10])


def date_check(dates: list[str]) -> tuple[int, date, date]:
    """1.2.3: (number that do not parse, first day, last day)."""
    days = []
    bad = 0
    for text in dates:
        try:
            days.append(parse_day(text))
        except ValueError:
            bad += 1
    return bad, min(days), max(days)


@dataclass(frozen=True)
class Features:
    """One match as a model sees it. None means no earlier match to learn from."""

    match_api_id: int
    season: str
    outcome: int
    home_form: float | None
    away_form: float | None
    home_split: float | None
    away_split: float | None
    home_rest: int
    away_rest: int
    elo_gap: float
    goal_diff: int


def _mean_points(history: deque[int]) -> float | None:
    return sum(history) / len(history) if history else None


def build_features(matches: list[MatchRow]) -> list[Features]:
    """1.3.2 to 1.3.5: form, splits, rest days and Elo gap for every match, in replay order.

    * form: points per game over the team's last FORM_WINDOW earlier matches this season, any venue.
    * split: the home side's last FORM_WINDOW home matches, the away side's last FORM_WINDOW away matches.
    * rest: days since the team's previous match, capped at REST_CAP (a team's first match counts as the cap).
    * elo_gap: home rating + HOME_ADVANTAGE - away rating, before the match.
    """
    form: dict[tuple[str, int], deque[int]] = {}
    splits: dict[tuple[str, int, str], deque[int]] = {}
    last_day: dict[int, date] = {}
    rating: dict[int, float] = {}
    out: list[Features] = []
    for m in sorted(matches, key=lambda r: (r.date, r.match_api_id)):
        day = parse_day(m.date)
        rest = {t: min(REST_CAP, (day - last_day[t]).days) if t in last_day else REST_CAP for t in (m.home, m.away)}
        h_form = form.setdefault((m.season, m.home), deque(maxlen=FORM_WINDOW))
        a_form = form.setdefault((m.season, m.away), deque(maxlen=FORM_WINDOW))
        h_split = splits.setdefault((m.season, m.home, "home"), deque(maxlen=FORM_WINDOW))
        a_split = splits.setdefault((m.season, m.away, "away"), deque(maxlen=FORM_WINDOW))
        r_home = rating.get(m.home, elo.INITIAL_RATING)
        r_away = rating.get(m.away, elo.INITIAL_RATING)
        out.append(
            Features(
                m.match_api_id,
                m.season,
                outcome(m),
                _mean_points(h_form),
                _mean_points(a_form),
                _mean_points(h_split),
                _mean_points(a_split),
                rest[m.home],
                rest[m.away],
                r_home + elo.HOME_ADVANTAGE - r_away,
                m.home_goals - m.away_goals,
            )
        )
        delta = elo.K_FACTOR * (elo.actual_home(m.home_goals, m.away_goals) - elo.expected_home(r_home, r_away))
        rating[m.home], rating[m.away] = r_home + delta, r_away - delta
        h_pts, a_pts = points(m.home_goals, m.away_goals), points(m.away_goals, m.home_goals)
        h_form.append(h_pts)
        a_form.append(a_pts)
        h_split.append(h_pts)
        a_split.append(a_pts)
        last_day[m.home] = last_day[m.away] = day
    return out


def gap(a: float | None, b: float | None) -> float:
    """a - b with a missing side counted as zero (a team with no history has no form edge)."""
    return (a or 0.0) - (b or 0.0)


def model_row(f: Features) -> list[float]:
    """The pre-match inputs used by the capstone model: Elo gap, form gap, split gap, rest gap."""
    return [f.elo_gap, gap(f.home_form, f.away_form), gap(f.home_split, f.away_split), float(f.home_rest - f.away_rest)]


def rest_vs_home_win(feats: list[Features]) -> list[tuple[int, int, float]]:
    """1.3.4: (home rest days, matches, home win rate) for each rest value 1..REST_CAP that occurs."""
    groups: dict[int, list[int]] = {}
    for f in feats:
        groups.setdefault(f.home_rest, []).append(1 if f.outcome == HOME else 0)
    return [(days, len(w), stats.mean(w)) for days, w in sorted(groups.items())]


def leakage_demo(feats: list[Features]) -> dict[str, float]:
    """1.3.5: accuracy of 'home win?' from the final score (leaky) and from pre-match form (clean).

    The leaky rule reads goal_diff, which exists only after the whistle: it scores 100 percent.
    The clean rule says 'home win' when the home side's form is better, and never beats the
    always-home baseline by much.
    """
    actual = [1 if f.outcome == HOME else 0 for f in feats]
    leaky = [1 if f.goal_diff > 0 else 0 for f in feats]
    clean = [1 if gap(f.home_form, f.away_form) > 0 else 0 for f in feats]
    baseline = [1] * len(feats)
    return {
        "leaky": _accuracy(leaky, actual),
        "clean": _accuracy(clean, actual),
        "baseline": _accuracy(baseline, actual),
    }


def _accuracy(predicted: list[int], actual: list[int]) -> float:
    return sum(1 for p, a in zip(predicted, actual, strict=True) if p == a) / len(actual)


def feature_importance(feats: list[Features]) -> list[tuple[str, float]]:
    """2.1.5: |correlation| of each input with 'home win', largest first. A leaky input stands out."""
    target = [1.0 if f.outcome == HOME else 0.0 for f in feats]
    columns = {
        "elo_gap": [f.elo_gap for f in feats],
        "form_gap": [gap(f.home_form, f.away_form) for f in feats],
        "split_gap": [gap(f.home_split, f.away_split) for f in feats],
        "rest_gap": [float(f.home_rest - f.away_rest) for f in feats],
        "goal_diff (leak)": [float(f.goal_diff) for f in feats],
    }
    scored = [(name, abs(stats.pearson(col, target))) for name, col in columns.items()]
    return sorted(scored, key=lambda s: (-s[1], s[0]))


def split_cutoff(feats: list[Features], last_train: str = LAST_TRAIN_SEASON) -> str:
    """The last training season: `last_train` when the data has seasons on both sides of it, else the first season.

    The full database (8 seasons) gives 2013/2014. The two-season fixture has nothing before 2014/2015,
    so it trains on 2014/2015 and tests on 2015/2016: the same code path on small data.
    """
    seasons = sorted({f.season for f in feats})
    return last_train if seasons[0] <= last_train < seasons[-1] else seasons[0]


def time_split(feats: list[Features], last_train: str = LAST_TRAIN_SEASON) -> tuple[list[Features], list[Features]]:
    """2.1.3: train on seasons up to `last_train`, test on every later season. Never shuffled."""
    train = [f for f in feats if f.season <= last_train]
    test = [f for f in feats if f.season > last_train]
    return train, test

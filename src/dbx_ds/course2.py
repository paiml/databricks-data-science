"""Course 2 (Statistics From Zero) demo functions: one per gap in the lesson scripts.

Each function returns plain data; the notebook prints it with dbx_ds.report. The same
questions appear in SQL in sql/demo_stats.sql, and tests/test_demo_sql_parity.py checks
the two agree.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import duckdb

from dbx_ds import stats
from dbx_ds.changelog import ChangeLog, drop_nulls
from dbx_ds.load import MatchRow, column

RATING_SQL = "SELECT overall_rating FROM Player_Attributes"
SEASON_LENGTH = 380
SIMULATION_SEED = 386  # first seed from 0 whose season is 175 / 96 / 109, the counts the script quotes
RESAMPLE_SEED = 7
RESAMPLE_TRIALS = 1000


@dataclass(frozen=True)
class Distribution:
    """Centre and shape of one column."""

    n: int
    mean: float
    median: float
    bars: list[tuple[str, int]]


def ratings(con: duckdb.DuckDBPyConnection) -> list[float]:
    """Every non-null overall_rating."""
    return column(con, RATING_SQL + " WHERE overall_rating IS NOT NULL")


def rating_percentiles(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """1.1.5: median, quartiles, top percentiles and the IQR of overall_rating."""
    values = ratings(con)
    out: dict[str, float] = {"n": float(len(values))}
    for q, value in stats.percentiles(values).items():
        out[f"p{int(q)}"] = value
    out["iqr"] = stats.iqr(values)
    return out


def goal_distribution(matches: list[MatchRow], side: str = "home") -> Distribution:
    """1.2.3: whole-number histogram of home or away goals, with mean and median."""
    goals = [m.home_goals if side == "home" else m.away_goals for m in matches]
    counts = stats.value_counts(goals)
    return Distribution(len(goals), stats.mean(goals), stats.median(goals), [(str(k), v) for k, v in counts.items()])


def rating_distribution(con: duckdb.DuckDBPyConnection, width: int = 5) -> Distribution:
    """1.2.3: histogram of overall_rating in bins of `width` points."""
    values = ratings(con)
    counts = stats.value_counts([int(v) // width * width for v in values])
    bars = [(f"{k}-{k + width - 1}", v) for k, v in counts.items()]
    return Distribution(len(values), stats.mean(values), stats.median(values), bars)


def top_home_goal_matches(con: duckdb.DuckDBPyConnection, limit: int = 5) -> list[tuple[str, str, int, int]]:
    """1.2.4: the matches with the most home goals (date, league, home goals, away goals)."""
    rows = con.execute(
        "SELECT CAST(m.date AS VARCHAR), l.name, m.home_team_goal, m.away_team_goal "
        "FROM Match m JOIN League l ON m.league_id = l.id "
        "ORDER BY m.home_team_goal DESC, m.date, m.match_api_id LIMIT ?",
        [limit],
    ).fetchall()
    return [(str(d), str(n), int(h), int(a)) for d, n, h, a in rows]


def outlier_effect(matches: list[MatchRow]) -> dict[str, float]:
    """1.2.4: mean and sd of home goals with and without the biggest scores (the maximum value)."""
    goals = [m.home_goals for m in matches]
    top = max(goals)
    kept = [g for g in goals if g != top]
    return {
        "max": float(top),
        "n_max": float(len(goals) - len(kept)),
        "mean_all": stats.mean(goals),
        "sd_all": stats.stdev(goals),
        "mean_without": stats.mean(kept),
        "sd_without": stats.stdev(kept),
    }


def rating_quality(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """1.2.5: min, max and null count of overall_rating."""
    lo, hi, nulls, rows = con.execute(
        "SELECT min(overall_rating), max(overall_rating), "
        "count(*) - count(overall_rating), count(*) FROM Player_Attributes"
    ).fetchone()  # type: ignore[misc]
    return {"min": float(lo), "max": float(hi), "nulls": float(nulls), "rows": float(rows)}


def clean_ratings(con: duckdb.DuckDBPyConnection) -> tuple[list[float], ChangeLog]:
    """1.2.5: drop rows with no rating, and say so in a change log."""
    log = ChangeLog()
    raw = [r[0] for r in con.execute(RATING_SQL).fetchall()]
    return drop_nulls(raw, "drop null overall_rating", "a rating we do not have cannot be summarised", log), log


def league_goals(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, float]]:
    """1.3.2: (league, matches, mean total goals), highest mean first."""
    rows = con.execute(
        "SELECT l.name, count(*), avg(m.home_team_goal + m.away_team_goal) AS gpm "
        "FROM Match m JOIN League l ON m.league_id = l.id "
        "GROUP BY l.name ORDER BY gpm DESC, l.name"
    ).fetchall()
    return [(str(n), int(c), float(g)) for n, c, g in rows]


def result_counts(matches: list[MatchRow]) -> tuple[int, int, int]:
    """(home wins, draws, away wins)."""
    home = sum(1 for m in matches if m.home_goals > m.away_goals)
    draws = sum(1 for m in matches if m.home_goals == m.away_goals)
    return home, draws, len(matches) - home - draws


def result_shares(matches: list[MatchRow]) -> tuple[float, float, float]:
    """1.3.3 and 2.1.2: home, draw and away shares of all matches."""
    return tuple(c / len(matches) for c in result_counts(matches))  # type: ignore[return-value]


def mean_goals(matches: list[MatchRow]) -> tuple[float, float]:
    """(mean home goals, mean away goals)."""
    return stats.mean([m.home_goals for m in matches]), stats.mean([m.away_goals for m in matches])


def league_home_win_rates(matches: list[MatchRow]) -> list[tuple[str, float]]:
    """1.3.3: home win rate per league, highest first."""
    by_league: dict[str, list[int]] = {}
    for m in matches:
        by_league.setdefault(m.league, []).append(1 if m.home_goals > m.away_goals else 0)
    rates = [(league, stats.mean(wins)) for league, wins in by_league.items()]
    return sorted(rates, key=lambda r: (-r[1], r[0]))


def small_sample_demo(
    matches: list[MatchRow], sizes: tuple[int, ...] = (10, SEASON_LENGTH)
) -> list[tuple[int, float, float]]:
    """1.3.5: for each sample size, (n, formula error, error seen in 1000 seeded resamples).

    The last row is every match, where the resample spread is the formula error on all the data.
    """
    outcomes = [1 if m.home_goals > m.away_goals else 0 for m in matches]
    rate = stats.mean(outcomes)
    rows = []
    for n in (*sizes, len(outcomes)):
        resampled = stats.resample_rates(outcomes, n, RESAMPLE_TRIALS, RESAMPLE_SEED)
        rows.append((n, stats.standard_error_rate(rate, n), stats.stdev(resampled)))
    return rows


def running_home_win_rate(matches: list[MatchRow], points: int = 10) -> list[tuple[int, float]]:
    """2.1.2: home win rate after the first k matches, at `points` evenly spaced values of k."""
    wins = 0
    cumulative = []
    for i, m in enumerate(matches, start=1):
        wins += 1 if m.home_goals > m.away_goals else 0
        cumulative.append((i, wins / i))
    step = max(1, len(cumulative) // points)
    picked = cumulative[step - 1 :: step]
    return picked if picked[-1] == cumulative[-1] else [*picked, cumulative[-1]]


def independence(matches: list[MatchRow]) -> dict[str, float]:
    """2.1.3: P(home 0), P(away 0), their product, P(0-0) and corr(home goals, away goals)."""
    n = len(matches)
    p_home0 = sum(1 for m in matches if m.home_goals == 0) / n
    p_away0 = sum(1 for m in matches if m.away_goals == 0) / n
    p_both = sum(1 for m in matches if m.home_goals == 0 and m.away_goals == 0) / n
    corr = stats.pearson([m.home_goals for m in matches], [m.away_goals for m in matches])
    return {"p_home0": p_home0, "p_away0": p_away0, "product": p_home0 * p_away0, "p_0_0": p_both, "corr": corr}


def conditional_home_win(matches: list[MatchRow]) -> dict[str, float]:
    """2.1.4: P(home win), P(home scored >= 1), P(home win | scored) and P(scored | home win)."""
    n = len(matches)
    scored = [m for m in matches if m.home_goals >= 1]
    won = [m for m in matches if m.home_goals > m.away_goals]
    both = [m for m in scored if m.home_goals > m.away_goals]
    return {
        "p_win": len(won) / n,
        "p_scored": len(scored) / n,
        "p_win_given_scored": len(both) / len(scored),
        "p_scored_given_win": len(both) / len(won),
    }


def fair_odds_table(matches: list[MatchRow], margin: float = 0.05) -> list[tuple[str, float, float, float]]:
    """2.1.5: (outcome, rate, fair decimal odds, odds with a margin) for home, draw, away.

    The dataset has no bookmaker odds, so the margin column is a made-up 5 percent: every price
    is the fair price divided by 1 + margin, so the implied probabilities add to 1 + margin.
    """
    names = ("home win", "draw", "away win")
    rows = []
    for name, rate in zip(names, result_shares(matches), strict=True):
        fair = stats.fair_odds(rate)
        rows.append((name, rate, fair, fair / (1.0 + margin)))
    return rows


def poisson_tables(matches: list[MatchRow], k_max: int = 7) -> dict[str, list[tuple[int, float]]]:
    """2.2.3: Poisson probability for k = 0..k_max goals, home and away, at each side's mean."""
    home, away = mean_goals(matches)
    return {"home": stats.poisson_table(home, k_max), "away": stats.poisson_table(away, k_max)}


def poisson_fit(matches: list[MatchRow], k_max: int = 7) -> list[tuple[int, float, float]]:
    """2.2.4: (k, observed share, Poisson share) of home goals."""
    goals = [m.home_goals for m in matches]
    counts = stats.value_counts(goals)
    lam = stats.mean(goals)
    return [(k, counts.get(k, 0) / len(goals), stats.poisson_pmf(k, lam)) for k in range(k_max + 1)]


def variance_vs_mean(matches: list[MatchRow]) -> tuple[float, float]:
    """2.2.4: (variance, mean) of home goals. A Poisson count has the two equal."""
    goals = [m.home_goals for m in matches]
    return stats.variance(goals), stats.mean(goals)


def simulate(matches: list[MatchRow], seed: int = SIMULATION_SEED) -> dict[str, float]:
    """2.2.5: a seeded 380-match season at the observed lambdas, against the real shares."""
    lam_home, lam_away = mean_goals(matches)
    _, (home, draws, away) = stats.simulate_season(lam_home, lam_away, SEASON_LENGTH, seed)
    real = result_shares(matches)
    return {
        "home_wins": float(home),
        "draws": float(draws),
        "away_wins": float(away),
        "sim_home": home / SEASON_LENGTH,
        "sim_draw": draws / SEASON_LENGTH,
        "sim_away": away / SEASON_LENGTH,
        "real_home": real[0],
        "real_draw": real[1],
        "real_away": real[2],
    }


def attribute_correlations(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str, float]]:
    """2.3.2: (x, y, correlation) for rating vs potential, sprint_speed, finishing and height vs weight."""
    out = []
    for x, y, table in (
        ("overall_rating", "potential", "Player_Attributes"),
        ("overall_rating", "sprint_speed", "Player_Attributes"),
        ("overall_rating", "finishing", "Player_Attributes"),
        ("height", "weight", "Player"),
    ):
        rows = con.execute(f"SELECT {x}, {y} FROM {table} WHERE {x} IS NOT NULL AND {y} IS NOT NULL").fetchall()
        out.append((x, y, stats.pearson([r[0] for r in rows], [r[1] for r in rows])))
    return out


def scatter_sample(
    con: duckdb.DuckDBPyConnection, x: str, y: str, k: int = 500, seed: int = 11
) -> list[tuple[float, float]]:
    """2.3.2: a seeded sample of (x, y) points from Player_Attributes for a scatter chart."""
    rows = con.execute(
        f"SELECT {x}, {y} FROM Player_Attributes WHERE {x} IS NOT NULL AND {y} IS NOT NULL ORDER BY id"
    ).fetchall()
    return [(float(a), float(b)) for a, b in random.Random(seed).sample(rows, min(k, len(rows)))]


def rating_potential_means(con: duckdb.DuckDBPyConnection) -> tuple[float, float]:
    """2.3.3: mean overall_rating and mean potential."""
    row = con.execute("SELECT avg(overall_rating), avg(potential) FROM Player_Attributes").fetchone()
    return float(row[0]), float(row[1])  # type: ignore[index]


def rating_z(con: duckdb.DuckDBPyConnection, values: tuple[float, ...] = (84.0, 64.0)) -> dict[str, float]:
    """2.3.4: mean and sd of overall_rating, and the z-score of each value given."""
    data = ratings(con)
    centre, spread = stats.mean(data), stats.stdev(data)
    out = {"mean": centre, "sd": spread}
    for v in values:
        out[f"z_{v:g}"] = stats.z_score(v, centre, spread)
    return out


def league_goal_z(con: duckdb.DuckDBPyConnection) -> list[tuple[str, float, float]]:
    """2.3.4 and 3.1.3: (league, mean goals per match, z across the leagues), highest first."""
    table = league_goals(con)
    means = [g for _, _, g in table]
    return [(name, g, z) for (name, _, g), z in zip(table, stats.z_scores(means), strict=True)]


def latest_player_rows(con: duckdb.DuckDBPyConnection) -> list[tuple[int, str, float, float]]:
    """(player id, name, rating, potential) from each player's newest attribute row that has both."""
    rows = con.execute(
        "SELECT player_api_id, player_name, overall_rating, potential FROM ("
        "SELECT p.player_api_id, p.player_name, pa.overall_rating, pa.potential, "
        "row_number() OVER (PARTITION BY p.player_api_id ORDER BY pa.date DESC, pa.id DESC) AS rn "
        "FROM Player p JOIN Player_Attributes pa ON pa.player_api_id = p.player_api_id "
        "WHERE pa.overall_rating IS NOT NULL AND pa.potential IS NOT NULL) WHERE rn = 1 "
        "ORDER BY player_api_id"
    ).fetchall()
    return [(int(i), str(n), float(r), float(p)) for i, n, r, p in rows]


def rank_players(con: duckdb.DuckDBPyConnection, top: int = 10) -> list[tuple[str, float, float, float]]:
    """2.3.5: top players on one scale: (name, rating, potential, z(rating) + z(potential))."""
    rows = latest_player_rows(con)
    zr = stats.z_scores([r[2] for r in rows])
    zp = stats.z_scores([r[3] for r in rows])
    scored = [(r[1], r[2], r[3], a + b, r[0]) for r, a, b in zip(rows, zr, zp, strict=True)]
    scored.sort(key=lambda s: (-s[3], s[4]))
    return [(n, r, p, z) for n, r, p, z, _ in scored[:top]]


def uncertainty(
    matches: list[MatchRow], sizes: tuple[int, ...] = (SEASON_LENGTH, 2000)
) -> list[tuple[int, float, float, float]]:
    """3.1.4: (n, home win rate, low, high), the rate plus or minus two standard errors."""
    rate = result_shares(matches)[0]
    rows = []
    for n in (*sizes, len(matches)):
        low, high = stats.two_sigma_range(rate, n)
        rows.append((n, rate, low, high))
    return rows

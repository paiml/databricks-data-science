"""Course 3 (Data Science From Zero) demo functions: one per gap in the lesson scripts."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from dbx_ds import models, stats
from dbx_ds.features import HOME, Features, model_row, split_cutoff, time_split

RATING_INPUTS = ("potential", "finishing", "sprint_speed", "reactions")
UNDERRATED_TOP = 10
MIN_PLAYERS_FOR_FIT = 20


def duplicate_check(con: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    """1.2.3: (largest number of rows sharing one Match id, number of ids that repeat)."""
    row = con.execute(
        "SELECT coalesce(max(c), 0), count(*) FILTER (WHERE c > 1) FROM "
        "(SELECT id, count(*) AS c FROM Match GROUP BY id)"
    ).fetchone()
    return int(row[0]), int(row[1])  # type: ignore[index]


def match_dates(con: duckdb.DuckDBPyConnection) -> list[str]:
    return [str(r[0]) for r in con.execute("SELECT CAST(date AS VARCHAR) FROM Match ORDER BY id").fetchall()]


def range_checks(con: duckdb.DuckDBPyConnection) -> list[tuple[str, float, float]]:
    """1.2.4: (name, min, max) for goals, ratings, and the number of distinct seasons."""
    out = []
    for name, sql in (
        ("home_team_goal", "SELECT min(home_team_goal), max(home_team_goal) FROM Match"),
        ("away_team_goal", "SELECT min(away_team_goal), max(away_team_goal) FROM Match"),
        ("overall_rating", "SELECT min(overall_rating), max(overall_rating) FROM Player_Attributes"),
    ):
        lo, hi = con.execute(sql).fetchone()  # type: ignore[misc]
        out.append((name, float(lo), float(hi)))
    seasons = con.execute("SELECT count(DISTINCT season) FROM Match").fetchone()[0]  # type: ignore[index]
    out.append(("distinct seasons", float(seasons), float(seasons)))
    return out


@dataclass(frozen=True)
class PlayerRow:
    player_api_id: int
    name: str
    rating: float
    inputs: list[float]


def player_rows(con: duckdb.DuckDBPyConnection) -> list[PlayerRow]:
    """Each player's newest attribute row that has a rating and every input in RATING_INPUTS."""
    cols = ", ".join(f"pa.{c}" for c in RATING_INPUTS)
    complete = " AND ".join(f"pa.{c} IS NOT NULL" for c in ("overall_rating", *RATING_INPUTS))
    rows = con.execute(
        f"SELECT player_api_id, player_name, overall_rating, {', '.join(RATING_INPUTS)} FROM ("
        f"SELECT p.player_api_id, p.player_name, pa.overall_rating, {cols}, "
        "row_number() OVER (PARTITION BY p.player_api_id ORDER BY pa.date DESC, pa.id DESC) AS rn "
        f"FROM Player p JOIN Player_Attributes pa ON pa.player_api_id = p.player_api_id WHERE {complete}) "
        "WHERE rn = 1 ORDER BY player_api_id"
    ).fetchall()
    return [PlayerRow(int(r[0]), str(r[1]), float(r[2]), [float(v) for v in r[3:]]) for r in rows]


@dataclass(frozen=True)
class RatingFit:
    names: tuple[str, ...]
    coefs: list[float]
    z_coefs: list[float]
    r_squared: float
    n: int


def fit_rating(players: list[PlayerRow]) -> RatingFit:
    """2.2.2 and 2.2.3: overall_rating on potential and attributes, raw and on z-scored inputs."""
    x = [p.inputs for p in players]
    y = [p.rating for p in players]
    coefs = models.ols(x, y)
    scaler = models.fit_scaler(x)
    z_coefs = models.ols(scaler.apply(x), y)
    return RatingFit(RATING_INPUTS, coefs, z_coefs, models.r_squared(coefs, x, y), len(players))


def residual_spread(players: list[PlayerRow], fit: RatingFit) -> dict[str, float]:
    """2.2.4: spread of actual - predicted rating."""
    resid = models.residuals(fit.coefs, [p.inputs for p in players], [p.rating for p in players])
    return {
        "mean": stats.mean(resid),
        "sd": stats.stdev(resid),
        "min": min(resid),
        "max": max(resid),
        "within_2sd": sum(1 for r in resid if abs(r) <= 2 * stats.stdev(resid)) / len(resid),
    }


def residual_histogram(players: list[PlayerRow], fit: RatingFit, width: int = 2) -> list[tuple[str, int]]:
    """2.2.4: counts of residuals in bins of `width` rating points (for the residual chart)."""
    resid = models.residuals(fit.coefs, [p.inputs for p in players], [p.rating for p in players])
    counts = stats.value_counts([int(r // width) * width for r in resid])
    return [(f"{k:+d}", v) for k, v in counts.items()]


def underrated(
    players: list[PlayerRow], fit: RatingFit, top: int = UNDERRATED_TOP
) -> list[tuple[str, float, float, float]]:
    """2.2.5: players whose rating is furthest below what their attributes predict.

    (name, rating, predicted, residual), most negative residual first, ties by player id.
    """
    rows = []
    for p in players:
        predicted = models.predict_linear(fit.coefs, p.inputs)
        rows.append((p.rating - predicted, p.player_api_id, p.name, p.rating, predicted))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [(name, rating, predicted, resid) for resid, _, name, rating, predicted in rows[:top]]


def plan_markdown(question: str, metric: str, baseline: str, split: str) -> str:
    """3.1.2: the one-page plan the capstone starts from, as markdown."""
    return "\n".join(
        [
            "# Capstone plan",
            f"- **Question:** {question}",
            "- **Target:** home_win (1 if home goals > away goals, else 0); the model gives home / draw / away odds",
            f"- **Metric:** {metric}",
            f"- **Baseline to beat:** {baseline}",
            f"- **Split:** {split}",
            "- **Inputs:** Elo gap, form gap, split gap, rest gap (all known before kickoff)",
            "- **Leakage check:** no input uses the final score",
        ]
    )


@dataclass(frozen=True)
class Capstone:
    """Fit on the training seasons, scored on the test seasons."""

    n_train: int
    n_test: int
    accuracy: float
    baseline_accuracy: float
    log_loss: float
    baseline_log_loss: float
    coefficients: list[tuple[str, float]]
    calibration: list[tuple[float, float, float, int]]


INPUT_NAMES = ("elo_gap", "form_gap", "split_gap", "rest_gap")


def accuracy_and_log_loss(
    model: models.Logistic, rows: list[list[float]], labels: list[int], shares: list[float]
) -> tuple[float, float, float, float]:
    """2.3.3: (accuracy, baseline accuracy, log loss, baseline log loss) on one set of rows.

    The baseline gives every match the training class shares and always picks the most common class.
    """
    probs = [model.proba(r) for r in rows]
    predicted = [p.index(max(p)) for p in probs]
    always = shares.index(max(shares))
    return (
        models.accuracy(predicted, labels),
        models.accuracy([always] * len(labels), labels),
        models.log_loss(probs, labels),
        models.log_loss([shares] * len(labels), labels),
    )


def capstone(feats: list[Features], steps: int = 150) -> Capstone:
    """3.1.4, 2.3.3 to 2.3.5: end-to-end logistic regression with a time split and a baseline."""
    train, test = time_split(feats, split_cutoff(feats))
    x_train = [model_row(f) for f in train]
    y_train = [f.outcome for f in train]
    scaler = models.fit_scaler(x_train)
    z_train = scaler.apply(x_train)
    model = models.fit_logistic(z_train, y_train, steps=steps)
    z_test = scaler.apply([model_row(f) for f in test])
    y_test = [f.outcome for f in test]
    acc, base_acc, loss, base_loss = accuracy_and_log_loss(model, z_test, y_test, models.class_shares(y_train))
    p_home = [model.proba(r)[HOME] for r in z_test]
    hits = [1 if y == HOME else 0 for y in y_test]
    coefs = [(name, model.weights[HOME][i + 1]) for i, name in enumerate(INPUT_NAMES)]
    return Capstone(len(train), len(test), acc, base_acc, loss, base_loss, coefs, models.calibration(p_home, hits))

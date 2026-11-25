# Databricks notebook source
# MAGIC %md
# MAGIC # Course 3: Data Science From Zero
# MAGIC From a question to a number: who wins at home? Target, clean, features, split, fit, compare with the baseline.
# MAGIC
# MAGIC Data: European Soccer Database (ODbL 1.0). See the repo README.

# COMMAND ----------

# MAGIC %pip install duckdb matplotlib

# COMMAND ----------

import os
import sys
from pathlib import Path

# Repo root: DBX_DS_ROOT if set, else the folder above this notebook (a Databricks Git folder).
ROOT = Path(os.environ.get("DBX_DS_ROOT", Path.cwd().parent))
sys.path.insert(0, str(ROOT / "src"))
# On Databricks Free Edition point DBX_DS_DATA at your Volume, e.g. /Volumes/main/default/soccer
DATA_DIR = Path(os.environ.get("DBX_DS_DATA", ROOT / "data" / "fixture"))

# COMMAND ----------

from dbx_ds import charts, course2, course3, data, features, load, report, stats

con = data.connect(DATA_DIR)
matches = load.load_matches(con)

# COMMAND ----------

# 1.1.3 pick the target
rows, ones, share = features.target_summary(matches)
report.pairs([("matches", rows), ("home_win = 1", ones), ("share", share)])

# COMMAND ----------

# 1.2.3 duplicates and dates
most, repeated = course3.duplicate_check(con)
bad, first, last = features.date_check(course3.match_dates(con))
report.pairs(
    [
        ("most rows on one id", most),
        ("ids that repeat", repeated),
        ("dates that do not parse", bad),
        ("first day", first),
        ("last day", last),
    ]
)

# COMMAND ----------

# 1.2.4 check the ranges
print("\n".join(report.table_lines(["column", "min", "max"], course3.range_checks(con))))

# COMMAND ----------

# 1.2.5 log every change
kept, log = course2.clean_ratings(con)
print("\n".join(report.table_lines(log.columns(), log.rows())))

# COMMAND ----------

# 1.3.2 to 1.3.4 form, splits and rest days (one row per match, no future data)
feats = features.build_features(matches)
print(
    "\n".join(
        report.table_lines(
            ["match", "home form", "away form", "home split", "away split", "home rest", "away rest", "elo gap"],
            [
                (
                    f.match_api_id,
                    f.home_form,
                    f.away_form,
                    f.home_split,
                    f.away_split,
                    f.home_rest,
                    f.away_rest,
                    f.elo_gap,
                )
                for f in feats[:8]
            ],
        )
    )
)

# COMMAND ----------

# 1.3.4 rest days against home win rate
rest = features.rest_vs_home_win(feats)
print("\n".join(report.table_lines(["home rest days", "matches", "home win rate"], rest)))
charts.show(
    charts.bar_chart(
        "Home win rate by rest days",
        "home rest days",
        "home win rate",
        [str(r) for r, _, _ in rest],
        [w for _, _, w in rest],
    )
)

# COMMAND ----------

# 1.3.5 leakage and how to avoid it
report.pairs(list(features.leakage_demo(feats).items()))

# COMMAND ----------

# 2.1.3 time-based splits
cutoff = features.split_cutoff(feats)
train, test = features.time_split(feats, cutoff)
report.pairs([("last training season", cutoff), ("train rows", len(train)), ("test rows", len(test))])

# COMMAND ----------

# 2.1.5 why 100 percent is a warning
print("\n".join(stats.text_bars([(name, round(value, 3)) for name, value in features.feature_importance(feats)])))

# COMMAND ----------

# 2.2.2 linear regression
players = course3.player_rows(con)
fit = course3.fit_rating(players)
report.pairs(
    [("players", fit.n), ("r squared", fit.r_squared), ("intercept", fit.coefs[0])]
    + list(zip(fit.names, fit.coefs[1:], strict=True))
)

# COMMAND ----------

# 2.2.3 read the coefficients (inputs as z-scores)
report.pairs(list(zip(["intercept", *fit.names], fit.z_coefs, strict=True)))

# COMMAND ----------

# 2.2.4 residuals
report.pairs(list(course3.residual_spread(players, fit).items()))
print("\n".join(stats.text_bars(course3.residual_histogram(players, fit))))

# COMMAND ----------

# 2.2.5 under-rated players are residuals
print("\n".join(report.table_lines(["player", "rating", "model says", "residual"], course3.underrated(players, fit))))

# COMMAND ----------

# 3.1.2 frame the question
print(
    course3.plan_markdown(
        "Who wins at home, before kickoff?",
        "accuracy and 3-way log loss",
        "always give each result its training share",
        "train to 2013/2014, test 2014/2015 and 2015/2016",
    )
)

# COMMAND ----------

# 2.3.3 to 2.3.5 and 3.1.4 fit, score and compare on the test seasons
result = course3.capstone(feats)
report.pairs(
    [
        ("train rows", result.n_train),
        ("test rows", result.n_test),
        ("accuracy", result.accuracy),
        ("baseline accuracy", result.baseline_accuracy),
        ("log loss", result.log_loss),
        ("baseline log loss", result.baseline_log_loss),
    ]
    + [(f"coef {name}", value) for name, value in result.coefficients]
)
print("\n".join(report.table_lines(["bin from", "mean predicted", "observed", "matches"], result.calibration)))
charts.show(charts.calibration_chart("Calibration on the test seasons", result.calibration))

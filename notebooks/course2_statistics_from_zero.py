# Databricks notebook source
# MAGIC %md
# MAGIC # Course 2: Statistics From Zero
# MAGIC Mean, spread, probability, Poisson goals and z-scores on the European Soccer Database. One cell per lesson demo.
# MAGIC
# MAGIC Data: European Soccer Database (ODbL 1.0). See the repo README.

# COMMAND ----------

# MAGIC %pip install duckdb

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

from dbx_ds import course2, data, load, report, stats

con = data.connect(DATA_DIR)
matches = load.load_matches(con)

# COMMAND ----------

# 1.1.5 percentiles
p = course2.rating_percentiles(con)
report.pairs([(k, v) for k, v in p.items()])

# COMMAND ----------

# 1.2.3 skew and tails: goals
d = course2.goal_distribution(matches)
print("\n".join(stats.text_bars(d.bars)))
report.pairs([("mean", d.mean), ("median", d.median)])

# COMMAND ----------

# 1.2.3 skew and tails: ratings
d = course2.rating_distribution(con)
print("\n".join(stats.text_bars(d.bars)))
report.pairs([("mean", d.mean), ("median", d.median)])

# COMMAND ----------

# 1.2.4 outliers you should keep
print("\n".join(report.table_lines(["date", "league", "home", "away"], course2.top_home_goal_matches(con))))
report.pairs(list(course2.outlier_effect(matches).items()))

# COMMAND ----------

# 1.2.5 outliers you should fix
report.pairs(list(course2.rating_quality(con).items()))
kept, log = course2.clean_ratings(con)
print("\n".join(report.table_lines(log.columns(), log.rows())))

# COMMAND ----------

# 1.3.2 leagues side by side
leagues = course2.league_goals(con)
print("\n".join(report.table_lines(["league", "matches", "goals per match"], leagues)))
print("\n".join(stats.text_bars([(name, round(g, 2)) for name, _, g in leagues])))

# COMMAND ----------

# 1.3.3 home advantage
home, draw, away = course2.result_shares(matches)
report.pairs([("home win", home), ("draw", draw), ("away win", away)])
mean_home, mean_away = course2.mean_goals(matches)
report.pairs([("mean home goals", mean_home), ("mean away goals", mean_away), ("gap", mean_home - mean_away)])
print("\n".join(report.table_lines(["league", "home win rate"], course2.league_home_win_rates(matches))))

# COMMAND ----------

# 1.3.5 beware of small samples
print(
    "\n".join(report.table_lines(["n", "formula error", "error in 1000 resamples"], course2.small_sample_demo(matches)))
)

# COMMAND ----------

# 2.1.2 win, draw, loss rates
home_wins, draws, away_wins = course2.result_counts(matches)
report.pairs([("home wins", home_wins), ("draws", draws), ("away wins", away_wins), ("matches", len(matches))])
print("\n".join(report.table_lines(["after n matches", "home win rate"], course2.running_home_win_rate(matches))))

# COMMAND ----------

# 2.1.3 independent events
report.pairs(list(course2.independence(matches).items()))

# COMMAND ----------

# 2.1.4 conditional probability
report.pairs(list(course2.conditional_home_win(matches).items()))

# COMMAND ----------

# 2.1.5 odds and fair odds
print(
    "\n".join(
        report.table_lines(["outcome", "rate", "fair odds", "odds with 5% margin"], course2.fair_odds_table(matches))
    )
)

# COMMAND ----------

# 2.2.3 fit a Poisson
for side, table in course2.poisson_tables(matches).items():
    print(side)
    print("\n".join(report.table_lines(["k", "probability"], table)))

# COMMAND ----------

# 2.2.4 check the fit
fit = course2.poisson_fit(matches)
print("\n".join(report.table_lines(["k", "real share", "Poisson share"], fit)))
variance, mean = course2.variance_vs_mean(matches)
report.pairs([("variance", variance), ("mean", mean)])

# COMMAND ----------

# 2.2.5 simulate a season
report.pairs(list(course2.simulate(matches).items()))

# COMMAND ----------

# 2.3.2 correlation is not cause
print("\n".join(report.table_lines(["x", "y", "correlation"], course2.attribute_correlations(con))))
points = course2.scatter_sample(con, "potential", "overall_rating")
print(len(points), "seeded points for the scatter chart; first three:", points[:3])

# COMMAND ----------

# 2.3.3 rating and value
mean_rating, mean_potential = course2.rating_potential_means(con)
report.pairs([("mean rating", mean_rating), ("mean potential", mean_potential)])

# COMMAND ----------

# 2.3.4 the z-score
report.pairs(list(course2.rating_z(con).items()))
print("\n".join(report.table_lines(["league", "goals per match", "z"], course2.league_goal_z(con))))

# COMMAND ----------

# 2.3.5 rank players on one scale
print(
    "\n".join(
        report.table_lines(["player", "rating", "potential", "z(rating) + z(potential)"], course2.rank_players(con))
    )
)

# COMMAND ----------

# 3.1.4 state your uncertainty
print("\n".join(report.table_lines(["matches", "home win rate", "low", "high"], course2.uncertainty(matches))))

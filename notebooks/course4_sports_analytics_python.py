# Databricks notebook source
# MAGIC %md
# MAGIC # Course 4: Sports Analytics on Databricks in Python
# MAGIC Elo team ranking and the MVP, in Python (src/dbx_ds).
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

from dbx_ds import data

con = data.connect(DATA_DIR)

# COMMAND ----------

# 1.3.3 home advantage: shares of home wins, draws and away wins, and mean goals per side
from dbx_ds import course4, eloplus

a = course4.analyse(con)
league = course4.league_id(con)  # England Premier League; the full database has 11 leagues
SEASON = "2015/2016"  # use "2008/2009" on the full database
stats = eloplus.home_stats([g.result for g in a.games])
print(f"home {stats.home_pct}%  draw {stats.draw_pct}%  away {stats.away_pct}%")
print(f"goals per match: home {stats.home_goals}, away {stats.away_goals}")

# COMMAND ----------

# 1.3.4 tuning: mean squared forecast error for each K and home bonus (K outer, bonus inner)
grid = eloplus.tune([g.result for g in a.games], course4.GRID_KS, course4.GRID_BONUSES)
course4.print_table(["K", "bonus", "mse"], [(t.k_factor, t.home_advantage, round(t.mse, 5)) for t in grid[:8]])
best = eloplus.best(grid)
print("best:", best.k_factor, best.home_advantage, round(best.mse, 5))

# COMMAND ----------

# 3.1.1 league and season filter on the Elo table
print("\n".join(course4.elo_lines(a, league, SEASON, top=10)))

# COMMAND ----------

# 3.1.1 all leagues together: the current Elo table, each team at its latest season
print("\n".join(course4.current_lines(a)))

# COMMAND ----------

# 1.3.5 standings check: points table against Elo, and the Spearman rank correlation
rows, rho = eloplus.standings_check(a.games, a.ratings, league, SEASON)
course4.print_table(
    ["team", "points", "elo", "points rank", "elo rank"],
    [(a.teams[r.team_api_id], r.points, round(r.elo, 1), r.points_rank, r.elo_rank) for r in rows[:6]],
)
print("Spearman rho:", round(rho, 3))

# COMMAND ----------

# 2.2.2 qualified players per season, and 2.2.4 the MVP of every season of this league
from dbx_ds import mvpplus

print(mvpplus.qualified_counts(a.scores))
for s in mvpplus.mvp_per_season(a.scores, league):
    print(s.season, s.player_name, s.position, round(s.score, 2))

# COMMAND ----------

# 2.1.3 position z-score and 2.2.3 Elo-adjusted win share, next to the plain score
top = sorted((s for s in a.scores if s.league_id == league and s.season == SEASON), key=lambda s: s.score_rank)[:6]
course4.print_table(
    ["player", "pos", "rating", "win share", "adj win share", "z rating", "score", "adj score", "z score"],
    [
        (
            s.player_name,
            s.position,
            s.overall_rating,
            round(s.win_share, 1),
            round(s.adj_win_share, 1),
            round(s.z_rating, 1),
            round(s.score, 2),
            round(s.score_adj, 2),
            round(s.score_z, 2),
        )
        for s in top
    ],
)
print(
    [
        (s.player_name, round(elo_, 1), rank)
        for s, elo_, rank in mvpplus.top_with_team_elo(a.scores, a.ratings, league, SEASON)
    ]
)

# COMMAND ----------

# 2.2.5 sweep: does the MVP change with the weights and the minimum starts?
for setting in mvpplus.sweep(a.games, a.player_ratings, a.names, league, course4.SWEEP_WEIGHTS, course4.SWEEP_STARTS):
    print(setting.quality_weight, setting.min_starts, "seasons changed:", setting.changed)

# COMMAND ----------

# 2.3.3 gap column and 2.3.4 the five-name shortlist with the biggest gap
for s in mvpplus.shortlist_by_gap(a.scores, league, SEASON):
    print(s.player_name, "score rank", s.score_rank, "rating rank", s.rating_rank, "gap", s.gap)

# COMMAND ----------

# 3.1.4 the report: Elo top teams, MVP card and the five-name shortlist
course4.print_report(a, league, SEASON)

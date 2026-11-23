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

from dbx_ds import data, queries

con = data.connect(DATA_DIR)

# COMMAND ----------

from dbx_ds import elo

table = elo.current_table(elo.season_ratings(queries.load_results(con)))
teams = dict(con.execute("SELECT team_api_id, team_long_name FROM Team").fetchall())
for team, rating in table[:5]:
    print(round(rating, 1), teams[team])

# COMMAND ----------

for row in queries.python_mvp(con):
    if row.is_mvp or row.is_adjacent:
        print(row.season, "MVP" if row.is_mvp else "adjacent", row.player_name, round(row.score, 2))

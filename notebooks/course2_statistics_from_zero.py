# Databricks notebook source
# MAGIC %md
# MAGIC # Course 2: Statistics From Zero
# MAGIC Stub. Mean, spread and a first look at home advantage.
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

import statistics

home = [r[0] for r in con.execute("SELECT home_team_goal FROM Match").fetchall()]
away = [r[0] for r in con.execute("SELECT away_team_goal FROM Match").fetchall()]
print("mean home goals", round(statistics.mean(home), 3), "sd", round(statistics.stdev(home), 3))
print("mean away goals", round(statistics.mean(away), 3), "sd", round(statistics.stdev(away), 3))

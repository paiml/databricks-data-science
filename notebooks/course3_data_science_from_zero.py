# Databricks notebook source
# MAGIC %md
# MAGIC # Course 3: Data Science From Zero
# MAGIC Stub. From a question to a number: who wins at home?
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

wins = con.execute("SELECT count(*) FROM Match WHERE home_team_goal > away_team_goal").fetchone()[0]
total = con.execute("SELECT count(*) FROM Match").fetchone()[0]
print("home win rate", round(wins / total, 3))

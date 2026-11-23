# Databricks notebook source
# MAGIC %md
# MAGIC # Course 1: Databricks From Zero
# MAGIC Open a notebook, run a cell, look at a table. Every query the lessons run is below, by lesson.
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
from dbx_ds.report import show

con = data.connect(DATA_DIR)

# COMMAND ----------

# Lesson 2.1.2
show(
    con,
    """
SELECT * FROM Match LIMIT 10
""",
)

# COMMAND ----------

show(
    con,
    """
SELECT date, home_team_goal, away_team_goal FROM Match LIMIT 10
""",
)

# COMMAND ----------

# Lesson 2.1.4
show(
    con,
    """
SELECT count(*) FROM Match
""",
)

# COMMAND ----------

show(
    con,
    """
SELECT count(*) FROM Match WHERE season = '2015/2016'
""",
)

# COMMAND ----------

show(
    con,
    """
SELECT date, home_team_goal, away_team_goal,
       home_team_goal + away_team_goal AS total_goals
FROM Match ORDER BY total_goals DESC, date LIMIT 5
""",
)

# COMMAND ----------

# Lesson 2.2.4
show(
    con,
    """
SELECT p.player_name, pa.overall_rating, pa.date
FROM Player p JOIN Player_Attributes pa ON pa.player_api_id = p.player_api_id
ORDER BY pa.overall_rating DESC, pa.date LIMIT 5
""",
)

# COMMAND ----------

# Lesson 2.2.5
show(
    con,
    """
SELECT count(*) FROM Match
""",
)

# COMMAND ----------

show(
    con,
    """
SELECT count(*) FROM Match m JOIN Team t ON m.home_team_api_id = t.team_api_id
""",
)

# COMMAND ----------

show(
    con,
    """
SELECT count(*) FROM Player_Attributes
""",
)

# COMMAND ----------

show(
    con,
    """
SELECT count(*) FROM Player_Attributes pa
JOIN Player p ON pa.player_api_id = p.player_api_id
""",
)

# COMMAND ----------

show(
    con,
    """
SELECT count(*), count(DISTINCT team_api_id) FROM Team
""",
)

# COMMAND ----------

# Lesson 2.3.2
show(
    con,
    """
SELECT count(*) AS matches, sum(home_team_goal + away_team_goal) AS goals FROM Match
""",
)

# COMMAND ----------

show(
    con,
    """
SELECT season, count(*) AS matches, sum(home_team_goal + away_team_goal) AS goals
FROM Match GROUP BY season ORDER BY season
""",
)

# COMMAND ----------

# Lesson 2.3.3 and capstone question 1
show(
    con,
    """
SELECT l.name, count(*) AS matches, sum(m.home_team_goal + m.away_team_goal) AS goals,
       round(avg(m.home_team_goal + m.away_team_goal), 2) AS goals_per_match
FROM Match m JOIN League l ON m.league_id = l.id
GROUP BY l.name ORDER BY goals_per_match DESC
""",
)

# COMMAND ----------

# Lesson capstone question 3
show(
    con,
    """
SELECT sum(CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END) AS home_wins,
       sum(CASE WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END) AS draws,
       sum(CASE WHEN home_team_goal < away_team_goal THEN 1 ELSE 0 END) AS away_wins
FROM Match
""",
)

# COMMAND ----------

# Lesson capstone question 4
show(
    con,
    """
SELECT t.team_long_name, sum(m.home_team_goal) AS home_goals
FROM Match m JOIN Team t ON m.home_team_api_id = t.team_api_id
GROUP BY t.team_long_name ORDER BY home_goals DESC LIMIT 5
""",
)

# COMMAND ----------

# Lesson capstone question 5
show(
    con,
    """
SELECT p.player_name, max(pa.overall_rating) AS best_rating
FROM Player p JOIN Player_Attributes pa ON pa.player_api_id = p.player_api_id
GROUP BY p.player_name ORDER BY best_rating DESC, p.player_name LIMIT 5
""",
)

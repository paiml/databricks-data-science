-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Course 5: Sports Analytics on Databricks in SQL
-- MAGIC Same Elo and MVP as Course 4, in SQL (sql/elo.sql, sql/mvp.sql).
-- MAGIC Data: European Soccer Database (ODbL 1.0). See the repo README.

-- COMMAND ----------

-- databricks-only: create the views over your Volume (the tests skip this cell)
CREATE OR REPLACE TEMP VIEW Match AS SELECT * FROM parquet.`/Volumes/main/default/soccer/Match.parquet`;
CREATE OR REPLACE TEMP VIEW Player AS SELECT * FROM parquet.`/Volumes/main/default/soccer/Player.parquet`;
CREATE OR REPLACE TEMP VIEW Player_Attributes AS SELECT * FROM parquet.`/Volumes/main/default/soccer/Player_Attributes.parquet`;
CREATE OR REPLACE TEMP VIEW Team AS SELECT * FROM parquet.`/Volumes/main/default/soccer/Team.parquet`;

-- COMMAND ----------

SELECT season, count(*) AS matches, sum(home_team_goal + away_team_goal) AS goals
FROM Match
GROUP BY season
ORDER BY season;

-- COMMAND ----------

SELECT t.team_long_name, count(*) AS home_wins
FROM Match m
JOIN Team t ON t.team_api_id = m.home_team_api_id
WHERE m.home_team_goal > m.away_team_goal
GROUP BY t.team_long_name
ORDER BY home_wins DESC, t.team_long_name
LIMIT 5;

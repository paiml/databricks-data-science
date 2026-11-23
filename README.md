# Data Science on Databricks

<p align="center">
  <a href="https://ds500.paiml.com" title="Pragmatic AI Labs">
    <img src="./assets/banner.svg" alt="Data Science on Databricks: Elo team ranking, MVP and MVP-adjacent players" width="600">
  </a>
</p>

[![CI](https://github.com/paiml/databricks-data-science/actions/workflows/ci.yml/badge.svg)](https://github.com/paiml/databricks-data-science/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/code%20license-Apache%202.0-green.svg)](LICENSE)
[![Data](https://img.shields.io/badge/data-ODbL%201.0-orange.svg)](#dataset-and-licence)

<p align="center">
  <strong>One dataset, five courses: find the MVP, find the MVP-adjacent, rank every team with Elo</strong><br>
  Databricks | Statistics | Data Science | Python | SQL
</p>

Demo repository for the **Data Science on Databricks** specialization on Coursera. Every course uses the same data
and the same two answers, in Python and in SQL, so the two sets of numbers must match.

## Courses

| # | Course | Notebook |
|---|--------|----------|
| 1 | Databricks From Zero | `notebooks/course1_databricks_from_zero.py` |
| 2 | Statistics From Zero | `notebooks/course2_statistics_from_zero.py` |
| 3 | Data Science From Zero | `notebooks/course3_data_science_from_zero.py` |
| 4 | Sports Analytics on Databricks in Python | `notebooks/course4_sports_analytics_python.py` |
| 5 | Sports Analytics on Databricks in SQL | `notebooks/course5_sports_analytics_sql.sql` |

## Quick start

```bash
make install        # pip install -e ".[dev]"
make gate           # lint, mypy, tests with 100% line and branch coverage
dbx-ds elo          # top 10 teams on the committed fixture
dbx-ds mvp          # MVP and MVP-adjacent players per season
```

The repo ships a small fixture (two Premier League seasons, 760 matches, `data/fixture/*.parquet`, about 125 KB), so
everything runs with no download. For all 11 leagues:

```bash
make data           # downloads database.sqlite (sha256 checked), writes data/parquet/*.parquet
```

## Dataset and licence

- **Name:** European Soccer Database, by Hugo Mathien (Kaggle `hugomathien/soccer`): 25,979 matches, 11,060 players,
  299 teams, 11 European leagues, seasons 2008/2009 to 2015/2016. Seven tables: Country, League, Match, Player,
  Player_Attributes, Team, Team_Attributes.
- **Licence:** "Database: Open Database, Contents: (c) Original Authors", that is the Open Data Commons Open Database
  License (ODbL) 1.0: <http://opendatacommons.org/licenses/odbl/1.0/>. Source of the licence statement: the dataset
  page <https://www.kaggle.com/datasets/hugomathien/soccer> (its structured metadata, read 2026-11-23).
- **Notice shipped with the data:** `data/fixture/NOTICE.txt` (written by `dbx-ds fixture`, ODbL section 4.2(b)) carries
  the licence name and URL and the attribution; keep it with any copy of the fixture.
- **Fixture ratings are synthetic:** `Player_Attributes.overall_rating` in `data/fixture/` is a deterministic synthetic
  integer, `50 + ((id * 7919 + 104729) % 41)`, not the real FIFA value (those are EA Sports contents). So fixture
  MVPs are illustrative of the method, not of real players. Real ratings come only from `make data`.
- **Rights in the contents:** the ODbL covers the database only. Match results, odds and player ratings remain (c) their
  original authors (football-data.co.uk, EA Sports FIFA via sofifa.com). This repo claims no rights in them.
- **Attribution:** data by Hugo Mathien via Kaggle; the Kaggle page lists the underlying sources (football-data.co.uk
  for results and odds, sofifa.com for the FIFA player and team attributes, football-data.mx-api.enetscores.com for
  match events). Contents remain (c) their original authors.
- **What this repo redistributes:** the fixture is a derived database (a subset of Country, League, Match, Team,
  Player and Player_Attributes). Under the ODbL it stays under the ODbL (share-alike) and carries this attribution.
  The code in this repo is Apache-2.0. The full file is never committed.
- **Where `make data` gets the file:** Kaggle needs credentials, so we download a credential-free mirror of the
  identical file and pin its hash:
  - URL: <https://huggingface.co/datasets/julien-c/kaggle-hugomathien-soccer/resolve/main/database.sqlite>
  - sha256: `4df8569777d59fdd690754b1cc8ca1f7989baf65f2eaddd0f1368285f11139a9` (313,090,048 bytes)
  - The mirror's own README states `license: odbl` and names the Kaggle page as its source. Its table set and row
    counts match the Kaggle description. We could not compare it byte for byte with Kaggle's copy without a Kaggle
    login; the hash pin means a changed file fails loudly.

## Elo team ranking

`src/dbx_ds/elo.py`, `sql/elo.sql`. Every team starts at 1500. Matches replay in order of date, then
`match_api_id`. The home side gets +100 points when we work out who was expected to win. A win scores 1, a draw
0.5, a loss 0. The rating moves by `K * (actual - expected)` with `K = 20`. Ratings carry across seasons. The
constants are named at the top of the file and checked against the SQL by a test.

## MVP and MVP-adjacent

`src/dbx_ds/mvp.py`, `sql/mvp.sql`. Per player per season:

```
score = 0.7 * rating + 0.3 * win_share
```

- `rating`: the player's newest `overall_rating` (0 to 100) inside the season (1 August to 31 July).
- `win_share`: league points the team won while the player started, as a percent of the 3 points per match possible.
- Only players with at least 10 starts count. "Started" means named in the 11 lineup slots of the Match table.
- **MVP:** rank 1 on `score`.
- **MVP-adjacent:** top 20 on `score`, not the MVP, and either under-rated (the `overall_rating` rank is 10 or more
  places worse than the score rank) or a part-timer (15 starts or fewer). High value, quietly so.

## Python and SQL agree

`tests/test_parity.py` runs `sql/elo.sql` and `sql/mvp.sql` on the fixture with DuckDB and asserts the output equals
the Python output (ratings to 1e-9, ranks and flags exactly). Not yet run on Databricks SQL itself; see
`CHANGELOG.md`.

## Databricks Free Edition: upload path

1. `make data` on your laptop (or use `data/fixture/` to start small).
2. In Databricks: Catalog, your schema, Create, Volume (for example `main.default.soccer`).
3. Upload `data/parquet/*.parquet` (or `data/fixture/*.parquet` **and `data/fixture/NOTICE.txt`**: the ODbL notice travels with every copy) to the Volume.
4. Add this repo as a Git folder, open a notebook from `notebooks/`, set `DBX_DS_DATA=/Volumes/main/default/soccer`.
5. For Course 5, run the first cell, which makes temp views over the Volume files; the Elo and MVP SQL then run as is.

## Project structure

```
src/dbx_ds/    elo.py, mvp.py, data.py, queries.py, cli.py
sql/           elo.sql, mvp.sql (DuckDB-verified)
notebooks/     one Databricks-importable notebook per course
data/fixture/  committed Parquet fixture (ODbL)
tests/         100% line and branch coverage, SQL/Python parity
assets/        banner.svg
```

## Quality gates

`make gate` runs `ruff`, `mypy --strict` and `pytest` with `fail_under = 100` on line and branch coverage. CI
(`ci / gate`) runs the same on pinned versions. There are no advisory or report-only checks.

## License

Code: Apache-2.0 (see [LICENSE](LICENSE)). Data: ODbL 1.0, contents (c) original authors (see above).

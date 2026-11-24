# databricks-data-science

Demo repo for the Data Science on Databricks specialization (5 courses). One dataset, the European Soccer Database
(ODbL 1.0); one through-line: MVP and MVP-adjacent players plus an Elo team ranking.

- Python lives only in `src/dbx_ds`, `tests`, `notebooks`. Typed, ruff-clean, 100% line and branch coverage.
- `sql/elo.sql` and `sql/mvp.sql` must equal the Python (tests/test_parity.py). Change one, change both.
- `make gate` before every push. Main is protected; work on a branch and open a PR.
- Never commit `data/raw` or `data/parquet` (full database). The fixture in `data/fixture` is the only data committed.

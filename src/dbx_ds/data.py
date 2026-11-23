"""Fetch the European Soccer Database, export it to Parquet, load it into DuckDB.

The same Parquet files load into a Databricks Free Edition Volume (see README) and
into a local DuckDB, so the Python and SQL courses read identical data.
"""

from __future__ import annotations

import hashlib
import sqlite3
import urllib.request
from collections.abc import Iterable
from pathlib import Path

import duckdb

# Credential-free mirror of the Kaggle file hugomathien/soccer (database.sqlite).
MIRROR_URL = "https://huggingface.co/datasets/julien-c/kaggle-hugomathien-soccer/resolve/main/database.sqlite"
MIRROR_SHA256 = "4df8569777d59fdd690754b1cc8ca1f7989baf65f2eaddd0f1368285f11139a9"

FIXTURE_LEAGUE = "England Premier League"
FIXTURE_SEASONS = ("2014/2015", "2015/2016")
SEASON_START_MONTH = 8

MATCH_COLUMNS = (
    "id, country_id, league_id, season, stage, date, match_api_id, "
    "home_team_api_id, away_team_api_id, home_team_goal, away_team_goal, "
    + ", ".join(f"home_player_{i}" for i in range(1, 12))
    + ", "
    + ", ".join(f"away_player_{i}" for i in range(1, 12))
)
LINEUP_COLUMNS = [f"{side}_player_{i}" for side in ("home", "away") for i in range(1, 12)]

SQLITE_TO_DUCKDB = {"INTEGER": "BIGINT", "NUMERIC": "DOUBLE", "REAL": "DOUBLE", "TEXT": "VARCHAR"}


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(dest: Path, url: str = MIRROR_URL, sha256: str = MIRROR_SHA256) -> Path:
    """Download the SQLite file once and check its sha256. Raises ValueError on a mismatch."""
    if dest.exists() and sha256_file(dest) == sha256:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    urllib.request.urlretrieve(url, part)  # noqa: S310 - fixed https mirror, or file:// in tests
    got = sha256_file(part)
    if got != sha256:
        part.unlink()
        raise ValueError(f"sha256 mismatch for {url}: expected {sha256}, got {got}")
    part.replace(dest)
    return dest


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def full_queries() -> dict[str, str]:
    """Every table in full; Match keeps its result and lineup columns only."""
    queries = {
        name: f"SELECT * FROM {name}"
        for name in ("Country", "League", "Team", "Player", "Player_Attributes", "Team_Attributes")
    }
    queries["Match"] = f"SELECT {MATCH_COLUMNS} FROM Match"
    return queries


def fixture_queries(league: str = FIXTURE_LEAGUE, seasons: Iterable[str] = FIXTURE_SEASONS) -> dict[str, str]:
    """One league, a few seasons: the small deterministic subset committed for tests."""
    season_list = sorted(seasons)
    league_ids = f"SELECT id FROM League WHERE name = {_quote(league)}"
    in_seasons = ", ".join(_quote(s) for s in season_list)
    match_where = f"league_id IN ({league_ids}) AND season IN ({in_seasons})"
    first = int(season_list[0][0:4])
    last = int(season_list[-1][5:9])
    start = f"{first}-{SEASON_START_MONTH:02d}-01"
    end = f"{last}-{SEASON_START_MONTH:02d}-01"
    players = " UNION ".join(f"SELECT {c} FROM Match WHERE {match_where}" for c in LINEUP_COLUMNS)
    teams = " UNION ".join(
        f"SELECT {c} FROM Match WHERE {match_where}" for c in ("home_team_api_id", "away_team_api_id")
    )
    return {
        "Country": f"SELECT * FROM Country WHERE id IN (SELECT country_id FROM League WHERE id IN ({league_ids}))",
        "League": f"SELECT * FROM League WHERE id IN ({league_ids})",
        "Match": f"SELECT {MATCH_COLUMNS} FROM Match WHERE {match_where}",
        "Team": f"SELECT * FROM Team WHERE team_api_id IN ({teams})",
        "Player": f"SELECT * FROM Player WHERE player_api_id IN ({players})",
        "Player_Attributes": (
            f"SELECT * FROM Player_Attributes WHERE player_api_id IN ({players}) "
            f"AND date >= {_quote(start)} AND date < {_quote(end)}"
        ),
    }


def export_tables(db_path: Path, out_dir: Path, queries: dict[str, str]) -> list[Path]:
    """Run each query against the SQLite file and write <table>.parquet, rows sorted."""
    out_dir.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    target = duckdb.connect()
    written: list[Path] = []
    for name, sql in queries.items():
        declared = {row[1]: row[2] for row in source.execute(f'PRAGMA table_info("{name}")')}
        cursor = source.execute(sql)
        columns = [d[0] for d in cursor.description]
        ddl = ", ".join(f'"{c}" {SQLITE_TO_DUCKDB.get(declared[c].upper(), "VARCHAR")}' for c in columns)
        target.execute(f'CREATE TABLE "{name}" ({ddl})')
        marks = ", ".join("?" for _ in columns)
        while rows := cursor.fetchmany(10_000):
            target.executemany(f'INSERT INTO "{name}" VALUES ({marks})', rows)
        path = out_dir / f"{name}.parquet"
        target.execute(f"COPY (SELECT * FROM \"{name}\" ORDER BY ALL) TO '{path}' (FORMAT parquet)")
        written.append(path)
    source.close()
    target.close()
    return written


def connect(data_dir: Path) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with one view per Parquet file in data_dir, named after the table."""
    con = duckdb.connect()
    for path in sorted(data_dir.glob("*.parquet")):
        con.execute(f"CREATE VIEW \"{path.stem}\" AS SELECT * FROM read_parquet('{path}')")
    return con

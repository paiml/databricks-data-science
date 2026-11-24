from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from dbx_ds import data


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    assert data.sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_fetch_downloads_verifies_and_caches(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"abc")
    digest = data.sha256_file(src)
    dest = tmp_path / "out" / "db.sqlite"
    assert data.fetch(dest, src.as_uri(), digest) == dest
    assert dest.read_bytes() == b"abc"
    src.unlink()  # a second call must not touch the network or the source
    assert data.fetch(dest, src.as_uri(), digest) == dest


def test_fetch_rejects_a_wrong_hash_and_leaves_nothing(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"abc")
    dest = tmp_path / "db.sqlite"
    with pytest.raises(ValueError, match="sha256 mismatch"):
        data.fetch(dest, src.as_uri(), "0" * 64)
    assert not dest.exists()
    assert not (tmp_path / "db.sqlite.part").exists()


def test_fetch_redownloads_a_corrupt_cached_file(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"abc")
    dest = tmp_path / "db.sqlite"
    dest.write_bytes(b"corrupt")
    data.fetch(dest, src.as_uri(), data.sha256_file(src))
    assert dest.read_bytes() == b"abc"


def test_pinned_mirror_constants_are_well_formed() -> None:
    assert data.MIRROR_URL.startswith("https://")
    assert len(data.MIRROR_SHA256) == 64


def test_fixture_export_keeps_one_league_and_the_window(tiny_sqlite: Path, tmp_path: Path) -> None:
    out = tmp_path / "fx"
    paths = data.export_tables(tiny_sqlite, out, data.fixture_queries("O'Hara League", ["2015/2016", "2014/2015"]))
    assert sorted(p.stem for p in paths) == [
        "Country",
        "League",
        "Match",
        "Player",
        "Player_Attributes",
        "Team",
    ]
    con = data.connect(out)
    assert con.execute("SELECT season FROM Match ORDER BY season").fetchall() == [
        ("2014/2015",),
        ("2015/2016",),
    ]
    assert con.execute("SELECT name FROM Country").fetchall() == [("Alpha",)]
    assert con.execute("SELECT team_api_id FROM Team ORDER BY 1").fetchall() == [(10,), (11,)]
    assert con.execute("SELECT player_api_id FROM Player ORDER BY 1").fetchall() == [
        (101,),
        (201,),
        (202,),
    ]
    # 2013 and 2016-09 rows fall outside 2014-08-01 .. 2016-08-01
    assert con.execute("SELECT id FROM Player_Attributes").fetchall() == [(1,)]


def test_full_export_keeps_every_table_and_types(tiny_sqlite: Path, tmp_path: Path) -> None:
    out = tmp_path / "full"
    data.export_tables(tiny_sqlite, out, data.full_queries())
    con = data.connect(out)
    assert con.execute("SELECT count(*) FROM Match").fetchone() == (4,)
    assert con.execute("SELECT count(*) FROM Team_Attributes").fetchone() == (1,)
    assert con.execute("SELECT typeof(weight) FROM Team LIMIT 1").fetchone() == ("DOUBLE",)
    assert con.execute("SELECT typeof(season) FROM Match LIMIT 1").fetchone() == ("VARCHAR",)


def test_export_is_deterministic(tiny_sqlite: Path, tmp_path: Path) -> None:
    for name in ("a", "b"):
        data.export_tables(tiny_sqlite, tmp_path / name, data.full_queries())
    for table in data.full_queries():
        assert (tmp_path / "a" / f"{table}.parquet").read_bytes() == (tmp_path / "b" / f"{table}.parquet").read_bytes()


def test_connect_returns_a_duckdb_connection(tmp_path: Path) -> None:
    assert isinstance(data.connect(tmp_path), duckdb.DuckDBPyConnection)


def test_fixture_attribute_columns_are_minimal(tiny_sqlite: Path, tmp_path: Path) -> None:
    out = tmp_path / "fx"
    data.export_tables(tiny_sqlite, out, data.fixture_queries("O'Hara League", ["2014/2015"]))
    cols = [r[0] for r in data.connect(out).execute("DESCRIBE Player_Attributes").fetchall()]
    assert cols == [
        "id",
        "player_api_id",
        "date",
        "overall_rating",
        "potential",
        "finishing",
        "sprint_speed",
        "reactions",
    ]


def test_write_notice_carries_odbl_attribution(tmp_path: Path) -> None:
    text = data.write_notice(tmp_path).read_text()
    for needle in ("ODbL", "opendatacommons.org/licenses/odbl/1.0", "Hugo Mathien", "Original Authors", "share-alike"):
        assert needle in text


def test_committed_fixture_ships_the_notice() -> None:
    from tests.conftest import FIXTURE

    assert (FIXTURE / "NOTICE.txt").read_text() == data.NOTICE


def test_fixture_ratings_are_synthetic_and_deterministic(tiny_sqlite: Path, tmp_path: Path) -> None:
    out = tmp_path / "fx"
    data.export_tables(tiny_sqlite, out, data.fixture_queries("O'Hara League", ["2014/2015"]))
    rows = data.connect(out).execute("SELECT id, overall_rating FROM Player_Attributes").fetchall()
    assert rows == [(i, 50 + (i * 7919 + data.SYNTHETIC_SEED) % 41) for i, _ in rows]
    assert all(50 <= r <= 90 for _, r in rows)
    extra = data.connect(out).execute(
        "SELECT overall_rating, potential, finishing, sprint_speed, reactions FROM Player_Attributes"
    )
    for rating, potential, finishing, speed, reactions in extra.fetchall():
        assert rating <= potential <= rating + 8
        assert 30 <= finishing <= 90 and 30 <= speed <= 90 and 35 <= reactions <= 90
    assert "SYNTHETIC" in data.NOTICE

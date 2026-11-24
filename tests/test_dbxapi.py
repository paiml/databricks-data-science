import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from dbx_ds import cli, dbxapi


class Fake:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = replies
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, str]]] = []

    def __call__(self, method: str, url: str, headers: Any, body: bytes | None) -> dict[str, Any]:
        self.calls.append((method, url, json.loads(body) if body else None, dict(headers)))
        return self.replies.pop(0)


def ok(cols: list[str], rows: list[list[str]]) -> dict[str, Any]:
    return {
        "statement_id": "s",
        "status": {"state": "SUCCEEDED"},
        "manifest": {"schema": {"columns": [{"name": c} for c in cols]}},
        "result": {"data_array": rows},
    }


def test_load_auth_env_and_file(tmp_path: Path) -> None:
    assert dbxapi.load_auth(tmp_path / "x", "p", {"DATABRICKS_HOST": "https://h/", "DATABRICKS_TOKEN": "t"}) == (
        "https://h",
        "t",
    )
    cfg = tmp_path / "cfg"
    cfg.write_text("[p]\nhost = https://h/\ntoken = t\n[bad]\nhost = h\n")
    assert dbxapi.load_auth(cfg, "p", {}) == ("https://h", "t")
    with pytest.raises(dbxapi.DbxError, match="not found"):
        dbxapi.load_auth(cfg, "zz", {})
    with pytest.raises(dbxapi.DbxError, match="needs host"):
        dbxapi.load_auth(cfg, "bad", {})


def test_load_auth_default_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABRICKS_HOST", "https://e")
    monkeypatch.setenv("DATABRICKS_TOKEN", "t")
    assert dbxapi.load_auth(tmp_path / "x", "p") == ("https://e", "t")


def test_whoami_and_warehouse() -> None:
    f = Fake([{"userName": "me"}, {"warehouses": [{"id": "w1"}]}, {}])
    c = dbxapi.Client("https://h", "tok", f)
    assert c.whoami() == "me"
    assert c.warehouse_id() == "w1"
    assert f.calls[0][3]["Authorization"] == "Bearer tok"
    with pytest.raises(dbxapi.DbxError, match="no SQL warehouse"):
        c.warehouse_id()


def test_import_notebook(tmp_path: Path) -> None:
    nb = tmp_path / "a.py"
    nb.write_text("print(1)")
    f = Fake([{}])
    dbxapi.Client("https://h", "t", f).import_notebook(nb, "/Shared/a")
    body = f.calls[0][2]
    assert (
        body is not None and body["language"] == "PYTHON" and body["overwrite"] is True and body["path"] == "/Shared/a"
    )


def test_run_sql_polls_and_fails() -> None:
    pending = {"statement_id": "s", "status": {"state": "RUNNING"}}
    f = Fake([pending, ok(["n"], [["1"]])])
    slept: list[float] = []
    res = dbxapi.Client("https://h", "t", f).run_sql("w", "select 1", sleep=slept.append)
    assert res["columns"] == ["n"] and res["rows"] == [["1"]] and slept == [1.0]
    bad = {"statement_id": "s", "status": {"state": "FAILED", "error": {"message": "boom"}}}
    with pytest.raises(dbxapi.DbxError, match="FAILED: boom"):
        dbxapi.Client("https://h", "t", Fake([bad])).run_sql("w", "x")
    empty = {"statement_id": "s", "status": {"state": "SUCCEEDED"}}
    assert dbxapi.Client("https://h", "t", Fake([empty])).run_sql("w", "x")["rows"] == []


def test_split_statements() -> None:
    sql = "-- c\nselect 'a;b';\n\nselect 2;"
    assert dbxapi.split_statements(sql) == ["select 'a;b'", "select 2"]


def test_capture(tmp_path: Path) -> None:
    sql = tmp_path / "demo_x.sql"
    sql.write_text("select 1; select 2;")
    f = Fake([ok(["a"], [["1"]]), ok(["a"], [["2"]])])
    out = dbxapi.capture(dbxapi.Client("https://h", "t", f), "w", sql, tmp_path / "o")
    assert [p.name for p in out] == ["demo_x.01.json", "demo_x.02.json"]
    assert json.loads(out[1].read_text())["rows"] == [["2"]]


class Resp(io.BytesIO):
    def __enter__(self) -> "Resp":
        return self

    def __exit__(self, *a: object) -> None:
        return None


def test_urllib_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dbxapi._OPENER, "open", lambda req, timeout: Resp(b'{"a": 1}'))
    assert dbxapi.urllib_transport("GET", "https://h", {}, None) == {"a": 1}
    monkeypatch.setattr(dbxapi._OPENER, "open", lambda req, timeout: Resp(b""))
    assert dbxapi.urllib_transport("GET", "https://h", {}, None) == {}

    def boom(body: bytes) -> Any:
        def _raise(req: Any, timeout: int) -> None:
            raise urllib.error.HTTPError("u", 403, "x", {}, io.BytesIO(body))  # type: ignore[arg-type]

        return _raise

    monkeypatch.setattr(dbxapi._OPENER, "open", boom(b'{"message": "Invalid access token"}'))
    with pytest.raises(dbxapi.DbxError, match="HTTP 403: Invalid access token"):
        dbxapi.urllib_transport("GET", "https://h", {}, None)
    monkeypatch.setattr(dbxapi._OPENER, "open", boom(b"not json"))
    with pytest.raises(dbxapi.DbxError, match="HTTP 403: $"):
        dbxapi.urllib_transport("GET", "https://h", {}, None)
    monkeypatch.setattr(dbxapi._OPENER, "open", boom(b"[1]"))
    with pytest.raises(dbxapi.DbxError, match="HTTP 403: $"):
        dbxapi.urllib_transport("GET", "https://h", {}, None)

    def down(req: Any, timeout: int) -> None:
        raise urllib.error.URLError("dns")

    monkeypatch.setattr(dbxapi._OPENER, "open", down)
    with pytest.raises(dbxapi.DbxError, match="request failed"):
        dbxapi.urllib_transport("GET", "https://h", {}, None)
    monkeypatch.setattr(dbxapi._OPENER, "open", lambda req, timeout: Resp(b"<html>"))
    with pytest.raises(dbxapi.DbxError, match="request failed"):
        dbxapi.urllib_transport("GET", "https://h", {}, None)


def test_no_redirect() -> None:
    handler = dbxapi._NoRedirect()
    req = urllib.request.Request("https://h/a")
    assert handler.redirect_request(req, None, 302, "Found", {}, "https://evil/") is None


def test_load_auth_hardening(tmp_path: Path) -> None:
    with pytest.raises(dbxapi.DbxError, match="https"):
        dbxapi.load_auth(tmp_path / "x", "p", {"DATABRICKS_HOST": "http://h", "DATABRICKS_TOKEN": "t"})
    cfg = tmp_path / "cfg"
    cfg.write_text("[DEFAULT]\nhost = https://d\ntoken = 100%\n[other]\nhost = https://o\n")
    assert dbxapi.load_auth(cfg, "DEFAULT", {}) == ("https://d", "100%")
    with pytest.raises(dbxapi.DbxError, match="needs host"):
        dbxapi.load_auth(cfg, "other", {})


def test_run_sql_deadline_and_chunks() -> None:
    pending = {"statement_id": "a/b", "status": {"state": "RUNNING"}}
    f = Fake([pending, pending, {}])
    with pytest.raises(dbxapi.DbxError, match="cancelled"):
        dbxapi.Client("https://h", "t", f).run_sql("w", "x", sleep=lambda s: None, max_polls=1)
    assert f.calls[1][1].endswith("/statements/a%2Fb") and f.calls[2][1].endswith("/statements/a%2Fb/cancel")
    chunked = ok(["n"], [["1"]])
    chunked["manifest"]["total_chunk_count"] = 2
    with pytest.raises(dbxapi.DbxError, match="chunked"):
        dbxapi.Client("https://h", "t", Fake([chunked])).run_sql("w", "x")


def test_split_comments() -> None:
    sql = "select 1; -- don't\nselect /* a;b */ 2 / 1 - 1; select 'it''s';"
    assert dbxapi.split_statements(sql) == ["select 1", "select  2 / 1 - 1", "select 'it''s'"]


def test_capture_removes_stale(tmp_path: Path) -> None:
    out = tmp_path / "o"
    out.mkdir()
    (out / "demo_x.05.json").write_text("{}")
    (out / "demo_y.01.json").write_text("{}")
    sql = tmp_path / "demo_x.sql"
    sql.write_text("select 1")
    dbxapi.capture(dbxapi.Client("https://h", "t", Fake([ok(["a"], [["1"]])])), "w", sql, out)
    assert not (out / "demo_x.05.json").exists() and (out / "demo_y.01.json").exists()


def test_cli_dbx(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = tmp_path / "cfg"
    cfg.write_text("[p]\nhost = https://h\ntoken = SECRET\n")
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "notebooks" / "course1_a.py").write_text("x")
    (tmp_path / "sql").mkdir()
    (tmp_path / "sql" / "demo_a.sql").write_text("select 1")
    monkeypatch.chdir(tmp_path)
    f = Fake([{"userName": "me"}, {}, {}, {"warehouses": [{"id": "w"}]}, ok(["a"], [["1"]])])
    monkeypatch.setattr(dbxapi, "urllib_transport", f)
    monkeypatch.setattr(dbxapi.Client.__init__, "__defaults__", (f,))
    base = ["dbx", "--profile", "p", "--cfg", str(cfg)]
    assert cli.main([*base, "whoami"]) == 0
    assert cli.main([*base, "import"]) == 0
    assert cli.main([*base, "capture", "--out", "o"]) == 0
    out = capsys.readouterr().out
    assert "auth OK: me" in out and "imported course1_a.py" in out and "captured o/demo_a.01.json" in out
    assert "SECRET" not in out
    (tmp_path / "notebooks" / "course1_a.sql").write_text("x")
    with pytest.raises(SystemExit, match="share a stem"):
        cli.main([*base, "import"])
    (tmp_path / "notebooks" / "course1_a.sql").unlink()
    (tmp_path / "notebooks" / "course1_a.py").unlink()
    with pytest.raises(SystemExit, match="no notebooks"):
        cli.main([*base, "import"])
    monkeypatch.setattr(dbxapi.Client.__init__, "__defaults__", (Fake([{"warehouses": []}]),))
    assert cli.main([*base, "capture"]) == 1
    assert "no SQL warehouse" in capsys.readouterr().err

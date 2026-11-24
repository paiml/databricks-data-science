"""Databricks REST driver: import notebooks, run SQL on a warehouse, capture result tables as JSON.

Auth comes from ~/.databrickscfg (or DATABRICKS_HOST / DATABRICKS_TOKEN). Tokens are never printed or logged.
"""

from __future__ import annotations

import base64
import configparser
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from dbx_ds.sqlinline import standalone

Transport = Callable[[str, str, Mapping[str, str], bytes | None], dict[str, Any]]

LANGUAGES = {".py": "PYTHON", ".sql": "SQL"}


class DbxError(RuntimeError):
    """API or auth failure. The message never contains the token."""


def _http_message(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(exc.read()).get("message", ""))
    except (ValueError, AttributeError):
        return ""


def _https(host: str) -> str:
    """Refuse a host that is not https: the bearer token must never travel in cleartext."""
    parsed = urllib.parse.urlparse(host)
    if parsed.scheme != "https" or not parsed.netloc:
        raise DbxError("host must be an https URL")
    return host


def load_auth(cfg: Path, profile: str, env: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    if env.get("DATABRICKS_HOST") and env.get("DATABRICKS_TOKEN"):
        return _https(env["DATABRICKS_HOST"].rstrip("/")), env["DATABRICKS_TOKEN"]
    # DEFAULT is an ordinary profile here: no section leaks its keys into the others, and no % interpolation.
    parser = configparser.RawConfigParser(default_section="\0unused")
    parser.read(cfg)
    sec = dict(parser[profile]) if parser.has_section(profile) else {}
    if not sec:
        raise DbxError(f"profile {profile!r} not found")
    if not {"host", "token"} <= sec.keys():
        raise DbxError(f"profile {profile!r} needs host and token")
    return _https(sec["host"].rstrip("/")), sec["token"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: urllib would forward the Authorization header to the new host."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> dict[str, Any]:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)  # noqa: S310
    try:
        with _OPENER.open(req, timeout=60) as resp:
            return json.loads(resp.read() or b"{}")  # type: ignore[no-any-return]
    except urllib.error.HTTPError as exc:
        raise DbxError(f"HTTP {exc.code}: {_http_message(exc)}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        raise DbxError("request failed (network error or invalid response)") from None


class Client:
    def __init__(self, host: str, token: str, transport: Transport = urllib_transport) -> None:
        self._host = host
        self._token = token
        self._transport = transport

    def call(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        data = None if body is None else json.dumps(body).encode()
        return self._transport(method, self._host + path, headers, data)

    def whoami(self) -> str:
        return str(self.call("GET", "/api/2.0/preview/scim/v2/Me").get("userName", ""))

    def warehouse_id(self) -> str:
        found = self.call("GET", "/api/2.0/sql/warehouses").get("warehouses", [])
        if not found:
            raise DbxError("no SQL warehouse")
        return str(found[0]["id"])

    def mkdirs(self, remote_dir: str) -> None:
        self.call("POST", "/api/2.0/workspace/mkdirs", {"path": remote_dir})

    def import_notebook(self, local: Path, remote: str) -> None:
        language = LANGUAGES[local.suffix]
        content = base64.b64encode(local.read_bytes()).decode()
        self.call(
            "POST",
            "/api/2.0/workspace/import",
            {
                "path": remote,
                "format": "SOURCE",
                "language": language,
                "content": content,
                "overwrite": True,
            },
        )

    def run_sql(
        self,
        warehouse: str,
        statement: str,
        poll: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        max_polls: int = 600,
    ) -> dict[str, Any]:
        out = self.call(
            "POST",
            "/api/2.0/sql/statements",
            {
                "warehouse_id": warehouse,
                "statement": statement,
                "wait_timeout": "30s",
                "disposition": "INLINE",
            },
        )
        sid = urllib.parse.quote(str(out["statement_id"]), safe="")
        polls = 0
        while out["status"]["state"] in ("PENDING", "RUNNING"):
            if polls >= max_polls:
                self.call("POST", f"/api/2.0/sql/statements/{sid}/cancel")
                raise DbxError(f"statement still running after {max_polls} polls; cancelled")
            polls += 1
            sleep(poll)
            out = self.call("GET", f"/api/2.0/sql/statements/{sid}")
        if out["status"]["state"] != "SUCCEEDED":
            raise DbxError(f"statement {out['status']['state']}: {out['status'].get('error', {}).get('message', '')}")
        if out.get("manifest", {}).get("truncated") or out.get("manifest", {}).get("total_chunk_count", 1) > 1:
            raise DbxError("result is chunked or truncated; refusing to capture a partial table")
        cols = [c["name"] for c in out.get("manifest", {}).get("schema", {}).get("columns", [])]
        return {"statement": statement, "columns": cols, "rows": out.get("result", {}).get("data_array", [])}


# A quoted run honours backslash escapes (Databricks reads \' inside '...'); '' still works as two adjacent runs.
_TOKEN = re.compile(
    r"(?P<c>--[^\n]*|/\*.*?\*/)|'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`|;|[^;'\"`/-]+|.",
    re.DOTALL,
)


def split_statements(sql: str) -> list[str]:
    """Split on semicolons outside quotes; drop -- and /* */ comments and blanks."""
    pieces = (" " if m.group("c") else "\0" if m.group() == ";" else m.group() for m in _TOKEN.finditer(sql))
    parts = "".join(pieces).split("\0")
    return [p.strip() for p in parts if p.strip()]


def capture(client: Client, warehouse: str, sql_file: Path, out_dir: Path) -> list[Path]:
    """Run every statement of sql_file on its own; write one JSON result table per statement.

    Files are numbered by statement position, so a CREATE VIEW (folded into later statements, never sent) leaves a gap.
    sql/c5_views.sql beside the file supplies the views the demo statements read.
    """
    views = sql_file.with_name("c5_views.sql")
    setup = split_statements(views.read_text()) if views.exists() and views != sql_file else []
    try:
        plan = standalone(split_statements(sql_file.read_text()), setup)
    except ValueError as exc:  # before anything is deleted or sent
        raise DbxError(f"{sql_file.name}: {exc}") from None
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"{sql_file.stem}.[0-9][0-9].json"):
        stale.unlink()
    written = []
    for i, stmt in enumerate(plan, 1):
        if stmt is None:
            continue
        path = out_dir / f"{sql_file.stem}.{i:02d}.json"
        path.write_text(json.dumps(client.run_sql(warehouse, stmt), indent=2) + "\n")
        written.append(path)
    return written

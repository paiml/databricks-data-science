"""Databricks REST driver: import notebooks, run SQL on a warehouse, capture result tables as JSON.

Auth comes from ~/.databrickscfg (or DATABRICKS_HOST / DATABRICKS_TOKEN). Tokens are never printed or logged.
"""

from __future__ import annotations

import base64
import configparser
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

Transport = Callable[[str, str, Mapping[str, str], bytes | None], dict[str, Any]]

LANGUAGES = {".py": "PYTHON", ".sql": "SQL"}


class DbxError(RuntimeError):
    """API or auth failure. The message never contains the token."""


def _http_message(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(exc.read()).get("message", ""))
    except ValueError:
        return ""


def load_auth(cfg: Path, profile: str, env: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    if env.get("DATABRICKS_HOST") and env.get("DATABRICKS_TOKEN"):
        return env["DATABRICKS_HOST"].rstrip("/"), env["DATABRICKS_TOKEN"]
    parser = configparser.ConfigParser()
    parser.read(cfg)
    sec = dict(parser[profile]) if parser.has_section(profile) else {}
    if not sec:
        raise DbxError(f"profile {profile!r} not found")
    if not {"host", "token"} <= sec.keys():
        raise DbxError(f"profile {profile!r} needs host and token")
    return sec["host"].rstrip("/"), sec["token"]


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> dict[str, Any]:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return json.loads(resp.read() or b"{}")  # type: ignore[no-any-return]
    except urllib.error.HTTPError as exc:
        raise DbxError(f"HTTP {exc.code}: {_http_message(exc)}") from None


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
        self, warehouse: str, statement: str, poll: float = 1.0, sleep: Callable[[float], None] = time.sleep
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
        while out["status"]["state"] in ("PENDING", "RUNNING"):
            sleep(poll)
            out = self.call("GET", f"/api/2.0/sql/statements/{out['statement_id']}")
        if out["status"]["state"] != "SUCCEEDED":
            raise DbxError(f"statement {out['status']['state']}: {out['status'].get('error', {}).get('message', '')}")
        cols = [c["name"] for c in out.get("manifest", {}).get("schema", {}).get("columns", [])]
        return {"statement": statement, "columns": cols, "rows": out.get("result", {}).get("data_array", [])}


_TOKEN = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`|;|[^;'\"`]+|['\"`]")


def split_statements(sql: str) -> list[str]:
    """Split on semicolons outside quotes; drop -- comment lines and blanks."""
    text = "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    parts = "".join(t if t != ";" else "\0" for t in _TOKEN.findall(text)).split("\0")
    return [p.strip() for p in parts if p.strip()]


def capture(client: Client, warehouse: str, sql_file: Path, out_dir: Path) -> list[Path]:
    """Run every statement of sql_file; write one JSON result table per statement."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i, stmt in enumerate(split_statements(sql_file.read_text()), 1):
        path = out_dir / f"{sql_file.stem}.{i:02d}.json"
        path.write_text(json.dumps(client.run_sql(warehouse, stmt), indent=2) + "\n")
        written.append(path)
    return written

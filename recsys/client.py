"""Minimal RawTree HTTP client for the recommender.

Reads TEAM_ID and RAWTREE_API_KEY from the repo's .env (or the environment). Never logs the key.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent

for _line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    _key, _, _value = _line.partition("=")
    if _key.strip() and not _key.lstrip().startswith("#"):
        os.environ.setdefault(_key.strip(), _value.strip())

API = os.environ.get("RAWTREE_API_URL", "https://api.rawtree.com")
TEAM = os.environ["TEAM_ID"]

Row = dict[str, Any]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {os.environ['RAWTREE_API_KEY']}"
    s.headers["User-Agent"] = "datathon-team-recsys/1.0"
    return s


# One session per thread: requests.Session is not guaranteed thread-safe.
_local = threading.local()


def _http() -> requests.Session:
    if not hasattr(_local, "s"):
        _local.s = _session()
    return _local.s


def query(sql: str, timeout: float = 30) -> list[Row]:
    """Run a read-only SQL query and return rows as dicts."""
    r = _http().post(f"{API}/v1/query", json={"sql": sql}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"RawTree query failed ({r.status_code}): {r.text[:300]}")
    return r.json()["data"]


def insert(table: str, rows: list[Row], timeout: float = 5) -> None:
    """Append rows to a table in our team database."""
    r = _http().post(f"{API}/v1/tables/{table}", params={"database": TEAM}, json=rows, timeout=timeout)
    if r.status_code >= 300:
        raise RuntimeError(f"RawTree insert into {table} failed ({r.status_code}): {r.text[:300]}")

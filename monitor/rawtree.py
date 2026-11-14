"""Minimal RawTree HTTP client for the monitoring tools.

Reads TEAM_ID and RAWTREE_API_KEY from the repo's .env (or the environment). Never logs the key.
"""
from __future__ import annotations

import os
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
LEADERBOARD_STATE_URL = "https://datathon.rawtree.dev/api/state"

_http = requests.Session()
_http.headers["Authorization"] = f"Bearer {os.environ['RAWTREE_API_KEY']}"
_http.headers["User-Agent"] = "datathon-team-monitor/1.0"


def query(sql: str, timeout: float = 30) -> list[dict[str, Any]]:
    """Run a read-only SQL query and return rows as dicts."""
    r = _http.post(f"{API}/v1/query", json={"sql": sql}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"RawTree query failed ({r.status_code}): {r.text[:300]}")
    return r.json()["data"]


def leaderboard_state(timeout: float = 10) -> dict[str, Any]:
    """The public leaderboard JSON (no auth needed)."""
    r = requests.get(LEADERBOARD_STATE_URL, timeout=timeout,
                     headers={"User-Agent": "datathon-team-monitor/1.0"})
    r.raise_for_status()
    return r.json()

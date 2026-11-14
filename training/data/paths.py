"""Where the historical dataset lives, and a DuckDB connection over it.

- In an IVAN run: the version the job was submitted with (`ivan.data.path`).
- Elsewhere: $RAWTREE_DATA, else data/raw/rawtree_history in the repo (written by training.data.export_history).
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DATASET = "rawtree_history"
LOCAL = ROOT / "data" / "raw" / DATASET


def history_dir() -> Path:
    if os.environ.get("RAWTREE_DATA"):
        return Path(os.environ["RAWTREE_DATA"])
    if os.environ.get("IVAN_JOB_ID") or not LOCAL.exists():
        import ivan.data  # only needed on IVAN, or when there is no local export

        return Path(ivan.data.path(DATASET))
    return LOCAL


def con(folder: Path | None = None) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with views `catalog`, `sessions` (history_sessions) and `events` (history_events)."""
    f = (folder or history_dir()).as_posix()
    c = duckdb.connect()
    c.execute("SET TimeZone = 'UTC'")
    c.execute(f"CREATE VIEW catalog AS SELECT * FROM read_parquet('{f}/catalog.parquet')")
    c.execute(f"CREATE VIEW sessions AS SELECT * FROM read_parquet('{f}/history_sessions/*.parquet')")
    c.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{f}/history_events/*.parquet')")
    return c

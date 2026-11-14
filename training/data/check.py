"""Smoke check of the historical dataset: python -m training.data.check [data.version=N].

Compares manifest.json against the rows actually in the Parquet files. Run it on IVAN with
`ivan run --machine epochserver training.data.check --name data-check --hypothesis "..."`.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import hydra
import ivan  # noqa: F401  registers the ${ivan:...} resolvers
from omegaconf import DictConfig


def check(folder: Path) -> bool:
    manifest = json.loads((folder / "manifest.json").read_text())
    ok = True
    for table, info in manifest["tables"].items():
        pattern = folder / (f"{table}.parquet" if info.get("single_file") else f"{table}/*.parquet")
        actual = duckdb.execute(f"SELECT count(*) FROM read_parquet('{pattern.as_posix()}')").fetchall()[0][0]
        expected = info["rows"]
        status = "OK " if actual == expected == info.get("rawtree_rows", expected) else "BAD"
        ok &= status == "OK "
        print(f"{status} {table:18s} parquet={actual:>12,} manifest={expected:>12,} rawtree={info.get('rawtree_rows', '-')}")
    return ok


@hydra.main(version_base=None, config_path="../../conf", config_name="default")
def main(cfg: DictConfig) -> None:
    folder = Path(cfg.history)
    print(f"dataset folder: {folder}")
    if not check(folder):
        raise SystemExit("row counts do not match the manifest")
    print("all tables complete")


if __name__ == "__main__":
    main()

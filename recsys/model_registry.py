"""Opaque public model IDs, and the private log of what each one means.

The `model_version` we send with every submission must say NOTHING about our approach (other teams may be
able to read it). So we send a random ID like `m3f9a2c`, and keep the mapping to the real policy, its
parameters and the git commit in `recsys/model_versions.json` (this repo is private).

A new ID is created automatically the first time a policy runs live with a combination of
name, version and parameters that has not been seen before.

    python -m recsys.model_registry     # list every public ID and what it means
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .policies import Policy

FILE = Path(__file__).resolve().parent / "model_versions.json"
_SIMPLE = (int, float, str, bool)


def params(policy: Policy) -> dict[str, Any]:
    """The policy's tunable class attributes (simple values only), e.g. {'decay': 0.7, 'top_k': 20}."""
    out: dict[str, Any] = {}
    for cls in reversed(type(policy).__mro__):
        for k, v in vars(cls).items():
            if not k.startswith("_") and k not in ("name", "version") and isinstance(v, _SIMPLE):
                out[k] = v
    for k, v in vars(policy).items():  # per-instance overrides of those settings
        if k in out and isinstance(v, _SIMPLE):
            out[k] = v
    return dict(sorted(out.items()))


def _fingerprint(policy: Policy) -> str:
    key = json.dumps({"internal": policy.internal_version, "params": params(policy)}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _git_commit() -> str:
    try:
        root = Path(__file__).resolve().parent.parent
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                             text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "recsys"], cwd=root, capture_output=True,
                               text=True, timeout=5).stdout.strip()
        return f"{sha}{'+dirty' if dirty else ''}" if sha else "unknown"
    except Exception:
        return "unknown"


def load() -> list[dict[str, Any]]:
    return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else []


def public_id(policy: Policy, register: bool = True) -> str:
    """The opaque ID to send as `model_version`. Registers a new one if this policy setup is new.

    With register=False (dry runs) nothing is written and an unsaved ID is returned.
    """
    entries = load()
    fp = _fingerprint(policy)
    for e in entries:
        if e["fingerprint"] == fp:
            return e["public_id"]
    taken = {e["public_id"] for e in entries}
    new = f"m{secrets.token_hex(3)}"
    while new in taken:
        new = f"m{secrets.token_hex(3)}"
    if not register:
        return f"{new}-unsaved"
    doc = (inspect.getmodule(type(policy)).__doc__ or type(policy).__doc__ or "").strip()
    entries.append({
        "public_id": new,
        "internal": policy.internal_version,
        "params": params(policy),
        "description": doc.splitlines()[0] if doc else "",
        "git_commit": _git_commit(),
        "first_live_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fingerprint": fp,
    })
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, FILE)
    return new


def main() -> None:
    for e in load():
        print(f"{e['public_id']}  {e['internal']:<20} {e['first_live_utc']}  {e['git_commit']:<14} {e['params']}")
        if e["description"]:
            print(f"{'':9}{e['description']}")


if __name__ == "__main__":
    main()

"""Last check on every answer, whatever the policy: exactly 10 distinct, active product IDs, none of them a
product the shopper already bought (it almost never sells again: see profiles.py).

An invalid answer is replaced by the organisers' fallback and costs reliability points, so a buggy or
half-loaded policy must never be able to send one.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable

from .catalog import LiveCatalog

N_ITEMS = 10


def finalize(items: Iterable[str], catalog: LiveCatalog, fallback: Iterable[str],
             bought: Collection[str] = ()) -> tuple[list[str], Counter[str]]:
    """Clean `items` and pad them from `fallback`, leaving out products in `bought`.

    Returns the 10 IDs and what had to be fixed: `inactive` / `unknown` / `duplicate` / `bought` (policy proposed
    them), `padded` (filled from the fallback), `emergency` (fallback ran dry, filled from any active product).
    """
    out: list[str] = []
    issues: Counter[str] = Counter()
    for p in items:
        if len(out) == N_ITEMS:
            break
        if p in out:
            issues["duplicate"] += 1
        elif p in bought:
            issues["bought"] += 1
        elif catalog.is_active(p):
            out.append(p)
        else:
            issues["unknown" if catalog.get(p) is None else "inactive"] += 1

    kept = len(out)
    for source in (fallback, catalog.active_ids()):
        for p in source:
            if len(out) == N_ITEMS:
                break
            if p not in out and p not in bought and catalog.is_active(p):
                out.append(p)
        if len(out) == N_ITEMS:
            break
        issues["emergency"] = 1  # only reached if the fallback list could not fill the answer
    if len(out) > kept:
        issues["padded"] = len(out) - kept
    return out, issues

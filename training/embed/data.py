"""History -> numpy arrays for the two-tower model, with the fold split. Cached on local disk per fold.

Split (deterministic from hashes, fold f):
- time: train days 0-52, validate days >= 53 (day 0 = first UTC day of the history);
- held-out users: 10 % (crc32(user_id:f) % 10 == 0); all their carousels and events leave training;
- held-out products: 300, systematic sample over (subcategory, price tercile, random) order seeded by f; removed from
  training carousels (impression dropped), events, recent_views and histories.
"""
from __future__ import annotations

import json
import math
import os
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from training.data.paths import con, history_dir
from training.export import features as F

DAY_MS = 86_400_000
TRAIN_LAST_DAY = 52
N_HELDOUT_PRODUCTS = 300
CACHE_VERSION = 3
KEY = 10**13
# Compact contexts (no gaps where a product was removed), as in a real request. False reproduces runs before 01:00 Sun.
COMPACT = os.environ.get("RAWTREE_COMPACT", "1") == "1"  # user index * KEY + ts_ms: sortable composite key


def _log(msg: str) -> None:
    print(f"[data {time.strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class Data:
    # catalogue
    product_ids: np.ndarray
    vocab: dict  # name -> {value: index}
    prod: dict  # cat, sub, brand (int64), price (float32 [P,2]), tokens [P,T]
    sub_mean: dict
    global_mean: float
    heldout_products: np.ndarray  # bool [P]
    # users
    user_ids: np.ndarray
    heldout_users: np.ndarray  # bool [U]
    # sessions
    s: dict = field(default_factory=dict)
    # events, sorted by (user, ts), held-out products and users removed (history source)
    h: dict = field(default_factory=dict)
    # organic samples (indices into a full sorted event table)
    e: dict = field(default_factory=dict)
    popularity: np.ndarray | None = None  # organic purchases per product in training days (best-seller baseline)
    t0: int = 0


def _cache_dir() -> Path:
    base = Path(os.environ.get("RAWTREE_CACHE", Path.home() / ".cache" / "rawtree_embed"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _map_ids(sorted_ids: np.ndarray, values: np.ndarray) -> np.ndarray:
    """String ids -> index in sorted_ids, -1 if missing or None."""
    vals = np.where(values == None, "", values).astype(str)  # noqa: E711
    pos = np.searchsorted(sorted_ids, vals)
    pos = np.clip(pos, 0, len(sorted_ids) - 1)
    ok = sorted_ids[pos] == vals
    return np.where(ok, pos, -1).astype(np.int64)


def _hash_frac(ids: np.ndarray, salt: str) -> np.ndarray:
    return np.array([zlib.crc32(f"{u}:{salt}".encode()) % 10 for u in ids], dtype=np.int64)


def load(fold: int, folder: Path | None = None) -> Data:
    folder = folder or history_dir()
    cache = _cache_dir() / f"v{CACHE_VERSION}_fold{fold}.npz"
    meta_path = cache.with_suffix(".json")
    if cache.exists() and meta_path.exists():
        _log(f"cache hit {cache}")
        d = _from_cache(cache, meta_path)
    else:
        d = _build(fold, folder)
        _to_cache(d, cache, meta_path)
    # organic context never holds the target product itself: a purchase follows its own view and add-to-cart
    # (99.98 %), which would teach the model to copy the context; a carousel click is in recent_views only 9 %.
    rv = d.e["rv"]
    rv[rv == d.e["prod"][:, None]] = -1
    if COMPACT:
        d.e["rv"] = F.compact(rv)
    return d


def _build(fold: int, folder: Path) -> Data:
    t_start = time.time()
    c = con(folder)
    cat = c.execute("SELECT product_id, category, subcategory, brand, price_eur, description FROM catalog "
                    "ORDER BY product_id").fetchall()
    pids = np.array([r[0] for r in cat])
    vocab = {"cat": F.make_vocab(r[1] for r in cat), "sub": F.make_vocab(r[2] for r in cat),
             "brand": F.make_vocab(r[3] for r in cat)}
    logs = np.log(np.maximum([float(r[4]) for r in cat], 0.01))
    global_mean = float(logs.mean())
    sub_mean: dict[str, list] = {}
    for r, lp in zip(cat, logs):
        sub_mean.setdefault(r[2], []).append(lp)
    sub_mean = {k: float(np.mean(v)) for k, v in sub_mean.items()}
    prod = {
        "cat": F.lookup(vocab["cat"], [r[1] for r in cat]),
        "sub": F.lookup(vocab["sub"], [r[2] for r in cat]),
        "brand": F.lookup(vocab["brand"], [r[3] for r in cat]),
        "price": F.price_features([r[4] for r in cat], [r[2] for r in cat], sub_mean, global_mean),
        "tokens": F.token_matrix([r[5] for r in cat]),
    }
    P = len(pids)

    # held-out products: systematic sample over (subcategory, price tercile, random)
    rng = np.random.default_rng(1000 + fold)
    terc = np.digitize(logs, np.quantile(logs, [1 / 3, 2 / 3]))
    order = np.lexsort((rng.random(P), terc, prod["sub"]))
    step = P / N_HELDOUT_PRODUCTS
    pick = order[(np.arange(N_HELDOUT_PRODUCTS) * step + rng.random() * step).astype(int)]
    held_p = np.zeros(P, dtype=bool)
    held_p[pick] = True
    _log(f"catalogue {P} products, {held_p.sum()} held out")

    # sessions
    rv_cols = ", ".join(f"recent_views[len(recent_views) - {5 - i}].product_id AS rv{i}" for i in range(6))
    sh_cols = ", ".join(f"shown[{i + 1}] AS s{i}" for i in range(10))
    pr_cols = ", ".join(f"propensity[{i + 1}] AS q{i}" for i in range(10))
    sql = (f"SELECT epoch_ms(ts) AS ts_ms, user_id, device, region, page, len(recent_views) AS nrv, {rv_cols}, "
           f"{sh_cols}, {pr_cols}, clicked, purchased FROM sessions")
    tab = c.execute(sql).fetchnumpy()
    _log(f"sessions read: {len(tab['ts_ms'])} rows ({time.time() - t_start:.0f}s)")
    ts = tab["ts_ms"].astype(np.int64)
    t0 = int(ts.min() // DAY_MS * DAY_MS)

    ev = c.execute("SELECT epoch_ms(ts) AS ts_ms, event_type, user_id, product_id, device, region FROM events"
                   ).fetchnumpy()
    _log(f"events read: {len(ev['ts_ms'])} rows ({time.time() - t_start:.0f}s)")
    t0 = min(t0, int(ev["ts_ms"].astype(np.int64).min() // DAY_MS * DAY_MS))

    users = np.unique(np.concatenate([tab["user_id"].astype(str), ev["user_id"].astype(str)]))
    held_u = _hash_frac(users, str(fold)) == 0
    vocab["device"] = F.make_vocab(np.unique(tab["device"].astype(str)))
    vocab["region"] = F.make_vocab(np.unique(np.concatenate([tab["region"].astype(str), ev["region"].astype(str)])))
    vocab["page"] = F.make_vocab(list(np.unique(tab["page"].astype(str))) + [F.ORGANIC_PAGE])

    nrv = tab["nrv"].astype(np.int64)
    rv = np.full((len(ts), 6), -1, dtype=np.int64)
    for i in range(6):
        col = tab[f"rv{i}"]
        m = _map_ids(pids, np.asarray(col, dtype=object))
        valid = (5 - i) < nrv  # rv{i} is the (6-i)-th from the end
        rv[:, i] = np.where(valid, m, -1)
    shown = np.stack([_map_ids(pids, np.asarray(tab[f"s{i}"], dtype=object)) for i in range(10)], 1)
    prop = np.stack([np.nan_to_num(np.asarray(tab[f"q{i}"], dtype=np.float64), nan=1.0) for i in range(10)], 1)
    clicked = _map_ids(pids, np.asarray(tab["clicked"], dtype=object))
    purchased = _map_ids(pids, np.asarray(tab["purchased"], dtype=object))
    click_slot = np.where((shown == clicked[:, None]) & (clicked[:, None] >= 0), np.arange(10), 99).min(1)
    click_slot = np.where(click_slot == 99, -1, click_slot)
    s = {
        "ts": ts, "day": (ts - t0) // DAY_MS, "user": _map_ids(users, tab["user_id"].astype(str)),
        "device": F.lookup(vocab["device"], tab["device"].astype(str)),
        "region": F.lookup(vocab["region"], tab["region"].astype(str)),
        "page": F.lookup(vocab["page"], tab["page"].astype(str)),
        "hour": ((ts // 3_600_000) % 24).astype(np.int64),
        "rv": rv, "shown": shown, "prop": prop.astype(np.float32), "click_slot": click_slot,
        "purchased": (purchased >= 0) & (purchased == clicked),
    }
    del tab

    # events: full table sorted by (user, ts)
    e_user = _map_ids(users, ev["user_id"].astype(str))
    e_ts = ev["ts_ms"].astype(np.int64)
    e_prod = _map_ids(pids, np.asarray(ev["product_id"], dtype=object))
    e_type = np.array([F.EVENT_TYPES.get(t, 0) for t in ev["event_type"].astype(str)], dtype=np.int64)
    e_dev = F.lookup(vocab["device"], ev["device"].astype(str))
    e_reg = F.lookup(vocab["region"], ev["region"].astype(str))
    del ev
    ok = e_prod >= 0
    o = np.lexsort((e_ts, e_user))
    o = o[ok[o]]
    e_user, e_ts, e_prod, e_type, e_dev, e_reg = (a[o] for a in (e_user, e_ts, e_prod, e_type, e_dev, e_reg))
    e_day = (e_ts - t0) // DAY_MS
    _log(f"events sorted ({time.time() - t_start:.0f}s)")

    # history source: held-out products and held-out users removed
    hk = ~held_p[e_prod] & ~held_u[e_user]
    h = {"user": e_user[hk], "ts": e_ts[hk], "prod": e_prod[hk], "type": e_type[hk]}
    h["key"] = h["user"] * KEY + h["ts"]
    h_lo_user = np.searchsorted(h["key"], np.arange(len(users) + 1) * KEY)  # first index of each user

    # per-session history window: events before the session's day start
    day_start = t0 + s["day"] * DAY_MS
    s["hist_end"] = np.searchsorted(h["key"], s["user"] * KEY + day_start)
    s["hist_lo"] = h_lo_user[s["user"]]

    # organic samples: every event; context = previous events of the user within 30 min (full table, so that
    # validation sees held-out products in context), history = filtered events before the day start
    n = len(e_ts)
    rec = np.full((n, F.MAX_RECENT), -1, dtype=np.int64)
    for k in range(1, F.MAX_RECENT + 1):
        prev = np.arange(n) - k
        pv = np.clip(prev, 0, None)
        valid = (prev >= 0) & (e_user[pv] == e_user) & (e_ts - e_ts[pv] <= 1_800_000)
        rec[:, F.MAX_RECENT - k] = np.where(valid, e_prod[pv], -1)  # oldest first
    e = {"user": e_user, "ts": e_ts, "day": e_day, "prod": e_prod, "type": e_type, "device": e_dev,
         "region": e_reg, "hour": ((e_ts // 3_600_000) % 24).astype(np.int64), "rv": rec,
         "hist_end": np.searchsorted(h["key"], e_user * KEY + t0 + e_day * DAY_MS),
         "hist_lo": h_lo_user[e_user]}
    pop = np.bincount(e_prod[(e_type == 2) & (e_day <= TRAIN_LAST_DAY)], minlength=P).astype(np.float64)
    _log(f"built fold {fold} in {time.time() - t_start:.0f}s")
    return Data(product_ids=pids, vocab=vocab, prod=prod, sub_mean=sub_mean, global_mean=global_mean,
                heldout_products=held_p, user_ids=users, heldout_users=held_u, s=s, h=h, e=e, popularity=pop, t0=t0)


def _to_cache(d: Data, path: Path, meta_path: Path) -> None:
    arrays = {"product_ids": d.product_ids, "heldout_products": d.heldout_products, "user_ids": d.user_ids,
              "heldout_users": d.heldout_users, "popularity": d.popularity}
    for name, part in (("prod", d.prod), ("s", d.s), ("h", d.h), ("e", d.e)):
        for k, v in part.items():
            arrays[f"{name}__{k}"] = v
    tmp = path.with_name(path.stem + f".{os.getpid()}.tmp.npz")
    np.savez(tmp, **arrays)
    os.replace(tmp, path)
    meta_path.write_text(json.dumps({"vocab": d.vocab, "sub_mean": d.sub_mean, "global_mean": d.global_mean,
                                     "t0": d.t0}))


def _from_cache(path: Path, meta_path: Path) -> Data:
    z = np.load(path, allow_pickle=False)
    meta = json.loads(meta_path.read_text())
    parts: dict[str, dict] = {"prod": {}, "s": {}, "h": {}, "e": {}}
    for k in z.files:
        if "__" in k:
            a, b = k.split("__", 1)
            parts[a][b] = z[k]
    return Data(product_ids=z["product_ids"], vocab=meta["vocab"], prod=parts["prod"], sub_mean=meta["sub_mean"],
                global_mean=meta["global_mean"], heldout_products=z["heldout_products"], user_ids=z["user_ids"],
                heldout_users=z["heldout_users"], s=parts["s"], h=parts["h"], e=parts["e"],
                popularity=z["popularity"], t0=meta["t0"])


# Attention per slot, product-adjusted (docs/EMBED_SWEEPS_FINAL.md, "Slot bias"), and slot 10 per device.
THETA = np.array([1, 0.62, 0.50, 0.42, 0.37, 0.36, 0.33, 0.31, 0.29, 0.28])
THETA10_DEVICE = {"android": 0.22, "ios": 0.32, "web": 0.32}


def theta_table(device_vocab: dict[str, int]) -> np.ndarray:
    """log theta [10, n_device + 1]: the overall curve, scaled per device to its measured slot-10 value."""
    n = len(device_vocab) + 1
    out = np.tile(np.log(THETA)[:, None], (1, n))
    for name, idx in device_vocab.items():
        t10 = THETA10_DEVICE.get(name)
        if t10:
            out[:, idx] = np.log(THETA) * math.log(t10) / math.log(THETA[-1])
    return out.astype(np.float32)

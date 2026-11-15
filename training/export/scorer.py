"""Numpy-only scorer for the two-tower model (no torch). Serving package for recsys.

    from training.export.scorer import load
    model = load("models/v0")                          # folder with model.npz (+ user_vectors.npz)
    pm = model.embed_products(rows)                    # once at startup; rows: dicts with product_id, category,
                                                       # subcategory, brand, description, price (ORIGINAL price)
    pm = model.embed_products(new_rows, pm)            # append new products (returns a new ProductMatrix)
    scores = model.score(request, pm)                  # one score per row of pm, in pm.ids order
    scores = model.score(request, pm, events=[("p_123", "purchase"), ...])   # optional live events, oldest first

The score is the log-odds that the shopper buys the product when shown in slot 1. `request` is a recsys Request (or
any object/dict with user_id, is_new_user, device, region, page, recent_views, ts_ms).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:  # works both as training.export.scorer and as a copied stand-alone module
    from training.export import features as F
except ImportError:  # pragma: no cover
    import features as F  # type: ignore


def _relu(x):
    return np.maximum(x, 0.0)


def _log_sigmoid(x):
    return -np.logaddexp(0.0, -x)


@dataclass
class ProductMatrix:
    ids: list
    vecs: np.ndarray  # [P, d] float32
    bias: np.ndarray  # [P] float32
    index: dict

    def __len__(self):
        return len(self.ids)


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class Model:
    def __init__(self, folder: str | Path):
        folder = Path(folder)
        z = np.load(folder / "model.npz", allow_pickle=False)
        self.w = {k: z[k] for k in z.files if not k.startswith("meta__")}
        meta = json.loads(str(z["meta__json"]))
        self.meta = meta
        self.vocab = meta["vocab"]
        self.sub_mean = meta["sub_mean"]
        self.global_mean = meta["global_mean"]
        self.use_desc = meta["use_desc"]
        self.use_price = meta["use_price"]
        self.pooling = meta["pooling"]
        self.recency = meta["recency"]
        self.d = int(meta["dim"])
        self.id_index = {pid: i for i, pid in enumerate(z["meta__id_products"].tolist())}
        self.id_has = z["meta__id_has"].astype(np.float32)
        self.type_w = self.w["type_w"]
        self.user_index: dict = {}
        self.user_vecs = np.zeros((0, self.d), dtype=np.float32)
        self.user_counts = None
        self.user_carts = None
        uv = folder / "user_vectors.npz"
        if uv.exists():
            u = np.load(uv, allow_pickle=False)
            self.user_index = {k: i for i, k in enumerate(u["user_ids"].tolist())}
            self.user_vecs = u["vectors"].astype(np.float32)
            self.user_counts = u["counts"] if "counts" in u.files else None
            if "cart_ids" in u.files:  # open cart at export time, per user row
                ids, off = u["cart_ids"].tolist(), u["cart_off"]
                self.user_carts = [ids[off[i]:off[i + 1]] for i in range(len(off) - 1)]
        # a history shorter than this is ignored (a very short history scores worse than none)
        self.min_hist = int(meta.get("min_history_events", 0))
        self.cart_window = int(meta.get("cart_window", 50))

    # ---------------- products ----------------
    def embed_products(self, rows, base: ProductMatrix | None = None) -> ProductMatrix:
        rows = list(rows)
        w = self.w
        cat = F.lookup(self.vocab["cat"], [_get(r, "category") for r in rows])
        sub = F.lookup(self.vocab["sub"], [_get(r, "subcategory") for r in rows])
        brand = F.lookup(self.vocab["brand"], [_get(r, "brand") for r in rows])
        price = F.price_features([_get(r, "price", _get(r, "price_eur")) for r in rows],
                                 [_get(r, "subcategory") for r in rows], self.sub_mean, self.global_mean)
        if not self.use_price:
            price = np.zeros_like(price)
        if self.use_desc:
            tok = F.token_matrix([_get(r, "description") for r in rows])
            tm = (tok > 0).astype(np.float32)
            desc = (w["e_tok.weight"][tok] * tm[..., None]).sum(1) / np.maximum(tm.sum(1, keepdims=True), 1)
        else:
            desc = np.zeros((len(rows), w["e_cat.weight"].shape[1]), dtype=np.float32)
        x = np.concatenate([w["e_cat.weight"][cat], w["e_sub.weight"][sub], w["e_brand.weight"][brand], price, desc],
                           1).astype(np.float32)
        h = _relu(x @ w["p1.weight"].T + w["p1.bias"])
        v = h @ w["p2.weight"].T + w["p2.bias"]
        b = (h @ w["p_bias.weight"].T + w["p_bias.bias"])[:, 0]
        no_id = float(w["no_id"]) if "no_id" in w else 0.0
        for i, r in enumerate(rows):
            j = self.id_index.get(str(_get(r, "product_id")))
            if j is not None and self.id_has[j] > 0:
                v[i] += w["e_id.weight"][j]
                b[i] += w["b_id.weight"][j, 0]
            else:
                b[i] += no_id
        ids = [str(_get(r, "product_id")) for r in rows]
        v, b = v.astype(np.float32), b.astype(np.float32)
        if base is not None:
            ids = list(base.ids) + ids
            v = np.concatenate([base.vecs, v])
            b = np.concatenate([base.bias, b])
        return ProductMatrix(ids=ids, vecs=v, bias=b, index={p: i for i, p in enumerate(ids)})

    # ---------------- users ----------------
    def user_vector(self, events, pm: ProductMatrix):
        """Pooled vector of a user's events [(product_id, event_type), ...], oldest first; None if none usable."""
        n = int(self.meta["history_len"])
        if n <= 0 or not events or len(events) < self.min_hist:
            return None
        rows = [(pm.index.get(str(p)), F.EVENT_TYPES.get(str(t), 0)) for p, t in list(events)[-n:]]
        rows = [(i, t) for i, t in rows if i is not None]
        if not rows:
            return None
        idx = np.array([i for i, _ in rows])
        wt = self.type_w[np.array([t for _, t in rows])]
        return (pm.vecs[idx] * wt[:, None]).sum(0) / wt.sum()

    def _user(self, request, pm: ProductMatrix, events=None, hist=None):
        w = self.w
        dev = self.vocab["device"].get(str(_get(request, "device")), 0)
        reg = self.vocab["region"].get(str(_get(request, "region")), 0)
        page = self.vocab["page"].get(str(_get(request, "page")), 0)
        ts = _get(request, "ts_ms")
        hour = int((int(ts) // 3_600_000) % 24) if ts is not None else 12
        ctx = np.concatenate([w["e_dev.weight"][dev], w["e_reg.weight"][reg], w["e_page.weight"][page],
                              w["e_hour.weight"][hour]]).astype(np.float32)
        rv = [pm.index.get(str(p)) for p in list(_get(request, "recent_views") or ())[-F.MAX_RECENT:]]
        rv = [i for i in rv if i is not None]
        if rv:
            vec = pm.vecs[np.array(rv)]
            if self.pooling == "attention":
                q = w["att_q.weight"] @ ctx + w["att_q.bias"]
                lg = vec @ q / np.sqrt(self.d)
                a = np.exp(lg - lg.max())
            elif self.pooling == "mean":
                a = np.ones(len(rv), dtype=np.float32)
            else:
                a = self.recency ** np.arange(len(rv) - 1, -1, -1, dtype=np.float32)
            rec = (vec * (a / a.sum())[:, None]).sum(0)
            rec_has = 1.0
        else:
            rec, rec_has = np.zeros(self.d, dtype=np.float32), 0.0
        if hist is None and int(self.meta["history_len"]) > 0:
            if events:
                hist = self.user_vector(events, pm)
            if hist is None:
                j = self.user_index.get(str(_get(request, "user_id")))
                if j is not None and (self.user_counts is None or self.user_counts[j] >= self.min_hist):
                    hist = self.user_vecs[j]
        hist_has = 1.0 if hist is not None else 0.0
        hist = hist if hist is not None else np.zeros(self.d, dtype=np.float32)
        x = np.concatenate([ctx, rec, [rec_has], hist * hist_has, [hist_has]]).astype(np.float32)
        h = x @ w["u1.weight"].T + w["u1.bias"] + float(bool(_get(request, "is_new_user"))) * w["w_new"]
        u = _relu(h) @ w["u2.weight"].T + w["u2.bias"]
        cart = self.open_cart(request, pm, events)
        if "cart_w.weight" in w and cart:
            vec = pm.vecs[np.array(cart)].mean(0)
            u = u + w["cart_w.weight"] @ np.concatenate([vec, [1.0]]).astype(np.float32)
        return u, cart

    def open_cart(self, request, pm: ProductMatrix, events=None) -> list:
        """Row indices in pm of the user's open cart: added to cart and not bought since, within the last
        cart_window events. From `events` when given, else the cart saved at export time."""
        if "cart_w.weight" not in self.w:
            return []
        if events:
            out, bought, seen = [], set(), set()
            for p, t in reversed(list(events)[-self.cart_window:]):
                p, t = str(p), str(t)
                if t == "purchase":
                    bought.add(p)
                elif t == "add_to_cart" and p not in bought and p not in seen:
                    seen.add(p)
                    out.append(p)
        else:
            j = self.user_index.get(str(_get(request, "user_id")))
            out = self.user_carts[j] if (j is not None and self.user_carts is not None) else []
        return [pm.index[p] for p in out if p in pm.index]

    # ---------------- score ----------------
    def score(self, request, pm: ProductMatrix, events=None, hist=None) -> np.ndarray:
        u, cart = self._user(request, pm, events, hist)
        gain = float(self.w["new_gain"]) if "new_gain" in self.w else 0.0
        x = pm.vecs @ u + pm.bias * (1.0 + gain * float(bool(_get(request, "is_new_user"))))
        w = self.w
        if cart and "cart_beta" in w:
            x[np.array(cart)] += float(w["cart_beta"])
        lc = _log_sigmoid(x + w["c_click"]) + _log_sigmoid(w["alpha"] * x + w["c_purchase"])
        sc = lc - np.log1p(-np.minimum(np.exp(lc), 1 - 1e-7))
        return (float(w.get("score_a", 1.0)) * sc + float(w.get("score_c", 0.0))).astype(np.float32)


def load(folder: str | Path) -> Model:
    return Model(folder)

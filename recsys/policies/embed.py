"""Two-tower embedding model (training/export/scorer.py), plain: top scores, no live corrections.

The model folder comes from $EMBED_MODEL (default models/v0): model.npz (+ user_vectors.npz). Products are embedded
once at fit with their ORIGINAL price (shop.catalog price, or the price in their `new_product` row) and again for
each product the catalogue adds later. Bas's correction layer (discounts, trends) goes on top of `scores()`.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

from .. import client
from .base import Policy, Request

ROOT = Path(__file__).resolve().parents[2]


class Embed(Policy):
    name = "embed"
    version = "v0"

    def fit(self) -> None:
        from training.export.scorer import load

        folder = Path(os.environ.get("EMBED_MODEL", ROOT / "models" / "v0"))
        self.model = load(folder)
        self.version = f"v0-{folder.name}"
        rows = client.query("SELECT product_id::String AS product_id, price_eur::Float64 AS p FROM shop.catalog")
        self.ref_price = {r["product_id"]: float(r["p"]) for r in rows}
        rows = client.query("SELECT product_id::String AS product_id, any(price_eur::Float64) AS p "
                            "FROM shop.catalog_updates WHERE change::String = 'new_product' GROUP BY product_id")
        self.ref_price.update({r["product_id"]: float(r["p"]) for r in rows if r["product_id"] not in self.ref_price})
        self._lock = threading.Lock()
        self.pm = None
        self._embed_missing()

    def _rows(self, products):
        return [dict(product_id=p.product_id, category=p.category, subcategory=p.subcategory, brand=p.brand,
                     description=p.description, price=self.ref_price.get(p.product_id, p.price_eur))
                for p in products]

    def _embed_missing(self) -> None:
        with self._lock:
            have = self.pm.index if self.pm is not None else {}
            todo = [p for p in self.catalog.snapshot() if p.product_id not in have]
            for p in todo:
                self.ref_price.setdefault(p.product_id, p.price_eur)
            if todo or self.pm is None:
                self.pm = self.model.embed_products(self._rows(todo), self.pm)
            self._seen_version = self.catalog.version

    def scores(self, req: Request) -> tuple[list[str], np.ndarray]:
        """Product ids and the model's scores (purchase log-odds in slot 1)."""
        if self.catalog.version != self._seen_version:
            self._embed_missing()
        pm = self.pm
        return pm.ids, self.model.score(req, pm)

    def recommend(self, req: Request) -> list[str]:
        ids, s = self.scores(req)
        out = []
        for i in np.argsort(-s):
            pid = ids[i]
            if self.catalog.is_active(pid):
                out.append(pid)
                if len(out) == 10:
                    break
        return out

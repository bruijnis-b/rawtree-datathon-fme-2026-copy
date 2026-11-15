"""Feature encoding shared by training and the numpy scorer (numpy and the standard library only).

Every categorical vocabulary reserves index 0 for "unknown". The description is a hashed bag of words.
"""
from __future__ import annotations

import math
import re
import zlib

import numpy as np

N_TOKENS = 4096  # hash buckets for description words (index 0 = padding)
MAX_TOKENS = 24
MAX_RECENT = 6
EVENT_TYPES = {"view": 0, "add_to_cart": 1, "purchase": 2}
ORGANIC_PAGE = "__organic__"
WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str | None) -> list[int]:
    words = WORD.findall((text or "").lower())[:MAX_TOKENS]
    return [1 + zlib.crc32(w.encode()) % (N_TOKENS - 1) for w in words]


def token_matrix(texts) -> np.ndarray:
    out = np.zeros((len(texts), MAX_TOKENS), dtype=np.int64)
    for i, t in enumerate(texts):
        ids = tokens(t)
        out[i, : len(ids)] = ids
    return out


def lookup(vocab: dict[str, int], values) -> np.ndarray:
    return np.array([vocab.get(str(v), 0) if v is not None else 0 for v in values], dtype=np.int64)


def make_vocab(values) -> dict[str, int]:
    return {v: i + 1 for i, v in enumerate(sorted({str(x) for x in values if x is not None}))}


def price_features(prices, subcats, sub_mean: dict[str, float], global_mean: float) -> np.ndarray:
    """[log price, log price minus its subcategory's mean log price], from the reference (original) price."""
    out = np.zeros((len(prices), 2), dtype=np.float32)
    for i, (p, s) in enumerate(zip(prices, subcats)):
        lp = math.log(max(float(p), 0.01)) if p is not None else global_mean
        out[i, 0] = lp - global_mean
        out[i, 1] = lp - sub_mean.get(str(s), global_mean)
    return out


def compact(rv: np.ndarray) -> np.ndarray:
    """Context rows [n, k] of product indices (-1 = none), oldest first: move the -1 gaps to the front, keeping the
    order of the real entries, so a context looks like a request's recent_views (which never has gaps)."""
    order = np.argsort((rv >= 0).astype(np.int8), axis=1, kind="stable")
    return np.take_along_axis(rv, order, axis=1)

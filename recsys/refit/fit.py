"""Fit embed_score's weights on the rows from build.py: python -m recsys.refit.fit v1 [--after '2026-11-14 21:00']

A logistic regression of "was the shown product bought" on the model score and the shopper factors, with list
position as dummies (so position does not leak into the weights), bought-before products left out (the policy
drops them). --after: use only answers from that UTC time on, e.g. after the end of the model's live fine-tuning
data, so the model is never scored on data it was trained on.

Prints (1) purchase AUC on half of the requests, fitted on the other half, for the model alone, the shopper factors
alone and both; (2) the weights fitted on each half and on all rows; (3) the embed_score settings, scaled so the model
keeps score_weight 1 (only ratios matter for the ranking), ready for --set or an arms file.
"""
from __future__ import annotations

import argparse
import zlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from .download import OUT

FACTORS = ["lpop", "cat", "sub", "ctx", "recent", "cart", "new"]
SETS = {"model only": ["s"], "shopper factors only": FACTORS, "model + shopper factors": ["s", *FACTORS]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model", help="the name build.py used, e.g. v1")
    ap.add_argument("--after", default=None, help="UTC 'YYYY-MM-DD HH:MM': only answers from then on")
    args = ap.parse_args()
    d = pd.read_parquet(OUT / f"ds_{args.model}.parquet")
    d = d[d.s.notna() & ~d.bought].copy()
    if args.after:
        ms = datetime.strptime(args.after, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() * 1000
        d = d[d.t >= ms]
    d["lpop"] = np.log(d["pop"] + 1e-5)
    for c in ("ctx", "recent", "cart", "new"):
        d[c] = d[c].astype(float)
    y = d.purch.values
    half = d.r.map(lambda r: zlib.crc32(r.encode()) % 2).values
    pos = pd.get_dummies(d.pos, prefix="pos", drop_first=True).astype(float)
    print(f"{len(d)} shown products, {int(y.sum())} purchases, {d.r.nunique()} answers\n")

    def fit(cols, mask):
        X = pd.concat([d[cols], pos], axis=1).values
        return LogisticRegression(C=1.0, max_iter=3000).fit(X[mask], y[mask]).coef_[0][:len(cols)]

    print("purchase AUC on the other half (0.5 = random); position left out of the score")
    for name, cols in SETS.items():
        aucs = [roc_auc_score(y[half == b], d[cols].values[half == b] @ fit(cols, half == a)) for a, b in ((0, 1), (1, 0))]
        print(f"  {name:28s} {np.mean(aucs):.4f}  (halves {aucs[0]:.4f}, {aucs[1]:.4f})")
    cols = SETS["model + shopper factors"]
    print("\nweights (log-odds), model + shopper factors")
    for name, mask in (("half 0", half == 0), ("half 1", half == 1), ("all", np.ones(len(d), bool))):
        c = fit(cols, mask)
        print(f"  {name:6s} " + " ".join(f"{k}={v:+.2f}" for k, v in zip(cols, c)))
    sw = c[0]
    s = dict(alpha=c[1] / sw, w_cat=c[2] / sw, w_sub=c[3] / sw, ctx=np.exp(c[4] / sw), recent=np.exp(c[5] / sw),
             cart=np.exp(c[6] / sw), new=np.exp(c[7] / sw))
    print("\nembed_score settings (score_weight 1):")
    print("  " + ",".join(f"{k}={v:.2f}" for k, v in s.items()))


if __name__ == "__main__":
    main()

"""Phase B style table: per configuration, mean over folds and seeds. python -m training.embed.aggregate embed-b [--md f]

Groups runs by their overrides without data.fold / train.seed. Selection value: mean objective minus one standard
error (SE = sd / sqrt(n)). Also: slate_auc, organic recall, new-user and new-product lifts (ips_hit@10), calibration
after recalibration, held-out share of top-10 / share of clicks, p99 latency, checks passed.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from training.embed.collect import ROOT, runs


def slice_lift(path: Path, metric: str, sl: str):
    f = path / "ivan" / "records" / "metrics.jsonl"
    if not f.exists():
        return None
    for line in f.read_text().splitlines():
        d = json.loads(line)
        if d["metric"] == metric and d["slice"] == sl:
            return d["lift"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("experiments", nargs="+")
    ap.add_argument("--md")
    a = ap.parse_args()
    groups = defaultdict(list)
    for e in a.experiments:
        for r in runs(e):
            key = re.sub(r"\s*(data\.fold|train\.seed)=\S+", "", r["overrides"]).strip() or "default"
            r["path"] = ROOT / r["run"]
            groups[key].append(r)
    rows = []
    for key, rs in groups.items():
        S = [r["summary"] for r in rs]
        get = lambda k: np.array([s.get(k) for s in S if s.get(k) is not None], dtype=float)  # noqa: E731
        obj = get("objective")
        se = obj.std(ddof=1) / np.sqrt(len(obj)) if len(obj) > 1 else float("nan")
        ratio = np.array([s["heldout_share_top10"] / s["heldout_share_clicks"] for s in S
                          if s.get("heldout_share_top10") is not None and s.get("heldout_share_clicks")])
        nu = np.array([v for v in (slice_lift(r["path"], "ips_hit@10", "new_user") for r in rs) if v is not None])
        npd = np.array([v for v in (slice_lift(r["path"], "ips_hit@10", "new_product") for r in rs) if v is not None])
        passed = sum(all(c.get("passed") for c in r["checks"]) for r in rs)
        rows.append(dict(config=key, n=len(rs), mean=obj.mean(), se=se, sel=obj.mean() - se,
                         cold=get("lift_cold").mean(), new_user=nu.mean() if len(nu) else np.nan,
                         new_product=npd.mean() if len(npd) else np.nan, slate=get("slate_auc").mean(),
                         org=get("organic_recall").mean(), cal=get("calibration_max_err").mean(),
                         cal_max=get("calibration_max_err").max(), ratio=ratio.mean() if len(ratio) else np.nan,
                         ratio_min=ratio.min() if len(ratio) else np.nan,
                         ratio_max=ratio.max() if len(ratio) else np.nan,
                         p99=get("latency_p99_ms").max(), passed=passed))
    rows.sort(key=lambda r: -r["sel"])
    lines = ["| # | configuration | runs | objective (mean ± SE) | mean − SE | lift cold | new user | new product | "
             "slate_auc | org. recall | calibration (mean / max) | held-out top-10 ÷ clicks (mean, range) | "
             "p99 ms (max) | runs passing all checks |", "|" + "---|" * 14]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['config'][:80]} | {r['n']} | {r['mean']:.3f} ± {r['se']:.3f} | {r['sel']:.3f} | "
                     f"{r['cold']:.2f} | {r['new_user']:.2f} | {r['new_product']:.2f} | {r['slate']:.3f} | "
                     f"{r['org']:.3f} | {r['cal']:.2f} / {r['cal_max']:.2f} | {r['ratio']:.2f} "
                     f"({r['ratio_min']:.2f}–{r['ratio_max']:.2f}) | {r['p99']:.2f} | {r['passed']}/{r['n']} |")
    text = "\n".join(lines)
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

"""Write description.md for a serving package: what the model embeds, what it focuses on, how it scores.

    python -m training.export.describe <export folder> [--name v1] [--note "free text"]

Reads only the folder itself (config.yaml, finetune.yaml if fine-tuned, metrics.json, model.npz, README.txt), so it
works on any export, old or new. Training and fine-tuning call write() at the end of every run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

POOLING = {"recency": "a recency-weighted mean (the newest view counts most, each step back × {decay})",
           "mean": "a plain mean", "attention": "attention (weights from the request context)"}


def _load(folder: Path):
    cfg = yaml.safe_load((folder / "config.yaml").read_text())
    ft = yaml.safe_load((folder / "finetune.yaml").read_text()) if (folder / "finetune.yaml").exists() else None
    met = json.loads((folder / "metrics.json").read_text()) if (folder / "metrics.json").exists() else {}
    readme = (folder / "README.txt").read_text() if (folder / "README.txt").exists() else ""
    n_users = None
    if (folder / "user_vectors.npz").exists():
        import numpy as np
        n_users = len(np.load(folder / "user_vectors.npz")["user_ids"])
    return cfg, ft, met, readme, n_users


def _metric(met, dataset, metric, sl):
    for m in met.get("metrics", []):
        if m["dataset"] == dataset and m["metric"] == metric and m["slice"] == sl:
            return m
    return None


def _num(x) -> bool:
    """A real, finite number (runs without a live hold-out leave NaN or None)."""
    return isinstance(x, (int, float)) and x == x and abs(x) != float("inf")


def _fmt(m, key="lift"):
    if not m or not _num(m.get(key)) or (key == "lift" and not (_num(m.get("lift_lo")) and _num(m.get("lift_hi")))):
        return "–"
    if key == "lift":
        return f"{m['lift']:+.2f} [{m['lift_lo']:+.2f}, {m['lift_hi']:+.2f}]"
    return f"{m[key]:.3f}"


def text(folder: Path, name: str | None = None, note: str | None = None) -> str:
    cfg, ft, met, readme, n_users = _load(folder)
    s = met.get("summary", {})
    mo, tr, org, loss = cfg["model"], cfg["train"], cfg["organic"], cfg["loss"]
    name = name or folder.name
    fine = ft is not None
    lines = [f"# Model {name}", ""]
    run = next((ln.split(": ", 1)[1] for ln in readme.splitlines() if ln.startswith("experiment:")), "?")
    commit = next((ln.split(": ", 1)[1] for ln in readme.splitlines() if ln.startswith("git commit:")), "?")
    base = next((ln.split(": ", 1)[1] for ln in readme.splitlines() if ln.startswith("base:")), None)
    lines += [f"IVAN experiment `{run}`, git `{commit}`" + (f", fine-tuned from `{base}`" if base else "") + ".", ""]
    if note:
        lines += [note, ""]

    lines += ["## In one paragraph", "",
              "A two-tower recommender. One tower turns a product into a vector of "
              f"{mo['dim']} numbers, the other turns a shopper's request into a vector of the same size; the score of a "
              "product is how well the two line up (dot product) plus a per-product bias. The score is calibrated as "
              "the **log-odds that the shopper buys the product when it is shown in slot 1**, so corrections (discount, "
              "trend) can be added to it. "
              + ("It was trained on the 60-day history and then fine-tuned on the live practice stream, so it has seen "
                 "today's new users and new products." if fine else
                 "It was trained on the 60-day history only: it has never seen a new user or a new product with labels."),
              ""]

    lines += ["## What it embeds", "", "**Product tower** (no request input, so product vectors are computed once):", ""]
    lines += ["- category, subcategory and brand: learned vectors;",
              "- reference price (the product's original price, never the current one): its log, and its log minus "
              "the subcategory's mean log price" + ("" if mo.get("price", True) else " (switched off in this model)") + ";",
              "- description: " + ("a bag of words (hashed into 4,096 buckets, averaged)" if mo.get("description")
                                    else "not used") + ";",
              f"- a learned vector per known product (its identity), hidden in training {mo['id_dropout']:.0%} of the "
              "time so the content path also learns to score a product alone"
              + (f"; during fine-tuning the practice-round products hid theirs {ft['ft']['new_id_dropout']:.0%} of the "
                 "time" if fine else "") + ";",
              "- a bias from the content (expected popularity), plus a learned offset for products without an identity "
              "vector (every new product at serving time).", ""]
    hl = int(mo["history_len"])
    lines += ["**User tower** (from the request, plus the user's history if known):", ""]
    lines += ["- device, region, page, hour of day: learned vectors;",
              f"- `recent_views` (up to 6 products from the request): their product vectors, pooled by "
              f"{POOLING.get(mo['pooling'], mo['pooling']).format(decay=mo.get('recency_decay', 0.7))};",
              (f"- long-term history: the product vectors of the user's last {hl} events (views 1×, add-to-carts 2×, "
               f"purchases 4×), averaged; dropped entirely in {mo['history_dropout']:.0%} of training examples so the "
               "model also works without it. Known users' history vectors are precomputed in `user_vectors.npz`"
               + (f" ({n_users:,} users)" if n_users else "")
               + "; live events can be passed with `score(..., events=...)`." if hl > 0 else
               "- long-term history: not used (this model only looks at the request);"),
              "- `is_new_user`: an input whose weights start at zero; "
              + ("learned during the live fine-tuning." if fine else "ignored by this model (the history has no flag)."),
              "- no per-user identity vector: a user is described only by what they do.", ""]

    lines += ["## How it was trained, and why", ""]
    lines += ["- **Two tasks on shared towers.** (1) Carousel: did the shopper click each of the 10 shown products, "
              "and buy after clicking. (2) Organic: which product did the shopper view, add to cart or buy next on "
              f"the site (weight {org['weight']}; purchases sampled {org['type_weights'][2]:.0f}× as often as views), "
              "against the other products in the batch, corrected for popularity (logQ)"
              + ("" if org.get("logq", True) else " (no correction in this model)") + ". The organic task covers the "
              "whole catalogue, where the old carousel only shows a few products; without it the model is much worse.",
              "- **Old-carousel bias removed.** A slot term (attention by slot and device) is learned in the click "
              "head and dropped at serving; products shown only by the old policy's choice are not treated as "
              "negatives elsewhere.",
              f"- Settings: dimension {mo['dim']}, hidden layer {mo['hidden']}, click weight {loss['click_weight']}, "
              f"learning rate {tr['lr']}, weight decay {tr['weight_decay']}, batch {tr['batch_size']}, "
              f"{tr['epochs']} epochs" + (f", trained on fold {cfg['data']['fold']} (10 % of users and 300 products "
                                         "held out to test cold start)" if not cfg["data"].get("all") else
                                         ", trained on all history (no hold-out)") + "."]
    if fine:
        f = ft["ft"]
        lines += [f"- **Live fine-tuning:** {f['epochs']} epochs over the live organic events (live dataset "
                  f"v{ft['live']['version']}), {f['history_share']:.0%} of each batch from the history to avoid forgetting, "
                  f"learning rate {f['lr_mult']}× the history rate, weights trained: {f['train']}, carousel feedback "
                  f"task {'on' if f['feedback'] else 'off'}"
                  + (" (with a live hold-out: 20 % of live users, the last 2 hours, 60 practice products)"
                     if f["holdout"] else " (on all live data, no hold-out)") + "."]
    if _num(s.get("score_a")):
        lines += [f"- **Recalibration:** the final score is `{s['score_a']:.3f} · score {s['score_c']:+.3f}`, fitted on "
                  "half of the history validation week and checked on the other half (applied inside the scorer)."]
    lines += [""]

    lines += ["## Strong points (measured)", "",
              "Lifts are relative to best sellers on the same requests (+2.0 = 3× best sellers), with 95 % intervals.", "",
              "| Measure | All | Cold | New users | New products |", "|---|---|---|---|---|"]
    rows = [("History: ips_hit@10 (carousel, propensity-weighted)", "history", "ips_hit@10", "lift"),
            ("History: organic recall@10", "history", "organic_recall@10", "lift"),
            ("Live hold-out: organic recall@10", "live", "organic_recall@10", "lift")]
    for label, ds, metric, key in rows:
        vals = [_metric(met, ds, metric, sl) for sl in ("all", "cold", "new_user", "new_product")]
        if any(vals):
            lines.append(f"| {label} | " + " | ".join(_fmt(v, key) for v in vals) + " |")
    lines += [""]
    extra = []
    if _num(s.get("slate_auc")):
        extra.append(f"within a shown carousel, the clicked product scores above another shown product "
                     f"{s['slate_auc']:.0%} of the time (slate_auc; 50 % = random)")
    if _num(s.get("live_share_top10_heldout_new")) and _num(s.get("live_share_purchases_heldout_new")):
        extra.append(f"held-out practice products get {s['live_share_top10_heldout_new']:.2%} of top-10 slots "
                     f"against {s['live_share_purchases_heldout_new']:.2%} of purchases")
    elif _num(s.get("heldout_share_top10")) and _num(s.get("heldout_share_clicks")):
        extra.append(f"held-out (content-only) products get {s['heldout_share_top10']:.2%} of top-10 slots against "
                     f"{s['heldout_share_clicks']:.2%} of clicks")
    if _num(s.get("calibration_max_err")):
        extra.append(f"calibration: predicted and observed purchase rates differ by at most "
                     f"{s['calibration_max_err']:.0%} per score decile")
    if _num(s.get("latency_p99_ms")):
        extra.append(f"serving: {s['latency_p99_ms']:.2f} ms per request (p99, numpy only)")
    if _num(s.get("hm_dynamic_50_new_user")) and _num(s.get("hm_none_0_new_user")):
        extra.append(f"new users: lift {s.get('hm_none_0_new_user', float('nan')):.2f} without history, "
                     f"{s['hm_dynamic_50_new_user']:.2f} when their last 50 live events are passed")
    lines += [f"- {e}." for e in extra] + [""]

    lines += ["## Weak points and what it does not do", ""]
    weak = ["Discounts are not in the model (it only sees the original price): the discount effect (+60 % purchases "
            "for a 20 % discount) belongs in the correction layer.",
            "Trends of the final round are not in the model: the history has none, and live trends are left out on "
            "purpose.",
            "Stock, already-bought and diversity are not handled: hard filters in recsys."]
    if not fine:
        weak.insert(0, "Never saw new users or new products with labels; `is_new_user` is ignored.")
    if _num(s.get("calibration_max_err")) and s["calibration_max_err"] > 0.2:
        weak.append(f"Calibration misses the 20 % target (max decile error {s['calibration_max_err']:.0%}): use the "
                    "score as a ranking first, refit any weight that is added to it.")
    if hl > 0:
        weak.append("A user's history is frozen at export time unless live events are passed with `events=`.")
    lines += [f"- {w}" for w in weak] + [""]
    lines += ["## Use", "", "```python", "from training.export.scorer import load",
              f"model = load(\"models/{name}\")", "pm = model.embed_products(rows)      # rows: product_id, category, "
              "subcategory, brand, description, price (ORIGINAL)", "scores = model.score(request, pm)  # one per "
              "product, in pm.ids order; optional events=[(product_id, event_type), ...]", "```", ""]
    return "\n".join(lines)


def write(folder: Path, name: str | None = None, note: str | None = None) -> Path:
    path = Path(folder) / "description.md"
    path.write_text(text(Path(folder), name, note), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--name")
    ap.add_argument("--note")
    a = ap.parse_args()
    print(write(a.folder, a.name, a.note))


if __name__ == "__main__":
    main()

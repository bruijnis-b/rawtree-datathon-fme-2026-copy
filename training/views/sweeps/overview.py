"""Sweep view `overview`: the configurations of a sweep, side by side on every measure the runs logged.

One row per configuration (the settings that vary, except folds and seeds), in the same order in every figure:
1. Measures: each offline measure in its own panel, every run as a dot and the mean per configuration with its
   standard error over runs; a table with the same numbers, the acceptance checks and what each configuration is.
2. Acceptance checks: each run's value against the thresholds set in docs/EMBED_SWEEPS_FINAL.md.
3. Shopper slices: lift over best sellers per slice; for fine-tuned runs also by the length of a new shopper's history.
4. History vs. live (sweeps that score both): each configuration's history and live objective.

The view shows data only; it does not rank, select or judge. Reads only what the runs logged (see "Logging
contract" in docs/EMBED_SWEEPS_FINAL.md).
"""
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yaml
from plotly.subplots import make_subplots

import ivan

sweep = ivan.results.sweep()
REPEAT = {"fold", "seed", "data.fold", "train.seed", "ft.seed", sweep.seed_parameter}
BLUE, MUTED, FG = ivan.style.SERIES[0], ivan.style.MUTED, ivan.style.FG
SLICES = {"warm": "Known shopper, known products", "new_user": "New shopper", "new_product": "New product in recent views"}
SLICE_COLORS = dict(zip(SLICES, ivan.style.SERIES[:3]))


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def short(key: str) -> str:
    return key.split(".")[-1]


runs = [r for r in sweep.runs if r.summary]
if not runs:
    raise ivan.results.MissingData(f"no run of {sweep.name} has a summary yet")
live = sum(num(r.summary.get("live_objective")) is not None for r in runs) > len(runs) / 2

# Every offline measure the runs may log: (summary key, name, its standard error in the summary, format, what it is).
MEASURES = [
    ("live_objective", "Live objective", "live_objective_se", "{:.3f}",
     "lift over best sellers on held-out live organic purchases, (50 · all + 10 · cold) / 60"),
    ("fb_lift_all", "Carousel lift", None, "{:.3f}",
     "lift over live best sellers on our own logged carousels of held-out shoppers"),
    ("pauc_all", "Purchase AUC", "pauc_se", "{:.3f}", "rank of the purchased product among the 10 shown"),
    ("objective", "History objective", "objective_se", "{:.3f}",
     "lift over best sellers on the history validation week, (50 · all + 10 · cold) / 60"),
    ("slate_auc", "Slate AUC (history)", None, "{:.4f}", "rank of the clicked product among the 10 shown"),
    ("organic_recall", "Organic recall@10 (history)", None, "{:.4f}", "next organic purchase in our top 10"),
]
if live:  # history slate AUC and recall add little next to the live measures
    MEASURES = [m for m in MEASURES if m[0] not in {"slate_auc", "organic_recall"}]
MEASURES = [m for m in MEASURES if sum(num(r.summary.get(m[0])) is not None for r in runs) > len(runs) / 2]
if not MEASURES:
    raise ivan.results.MissingData(f"no run of {sweep.name} logged one of the measures this view shows")
ORDER_KEY = sweep.metric if any(m[0] == sweep.metric for m in MEASURES) else MEASURES[0][0]
ORDER_NAME = next(m[1] for m in MEASURES if m[0] == ORDER_KEY)

# --- Configurations: every setting that varies, except folds and seeds ---------------------------------------
varying = sorted(k for k in {k for r in runs for k in r.params} if len({str(r.params.get(k)) for r in runs}) > 1)
settings = [k for k in varying if k not in REPEAT]
repeats = [k for k in varying if k in REPEAT]


def config_of(r) -> str:
    return " · ".join(f"{short(k)}={r.params.get(k)}" if len(settings) > 1 else str(r.params.get(k))
                      for k in settings) or "default"


def resolved(r) -> dict:
    """The run's resolved settings (export/config.yaml), flattened; empty when the run kept none."""
    try:
        config = yaml.safe_load((Path(r.path) / "export" / "config.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    skip = {"seed", "epochs", "epoch_fraction", "calibrate_epochs", "score_affine"}
    return {f"{group}.{k}": v for group in ("model", "loss", "train", "organic", "ft")
            for k, v in (config.get(group) or {}).items() if not isinstance(v, (dict, list)) and k not in skip}


by_config = defaultdict(list)
for r in runs:
    by_config[config_of(r)].append(r)

first_resolved = {c: resolved(rs[0]) for c, rs in by_config.items()}
keys = sorted({k for d in first_resolved.values() for k in d})
differs = [k for k in keys if len({str(d.get(k)) for d in first_resolved.values()}) > 1]
LABELS = {"model.dim": "dim", "model.hidden": "hidden", "model.id_dropout": "ID drop", "model.history_dropout": "hist drop",
          "model.history_len": "hist len", "model.pooling": "pool", "model.slot": "slot", "model.description": "desc",
          "loss.click_weight": "click w", "loss.propensity_clip": "IPS clip", "organic.weight": "organic w",
          "train.lr": "lr", "train.weight_decay": "wd", "train.batch_size": "batch"}


def typical(key):
    values = [str(d.get(key)) for d in first_resolved.values()]
    return max(set(values), key=values.count)


def what_is(config: str) -> str:
    """The settings where this configuration differs from the sweep's most common value."""
    d = first_resolved.get(config) or {}
    if len(first_resolved) == 2:  # with two configurations there is no common value: list every difference
        return ", ".join(f"{LABELS.get(k, short(k))} {d.get(k)}" for k in differs if k in d) or "–"
    return ", ".join(f"{LABELS.get(k, short(k))} {d.get(k)}" for k in differs
                     if k in d and str(d.get(k)) != typical(k)) or "the sweep's common settings"


def checks_of(r) -> dict:
    found = r.records.get("checks")
    return {c["check"]: bool(c["passed"]) for c in found} if found else {}


CHECK_NAMES = [("held-out share", "new products"), ("new products' top-10", "new products"), ("calibration", "calibration"),
               ("lift_cold", "cold lift"), ("beats the model", "beats untuned"), ("numpy", "parity"), ("latency", "latency")]


def check_name(check: str) -> str:
    return next((name for key, name in CHECK_NAMES if key in check), check)


def stats(values):
    """Mean and standard error over runs (None when fewer than two runs)."""
    values = [v for v in values if v is not None]
    if not values:
        return None, None
    return float(np.mean(values)), (float(np.std(values, ddof=1) / math.sqrt(len(values))) if len(values) > 1 else None)


rows = []
for config, rs in by_config.items():
    per_check = defaultdict(list)
    all_pass = []
    for r in rs:
        checks = checks_of(r)
        for check, passed in checks.items():
            per_check[check_name(check)].append(passed)
        if checks:
            all_pass.append(all(checks.values()))
    rows.append({"config": config, "runs": rs, "n": len(rs), "per_check": per_check, "pass_all": sum(all_pass),
                 "checked": len(all_pass), "order": stats([num(r.summary.get(ORDER_KEY)) for r in rs])[0]})
rows.sort(key=lambda c: (c["order"] is None, -(c["order"] or 0) if sweep.goal != "minimize" else (c["order"] or 0)))
MAX_ROWS = 25
shown = rows[:MAX_ROWS]
y_of = {c["config"]: i for i, c in enumerate(shown)}
ticks = dict(tickmode="array", tickvals=list(range(len(shown))), ticktext=[c["config"] for c in shown], autorange="reversed",
             range=[len(shown) - 0.5, -0.5])
height = max(300, 40 * len(shown) + 150)


def offsets(n: int, width: float = 0.4):
    """Spread the n runs of one row vertically, so they do not hide each other."""
    return [0.0] if n == 1 else list(np.linspace(-width / 2, width / 2, n))


def repeat_label(r) -> str:
    return ", ".join(f"{short(k)} {r.params.get(k)}" for k in repeats) or r.name


def strip(fig, value, label, fmt, row=None, col=None, geometric=False):
    """One row per configuration: every run as a small dot, the mean as a diamond with ± one SE over runs."""
    where = dict(row=row, col=col) if row else {}
    for c in shown:
        rs = [r for r in c["runs"] if value(r) is not None]
        if not rs:
            continue
        y0 = y_of[c["config"]]
        vals = [value(r) for r in rs]
        fig.add_scatter(**where, x=vals, y=[y0 + o for o in offsets(len(rs))], mode="markers", showlegend=False,
                        marker=dict(size=7, color=BLUE, opacity=0.45), meta=ivan.results.link(rs),
                        customdata=[[r.name, repeat_label(r)] for r in rs],
                        hovertemplate=f"<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>{label} %{{x:{fmt}}}<extra></extra>")
        if geometric:
            logs = np.log(np.maximum(vals, 1e-3))
            center = float(np.exp(logs.mean()))
            se = float(logs.std(ddof=1) / math.sqrt(len(vals))) if len(vals) > 1 else 0.0
            err = dict(type="data", symmetric=False, array=[center * (math.exp(se) - 1)], arrayminus=[center * (1 - math.exp(-se))])
        else:
            center, se = stats(vals)
            err = dict(type="data", array=[se or 0])
        fig.add_scatter(**where, x=[center], y=[y0], mode="markers", showlegend=False,
                        error_x={**err, "thickness": 2, "width": 5, "color": BLUE},
                        marker=dict(size=12, symbol="diamond", color=BLUE, line=dict(width=1, color=FG)),
                        customdata=[[c["config"], len(rs), what_is(c["config"])]],
                        hovertemplate=f"<b>%{{customdata[0]}}</b><br>{'geometric ' if geometric else ''}mean {label} "
                                      f"%{{x:{fmt}}} over %{{customdata[1]}} runs<br>%{{customdata[2]}}<extra></extra>")


# --- 1. Measures ---------------------------------------------------------------------------------------------
fig = make_subplots(rows=1, cols=len(MEASURES), shared_yaxes=True, horizontal_spacing=0.04,
                    subplot_titles=[m[1] for m in MEASURES])
for col, (key, name, _, fmt, _) in enumerate(MEASURES, 1):
    strip(fig, lambda r, key=key: num(r.summary.get(key)), name, fmt.strip("{}:"), row=1, col=col)
    fig.update_xaxes(row=1, col=col, nticks=4)
fig.update_yaxes(**ticks)
fig.update_layout(height=height)
sweep.figure(fig, "measures", title="Measures", section="Measures", wide=True)


# --- 1b. Configurations table --------------------------------------------------------------------------------
def exposure_of(r):
    if live:
        share = num(r.summary.get("live_share_purchases_heldout_new"))
        return (num(r.summary.get("live_share_top10_heldout_new")) or 0) / share if share else None
    share = num(r.summary.get("heldout_share_clicks"))
    return (num(r.summary.get("heldout_share_top10")) or 0) / share if share else None


table, formats = [], {}
for c in rows:
    rs = c["runs"]
    row = {"Configuration": c["config"], "What it is": what_is(c["config"]), "Runs": c["n"]}
    for key, name, _, fmt, _ in MEASURES:
        m, se = stats([num(r.summary.get(key)) for r in rs])
        row[name] = m
        row[f"{name} ± SE"] = se
        formats[name] = formats[f"{name} ± SE"] = fmt
    ratios = [v for v in (exposure_of(r) for r in rs) if v is not None]
    if ratios:
        row["New products, × demand"] = float(np.exp(np.mean(np.log(np.maximum(ratios, 1e-3)))))
        row["(range)"] = f"{min(ratios):.2f}–{max(ratios):.2f}" if len(ratios) > 1 else None
    row["Calibration error"] = mean([num(r.summary.get("calibration_max_err")) for r in rs])
    row["All checks"] = f"{c['pass_all']}/{c['checked']}" if c["checked"] else None
    row["Failed"] = ", ".join(f"{name} {len(v) - sum(v)}/{len(v)}" for name, v in c["per_check"].items()
                                            if sum(v) < len(v)) or ("none" if c["checked"] else None)
    table.append(row)
columns = [k for k in dict.fromkeys(k for row in table for k in row) if any(row.get(k) is not None for row in table)]
formats.update({"New products, × demand": "{:.2f}", "Calibration error": "{:.3f}"})
sweep.table("configurations", [{k: row.get(k) for k in columns} for row in table], section="Measures",
            title="Configurations", columns=columns, formats={k: v for k, v in formats.items() if k in columns})

# --- 2. Acceptance checks ------------------------------------------------------------------------------------
panels = [("New products, × demand", exposure_of,
           (0.5, 2.0), True, "{:.2f}"),
          ("Calibration error", lambda r: num(r.summary.get("calibration_max_err")), (0.0, 0.2), False, "{:.3f}")]
panels = [p for p in panels if any(p[1](r) is not None for r in runs)]
if panels:
    fig = make_subplots(rows=1, cols=len(panels), shared_yaxes=True, horizontal_spacing=0.06,
                        subplot_titles=[p[0] for p in panels])
    for col, (name, value, (lo, hi), log, fmt) in enumerate(panels, 1):
        fig.add_vrect(x0=lo, x1=hi, fillcolor=ivan.style.SERIES[2], opacity=0.15, line_width=0, row=1, col=col,
                      layer="below", exclude_empty_subplots=False)
        strip(fig, value, name, fmt.strip("{}:"), row=1, col=col, geometric=log)
        values = [value(r) for r in runs if value(r) is not None]
        if log:  # a fixed range: plotly's autorange on a log axis is thrown off by the band
            span = [math.log10(max(min(values + [lo]) / 1.5, 1e-3)), math.log10(max(values + [hi]) * 1.5)]
        else:
            span = [0, max(values + [hi]) * 1.1]
        fig.update_xaxes(type="log" if log else "linear", row=1, col=col, range=span)
    fig.update_yaxes(**ticks)
    fig.update_layout(height=height)
    sweep.figure(fig, "checks", title="Acceptance checks", section="Acceptance checks", wide=True)

# --- 3. Shopper slices ---------------------------------------------------------------------------------------
dataset, primary = ("live", "organic_recall@10") if live else ("history", "ips_hit@10")
frames = []
for c in shown:
    for r in c["runs"]:
        metrics = r.records.get("metrics")
        if metrics:
            f = metrics.frame()
            f = f[(f["dataset"] == dataset) & (f["metric"] == primary) & f["slice"].isin(SLICES)]
            frames.append(f.assign(config=c["config"]))
if frames:
    lifts = pd.concat(frames).groupby(["config", "slice"]).agg(lift=("lift", "mean"), sd=("lift", "std"), k=("lift", "size"),
                                                              n=("n", "mean")).reset_index()
    lifts["se"] = (lifts["sd"] / np.sqrt(lifts["k"])).fillna(0)
    fig = go.Figure()
    for i, (slice_, color) in enumerate(SLICE_COLORS.items()):
        part = lifts[lifts["slice"] == slice_]
        if part.empty:
            continue
        fig.add_scatter(x=part["lift"], y=[y_of[c] + (i - 1) * 0.22 for c in part["config"]], mode="markers",
                        name=SLICES[slice_], marker=dict(size=10, color=color),
                        error_x=dict(type="data", array=part["se"], thickness=2, width=4, color=color),
                        customdata=np.stack([part["config"], part["n"], part["se"], part["k"]], axis=-1),
                        hovertemplate=f"<b>%{{customdata[0]}}</b><br>{SLICES[slice_]}: lift %{{x:.2f}} ± %{{customdata[2]:.2f}}"
                                      " over %{customdata[3]} runs<br>~%{customdata[1]:.0f} requests per run<extra></extra>")
    fig.add_vline(x=0, line_width=1, line_color=MUTED)
    fig.update_layout(height=height, yaxis=ticks, legend=dict(y=1.0, yanchor="bottom"),
                      xaxis_title="Lift over best sellers")
    sweep.figure(fig, "slices", title="Lift per slice", section="Shopper slices", wide=True)

# How much a new shopper's own history adds, by its length at scoring time (fine-tuned runs log this).
lengths = sorted({int(k.split("_")[2]) for r in runs for k in r.summary if k.startswith("hm_dynamic_") and k.endswith("_new_user")})
if lengths and len(shown) <= len(ivan.style.SERIES):
    fig = go.Figure()
    for i, c in enumerate(shown):
        xs, ys = [0], [mean([num(r.summary.get("hm_none_0_new_user")) for r in c["runs"]])]
        for n in lengths:
            xs.append(n)
            ys.append(mean([num(r.summary.get(f"hm_dynamic_{n}_new_user")) for r in c["runs"]]))
        fig.add_scatter(x=[0.7 if x == 0 else x for x in xs], y=ys, mode="lines+markers", name=c["config"],
                        line=dict(width=2, color=ivan.style.SERIES[i]), marker=dict(size=8),
                        customdata=[[c["config"], len(c["runs"]), x] for x in xs],
                        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[2]} events: lift %{y:.2f} "
                                      "(mean of %{customdata[1]} runs)<extra></extra>")
    fig.update_layout(xaxis=dict(type="log", title="Own events used", tickvals=[0.7] + lengths,
                                 ticktext=["0"] + [str(n) for n in lengths]),
                      yaxis_title="Lift over best sellers")
    sweep.figure(fig, "history-length", title="New shoppers: lift vs. own events used", section="Shopper slices",
                 wide=True)

# --- 4. History vs. live (sweeps that score both) ------------------------------------------------------------
both = [c for c in rows if all(num(r.summary.get("objective")) is not None and num(r.summary.get("live_objective")) is not None
                               for r in c["runs"])] if live else []
if len(both) >= 3:
    hx = [mean([r.summary["objective"] for r in c["runs"]]) for c in both]
    ly = [mean([r.summary["live_objective"] for r in c["runs"]]) for c in both]
    rho = pd.Series(hx).rank().corr(pd.Series(ly).rank())
    fig = go.Figure()
    fig.add_scatter(x=hx, y=ly, mode="markers", marker=dict(size=11, color=BLUE), showlegend=False,
                    customdata=[[c["config"], what_is(c["config"])] for c in both],
                    hovertemplate="<b>%{customdata[0]}</b><br>history %{x:.2f}, live %{y:.3f}<br>%{customdata[1]}<extra></extra>")
    fig.update_layout(xaxis_title="History objective", yaxis_title="Live objective")
    sweep.figure(fig, "history-vs-live", title=f"History vs. live (Spearman {rho:+.2f})", wide=True,
                 section="History vs. live")

# --- All runs ------------------------------------------------------------------------------------------------
extra = [("Lift cold" + (" (live)" if live else ""), "live_lift_cold" if live else "lift_cold", "{:.3f}"),
         ("Calibration error", "calibration_max_err", "{:.3f}"), ("p99 ms", "latency_p99_ms", "{:.2f}")]
cols = [(name, key, fmt) for key, name, _, fmt, _ in MEASURES] + extra
cols = [c for c in cols if any(num(r.summary.get(c[1])) is not None for r in runs)]
ordered = [r for c in rows for r in c["runs"]]
sweep.table("runs", [{"Run": r.name, "Configuration": config_of(r), **{short(k): str(r.params.get(k)) for k in repeats},
                      **{name: num(r.summary.get(key)) for name, key, _ in cols},
                      "Checks passed": f"{sum(checks_of(r).values())}/{len(checks_of(r))}" if checks_of(r) else None}
                     for r in ordered],
            title=f"All {len(runs)} runs", section="All runs", formats={name: fmt for name, _, fmt in cols})

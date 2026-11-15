"""Run view `overview`: one embedding run's measures.

1. Summary: the run's headline numbers.
2. Lift per slice: every measure (live organic, our logged carousels, history) per request slice, with its 95 %
   bootstrap interval; purchase AUC per shopper group.
3. Shopper history: lift by the number of the shopper's own events used at scoring time (fine-tuned runs).
4. Acceptance checks and training curves.

Data only. Reads what the pipeline logged (see "Logging contract" in docs/EMBED_SWEEPS_FINAL.md).
"""
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import ivan

run = ivan.results.run()
S = run.summary
BLUE, MUTED = ivan.style.SERIES[0], ivan.style.MUTED
SLICE_ORDER = ["all", "cold", "warm", "known", "new_user", "new_product", "in_cart"]
SLICE_NAMES = {"all": "All", "cold": "Cold", "warm": "Known shopper, known products", "known": "Known shopper",
               "new_user": "New shopper", "new_product": "New product in recent views", "in_cart": "Clicked product in cart"}


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


shown = 0

# --- Summary -------------------------------------------------------------------------------------------------
headline = [
    ("Live objective", "live_objective", "live_objective_se", "{:.3f}"),
    ("Live objective before fine-tuning", "live_objective_before", None, "{:.3f}"),
    ("Live lift, cold", "live_lift_cold", None, "{:.3f}"),
    ("Carousel lift", "fb_lift_all", None, "{:.3f}"),
    ("Purchase AUC", "pauc_all", "pauc_se", "{:.3f}"),
    ("History objective", "objective", "objective_se", "{:.3f}"),
    ("History lift, cold", "lift_cold", None, "{:.3f}"),
    ("Calibration error", "calibration_max_err", None, "{:.3f}"),
    ("Discount weight (live)", "disc_beta", None, "{:.3f}"),
    ("Latency p99, ms", "latency_p99_ms", None, "{:.2f}"),
    ("Minutes", "minutes", None, "{:.1f}"),
]
rows = []
for name, key, se_key, fmt in headline:
    if num(S.get(key)) is None:
        continue
    se = num(S.get(se_key)) if se_key else None
    rows.append({"Measure": name, "Value": fmt.format(S[key]), "SE": fmt.format(se) if se is not None else ""})
if rows:
    run.table("summary", rows, title="Summary", section="Summary")
    shown += 1

# --- Lift per slice ------------------------------------------------------------------------------------------
panels = []  # (title, frame with slice, value, lo, hi, plus hover columns)
metrics = run.records.get("metrics")
if metrics:
    frame = metrics.frame()
    names = {("live", "organic_recall@10"): "Live organic recall@10", ("history", "ips_hit@10"): "History IPS hit@10",
             ("history", "slate_auc"): "History slate AUC", ("history", "organic_recall@10"): "History organic recall@10"}
    for (dataset, metric), title in names.items():
        part = frame[(frame["dataset"] == dataset) & (frame["metric"] == metric)]
        if not part.empty:
            panels.append((title, part))
feedback = run.records.get("feedback_holdout")
if feedback:
    panels.insert(1 if panels and panels[0][0].startswith("Live") else 0, ("Carousel hold-out", feedback.frame()))
if panels:
    present = [s for s in SLICE_ORDER if any(s in set(p["slice"]) for _, p in panels)]
    y_of = {s: i for i, s in enumerate(present)}
    fig = make_subplots(rows=1, cols=len(panels), shared_yaxes=True, horizontal_spacing=0.03,
                        subplot_titles=[t for t, _ in panels])
    for col, (title, part) in enumerate(panels, 1):
        part = part[part["slice"].isin(present)]
        has_ci = {"lift_lo", "lift_hi"} <= set(part.columns)
        extra = [c for c in ("value", "baseline", "n") if c in part.columns]
        fig.add_scatter(row=1, col=col, x=part["lift"], y=[y_of[s] for s in part["slice"]], mode="markers", showlegend=False,
                        marker=dict(size=10, color=BLUE),
                        error_x=dict(type="data", symmetric=False, array=part["lift_hi"] - part["lift"],
                                     arrayminus=part["lift"] - part["lift_lo"], thickness=2, width=4, color=BLUE)
                        if has_ci else None,
                        customdata=np.column_stack([part["slice"].map(SLICE_NAMES)] + [part[c] for c in extra]),
                        hovertemplate=f"<b>{title}</b>, %{{customdata[0]}}<br>lift %{{x:.2f}}"
                                      + ("<br>model %{customdata[1]:.4f}, best sellers %{customdata[2]:.4f}"
                                         "<br>n %{customdata[3]:,.0f}" if len(extra) == 3 else "") + "<extra></extra>")
        fig.add_vline(x=0, line_width=1, line_color=MUTED, row=1, col=col)
        fig.update_xaxes(row=1, col=col, nticks=4)
    fig.update_yaxes(tickmode="array", tickvals=list(range(len(present))), ticktext=[SLICE_NAMES[s] for s in present],
                     autorange="reversed")
    fig.update_layout(height=max(300, 42 * len(present) + 130))
    run.figure(fig, "lift", title="Lift over best sellers per slice (95 % interval)", section="Lift per slice", wide=True)
    shown += 1

auc = [(g, S.get(k)) for g, k in [("All", "pauc_all"), ("Known shopper", "pauc_known"), ("New shopper", "pauc_new_user")]
       if num(S.get(k)) is not None]
if auc:
    se = num(S.get("pauc_se"))
    fig = go.Figure()
    fig.add_scatter(x=[v for _, v in auc], y=[g for g, _ in auc], mode="markers", marker=dict(size=10, color=BLUE),
                    showlegend=False,
                    error_x=dict(type="data", array=[1.96 * se if g == "All" else 0 for g, _ in auc], thickness=2, width=4,
                                 color=BLUE) if se else None,
                    hovertemplate="%{y}: %{x:.3f}<extra></extra>")
    spread = (1.96 * se if se else 0) + 0.01
    fig.update_layout(height=200, yaxis=dict(autorange="reversed"), xaxis_title="Purchase AUC",
                      xaxis_range=[min(v for _, v in auc) - spread, max(v for _, v in auc) + spread])
    run.figure(fig, "purchase-auc", title=f"Purchase AUC ({S.get('pauc_n', '?')} purchases)", section="Lift per slice")

# --- Shopper history at scoring time -------------------------------------------------------------------------
modes = run.records.get("history_modes")
if modes:
    frame = modes.frame()
    slices = [s for s in ["all", "new_user", "cold"] if s in set(frame["slice"])]
    none = frame[frame["mode"] == "none"]
    fig = make_subplots(rows=1, cols=len(slices), shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=[SLICE_NAMES[s] for s in slices])
    styles = {"snapshot": ivan.style.SERIES[0], "dynamic": ivan.style.SERIES[1]}
    for col, s in enumerate(slices, 1):
        base = none[none["slice"] == s]
        for mode, color in styles.items():
            part = frame[(frame["mode"] == mode) & (frame["slice"] == s)].sort_values("length")
            if part.empty:
                continue
            part = pd.concat([base, part]) if not base.empty else part
            fig.add_scatter(row=1, col=col, x=part["length"].replace(0, 0.7), y=part["lift"], mode="lines+markers",
                            name=mode, legendgroup=mode, showlegend=col == 1, line=dict(color=color, width=2),
                            error_y=dict(type="data", symmetric=False, array=part["lift_hi"] - part["lift"],
                                         arrayminus=part["lift"] - part["lift_lo"], thickness=1, width=3, color=color),
                            customdata=np.column_stack([part["length"], part["n"]]),
                            hovertemplate=f"{mode}, %{{customdata[0]:.0f}} events<br>lift %{{y:.2f}}<br>n %{{customdata[1]:,.0f}}"
                                          "<extra></extra>")
        lengths = sorted(set(frame["length"]) - {0})
        fig.update_xaxes(row=1, col=col, type="log", tickvals=[0.7] + lengths, ticktext=["0"] + [str(int(v)) for v in lengths])
    fig.update_xaxes(title_text="Own events used", row=1, col=(len(slices) + 1) // 2)
    fig.update_yaxes(title_text="Lift over best sellers", row=1, col=1)
    fig.update_layout(legend=dict(y=1.12), margin=dict(t=70))
    run.figure(fig, "history-length", title="Lift vs. own events used (95 % interval)", section="Shopper history", wide=True)
    shown += 1

# --- Acceptance checks ---------------------------------------------------------------------------------------
checks = run.records.get("checks")
if checks:
    run.table("checks", [{"Check": c.get("check"), "Value": c.get("value"), "Needed": c.get("needed"),
                          "Passed": "yes" if c.get("passed") else "no"} for c in checks],
              title="Acceptance checks", section="Acceptance checks")
    shown += 1

# --- Training ------------------------------------------------------------------------------------------------
if run.steps:
    steps = run.steps.frame()
    x = steps["epoch"] if "epoch" in steps else steps["_step"]
    losses = [c for c in ("loss", "loss_click", "loss_purchase", "loss_organic") if c in steps and steps[c].abs().sum() > 0]
    vals = [c for c in ("val_objective", "val_lift_all", "val_lift_cold") if c in steps and steps[c].notna().any()]
    panels = [p for p in (("Training loss", losses), ("Validation", vals)) if p[1]]
    if panels:
        fig = make_subplots(rows=1, cols=len(panels), horizontal_spacing=0.08, subplot_titles=[t for t, _ in panels])
        for col, (_, columns) in enumerate(panels, 1):
            for i, column in enumerate(columns):
                label = {"loss": "total"}.get(column, column.replace("loss_", "").replace("val_", "").replace("_", " "))
                fig.add_scatter(row=1, col=col, x=x, y=steps[column], name=label, mode="lines+markers",
                                line=dict(color=ivan.style.SERIES[(i + 3 * (col - 1)) % len(ivan.style.SERIES)], width=2),
                                hovertemplate=f"{label}<br>epoch %{{x}}: %{{y:.4f}}<extra></extra>")
            fig.update_xaxes(row=1, col=col, title_text="Epoch", dtick=1 if len(x) <= 20 else None)
        fig.update_layout(legend=dict(y=1.12), margin=dict(t=70))
        run.figure(fig, "training", title="Training", section="Training", wide=True)
        shown += 1

if not shown:
    raise ivan.results.MissingData(f"{run.name} logged no summary, metrics or steps yet")

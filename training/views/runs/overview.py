"""Run view `overview`: the result of one embedding run at a glance.

Shows the headline numbers, the lift over best sellers per slice (with intervals), the acceptance checks and the
training curves. Reads only what the pipeline logged (see "Logging contract" in docs/EMBED_SWEEPS_FINAL.md).
"""
import plotly.graph_objects as go

import ivan

run = ivan.results.run()
S = run.summary

METRIC_NAMES = {"ips_hit@10": "IPS hit@10 (primary)", "slate_auc": "Slate AUC", "organic_recall@10": "Organic recall@10"}
SLICES = ["all", "cold", "warm", "new_user", "new_product"]

# --- Result -------------------------------------------------------------------------------------------------
headline = [
    ("Objective (50·all + 10·cold) / 60", S.get("objective"), "{:+.3f}"),
    ("Lift over best sellers, all requests", S.get("lift_all"), "{:+.1%}"),
    ("Lift over best sellers, cold requests", S.get("lift_cold"), "{:+.1%}"),
    ("Live objective (hold-out)", S.get("live_objective"), "{:+.3f}"),
    ("Live lift, cold requests", S.get("live_lift_cold"), "{:+.1%}"),
    ("Slate AUC", S.get("slate_auc"), "{:.4f}"),
    ("Organic recall@10", S.get("organic_recall"), "{:.4f}"),
    ("Latency p99, ms (CPU, batch 1)", S.get("latency_p99_ms"), "{:.2f}"),
]
rows = [{"Result": name, "Value": fmt.format(value)} for name, value, fmt in headline if isinstance(value, (int, float))]
if rows:
    run.table("headline", rows, title=f"{run.name}: result", section="Result",
              caption="Lift = (model − best sellers) / best sellers on the same requests.")

# --- Lift per slice -----------------------------------------------------------------------------------------
metrics = run.records.get("metrics")
if metrics:
    frame = metrics.frame()
    for dataset, part in frame.groupby("dataset", sort=False):
        fig = go.Figure()
        for metric, rows_m in part.groupby("metric", sort=False):
            rows_m = rows_m.set_index("slice").reindex([s for s in SLICES if s in set(rows_m["slice"])])
            has_ci = {"lift_lo", "lift_hi"} <= set(rows_m.columns)
            fig.add_bar(
                x=rows_m.index, y=rows_m["lift"], name=METRIC_NAMES.get(metric, metric),
                error_y=dict(type="data", symmetric=False, array=rows_m["lift_hi"] - rows_m["lift"],
                             arrayminus=rows_m["lift"] - rows_m["lift_lo"]) if has_ci else None,
                customdata=rows_m[["value", "baseline", "n"]].to_numpy() if {"value", "baseline", "n"} <= set(rows_m.columns) else None,
                hovertemplate=f"{METRIC_NAMES.get(metric, metric)}, %{{x}}<br>lift %{{y:+.1%}}"
                              "<br>model %{customdata[0]:.4f}, best sellers %{customdata[1]:.4f}"
                              "<br>%{customdata[2]:,} requests<extra></extra>")
        fig.add_hline(y=0, line_width=1)
        fig.update_layout(barmode="group", yaxis_tickformat="+.0%", yaxis_title="Lift over best sellers",
                          xaxis_title="Request slice")
        run.figure(fig, f"lift-{dataset}", title=f"Lift over best sellers per slice ({dataset} validation)",
                   caption="Bars: lift over in-stock best sellers on the same requests; whiskers: 95 % bootstrap interval. "
                           "cold = new user or a new product in recent_views.", section="Lift per slice", wide=True)

# --- Acceptance checks --------------------------------------------------------------------------------------
checks = run.records.get("checks")
if checks:
    run.table("checks", [{"Check": c.get("check"), "Value": c.get("value"), "Needed": c.get("needed"),
                          "Pass": "yes" if c.get("passed") else "NO"} for c in checks],
              title="Acceptance checks", section="Acceptance checks",
              caption="A model goes to serving only if every check passes.")

# --- Training -----------------------------------------------------------------------------------------------
if run.steps:
    steps = run.steps.frame()
    x = steps["epoch"] if "epoch" in steps else steps["_step"]
    losses = [c for c in ("loss", "loss_click", "loss_purchase", "loss_organic") if c in steps]
    if losses:
        fig = go.Figure()
        for column in losses:
            fig.add_scatter(x=x, y=steps[column], name=column.replace("loss_", "").replace("loss", "total"), mode="lines+markers",
                            hovertemplate=f"{column}<br>epoch %{{x}}: %{{y:.4f}}<extra></extra>")
        fig.update_layout(xaxis_title="Epoch", yaxis_title="Training loss")
        run.figure(fig, "loss", title="Training loss", section="Training",
                   caption="Epochs of the live fine-tuning stage follow the history epochs.")
    vals = [c for c in ("val_objective", "val_lift_all", "val_lift_cold") if c in steps]
    if vals:
        fig = go.Figure()
        for column in vals:
            fig.add_scatter(x=x, y=steps[column], name=column.replace("val_", "").replace("_", " "), mode="lines+markers",
                            hovertemplate=f"{column}<br>epoch %{{x}}: %{{y:+.3f}}<extra></extra>")
        fig.update_layout(xaxis_title="Epoch", yaxis_title="Validation lift")
        run.figure(fig, "validation", title="Validation per epoch", section="Training")

if not (rows or metrics or run.steps):
    raise ivan.results.MissingData(f"{run.name} logged no summary, metrics or steps yet")

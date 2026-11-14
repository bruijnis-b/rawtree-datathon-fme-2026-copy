"""Sweep view `overview`: which embedding runs are best, and at what cost?

Shows a leaderboard, the trade-off between all requests and cold requests, the objective of every run with its
interval, and the mean per configuration when a sweep repeats configurations over folds and seeds. Reads only what
the runs logged (see "Logging contract" in docs/EMBED_SWEEPS_FINAL.md).
"""
import pandas as pd
import plotly.graph_objects as go

import ivan

sweep = ivan.results.sweep()
METRIC = sweep.metric or "objective"
REPEAT = {"fold", "seed", "data.fold", "train.seed", sweep.seed_parameter}

runs = [r for r in sweep.runs if isinstance(r.summary.get(METRIC), (int, float))]
if not runs:
    raise ivan.results.MissingData(f"no run of {sweep.name} has a summary value {METRIC!r} yet")
runs.sort(key=lambda r: r.summary[METRIC], reverse=sweep.goal != "minimize")

varying = sorted(k for k in {k for r in runs for k in r.params} if len({str(r.params.get(k)) for r in runs}) > 1)
settings = [k for k in varying if k not in REPEAT]


def short(key: str) -> str:
    return key.split(".")[-1]


def describe(r) -> str:
    return "<br>".join(f"{short(k)} = {r.params.get(k)}" for k in varying) or "default settings"


def number(r, key):
    value = r.summary.get(key)
    return value if isinstance(value, (int, float)) else None


# --- Leaderboard --------------------------------------------------------------------------------------------
columns = [("Objective", METRIC, "{:+.3f}"), ("Lift all", "lift_all", "{:+.1%}"), ("Lift cold", "lift_cold", "{:+.1%}"),
           ("Live objective", "live_objective", "{:+.3f}"), ("Live lift cold", "live_lift_cold", "{:+.1%}"),
           ("Slate AUC", "slate_auc", "{:.4f}"), ("Organic recall@10", "organic_recall", "{:.4f}"),
           ("p99 ms", "latency_p99_ms", "{:.1f}")]
columns = [c for c in columns if any(number(r, c[1]) is not None for r in runs)]
table = []
for rank, r in enumerate(runs, 1):
    row = {"#": rank, "Run": r.name}
    row.update({name: number(r, key) for name, key, _ in columns})
    row.update({short(k): str(r.params.get(k)) for k in varying})
    table.append(row)
sweep.table("leaderboard", table, title=f"{sweep.name}: {len(runs)} runs, best first", section="Leaderboard",
            formats={name: fmt for name, _, fmt in columns},
            caption="Objective = (50 · lift on all requests + 10 · lift on cold requests) / 60, lift over best sellers.")

# --- All vs. cold -------------------------------------------------------------------------------------------
both = [r for r in runs if number(r, "lift_all") is not None and number(r, "lift_cold") is not None]
if both:
    fig = go.Figure()
    fig.add_scatter(
        x=[r.summary["lift_all"] for r in both], y=[r.summary["lift_cold"] for r in both], mode="markers",
        marker=dict(size=11, color=[r.summary[METRIC] for r in both], coloraxis="coloraxis"),
        customdata=[[r.name, describe(r), r.summary[METRIC]] for r in both], meta=ivan.results.link(both),
        hovertemplate="<b>%{customdata[0]}</b><br>all %{x:+.1%}, cold %{y:+.1%}<br>objective %{customdata[2]:+.3f}"
                      "<br>%{customdata[1]}<extra></extra>")
    fig.add_hline(y=0, line_width=1)
    fig.add_vline(x=0, line_width=1)
    fig.update_layout(xaxis_title="Lift over best sellers, all requests (50 points)",
                      yaxis_title="Lift over best sellers, cold requests (10 points)", xaxis_tickformat="+.0%",
                      yaxis_tickformat="+.0%", coloraxis_colorbar_title="Objective", showlegend=False)
    sweep.figure(fig, "all-vs-cold", title="All requests vs. cold requests", section="Trade-off", wide=True,
                 caption="One dot per run; click a dot to open the run. Up and to the right is better; the lines mark "
                         "best sellers.")

# --- Objective per run --------------------------------------------------------------------------------------
top = runs[:30]
errors = [number(r, "objective_se") for r in top]
fig = go.Figure()
fig.add_bar(x=[r.name for r in top], y=[r.summary[METRIC] for r in top],
            error_y=dict(type="data", array=[e or 0 for e in errors]) if any(errors) else None,
            customdata=[[describe(r)] for r in top], meta=ivan.results.link(top),
            hovertemplate="<b>%{x}</b><br>objective %{y:+.3f}<br>%{customdata[0]}<extra></extra>")
fig.update_layout(xaxis_title="Run (best first)", yaxis_title="Objective", xaxis_tickangle=-45, showlegend=False)
sweep.figure(fig, "objective", title="Objective of the best runs", section="Leaderboard", wide=True,
             caption="Whiskers: one standard error from the bootstrap over requests. Runs whose whiskers overlap are "
                     "not clearly different.")

# --- Folds and seeds ----------------------------------------------------------------------------------------
if any(k in REPEAT for k in varying):
    frame = pd.DataFrame([{"config": " · ".join(f"{short(k)}={r.params.get(k)}" for k in settings) or "default",
                           "objective": r.summary[METRIC], "lift_all": number(r, "lift_all"),
                           "lift_cold": number(r, "lift_cold"), "p99": number(r, "latency_p99_ms")} for r in runs])
    grouped = frame.groupby("config").agg(runs=("objective", "size"), mean=("objective", "mean"), sd=("objective", "std"),
                                          lift_all=("lift_all", "mean"), lift_cold=("lift_cold", "mean"),
                                          p99=("p99", "max")).reset_index()
    grouped["se"] = (grouped["sd"] / grouped["runs"] ** 0.5).fillna(0)
    grouped["lower"] = grouped["mean"] - grouped["se"]
    grouped = grouped.sort_values("lower", ascending=False)
    fig = go.Figure()
    fig.add_bar(x=grouped["config"], y=grouped["mean"], error_y=dict(type="data", array=grouped["se"]),
                customdata=grouped[["runs", "lift_all", "lift_cold"]].to_numpy(),
                hovertemplate="<b>%{x}</b><br>objective %{y:+.3f} over %{customdata[0]} runs"
                              "<br>all %{customdata[1]:+.1%}, cold %{customdata[2]:+.1%}<extra></extra>")
    fig.update_layout(xaxis_title="Configuration", yaxis_title="Mean objective over folds and seeds", xaxis_tickangle=-30,
                      showlegend=False)
    sweep.figure(fig, "configs", title="Configurations, averaged over folds and seeds", section="Folds and seeds", wide=True,
                 caption="Whiskers: one standard error over the folds and seeds. Selection uses the mean minus one "
                         "standard error.")
    sweep.table("configs-table", grouped.rename(columns={
        "config": "Configuration", "runs": "Runs", "mean": "Mean objective", "se": "Std. error", "lower": "Mean - SE",
        "lift_all": "Lift all", "lift_cold": "Lift cold", "p99": "Worst p99 ms"}).drop(columns="sd"),
        title="Configurations, best first", section="Folds and seeds",
        formats={"Mean objective": "{:+.3f}", "Std. error": "{:.3f}", "Mean - SE": "{:+.3f}", "Lift all": "{:+.1%}",
                 "Lift cold": "{:+.1%}", "Worst p99 ms": "{:.1f}"})

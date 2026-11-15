"""Run view `diagnostics`: slot term, calibration, new products, serving and settings of one embedding run.

Data only. Reads what the pipeline logged (see "Logging contract" in docs/EMBED_SWEEPS_FINAL.md).
"""
import math

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import ivan

run = ivan.results.run()
S = run.summary
SERIES, MUTED = ivan.style.SERIES, ivan.style.MUTED
shown = 0


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


# --- Slot term (history runs) --------------------------------------------------------------------------------
slot = run.records.get("slot")
if slot:
    frame = slot.frame()
    has_ctr = {"ctr_pred", "ctr_obs"} <= set(frame.columns)
    fig = make_subplots(rows=1, cols=2 if has_ctr else 1, horizontal_spacing=0.08,
                        subplot_titles=["Attention relative to slot 1"] + (["Click rate"] if has_ctr else []))
    for i, (device, part) in enumerate(frame.groupby("device", sort=True)):
        part = part.sort_values("slot")
        color = SERIES[i % len(SERIES)]
        fig.add_scatter(row=1, col=1, x=part["slot"], y=part["theta_learned"], name=f"{device}, learned", mode="lines+markers",
                        line=dict(color=color, width=2), legendgroup=device,
                        hovertemplate=f"{device}, slot %{{x}}<br>learned %{{y:.3f}}<extra></extra>")
        if "theta_measured" in part:
            fig.add_scatter(row=1, col=1, x=part["slot"], y=part["theta_measured"], name=f"{device}, measured", mode="lines",
                            line=dict(color=color, dash="dot", width=2), legendgroup=device,
                            hovertemplate=f"{device}, slot %{{x}}<br>measured %{{y:.3f}}<extra></extra>")
    if has_ctr:
        per_slot = frame.groupby("slot")[["ctr_pred", "ctr_obs"]].mean().reset_index()
        fig.add_bar(row=1, col=2, x=per_slot["slot"], y=per_slot["ctr_obs"], name="observed", marker_color=MUTED,
                    hovertemplate="slot %{x}<br>observed %{y:.3%}<extra></extra>")
        fig.add_bar(row=1, col=2, x=per_slot["slot"], y=per_slot["ctr_pred"], name="predicted", marker_color=SERIES[0],
                    hovertemplate="slot %{x}<br>predicted %{y:.3%}<extra></extra>")
        fig.update_yaxes(row=1, col=2, tickformat=".2%")
    fig.update_xaxes(title_text="Slot", dtick=1)
    fig.update_yaxes(row=1, col=1, rangemode="tozero")
    fig.update_layout(barmode="group")
    run.figure(fig, "slot", title="Slot term", section="Slot term", wide=True)
    shown += 1

# --- Calibration ---------------------------------------------------------------------------------------------
calibration = run.records.get("calibration")
if calibration:
    frame = calibration.frame()
    frame = frame[(frame["predicted"] > 0) & (frame["observed"] > 0)]
    if not frame.empty:
        fig = go.Figure()
        low, high = frame[["predicted", "observed"]].min().min(), frame[["predicted", "observed"]].max().max()
        fig.add_scatter(x=[low, high], y=[low, high], mode="lines", name="predicted = observed",
                        line=dict(dash="dot", width=1, color=MUTED), hoverinfo="skip")
        keys = [c for c in ("dataset", "slice") if c in frame]
        for i, (key, part) in enumerate(frame.groupby(keys, sort=False)):
            label = " · ".join(map(str, key)) if isinstance(key, tuple) else str(key)
            part = part.sort_values("predicted")
            fig.add_scatter(x=part["predicted"], y=part["observed"], name=label, mode="lines+markers",
                            line=dict(color=SERIES[i % len(SERIES)], width=2),
                            customdata=part[["decile", "n"]].to_numpy(),
                            hovertemplate=f"{label}, decile %{{customdata[0]}}<br>predicted %{{x:.3%}}<br>observed %{{y:.3%}}"
                                          "<br>n %{customdata[1]:,}<extra></extra>")
        fig.update_layout(xaxis_type="log", yaxis_type="log", xaxis_title="Predicted purchase probability",
                          yaxis_title="Observed purchase rate", xaxis_tickformat=".2%", yaxis_tickformat=".2%")
        error = num(S.get("calibration_max_err"))
        run.figure(fig, "calibration", section="Calibration", wide=True,
                   title="Calibration per score decile" + (f" (max error {error:.3f})" if error is not None else ""))
        shown += 1

# --- New products --------------------------------------------------------------------------------------------
groups = []  # (label, share of our top-10 slots, share of demand, demand name)
products = run.records.get("products")
if products:
    for p in products:
        if p.get("group") == "held-out":
            groups.append(("History held-out products", p["share_top10"], p["share_clicks"], "clicks"))
if num(S.get("live_share_top10_heldout_new")) is not None and num(S.get("live_share_purchases_heldout_new")):
    groups.append(("Live held-out new products", S["live_share_top10_heldout_new"], S["live_share_purchases_heldout_new"],
                   "purchases"))
if groups:
    fig = go.Figure()
    fig.add_bar(y=[g[0] for g in groups], x=[g[1] for g in groups], orientation="h", name="Share of our top-10 slots",
                marker_color=SERIES[0], hovertemplate="%{y}<br>%{x:.2%} of top-10 slots<extra></extra>")
    fig.add_bar(y=[g[0] for g in groups], x=[g[2] for g in groups], orientation="h", name="Share of demand",
                marker_color=MUTED, customdata=[[g[3]] for g in groups],
                hovertemplate="%{y}<br>%{x:.2%} of %{customdata[0]}<extra></extra>")
    fig.update_layout(barmode="group", xaxis_tickformat=".1%", height=160 + 70 * len(groups), yaxis=dict(autorange="reversed"))
    run.figure(fig, "new-products", title="New products: top-10 share vs. demand share", section="New products", wide=True)
    shown += 1

# --- Serving -------------------------------------------------------------------------------------------------
serving = [("Latency p50, ms", "latency_p50_ms", "{:.2f}"), ("Latency p99, ms", "latency_p99_ms", "{:.2f}"),
           ("Parity, scores", "parity_max_abs", "{:.1e}"), ("Parity, product vectors", "product_parity_max_abs", "{:.1e}"),
           ("Score scale a", "score_a", "{:.4f}"), ("Score offset c", "score_c", "{:.4f}"),
           ("Calibration error before recalibration", "calibration_max_err_raw", "{:.3f}"),
           ("Slot term, max gap", "slot_max_gap", "{:.3f}")]
rows = [{"Item": name, "Value": fmt.format(S[key])} for name, key, fmt in serving if num(S.get(key)) is not None]
if rows:
    run.table("serving", rows, title="Serving", section="Serving")
    shown += 1
if run.params:
    run.table("settings", [{"Setting": k, "Value": str(v)} for k, v in sorted(run.params.items())], title="Settings",
              section="Settings")

if not shown:
    raise ivan.results.MissingData(f"{run.name} logged no slot, calibration, products or serving data yet")

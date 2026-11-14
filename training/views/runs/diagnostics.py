"""Run view `diagnostics`: is the model unbiased, calibrated and safe to serve?

Shows the slot term (carousel position bias), calibration of the purchase probability, how new products are
ranked, latency and the run's settings. Reads only what the pipeline logged (see "Logging contract" in
docs/EMBED_SWEEPS_FINAL.md).
"""
import plotly.graph_objects as go

import ivan

run = ivan.results.run()
S = run.summary
shown = 0

# --- Slot bias ----------------------------------------------------------------------------------------------
slot = run.records.get("slot")
if slot:
    frame = slot.frame()
    fig = go.Figure()
    for i, (device, part) in enumerate(frame.groupby("device", sort=True)):
        part = part.sort_values("slot")
        colour = ivan.style.SERIES[i % len(ivan.style.SERIES)]
        fig.add_scatter(x=part["slot"], y=part["theta_learned"], name=f"{device}, learned", mode="lines+markers",
                        line=dict(color=colour), hovertemplate=f"{device}, slot %{{x}}<br>learned %{{y:.3f}}<extra></extra>")
        if "theta_measured" in part:
            fig.add_scatter(x=part["slot"], y=part["theta_measured"], name=f"{device}, measured", mode="lines",
                            line=dict(color=colour, dash="dot"),
                            hovertemplate=f"{device}, slot %{{x}}<br>measured %{{y:.3f}}<extra></extra>")
    fig.update_layout(xaxis_title="Carousel slot", yaxis_title="Attention relative to slot 1", xaxis_dtick=1,
                      yaxis_rangemode="tozero")
    run.figure(fig, "slot-term", title="Slot effect: learned by the model vs. measured in the history", section="Slot bias",
               caption="Solid: exp(slot term) of the click head. Dotted: product-adjusted attention curve from the "
                       "historical carousels. The term is removed at inference, so scores are for slot 1.")
    if {"ctr_pred", "ctr_obs"} <= set(frame.columns):
        per_slot = frame.groupby("slot")[["ctr_pred", "ctr_obs"]].mean().reset_index()
        fig = go.Figure()
        fig.add_bar(x=per_slot["slot"], y=per_slot["ctr_obs"], name="observed",
                    hovertemplate="slot %{x}<br>observed %{y:.3%}<extra></extra>")
        fig.add_bar(x=per_slot["slot"], y=per_slot["ctr_pred"], name="predicted",
                    hovertemplate="slot %{x}<br>predicted %{y:.3%}<extra></extra>")
        fig.update_layout(barmode="group", xaxis_title="Carousel slot", yaxis_title="Click rate", yaxis_tickformat=".2%",
                          xaxis_dtick=1)
        run.figure(fig, "slot-ctr", title="Click rate per slot on the validation week", section="Slot bias",
                   caption="Predicted with the slot term switched on. The two should agree in every slot.")
    shown += 1

# --- Calibration --------------------------------------------------------------------------------------------
calibration = run.records.get("calibration")
if calibration:
    frame = calibration.frame()
    fig = go.Figure()
    low, high = frame[["predicted", "observed"]].replace(0, float("nan")).min().min(), frame[["predicted", "observed"]].max().max()
    fig.add_scatter(x=[low, high], y=[low, high], mode="lines", name="perfect", line=dict(dash="dot", width=1),
                    hoverinfo="skip")
    keys = [c for c in ("dataset", "slice") if c in frame]
    for key, part in frame.groupby(keys, sort=False):
        label = " · ".join(key) if isinstance(key, tuple) else str(key)
        part = part.sort_values("predicted")
        fig.add_scatter(x=part["predicted"], y=part["observed"], name=label, mode="lines+markers",
                        customdata=part[["n"]].to_numpy() if "n" in part else None,
                        hovertemplate=f"{label}<br>predicted %{{x:.3%}}<br>observed %{{y:.3%}}"
                                      + ("<br>%{customdata[0]:,} impressions" if "n" in part else "") + "<extra></extra>")
    fig.update_layout(xaxis_type="log", yaxis_type="log", xaxis_title="Predicted purchase probability",
                      yaxis_title="Observed purchase rate", xaxis_tickformat=".2%", yaxis_tickformat=".2%")
    run.figure(fig, "calibration", title="Calibration of the purchase probability", section="Calibration",
               caption="One point per score decile. The serving layer adds its corrections on the log-odds scale, so "
                       "the points must lie on the dotted line.", wide=True)
    shown += 1

# --- New products -------------------------------------------------------------------------------------------
products = run.records.get("products")
if products:
    frame = products.frame()
    fig = go.Figure()
    fig.add_bar(x=frame["group"], y=frame["share_top10"], name="share of our top-10 slots",
                hovertemplate="%{x}<br>%{y:.2%} of top-10 slots<extra></extra>")
    fig.add_bar(x=frame["group"], y=frame["share_clicks"], name="share of clicks and purchases",
                hovertemplate="%{x}<br>%{y:.2%} of clicks and purchases<extra></extra>")
    fig.update_layout(barmode="group", yaxis_tickformat=".1%", yaxis_title="Share")
    run.figure(fig, "new-products", title="Are new products ranked in proportion to their demand?", section="New products",
               caption="Held-out products are scored from content alone, like the 300 products of the final round. "
                       "Their share of top-10 slots should stay below twice their share of clicks.")
    shown += 1

# --- Serving and settings -----------------------------------------------------------------------------------
serving = [("Latency p50, ms", "latency_p50_ms", "{:.2f}"), ("Latency p99, ms", "latency_p99_ms", "{:.2f}"),
           ("Numpy vs. PyTorch, max abs difference", "parity_max_abs", "{:.1e}"),
           ("Calibration, largest relative error", "calibration_max_err", "{:.1%}"),
           ("Slot term, largest gap to measured (log)", "slot_max_gap", "{:.3f}")]
rows = [{"Serving check": name, "Value": fmt.format(S[key])} for name, key, fmt in serving if isinstance(S.get(key), (int, float))]
if rows:
    run.table("serving", rows, title="Serving checks", section="Serving",
              caption="Latency: one request against the whole catalogue with the numpy scorer, on CPU.")
    shown += 1
if run.params:
    run.table("settings", [{"Setting": k, "Value": str(v)} for k, v in sorted(run.params.items())], title="Settings",
              section="Settings")

if not shown:
    raise ivan.results.MissingData(f"{run.name} logged no slot, calibration, products or serving data yet")

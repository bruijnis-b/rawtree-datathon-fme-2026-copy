"""Team monitor: health, our own leaderboard row, model performance and the store.

    streamlit run monitor/dashboard.py

See monitor/README.md for what each view shows and how to read the numbers.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitor import data  # noqa: E402
from monitor.rawtree import TEAM  # noqa: E402

st.set_page_config(page_title=f"{TEAM} monitor", page_icon=":material/monitor_heart:", layout="wide")

STATUS_THRESHOLD = 90.0  # the organisers' status light: >90% valid and on time in the last 5 minutes
DEADLINE_MS = 3000


# --------------------------------------------------------------------------------------------
# Cached loaders. `bucket` rounds "now" so reruns within the TTL share one query.
# --------------------------------------------------------------------------------------------

@st.cache_data(ttl=25, max_entries=20, show_spinner=False)
def load_detail(t0: float, t1: float) -> pd.DataFrame:
    return data.request_detail(t0, t1)


@st.cache_data(ttl=55, max_entries=8, show_spinner=False)
def load_official_by_model(t0: float, t1: float) -> pd.DataFrame | None:
    try:
        return data.official_by_model(t0, t1)
    except Exception:
        return None


@st.cache_data(ttl=55, max_entries=2, show_spinner=False)
def load_official(bucket: int) -> dict | None:
    try:
        snap = data.official_snapshot()
    except Exception:
        return None
    data.record_snapshot(snap)
    return snap


@st.cache_data(ttl=55, max_entries=2, show_spinner=False)
def load_board(bucket: int) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    try:
        return data.all_teams()
    except Exception:
        return None


@st.cache_data(ttl=55, max_entries=6, show_spinner=False)
def load_best_models(t0: float, t1: float, min_requests: int) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    try:
        return data.best_models(t0, t1, min_requests)
    except Exception:
        return None


@st.cache_data(ttl=25, max_entries=4, show_spinner=False)
def load_store(bucket: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    return (data.trending_subcategories(), data.events_per_minute(60), data.catalog_changes(60),
            data.catalog_change_counts())


def naive(ts: pd.Series) -> pd.Series:
    """Barcelona wall-clock time without tz info, so charts show CET whatever the browser's zone."""
    return ts.dt.tz_localize(None)


def fmt(v: float, digits: int = 2, suffix: str = "") -> str:
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{digits}f}{suffix}"


def window_bounds(choice: str, official: dict | None) -> tuple[float, float, str]:
    now = time.time()
    if choice == "Final round":
        start = (official or {}).get("final_start", data.FINAL_START)
        end = (official or {}).get("final_end", data.FINAL_END)
        return start, min(end, now), "Sun 10:00–12:00 CET"
    minutes = {"15 min": 15, "1 hour": 60, "3 hours": 180}[choice]
    return now - minutes * 60, now, f"last {choice}"


# --------------------------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------------------------

with st.sidebar:
    st.header(f":material/monitor_heart: {TEAM}")
    window_choice = st.segmented_control(
        "Window", ["15 min", "1 hour", "3 hours", "Final round"], default="1 hour",
        help="The final is scored on Sun 10:00–12:00 CET.")
    window_choice = window_choice or "1 hour"
    refresh_s = st.select_slider("Auto-refresh", options=[15, 30, 60, 120], value=30,
                                 format_func=lambda s: f"every {s} s")
    st.caption("Times in Barcelona time (CET). Self-computed numbers use realised purchases from "
               f"`{TEAM}.feedback`; the official leaderboard uses expected purchases.")
    st.link_button("Public leaderboard", "https://datathon.rawtree.dev/leaderboard",
                   icon=":material/leaderboard:", width="stretch")

view = st.segmented_control(
    "View", ["Leaderboard copy", "Health", "Model performance", "Store"],
    default="Leaderboard copy", label_visibility="collapsed", key="view")
view = view or "Leaderboard copy"


# --------------------------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------------------------

STATUS_REFRESH_S = 5  # the health strip refreshes on its own, faster than the rest of the page
ANSWERING_ALERT = 50.0  # below this share of recent requests answered, we are (mostly) down


def age_label(age: float, refresh_s: int) -> str:
    """An age no finer than the refresh interval: anything newer than one refresh reads as live."""
    if math.isnan(age):
        return "never"
    if age < refresh_s:
        return f"within {refresh_s} s"
    if age < 120:
        return f"{int(age // refresh_s) * refresh_s}+ s ago"
    if age < 7200:
        return f"{int(age // 60)} min ago"
    return f"{age / 3600:.0f} h ago"


@st.fragment(run_every=STATUS_REFRESH_S)
def status_bar() -> None:
    """Always-visible health strip, refreshed every few seconds and never cached.

    Two signals with different speeds:
    - Answering now: requests from 4-15 s ago that have a submission of ours. Does not wait for
      feedback, so it reacts within ~10 s when the recommender stops or starts.
    - Organiser status light: >90% valid and on time over the last 5 minutes of feedback. This is
      the organisers' rule and is slow by design (feedback lands ~4 s late, and a 5-minute share
      needs ~30 s of misses to drop below 90%).
    """
    try:
        live = data.answering_now()
        hb = data.heartbeat()
        now = time.time()
        last5 = data.request_detail(now - 300, now)
    except Exception as e:
        st.error(f"{type(e).__name__}: {e}", icon=":material/cloud_off:", title="Health check failed")
        return
    on_time_5m = 100 * last5["team"].mean() if len(last5) else math.nan
    light_green = not math.isnan(on_time_5m) and on_time_5m > STATUS_THRESHOLD
    answering = live["share"]
    down = not math.isnan(answering) and answering < ANSWERING_ALERT
    recent = last5[last5["team"] & (last5["ts"] >= last5["ts"].max() - pd.Timedelta(seconds=90))] if len(last5) else last5
    live_models = sorted(recent["model"].unique()) if len(recent) else []  # last 90 s: restarts drop out quickly
    model = live_models[0] if len(live_models) == 1 else f"{len(live_models)} models (A/B)" if live_models else "–"

    if down:
        st.error(f"Only {live['answered']} of the last {live['requests']} requests got an answer from us. "
                 f"Shoppers are getting the fallback.", icon=":material/error:", title="Recommender not answering")
    elif not light_green:
        st.warning(f"Answering ({fmt(answering, 0, '%')} of recent requests), but the organiser status light is "
                   f"red: {fmt(on_time_5m, 1, '%')} valid and on time over the last 5 min. It turns green once "
                   f"that share is above {STATUS_THRESHOLD:.0f}%, or check for late/invalid answers.",
                   icon=":material/warning:", title="Status light red")
    else:
        st.success(f"Answering {fmt(answering, 0, '%')} of recent requests · status light green "
                   f"({on_time_5m:.1f}% valid and on time over 5 min).", icon=":material/check_circle:")

    with st.container(horizontal=True):
        st.metric("Answering now", fmt(answering, 0, "%"), border=True,
                  help="Requests from 4–15 s ago that have a submission of ours. Reacts within ~10 s.")
        st.metric("Status light, 5 min", fmt(on_time_5m, 1, "%"), border=True,
                  help="The organisers' rule: >90% valid and on time over 5 min of feedback. Slow by design.")
        st.metric("Last answer served", age_label(hb["served_age_s"], STATUS_REFRESH_S), border=True,
                  help="From feedback, which lands about 4 s after each request.")
        st.metric("Last request in stream", age_label(hb["request_age_s"], STATUS_REFRESH_S), border=True)
        st.metric("Model live", model, border=True,
                  help="Models that answered in the last 5 min: " + ("; ".join(live_models) or "none"))


def leaderboard_view(t0: float, t1: float, label: str, official: dict | None) -> None:
    st.subheader("Our leaderboard row")
    st.caption("Only our own numbers. When the leaderboard goes dark, the official side keeps the last "
               "values we recorded and the self-computed side keeps updating.")

    snaps = data.load_snapshots(tail=200)
    last_with_row = next((s for s in reversed(snaps) if (s.get("ours") or {}).get("requests")), None)
    shown = official if official and (official.get("ours") or {}).get("requests") else last_with_row

    left, right = st.columns(2, border=True)
    with left:
        st.markdown("**Official** · public leaderboard")
        if shown is None:
            st.info("No official numbers recorded yet.", icon=":material/hourglass_empty:")
        else:
            ours, base, ref = shown.get("ours") or {}, shown.get("baseline") or {}, shown.get("reference") or {}
            w0, w1 = shown.get("window") or [None, None]
            when = pd.Timestamp(shown["updated_at"], unit="s", tz="UTC").tz_convert(data.TZ)
            dark = official is not None and shown is not official
            st.caption(f"{'Last recorded before the leaderboard went dark · ' if dark else ''}"
                       f"mode `{shown.get('mode')}` · updated {when:%a %H:%M} · window "
                       f"{pd.Timestamp(w0, unit='s', tz='UTC').tz_convert(data.TZ):%H:%M}–"
                       f"{pd.Timestamp(w1, unit='s', tz='UTC').tz_convert(data.TZ):%H:%M}")
            with st.container(horizontal=True):
                st.metric("Conversion", fmt(ours.get("conversion"), 3, "%"),
                          delta=f"{ours.get('conversion', 0) - base.get('conversion', 0):+.3f} vs baseline"
                          if base else None, border=True)
                st.metric("Cold conversion", fmt(ours.get("cold_conversion"), 3, "%"),
                          delta=f"{ours.get('cold_conversion', 0) - base.get('cold_conversion', 0):+.3f} vs baseline"
                          if base else None, border=True)
                st.metric("On time", fmt(ours.get("on_time"), 1, "%"), border=True)
                st.metric("Revenue / request", f"€{fmt(ours.get('revenue_per_request'), 3)}", border=True)
            st.caption(f"Baseline {fmt(base.get('conversion'), 3, '%')} · reference "
                       f"{fmt(ref.get('conversion'), 3, '%')} · model "
                       f"`{data.model_labels().get(ours.get('model_version'), (ours.get('model_version') or '–',))[0]}`")
            if official is None:
                st.warning("Leaderboard unreachable right now; showing the last recorded values.",
                           icon=":material/cloud_off:")

    with right:
        st.markdown(f"**Self-computed** · {label}")
        df = load_detail(t0, t1)
        s = data.summarize(df)
        st.caption(f"{s['requests']:,} requests · realised purchases · 95% interval "
                   f"±{fmt(s['conversion_ci'], 3)} pts on conversion")
        with st.container(horizontal=True):
            st.metric("Conversion", fmt(s["conversion"], 3, "%"), border=True)
            st.metric("Cold conversion", fmt(s["cold_conversion"], 3, "%"),
                      help=f"{s['cold_requests']:,} cold requests", border=True)
            st.metric("On time", fmt(s["on_time"], 1, "%"), border=True)
            st.metric("Revenue / request", f"€{fmt(s['revenue_per_request'], 3)}", border=True)
        st.caption(f"Click rate {fmt(s['ctr'], 2, '%')} · conversion when we served "
                   f"{fmt(s['team_conversion'], 3, '%')} · when the fallback served "
                   f"{fmt(s['fallback_conversion'], 3, '%')}")

    # Calibration: our realised numbers over the exact official window.
    if shown and shown.get("window") and (shown.get("ours") or {}).get("requests"):
        w0, w1 = shown["window"]
        cal = data.summarize(load_detail(w0, w1))
        ours = shown["ours"]
        st.caption(
            f"Calibration over the official window: official {fmt(ours.get('conversion'), 3, '%')} expected "
            f"vs {fmt(cal['conversion'], 3, '%')} realised (±{fmt(cal['conversion_ci'], 3)}); on time official "
            f"{fmt(ours.get('on_time'), 1, '%')} vs ours {fmt(cal['on_time'], 1, '%')}.")

    hist = data.snapshot_history()
    progress = (shown or {}).get("progress") or []
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Official conversion over time** (recorded snapshots)")
        if hist.empty:
            st.caption("Snapshots build up while this dashboard or `monitor/record_official.py` runs.")
        else:
            long = hist.assign(updated=naive(hist["updated"])).melt(
                id_vars="updated", value_vars=["conversion", "baseline_conversion", "reference_conversion"],
                var_name="series", value_name="pct")
            long["series"] = long["series"].map({"conversion": TEAM, "baseline_conversion": "baseline",
                                                 "reference_conversion": "reference"})
            chart = alt.Chart(long).mark_line(point=True).encode(
                x=alt.X("updated:T", title=None), y=alt.Y("pct:Q", title="Expected purchases per 100"),
                color=alt.Color("series:N", title=None),
                tooltip=["updated:T", "series:N", alt.Tooltip("pct:Q", format=".3f")])
            st.altair_chart(chart, alt="Our official conversion against baseline and reference over time")
    with c2, st.container(border=True):
        st.markdown("**Official score per hour** (out of 100)")
        if not progress:
            st.caption("No hourly scores published yet.")
        else:
            pdf = pd.DataFrame(progress, columns=["hour", "score"])
            pdf["hour"] = naive(pd.to_datetime(pdf["hour"], unit="s", utc=True).dt.tz_convert(data.TZ))
            chart = alt.Chart(pdf).mark_bar().encode(
                x=alt.X("hour:T", title=None), y=alt.Y("score:Q", title="Score"),
                tooltip=[alt.Tooltip("hour:T", format="%a %H:%M"), alt.Tooltip("score:Q", format=".2f")])
            st.altair_chart(chart, alt="Our official hourly score from the leaderboard")

    score_comparison()
    best_models_view(t0, t1, label)


def score_comparison() -> None:
    """Every team's score out of 100 next to ours."""
    st.subheader("Score vs the other teams")
    got = load_board(int(time.time() // 55))
    if got is None or got[0].empty:
        st.info("Leaderboard unreachable or empty right now.", icon=":material/cloud_off:")
        return
    board, hourly = got
    us = board[board["is_us"]]
    n = len(board)
    st.caption(f"{n} teams over the leaderboard's current window. **Score now** is our estimate from each "
               "team's expected conversions (same formula as the model table, ~0.2-1 pt off the official); "
               "**last hour** is the newest official hourly score.")
    if not us.empty:
        r = us.iloc[0]
        above = board[board["rank"] == r["rank"] - 1]
        with st.container(horizontal=True):
            st.metric("Our rank", f"{int(r['rank'])} / {n}", border=True)
            st.metric("Our score now", fmt(r["score_est"], 1), border=True,
                      delta=f"{r['score_est'] - board['score_est'].median():+.1f} vs median")
            st.metric("Gap to #1", fmt(board["score_est"].iloc[0] - r["score_est"], 1), border=True,
                      help=f"#1 is {board['team'].iloc[0]}")
            st.metric("Gap to next team up", fmt(above["score_est"].iloc[0] - r["score_est"], 1)
                      if not above.empty else "–", border=True,
                      help=f"{above['team'].iloc[0]}" if not above.empty else "We are first")
            st.metric("Our last official hour", fmt(r["last_hour_score"], 1), border=True)

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Score now** (estimated, out of 100)")
        chart = alt.Chart(board).mark_bar().encode(
            y=alt.Y("team:N", sort="-x", title=None, axis=alt.Axis(labelOverlap=False, labelFontSize=10)),
            x=alt.X("score_est:Q", title="Score", scale=alt.Scale(domain=[0, 100])),
            color=alt.condition("datum.is_us", alt.value("#e4572e"), alt.value("#9aa5b1")),
            tooltip=["rank:Q", "team:N", alt.Tooltip("score_est:Q", format=".1f", title="score now"),
                     alt.Tooltip("last_hour_score:Q", format=".1f", title="last official hour")],
        ).properties(height=max(300, 16 * n))
        st.altair_chart(chart, alt="Estimated score of every team, ours highlighted")
    with c2, st.container(border=True):
        st.markdown("**Official score per hour**")
        top = board["team"].head(5).tolist()
        default = top + ([TEAM] if TEAM not in top else [])
        picked = st.multiselect("Teams", sorted(board["team"]), default=default, key="compare_teams",
                                label_visibility="collapsed")
        h = hourly[hourly["team"].isin(picked)].copy()
        if h.empty:
            st.caption("No hourly scores for these teams.")
        else:
            h["hour"] = naive(pd.to_datetime(h["hour"], unit="s", utc=True).dt.tz_convert(data.TZ))
            h["us"] = h["team"] == TEAM
            chart = alt.Chart(h).mark_line(point=True).encode(
                x=alt.X("hour:T", title=None), y=alt.Y("score:Q", title="Score", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("team:N", title=None),
                strokeWidth=alt.condition("datum.us", alt.value(4), alt.value(1.5)),
                tooltip=["team:N", alt.Tooltip("hour:T", format="%a %H:%M"), alt.Tooltip("score:Q", format=".1f")])
            st.altair_chart(chart, alt="Official hourly score of the chosen teams, ours thicker")

    with st.expander("All teams"):
        st.dataframe(
            board.drop(columns=["is_us", "last_hour"]),
            hide_index=True, width="stretch",
            column_config={
                "score_est": st.column_config.ProgressColumn("Score now", min_value=0, max_value=100, format="%.1f"),
                "last_hour_score": st.column_config.NumberColumn("Last official hour", format="%.1f"),
                "conversion": st.column_config.NumberColumn("Conversion %", format="%.3f"),
                "cold_conversion": st.column_config.NumberColumn("Cold %", format="%.3f"),
                "on_time": st.column_config.NumberColumn("On time %", format="%.1f"),
            })


def best_models_view(t0: float, t1: float, label: str) -> None:
    """Each team's best single model next to ours: what a team would score if its best model answered everything."""
    st.subheader(f"Best single model per team · {label}")
    min_req = st.segmented_control("Minimum requests per model", [300, 1000, 2500], default=1000,
                                   key="best_min_req", help="Fewer requests swing 10+ points per quarter hour")
    bucket = int(time.time() // 55) * 55
    got = load_best_models(max(t0, t1 - 10800), min(t1, bucket + 55), int(min_req or 1000))
    if got is None:
        st.info("Leaderboard unreachable right now.", icon=":material/cloud_off:")
        return
    best, ours = got
    st.caption("Official expected conversions from the leaderboard's per-model view (the window is cut to its "
               "last 3 h). A team's own score averages all its models; **Best model** is its strongest single "
               "model scored as if it answered every request. Models that answer only cold requests (conversion "
               "equal to cold conversion) are left out: they are not comparable.")
    if best.empty:
        st.caption("No model has enough requests in this window yet.")
    else:
        us = best[best["is_us"]]
        if not us.empty:
            r = us.iloc[0]
            with st.container(horizontal=True):
                st.metric("Our best model's rank", f"{int(r['rank'])} / {len(best)}", border=True)
                st.metric("Its score", fmt(r["score"], 1), border=True,
                          delta=f"{r['score'] - best['score'].iloc[0]:+.1f} vs #1" if r["rank"] > 1 else "#1")
                st.metric("Its cold conversion", fmt(r["cold_conversion"], 2, " %"), border=True,
                          delta=f"{r['cold_conversion'] - best['cold_conversion'].head(5).median():+.2f} vs top-5 median")
        with st.container(border=True):
            chart = alt.Chart(best).mark_bar().encode(
                y=alt.Y("team:N", sort="-x", title=None, axis=alt.Axis(labelOverlap=False, labelFontSize=10)),
                x=alt.X("score:Q", title="Best single model, score", scale=alt.Scale(domain=[0, 100])),
                color=alt.condition("datum.is_us", alt.value("#e4572e"), alt.value("#9aa5b1")),
                tooltip=["rank:Q", "team:N", alt.Tooltip("score:Q", format=".1f", title="best model"),
                         alt.Tooltip("team_score:Q", format=".1f", title="team score"),
                         alt.Tooltip("conversion:Q", format=".2f"), alt.Tooltip("cold_conversion:Q", format=".2f"),
                         "requests:Q", "models:Q"],
            ).properties(height=max(240, 16 * len(best)))
            st.altair_chart(chart, alt="Best single model of every team, ours highlighted")
        st.dataframe(best.drop(columns=["is_us"]), hide_index=True, width="stretch", column_config={
            "score": st.column_config.ProgressColumn("Best model", min_value=0, max_value=100, format="%.1f"),
            "team_score": st.column_config.NumberColumn("Team score", format="%.1f"),
            "conversion": st.column_config.NumberColumn("Conversion %", format="%.2f"),
            "cold_conversion": st.column_config.NumberColumn("Cold %", format="%.2f"),
            "models": st.column_config.NumberColumn("Models run"),
            "model": st.column_config.TextColumn("Our model"),
        })
    if ours is not None and not ours.empty:
        with st.expander("All our models in this window"):
            st.dataframe(ours, hide_index=True, width="stretch", column_config={
                "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
                "conversion": st.column_config.NumberColumn("Conversion %", format="%.2f"),
                "cold_conversion": st.column_config.NumberColumn("Cold %", format="%.2f"),
                "warm_conversion": st.column_config.NumberColumn("Warm %", format="%.2f"),
            })


def health_view(t0: float, t1: float, label: str) -> None:
    st.subheader(f"Health · {label}")
    df = load_detail(t0, t1)
    if df.empty:
        st.info("No feedback in this window yet.", icon=":material/hourglass_empty:")
        return
    df = df.assign(minute=naive(df["ts"]).dt.floor("min"),
                   outcome=df["fallback_reason"].where(~df["team"], "served by us").replace("", "fallback"))

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Who served each request, per minute**")
        per_min = df.groupby(["minute", "outcome"]).size().rename("requests").reset_index()
        chart = alt.Chart(per_min).mark_area(interpolate="step-after").encode(
            x=alt.X("minute:T", title=None), y=alt.Y("requests:Q", title="Requests", stack=True),
            color=alt.Color("outcome:N", title=None,
                            scale=alt.Scale(domain=["served by us", "late", "invalid", "missing"],
                                            range=["#2e9e5b", "#e8a33d", "#d64545", "#8a8a8a"])),
            tooltip=["minute:T", "outcome:N", "requests:Q"]).configure_legend(orient="bottom")
        st.altair_chart(chart, alt="Requests per minute split by who served them")
    with c2, st.container(border=True):
        st.markdown("**Answer latency per minute** (3 s deadline)")
        lat = df.dropna(subset=["latency_ms"])
        if lat.empty:
            st.caption("No latencies yet: none of our answers has arrived in this window.")
        else:
            q = lat.groupby("minute")["latency_ms"].quantile([0.5, 0.95]).unstack()
            q.columns = ["p50", "p95"]
            q = q.reset_index().melt(id_vars="minute", var_name="quantile", value_name="ms")
            lines = alt.Chart(q).mark_line().encode(
                x=alt.X("minute:T", title=None), y=alt.Y("ms:Q", title="Latency (ms)"),
                color=alt.Color("quantile:N", title=None), tooltip=["minute:T", "quantile:N", "ms:Q"])
            rule = alt.Chart(pd.DataFrame({"ms": [DEADLINE_MS]})).mark_rule(
                strokeDash=[4, 4], color="#d64545").encode(y="ms:Q")
            st.altair_chart((lines + rule).configure_legend(orient="bottom"), alt="Median and 95th percentile latency per minute against 3 s")

    with st.container(border=True):
        st.markdown("**Fallback reasons**")
        reasons = df.groupby("outcome").agg(
            requests=("rid", "size"), p50_ms=("latency_ms", "median"),
            p95_ms=("latency_ms", lambda s: s.quantile(0.95) if s.notna().any() else math.nan)).reset_index()
        reasons["share"] = reasons["requests"] / reasons["requests"].sum()
        st.dataframe(reasons.sort_values("requests", ascending=False), hide_index=True,
                     column_config={"share": st.column_config.ProgressColumn("Share", format="percent"),
                                    "p50_ms": st.column_config.NumberColumn("p50 ms", format="%.0f"),
                                    "p95_ms": st.column_config.NumberColumn("p95 ms", format="%.0f")},
                     alt="Requests per outcome with latency")


def group_table(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by).agg(requests=("rid", "size"), served=("team", "mean"), purchases=("bought", "sum"),
                           ctr=("click", "mean"), revenue=("revenue", "mean")).reset_index()
    p = g["purchases"] / g["requests"]
    g["conversion"] = 100 * p
    g["ci95"] = 100 * 1.96 * (p * (1 - p) / g["requests"]).pow(0.5)
    g["served"] *= 100
    g["ctr"] *= 100
    return g.sort_values("requests", ascending=False)


GROUP_COLS = {
    "requests": st.column_config.NumberColumn("Requests", format="%d"),
    "served": st.column_config.NumberColumn("Served by us", format="%.1f%%"),
    "purchases": st.column_config.NumberColumn("Purchases", format="%d"),
    "conversion": st.column_config.NumberColumn("Conversion", format="%.3f%%"),
    "ci95": st.column_config.NumberColumn("± 95%", format="%.3f"),
    "ctr": st.column_config.NumberColumn("Click rate", format="%.2f%%"),
    "revenue": st.column_config.NumberColumn("Revenue / req", format="€%.3f"),
}


def performance_view(t0: float, t1: float, label: str) -> None:
    st.subheader(f"Model performance · {label}")
    df = load_detail(t0, t1)
    if df.empty:
        st.info("No feedback in this window yet.", icon=":material/hourglass_empty:")
        return
    st.caption("Purchases are rare (about 1 per 100 requests): compare models over an hour or more and "
               "check the ± 95% column before concluding anything.")

    with st.container(border=True):
        st.markdown("**By model** (public `model_version` IDs translated with `recsys/model_versions.json`)")
        firsts = df.drop_duplicates("model").set_index("model")
        t = group_table(df, "model")
        t.insert(1, "settings", t["model"].map(firsts["settings"]))
        official = load_official_by_model(t0, t1)
        if official is not None and len(official):
            t["model_version"] = t["model"].map(firsts["model_version"])
            t = t.merge(official[["model_version", "score_est", "off_conversion", "off_cold"]], on="model_version",
                        how="left").drop(columns="model_version")
            t.insert(2, "score_est", t.pop("score_est"))
        st.dataframe(t, hide_index=True, alt="Conversion and estimated score per model",
                     column_config={**GROUP_COLS, "model": st.column_config.TextColumn("Model (public ID)"),
                                    "settings": st.column_config.TextColumn("Settings"),
                                    "score_est": st.column_config.NumberColumn(
                                        "Score (est.)", format="%.1f",
                                        help="Estimated leaderboard score (0-100) if this model answered every "
                                             "request in the window, from the official expected conversion"),
                                    "off_conversion": st.column_config.NumberColumn(
                                        "Official conv", format="%.3f%%", help="Expected purchases per 100 requests, "
                                        "from the leaderboard's per-model view (no luck)"),
                                    "off_cold": st.column_config.NumberColumn(
                                        "Official cold", format="%.3f%%", help="The same, on cold requests only")})
        st.caption("Score (est.) = (50 × conversion part + 10 × cold part) / 70, each part 100 × (model − "
                   "baseline) / (oracle − baseline) clipped to 0–100, against this window's baseline. The oracle "
                   "is hidden: estimated as 1.31 × the reference (fit on every team's hourly scores, error ~0.2 "
                   "points). Reliability added nothing on the practice day. Short windows and small models are "
                   "noisy; the realised columns come from our own feedback.")

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Conversion per 10 minutes**")
        b = df.assign(bucket=naive(df["ts"]).dt.floor("10min")).groupby(["bucket", "model"]).agg(
            requests=("rid", "size"), purchases=("bought", "sum")).reset_index()
        b["conversion"] = 100 * b["purchases"] / b["requests"]
        chart = alt.Chart(b).mark_line(point=True).encode(
            x=alt.X("bucket:T", title=None), y=alt.Y("conversion:Q", title="Purchases per 100 requests"),
            color=alt.Color("model:N", title=None, legend=alt.Legend(orient="bottom", columns=1, labelLimit=400)),
            tooltip=["bucket:T", "model:N", "requests:Q", "purchases:Q",
                     alt.Tooltip("conversion:Q", format=".3f")])
        st.altair_chart(chart, alt="Realised conversion per 10 minutes by model version")
    with c2, st.container(border=True):
        st.markdown("**Which slot gets the click / purchase**")
        slots = pd.concat([
            df.loc[df["click_slot"] > 0, "click_slot"].value_counts().rename("count").reset_index()
              .assign(kind="click").rename(columns={"click_slot": "slot"}),
            df.loc[df["buy_slot"] > 0, "buy_slot"].value_counts().rename("count").reset_index()
              .assign(kind="purchase").rename(columns={"buy_slot": "slot"}),
        ])
        if slots.empty:
            st.caption("No clicks yet in this window.")
        else:
            chart = alt.Chart(slots).mark_bar().encode(
                x=alt.X("slot:O", title="Slot"), xOffset="kind:N", y=alt.Y("count:Q", title="Count"),
                color=alt.Color("kind:N", title=None), tooltip=["slot:O", "kind:N", "count:Q"])
            st.altair_chart(chart, alt="Clicks and purchases per carousel slot")

    c3, c4 = st.columns(2)
    with c3, st.container(border=True):
        st.markdown("**Cold vs warm requests**")
        st.dataframe(group_table(df.assign(segment=df["cold"].map({True: "cold", False: "warm"})), "segment"),
                     hide_index=True, column_config=GROUP_COLS, alt="Conversion for cold and warm requests")
    with c4, st.container(border=True):
        st.markdown("**By page and device**")
        seg = df.assign(segment=df["page"].fillna("?") + " · " + df["device"].fillna("?"))
        st.dataframe(group_table(seg, "segment"), hide_index=True, column_config=GROUP_COLS,
                     alt="Conversion per page and device")


def store_view() -> None:
    st.subheader("The store · live")
    trending, events, changes, counts = load_store(int(time.time() // 30))
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Trending subcategories** (views, last 15 min vs the 3 h before)")
        st.dataframe(trending, hide_index=True, column_config={
            "lift": st.column_config.NumberColumn("Lift", format="%.2f×"),
            "avg_per_15m_before": st.column_config.NumberColumn("Avg / 15 min before", format="%.0f"),
            "views_15m": st.column_config.NumberColumn("Views, 15 min", format="%d")},
            alt="Subcategories with the biggest rise in views")
    with c2, st.container(border=True):
        st.markdown("**Organic activity per minute**")
        if events.empty:
            st.caption("No events in the last hour.")
        else:
            chart = alt.Chart(events.assign(minute=naive(events["minute"]))).mark_line().encode(
                x=alt.X("minute:T", title=None), y=alt.Y("events:Q", title="Events", scale=alt.Scale(type="log")),
                color=alt.Color("event_type:N", title=None), tooltip=["minute:T", "event_type:N", "events:Q"])
            st.altair_chart(chart, alt="Views, add-to-cart and purchases per minute")
    with st.container(border=True):
        st.markdown("**Catalogue changes, last hour** (delta vs the hour before)")
        # Fixed cards in a fixed order, so a type showing up or going quiet never reshuffles the row.
        with st.grid(5, gap="small"):
            for change in data.CHANGE_TYPES:
                c = counts["counts"].get(change, {"last_hour": 0, "prev_hour": 0})
                st.metric(change.replace("_", " ").capitalize(), f"{c['last_hour']:,}",
                          delta=c["last_hour"] - c["prev_hour"], delta_color="off", border=True, height="stretch")
            st.metric("Out of stock now", f"{counts['out_of_stock_now']:,}", border=True, height="stretch",
                      help="Products whose latest stock change is a stock-out: recommending one invalidates the answer.")
        if changes.empty:
            st.caption("No catalogue changes in the last hour.")
        else:
            st.dataframe(changes.assign(ts=naive(changes["ts"])), hide_index=True,
                         column_config={"ts": st.column_config.DatetimeColumn("Time", format="HH:mm:ss"),
                                        "price_eur": st.column_config.NumberColumn("Price", format="€%.2f")},
                         alt="Recent catalogue changes")


@st.fragment(run_every=refresh_s)
def live_body(window_choice: str, view: str) -> None:
    official = load_official(int(time.time() // 60))
    t0, t1, label = window_bounds(window_choice, official)
    try:
        if t1 <= t0:
            start = pd.Timestamp(t0, unit="s", tz="UTC").tz_convert(data.TZ)
            st.info(f"The final round starts {start:%a %d %b %H:%M} CET; nothing to show for it yet. "
                    "Pick another window to see the practice stream.", icon=":material/schedule:")
            if view != "Leaderboard copy":
                return
        if view == "Leaderboard copy":
            leaderboard_view(t0, t1, label, official)
        elif view == "Health":
            health_view(t0, t1, label)
        elif view == "Model performance":
            performance_view(t0, t1, label)
        else:
            store_view()
    except Exception as e:  # a failed query should not blank the whole dashboard
        st.error(f"{type(e).__name__}: {e}", icon=":material/error:", title="Could not load data")
    st.caption(f"Updated {pd.Timestamp.now(tz=data.TZ):%H:%M:%S} · refreshes every {refresh_s} s")


status_bar()
live_body(window_choice, view)

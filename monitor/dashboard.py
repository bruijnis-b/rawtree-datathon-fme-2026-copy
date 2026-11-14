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


@st.cache_data(ttl=55, max_entries=2, show_spinner=False)
def load_official(bucket: int) -> dict | None:
    try:
        snap = data.official_snapshot()
    except Exception:
        return None
    data.record_snapshot(snap)
    return snap


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
    model = (last5.loc[last5["team"], "model_version"].mode().iat[0]
             if len(last5) and last5["team"].any() else "–")

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
        st.metric("Model live", model, border=True)


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
                       f"{fmt(ref.get('conversion'), 3, '%')} · model `{ours.get('model_version') or '–'}`")
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
        st.markdown("**By model version** (from `model_version` in our submissions)")
        st.dataframe(group_table(df, "model_version"), hide_index=True, column_config=GROUP_COLS,
                     alt="Conversion per model version")

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Conversion per 10 minutes**")
        b = df.assign(bucket=naive(df["ts"]).dt.floor("10min")).groupby(["bucket", "model_version"]).agg(
            requests=("rid", "size"), purchases=("bought", "sum")).reset_index()
        b["conversion"] = 100 * b["purchases"] / b["requests"]
        chart = alt.Chart(b).mark_line(point=True).encode(
            x=alt.X("bucket:T", title=None), y=alt.Y("conversion:Q", title="Purchases per 100 requests"),
            color=alt.Color("model_version:N", title=None),
            tooltip=["bucket:T", "model_version:N", "requests:Q", "purchases:Q",
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

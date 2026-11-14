"""Sweep view `axes`: what does each design choice do to the result?

One panel per setting that varies in the sweep: every run as a dot at its value, and the mean per value. A table
lists the effect of every value against the sweep's default. Reads only what the runs logged (see "Logging contract"
in docs/EMBED_SWEEPS_FINAL.md).
"""
from collections import defaultdict

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import ivan

sweep = ivan.results.sweep()
METRIC = sweep.metric or "objective"
REPEAT = {"fold", "seed", "data.fold", "train.seed", sweep.seed_parameter}
PARTS = [("lift_all", "Lift all"), ("lift_cold", "Lift cold")]

runs = [r for r in sweep.runs if isinstance(r.summary.get(METRIC), (int, float))]
if len(runs) < 2:
    raise ivan.results.MissingData(f"{sweep.name} needs at least 2 runs with a summary value {METRIC!r}")

settings = sorted(k for k in {k for r in runs for k in r.params}
                  if k not in REPEAT and len({str(r.params.get(k)) for r in runs}) > 1)
if not settings:
    raise ivan.results.MissingData(f"no setting varies between the runs of {sweep.name}")


def short(key: str) -> str:
    return key.split(".")[-1]


def order(values):
    """Numbers in numeric order, anything else alphabetically."""
    try:
        return sorted(values, key=float)
    except (TypeError, ValueError):
        return sorted(values)


def mean(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else None


overall = mean([r.summary[METRIC] for r in runs])
columns = min(3, len(settings))
grid_rows = -(-len(settings) // columns)
fig = make_subplots(rows=grid_rows, cols=columns, subplot_titles=[short(k) for k in settings], shared_yaxes=True,
                    vertical_spacing=min(0.12, 0.6 / grid_rows))
effects = []
for i, key in enumerate(settings):
    row, col = i // columns + 1, i % columns + 1
    by_value = defaultdict(list)
    for r in runs:
        by_value[str(r.params.get(key))].append(r)
    values = order(by_value)
    dots = [r for v in values for r in by_value[v]]
    fig.add_scatter(row=row, col=col, x=[str(r.params.get(key)) for r in dots], y=[r.summary[METRIC] for r in dots],
                    mode="markers", marker=dict(size=7, opacity=0.55, color=ivan.style.SERIES[0]), showlegend=False,
                    customdata=[[r.name] for r in dots], meta=ivan.results.link(dots),
                    hovertemplate=f"<b>%{{customdata[0]}}</b><br>{short(key)} = %{{x}}<br>objective %{{y:+.3f}}<extra></extra>")
    means = [mean([r.summary[METRIC] for r in by_value[v]]) for v in values]
    fig.add_scatter(row=row, col=col, x=values, y=means, mode="lines+markers", showlegend=False,
                    marker=dict(size=11, symbol="diamond", color=ivan.style.SERIES[1]), line=dict(color=ivan.style.SERIES[1]),
                    customdata=[[len(by_value[v])] for v in values],
                    hovertemplate=f"{short(key)} = %{{x}}<br>mean objective %{{y:+.3f}} over %{{customdata[0]}} runs<extra></extra>")
    fig.add_hline(y=overall, line_width=1, line_dash="dot", row=row, col=col)
    fig.update_xaxes(type="category", row=row, col=col)
    for v, m in zip(values, means):
        effect = {"Setting": short(key), "Value": v, "Runs": len(by_value[v]), "Mean objective": m,
                  "vs. sweep mean": m - overall}
        effect.update({name: mean([r.summary.get(part) for r in by_value[v]]) for part, name in PARTS})
        effects.append(effect)
fig.update_layout(height=max(360, 300 * grid_rows))
fig.update_yaxes(title_text="Objective", col=1)
sweep.figure(fig, "axes", title="Objective per setting", section="Design choices", wide=True,
             caption="Blue dots: one run each (click to open). Orange diamonds: the mean per value. Dotted line: the "
                     "mean of the whole sweep. In a one-axis-at-a-time sweep, the value shared by most runs is the default.")

effects.sort(key=lambda e: (e["Setting"], -e["Mean objective"]))
sweep.table("effects", effects, title="Effect of every value", section="Design choices",
            formats={"Mean objective": "{:+.3f}", "vs. sweep mean": "{:+.3f}", "Lift all": "{:+.1%}", "Lift cold": "{:+.1%}"},
            caption="Means over the runs with that value. With few runs per value, differences below about one "
                    "standard error of a run are noise.")

# Which single change helps most: the range of the per-value means, per setting.
spread = defaultdict(list)
for e in effects:
    spread[e["Setting"]].append(e["Mean objective"])
ranked = sorted(((max(v) - min(v), k) for k, v in spread.items()), reverse=True)
fig = go.Figure()
fig.add_bar(x=[s for s, _ in ranked][::-1], y=[k for _, k in ranked][::-1], orientation="h",
            hovertemplate="%{y}<br>best value − worst value: %{x:.3f}<extra></extra>")
fig.update_layout(xaxis_title="Best value − worst value (mean objective)", showlegend=False,
                  height=max(300, 28 * len(ranked) + 120))
sweep.figure(fig, "importance", title="Which choices matter most", section="Design choices",
             caption="The difference in mean objective between a setting's best and worst value.")

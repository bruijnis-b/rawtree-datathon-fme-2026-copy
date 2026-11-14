# Team monitor

A Streamlit dashboard that watches our recommender live: is it answering, is it selling, and how does
our leaderboard row look, including during the final (Sun 15 Nov 10:00–12:00 CET), when the public
leaderboard goes dark.

## Run

From the repo root, with `TEAM_ID` and `RAWTREE_API_KEY` in `.env`:

Each command on its own (Windows PowerShell 5.1 has no `&&`):

```bash
uv venv .venv
```

```bash
uv pip install --python .venv/Scripts/python.exe -r monitor/requirements.txt
```

```bash
.venv/Scripts/python.exe -m streamlit run monitor/dashboard.py
```

Open http://localhost:8501. To keep our official numbers recorded while nobody has the dashboard
open (overnight, and before the final), also run:

```bash
.venv/Scripts/python.exe -m monitor.record_official
```

## Views

Always at the top, refreshed every 5 s on its own (uncached), a health strip with two signals of
different speed:

- **Answering now** (fast): of the requests that arrived 4–15 s ago, the share that has a submission
  of ours. It reads `team_NN.submissions` directly instead of waiting for feedback, so it goes red
  within about 10 s of the recommender stopping and green again soon after it restarts. Below 50%
  the banner turns red.
- **Status light** (slow, the organisers' rule): more than 90% of requests in the last 5 minutes
  answered validly and on time, from feedback. It lags by design: feedback lands about 4 s after
  each request, and a 5-minute share needs about 30 s of misses to drop below 90% (and minutes of
  good answers to recover). While we answer but this is still below 90%, the banner is amber.

The strip also shows when our last answer was served (from feedback), how fresh the request stream
is, and which models are live (a count during A/B tests; hover for the list). Ages are shown no finer than the strip's 5 s refresh.

| View | What it shows |
|---|---|
| **Leaderboard copy** | Our row only. *Official*: conversion, cold conversion, on time and revenue per request from the public leaderboard, with baseline and reference for context, plus our hourly official score. *Self-computed*: the same columns from `team_NN.feedback` for the selected window. A calibration line compares both over the official window. |
| **Health** | Requests per minute by who served them (us, late, invalid, missing), answer latency p50/p95 against the 3 s deadline, fallback reasons. |
| **Model performance** | Per model (public `model_version` IDs translated to policy chain and settings with our private `recsys/model_versions.json`): **estimated leaderboard score** and official expected conversion (from the leaderboard's per-model view), plus realised conversion, click rate and revenue, conversion per 10 minutes, clicks and purchases per carousel slot, cold vs warm requests, page × device. |
| **Store** | Trending subcategories (views in the last 15 min vs the 3 h before), organic activity per minute, catalogue changes in the last hour as fixed cards (new product, price change, out of stock, back in stock, each with the change vs the hour before) plus how many products are out of stock right now, and a table of the changes. |

Sidebar: the time window (15 min, 1 hour, 3 hours, final round) and the auto-refresh interval for
the views below the health strip (their queries are cached for up to 25 s).

## How to read the numbers

- **Official vs self-computed.** The leaderboard scores *expected* purchases (each shopper's buy
  probability from the hidden model). Feedback only has *realised* purchases, which are noisy:
  about 1 purchase per 100 requests, so an hour gives roughly ±0.2 points of conversion at 95%.
  Compare models over an hour or more and check the ± column.
- **When the leaderboard goes dark**, the official side keeps the last values recorded in
  `data/official_snapshots.jsonl` (written by the dashboard and by `record_official.py`).
- **Cold requests** follow the challenge definition: a new user, or recent views that include a product
  added during the event (`new_product` in `shop.catalog_updates`).
- **On time** is the share of requests served by us (`served_by = team`): valid and within 3 s.
- Times are Barcelona time (CET).

- **Score (est.)** per model: the leaderboard's formula applied to that model's official expected
  conversion in the selected window, as if it had answered every request. The leaderboard hides the oracle
  (the top anchor), so it is estimated as 1.31 x the reference's conversion, fitted on every team's
  published hourly scores (error ~0.2 points). On the practice day reliability added nothing to the score.
  The per-model numbers come from `https://datathon.rawtree.dev/api/state?by=model&from=..&to=..`.

## Files

| File | Role |
|---|---|
| `dashboard.py` | The Streamlit app |
| `data.py` | SQL against RawTree and the leaderboard feed; no Streamlit, reusable in scripts |
| `rawtree.py` | Minimal HTTP client; reads `.env`, never prints the key |
| `record_official.py` | Saves our official leaderboard row every minute |
| `requirements.txt` | Dependencies for the monitor |

Data sources: `team_NN.feedback` and `team_NN.submissions` (for `model_version`, named via `recsys/model_versions.json`), `shop.requests`
(context and cold flag), `shop.events`, `shop.catalog`, `shop.catalog_updates`, and the public
`https://datathon.rawtree.dev/api/state` feed (only our row is used).

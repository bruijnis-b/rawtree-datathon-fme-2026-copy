# Final round runbook (Sun 15 Nov, 10:00–12:00 CET = 09:00–11:00 UTC)

Live: one process, `python -m recsys.main --arms arms.txt`, in `D:/Documenten/rawtree-live` (branch `run/live-ab`),
serving only the final setup: `md363d5` = average of models v10 and v11, default settings except `cart=2.5`.
Whatever it answers 10:00–12:00 CET is scored. The leaderboard shows only a status light from 10:00.

## What to look at (dashboard, http://localhost:8502)

| Where | Healthy | Act when |
|---|---|---|
| Health strip: **Answering now** | 100% | below ~95% for more than a minute |
| Health strip: **Status light, 5 min** | green, 98–100% | amber or red (organisers' light: > 90% valid and on time) |
| Health strip: **Model live** | `md363d5` only | anything else |
| Health tab: answer latency p95 | ~1.0–1.7 s | above 2.5 s for several minutes (deadline is 3 s) |
| Health tab: fallbacks | a few per window at most | a steady stream |
| Model performance: realised conversion | ~2% ± 0.3 per 30 min | far below 1% for half an hour (noise is large; do not react to one window) |
| Store tab: trending subcategories, catalogue changes | new products at 10:00, trends | nothing to do: both are handled automatically |

The official per-model numbers go dark at 10:00 CET; from then on only our own feedback counts (realised
purchases, noisy). Do not judge the model on it in the final round: there is nothing to switch to.

## Scenarios and what to do

| Scenario | How you see it | Action |
|---|---|---|
| **Process died** | Answering now drops to 0%; my log watch reports "NO ANSWERS" | Restart it (command below). Costs ~15 s without answers |
| **RawTree network blips** | a few fallbacks, "loop error / read timed out" in the log | Nothing. It recovered on its own every time overnight (01:15, 05:50, 08:02, 08:09 UTC) |
| **300 new products at 10:00** | "catalogue: applied {'new_product': 300 ...}" then "embedded 300 new products" per model, within ~2 s | Nothing. If "embedding new products failed" repeats: the products are still served by the guard's fallback and the rest of the catalogue; tell me |
| **New trend** | Store tab, or "trend started: X" in the log, ~3 min after it starts | Nothing. x8 lift applies automatically (checked on Face Cream, 07:30 UTC) |
| **Big discounts** | price changes in the Store tab | Nothing. The discount lift is uncapped in the final setup (a 40% discount gets about x2.6); no evidence to change it |
| **Model fails on every request** | "policy errors" > 0 in every stats line; answers padded from the fallback | Emergency switch, no restart: `cp arms.emergency.txt arms.txt` (policy `combined`, no model). Only if it persists for minutes |
| **Laptop sleeps** | everything stops | Prevent it: on AC power, lid open, sleep off. Windows here sleeps after **2 h idle on AC** |
| **Key rejected** | "push errors" > 0 every window, status light red | Check `.env` (`RAWTREE_API_KEY`) in `D:/Documenten/rawtree-datathon-fme-2026` |

Restart (only if the process is dead), from a Git Bash terminal:

```bash
cd /d/Documenten/rawtree-live && set -a && . /d/Documenten/rawtree-datathon-fme-2026/.env && set +a && python -m recsys.main --arms arms.txt
```

## Too dangerous during the final round

- **A second process answering.** Only one `recsys.main` without `--dry-run` may run, anywhere (laptop, office PC,
  IVAN). Two would send two answers per request. Jules: please run nothing live.
- **Restarting a healthy process**, for any reason: ~15 s without answers and 25–40 fallbacks.
- **Changing `arms.txt`, settings or code** without a failure that the table above names. There is no live
  comparison any more, so any change is untested.
- **Offline jobs or dry runs on this laptop** (`refit.download/build`, `--dry-run`): they cost the live process CPU
  and caused fallbacks overnight, and dry runs write to the same log file.
- **New models.** The trainer is finished; nothing goes live untested.
- **`git pull` / checkout in `D:/Documenten/rawtree-live`.** Harmless until a restart, but then the restart runs
  code nobody tested live.

## Who watches what

- **Bas:** the dashboard health strip, and the laptop (power, lid, sleep).
- **Claude (side):** a watch on the live log that reports errors, silence (> 90 s without a stats line), new
  products, embedding failures, trends and arms changes as they happen; and a check every 30 minutes (health,
  our feedback, and once after 10:00 CET whether the 300 new products use brands or subcategories the models never
  saw: the 100 from 06:00 UTC had none). Claude does not restart or change anything without Bas's go.

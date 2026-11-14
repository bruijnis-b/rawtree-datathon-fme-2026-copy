# Night loop: live arms until 06:30 (Sun 15 Nov)

Goal: by 06:30, pick the best (policy × embedding model) pair, chosen on live results, and run it as the
champion. Tonight is the last chance to score arms on the leaderboard's per-model view: expected (no-luck)
conversion and cold conversion per `model_version`. That view goes dark at 10:00.

## Roles

| Who | Runs where | Does |
|---|---|---|
| **Server** | Bas's machine, one process: `python -m recsys.main --arms arms.txt` | Answers every request. Reloads `arms.txt` within ~2 s; an arm whose line is unchanged keeps its state |
| **Loop job** | Bas's machine, every 15 min: `python -m recsys.night.loop` | Pulls the `night` branch, builds `arms.txt` from the lane files, fetches models, writes and pushes the report |
| **Bas's session** | Claude, `/loop 30m` | Owns the policy lane: edits `night/lane_bas.txt` only |
| **Jules's session** | Claude, `/loop 30m` | Owns the embedding lane: trains/selects models, publishes them, edits `night/lane_jules.txt` only |

Everything goes through git, on the `night` branch of our private repo. Each writer owns its own files, so
there are no merge conflicts:

| File | Written by | Read by |
|---|---|---|
| `night/control.txt` | Loop job (promotion rule below) | Everyone |
| `night/lane_bas.txt`, `night/lane_jules.txt` | One session each | Loop job |
| `night/report.md`, `night/report.json` | Loop job | Both sessions |
| `night/decisions.md` | Both sessions (append only, one line per decision) | Everyone, plus the jury story later |

Never write any of this to a RawTree table: only the opaque `model_version` leaves the repo.

## Traffic budget (fixed shares, 1 % buckets by request ID)

| Share | Arm(s) | Contents |
|---|---|---|
| 10 + 10 | **Control A/A** | Two copies of the champion with different public IDs (a no-op `tag=a` / `tag=b` setting). The gap between them is the noise floor of each window |
| 40 | **Bas's lane** | Up to 3 policy variants, all on the **champion embedding model** |
| 40 | **Jules's lane** | Up to 2 embedding models (v2, v3, ...), each inside the **champion policy**: `<champion policy>:embed_model=vN` |

Each lane changes one factor and keeps the other at the champion's value, so every arm is compared with the
control in the same window. A lane with fewer arms gives its unused share to the control.

Lane file format (the same as the `--arms` file, shares within the lane, summing to 40):

```
20 embed_score:embed_model=v2
20 embed_score:embed_model=v3
```

## Getting a model from Jules to the server

1. Jules's session: `python -m recsys.embeddings publish models/vN --name vN` (GitHub release + manifest
   entry), then commits `recsys/embed_models.json` to `night` together with the lane line that uses it.
2. Loop job: `git pull`, then `python -m recsys.embeddings fetch vN` for every model a lane names that is
   not downloaded yet. The server reads the manifest on every load, so no restart is needed.
3. Loop job: before an arm goes into `arms.txt`, loads it once in dry-run mode: does it fit, are 50
   sample requests under 50 ms p95? If not, the arm is left out, and the report says why.

A model that needs **new serving code** (a new backend or history mode) needs a server restart. Bundle those
into a planned restart at a cycle boundary, announced in `decisions.md`. Restart from `arms.txt`, so every
arm comes back.

## The cycle (every 30 min, at :00 and :30)

```
:00  Loop job       pull → compose arms.txt → server reloads → report → push
:05  Both sessions  pull, read report.md, decide, edit own lane, append to decisions.md, push
:15  Loop job       pull → compose (lane changes go live) → report → push
:30  ... repeat
```

### What the report shows (per arm, vs control, over the arm's own live window and the last 60 min)

- **Official** (leaderboard per-model view): requests, expected conversion, expected cold conversion and
  estimated score (`monitor.data.estimated_score`, the leaderboard formula). **This is the primary metric.**
- **Feedback** (`team_NN.feedback` × `submissions` × `requests`): realised conversion, click rate and
  revenue, split into cold / new user / known user with history / cart, with 95 % intervals, plus fallback
  and late rates. This tells us **why** an arm wins (e.g. better on new users, worse on known ones).
- **Noise floor:** |A − B| of the control copies over the same window.
- **Calibration:** realised vs official conversion over the whole night, so that during the final (no
  leaderboard) we know how far to trust the feedback numbers.

### Decision rules (the same for both lanes)

- **Minimum exposure:** judge an arm only after ≥ 45 min live and ≥ 2,000 official requests.
- **Kill:** estimated score below the control by more than 2 × the noise floor, or cold conversion clearly
  worse, or fallback/late rate above 1 %. Remove its line and free the share.
- **Promote:** after ≥ 60 min, the estimated score is above the control by more than 2 × the noise floor,
  over both the arm's whole window and the last 60 min, and cold conversion is not worse. The loop job
  writes the new champion to `night/control.txt`, at most once per hour. Both lanes then rebase onto it: Bas's
  arms take the new embedding model, Jules's arms the new policy.
- **Otherwise:** keep running. An arm that is still level with the control after 90 min is dropped (the
  difference is too small to matter tonight).
- Never change an arm's settings in place: changed settings make a new arm (a new public ID).

### What each session does in its turn

**Jules's session (embedding lane):** read the per-segment feedback of its arms (cold and new-user rows
first: cold start is ~14 of the 100 points). Offline, pick the next candidate that targets the weakest
segment: from the sweep results, at most 2 live at once. Publish it and add its lane line before :05 so it
goes live at :15. Log in `decisions.md`: model, why, which arm it replaces.

**Bas's session (policy lane):** the same, for corrections on top of the champion model (trend, discount,
cart, `score_weight`, cold-product boost). No new policy files after 05:00 (they need a restart).

## Timeline

| Time | What |
|---|---|
| Until ~01:00 | Build and test `recsys.night` (compose, report, loop); start the server with control + lanes; first report |
| 01:00–05:30 | Cycles. New arms may start until 05:30 (they need ≥ 60 min) |
| 05:30–06:30 | No new arms. The top 1–2 challengers keep running so the champion is confirmed over ≥ 60 min |
| **06:30** | Freeze: the champion in `control.txt` is the final config. Write `night/final.md` (policy, model, settings, public ID, its numbers). Set the server to the champion at 100 % |

## Failure handling

- **Server down:** the monitor's "Answering now" goes red in ~10 s. Restart from `arms.txt`; reliability
  matters more than any arm.
- **Bad `arms.txt`:** the server logs it and keeps its old arms. The loop job validates before writing, so
  this should not happen.
- **Model fetch or load fails:** the arm is skipped, the report says why, and the lane's share goes to the
  control.
- **Leaderboard view unavailable:** decide on feedback only, with doubled minimum exposure, and say so in
  `decisions.md`.

## To build (≈ 1 h)

- `recsys/night/compose.py`: lanes + control → validated `arms.txt` (shares, budget, A/A tags, model fetch,
  dry-run load check).
- `recsys/night/report.py`: per-arm official + feedback by segment, noise floor, calibration, promote/kill
  suggestions → `report.md` / `report.json`. Reuses `monitor/data.py`.
- `recsys/night/loop.py`: every 15 min: pull, compose, report, promote, commit and push (only `arms.txt`
  stays local; `night/*` is pushed).
- Check that a no-op `tag` setting is accepted by the arm parser and makes a separate public ID; add it to
  `Policy` if not.

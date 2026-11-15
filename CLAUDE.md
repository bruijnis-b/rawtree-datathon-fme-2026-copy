# RawTree Challenge · Datathon FME 2026 (finished)

Real-time recommender: for each row in `shop.requests`, insert 10 ranked, distinct, active product IDs into
`team_NN.submissions` within 3 s of the request `ts`. Full rules: `CHALLENGE_README.md` (the organisers' README);
our own overview and result: `README.md`.

**The event is over.** It was scored only on Sun 15 Nov 2026, 10:00–12:00 CET. This repo is now a record: do not
start a live server, and expect the RawTree database to be read-only or gone.

## What the final round asked for (context for reading the code)

- **300 new products** were added at 10:00 (`new_product` in `shop.catalog_updates`), each with only its
  catalogue fields: no ID history, no sales. Every model had to score them from content alone.
- **New trends** started in the final round and could only be picked up from the live stream (the trend layer).
- **New shoppers:** in the practice stream, a third of users were not in the 60-day history.
- **Cold start was 10 of the 70 automatic points.** A request was cold when `is_new_user` was set, or when its
  `recent_views` contained a product added during the event.
- What ran in the final and why: `recsys/README.md`, "Final setup (15 Nov)"; arms file `recsys/arms.final.txt`.

## Opaque model IDs

- Every submission's `model_version` was an opaque random ID (e.g. `m3f9a2c`) from
  `recsys.model_registry.public_id(policy)`, so other teams could not read our approach from it. Its meaning
  lives in `recsys/model_versions.json`.
- Keep this repo private: it holds the mapping and our evidence.

## Repo layout

- `starter/`: the organisers' starter kit (baseline recommender, SQL examples, offline evaluation notebook).
- `monitor/`: our Streamlit monitoring dashboard. Read `monitor/README.md` before running or changing it.
- `recsys/`: our recommender (live catalogue, policies, guard, serving loop). Read `recsys/README.md` before
  running or changing it. Only one process may answer live at a time.
- `training/`: Jules's model code (history export, data inspection, embedding training on IVAN).
- `conf/`, `ivan.yaml`, `pyproject.toml`: the Hydra config and uv project that IVAN runs `training/` with.

## Plan & tools

- **`docs/POA.md`**: the general approach (product × user embeddings, live steering) and who does what
  (Jules: the model, which returns scores; Bas: the framework, live adjustments, serving).
- **IVAN** (Team Epoch's GPU scheduler) runs training and sweeps. CLI reference: `ivan-cli.md` in
  `TeamEpochGithub/ivan` (Jules's laptop: `C:\Users\jules\Projects\ivan\ivan-cli.md`).
  - From outside the office, set `IVAN_URL=http://localhost:8000`, through an SSH tunnel to an office PC (`ssh epoch`).
  - Runs that read or write data use `--machine epochserver`, because the share lives there.
  - `ivan data add` needs the share mounted: run it on an office PC (`ssh epoch`, epochviipc5).
- **Historical data**: IVAN dataset `rawtree_history` (`ivan.data.path("rawtree_history")`). Locally it lives at
  `data/raw/rawtree_history/` (gitignored), as Parquet. Inspect it with `python -m training.data.inspect`.

## Accessing RawTree

- Credentials live in `.env` (`TEAM_ID`, `RAWTREE_API_KEY`). Never print, log or commit the key.
- For RawTree work, load the `rawtree` skill (`.claude/skills/rawtree/`) and its matching references first.
- Three equivalent surfaces:
  - **MCP**: server `rawtree` (hosted, API-key auth, local scope). Tools: `run-query`, `insert-json`, `describe-table`, `list-tables`, ...
  - **CLI**: `rtree` (installed in `~/.local/bin`). Load env first:
    `set -a; . ./.env; set +a; export RAWTREE_DATABASE=$TEAM_ID; rtree query --json "SELECT ..."`
  - **HTTP**: `POST https://api.rawtree.com/v1/query` `{"sql": ...}`; inserts `POST /v1/tables/{table}?database=$TEAM_ID`.
- The team key can read `shop.*` and read/write its own database only. Use `LIMIT` while exploring; queries time out at 30 s.
- Do not send RawTree feedback reports (`rtree feedback`, `submit-feedback`) without asking the user first.

## Data gotchas

- Every column is `Dynamic`. Cast join keys, `argMax`/`argMin` and some aggregates: `product_id::String`, `ts::DateTime64(3)`.
- `ts` is stored as `DateTime64(9)` (UTC). Aggregates like `max(ts)` come back over JSON as epoch floats
  (e.g. `1794657975.682`). Cast before comparing: `ts::DateTime64(3) > now() - INTERVAL 1 HOUR`.
- `team_NN.feedback` has a placeholder row `request_id = '__init__'`; filter it out.
- Products go out of stock live (`shop.catalog_updates`); an out-of-stock or inactive item makes the whole answer invalid.
- `history_sessions` = old carousel log (shown, propensity, clicked, purchased). `history_events` = organic views,
  add-to-cart and purchases outside the carousel. Live equivalents: `team_NN.feedback` and `shop.events`.

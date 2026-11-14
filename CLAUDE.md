# RawTree Challenge · Datathon FME 2026

Real-time recommender: for each row in `shop.requests`, insert 10 ranked, distinct, active product IDs into
`team_NN.submissions` within 3 s of the request `ts`. Full rules: `CHALLENGE_README.md` (the organisers' README);
our own overview: `README.md`. Scored only Sun 15 Nov 10:00–12:00 CET.

## Never leak our approach (IMPORTANT)

- The `model_version` field of every submission must be an **opaque random ID** (e.g. `m3f9a2c`) that reveals
  nothing: no policy or algorithm names, parameters or version counts. Other teams may be able to read it.
- Get it from `recsys.model_registry.public_id(policy)`; its meaning lives only in our private
  `recsys/model_versions.json`. Never send `Policy.internal_version` or any descriptive string.
- The same goes for anything else we write to a table others might read.

## Repo layout

- `starter/`: the organisers' starter kit (baseline recommender, SQL examples, offline evaluation notebook).
- `monitor/`: our Streamlit monitoring dashboard. Read `monitor/README.md` before running or changing it.
- `recsys/`: our recommender (live catalogue, policies, guard, serving loop). Read `recsys/README.md` before
  running or changing it. Only one process may answer live at a time.

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

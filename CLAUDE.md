# RawTree Challenge · Datathon FME 2026

Real-time recommender: for each row in `shop.requests`, insert 10 ranked, distinct, active product IDs into
`team_NN.submissions` within 3 s of the request `ts`. Full rules: `README.md`. Scored only Sun 15 Nov 10:00–12:00 CET.

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
- Timestamps are stored as Unix epoch seconds (floats, e.g. `1794657975.682`), not ISO strings. String date filters
  like `ts < '2026-11-07'` (used in the starter code) may not behave as intended; verify before trusting them.
- `team_NN.feedback` has a placeholder row `request_id = '__init__'`; filter it out.
- Products go out of stock live (`shop.catalog_updates`); an out-of-stock or inactive item makes the whole answer invalid.
- `history_sessions` = old carousel log (shown, propensity, clicked, purchased). `history_events` = organic views,
  add-to-cart and purchases outside the carousel. Live equivalents: `team_NN.feedback` and `shop.events`.

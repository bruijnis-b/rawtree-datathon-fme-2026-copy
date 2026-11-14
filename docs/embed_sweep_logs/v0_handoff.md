# v0 for Bas (Sat 21:39 CET)

**Where:** `models/v0/` on Jules's laptop (copied from IVAN `embed-v0`, share path
`/mnt/epoch/projects/rawtree/experiments/names/embed-v0/1/export`). Not committed: send the folder directly
(≈ 21 MB incl. `model.pt`; the scorer needs only `model.npz` and `user_vectors.npz`).

**What:** default config, trained on the history (fold 0: days 0–52, 90 % of users, 4,700 of 5,000 products with ID
vectors), git `62bc1a7`. Interface as in `docs/EMBED_HANDOFF_BAS.md`:

```python
from training.export.scorer import load
model = load("models/v0")
pm = model.embed_products(rows)          # rows: product_id, category, subcategory, brand, description, price (ORIGINAL)
pm = model.embed_products(new_rows, pm)  # append new products; returns a new matrix
scores = model.score(request, pm)        # purchase log-odds in slot 1, in pm.ids order
scores = model.score(request, pm, events=[(product_id, event_type), ...])  # optional live events, oldest first
```

Ready-made policy: `EMBED_MODEL=models/v0 python -m recsys.main --policy embed --dry-run` (plain model scores, top
10 active). `recsys/policies/embed.py` fetches the original prices itself (shop.catalog, `new_product` rows) and
embeds new products when the catalogue version changes; `Embed.scores(req)` returns ids and scores for your layer.
Dry run Sat 21:39: 0 policy errors, 0 deadline fallbacks after the start-up backlog, guard fixes none.

**Validation (fold 0, history week 8):** ips_hit@10 lift over best sellers +2.79 all / +2.73 cold; slate_auc 0.75;
organic recall@10 0.24 (best sellers 0.074). Numpy = torch to 8e-6; p99 0.2 ms per request.

**Known weaknesses of v0** (fixed in the final model if its checks pass):
- Calibration: low scores are too low (predicted purchase rate about half the observed in deciles 3–8). The top
  decile is right (0.0123 vs 0.0120). Treat v0 scores as a ranking, not exact log-odds, when you fit β on it.
- New (content-only) products are ranked a bit too high: 7.2 % of top-10 slots vs 2.6 % of clicks.
- `is_new_user` is ignored (zero weights) until the live fine-tuning.

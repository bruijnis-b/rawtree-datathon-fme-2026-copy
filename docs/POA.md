# Plan of approach

## General approach

- **Two towers.** A *product embedding* comes from content: category, subcategory, brand, price and description. A *user embedding* comes from the request: device, region, page, `recent_views` (embedded with the product tower) and the user's past events. The score is their dot product. We rank all products and the top 10 form the carousel.
- **Cold start by design.** The product tower never needs a product's ID or its interaction history, so a new product is embedded as soon as it appears in the catalogue.
- **Learned on history, steered live.** The model learns stable preferences from the 60-day history. Every live adjustment sits on Bas's side, on top of the model's scores:
  - trend boost per product or category
  - price-change correction, starting at 0 (see below)
  - out of stock and already bought: hard filter
- **Price.** The model takes the *current* price from Bas's catalogue and applies the price effect it learned from the history. Bas's correction stays at 0 unless products whose price changed sell differently from what the model predicts.
- **Validation.** Offline: the last 7 days of history, with 10 % of products held out to test cold start. Live: the practice stream and our feedback.

## Work split

### Jules: the model

- Exports the history (raw Parquet) to IVAN and to the laptop, and analyses it: which request fields drive clicks and purchases, and the effect of slot position.
- Trains the product and user towers on IVAN, including the cold-start hold-out.
- Tests early whether the model, given the current price, explains how sales change after the ~1.9 k live price changes. The result tells Bas whether he needs his correction.
- Delivers `recommend(request, catalogue) → score per product`. It gets all its inputs from Bas's API and never calls RawTree itself.

### Bas: the framework

- Builds an API that gives the model the current catalogue (with live updates applied) and each user's session and history.
- Runs the loop: read requests, call the model, apply the trend boost and the filters, take the top 10, write to `submissions`. It answers within 3 s, with fallbacks.
- Owns every live adjustment: trend detection (from `shop.events` and feedback) and the price-change correction (0 by default), both applied on top of the model's scores.
- Handles health checks, latency (office vs. campus) and retraining during the final round.

### Interface

The model returns **scores**, not just a ranked list, so Bas can apply his live adjustments before ranking. The model contract is still open; we fix it before the end of Saturday.

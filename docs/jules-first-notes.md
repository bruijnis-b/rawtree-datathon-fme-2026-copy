# Bas & Jules split

_Handoff: Jules delivers trained models, Bas serves and monitors them._

## Jules: model optimisation on historical data

- Trains and tunes models on the 60-day history, using IVAN.
- Open issue: it is unclear whether *product additions* are visible in the history. Other product events are. If they are not, new-product behaviour must be simulated (e.g. hold out products) or learned from the live stream.

## Bas: framework around the models

- **Serving:** load Jules' models and use them to answer requests.
- **Health:** validate that each model works (valid output, latency) before it goes live.
- **Retraining in the final 2-h phase:** re-activate the training pipeline, since this phase produces new data we need to keep training on.
- **Hosting:** test whether hosting from the office or from campus gives lower latency.

## Open questions:
- The historical data must learn us something about user behaviour (and maybe responses to trends), but the final phase will have new products and new trends. How do we feed live, new data in a model?

## Notes:
- The final phase will have 300 new items added at 10 am ('new catalog'). Also, new trend(s) will be launched. Everything else stays the same. Ergo, our model needs to use the live data to learn the new trends and it must adapt to 300 newly added (cold products).
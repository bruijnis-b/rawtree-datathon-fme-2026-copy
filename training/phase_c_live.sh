#!/usr/bin/env bash
# Phase C on a given live snapshot: LIVE=<rawtree_live version> TAG=<model name> bash training/phase_c_live.sh
# Same steps as phase_c.sh (check run with the live hold-out, then the 3 all-history seeds on all of the snapshot).
# 1. waits until rawtree_live v$LIVE exists;
# 2. check runs on snapshot $LIVE with the live hold-out: phase C base (fold 0) without and with fine-tuning;
# 3. the final fine-tunes: the 3 all-history seeds (embed-c-hist) on all of snapshot $LIVE, no hold-out, with the
#    score recalibration taken from the check run;
# 4. copies every export to models/ and prints the summaries. Choosing and delivering is done by hand.
set -euo pipefail
LIVE=${LIVE:?set LIVE=<rawtree_live version>}; TAG=${TAG:?set TAG=<name suffix, e.g. v4>}
cd "$(dirname "$0")/.."
export IVAN_URL=${IVAN_URL:-http://localhost:8000}
RECIPE="ft.history_share=0.5 ft.lr_mult=0.3 ft.new_id_dropout=0.5 ft.train=all ft.feedback=false ft.cart=false ft.new_user_trunc=true ft.min_history_events=5"
NAMES=/mnt/epoch/projects/rawtree/experiments/names
wait_done() { until ivan experiment show "$1" 2>/dev/null | head -1 | grep -q "finished\|failed"; do sleep 30; done; ivan experiment show "$1" | head -1; }

echo "[phase C $(date +%H:%M)] waiting for rawtree_live v$LIVE"
until ssh epoch 'bash -ic "ivan data --project rawtree show rawtree_live"' 2>/dev/null | grep -q "^  v$LIVE "; do sleep 30; done
echo "[phase C $(date +%H:%M)] rawtree_live v$LIVE is published"

ivan run training.finetune base=embed-cmp/1 live.version=$LIVE ft.epochs=0,2 $RECIPE --name embed-c-check-$TAG \
  --hypothesis "Phase C check: the final recipe on the phase C base (fold 0) with the live hold-out on snapshot $LIVE; tuned must beat untuned, and gives the score recalibration for the final runs"
wait_done embed-c-check-$TAG
CHECK_JSON=$(ssh epoch "cat $NAMES/embed-c-check-$TAG/2/ivan/summary.json" 2>/dev/null)
AFF=$(printf "%s" "$CHECK_JSON" | python -c "import json,sys;s=json.load(sys.stdin);print(f\"{s['score_a']:.4f},{s['score_c']:.4f}\")")
echo "[phase C $(date +%H:%M)] check run recalibration: [$AFF]"
wait_done embed-c-hist
ivan run training.finetune base=embed-c-hist/1,embed-c-hist/2,embed-c-hist/3 live.version=$LIVE ft.holdout=false \
  ft.all_history=true "ft.score_affine=[$AFF]" ft.history_modes=false ft.epochs=2 $RECIPE --name embed-c-final-$TAG \
  --hypothesis "Phase C final: the 3 all-history seeds fine-tuned on all of live snapshot $LIVE (no hold-out) with the final recipe; recalibration from embed-c-check-$TAG"
ivan group add "Embed phase C" embed-c-check-$TAG embed-c-final-$TAG >/dev/null
wait_done embed-c-final-$TAG
for k in 1 2 3; do
  rm -rf "models/$TAG-$k"
  scp -q -r "epoch:$NAMES/embed-c-final-$TAG/$k/export" "models/$TAG-$k" 2>/dev/null || echo "copy of final-$k failed"
done
for x in embed-c-check-$TAG/1 embed-c-check-$TAG/2 embed-c-final-$TAG/1 embed-c-final-$TAG/2 embed-c-final-$TAG/3 embed-c-hist/1 embed-c-hist/2 embed-c-hist/3; do
  echo "== $x"; ssh epoch "cat $NAMES/$x/ivan/summary.json" 2>/dev/null | python -c "
import json,sys; s=json.load(sys.stdin)
print({k: round(v, 4) for k, v in s.items() if isinstance(v, (int, float)) and k in ('objective', 'live_objective',
  'live_objective_before', 'live_lift_cold', 'fb_lift_all', 'fb_lift_new_user', 'calibration_max_err', 'parity_max_abs',
  'product_parity_max_abs', 'latency_p99_ms', 'score_a', 'score_c', 'hm_dynamic_5_new_user', 'hm_none_0_new_user',
  'live_share_top10_heldout_new', 'live_share_purchases_heldout_new')})"
done
echo "[phase C $(date +%H:%M)] done"

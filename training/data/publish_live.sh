#!/usr/bin/env bash
# Live snapshot: export on the laptop, copy to the office PC, publish as IVAN dataset rawtree_live.
# Usage (repo root): bash training/data/publish_live.sh "<note>"
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
.venv/Scripts/python -m training.data.export_live --out data/raw/rawtree_live
UNTIL=$(python -c "import json;print(json.load(open('data/raw/rawtree_live/manifest.json'))['until_utc'])")
ssh epoch "rm -rf ~/rawtree_live" 2>/dev/null || true
scp -q -r data/raw/rawtree_live epoch:~/rawtree_live 2>&1 | grep -v "bind\|channel_setup\|forwarding" || true
ssh epoch "bash -ic 'export PATH=\$HOME/rsyncfix:\$PATH; ivan data --project rawtree add rawtree_live ~/rawtree_live -m \"live stream up to $UNTIL UTC. $1\"'" 2>&1 | grep -v "bind\|channel_setup\|forwarding\|cannot set terminal\|no job control"

"""Record our own row of the public leaderboard every minute, so it survives the final-round blackout.

    python -m monitor.record_official

Appends to data/official_snapshots.jsonl (one line per leaderboard update). The dashboard also
records while it is open; run this when nobody has the dashboard open (overnight).
"""
from __future__ import annotations

import time

from monitor import data


def main() -> None:
    while True:
        try:
            snap = data.official_snapshot()
            data.record_snapshot(snap)
            ours = snap.get("ours") or {}
            print(f"{time.strftime('%H:%M:%S')} mode={snap.get('mode')} conversion={ours.get('conversion')} "
                  f"on_time={ours.get('on_time')}", flush=True)
        except Exception as e:  # keep recording through network hiccups
            print(f"{time.strftime('%H:%M:%S')} error: {e}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()

"""Leaderboard from backed-up IVAN experiments: python -m training.embed.collect embed-a1 embed-a2 [--md out.md].

Reads ivan_backup/<experiment>/<k>/{ivan/summary.json, ivan-run.yaml, ivan/records/checks.jsonl}. A run is eligible
when its slate_auc and organic_recall lifts are not below the lower interval bound of the default run (preset=default
in the first experiment, else --default <exp/k>).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2] / "ivan_backup"


def runs(exp: str):
    for d in sorted((ROOT / exp).iterdir(), key=lambda p: (len(p.name), p.name)):
        s = d / "ivan" / "summary.json"
        if not d.is_dir() or not s.exists():
            continue
        meta = yaml.safe_load((d / "ivan-run.yaml").read_text()) if (d / "ivan-run.yaml").exists() else {}
        ov = meta.get("overrides") or meta.get("params") or ""
        if isinstance(ov, list):
            ov = " ".join(map(str, ov))
        if isinstance(ov, dict):
            ov = " ".join(f"{k}={v}" for k, v in ov.items())
        checks = []
        c = d / "ivan" / "records" / "checks.jsonl"
        if c.exists():
            checks = [json.loads(line) for line in c.read_text().splitlines() if line.strip()]
        yield {"run": f"{exp}/{d.name}", "overrides": str(ov), "summary": json.loads(s.read_text()), "checks": checks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("experiments", nargs="+")
    ap.add_argument("--default")
    ap.add_argument("--md")
    ap.add_argument("--key", default="objective")
    a = ap.parse_args()
    rs = [r for e in a.experiments for r in runs(e)]
    default = None
    for r in rs:
        if (a.default and r["run"] == a.default) or (not a.default and "preset=default" in r["overrides"]):
            default = r
            break
    ds = default["summary"] if default else {}
    rows = []
    for r in rs:
        s = r["summary"]
        elig = True
        if ds:
            for k in ("slate_auc_lift", "organic_recall_lift"):
                lo = ds.get(k + "_lo")
                if lo is not None and s.get(k) is not None and s[k] < lo:
                    elig = False
        r["eligible"] = elig
        rows.append(r)
    rows.sort(key=lambda r: -(r["summary"].get(a.key) or -1e9))
    hdr = ("| # | run | settings | objective ± se | lift all | lift cold | slate_auc | org. recall | cal. err | "
           "slot gap | eligible | checks failed |")
    lines = [hdr, "|" + "---|" * 12]
    for i, r in enumerate(rows, 1):
        s = r["summary"]
        f = lambda k, p=3: ("" if s.get(k) is None else f"{s[k]:.{p}f}")  # noqa: E731
        failed = ", ".join(c["check"].split(" (")[0] for c in r["checks"] if not c.get("passed"))
        lines.append(f"| {i} | {r['run']} | {r['overrides'][:90]} | {f(a.key)} ± {f(a.key + '_se')} | {f('lift_all')} | "
                     f"{f('lift_cold')} | {f('slate_auc')} | {f('organic_recall')} | {f('calibration_max_err', 2)} | "
                     f"{f('slot_max_gap', 2)} | {'yes' if r['eligible'] else 'no'} | {failed} |")
    text = "\n".join(lines)
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n")


if __name__ == "__main__":
    main()

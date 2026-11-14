"""Train the two-tower embedding model on the history: python -m training.train [overrides].

Logs to IVAN (log_step per epoch, log_records, log_summary) and writes the serving package to <run dir>/export:
model.npz, user_vectors.npz, config.yaml, metrics.json, README.txt, model.pt. See docs/EMBED_SWEEPS_FINAL.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import hydra
import numpy as np
import torch
from omegaconf import DictConfig, OmegaConf
from torch.nn import functional as Fn

import ivan
from training.embed import data as D
from training.embed.metrics import Evaluator
from training.embed.model import TwoTower
from training.embed.presets import apply_preset
from training.export import features as F

ROOT = Path(__file__).resolve().parents[1]


def log(msg: str) -> None:
    print(f"[train {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return os.environ.get("IVAN_COMMIT", "unknown")


def run_dir() -> Path:
    found = ivan.runs.dir()
    if found is not None:
        return Path(found)
    return ROOT / "outputs" / time.strftime("%Y%m%d-%H%M%S")


class Trainer:
    def __init__(self, cfg: DictConfig):
        self.cfg = cfg
        self.dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        torch.manual_seed(cfg.train.seed)
        np.random.seed(cfg.train.seed)
        self.rng = np.random.default_rng(cfg.train.seed)
        self.data = d = D.load(int(cfg.data.fold))
        self.all_data = bool(cfg.data.all)
        P = len(d.product_ids)
        self.log_theta = D.theta_table(d.vocab["device"])
        self.model = TwoTower(len(d.vocab["cat"]), len(d.vocab["sub"]), len(d.vocab["brand"]), P,
                              len(d.vocab["device"]), len(d.vocab["region"]), len(d.vocab["page"]),
                              self.log_theta, cfg).to(self.dev)
        t = lambda a: torch.as_tensor(a, device=self.dev)  # noqa: E731
        self.t = t
        held_p = np.zeros(P, bool) if self.all_data else d.heldout_products
        held_u = np.zeros(len(d.user_ids), bool) if self.all_data else d.heldout_users
        self.held_p_np, self.held_u_np = held_p, held_u
        self.prod = {k: t(v) for k, v in d.prod.items()}
        self.has_id = t((~held_p).astype(np.float32))
        self.held_p = t(held_p)
        # carousel training sessions
        s = d.s
        last = 10**9 if self.all_data else D.TRAIN_LAST_DAY
        ok = (s["day"] <= last) & ~held_u[s["user"]]
        self.train_idx = np.flatnonzero(ok)
        self.S = {k: t(v) for k, v in s.items() if k not in ("ts",)}
        rv = s["rv"].copy()
        rv[(rv >= 0) & held_p[rv.clip(0)]] = -1
        self.S["rv_train"] = t(rv)
        # history source (held-out removed): on GPU
        self.h_prod = t(d.h["prod"])
        self.h_type = t(d.h["type"])
        # organic training samples
        e = d.e
        eok = (e["day"] <= last) & ~held_u[e["user"]] & ~held_p[e["prod"]]
        self.org_idx = np.flatnonzero(eok)
        tw = np.array(cfg.organic.type_weights, dtype=np.float64)[e["type"][self.org_idx]]
        self.org_p = tw / tw.sum()
        q = np.bincount(e["prod"][self.org_idx], weights=tw, minlength=P)
        q = q / q.sum()
        self.logq = t(np.log(np.maximum(q, 1e-9)).astype(np.float32))
        erv = e["rv"].copy()
        erv[(erv >= 0) & held_p[erv.clip(0)]] = -1
        self.E = {k: t(e[k]) for k in ("prod", "device", "region", "hour", "hist_end", "hist_lo", "user")}
        self.E["rv"] = t(erv)
        self.page_org = d.vocab["page"][F.ORGANIC_PAGE]
        log(f"device {self.dev}; {len(self.train_idx)} carousel sessions, {len(self.org_idx)} organic events")

    # ---------------- helpers ----------------
    def product_matrix(self, train: bool):
        p = self.prod
        mask = self.has_id
        if train and self.cfg.model.id_dropout > 0:
            mask = mask * (torch.rand_like(mask) >= self.cfg.model.id_dropout).float()
        return self.model.products(p["cat"], p["sub"], p["brand"], p["price"], p["tokens"], mask)

    def history(self, V, end, lo, train: bool):
        N = self.model.hist_len
        B = end.shape[0]
        if N <= 0:
            z = torch.zeros(B, self.model.d, device=self.dev)
            return z, torch.zeros(B, 1, device=self.dev)
        pos = end[:, None] - 1 - torch.arange(N, device=self.dev)[None]
        hm = (pos >= lo[:, None]).float()
        if train and self.cfg.model.history_dropout > 0:
            keep = (torch.rand(B, device=self.dev) >= self.cfg.model.history_dropout).float()
            hm = hm * keep[:, None]
        pos = pos.clamp(min=0)
        return self.model.pool_history(V, self.h_prod[pos], self.h_type[pos], hm)

    def user_batch(self, V, part, idx, rv_key, page=None, train=True):
        m = self.model
        page_t = part["page"][idx] if page is None else torch.full_like(idx, page)
        ctx = m.context(part["device"][idx], part["region"][idx], page_t, part["hour"][idx])
        rec, rec_has = m.pool_recent(V, part[rv_key][idx], ctx)
        hist, hist_has = self.history(V, part["hist_end"][idx], part["hist_lo"][idx], train)
        return m.users(ctx, rec, rec_has, hist, hist_has, torch.zeros(idx.shape[0], device=self.dev))

    # ---------------- losses ----------------
    def carousel_loss(self, V, b, idx):
        S, m, cfg = self.S, self.model, self.cfg
        u = self.user_batch(V, S, idx, "rv_train", train=m.training)
        shown = S["shown"][idx]
        valid = (shown >= 0) & ~self.held_p[shown.clamp(min=0)]
        x = m.x_scale * ((u[:, None, :] * V[shown.clamp(min=0)]).sum(-1) + b[shown.clamp(min=0)])
        devi = S["device"][idx]
        k = torch.arange(10, device=self.dev)[None].expand_as(shown)
        sl = m.slot[k, devi[:, None].expand_as(shown)]
        click = (k == S["click_slot"][idx][:, None]) & valid
        w = valid.float()
        if cfg.loss.propensity_clip > 0:
            w = w / S["prop"][idx].clamp(min=cfg.loss.propensity_clip)
            w = w / (w.sum() / valid.float().sum().clamp(min=1))
        lc = Fn.binary_cross_entropy_with_logits(x + m.c_click + sl, click.float(), weight=w, reduction="sum")
        lc = lc / valid.float().sum().clamp(min=1) * 100  # per 100 impressions: about 1 click
        ck = click.any(1)
        if ck.any():
            cs = S["click_slot"][idx][ck]
            xc = x[ck].gather(1, cs[:, None])[:, 0]
            wc = w[ck].gather(1, cs[:, None])[:, 0]
            lp = Fn.binary_cross_entropy_with_logits(m.alpha * xc + m.c_purchase, S["purchased"][idx][ck].float(),
                                                     weight=wc, reduction="sum") / valid.float().sum().clamp(min=1) * 100
        else:
            lp = torch.zeros((), device=self.dev)
        return lc, lp

    def organic_loss(self, V, b, idx):
        E = self.E
        u = self.user_batch(V, E, idx, "rv", page=self.page_org)
        tgt = E["prod"][idx]
        logits = u @ V[tgt].T + b[tgt][None]
        if self.cfg.organic.logq:
            logits = logits - self.logq[tgt][None]
        same = tgt[:, None] == tgt[None]
        eye = torch.eye(len(idx), device=self.dev, dtype=torch.bool)
        logits = logits.masked_fill(same & ~eye, -1e9)
        return Fn.cross_entropy(logits, torch.arange(len(idx), device=self.dev))

    # ---------------- training ----------------
    def fit(self, evaluator):
        cfg = self.cfg
        m = self.model
        opt = torch.optim.AdamW([p for p in m.parameters() if p.requires_grad], lr=cfg.train.lr,
                                weight_decay=cfg.train.weight_decay)
        bs = int(cfg.train.batch_size)
        epochs = int(cfg.train.epochs)
        steps_per_epoch = max(1, int(len(self.train_idx) * cfg.train.epoch_fraction) // bs)
        total = epochs * steps_per_epoch
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.train.lr, total_steps=total, pct_start=0.1)
        mode = cfg.organic.mode
        step = 0
        history = []
        for ep in range(epochs):
            t0 = time.time()
            perm = self.rng.permutation(self.train_idx)[: steps_per_epoch * bs]
            org = self.rng.choice(self.org_idx, size=steps_per_epoch * bs, p=self.org_p)
            staged_org = mode == "staged" and ep < max(1, epochs // 3)
            sums = {"loss": 0.0, "loss_click": 0.0, "loss_purchase": 0.0, "loss_organic": 0.0}
            m.train()
            for i in range(steps_per_epoch):
                V, b = self.product_matrix(train=True)
                loss = torch.zeros((), device=self.dev)
                if not staged_org:
                    idx = self.t(perm[i * bs:(i + 1) * bs])
                    lc, lp = self.carousel_loss(V, b, idx)
                    loss = loss + cfg.loss.click_weight * lc + lp
                    sums["loss_click"] += lc.item() if i % 20 == 0 else 0
                    sums["loss_purchase"] += lp.item() if i % 20 == 0 else 0
                use_org = mode == "joint" or staged_org
                if use_org and cfg.organic.weight > 0:
                    oi = self.t(org[i * bs:(i + 1) * bs])
                    lo = self.organic_loss(V, b, oi)
                    loss = loss + (cfg.organic.weight if mode == "joint" else 1.0) * lo
                    sums["loss_organic"] += lo.item() if i % 20 == 0 else 0
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(m.parameters(), 5.0)
                opt.step()
                sched.step()
                if m.slot.requires_grad:
                    with torch.no_grad():
                        m.slot[0].zero_()
                if i % 20 == 0:
                    sums["loss"] += loss.item()
                step += 1
            n_logged = len(range(0, steps_per_epoch, 20))
            row = {k: v / n_logged for k, v in sums.items()}
            row["epoch"] = ep + 1
            row["train_s"] = time.time() - t0
            if evaluator is not None and (cfg.eval.every_epoch or ep == epochs - 1):
                m.eval()
                with torch.no_grad():
                    V, b = self.product_matrix(train=False)
                    r = evaluator.run(m, V, b, B=200, full=False)
                row.update(val_objective=r["objective"], val_lift_all=r["lift_all"], val_lift_cold=r["lift_cold"])
            log(" ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()))
            ivan.log_step(row, step=ep + 1)
            history.append(row)
        return history


def calibrate(tr: "Trainer", epochs: int) -> None:
    """Refit the heads with frozen towers: x -> x_scale * x, c_click, c_purchase, alpha (and the slot term if
    learned), on the carousel loss only. Then fold x_scale into the user tower output and the product biases, so the
    exported weights (and the numpy scorer) need no extra parameter."""
    m = tr.model
    heads = [m.x_scale, m.c_click, m.c_purchase, m.alpha]  # the slot term stays as trained
    saved = {n: p.requires_grad for n, p in m.named_parameters()}
    for p in m.parameters():
        p.requires_grad_(False)
    for p in heads:
        p.requires_grad_(True)
    with torch.no_grad():
        V, b = tr.product_matrix(train=False)
    opt = torch.optim.Adam(heads, lr=0.01)
    bs = int(tr.cfg.train.batch_size)
    last = tr.train_idx[tr.data.s["day"][tr.train_idx] >= tr.data.s["day"][tr.train_idx].max() - 13]
    m.eval()
    for ep in range(epochs):
        perm = tr.rng.permutation(last)
        for i in range(len(perm) // bs):
            idx = tr.t(perm[i * bs:(i + 1) * bs])
            lc, lp = tr.carousel_loss(V * 1.0, b, idx)
            loss = lc + lp
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            if isinstance(m.slot, torch.nn.Parameter):
                with torch.no_grad():
                    m.slot[0].zero_()
    g = float(m.x_scale.item())
    with torch.no_grad():
        m.u2.weight.mul_(g)
        m.u2.bias.mul_(g)
        m.p_bias.weight.mul_(g)
        m.p_bias.bias.mul_(g)
        m.b_id.weight.mul_(g)
        m.no_id.mul_(g)
        m.x_scale.fill_(1.0)
    for n, p in m.named_parameters():
        p.requires_grad_(saved[n])
    m.x_scale.requires_grad_(False)
    log(f"calibrated heads: x_scale {g:.3f}, c_click {m.c_click.item():.3f}, alpha {m.alpha.item():.3f}, "
        f"c_purchase {m.c_purchase.item():.3f}")
    tr.x_scale = g


def export_package(tr: Trainer, out: Path, cfg: DictConfig) -> dict:
    """model.npz + user_vectors.npz; returns parity and latency numbers."""
    from training.export.scorer import load as load_scorer

    out.mkdir(parents=True, exist_ok=True)
    m, d = tr.model, tr.data
    m.eval()
    w = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in m.state_dict().items()}
    w["type_w"] = m.type_w.detach().cpu().numpy()
    meta = {"vocab": d.vocab, "sub_mean": d.sub_mean, "global_mean": d.global_mean,
            "use_desc": m.use_desc, "use_price": m.use_price, "pooling": m.pooling,
            "recency": float(m.recency), "dim": m.d, "history_len": m.hist_len}
    np.savez(out / "model.npz", **w, meta__json=np.array(json.dumps(meta)),
             meta__id_products=d.product_ids.astype(str), meta__id_has=tr.has_id.cpu().numpy())
    # user vectors from each user's last N events (all history, held-out products' ID vectors masked)
    with torch.no_grad():
        V, b = tr.product_matrix(train=False)
    N = m.hist_len
    if N > 0 and cfg.export.user_vectors:
        e = d.e
        user, prod, typ = e["user"], e["prod"], e["type"]
        ends = np.searchsorted(user, np.arange(len(d.user_ids) + 1))
        lo, hi = ends[:-1], ends[1:]
        users_with = np.flatnonzero(hi > lo)
        vecs = np.zeros((len(users_with), m.d), np.float32)
        tp, tt = torch.as_tensor(prod, device=tr.dev), torch.as_tensor(typ, device=tr.dev)
        for a in range(0, len(users_with), 8192):
            uu = users_with[a:a + 8192]
            end = torch.as_tensor(hi[uu], device=tr.dev)
            lo_t = torch.as_tensor(lo[uu], device=tr.dev)
            pos = end[:, None] - 1 - torch.arange(N, device=tr.dev)[None]
            hm = (pos >= lo_t[:, None]).float()
            pos = pos.clamp(min=0)
            with torch.no_grad():
                vec, _ = m.pool_history(V, tp[pos], tt[pos], hm)
            vecs[a:a + 8192] = vec.cpu().numpy()
        np.savez(out / "user_vectors.npz", user_ids=d.user_ids[users_with].astype(str), vectors=vecs)
    # parity + latency with the numpy scorer
    sc = load_scorer(out)
    cat = D.con().execute("SELECT product_id, category, subcategory, brand, price_eur, description FROM catalog "
                          "ORDER BY product_id").fetchall()
    rows = [dict(product_id=r[0], category=r[1], subcategory=r[2], brand=r[3], price=r[4], description=r[5])
            for r in cat]
    pm = sc.embed_products(rows)
    vp = np.abs(pm.vecs - V.cpu().numpy()).max()
    s = d.s
    rng = np.random.default_rng(0)
    idx = rng.choice(np.flatnonzero(s["day"] > D.TRAIN_LAST_DAY), 300, replace=False)
    inv = {v: k for k, v in d.vocab["device"].items()}
    invr = {v: k for k, v in d.vocab["region"].items()}
    invp = {v: k for k, v in d.vocab["page"].items()}
    reqs = []
    for i in idx:
        rv = [str(d.product_ids[p]) for p in s["rv"][i] if p >= 0]
        reqs.append(dict(user_id=str(d.user_ids[s["user"][i]]), is_new_user=False, device=inv[int(s["device"][i])],
                         region=invr[int(s["region"][i])], page=invp[int(s["page"][i])], recent_views=rv,
                         ts_ms=int(s["ts"][i])))
    # torch reference with the same inputs (user vectors from the export)
    max_abs = 0.0
    lat = []
    with torch.no_grad():
        for rq, i in zip(reqs, idx):
            t0 = time.perf_counter()
            ns = sc.score(rq, pm)
            lat.append((time.perf_counter() - t0) * 1000)
            j = sc.user_index.get(rq["user_id"])
            hist = torch.as_tensor(sc.user_vecs[j] if j is not None else np.zeros(m.d, np.float32),
                                   device=tr.dev)[None]
            hh = torch.tensor([[1.0 if (j is not None and N > 0) else 0.0]], device=tr.dev)
            ii = torch.as_tensor([i], device=tr.dev)
            ctx = m.context(tr.S["device"][ii], tr.S["region"][ii], tr.S["page"][ii], tr.S["hour"][ii])
            rec, rh = m.pool_recent(V, tr.S["rv"][ii], ctx)
            u = m.users(ctx, rec, rh, hist, hh, torch.zeros(1, device=tr.dev))
            ts_ = m.score_from_x(u @ V.T + b)[0].cpu().numpy()
            max_abs = max(max_abs, float(np.abs(ts_ - ns).max()))
    lat = np.array(lat)
    return {"parity_max_abs": max_abs, "product_parity_max_abs": float(vp),
            "latency_p50_ms": float(np.percentile(lat, 50)), "latency_p99_ms": float(np.percentile(lat, 99))}


@hydra.main(version_base=None, config_path="../conf", config_name="train")
def main(cfg: DictConfig) -> None:
    cfg = apply_preset(cfg)
    log("config:\n" + OmegaConf.to_yaml(cfg))
    t_start = time.time()
    tr = Trainer(cfg)
    ev = Evaluator(tr.data, tr.dev, tr.log_theta, max_organic=int(cfg.eval.max_organic))
    tr.fit(ev)
    tr.x_scale = 1.0
    if int(cfg.train.calibrate_epochs) > 0:
        calibrate(tr, int(cfg.train.calibrate_epochs))
    m = tr.model
    m.eval()
    with torch.no_grad():
        V, b = tr.product_matrix(train=False)
        r = ev.run(m, V, b, B=int(cfg.eval.bootstrap), full=True)
    out = run_dir() / "export"
    serve = export_package(tr, out, cfg)
    torch.save(m.state_dict(), out / "model.pt")
    lt = tr.log_theta
    slot_gap = float(np.abs(m.slot.detach().cpu().numpy() - lt)[:, 1:].max())
    summary = {
        "objective": r["objective"], "objective_se": r["objective_se"], "lift_all": r["lift_all"],
        "lift_cold": r["lift_cold"],
        "slate_auc": r["metrics"]["slate_auc"]["all"]["value"],
        "slate_auc_lift": r["metrics"]["slate_auc"]["all"]["lift"],
        "organic_recall": r["metrics"]["organic_recall@10"]["all"]["value"],
        "organic_recall_lift": r["metrics"]["organic_recall@10"]["all"]["lift"],
        "organic_recall_cold": r["metrics"]["organic_recall@10"]["cold"]["value"],
        "calibration_max_err": r.get("calibration_max_err"), "slot_max_gap": slot_gap,
        **serve, "minutes": (time.time() - t_start) / 60,
        "alpha": float(m.alpha.item()), "x_scale": tr.x_scale, "no_id": float(m.no_id.item()), "c_click": float(m.c_click.item()), "c_purchase": float(m.c_purchase.item()),
    }
    if not tr.all_data:
        # interval bounds for the eligibility rule
        for metric, key in (("slate_auc", "slate_auc"), ("organic_recall@10", "organic_recall")):
            a = r["metrics"][metric]["all"]
            summary[f"{key}_lift_lo"], summary[f"{key}_lift_hi"] = a["lift_lo"], a["lift_hi"]
    recs = []
    for metric, by in r["metrics"].items():
        for sl, v in by.items():
            recs.append(dict(dataset="history", slice=sl, metric=metric, value=v["value"], baseline=v["baseline"],
                             lift=v["lift"], lift_lo=v["lift_lo"], lift_hi=v["lift_hi"], n=v["n"]))
    ivan.log_records("metrics", recs)
    ivan.log_records("calibration", r.get("calibration", []))
    ivan.log_records("slot", r.get("slot", []))
    sh_top, sh_clk = r["share_top10_heldout"], r.get("share_clicks_heldout")
    ivan.log_records("products", [dict(group="held-out", share_top10=sh_top, share_clicks=sh_clk),
                                  dict(group="known", share_top10=1 - sh_top,
                                       share_clicks=None if sh_clk is None else 1 - sh_clk)])
    cold_lift = r["lift_cold"]
    cal = summary["calibration_max_err"]
    checks = [
        dict(check="lift_cold > 0 (history fold)", value=f"{cold_lift:+.3f}", needed="> 0", passed=bool(cold_lift > 0)),
        dict(check="held-out share of top-10 <= 2x share of clicks", value=f"{sh_top:.4f} vs {sh_clk or 0:.4f}",
             needed="<= 2x", passed=bool(sh_clk is not None and sh_top <= 2 * sh_clk)),
        dict(check="calibration within 20 % per decile", value=f"{cal:.3f}" if cal is not None else "n/a",
             needed="<= 0.20", passed=bool(cal is not None and cal <= 0.2)),
        dict(check="numpy = torch", value=f"{serve['parity_max_abs']:.2e}", needed="< 1e-4",
             passed=bool(serve["parity_max_abs"] < 1e-4)),
        dict(check="p99 latency, batch 1", value=f"{serve['latency_p99_ms']:.2f} ms", needed="< 20 ms",
             passed=bool(serve["latency_p99_ms"] < 20)),
    ]
    ivan.log_records("checks", checks)
    ivan.log_summary(summary)
    (out / "metrics.json").write_text(json.dumps({"summary": summary, "metrics": recs, "checks": checks}, indent=1))
    (out / "config.yaml").write_text(OmegaConf.to_yaml(cfg))
    exp = os.environ.get("IVAN_EXPERIMENT", "local")
    (out / "README.txt").write_text(
        f"Two-tower embedding model, serving package.\nexperiment: {exp}\nrun dir: {run_dir()}\n"
        f"git commit: {git_commit()}\ntrained: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"fold: {cfg.data.fold} (all data: {cfg.data.all}); preset: {cfg.preset}\n\n"
        + "\n".join(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}" for k, v in summary.items())
        + "\n\nUse: from training.export.scorer import load; model = load(<this folder>)\n")
    log("summary: " + json.dumps(summary))


if __name__ == "__main__":
    main()

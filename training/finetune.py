"""Fine-tune a history model on the live practice stream: python -m training.finetune base=<experiment> [overrides].

`base` names a history run (`ivan run ... --name <base>`; its export is read from the share). The run evaluates on
the live hold-out (organic_recall@10 lift over live best sellers, objective (50 all + 10 cold) / 60) and checks
forgetting on the history validation week (ips_hit@10). `ft.epochs=0` is the reference: the base without tuning.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import hydra
import numpy as np
import torch
from omegaconf import DictConfig, OmegaConf
from torch.nn import functional as Fn

import ivan
from training.embed import live as L
from training.embed.metrics import boot_lift
from training.embed.presets import apply_preset
from training.export import features as F
from training.train import Trainer, git_commit, log, run_dir

SHARE_NAMES = Path("/mnt/epoch/projects/rawtree/experiments/names")


def base_dir(name: str) -> Path:
    if os.path.isdir(name):
        return Path(name)
    rd = ivan.runs.dir()
    roots = [Path(rd).parent.parent / "names"] if rd is not None else []
    roots.append(SHARE_NAMES)
    for root in roots:
        for cand in (root / name / "1" / "export", root / name / "export"):
            if (cand / "model.pt").exists():
                return cand
    if "/" in name:
        exp, k = name.split("/", 1)
        for root in roots:
            cand = root / exp / k / "export"
            if (cand / "model.pt").exists():
                return cand
    raise FileNotFoundError(f"no export with model.pt for base {name!r} under {roots}")


def live_folder(cfg) -> Path:
    if os.environ.get("RAWTREE_LIVE"):
        return Path(os.environ["RAWTREE_LIVE"])
    if os.environ.get("IVAN_JOB_ID"):
        import ivan.data
        return Path(ivan.data.path("rawtree_live", cfg.live.version))
    return Path(__file__).resolve().parents[1] / "data" / "raw" / "rawtree_live"


class FineTuner:
    def __init__(self, cfg: DictConfig):
        bdir = base_dir(str(cfg.base))
        log(f"base export: {bdir}")
        bcfg = OmegaConf.load(bdir / "config.yaml")
        # history side: the base's own config (fold, model shape); our run's seed
        OmegaConf.set_struct(bcfg, False)
        bcfg.train.seed = cfg.train.seed
        bcfg.data.all = bool(cfg.ft.all_history) or bool(bcfg.data.all)
        self.bcfg = bcfg
        self.cfg = cfg
        self.tr = tr = Trainer(bcfg)
        self.dev = tr.dev
        m = tr.model
        sd = torch.load(bdir / "model.pt", map_location=tr.dev)
        if "disc_beta" in sd:
            m.disc_beta = torch.nn.Parameter(torch.tensor(0.0, device=tr.dev))
        if "new_gain" in sd:
            m.new_gain = torch.nn.Parameter(torch.tensor(0.0, device=tr.dev),
                                            requires_grad=bool(cfg.ft.get("new_gain", False)))
        if sd["e_id.weight"].shape[0] == m.e_id.weight.shape[0]:
            missing = m.load_state_dict(sd, strict=False)
            log(f"base weights loaded; missing {missing.missing_keys}")
            sd = None
        self.live = lv = L.build(tr.data, live_folder(cfg), holdout=bool(cfg.ft.holdout))
        P0, P = lv.n_hist_products, len(lv.product_ids)
        # extend the ID tables to the new products
        with torch.no_grad():
            e_id = torch.nn.Embedding(P, m.d).to(self.dev)
            b_id = torch.nn.Embedding(P, 1).to(self.dev)
            torch.nn.init.normal_(e_id.weight, std=0.01)
            torch.nn.init.zeros_(b_id.weight)
            e_id.weight[:P0] = m.e_id.weight
            b_id.weight[:P0] = m.b_id.weight
        m.e_id, m.b_id = e_id, b_id
        if not hasattr(m, "disc_beta"):
            m.disc_beta = torch.nn.Parameter(torch.tensor(0.0, device=self.dev))  # live-only discount weight
        if not hasattr(m, "new_gain"):
            # x = u.v + (1 + new_gain * is_new) * b: new users lean more on popularity (cold-analysis proposal 3)
            m.new_gain = torch.nn.Parameter(torch.tensor(0.0, device=self.dev),
                                            requires_grad=bool(cfg.ft.get("new_gain", False)))
        if sd is not None:  # the base is itself a fine-tuned model: its ID tables already cover the live products
            assert sd["e_id.weight"].shape[0] == P, (sd["e_id.weight"].shape, P)
            missing = m.load_state_dict(sd, strict=False)
            log(f"fine-tuned base weights loaded; missing {missing.missing_keys}")
        t = tr.t
        self.P0, self.P = P0, P
        self.prod = {k: t(v) for k, v in lv.prod.items()}
        self.has_id = t((~lv.heldout_products).astype(np.float32))
        self.held_p = t(lv.heldout_products)
        e = lv.e
        self.E = {k: t(v) for k, v in e.items() if k != "ts"}
        self.h_prod, self.h_type = t(lv.h["prod"]), t(lv.h["type"])
        self.a_prod, self.a_type = t(lv.a["prod"]), t(lv.a["type"])
        self.a_bounds = np.searchsorted(lv.a["user"], np.arange(len(lv.user_ids) + 1))
        self.use_cart = bool(cfg.ft.get("cart", False))
        if not hasattr(m, "cart_w"):
            # open cart (carted, not bought since): pooled into the user vector through a zero-start adapter, and a
            # learned score term for a candidate that is in the cart (cold analysis: odds ratio 5-6 for a purchase)
            m.cart_w = torch.nn.Linear(m.d + 1, m.d, bias=False).to(self.dev)
            torch.nn.init.zeros_(m.cart_w.weight)
            m.cart_beta = torch.nn.Parameter(torch.tensor(0.0, device=self.dev))
        for p_ in (m.cart_w.weight, m.cart_beta):
            p_.requires_grad_(self.use_cart)
        self.page_org = tr.data.vocab["page"][F.ORGANIC_PAGE]
        train = (e["ts"] < lv.t_holdout) & ~lv.heldout_users[e["user"]] & ~lv.heldout_products[e["prod"]]
        self.org_idx = np.flatnonzero(train)
        w = np.array(cfg.organic.type_weights, dtype=np.float64)[e["type"][self.org_idx]]
        if cfg.ft.half_life_h > 0:
            age_h = (lv.t_end - e["ts"][self.org_idx]) / L.HOUR_MS
            w = w * 0.5 ** (age_h / cfg.ft.half_life_h)
        self.org_p = w / w.sum()
        q = np.bincount(e["prod"][self.org_idx], weights=w, minlength=P)
        self.logq = t(np.log(np.maximum(q / q.sum(), 1e-9)).astype(np.float32))
        f = lv.f
        self.Fb = {k: t(v) for k, v in f.items() if k != "ts"}
        self.fb_idx = np.flatnonzero((f["ts"] < lv.t_holdout) & ~lv.heldout_users[f["user"]])
        # validation: held-out purchases (held-out users, or the last 2 hours)
        vi = np.flatnonzero((e["type"] == 2) & ((e["ts"] >= lv.t_holdout) | lv.heldout_users[e["user"]]))
        rng = np.random.default_rng(0)
        if len(vi) > 40000:
            vi = np.sort(rng.choice(vi, 40000, replace=False))
        self.vidx = vi
        nu = lv.new_user[e["user"][vi]]
        rvv = e["rv"][vi]
        npd = lv.new_product[e["prod"][vi]] | (lv.new_product[rvv.clip(0)] & (rvv >= 0)).any(1)
        self.slices = {"all": np.ones(len(vi), bool), "new_user": nu, "new_product": npd, "cold": nu | npd,
                       "warm": ~(nu | npd)}
        self.best = np.argsort(-lv.popularity)[:10]
        log(f"live: {len(self.org_idx)} training events, {len(self.fb_idx)} carousels, {len(vi)} validation purchases")

    def product_matrix(self, train):
        m, p = self.tr.model, self.prod
        mask = self.has_id
        if train:
            # practice-round products drop their ID vector more often (ft.new_id_dropout), so the content path and
            # the no-ID bias learn how the live simulator treats products without history
            drop = torch.full_like(mask, float(self.bcfg.model.id_dropout))
            drop[self.P0:] = float(self.cfg.ft.get("new_id_dropout", self.bcfg.model.id_dropout))
            mask = mask * (torch.rand_like(mask) >= drop).float()
        return m.products(p["cat"], p["sub"], p["brand"], p["price"], p["tokens"], mask)

    def bias(self, b, is_new):
        """Per-row product bias [rows, P]: b scaled by (1 + new_gain) for new users."""
        return b[None] * (1 + self.tr.model.new_gain * is_new[:, None])

    def open_cart(self, end, lo, exclude=None):
        """Products in the user's open cart before `end` (events [lo, end) of the all-events source): added to cart
        and not bought since, within the last ft.cart_window events, each product once. -> (products, mask) [B, W]."""
        W = int(self.cfg.ft.get("cart_window", 50))
        pos = end[:, None] - 1 - torch.arange(W, device=self.dev)[None]
        valid = pos >= lo[:, None]
        pp = self.a_prod[pos.clamp(min=0)]
        tt = self.a_type[pos.clamp(min=0)]
        cart, buy = valid & (tt == 1), valid & (tt == 2)
        newer = torch.ones(W, W, device=self.dev, dtype=torch.bool).tril(-1)  # [i, j]: column j is newer than i
        same = pp[:, :, None] == pp[:, None, :]
        bought = (same & buy[:, None, :] & newer[None]).any(-1)
        open_ = cart & ~bought
        open_ = open_ & ~(same & open_[:, None, :] & newer[None]).any(-1)  # keep the newest add of a product
        if exclude is not None:
            open_ = open_ & (pp != exclude[:, None])
        return pp, open_

    def in_cart(self, cart, cand):
        """cand [B, K] product indices -> [B, K] bool: candidate is in the row's open cart."""
        pp, open_ = cart
        return ((cand[:, :, None] == pp[:, None, :]) & open_[:, None, :]).any(-1)

    def cart_scores(self, cart, P):
        """[B, P] in-cart indicator for every product."""
        pp, open_ = cart
        out = torch.zeros(pp.shape[0], P, device=self.dev)
        # additive, capped at 1: a plain scatter_ lets a closed or duplicate entry (0) overwrite an open one (1)
        return out.scatter_add_(1, pp.clamp(min=0), open_.float()).clamp_(max=1.0)

    def add_cart(self, u, V, cart):
        if not self.use_cart:
            return u
        pp, open_ = cart
        w = open_.float()
        has = (w.sum(1, keepdim=True) > 0).float()
        vec = (V[pp] * w[..., None]).sum(1) / w.sum(1, keepdim=True).clamp(min=1)
        return u + self.tr.model.cart_w(torch.cat([vec * has, has], 1))

    def users(self, V, part, idx, page=None, train=True, no_hist=None, cart_exclude=None, with_cart=False):
        m = self.tr.model
        page_t = part["page"][idx] if page is None else torch.full_like(idx, page)
        ctx = m.context(part["device"][idx], part["region"][idx], page_t, part["hour"][idx])
        rec, rh = m.pool_recent(V, part["rv"][idx], ctx)
        N = m.hist_len
        if N > 0:
            pos = part["hist_end"][idx][:, None] - 1 - torch.arange(N, device=self.dev)[None]
            hm = (pos >= part["hist_lo"][idx][:, None]).float()
            if no_hist is not None:
                hm = hm * (~no_hist).float()[:, None]
            if train and self.bcfg.model.history_dropout > 0:
                hm = hm * (torch.rand(len(idx), device=self.dev) >= self.bcfg.model.history_dropout).float()[:, None]
            if train and self.cfg.ft.get("new_user_trunc", False):
                # new users: keep only their last k events, k in {0, 1, 2, 3, 5, 10, 20, all} (cold-analysis
                # proposal 2: early in a stream new users have almost no history)
                ks = torch.tensor([0, 1, 2, 3, 5, 10, 20, N], device=self.dev)
                k = ks[torch.randint(len(ks), (len(idx),), device=self.dev)]
                k = torch.where(part["is_new"][idx] > 0, k, torch.full_like(k, N))
                hm = hm * (torch.arange(N, device=self.dev)[None] < k[:, None]).float()
            hist, hh = m.pool_history(V, self.h_prod[pos.clamp(min=0)], self.h_type[pos.clamp(min=0)], hm)
        else:
            hist, hh = torch.zeros_like(rec), torch.zeros_like(rh)
        u = m.users(ctx, rec, rh, hist, hh, part["is_new"][idx])
        cart = self.open_cart(part["cart_end"][idx], part["cart_lo"][idx], cart_exclude) if self.use_cart else None
        if cart is not None:
            u = self.add_cart(u, V, cart)
        return (u, cart) if with_cart else u

    def organic_loss(self, V, b, idx):
        m, E = self.tr.model, self.E
        tgt = E["prod"][idx]
        u = self.users(V, E, idx, page=self.page_org, cart_exclude=tgt)
        logits = u @ V[tgt].T + self.bias(b[tgt], E["is_new"][idx]) + m.disc_beta * E["disc"][idx][None] - self.logq[tgt][None]
        same = tgt[:, None] == tgt[None]
        eye = torch.eye(len(idx), device=self.dev, dtype=torch.bool)
        return Fn.cross_entropy(logits.masked_fill(same & ~eye, -1e9), torch.arange(len(idx), device=self.dev))

    def feedback_loss(self, V, b, idx):
        m, S = self.tr.model, self.Fb
        u, cart = self.users(V, S, idx, with_cart=True)
        shown = S["shown"][idx]
        valid = (shown >= 0) & ~self.held_p[shown.clamp(min=0)]
        x = (u[:, None] * V[shown.clamp(min=0)]).sum(-1) + b[shown.clamp(min=0)] * (
            1 + m.new_gain * S["is_new"][idx][:, None])
        if cart is not None:
            x = x + m.cart_beta * self.in_cart(cart, shown.clamp(min=0)).float()
        k = torch.arange(10, device=self.dev)[None].expand_as(shown)
        sl = m.slot[k, S["device"][idx][:, None].expand_as(shown)]
        click = (k == S["click_slot"][idx][:, None]) & valid
        lc = Fn.binary_cross_entropy_with_logits(x + m.c_click + sl, click.float(), weight=valid.float(),
                                                 reduction="sum") / valid.float().sum().clamp(min=1) * 100
        ck = click.any(1)
        lp = torch.zeros((), device=self.dev)
        if ck.any():
            cs = S["click_slot"][idx][ck]
            xc = x[ck].gather(1, cs[:, None])[:, 0]
            lp = Fn.binary_cross_entropy_with_logits(m.alpha * xc + m.c_purchase, S["purchased"][idx][ck].float(),
                                                     reduction="sum") / valid.float().sum().clamp(min=1) * 100
        return lc, lp

    def param_groups(self):
        m = self.tr.model
        what = self.cfg.ft.train
        P0 = self.P0
        if what == "new_parts":
            for p in m.parameters():
                p.requires_grad_(False)
            for p in (m.w_new, m.e_id.weight, m.b_id.weight, m.p_bias.weight, m.p_bias.bias, m.disc_beta, m.no_id, m.new_gain, m.cart_w.weight, m.cart_beta):
                p.requires_grad_(True)
        if what in ("new_parts", "freeze_hist_ids"):
            def hook(g):
                g = g.clone()
                g[:P0] = 0
                return g
            m.e_id.weight.register_hook(hook)
            m.b_id.weight.register_hook(hook)
        m.type_w.requires_grad_(False)
        if not isinstance(m.slot, torch.nn.Parameter):
            pass
        return [p for p in m.parameters() if p.requires_grad]

    def fit(self):
        cfg, tr, m = self.cfg, self.tr, self.tr.model
        epochs = int(cfg.ft.epochs)
        if epochs <= 0:
            return
        params = self.param_groups()
        lr = float(self.bcfg.train.lr) * float(cfg.ft.lr_mult)
        opt = torch.optim.AdamW(params, lr=lr, weight_decay=float(self.bcfg.train.weight_decay))
        bs = int(self.bcfg.train.batch_size)
        steps = max(1, len(self.org_idx) // bs)
        hist_share = float(cfg.ft.history_share)
        for ep in range(epochs):
            t0 = time.time()
            org = tr.rng.choice(self.org_idx, size=steps * bs, p=self.org_p)
            fbi = tr.rng.choice(self.fb_idx, size=steps * (bs // 4)) if len(self.fb_idx) else None
            hperm = tr.rng.choice(tr.train_idx, size=steps * bs)
            horg = tr.rng.choice(tr.org_idx, size=steps * bs, p=tr.org_p)
            sums = {"loss": 0.0, "loss_organic": 0.0, "loss_click": 0.0, "loss_purchase": 0.0}
            m.train()
            for i in range(steps):
                V, b = self.product_matrix(True)
                lo = self.organic_loss(V, b, tr.t(org[i * bs:(i + 1) * bs]))
                loss = lo
                if cfg.ft.feedback and fbi is not None:
                    q = bs // 4
                    lc, lp = self.feedback_loss(V, b, tr.t(fbi[i * q:(i + 1) * q]))
                    loss = loss + cfg.loss.click_weight * lc + lp
                    if i % 20 == 0:
                        sums["loss_click"] += lc.item()
                        sums["loss_purchase"] += lp.item()
                if hist_share > 0:
                    Vh, bh = tr.product_matrix(train=True)
                    hc, hp = tr.carousel_loss(Vh, bh, tr.t(hperm[i * bs:(i + 1) * bs]))
                    ho = tr.organic_loss(Vh, bh, tr.t(horg[i * bs:(i + 1) * bs]))
                    hl = self.bcfg.loss.click_weight * hc + hp + self.bcfg.organic.weight * ho
                    loss = (1 - hist_share) * loss + hist_share * hl
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(params, 5.0)
                opt.step()
                if isinstance(m.slot, torch.nn.Parameter):
                    with torch.no_grad():
                        m.slot[0].zero_()
                if i % 20 == 0:
                    sums["loss"] += loss.item()
                    sums["loss_organic"] += lo.item()
            nl = len(range(0, steps, 20))
            row = {k: v / nl for k, v in sums.items()}
            row.update(epoch=ep + 1, train_s=time.time() - t0)
            r = self.evaluate(B=200)
            row.update(val_objective=r["live_objective"], val_lift_all=r["live_lift_all"],
                       val_lift_cold=r["live_lift_cold"])
            log(" ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()))
            ivan.log_step(row, step=ep + 1)

    @torch.no_grad()
    def evaluate(self, B=1000):
        m = self.tr.model
        m.eval()
        V, b = self.product_matrix(False)
        E = self.E
        n = len(self.vidx)
        if n == 0:  # no live hold-out (final model)
            m.train()
            nan = float("nan")
            return {"live": {}, "live_objective": nan, "live_objective_se": nan, "live_lift_all": nan,
                    "live_lift_cold": nan, "live_share_top10_heldout_new": nan}
        hit = np.zeros(n, np.float32)
        top_new = 0.0
        for a in range(0, n, 4096):
            idx = self.tr.t(self.vidx[a:a + 4096])
            held = self.tr.t(self.live.heldout_users)[E["user"][idx]]
            u, cart = self.users(V, E, idx, page=self.page_org, train=False, no_hist=held,
                                 cart_exclude=E["prod"][idx], with_cart=True)
            x = u @ V.T + self.bias(b, E["is_new"][idx])
            if cart is not None:
                x = x + m.cart_beta * self.cart_scores(cart, V.shape[0])
            top = m.score_from_x(x).topk(10, dim=1).indices
            top_new += self.held_p[top].float().sum().item()
            hit[a:a + 4096] = (top == E["prod"][idx][:, None]).any(1).float().cpu().numpy()
        base = np.isin(self.live.e["prod"][self.vidx], self.best).astype(np.float32)
        res, draws = boot_lift(hit, base, {k: v.astype(np.float32) for k, v in self.slices.items()}, B)
        obj = (50 * res["all"]["lift"] + 10 * res["cold"]["lift"]) / 60
        od = (50 * draws["all"] + 10 * draws["cold"]) / 60
        m.train()
        return {"live": res, "live_objective": float(obj), "live_objective_se": float(np.nanstd(od)),
                "live_lift_all": res["all"]["lift"], "live_lift_cold": res["cold"]["lift"],
                "live_share_top10_heldout_new": top_new / max(n * 10, 1),
                "live_share_purchases_heldout_new": float(self.live.heldout_products[self.live.e["prod"][self.vidx]].mean())}

    @torch.no_grad()
    def evaluate_feedback(self, B=1000):
        """Live carousel hold-out: our own carousels (feedback) of held-out users or from the last 2 hours, with a
        click. Rank the whole catalogue as at serving (full context, open cart included); a click counts if the
        clicked product is in our top 10 (a purchase counts 3x), against live best sellers. Also the share of these
        clicks that went to an open-cart product, and the lift on that subset."""
        lv, m, S = self.live, self.tr.model, self.Fb
        f = lv.f
        held = (f["ts"] >= lv.t_holdout) | lv.heldout_users[f["user"]]
        vi = np.flatnonzero(held & (f["click_slot"] >= 0))
        if not len(vi):
            return {}
        m.eval()
        V, b = self.product_matrix(False)
        hit = np.zeros(len(vi), np.float32)
        incart = np.zeros(len(vi), bool)
        cprod = f["shown"][vi, f["click_slot"][vi]]
        w = np.where(f["purchased"][vi], 3.0, 1.0).astype(np.float32)
        for a in range(0, len(vi), 2048):
            idx = self.tr.t(vi[a:a + 2048])
            # history as at serving: no hour cut; held-out users keep their own past (inputs, not labels)
            u, cart = self.users(V, S, idx, train=False, with_cart=True)
            if cart is None:
                cart = self.open_cart(S["cart_end"][idx], S["cart_lo"][idx])
            else:
                x_c = m.cart_beta * self.cart_scores(cart, V.shape[0])
            x = u @ V.T + self.bias(b, S["is_new"][idx])
            if self.use_cart:
                x = x + x_c
            top = m.score_from_x(x).topk(10, dim=1).indices
            cp = self.tr.t(cprod[a:a + 2048])
            hit[a:a + 2048] = (top == cp[:, None]).any(1).float().cpu().numpy()
            incart[a:a + 2048] = self.in_cart(cart, cp[:, None])[:, 0].cpu().numpy()
        base = np.isin(cprod, self.best).astype(np.float32)
        nu = f["is_new"][vi] > 0
        masks = {"all": np.ones(len(vi), np.float32), "new_user": nu.astype(np.float32),
                 "known": (~nu).astype(np.float32), "in_cart": incart.astype(np.float32)}
        res, _ = boot_lift(hit * w, base * w, masks, B)
        m.train()
        out = {"fb": res, "fb_lift_all": res["all"]["lift"], "fb_lift_new_user": res["new_user"]["lift"],
               "fb_hit_all": float((hit * w).sum() / w.sum()), "fb_clicks": int(len(vi)),
               "fb_share_clicks_in_cart": float(incart.mean())}
        out.update(self.purchase_auc(V, b))
        if incart.any():
            out["fb_hit_in_cart"] = float(hit[incart].mean())
        return out

    @torch.no_grad()
    def purchase_auc(self, V, b, B=500):
        """The server's offline measure: on held-out carousels with a purchase (held-out users or the last 2 hours),
        the AUC of the purchased product against the other shown products, by model score (0.5 = random). Also
        for new and known shoppers, and the mean rank of the bought product among the 10 (1 = top)."""
        lv, m, S = self.live, self.tr.model, self.Fb
        f = lv.f
        held = (f["ts"] >= lv.t_holdout) | lv.heldout_users[f["user"]]
        vi = np.flatnonzero(held & f["purchased"] & (f["click_slot"] >= 0))
        if not len(vi):
            return {}
        m.eval()
        auc = np.zeros(len(vi), np.float32)
        rank = np.zeros(len(vi), np.float32)
        for a in range(0, len(vi), 2048):
            idx = self.tr.t(vi[a:a + 2048])
            u = self.users(V, S, idx, train=False)
            shown = S["shown"][idx]
            valid = shown >= 0
            x = (u[:, None] * V[shown.clamp(min=0)]).sum(-1) + b[shown.clamp(min=0)] * (
                1 + m.new_gain * S["is_new"][idx][:, None])
            sc = m.score_from_x(x)
            cs = S["click_slot"][idx]
            c = sc.gather(1, cs[:, None])
            others = valid & (torch.arange(10, device=self.dev)[None] != cs[:, None])
            gt = ((c > sc).float() + 0.5 * (c == sc).float()) * others
            auc[a:a + 2048] = (gt.sum(1) / others.sum(1).clamp(min=1)).cpu().numpy()
            rank[a:a + 2048] = (1 + ((sc > c) & others).float().sum(1)).cpu().numpy()
        nu = f["is_new"][vi] > 0
        rng = np.random.default_rng(0)
        boot = np.array([auc[rng.integers(0, len(auc), len(auc))].mean() for _ in range(B)])
        m.train()
        out = {"pauc_all": float(auc.mean()), "pauc_se": float(boot.std()), "pauc_n": int(len(vi)),
               "pauc_rank": float(rank.mean())}
        if nu.any():
            out["pauc_new_user"] = float(auc[nu].mean())
        if (~nu).any():
            out["pauc_known"] = float(auc[~nu].mean())
        return out

    @torch.no_grad()
    def history_modes(self, lengths=(1, 3, 5, 10, 20, 50, 100), B=300):
        """Held-out live purchases scored with three kinds of long-term history, at several lengths:
        none (a brand-new user); snapshot (history + live events up to the start of the hold-out window, as a
        user_vectors.npz exported then); dynamic (every event of the user before the purchase, as Bas passing
        `events=`). Events on the purchased product itself are left out (as in the recent context)."""
        lv, m, dev = self.live, self.tr.model, self.dev
        if not len(self.vidx) or lv.t_holdout > lv.t_end:
            return []
        hh, e = self.tr.data.h, lv.e
        user = np.concatenate([hh["user"], e["user"]])
        ts = np.concatenate([hh["ts"], e["ts"]])
        prod = np.concatenate([hh["prod"], e["prod"]])
        typ = np.concatenate([hh["type"], e["type"]])
        o = np.lexsort((ts, user))
        user, ts, prod, typ = user[o], ts[o], prod[o], typ[o]
        from training.embed.data import KEY
        key = user * KEY + ts
        vu, vt, vp = e["user"][self.vidx], e["ts"][self.vidx], e["prod"][self.vidx]
        lo = np.searchsorted(key, vu * KEY)
        ends = {"snapshot": np.searchsorted(key, vu * KEY + np.minimum(vt, lv.t_holdout)),
                "dynamic": np.searchsorted(key, vu * KEY + vt)}
        tp, tt = torch.as_tensor(prod, device=dev), torch.as_tensor(typ, device=dev)
        m.eval()
        V, b = self.product_matrix(False)
        E = self.E
        base = np.isin(vp, self.best).astype(np.float32)
        masks = {k: v.astype(np.float32) for k, v in self.slices.items()}
        n_hist = {}
        rows = []
        for mode, L in [("none", 0)] + [(md, L) for md in ("snapshot", "dynamic") for L in lengths
                                        if md == "dynamic" or L >= 10]:
            hit = np.zeros(len(self.vidx), np.float32)
            nh = np.zeros(len(self.vidx), np.float32)
            for a in range(0, len(self.vidx), 4096):
                sl = slice(a, a + 4096)
                idx = self.tr.t(self.vidx[sl])
                ctx = m.context(E["device"][idx], E["region"][idx], torch.full_like(idx, self.page_org), E["hour"][idx])
                rec, rh = m.pool_recent(V, E["rv"][idx], ctx)
                if L == 0:
                    hist, hh_ = torch.zeros_like(rec), torch.zeros_like(rh)
                else:
                    end = torch.as_tensor(ends[mode][sl], device=dev)
                    lo_t = torch.as_tensor(lo[sl], device=dev)
                    # walk back up to 2L positions, keep at most L events that are not the purchased product
                    pos = end[:, None] - 1 - torch.arange(2 * L, device=dev)[None]
                    ok = (pos >= lo_t[:, None]) & (tp[pos.clamp(min=0)] != E["prod"][idx][:, None])
                    ok = ok & (ok.long().cumsum(1) <= L)
                    hist, hh_ = m.pool_history(V, tp[pos.clamp(min=0)], tt[pos.clamp(min=0)], ok.float())
                    nh[sl] = ok.float().sum(1).cpu().numpy()
                u = m.users(ctx, rec, rh, hist, hh_, E["is_new"][idx])
                top = m.score_from_x(u @ V.T + self.bias(b, E["is_new"][idx])).topk(10, dim=1).indices
                hit[sl] = (top == E["prod"][idx][:, None]).any(1).float().cpu().numpy()
            res, _ = boot_lift(hit, base, masks, B)
            for s, v in res.items():
                rows.append(dict(mode=mode, length=L, slice=s, value=v["value"], baseline=v["baseline"],
                                 lift=v["lift"], lift_lo=v["lift_lo"], lift_hi=v["lift_hi"], n=v["n"],
                                 mean_events=float(nh[self.slices[s]].mean()) if L else 0.0))
        m.train()
        return rows

    @torch.no_grad()
    def history_check(self):
        from training.embed.metrics import Evaluator
        tr = self.tr
        ev = Evaluator(tr.data, tr.dev, tr.log_theta, max_organic=20000)
        V, b = tr.product_matrix(train=False)
        tr.model.eval()
        return ev.run(tr.model, V, b, B=1000, full=True)

    def export(self, out: Path):
        from training.export.scorer import load as load_scorer
        out.mkdir(parents=True, exist_ok=True)
        m, lv, tr = self.tr.model, self.live, self.tr
        m.eval()
        w = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in m.state_dict().items()}
        w.pop("disc_beta", None)
        if not self.use_cart:
            w.pop("cart_w.weight", None)
            w.pop("cart_beta", None)
        w["type_w"] = m.type_w.detach().cpu().numpy()
        d = tr.data
        meta = {"vocab": d.vocab, "sub_mean": d.sub_mean, "global_mean": d.global_mean, "use_desc": m.use_desc,
                "use_price": m.use_price, "pooling": m.pooling, "recency": float(m.recency), "dim": m.d,
                "history_len": m.hist_len, "min_history_events": int(self.cfg.ft.get("min_history_events", 0)),
                "cart_window": int(self.cfg.ft.get("cart_window", 50))}
        np.savez(out / "model.npz", **w, meta__json=np.array(json.dumps(meta)),
                 meta__id_products=lv.product_ids.astype(str), meta__id_has=self.has_id.cpu().numpy())
        with torch.no_grad():
            V, _ = self.product_matrix(False)
        N = m.hist_len
        if N > 0:
            hu = lv.h["user"]
            ends = np.searchsorted(hu, np.arange(len(lv.user_ids) + 1))
            lo, hi = ends[:-1], ends[1:]
            uw = np.flatnonzero(hi > lo)
            vecs = np.zeros((len(uw), m.d), np.float32)
            for a in range(0, len(uw), 8192):
                uu = uw[a:a + 8192]
                pos = torch.as_tensor(hi[uu], device=self.dev)[:, None] - 1 - torch.arange(N, device=self.dev)[None]
                hm = (pos >= torch.as_tensor(lo[uu], device=self.dev)[:, None]).float()
                vec, _ = m.pool_history(V, self.h_prod[pos.clamp(min=0)], self.h_type[pos.clamp(min=0)], hm)
                vecs[a:a + 8192] = vec.cpu().numpy()
            extra = {"counts": (hi - lo)[uw].astype(np.int32)}
            if self.use_cart:  # each user's open cart at export time, from every event of the user
                ab = self.a_bounds
                ids, off = [], [0]
                for a in range(0, len(uw), 8192):
                    uu = uw[a:a + 8192]
                    pp, op = self.open_cart(torch.as_tensor(ab[uu + 1], device=self.dev),
                                            torch.as_tensor(ab[uu], device=self.dev))
                    pp, op = pp.cpu().numpy(), op.cpu().numpy()
                    for r in range(len(uu)):
                        ids += [str(lv.product_ids[q]) for q in pp[r][op[r]]]
                        off.append(len(ids))
                extra.update(cart_ids=np.array(ids, dtype=str), cart_off=np.array(off, dtype=np.int64))
            np.savez(out / "user_vectors.npz", user_ids=lv.user_ids[uw].astype(str), vectors=vecs, **extra)
        return self.parity(out, V)

    @torch.no_grad()
    def parity(self, out: Path, V):
        """Numpy scorer vs PyTorch on the exported package: product vectors from the raw catalogue rows (history
        catalogue + new_product rows), and scores of 300 live requests; plus latency at batch size 1."""
        import duckdb
        from training.data.paths import con
        from training.export.scorer import load as load_scorer
        m, lv = self.tr.model, self.live
        sc = load_scorer(out)
        cols = "product_id, category, subcategory, brand, price_eur, description"
        rows = con().execute(f"SELECT {cols} FROM catalog ORDER BY product_id").fetchall()
        f = live_folder(self.cfg).as_posix()
        rows += duckdb.connect().execute(
            f"SELECT product_id, any_value(category), any_value(subcategory), any_value(brand), any_value(price_eur), "
            f"any_value(description) FROM read_parquet('{f}/catalog_updates.parquet') WHERE change = 'new_product' "
            f"GROUP BY product_id ORDER BY product_id").fetchall()
        known = set()
        rows = [r for r in rows if not (r[0] in known or known.add(r[0]))]
        pm = sc.embed_products([dict(product_id=r[0], category=r[1], subcategory=r[2], brand=r[3], price=r[4],
                                     description=r[5]) for r in rows])
        order = np.array([pm.index[str(pid)] for pid in lv.product_ids])
        V_np, b_np = pm.vecs[order], pm.bias[order]
        _, b = self.product_matrix(False)
        prod_gap = float(max(np.abs(V_np - V.cpu().numpy()).max(), np.abs(b_np - b.cpu().numpy()).max()))
        # requests: live events, with their recent context; history from the exported user vectors
        e, E = lv.e, self.E
        rng = np.random.default_rng(0)
        idx = rng.choice(len(e["ts"]), 300, replace=False)
        inv = {k: {v: kk for kk, v in self.tr.data.vocab[k].items()} for k in ("device", "region")}
        gap, lat = 0.0, []
        for i in idx:
            rq = dict(user_id=str(lv.user_ids[e["user"][i]]), is_new_user=bool(e["is_new"][i]),
                      device=inv["device"].get(int(e["device"][i])), region=inv["region"].get(int(e["region"][i])),
                      page="__organic__", ts_ms=int(e["ts"][i]),
                      recent_views=[str(lv.product_ids[p]) for p in e["rv"][i] if p >= 0])
            t0 = time.perf_counter()
            ns = sc.score(rq, pm)
            lat.append((time.perf_counter() - t0) * 1000)
            j = sc.user_index.get(rq["user_id"])
            ii = self.tr.t(np.array([i]))
            ctx = m.context(E["device"][ii], E["region"][ii], torch.full_like(ii, self.page_org), E["hour"][ii])
            # a request lists its recent views without gaps: compact the context the same way for torch
            rv = [p for p in e["rv"][i] if p >= 0]
            rv_t = torch.as_tensor([[-1] * (len(e["rv"][i]) - len(rv)) + rv], device=self.dev)
            rec, rh = m.pool_recent(V, rv_t, ctx)
            has = j is not None and m.hist_len > 0 and (sc.user_counts is None or sc.user_counts[j] >= sc.min_hist)
            hist = torch.as_tensor(sc.user_vecs[j] if has else np.zeros(m.d, np.float32), device=self.dev)[None]
            u = m.users(ctx, rec, rh, hist, torch.tensor([[1.0 if has else 0.0]], device=self.dev), E["is_new"][ii])
            x = u @ V.T + self.bias(b, E["is_new"][ii])
            if self.use_cart and j is not None:
                uix = int(e["user"][i])
                cart = self.open_cart(torch.as_tensor([self.a_bounds[uix + 1]], device=self.dev),
                                      torch.as_tensor([self.a_bounds[uix]], device=self.dev))
                u = self.add_cart(u, V, cart)
                x = u @ V.T + self.bias(b, E["is_new"][ii]) + m.cart_beta * self.cart_scores(cart, V.shape[0])
            ts_ = m.score_from_x(x)[0].cpu().numpy()[order.argsort()]
            gap = max(gap, float(np.abs(ts_ - ns).max()))
        lat = np.array(lat)
        return {"parity_max_abs": gap, "product_parity_max_abs": prod_gap,
                "latency_p50_ms": float(np.percentile(lat, 50)), "latency_p99_ms": float(np.percentile(lat, 99))}


@hydra.main(version_base=None, config_path="../conf", config_name="finetune")
def main(cfg: DictConfig) -> None:
    cfg = apply_preset(cfg)
    log("config:\n" + OmegaConf.to_yaml(cfg))
    t0 = time.time()
    ft = FineTuner(cfg)
    ref = ft.evaluate(B=200) if int(cfg.ft.epochs) > 0 else None
    ft.fit()
    r = ft.evaluate(B=1000)
    fb = ft.evaluate_feedback()
    if fb:
        ivan.log_records("feedback_holdout", [dict(slice=k, **v) for k, v in fb.pop("fb").items()])
    hm = ft.history_modes() if cfg.ft.get("history_modes", True) else []
    if hm:
        ivan.log_records("history_modes", hm)
    hc = ft.history_check() if not ft.bcfg.data.all else None
    # recalibrate the delivered score after tuning: fit on half of the history validation week (check on the other
    # half), or use fixed values (ft.score_affine) when the base saw all history
    from training.train import recalibrate
    fixed = cfg.ft.get("score_affine")
    rc = OmegaConf.create({"train": {"score_affine": list(fixed) if fixed else None}})
    if hc is not None:
        recal = recalibrate(ft.tr.model, hc, rc)
    elif fixed:
        with torch.no_grad():
            ft.tr.model.score_a.fill_(float(fixed[0]))
            ft.tr.model.score_c.fill_(float(fixed[1]))
        recal = {"score_a": float(fixed[0]), "score_c": float(fixed[1])}
    else:
        recal = {}
    out = run_dir() / "export"
    serve = ft.export(out)
    torch.save(ft.tr.model.state_dict(), out / "model.pt")
    hm_summary = {f"hm_{h['mode']}_{h['length']}_{h['slice']}": h["lift"] for h in hm
                  if h["slice"] in ("all", "cold", "new_user")}
    summary = {**recal, **serve, **hm_summary, **fb, "cart_beta": float(ft.tr.model.cart_beta.item()), "live_share_purchases_heldout_new": r.get("live_share_purchases_heldout_new"),
               "calibration_max_err": hc.get("calibration_max_err") if hc else None,
               "live_objective": r["live_objective"], "live_objective_se": r["live_objective_se"],
               "live_lift_all": r["live_lift_all"], "live_lift_cold": r["live_lift_cold"],
               "live_share_top10_heldout_new": r["live_share_top10_heldout_new"],
               "disc_beta": float(ft.tr.model.disc_beta.item()), "new_gain": float(ft.tr.model.new_gain.item()), "minutes": (time.time() - t0) / 60}
    if ref is not None:
        summary["live_objective_before"] = ref["live_objective"]
    if hc is not None:
        summary.update(objective=hc["objective"], objective_se=hc["objective_se"], lift_all=hc["lift_all"],
                       lift_cold=hc["lift_cold"], organic_recall=hc["metrics"]["organic_recall@10"]["all"]["value"],
                       slate_auc=hc["metrics"]["slate_auc"]["all"]["value"])
    recs = [dict(dataset="live", slice=sl, metric="organic_recall@10", value=v["value"], baseline=v["baseline"],
                 lift=v["lift"], lift_lo=v["lift_lo"], lift_hi=v["lift_hi"], n=v["n"]) for sl, v in r["live"].items()]
    if hc is not None:
        for metric, by in hc["metrics"].items():
            for sl, v in by.items():
                recs.append(dict(dataset="history", slice=sl, metric=metric, value=v["value"], baseline=v["baseline"],
                                 lift=v["lift"], lift_lo=v["lift_lo"], lift_hi=v["lift_hi"], n=v["n"]))
    ivan.log_records("metrics", recs)
    checks = []
    if r.get("live"):
        st, sp = r["live_share_top10_heldout_new"], r["live_share_purchases_heldout_new"]
        checks.append(dict(check="live: held-out new products' top-10 share within 0.5x-2x of their purchase share",
                           value=f"{st:.4f} vs {sp:.4f}", needed="0.5x-2x", passed=bool(0.5 * sp <= st <= 2 * sp)))
        checks.append(dict(check="live: lift_cold > 0", value=f"{r['live_lift_cold']:+.3f}", needed="> 0",
                           passed=bool(r["live_lift_cold"] > 0)))
        if ref is not None:
            checks.append(dict(check="live: beats the model without fine-tuning",
                               value=f"{r['live_objective']:.3f} vs {ref['live_objective']:.3f}", needed=">",
                               passed=bool(r["live_objective"] > ref["live_objective"])))
    checks.append(dict(check="numpy = torch (scores and product vectors)",
                       value=f"{max(serve['parity_max_abs'], serve['product_parity_max_abs']):.2e}", needed="< 1e-4",
                       passed=bool(max(serve["parity_max_abs"], serve["product_parity_max_abs"]) < 1e-4)))
    checks.append(dict(check="p99 latency, batch 1", value=f"{serve['latency_p99_ms']:.2f} ms", needed="< 20 ms",
                       passed=bool(serve["latency_p99_ms"] < 20)))
    if hc is not None:
        cal = hc.get("calibration_max_err")
        checks.append(dict(check="calibration within 20 % per decile (history, after recalibration)",
                           value=f"{cal:.3f}" if cal is not None else "n/a", needed="<= 0.20",
                           passed=bool(cal is not None and cal <= 0.2)))
        ivan.log_records("calibration", hc.get("calibration", []))
    ivan.log_records("checks", checks)
    ivan.log_summary(summary)
    (out / "metrics.json").write_text(json.dumps({"summary": summary, "metrics": recs}, indent=1))
    (out / "config.yaml").write_text(OmegaConf.to_yaml(ft.bcfg))
    (out / "finetune.yaml").write_text(OmegaConf.to_yaml(cfg))
    (out / "README.txt").write_text(
        f"Two-tower embedding model, fine-tuned on the live stream.\nexperiment: "
        f"{os.environ.get('IVAN_EXPERIMENT', 'local')}\nrun dir: {run_dir()}\nbase: {cfg.base}\n"
        f"live dataset version: {cfg.live.version}\ngit commit: {git_commit()}\n"
        f"trained: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        + "\n".join(f"{k}: {v}" for k, v in summary.items())
        + "\n\nUse: from training.export.scorer import load; model = load(<this folder>)\n")
    from training.export.describe import write as describe
    describe(out, name=os.environ.get("IVAN_EXPERIMENT", "local"))
    log("summary: " + json.dumps(summary))


if __name__ == "__main__":
    main()

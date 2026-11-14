"""Validation metrics on the held-out week: lift over best sellers per slice, with bootstrap intervals."""
from __future__ import annotations

import numpy as np
import torch

from training.embed.data import TRAIN_LAST_DAY
from training.export import features as F

SLICES = ("all", "cold", "warm", "new_user", "new_product")
OBJ_W = (50.0, 10.0)


def boot_lift(num_m, num_b, masks: dict, B: int, seed: int = 0):
    """lift = sum(m)/sum(b) - 1 per slice, with a Poisson bootstrap (shared weights across slices)."""
    rng = np.random.default_rng(seed)
    n = len(num_m)
    W = rng.poisson(1.0, size=(B, n)).astype(np.float32)
    out, draws = {}, {}
    for name, mk in masks.items():
        m, b = num_m * mk, num_b * mk
        sb = b.sum()
        val = m.sum() / sb - 1 if sb > 0 else np.nan
        bm, bb = W @ m, W @ b
        with np.errstate(divide="ignore", invalid="ignore"):
            d = bm / bb - 1
        d = d[np.isfinite(d)]
        draws[name] = (W @ m) / np.maximum(W @ b, 1e-12) - 1
        lo, hi = (np.percentile(d, [2.5, 97.5]) if len(d) else (np.nan, np.nan))
        out[name] = dict(lift=float(val), lift_lo=float(lo), lift_hi=float(hi), n=int((mk > 0).sum()),
                         value=float(m.sum() / max(mk.sum(), 1e-12)), baseline=float(b.sum() / max(mk.sum(), 1e-12)))
    return out, draws


class Evaluator:
    def __init__(self, data, dev, log_theta, max_organic=40000, seed=0):
        self.d = data
        self.dev = dev
        s = data.s
        P = len(data.product_ids)
        held_p = data.heldout_products
        held_u = data.heldout_users
        v = s["day"] > TRAIN_LAST_DAY
        self.vidx = np.flatnonzero(v)
        rv = s["rv"][self.vidx]
        new_user = held_u[s["user"][self.vidx]]
        new_prod = (held_p[rv.clip(0)] & (rv >= 0)).any(1)
        self.sess_slices = {"all": np.ones(len(self.vidx), bool), "new_user": new_user, "new_product": new_prod,
                            "cold": new_user | new_prod, "warm": ~(new_user | new_prod)}
        self.log_theta = log_theta  # [10, n_dev]
        pop = data.popularity.copy()
        self.pop_score = pop + 1e-6 * np.arange(P)[::-1] / P  # deterministic tie-break
        self.best = np.argsort(-self.pop_score)[:10]
        # organic purchases of the validation week
        e = data.e
        oi = np.flatnonzero((e["type"] == 2) & (e["day"] > TRAIN_LAST_DAY))
        rng = np.random.default_rng(seed)
        if len(oi) > max_organic:
            oi = np.sort(rng.choice(oi, max_organic, replace=False))
        self.oidx = oi
        ou = held_u[e["user"][oi]]
        orv = e["rv"][oi]
        op = held_p[e["prod"][oi]] | (held_p[orv.clip(0)] & (orv >= 0)).any(1)
        self.org_slices = {"all": np.ones(len(oi), bool), "new_user": ou, "new_product": op, "cold": ou | op,
                           "warm": ~(ou | op)}
        self.held_p = held_p

    # user vectors for arbitrary rows, with no history for held-out users
    def _users(self, model, V, part, idx, page=None, hist_len=None):
        d, dev = self.d, self.dev
        t = lambda a: torch.as_tensor(a, device=dev)  # noqa: E731
        ctx = model.context(t(part["device"][idx]), t(part["region"][idx]),
                            t(part["page"][idx]) if page is None else t(np.full(len(idx), page)),
                            t(part["hour"][idx]))
        rec, rec_has = model.pool_recent(V, t(part["rv"][idx]), ctx)
        N = model.hist_len
        if N > 0:
            end = t(part["hist_end"][idx])
            lo = t(part["hist_lo"][idx])
            pos = end[:, None] - 1 - torch.arange(N, device=dev)[None]
            hm = (pos >= lo[:, None]).float()
            held = t(d.heldout_users[part["user"][idx]])
            hm = hm * (~held).float()[:, None]
            pos = pos.clamp(min=0)
            hist, hist_has = model.pool_history(V, self.h_prod[pos], self.h_type[pos], hm)
        else:
            hist = torch.zeros_like(rec)
            hist_has = torch.zeros_like(rec_has)
        return model.users(ctx, rec, rec_has, hist, hist_has, torch.zeros(len(idx), device=dev))

    @torch.no_grad()
    def run(self, model, V, b, B=1000, chunk=4096, full=True):
        dev = self.dev
        d = self.d
        s = d.s
        if not hasattr(self, "h_prod"):
            self.h_prod = torch.as_tensor(d.h["prod"], device=dev)
            self.h_type = torch.as_tensor(d.h["type"], device=dev)
        lt = torch.as_tensor(self.log_theta, device=dev)
        P = V.shape[0]
        best_t = torch.as_tensor(self.best, device=dev)
        pop_t = torch.as_tensor(self.pop_score, device=dev, dtype=torch.float32)
        heldp_t = torch.as_tensor(self.held_p, device=dev)
        n = len(self.vidx)
        ips_m = np.zeros(n, np.float32)
        ips_b = np.zeros(n, np.float32)
        ips_den = np.zeros(n, np.float32)
        auc_m = np.zeros(n, np.float32)
        auc_b = np.zeros(n, np.float32)
        auc_w = np.zeros(n, np.float32)
        top_held = 0.0
        top_total = 0.0
        # calibration and slot rows
        pred_all, obs_all, cold_all, slot_all, devv_all, ctrp_all, clk_all = [], [], [], [], [], [], []
        for a in range(0, n, chunk):
            idx = self.vidx[a:a + chunk]
            u = self._users(model, V, s, idx)
            x_all = u @ V.T + b
            score = model.score_from_x(x_all)
            top = score.topk(10, dim=1).indices  # [c, 10]
            top_held += heldp_t[top].float().sum().item()
            top_total += top.numel()
            cs = torch.as_tensor(s["click_slot"][idx], device=dev)
            shown = torch.as_tensor(s["shown"][idx], device=dev)
            devi = torch.as_tensor(s["device"][idx], device=dev)
            has = cs >= 0
            rows = torch.nonzero(has)[:, 0]
            if len(rows):
                cslot = cs[rows]
                cprod = shown[rows, cslot]
                purch = torch.as_tensor(s["purchased"][idx], device=dev)[rows]
                prop = torch.as_tensor(s["prop"][idx], device=dev)[rows, cslot]
                w = torch.where(purch, 3.0, 1.0) / prop.clamp(min=0.01)
                dv = devi[rows]
                hit_m = (top[rows] == cprod[:, None])
                th = torch.exp(lt[:, dv].T)  # [r, 10]
                m_val = (hit_m.float() * th).sum(1) * w
                hit_b = (best_t[None] == cprod[:, None])
                b_val = (hit_b.float() * th).sum(1) * w
                ri = rows.cpu().numpy() + a
                ips_m[ri] = m_val.cpu().numpy()
                ips_b[ri] = b_val.cpu().numpy()
                ips_den[ri] = w.cpu().numpy()
                # slate auc within the shown 10
                sh = shown[rows]
                valid = sh >= 0
                sm = score[rows].gather(1, sh.clamp(min=0))
                sb = pop_t[sh.clamp(min=0)]
                for sc, out in ((sm, auc_m), (sb, auc_b)):
                    c = sc.gather(1, cslot[:, None])
                    others = valid & (torch.arange(10, device=dev)[None] != cslot[:, None])
                    gt = ((c > sc).float() + 0.5 * (c == sc).float()) * others
                    out[ri] = (gt.sum(1) / others.sum(1).clamp(min=1)).cpu().numpy()
                auc_w[ri] = (1.0 / torch.exp(lt[cslot, dv])).cpu().numpy()
            if full:
                # calibration and per-slot click rates on every shown impression
                valid = shown >= 0
                xs = x_all.gather(1, shown.clamp(min=0))
                k = torch.arange(10, device=dev)[None].expand_as(shown)
                sl = model.slot[k, devi[:, None].expand_as(shown)]
                pc = torch.sigmoid(xs + model.c_click + sl)
                pp = pc * torch.sigmoid(model.alpha * xs + model.c_purchase)
                clk = (k == cs[:, None])
                obs = clk & torch.as_tensor(s["purchased"][idx], device=dev)[:, None]
                cold = torch.as_tensor(self.sess_slices["cold"][a:a + chunk], device=dev)[:, None].expand_as(shown)
                vm = valid
                pred_all.append(pp[vm].cpu().numpy())
                obs_all.append(obs[vm].cpu().numpy())
                cold_all.append(cold[vm].cpu().numpy())
                slot_all.append(k[vm].cpu().numpy())
                devv_all.append(devi[:, None].expand_as(shown)[vm].cpu().numpy())
                ctrp_all.append(pc[vm].cpu().numpy())
                clk_all.append(clk[vm].cpu().numpy())
        res = {}
        click_rows = ips_den > 0
        masks = {k: (v & click_rows).astype(np.float32) for k, v in self.sess_slices.items()}
        ips, ips_draws = boot_lift(ips_m, ips_b, masks, B)
        res["ips_hit@10"] = ips
        aw = auc_w * click_rows
        auc, _ = boot_lift(auc_m * aw, auc_b * aw, {k: v.astype(np.float32) for k, v in self.sess_slices.items()}, B)
        # value as weighted mean auc
        for k, v in self.sess_slices.items():
            wsum = (aw * v).sum()
            auc[k]["value"] = float((auc_m * aw * v).sum() / max(wsum, 1e-12))
            auc[k]["baseline"] = float((auc_b * aw * v).sum() / max(wsum, 1e-12))
            auc[k]["n"] = int(((aw > 0) & v).sum())
        res["slate_auc"] = auc
        # organic recall
        e = d.e
        on = len(self.oidx)
        rec_m = np.zeros(on, np.float32)
        page_org = d.vocab["page"][F.ORGANIC_PAGE]
        for a in range(0, on, chunk):
            idx = self.oidx[a:a + chunk]
            u = self._users(model, V, e, idx, page=page_org)
            score = model.score_from_x(u @ V.T + b)
            top = score.topk(10, dim=1).indices
            tgt = torch.as_tensor(e["prod"][idx], device=dev)
            rec_m[a:a + chunk] = (top == tgt[:, None]).any(1).float().cpu().numpy()
        rec_b = np.isin(e["prod"][self.oidx], self.best).astype(np.float32)
        orec, _ = boot_lift(rec_m, rec_b, {k: v.astype(np.float32) for k, v in self.org_slices.items()}, B)
        res["organic_recall@10"] = orec
        # objective
        dr = ips_draws
        obj = (OBJ_W[0] * ips["all"]["lift"] + OBJ_W[1] * ips["cold"]["lift"]) / sum(OBJ_W)
        obj_draws = (OBJ_W[0] * dr["all"] + OBJ_W[1] * dr["cold"]) / sum(OBJ_W)
        obj_draws = obj_draws[np.isfinite(obj_draws)]
        out = {"metrics": res, "objective": float(obj), "objective_se": float(obj_draws.std()) if len(obj_draws) else None,
               "lift_all": ips["all"]["lift"], "lift_cold": ips["cold"]["lift"],
               "share_top10_heldout": top_held / max(top_total, 1)}
        if full:
            pred = np.concatenate(pred_all)
            obs = np.concatenate(obs_all).astype(np.float64)
            cold = np.concatenate(cold_all)
            slot = np.concatenate(slot_all)
            devv = np.concatenate(devv_all)
            ctrp = np.concatenate(ctrp_all)
            clk = np.concatenate(clk_all).astype(np.float64)
            cal = []
            errs = []
            for name, mk in (("all", np.ones_like(cold)), ("cold", cold)):
                p, o = pred[mk], obs[mk]
                if len(p) < 100:
                    continue
                edges = np.quantile(p, np.linspace(0, 1, 11))
                dec = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, 9)
                for q in range(10):
                    sel = dec == q
                    pm, om = float(p[sel].mean()), float(o[sel].mean())
                    cal.append(dict(dataset="history", slice=name, decile=q + 1, predicted=pm, observed=om,
                                    n=int(sel.sum())))
                    if om > 0:
                        errs.append(abs(pm / om - 1))
                    else:
                        errs.append(np.inf if pm > 0 else 0.0)
            out["calibration"] = cal
            out["calibration_max_err"] = float(max(errs)) if errs else None
            slots = []
            dev_names = {v: k for k, v in d.vocab["device"].items()}
            for dv in np.unique(devv):
                for k in range(10):
                    sel = (devv == dv) & (slot == k)
                    if not sel.any():
                        continue
                    slots.append(dict(device=dev_names.get(int(dv), "?"), slot=k + 1,
                                      theta_learned=float(np.exp(model.slot[k, dv].item())),
                                      theta_measured=float(np.exp(self.log_theta[k, dv])),
                                      ctr_pred=float(ctrp[sel].mean()), ctr_obs=float(clk[sel].mean())))
            out["slot"] = slots
            # share of clicks on held-out products (validation week)
            vc = s["click_slot"][self.vidx]
            hc = vc >= 0
            cp = s["shown"][self.vidx][hc, vc[hc]]
            out["share_clicks_heldout"] = float(self.held_p[cp].mean()) if len(cp) else None
        return out

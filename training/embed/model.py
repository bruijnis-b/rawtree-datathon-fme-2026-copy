"""Two-tower model in PyTorch. The numpy scorer (training/export/scorer.py) mirrors forward() exactly.

score(user, product) = logit( sigmoid(x + c_click) * sigmoid(alpha * x + c_purchase) ),  x = u . v + b
i.e. the log-odds of a purchase when the product is shown in slot 1. In training the click head also gets the slot
term s[slot, device] (s[slot 1] = 0); it is dropped at inference.
"""
from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as Fn

from training.export import features as F

CTX = 16  # dimension of each context embedding


class TwoTower(nn.Module):
    def __init__(self, n_cat, n_sub, n_brand, n_products, n_device, n_region, n_page, log_theta, cfg):
        super().__init__()
        m = cfg.model
        d, H = m.dim, m.hidden
        self.cfg = cfg
        self.d = d
        self.use_desc = bool(m.description)
        self.use_price = bool(m.price)
        self.pooling = m.pooling
        self.hist_len = int(m.history_len)
        # product tower
        self.e_cat = nn.Embedding(n_cat + 1, CTX)
        self.e_sub = nn.Embedding(n_sub + 1, CTX)
        self.e_brand = nn.Embedding(n_brand + 1, CTX)
        self.e_tok = nn.Embedding(F.N_TOKENS, CTX)
        p_in = 3 * CTX + 2 + CTX
        self.p1 = nn.Linear(p_in, H)
        self.p2 = nn.Linear(H, d)
        self.p_bias = nn.Linear(H, 1)
        self.e_id = nn.Embedding(n_products, d)
        self.b_id = nn.Embedding(n_products, 1)
        nn.init.normal_(self.e_id.weight, std=0.01)
        nn.init.zeros_(self.b_id.weight)
        self.no_id = nn.Parameter(torch.tensor(0.0))  # bias offset for a product scored without its ID vector
        self.x_scale = nn.Parameter(torch.tensor(1.0), requires_grad=False)  # head recalibration; folded at export
        # user tower
        self.e_dev = nn.Embedding(n_device + 1, CTX)
        self.e_reg = nn.Embedding(n_region + 1, CTX)
        self.e_page = nn.Embedding(n_page + 1, CTX)
        self.e_hour = nn.Embedding(24, CTX)
        u_in = 4 * CTX + d + 1 + d + 1
        self.u1 = nn.Linear(u_in, H)
        self.u2 = nn.Linear(H, d)
        self.w_new = nn.Parameter(torch.zeros(H))  # is_new_user: zero start, learned only on live data
        self.att_q = nn.Linear(4 * CTX, d)
        self.recency = m.recency_decay
        self.type_w = nn.Parameter(torch.tensor([1.0, 2.0, 4.0]), requires_grad=False)
        # heads
        self.c_click = nn.Parameter(torch.tensor(-4.6))
        self.c_purchase = nn.Parameter(torch.tensor(-0.3))
        self.alpha = nn.Parameter(torch.tensor(1.0))
        lt = torch.as_tensor(log_theta)
        if m.slot == "learned":
            self.slot = nn.Parameter(lt.clone())
        else:
            self.register_buffer("slot", lt.clone() if m.slot == "fixed" else torch.zeros_like(lt))
        self.register_buffer("slot_init", lt.clone())
        # out-of-sample recalibration of the delivered score: score -> score_a * score + score_c
        self.register_buffer("score_a", torch.tensor(1.0))
        self.register_buffer("score_c", torch.tensor(0.0))

    # ---------------- product tower ----------------
    def products(self, cat, sub, brand, price, tok, id_mask):
        """[P, d] vectors and [P] biases. id_mask (float [P]): 1 where the product's ID vector is used."""
        price = price if self.use_price else torch.zeros_like(price)
        if self.use_desc:
            tm = (tok > 0).float()
            desc = (self.e_tok(tok) * tm[..., None]).sum(1) / tm.sum(1, keepdim=True).clamp(min=1)
        else:
            desc = torch.zeros(cat.shape[0], CTX, device=cat.device)
        x = torch.cat([self.e_cat(cat), self.e_sub(sub), self.e_brand(brand), price, desc], 1)
        h = Fn.relu(self.p1(x))
        idx = torch.arange(cat.shape[0], device=cat.device)
        v = self.p2(h) + id_mask[:, None] * self.e_id(idx)
        b = self.p_bias(h)[:, 0] + id_mask * self.b_id(idx)[:, 0]
        if self.cfg.model.get("no_id_offset", True):
            b = b + (1 - id_mask) * self.no_id
        return v, b

    # ---------------- user tower ----------------
    def context(self, device, region, page, hour):
        return torch.cat([self.e_dev(device), self.e_reg(region), self.e_page(page), self.e_hour(hour)], 1)

    def pool_recent(self, V, rv, ctx):
        """rv [B, 6] product indices, oldest first, -1 = none."""
        mask = (rv >= 0).float()
        vec = V[rv.clamp(min=0)] * mask[..., None]
        has = (mask.sum(1, keepdim=True) > 0).float()
        if self.pooling == "attention":
            q = self.att_q(ctx)
            logit = (vec * q[:, None]).sum(-1) / math.sqrt(self.d)
            logit = logit.masked_fill(mask == 0, -1e9)
            w = torch.softmax(logit, 1) * mask
        elif self.pooling == "mean":
            w = mask
        else:  # recency-weighted mean: weight decay^(age), age 0 for the newest view
            age = torch.arange(rv.shape[1] - 1, -1, -1, device=rv.device, dtype=torch.float32)
            w = mask * self.recency ** age
        w = w / w.sum(1, keepdim=True).clamp(min=1e-9)
        return (vec * w[..., None]).sum(1), has

    def pool_history(self, V, hp, ht, hm):
        """hp, ht [B, N] product index and event type; hm float mask. Type-weighted mean of product vectors."""
        w = hm * self.type_w[ht.clamp(min=0)]
        vec = (V[hp.clamp(min=0)] * w[..., None]).sum(1) / w.sum(1, keepdim=True).clamp(min=1e-9)
        return vec, (hm.sum(1, keepdim=True) > 0).float()

    def users(self, ctx, rec, rec_has, hist, hist_has, is_new):
        x = torch.cat([ctx, rec, rec_has, hist * hist_has, hist_has], 1)
        h = self.u1(x) + is_new[:, None] * self.w_new
        return self.u2(Fn.relu(h))

    # ---------------- heads ----------------
    def score_from_x(self, x):
        """Delivered score: purchase log-odds in slot 1."""
        lc = Fn.logsigmoid(x + self.c_click) + Fn.logsigmoid(self.alpha * x + self.c_purchase)  # log p
        return self.score_a * (lc - torch.log1p(-torch.exp(lc).clamp(max=1 - 1e-7))) + self.score_c

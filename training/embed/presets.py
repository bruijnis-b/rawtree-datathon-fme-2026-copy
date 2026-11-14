"""Named one-axis variants of the default config (phase A): `preset=<name>` applies its overrides.

`ivan run training.train preset=a,b,c` queues one run per preset, so the axes view shows them side by side.
"""
from __future__ import annotations

from omegaconf import DictConfig, OmegaConf

PRESETS: dict[str, dict] = {
    "default": {},
    "dim32": {"model.dim": 32},
    "dim128": {"model.dim": 128},
    "hidden256": {"model.hidden": 256},
    "iddrop0": {"model.id_dropout": 0.0},
    "iddrop50": {"model.id_dropout": 0.5},
    "iddrop100": {"model.id_dropout": 1.0},
    "histdrop0": {"model.history_dropout": 0.0},
    "histdrop50": {"model.history_dropout": 0.5},
    "hist0": {"model.history_len": 0},
    "hist50": {"model.history_len": 50},
    "pool_mean": {"model.pooling": "mean"},
    "pool_att": {"model.pooling": "attention"},
    "recency50": {"model.recency_decay": 0.5},
    "org_off": {"organic.mode": "off"},
    "org_w03": {"organic.weight": 0.3},
    "org_staged": {"organic.mode": "staged"},
    "org_nologq": {"organic.logq": False},
    "org_uniform_types": {"organic.type_weights": [1.0, 1.0, 1.0]},
    "prop05": {"loss.propensity_clip": 0.05},
    "prop01": {"loss.propensity_clip": 0.01},
    "click03": {"loss.click_weight": 0.3},
    "click3": {"loss.click_weight": 3.0},
    "slot_fixed": {"model.slot": "fixed"},
    "slot_off": {"model.slot": "off"},
    "desc": {"model.description": True},
    "noprice": {"model.price": False},
    "lr07": {"train.lr": 0.0007},
    "lr5": {"train.lr": 0.005},
    "wd0": {"train.weight_decay": 0.0},
    "wd4": {"train.weight_decay": 1.0e-4},
    "bs1024": {"train.batch_size": 1024},
    "bs4096": {"train.batch_size": 4096},
}

# Phase B candidates: the top eligible configurations of phase A (full settings of the A run they come from).
PRESETS.update({
    'b_a2_45': {'loss.click_weight': 1.0, 'loss.propensity_clip': 0.0, 'model.description': True, 'model.dim': 32, 'model.history_dropout': 0.3, 'model.history_len': 50, 'model.id_dropout': 0.0, 'model.pooling': 'mean', 'model.slot': 'fixed', 'organic.mode': 'joint', 'organic.weight': 1.0, 'train.batch_size': 2048, 'train.lr': 0.002, 'train.weight_decay': 0.0001},  # embed-a2/45
    'b_a2_25': {'loss.click_weight': 1.0, 'loss.propensity_clip': 0.0, 'model.description': True, 'model.dim': 64, 'model.history_dropout': 0.5, 'model.history_len': 20, 'model.id_dropout': 0.5, 'model.pooling': 'mean', 'model.slot': 'learned', 'organic.mode': 'joint', 'organic.weight': 1.0, 'train.batch_size': 2048, 'train.lr': 0.0007, 'train.weight_decay': 1e-05},  # embed-a2/25
    'b_a2_43': {'loss.click_weight': 0.3, 'loss.propensity_clip': 0.0, 'model.description': True, 'model.dim': 32, 'model.history_dropout': 0.5, 'model.history_len': 20, 'model.id_dropout': 0.5, 'model.pooling': 'recency', 'model.slot': 'learned', 'organic.mode': 'joint', 'organic.weight': 1.0, 'train.batch_size': 4096, 'train.lr': 0.0007, 'train.weight_decay': 1e-05},  # embed-a2/43
    'b_a2_8': {'loss.click_weight': 0.3, 'loss.propensity_clip': 0.0, 'model.description': True, 'model.dim': 128, 'model.history_dropout': 0.3, 'model.history_len': 50, 'model.id_dropout': 0.5, 'model.pooling': 'mean', 'model.slot': 'learned', 'organic.mode': 'joint', 'organic.weight': 0.3, 'train.batch_size': 1024, 'train.lr': 0.0007, 'train.weight_decay': 0.0},  # embed-a2/8
    'b_a2_10': {'loss.click_weight': 1.0, 'loss.propensity_clip': 0.05, 'model.description': True, 'model.dim': 32, 'model.history_dropout': 0.3, 'model.history_len': 20, 'model.id_dropout': 0.25, 'model.pooling': 'attention', 'model.slot': 'fixed', 'organic.mode': 'joint', 'organic.weight': 1.0, 'train.batch_size': 1024, 'train.lr': 0.002, 'train.weight_decay': 0.0},  # embed-a2/10
    'b_desc': PRESETS['desc'],  # embed-a1/26
    'b_hist50': PRESETS['hist50'],  # embed-a1/11
    'b_lr07': PRESETS['lr07'],  # embed-a1/28
})


def apply_preset(cfg: DictConfig) -> DictConfig:
    name = str(cfg.get("preset", "default"))
    extra = PRESETS.get(name)
    if extra is None:
        if "+" in name:  # combination: a+b
            extra = {}
            for part in name.split("+"):
                extra.update(PRESETS[part])
        else:
            raise KeyError(f"unknown preset {name!r}")
    OmegaConf.set_struct(cfg, False)
    # settings given on the command line win over the preset (e.g. preset=b_a2_43 model.history_len=50)
    explicit = set()
    try:
        from hydra.core.hydra_config import HydraConfig
        explicit = {o.split("=", 1)[0].lstrip("+~") for o in HydraConfig.get().overrides.task}
    except Exception:  # noqa: BLE001  (not under @hydra.main)
        pass
    for k, v in extra.items():
        if k not in explicit:
            OmegaConf.update(cfg, k, v, merge=False)
    return cfg

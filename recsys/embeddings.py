"""Embedding models as a shared live service: per request, one purchase score per product, for any policy.

    model = self.embedding_model()                # in a policy's fit(): the model named by its `embed_model`
    s = model.scores(req)                         # per request: Scores (ids, values, index), log-odds
    s.get("p_123")                                # one product's score
    s.aligned(my_ids)                             # the scores in your own product order (e.g. ShopperScore's)
    model.similar("p_123", 20)                    # nearest products by embedding

**The score is the log-odds that the shopper buys the product when it is shown in slot 1**, whatever model is
behind it. A difference of 0.7 doubles the odds. Corrections go on top, on the same scale: add log-odds, or
multiply odds (`exp(score) x factor`, as shopper_score does).

The model covers the product's content (category, subcategory, brand, original price) and identity, the request
context (device, region, page, hour), the request's recent views and the shopper's history (their last events,
history and live; see `user_events`). Do not correct for those again. Discounts, trends, cart and already-bought
products are not in it.

## Which model

Models are named folders under `models/` (gitignored; a few MB to ~20 MB each), listed in
`recsys/embed_models.json` with their checksums and the GitHub release they are published in. That file also
names the `default` model. Policies pick one with their `embed_model` setting:

    python -m recsys.main --policy embed_score                       # the default model
    python -m recsys.main --policy embed_score --set embed_model=v1   # another one
    python -m recsys.main --policy embed_score --ab embed_score:embed_model=v1   # A/B: default vs v1

The resolved name is part of the policy's settings, so each model gets its own public model ID.

    python -m recsys.embeddings list              # models, which are downloaded, which is the default
    python -m recsys.embeddings fetch v0          # download one from its GitHub release (needs `gh`)
    python -m recsys.embeddings publish models/v1 --name v1 [--default]   # upload a new one (Jules)

## Live sync

New products (`new_product` in shop.catalog_updates) are embedded from their catalogue fields in a background
thread within ~0.2 s, with their original price (`Product.list_price`). Price and stock changes do not change the
vectors. A product not embedded yet gets the lowest score in `aligned` for that moment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from .catalog import LiveCatalog
    from .profiles import Profiles

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
MANIFEST = Path(__file__).resolve().parent / "embed_models.json"
FILES = ("model.npz", "user_vectors.npz", "README.txt", "metrics.json", "config.yaml")  # published per model
CHECKED = ("model.npz", "user_vectors.npz")  # files whose checksum must match the manifest
SYNC_S = 0.2  # how often the background thread checks the catalogue for new products


# ---------------------------------------------------------------- model selection
def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"default": "", "models": {}}


def default_name() -> str:
    return manifest().get("default", "")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(name: str = "") -> tuple[str, Path]:
    """(model id, folder) for a manifest name, or for a folder path (not published, for trying a model locally).

    The id of a folder path includes the checksum of its model.npz, so a changed model gets a new public ID."""
    name = name or default_name()
    if not name:
        raise RuntimeError(f"no embedding model given and no default in {MANIFEST.name}")
    entry = manifest()["models"].get(name)
    if entry is None:
        folder = Path(name)
        if not (folder / "model.npz").exists():
            raise RuntimeError(f"embedding model {name!r} is neither in {MANIFEST.name} nor a folder with model.npz")
        return f"{folder.resolve().name}@{sha256(folder / 'model.npz')[:8]}", folder
    folder = MODELS_DIR / name
    for f in CHECKED:
        want = entry.get("sha256", {}).get(f)
        if want is None:
            continue
        if not (folder / f).exists():
            raise RuntimeError(f"embedding model {name!r} is not downloaded: python -m recsys.embeddings fetch {name}")
        if sha256(folder / f) != want:
            raise RuntimeError(f"{folder / f} does not match {MANIFEST.name} (other version of {name!r}?): "
                               f"delete the folder and run python -m recsys.embeddings fetch {name}")
    return name, folder


def load_backend(folder: Path):
    """The scorer for this model's format. Every backend has embed_products(rows, base) -> matrix with .ids,
    .vecs, .index; score(request, matrix, events=None) -> log-odds per row; and meta['history_len'].

    A future model with a different architecture adds its format here; policies do not change."""
    z = np.load(folder / "model.npz", allow_pickle=False)
    fmt = json.loads(str(z["meta__json"])).get("format", "two_tower_v1")
    if fmt == "two_tower_v1":
        from training.export.scorer import load
        return load(folder)
    raise RuntimeError(f"{folder}: unknown embedding model format {fmt!r} (update recsys/embeddings.py)")


# ---------------------------------------------------------------- scores
@dataclass
class Scores:
    """One request's model scores: values[i] is the purchase log-odds of ids[i]."""
    ids: list[str]
    values: np.ndarray
    index: dict[str, int]
    _model: "EmbeddingModel" = field(repr=False)

    def get(self, pid: str, default: float | None = None) -> float | None:
        i = self.index.get(pid)
        return float(self.values[i]) if i is not None else default

    def aligned(self, ids: list[str], fill: float | None = None) -> np.ndarray:
        """The scores in the order of `ids` (products the model has not embedded yet get `fill`, default the
        lowest score). The position lookup is cached per `ids` list, so pass the same list object each time."""
        pos = self._model._positions(ids, self.index)
        out = self.values[np.maximum(pos, 0)]
        if (pos < 0).any():
            out = out.copy()
            out[pos < 0] = self.values.min() if fill is None else fill
        return out

    def top(self, k: int = 10, active_only: bool = True) -> list[str]:
        """The k best products (in stock only, by default), best first."""
        n = min(len(self.ids), k + 50)
        cand = np.argpartition(-self.values, n - 1)[:n]
        out = []
        for i in cand[np.argsort(-self.values[cand])]:
            pid = self.ids[i]
            if not active_only or self._model.catalog.is_active(pid):
                out.append(pid)
                if len(out) == k:
                    break
        return out


class EmbeddingModel:
    """One loaded model, kept in sync with the live catalogue. Get it through Embeddings.get (shared)."""

    def __init__(self, name: str, catalog: "LiveCatalog", profiles: "Profiles | None" = None) -> None:
        self.model_id, self.folder = resolve(name)
        self.catalog = catalog
        self.profiles = profiles
        self.backend = load_backend(self.folder)
        self.history_len = int(self.backend.meta.get("history_len", 0))
        self._lock = threading.Lock()
        self._pos_cache: tuple[Any, Any, np.ndarray] | None = None
        self.pm = None
        self.sync()
        log.info("embedding model %s loaded from %s: %d products, %d user vectors, history of %d events",
                 self.model_id, self.folder, len(self.pm.ids), len(getattr(self.backend, "user_index", {})),
                 self.history_len)
        threading.Thread(target=self._run, name=f"embed-{self.model_id}", daemon=True).start()

    # -------- products
    def sync(self) -> int:
        """Embed the catalogue products the model does not have yet; returns how many."""
        with self._lock:
            version = self.catalog.version
            have = self.pm.index if self.pm is not None else {}
            todo = [p for p in self.catalog.snapshot() if p.product_id not in have]
            if todo or self.pm is None:
                rows = [dict(product_id=p.product_id, category=p.category, subcategory=p.subcategory,
                             brand=p.brand, description=p.description, price=p.list_price or p.price_eur)
                        for p in todo]
                self.pm = self.backend.embed_products(rows, self.pm)  # a new matrix: swapped in at once
                self._norm = None
            self._seen_version = version
            return len(todo)

    def _run(self) -> None:
        while True:
            time.sleep(SYNC_S)
            if self.catalog.version != self._seen_version:
                try:
                    n = self.sync()
                    if n:
                        log.info("embedding model %s: embedded %d new products", self.model_id, n)
                except Exception as e:
                    log.warning("embedding model %s: embedding new products failed: %s", self.model_id, e)

    def vector(self, pid: str) -> np.ndarray | None:
        pm = self.pm
        i = pm.index.get(pid)
        return pm.vecs[i] if i is not None else None

    def similar(self, pid: str, k: int = 20) -> list[tuple[str, float]]:
        """The k products closest to `pid` by cosine similarity of their vectors (pid itself excluded)."""
        pm = self.pm
        i = pm.index.get(pid)
        if i is None:
            return []
        norm = self._norm
        if norm is None or len(norm) != len(pm.ids):
            norm = self._norm = pm.vecs / np.maximum(np.linalg.norm(pm.vecs, axis=1, keepdims=True), 1e-9)
        sim = norm @ norm[i]
        sim[i] = -np.inf
        top = np.argpartition(-sim, min(k, len(sim) - 1))[:k]
        return [(pm.ids[j], float(sim[j])) for j in top[np.argsort(-sim[top])]]

    def _positions(self, ids: list[str], index: dict[str, int]) -> np.ndarray:
        c = self._pos_cache
        if c is not None and c[0] is ids and c[1] is index:
            return c[2]
        pos = np.array([index.get(p, -1) for p in ids], dtype=np.int64)
        self._pos_cache = (ids, index, pos)
        return pos

    # -------- users
    def user_events(self, req) -> list[tuple[str, str]] | None:
        """The shopper's last events, history then live, oldest first, as the model was trained on them; None
        to let the model use its precomputed history vector (same result without live events, cheaper).

        Training pooled each shopper's last `history_len` events (view, add_to_cart, purchase) of
        shop.history_events followed by the live shop.events, so this passes exactly that sequence once the
        shopper has live events. Until Profiles has loaded the history, known shoppers keep their precomputed
        vector (an incomplete sequence would drop their history)."""
        if self.profiles is None or self.history_len <= 0 or not req.user_id:
            return None
        if not self.profiles.has_live_events(req.user_id):
            return None
        if not self.profiles.history_ready and req.user_id in getattr(self.backend, "user_index", {}):
            return None
        index = self.pm.index
        events = [e for e in self.profiles.events(req.user_id) if e[0] in index]  # training dropped unknown ones
        return events[-self.history_len:] or None

    def scores(self, req, events: Any = "auto") -> Scores:
        """The model's score for every product it has embedded (in stock or not), for this request.

        events: "auto" (the shopper's history and live events, see user_events), None (precomputed history
        vector only) or your own list of (product_id, event_type), oldest first."""
        pm = self.pm
        if events == "auto":
            events = self.user_events(req)
        return Scores(pm.ids, self.backend.score(req, pm, events=events), pm.index, self)


class Embeddings:
    """All embedding models of this process, loaded on first use and shared by every policy (main.py makes one).

    Loading a model takes a few seconds (~20 MB, embedding ~5,000 products); after that a request costs a few ms."""

    def __init__(self, catalog: "LiveCatalog", profiles: "Profiles | None" = None) -> None:
        self.catalog = catalog
        self.profiles = profiles
        self.models: dict[str, EmbeddingModel] = {}
        self._lock = threading.Lock()

    def get(self, name: str = "") -> EmbeddingModel:
        """The model with this manifest name or folder ('' = the default), loading it if needed."""
        model_id, _ = resolve(name)
        with self._lock:
            if model_id not in self.models:
                self.models[model_id] = EmbeddingModel(name or default_name(), self.catalog, self.profiles)
            return self.models[model_id]


# ---------------------------------------------------------------- CLI: list, fetch, publish
def _repo() -> str:
    return subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()


def cmd_list(_: argparse.Namespace) -> None:
    m = manifest()
    for name, e in m["models"].items():
        folder = MODELS_DIR / name
        try:
            resolve(name)
            state = "ready"
        except RuntimeError:
            state = "different version on disk" if folder.exists() else "not downloaded"
        print(f"{'*' if name == m.get('default') else ' '} {name:12s} {state:26s} release {e.get('release', '-'):14s} "
              f"{e.get('notes', '')}")
    print("\n* = default. Download: python -m recsys.embeddings fetch NAME")


def cmd_fetch(args: argparse.Namespace) -> None:
    entry = manifest()["models"].get(args.name)
    if entry is None:
        sys.exit(f"{args.name!r} is not in {MANIFEST.name}: git pull first?")
    folder = MODELS_DIR / args.name
    folder.mkdir(parents=True, exist_ok=True)
    cmd = ["gh", "release", "download", entry["release"], "--repo", _repo(), "--dir", str(folder), "--clobber"]
    for f in FILES:
        cmd += ["--pattern", f]
    subprocess.run(cmd, check=True)
    resolve(args.name)  # checksums
    print(f"{args.name}: ready in {folder}")


def cmd_publish(args: argparse.Namespace) -> None:
    folder = Path(args.folder)
    files = [folder / f for f in FILES if (folder / f).exists()]
    if not (folder / "model.npz").exists():
        sys.exit(f"{folder} has no model.npz")
    m = manifest()
    if args.name in m["models"] and not args.replace:
        sys.exit(f"{args.name!r} already exists: published models never change (pick a new name)")
    load_backend(folder)  # refuses a model this code cannot serve
    release = f"embed-{args.name}"
    readme = folder / "README.txt"
    notes = ["--notes-file", str(readme)] if readme.exists() else ["--notes", args.notes or args.name]
    subprocess.run(["gh", "release", "create", release, "--repo", _repo(), "--title", f"Embedding model {args.name}",
                    "--prerelease", *notes, *map(str, files)], check=True)
    m["models"][args.name] = {"release": release, "notes": args.notes,
                              "sha256": {f: sha256(folder / f) for f in CHECKED if (folder / f).exists()}}
    if args.default:
        m["default"] = args.name
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    dest = MODELS_DIR / args.name
    if folder.resolve() != dest.resolve():
        dest.mkdir(parents=True, exist_ok=True)
        for f in files:
            (dest / f.name).write_bytes(f.read_bytes())
    print(f"published {args.name} as release {release}; commit {MANIFEST.relative_to(ROOT)} so others see it")


def main() -> None:
    ap = argparse.ArgumentParser(description="Embedding models: list, download, publish.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    f = sub.add_parser("fetch")
    f.add_argument("name")
    f.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("publish")
    p.add_argument("folder")
    p.add_argument("--name", required=True)
    p.add_argument("--notes", default="")
    p.add_argument("--default", action="store_true", help="make it the default model")
    p.add_argument("--replace", action="store_true", help="overwrite the manifest entry (never for a served model)")
    p.set_defaults(fn=cmd_publish)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

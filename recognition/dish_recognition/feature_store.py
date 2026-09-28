from __future__ import annotations

import json
import os
import threading
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np

_INDEX_FILE = "index.json"
_VECTORS_FILE = "vectors.npy"
_FORMAT_VERSION = 1
_SNAPSHOT_FILE = 'store.npz'


@dataclass(frozen=True)
class Match:
    dish_id: str
    score: float


def _normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors[None, :]
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return vectors / norms


class FeatureStore:
    """In-memory vector store with cosine search and atomic disk persistence.

    Each dish may own any number of vectors (multi-view enrollment); a
    dish's score against a query is the max over its vectors. Brute-force
    numpy matmul is plenty for the hundreds-of-dishes scale of a canteen.
    """

    def __init__(self, dim: int = 2048):
        self.dim = dim
        self._ids: List[str] = []
        self._vectors = np.zeros((0, dim), dtype=np.float32)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ CRUD

    def add(self, dish_id: str, vectors: np.ndarray, replace: bool = False) -> int:
        vectors = _normalize(vectors)
        if vectors.shape[1] != self.dim:
            raise ValueError(
                f"vector dim {vectors.shape[1]} != store dim {self.dim}"
            )
        with self._lock:
            if replace:
                self.remove(dish_id)
            self._vectors = np.vstack([self._vectors, vectors])
            self._ids.extend([str(dish_id)] * len(vectors))
        return len(vectors)

    def remove(self, dish_id: str) -> int:
        dish_id = str(dish_id)
        with self._lock:
            keep = np.array([i != dish_id for i in self._ids], dtype=bool)
            removed = int((~keep).sum())
            if removed:
                self._vectors = self._vectors[keep]
                self._ids = [i for i, k in zip(self._ids, keep) if k]
        return removed

    def __len__(self) -> int:
        return len(self._ids)

    @property
    def dish_ids(self) -> List[str]:
        with self._lock:
            return sorted(set(self._ids))

    @property
    def counts(self) -> Dict[str, int]:
        with self._lock:
            return dict(Counter(self._ids))

    # ---------------------------------------------------------------- search

    def search(self, vector: np.ndarray, top_k: int = 3) -> List[Match]:
        """Rank dishes by max cosine similarity against `vector`."""
        query = _normalize(vector)[0]
        with self._lock:
            if not self._ids:
                return []
            sims = self._vectors @ query
            best: Dict[str, float] = {}
            for dish_id, sim in zip(self._ids, sims):
                s = float(sim)
                if s > best.get(dish_id, -2.0):
                    best[dish_id] = s
        ranked = sorted(best.items(), key=lambda kv: -kv[1])[:top_k]
        return [Match(dish_id, score) for dish_id, score in ranked]

    def conflicts(
        self,
        vectors: np.ndarray,
        threshold: float,
        exclude: Optional[Set[str]] = None,
    ) -> List[Match]:
        """Existing dishes whose similarity to any of `vectors` >= threshold.

        Used at enrollment time to warn that a new dish is hard to tell
        apart from an existing one. Never mutates anything.
        """
        vectors = _normalize(vectors)
        exclude = {str(e) for e in (exclude or set())}
        with self._lock:
            if not self._ids:
                return []
            sims = vectors @ self._vectors.T  # (new, stored)
            per_stored = sims.max(axis=0)
            best: Dict[str, float] = {}
            for dish_id, sim in zip(self._ids, per_stored):
                if dish_id in exclude:
                    continue
                s = float(sim)
                if s > best.get(dish_id, -2.0):
                    best[dish_id] = s
        hits = [Match(d, s) for d, s in best.items() if s >= threshold]
        return sorted(hits, key=lambda m: -m.score)

    # ----------------------------------------------------------- persistence

    def save(self, store_dir: Path) -> None:
        store_dir = Path(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            ids = list(self._ids)
            vectors = self._vectors.copy()

        # IDs and vectors must switch together. Two independent file renames
        # can leave mismatched generations after an interrupted sample update.
        fd, name = tempfile.mkstemp(suffix='.tmp', dir=store_dir)
        try:
            with os.fdopen(fd, 'wb') as f:
                np.savez(f, ids=np.asarray(ids, dtype=str), vectors=vectors,
                         dim=self.dim, version=_FORMAT_VERSION)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, store_dir / _SNAPSHOT_FILE)
        finally:
            Path(name).unlink(missing_ok=True)

    @classmethod
    def load(cls, store_dir: Path) -> "FeatureStore":
        store_dir = Path(store_dir)
        if (store_dir / _SNAPSHOT_FILE).is_file():
            with np.load(store_dir / _SNAPSHOT_FILE, allow_pickle=False) as data:
                store = cls(dim=int(data['dim']))
                store._ids = data['ids'].tolist()
                store._vectors = np.asarray(data['vectors'], dtype=np.float32)
                if store._vectors.shape != (len(store._ids), store.dim):
                    raise ValueError('corrupt feature snapshot')
                return store
        index = json.loads((store_dir / _INDEX_FILE).read_text(encoding="utf-8"))
        vectors = np.load(store_dir / _VECTORS_FILE)
        if len(index["ids"]) != len(vectors):
            raise ValueError(
                f"corrupt store: {len(index['ids'])} ids vs {len(vectors)} vectors"
            )
        store = cls(dim=int(index["dim"]))
        store._ids = [str(i) for i in index["ids"]]
        store._vectors = np.asarray(vectors, dtype=np.float32)
        return store

    @classmethod
    def exists(cls, store_dir: Path) -> bool:
        store_dir = Path(store_dir)
        return (store_dir / _SNAPSHOT_FILE).is_file() or (store_dir / _INDEX_FILE).is_file() and (
            store_dir / _VECTORS_FILE
        ).is_file()

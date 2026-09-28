"""Drop-in replacement for afterend/payment/utils/cuisine_detect.py.

The old module wrapped Baidu's custom-dishes API with three functions; this
one keeps their exact signatures so the Flask backend only needs to change
its import:

    from dish_recognition import legacy_api as cuisine_detect

Configuration via environment variables (all optional):
    DISH_STORE_DIR          where the feature store lives
                            (default: ./dish_feature_store)
    DISH_DETECTOR_WEIGHTS   YOLO weights path/name; "none" disables the
                            detector (default: the copy pinned in this repo)
    DISH_ACCEPT_THRESHOLD   min cosine similarity to accept a match

Note for the new backend: `detect()` preserves duplicates (two portions of
the same dish -> its id appears twice). Do not collapse them with an SQL
`IN (...)` lookup the way the old /admin/detect did — count them.

Threading contract: the four public functions below are safe to call from a
threaded WSGI server (the backend runs gunicorn with --threads 4). They are
serialized against each other — see `_pipeline_lock`. Note this covers a
single *process* only; running 2+ gunicorn workers is a correctness bug, not
a tuning choice, because each would hold its own copy of the feature store
and only one of them would see a newly enrolled dish.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List, Optional

from .config import RecognizerConfig
from .recognizer import DishRecognizer

_recognizer: Optional[DishRecognizer] = None

# Guards construction of the singleton only.
_build_lock = threading.Lock()

# Guards *use* of it. Must be a separate lock from _build_lock: the wrapped
# functions call get_recognizer(), which takes _build_lock, and a plain Lock
# is not reentrant. Reentrant here anyway so a future wrapper can nest.
#
# Why serialize at all — the recognizer is shared mutable state:
#   - enroll() does conflicts() -> add() -> save(); each is individually
#     locked inside FeatureStore, but the sequence is not atomic, so two
#     concurrent enrollments can interleave and report stale conflicts.
#   - ultralytics YOLO models are documented as not thread-safe; one shared
#     instance being predicted on from several threads is unsupported.
# Recognition is CPU-bound and holds the GIL for most of its work, so this
# costs little: threads exist here for the DB-bound endpoints, not for
# parallel inference.
_pipeline_lock = threading.RLock()


def _config_from_env() -> RecognizerConfig:
    config = RecognizerConfig(
        store_dir=Path(os.environ.get("DISH_STORE_DIR", "dish_feature_store"))
    )
    weights = os.environ.get("DISH_DETECTOR_WEIGHTS")
    if weights is not None:
        config.detector_weights = None if weights.lower() == "none" else weights
    accept = os.environ.get("DISH_ACCEPT_THRESHOLD")
    if accept is not None:
        config.accept_threshold = float(accept)
    margin = os.environ.get('DISH_AMBIGUITY_MARGIN')
    if margin is not None:
        config.ambiguity_margin = float(margin)
    config.__post_init__()
    return config


def status() -> dict:
    """Describe the recognizer *without* building it.

    Deliberately does not call get_recognizer(): a liveness probe must never
    be the thing that loads ResNet50, or a cheap health check turns into a
    multi-second request and trips the probe timeout on a cold container.

    `detector` is the class actually in use. Seeing FullImageDetector while
    weights are configured means YOLO could not load. Automatic tray
    recognition will reject requests; operators can enter dishes manually.
    """
    recognizer = _recognizer
    if recognizer is None:
        return {'loaded': False}
    return {
        'loaded': True,
        'detector': type(recognizer.detector).__name__,
        'dishes': len(recognizer.store.dish_ids),
        'vectors': len(recognizer.store),
    }


def get_recognizer() -> DishRecognizer:
    """Lazily built process-wide singleton (models load once)."""
    global _recognizer
    with _build_lock:
        if _recognizer is None:
            _recognizer = DishRecognizer(_config_from_env())
        return _recognizer


# --------------------------------------------------------------------------
# Legacy surface — same names/signatures as the Baidu-backed module.
# --------------------------------------------------------------------------

def store(filePath, c_id) -> dict:
    """Enroll dish `c_id` from the image at filePath.

    Returns the enrollment report as a dict; `conflicts` lists existing
    dishes the new one is hard to distinguish from (the old API had no
    such signal — callers may ignore it or surface a warning).
    """
    with _pipeline_lock:
        report = get_recognizer().enroll(str(c_id), [filePath])
    return report.to_dict()


def store_many(filePaths, c_id) -> dict:
    """Enroll dish `c_id` from several photos in one report.

    Multi-view enrollment (5-10 angles per dish) is the recommended path;
    conflicts are computed once against all new vectors together.
    """
    with _pipeline_lock:
        report = get_recognizer().enroll(str(c_id), list(filePaths))
    return report.to_dict()


def detect(filePath) -> List[int]:
    """Recognize dishes in the image; returns c_ids, duplicates preserved."""
    with _pipeline_lock:
        result = get_recognizer().recognize(filePath)
    ids: List[int] = []
    for dish_id in result.dish_ids():
        try:
            ids.append(int(dish_id))
        except ValueError:
            # Non-numeric ids can't be represented in the legacy int list;
            # skip rather than crash the checkout flow.
            continue
    return ids


def recognize(file_path) -> dict:
    """Checkout API: preserve every region, including unknown/ambiguous ones."""
    with _pipeline_lock:
        return get_recognizer().recognize(file_path).to_dict()


def preview(file_path):
    """Return normalized original and proposed enrollment crop (no mutation)."""
    from .embedder import load_image
    with _pipeline_lock:
        original = load_image(file_path)
        crop = get_recognizer()._enrollment_crop(original)
        return original, crop


def replace_samples(c_id, samples):
    """Rebuild one dish from (path, is_confirmed_crop) pairs.

    Build and persist a candidate store before replacing the live reference,
    so failed embedding or persistence leaves live recognition unchanged.
    Caller serializes image-file mutations for the same operation.
    """
    from .embedder import load_image
    from .feature_store import FeatureStore
    with _pipeline_lock:
        recognizer = get_recognizer()
        crops = [load_image(path) if confirmed else
                 recognizer._enrollment_crop(load_image(path))
                 for path, confirmed in samples]
        vectors = recognizer.embedder.embed_images(crops)
        conflicts = recognizer.store.conflicts(
            vectors, recognizer.config.conflict_threshold, exclude={str(c_id)}
        ) if len(vectors) else []
        # Clone under the store lock; all public recognition operations hold
        # _pipeline_lock, so readers never see the intermediate replacement.
        with recognizer.store._lock:
            candidate = FeatureStore(recognizer.store.dim)
            candidate._ids = list(recognizer.store._ids)
            candidate._vectors = recognizer.store._vectors.copy()
        candidate.remove(str(c_id))
        if len(vectors):
            candidate.add(str(c_id), vectors)
        candidate.save(recognizer.config.store_dir)
        recognizer.store = candidate
        return {'vectors_added': len(vectors), 'conflicts': [
            {'dish_id': c.dish_id, 'similarity': c.score} for c in conflicts]}


def delete(filePath) -> None:
    """Remove a dish by its enrollment image path.

    The old backend calls delete(f'static/cuisine/{c_id}.png'), so the
    dish id is recovered from the filename stem.
    """
    c_id = Path(filePath).stem
    with _pipeline_lock:
        get_recognizer().remove(c_id)

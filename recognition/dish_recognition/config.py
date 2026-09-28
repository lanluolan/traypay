from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_PACKAGED_WEIGHTS = Path(__file__).resolve().parent.parent / "weights" / "yolov8n.pt"


def _default_detector_weights() -> str:
    """The weights pinned in this repo, when they are there.

    The obvious default — the bare name "yolov8n.pt" — makes ultralytics
    download 6 MB into the *current working directory* the first time a
    detector is built. That bites anything not started by the backend (a
    maintenance script, the CLI, a test) even though a copy is sitting in
    the tree, and it means a container without outbound network cannot
    build a detector at all.

    Resolving to the packaged file keeps every entry point on the same
    weights. DISH_DETECTOR_WEIGHTS still overrides, and "none" still
    disables the detector.
    """
    return str(_PACKAGED_WEIGHTS) if _PACKAGED_WEIGHTS.is_file() else "yolov8n.pt"


@dataclass
class RecognizerConfig:
    """Tunable knobs for the recognition pipeline.

    Thresholds are cosine similarities in [0, 1] between L2-normalized
    ImageNet ResNet50 embeddings. Defaults are sane starting points but
    should be calibrated on real canteen photos (see recognition/README.md).
    """

    # Where the feature store persists (vectors.npy + index.json).
    store_dir: Path = field(default_factory=lambda: Path("dish_feature_store"))

    # A detected region counts as a known dish only if its best match
    # scores at least this. Below it the region is reported as unknown.
    accept_threshold: float = 0.60

    # Provisional value; calibrate on independent canteen photos.
    ambiguity_margin: float = 0.05

    # Enrolling a new dish warns about existing dishes at least this
    # similar. The dish is still enrolled; the caller decides what to do
    # (e.g. ask the operator for more distinctive photos).
    conflict_threshold: float = 0.80

    # Detector boxes are expanded by this fraction of their size before
    # cropping, so the embedder sees a little context around the dish.
    crop_pad_ratio: float = 0.04

    # Weights for the YOLO detector. Any ultralytics-loadable path or model
    # name works; a single-class "dish" model fine-tuned on canteen trays is
    # the intended production setup, pretrained COCO is a stopgap. None
    # disables YOLO and uses the whole image as one region.
    # Defaults to the copy pinned in this repo — see _default_detector_weights.
    detector_weights: Optional[str] = field(default_factory=_default_detector_weights)
    detector_conf: float = 0.35

    # "auto" picks cuda when available, else cpu.
    device: str = "auto"

    # During enrollment, crop to the highest-confidence detection instead
    # of embedding the full photo (falls back to the full photo when the
    # detector finds nothing).
    enroll_with_detector: bool = True

    def __post_init__(self):
        for name in ('accept_threshold', 'ambiguity_margin', 'conflict_threshold'):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f'{name} must be between 0 and 1')

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image

from .config import RecognizerConfig
from .detector import DishDetector, FullImageDetector, Region, default_detector
from .embedder import load_image
from .feature_store import FeatureStore, Match


class DetectorUnavailable(RuntimeError):
    pass


class NoDishesDetected(ValueError):
    pass


@dataclass(frozen=True)
class RegionMatch:
    """One detected region and what it matched to."""

    box: Tuple[int, int, int, int]
    detector_confidence: float
    dish_id: Optional[str]  # None => below accept_threshold (unknown dish)
    similarity: float
    runner_up: Optional[Match] = None
    status: str = 'accepted'
    candidates: List[Match] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "box": list(self.box),
            "detector_confidence": round(self.detector_confidence, 4),
            "dish_id": self.dish_id,
            "similarity": round(self.similarity, 4),
            "status": self.status,
            "candidates": [
                {'dish_id': c.dish_id, 'similarity': round(c.score, 4)}
                for c in self.candidates
            ],
            "runner_up": (
                {
                    "dish_id": self.runner_up.dish_id,
                    "similarity": round(self.runner_up.score, 4),
                }
                if self.runner_up
                else None
            ),
        }


@dataclass(frozen=True)
class RecognitionResult:
    matches: List[RegionMatch]
    image_width: int = 0
    image_height: int = 0

    def dish_ids(self) -> List[str]:
        """Matched ids, one per region — duplicates preserved on purpose:
        two portions of the same dish must be charged twice."""
        return [m.dish_id for m in self.matches if m.dish_id is not None]

    @property
    def unknown_count(self) -> int:
        return sum(1 for m in self.matches if m.dish_id is None)

    def to_dict(self) -> dict:
        return {
            "dish_ids": self.dish_ids(),
            "unknown_count": self.unknown_count,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "matches": [m.to_dict() for m in self.matches],
        }


@dataclass(frozen=True)
class EnrollmentReport:
    dish_id: str
    vectors_added: int
    conflicts: List[Match] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dish_id": self.dish_id,
            "vectors_added": self.vectors_added,
            "conflicts": [
                {"dish_id": c.dish_id, "similarity": round(c.score, 4)}
                for c in self.conflicts
            ],
        }


class DishRecognizer:
    """detect -> crop -> embed -> retrieve. Enrollment never touches weights.

    detector / embedder / store are injectable for testing; by default a
    YOLO (or full-image) detector and a frozen ResNet50 embedder are built,
    and the store is loaded from config.store_dir when it exists.
    """

    def __init__(
        self,
        config: Optional[RecognizerConfig] = None,
        detector: Optional[DishDetector] = None,
        embedder=None,
        store: Optional[FeatureStore] = None,
    ):
        self.config = config or RecognizerConfig()
        if embedder is None:
            from .embedder import ResNet50Embedder  # imports torch

            embedder = ResNet50Embedder(self.config.device)
        self.embedder = embedder
        self.detector = detector or default_detector(self.config)
        if store is None:
            if FeatureStore.exists(self.config.store_dir):
                store = FeatureStore.load(self.config.store_dir)
            else:
                store = FeatureStore(dim=self.embedder.dim)
        self.store = store

    # ------------------------------------------------------------ enrollment

    def enroll(
        self,
        dish_id,
        image_paths: Sequence,
        replace: bool = False,
        confirmed_crops: bool = False,
    ) -> EnrollmentReport:
        """Register a dish from one or (preferably) several photos.

        High similarity to an existing dish is reported as a conflict, not
        "fixed" by touching the model: the right response is more
        distinctive photos or distinctive tableware, decided by a human.
        """
        dish_id = str(dish_id)
        crops = [load_image(p) if confirmed_crops else self._enrollment_crop(load_image(p))
                 for p in image_paths]
        vectors = self.embedder.embed_images(crops)
        if len(vectors) == 0:
            raise ValueError("enroll needs at least one image")
        conflicts = self.store.conflicts(
            vectors, self.config.conflict_threshold, exclude={dish_id}
        )
        self.store.add(dish_id, vectors, replace=replace)
        self._save()
        return EnrollmentReport(dish_id, len(vectors), conflicts)

    def remove(self, dish_id) -> int:
        removed = self.store.remove(str(dish_id))
        if removed:
            self._save()
        return removed

    # ----------------------------------------------------------- recognition

    def recognize(self, image_path) -> RecognitionResult:
        image = load_image(image_path)
        if isinstance(self.detector, FullImageDetector):
            raise DetectorUnavailable('multi-dish detector is unavailable')
        try:
            regions = self.detector.detect(image)
        except Exception as exc:
            raise DetectorUnavailable('multi-dish detector failed') from exc
        if not regions:
            raise NoDishesDetected('no dishes detected; retake or enter manually')
        crops = [self._crop(image, r) for r in regions]
        vectors = self.embedder.embed_images(crops)

        matches: List[RegionMatch] = []
        for region, vector in zip(regions, vectors):
            ranked = self.store.search(vector, top_k=2)
            top = ranked[0] if ranked else None
            accepted = top is not None and top.score >= self.config.accept_threshold
            ambiguous = (accepted and len(ranked) > 1 and
                         top.score - ranked[1].score < self.config.ambiguity_margin)
            status = 'ambiguous' if ambiguous else ('accepted' if accepted else 'unknown')
            matches.append(
                RegionMatch(
                    box=(region.x1, region.y1, region.x2, region.y2),
                    detector_confidence=region.confidence,
                    dish_id=top.dish_id if accepted and not ambiguous else None,
                    similarity=top.score if top else 0.0,
                    runner_up=ranked[1] if len(ranked) > 1 else None,
                    status=status,
                    candidates=ranked,
                )
            )
        return RecognitionResult(matches, image.width, image.height)

    # -------------------------------------------------------------- internal

    def _enrollment_crop(self, image: Image.Image) -> Image.Image:
        if not self.config.enroll_with_detector:
            return image
        regions = self.detector.detect(image)
        if not regions:
            return image
        best = max(regions, key=lambda r: r.confidence)
        return self._crop(image, best)

    def _crop(self, image: Image.Image, region: Region) -> Image.Image:
        pad = self.config.crop_pad_ratio
        bw, bh = region.x2 - region.x1, region.y2 - region.y1
        px, py = bw * pad, bh * pad
        box = (
            max(0, int(region.x1 - px)),
            max(0, int(region.y1 - py)),
            min(image.width, int(region.x2 + px)),
            min(image.height, int(region.y2 + py)),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            return image
        return image.crop(box)

    def _save(self) -> None:
        self.store.save(Path(self.config.store_dir))

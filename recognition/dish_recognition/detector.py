from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Protocol

from PIL import Image

from .config import RecognizerConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Region:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    @classmethod
    def full_image(cls, image: Image.Image) -> "Region":
        return cls(0, 0, image.width, image.height, 1.0)


class DishDetector(Protocol):
    def detect(self, image: Image.Image) -> List[Region]: ...


class FullImageDetector:
    """Fallback detector: the whole photo is one region.

    Usable for single-dish enrollment close-ups. DishRecognizer rejects
    this detector for checkout: install ultralytics and provide YOLO weights.
    """

    def detect(self, image: Image.Image) -> List[Region]:
        return [Region.full_image(image)]


class YoloDishDetector:
    """Class-agnostic region proposals from a YOLO model.

    Intended for weights fine-tuned as a single-class "dish" detector on
    canteen tray photos. Pretrained COCO weights (e.g. "yolov8n.pt") work
    as a stopgap — bowls/cups on trays are detected reasonably — which is
    why detections are taken class-agnostically instead of filtering to
    specific COCO class ids.
    """

    def __init__(self, weights: str, conf: float = 0.35, device: str = "auto"):
        from ultralytics import YOLO  # lazy: optional dependency

        self._model = YOLO(weights)
        self.conf = conf
        self.device = None if device == "auto" else device

    def detect(self, image: Image.Image) -> List[Region]:
        # Pass the PIL image directly: ultralytics treats raw numpy arrays
        # as BGR (cv2 convention), which would silently swap channels.
        results = self._model.predict(
            image,
            conf=self.conf,
            agnostic_nms=True,
            device=self.device,
            verbose=False,
        )
        regions: List[Region] = []
        for r in results:
            if r.boxes is None:
                continue
            xyxy = r.boxes.xyxy.cpu().numpy()
            confs = r.boxes.conf.cpu().numpy()
            for (x1, y1, x2, y2), c in zip(xyxy, confs):
                regions.append(
                    Region(int(x1), int(y1), int(x2), int(y2), float(c))
                )
        regions.sort(key=lambda reg: -reg.confidence)
        return regions


def default_detector(config: RecognizerConfig) -> DishDetector:
    """YOLO when configured and usable, otherwise the full-image fallback.

    Keeps single-dish sample enrollment available. Checkout explicitly rejects
    FullImageDetector and tells the operator to enter the tray manually.
    """
    if not config.detector_weights:
        return FullImageDetector()

    try:
        return YoloDishDetector(
            config.detector_weights,
            conf=config.detector_conf,
            device=config.device,
        )
    except ImportError:
        # Installing without the [yolo] extra is a supported (if limited)
        # setup, so this one is expected rather than broken.
        logger.warning(
            "ultralytics is not installed; falling back to whole-image "
            "recognition (fine for single-dish photos, install "
            "ultralytics for multi-dish trays)."
        )
    except Exception:
        # Wrong path, corrupt checkpoint, no network for a lazy download,
        # torch/ultralytics version mismatch — none of these are ImportError,
        # so before this branch existed they all escaped and crashed the
        # recognizer at request time.
        logger.error(
            "Could not load YOLO from %r; only whole-image enrollment is "
            "available. Automatic tray recognition will be blocked.",
            config.detector_weights,
            exc_info=True,
        )
    return FullImageDetector()

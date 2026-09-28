"""Dish recognition via detection + feature retrieval.

Pipeline:  image -> DishDetector (region proposals) -> crop
                 -> Embedder (frozen ResNet50, 2048-d L2-normalized vector)
                 -> FeatureStore (cosine similarity search) -> dish ids

Enrollment appends vectors to the store and never mutates model weights.
"""

from .config import RecognizerConfig
from .feature_store import FeatureStore, Match
from .recognizer import (
    DishRecognizer,
    EnrollmentReport,
    RecognitionResult,
    RegionMatch,
)

__version__ = "0.1.0"

__all__ = [
    "RecognizerConfig",
    "FeatureStore",
    "Match",
    "DishRecognizer",
    "EnrollmentReport",
    "RecognitionResult",
    "RegionMatch",
    "__version__",
]

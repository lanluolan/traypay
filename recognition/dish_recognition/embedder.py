from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence

import numpy as np
from PIL import Image, ImageOps

# torch / torchvision are imported lazily inside ResNet50Embedder so the
# rest of the package (feature store, recognizer logic, tests with stub
# embedders) works without them installed.


def load_image(path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


class ResNet50Embedder:
    """Frozen ImageNet ResNet50 -> 2048-d L2-normalized embeddings.

    The classification head (fc) is replaced with identity but the global
    average pool is KEPT, so the descriptor is a bag of features rather than
    a spatial grid: *where* something sits inside the crop barely matters.
    Weights are never updated; enrollment is purely additive on the store.

    That tolerance is translation, NOT rotation. Conv filters are
    orientation-sensitive and averaging their responses does not undo that.
    Measured cosine against the unrotated embedding of a real photo:

        brightness +/-35%    0.98   lighting is essentially free
        horizontal mirror    0.88
        rotated 90 deg       0.69
        rotated 180 deg      0.47   *below* the 0.60 accept threshold
        25% tighter crop     0.63   framing matters as much as content

    (Measured on a strongly oriented scene; a round plated dish shot from
    above should degrade less. Re-measure on real canteen photos during
    threshold calibration.)

    Consequences for enrollment: shoot each dish from several orientations,
    do not spend shots on lighting, and keep framing consistent — the
    pipeline helps by cropping both enrollment and query images to detector
    boxes, so avoid close-ups so tight that the detector finds nothing and
    falls back to the whole frame.
    """

    dim = 2048

    def __init__(self, device: str = "auto"):
        import torch
        import torchvision

        self._torch = torch
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        weights = torchvision.models.ResNet50_Weights.IMAGENET1K_V2
        model = torchvision.models.resnet50(weights=weights)
        model.fc = torch.nn.Identity()
        model.eval()
        for p in model.parameters():
            p.requires_grad_(False)
        self._model = model.to(device)
        self._preprocess = weights.transforms()

    def embed_images(self, images: Sequence[Image.Image], batch_size: int = 16) -> np.ndarray:
        torch = self._torch
        out: List[np.ndarray] = []
        for start in range(0, len(images), batch_size):
            batch = images[start : start + batch_size]
            tensors = torch.stack(
                [self._preprocess(img.convert("RGB")) for img in batch]
            ).to(self.device)
            with torch.inference_mode():
                feats = self._model(tensors)
            out.append(feats.cpu().numpy().astype(np.float32))
        if not out:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = np.vstack(out)
        norms = np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        return vectors / norms

    def embed_files(self, paths: Iterable) -> np.ndarray:
        return self.embed_images([load_image(Path(p)) for p in paths])

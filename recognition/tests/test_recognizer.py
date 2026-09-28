"""End-to-end pipeline tests with stub detector/embedder — no torch needed.

The behaviour that actually costs money is pinned here: one result per
detected region with duplicates preserved (two portions of the same dish
must be charged twice), and anything below accept_threshold reported as
unknown rather than guessed.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from dish_recognition.config import RecognizerConfig
from dish_recognition.detector import Region
from dish_recognition.feature_store import FeatureStore
from dish_recognition.recognizer import DishRecognizer, DetectorUnavailable, NoDishesDetected
from dish_recognition.detector import FullImageDetector


DIM = 8


def vec(*components):
    v = np.zeros(DIM, dtype=np.float32)
    for i, value in enumerate(components):
        v[i] = value
    return v


class StubDetector:
    """Returns a fixed set of boxes, ignoring the image."""

    def __init__(self, regions):
        self.regions = regions
        self.calls = 0

    def detect(self, image):
        self.calls += 1
        return list(self.regions)


class StubEmbedder:
    """Maps each crop to a preset vector, in call order."""

    dim = DIM

    def __init__(self, vectors):
        self.vectors = list(vectors)
        self.seen_sizes = []

    def embed_images(self, images, batch_size=16):
        self.seen_sizes.extend(img.size for img in images)
        out = [self.vectors.pop(0) for _ in images]
        if not out:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.stack(out)


def write_image(path, size=(400, 300)):
    Image.new("RGB", size, (128, 128, 128)).save(path)
    return path


class RecognizeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.image = write_image(self.dir / "tray.png")
        self.store = FeatureStore(dim=DIM)
        self.store.add("1", vec(1.0))
        self.store.add("2", vec(0.0, 1.0))
        self.config = RecognizerConfig(store_dir=self.dir / "store")

    def tearDown(self):
        self.tmp.cleanup()

    def _recognizer(self, regions, vectors):
        return DishRecognizer(
            config=self.config,
            detector=StubDetector(regions),
            embedder=StubEmbedder(vectors),
            store=self.store,
        )

    def test_two_portions_of_one_dish_are_not_deduped(self):
        # The whole point: /admin/detect used to collapse these with
        # `IN (...)` and undercharge the tray.
        regions = [Region(0, 0, 100, 100, 0.9), Region(100, 0, 200, 100, 0.8)]
        rec = self._recognizer(regions, [vec(1.0), vec(1.0)])
        result = rec.recognize(self.image)
        self.assertEqual(result.dish_ids(), ["1", "1"])
        self.assertEqual(result.unknown_count, 0)

    def test_below_threshold_is_unknown_not_a_guess(self):
        regions = [Region(0, 0, 100, 100, 0.9)]
        rec = self._recognizer(regions, [vec(0.5, 0.5, 0.7071)])  # ~0.5 cosine
        result = rec.recognize(self.image)
        self.assertEqual(result.dish_ids(), [])
        self.assertEqual(result.unknown_count, 1)
        self.assertIsNone(result.matches[0].dish_id)

    def test_mixed_tray_reports_knowns_and_unknowns(self):
        regions = [
            Region(0, 0, 100, 100, 0.9),
            Region(100, 0, 200, 100, 0.8),
            Region(200, 0, 300, 100, 0.7),
        ]
        rec = self._recognizer(
            regions, [vec(1.0), vec(0.0, 1.0), vec(0.0, 0.0, 1.0)]
        )
        result = rec.recognize(self.image)
        self.assertEqual(result.dish_ids(), ["1", "2"])
        self.assertEqual(result.unknown_count, 1)

    def test_no_detections_requires_operator_action(self):
        rec = self._recognizer([], [vec(1.0)])
        with self.assertRaises(NoDishesDetected):
            rec.recognize(self.image)

    def test_full_image_detector_cannot_checkout(self):
        rec = self._recognizer([], [vec(1.0)])
        rec.detector = FullImageDetector()
        with self.assertRaises(DetectorUnavailable):
            rec.recognize(self.image)

    def test_close_candidates_require_confirmation_even_above_threshold(self):
        rec = self._recognizer([Region(0, 0, 100, 100, .9)], [vec(.71, .70)])
        result = rec.recognize(self.image)
        self.assertEqual(result.matches[0].status, 'ambiguous')
        self.assertIsNone(result.matches[0].dish_id)
        self.assertEqual(len(result.matches[0].candidates), 2)
        self.assertEqual(result.dish_ids(), [])
        self.assertEqual((result.image_width, result.image_height), (400, 300))

    def test_margin_is_configurable(self):
        rec = self._recognizer([Region(0, 0, 100, 100, .9)], [vec(.71, .70)])
        rec.config.ambiguity_margin = 0
        self.assertEqual(rec.recognize(self.image).matches[0].status, 'accepted')

    def test_runner_up_is_reported(self):
        regions = [Region(0, 0, 100, 100, 0.9)]
        rec = self._recognizer(regions, [vec(0.9, 0.4)])
        result = rec.recognize(self.image)
        match = result.matches[0]
        self.assertEqual(match.dish_id, "1")
        self.assertIsNotNone(match.runner_up)
        self.assertEqual(match.runner_up.dish_id, "2")

    def test_to_dict_is_jsonifiable_shape(self):
        regions = [Region(0, 0, 100, 100, 0.9)]
        rec = self._recognizer(regions, [vec(1.0)])
        payload = rec.recognize(self.image).to_dict()
        self.assertEqual(
            sorted(payload), ["dish_ids", "image_height", "image_width", "matches", "unknown_count"]
        )
        self.assertEqual(
            sorted(payload["matches"][0]),
            ["box", "candidates", "detector_confidence", "dish_id", "runner_up", "similarity", "status"],
        )

    def test_crop_padding_expands_the_box(self):
        # crop_pad_ratio gives the embedder a little context around the dish.
        regions = [Region(100, 100, 200, 200, 0.9)]
        embedder = StubEmbedder([vec(1.0)])
        rec = DishRecognizer(
            config=RecognizerConfig(
                store_dir=self.dir / "store", crop_pad_ratio=0.10
            ),
            detector=StubDetector(regions),
            embedder=embedder,
            store=self.store,
        )
        rec.recognize(self.image)
        self.assertEqual(embedder.seen_sizes, [(120, 120)])


class EnrollTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.images = [
            write_image(self.dir / "a.png"),
            write_image(self.dir / "b.png"),
        ]
        self.config = RecognizerConfig(store_dir=self.dir / "store")

    def tearDown(self):
        self.tmp.cleanup()

    def _recognizer(self, vectors, store=None):
        return DishRecognizer(
            config=self.config,
            detector=StubDetector([Region(0, 0, 100, 100, 0.9)]),
            embedder=StubEmbedder(vectors),
            store=store if store is not None else FeatureStore(dim=DIM),
        )

    def test_multi_view_adds_one_vector_per_photo(self):
        rec = self._recognizer([vec(1.0), vec(0.9, 0.1)])
        report = rec.enroll("7", self.images)
        self.assertEqual(report.vectors_added, 2)
        self.assertEqual(rec.store.counts, {"7": 2})

    def test_confirmed_crop_is_not_detected_or_cropped_again(self):
        rec = self._recognizer([vec(1.0)])
        rec.enroll('7', self.images[:1], confirmed_crops=True)
        self.assertEqual(rec.detector.calls, 0)
        self.assertEqual(rec.embedder.seen_sizes, [(400, 300)])

    def test_enroll_persists_the_store(self):
        rec = self._recognizer([vec(1.0)])
        rec.enroll("7", self.images[:1])
        self.assertTrue(FeatureStore.exists(self.config.store_dir))
        reloaded = FeatureStore.load(self.config.store_dir)
        self.assertEqual(reloaded.counts, {"7": 1})

    def test_conflict_is_reported_but_dish_is_still_enrolled(self):
        # The right response to two look-alike dishes is more distinctive
        # photos decided by a human, never a weight update.
        store = FeatureStore(dim=DIM)
        store.add("1", vec(1.0))
        rec = self._recognizer([vec(0.99, 0.14)], store=store)
        report = rec.enroll("7", self.images[:1])
        self.assertEqual([c.dish_id for c in report.conflicts], ["1"])
        self.assertIn("7", rec.store.dish_ids)

    def test_reenroll_does_not_conflict_with_itself(self):
        store = FeatureStore(dim=DIM)
        store.add("7", vec(1.0))
        rec = self._recognizer([vec(1.0)], store=store)
        report = rec.enroll("7", self.images[:1])
        self.assertEqual(report.conflicts, [])

    def test_replace_drops_previous_vectors(self):
        store = FeatureStore(dim=DIM)
        store.add("7", np.stack([vec(1.0), vec(0.0, 1.0)]))
        rec = self._recognizer([vec(0.0, 0.0, 1.0)], store=store)
        rec.enroll("7", self.images[:1], replace=True)
        self.assertEqual(rec.store.counts, {"7": 1})

    def test_enroll_without_images_raises(self):
        rec = self._recognizer([])
        with self.assertRaises(ValueError):
            rec.enroll("7", [])

    def test_remove_persists_and_is_idempotent(self):
        rec = self._recognizer([vec(1.0)])
        rec.enroll("7", self.images[:1])
        self.assertEqual(rec.remove("7"), 1)
        self.assertEqual(rec.remove("7"), 0)
        self.assertEqual(FeatureStore.load(self.config.store_dir).counts, {})


if __name__ == "__main__":
    unittest.main()

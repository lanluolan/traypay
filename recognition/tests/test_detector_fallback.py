"""default_detector() must never raise.

DishRecognizer is built lazily inside the first request, so an exception
escaping here surfaces as a failed /admin/detect and gets reported to the
operator as "invalid image" — who then retakes the photo forever without
ever learning that the weights path is wrong.
"""

import unittest
from unittest import mock

from PIL import Image

from dish_recognition.config import RecognizerConfig
from dish_recognition.detector import (
    FullImageDetector,
    Region,
    default_detector,
)


class FullImageDetectorTest(unittest.TestCase):
    def test_returns_the_whole_image_as_one_region(self):
        image = Image.new("RGB", (640, 480))
        regions = FullImageDetector().detect(image)
        self.assertEqual(len(regions), 1)
        self.assertEqual(
            (regions[0].x1, regions[0].y1, regions[0].x2, regions[0].y2),
            (0, 0, 640, 480),
        )
        self.assertEqual(regions[0].confidence, 1.0)

    def test_region_full_image_helper(self):
        image = Image.new("RGB", (100, 50))
        self.assertEqual(Region.full_image(image), Region(0, 0, 100, 50, 1.0))


class DefaultDetectorFallbackTest(unittest.TestCase):
    def test_weights_none_uses_full_image(self):
        config = RecognizerConfig(detector_weights=None)
        self.assertIsInstance(default_detector(config), FullImageDetector)

    def test_missing_ultralytics_degrades_quietly(self):
        # ImportError is the supported "installed without the [yolo] extra"
        # case, so it must be a warning, not an error.
        config = RecognizerConfig(detector_weights="yolov8n.pt")
        with mock.patch(
            "dish_recognition.detector.YoloDishDetector",
            side_effect=ImportError("no ultralytics"),
        ):
            with self.assertLogs("dish_recognition.detector", "WARNING") as logs:
                detector = default_detector(config)
        self.assertIsInstance(detector, FullImageDetector)
        self.assertNotIn("ERROR", logs.output[0])

    def test_broken_weights_degrade_but_log_at_error(self):
        # A wrong path / corrupt checkpoint / version mismatch is a
        # misconfiguration that blocks automatic multi-dish recognition.
        config = RecognizerConfig(detector_weights="/no/such/weights.pt")
        with mock.patch(
            "dish_recognition.detector.YoloDishDetector",
            side_effect=RuntimeError("corrupt checkpoint"),
        ):
            with self.assertLogs("dish_recognition.detector", "ERROR") as logs:
                detector = default_detector(config)
        self.assertIsInstance(detector, FullImageDetector)
        self.assertIn("/no/such/weights.pt", logs.output[0])

    def test_working_detector_is_returned_unchanged(self):
        sentinel = object()
        config = RecognizerConfig(detector_weights="yolov8n.pt")
        with mock.patch(
            "dish_recognition.detector.YoloDishDetector", return_value=sentinel
        ):
            self.assertIs(default_detector(config), sentinel)


if __name__ == "__main__":
    unittest.main()

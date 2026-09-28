"""Contract checks for the real ResNet50 embedder.

Self-skips when torch/torchvision are absent, which is how CI gets away with
installing only numpy and Pillow. The first run downloads ~100 MB of
ImageNet weights into ~/.cache/torch.
"""

import unittest

import numpy as np
from PIL import Image

try:
    import torch  # noqa: F401
    import torchvision  # noqa: F401

    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False


@unittest.skipUnless(HAVE_TORCH, "torch/torchvision not installed")
class ResNet50EmbedderSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dish_recognition.embedder import ResNet50Embedder

        cls.embedder = ResNet50Embedder(device="cpu")

    def _image(self, color=(200, 60, 60), size=(320, 240)):
        return Image.new("RGB", size, color)

    def test_shape_and_dtype(self):
        vectors = self.embedder.embed_images([self._image(), self._image()])
        self.assertEqual(vectors.shape, (2, 2048))
        self.assertEqual(vectors.dtype, np.float32)

    def test_output_is_l2_normalized(self):
        # FeatureStore treats a dot product as a cosine similarity, so the
        # embedder owes it unit vectors.
        vectors = self.embedder.embed_images([self._image()])
        np.testing.assert_allclose(
            np.linalg.norm(vectors, axis=1), 1.0, rtol=1e-5
        )

    def test_deterministic(self):
        a = self.embedder.embed_images([self._image()])
        b = self.embedder.embed_images([self._image()])
        np.testing.assert_allclose(a, b, atol=1e-6)

    def test_empty_input_returns_empty_matrix(self):
        vectors = self.embedder.embed_images([])
        self.assertEqual(vectors.shape, (0, 2048))

    def test_batching_matches_single_pass(self):
        images = [self._image((i * 40, 60, 60)) for i in range(5)]
        batched = self.embedder.embed_images(images, batch_size=2)
        single = self.embedder.embed_images(images, batch_size=16)
        np.testing.assert_allclose(batched, single, atol=1e-5)

    def test_different_images_are_not_identical(self):
        a = self.embedder.embed_images([self._image((220, 40, 40))])
        b = self.embedder.embed_images([self._image((40, 40, 220))])
        self.assertLess((a @ b.T).item(), 0.999)

    def test_declared_dim_matches_output(self):
        from dish_recognition.embedder import ResNet50Embedder

        self.assertEqual(
            ResNet50Embedder.dim, self.embedder.embed_images([self._image()]).shape[1]
        )


if __name__ == "__main__":
    unittest.main()

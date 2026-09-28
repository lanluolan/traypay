import tempfile
import unittest
import json
from unittest import mock
from pathlib import Path

import numpy as np

from dish_recognition.feature_store import FeatureStore


def vec(*components, dim=8):
    v = np.zeros(dim, dtype=np.float32)
    for i, value in enumerate(components):
        v[i] = value
    return v


class FeatureStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = FeatureStore(dim=8)
        self.e1 = vec(1.0)
        self.e2 = vec(0.0, 1.0)
        self.e3 = vec(0.0, 0.0, 1.0)

    def test_add_and_search_ranks_by_cosine(self):
        self.store.add("1", self.e1)
        self.store.add("2", self.e2)
        matches = self.store.search(vec(0.9, 0.1))
        self.assertEqual(matches[0].dish_id, "1")
        self.assertGreater(matches[0].score, matches[1].score)
        self.assertAlmostEqual(matches[0].score, 0.9938, places=3)

    def test_vectors_are_normalized_on_add_and_query(self):
        self.store.add("1", self.e1 * 47.0)  # unnormalized input
        matches = self.store.search(self.e1 * 0.001)
        self.assertAlmostEqual(matches[0].score, 1.0, places=5)

    def test_multi_view_uses_max_over_dish_vectors(self):
        self.store.add("1", np.stack([self.e1, self.e2]))  # two views
        self.store.add("2", self.e3)
        matches = self.store.search(self.e2)
        self.assertEqual(matches[0].dish_id, "1")
        self.assertAlmostEqual(matches[0].score, 1.0, places=5)

    def test_search_empty_store(self):
        self.assertEqual(self.store.search(self.e1), [])

    def test_remove(self):
        self.store.add("1", np.stack([self.e1, self.e2]))
        self.store.add("2", self.e3)
        self.assertEqual(self.store.remove("1"), 2)
        self.assertEqual(self.store.remove("1"), 0)
        self.assertEqual(self.store.dish_ids, ["2"])
        self.assertEqual(len(self.store), 1)

    def test_replace(self):
        self.store.add("1", self.e1)
        self.store.add("1", self.e2, replace=True)
        matches = self.store.search(self.e1)
        self.assertAlmostEqual(matches[0].score, 0.0, places=5)
        self.assertEqual(self.store.counts, {"1": 1})

    def test_conflicts_detects_similar_dish(self):
        self.store.add("1", self.e1)
        self.store.add("2", self.e3)
        near_e1 = vec(0.95, 0.05)
        hits = self.store.conflicts(near_e1[None, :], threshold=0.8)
        self.assertEqual([h.dish_id for h in hits], ["1"])

    def test_conflicts_excludes_self_on_reenroll(self):
        self.store.add("1", self.e1)
        hits = self.store.conflicts(self.e1[None, :], threshold=0.8, exclude={"1"})
        self.assertEqual(hits, [])

    def test_conflicts_below_threshold_empty(self):
        self.store.add("1", self.e1)
        hits = self.store.conflicts(self.e3[None, :], threshold=0.8)
        self.assertEqual(hits, [])

    def test_dim_mismatch_raises(self):
        with self.assertRaises(ValueError):
            self.store.add("1", np.ones(5, dtype=np.float32))

    def test_save_load_roundtrip(self):
        self.store.add("1", np.stack([self.e1, self.e2]))
        self.store.add("2", self.e3)
        with tempfile.TemporaryDirectory() as tmp:
            self.store.save(Path(tmp))
            self.assertTrue(FeatureStore.exists(Path(tmp)))
            loaded = FeatureStore.load(Path(tmp))
        self.assertEqual(loaded.counts, {"1": 2, "2": 1})
        self.assertEqual(loaded.search(self.e3)[0].dish_id, "2")

    def test_save_leaves_no_temp_files(self):
        # save() writes .tmp then os.replace()s. A leftover .tmp would mean
        # the atomic swap did not happen and a crash could strand a
        # half-written store.
        self.store.add("1", self.e1)
        with tempfile.TemporaryDirectory() as tmp:
            self.store.save(Path(tmp))
            leftovers = list(Path(tmp).glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_exists_false_for_missing_dir(self):
        self.assertFalse(FeatureStore.exists(Path("no/such/dir")))

    def test_legacy_store_is_readable_and_migrates_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.json').write_text(json.dumps({'dim': 8, 'ids': ['1']}))
            np.save(root / 'vectors.npy', self.e1[None, :])
            store = FeatureStore.load(root)
            store.add('2', self.e2)
            store.save(root)
            self.assertEqual(FeatureStore.load(root).counts, {'1': 1, '2': 1})

    def test_failed_snapshot_replace_preserves_previous_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.store.add('1', self.e1)
            self.store.save(root)
            self.store.add('2', self.e2)
            with mock.patch('dish_recognition.feature_store.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    self.store.save(root)
            self.assertEqual(FeatureStore.load(root).counts, {'1': 1})
            self.assertEqual(list(root.glob('*.tmp')), [])


if __name__ == "__main__":
    unittest.main()

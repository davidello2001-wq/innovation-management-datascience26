import unittest
from project.src.policy_metrics import binary_metrics


class PolicyMetricsTests(unittest.TestCase):
    def test_reported_hybrid_counts(self):
        result = binary_metrics([1] * 156 + [0] * 224,
                                [1] * 138 + [0] * 18 + [1] * 78 + [0] * 146)
        self.assertEqual((result['tp'], result['fp'], result['fn'], result['tn']),
                         (138, 78, 18, 146))
        self.assertAlmostEqual(result['f1'], 276 / 372)

    def test_removing_core_can_lose_positives_and_remove_negatives(self):
        before = binary_metrics([1, 0, 1, 0], [1, 1, 1, 0])
        after = binary_metrics([1, 0, 1, 0], [0, 0, 1, 0])
        self.assertEqual(after['fn'] - before['fn'], 1)
        self.assertEqual(before['fp'] - after['fp'], 1)

    def test_length_mismatch(self):
        with self.assertRaises(ValueError):
            binary_metrics([1], [])

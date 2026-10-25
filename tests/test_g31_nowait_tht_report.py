"""Paired posthoc summaries must preserve population identity and censoring."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.experiments.g31_no_wait.tht_report import paired_summary


def arm(name, values):
    return dict(id=name, cell="map2_1x", canonical_sha256="same", horizon=100,
                comparison_population_complete=True, business_values=values)


class PairedReportTests(unittest.TestCase):
    def test_lower_network_does_not_hide_larger_retry_hold(self):
        result = paired_summary(arm("g31", {"a": (5, 100, 105)}), arm("hca", {"a": (10, 0, 10)}))
        self.assertTrue(result["comparable"])
        self.assertEqual(result["network_elapsed"]["mean_difference_seconds"], -5)
        self.assertEqual(result["canonical_elapsed"]["mean_difference_seconds"], 95)

    def test_incomplete_population_is_not_paired(self):
        a, b = arm("a", {}), arm("b", {})
        a["comparison_population_complete"] = False
        self.assertFalse(paired_summary(a, b)["comparable"])

    def test_population_or_horizon_mismatch_rejected(self):
        a, b = arm("a", {"a": (1, 1, 2)}), arm("b", {"b": (1, 1, 2)})
        self.assertFalse(paired_summary(a, b)["comparable"])
        b["horizon"] = 101
        self.assertIn("different_horizon", paired_summary(a, b)["reasons"])


if __name__ == "__main__":
    unittest.main()

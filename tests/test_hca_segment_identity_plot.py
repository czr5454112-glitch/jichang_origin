"""Synthetic checks for new-HCA group qualification and scientific figures."""
from __future__ import annotations

import unittest

from scripts.eval import plot_hca_segment_identity_campaign as plot
from tests.test_hca_segment_identity_report import synthetic_rows


class HcaPlotContractTest(unittest.TestCase):
    def test_new_hca_unfinished_seed_suppresses_all_tht_but_keeps_th(self):
        groups = plot.summarize(plot.report.validate_cells(synthetic_rows()))
        value = next(g for g in groups if (g["map"], g["load_factor"], g["method"]) == ("nanning", 1.75, plot.METHODS[2]))
        self.assertEqual(value["THT_status"], "NA_INCOMPLETE_RAW_POPULATION")
        self.assertEqual(value["statistics"]["THT_mean"]["seed_values"], [])
        self.assertEqual(len(value["statistics"]["TH"]["seed_values"]), 10)
        for value in groups:
            if value["load_factor"] == 2:
                self.assertEqual(value["THT_status"], "NA_2X_PROTOCOL")
                self.assertIsNone(value["statistics"]["THT_max"]["mean_across_seeds"])

    def test_partial_seed_group_does_not_plot_subset_estimate(self):
        rows = synthetic_rows()[1:]
        value = plot.summarize(plot.report.validate_cells(rows, allow_partial=True))[0]
        self.assertEqual(value["observed_seed_count"], 9)
        self.assertEqual(value["TH_status"], "NA_MISSING_FROZEN_SEEDS")
        self.assertIsNone(value["statistics"]["TH"]["mean_across_seeds"])

    def test_old_hca_is_absent_from_new_plot_methods(self):
        self.assertNotIn("FENG_NATIVE_HCA", plot.METHODS)
        self.assertEqual(plot.METHODS[2], "HCA_SEGMENT_IDENTITY_V1")
        self.assertEqual(plot.LABELS[plot.METHODS[2]], "HCA identity repair (new)")


if __name__ == "__main__":
    unittest.main()

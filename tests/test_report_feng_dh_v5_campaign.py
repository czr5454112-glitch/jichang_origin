"""Report qualification and signed-comparison checks using synthetic statistics."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.eval import report_feng_dh_v5_campaign as report


class ReportContractTest(unittest.TestCase):
    def group_rows(self):
        return [{"seed": seed, "full_population_complete": i != 9,
            "TH_completed_raw_bags": 100 if i != 9 else 99, "completion_rate": 1 if i != 9 else .99,
            **{f"tht_scheduled_release_{s}_seconds": 10 if i != 9 else None for s in report.STATS}}
            for i, seed in enumerate(report.external.SEEDS)]

    def test_incomplete_population_and_2x_never_report_timing(self):
        rows = self.group_rows()
        group = report.completion_group(rows, load=1.75)
        self.assertEqual(group["TH_mean"], 99.9)
        self.assertEqual(group["complete_seeds"], 9)
        self.assertEqual(group["THT"], dict.fromkeys(report.STATS))
        self.assertEqual(report.completion_group(rows, load=2)["THT_status"], "2×协议")
        with self.assertRaisesRegex(ValueError, "all ten"):
            report.completion_group(rows[:-1], load=1.75)

    def test_adverse_and_tied_results_keep_sign_and_original_unit_ci(self):
        self.assertEqual(report.improvement_percent(100, 110, higher_is_better=False), -10)
        self.assertEqual(report.improvement_percent(100, 90, higher_is_better=True), -10)
        self.assertEqual(report.improvement_percent(100, 100, higher_is_better=False), 0)
        pair = {"status": "COMPLETE", "baseline_mean": 100, "reference_mean": 110,
            "mean_delta_reference_minus_baseline": 10, "bootstrap_ci_low": 8,
            "bootstrap_ci_high": 12, "reference_win_count": 0, "tie_count": 2, "reference_loss_count": 8}
        self.assertEqual(report.comparison_cells(pair, metric="tht_scheduled_release_mean_seconds"),
                         ["-10.00%", "+10.00", "[+8.00, +12.00]", "0/2/8"])

    def test_partial_matrix_cannot_be_reported_as_final(self):
        with self.assertRaisesRegex(ValueError, "all 180"):
            report.validate_final_manifest({"status": "INCOMPLETE", "expected_cells": 180, "observed_cells": 125}, {}, Path("unused"))

    def test_historical_percentages_are_derived_from_separate_audit(self):
        value = report.read_json(report.HISTORICAL)
        self.assertTrue(value["pass"])
        for stat in report.STATS:
            summaries = value["summaries_seconds"]
            actual = report.improvement_percent(summaries["V5_DH"][stat], summaries["G31"][stat], higher_is_better=False)
            self.assertAlmostEqual(actual, value["G31_reduction_percent"]["V5_DH"][stat], places=9)

    def test_accounting_flags_limit_headline_scope_without_changing_pairs(self):
        notes = report.load_control_notes(report.CONTROL_NOTES)
        self.assertEqual(notes["affected_cell_count"], 43)
        self.assertEqual(len(notes["_affected_groups"]), 5)
        pairs = {}
        for map_name in report.external.MAPS:
            for load in report.external.LOAD_FACTORS:
                for baseline in report.METHODS[1:]:
                    value = {"map": map_name, "load_factor": load, "baseline": baseline,
                        "reference": report.METHODS[0], "metric": "completed_raw_bag_count", "status": "COMPLETE"}
                    pairs[report.pair_key(value)] = value
        original = [dict(p) for p in pairs.values()]
        selected, excluded = report.headline_pairs(pairs, "completed_raw_bag_count", notes["_affected_groups"])
        self.assertEqual(excluded, 5)
        self.assertEqual(sum(p["baseline"] == report.METHODS[1] for p in selected), 6)
        hca = [p for p in selected if p["baseline"] == report.METHODS[2]]
        self.assertEqual([(p["map"], p["load_factor"]) for p in hca], [("map2", 1.0)])
        self.assertEqual(list(pairs.values()), original)

    def test_missing_interpretation_does_not_create_a_simulation_gate(self):
        self.assertIsNone(report.load_control_notes(Path("build/nonexistent_optional_control_notes.json")))


if __name__ == "__main__":
    unittest.main()

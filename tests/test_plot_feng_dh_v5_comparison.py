"""Synthetic scientific-display contract checks; no simulation or measured cells."""
from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest

from scripts.eval import plot_feng_dh_v5_comparison as plot


def synthetic_rows():
    rows = []
    for map_name in plot.external.MAPS:
        for load in plot.external.LOAD_FACTORS:
            for i, seed in enumerate(plot.external.SEEDS):
                for j, method in enumerate(plot.METHODS):
                    raw = plot.external.EXPECTED_POPULATIONS[load][0]
                    incomplete = map_name == "nanning" and load == 1.75 and method == plot.METHODS[1] and i == 9
                    completed = raw - 1 if incomplete else raw
                    value = {"map": map_name, "load_factor": load, "seed": seed, "method": method,
                        "fixed_horizon_seconds": plot.external.FIXED_HORIZON_SECONDS,
                        "primary_timing_definition": "SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_COMMON_CANONICAL_SCHEDULED_RELEASE",
                        "TH_definition": "COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259",
                        "historical_shared_D": False, "raw_bag_count": raw,
                        "full_population_complete": not incomplete, "TH_completed_raw_bags": completed,
                        "completed_raw_bag_count": completed, "unfinished_raw_bag_count": raw - completed,
                        "source_sha256": plot.SOURCE_SHA if method == plot.METHODS[1] else "",
                        "class_sha256": plot.CLASS_SHA if method == plot.METHODS[1] else "",
                        "workload_identity_sha256": f"SYNTHETIC-{map_name}-{load}-{seed}",
                        "formal_timing_status": "FULL_POPULATION_RAW_BAG_TIMING" if load != 2 and not incomplete else "NOT_ELIGIBLE"}
                    for stat, base in (("min", 12), ("mean", 150), ("max", 700)):
                        value[f"tht_scheduled_release_{stat}_seconds"] = None if load == 2 or incomplete else base + (i + 2 * j) * 1.5 * load
                    rows.append(value)
    return rows


def write_rows(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class PlotContractTest(unittest.TestCase):
    def parse(self, rows: list, *, partial: bool = False):
        with tempfile.TemporaryDirectory(dir=plot.ROOT / "build", prefix="feng_v5_plot_test_") as directory:
            path = Path(directory) / "synthetic.csv"
            write_rows(path, rows)
            return plot.load_cells(path, allow_partial=partial)

    def test_one_unfinished_seed_suppresses_group_tht_but_preserves_th(self):
        groups = plot.summarize(self.parse(synthetic_rows()))
        group = next(g for g in groups if (g["map"], g["load_factor"], g["method"]) == ("nanning", 1.75, plot.METHODS[1]))
        self.assertEqual(group["THT_status"], "NA_INCOMPLETE_RAW_POPULATION")
        self.assertEqual(group["statistics"]["THT_mean"]["seed_values"], [])
        self.assertIsNone(group["statistics"]["THT_mean"]["mean_across_seeds"])
        self.assertEqual(len(group["statistics"]["TH"]["seed_values"]), 10)
        self.assertEqual(group["statistics"]["TH"]["seed_range_high"] - group["statistics"]["TH"]["seed_range_low"], 1)
        for item in groups:
            if item["load_factor"] == 2:
                self.assertEqual(item["THT_status"], "NA_2X_PROTOCOL")
                self.assertIsNone(item["statistics"]["THT_max"]["mean_across_seeds"])
                self.assertEqual(len(item["statistics"]["TH"]["seed_values"]), 10)

    def test_missing_seed_never_generates_available_subset_mean(self):
        rows = synthetic_rows()[1:]
        with self.assertRaisesRegex(ValueError, "all 180"):
            self.parse(rows)
        group = plot.summarize(self.parse(rows, partial=True))[0]
        self.assertEqual(group["observed_seed_count"], 9)
        self.assertEqual(group["THT_status"], "NA_MISSING_FROZEN_SEEDS")
        self.assertIsNone(group["statistics"]["TH"]["mean_across_seeds"])

    def test_forbidden_2x_value_or_duplicate_seed_is_rejected(self):
        rows = synthetic_rows()
        row = next(r for r in rows if r["load_factor"] == 2)
        row["tht_scheduled_release_mean_seconds"] = 0
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.parse(rows)
        rows = synthetic_rows()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.parse(rows + [rows[0]])

    def test_control_accounting_annotation_keeps_observation_statistics(self):
        indexed = self.parse(synthetic_rows())
        before = plot.summarize(indexed)
        audit = plot.load_control_audit(plot.CONTROL_NOTES)
        self.assertEqual((audit["affected_cell_count"], audit["audited_cell_count"]), (43, 60))
        self.assertEqual(audit["sha256"], plot.sha(plot.CONTROL_NOTES))
        self.assertEqual(before, plot.summarize(indexed))


if __name__ == "__main__":
    unittest.main()

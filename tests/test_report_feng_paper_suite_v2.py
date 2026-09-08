"""Explicitly synthetic boundaries for the reduced 480+96 reporting scope."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from scripts.eval import report_feng_paper_suite_v2 as report


def synthetic_rows():
    rows = []
    for index, coordinate in enumerate(sorted(report.expected_coordinates())):
        row = dict(zip((*report.COORD, "method"), coordinate))
        row.update(cell_id=f"SYNTHETIC_NOT_AN_EXPERIMENT_{index}", cell_state="COMPLETE",
                   input_signature_sha256="SYNTHETIC_SHARED_INPUT", full_population_complete=True,
                   TH=100, completion_rate=1, success_std_rate=.8, success_paper_literal_rate=.2,
                   native_wall_seconds=1, affected_edge_count=0 if row["family"] == "base" else 1)
        for clock, value in (("D", 10 if row["method"] == report.G31 else 8),
                             ("native", 4 if row["method"] == report.G31 else 6)):
            for stat, multiplier in (("min", .5), ("mean", 1), ("max", 2)):
                row[f"tht_{clock}_{stat}_seconds"] = value * multiplier
        rows.append(row)
    return rows


def synthetic_scope():
    result = {"schema": "czr005.feng_paper_suite.reduced_scope.v1", "cell_count": 576,
              "family_counts": {"base": 480, "all_day_fault": 96}, "execution_order": ["base", "all_day_fault"]}
    for fam in report.FAMILY_COUNTS:
        result[fam] = {"maps": ["map2", "nanning"], "load_factors": [1., 2.],
                       "speed_mps": [1.5, 2.5, 3.] if fam == "base" else [2.5],
                       "seeds": list(report.registered_seeds(fam)),
                       "methods": list(report.METHODS if fam == "base" else (report.G31, report.HCA))}
    result["all_day_fault"].update(scenario_indices=[1, 2, 9, 14], initial_line_sets=[[1], [2], [1, 7], [2, 4, 6]])
    return result


class ReducedSuiteReportTests(unittest.TestCase):
    def test_exact_scope_and_pair_group_counts(self):
        rows = synthetic_rows()
        pairs = report.pair_cells(rows)
        groups, pgroups = report.group_results(rows, pairs, report.BASE_SEEDS)
        self.assertEqual((len(rows), len(pairs), len(groups), len(pgroups)), (576, 408, 80, 52))
        self.assertEqual({g["expected_seed_count"] for g in groups if g["family"] == "base"}, {10})
        self.assertEqual({g["expected_seed_count"] for g in groups if g["family"] == "all_day_fault"}, {3})
        self.assertEqual(report.summarize_progress(rows, pairs)["status"], "COMPLETE")

    def test_same_count_arbitrary_mask_or_alternate_seed_rejected(self):
        for field, value in (("scenario_index", 15), ("seed", 181081)):
            rows = synthetic_rows()
            next(r for r in rows if r["family"] == "all_day_fault")[field] = value
            with self.assertRaisesRegex(ValueError, "coordinate set"):
                report.pair_cells(rows)
        rows = synthetic_rows()
        with self.assertRaisesRegex(ValueError, "coordinate set"):
            report.pair_cells(rows[:-1])
        rows[-1] = deepcopy(rows[0])
        with self.assertRaisesRegex(ValueError, "coordinate set"):
            report.pair_cells(rows)

    def test_scope_contract_values_and_sha_are_binding(self):
        scope = synthetic_scope()
        report.validate_scope_contract(scope)
        scope["all_day_fault"]["scenario_indices"][-1] = 15
        with self.assertRaisesRegex(ValueError, "registration differs"):
            report.validate_scope_contract(scope)
        scope = synthetic_scope()
        scope["execution_order"].reverse()
        with self.assertRaisesRegex(ValueError, "execution order"):
            report.validate_scope_contract(scope)
        with tempfile.TemporaryDirectory() as directory:
            scope_path = Path(directory) / "scope.json"
            scope_path.write_bytes(report.json_bytes(synthetic_scope()))
            plan_path = Path(directory) / "plan.json"
            plan_path.write_bytes(report.json_bytes({"schema": "czr005.feng_paper_suite.plan.v1",
                "status": "FROZEN_SPECS_NOT_ALL_EXECUTED", "scope_contract": {"path": str(scope_path), "sha256": "bad"}}))
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                report.load_plan(plan_path, report.Reader())

    def test_fault_missing_one_of_three_does_not_use_two_seed_subset(self):
        rows = synthetic_rows()
        missing = next(r for r in rows if r["family"] == "all_day_fault" and r["method"] == report.HCA)
        missing["cell_state"] = "MISSING"
        _, groups = report.group_results(rows, report.pair_cells(rows), report.BASE_SEEDS)
        group = next(g for g in groups if all(g[k] == missing[k] for k in report.COORD[:-1]))
        self.assertEqual((group["complete_seed_count"], group["expected_seed_count"]), (2, 3))
        self.assertFalse(group["metrics"]["TH"]["eligible"])
        self.assertIsNone(group["metrics"]["TH"]["g31_mean"])

    def test_base_complete_is_not_whole_task_complete(self):
        rows = synthetic_rows()
        for row in rows:
            if row["family"] == "all_day_fault":
                row["cell_state"] = "MISSING"
        progress = report.summarize_progress(rows, report.pair_cells(rows))
        self.assertEqual(progress["family_progress"]["base"]["accepted_cells"], 480)
        self.assertEqual(progress["family_progress"]["base"]["status"], "COMPLETE")
        self.assertEqual(progress["family_progress"]["all_day_fault"]["status"], "PARTIAL")
        self.assertEqual(progress["status"], "PARTIAL_NOT_A_FINAL_CONCLUSION")

    def test_fault_censored_tht_na_th_and_deadlines_remain_eligible(self):
        rows = synthetic_rows()
        for row in rows:
            if row["family"] == "all_day_fault" and row["method"] == report.HCA:
                row.update(full_population_complete=False, TH=80, completion_rate=.8,
                           success_std_rate=.7, success_paper_literal_rate=.1)
                row.update({name: None for name in report.TIMINGS})
        _, groups = report.group_results(rows, report.pair_cells(rows), report.BASE_SEEDS)
        fault = next(g for g in groups if g["family"] == "all_day_fault")
        self.assertEqual(fault["complete_seed_count"], 3)
        self.assertEqual(fault["tht_eligible_seed_count"], 0)
        self.assertEqual(fault["metrics"]["TH"]["mean_benefit"], 20)
        self.assertAlmostEqual(fault["metrics"]["completion_rate"]["benefit_pp"], 20)
        self.assertFalse(fault["metrics"]["tht_D_mean_seconds"]["eligible"])
        full_2x = next(g for g in groups if g["family"] == "base" and g["load_factor"] == 2)
        self.assertTrue(full_2x["metrics"]["tht_D_mean_seconds"]["eligible"])

    def test_bad_pair_coordinate_and_input_mismatch_cannot_enter_group(self):
        rows = synthetic_rows()
        changed = next(r for r in rows if r["family"] == "all_day_fault" and r["method"] == report.HCA)
        changed["input_signature_sha256"] = "SYNTHETIC_FOREIGN_INPUT"
        pairs = report.pair_cells(rows)
        self.assertEqual(sum(p["pair_status"] == "INPUT_MISMATCH" for p in pairs), 1)
        self.assertEqual(report.summarize_progress(rows, pairs)["family_progress"]["all_day_fault"]["status"], "PARTIAL")
        pairs[-1]["scenario_index"] = 15
        with self.assertRaisesRegex(ValueError, "paired coordinates"):
            report.group_results(rows, pairs, report.BASE_SEEDS)

    def test_native_reversal_negative_benefit_and_three_seed_labels_visible(self):
        rows = synthetic_rows()
        pairs = report.pair_cells(rows)
        groups, paired = report.group_results(rows, pairs, report.BASE_SEEDS)
        fault = next(g for g in paired if g["family"] == "all_day_fault")
        self.assertEqual(fault["metrics"]["tht_D_mean_seconds"]["losses"], 3)
        snapshot = {"observed_finished_at_utc": "SYNTHETIC_NOT_REAL_DATA", **report.summarize_progress(rows, pairs),
                    "expected_cells": 576, "expected_pairs": 408,
                    "cell_state_counts": {k: 576 if k == "COMPLETE" else 0 for k in report.STATES},
                    "full_population_cell_count": 576, "censored_population_cell_count": 0,
                    "method_groups": groups, "paired_groups": paired,
                    "plan_sha256": "SYNTHETIC", "generator_sha256": "SYNTHETIC", "plan_path": "SYNTHETIC"}
        text = report.render_report(snapshot)
        self.assertIn("-25.000 / -25.000", text)
        self.assertIn("33.333 / 33.333", text)
        self.assertIn("3/3；3/3", text)
        self.assertIn("不等于完整 16 场景论文复现", text)
        self.assertIn("无重连", text)
        self.assertNotIn("全部 1760 格", text)


if __name__ == "__main__":
    unittest.main()

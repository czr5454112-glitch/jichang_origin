"""Synthetic reporting boundaries; fixtures are explicitly not experiment data."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from scripts.eval import report_feng_paper_suite as report


def cpp_result(full=True):
    timing = {"count": 100, "min": 1.0, "mean": 4.0, "max": 10.0}
    return {"population_audit": {"status": "PASS", "gates": {"population": True},
            "full_population_complete": full, "timing_eligible": full, "raw_bag_count": 100,
            "segment_count": 120, "completed_segment_count": 120 if full else 95,
            "completed_raw_bag_count": 100 if full else 80, "completion_rate": 1 if full else .8,
            "success_rate_std": .8, "success_rate_paper_literal": .2,
            "primary_timing": timing.copy() if full else None,
            "native_timing": timing.copy() if full else None,
            "trace": {"native_full_protocol_integrity_pass": False,
                      "native_active_state_integrity_pass": True,
                      "merge_grant_lifecycle_complete": False}}}


def synthetic_rows():
    rows = []
    for fam, speeds, scenarios, methods in (
            ("base", (1.5, 2.5, 3), (0,), report.METHODS),
            ("all_day_fault", (2.5,), range(1, 17), (report.G31, report.HCA))):
        for m, load, speed, scenario, seed, method in itertools.product(
                ("map2", "nanning"), (1, 2), speeds, scenarios, range(10), methods):
            row = dict(zip(report.COORD, (fam, m, load, speed, scenario, seed)))
            row.update(cell_id=f"SYNTHETIC_{len(rows)}", method=method, cell_state="COMPLETE",
                       input_signature_sha256="SYNTHETIC_IDENTICAL_INPUT", full_population_complete=True,
                       TH=100, completion_rate=1, success_std_rate=.8, success_paper_literal_rate=.2,
                       native_wall_seconds=1, affected_edge_count=0 if fam == "base" else 1)
            # G31 loses D but wins native. This must not disappear in reporting.
            for clock, value in (("D", 10 if method == report.G31 else 8),
                                 ("native", 4 if method == report.G31 else 6)):
                for stat, factor in (("min", .5), ("mean", 1), ("max", 2)):
                    row[f"tht_{clock}_{stat}_seconds"] = value * factor
            rows.append(row)
    return rows


class PaperSuiteReportTests(unittest.TestCase):
    def test_all_schemas_translate_exactly_and_keep_trace_limit(self):
        cpp = cpp_result()
        for method in (report.G31, report.TARAU):
            got = report.extract_metrics(method, cpp)
            self.assertEqual(got["tht_D_mean_seconds"], 4)
            self.assertFalse(got["native_full_protocol_integrity_pass"])
            self.assertTrue(got["native_active_state_integrity_pass"])
        for method in (report.HCA, report.DH):
            metrics = {"completed_raw_bag_count": 100, "raw_bag_denominator": 100}
            for clock, prefix in (("D", "tht_scheduled_release" if method == report.HCA else "tht_D"),
                                  ("native", "tht_admission" if method == report.HCA else "tht_native")):
                for stat, value in (("min", 2), ("mean", 3), ("max", 7)):
                    metrics[f"{prefix}_{stat}_seconds"] = value
            metrics.update({"success_std_rate" if method == report.HCA else "success_rate_std": .8,
                            "success_std_minus_2700_rate" if method == report.HCA else "success_rate_paper_literal": .2})
            value = {"metrics": metrics, "raw_bag_denominator": 100, "population_audit": {"status": "PASS", "full_population_complete": True},
                     "audit_status": "PASS", "survivor_timing_used": False, "full_population_complete": True}
            self.assertEqual(report.extract_metrics(method, value)["tht_native_mean_seconds"], 3)

    def test_incomplete_population_forbids_survivor_timing(self):
        value = cpp_result(False)
        got = report.extract_metrics(report.G31, value)
        self.assertEqual(got["TH"], 80)
        self.assertTrue(all(got[k] is None for k in report.TIMINGS))
        value["population_audit"]["primary_timing"] = {"count": 80, "min": 1, "mean": 2, "max": 3}
        with self.assertRaisesRegex(ValueError, "timing/full"):
            report.extract_metrics(report.G31, value)

    def test_full_timing_count_must_use_whole_population(self):
        value = cpp_result()
        value["population_audit"]["primary_timing"]["count"] = 99
        with self.assertRaisesRegex(ValueError, "timing count"):
            report.extract_metrics(report.TARAU, value)

    def test_all_1760_rows_and_1000_pairs_retained_missing_seed_disables_group(self):
        rows = synthetic_rows()
        missing = next(r for r in rows if r["method"] == report.HCA and r["family"] == "base")
        missing["cell_state"] = "MISSING"
        pairs = report.pair_cells(rows)
        groups, paired = report.group_results(rows, pairs, list(range(10)))
        self.assertEqual((len(rows), len(pairs), len(groups), len(paired)), (1760, 1000, 176, 100))
        g = next(g for g in paired if all(g[k] == missing[k] for k in report.COORD[:-1]) and g["baseline"] == report.HCA)
        self.assertEqual(g["complete_seed_count"], 9)
        self.assertFalse(g["metrics"]["TH"]["eligible"])
        self.assertIsNone(g["metrics"]["TH"]["g31_mean"])

    def test_two_x_full_allows_tht_censored_keeps_th_and_deadline_pp(self):
        rows = synthetic_rows()
        for r in rows:
            if r["map"] == "map2" and r["load_factor"] == 2 and r["family"] == "base" and r["method"] == report.HCA:
                r.update(full_population_complete=False, TH=80, completion_rate=.8,
                         success_std_rate=.7, success_paper_literal_rate=.1)
                r.update({k: None for k in report.TIMINGS})
        _, groups = report.group_results(rows, report.pair_cells(rows), list(range(10)))
        g = next(g for g in groups if g["family"] == "base" and g["map"] == "map2" and g["load_factor"] == 2 and g["baseline"] == report.HCA)
        self.assertEqual(g["complete_seed_count"], 10)
        self.assertEqual(g["tht_eligible_seed_count"], 0)
        self.assertEqual(g["metrics"]["TH"]["mean_benefit"], 20)
        self.assertAlmostEqual(g["metrics"]["completion_rate"]["benefit_pp"], 20)
        self.assertFalse(g["metrics"]["tht_D_mean_seconds"]["eligible"])
        other = next(g for g in groups if g["family"] == "base" and g["load_factor"] == 2 and g["baseline"] == report.DH)
        self.assertTrue(other["metrics"]["tht_D_mean_seconds"]["eligible"])

    def test_input_mismatch_excluded_even_if_both_completed(self):
        rows = synthetic_rows()
        changed = next(r for r in rows if r["method"] == report.DH)
        changed["input_signature_sha256"] = "SYNTHETIC_FOREIGN_CANONICAL"
        pairs = report.pair_cells(rows)
        match = next(p for p in pairs if p["baseline_cell_id"] == changed["cell_id"])
        self.assertEqual(match["pair_status"], "INPUT_MISMATCH")
        self.assertIsNone(match["g31_TH"])

    def test_negative_benefits_and_reverse_native_visible(self):
        rows = synthetic_rows()
        before = deepcopy(rows)
        methods, pairs = report.group_results(rows, report.pair_cells(rows), list(range(10)))
        metric = pairs[0]["metrics"]["tht_D_mean_seconds"]
        self.assertEqual(metric["benefit_percent_of_means"], -25)
        self.assertEqual((metric["wins"], metric["ties"], metric["losses"]), (0, 0, 10))
        self.assertAlmostEqual(pairs[0]["metrics"]["tht_native_mean_seconds"]["benefit_percent_of_means"], 100/3)
        text = report.render_report({"observed_finished_at_utc": "SYNTHETIC_NOT_RESULTS", "status": "SYNTHETIC",
                 "cell_state_counts": {k: 1760 if k == "COMPLETE" else 0 for k in report.STATES},
                 "full_population_cell_count": 1760, "censored_population_cell_count": 0,
                 "method_groups": methods, "paired_groups": pairs,
                 "plan_sha256": "SYNTHETIC", "generator_sha256": "SYNTHETIC", "plan_path": "SYNTHETIC"})
        self.assertIn("-25.000 / -25.000", text)
        self.assertIn("33.333 / 33.333", text)
        self.assertIn("起点尚未证明完全相同", text)
        self.assertEqual(rows, before)

    def test_failed_and_postprocessing_are_not_accepted_and_sha_drift_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identity = {"map": "map2", "load_factor": 1, "seed": 1, "raw_sha256": "raw",
                        "canonical_sha256": "D", "map_sha256": "map", "raw_bag_count": 100, "segment_count": 120}
            ip = root / "identity.json"
            ip.write_bytes(report.json_bytes(identity))
            spec = {"workload_identity_path": str(ip), "workload_identity_sha256": report.digest(ip.read_bytes())}
            c = {"cell_id": "SYNTHETIC", "family": "base", "map": "map2", "load_factor": 1,
                 "speed_mps": 2.5, "scenario_index": 0, "seed": 1, "method": report.G31,
                 "output_dir": str(root), "spec_sha256": "spec", "runner_sha256": "runner"}
            status = root / "runner_status.json"
            status.write_bytes(report.json_bytes({"status": "FAILED", "error": "synthetic"}))
            self.assertEqual(report.observe_cell(c, spec, report.Reader())["cell_state"], "FAILED")
            status.write_bytes(report.json_bytes({"status": "COMPLETE"}))
            self.assertEqual(report.observe_cell(c, spec, report.Reader())["cell_state"], "POSTPROCESSING")
            result = {"status": "COMPLETE", "method": report.G31, "map": "map2", "load_factor": 1,
                      "seed": 1, "workload_identity_sha256": spec["workload_identity_sha256"]}
            (root / "normalized_result.json").write_bytes(report.json_bytes(result))
            status.write_bytes(report.json_bytes({"status": "COMPLETE", "normalized_result_sha256": "wrong"}))
            row = report.observe_cell(c, spec, report.Reader())
            self.assertEqual(row["cell_state"], "INVALID")
            self.assertIn("SHA differs", row["error"])
            self.assertTrue(all(row[k] is None for k in report.METRICS))

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keep.txt"
            path.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                report.generate("not-read.json", directory)
            self.assertEqual(path.read_text(encoding="utf-8"), "preserve")

    def test_outer_timeout_cannot_be_mistaken_for_live_or_valid_result(self):
        row = synthetic_rows()[0]
        row.update(terminal_result_accepted=True, normalized_sha256="content")
        record = {"status": "TIMED_OUT", "_path": "SYNTHETIC", "_sha256": "sha", "error": "timeout"}
        report.apply_orchestration(row, record)
        self.assertEqual(row["cell_state"], "FAILED")
        self.assertFalse(row["terminal_result_accepted"])
        self.assertTrue(all(row[k] is None for k in report.METRICS))
        row.update(cell_state="COMPLETE", terminal_result_accepted=True)
        record.update(status="REUSED_VERIFIED", normalized_result_sha256="different")
        report.apply_orchestration(row, record)
        self.assertEqual(row["cell_state"], "INVALID")


if __name__ == "__main__":
    unittest.main()

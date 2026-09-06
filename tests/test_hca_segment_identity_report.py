"""Synthetic contract tests for the separately identified repaired HCA report."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import statistics
from pathlib import Path
import tempfile
import unittest

from scripts.eval import report_hca_segment_identity_campaign as report


def synthetic_rows() -> list[dict]:
    result = []
    for m in report.external.MAPS:
        for load in report.external.LOAD_FACTORS:
            for i, seed in enumerate(report.external.SEEDS):
                for j, method in enumerate(report.METHODS):
                    raw = report.external.EXPECTED_POPULATIONS[load][0]
                    unfinished = m == "nanning" and load == 1.75 and method == report.METHODS[2] and i == 9
                    completed = raw-int(unfinished)
                    value = {"map": m, "load_factor": load, "seed": seed, "method": method,
                        "fixed_horizon_seconds": report.external.FIXED_HORIZON_SECONDS,
                        "primary_timing_definition": "SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_COMMON_CANONICAL_SCHEDULED_RELEASE",
                        "TH_definition": "COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259", "historical_shared_D": False,
                        "raw_bag_count": raw, "completed_raw_bag_count": completed, "TH_completed_raw_bags": completed,
                        "completion_rate": completed/raw, "unfinished_raw_bag_count": raw-completed,
                        "full_population_complete": not unfinished, "source_sha256": report.SOURCE_SHA if j == 1 else "a"*64,
                        "class_sha256": report.CLASS_SHA if j == 1 else "b"*64,
                        "workload_identity_sha256": f"SYNTHETIC-{m}-{load}-{seed}",
                        "formal_timing_status": "FULL_POPULATION_RAW_BAG_TIMING" if load != 2 and not unfinished else "NOT_ELIGIBLE",
                        "native_terminal_status": "HORIZON_REACHED" if unfinished else "COMPLETE", "wall_seconds": 10+i}
                    for stat, base in (("min", 20), ("mean", 100), ("max", 700)):
                        # Synthetic HCA min beats G31; other metrics need not.
                        offset = -5 if stat == "min" and j == 2 else j*10
                        value[f"tht_scheduled_release_{stat}_seconds"] = None if load == 2 or unfinished else base+i+offset
                        # Native HCA is deliberately faster than G31 here.
                        value[f"tht_admission_{stat}_seconds"] = None if load == 2 or unfinished else (base+i)*(0.4 if j == 2 else 0.8)
                    result.append(value)
    return result


def csv_rows(values: list[dict]) -> list[dict]:
    return [{k: "" if v is None else str(v) for k, v in row.items()} for row in values]


def synthetic_pairs(indexed: dict) -> dict:
    pairs = []
    for m in report.external.MAPS:
        for load in report.external.LOAD_FACTORS:
            for baseline in report.METHODS[1:]:
                for metric in report.METRICS:
                    values = [(report.number(indexed[m, load, s, baseline][metric]), report.number(indexed[m, load, s, report.METHODS[0]][metric])) for s in report.external.SEEDS]
                    value = {"map": m, "load_factor": load, "baseline": baseline, "reference": report.METHODS[0], "metric": metric,
                             "paired_seed_count": 10, "missing_seed_count": 0}
                    if metric != report.METRICS[3] and load == 2:
                        value["status"] = "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
                    elif any(a is None or b is None for a, b in values):
                        value["status"] = "INCOMPLETE_TEN_SEED_COMPARISON_NO_SUBSET_ESTIMATE"
                    else:
                        delta = [b-a for a, b in values]
                        oriented = delta if metric == report.METRICS[3] else [-d for d in delta]
                        value.update(status="COMPLETE", baseline_mean=statistics.fmean(a for a, _ in values),
                            reference_mean=statistics.fmean(b for _, b in values), mean_delta_reference_minus_baseline=statistics.fmean(delta),
                            bootstrap_ci_low=min(delta), bootstrap_ci_high=max(delta),
                            reference_win_count=sum(v > 1e-12 for v in oriented), tie_count=sum(abs(v) <= 1e-12 for v in oriented),
                            reference_loss_count=sum(v < -1e-12 for v in oriented))
                    pairs.append(value)
    return {"status": "COMPLETE", "expected_cells": 180, "observed_cells": 180,
            "bootstrap_replicates": 10000, "confidence_level": .95,
            "bootstrap_unit": "MATCHED_WORKLOAD_SEED_NOT_INDIVIDUAL_BAG", "partial_seed_estimates_suppressed": True, "rows": pairs}


class HcaReportContractTest(unittest.TestCase):
    def test_population_and_missing_seed_qualification(self):
        rows = synthetic_rows()
        report.validate_cells(rows)
        g = report.group(rows, "nanning", 1.75, report.METHODS[2])
        self.assertEqual(g["complete_seeds"], 9)
        self.assertEqual(g["THT"], dict.fromkeys(report.STATS))
        self.assertEqual(report.group(rows, "map2", 2, report.METHODS[2])["THT_status"], "2×协议")
        with self.assertRaisesRegex(ValueError, "all 180"):
            report.validate_cells(rows[:-1])

    def test_build_and_forbidden_timing_are_rejected(self):
        rows = synthetic_rows()
        next(r for r in rows if r["method"] == report.METHODS[2])["class_sha256"] = "c"*64
        with self.assertRaisesRegex(ValueError, "mixed HCA builds"):
            report.validate_cells(rows)
        rows = synthetic_rows()
        next(r for r in rows if r["load_factor"] == 2)["tht_scheduled_release_mean_seconds"] = 0
        with self.assertRaisesRegex(ValueError, "forbidden"):
            report.validate_cells(rows)

    def test_native_table_preserves_clock_and_full_ten_seed_qualification(self):
        rows = synthetic_rows()
        untouched = copy.deepcopy(rows)
        hca = report.native_timing_group(rows, "map2", 1, report.METHODS[2])
        self.assertAlmostEqual(hca["THT"]["mean"], 41.8)
        self.assertLess(hca["THT"]["mean"], report.native_timing_group(rows, "map2", 1, report.METHODS[0])["THT"]["mean"])
        self.assertEqual(rows, untouched)
        self.assertEqual(report.native_timing_group(rows, "map2", 2, report.METHODS[0])["THT"], dict.fromkeys(report.STATS))
        self.assertEqual(report.native_timing_group(rows, "nanning", 1.75, report.METHODS[2])["THT"], dict.fromkeys(report.STATS))
        next(r for r in rows if r["map"] == "map2" and r["load_factor"] == 1 and r["method"] == report.METHODS[2])["tht_admission_max_seconds"] = None
        missing = report.native_timing_group(rows, "map2", 1, report.METHODS[2])
        self.assertEqual(missing["THT"], dict.fromkeys(report.STATS))
        self.assertEqual(missing["THT_status"], "时间证据不足")
        with self.assertRaisesRegex(ValueError, "all ten frozen seeds"):
            report.native_timing_group(rows[3:], "map2", 1, report.METHODS[2])

    def test_native_headline_shows_reversal_and_does_not_select_partial_group(self):
        rows = synthetic_rows()
        headline = report.native_headline(rows)
        self.assertIn("均值在 7 个完整十种子条件中", headline)
        self.assertIn("最大值在 7 个完整十种子条件中", headline)
        self.assertEqual(headline.count("更低 0、持平 4、更高 3 个"), 2)
        self.assertIn("map2 1.75×", headline)
        self.assertIn("THT mean 为 83.60 / 41.80 秒", headline)
        self.assertIn("THT max 为 563.60 / 281.80 秒", headline)
        self.assertIn("不能据任一列认定同一物理 THT 的全面优劣", headline)
        # Suppress the whole representative condition if one native stat is missing.
        next(r for r in rows if r["map"] == "map2" and r["load_factor"] == 1.75 and r["method"] == report.METHODS[2])["tht_admission_max_seconds"] = None
        missing = report.native_headline(rows)
        self.assertIn("6 个完整十种子条件", missing)
        self.assertNotIn("以 map2", missing)

    def test_reused_control_values_are_immutable_but_new_empty_columns_allowed(self):
        old = csv_rows(synthetic_rows())
        current = copy.deepcopy(old)
        for row in current:
            row["terminal_accounting_residual"] = "0" if row["method"] == report.METHODS[2] else ""
        indexed = report.validate_cells(current)
        report.validate_reused_controls(indexed, old)
        indexed["map2", 1, report.external.SEEDS[0], report.METHODS[0]]["wall_seconds"] = "999"
        with self.assertRaisesRegex(ValueError, "CSV row changed"):
            report.validate_reused_controls(indexed, old)

    def test_paired_signs_ties_and_numeric_recomputation(self):
        indexed = report.validate_cells(synthetic_rows())
        paired = synthetic_pairs(indexed)
        pairs = report.validate_pairs(indexed, paired, csv_rows(paired["rows"]))
        p = pairs["map2", 1, report.METHODS[2], report.METHODS[0], report.METRICS[0]]
        self.assertEqual(p["reference_win_count"], "0")
        self.assertEqual(p["reference_loss_count"], "10")
        self.assertTrue(report.comparison_cells(p, metric=report.METRICS[0])[0].startswith("-"))
        paired["rows"][0]["baseline_mean"] += 1
        with self.assertRaisesRegex(ValueError, "baseline mean differs"):
            report.validate_pairs(indexed, paired, csv_rows(paired["rows"]))

    def test_historical_accounting_does_not_filter_new_hca(self):
        indexed = report.validate_cells(synthetic_rows())
        paired = synthetic_pairs(indexed)
        pairs = report.validate_pairs(indexed, paired, csv_rows(paired["rows"]))
        eligible = report.headline_pairs(pairs, "completed_raw_bag_count")
        self.assertEqual(len(eligible), 12)
        self.assertEqual(sum(p["baseline"] == report.METHODS[2] for p in eligible), 6)
        self.assertEqual(len(report.common.load_control_notes(report.CONTROL_NOTES)["_affected_groups"]), 5)

    def test_stale_or_incomplete_archive_is_not_a_final_report(self):
        with self.assertRaisesRegex(ValueError, "complete 180"):
            report.validate_manifest({"status": "INCOMPLETE", "cells": []}, {}, Path("unused"), {})
        rows = synthetic_rows()
        indexed = report.validate_cells(csv_rows(rows))
        manifest = {"status": "COMPLETE", "new_hca_cells": 60, "reused_control_cells": 120,
                    "source_prior_manifest_sha256": report.OLD_MANIFEST_SHA,
                    "cells": [dict(r, origin="NEW_EXECUTION" if r["method"] == report.METHODS[2] else "REUSED_PREVIOUS_FROZEN_ARCHIVE",
                                   exported_metrics=r, table_row=r) for r in rows]}
        with self.assertRaisesRegex(ValueError, "absent or stale"):
            report.validate_manifest(manifest, {"status": "FAILED"}, Path("unused"), indexed)

    def test_full_synthetic_file_contract_binds_tables_and_typed_manifest_rows(self):
        # The entire temporary bundle is synthetic, including its verifier
        # fixture. It tests file contracts and is never published as evidence.
        with tempfile.TemporaryDirectory(dir=report.ROOT / "build", prefix="synthetic_hca_report_") as directory:
            base = Path(directory)
            rows = synthetic_rows()
            paired = synthetic_pairs(report.validate_cells(rows))
            old_rows = copy.deepcopy(rows)
            for row in old_rows:
                if row["method"] == report.METHODS[2]:
                    row["method"] = "FENG_NATIVE_HCA"
            for row in rows:
                row["terminal_accounting_residual"] = 0 if row["method"] == report.METHODS[2] else None

            def write_csv(name, values):
                path = base / name
                fields = sorted(set().union(*(v.keys() for v in values)))
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(values)
                return path

            cells_path = write_csv("hca_segment_identity_cells_20260906.csv", rows)
            pair_path = write_csv("hca_segment_identity_paired_20260906.csv", paired["rows"])
            json_path = pair_path.with_suffix(".json")
            json_path.write_text(json.dumps(paired), encoding="utf-8")
            old_path = write_csv("SYNTHETIC_OLD_CELLS.csv", old_rows)
            manifest = {"status": "COMPLETE", "expected_cells": 180, "observed_cells": 180,
                "new_hca_cells": 60, "reused_control_cells": 120, "source_prior_manifest_sha256": report.OLD_MANIFEST_SHA,
                "source_sha256": "a"*64, "class_sha256": "b"*64,
                "tables": [{"path": p.name, "sha256": report.sha(p)} for p in (cells_path, pair_path, json_path)],
                "cells": [dict(r, origin="NEW_EXECUTION" if r["method"] == report.METHODS[2] else "REUSED_PREVIOUS_FROZEN_ARCHIVE",
                               exported_metrics=r, table_row=r) for r in rows]}
            manifest_path = base / "campaign_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            verification = {"status": "PASS", "new_hca_cells_recomputed": 60, "reused_control_cells_verified": 120,
                            "campaign_manifest_sha256": report.sha(manifest_path)}
            (base / "archive_verification.json").write_text(json.dumps(verification), encoding="utf-8")
            args = argparse.Namespace(table_root=base, evidence_root=base, old_cells=old_path,
                                      control_notes=report.CONTROL_NOTES)
            self.assertEqual(len(report.load_final(args)[0]), 180)
            # Even a harmless whitespace change must break the manifest binding.
            with json_path.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "table SHA"):
                report.load_final(args)

    def test_synthetic_render_separates_new_hca_from_old_43(self):
        rows = synthetic_rows()
        indexed = report.validate_cells(rows)
        paired = synthetic_pairs(indexed)
        pairs = report.validate_pairs(indexed, paired, csv_rows(paired["rows"]))
        old = copy.deepcopy(rows)
        for row in old:
            if row["method"] == report.METHODS[2]:
                row["method"] = "FENG_NATIVE_HCA"
        args = argparse.Namespace(output=report.OUTPUT, table_root=report.TABLE_ROOT,
                                  evidence_root=report.EVIDENCE, control_notes=report.CONTROL_NOTES)
        text = report.render_report(args, rows, pairs, {}, {}, old, {}, synthetic_qa=True)
        self.assertIn("SYNTHETIC QA — NOT EXPERIMENT RESULTS", text)
        self.assertIn("旧 60 格中的 43 格", text)
        self.assertNotIn("HCA 段身份修复版（新跑）†", text)
        self.assertIn("仅作合成数据布局与口径测试", text)
        self.assertIn("不贴到本次新方法", text)
        self.assertIn("publisher 正式全文仍未取得", text)
        self.assertIn("THT(native) mean", text)
        self.assertIn("entering time", text)
        self.assertIn("不宣称复现论文原始计时起点", text)
        self.assertIn("| map2 | 1× | 新 HCA | 成功 planning / processed_attempt_epoch | 9.80 | 41.80 | 281.80 |", text)
        self.assertLess(text.index("另一计时口径的方向"), text.index("**修复范围。**"))
        self.assertIn("另一计时口径：各执行器原生", text)


if __name__ == "__main__":
    unittest.main()

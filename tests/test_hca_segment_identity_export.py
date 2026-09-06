"""Scientific gates and portable archive corruption tests; no simulation runs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.eval import export_hca_segment_identity_campaign as export
from scripts.eval import run_hca_segment_identity as native


def matrix_rows():
    result = []
    for map_name, load, seed in export.campaign.keys():
        for method in export.METHODS:
            result.append({"map": map_name, "load_factor": load, "seed": seed, "method": method,
                "workload_identity_sha256": f"{map_name}/{load}/{seed}",
                "full_population_complete": True,
                "completed_raw_bag_count": 100 if method == export.G31 else 110,
                "tht_scheduled_release_mean_seconds": None if load == 2 else 12 if method == export.G31 else 10})
    return result


def paired_row(value, *, load=1.0, metric="tht_scheduled_release_mean_seconds"):
    return next(row for row in value["rows"] if row["map"] == "map2"
                and row["load_factor"] == load and row["baseline"] == export.HCA
                and row["reference"] == export.G31 and row["metric"] == metric)


class PairedScientificGates(unittest.TestCase):
    def test_deep_support_paths_are_short_and_same_basenames_stay_distinct(self):
        parent = export.ROOT / ('outputs/runtime/' + 'historical_attempt_' * 5)
        first = export.support_destination(parent / 'first/build_identity.json', digest='0' * 64)
        second = export.support_destination(parent / 'second/build_identity.json', digest='0' * 64)
        self.assertNotEqual(first, second)
        self.assertEqual(first.name, 'build_identity.json')
        self.assertEqual(first.parts[0], 'support')
        self.assertLess(len(str(export.EVIDENCE / first)) + len('.tmp'), 240)

    def test_complete_negative_results_and_ties_are_retained(self):
        value = export.paired_aggregate(matrix_rows(), replicates=32)
        timing = paired_row(value)
        self.assertEqual(timing["status"], "COMPLETE")
        self.assertEqual(timing["reference_win_count"], 0)
        self.assertEqual(timing["reference_loss_count"], 10)
        self.assertEqual((timing["bootstrap_ci_low"], timing["bootstrap_ci_high"]), (2.0, 2.0))
        rows = matrix_rows()
        for row in rows:
            row["completed_raw_bag_count"] = 100
        throughput = paired_row(export.paired_aggregate(rows, replicates=32), metric="completed_raw_bag_count")
        self.assertEqual(throughput["tie_count"], 10)

    def test_missing_seed_suppresses_subset_estimate(self):
        rows = matrix_rows()
        rows = [row for row in rows if not (row["method"] == export.HCA and row["map"] == "map2"
                and row["load_factor"] == 1.0 and row["seed"] == export.external.SEEDS[0])]
        result = export.paired_aggregate(rows, replicates=32)
        row = paired_row(result)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(row["paired_seed_count"], 9)
        self.assertEqual(row["status"], "INCOMPLETE_TEN_SEED_COMPARISON_NO_SUBSET_ESTIMATE")
        self.assertNotIn("mean_delta_reference_minus_baseline", row)
        self.assertNotIn("bootstrap_ci_low", row)

    def test_one_unfinished_seed_timing_is_na_but_throughput_remains(self):
        rows = matrix_rows()
        row = next(r for r in rows if r["method"] == export.HCA and r["map"] == "map2" and r["load_factor"] == 1.0)
        row.update(full_population_complete=False, tht_scheduled_release_mean_seconds=None)
        result = export.paired_aggregate(rows, replicates=32)
        self.assertEqual(paired_row(result)["status"], "INCOMPLETE_TEN_SEED_COMPARISON_NO_SUBSET_ESTIMATE")
        self.assertEqual(paired_row(result, metric="completed_raw_bag_count")["status"], "COMPLETE")

    def test_formal_2x_never_emits_timing_estimate_even_if_nonempty(self):
        rows = matrix_rows()
        for row in rows:
            if row["load_factor"] == 2:
                row["tht_scheduled_release_mean_seconds"] = 13.0
        result = export.paired_aggregate(rows, replicates=32)
        row = paired_row(result, load=2.0)
        self.assertEqual(row["status"], "FORMAL_2X_TIMING_NA_BY_PROTOCOL")
        self.assertNotIn("reference_mean", row)
        self.assertEqual(paired_row(result, load=2.0, metric="completed_raw_bag_count")["status"], "COMPLETE")

    def test_duplicate_coordinates_and_mismatched_inputs_rejected(self):
        rows = matrix_rows()
        with self.assertRaisesRegex(ValueError, "duplicate matrix cell"):
            export.paired_aggregate(rows + [dict(rows[0])], replicates=32)
        rows[0]["workload_identity_sha256"] = "different input bytes"
        with self.assertRaisesRegex(ValueError, "workload identity"):
            export.paired_aggregate(rows, replicates=32)


class PortableArchiveGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hca_segment_export_tests_")
        self.root = Path(self.temporary.name).resolve()
        self.evidence = self.root / "outputs/evidence/repair"
        self.evidence.mkdir(parents=True)
        self.root_patch = patch.object(export, "ROOT", self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def fixture_manifest(self):
        cells = [{"map": m, "load_factor": l, "seed": s, "method": method, "files": []}
                 for m, l, s in export.campaign.keys() for method in export.METHODS]
        return {"status": "COMPLETE", "observed_cells": 180, "new_hca_cells": 60,
                "cells": cells, "support_files": [], "build_files": [], "tables": [], "microtest_old_classes": []}

    def save(self, manifest):
        (self.evidence / "campaign_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def artifact(self, name, content):
        path = self.evidence / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        digest = export.sha(path)
        return {"archive_path": path.relative_to(self.root).as_posix(), "source_path": path.relative_to(self.root).as_posix(), "archive_sha256": digest,
                "source_sha256": digest, "gzip": False}

    def build_chain(self, manifest, *, tested_class_override=None):
        """Small internally bound support chain; bytecode is never executed."""
        source = self.artifact("frozen/source/Test.java", b"class Test {}\n")
        bytecode = self.artifact("frozen/classes/Test.class", b"bounded fixture bytes")
        source.update(build_kind="source", build_relative_path="Test.java")
        bytecode.update(build_kind="classes", build_relative_path="Test.class")
        source_items = [{"path": "Test.java", "sha256": source["source_sha256"]}]
        class_items = [{"path": "Test.class", "sha256": bytecode["source_sha256"]}]
        build = {"source_files": source_items, "class_files": class_items,
                 "source_sha256": native.set_sha(source_items), "class_sha256": native.set_sha(class_items)}
        manifest.update(source_sha256=build["source_sha256"], class_sha256=build["class_sha256"])
        manifest["build_files"] = [source, bytecode]
        support = []

        def add(source_path, content):
            record = self.artifact("support/" + source_path, content)
            record["source_path"] = source_path
            support.append(record)
            return {"path": source_path, "sha256": record["source_sha256"]}

        driver = add("scripts/eval/test_hca_segment_identity.py", b"test driver fixture\n")
        harness = add("tests/java/HcaSegmentIdentityAudit.java", b"test harness fixture\n")
        micro = {"status": "PASS", "method": export.HCA, "checks": [{"pass": True}],
                 "production_identity": {"source_files": {"Test.java": source["source_sha256"]},
                     "class_files": {"Test.class": tested_class_override or bytecode["source_sha256"]}},
                 "test_driver_sha256": driver["sha256"], "java_audit_source_sha256": harness["sha256"],
                 "native_evidence": [], "old_control_identity": {"source_files": {}, "class_files": {}}}
        freeze = {"method": export.HCA, "cell_count": 60,
                  "cells": [{"map": m, "load_factor": l, "seed": s} for m, l, s in export.campaign.keys()],
                  "build_identity": add("build/fixture/build_identity.json", json.dumps(build).encode()),
                  "microtests": add("outputs/runtime/fixture/preflight/microtests.json", json.dumps(micro).encode())}
        for field in ("protocol", "runner", "orchestrator", "previous_manifest", "control_reuse_audit"):
            freeze[field] = add("outputs/runtime/fixture/" + field + ".json", (field + " fixture").encode())
        freeze_file = add("outputs/runtime/fixture/campaign_freeze.json", json.dumps(freeze).encode())
        manifest["freeze_sha256"] = freeze_file["sha256"]
        manifest["support_files"] = support

    def test_relocation_is_portable_and_rejects_repository_escape(self):
        desired = self.root / "outputs/evidence/repair/data.csv"
        self.assertEqual(export.relocated("C:/old/checkouts/project/outputs/evidence/repair/data.csv"), desired)
        with self.assertRaisesRegex(ValueError, "escapes repository"):
            export.relocated("outputs/../../../outside.csv")
        with self.assertRaisesRegex(ValueError, "not a repository evidence path"):
            export.relocated("C:/unrelated/data.csv")

    def test_same_support_path_with_new_content_keeps_both_archive_versions(self):
        source = self.root / "outputs/runtime/remaining_execution_status.json"
        source.parent.mkdir(parents=True)
        source.write_bytes(b'{"status":"RUNNING"}\n')
        first = self.evidence / export.support_destination(source)
        before = export.archive_file(source, first)
        source.write_bytes(b'{"status":"COMPLETE"}\n')
        second = self.evidence / export.support_destination(source)
        after = export.archive_file(source, second)
        self.assertNotEqual(first, second)
        self.assertEqual(second, self.evidence / export.support_destination(source))
        self.assertEqual(before["source_path"], after["source_path"])
        self.assertEqual(export.sha(first), before["source_sha256"])
        self.assertEqual(export.sha(second), after["source_sha256"])
        self.assertEqual(first.read_bytes(), b'{"status":"RUNNING"}\n')
        self.assertEqual(second.read_bytes(), b'{"status":"COMPLETE"}\n')

    def test_missing_seed_and_old_hca_substitution_rejected_before_io(self):
        manifest = self.fixture_manifest()
        manifest["cells"].pop()
        self.save(manifest)
        with self.assertRaisesRegex(ValueError, "archive coordinates differ"):
            export.verify_archive(self.evidence)
        manifest = self.fixture_manifest()
        next(c for c in manifest["cells"] if c["method"] == export.HCA)["method"] = "FENG_NATIVE_HCA"
        self.save(manifest)
        with self.assertRaisesRegex(ValueError, "archive coordinates differ"):
            export.verify_archive(self.evidence)

    def test_native_byte_tampering_rejected_before_population_recomputation(self):
        manifest = self.fixture_manifest()
        record = self.artifact("native/output.txt", b"8 9000.0\n")
        manifest["cells"][0]["files"] = [record]
        export.relocated(record["archive_path"]).write_bytes(b"8 8000.0\n")
        self.save(manifest)
        with patch.object(export, "previous_controls", side_effect=AssertionError("must fail before controls")):
            with self.assertRaisesRegex(ValueError, "archive digest mismatch"):
                export.verify_archive(self.evidence)

    def test_source_class_digest_claim_cannot_be_changed_without_rejection(self):
        manifest = self.fixture_manifest()
        self.build_chain(manifest)
        manifest["class_sha256"] = "0" * 64
        self.save(manifest)
        controls = [copy.deepcopy(c) for c in manifest["cells"] if c["method"] != export.HCA]
        with patch.object(export, "previous_controls", return_value=([], controls)):
            with self.assertRaisesRegex(ValueError, "build aggregate mismatch"):
                export.verify_archive(self.evidence)

    def test_archived_classes_must_be_the_classes_that_passed_microtests(self):
        manifest = self.fixture_manifest()
        self.build_chain(manifest, tested_class_override="9" * 64)
        self.save(manifest)
        controls = [copy.deepcopy(c) for c in manifest["cells"] if c["method"] != export.HCA]
        with patch.object(export, "previous_controls", return_value=([], controls)):
            with self.assertRaisesRegex(ValueError, "archived production classes differs? from tested implementation"):
                export.verify_archive(self.evidence)


if __name__ == "__main__":
    unittest.main()

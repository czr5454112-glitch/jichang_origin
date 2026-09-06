"""Independent timing-clock and source-blocking diagnostic unit fixtures."""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.eval import diagnose_hca_segment_identity_release_delay as diagnostic
from scripts.eval import report_hca_segment_identity_campaign as report


class ReleaseDelayDiagnosticTest(unittest.TestCase):
    def test_portable_archive_checks_container_source_and_safe_suffix(self):
        with tempfile.TemporaryDirectory(dir=diagnostic.ROOT / "build", prefix="diagnostic_archive_fixture_") as directory:
            base = Path(directory) / "fixture_evidence"
            base.mkdir()
            raw = b"task_id,finish\n7,125\n"
            data = gzip.compress(raw, mtime=0)
            (base / "event.csv.gz").write_bytes(data)
            descriptor = {"archive_path": "C:/old/workspace/fixture_evidence/event.csv.gz", "gzip": True,
                "archive_sha256": hashlib.sha256(data).hexdigest(), "archive_size_bytes": len(data),
                "source_sha256": hashlib.sha256(raw).hexdigest(), "source_size_bytes": len(raw)}
            self.assertEqual(diagnostic.checked_archive_bytes(descriptor, base), raw)
            with self.assertRaisesRegex(ValueError, "unsafe"):
                diagnostic.archive_path("fixture_evidence/../event.csv.gz", base)
            damaged = bytearray(data)
            damaged[-1] ^= 1
            (base / "event.csv.gz").write_bytes(damaged)
            with self.assertRaisesRegex(ValueError, "container SHA/size"):
                diagnostic.checked_archive_bytes(descriptor, base)
            (base / "event.csv.gz").write_bytes(data)
            descriptor["source_sha256"] = "0"*64
            with self.assertRaisesRegex(ValueError, "source SHA/size"):
                diagnostic.checked_archive_bytes(descriptor, base)

    def test_scientific_comparison_ignores_only_read_metadata(self):
        native = {"status": "PASS", "common_completed_cohort_diagnostic": {"hash": "original", "bags": 28505},
                  "evidence": [{"path": "native.csv"}]}
        archive = {**native, "evidence": [{"path": "restored.csv"}], "archive_read_provenance": {"mode": "archive"}}
        self.assertEqual(diagnostic.scientific_payload(native), diagnostic.scientific_payload(archive))
        archive["common_completed_cohort_diagnostic"] = {"hash": "changed", "bags": 28505}
        self.assertNotEqual(diagnostic.scientific_payload(native), diagnostic.scientific_payload(archive))

    def test_two_leg_tht_uses_canonical_D_and_preserves_components(self):
        life = {"7:in": {"task_id": 7, "scheduled_pass_time": 100.25, "release_epoch": 100,
                          "processed_attempt_epoch": 105, "finish_epoch": 125},
                "7:out": {"task_id": 7, "scheduled_pass_time": 110, "release_epoch": 120,
                           "processed_attempt_epoch": 125, "finish_epoch": 130}}
        values = diagnostic.bag_components(life)[7]
        self.assertEqual(values, {"scheduled_D_THT": 44.75, "native_release_minus_D": 9.75,
                                 "planning_minus_native_release": 10, "completion_minus_planning": 25})
        # Outbound and inbound are summed, not reduced to one raw wall clock.
        self.assertNotEqual(values["scheduled_D_THT"], 130-100.25)

    def test_source_next_epoch_and_independent_other_source(self):
        life = {"a": {"segment_id": "a", "start": 49, "scheduled_pass_time": 8260.75,
                       "release_epoch": 8260, "processed_attempt_epoch": 8265},
                "b": {"segment_id": "b", "start": 49, "scheduled_pass_time": 8261,
                       "release_epoch": 8266, "processed_attempt_epoch": 8268},
                "c": {"segment_id": "c", "start": 53, "scheduled_pass_time": 8261,
                       "release_epoch": 8261, "processed_attempt_epoch": 8262}}
        self.assertEqual(diagnostic.source_release_replay(life)["mismatch_count"], 0)
        life["b"]["release_epoch"] = 8265
        self.assertEqual(diagnostic.source_release_replay(life)["mismatch_count"], 1)

    def test_published_diagnostic_keeps_cohort_ineligible_and_single_cell_scope(self):
        value = report.load_timing_diagnostic(report.TIMING_DIAGNOSTIC)
        self.assertTrue(value["scope"]["single_cell_only"])
        self.assertFalse(value["common_completed_cohort_diagnostic"]["formal_timing_eligible"])
        self.assertEqual(value["common_completed_cohort_diagnostic"]["difference_count"], 0)


if __name__ == "__main__":
    unittest.main()

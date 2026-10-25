"""Small adversarial fixtures for independent no-wait calendar replay."""
import importlib.util
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TARGET = Path(__file__).resolve().parents[1] / "scripts/experiments/g31_no_wait/replay.py"
SPEC = importlib.util.spec_from_file_location("nowait_replay", TARGET)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(sid, route, order, release=None):
    admission, finish = route[0][1], route[-1][1]
    row = {"segment_id": sid, "pass_time": admission if release is None else release,
           "start": route[0][0], "goal": route[-1][0]}
    bag = {"segment_id": sid, "route": route, "admission": admission, "finish": finish,
           "commit_time": admission, "commit_order": order, "completion_epoch": math.ceil(finish)}
    return row, bag


def run(*pairs, **kwargs):
    return MODULE.replay_calendar([p[0] for p in pairs], [p[1] for p in pairs], **kwargs)


class ReplayTests(unittest.TestCase):
    def test_closed_internal_endpoints_conflict(self):
        a = fixture("a", [(0, 0, 2), (1, 10, 12), (2, 20, 22)], 0)
        b = fixture("b", [(3, 1, 3), (1, 12, 14), (4, 21, 23)], 1)
        result = run(a, b)
        self.assertFalse(result["passed"])
        self.assertEqual(result["violation_counts"], {"reservation_query_conflict": 1})

    def test_prior_endpoint_is_not_blanket_exemption(self):
        a = fixture("a", [(0, 0, 2), (1, 100, 102)], 0)
        b = fixture("b", [(2, 90, 92), (1, 101, 103), (3, 104, 106)], 1)
        result = run(a, b)
        self.assertFalse(result["passed"])
        self.assertEqual(result["stats"]["internal_query_conflicts_with_prior_endpoint"], 1)
        self.assertTrue(run(a, b, endpoint_policy="internal_only")["passed"])

    def test_equal_start_zero_goal_cannot_hide_long_internal(self):
        a = fixture("a", [(0, 0, 2), (1, 2.4, 4.4), (3, 14.4, 16.4)], 0)
        b = fixture("b", [(2, 0, 2), (1, 2.4, 2.4)], 1)
        c = fixture("c", [(4, 2, 4), (1, 4.4, 6.4), (5, 7.4, 9.4)], 2)
        result = run(a, b, c)
        self.assertFalse(result["passed"])
        conflicts = [e for e in result["violation_examples"]
                     if e["reason"] == "reservation_query_conflict"]
        self.assertEqual([(e["segment_id"], e["prior_segment_id"]) for e in conflicts], [("c", "a")])

    def test_large_duration_closed_boundary_detected_without_inverse(self):
        a = fixture("a", [(0, 0, 0), (1, 1e-10, 1e12), (3, 1e12 + 10, 1e12 + 10)], 0)
        b = fixture("b", [(2, 1, 1), (1, 1e12, 1e12 + 2), (4, 1e12 + 3, 1e12 + 3)], 1)
        self.assertFalse(run(a, b)["passed"])

    def test_current_source_query_is_exempt(self):
        a = fixture("a", [(0, 0, 2), (1, 10, 12), (2, 20, 22)], 0)
        b = fixture("b", [(1, 10, 12), (3, 15, 17)], 1)
        self.assertTrue(run(a, b)["passed"])
        self.assertFalse(run(a, b, endpoint_policy="all_nodes")["passed"])

    def test_completion_removed_before_equal_epoch_commit(self):
        a = fixture("a", [(0, 0, 2), (1, 100, 102)], 0)
        b = fixture("b", [(2, 100, 102), (1, 102, 104), (3, 105, 107)], 1)
        self.assertTrue(run(a, b)["passed"])
        self.assertFalse(run(a, b, cleanup_phase="before_commit_lt")["passed"])

    def test_future_release_commit_and_order_reversal_detected(self):
        a = fixture("a", [(0, 10, 12), (1, 20, 22)], 0)
        b = fixture("b", [(2, 1, 3), (3, 4, 6)], 1, release=2)
        result = run(a, b)
        self.assertFalse(result["passed"])
        self.assertIn("committed_before_business_release", result["violation_counts"])
        self.assertIn("admitted_before_business_release", result["violation_counts"])
        self.assertIn("commit_order_time_reversal", result["violation_counts"])

    def test_duplicate_or_missing_metadata_is_failure(self):
        a = fixture("a", [(0, 0, 2), (1, 20, 22)], 0)
        b = fixture("b", [(2, 1, 3), (3, 4, 6)], 0)
        self.assertIn("invalid_or_duplicate_commit_order", run(a, b)["violation_counts"])
        del b[1]["commit_time"]
        self.assertIn("invalid_or_missing_commit_metadata", run(a, b)["violation_counts"])

    def test_complete_identity_including_unplanned_preserved(self):
        a = fixture("a", [(0, 0, 2), (1, 20, 22)], 0)
        unplanned = ({"segment_id": "failed", "pass_time": 3, "start": 2, "goal": 3},
                     {"segment_id": "failed", "route": []})
        result = run(a, unplanned)
        self.assertTrue(result["passed"])
        self.assertEqual(result["segment_denominator"], 2)
        self.assertEqual(result["replayed_certificates"], 1)
        with self.assertRaises(ValueError):
            MODULE.replay_calendar([a[0], unplanned[0]], [a[1]])

    def test_half_open_touch_and_empty_zero_are_legal(self):
        a = fixture("a", [(0, 0, 0), (1, 10, 12), (2, 20, 22)], 0)
        b = fixture("b", [(3, 1, 1), (1, 12, 14), (4, 21, 23)], 1)
        c = fixture("c", [(0, 0, 0), (5, 6, 6)], 2)
        # At equal commit time order remains valid; no zero-length point occupies.
        c[1]["commit_order"] = 1
        b[1]["commit_order"] = 2
        result = run(a, c, b, endpoint_policy="all_nodes", interval_mode="half_open",
                     time_grid_seconds=1e-6)
        self.assertTrue(result["passed"], result)
        self.assertGreater(result["stats"]["empty_intervals_ignored"], 0)

    def test_resource_cleanup_retains_goal_after_business_completion(self):
        a = fixture("a", [(0, 0, 0), (1, 10, 12)], 0)
        b = fixture("b", [(2, 10, 10), (1, 11, 13), (3, 14, 16)], 1)
        a[1]["resource_cleanup_epoch"] = 12
        b[1]["resource_cleanup_epoch"] = 16
        options = dict(endpoint_policy="all_nodes", interval_mode="half_open",
                       time_grid_seconds=1e-6, edge_entry_headway_seconds=2)
        self.assertTrue(run(a, b, **options)["passed"])
        physical = run(a, b, cleanup_field="resource_cleanup_epoch", **options)
        self.assertFalse(physical["passed"])
        self.assertIn("reservation_query_conflict", physical["violation_counts"])

    def test_resource_cleanup_must_cover_last_edge_window(self):
        a = fixture("a", [(0, 0, 0), (1, 0.1, 0.1)], 0)
        a[1]["resource_cleanup_epoch"] = 1
        result = run(a, interval_mode="half_open", time_grid_seconds=1e-6,
                     cleanup_field="resource_cleanup_epoch", edge_entry_headway_seconds=2)
        self.assertIn("resource_cleanup_epoch_mismatch", result["violation_counts"])


if __name__ == "__main__":
    unittest.main()

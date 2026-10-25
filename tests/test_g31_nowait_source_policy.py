"""Canonical source order cannot be reconstructed from successful admissions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.experiments.g31_no_wait.source_policy_audit import audit_source_policy


def row(sid, release=0, source=0, task_id=None, leg="direct"):
    return dict(segment_id=sid, pass_time=release, start=source, goal=9,
                task_id=sid if task_id is None else task_id, leg=leg)


def bag(sid, attempt=None, admission=None, finish=None, **kwargs):
    return dict(segment_id=sid, first_planning_attempt_time=attempt,
                admission=admission, finish=finish, completed=finish is not None, **kwargs)


class SourcePolicyTests(unittest.TestCase):
    def test_raw_release_and_stable_ties_not_algorithm_order(self):
        rows = [row("later", 5.9), row("tie_first", 5.1), row("tie_second", 5.1)]
        bags = [bag("later", 9, 10, 13), bag("tie_first", 6, 6, 9), bag("tie_second", 7, 8, 11)]
        self.assertTrue(audit_source_policy(rows, bags)["passed"])
        bags[1], bags[2] = bag("tie_first", 7, 8, 11), bag("tie_second", 6, 6, 9)
        self.assertIn("first_attempt_before_previous_success_plus_source_interval", audit_source_policy(rows, bags)["violation_counts"])

    def test_ready_later_cannot_pass_unattempted_or_failed_head(self):
        rows = [row("head"), row("later", 1)]
        for attempt in (None, 0):
            result = audit_source_policy(rows, [bag("head", attempt), bag("later", 1, 1, 2)])
            self.assertIn("bypassed_unadmitted_canonical_predecessor", result["violation_counts"])

    def test_future_unattempted_population_is_legal_and_retained(self):
        result = audit_source_policy([row("a", 200), row("b", 201)], [bag("a"), bag("b")])
        self.assertTrue(result["passed"])
        self.assertEqual(result["segment_denominator"], 2)
        self.assertEqual(result["unattempted_segments"], 2)

    def test_source_tick_exact_boundary_no_epsilon(self):
        rows = [row("a"), row("b")]
        self.assertTrue(audit_source_policy(rows, [bag("a", 0, 2, 4), bag("b", 3, 3, 5)])["passed"])
        self.assertFalse(audit_source_policy(rows, [bag("a", 0, 2, 4), bag("b", 2.999999, 3, 5)])["passed"])

    def test_ceil_release_and_later_actual_inbound_report(self):
        rows = [row("in", 0, 1, 7, "storage_in"), row("out", .2, 2, 7, "storage_out")]
        bags = [bag("in", 0, 0, 5.2, observed_finish=7), bag("out", 6, 8, 10)]
        self.assertIn("outbound_first_attempt_before_inbound_report", audit_source_policy(rows, bags)["violation_counts"])
        bags[1] = bag("out", 7, 8, 10)
        self.assertTrue(audit_source_policy(rows, bags)["passed"])
        self.assertFalse(audit_source_policy([row("r", .2)], [bag("r", .5, 1, 3)])["passed"])

    def test_missing_clock_cannot_be_filled_by_success_or_generated_release(self):
        result = audit_source_policy([row("a")], [dict(segment_id="a", admission=5, finish=6, generated_release=0)])
        self.assertIn("missing_first_planning_attempt_telemetry", result["violation_counts"])
        self.assertIn("admitted_without_first_attempt", result["violation_counts"])

    def test_declared_activation_policy_does_not_change_reference(self):
        result = audit_source_policy([row("a"), row("b", 1)], [bag("a"), bag("b", 1, 1, 3)], source_fifo_order="activation")
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()

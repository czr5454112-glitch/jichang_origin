"""Adversarial denominator, external-hold, and two-leg THT accounting tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.experiments.g31_no_wait.tht_metrics import audit_tht


def row(task, leg="direct", release=0, original=0):
    return dict(segment_id=f"{task}:{leg}", task_id=task, leg=leg,
                pass_time=release, original_entry_time=original)


def bag(r, admission=None, finish=None, completed=True, **kwargs):
    return dict(segment_id=r["segment_id"], admission=admission,
                finish=finish, completed=completed, **kwargs)


class ThtTests(unittest.TestCase):
    def test_first_attempt_includes_retry_but_not_preactivation_hold(self):
        r = row(0, release=10, original=10)
        result = audit_tht([r], [bag(r, 50, 70, first_planning_attempt_time=30, activation_time=20)])
        self.assertTrue(result["passed"])
        self.assertEqual(result["primary"], "user_tht")
        self.assertEqual(result["user_tht_total_seconds"], 40)
        self.assertEqual(result["paper_tht_total_seconds"], 20)
        self.assertEqual(result["secondary"]["business_sum_planning_wait"]["full_population"]["sum"], 20)
        self.assertEqual(result["secondary"]["business_sum_canonical_preplanning"]["full_population"]["sum"], 20)
        self.assertEqual(result["secondary"]["business_sum_activation_to_first_planning"]["full_population"]["sum"], 10)
        self.assertEqual(60, result["user_tht_total_seconds"] + 20)

    def test_old_successful_admission_does_not_invent_first_attempt(self):
        r = row(0)
        result = audit_tht([r], [bag(r, 50, 70, generated_release=10, release_time=10, activation_time=10)])
        self.assertTrue(result["passed"])
        self.assertFalse(result["user_tht_full_population_available"])
        self.assertIsNone(result["user_tht_total_seconds"])
        self.assertEqual(result["missing_first_planning_attempt_segments"], 1)
        self.assertEqual(result["network_elapsed"]["full_population"]["sum"], 20)

    def test_ebs_user_tht_sums_each_first_attempt_without_storage(self):
        a, b = row(0, "storage_in", 10, 10), row(0, "storage_out", 1000, 10)
        result = audit_tht([a, b], [bag(a, 20, 50, first_planning_attempt_time=15),
                                   bag(b, 1020, 1040, first_planning_attempt_time=1005)])
        self.assertEqual(result["user_tht_total_seconds"], 70)
        self.assertEqual(result["paper_tht_total_seconds"], 50)
        self.assertEqual(result["secondary"]["business_sum_planning_wait"]["full_population"]["sum"], 20)
        self.assertEqual(result["secondary"]["business_sum_canonical_preplanning"]["full_population"]["sum"], 10)

    def test_attempted_unadmitted_censored_wait_counts_to_horizon(self):
        a, b = row(0), row(1)
        result = audit_tht([a, b], [bag(a, completed=False, first_planning_attempt_time=25),
                                   bag(b, completed=False, first_planning_attempt_time=None)], horizon=100)
        self.assertTrue(result["passed"])
        self.assertIsNone(result["user_tht_total_seconds"])
        self.assertEqual(result["user_tht"]["restricted_full_population"]["sum"], 75)
        self.assertEqual(result["secondary"]["business_sum_canonical_preplanning"]["restricted_full_population"]["sum"], 125)

    def test_attempt_after_successful_admission_is_invalid(self):
        r = row(0)
        result = audit_tht([r], [bag(r, 5, 10, first_planning_attempt_time=6)])
        self.assertFalse(result["passed"])
        self.assertIn("first_attempt_outside_release_admission_window", result["violation_counts"])

    def test_external_hold_not_paper_tht_but_always_reported(self):
        r = row(0, release=10, original=10)
        result = audit_tht([r], [bag(r, 50, 70, generated_release=49)])
        self.assertTrue(result["passed"])
        self.assertEqual(result["paper_tht_total_seconds"], 20)
        self.assertEqual(result["secondary"]["segment_canonical_elapsed"]["full_population"]["mean"], 60)
        self.assertEqual(result["secondary"]["segment_source_hold"]["full_population"]["sum"], 40)

    def test_ebs_sum_of_legs_does_not_count_storage_dwell(self):
        a, b = row(0, "storage_in", 10, 10), row(0, "storage_out", 1000, 10)
        result = audit_tht([a, b], [bag(a, 20, 50), bag(b, 1020, 1040)])
        self.assertEqual(result["business_denominator"], 1)
        self.assertEqual(result["segment_denominator"], 2)
        self.assertEqual(result["paper_tht_total_seconds"], 50)
        self.assertEqual(result["secondary"]["business_sum_canonical_elapsed"]["full_population"]["sum"], 80)
        self.assertEqual(result["secondary"]["business_end_to_end"]["full_population"]["sum"], 1030)
        self.assertEqual(result["secondary"]["business_sum_source_hold"]["full_population"]["sum"], 30)
        system_elapsed = result["secondary"]["business_first_admission_to_final_goal"]["full_population"]["sum"]
        self.assertEqual(system_elapsed, 1020)
        self.assertEqual(system_elapsed, 50 + (1020 - 50))  # sum network + actual EBS inter-leg dwell
        self.assertEqual(1030, system_elapsed + (20 - 10))  # original entry includes first external hold

    def test_incomplete_planned_finish_never_becomes_completion(self):
        a, b, c = row(0), row(1, release=5), row(2, release=200)
        result = audit_tht([a, b, c], [bag(a, 1, 11), bag(b, 20, 50, False), bag(c, completed=False)], 100)
        self.assertTrue(result["passed"])
        self.assertEqual(result["completed_businesses"], 1)
        self.assertEqual(result["censored_businesses"], 2)
        self.assertEqual(result["unreleased_segments"], 1)
        self.assertIsNone(result["paper_tht_total_seconds"])
        self.assertEqual(result["paper_tht"]["full_population"]["count"], 3)
        self.assertEqual(result["paper_tht"]["restricted_full_population"]["sum"], 90)
        self.assertEqual(result["secondary"]["segment_canonical_elapsed"]["restricted_full_population"]["sum"], 106)

    def test_missing_sample_preserves_denominator_and_invalidates_split(self):
        a, b = row(0), row(1)
        result = audit_tht([a, b], [bag(a, 2, 12)], 100)
        self.assertFalse(result["passed"])
        self.assertEqual(result["business_denominator"], 2)
        self.assertEqual(result["missing_segments"], 1)
        self.assertIsNone(result["paper_tht_total_seconds"])
        self.assertIsNone(result["paper_tht"]["restricted_full_population"]["sum"])
        self.assertEqual(result["secondary"]["segment_canonical_elapsed"]["restricted_full_population"]["sum"], 112)

    def test_observed_ceil_is_shared_and_supplied_observation_ignored(self):
        r = row(0, release=.25, original=.25)
        result = audit_tht([r], [bag(r, 2.5, 10.25, observed_finish=99)])
        self.assertEqual(result["paper_tht_total_seconds"], 7.75)
        self.assertEqual(result["observed_ceil_finish"]["paper_tht"]["full_population"]["sum"], 8.5)
        self.assertEqual(result["observed_ceil_finish"]["segment_canonical_elapsed"]["full_population"]["sum"], 10.75)

    def test_missing_ebs_leg_is_not_a_complete_business(self):
        r = row(0, "storage_in")
        with self.assertRaisesRegex(ValueError, "both EBS legs"):
            audit_tht([r], [bag(r, 0, 10)])

    def test_completed_but_future_or_early_admission_is_invalid(self):
        a, b = row(0, release=10, original=10), row(1)
        result = audit_tht([a, b], [bag(a, 9, 20), bag(b, 2, 101)], 100)
        self.assertFalse(result["passed"])
        self.assertEqual(result["completed_segments"], 0)
        self.assertIsNone(result["paper_tht_total_seconds"])


if __name__ == "__main__":
    unittest.main()

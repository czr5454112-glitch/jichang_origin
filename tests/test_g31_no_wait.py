"""Independent no-stop audit rejects the failure modes hidden by totals."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_no_wait.run import audit


PROFILE = {"nodes": [{"location": i, "service_time": 2.0} for i in range(3)],
           "edges": [{"start": 0, "end": 1, "length": 2.0},
                     {"start": 1, "end": 2, "length": 2.0}]}


def row(sid="a", task=0, release=0, deadline=20):
    return {"segment_id": sid, "task_id": task, "pass_time": release,
            "std": deadline, "start": 0, "goal": 2, "leg": "direct"}


def bag(sid="a", start=0):
    return {"segment_id": sid, "admission": start, "finish": start+6,
            "completed": True, "route": [[0, start, start+2],
                                         [1, start+3, start+5],
                                         [2, start+6, start+8]]}


class IndependentAuditTests(unittest.TestCase):
    def test_continuous_service_is_not_wait(self):
        a = audit([row()], [bag()], PROFILE)
        self.assertEqual(a["safety"]["route_violations"], 0)
        self.assertEqual(a["safety"]["internal_extra_wait_max_seconds"], 0)
        self.assertEqual(a["business"]["counts"]["std_strict_causal"], 1)

    def test_wait_hidden_in_edge_is_rejected(self):
        b = bag()
        b["route"][1] = [1, 4, 6]
        b["route"][2] = [2, 7, 9]
        b["finish"] = 7
        a = audit([row()], [b], PROFILE)
        self.assertEqual(a["safety"]["route_violations"], 1)
        self.assertEqual(a["safety"]["internal_extra_wait_max_seconds"], 1)

    def test_post_service_queue_is_rejected(self):
        b = bag()
        b["route"][1] = [1, 3, 6]
        b["route"][2] = [2, 7, 9]
        b["finish"] = 7
        a = audit([row()], [b], PROFILE)
        self.assertEqual(a["safety"]["violation_examples"][0][1], "incorrect_service")

    def test_closed_boundary_and_overlap_detected(self):
        a = audit([row(), row("b", 1, release=2)], [bag(), bag("b", 2)], PROFILE)
        self.assertEqual(a["safety"]["internal_internal_closed_interval_overlaps"], 1)
        a = audit([row(), row("b", 1, release=2.001)], [bag(), bag("b", 2.001)], PROFILE)
        self.assertEqual(a["safety"]["internal_internal_closed_interval_overlaps"], 0)

    def test_no_silent_population_drop(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            audit([row(), row("b", 1)], [bag()], PROFILE)

    def test_unfinished_kept_in_denominator(self):
        b = {"segment_id": "b", "completed": False, "route": []}
        a = audit([row(), row("b", 1)], [bag(), b], PROFILE)
        self.assertEqual(a["business"]["rates"]["std_strict_causal"], .5)
        self.assertEqual(a["segments"]["unfinished"], 1)

    def test_storage_teleport_not_counted_as_causal_success(self):
        incoming = row("a", 0)
        outgoing = row("b", 0, release=1)
        incoming["leg"] = "storage_in"
        outgoing["leg"] = "storage_out"
        a = audit([incoming, outgoing], [bag(), bag("b", 3)], PROFILE)
        self.assertEqual(a["business"]["counts"]["std"], 1)
        self.assertEqual(a["business"]["counts"]["std_strict_causal"], 0)
        self.assertEqual(a["business"]["counts"]["causally_invalid_completed"], 1)


if __name__ == "__main__":
    unittest.main()

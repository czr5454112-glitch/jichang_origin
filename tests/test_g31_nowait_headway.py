"""Physical node and directed-edge invariants on the declared microsecond grid."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.experiments.g31_no_wait.headway_audit import audit_headway


def profile(nodes, edges):
    return dict(nodes=[dict(location=n, service_time=s) for n, s in nodes],
                edges=[dict(start=u, end=v, length=2*t) for u, v, t in edges])


def case(sid, route, release=0):
    row = dict(segment_id=sid, start=route[0][0], goal=route[-1][0], pass_time=release)
    bag = dict(segment_id=sid, route=route, admission=route[0][1], finish=route[-1][1])
    return row, bag


def audit(p, *cases, **kwargs):
    return audit_headway([x[0] for x in cases], [x[1] for x in cases], p, **kwargs)


class HeadwayTests(unittest.TestCase):
    def test_exact_2_seconds_legal_and_source_goal_checked(self):
        p = profile([(0, 2), (1, 2)], [(0, 1, 1)])
        a = case("a", [(0, 0, 2), (1, 3, 5)])
        b = case("b", [(0, 2, 4), (1, 5, 7)])
        result = audit(p, a, b)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["minimum_edge_headway_ticks"], 2000000)

    def test_one_tick_short_is_rejected_without_epsilon(self):
        p = profile([(0, 2), (1, 2)], [(0, 1, 1)])
        a = case("a", [(0, 0, 2), (1, 3, 5)])
        b = case("b", [(0, 1.999999, 3.999999), (1, 4.999999, 6.999999)])
        result = audit(p, a, b)
        self.assertFalse(result["passed"])
        self.assertEqual(result["violation_counts"]["physical_node_overlap"], 2)
        self.assertEqual(result["violation_counts"]["directed_edge_headway"], 1)

    def test_zero_service_endpoints_do_not_exempt_shared_edge(self):
        p = profile([(0, 0), (1, 0)], [(0, 1, 10)])
        a = case("a", [(0, 0, 0), (1, 10, 10)])
        b = case("b", [(0, 1, 1), (1, 11, 11)])
        result = audit(p, a, b)
        self.assertEqual(result["violation_counts"], {"directed_edge_headway": 1})

    def test_goal_must_retain_physical_service(self):
        p = profile([(0, 0), (1, 2)], [(0, 1, 1)])
        a = case("a", [(0, 0, 0), (1, 1, 1)])
        self.assertIn("device_through_time_mismatch", audit(p, a)["violation_counts"])
        self.assertTrue(audit(p, a, strict_endpoint_resources=False)["passed"])

    def test_merging_distinct_edges_is_caught_at_physical_device(self):
        p = profile([(0, 0), (1, 0), (2, 2)], [(0, 2, 10), (1, 2, 5)])
        a = case("a", [(0, 0, 0), (2, 10, 12)])
        b = case("b", [(1, 6, 6), (2, 11, 13)])
        self.assertEqual(audit(p, a, b)["violation_counts"], {"physical_node_overlap": 1})

    def test_no_full_edge_capacity_one_assumption(self):
        p = profile([(0, 0), (1, 0)], [(0, 1, 100)])
        a = case("a", [(0, 0, 0), (1, 100, 100)])
        b = case("b", [(0, 2, 2), (1, 102, 102)])
        self.assertTrue(audit(p, a, b)["passed"])

    def test_exact_integer_reconstruction_detects_hidden_wait(self):
        p = profile([(0, 0), (1, 2), (2, 0)], [(0, 1, 1), (1, 2, 1)])
        a = case("a", [(0, 0, 0), (1, 1, 3), (2, 4.000001, 4.000001)])
        self.assertIn("no_wait_route_time_mismatch", audit(p, a)["violation_counts"])

    def test_offgrid_output_not_silently_rounded_safe(self):
        p = profile([(0, 0), (1, 0)], [(0, 1, 1)])
        a = case("a", [(0, 0, 0), (1, 1.0000001, 1.0000001)])
        self.assertIn("malformed_or_offgrid_route", audit(p, a)["violation_counts"])


if __name__ == "__main__":
    unittest.main()

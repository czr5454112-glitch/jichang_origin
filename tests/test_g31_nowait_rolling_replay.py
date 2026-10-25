"""Adversarial transaction histories whose final route alone can look valid."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.experiments.g31_no_wait.rolling_replay import replay_rolling


def base_fixture():
    profile = dict(nodes=[dict(location=n, service_time=2 if n in (1, 2, 4) else 0)
                          for n in range(7)],
                   edges=[dict(start=u, end=v, length=2 * t) for u, v, t in
                          [(0, 1, 1), (1, 2, 1), (2, 3, 4), (1, 4, 2), (4, 3, 5),
                           (5, 2, 3.5), (2, 6, 1)]])
    old = [[0, 0, 0], [1, 1, 3], [2, 4, 6], [3, 10, 10]]
    new = [[0, 0, 0], [1, 1, 3], [4, 5, 7], [3, 12, 12]]
    rows = [dict(segment_id="a", start=0, goal=3, pass_time=0)]
    bags = [dict(segment_id="a", route=new, admission=0, finish=12, completed=True)]
    source = dict(time=0, kind="source_commit", segment_id="a", committed_route=old,
                  node_reservation_ids=[None, 1, 2, None], edge_reservation_ids=[3, 4, 5],
                  removed_ids=[], old_generation=0, new_generation=1, current_index=0,
                  goal_arrival=10, resource_cleanup_epoch=10)
    replace = dict(time=1, kind="replace_commit", segment_id="a", committed_route=new,
                   node_reservation_ids=[None, 1, 6, None], edge_reservation_ids=[3, 7, 8],
                   removed_ids=[2, 4, 5], old_generation=1, new_generation=2,
                   current_index=1, goal_arrival=12, resource_cleanup_epoch=12)
    events = [source,
              dict(time=1, kind="arrival", segment_id="a", generation=1, index=1, node=1),
              replace,
              dict(time=5, kind="arrival", segment_id="a", generation=2, index=2, node=4),
              dict(time=10, kind="cleanup", segment_id="a", event_generation=1,
                   current_generation=2, valid=False, removed_ids=[]),
              dict(time=12, kind="arrival", segment_id="a", generation=2, index=3, node=3),
              dict(time=12, kind="cleanup", segment_id="a", event_generation=2,
                   current_generation=2, valid=True, removed_ids=[1, 6, 3, 7, 8])]
    return rows, bags, profile, events


def replay(data, *, horizon=12, **kwargs):
    rows, bags, profile, events = deepcopy(data)
    for order, event in enumerate(events, 1):
        event["ledger_order"] = order
    return replay_rolling(rows, bags, profile, events, horizon=horizon, **kwargs)


class RollingReplayTests(unittest.TestCase):
    def test_atomic_swap_with_preserved_current_and_stale_cleanup(self):
        result = replay(base_fixture())
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["current_live_reservations"], 0)

    def test_source_only_unfinished_certificate_remains_valid(self):
        data = base_fixture()
        data[1][0].update(route=data[3][0]["committed_route"], finish=10, completed=False)
        del data[3][1:]
        self.assertTrue(replay(data, horizon=.5)["passed"])

    def test_old_future_cannot_be_used_before_exchange_even_if_final_paths_disjoint(self):
        data = base_fixture()
        route = [[5, .5, .5], [2, 4, 6], [6, 7, 7]]
        data[0].append(dict(segment_id="b", start=5, goal=6, pass_time=.5))
        data[1].append(dict(segment_id="b", route=route, admission=.5, finish=7, completed=True))
        extra = [dict(time=.5, kind="source_commit", segment_id="b", committed_route=route,
                      node_reservation_ids=[None, 20, None], edge_reservation_ids=[21, 22],
                      removed_ids=[], old_generation=0, new_generation=1, current_index=0,
                      goal_arrival=7, resource_cleanup_epoch=8),
                 dict(time=4, kind="arrival", segment_id="b", generation=1, index=1, node=2),
                 dict(time=7, kind="arrival", segment_id="b", generation=1, index=2, node=6),
                 dict(time=8, kind="cleanup", segment_id="b", event_generation=1,
                      current_generation=1, valid=True, removed_ids=[20, 21, 22])]
        data[3].extend(extra)
        data[3].sort(key=lambda e: e["time"])
        result = replay(data)
        self.assertIn("commit_resource_conflict", result["violation_counts"])

    def test_old_current_right_cannot_be_released(self):
        data = base_fixture()
        data[3][2]["removed_ids"].append(1)
        result = replay(data)
        self.assertIn("replacement_removes_wrong_rights", result["violation_counts"])

    def test_internal_wait_in_new_suffix_detected(self):
        data = base_fixture()
        data[3][2]["committed_route"][2] = [4, 5.000001, 7.000001]
        result = replay(data)
        self.assertIn("internal_wait_or_teleport", result["violation_counts"])

    def test_executed_prefix_cannot_be_rewritten(self):
        data = base_fixture()
        data[3][2]["committed_route"][0] = [0, .1, .1]
        self.assertIn("executed_prefix_mutated", replay(data)["violation_counts"])

    def test_generation_must_increment_by_one(self):
        data = base_fixture()
        data[3][2]["new_generation"] = 3
        self.assertIn("replacement_generation_mismatch", replay(data)["violation_counts"])

    def test_arrival_cannot_follow_obsolete_certificate(self):
        data = base_fixture()
        data[3][3].update(time=4, node=2, generation=1)
        result = replay(data)
        self.assertIn("arrival_uses_stale_generation", result["violation_counts"])
        self.assertIn("arrival_not_on_current_certificate", result["violation_counts"])

    def test_stale_cleanup_cannot_remove_current_rights(self):
        data = base_fixture()
        data[3][4]["removed_ids"] = [1]
        self.assertIn("stale_cleanup_removed_rights", replay(data)["violation_counts"])

    def test_goal_arrival_precedes_equal_time_cleanup(self):
        data = base_fixture()
        data[3][-2], data[3][-1] = data[3][-1], data[3][-2]
        self.assertIn("resource_cleaned_before_actual_goal", replay(data)["violation_counts"])

    def test_final_route_cannot_synthesize_unlogged_exchange(self):
        data = base_fixture()
        data[1][0]["route"] = data[3][0]["committed_route"]
        self.assertIn("final_route_not_latest_certificate", replay(data)["violation_counts"])

    def test_missing_due_arrival_and_complete_flag_detected(self):
        data = base_fixture()
        del data[3][-2:]
        result = replay(data)
        self.assertIn("missing_due_physical_arrival", result["violation_counts"])
        self.assertIn("completion_not_backed_by_actual_goal_event", result["violation_counts"])

    def test_resource_ids_are_never_recycled(self):
        data = base_fixture()
        data[3][2]["node_reservation_ids"][2] = 2
        result = replay(data)
        self.assertIn("replacement_suffix_reuses_old_id", result["violation_counts"])

    def test_failed_unplanned_population_is_not_dropped(self):
        data = base_fixture()
        data[0].append(dict(segment_id="unplanned", start=5, goal=6, pass_time=20))
        data[1].append(dict(segment_id="unplanned", route=[], completed=False))
        result = replay(data)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["segment_denominator"], 2)
        self.assertEqual(result["admitted_certificates"], 1)

    def test_replacement_requires_prior_physical_arrival_event(self):
        data = base_fixture()
        del data[3][1]
        self.assertIn("malformed_or_inconsistent_event", replay(data)["violation_counts"])

    def test_replacement_cannot_be_delayed_inside_device(self):
        data = base_fixture()
        data[3][2]["time"] = 1.000001
        self.assertIn("replacement_not_at_exact_current_arrival", replay(data)["violation_counts"])

    def test_source_commit_cannot_use_unreleased_task(self):
        data = base_fixture()
        data[0][0]["pass_time"] = .000001
        self.assertIn("source_commit_before_release", replay(data)["violation_counts"])

    def test_source_equals_goal_still_holds_positive_device(self):
        profile = dict(nodes=[dict(location=0, service_time=2)], edges=[])
        route = [[0, 0, 2]]
        rows = [dict(segment_id="a", start=0, goal=0, pass_time=0)]
        bags = [dict(segment_id="a", route=route, admission=0, finish=0, completed=True)]
        events = [dict(time=0, kind="source_commit", segment_id="a", committed_route=route,
                       node_reservation_ids=[1], edge_reservation_ids=[], removed_ids=[],
                       old_generation=0, new_generation=1, current_index=0, goal_arrival=0,
                       resource_cleanup_epoch=2),
                  dict(time=2, kind="cleanup", segment_id="a", event_generation=1,
                       current_generation=1, valid=True, removed_ids=[1])]
        result = replay((rows, bags, profile, events), horizon=2)
        self.assertTrue(result["passed"], result)

    def test_new_suffix_checks_edge_headway_even_with_zero_node(self):
        data = base_fixture()
        for node in data[2]["nodes"]:
            if node["location"] == 4:
                node["service_time"] = 0
        data[2]["edges"].append(dict(start=5, end=4, length=10))
        data[3][2]["committed_route"][2:] = [[4, 5, 5], [3, 10, 10]]
        data[3][2]["node_reservation_ids"][2] = None
        data[3][2].update(goal_arrival=10, resource_cleanup_epoch=10)
        data[1][0].update(finish=10)
        data[3][-2]["time"] = 10
        data[3][-1].update(time=10, removed_ids=[1, 3, 7, 8])
        route = [[5, 0, 0], [4, 5, 5], [3, 10, 10]]
        data[0].append(dict(segment_id="b", start=5, goal=3, pass_time=0))
        data[1].append(dict(segment_id="b", route=route, admission=0, finish=10, completed=True))
        data[3].extend([
            dict(time=0, kind="source_commit", segment_id="b", committed_route=route,
                 node_reservation_ids=[None, None, None], edge_reservation_ids=[20, 21],
                 removed_ids=[], old_generation=0, new_generation=1, current_index=0,
                 goal_arrival=10, resource_cleanup_epoch=10),
            dict(time=5, kind="arrival", segment_id="b", generation=1, index=1, node=4),
            dict(time=10, kind="arrival", segment_id="b", generation=1, index=2, node=3),
            dict(time=10, kind="cleanup", segment_id="b", event_generation=1,
                 current_generation=1, valid=True, removed_ids=[20, 21])])
        data[3].sort(key=lambda e: e["time"])
        result = replay(data)
        conflicts = [e for e in result["violation_examples"] if e["reason"] == "commit_resource_conflict"]
        self.assertEqual(len(conflicts), 1, result)
        self.assertEqual(conflicts[0]["resource"], ["edge", 4, 3])

    def test_nonincreasing_finish_policy_is_explicit(self):
        result = replay(base_fixture(), require_nonincreasing_finish=True)
        self.assertIn("replacement_extends_finish_against_policy", result["violation_counts"])

    def test_shortened_route_cleanup_then_later_obsolete_cleanup(self):
        data = base_fixture()
        for edge in data[2]["edges"]:
            if (edge["start"], edge["end"]) == (2, 3):
                edge["length"] = 16
        data[3][0]["committed_route"][-1] = [3, 14, 14]
        data[3][0].update(goal_arrival=14, resource_cleanup_epoch=14)
        data[3][4]["time"] = 14
        data[3].sort(key=lambda e: e["time"])
        result = replay(data, horizon=14, require_nonincreasing_finish=True)
        self.assertTrue(result["passed"], result)


if __name__ == "__main__":
    unittest.main()

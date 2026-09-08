"""Pure audit/metric negative cases; no formal native simulation is run."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.eval import run_hca_paper_suite as hca


def fixture():
    canonical = [
        dict(task_id=7, segment_id="7:storage_in", leg="storage_in", start=1, goal=47,
             pass_time=8260.4, original_entry_time=8260.4, std=14000),
        dict(task_id=7, segment_id="7:storage_out", leg="storage_out", start=52, goal=4,
             pass_time=11300, original_entry_time=8260.4, std=14000),
        dict(task_id=9, segment_id="9:direct", leg="direct", start=2, goal=5,
             pass_time=8261.6, original_entry_time=8261.6, std=12000)]
    mapping, releases, plans, completions, terminals, routes = [], [], [], [], [], []
    for row, eid, released, planned, finish in zip(canonical, (7, 10, 9), (8260, 11300, 8261),
                                                (8270, 11301, 8262), (12000, 11900, 8400)):
        m = dict(execution_id=eid, raw_task_id=row["task_id"], leg=row["leg"], start=row["start"], goal=row["goal"],
                 scheduled_release_seconds=row["pass_time"], original_entry_seconds=row["original_entry_time"], deadline_seconds=row["std"])
        mapping.append(m)
        releases.append(dict(task_id=eid, start=row["start"], goal=row["goal"], release_epoch=released))
        plans.append(dict(task_id=eid, start=row["start"], legacy_task_pass_time=0, processed_attempt_epoch=planned))
        completions.append(dict(task_id=eid, finish_epoch=finish))
        terminals.append({**{k: m[k] for k in ("execution_id", "raw_task_id", "leg", "start", "goal", "scheduled_release_seconds")},
            "release_epoch": released, "planned_epoch": planned, "planned_finish_epoch": finish-.2,
            "completion_epoch": finish, "terminal_state": "COMPLETED", "active_route_member": "false",
            "unplanned_member": "false", "source_pending_member": "false"})
        routes.append(dict(task_id=eid, start=row["start"], goal=row["goal"], epoch=planned,
                           finish_time=finish-.2, path=f"{row['start']};{row['goal']}"))
    summary = dict(repeat=1, speed_mps=2.5, start_epoch=8260, max_epochs=90000, max_new_tasks=0,
                   epochs_run=90000, generated_count=3, planned_count=3, completed_count=3,
                   fault_event_count=0, repair_event_count=0, active_fault_count=0,
                   generated_fault_edge_count=0, generated_repair_edge_count=0,
                   active_route_count=0, unfinished_count=0, last_epoch=98259)
    return dict(canonical=canonical, mappings=mapping, releases=releases, plans=plans,
                completions=completions, terminals=terminals, summary=summary, route_rows=routes, raw_order=[7, 9])


def write_native(root, data, load=1):
    raw, canonical, map_path = root / "raw.txt", root / "canonical.jsonl", root / "map.txt"
    raw.write_text("ID EntryTime STD start end\n7 8260.4 14000 1 4\n9 8261.6 12000 2 5\n", encoding="utf-8")
    canonical.write_text("".join(json.dumps(row)+"\n" for row in data["canonical"]), encoding="utf-8")
    original_routes = fixture()["route_rows"]
    edges = [(r["start"], r["goal"], (r["finish_time"]-r["epoch"])*2.5) for r in original_routes]
    edges.append((0, 6, 5))
    lines = ["53 1 0 4"]
    for node in range(53):
        successors = [str(b) for a, b, _ in edges if a == node]
        lines.append(f"{node} 4 0 0 0" + (" " + " ".join(successors) if successors else ""))
    lines += [" ".join(["0"] * 53)] * 53
    lines += [f"{a} {b} {length} 2.5" for a, b, length in edges]
    map_path.write_text("\n".join(lines)+"\n", encoding="utf-8")
    for key, filename in (("mappings", "segment_execution_identity.csv"), ("terminals", "execution_terminal.csv"),
                          ("releases", "release.csv"), ("route_rows", "routes.csv")):
        hca.write_csv(root / filename, data[key])
    hca.write_csv(root / "summary.csv", [data["summary"]])
    (root / "outputstarttime.txt").write_text("".join(f"{r['task_id']} {r['start']} 0 {r['processed_attempt_epoch']}\n" for r in data["plans"]), encoding="utf-8")
    (root / "output.txt").write_text("".join(f"{r['task_id']} {r['finish_epoch']}\n" for r in data["completions"]), encoding="utf-8")
    return {"raw_path": str(raw), "canonical_path": str(canonical), "map_path": str(map_path),
            "raw_sha256": hca.sha(raw), "canonical_sha256": hca.sha(canonical), "map_sha256": hca.sha(map_path),
            "segment_count": 3, "raw_bag_count": 2, "load_factor": load}


class SuiteAuditTests(unittest.TestCase):
    def test_full_2x_timing_and_dual_deadlines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); identity = write_native(root, fixture(), load=2)
            value = hca.recompute_population(identity, root, "a"*64, speed_mps=2.5)
            self.assertTrue(value["full_population_complete"])
            self.assertAlmostEqual(value["metrics"]["tht_scheduled_release_mean_seconds"], (4339.6+138.4)/2)
            self.assertEqual(value["metrics"]["success_std_rate"], 1)
            self.assertEqual(value["metrics"]["success_std_minus_2700_rate"], .5)
            self.assertEqual(value["population_audit"]["planned_route_time_recurrence_count"], 3)

    def test_incomplete_any_load_never_uses_survivor_timing(self):
        data = fixture(); del data["completions"][0]
        data["terminals"][0].update(terminal_state="ACTIVE_ROUTE", active_route_member="true", completion_epoch="")
        data["summary"].update(completed_count=2, active_route_count=1)
        for load in (1, 2):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); identity = write_native(root, data, load=load)
                value = hca.recompute_population(identity, root, "a"*64, speed_mps=2.5)
                self.assertFalse(value["full_population_complete"])
                self.assertTrue(all(value["metrics"][key] is None for key in hca.FORMAL_TIMING))
                self.assertEqual(value["metrics"]["completion_rate"], .5)
                self.assertEqual(value["metrics"]["success_std_rate"], .5)

    def test_duplicate_completion_and_wrong_terminal_membership_rejected(self):
        data = fixture(); data["completions"].append(deepcopy(data["completions"][0]))
        with self.assertRaisesRegex(RuntimeError, "duplicate completion"):
            hca.audit_records(**data)
        data = fixture(); data["terminals"][0]["active_route_member"] = "true"
        with self.assertRaisesRegex(RuntimeError, "actual native membership"):
            hca.audit_records(**data)

    def test_source_goal_dwell_recurrence_and_failed_route_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data = fixture(); data["route_rows"][0]["finish_time"] += 2
            identity = write_native(root, data)
            with self.assertRaisesRegex(RuntimeError, "goal T2 recurrence"):
                hca.recompute_population(identity, root, "a"*64, speed_mps=2.5)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); identity = write_native(root, fixture())
            with self.assertRaisesRegex(RuntimeError, "uses declared failed edge"):
                hca.recompute_population(identity, root, "a"*64, speed_mps=2.5, failed_edges=[[1, 47]])

    def test_speed_and_known_fault_counts_are_part_of_audit_contract(self):
        data = fixture(); data["summary"]["speed_mps"] = 1.5
        with self.assertRaisesRegex(RuntimeError, "speed_mps"):
            hca.audit_records(**data)
        hca.audit_records(**data, expected_speed_mps=1.5)
        data = fixture()
        for key in ("fault_event_count", "active_fault_count", "generated_fault_edge_count"):
            data["summary"][key] = 2
        hca.audit_records(**data, expected_fault_count=2)
        with self.assertRaisesRegex(RuntimeError, "fault_event_count"):
            hca.audit_records(**data, expected_fault_count=1)

    def test_run_spec_rejects_unimplemented_or_mismatched_conditions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); identity = write_native(root, fixture())
            protocol = root / "protocol.md"; protocol.write_text("fixture protocol", encoding="utf-8")
            identity.update(map="map2", seed=104729, fixed_horizon_seconds=98259)
            spec = dict(method=hca.METHOD, family="base", speed_mps=2.5, horizon_seconds=98259,
                        timing_policy="full_population_only", seed=104729,
                        protocol_path=str(protocol), protocol_sha256=hca.sha(protocol))
            hca.validate_spec(spec, identity)
            for change in (dict(timing_policy="old_2x_na"), dict(seed=999), dict(family="dynamic"),
                           dict(failed_edges=[[0, 6]]), dict(bias_fraction=.1), dict(protocol_sha256="a"*64)):
                with self.assertRaises(RuntimeError):
                    hca.validate_spec({**spec, **change}, identity)
            fault = {**spec, "family": "all_day_fault", "scenario_id": "fixture", "fault_notification_epoch": 8260, "failed_edges": [[0, 6]]}
            fault["scenario"] = {"information_contract": "KNOWN_SURVIVING_TOPOLOGY_NO_SOURCE_PREFILTER", "fault_edges": [[0, 6]]}
            hca.validate_spec(fault, identity)
            command = hca.java_run_command(identity | {"storage_in_goal": 47, "storage_out_start": 52}, root,
                                           root, "java", fault)
            self.assertIn("8260:0:6:fault", command)
            self.assertIn("FULL_DAY_KNOWN_EDGE_FAILURE", command)
            for change in (dict(failed_edges=[[0, 6], [0, 6]]), dict(failed_edges=[[6, 0]]),
                           dict(fault_notification_epoch=8261), dict(repairs=[[0, 6]]),
                           dict(initial_failed_edges=[[6, 0]])):
                with self.assertRaises(RuntimeError):
                    hca.validate_spec({**fault, **change}, identity)


if __name__ == "__main__":
    unittest.main()

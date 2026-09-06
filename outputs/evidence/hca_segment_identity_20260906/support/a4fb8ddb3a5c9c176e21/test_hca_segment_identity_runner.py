"""Independent exact-ID population, clock and evidence tests; no full-map runs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.eval import run_hca_segment_identity as hca


def fixture():
    canonical = [
        dict(task_id=7, segment_id="7:storage_in", leg="storage_in", start=1, goal=47,
             pass_time=8260.4, original_entry_time=8260.4, std=14000),
        dict(task_id=7, segment_id="7:storage_out", leg="storage_out", start=52, goal=4,
             pass_time=11300, original_entry_time=8260.4, std=14000),
        dict(task_id=9, segment_id="9:direct", leg="direct", start=2, goal=5,
             pass_time=8261.6, original_entry_time=8261.6, std=10000)]
    mapping, releases, plans, completions, terminals, routes = [], [], [], [], [], []
    for row, eid, released, planned, finish in zip(canonical, (7, 10, 9), (8260, 11300, 8261),
                                                (8270, 11301, 8262), (12000, 11900, 8400)):
        m = dict(execution_id=eid, raw_task_id=row["task_id"], leg=row["leg"], start=row["start"], goal=row["goal"],
                 scheduled_release_seconds=row["pass_time"], original_entry_seconds=row["original_entry_time"], deadline_seconds=row["std"])
        mapping.append(m)
        releases.append(dict(task_id=eid, start=row["start"], goal=row["goal"], release_epoch=released))
        # Native legacy task pass_time is 0, and is deliberately not canonical D.
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


def write_native(root: Path, data: dict, load: float = 1):
    raw = root / "raw.txt"
    raw.write_text("ID EntryTime STD start end\n7 8260.4 14000 1 4\n9 8261.6 10000 2 5\n", encoding="utf-8")
    canonical = root / "canonical.jsonl"
    canonical.write_text("".join(json.dumps(r)+"\n" for r in data["canonical"]), encoding="utf-8")
    map_path = root / "map.txt"
    map_path.write_text("portable byte identity only; graph not executed\n", encoding="utf-8")
    for key, filename in (("mappings", "segment_execution_identity.csv"), ("terminals", "execution_terminal.csv"),
                          ("releases", "release.csv"), ("route_rows", "routes.csv")):
        hca.write_csv(root / filename, data[key])
    hca.write_csv(root / "summary.csv", [data["summary"]])
    (root / "outputstarttime.txt").write_text("".join(f"{r['task_id']} {r['start']} 0 {r['processed_attempt_epoch']}\n"
        for r in data["plans"]), encoding="utf-8")
    (root / "output.txt").write_text("".join(f"{r['task_id']} {r['finish_epoch']}\n" for r in data["completions"]), encoding="utf-8")
    return {"raw_path": str(raw), "canonical_path": str(canonical), "map_path": str(map_path),
            "raw_sha256": hca.sha(raw), "canonical_sha256": hca.sha(canonical), "map_sha256": hca.sha(map_path),
            "segment_count": 3, "raw_bag_count": 2, "load_factor": load}


class ExactIdentityTests(unittest.TestCase):
    def test_overlapping_ebs_remains_two_independent_executions(self):
        lifecycle, audit = hca.audit_records(**fixture())
        self.assertEqual(len(lifecycle), 3)
        self.assertEqual(audit["terminal_accounting_residual"], 0)
        self.assertEqual(audit["ebs_overlap_raw_task_ids"], [7])
        self.assertEqual(lifecycle[0]["legacy_planning_task_pass_time"], 0)

    def test_raw_id_collision_rejected_not_fifo_repaired(self):
        data = fixture()
        data["mappings"][1]["execution_id"] = 7
        with self.assertRaisesRegex(RuntimeError, "duplicate mapping"):
            hca.audit_records(**data)

    def test_duplicate_completion_rejected(self):
        data = fixture()
        data["completions"].append(deepcopy(data["completions"][0]))
        with self.assertRaisesRegex(RuntimeError, "duplicate completion"):
            hca.audit_records(**data)

    def test_terminal_native_membership_required(self):
        data = fixture()
        data["terminals"][0]["active_route_member"] = "true"
        with self.assertRaisesRegex(RuntimeError, "actual native membership"):
            hca.audit_records(**data)

    def test_mapping_drift_rejected(self):
        data = fixture()
        data["mappings"][1]["scheduled_release_seconds"] += 1
        with self.assertRaisesRegex(RuntimeError, "mapping scheduled"):
            hca.audit_records(**data)

    def test_legacy_fractional_early_release_is_preserved(self):
        lifecycle, _ = hca.audit_records(**fixture())
        self.assertAlmostEqual(lifecycle[0]["release_epoch"]-lifecycle[0]["scheduled_pass_time"], -.4)

    def test_release_a_full_second_before_d_rejected(self):
        data = fixture()
        data["releases"][0]["release_epoch"] = 8259
        with self.assertRaisesRegex(RuntimeError, "release violates"):
            hca.audit_records(**data)

    def test_summary_deficit_rejected(self):
        data = fixture()
        data["summary"]["generated_count"] += 1
        with self.assertRaisesRegex(RuntimeError, "summary generated_count"):
            hca.audit_records(**data)

    def test_active_incomplete_is_retained(self):
        data = fixture()
        del data["completions"][0]
        data["terminals"][0].update(terminal_state="ACTIVE_ROUTE", active_route_member="true", completion_epoch="")
        data["summary"].update(completed_count=2, active_route_count=1)
        lifecycle, audit = hca.audit_records(**data)
        self.assertFalse(lifecycle[0]["complete"])
        self.assertEqual(audit["terminal_state_counts"]["ACTIVE_ROUTE"], 1)
        with tempfile.TemporaryDirectory() as temp:
            identity = write_native(Path(temp), data)
            derived = hca.recompute_population(identity, Path(temp), "a"*64)
            self.assertEqual(derived["metrics"]["completed_raw_bag_count"], 1)
            self.assertFalse(derived["full_population_complete"])
            self.assertTrue(all(derived["metrics"][name] is None for name in hca.FORMAL_TIMING))

    def test_unplanned_and_not_released_are_retained(self):
        for state in ("UNPLANNED", "NOT_RELEASED"):
            data = fixture()
            for field in ("plans", "completions", "route_rows"):
                data[field] = [r for r in data[field] if r["task_id"] != 9]
            terminal = data["terminals"][2]
            terminal.update(terminal_state=state, planned_epoch="", planned_finish_epoch="", completion_epoch="",
                            unplanned_member="true" if state == "UNPLANNED" else "false",
                            source_pending_member="true" if state == "NOT_RELEASED" else "false")
            data["summary"].update(planned_count=2, completed_count=2, unfinished_count=int(state == "UNPLANNED"))
            if state == "NOT_RELEASED":
                data["releases"] = [r for r in data["releases"] if r["task_id"] != 9]
                terminal["release_epoch"] = ""
                data["summary"]["generated_count"] = 2
            _, audit = hca.audit_records(**data)
            self.assertEqual(audit["terminal_state_counts"][state], 1)

    def test_cleanup_requires_verified_archive_and_preserves_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            output = root / "outputs/runtime/hca_segment_identity_test/cell"
            (output / "task").mkdir(parents=True)
            (output / "task/8260.txt").write_text("native epoch scratch")
            (output / "segment_lifecycle.csv").write_text("must remain")
            (output / "native_archive").mkdir()
            hca.write_json(output / "native_archive/manifest.json", {"verified": True})
            with patch.object(hca, "ROOT", root), patch.object(hca, "archive_cell", side_effect=RuntimeError("bad archive")):
                with self.assertRaisesRegex(RuntimeError, "bad archive"):
                    hca.cleanup_epoch_scratch(output)
                self.assertTrue((output / "task/8260.txt").exists())
            with patch.object(hca, "ROOT", root), patch.object(hca, "archive_cell"):
                result = hca.cleanup_epoch_scratch(output)
                self.assertEqual(result["removed_file_count"], 1)
                self.assertFalse((output / "task").exists())
                self.assertTrue((output / "segment_lifecycle.csv").exists())
                self.assertEqual(hca.cleanup_epoch_scratch(output), result)

    def test_old_output_namespace_refused(self):
        with self.assertRaisesRegex(RuntimeError, "use a new"):
            hca.validate_output_directory(hca.ROOT / "outputs/runtime/cie_external_baseline_robustness/map2")

    def test_scheduled_d_sum_uses_each_segment_and_portable_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = write_native(Path(temp), fixture())
            derived = hca.recompute_population(identity, Path(temp), "a"*64)
            self.assertAlmostEqual(derived["raw_bag_timings"][0]["tht_scheduled_release_seconds"], 4339.6)
            self.assertAlmostEqual(derived["raw_bag_timings"][1]["tht_scheduled_release_seconds"], 138.4)
            self.assertAlmostEqual(derived["metrics"]["tht_scheduled_release_mean_seconds"], 2239.0)
            self.assertEqual(derived["metrics"]["completed_raw_bag_count"], 2)
            self.assertEqual(derived["population_audit"]["workload_identity_sha256"], "a"*64)
            self.assertFalse((Path(temp) / "population_audit.json").exists())

    def test_two_x_formal_timing_all_na_even_when_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = write_native(Path(temp), fixture(), load=2)
            derived = hca.recompute_population(identity, Path(temp), "a"*64)
            self.assertTrue(derived["full_population_complete"])
            self.assertTrue(all(derived["metrics"][name] is None for name in hca.FORMAL_TIMING))

    def test_portable_input_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = write_native(Path(temp), fixture())
            Path(identity["raw_path"]).write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "remapped raw bytes differ"):
                hca.recompute_population(identity, Path(temp), "a"*64)

    def test_absent_completion_log_requires_zero_native_count(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture()
            identity = write_native(Path(temp), data)
            (Path(temp) / "output.txt").unlink()
            with self.assertRaisesRegex(RuntimeError, "terminal completion_epoch"):
                hca.recompute_population(identity, Path(temp), "a"*64)
            data["completions"] = []
            data["summary"].update(completed_count=0, active_route_count=3)
            for row in data["terminals"]:
                row.update(terminal_state="ACTIVE_ROUTE", active_route_member="true", completion_epoch="")
            identity = write_native(Path(temp), data)
            (Path(temp) / "output.txt").unlink()
            derived = hca.recompute_population(identity, Path(temp), "a"*64)
            self.assertEqual(derived["population_audit"]["absent_zero_event_logs"], ["output.txt"])
            self.assertEqual(derived["metrics"]["completed_raw_bag_count"], 0)

    def test_absent_plan_and_completion_with_native_unplanned_states(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture()
            data["completions"] = []
            data["plans"] = []
            data["summary"].update(planned_count=0, completed_count=0, unfinished_count=3)
            for row in data["terminals"]:
                row.update(terminal_state="UNPLANNED", unplanned_member="true", planned_epoch="", planned_finish_epoch="", completion_epoch="")
            identity = write_native(Path(temp), data)
            (Path(temp) / "output.txt").unlink()
            (Path(temp) / "outputstarttime.txt").unlink()
            # Native empty route export still retains its CSV header.
            (Path(temp) / "routes.csv").write_text("ordinal,task_id,start,goal,epoch,finish_time,path\n")
            derived = hca.recompute_population(identity, Path(temp), "a"*64)
            self.assertEqual(derived["population_audit"]["absent_zero_event_logs"], ["output.txt", "outputstarttime.txt"])
            self.assertEqual(derived["population_audit"]["terminal_state_counts"]["UNPLANNED"], 3)


if __name__ == "__main__":
    unittest.main()

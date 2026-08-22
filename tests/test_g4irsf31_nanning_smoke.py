from __future__ import annotations

import json
from pathlib import Path

from scripts.eval import run_g4irsf31_nanning_smoke as smoke


def _workload_fixture(root: Path) -> Path:
    task_dir = root / "tasks"
    task_dir.mkdir()
    raw = task_dir / "raw.txt"
    canonical = task_dir / "canonical.jsonl"
    raw.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "10 100 6000 0 4 U L\n"
        "11 200 1000 0 4 U L\n",
        encoding="utf-8",
    )
    rows = [
        {
            "segment_id": "10:storage_in",
            "task_id": 10,
            "pass_time": 100.0,
            "std": 6000.0,
            "start": 0,
            "goal": 2,
            "leg": "storage_in",
        },
        {
            "segment_id": "10:storage_out",
            "task_id": 10,
            "pass_time": 3300.0,
            "std": 6000.0,
            "start": 2,
            "goal": 4,
            "leg": "storage_out",
        },
        {
            "segment_id": "11:direct",
            "task_id": 11,
            "pass_time": 200.0,
            "std": 1000.0,
            "start": 0,
            "goal": 4,
            "leg": "direct",
        },
    ]
    canonical.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    manifest = {
        "scale": 1,
        "raw_output": str(raw),
        "canonical_output": str(canonical),
        "lifecycle": {
            "early_bag_threshold_seconds": 4800.0,
            "storage_out_lead_seconds": 2700.0,
            "storage_in_goal": 2,
            "storage_out_start": 2,
        },
    }
    (task_dir / "nanning_1x_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return task_dir


def test_earliest_selection_keeps_both_storage_legs(tmp_path: Path) -> None:
    selection = smoke.load_selection(
        scale=1,
        earliest_raw_bags=1,
        task_dir=_workload_fixture(tmp_path),
    )

    assert selection.task_ids == (10,)
    assert [row["leg"] for row in selection.canonical_rows] == [
        "storage_in",
        "storage_out",
    ]
    raw_path, canonical_path = smoke.write_selection(selection, tmp_path / "out")
    assert len(raw_path.read_text(encoding="utf-8").splitlines()) == 2
    assert len(canonical_path.read_text(encoding="utf-8").splitlines()) == 2


def test_smoke_orchestrator_uses_same_population_speed_and_storage_role(
    tmp_path: Path, monkeypatch
) -> None:
    task_dir = _workload_fixture(tmp_path)
    captured = {}

    def fake_hca(selection, **kwargs):
        captured["hca"] = (selection.task_ids, kwargs)
        return {
            "all_selected_segments_completed": True,
            "safety": {"pass": True},
            "counts": {"expected_segment_count": 2},
        }

    def fake_s4(selection, **kwargs):
        captured["s4"] = (selection.task_ids, kwargs)
        return {
            "all_selected_segments_completed": True,
            "safety": {"pass": True},
            "counts": {"expected_segment_count": 2},
        }

    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.write_bytes(b"fixture")
    monkeypatch.setattr(smoke, "run_hca", fake_hca)
    monkeypatch.setattr(smoke, "run_s4", fake_s4)

    report = smoke.run_smoke(
        scale=1,
        earliest_raw_bags=1,
        task_dir=task_dir,
        map_profile_path=tmp_path / "map.json",
        legacy_map_path=tmp_path / "map.txt",
        output_dir=tmp_path / "smoke",
        binary=binary,
    )

    assert report["status"] == "PASS"
    assert report["speed_mps"] == smoke.SPEED_MPS == 2.5
    assert report["selection"]["selected_raw_bag_count"] == 1
    assert report["selection"]["selected_segment_count"] == 2
    assert report["storage_role"] == {
        "storage_in_goal": 2,
        "storage_out_start": 2,
        "same_node": True,
    }
    assert captured["hca"][0] == captured["s4"][0] == (10,)


def test_s4_summary_records_completion_and_structural_safety(
    tmp_path: Path, monkeypatch
) -> None:
    task_dir = _workload_fixture(tmp_path)
    selection = smoke.load_selection(
        scale=1, earliest_raw_bags=1, task_dir=task_dir
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": "fixture",
                "start_nodes": [0],
                "end_nodes": [4],
                "nodes": [
                    {"location": 0, "node_type": 1, "service_time": 0, "outgoing": [2]},
                    {"location": 1, "node_type": 4, "service_time": 0, "outgoing": []},
                    {"location": 2, "node_type": 7, "service_time": 0, "outgoing": [3]},
                    {"location": 3, "node_type": 4, "service_time": 0, "outgoing": [4]},
                    {"location": 4, "node_type": 2, "service_time": 0, "outgoing": []},
                ],
                "edges": [
                    {"start": 0, "end": 2, "length": 1, "speed": 2},
                    {"start": 2, "end": 3, "length": 1, "speed": 2},
                    {"start": 3, "end": 4, "length": 1, "speed": 2},
                ],
            }
        ),
        encoding="utf-8",
    )
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.write_bytes(b"fixture")
    captured = {}

    def fake_runtime(**request):
        captured.update(request)
        return {
            "summary": {
                "requested_count": 2,
                "completed_count": 2,
                "failed_count": 0,
                "reservation_conflicts": 0,
                "physical_fault_edge_entry_violation_count": 0,
                "unresolved_deadlock_count": 0,
                "event_count": 20,
                "decision_count": 4,
                "event_limit_reached": False,
                "time_limit_reached": False,
            }
        }

    monkeypatch.setattr(
        smoke.cpp_backend, "g4irsf11_event_runtime_from_records", fake_runtime
    )
    result = smoke.run_s4(
        selection,
        map_profile_path=profile_path,
        binary=binary,
        max_events=1000,
    )

    assert result["all_selected_segments_completed"] is True
    assert result["safety"]["pass"] is True
    assert captured["storage_source_nodes"] == [2]
    assert {row[3] for row in captured["edge_records"]} == {2.5}
    assert captured["enable_s4_local_potential_descent_guard"] is True
    assert (
        captured["enable_s4_direct_neighbor_merge_calendar_visibility"] is True
    )
    assert captured["complete_on_goal_arrival"] is True

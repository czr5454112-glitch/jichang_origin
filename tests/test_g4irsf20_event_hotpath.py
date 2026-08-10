from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records
from scripts.eval import run_g4irsf20_event_hotpath as hotpath


ROOT = Path(__file__).resolve().parents[1]


def _wrapper_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], list[tuple[object, ...]]]:
    captured: list[tuple[object, ...]] = []

    def fake_runtime(*args: object) -> dict[str, object]:
        captured.append(args)
        return {"summary": {}}

    fake_module = SimpleNamespace(
        __file__=str(Path(__file__).resolve()),
        g4irsf11_event_runtime_from_records=fake_runtime,
    )
    monkeypatch.setattr(
        cpp_backend,
        "load_cpp_module",
        lambda search_path=None: fake_module,
    )
    nodes, edges, heuristic = canonical_graph_records()
    common: dict[str, object] = {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": [("g20-wrapper", 1, 0.0, 100.0, 3, 47, "fixture")],
        "event_semantics": "E4",
        "resource_semantics": "R3",
        "enable_source_admission": False,
        "admission_mode": "off",
        "pibt_mode": "P2",
        "priority_mode": "Q0",
        "scorer_mode": "S4",
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "J2",
    }
    return common, captured


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (None, TypeError),
        (1, TypeError),
        (True, TypeError),
        ("E3", ValueError),
        ("e1", ValueError),
    ],
)
def test_wrapper_rejects_invalid_hotpath_policy(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
    error: type[Exception],
) -> None:
    common, _captured = _wrapper_fixture(monkeypatch)
    with pytest.raises(error, match="g4irsf20_event_hotpath_policy"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            g4irsf20_event_hotpath_policy=value,  # type: ignore[arg-type]
        )


def test_wrapper_e0_keeps_exact_legacy_call_and_e1_e2_append_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common, captured = _wrapper_fixture(monkeypatch)
    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf20_event_hotpath_policy="E0",
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf20_event_hotpath_policy="E1",
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf20_event_hotpath_policy="E2",
    )

    omitted, explicit_e0, e1, e2 = captured
    assert omitted == explicit_e0
    assert e1[-1] == "E1"
    assert e2[-1] == "E2"
    assert e1[:-1] == e2[:-1]
    assert len(e1) == len(e2) == len(omitted) + 12


def _input_loader(
    scale: int,
    root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    del root
    rows = [
        {
            "segment_id": f"fixture-{scale}-{index}",
            "task_id": scale * 100 + index,
            "pass_time": float(index),
            "original_entry_time": float(index),
            "std": 100.0,
            "start": 3,
            "goal": 47,
            "source": "fixture",
        }
        for index in range(2)
    ]
    return rows, {
        "protocol": "fixture_fixed_map",
        "segments": len(rows),
        "scale": scale,
        "topology_changed": False,
        "tth_denominator": "original_entry_time_tth",
    }


def _safety_summary(*, completed: int, event_count: int, beacons: int) -> dict[str, Any]:
    return {
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "scorer_mode": hotpath.g19_capacity.SCORER_MODES["S4"],
        "completed_count": completed,
        "failed_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "unresolved_deadlock_count": 0,
        "runtime_full_astar_calls": 0,
        "runtime_full_cie_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "priority_global_scan_count": 0,
        "scorer_runtime_global_scan_count": 0,
        "microphase_runtime_global_scan_count": 0,
        "first_edge_credit_global_scan_count": 0,
        "priority_future_route_input_count": 0,
        "scorer_future_route_input_count": 0,
        "first_edge_credit_future_route_count": 0,
        "scorer_future_schedule_input_count": 0,
        "full_future_routes_stored": 0,
        "bag_future_path_field_present": False,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "bag_release_event_count": 2,
        "event_count": event_count,
        "congestion_beacon_update_event_count": beacons,
    }


def _full_payload(request: Mapping[str, Any], *, events: int, beacons: int) -> dict[str, Any]:
    policy = str(request["g4irsf20_event_hotpath_policy"])
    summary = _safety_summary(completed=2, event_count=events, beacons=beacons)
    if policy != "E0":
        summary.update(
            g4irsf20_event_hotpath_policy=policy,
            g4irsf20_redundant_beacon_suppressed_count=20,
            g4irsf20_same_state_beacon_suppressed_count=10 if policy == "E2" else 0,
        )
    bags = []
    for segment_id, task_id, release, _deadline, start, goal, _source in request[
        "bag_records"
    ]:
        bags.append(
            {
                "segment_id": segment_id,
                "task_id": task_id,
                "start": start,
                "goal": goal,
                "final_node": goal,
                "release_time": release,
                "admitted_time": release + 1.0,
                "finish_time": release + 5.0,
                "junction_queue_wait_seconds": 0.5,
                "merge_grant_wait_seconds": 0.25,
                "decision_count": 2,
                "retry_count": 0,
                "loop_count": 0,
                "short_history": [start, goal],
                "completed": True,
                "failure_reason": "",
            }
        )
    return {"summary": summary, "bags": bags}


def _progress(
    *,
    wall: float,
    events: int,
    completed: int,
    beacons: int,
    policy: str,
) -> dict[str, Any]:
    row = {
        "schema": "czr005.g4irsf19.runtime_progress.v1",
        "phase": "READY",
        "wall_seconds": wall,
        "simulated_time": wall * 10.0,
        "requested_bags": 2,
        "released_bags": 2 if wall else 0,
        "completed_bags": completed,
        "failed_bags": 0,
        "terminal_bags": completed,
        "current_backlog": max(2 - completed, 0),
        "event_total": events,
        "heap_size": 0,
        "event_type_counts": {
            name: (beacons if name == "congestion_beacon_update" else 0)
            for name in hotpath.g19_capacity.EVENT_TYPES
        },
        "source_admission_attempt_count": 0,
        "source_admission_admitted_count": 0,
        "source_admission_hold_count": 0,
        "stale_event_count": 0,
        "retry_count_by_reason": {},
        "duplicate_wakeup_count": 0,
        "coalesced_event_count": 0,
    }
    if policy != "E0":
        row.update(
            g4irsf20_event_hotpath_policy=policy,
            g4irsf20_redundant_beacon_suppressed_count=20,
            g4irsf20_same_state_beacon_suppressed_count=10 if policy == "E2" else 0,
        )
    return row


def _fake_executor(**request: Any) -> dict[str, Any]:
    policy = str(request["g4irsf20_event_hotpath_policy"])
    scale = int(str(request["scenario"]).split("_")[-2][:-1])
    events_by_policy = {"E0": 100, "E1": 70, "E2": 60}
    beacons_by_policy = {"E0": 40, "E1": 20, "E2": 10}
    if scale in hotpath.FULL_SCALES:
        return _full_payload(
            request,
            events=events_by_policy[policy],
            beacons=beacons_by_policy[policy],
        )
    bounded_events = {"E0": 1_000, "E1": 900, "E2": 800}[policy]
    bounded_complete = {"E0": 10, "E1": 12, "E2": 15}[policy]
    initial = _progress(wall=0.0, events=0, completed=0, beacons=0, policy=policy)
    final = _progress(
        wall=10.0,
        events=bounded_events,
        completed=bounded_complete,
        beacons=beacons_by_policy[policy] * 10,
        policy=policy,
    )
    summary = _safety_summary(
        completed=bounded_complete,
        event_count=bounded_events,
        beacons=beacons_by_policy[policy] * 10,
    )
    if policy != "E0":
        summary.update(
            g4irsf20_event_hotpath_policy=policy,
            g4irsf20_redundant_beacon_suppressed_count=20,
            g4irsf20_same_state_beacon_suppressed_count=10 if policy == "E2" else 0,
        )
    return {
        "execution_status": "BOUNDED_PROGRESS",
        "stop_reason": "WALL_LIMIT",
        "progress_history": [initial, final],
        "progress": final,
        "summary": summary,
    }


def test_request_contract_is_full_for_1x_2x_and_bounded_for_4x(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.touch()
    rows, _ = _input_loader(1, tmp_path)
    full = hotpath.build_native_request(
        rows,
        scale=1,
        policy="E0",
        binary=binary,
        root=ROOT,
        bounded_wall_seconds=60.0,
        check_events=123,
    )
    bounded = hotpath.build_native_request(
        rows,
        scale=4,
        policy="E2",
        binary=binary,
        root=ROOT,
        bounded_wall_seconds=60.0,
        check_events=123,
    )

    assert full["summary_only"] is False
    assert "bounded_wall_seconds" not in full
    assert "bounded_check_every_events" not in full
    assert full["g4irsf20_event_hotpath_policy"] == "E0"
    assert bounded["summary_only"] is True
    assert bounded["bounded_wall_seconds"] == 60.0
    assert bounded["bounded_check_every_events"] == 123
    assert bounded["g4irsf20_event_hotpath_policy"] == "E2"
    assert "scorer_model_path" not in full
    assert "scorer_model_path" not in bounded


def test_fake_paired_ladder_counts_hotpath_and_ignores_event_delta_for_semantics(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.touch()
    json_path = tmp_path / "event.json"
    csv_path = tmp_path / "event.csv"
    report_path = tmp_path / "event.md"
    best_path = tmp_path / "best.json"
    campaign = hotpath.run_campaign(
        binary=binary,
        root=ROOT,
        json_path=json_path,
        csv_path=csv_path,
        report_path=report_path,
        best_policy_path=best_path,
        executor=_fake_executor,
        input_loader=_input_loader,
    )

    assert campaign["status"] == "COMPLETE"
    assert len(campaign["rows"]) == 9
    comparisons = {
        (row["scale"], row["policy"]): row for row in campaign["comparisons"]
    }
    for scale in hotpath.FULL_SCALES:
        for policy in ("E1", "E2"):
            pair = comparisons[(scale, policy)]
            assert pair["event_count_delta_vs_e0"] < 0
            assert pair["action_semantics_equal_to_e0"] is True
            assert pair["tth_semantics_equal_to_e0"] is True
            assert pair["route_wait_semantics_equal_to_e0"] is True
            assert pair["hard_safety_equal_to_e0"] is True
            assert pair["full_semantic_gate_pass"] is True

    rows = {(row["scale"], row["policy"]): row for row in campaign["rows"]}
    assert rows[(1, "E1")]["hotpath"]["redundant_beacon_suppressed_count"] == 20
    assert rows[(1, "E1")]["hotpath"]["same_state_beacon_suppressed_count"] == 0
    assert rows[(1, "E2")]["hotpath"]["same_state_beacon_suppressed_count"] == 10
    assert comparisons[(4, "E2")]["completion_improvement_fraction"] == pytest.approx(0.5)
    assert campaign["selection"]["selected_policy"] == "E2"
    selected = next(
        row
        for row in campaign["selection"]["candidates"]
        if row["policy"] == "E2"
    )
    assert selected["bounded_work_nonregression_pass"] is True

    assert json_path.is_file() and csv_path.is_file()
    assert report_path.is_file() and best_path.is_file()
    persisted = json.loads(json_path.read_text(encoding="utf-8"))
    def keys(value: object) -> list[str]:
        if isinstance(value, dict):
            return [str(key) for key in value] + [
                nested for child in value.values() for nested in keys(child)
            ]
        if isinstance(value, list):
            return [nested for child in value for nested in keys(child)]
        return []

    persisted_keys = [name.lower() for name in keys(persisted)]
    assert "bags" not in persisted_keys
    assert "decision_trace" not in persisted_keys
    assert not any("sha256" in name or "hash" in name for name in persisted_keys)
    assert json.loads(best_path.read_text(encoding="utf-8"))["selected_policy"] == "E2"
    assert len(list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))) == 9
    assert "bounded live-frontier observation" in report_path.read_text(encoding="utf-8")


def test_real_small_graph_preserves_semantics_when_g20_native_is_available() -> None:
    if not cpp_backend.is_available():
        pytest.skip("native extension is not available")
    module = cpp_backend.load_cpp_module()
    native_function = module.g4irsf11_event_runtime_from_records
    if "g4irsf20_event_hotpath_policy" not in (native_function.__doc__ or ""):
        pytest.skip("available native extension predates the G20 append-only ABI")
    binary = Path(module.__file__).resolve()
    rows = [
        {
            "segment_id": f"g20-native-{index}",
            "task_id": 90_000 + index,
            "pass_time": 0.0,
            "original_entry_time": 0.0,
            "std": 1_000.0,
            "start": 3,
            "goal": 47,
            "source": "native-fixture",
        }
        for index in range(2)
    ]
    descriptor = {
        "protocol": "canonical_small_graph",
        "segments": 2,
        "scale": 1,
        "topology_changed": False,
        "tth_denominator": "original_entry_time_tth",
    }
    results = []
    semantics = {}
    for policy in hotpath.POLICIES:
        result, semantic = hotpath.execute_job(
            rows,
            descriptor,
            scale=1,
            policy=policy,
            binary=binary,
            root=ROOT,
            bounded_wall_seconds=60.0,
            check_events=64,
            executor=cpp_backend.g4irsf11_event_runtime_from_records,
        )
        results.append(result)
        semantics[(1, policy)] = semantic
    # Pair helper expects all scales; direct projection checks keep this smoke tiny.
    assert semantics[(1, "E1")]["actions"] == semantics[(1, "E0")]["actions"]
    assert hotpath._close(semantics[(1, "E1")]["tth"], semantics[(1, "E0")]["tth"])
    assert semantics[(1, "E2")]["hard_safety"] == semantics[(1, "E0")]["hard_safety"]
    by_policy = {row["policy"]: row for row in results}
    assert by_policy["E1"]["hotpath"]["redundant_beacon_suppressed_count"] > 0
    assert by_policy["E2"]["hotpath"]["total_beacon_suppressed_count"] > 0


def test_real_native_rejects_unverified_beacon_extension_combinations() -> None:
    if not cpp_backend.is_available():
        pytest.skip("native extension is not available")
    module = cpp_backend.load_cpp_module()
    native_function = module.g4irsf11_event_runtime_from_records
    if "g4irsf20_event_hotpath_policy" not in (native_function.__doc__ or ""):
        pytest.skip("available native extension predates the G20 append-only ABI")

    nodes, edges, heuristic = canonical_graph_records()
    common = {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": [("g20-guard", 1, 0.0, 100.0, 3, 47, "fixture")],
    }
    with pytest.raises(ValueError, match="cannot be combined"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            g4irsf20_event_hotpath_policy="E1",
            enable_g4irsf17_source_wait_telemetry=True,
        )
    with pytest.raises(ValueError, match="cannot be combined"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            **common,
            g4irsf20_event_hotpath_policy="E2",
            enable_source_admission=True,
            admission_mode="expiring_first_edge_credit",
        )

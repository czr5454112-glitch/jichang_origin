from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf24_native_race as g24
from scripts.eval import run_g4irsf27_fault_values as g27


def _nodes(count: int) -> list[tuple[object, ...]]:
    return [(node, 1, 0.0, 1, 0, []) for node in range(count)]


def _prefix(rows: list[dict[str, object]]) -> harness.InputPrefix:
    tasks = {int(row["task_id"]) for row in rows}
    return harness.InputPrefix(
        size_segments=len(rows),
        rows=tuple(rows),
        prefix_sha256="",
        raw_bag_count=len(tasks),
        first_segment_id=str(rows[0]["segment_id"]),
        last_segment_id=str(rows[-1]["segment_id"]),
    )


def _row(
    segment_id: str,
    task_id: int,
    start: int,
    goal: int,
) -> dict[str, object]:
    return {
        "segment_id": segment_id,
        "task_id": task_id,
        "original_entry_time": 0.0,
        "pass_time": 0.0,
        "start": start,
        "goal": goal,
        "std": 100.0,
    }


def test_fault_bellman_fixed_point_terminates_on_cycle_and_marks_unreachable() -> None:
    edges = [
        (0, 1, 1.0, 1.0),
        (1, 0, 1.0, 1.0),
        (1, 2, 1.0, 1.0),
        (2, 3, 1.0, 1.0),
    ]

    values, audit = g27.local_bellman_fixed_point(
        _nodes(4), edges, removed_edges=[(1, 2)], goals=[3]
    )

    assert math.isinf(values[3][0])
    assert math.isinf(values[3][1])
    assert values[3][2] == pytest.approx(1.0)
    assert values[3][3] == 0.0
    assert audit["maximum_rounds"] <= 4
    assert audit["per_goal"]["3"]["unreachable_node_count"] == 2


def test_structural_artifact_uses_graph_derived_finite_penalty() -> None:
    edges = [
        (0, 1, 2.0, 1.0),
        (1, 2, 3.0, 1.0),
        (0, 2, 4.0, 1.0),
    ]
    distances = {2: {0: math.inf, 1: 3.0, 2: 0.0}}
    heuristic = [
        [0.0, 2.0, 4.0],
        [10.0, 0.0, 3.0],
        [10.0, 10.0, 0.0],
    ]

    artifact, contract = g27.structural_td_artifact(
        _nodes(3), edges, heuristic, distances
    )

    assert artifact["mode"] == "td"
    assert artifact["min_support"] == 1
    assert artifact["margin_seconds"] == 0.0
    assert artifact["detour_allowance_seconds"] == pytest.approx(9.0)
    assert all(row["residual_seconds"] == 0.0 for row in artifact["edge_residuals"])
    assert all(row["support"] == 1 for row in artifact["edge_residuals"])
    unreachable = next(
        row
        for row in artifact["value_residuals"]
        if row["node"] == 0 and row["goal"] == 2
    )
    assert contract["unreachable_penalty_seconds"] == pytest.approx(13.0)
    assert unreachable["residual_seconds"] == pytest.approx(9.0)
    assert unreachable["support"] == 1


def test_prepare_request_keeps_fault_values_off_but_enables_local_fifo_without_fault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prefix = _prefix([_row("s0", 1, 0, 2)])
    base_request = {"bag_records": [("baseline",)]}
    monkeypatch.setattr(
        g27.g26,
        "build_s4_request",
        lambda case, supplied, binary: (dict(base_request), {"fault": {"mode": "no_fault"}}),
    )

    request, runtime_rows, rejected, evidence = g27.prepare_request(
        {"seed_edges": []}, prefix, binary=tmp_path / "unused.pyd"
    )

    assert request == {
        **base_request,
        "queue_discipline": g27.G27_QUEUE_DISCIPLINE,
    }
    assert "g4irsf24_dlp_artifact" not in request
    assert len(runtime_rows) == 1
    assert rejected == ()
    assert evidence["activation"] == "FAULT_VALUES_DLP_EXACT_OFF_NO_FAULT_CASE"
    assert evidence["active_policy"] == {
        "choice": "local_junction_fifo_arbitration",
        "queue_discipline": "fifo",
        "scope": "one_junction_local_queue",
    }


def test_source_reject_filters_only_unreachable_segment_of_same_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prefix = _prefix(
        [
            _row("unreachable-leg", 1, 0, 3),
            _row("reachable-leg", 1, 2, 3),
            _row("other-bag", 2, 2, 3),
        ]
    )
    edges = [
        (0, 1, 1.0, 1.0),
        (1, 2, 1.0, 1.0),
        (2, 3, 1.0, 1.0),
    ]
    heuristic = [[0.0] * 4 for _ in range(4)]

    def fake_build(case, supplied, *, binary):
        return {
            "node_records": _nodes(4),
            "edge_records": edges,
            "heuristic_time": heuristic,
            "bag_records": [],
        }, {"fault": {"fixed_runtime_limit": 98_259.0}}

    monkeypatch.setattr(g27.g26, "build_s4_request", fake_build)
    request, runtime_rows, rejected, evidence = g27.prepare_request(
        {"seed_edges": [[1, 2]]}, prefix, binary=tmp_path / "unused.pyd"
    )

    assert [row["segment_id"] for row in rejected] == ["unreachable-leg"]
    assert [row["segment_id"] for row in runtime_rows] == [
        "reachable-leg",
        "other-bag",
    ]
    assert [record[0] for record in request["bag_records"]] == [
        "reachable-leg",
        "other-bag",
    ]
    assert request["g4irsf24_dlp_artifact"]["mode"] == "td"
    assert request["queue_discipline"] == "fifo"
    assert evidence["active_policy"]["queue_discipline"] == "fifo"
    assert evidence["source_rejected_unreachable_segment_count"] == 1


def test_service_aware_fault_residual_cancels_to_travel_only_structural_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prefix = _prefix([_row("reachable", 1, 0, 2)])
    nodes = [
        (0, 1, 0.0, 1, 0, [1, 2]),
        (1, 1, 4.0, 1, 0, [2]),
        (2, 1, 0.0, 1, 0, []),
    ]
    edges = [
        (0, 1, 1.0, 1.0),
        (1, 2, 1.0, 1.0),
        (0, 2, 3.0, 1.0),
    ]

    monkeypatch.setattr(
        g27.g26,
        "build_s4_request",
        lambda case, supplied, binary: (
            {
                "node_records": nodes,
                "edge_records": edges,
                "heuristic_time": [[77.0] * 3 for _ in range(3)],
                "bag_records": [],
            },
            {"fault": {"fixed_runtime_limit": 98_259.0}},
        ),
    )

    request, runtime_rows, rejected, evidence = g27.prepare_request(
        {"seed_edges": [[0, 2]]},
        prefix,
        binary=tmp_path / "unused.pyd",
        service_aware_potential=True,
    )

    assert len(runtime_rows) == 1
    assert rejected == ()
    static = request["heuristic_time"][0][2]
    residual = next(
        row["residual_seconds"]
        for row in request["g4irsf24_dlp_artifact"]["value_residuals"]
        if row["node"] == 0 and row["goal"] == 2
    )
    # The surviving 0->1->2 travel-only structural distance is two seconds.
    assert static + residual == pytest.approx(2.0)
    assert static != pytest.approx(77.0)
    assert evidence["service_aware_potential"]["enabled"] is True
    assert evidence["artifact_contract"]["dynamic_distance_semantics"] == (
        "surviving_edge_travel_time_only"
    )
    assert evidence["artifact_contract"]["residual_reference"] == (
        "SERVICE_AWARE_STATIC_LOCAL_POTENTIAL"
    )


def _safe_summary(*, completed: int = 2) -> dict[str, object]:
    summary: dict[str, object] = {
        name: 0 for name in g24.HARD_SAFETY_ZERO_FIELDS
    }
    summary.update({name: False for name in g24.HARD_SAFETY_FALSE_FIELDS})
    summary.update(
        completed_count=completed,
        fault_event_count=1,
        repair_event_count=0,
        time_limit_reached=True,
    )
    return summary


def test_custom_gate_accounts_source_reject_and_keeps_hard_safety_strict() -> None:
    bags = [
        {"segment_id": "s1", "completed": True},
        {"segment_id": "s2", "completed": True},
    ]
    admitted = g27.g27_source_admission_safety(
        _safe_summary(),
        selected_segment_count=3,
        runtime_requested_segment_count=2,
        source_rejected_segment_count=1,
        seed_fault_count=1,
        expected_runtime_segment_ids=["s1", "s2"],
        runtime_bags=bags,
    )
    failed = g27.g27_source_admission_safety(
        _safe_summary(completed=1),
        selected_segment_count=3,
        runtime_requested_segment_count=2,
        source_rejected_segment_count=1,
        seed_fault_count=1,
        expected_runtime_segment_ids=["s1", "s2"],
        runtime_bags=bags,
    )

    assert admitted["pass"] is True
    assert admitted["claim_boundary"]["is_original_g26_strict_gate"] is False
    assert failed["pass"] is False


def test_source_rejection_is_merged_as_failed_raw_bag_leg() -> None:
    rows = [
        _row("task1-ok", 1, 0, 1),
        _row("task1-rejected", 1, 0, 1),
        _row("task2-ok", 2, 0, 1),
    ]
    completed = [
        {
            "segment_id": segment_id,
            "task_id": task_id,
            "completed": True,
            "release_time": 0.0,
            "admitted_time": 0.0,
            "finish_time": 5.0,
        }
        for segment_id, task_id in (("task1-ok", 1), ("task2-ok", 2))
    ]
    combined = completed + g27._synthetic_source_rejections([rows[1]])

    outcome = g27.g26.summarize_paper_outcome(
        rows, combined, total_raw_bags=2
    )

    assert outcome["completed_raw_bag_count"] == 1
    assert outcome["success"]["primary_completed_raw_bags"]["rate"] == 0.5


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (g27.ADMITTED_STATUS, 0),
        ("FAILED_G27_ADMISSION_GATE", 2),
    ],
)
def test_case_cli_atomically_persists_main_gate_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: str,
    expected_code: int,
) -> None:
    output = tmp_path / "case.json"
    monkeypatch.setattr(
        g27,
        "execute_case",
        lambda case_id, segments, binary, service_aware_potential: {
            "schema": g27.SCHEMA,
            "status": status,
            "case": {"case_id": case_id},
        },
    )

    code = g27.main(
        [
            "case",
            "--case-id",
            "t5_5_fault_single_4",
            "--segments",
            "512",
            "--binary",
            str(tmp_path / "runtime.pyd"),
            "--output",
            str(output),
        ]
    )

    assert code == expected_code
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == status
    assert not list(tmp_path.glob(".*.tmp"))


def test_case_cli_forwards_explicit_service_aware_option(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    output = tmp_path / "g28_fault_case.json"

    def fake_execute(
        case_id: str,
        *,
        segments: int,
        binary: Path,
        service_aware_potential: bool,
    ) -> dict[str, object]:
        captured.update(
            case_id=case_id,
            segments=segments,
            binary=binary,
            service_aware_potential=service_aware_potential,
        )
        return {
            "schema": g27.SCHEMA,
            "status": g27.ADMITTED_STATUS,
            "case": {"case_id": case_id},
        }

    monkeypatch.setattr(g27, "execute_case", fake_execute)

    assert g27.main(
        [
            "case",
            "--case-id",
            "t5_5_fault_single_4",
            "--segments",
            "512",
            "--binary",
            str(tmp_path / "runtime.pyd"),
            "--output",
            str(output),
            "--service-aware-potential",
        ]
    ) == 0
    assert captured["service_aware_potential"] is True

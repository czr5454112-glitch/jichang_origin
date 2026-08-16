from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf28_service_potential as g28


def _nodes() -> list[tuple[object, ...]]:
    return [
        (0, 1, 0.0, 0, 0, [1, 2]),
        (1, 1, 4.0, 0, 0, [3]),
        (2, 1, 1.0, 0, 0, [3]),
        (3, 2, 0.0, 0, 0, []),
    ]


def _edges() -> list[tuple[int, int, float, float]]:
    return [
        (0, 1, 1.0, 1.0),
        (1, 3, 1.0, 1.0),
        (0, 2, 2.0, 1.0),
        (2, 3, 2.0, 1.0),
    ]


def _prefix() -> harness.InputPrefix:
    rows = (
        {
            "segment_id": "one",
            "task_id": 1,
            "original_entry_time": 0.0,
            "pass_time": 0.0,
            "start": 0,
            "goal": 3,
            "std": 100.0,
        },
    )
    return harness.InputPrefix(
        size_segments=1,
        rows=rows,
        prefix_sha256="",
        raw_bag_count=1,
        first_segment_id="one",
        last_segment_id="one",
    )


def test_potential_includes_candidate_service_in_the_runtime_lookup_row() -> None:
    potential, contract = g28.service_aware_potential(_nodes(), _edges())

    # travel(0,1)+H(1,3) = 1 + (service(1) + travel(1,3)) = 6
    # travel(0,2)+H(2,3) = 2 + (service(2) + travel(2,3)) = 5
    assert potential[1][3] == pytest.approx(5.0)
    assert potential[2][3] == pytest.approx(3.0)
    assert 1.0 + potential[1][3] > 2.0 + potential[2][3]
    assert potential[3][3] == 0.0
    assert potential[0][3] == pytest.approx(5.001)
    assert contract["runtime_decision_complexity"] == "O(outdegree)"
    assert contract["runtime_full_astar_required"] is False


def test_prepare_request_replaces_only_static_potential_on_g27_fifo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baseline = [[77.0] * 4 for _ in range(4)]
    request = {
        "node_records": _nodes(),
        "edge_records": _edges(),
        "heuristic_time": baseline,
        "queue_discipline": "fifo",
    }
    local = {
        "active_policy": {
            "choice": "local_junction_fifo_arbitration",
            "queue_discipline": "fifo",
            "scope": "one_junction_local_queue",
        }
    }
    monkeypatch.setattr(
        g28.g27,
        "prepare_request",
        lambda case, prefix, binary: (dict(request), tuple(prefix.rows), (), local),
    )

    prepared, contract, returned_local = g28.prepare_request(
        {"seed_edges": []}, _prefix(), binary=tmp_path / "unused.pyd"
    )

    assert prepared["heuristic_time"] != baseline
    assert {key: value for key, value in prepared.items() if key != "heuristic_time"} == {
        key: value for key, value in request.items() if key != "heuristic_time"
    }
    assert prepared["queue_discipline"] == "fifo"
    assert "g4irsf24_dlp_artifact" not in prepared
    assert contract["mode"] == "SERVICE_AWARE_STATIC_LOCAL_POTENTIAL"
    assert returned_local is local


def test_apply_helper_copies_request_and_preserves_every_non_heuristic_field() -> None:
    baseline = [[77.0] * 4 for _ in range(4)]
    request = {
        "node_records": _nodes(),
        "edge_records": _edges(),
        "heuristic_time": baseline,
        "minimum_service_seconds": 0.001,
        "queue_discipline": "fifo",
        "scenario": "reuse_from_bias_or_fault_runner",
    }

    prepared, contract = g28.apply_service_aware_potential(request)

    assert prepared is not request
    assert request["heuristic_time"] is baseline
    assert prepared["heuristic_time"] != baseline
    assert prepared["queue_discipline"] == "fifo"
    assert prepared["scenario"] == "reuse_from_bias_or_fault_runner"
    assert contract["minimum_service_seconds"] == pytest.approx(0.001)


def test_prepare_request_refuses_fault_case_instead_of_changing_g27_semantics(
    tmp_path: Path,
) -> None:
    with pytest.raises(g28.ServicePotentialError, match="no-fault"):
        g28.prepare_request(
            {"seed_edges": [[1, 3]]},
            _prefix(),
            binary=tmp_path / "unused.pyd",
        )


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [(g28.ADMITTED_STATUS, 0), ("FAILED_G28_ADMISSION_GATE", 2)],
)
def test_case_cli_persists_the_main_gate_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: str,
    expected_code: int,
) -> None:
    output = tmp_path / "case.json"
    monkeypatch.setattr(
        g28,
        "execute_case",
        lambda case_id, segments, binary: {
            "schema": g28.SCHEMA,
            "status": status,
            "case": {"case_id": case_id},
        },
    )

    code = g28.main(
        [
            "case",
            "--case-id",
            "t5_2_speed_3",
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

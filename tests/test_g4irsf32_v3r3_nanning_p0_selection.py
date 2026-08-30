from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf32_v3r3_nanning_p0_selection as selection


def test_content_hash_returns_json_native_mapping_and_rejects_collisions(
    tmp_path: Path,
) -> None:
    source = {"schema": "json-domain-fixture", "nested": {4: (tmp_path, 5)}}
    expected_content_sha = selection.canonical_sha256(source)

    artifact = selection.with_content_hash(source)
    reread = json.loads(
        selection._json_bytes(artifact, pretty=True),
        object_pairs_hook=selection._strict_json_object,
    )

    assert reread == artifact
    assert artifact["nested"] == {"4": [str(tmp_path), 5]}
    assert artifact["artifact_content_sha256"] == expected_content_sha
    assert selection.verify_content_hash(reread) == expected_content_sha

    with pytest.raises(selection.SelectionError, match="key collision"):
        selection.with_content_hash({"nested": {1: "integer", "1": "string"}})
    with pytest.raises(ValueError, match="Out of range float values"):
        selection.with_content_hash({"value": float("inf")})


def test_registered_cli_bootstraps_from_its_script_path() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/eval/run_g4irsf32_v3r3_nanning_p0_selection.py"
            ),
            "--help",
        ],
        cwd=str(selection.ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Freeze the outcome-blind V3R7 Nanning" in completed.stdout
    assert "commit_rank=max(0,ceil(" in selection.SELECTOR_RULE


def _row(
    task_id: int,
    *,
    start: int,
    release: float,
    leg: str,
    goal: int = 60,
) -> dict[str, Any]:
    return {
        "segment_id": f"{task_id}:{leg}",
        "task_id": task_id,
        "original_entry_time": release,
        "pass_time": release,
        "std": release + 1_000.0,
        "start": start,
        "goal": goal,
        "leg": leg,
    }


def _prearrival_overlap_oracle(
    rows: list[Mapping[str, Any]],
) -> tuple[dict[str, Any], int, str, list[str]]:
    external = sorted(
        [
        row
        for row in rows
        if row["start"] == selection.EXTERNAL_START
        and row["leg"] == "storage_out"
        ],
        key=lambda row: (row["pass_time"], row["segment_id"], row["task_id"]),
    )
    local = sorted(
        [row for row in rows if row["start"] == selection.LOCAL_START],
        key=lambda row: (row["pass_time"], row["segment_id"], row["task_id"]),
    )
    bursts: dict[float, list[Mapping[str, Any]]] = {}
    for row in external:
        bursts.setdefault(float(row["pass_time"]), []).append(row)
    candidates: list[dict[str, Any]] = []
    for first, second in zip(local, local[1:]):
        first_release = float(first["pass_time"])
        second_release = float(second["pass_time"])
        gap = second_release - first_release
        if not (
            selection.AUDIT_EPSILON
            < gap
            < selection.NODE49_SERVICE_SECONDS - selection.AUDIT_EPSILON
        ):
            continue
        for external_release, burst in bursts.items():
            first_arrival = (
                external_release
                + selection.EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
                + selection.EXTERNAL_53_TO_49_TRAVEL_SECONDS
            )
            second_local_service_complete = (
                max(
                    second_release + selection.SOURCE_RETRY_INTERVAL_SECONDS,
                    first_release + selection.NODE49_SERVICE_SECONDS,
                )
                + selection.NODE49_SERVICE_SECONDS
            )
            if (
                second_local_service_complete
                > first_arrival - selection.AUDIT_EPSILON
            ):
                continue
            rank = max(
                0,
                math.ceil(
                    (
                        second_release
                        - external_release
                        - selection.EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
                    )
                    / selection.NODE49_SERVICE_SECONDS
                ),
            )
            commit = (
                external_release
                + selection.EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
                + rank * selection.NODE49_SERVICE_SECONDS
            )
            if (
                rank >= len(burst)
                or commit <= second_release + selection.AUDIT_EPSILON
                or commit
                >= first_release
                + selection.NODE49_SERVICE_SECONDS
                - selection.AUDIT_EPSILON
                or commit >= first_arrival - selection.AUDIT_EPSILON
            ):
                continue
            candidates.append(
                {
                    "external_release": external_release,
                    "external_release_multiplicity": len(burst),
                    "external_prefix_count": rank + 1,
                    "external_commit_rank": rank,
                    "predicted_external_commit_time": commit,
                    "first_local_release": first_release,
                    "first_local_segment_id": str(first["segment_id"]),
                    "first_local_task_id": int(first["task_id"]),
                    "second_local_release": second_release,
                    "second_local_segment_id": str(second["segment_id"]),
                    "second_local_task_id": int(second["task_id"]),
                    "local_release_gap_seconds": gap,
                }
            )
    candidates.sort(
        key=lambda row: (
            row["external_prefix_count"],
            row["external_release"],
            row["first_local_release"],
            row["second_local_release"],
            row["first_local_segment_id"],
            row["first_local_task_id"],
            row["second_local_segment_id"],
            row["second_local_task_id"],
        )
    )
    chosen = candidates[0]
    local_ids = {
        chosen["first_local_segment_id"],
        chosen["second_local_segment_id"],
    }
    selected = [
        *bursts[chosen["external_release"]][
            : chosen["external_prefix_count"]
        ],
        *(row for row in local if str(row["segment_id"]) in local_ids),
    ]
    selected.sort(
        key=lambda row: (row["pass_time"], row["segment_id"], row["task_id"])
    )
    return (
        chosen,
        len(candidates),
        selection.canonical_sha256(candidates),
        [str(row["segment_id"]) for row in selected],
    )


def test_selector_allows_released_local_pair_before_external_release() -> None:
    rows = [
        _row(10, start=53, release=50.0, leg="storage_out"),
        _row(11, start=53, release=50.0, leg="storage_out"),
        _row(20, start=49, release=50.2, leg="direct"),
        _row(21, start=49, release=50.4, leg="direct"),
        _row(30, start=53, release=100.0, leg="storage_out"),
        _row(40, start=49, release=99.2, leg="direct"),
        _row(41, start=49, release=99.4, leg="direct"),
    ]

    cohort, selected_rows = selection.select_commit_aligned_cohort(rows)

    assert cohort["external_release"] == 100.0
    assert cohort["external_commit_rank"] == 0
    assert cohort["predicted_external_commit_time"] == 100.001
    assert cohort["external_selected_count"] == 1
    assert cohort["local_selected_count"] == 2
    assert cohort["selected_segment_count"] == 3
    chosen, count, candidate_sha, expected_ids = _prearrival_overlap_oracle(rows)
    assert cohort["candidate_count"] == count
    assert cohort["candidate_set_sha256"] == candidate_sha
    assert cohort["first_local_segment_id"] == chosen["first_local_segment_id"]
    assert [row["segment_id"] for row in selected_rows] == expected_ids


def test_selector_matches_independent_oracle_and_is_order_invariant() -> None:
    for seed in range(40):
        generator = random.Random(seed)
        base = float(generator.randint(100, 300))
        rows = [
            _row(100, start=53, release=base, leg="storage_out"),
            _row(200, start=49, release=base - 0.8, leg="direct"),
            _row(201, start=49, release=base - 0.6, leg="direct"),
            # A later prefix-one candidate must lose the earlier-release tie.
            _row(300, start=53, release=base + 20.0, leg="storage_out"),
            _row(400, start=49, release=base + 19.3, leg="direct"),
            _row(401, start=49, release=base + 19.5, leg="direct"),
            # Isolated noise cannot form an adjacent sub-one-second pair.
            _row(500, start=53, release=base + 100.0, leg="storage_out"),
            _row(600, start=49, release=base + 80.0, leg="direct"),
        ]
        chosen, count, candidate_sha, expected_ids = _prearrival_overlap_oracle(rows)
        generator.shuffle(rows)
        cohort, selected_rows = selection.select_commit_aligned_cohort(rows)

        assert cohort["external_release"] == chosen["external_release"]
        assert cohort["candidate_count"] == count
        assert cohort["candidate_set_sha256"] == candidate_sha
        assert [row["segment_id"] for row in selected_rows] == expected_ids


def test_selector_fails_closed_on_invalid_pools_and_no_overlap() -> None:
    external = _row(10, start=53, release=100.0, leg="storage_out")
    local_a = _row(20, start=49, release=99.2, leg="direct")
    local_b = _row(21, start=49, release=99.4, leg="direct")

    with pytest.raises(selection.SelectionError, match="at least two local"):
        selection.select_commit_aligned_cohort([external])
    with pytest.raises(selection.SelectionError, match="E pool"):
        selection.select_commit_aligned_cohort([local_a, local_b])
    with pytest.raises(selection.SelectionError, match="external pool.*not unique"):
        selection.select_commit_aligned_cohort(
            [external, dict(external), local_a, local_b]
        )
    with pytest.raises(selection.SelectionError, match="local pool.*not unique"):
        selection.select_commit_aligned_cohort(
            [external, local_a, dict(local_a)]
        )
    with pytest.raises(selection.SelectionError, match="no frozen pre-arrival"):
        selection.select_commit_aligned_cohort(
            [
                external,
                _row(30, start=49, release=200.0, leg="direct"),
                _row(31, start=49, release=202.0, leg="direct"),
            ]
        )


def test_selector_fails_closed_at_epsilon_overlap_boundaries() -> None:
    external = _row(10, start=53, release=100.0, leg="storage_out")
    commit = 100.0 + selection.EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
    epsilon = selection.AUDIT_EPSILON

    lower_pass = [
        external,
        _row(20, start=49, release=99.5, leg="direct"),
        _row(21, start=49, release=commit - 2.0 * epsilon, leg="direct"),
    ]
    cohort, _rows = selection.select_commit_aligned_cohort(lower_pass)
    assert cohort["external_prefix_count"] == 1

    lower_reject = deepcopy(lower_pass)
    lower_reject[2]["pass_time"] = commit - 0.5 * epsilon
    lower_reject[2]["original_entry_time"] = commit - 0.5 * epsilon
    with pytest.raises(selection.SelectionError, match="no frozen pre-arrival"):
        selection.select_commit_aligned_cohort(lower_reject)

    upper_pass = [
        external,
        _row(30, start=49, release=99.001 + 2.0 * epsilon, leg="direct"),
        _row(31, start=49, release=99.5, leg="direct"),
    ]
    cohort, _rows = selection.select_commit_aligned_cohort(upper_pass)
    assert cohort["external_prefix_count"] == 1

    upper_reject = deepcopy(upper_pass)
    upper_reject[1]["pass_time"] = 99.001 + 0.5 * epsilon
    upper_reject[1]["original_entry_time"] = 99.001 + 0.5 * epsilon
    with pytest.raises(selection.SelectionError, match="no frozen pre-arrival"):
        selection.select_commit_aligned_cohort(upper_reject)

    for gap in (0.5 * epsilon, 1.0 - 0.5 * epsilon):
        invalid_gap = [
            external,
            _row(40, start=49, release=99.0, leg="direct"),
            _row(41, start=49, release=99.0 + gap, leg="direct"),
        ]
        with pytest.raises(selection.SelectionError, match="no frozen pre-arrival"):
            selection.select_commit_aligned_cohort(invalid_gap)


def test_selector_requires_full_local_clearance_and_exact_prefix_multiplicity() -> None:
    epsilon = selection.AUDIT_EPSILON
    external_60 = [
        _row(1_000 + index, start=53, release=100.0, leg="storage_out")
        for index in range(60)
    ]
    clear_pass = [
        *external_60,
        _row(
            2_000,
            start=49,
            release=158.101 - 2.0 * epsilon,
            leg="direct",
        ),
        _row(2_001, start=49, release=158.3, leg="direct"),
    ]
    cohort, _rows = selection.select_commit_aligned_cohort(clear_pass)
    assert cohort["external_commit_rank"] == 59
    assert cohort["external_prefix_count"] == 60
    assert cohort["source_retry_interval_seconds"] == 0.25

    clear_reject = deepcopy(clear_pass)
    clear_reject[-2]["pass_time"] = 158.101
    clear_reject[-2]["original_entry_time"] = 158.101
    with pytest.raises(selection.SelectionError, match="no frozen pre-arrival"):
        selection.select_commit_aligned_cohort(clear_reject)

    # A+2 alone is insufficient when B+retry starts after A completes.
    retry_delayed_reject = [
        *external_60,
        _row(2_100, start=49, release=158.01, leg="direct"),
        _row(2_101, start=49, release=158.91, leg="direct"),
    ]
    with pytest.raises(selection.SelectionError, match="no frozen pre-arrival"):
        selection.select_commit_aligned_cohort(retry_delayed_reject)

    locals_for_rank_three = [
        _row(3_000, start=49, release=102.2, leg="direct"),
        _row(3_001, start=49, release=102.4, leg="direct"),
    ]
    external_3 = [
        _row(4_000 + index, start=53, release=100.0, leg="storage_out")
        for index in range(3)
    ]
    with pytest.raises(selection.SelectionError, match="no frozen pre-arrival"):
        selection.select_commit_aligned_cohort(
            [*external_3, *locals_for_rank_three]
        )
    external_4 = [
        *external_3,
        _row(4_003, start=53, release=100.0, leg="storage_out"),
    ]
    cohort, _rows = selection.select_commit_aligned_cohort(
        [*external_4, *locals_for_rank_three]
    )
    assert cohort["external_commit_rank"] == 3
    assert cohort["external_prefix_count"] == 4


def test_origin_projection_is_one_to_one_and_source_only() -> None:
    original = [
        *[
            _row(index, start=53, release=float(index), leg="storage_out")
            for index in range(3)
        ],
        *[
            _row(100 + index, start=49, release=float(index), leg="direct")
            for index in range(2)
        ],
    ]

    projected, identity = selection.project_selected_rows(original)

    assert {row["source"] for row in projected} == {"external", "local"}
    assert len(identity) == 5
    for before, after in zip(original, projected):
        assert {key: value for key, value in after.items() if key != "source"} == before


def test_g31_request_matches_complete_registered_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = [
        _row(10, start=53, release=100.0, leg="storage_out"),
        _row(20, start=49, release=100.0, leg="direct"),
    ]
    original.sort(key=lambda row: (row["pass_time"], row["segment_id"], row["task_id"]))
    projected, _identity = selection.project_selected_rows(original)
    monkeypatch.setitem(selection.EXPECTED_SELECTION_COUNTS[1], "total", 2)

    request, _potential = selection.build_g31_control_request(1, projected)
    auditor = selection._v3_auditor()

    assert request["scenario"] == "g4irsf32_v3r7_nanning_p0_1x"
    assert request["max_events"] == 2_000_000
    assert request["max_simulation_time"] == -1.0
    assert request["storage_source_nodes"] == [53]
    assert "source_aware_destination_service_mode" not in request
    assert "source_aware_destination_service_trace_limit" not in request
    ordinary_projection = {
        key: value
        for key, value in auditor.REQUEST_PROJECTION.items()
        if key != "source_aware_destination_service_trace_limit"
    }
    assert {
        key: request[key] for key in ordinary_projection
    } == ordinary_projection

    monkeypatch.setattr(selection, "SOURCE_RETRY_INTERVAL_SECONDS", 0.5)
    with pytest.raises(selection.SelectionError, match="retry interval"):
        selection.build_g31_control_request(1, projected)


def _request() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [
        _row(10, start=53, release=0.0, leg="storage_out", goal=53),
        _row(20, start=49, release=60.0, leg="direct", goal=53),
    ]
    request = {
        "node_records": [
            (49, 1, 1.0, 0, 0, [53]),
            (53, 2, 0.0, 1, 0, []),
        ],
        "edge_records": [(49, 53, 1.0, 2.5), (53, 49, 150.25, 2.5)],
        "heuristic_time": [[0.0, 1.0], [1.0, 0.0]],
        "bag_records": [
            ("10:storage_out", 10, 0.0, 1_000.0, 53, 53, "external"),
            ("20:direct", 20, 60.0, 1_060.0, 49, 53, "local"),
        ],
        "fault_windows": [],
        "minimum_service_seconds": 0.001,
        "complete_on_goal_arrival": True,
        "expected_binary_path": selection.G31_BINARY,
        "search_path": selection.G31_BINARY.parent,
    }
    return rows, request


def _payload(*, qualifying: bool = True) -> dict[str, Any]:
    binary_path = str(selection.G31_BINARY.resolve(strict=True))
    digest = selection.FROZEN_SOURCE_HASHES[selection.G31_BINARY]
    events = [
        {
            "seq": 1,
            "event": "LOCAL_QUEUE_UPDATE",
            "time": 60.0,
            "task_id": 20,
            "runtime_bag_id": 1,
            "segment_id": "20:direct",
            "node": 49,
            "from_node": -1,
            "to_node": 49,
            "reason": "source_enqueue",
            "selected_edge_count": 0,
        },
        {
            "seq": 2,
            "event": "EDGE_ENTER",
            "time": 61.0,
            "task_id": 10,
            "runtime_bag_id": 0,
            "segment_id": "10:storage_out",
            "node": 53,
            "from_node": 53,
            "to_node": 49,
            "reason": "one_step_reservation_committed" if qualifying else "ordinary_move",
            "selected_edge_count": 1,
        },
        {
            "seq": 3,
            "event": "LOCAL_QUEUE_UPDATE",
            "time": 61.5,
            "task_id": 20,
            "runtime_bag_id": 1,
            "segment_id": "20:direct",
            "node": 49,
            "from_node": -1,
            "to_node": 49,
            "reason": "source_dequeue",
            "selected_edge_count": 0,
        },
        {
            "seq": 4,
            "event": "JUNCTION_SERVICE_COMPLETE",
            "time": 62.5,
            "task_id": 20,
            "runtime_bag_id": 1,
            "segment_id": "20:direct",
            "node": 49,
            "from_node": -1,
            "to_node": 49,
            "reason": "junction_service_complete",
            "selected_edge_count": 0,
        },
        {
            "seq": 5,
            "event": "EDGE_EXIT",
            "time": 121.0,
            "task_id": 10,
            "runtime_bag_id": 0,
            "segment_id": "10:storage_out",
            "node": 49,
            "from_node": 53,
            "to_node": 49,
            "reason": "edge_traversal_complete",
            "selected_edge_count": 0,
        },
        {
            "seq": 6,
            "event": "JUNCTION_SERVICE_COMPLETE",
            "time": 122.0,
            "task_id": 10,
            "runtime_bag_id": 0,
            "segment_id": "10:storage_out",
            "node": 49,
            "from_node": 53,
            "to_node": 49,
            "reason": "junction_service_complete",
            "selected_edge_count": 0,
        },
    ]
    summary = {
        "loaded_cpp_binary_path": binary_path,
        "loaded_cpp_binary_sha256": digest,
        "event_trace_truncated": False,
        "decision_trace_truncated": False,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "requested_count": 2,
        "completed_count": 2,
        "failed_count": 0,
        "final_active_bag_count": 0,
        "decision_trace_stored_count": 0,
        "hold_trace_stored_count": 0,
        "merge_grant_lifecycle_stored_count": 0,
        "merge_grant_lifecycle_dropped_count": 0,
        "merge_grant_lifecycle_complete": True,
        "merge_grant_lifecycle_telemetry_truncated": False,
        "merge_grant_final_active_unconsumed": 0,
        "merge_grant_outstanding_request_count": 0,
        "merge_grant_active_state_integrity_pass": True,
        "merge_grant_protocol_integrity_pass": True,
        "first_edge_credit_active_count": 0,
        "starvation_count": 0,
        "merge_grant_request_count": 0,
        "merge_grant_issued_count": 0,
        "merge_grant_issued_transition_count": 0,
        "merge_grant_prepared_count": 0,
        "merge_grant_prepared_transition_count": 0,
        "merge_grant_committed_count": 0,
        "merge_grant_committed_transition_count": 0,
        "merge_grant_consumed_count": 0,
        "merge_grant_post_commit_revoked_count": 0,
        "merge_grant_post_commit_expired_count": 0,
        "merge_grant_post_commit_rollback_count": 0,
        "merge_grant_expired_count": 0,
        "merge_grant_revoked_count": 0,
        "merge_grant_rolled_back_count": 0,
        "merge_grant_lifecycle_transition_count": 0,
        "merge_grant_terminal_request_count": 0,
        "merge_grant_peak_pending_requests": 0,
        "merge_grant_peak_active_unconsumed": 0,
        "max_edges_selected_per_bag_per_decision": 1,
        "artificial_batch_delay_seconds": 0.0,
        "merge_grant_conservation_holds": True,
        "merge_grant_active_bijection_holds": True,
        "safe_execution_pass": True,
        **{field: 0 for field in selection.SAFETY_ZERO_FIELDS},
        **{
            field: 0
            for field in (
                selection._v3_auditor().SAFETY_ZERO_KEYS
                + selection._v3_auditor().CLONE_SAFETY_ZERO_KEYS
            )
        },
    }
    return {
        "loaded_cpp_binary_path": binary_path,
        "loaded_cpp_binary_sha256": digest,
        "trace_context": {
            "schema_id": "czr005.g4irsf11.decision_trace.v1",
        },
        "summary": summary,
        "bags": [
            {
                "segment_id": "10:storage_out",
                "task_id": 10,
                "runtime_bag_id": 0,
                "start": 53,
                "goal": 53,
                "release_time": 0.0,
                "deadline": 1_000.0,
                "source": "external",
                "completed": True,
                "finish_time": 130.0,
                "starved": False,
                "total_local_wait": 0.0,
            },
            {
                "segment_id": "20:direct",
                "task_id": 20,
                "runtime_bag_id": 1,
                "start": 49,
                "goal": 53,
                "release_time": 60.0,
                "deadline": 1_060.0,
                "source": "local",
                "completed": True,
                "finish_time": 70.0,
                "starved": False,
                "total_local_wait": 0.0,
            },
        ],
        "events": events,
        "decisions": [],
        "hold_attempts": [],
        "merge_grant_lifecycle": [],
        "junction_state": [
            {
                "node": 49,
                "final_source_queue_length": 0,
                "final_junction_queue_length": 0,
                "scheduled_incoming": 0,
                "service_reservation_count": 2,
            },
            {
                "node": 53,
                "final_source_queue_length": 0,
                "final_junction_queue_length": 0,
                "scheduled_incoming": 0,
                "service_reservation_count": 0,
            },
        ],
    }


def test_control_audit_admits_real_53_to_49_with_live_local_winner() -> None:
    rows, request = _request()

    audit = selection.audit_g31_control_payload(
        scale=1, selected_rows=rows, request=request, payload=_payload()
    )

    assert audit["pass"] is True
    assert audit["status"] == selection.PASS
    assert audit["qualifying_event_count"] == 1
    event = audit["qualifying_events"][0]
    assert event["external_runtime_bag_id"] == 0
    assert event["local_runtime_bag_id"] == 1
    assert event["node49_service_non_overlap"] is True


def test_control_event_order_uses_unique_seq_identity_not_global_seq_order() -> None:
    rows, request = _request()
    payload = _payload()
    # Runtime seq is assigned at scheduling time.  The event scheduled later
    # can execute first when its time/microphase precedes an older future event.
    payload["events"][1]["seq"] = 3
    payload["events"][2]["seq"] = 2

    audit = selection.audit_g31_control_payload(
        scale=1, selected_rows=rows, request=request, payload=payload
    )

    assert audit["pass"] is True


def test_control_live_winner_uses_execution_time_not_scheduling_seq_order() -> None:
    rows, request = _request()
    payload = _payload()
    payload["events"][1]["seq"] = 50
    payload["events"][4]["seq"] = 51
    payload["events"][5]["seq"] = 52

    audit = selection.audit_g31_control_payload(
        scale=1, selected_rows=rows, request=request, payload=payload
    )

    assert audit["pass"] is True
    assert audit["qualifying_event_count"] == 1


def test_global_service_deep_replay_uses_each_bags_own_goal() -> None:
    episodes = [
        {
            "runtime_bag_id": 0,
            "node": 0,
            "start": 0.0,
            "complete": 0.25,
            "completion_event_seq": 1,
        },
        {
            "runtime_bag_id": 1,
            "node": 0,
            "start": 0.25,
            "complete": 0.5,
            "completion_event_seq": 2,
        },
        {
            "runtime_bag_id": 0,
            "node": 1,
            "start": 1.0,
            "complete": 2.0,
            "completion_event_seq": 3,
        },
        {
            "runtime_bag_id": 1,
            "node": 1,
            "start": 2.0,
            "complete": 3.0,
            "completion_event_seq": 4,
        },
    ]
    evidence = {
        "pass": True,
        "checks": {
            "unique_bag_node": True,
            "completion_event_identity_unique": True,
            "no_node_overlap": True,
            "reservation_count_match": True,
            "goal_arrival_has_no_service": True,
            "evidence_vector_bounded": True,
        },
        "completion_counts": {"0": 2, "1": 2},
        "reservation_counts": {"0": 2, "1": 2},
        "ordered_service_episodes": episodes,
        "service_episodes_sha256": selection.canonical_sha256(episodes),
        "service_episode_count": 4,
        "evidence_vector_limit": 4,
        "evidence_vector_bounded": True,
        "error": None,
    }
    sequence = [
        {
            "runtime_bag_id": 0,
            "node": 1,
            "start": 1.0,
            "complete": 2.0,
            "completion_event_seq": 3,
        },
        {
            "runtime_bag_id": 1,
            "node": 1,
            "start": 2.0,
            "complete": 3.0,
            "completion_event_seq": 4,
        }
    ]

    selection._validate_global_service_evidence(
        evidence,
        "shared-role",
        complete_sequence=sequence,
        goal_by_runtime={0: 3, 1: 3},
        exact_l=True,
        expected_exact_node=1,
        expected_reservation_counts={0: 2, 1: 2},
        expected_service_by_node={0: 0.25, 1: 1.0, 3: 0.001},
    )

    # A same-duration node cannot replace the externally frozen exact-L node,
    # even when every affected vector/count/hash is changed coherently.
    wrong_node = deepcopy(evidence)
    for row in wrong_node["ordered_service_episodes"]:
        if row["node"] == 1:
            row["node"] = 2
    wrong_node["completion_counts"] = {"0": 2, "2": 2}
    wrong_node["reservation_counts"] = {"0": 2, "2": 2}
    wrong_node["service_episodes_sha256"] = selection.canonical_sha256(
        wrong_node["ordered_service_episodes"]
    )
    wrong_sequence = deepcopy(sequence)
    for row in wrong_sequence:
        row["node"] = 2
    with pytest.raises(
        selection.SelectionError, match="exact-L sequence node identity changed"
    ):
        selection._validate_global_service_evidence(
            wrong_node,
            "wrong-exact-node",
            complete_sequence=wrong_sequence,
            goal_by_runtime={0: 3, 1: 3},
            exact_l=True,
            expected_exact_node=1,
            expected_reservation_counts={0: 2, 2: 2},
            expected_service_by_node={0: 0.25, 1: 1.0, 2: 1.0, 3: 0.001},
        )
    with pytest.raises(selection.SelectionError, match="global service replay failed"):
        selection._validate_global_service_evidence(
            evidence,
            "own-goal",
            complete_sequence=sequence,
            goal_by_runtime={0: 1, 1: 3},
            exact_l=True,
            expected_exact_node=1,
            expected_reservation_counts={0: 2, 1: 2},
            expected_service_by_node={0: 0.25, 1: 1.0, 3: 0.001},
        )

    # The exact-L sequence remains valid, but an overlap on another node must
    # be independently rejected from the complete global episode vector.
    overlap = deepcopy(evidence)
    overlap["ordered_service_episodes"][1].update(start=0.2, complete=0.45)
    overlap["service_episodes_sha256"] = selection.canonical_sha256(
        overlap["ordered_service_episodes"]
    )
    with pytest.raises(selection.SelectionError, match="global service replay failed"):
        selection._validate_global_service_evidence(
            overlap,
            "other-node-overlap",
            complete_sequence=sequence,
            goal_by_runtime={0: 3, 1: 3},
            exact_l=True,
            expected_exact_node=1,
            expected_reservation_counts={0: 2, 1: 2},
            expected_service_by_node={0: 0.25, 1: 1.0, 3: 0.001},
        )

    duration = deepcopy(evidence)
    duration["ordered_service_episodes"][0]["complete"] = 0.2
    duration["service_episodes_sha256"] = selection.canonical_sha256(
        duration["ordered_service_episodes"]
    )
    with pytest.raises(selection.SelectionError, match="global service episode is invalid"):
        selection._validate_global_service_evidence(
            duration,
            "other-node-duration",
            complete_sequence=sequence,
            goal_by_runtime={0: 3, 1: 3},
            exact_l=True,
            expected_exact_node=1,
            expected_reservation_counts={0: 2, 1: 2},
            expected_service_by_node={0: 0.25, 1: 1.0, 3: 0.001},
        )


def test_service_audit_rejects_rehashed_completion_goal_rebinding() -> None:
    _rows_value, request = _request()
    payload = _payload()
    auditor = selection._v3_auditor()
    evidence = json.loads(
        json.dumps(
            auditor._service_audit(
                "goal-binding",
                2,
                {"external", "local"},
                payload,
                request,
                exact_node=49,
            ),
            allow_nan=False,
        )
    )
    request_goals = {
        runtime_id: int(record[5])
        for runtime_id, record in enumerate(request["bag_records"])
    }

    selection._validate_service_audit_evidence(
        evidence,
        bag_count=2,
        exact_l=True,
        expected_exact_node=49,
        expected_goal_by_runtime=request_goals,
        expected_service_by_node=selection._service_profile_from_request(
            request, label="valid-goal-binding.request"
        ),
        service_seconds=1.0,
        expected_origins={"external", "local"},
        label="valid-goal-binding",
    )

    tampered = deepcopy(evidence)
    permanent = tampered["permanent_starvation"]
    permanent["bag_completion_vector"][0]["goal"] = 999
    permanent["bag_completion_vector_sha256"] = selection.canonical_sha256(
        permanent["bag_completion_vector"]
    )
    with pytest.raises(selection.SelectionError, match="own-goal mapping differs"):
        selection._validate_service_audit_evidence(
            tampered,
            bag_count=2,
            exact_l=True,
            expected_exact_node=49,
            expected_goal_by_runtime=request_goals,
            expected_service_by_node=selection._service_profile_from_request(
                request, label="tampered-goal-binding.request"
            ),
            service_seconds=1.0,
            expected_origins={"external", "local"},
            label="tampered-goal-binding",
        )


def test_control_event_order_rejects_duplicate_seq_and_time_regression() -> None:
    rows, request = _request()
    duplicate = _payload()
    duplicate["events"][1]["seq"] = duplicate["events"][0]["seq"]
    with pytest.raises(ValueError, match="event seq is not unique"):
        selection.audit_g31_control_payload(
            scale=1, selected_rows=rows, request=request, payload=duplicate
        )

    regressed = _payload()
    regressed["events"][2]["time"] = regressed["events"][1]["time"] - 1.0
    with pytest.raises(selection.SelectionError, match="times are not monotonic"):
        selection.audit_g31_control_payload(
            scale=1, selected_rows=rows, request=request, payload=regressed
        )


def test_control_source_queue_replay_ignores_known_junction_queue_rows() -> None:
    rows, request = _request()
    payload = _payload()
    junction_update = deepcopy(payload["events"][0])
    junction_update.update(
        seq=7,
        time=61.25,
        reason="junction_enqueue",
        node=49,
        from_node=-1,
        to_node=49,
    )
    payload["events"].insert(2, junction_update)

    audit = selection.audit_g31_control_payload(
        scale=1, selected_rows=rows, request=request, payload=payload
    )

    assert audit["pass"] is True


def test_control_source_queue_replay_rejects_unknown_queue_reason() -> None:
    rows, request = _request()
    payload = _payload()
    unknown_update = deepcopy(payload["events"][0])
    unknown_update.update(
        seq=7,
        time=61.25,
        reason="unknown_queue_transition",
        node=49,
        from_node=-1,
        to_node=49,
    )
    payload["events"].insert(2, unknown_update)

    with pytest.raises(selection.SelectionError, match="reason is not replayable"):
        selection.audit_g31_control_payload(
            scale=1, selected_rows=rows, request=request, payload=payload
        )


def test_control_audit_does_not_require_dormant_configured_node_state() -> None:
    rows, request = _request()
    request["node_records"].append((99, 4, 0.0, 2, 0, []))

    audit = selection.audit_g31_control_payload(
        scale=1, selected_rows=rows, request=request, payload=_payload()
    )

    assert audit["pass"] is True
    assert audit["checks"]["final_pending_zero"] is True


def test_control_audit_accepts_only_inert_materialized_dormant_state() -> None:
    rows, request = _request()
    request["node_records"].append((99, 4, 0.0, 2, 0, []))
    payload = _payload()
    payload["junction_state"].append(
        {
            "node": 99,
            "final_source_queue_length": 0,
            "final_junction_queue_length": 0,
            "scheduled_incoming": 0,
            "service_reservation_count": 0,
        }
    )

    audit = selection.audit_g31_control_payload(
        scale=1, selected_rows=rows, request=request, payload=payload
    )
    assert audit["pass"] is True
    assert audit["checks"]["final_pending_zero"] is True

    payload["junction_state"][-1]["service_reservation_count"] = 1
    audit = selection.audit_g31_control_payload(
        scale=1, selected_rows=rows, request=request, payload=payload
    )
    assert audit["pass"] is False
    assert audit["checks"]["final_pending_zero"] is False


def test_control_audit_rejects_unconfigured_materialized_state() -> None:
    rows, request = _request()
    payload = _payload()
    payload["junction_state"].append(
        {
            "node": 99,
            "final_source_queue_length": 0,
            "final_junction_queue_length": 0,
            "scheduled_incoming": 0,
            "service_reservation_count": 0,
        }
    )

    audit = selection.audit_g31_control_payload(
        scale=1, selected_rows=rows, request=request, payload=payload
    )
    assert audit["pass"] is False
    assert audit["checks"]["final_pending_zero"] is False


def test_control_audit_preserves_zero_event_no_go() -> None:
    rows, request = _request()

    audit = selection.audit_g31_control_payload(
        scale=1,
        selected_rows=rows,
        request=request,
        payload=_payload(qualifying=False),
    )

    assert audit["pass"] is False
    assert audit["status"] == selection.NO_EVENT
    assert audit["qualifying_event_count"] == 0
    assert all(
        value
        for name, value in audit["checks"].items()
        if name != "real_53_to_49_with_released_live_local_winner"
    )


def test_control_seam_fails_closed_without_unique_local_winner() -> None:
    _rows_value, request = _request()
    payload = _payload()
    extra = deepcopy(payload["bags"][1])
    extra.update(
        runtime_bag_id=2,
        task_id=21,
        segment_id="21:direct",
        finish_time=80.0,
    )
    payload["bags"].append(extra)
    for event in payload["events"]:
        if event["seq"] >= 2:
            event["seq"] += 1
    payload["events"].insert(
        1,
        {
            "seq": 2,
            "event": "LOCAL_QUEUE_UPDATE",
            "time": 60.5,
            "task_id": 21,
            "runtime_bag_id": 2,
            "segment_id": "21:direct",
            "node": 49,
            "from_node": -1,
            "to_node": 49,
            "reason": "source_enqueue",
            "selected_edge_count": 0,
        },
    )
    auditor = selection._v3_auditor()
    episodes, _events, _bags = auditor._base_episodes(
        "unique_local", payload, auditor._services(request)
    )

    assert selection._qualifying_control_events(payload, episodes) == []


def test_control_seam_requires_unique_exit_and_exit_service_start() -> None:
    _rows_value, request = _request()
    auditor = selection._v3_auditor()
    duplicate = _payload()
    second_exit = deepcopy(duplicate["events"][4])
    second_exit.update(seq=7, time=123.0)
    duplicate["events"].append(second_exit)
    episodes, _events, _bags = auditor._base_episodes(
        "duplicate_exit", duplicate, auditor._services(request)
    )
    with pytest.raises(selection.SelectionError, match="unique EDGE_ENTER/EDGE_EXIT"):
        selection._qualifying_control_events(duplicate, episodes)

    wrong_epoch = _payload()
    wrong_epoch["events"][4]["time"] = 120.5
    episodes, _events, _bags = auditor._base_episodes(
        "wrong_exit_epoch", wrong_epoch, auditor._services(request)
    )
    assert selection._qualifying_control_events(wrong_epoch, episodes) == []


def test_control_audit_rejects_g32_contamination() -> None:
    rows, request = _request()
    payload = _payload()
    payload["summary"][
        "source_aware_destination_service_mode"
    ] = "shadow"

    with pytest.raises(selection.SelectionError, match="contaminated"):
        selection.audit_g31_control_payload(
            scale=1, selected_rows=rows, request=request, payload=payload
        )


def test_control_audit_rejects_loaded_binary_path_alias() -> None:
    rows, request = _request()
    payload = _payload()
    wrong_path = str(selection.RUNNER_PATH.resolve(strict=True))
    payload["loaded_cpp_binary_path"] = wrong_path
    payload["summary"]["loaded_cpp_binary_path"] = wrong_path

    with pytest.raises(selection.SelectionError, match="frozen G31 binary"):
        selection.audit_g31_control_payload(
            scale=1, selected_rows=rows, request=request, payload=payload
        )


def test_atomic_writer_is_append_only_and_strict_json(tmp_path: Path) -> None:
    path = tmp_path / "control.json"
    artifact = selection.with_content_hash({"schema": "fixture", "value": 1})

    selection.atomic_write_strict_json(path, artifact)

    assert selection.read_strict_json(path) == artifact
    assert selection.verify_content_hash(artifact) == artifact["artifact_content_sha256"]
    assert not list(tmp_path.glob(".control.json.*.tmp"))
    with pytest.raises(FileExistsError):
        selection.atomic_write_strict_json(path, artifact)
    invalid = tmp_path / "invalid.json"
    with pytest.raises(ValueError, match="Out of range float values"):
        selection.atomic_write_strict_json(invalid, {"value": math.nan})
    assert not invalid.exists()
    assert not list(tmp_path.glob(".invalid.json.*.tmp"))


def test_shadow_gate_rejects_invalid_control_before_executor(
    tmp_path: Path,
) -> None:
    invalid = selection.with_content_hash(
        {
            "schema": selection.SCHEMA,
            "protocol_id": selection.PROTOCOL_ID,
            "status": selection.PASS,
            "pass": True,
            "g32_executed": False,
            "execution_dependencies_start": selection.execution_dependency_identity(),
            "execution_dependencies_unchanged": True,
            "scales": {},
        }
    )
    calls = 0

    def executor(**_request: Any) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return {}

    with pytest.raises(TypeError, match="Path"):
        selection.load_and_validate_control_artifact(
            invalid,
            expected_file_sha256="0" * 64,
        )

    path = tmp_path / "invalid-control.json"
    selection.atomic_write_strict_json(path, invalid)
    with pytest.raises(selection.SelectionError, match="registered output path"):
        selection.run_g32_shadow_gate(
            path,
            tmp_path / "missing-g32.pyd",
            executor,
            expected_control_file_sha256=selection.file_sha256(path),
            synthetic_artifact=tmp_path / "missing-synthetic.json",
            expected_synthetic_file_sha256="0" * 64,
            expected_g32_binary_sha256="1" * 64,
            _test_only=True,
        )
    assert calls == 0


def test_frozen_control_stays_blocked_while_shadow_reaches_registered_inputs(
    tmp_path: Path,
) -> None:
    calls = 0
    def executor(**_request: Any) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        raise AssertionError("executor must not run while revision is blocked")
    with pytest.raises(
        selection.SelectionError,
        match=selection.CONTROL_EXECUTION_BLOCKED_REASON,
    ):
        selection.run_control_selection(executor=executor)
    with pytest.raises(
        selection.SelectionError,
        match="registered output path",
    ):
        selection.run_g32_shadow_gate(
            tmp_path / "missing-control.json",
            tmp_path / "missing-g32.pyd",
            executor,
            expected_control_file_sha256="1" * 64,
            synthetic_artifact=tmp_path / "missing-synthetic.json",
            expected_synthetic_file_sha256="2" * 64,
            expected_g32_binary_sha256="3" * 64,
        )
    output = tmp_path / "must-not-exist.json"
    with pytest.raises(
        selection.SelectionError,
        match=selection.CONTROL_EXECUTION_BLOCKED_REASON,
    ):
        selection.main(["--output", str(output)])
    assert calls == 0
    assert not output.exists()


@lru_cache(maxsize=1)
def _real_regenerated_selections() -> dict[int, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="g4irsf32_v3r7_test_regen_") as name:
        return selection.regenerate_and_select(Path(name))


def _mock_scale_selection(scale: int) -> tuple[dict[str, Any], dict[str, str]]:
    item = deepcopy(_real_regenerated_selections()[scale])
    selected = item["selection"]
    hashes = {
        "external_release_histogram": selected[
            "external_release_histogram_sha256"
        ],
        "candidate_set": selected["candidate_set_sha256"],
        "original_rows": selected["original_selected_rows_sha256"],
        "projected_rows": selected["selected_rows_sha256"],
        "projection_identity": selected["projection_identity_sha256"],
        "selected_segment_ids": selected["selected_segment_ids_sha256"],
    }
    return item, hashes


V3R7_CONTROL_FILE_SHA256 = (
    "79db82402cc8f8c9abd8d1a9a01a6e9216aded76008ffc9da5945d4f7cbd38b0"
)


@lru_cache(maxsize=1)
def _registered_v3r7_control() -> dict[str, Any]:
    value = selection.read_strict_json(selection.OUTPUT_PATH)
    assert isinstance(value, dict)
    return value


def test_registered_v3r7_control_compat_loader_accepts_historical_audit() -> None:
    loaded, file_hash = selection.load_and_validate_control_artifact(
        selection.OUTPUT_PATH,
        expected_file_sha256=V3R7_CONTROL_FILE_SHA256,
    )

    assert file_hash == V3R7_CONTROL_FILE_SHA256
    assert loaded["pass"] is True
    assert loaded["status"] == selection.PASS
    assert loaded["frozen_sources_start"] == loaded["frozen_sources_end"]
    assert (
        loaded["execution_dependencies_start"]
        == loaded["execution_dependencies_end"]
    )


def test_registered_v3r7_control_compat_loader_rejects_wrong_file_identity() -> None:
    with pytest.raises(selection.SelectionError, match="file SHA-256 mismatch"):
        selection.load_and_validate_control_artifact(
            selection.OUTPUT_PATH,
            expected_file_sha256="0" * 64,
        )


def test_registered_v3r7_control_compat_loader_rejects_recorded_audit_failure() -> None:
    artifact = deepcopy(_registered_v3r7_control())
    artifact.pop("artifact_content_sha256")
    artifact["scales"]["1x"]["control"]["audit"]["pass"] = False
    artifact = selection.with_content_hash(artifact)

    with pytest.raises(selection.SelectionError, match="recorded control audit"):
        selection._validate_control_artifact_mapping(artifact)


def test_registered_v3r7_control_compat_loader_rejects_current_replay_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        selection,
        "audit_g31_control_payload",
        lambda **_kwargs: {"pass": False, "status": selection.NO_GO},
    )

    with pytest.raises(selection.SelectionError, match="current deep replay"):
        selection._validate_control_artifact_mapping(
            deepcopy(_registered_v3r7_control())
        )


def test_control_deep_replay_accepts_complete_mock_and_rejects_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one, one_hashes = _mock_scale_selection(1)
    two, two_hashes = _mock_scale_selection(2)
    monkeypatch.setattr(
        selection, "EXPECTED_SELECTION_HASHES", {1: one_hashes, 2: two_hashes}
    )
    monkeypatch.setattr(
        selection,
        "regenerate_and_select",
        lambda *_args, **_kwargs: {1: one, 2: two},
    )

    def replay_audit(**values: Any) -> dict[str, Any]:
        passed = values["payload"]["summary"]["completed_count"] == 2
        return {
            "pass": passed,
            "status": selection.PASS if passed else selection.NO_GO,
            "checks": {"mock_deep_replay": passed},
            "qualifying_event_count": 1 if passed else 0,
            "qualifying_events": [],
            "service_episodes_sha256": selection.canonical_sha256([]),
            "service_episodes": [],
        }

    monkeypatch.setattr(selection, "audit_g31_control_payload", replay_audit)
    artifact = selection.run_control_selection(executor=lambda **_request: _payload(), _test_only=True)

    validated = selection._validate_control_artifact_mapping(artifact)
    assert validated["pass"] is True
    assert validated["control_revision_id"] == selection.CONTROL_REVISION_ID
    assert validated["scales"]["1x"]["control"]["audit"]["pass"] is True

    wrong_revision = deepcopy(artifact)
    wrong_revision["control_revision_id"] = "V3R3_TERMINAL_REVISION"
    wrong_revision["artifact_content_sha256"] = selection.canonical_sha256(
        {
            key: value
            for key, value in wrong_revision.items()
            if key != "artifact_content_sha256"
        }
    )
    with pytest.raises(
        selection.SelectionError, match="source/dependency checkpoints"
    ):
        selection._validate_control_artifact_mapping(wrong_revision)

    tampered = deepcopy(artifact)
    scale = tampered["scales"]["1x"]
    control = scale["control"]
    payload = control["payload"]
    payload["summary"]["completed_count"] = 1
    auditor = selection._v3_auditor()
    control["payload_sha256"] = selection.canonical_sha256(payload)
    control["ordinary_payload_hashes"] = auditor.ordinary_payload_hashes(payload)
    without_hash = {
        key: value
        for key, value in tampered.items()
        if key != "artifact_content_sha256"
    }
    tampered["artifact_content_sha256"] = selection.canonical_sha256(without_hash)

    with pytest.raises(selection.SelectionError, match="deep replay"):
        selection._validate_control_artifact_mapping(tampered)


def test_control_run_retains_completed_scale_when_later_scale_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one, one_hashes = _mock_scale_selection(1)
    two, two_hashes = _mock_scale_selection(2)
    monkeypatch.setattr(
        selection, "EXPECTED_SELECTION_HASHES", {1: one_hashes, 2: two_hashes}
    )
    monkeypatch.setattr(
        selection,
        "regenerate_and_select",
        lambda *_args, **_kwargs: {1: one, 2: two},
    )
    monkeypatch.setattr(
        selection,
        "audit_g31_control_payload",
        lambda **_values: {
            "pass": True,
            "status": selection.PASS,
            "checks": {"mock": True},
            "qualifying_event_count": 1,
            "qualifying_events": [],
            "service_episodes": [],
        },
    )
    calls = 0

    def executor(**_request: Any) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("mock 2x executor failure")
        return _payload()

    artifact = selection.run_control_selection(executor=executor, _test_only=True)

    assert artifact["pass"] is False
    assert artifact["status"] == selection.NO_GO
    assert artifact["scales"]["1x"]["pass"] is True
    assert artifact["scales"]["2x"]["pass"] is False
    assert artifact["scales"]["2x"]["error_type"] == "RuntimeError"
    assert "mock 2x executor failure" in artifact["scales"]["2x"]["error"]
    assert artifact["frozen_sources_unchanged"] is True
    assert artifact["execution_dependencies_unchanged"] is True
    assert selection.verify_content_hash(artifact) == artifact[
        "artifact_content_sha256"
    ]


def test_control_preflight_rejects_binary_and_regeneration_drift_before_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"regenerate": 0, "executor": 0}

    def regenerate(*_args: Any, **_kwargs: Any) -> Mapping[int, Mapping[str, Any]]:
        calls["regenerate"] += 1
        return {}

    def executor(**_request: Any) -> Mapping[str, Any]:
        calls["executor"] += 1
        return {}

    monkeypatch.setattr(selection, "regenerate_and_select", regenerate)
    wrong_binary = tmp_path / "wrong-g31.pyd"
    wrong_binary.write_bytes(b"not-the-frozen-binary")
    with pytest.raises(selection.SelectionError, match="frozen Release path"):
        selection.run_control_selection(binary=wrong_binary, executor=executor, _test_only=True)
    assert calls == {"regenerate": 0, "executor": 0}

    frozen_digest = selection.FROZEN_SOURCE_HASHES[selection.G31_BINARY]
    monkeypatch.setitem(
        selection.FROZEN_SOURCE_HASHES, selection.G31_BINARY, "0" * 64
    )
    with pytest.raises(selection.SelectionError, match="SHA-256 changed"):
        selection.run_control_selection(executor=executor, _test_only=True)
    assert calls == {"regenerate": 0, "executor": 0}
    monkeypatch.setitem(
        selection.FROZEN_SOURCE_HASHES, selection.G31_BINARY, frozen_digest
    )

    one, one_hashes = _mock_scale_selection(1)
    two, two_hashes = _mock_scale_selection(2)
    one["workload"]["regenerated_raw_sha256"] = "0" * 64
    monkeypatch.setattr(
        selection, "EXPECTED_SELECTION_HASHES", {1: one_hashes, 2: two_hashes}
    )
    monkeypatch.setattr(
        selection,
        "regenerate_and_select",
        lambda *_args, **_kwargs: {1: one, 2: two},
    )
    with pytest.raises(selection.SelectionError, match="regenerated workload"):
        selection.run_control_selection(executor=executor, _test_only=True)
    assert calls["executor"] == 0


def test_load_bound_json_hashes_and_parses_one_byte_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bound.json"
    data = b'{"schema":"one-read"}'
    path.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    original_read_bytes = Path.read_bytes
    reads = 0

    def tracked_read_bytes(value: Path) -> bytes:
        nonlocal reads
        if value.resolve() == path.resolve():
            reads += 1
        return original_read_bytes(value)

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
    loaded, actual = selection._load_bound_json(
        path, expected, label="one-read fixture"
    )

    assert loaded == {"schema": "one-read"}
    assert actual == expected
    assert reads == 1


def test_synthetic_loader_accepts_complete_mock_and_rejects_case_tamper(
    tmp_path: Path,
) -> None:
    g32_sha = "3" * 64
    head = "a" * 40
    g32_path = str((tmp_path / "g32.pyd").resolve())
    g31_path = str((tmp_path / "g31.pyd").resolve())
    g31_sha = "1" * 64
    proof_executable = tmp_path / "proof.exe"
    nested_proof_executable = tmp_path / "nested-proof.exe"
    proof_executable.write_bytes(b"mock registered native proof executable")
    nested_proof_executable.write_bytes(
        b"mock registered nested native proof executable"
    )
    proof_executable_sha = selection.file_sha256(proof_executable)
    nested_proof_executable_sha = selection.file_sha256(nested_proof_executable)
    synthetic_revision_id = selection.SYNTHETIC_REVISION_ID
    campaign_revision_id = selection.CAMPAIGN_REVISION_ID
    protocol_bag_rows = [{"goal": 2}, {"goal": 2}]
    safety_protocol_cases = [
        {
            "cohort": "safety_regression",
            "replica": None,
            "case_id": f"case-{index:03d}",
            "service_seconds": 1.0,
            "bag_count": 2,
            "flow_pattern": "simultaneous_local_first",
            "negative_control": False,
            "bag_rows": deepcopy(protocol_bag_rows),
            "bag_rows_sha256": selection.canonical_sha256(protocol_bag_rows),
        }
        for index in range(120)
    ]
    identification_flow_patterns = tuple(
        f"identification_p{index}" for index in range(4)
    )
    identification_protocol_cases = [
        {
            "cohort": "identification",
            "replica": index % 2,
            "case_id": f"identification-case-{index:03d}",
            "service_seconds": 1.0,
            "bag_count": 2,
            "flow_pattern": identification_flow_patterns[(index // 2) % 4],
            "negative_control": False,
            "bag_rows": deepcopy(protocol_bag_rows),
            "bag_rows_sha256": selection.canonical_sha256(protocol_bag_rows),
        }
        for index in range(24)
    ]
    protocol_cohorts = {
        "safety_regression": {
            "case_count": 120,
            "cases": safety_protocol_cases,
            "cases_sha256": selection.canonical_sha256(safety_protocol_cases),
        },
        "identification": {
            "case_count": 24,
            "cases": identification_protocol_cases,
            "cases_sha256": selection.canonical_sha256(
                identification_protocol_cases
            ),
        },
    }
    protocol = {
        "synthetic_revision_id": synthetic_revision_id,
        "campaign_revision_id": campaign_revision_id,
        "historical_control_revision_id": selection.CONTROL_REVISION_ID,
        "case_count": 144,
        "cohorts": protocol_cohorts,
        "cohorts_sha256": selection.canonical_sha256(protocol_cohorts),
    }
    source_files = [{"path": "runner.py", "sha256": "4" * 64}]
    source_bundle = {
        "files": source_files,
        "sha256": selection.canonical_sha256(source_files),
    }

    def gates(names: set[str]) -> list[dict[str, Any]]:
        return [
            {"name": name, "pass": True, "evidence": None}
            for name in sorted(names)
        ]

    resources = {
        "pass": True,
        "gates": [
            {
                "name": name,
                "pass": True,
                "evidence": {
                    "limit": selection.RESOURCE_RATIO_LIMIT,
                    "max_ratio": 1.0,
                    "non_finite": 0,
                },
            }
            for name in sorted(selection.RESOURCE_GATE_NAMES)
        ],
    }
    primary = {
        "pass": True,
        "gates": gates(selection.IDENTIFICATION_PRIMARY_GATE_NAMES),
    }
    safety_evaluation = {
        "pass": True,
        "gates": gates(selection.SAFETY_REGRESSION_GATE_NAMES),
    }
    auditor = selection._v3_auditor()
    _selected_rows, request = _request()
    payload = _payload()
    exact_audit = auditor._service_audit(
        "mock", 2, {"external", "local"}, payload, request, exact_node=49
    )

    def general_service_audit(
        *,
        bag_count: int = 8,
        exact_node: int | None = None,
        sources: tuple[str, ...] = ("local", "external"),
        goal: int = 2,
    ) -> Mapping[str, Any]:
        configured_nodes = sorted({0, 1, goal})
        bag_records = []
        bags = []
        events = []
        for index in range(bag_count):
            source = sources[index % len(sources)]
            bag_records.append(
                (f"map2-{index}", 1000 + index, 0.0, 100.0, 0, goal, source)
            )
            bags.append(
                {
                    "runtime_bag_id": index,
                    "segment_id": f"map2-{index}",
                    "task_id": 1000 + index,
                    "release_time": 0.0,
                    "deadline": 100.0,
                    "start": 0,
                    "goal": goal,
                    "source": source,
                    "completed": True,
                    "finish_time": float(index + 2),
                    "total_local_wait": 0.0,
                    "starved": False,
                }
            )
            events.append(
                {
                    "seq": index + 1,
                    "event": "JUNCTION_SERVICE_COMPLETE",
                    "runtime_bag_id": index,
                    "task_id": 1000 + index,
                    "node": 1,
                    "from_node": 0,
                    "to_node": 1,
                    "time": float(index + 1),
                    "reason": "junction_service_complete",
                }
            )
        summary = deepcopy(payload["summary"])
        summary.update(
            requested_count=bag_count,
            completed_count=bag_count,
            failed_count=0,
            final_active_bag_count=0,
            starvation_count=0,
        )
        semantic_payload = {
            "trace_context": {"schema_id": auditor.ORDINARY_TRACE_SCHEMA_ID},
            "summary": summary,
            "bags": bags,
            "events": events,
            "decisions": [],
            "hold_attempts": [],
            "merge_grant_lifecycle": [],
            "junction_state": [
                {
                    "node": node,
                    "service_reservation_count": bag_count if node == 1 else 0,
                    "final_source_queue_length": 0,
                    "final_junction_queue_length": 0,
                    "scheduled_incoming": 0,
                }
                for node in configured_nodes
            ],
            auditor.ROW_KEY: [],
        }
        semantic_request = {
            "minimum_service_seconds": 0.001,
            "complete_on_goal_arrival": True,
            "node_records": [
                [0, 7, 0.0, 0, 0, [1]],
                [1, 1, 1.0, 1, 0, [goal]],
                [goal, 2, 0.0, 2, 0, []],
            ],
            "bag_records": bag_records,
        }
        return auditor._service_audit(
            "mock-stage0",
            bag_count,
            set(sources),
            semantic_payload,
            semantic_request,
            exact_node=exact_node,
        )

    general_audit = general_service_audit()
    exact_audit = general_service_audit(bag_count=2, exact_node=1)
    stage0_case_audit = general_service_audit(exact_node=1)
    future_probe_service = general_service_audit(bag_count=10, exact_node=1)
    distant_probe_service = general_service_audit(
        bag_count=9,
        sources=("local", "external", "distant"),
    )
    legacy_pair = auditor.legacy_wait_pair(payload, payload)
    ordinary_hashes = {name: "6" * 64 for name in selection.ORDINARY_PAYLOAD_HASH_NAMES}
    off_resource_values = {
        "events_per_completed": 10.0,
        "junction_local_accounted_bytes": 100.0,
        "runtime_internal_accounted_bytes": 100.0,
        "trace_sidecar_accounted_bytes": 0.0,
        "total_accounted_bytes": 100.0,
    }
    shadow_resource_values = {
        "events_per_completed": 10.5,
        "junction_local_accounted_bytes": 100.0,
        "runtime_internal_accounted_bytes": 102.0,
        "trace_sidecar_accounted_bytes": 5.0,
        "total_accounted_bytes": 107.0,
    }
    census = {
        "pass": True,
        **{name: True for name in selection.CENSUS_CHECK_NAMES},
        "values": {
            "external_commit_considered_count": 0,
            "direct_external_commit_count": 0,
            "j2_exact_commit_count": 0,
            **{
                name: 0
                for name in selection.CENSUS_PART_NAMES
                | selection.CENSUS_ZERO_NAMES
            },
        },
        "ordinary_commit_counts": {"direct": 0, "j2": 0, "unclassified": 0},
    }
    empty_hash = selection.canonical_sha256([])
    safety_cases = [
        {
            "cohort": row["cohort"],
            "replica": row["replica"],
            "case_id": row["case_id"],
            "service_seconds": row["service_seconds"],
            "bag_count": row["bag_count"],
            "flow_pattern": row["flow_pattern"],
            "negative_control": row["negative_control"],
            "admitted_row_count": 0,
            "hard_gate_pass": True,
            "join_status": "V3R2_OUTCOME_JOINED",
            "census_partition_pass": True,
            "loaded_cpp_binary_path": g32_path,
            "loaded_cpp_binary_sha256": g32_sha,
            "ordinary_parity": True,
            "request_parity": True,
            "binary_parity": True,
            "off_audit": deepcopy(exact_audit),
            "shadow_audit": deepcopy(exact_audit),
            "legacy_wait_over_120": deepcopy(legacy_pair),
            "service_sequence_parity": {
                "sequence_sha256": True,
                "origin_sequence_sha256": True,
                "maximum_consecutive_origin_run": True,
            },
            "census": deepcopy(census),
            "off_hashes": deepcopy(ordinary_hashes),
            "shadow_hashes": deepcopy(ordinary_hashes),
            "rows_sha256": empty_hash,
            "pairs_sha256": empty_hash,
            "profile_sha256": "7" * 64,
            "potential_sha256": "8" * 64,
            "off_request_sha256": "9" * 64,
            "shadow_request_sha256": "a" * 64,
            "off_ordinary_request_sha256": "b" * 64,
            "shadow_ordinary_request_sha256": "b" * 64,
            "resources": {
                "off": deepcopy(off_resource_values),
                "shadow": deepcopy(shadow_resource_values),
            },
        }
        for row in safety_protocol_cases
    ]
    identification_cases = []
    for row in identification_protocol_cases:
        value = deepcopy(safety_cases[0])
        value.update(
            cohort=row["cohort"],
            replica=row["replica"],
            case_id=row["case_id"],
            service_seconds=row["service_seconds"],
            bag_count=row["bag_count"],
            flow_pattern=row["flow_pattern"],
            negative_control=row["negative_control"],
        )
        identification_cases.append(value)
    synthetic_path = tmp_path / "synthetic.json"
    stage0_request_j2_calls: list[tuple[str, bool]] = []

    class FakeAuditor:
        V3R2Case = auditor.V3R2Case
        IdentificationCase = auditor.IdentificationCase
        IDENTIFICATION_FLOW_PATTERNS = identification_flow_patterns
        SCHEMA = "mock.synthetic.schema"
        SYNTHETIC_REVISION_ID = synthetic_revision_id
        CAMPAIGN_REVISION_ID = campaign_revision_id
        SYNTHETIC_PASS = "MOCK_SYNTHETIC_PASS"
        STAGE0_PASS = "MOCK_STAGE0_PASS"
        FINAL_GO = "MOCK_FINAL_GO_LABEL"
        JOINED = "V3R2_OUTCOME_JOINED"
        BOOTSTRAP_DRAWS = 5
        RESOURCE_RATIO_LIMIT = 1.10
        OUTPUT_JSON = synthetic_path
        NATIVE_PROOF_EXE = proof_executable
        NESTED_PROOF_EXE = nested_proof_executable
        NATIVE_PROOF_SCHEMA = "mock.native.proof"
        NATIVE_PROOF_TEST_ID = "mock-native-test"
        NATIVE_PROOF_ASSERTIONS = ("native_assertion_a", "native_assertion_b")
        NESTED_PROOF_SCHEMA = "mock.nested.proof"
        NESTED_PROOF_TEST_ID = "mock-nested-test"
        NESTED_PROOF_ASSERTION = "nested_assertion"
        G31_BINARY = Path(g31_path)
        G31_BINARY_SHA256 = g31_sha
        MAP2_RAW_SHA256 = "1" * 64
        MAP2_PROFILE_SHA256 = "2" * 64
        MAP2_POTENTIAL_SHA256 = "3" * 64
        MAP2_ROWS_SHA256 = "4" * 64
        MAP2_SEGMENTS = tuple(f"segment-{index}" for index in range(8))
        ORDINARY_RESOURCE_SUMMARY_KEYS = {
            "cpp_internal_accounted_bytes",
            "internal_state_bytes",
        }
        normalize_numeric_rows = staticmethod(auditor.normalize_numeric_rows)
        request_sha256 = staticmethod(auditor.request_sha256)
        profile_sha256 = staticmethod(auditor.profile_sha256)

        @staticmethod
        def build_request(
            case: Any,
            *,
            mode: str,
            binary: Path | None = None,
            j2: bool = False,
        ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
            assert mode == "off"
            assert binary is None
            if case.bag_count == 2:
                return (
                    FakeAuditor._probe_request(
                        prefix="stage1",
                        releases=(0.0,),
                        sources=("external", "local"),
                    ),
                    {},
                )
            stage0_request_j2_calls.append((case.flow_pattern, j2))
            return (
                FakeAuditor._probe_request(
                    prefix="stage0",
                    releases=(0.0,),
                    sources=tuple(
                        "external" if index % 2 == 0 else "local"
                        for index in range(case.bag_count)
                    ),
                ),
                {},
            )

        @staticmethod
        def build_identification_request(
            case: Any, *, mode: str, binary: Path | None = None
        ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
            assert mode == "off"
            assert binary is None
            return (
                FakeAuditor._probe_request(
                    prefix=f"identification-r{case.replica}",
                    releases=(0.0,),
                    sources=("external", "local"),
                ),
                {},
            )

        @staticmethod
        def _probe_request(
            *,
            prefix: str,
            releases: tuple[float, ...],
            sources: tuple[str, ...],
        ) -> Mapping[str, Any]:
            bag_count = len(sources)
            return {
                "minimum_service_seconds": 0.001,
                "complete_on_goal_arrival": True,
                "node_records": [
                    [0, 7, 0.0, 0, 0, [1]],
                    [1, 1, 1.0, 1, 0, [2]],
                    [2, 2, 0.0, 2, 0, []],
                ],
                "edge_records": [[0, 1, 1.0, 1.0], [1, 2, 1.0, 1.0]],
                "heuristic_time": [
                    [0.0, 1.0, 2.0],
                    [1.0, 0.0, 1.0],
                    [2.0, 1.0, 0.0],
                ],
                "storage_source_nodes": [0],
                "bag_records": [
                    (
                        f"{prefix}-{index}",
                        index,
                        float(releases[index % len(releases)]),
                        1_000.0,
                        0,
                        2,
                        source,
                    )
                    for index, source in enumerate(sources)
                ],
                "scenario": f"mock-{prefix}-{bag_count}",
            }

        @staticmethod
        def build_bag_rows(case: Any) -> list[dict[str, int]]:
            return [{"goal": 2} for _index in range(case.bag_count)]

        @staticmethod
        def _future_request(
            _case: Any, releases: tuple[float, float], _binary: Path | None
        ) -> Mapping[str, Any]:
            return FakeAuditor._probe_request(
                prefix="future",
                releases=releases,
                sources=tuple(
                    "external" if index % 2 == 0 else "local"
                    for index in range(10)
                ),
            )

        @staticmethod
        def _distant_request(
            _case: Any, _binary: Path | None
        ) -> Mapping[str, Any]:
            return FakeAuditor._probe_request(
                prefix="distant",
                releases=(0.0,),
                sources=("external", "local", "distant") * 3,
            )

        @staticmethod
        def map2_fixture(
            *, mode: str, binary: Path | None = None
        ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
            assert mode == "off"
            assert binary is None
            return (
                FakeAuditor._probe_request(
                    prefix="map2",
                    releases=(0.0,),
                    sources=("local",) * 8,
                ),
                {
                    "raw": FakeAuditor.MAP2_RAW_SHA256,
                    "profile": FakeAuditor.MAP2_PROFILE_SHA256,
                    "potential": FakeAuditor.MAP2_POTENTIAL_SHA256,
                    "rows": FakeAuditor.MAP2_ROWS_SHA256,
                    "segments": list(FakeAuditor.MAP2_SEGMENTS),
                    "storage_source_nodes": [52],
                },
            )

        @staticmethod
        def population_manifest() -> Mapping[str, Any]:
            return deepcopy(protocol)

        @staticmethod
        def source_bundle_manifest() -> Mapping[str, Any]:
            return deepcopy(source_bundle)

        @staticmethod
        def evaluate_safety_regression(
            _cases: list[Mapping[str, Any]],
        ) -> Mapping[str, Any]:
            return deepcopy(safety_evaluation)

        @staticmethod
        def evaluate_identification_primary(
            _pairs: list[Mapping[str, Any]],
            _cases: list[Mapping[str, Any]],
            *,
            draws: int,
        ) -> Mapping[str, Any]:
            assert draws == 5
            return deepcopy(primary)

        @staticmethod
        def evaluate_resources(
            _cases: list[Mapping[str, Any]],
        ) -> Mapping[str, Any]:
            return deepcopy(resources)

    observations: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    cross_ordinary = {
        name: "e" * 64 for name in selection.ORDINARY_PAYLOAD_HASH_NAMES
    }
    cross_accounting = {
        "cpp_internal_accounted_bytes": 100.0,
        "internal_state_bytes": 100.0,
    }

    def cross_run(
        *, binary_path: str, binary_sha256: str, request_sha256: str
    ) -> dict[str, Any]:
        return {
            "schema": selection.CROSS_BINARY_WORKER_SCHEMA,
            "binary_path": binary_path,
            "binary_sha256": binary_sha256,
            "request_sha256": request_sha256,
            "ordinary_request_sha256": "f" * 64,
            "ordinary": deepcopy(cross_ordinary),
            "accounting": deepcopy(cross_accounting),
            "extension_absent": True,
        }

    cross_runs = {
        "g31_parent": cross_run(
            binary_path=g31_path,
            binary_sha256=g31_sha,
            request_sha256="7" * 64,
        ),
        "g32_explicit": cross_run(
            binary_path=g32_path,
            binary_sha256=g32_sha,
            request_sha256="8" * 64,
        ),
        "g32_omitted": cross_run(
            binary_path=g32_path,
            binary_sha256=g32_sha,
            request_sha256="7" * 64,
        ),
        "g32_repeated": cross_run(
            binary_path=g32_path,
            binary_sha256=g32_sha,
            request_sha256="8" * 64,
        ),
    }

    anchor_case_id = "v3r2_simultaneous_local_first__n8__service_1p0s"

    def census_for_path(path: int | None) -> dict[str, Any]:
        value = deepcopy(census)
        if path is not None:
            value["values"].update(
                external_commit_considered_count=1,
                direct_external_commit_count=1 if path == 1 else 0,
                j2_exact_commit_count=1 if path == 2 else 0,
                observation_stored_count=1,
            )
            value["ordinary_commit_counts"] = {
                "direct": 1 if path == 1 else 0,
                "j2": 1 if path == 2 else 0,
                "unclassified": 0,
            }
        return value

    direct_row = {
        "case_id": anchor_case_id,
        "observation_ordinal": 1,
        "opportunity_id": 1,
        "external_path_code": 1,
        "external_runtime_bag_id": 1,
        "external_task_id": 1001,
        "external_upstream_node": 0,
        "node": 1,
        "external_direct_episode_event_seq": 101,
    }
    j2_row = {
        "case_id": anchor_case_id,
        "observation_ordinal": 1,
        "opportunity_id": 2,
        "external_path_code": 2,
        "external_runtime_bag_id": 2,
        "external_task_id": 1002,
        "external_upstream_node": 0,
        "node": 1,
        "external_request_id": 201,
        "external_request_lineage": 202,
        "external_request_generation": 203,
        "external_junction_queue_generation": 204,
    }

    def joined_pair(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "case_id": row["case_id"],
            "observation_ordinal": row["observation_ordinal"],
            "opportunity_id": row["opportunity_id"],
            "primary": True,
            "status": FakeAuditor.JOINED,
            "reason": "MOCK_JOINED",
            "local": {},
            "external": {},
            "Y_realized": 1.0,
            "A_gap": 1.0,
            "X_insert": 1.0,
            "H_gap": 1.0,
            "case_status": FakeAuditor.JOINED,
        }

    direct_fixture = {
        "rows": [direct_row],
        "pairs": [joined_pair(direct_row)],
        "off_ordinary_hashes": deepcopy(ordinary_hashes),
        "shadow_ordinary_hashes": deepcopy(ordinary_hashes),
    }
    j2_fixture = {
        "rows": [j2_row],
        "pairs": [joined_pair(j2_row)],
        "off_ordinary_hashes": deepcopy(ordinary_hashes),
        "shadow_ordinary_hashes": deepcopy(ordinary_hashes),
    }
    empty_fixture = {
        "rows": [],
        "pairs": [],
        "off_ordinary_hashes": deepcopy(ordinary_hashes),
        "shadow_ordinary_hashes": deepcopy(ordinary_hashes),
    }
    repeated_fixture = deepcopy(direct_fixture)

    def stage0_case(
        *,
        fixture: Mapping[str, Any],
        flow: str,
        negative: bool,
        path: int | None,
    ) -> dict[str, Any]:
        value = deepcopy(safety_cases[0])
        value.update(
            case_id=f"v3r2_{flow}__n8__service_1p0s",
            service_seconds=1.0,
            bag_count=8,
            flow_pattern=flow,
            negative_control=negative,
            admitted_row_count=len(fixture["rows"]),
            off_audit=deepcopy(stage0_case_audit),
            shadow_audit=deepcopy(stage0_case_audit),
            census=census_for_path(path),
            off_hashes=deepcopy(fixture["off_ordinary_hashes"]),
            shadow_hashes=deepcopy(fixture["shadow_ordinary_hashes"]),
            rows_sha256=selection.canonical_sha256(fixture["rows"]),
            pairs_sha256=selection.canonical_sha256(fixture["pairs"]),
        )
        return value

    stage0_cases = [
        stage0_case(
            fixture=direct_fixture,
            flow="simultaneous_local_first",
            negative=False,
            path=1,
        ),
        stage0_case(
            fixture=j2_fixture,
            flow="simultaneous_local_first",
            negative=False,
            path=2,
        ),
        stage0_case(
            fixture=empty_fixture,
            flow="external_only",
            negative=True,
            path=None,
        ),
        stage0_case(
            fixture=empty_fixture,
            flow="local_only",
            negative=True,
            path=None,
        ),
    ]

    def probe_audit(service: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "pass": True,
            "row_count": 0,
            "join_status": FakeAuditor.JOINED,
            "census": deepcopy(census),
            "service": deepcopy(service),
            "rows": [],
            "pairs": [],
            "off_ordinary_hashes": None,
            "shadow_ordinary_hashes": deepcopy(ordinary_hashes),
        }

    future_audit = probe_audit(future_probe_service)
    future_b_audit = probe_audit(future_probe_service)
    distant_audit = probe_audit(distant_probe_service)
    anchor = FakeAuditor.V3R2Case(1.0, 8, "simultaneous_local_first")
    future_request_a = FakeAuditor._future_request(
        anchor, (100.0, 120.0), None
    )
    future_request_b = FakeAuditor._future_request(
        anchor, (500.0, 600.0), None
    )
    distant_request = FakeAuditor._distant_request(anchor, None)
    future_probe = {
        "request_a_sha256": FakeAuditor.request_sha256(future_request_a),
        "request_b_sha256": FakeAuditor.request_sha256(future_request_b),
        "profile_a_sha256": FakeAuditor.profile_sha256(future_request_a),
        "profile_b_sha256": FakeAuditor.profile_sha256(future_request_b),
        "potential_a_sha256": selection.canonical_sha256(
            future_request_a["heuristic_time"]
        ),
        "potential_b_sha256": selection.canonical_sha256(
            future_request_b["heuristic_time"]
        ),
        "prefix_sha256": {"a": "7" * 64, "b": "7" * 64},
        "audit": [future_audit, future_b_audit],
    }
    distant_probe = {
        "request_sha256": FakeAuditor.request_sha256(distant_request),
        "profile_sha256": FakeAuditor.profile_sha256(distant_request),
        "potential_sha256": selection.canonical_sha256(
            distant_request["heuristic_time"]
        ),
        "prefix_sha256": {"direct": "b" * 64, "distant": "b" * 64},
        "audit": distant_audit,
    }
    map2_hashes = {
        "raw": FakeAuditor.MAP2_RAW_SHA256,
        "profile": FakeAuditor.MAP2_PROFILE_SHA256,
        "potential": FakeAuditor.MAP2_POTENTIAL_SHA256,
        "rows": FakeAuditor.MAP2_ROWS_SHA256,
        "segments": list(FakeAuditor.MAP2_SEGMENTS),
        "storage_source_nodes": [52],
    }
    map2_fixture = deepcopy(empty_fixture)
    stage0_fixtures = {
        "direct": direct_fixture,
        "j2": j2_fixture,
        "external_only": deepcopy(empty_fixture),
        "local_only": deepcopy(empty_fixture),
        "repeated_shadow": repeated_fixture,
        "future_a": future_audit,
        "future_b": future_b_audit,
        "distant": distant_audit,
        "map2": map2_fixture,
    }
    stage0_gate_vector = gates(selection.STAGE0_GATE_NAMES)
    repeat_gate = next(
        gate for gate in stage0_gate_vector if gate["name"] == "shadow_repeat_exact"
    )
    repeat_gate["evidence"] = {
        "hashes": {
            "ordinary": [
                selection.canonical_sha256(ordinary_hashes),
                selection.canonical_sha256(ordinary_hashes),
            ],
            "extension": ["c" * 64, "c" * 64],
            "rows": [
                selection.canonical_sha256(direct_fixture["rows"]),
                selection.canonical_sha256(repeated_fixture["rows"]),
            ],
            "join": ["d" * 64, "d" * 64],
        },
        "repeat_census": census_for_path(1),
        "repeat_resources": deepcopy(shadow_resource_values),
        "error": None,
    }
    map2_gate_vector = gates(selection.MAP2_GATE_NAMES)
    artifact = selection.with_content_hash(
        {
            "schema": FakeAuditor.SCHEMA,
            "synthetic_revision_id": FakeAuditor.SYNTHETIC_REVISION_ID,
            "campaign_revision_id": FakeAuditor.CAMPAIGN_REVISION_ID,
            "historical_control_revision_id": selection.CONTROL_REVISION_ID,
            "status": FakeAuditor.SYNTHETIC_PASS,
            "decision": FakeAuditor.SYNTHETIC_PASS,
            "synthetic_pass": True,
            "nanning_p0_status": "PENDING_NOT_RUN_BY_SYNTHETIC_RUNNER",
            "p1_review_authorized": False,
            "protocol": protocol,
            "source_bundle": source_bundle,
            "source_bundle_checkpoints": {
                "start": source_bundle,
                "after_stage0": source_bundle,
                "after_stage1": source_bundle,
            },
                "implementation": {
                    "pass": True,
                    "head": head,
                    "gates": gates(selection.IMPLEMENTATION_GATE_NAMES),
                },
            "implementation_head": head,
            "g32_binary_sha256": g32_sha,
            "issue_remediation_ledger_file": {"sha256": "5" * 64},
            "bootstrap": {"draws": 5},
            "resource_ratio_limit": 1.1,
                "stage0": {
                    "pass": True,
                    "status": FakeAuditor.STAGE0_PASS,
                    "gates": stage0_gate_vector,
                    "native_proof": {
                        "pass": True,
                        "executable_path": str(proof_executable.resolve()),
                        "executable_sha256": proof_executable_sha,
                        "executable_sha256_after": proof_executable_sha,
                        "nested_executable_path": str(
                            nested_proof_executable.resolve()
                        ),
                        "nested_executable_sha256": nested_proof_executable_sha,
                        "nested_executable_sha256_after": nested_proof_executable_sha,
                        "g32_binary_path": g32_path,
                        "build_head": head,
                        "proof_build_head": head,
                        "nested_proof_build_head": head,
                        "g32_binary_sha256": g32_sha,
                        "g32_binary_sha256_after": g32_sha,
                        "source_bundle": source_bundle,
                        "exit_code": 0,
                        "nested_exit_code": 0,
                        "proof": {
                            "schema_id": FakeAuditor.NATIVE_PROOF_SCHEMA,
                            "test_id": FakeAuditor.NATIVE_PROOF_TEST_ID,
                            "build_head": head,
                            **{
                                name: True
                                for name in FakeAuditor.NATIVE_PROOF_ASSERTIONS
                            },
                        },
                        "nested_proof": {
                            "schema_id": FakeAuditor.NESTED_PROOF_SCHEMA,
                            "test_id": FakeAuditor.NESTED_PROOF_TEST_ID,
                            "build_head": head,
                            FakeAuditor.NESTED_PROOF_ASSERTION: True,
                        },
                        "gates": gates(selection.NATIVE_PROOF_GATE_NAMES),
                    },
                    "cross_binary": {
                        "pass": True,
                        "gates": gates(selection.CROSS_BINARY_GATE_NAMES),
                        "runs": cross_runs,
                    },
                    "map2": {
                        "pass": True,
                        "gates": map2_gate_vector,
                        "hashes": map2_hashes,
                        "off_audit": deepcopy(general_audit),
                        "shadow_audit": deepcopy(general_audit),
                        "legacy_wait_over_120": deepcopy(legacy_pair),
                        "service_sequence_parity": {
                            "sequence_sha256": True,
                            "origin_sequence_sha256": True,
                            "maximum_consecutive_origin_run": True,
                        },
                        "rows": [],
                        "pairs": [],
                        "row_count": 0,
                        "join_status": FakeAuditor.JOINED,
                        "census": deepcopy(census),
                        "rows_sha256": empty_hash,
                        "pairs_sha256": empty_hash,
                        "resources": deepcopy(resources),
                        "off_ordinary_hashes": deepcopy(ordinary_hashes),
                        "shadow_ordinary_hashes": deepcopy(ordinary_hashes),
                    },
                    "cases": stage0_cases,
                    "probes": {
                        "future": future_probe,
                        "distant": distant_probe,
                    },
                    "fixtures": stage0_fixtures,
                    "error": None,
                },
                "stage1": {
                    "pass": True,
                    "status": "V3R11_STAGE1_PASS",
                    "gates": gates(selection.STAGE1_GATE_NAMES),
                    "manifest_sha256": protocol["cohorts_sha256"],
                    "safety_regression": {
                        "pass": True,
                        "gates": deepcopy(safety_evaluation["gates"]),
                        "manifest_sha256": protocol_cohorts[
                            "safety_regression"
                        ]["cases_sha256"],
                        "cases": safety_cases,
                        "resources": deepcopy(resources),
                        "observation_count": 0,
                        "observations_sha256": selection.canonical_sha256(
                            observations
                        ),
                        "observations": observations,
                        "pair_count": 0,
                        "pairs_sha256": selection.canonical_sha256(pairs),
                        "pairs": pairs,
                    },
                    "identification": {
                        "pass": True,
                        "manifest_sha256": protocol_cohorts["identification"][
                            "cases_sha256"
                        ],
                        "cases": identification_cases,
                        "primary": primary,
                        "resources": deepcopy(resources),
                        "observation_count": 0,
                        "observations_sha256": selection.canonical_sha256(
                            observations
                        ),
                        "observations": observations,
                        "pair_count": 0,
                        "pairs_sha256": selection.canonical_sha256(pairs),
                        "pairs": pairs,
                    },
                    "resources": resources,
                },
            "issue_remediation_ledger": [],
        }
    )
    selection.atomic_write_strict_json(synthetic_path, artifact)
    expected_file_sha = selection.file_sha256(synthetic_path)

    loaded, actual_file_sha = selection.load_and_validate_synthetic_artifact(
        synthetic_path,
        expected_file_sha256=expected_file_sha,
        expected_g32_binary_sha256=g32_sha,
        auditor=FakeAuditor,
    )
    assert loaded["synthetic_pass"] is True
    assert (
        loaded["synthetic_revision_id"]
        == selection.SYNTHETIC_REVISION_ID
        == "G4IRSF32_V3R11_DEEP_REPLAY_COMPATIBILITY_P0_20260829"
    )
    assert (
        loaded["campaign_revision_id"]
        == selection.CAMPAIGN_REVISION_ID
        == "G4IRSF32_V3R11_P0_CAMPAIGN_20260829"
    )
    assert actual_file_sha == expected_file_sha
    assert stage0_request_j2_calls == [
        ("simultaneous_local_first", False),
        ("simultaneous_local_first", True),
        ("external_only", False),
        ("local_only", False),
    ]

    def publish_tamper(
        tampered_artifact: Mapping[str, Any], *, sort_keys: bool = True
    ) -> None:
        unhashed = {
            key: value
            for key, value in tampered_artifact.items()
            if key != "artifact_content_sha256"
        }
        updated = dict(tampered_artifact)
        updated["artifact_content_sha256"] = selection.canonical_sha256(unhashed)
        synthetic_path.write_text(
            json.dumps(updated, sort_keys=sort_keys, allow_nan=False), encoding="utf-8"
        )

    for field, delete, replacement in (
        ("segments", True, None),
        ("segments", False, ["tampered-segment"]),
        ("storage_source_nodes", True, None),
        ("storage_source_nodes", False, [51]),
    ):
        map2_identity_tampered = deepcopy(artifact)
        hashes = map2_identity_tampered["stage0"]["map2"]["hashes"]
        if delete:
            del hashes[field]
        else:
            hashes[field] = replacement
        publish_tamper(map2_identity_tampered)
        with pytest.raises(
            selection.SelectionError,
            match="map2 hashes|map2 frozen identity",
        ):
            selection.load_and_validate_synthetic_artifact(
                synthetic_path,
                expected_file_sha256=selection.file_sha256(synthetic_path),
                expected_g32_binary_sha256=g32_sha,
                auditor=FakeAuditor,
            )

    completion_tampered = deepcopy(artifact)
    permanent = completion_tampered["stage1"]["safety_regression"]["cases"][0][
        "off_audit"
    ]["permanent_starvation"]
    permanent["bag_completion_vector"][0]["completed"] = False
    permanent["completed_origin_counts"] = {"local": 1}
    permanent["bag_completion_vector_sha256"] = selection.canonical_sha256(
        permanent["bag_completion_vector"]
    )
    publish_tamper(completion_tampered)
    with pytest.raises(selection.SelectionError, match="permanent-starvation"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    duration_tampered = deepcopy(artifact)
    sequence = duration_tampered["stage1"]["safety_regression"]["cases"][0][
        "off_audit"
    ]["service_sequence"]
    sequence["ordered_service_episodes"][0]["complete"] = 61.0
    sequence["sequence_sha256"] = selection.canonical_sha256(
        sequence["ordered_service_episodes"]
    )
    publish_tamper(duration_tampered)
    with pytest.raises(selection.SelectionError, match="service duration"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    lifecycle_tampered = deepcopy(artifact)
    permanent = lifecycle_tampered["stage1"]["safety_regression"]["cases"][0][
        "off_audit"
    ]["permanent_starvation"]
    permanent["lifecycle_final_state_vector"] = [
        {
            "request_id": 1,
            "lineage": 1,
            "request_generation": 1,
            "junction_queue_generation": 1,
            "destination_node": 1,
            "state": "BOGUS",
        }
    ]
    permanent["lifecycle_final_state_vector_sha256"] = selection.canonical_sha256(
        permanent["lifecycle_final_state_vector"]
    )
    permanent["historical_last_lifecycle_state_counts"] = {"BOGUS": 1}
    permanent["merge_request_accounting"].update(
        request_count=1, committed_count=1
    )
    permanent["recomputable_vector_count"] += 1
    permanent["recomputable_vector_limit"] += 1
    publish_tamper(lifecycle_tampered)
    with pytest.raises(selection.SelectionError, match="lifecycle state"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    calendar_tampered = deepcopy(artifact)
    calendar_tampered["stage1"]["safety_regression"]["cases"][0]["off_audit"][
        "global_service_calendar"
    ]["completion_counts"] = {"1": 999}
    publish_tamper(calendar_tampered)
    with pytest.raises(selection.SelectionError, match="completion-count"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    origins_tampered = deepcopy(artifact)
    origins_tampered["stage1"]["safety_regression"]["cases"][0]["off_audit"][
        "origins"
    ] = ["bogus"]
    publish_tamper(origins_tampered)
    with pytest.raises(selection.SelectionError, match="service-audit"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    row_tampered = deepcopy(artifact)
    case = row_tampered["stage1"]["safety_regression"]["cases"][0]
    observation = {
        "cohort": case["cohort"],
        "replica": case["replica"],
        "case_id": case["case_id"],
        "observation_ordinal": 1,
        "opportunity_id": 1,
        "service_seconds": case["service_seconds"],
        "bag_count": case["bag_count"],
        "flow_pattern": case["flow_pattern"],
        "local_origin_code": 99,
        "external_origin_code": 99,
        "calendar_mutation_count": 999,
    }
    pair = {
        **observation,
        "primary": False,
        "status": "V3R2_REPEATED_BAG_DIAGNOSTIC",
        "reason": "EARLIER_PRIMARY_USED_BAG",
        "local": None,
        "external": None,
        "Y_realized": None,
        "A_gap": None,
        "X_insert": None,
        "H_gap": None,
        "case_status": "V3R2_OUTCOME_JOINED",
    }
    row_tampered["stage1"]["safety_regression"].update(
        observation_count=1,
        observations=[observation],
        observations_sha256=selection.canonical_sha256([observation]),
        pair_count=1,
        pairs=[pair],
        pairs_sha256=selection.canonical_sha256([pair]),
    )
    case.update(
        admitted_row_count=1,
        rows_sha256=selection.canonical_sha256([observation]),
        pairs_sha256=selection.canonical_sha256(
            [{key: pair[key] for key in selection.JOIN_PAIR_KEYS}]
        ),
    )
    case["census"]["values"].update(
        external_commit_considered_count=1,
        direct_external_commit_count=1,
        observation_stored_count=1,
    )
    case["census"]["ordinary_commit_counts"]["direct"] = 1
    publish_tamper(row_tampered)
    with pytest.raises(selection.SelectionError, match="V3R4 observation"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    ratio_tampered = deepcopy(artifact)
    ratio_tampered["resource_ratio_limit"] = 1.09
    publish_tamper(ratio_tampered)
    with pytest.raises(selection.SelectionError, match="fixed 1.10"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    class DriftedRatioAuditor(FakeAuditor):
        RESOURCE_RATIO_LIMIT = 1.09

    publish_tamper(artifact)
    with pytest.raises(selection.SelectionError, match="fixed 1.10"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=DriftedRatioAuditor,
        )

    native_identity_tampers = (
        ("executable_sha256_after", "e" * 64, "identity changed"),
        ("nested_executable_sha256", "not-a-sha", "identity changed"),
        ("g32_binary_sha256_after", "f" * 64, "identity changed"),
        ("g32_binary_sha256", "0" * 64, "identity changed"),
        ("proof_build_head", "b" * 40, "build head changed"),
        ("executable_path", str(tmp_path / "other.exe"), "executable path changed"),
        ("g32_binary_path", str(tmp_path / "other.pyd"), "G32 path is unbound"),
    )
    for field, replacement, message in native_identity_tampers:
        identity_tampered = deepcopy(artifact)
        identity_tampered["stage0"]["native_proof"][field] = replacement
        publish_tamper(identity_tampered)
        with pytest.raises(selection.SelectionError, match=message):
            selection.load_and_validate_synthetic_artifact(
                synthetic_path,
                expected_file_sha256=selection.file_sha256(synthetic_path),
                expected_g32_binary_sha256=g32_sha,
                auditor=FakeAuditor,
            )

    missing_identity = deepcopy(artifact)
    del missing_identity["stage0"]["native_proof"][
        "nested_executable_sha256_after"
    ]
    publish_tamper(missing_identity)
    with pytest.raises(selection.SelectionError, match="identity changed"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    wrong_expected_g32 = deepcopy(artifact)
    wrong_expected_g32["stage0"]["native_proof"]["g32_binary_sha256"] = "0" * 64
    wrong_expected_g32["stage0"]["native_proof"][
        "g32_binary_sha256_after"
    ] = "0" * 64
    publish_tamper(wrong_expected_g32)
    with pytest.raises(selection.SelectionError, match="G32 identity changed"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    raw_head_tampered = deepcopy(artifact)
    raw_head_tampered["stage0"]["native_proof"]["nested_proof"][
        "build_head"
    ] = "b" * 40
    publish_tamper(raw_head_tampered)
    with pytest.raises(selection.SelectionError, match="build head changed"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    raw_native_tampers = (
        ("proof", "native_assertion_a", False),
        ("proof", "schema_id", "wrong.native.schema"),
        ("proof", "test_id", "wrong-native-test"),
        ("nested_proof", "nested_assertion", False),
        ("nested_proof", "schema_id", "wrong.nested.schema"),
        ("nested_proof", "test_id", "wrong-nested-test"),
    )
    for payload_name, field, replacement in raw_native_tampers:
        raw_tampered = deepcopy(artifact)
        raw_tampered["stage0"]["native_proof"][payload_name][field] = replacement
        publish_tamper(raw_tampered)
        with pytest.raises(selection.SelectionError, match="gate replay changed"):
            selection.load_and_validate_synthetic_artifact(
                synthetic_path,
                expected_file_sha256=selection.file_sha256(synthetic_path),
                expected_g32_binary_sha256=g32_sha,
                auditor=FakeAuditor,
            )

    missing_raw_field = deepcopy(artifact)
    del missing_raw_field["stage0"]["native_proof"]["proof"][
        "native_assertion_b"
    ]
    publish_tamper(missing_raw_field)
    with pytest.raises(selection.SelectionError, match="keys differ"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    for exit_name, exit_value in (
        ("exit_code", 1),
        ("nested_exit_code", 1),
        ("exit_code", False),
    ):
        exit_tampered = deepcopy(artifact)
        exit_tampered["stage0"]["native_proof"][exit_name] = exit_value
        publish_tamper(exit_tampered)
        with pytest.raises(selection.SelectionError, match="gate replay changed"):
            selection.load_and_validate_synthetic_artifact(
                synthetic_path,
                expected_file_sha256=selection.file_sha256(synthetic_path),
                expected_g32_binary_sha256=g32_sha,
                auditor=FakeAuditor,
            )

    cross_tampers = (
        ("g31_parent", "schema", "wrong.worker.schema", "worker evidence"),
        ("g31_parent", "binary_sha256", "2" * 64, "G31 identity"),
        ("g32_explicit", "binary_path", str(tmp_path / "other.pyd"), "G32 identity"),
        ("g32_omitted", "ordinary_request_sha256", "0" * 64, "gate replay"),
        ("g32_repeated", "extension_absent", False, "worker evidence"),
    )
    for run_name, field, replacement, message in cross_tampers:
        cross_tampered = deepcopy(artifact)
        cross_tampered["stage0"]["cross_binary"]["runs"][run_name][
            field
        ] = replacement
        publish_tamper(cross_tampered)
        with pytest.raises(selection.SelectionError, match=message):
            selection.load_and_validate_synthetic_artifact(
                synthetic_path,
                expected_file_sha256=selection.file_sha256(synthetic_path),
                expected_g32_binary_sha256=g32_sha,
                auditor=FakeAuditor,
            )

    missing_cross_run = deepcopy(artifact)
    del missing_cross_run["stage0"]["cross_binary"]["runs"]["g32_repeated"]
    publish_tamper(missing_cross_run)
    with pytest.raises(selection.SelectionError, match="run labels/order"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    missing_cross_field = deepcopy(artifact)
    del missing_cross_field["stage0"]["cross_binary"]["runs"]["g31_parent"][
        "accounting"
    ]
    publish_tamper(missing_cross_field)
    with pytest.raises(selection.SelectionError, match="keys differ"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    reordered_cross_runs = deepcopy(artifact)
    original_runs = reordered_cross_runs["stage0"]["cross_binary"]["runs"]
    reordered_cross_runs["stage0"]["cross_binary"]["runs"] = {
        name: original_runs[name] for name in reversed(selection.CROSS_BINARY_RUN_NAMES)
    }
    publish_tamper(reordered_cross_runs, sort_keys=False)
    with pytest.raises(selection.SelectionError, match="run labels/order"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    missing_stage0_fixture = deepcopy(artifact)
    del missing_stage0_fixture["stage0"]["fixtures"]["direct"]
    publish_tamper(missing_stage0_fixture)
    with pytest.raises(selection.SelectionError, match="fixture set changed"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    missing_stage0_roles = deepcopy(artifact)
    missing_stage0_roles["stage0"]["cases"] = []
    publish_tamper(missing_stage0_roles)
    with pytest.raises(selection.SelectionError, match="four frozen roles"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    prefix_tampered = deepcopy(artifact)
    prefix_tampered["stage0"]["probes"]["future"]["prefix_sha256"]["b"] = (
        "0" * 64
    )
    publish_tamper(prefix_tampered)
    with pytest.raises(selection.SelectionError, match="fixture/probe gate replay"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    map2_deadline_tampered = deepcopy(artifact)
    permanent = map2_deadline_tampered["stage0"]["map2"]["off_audit"][
        "permanent_starvation"
    ]
    permanent["bag_completion_vector"][0]["deadline"] = 0.0
    permanent["late_runtime_bag_ids"] = [0]
    permanent["bag_completion_vector_sha256"] = selection.canonical_sha256(
        permanent["bag_completion_vector"]
    )
    publish_tamper(map2_deadline_tampered)
    with pytest.raises(selection.SelectionError, match="permanent-starvation replay"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    proof_executable.write_bytes(b"changed after native proof publication")
    publish_tamper(artifact)
    with pytest.raises(selection.SelectionError, match="current identity changed"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )
    proof_executable.write_bytes(b"mock registered native proof executable")

    over_limit = deepcopy(artifact)
    over_limit["stage1"]["safety_regression"]["cases"][0]["resources"][
        "shadow"
    ].update(
        runtime_internal_accounted_bytes=106.0,
        trace_sidecar_accounted_bytes=5.0,
        total_accounted_bytes=111.0,
    )
    unhashed = {
        key: value
        for key, value in over_limit.items()
        if key != "artifact_content_sha256"
    }
    over_limit["artifact_content_sha256"] = selection.canonical_sha256(unhashed)
    synthetic_path.write_text(
        json.dumps(over_limit, sort_keys=True, allow_nan=False), encoding="utf-8"
    )
    with pytest.raises(selection.SelectionError, match="hard gate"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    self_authorizing = deepcopy(artifact)
    self_authorizing["final_go_label"] = FakeAuditor.FINAL_GO
    unhashed = {
        key: value
        for key, value in self_authorizing.items()
        if key != "artifact_content_sha256"
    }
    self_authorizing["artifact_content_sha256"] = selection.canonical_sha256(
        unhashed
    )
    synthetic_path.write_text(
        json.dumps(self_authorizing, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    with pytest.raises(selection.SelectionError, match="keys differ"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    tampered = deepcopy(artifact)
    tampered["stage1"]["safety_regression"]["cases"][0][
        "hard_gate_pass"
    ] = False
    unhashed = {
        key: value
        for key, value in tampered.items()
        if key != "artifact_content_sha256"
    }
    tampered["artifact_content_sha256"] = selection.canonical_sha256(unhashed)
    synthetic_path.write_text(
        json.dumps(tampered, sort_keys=True, allow_nan=False), encoding="utf-8"
    )
    with pytest.raises(selection.SelectionError, match="hard gate|sequencing evidence"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )

    vector_tampered = deepcopy(artifact)
    vector_tampered["stage1"]["safety_regression"]["cases"][0]["off_audit"][
        "service_sequence"
    ]["sequence_sha256"] = "0" * 64
    unhashed = {
        key: value
        for key, value in vector_tampered.items()
        if key != "artifact_content_sha256"
    }
    vector_tampered["artifact_content_sha256"] = selection.canonical_sha256(
        unhashed
    )
    synthetic_path.write_text(
        json.dumps(vector_tampered, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    with pytest.raises(selection.SelectionError, match="sequence/vector replay"):
        selection.load_and_validate_synthetic_artifact(
            synthetic_path,
            expected_file_sha256=selection.file_sha256(synthetic_path),
            expected_g32_binary_sha256=g32_sha,
            auditor=FakeAuditor,
        )


def test_stage1_observation_pair_association_rejects_cross_case_rebinding() -> None:
    observation = {
        "case_id": "case-a",
        "observation_ordinal": 1,
        "opportunity_id": 7,
        "event_time": 1.0,
        "external_slot_start_seconds": 2.0,
        "external_slot_end_seconds": 3.0,
        "external_service_seconds": 1.0,
        "local_service_seconds": 1.0,
        "L0": 2.0,
        "X_insert": 1.0,
        "H_gap": 1.0,
    }
    external = {
        "actual_L_service_start": 2.0,
        "actual_L_service_complete": 3.0,
        "actual_subsequent_source_wait": 0.0,
        "actual_subsequent_junction_wait": 0.0,
        "actual_transit_seconds": 0.0,
        "actual_subsequent_calendar_wait": 0.0,
        "actual_subsequent_wait": 0.0,
    }
    local = {
        "actual_L_service_start": 4.0,
        "actual_L_service_complete": 5.0,
        "actual_subsequent_source_wait": 3.0,
        "actual_subsequent_junction_wait": 0.0,
        "actual_transit_seconds": 0.0,
        "actual_subsequent_calendar_wait": 0.0,
        "actual_subsequent_wait": 3.0,
    }
    pair = {
        **observation,
        "primary": True,
        "status": "V3R2_OUTCOME_JOINED",
        "reason": "UNIQUE_V3R2_PAIR",
        "local": local,
        "external": external,
        "Y_realized": 2.0,
        "A_gap": 2.0,
        "X_insert": 1.0,
        "H_gap": 1.0,
        "case_status": "V3R2_OUTCOME_JOINED",
    }
    raw_pair = {key: pair[key] for key in selection.JOIN_PAIR_KEYS}
    cases = [
        {
            "case_id": "case-a",
            "admitted_row_count": 1,
            "rows_sha256": selection.canonical_sha256([observation]),
            "pairs_sha256": selection.canonical_sha256([raw_pair]),
        },
        {
            "case_id": "case-b",
            "admitted_row_count": 0,
            "rows_sha256": selection.canonical_sha256([]),
            "pairs_sha256": selection.canonical_sha256([]),
        },
    ]
    selection._validate_stage1_case_association(cases, [observation], [pair])

    rebound = deepcopy(pair)
    rebound["case_id"] = "case-b"
    with pytest.raises(selection.SelectionError, match="source observation"):
        selection._validate_stage1_case_association(
            cases, [observation], [rebound]
        )


def test_stage1_repeated_diagnostic_binds_only_non_join_source_fields() -> None:
    observation = {
        "cohort": "safety_regression",
        "replica": None,
        "case_id": "case-repeat",
        "observation_ordinal": 1,
        "opportunity_id": 7,
        "service_seconds": 1.0,
        "bag_count": 8,
        "flow_pattern": "simultaneous_local_first",
        "calendar_mutation_count": 0,
        "X_insert": 1.0,
        "H_gap": 0.25,
    }
    pair = {
        **observation,
        "primary": False,
        "status": "V3R2_REPEATED_BAG_DIAGNOSTIC",
        "reason": "EARLIER_PRIMARY_USED_BAG",
        "local": None,
        "external": None,
        "Y_realized": None,
        "A_gap": None,
        "X_insert": None,
        "H_gap": None,
        "case_status": "V3R2_OUTCOME_JOINED",
    }
    raw_pair = {key: pair[key] for key in selection.JOIN_PAIR_KEYS}
    cases = [
        {
            "case_id": observation["case_id"],
            "admitted_row_count": 1,
            "rows_sha256": selection.canonical_sha256([observation]),
            "pairs_sha256": selection.canonical_sha256([raw_pair]),
        }
    ]

    selection._validate_stage1_case_association(cases, [observation], [pair])

    for field in set(observation) - selection.JOIN_PAIR_KEYS:
        tampered = deepcopy(pair)
        tampered[field] = "tampered"
        with pytest.raises(selection.SelectionError, match="source observation"):
            selection._validate_stage1_case_association(
                cases, [observation], [tampered]
            )


def test_shadow_gate_requires_legacy_pair_callable_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "g32.pyd"
    binary.write_bytes(b"mock-g32-binary")
    binary_sha = selection.file_sha256(binary)
    control = {
        "artifact_content_sha256": "6" * 64,
        "control_revision_id": selection.CONTROL_REVISION_ID,
        "scales": {},
    }
    synthetic = {
        "decision": "synthetic-pass",
        "implementation_head": "a" * 40,
    }
    monkeypatch.setattr(
        selection,
        "load_and_validate_control_artifact",
        lambda *_args, **_kwargs: (control, "7" * 64),
    )
    monkeypatch.setattr(
        selection,
        "load_and_validate_synthetic_artifact",
        lambda *_args, **_kwargs: (synthetic, "8" * 64),
    )

    class AuditorWithoutLegacy:
        pass

    calls = 0

    def executor(**_request: Any) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return {}

    with pytest.raises(selection.SelectionError, match="legacy_wait_pair"):
        selection.run_g32_shadow_gate(
            tmp_path / "control.json",
            binary,
            executor,
            expected_control_file_sha256="7" * 64,
            synthetic_artifact=tmp_path / "synthetic.json",
            expected_synthetic_file_sha256="8" * 64,
            expected_g32_binary_sha256=binary_sha,
            auditor=AuditorWithoutLegacy,
            _test_only=True,
        )
    assert calls == 0


def test_shadow_no_event_cannot_mask_exception_or_another_hard_gate() -> None:
    passing_checks = {name: True for name in selection.SHADOW_CHECK_NAMES}
    no_event_checks = dict(passing_checks)
    no_event_checks["node49_upstream53_admitted"] = False
    no_event = {"pass": False, "checks": no_event_checks, "error": None}
    passed = {"pass": True, "checks": passing_checks, "error": None}

    assert (
        selection._shadow_campaign_status({"1x": no_event, "2x": passed})
        == selection.SHADOW_NO_EVENT
    )

    exception = {
        "pass": False,
        "checks": {},
        "error_type": "RuntimeError",
        "error": "boom",
    }
    assert (
        selection._shadow_campaign_status({"1x": no_event, "2x": exception})
        == selection.SHADOW_NO_GO
    )

    other_failure_checks = dict(no_event_checks)
    other_failure_checks["shadow_census"] = False
    other_failure = {
        "pass": False,
        "checks": other_failure_checks,
        "error": None,
    }
    assert (
        selection._shadow_campaign_status(
            {"1x": no_event, "2x": other_failure}
        )
        == selection.SHADOW_NO_GO
    )


def test_shadow_gate_adds_only_registered_mode_and_trace_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "g32-tail.pyd"
    binary.write_bytes(b"mock-g32-tail")
    binary_sha = selection.file_sha256(binary)
    scale = {
        "selection": {"selected_rows": []},
        "request": {},
        "control": {"payload": {}},
    }
    control = {
        "artifact_content_sha256": "6" * 64,
        "control_revision_id": selection.CONTROL_REVISION_ID,
        "scales": {"1x": deepcopy(scale), "2x": deepcopy(scale)},
    }
    synthetic = {
        "decision": "synthetic-pass",
        "implementation_head": "a" * 40,
    }
    monkeypatch.setattr(
        selection,
        "load_and_validate_control_artifact",
        lambda *_args, **_kwargs: (control, "7" * 64),
    )
    monkeypatch.setattr(
        selection,
        "load_and_validate_synthetic_artifact",
        lambda *_args, **_kwargs: (synthetic, "8" * 64),
    )

    class TailAuditor:
        @staticmethod
        def legacy_wait_pair(
            _off: Mapping[str, Any], _shadow: Mapping[str, Any]
        ) -> Mapping[str, Any]:
            return {"pass": True}

        @staticmethod
        def ordinary_request_sha256(request: Mapping[str, Any]) -> str:
            ignored = {
                "expected_binary_path",
                "search_path",
                "source_aware_destination_service_mode",
                "source_aware_destination_service_trace_limit",
            }
            return selection.canonical_sha256(
                {key: value for key, value in request.items() if key not in ignored}
            )

        @staticmethod
        def assert_request_projection(
            request: Mapping[str, Any],
            mode: str,
            storage: list[int],
            scenario: str,
        ) -> None:
            assert request["source_aware_destination_service_mode"] == mode
            assert request["source_aware_destination_service_trace_limit"] == 200_000
            assert storage == [53]
            assert scenario.endswith("_1x")

    captured: dict[str, Any] = {}

    def executor(**request: Any) -> Mapping[str, Any]:
        captured.update(request)
        raise RuntimeError("stop after request capture")

    result = selection.run_g32_shadow_gate(
        tmp_path / "control.json",
        binary,
        executor,
        expected_control_file_sha256="7" * 64,
        synthetic_artifact=tmp_path / "synthetic.json",
        expected_synthetic_file_sha256="8" * 64,
        expected_g32_binary_sha256=binary_sha,
        auditor=TailAuditor,
        _test_only=True,
    )

    assert captured["source_aware_destination_service_mode"] == "shadow"
    assert captured["source_aware_destination_service_trace_limit"] == 200_000
    assert result["control_revision_id"] == selection.CONTROL_REVISION_ID
    assert result["pass"] is False
    assert selection.verify_content_hash(result) == result["artifact_content_sha256"]


def test_shadow_gate_success_retains_full_payload_and_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "g32-success.pyd"
    binary.write_bytes(b"mock-g32-success")
    binary_sha = selection.file_sha256(binary)
    def shadow_scale(scale_number: int) -> dict[str, Any]:
        count = selection.EXPECTED_SELECTION_COUNTS[scale_number]["total"]
        rows = [
            {"segment_id": f"{scale_number}x-row-{index}", "row_ordinal": index}
            for index in range(count)
        ]
        return {
            "selection": {"selected_rows": rows},
            "request": {
                "bag_records": [
                    (row["segment_id"], row["row_ordinal"])
                    for row in rows
                ]
            },
            "control": {
                "payload": {"off": True},
                "ordinary_payload_hashes": {"ordinary": "same"},
            },
        }

    control = {
        "artifact_content_sha256": "6" * 64,
        "control_revision_id": selection.CONTROL_REVISION_ID,
        "scales": {"1x": shadow_scale(1), "2x": shadow_scale(2)},
    }
    synthetic = {
        "decision": "synthetic-pass",
        "implementation_head": "a" * 40,
    }
    monkeypatch.setattr(
        selection,
        "load_and_validate_control_artifact",
        lambda *_args, **_kwargs: (control, "7" * 64),
    )
    monkeypatch.setattr(
        selection,
        "load_and_validate_synthetic_artifact",
        lambda *_args, **_kwargs: (synthetic, "8" * 64),
    )

    class SuccessAuditor:
        JOINED = "JOINED"

        @staticmethod
        def legacy_wait_pair(
            _off: Mapping[str, Any], _shadow: Mapping[str, Any]
        ) -> Mapping[str, Any]:
            return {"pass": True}

        @staticmethod
        def ordinary_request_sha256(request: Mapping[str, Any]) -> str:
            ignored = {
                "expected_binary_path",
                "search_path",
                "source_aware_destination_service_mode",
                "source_aware_destination_service_trace_limit",
            }
            return selection.canonical_sha256(
                {key: value for key, value in request.items() if key not in ignored}
            )

        @staticmethod
        def assert_request_projection(*_args: Any, **_kwargs: Any) -> None:
            return None

        @staticmethod
        def _loaded_binary(payload: Mapping[str, Any]) -> tuple[str, str]:
            return str(payload["loaded_cpp_binary_path"]), str(
                payload["loaded_cpp_binary_sha256"]
            )

        @staticmethod
        def extract_rows(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return [{"node": 49, "external_upstream_node": 53}]

        @staticmethod
        def build_service_episodes(*_args: Any, **_kwargs: Any) -> list[Any]:
            return []

        @staticmethod
        def join_v3r2_outcomes(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
            return {"status": "JOINED"}

        @staticmethod
        def _shadow_census(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
            return {"pass": True}

        @staticmethod
        def _service_audit(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
            return {"pass": True}

        @staticmethod
        def _resource_values(*_args: Any, **_kwargs: Any) -> Mapping[str, float]:
            return {"events_per_completed": 1.0}

        @staticmethod
        def evaluate_resources(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
            return {"pass": True}

        @staticmethod
        def ordinary_payload_hashes(
            _payload: Mapping[str, Any],
        ) -> Mapping[str, str]:
            return {"ordinary": "same"}

        @staticmethod
        def request_sha256(request: Mapping[str, Any]) -> str:
            return selection.canonical_sha256(request)

    calls = 0

    def executor(**request: Any) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "loaded_cpp_binary_path": str(request["expected_binary_path"]),
            "loaded_cpp_binary_sha256": binary_sha,
            "summary": {},
            "scale_call": calls,
        }

    result = selection.run_g32_shadow_gate(
        tmp_path / "control.json",
        binary,
        executor,
        expected_control_file_sha256="7" * 64,
        synthetic_artifact=tmp_path / "synthetic.json",
        expected_synthetic_file_sha256="8" * 64,
        expected_g32_binary_sha256=binary_sha,
        auditor=SuccessAuditor,
        _test_only=True,
    )

    assert result["pass"] is True
    assert (
        result["status"]
        == selection.SHADOW_PASS
        == "PASS_V3R11_NANNING_P0_G32_SHADOW"
    )
    assert result["schema"] == "czr005.g4irsf32.nanning_p0_shadow_gate.v3r11"
    assert (
        result["campaign_revision_id"]
        == "G4IRSF32_V3R11_P0_CAMPAIGN_20260829"
    )
    assert result["control_revision_id"] == selection.CONTROL_REVISION_ID
    assert calls == 2
    for name in ("1x", "2x"):
        scale_result = result["scales"][name]
        assert scale_result["scale"] == int(name[0])
        expected_rows = control["scales"][name]["selection"]["selected_rows"]
        expected_count = selection.EXPECTED_SELECTION_COUNTS[int(name[0])]["total"]
        assert scale_result["selected_row_count"] == expected_count
        assert scale_result["selected_rows_sha256"] == selection.canonical_sha256(
            expected_rows
        )
        assert scale_result["shadow_payload"]["loaded_cpp_binary_sha256"] == binary_sha
        assert scale_result["shadow_payload_sha256"] == selection.canonical_sha256(
            scale_result["shadow_payload"]
        )
    assert selection.verify_content_hash(result) == result["artifact_content_sha256"]

    replay = selection._deep_validate_g32_shadow_result_mapping(
        result,
        control=control,
        control_file_sha256="7" * 64,
        synthetic=synthetic,
        synthetic_file_sha256="8" * 64,
        g32_binary=binary,
        expected_g32_binary_sha256=binary_sha,
        expected_implementation_head="a" * 40,
        auditor=SuccessAuditor,
    )
    assert replay["pass"] is True

    shallow_scales = deepcopy(result)
    shallow_scales.pop("artifact_content_sha256")
    shallow_scales["scales"] = {
        "1x": {"pass": True},
        "2x": {"pass": True},
    }
    shallow_scales = selection.with_content_hash(shallow_scales)
    with pytest.raises(
        selection.SelectionError,
        match=r"shadow\.scales\.1x\.shadow_payload must be an object",
    ):
        selection._deep_validate_g32_shadow_result_mapping(
            shallow_scales,
            control=control,
            control_file_sha256="7" * 64,
            synthetic=synthetic,
            synthetic_file_sha256="8" * 64,
            g32_binary=binary,
            expected_g32_binary_sha256=binary_sha,
            expected_implementation_head="a" * 40,
            auditor=SuccessAuditor,
        )

    coordinated_tamper = deepcopy(result)
    coordinated_tamper.pop("artifact_content_sha256")
    observations = coordinated_tamper["scales"]["1x"]["observations"]
    observations[0]["forged_self_consistent_field"] = True
    coordinated_tamper["scales"]["1x"]["observations_sha256"] = (
        selection.canonical_sha256(observations)
    )
    admitted = [
        row
        for row in observations
        if row.get("node") == selection.LOCAL_START
        and row.get("external_upstream_node") == selection.EXTERNAL_START
    ]
    coordinated_tamper["scales"]["1x"][
        "admitted_node49_upstream53_sha256"
    ] = selection.canonical_sha256(admitted)
    coordinated_tamper = selection.with_content_hash(coordinated_tamper)
    assert (
        selection.verify_content_hash(coordinated_tamper)
        == coordinated_tamper["artifact_content_sha256"]
    )
    with pytest.raises(selection.SelectionError, match="differs on deep replay"):
        selection._deep_validate_g32_shadow_result_mapping(
            coordinated_tamper,
            control=control,
            control_file_sha256="7" * 64,
            synthetic=synthetic,
            synthetic_file_sha256="8" * 64,
            g32_binary=binary,
            expected_g32_binary_sha256=binary_sha,
            expected_implementation_head="a" * 40,
            auditor=SuccessAuditor,
        )

    wrong_loaded_binary = tmp_path / "different-loaded.pyd"
    wrong_loaded_binary.write_bytes(b"different-file-but-forged-sha-field")

    def wrong_path_executor(**_request: Any) -> Mapping[str, Any]:
        return {
            "loaded_cpp_binary_path": str(wrong_loaded_binary),
            "loaded_cpp_binary_sha256": binary_sha,
            "summary": {},
        }

    wrong_path_result = selection.run_g32_shadow_gate(
        tmp_path / "control.json",
        binary,
        wrong_path_executor,
        expected_control_file_sha256="7" * 64,
        synthetic_artifact=tmp_path / "synthetic.json",
        expected_synthetic_file_sha256="8" * 64,
        expected_g32_binary_sha256=binary_sha,
        auditor=SuccessAuditor,
        _test_only=True,
    )
    assert wrong_path_result["status"] == selection.SHADOW_NO_GO
    assert all(
        scale["checks"]["loaded_g32_binary"] is False
        for scale in wrong_path_result["scales"].values()
    )


def test_content_hash_detects_mutation() -> None:
    artifact = selection.with_content_hash({"schema": "fixture", "rows": [1]})
    corrupted = deepcopy(artifact)
    corrupted["rows"].append(2)

    with pytest.raises(selection.SelectionError, match="mismatch"):
        selection.verify_content_hash(corrupted)


def test_read_strict_json_rejects_nonfinite_constant(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"value":NaN}', encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite"):
        selection.read_strict_json(path)


def test_read_strict_json_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"outer":{"same":1,"same":2}}', encoding="utf-8")

    with pytest.raises(selection.SelectionError, match="duplicate"):
        selection.read_strict_json(path)

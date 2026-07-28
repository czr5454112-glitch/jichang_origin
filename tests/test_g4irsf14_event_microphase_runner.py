from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from typing import Any

import pytest

from scripts.eval import g4irsf14_event_microphase as phase


def _bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _selection(tier: str = "motif") -> phase.g13.WorkloadSelection:
    rows = (
        {
            "segment_id": "0:direct",
            "task_id": 0,
            "pass_time": 10.0,
            "original_entry_time": 9.0,
            "std": 100.0,
            "start": 3,
            "goal": 50,
            "source": "source_3",
            "input_row_index": 0,
            "input_physical_line": 1,
        },
    )
    return phase.g13.WorkloadSelection(
        selection_id=f"test_{tier}",
        tier=tier,
        rows=rows,
        selected_rows_sha256=phase.canonical_sha256(rows),
        selected_segment_ids_sha256=phase.canonical_sha256(["0:direct"]),
        raw_bag_count=1,
        provenance={"test_only": True},
    )


def _source_row() -> dict[str, Any]:
    return {
        "event_time": 10.0,
        "timestamp_bits": _bits(10.0),
        "source_node": 3,
        "queue_length_before_enqueue": 0,
        "queue_length_after_enqueue": 1,
        "queue_length_before_arbitration": 1,
        "queue_length_after_arbitration": 0,
        "same_timestamp_release_batch_size": 1,
        "same_time_pending_source_releases": 1,
        "same_time_pending_shared_merge_releases": 1,
        "ready_set_size": 1,
        "priority_comparison_count": 0,
        "chosen_task_id": 0,
        "chosen_runtime_bag_id": 0,
        "chosen_segment_id": "0:direct",
        "queue_discipline": "aging",
        "event_seq": 1,
        "arbitration_generation": 1,
        "batched_arbitration": True,
    }


def _junction_row() -> dict[str, Any]:
    return {
        "event_time": 10.0,
        "timestamp_bits": _bits(10.0),
        "junction_node": 52,
        "queue_length_before_enqueue": 0,
        "queue_length_after_enqueue": 2,
        "queue_length_before_arbitration": 2,
        "queue_length_after_arbitration": 1,
        "same_timestamp_arrival_batch_size": 2,
        "same_time_pending_arrivals": 0,
        "same_time_pending_shared_merge_requests": 1,
        "ready_set_size": 2,
        "priority_comparison_count": 1,
        "pibt_slice_bag_count": 2,
        "pibt_owner_count": 1,
        "chosen_task_id": 0,
        "chosen_runtime_bag_id": 0,
        "chosen_segment_id": "0:direct",
        "event_seq": 2,
        "arbitration_generation": 1,
        "batched_arbitration": True,
    }


def _merge_row() -> dict[str, Any]:
    return {
        "event_time": 10.0,
        "timestamp_bits": _bits(10.0),
        "destination_node": 52,
        "upstream_node": 3,
        "incoming_edge_start": 3,
        "incoming_edge_end": 52,
        "requesting_task_id": 0,
        "requesting_runtime_bag_id": 0,
        "requesting_segment_id": "0:direct",
        "earliest_arrival": 11.0,
        "slot_start": 11.0,
        "slot_end": 12.0,
        "known_competing_request_count": 0,
        "later_same_time_competitor_count": 1,
        "later_same_time_competitor_exists": True,
        "seq_determined_order": True,
        "event_seq": 3,
    }


def _seq_row() -> dict[str, Any]:
    return {
        "event_time": 10.0,
        "timestamp_bits": _bits(10.0),
        "boundary": "destination_reservation",
        "node": 3,
        "destination_node": 52,
        "ready_set_size": 1,
        "priority_comparison_count": 0,
        "later_same_time_competitor_count": 1,
        "chosen_runtime_bag_id": 0,
        "chosen_enqueue_sequence": 1,
        "event_seq": 3,
        "seq_determined_order": True,
        "reason": "later_same_time_request_unseen_at_reservation",
    }


def _batch_row() -> dict[str, Any]:
    return {
        "event_time": 10.0,
        "timestamp_bits": _bits(10.0),
        "boundary": "junction",
        "node": 52,
        "enqueue_count": 2,
        "ready_set_size": 2,
        "pending_same_time_event_count": 0,
        "chosen_runtime_bag_id": 0,
        "event_seq": 2,
        "arbitration_generation": 1,
    }


def _payload(binary: Path, mode: str) -> dict[str, Any]:
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    source_seq = {
        **_seq_row(),
        "boundary": "source_admission",
        "node": 3,
        "destination_node": -1,
        "later_same_time_competitor_count": 0,
        "event_seq": 1,
        "seq_determined_order": False,
        "reason": "batched_source_ready_set_visible",
    }
    junction_seq = {
        **_seq_row(),
        "boundary": "junction_dispatch",
        "node": 52,
        "destination_node": -1,
        "later_same_time_competitor_count": 0,
        "event_seq": 2,
        "seq_determined_order": False,
        "reason": "batched_junction_ready_set_visible",
    }
    source_batch = {
        **_batch_row(),
        "boundary": "source",
        "node": 3,
        "enqueue_count": 1,
        "ready_set_size": 1,
        "event_seq": 1,
    }
    arrays = {
        "source_admission_opportunities": [_source_row()],
        "junction_arbitration_opportunities": [_junction_row()],
        "merge_request_visibility": [_merge_row()],
        "event_seq_ordering_audit": [
            source_seq,
            junction_seq,
            _seq_row(),
        ],
        "arbitration_batch_cardinality": [
            source_batch,
            _batch_row(),
        ],
    }
    summary: dict[str, Any] = {
        "loaded_cpp_binary_path": str(binary.resolve()),
        "loaded_cpp_binary_sha256": binary_hash,
        "event_semantics": mode,
        "event_semantics_echo": mode,
        "opportunity_telemetry_enabled": True,
        "resource_semantics_echo": phase.FROZEN_CONTROL["resource_semantics"],
        "scorer_mode_echo": phase.FROZEN_CONTROL["scorer_mode"],
        "pibt_mode_echo": phase.FROZEN_CONTROL["pibt_mode"],
        "priority_mode_echo": phase.FROZEN_CONTROL["priority_mode"],
        "framework_mode_echo": phase.FROZEN_CONTROL["framework_mode"],
        "admission_mode_echo": phase.FROZEN_CONTROL["admission_mode"],
        "pressure_mode_echo": phase.FROZEN_CONTROL["pressure_mode"],
        "pibt_preference_mode_echo": phase.FROZEN_CONTROL[
            "pibt_preference_mode"
        ],
        "failed_count": 0,
        "conflict_count": 0,
        "unsafe_entry_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "full_future_routes_stored": 0,
        "unresolved_deadlock_count": 0,
        "priority_teacher_input_count": 0,
        "priority_future_route_input_count": 0,
        "priority_global_scan_count": 0,
        "decision_count": 1,
        "opportunity_event_queue_inspection_count": 3,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "reservation_depth": 1,
        "max_edges_selected_per_arrive": 1,
        "stale_arbitration_event_count": 0,
        "superseded_arbitration_event_rejected_count": 1,
        "microphase_runtime_global_scan_count": 0,
        "artificial_batch_delay_seconds": 0.0,
        "source_same_timestamp_batch_count": 1,
        "junction_same_timestamp_batch_count": 1,
        "max_source_arbitration_batch_size": 1,
        "max_junction_arbitration_batch_size": 2,
    }
    for array_name, counter_names in phase.TELEMETRY_COUNTERS.items():
        total, stored, dropped = counter_names
        summary[total] = len(arrays[array_name])
        summary[stored] = len(arrays[array_name])
        summary[dropped] = 0
    return {
        "summary": summary,
        "bags": [
            {
                "segment_id": "0:direct",
                "task_id": 0,
                "runtime_bag_id": 0,
                "completed": True,
                "release_time": 10.0,
                "admitted_time": 10.0,
                "finish_time": 20.0,
            }
        ],
        "events": [],
        "decisions": [],
        "decision_trace": [],
        "hold_attempts": [],
        "pibt_events": [],
        "credit_events": [],
        "fault_events": [],
        "trace_context": {
            "event_semantics": mode,
            "event_semantics_echo": mode,
            "opportunity_telemetry_enabled": True,
            "event_timestamp_grouping": (
                "exact_double_bits_or_numeric_epsilon_1e-9"
            ),
            "local_arbitration_key": (
                "node,timestamp_bits,wakeup_generation"
            ),
            "stale_arbitration_event_semantics": (
                "valid_generation_arbitration_executed_against_stale_"
                "runtime_state"
            ),
            "superseded_arbitration_event_rejected_semantics": (
                "generation_or_pending_mismatch_rejected_before_"
                "arbitration_execution"
            ),
            "event_queue_inspection_scope": (
                "passive_opportunity_audit_only_not_runtime_feature_or_"
                "reservation_scan"
            ),
            "destination_competitor_visibility_semantics": (
                "outgoing_edge_potential_competitor_upper_bound_not_"
                "selected_route_or_grant"
            ),
            "priority_comparison_semantics": (
                phase.PRIORITY_COMPARISON_SEMANTICS
            ),
            "opportunity_trace_limit": 100,
            "artificial_batch_delay_seconds": 0.0,
            "destination_merge_grant_enabled": False,
            "arbitration_worklist_scope": (
                "event_triggered_active_nodes_only_no_all_node_scan"
            ),
        },
        **arrays,
    }


def _oracle_projection(
    *,
    role: str,
    tier: str,
    binary: Path,
    projection_seed: str = "same",
) -> dict[str, Any]:
    digest = hashlib.sha256(projection_seed.encode("utf-8")).hexdigest()
    trace_lengths = {
        name: (1 if name in {"decisions", "decision_trace"} else 0)
        for name in phase.E0_ORACLE_TRACE_ARRAYS
    }
    selection = _selection(tier)
    return {
        "schema": phase.E0_ORACLE_SCHEMA,
        "role": role,
        "tier": tier,
        "selection": {
            "selection_id": selection.selection_id,
            "segment_count": selection.segment_count,
            "raw_bag_count": selection.raw_bag_count,
            "selected_rows_sha256": selection.selected_rows_sha256,
            "selected_segment_ids_sha256": (
                selection.selected_segment_ids_sha256
            ),
        },
        "binary": {
            "path": binary.resolve().as_posix(),
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        },
        "controls_sha256": phase.canonical_sha256(
            phase._e0_oracle_controls()
        ),
        "excluded_summary_fields": sorted(
            phase.E0_ORACLE_EXCLUDED_SUMMARY_FIELDS
        ),
        "extension_fields_absent": True,
        "bags_count": 1,
        "junction_state_count": 54,
        "trace_lengths": trace_lengths,
        **{
            field: digest
            for field in phase.E0_ORACLE_PROJECTION_HASH_FIELDS
        },
    }


def _oracle_audit_rows(tmp_path: Path) -> list[dict[str, Any]]:
    frozen_binary = tmp_path / "frozen.pyd"
    new_binary = tmp_path / "new.pyd"
    frozen_binary.write_bytes(b"frozen")
    new_binary.write_bytes(b"new")
    rows: list[dict[str, Any]] = []
    for tier in phase.E0_ORACLE_TIERS:
        frozen = _oracle_projection(
            role="frozen", tier=tier, binary=frozen_binary
        )
        new = _oracle_projection(role="new", tier=tier, binary=new_binary)
        rows.append(phase._compare_e0_oracle_pair(frozen, new, tier=tier))
    return rows


def _git(
    root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )


def _source_history_repo(
    tmp_path: Path,
    *,
    crlf_worktree: bool = False,
) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "source-history-repo"
    root.mkdir()
    (root / ".gitattributes").write_text(
        "* text eol=crlf\n", encoding="utf-8", newline="\n"
    )
    for index, relative in enumerate(phase.SOURCE_BUNDLE_PATHS):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"source-{index}\nsecond-line\n",
            encoding="utf-8",
            newline="\n",
        )
    _git(root, "init")
    _git(root, "config", "user.email", "oracle-test@example.invalid")
    _git(root, "config", "user.name", "Oracle Test")
    _git(root, "config", "core.autocrlf", "true")
    _git(root, "add", "--", ".")
    _git(root, "commit", "-m", "source history fixture")
    if crlf_worktree:
        path = root / phase.SOURCE_BUNDLE_PATHS[0]
        text = path.read_text(encoding="utf-8")
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    return root, phase.execution_source_history_identity(root)


def _phase_a_binary_identity(
    frozen_binary: Path,
) -> dict[str, Any]:
    digest = hashlib.sha256(frozen_binary.read_bytes()).hexdigest()
    return {
        "frozen_binary": {
            "path": "build_frozen/python/czr005_cpp.test.pyd",
            "file_sha256": digest,
            "expected_file_sha256": digest,
        }
    }


def _valid_oracle_certificate(
    tmp_path: Path,
    source_history: dict[str, Any],
) -> tuple[dict[str, Any], Path, Path, dict[str, Any]]:
    frozen_binary = tmp_path / "frozen-czr005_cpp.pyd"
    new_binary = tmp_path / "new-czr005_cpp.pyd"
    frozen_binary.write_bytes(b"frozen")
    new_binary.write_bytes(b"new")
    phase_a_identity = _phase_a_binary_identity(frozen_binary)
    comparisons = _oracle_audit_rows(tmp_path)
    frozen_digest = hashlib.sha256(frozen_binary.read_bytes()).hexdigest()
    certificate: dict[str, Any] = {
        "schema": phase.E0_ORACLE_CERTIFICATE_SCHEMA,
        "status": "PASS_EXACT_EXTERNAL_ORACLE",
        "process_isolation": "one_named_pyd_per_child_process",
        "tiers": list(phase.E0_ORACLE_TIERS),
        "controls": phase._e0_oracle_controls(),
        "controls_sha256": phase.canonical_sha256(
            phase._e0_oracle_controls()
        ),
        "frozen_binary": {
            "artifact_path": phase_a_identity["frozen_binary"]["path"],
            "artifact_sha256": frozen_digest,
            "physical_path": frozen_binary.resolve().as_posix(),
            "physical_sha256": frozen_digest,
        },
        "new_binary": {
            "path": new_binary.resolve().as_posix(),
            "sha256": hashlib.sha256(new_binary.read_bytes()).hexdigest(),
        },
        "execution_git_commit_sha": source_history["git_commit_sha"],
        "working_source_bundle": source_history["working_source_bundle"],
        "git_source_bundle": source_history["git_source_bundle"],
        "source_history_clean_gate": source_history["clean_gate"],
        "excluded_summary_fields": sorted(
            phase.E0_ORACLE_EXCLUDED_SUMMARY_FIELDS
        ),
        "extension_fields_required_absent": True,
        "comparisons": comparisons,
    }
    certificate["certificate_sha256"] = phase.canonical_sha256(certificate)
    return certificate, frozen_binary, new_binary, phase_a_identity


def _resign_certificate(certificate: dict[str, Any]) -> None:
    certificate.pop("certificate_sha256", None)
    certificate["certificate_sha256"] = phase.canonical_sha256(certificate)


def _validate_certificate_fixture(
    certificate: dict[str, Any],
    *,
    root: Path,
    new_binary: Path,
    phase_a_identity: dict[str, Any],
    expected_working_sha256: str | None = None,
) -> dict[str, Any]:
    return phase._validate_e0_oracle_certificate(
        certificate,
        phase_a_identity=phase_a_identity,
        root=root,
        expected_new_binary_path=new_binary.resolve().as_posix(),
        expected_new_binary_sha256=hashlib.sha256(
            new_binary.read_bytes()
        ).hexdigest(),
        expected_working_source_bundle_sha256=(
            expected_working_sha256
            if expected_working_sha256 is not None
            else certificate["working_source_bundle"]["bundle_sha256"]
        ),
        expected_projection_audit=certificate["comparisons"],
    )


def _validate(tmp_path: Path, mode: str = phase.MODE_ORDER[3]) -> dict[str, Any]:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"instrumented-binary")
    payload = _payload(binary, mode)
    case = phase.RuntimeCase(mode, "motif", _selection())
    controls = phase.runtime_controls(mode, opportunity_trace_limit=100)
    return phase.validate_runtime_payload(
        payload,
        case,
        controls,
        expected_binary={
            "path": binary.resolve().as_posix(),
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        },
    )


def test_mock_payload_passes_all_hard_and_telemetry_gates(
    tmp_path: Path,
) -> None:
    validation = _validate(tmp_path)
    assert validation["gate_status"] == "PASS"
    assert validation["blockers"] == []
    assert validation["timing"]["comparison_eligible"] is True
    metrics = validation["telemetry_metrics"]
    assert metrics["q0_actual_priority_comparator_opportunity_count"] == 1
    assert metrics["pibt_feasible_slice_proxy_count"] == 1
    assert (
        metrics[
            "event_seq_determined_local_reservation_order_proxy_count"
        ]
        == 1
    )
    assert metrics["batched_multi_enqueue_count"] == 1


def test_priority_comparison_semantics_is_exact_hard_gate(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"instrumented-binary")
    payload = _payload(binary, phase.MODE_ORDER[3])
    payload["trace_context"]["priority_comparison_semantics"] = (
        "ready_set_size_minus_one_proxy"
    )
    case = phase.RuntimeCase(phase.MODE_ORDER[3], "motif", _selection())
    result = phase.validate_runtime_payload(
        payload,
        case,
        phase.runtime_controls(
            phase.MODE_ORDER[3], opportunity_trace_limit=100
        ),
        expected_binary={
            "path": binary.resolve().as_posix(),
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        },
    )
    assert result["gate_status"] == "FAIL"
    assert (
        "TRACE_CONTEXT_MISMATCH:priority_comparison_semantics"
        in result["blockers"]
    )


def test_dropped_telemetry_fails_closed(tmp_path: Path) -> None:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"instrumented-binary")
    payload = _payload(binary, phase.MODE_ORDER[3])
    summary = payload["summary"]
    summary["source_opportunity_total_count"] = 2
    summary["source_opportunity_dropped_count"] = 1
    case = phase.RuntimeCase(phase.MODE_ORDER[3], "motif", _selection())
    result = phase.validate_runtime_payload(
        payload,
        case,
        phase.runtime_controls(
            phase.MODE_ORDER[3], opportunity_trace_limit=1
        ),
        expected_binary={
            "path": binary.resolve().as_posix(),
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        },
    )
    assert result["gate_status"] == "FAIL"
    assert any(
        blocker.startswith("TELEMETRY_TRUNCATED")
        for blocker in result["blockers"]
    )


def test_timestamp_bit_mismatch_is_rejected(tmp_path: Path) -> None:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"instrumented-binary")
    payload = _payload(binary, phase.MODE_ORDER[1])
    payload["source_admission_opportunities"][0]["timestamp_bits"] += 1
    case = phase.RuntimeCase(phase.MODE_ORDER[1], "motif", _selection())
    with pytest.raises(phase.MicrophaseError, match="timestamp bits mismatch"):
        phase.validate_runtime_payload(
            payload,
            case,
            phase.runtime_controls(
                phase.MODE_ORDER[1], opportunity_trace_limit=100
            ),
            expected_binary={
                "path": binary.resolve().as_posix(),
                "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            },
        )


def test_telemetry_conservation_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"instrumented-binary")
    payload = _payload(binary, phase.MODE_ORDER[3])
    payload["summary"]["decision_count"] = 2
    case = phase.RuntimeCase(phase.MODE_ORDER[3], "motif", _selection())
    result = phase.validate_runtime_payload(
        payload,
        case,
        phase.runtime_controls(
            phase.MODE_ORDER[3], opportunity_trace_limit=100
        ),
        expected_binary={
            "path": binary.resolve().as_posix(),
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        },
    )
    assert result["gate_status"] == "FAIL"
    assert any(
        blocker.startswith("TELEMETRY_CONSERVATION_MERGE_DECISION")
        for blocker in result["blockers"]
    )


def test_runtime_request_requires_new_append_only_capabilities(
    tmp_path: Path,
) -> None:
    def old_executor(*, node_records: object) -> dict[str, Any]:
        return {"node_records": node_records}

    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"x")
    case = phase.RuntimeCase(phase.MODE_ORDER[0], "motif", _selection())
    with pytest.raises(phase.MicrophaseError, match="MISSING_RUNTIME_CAPABILITY"):
        phase.bind_runtime_request(
            old_executor,
            case,
            phase.runtime_controls(
                phase.MODE_ORDER[0], opportunity_trace_limit=100
            ),
            binary=binary,
            search_path=tmp_path,
            root=phase.ROOT,
        )


def test_full_requires_explicit_authorization() -> None:
    with pytest.raises(phase.MicrophaseError, match="--allow-full"):
        phase.execute_ladder(
            executor=lambda **_kwargs: {},
            binary=Path("does-not-matter"),
            search_path=Path("."),
            max_tier="full",
            allow_full=False,
            opportunity_trace_limit=100,
        )


def test_baseline_comparison_requires_real_mechanism_change() -> None:
    base = {
        "schema": phase.RESULT_SCHEMA,
        "mode": phase.MODE_ORDER[0],
        "tier": "8192",
        "gate_status": "PASS",
        "promotion_status": "DIAGNOSTIC_ONLY",
        "timing": {
            "original_entry_mean_minutes": 10.0,
            "original_entry_p95_seconds": 100.0,
            "original_entry_p99_seconds": 120.0,
        },
        "telemetry_metrics": {
            "q0_actual_priority_comparator_opportunity_count": 5,
            "merge_known_competitor_count": 2,
            "event_seq_determined_local_reservation_order_proxy_count": 4,
            "pibt_feasible_slice_proxy_count": 1,
        },
    }
    candidate = json.loads(json.dumps(base))
    candidate["mode"] = phase.MODE_ORDER[3]
    candidate["telemetry_metrics"][
        "q0_actual_priority_comparator_opportunity_count"
    ] = 6
    compared = phase.apply_baseline_comparisons([base, candidate])
    measured = next(row for row in compared if row["mode"] == phase.MODE_ORDER[3])
    assert measured["mechanism_gate"] == "PASS"
    assert measured["promotion_status"] == "ELIGIBLE_FOR_NEXT_TIER"
    assert phase.select_best_batched(compared) == phase.MODE_ORDER[3]
    assert phase.apply_baseline_comparisons(compared) == compared


def test_atomic_gzip_json_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "one.json.gz"
    second = tmp_path / "two.json.gz"
    value = {"b": [2, 1], "a": {"x": True}}
    first_raw, first_file = phase.atomic_write_gzip_json(first, value)
    second_raw, second_file = phase.atomic_write_gzip_json(second, value)
    assert first_raw == second_raw == phase.canonical_sha256(value)
    assert first_file == second_file


def test_frozen_e0_oracle_projection_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    frozen_binary = tmp_path / "frozen.pyd"
    new_binary = tmp_path / "new.pyd"
    frozen_binary.write_bytes(b"frozen")
    new_binary.write_bytes(b"new")
    frozen = _oracle_projection(
        role="frozen", tier="motif", binary=frozen_binary
    )
    new = _oracle_projection(role="new", tier="motif", binary=new_binary)
    new["bags_sha256"] = "f" * 64
    with pytest.raises(
        phase.MicrophaseError,
        match=r"E0_FROZEN_ORACLE_MISMATCH:tier=motif:field=bags_sha256",
    ):
        phase._compare_e0_oracle_pair(frozen, new, tier="motif")


def test_frozen_e0_oracle_child_nonzero_is_hard_failure() -> None:
    completed = subprocess.CompletedProcess(
        args=["python", "oracle"],
        returncode=9,
        stdout="",
        stderr="native loader failed",
    )
    with pytest.raises(
        phase.MicrophaseError,
        match=r"E0_ORACLE_CHILD_FAILED:role=frozen:tier=144:exit=9",
    ):
        phase._decode_e0_oracle_child(
            completed, role="frozen", tier="144"
        )


def test_frozen_e0_oracle_child_invalid_json_is_hard_failure() -> None:
    completed = subprocess.CompletedProcess(
        args=["python", "oracle"],
        returncode=0,
        stdout="not-json",
        stderr="",
    )
    with pytest.raises(
        phase.MicrophaseError,
        match=r"E0_ORACLE_CHILD_INVALID_JSON:role=new:tier=motif",
    ):
        phase._decode_e0_oracle_child(
            completed, role="new", tier="motif"
        )


def test_new_e0_oracle_rejects_disabled_extension_field(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "new.pyd"
    binary.write_bytes(b"new")
    binary_identity = {
        "path": binary.resolve().as_posix(),
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }
    empty_traces = {name: [] for name in phase.E0_ORACLE_TRACE_ARRAYS}
    payload: dict[str, Any] = {
        "summary": {
            "loaded_cpp_binary_path": str(binary.resolve()),
            "loaded_cpp_binary_sha256": binary_identity["sha256"],
            "decision_trace_truncated": False,
            "event_trace_truncated": False,
            "trace_limit": -1,
            "event_trace_limit": -1,
            "trace_shard_count": 1,
            "trace_shard_index": 0,
            "decision_trace_stored_count": 0,
            "hold_trace_stored_count": 0,
            "event_semantics": phase.MODE_ORDER[0],
        },
        "bags": [],
        "junction_state": [],
        "trace_context": {},
        "loaded_cpp_binary_path": str(binary.resolve()),
        "loaded_cpp_binary_sha256": binary_identity["sha256"],
        **empty_traces,
    }
    with pytest.raises(
        phase.MicrophaseError,
        match="E0_ORACLE_DISABLED_EXTENSION_FIELD_PRESENT",
    ):
        phase._e0_oracle_projection(
            payload,
            role="new",
            tier="motif",
            selection=_selection(),
            expected_binary=binary_identity,
        )


def test_frozen_e0_oracle_projection_audit_is_structurally_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase, "load_selection", lambda tier, _root: _selection(tier)
    )
    rows = _oracle_audit_rows(tmp_path)
    encoded = phase.canonical_json_bytes(rows).decode("utf-8")
    assert (
        phase._validate_e0_oracle_projection_audit(
            encoded, root=tmp_path
        )
        == rows
    )
    rows[1]["projection_hashes"]["trace_payload_sha256"] = ""
    with pytest.raises(
        phase.MicrophaseError,
        match="invalid projection hash trace_payload_sha256",
    ):
        phase._validate_e0_oracle_projection_audit(
            phase.canonical_json_bytes(rows).decode("utf-8"),
            root=tmp_path,
        )
    extra_key_rows = _oracle_audit_rows(tmp_path)
    extra_key_rows[0]["projection_hashes"]["unlisted_sha256"] = "0" * 64
    with pytest.raises(
        phase.MicrophaseError,
        match="projection hash shape drift",
    ):
        phase._validate_e0_oracle_projection_audit(
            phase.canonical_json_bytes(extra_key_rows).decode("utf-8"),
            root=tmp_path,
        )


def test_external_oracle_spawns_exact_role_tier_matrix(
    tmp_path: Path,
) -> None:
    root, source_history = _source_history_repo(tmp_path)
    frozen_binary = tmp_path / "matrix-frozen.pyd"
    new_binary = tmp_path / "matrix-new.pyd"
    frozen_binary.write_bytes(b"frozen-matrix")
    new_binary.write_bytes(b"new-matrix")
    frozen_hash = hashlib.sha256(frozen_binary.read_bytes()).hexdigest()
    frozen_descriptor = {
        "artifact_path": "build_frozen/python/czr005_cpp.test.pyd",
        "artifact_sha256": frozen_hash,
        "physical_path": frozen_binary.resolve().as_posix(),
        "physical_sha256": frozen_hash,
    }
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def spy(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        calls.append((list(command), dict(kwargs)))
        role = command[command.index("--e0-oracle-role") + 1]
        tier = command[command.index("--e0-oracle-tier") + 1]
        binary = Path(command[command.index("--binary") + 1])
        projection = _oracle_projection(
            role=role, tier=tier, binary=binary
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(projection),
            stderr="",
        )

    certificate = phase.run_e0_frozen_oracle(
        new_binary=new_binary,
        frozen_binary=frozen_descriptor,
        source_history=source_history,
        root=root,
        run_child=spy,
    )
    assert certificate["status"] == "PASS_EXACT_EXTERNAL_ORACLE"
    assert len(calls) == 4
    expected = [
        ("frozen", "motif"),
        ("new", "motif"),
        ("frozen", "144"),
        ("new", "144"),
    ]
    for (command, kwargs), (role, tier) in zip(calls, expected):
        assert command[0] == phase.sys.executable
        assert command[1] == str(Path(phase.__file__).resolve())
        assert command.count("--e0-oracle-child") == 1
        assert command[command.index("--e0-oracle-role") + 1] == role
        assert command[command.index("--e0-oracle-tier") + 1] == tier
        expected_binary = frozen_binary if role == "frozen" else new_binary
        assert Path(command[command.index("--binary") + 1]).resolve() == (
            expected_binary.resolve()
        )
        assert Path(command[command.index("--output-root") + 1]) == root
        assert kwargs["cwd"] == str(root)
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False


def test_committed_oracle_replay_rejects_self_signed_fake_certificate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase, "load_selection", lambda tier, _root: _selection(tier)
    )
    root, source_history = _source_history_repo(tmp_path)
    certificate, frozen_binary, new_binary, phase_a_identity = (
        _valid_oracle_certificate(tmp_path, source_history)
    )
    assert (
        _validate_certificate_fixture(
            certificate,
            root=root,
            new_binary=new_binary,
            phase_a_identity=phase_a_identity,
        )
        == certificate
    )
    calls: list[tuple[str, str]] = []

    def spy(
        command: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        role = command[command.index("--e0-oracle-role") + 1]
        tier = command[command.index("--e0-oracle-tier") + 1]
        binary = Path(command[command.index("--binary") + 1])
        calls.append((role, tier))
        projection = _oracle_projection(
            role=role,
            tier=tier,
            binary=binary,
            projection_seed="actual-external-output",
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(projection),
            stderr="",
        )

    with pytest.raises(
        phase.MicrophaseError,
        match="COMMITTED_E0_ORACLE_EXTERNAL_REPLAY_MISMATCH",
    ):
        phase.rerun_committed_e0_frozen_oracle(
            certificate,
            root=root,
            new_binary_override=new_binary,
            frozen_binary_override=frozen_binary,
            run_child=spy,
        )
    assert calls == [
        ("frozen", "motif"),
        ("new", "motif"),
        ("frozen", "144"),
        ("new", "144"),
    ]


def test_committed_oracle_replay_rejects_binary_hash_drift(
    tmp_path: Path,
) -> None:
    root, source_history = _source_history_repo(tmp_path)
    certificate, frozen_binary, new_binary, _phase_a_identity_value = (
        _valid_oracle_certificate(tmp_path, source_history)
    )
    new_binary.write_bytes(b"new-but-drifted")
    with pytest.raises(
        phase.MicrophaseError,
        match="COMMITTED_E0_ORACLE_NEW_BINARY_SHA256_DRIFT",
    ):
        phase.rerun_committed_e0_frozen_oracle(
            certificate,
            root=root,
            new_binary_override=new_binary,
            frozen_binary_override=frozen_binary,
        )


def test_legacy_append_only_adapter_strips_exactly_three_arguments() -> None:
    captured: list[tuple[Any, ...]] = []

    def legacy(*args: Any) -> str:
        captured.append(args)
        return "ok"

    result = phase._call_frozen_e0_append_only_adapter(
        legacy,
        ("kept-a", "kept-b", phase.MODE_ORDER[0], False, 0),
    )
    assert result == "ok"
    assert captured == [("kept-a", "kept-b")]
    invalid_tails = (
        ("kept", phase.MODE_ORDER[1], False, 0),
        ("kept", phase.MODE_ORDER[0], True, 0),
        ("kept", phase.MODE_ORDER[0], False, 1),
        ("kept", phase.MODE_ORDER[0], False, False),
    )
    for arguments in invalid_tails:
        with pytest.raises(
            phase.MicrophaseError,
            match="LEGACY_APPEND_ONLY_ARGUMENT_CONTRACT_DRIFT",
        ):
            phase._call_frozen_e0_append_only_adapter(
                legacy, arguments
            )
    assert captured == [("kept-a", "kept-b")]


def test_resolve_frozen_binary_override_hash_mismatch(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected.pyd"
    override = tmp_path / "override.pyd"
    expected.write_bytes(b"expected")
    override.write_bytes(b"different")
    identity = _phase_a_binary_identity(expected)
    with pytest.raises(
        phase.MicrophaseError,
        match="STAGE_14A_FROZEN_BINARY_SHA256_MISMATCH",
    ):
        phase._resolve_frozen_binary(
            identity,
            root=tmp_path,
            override=override,
        )


def test_committed_certificate_rejects_self_hash_and_selection_forgery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase, "load_selection", lambda tier, _root: _selection(tier)
    )
    root, source_history = _source_history_repo(tmp_path)
    certificate, _frozen, new_binary, phase_a_identity = (
        _valid_oracle_certificate(tmp_path, source_history)
    )
    assert (
        _validate_certificate_fixture(
            certificate,
            root=root,
            new_binary=new_binary,
            phase_a_identity=phase_a_identity,
        )
        == certificate
    )

    bad_self_hash = json.loads(json.dumps(certificate))
    bad_self_hash["certificate_sha256"] = "0" * 64
    with pytest.raises(
        phase.MicrophaseError, match="certificate self-hash drift"
    ):
        _validate_certificate_fixture(
            bad_self_hash,
            root=root,
            new_binary=new_binary,
            phase_a_identity=phase_a_identity,
        )

    bad_selection = json.loads(json.dumps(certificate))
    bad_selection["comparisons"][0]["selection"]["selection_id"] = "forged"
    _resign_certificate(bad_selection)
    with pytest.raises(phase.MicrophaseError, match="selection drift"):
        _validate_certificate_fixture(
            bad_selection,
            root=root,
            new_binary=new_binary,
            phase_a_identity=phase_a_identity,
        )


def test_committed_certificate_rejects_commit_blob_and_source_bundle_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase, "load_selection", lambda tier, _root: _selection(tier)
    )
    root, source_history = _source_history_repo(tmp_path)
    certificate, _frozen, new_binary, phase_a_identity = (
        _valid_oracle_certificate(tmp_path, source_history)
    )
    original_working_sha = certificate["working_source_bundle"][
        "bundle_sha256"
    ]

    bad_commit = json.loads(json.dumps(certificate))
    bad_commit["execution_git_commit_sha"] = "0" * 40
    _resign_certificate(bad_commit)
    with pytest.raises(
        phase.MicrophaseError,
        match="RECORDED_EXECUTION_GIT_COMMIT_MISSING",
    ):
        _validate_certificate_fixture(
            bad_commit,
            root=root,
            new_binary=new_binary,
            phase_a_identity=phase_a_identity,
        )

    bad_blob = json.loads(json.dumps(certificate))
    bad_blob["git_source_bundle"]["files"][0]["blob_sha256"] = "f" * 64
    bad_blob["git_source_bundle"]["bundle_sha256"] = phase.canonical_sha256(
        bad_blob["git_source_bundle"]["files"]
    )
    _resign_certificate(bad_blob)
    with pytest.raises(
        phase.MicrophaseError, match="recorded Git source bundle drift"
    ):
        _validate_certificate_fixture(
            bad_blob,
            root=root,
            new_binary=new_binary,
            phase_a_identity=phase_a_identity,
        )

    bad_working = json.loads(json.dumps(certificate))
    bad_working["working_source_bundle"]["files"][0]["sha256"] = "e" * 64
    bad_working["working_source_bundle"]["bundle_sha256"] = (
        phase.canonical_sha256(
            bad_working["working_source_bundle"]["files"]
        )
    )
    _resign_certificate(bad_working)
    with pytest.raises(
        phase.MicrophaseError,
        match="working source bundle mismatch",
    ):
        _validate_certificate_fixture(
            bad_working,
            root=root,
            new_binary=new_binary,
            phase_a_identity=phase_a_identity,
            expected_working_sha256=original_working_sha,
        )


def test_source_history_clean_gate_allows_autocrlf_worktree_bytes(
    tmp_path: Path,
) -> None:
    _root, source_history = _source_history_repo(
        tmp_path, crlf_worktree=True
    )
    working = source_history["working_source_bundle"]["files"][0]
    git_blob = source_history["git_source_bundle"]["files"][0]
    assert working["path"] == git_blob["path"]
    assert working["sha256"] != git_blob["blob_sha256"]
    assert (
        source_history["clean_gate"][
            "tracked_tree_worktree_diff_quiet"
        ]
        is True
    )
    assert "normalization_aware" in source_history["clean_gate"][
        "normalization"
    ]


def test_source_history_rejects_unlisted_tracked_dependency_dirty(
    tmp_path: Path,
) -> None:
    root, _source_history = _source_history_repo(tmp_path)
    (root / ".gitattributes").write_text(
        "* text eol=crlf\n*.bin binary\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(
        phase.MicrophaseError,
        match="EXECUTION_TRACKED_TREE_WORKTREE_DIRTY",
    ):
        phase.execution_source_history_identity(root)


def test_committed_matrix_keeps_not_run_metrics_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selections = {
        tier: _selection(tier) for tier in phase.TIER_ORDER
    }
    monkeypatch.setattr(
        phase, "assert_phase_a_and_inputs", lambda _root, **_kwargs: {}
    )
    monkeypatch.setattr(
        phase, "load_selection", lambda tier, _root: selections[tier]
    )
    monkeypatch.setattr(
        phase,
        "_prior_q0_q1_equivalence",
        lambda _root: {
            "all_small_tiers_equivalent": True,
            "evidence": [],
        },
    )
    publication = phase.write_outputs([], best_batched=None, root=tmp_path)
    assert publication["status"] == "PROTOCOL_READY_NO_RUNTIME_ATTEMPTS"
    with (tmp_path / phase.OUTPUT_PATHS["ab"]).open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(phase.MODE_ORDER) * len(phase.TIER_ORDER)
    assert all(row["execution_status"] == "NOT_RUN" for row in rows)
    assert all(row["original_entry_mean_minutes"] == "" for row in rows)

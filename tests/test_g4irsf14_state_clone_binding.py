"""Production-binding checks for the Stage-E no-op clone mechanism.

The records below are a deliberately tiny NON_FORMAL_UNIT workload on the
protected canonical map2 topology.  These tests verify the exact-binary
checkpoint/rerun mechanism; they are not a 2,000-intervention campaign and
must never be cited as a formal Stage-E causal result.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_PATH,
    assert_canonical_map,
    canonical_graph_records,
)
from scripts.eval.g4irsf14_state_clone_validation import (
    REQUIRED_FIDELITY_HASHES,
    REQUIRED_STATE_COMPONENTS,
    canonical_state_component_sha256,
)


def _binary_path() -> Path:
    try:
        module = cpp_backend.load_cpp_module()
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))
    module_file = getattr(module, "__file__", None)
    assert module_file
    return Path(module_file).resolve()


def _non_formal_unit_bags(
    count: int = 1,
) -> list[tuple[str, int, float, float, int, int, str]]:
    return [
        (
            f"NON_FORMAL_UNIT_clone_{index}",
            91_000 + index,
            0.0,
            10_000.0,
            3,
            47,
            "NON_FORMAL_UNIT_ON_CANONICAL_MAP2",
        )
        for index in range(count)
    ]


def _run(
    *,
    event_ordinal: int = 0,
    bag_count: int = 1,
) -> dict[str, object]:
    binary_path = _binary_path()
    assert assert_canonical_map() == CANONICAL_MAP_PATH
    nodes, edges, heuristic = canonical_graph_records()
    return cpp_backend.g4irsf14_state_clone_noop_rerun_from_records(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=_non_formal_unit_bags(bag_count),
        preregistered_event_ordinal=event_ordinal,
        expected_binary_path=binary_path,
        search_path=binary_path.parent,
    )


def test_non_formal_unit_exact_binary_noop_rerun_is_raw_three_way_match() -> None:
    payload = _run()
    assert payload["schema"] == (
        "czr005.g4irsf14.exact_binary_noop_rerun.v1"
    )
    assert payload["evidence_scope"] == (
        "NOOP_FIDELITY_MECHANISM_ONLY_NOT_A_CAUSAL_LABEL"
    )
    assert payload["formal_pass_claimed"] is False
    assert payload["intervention_applied"] is False
    assert payload["native_three_way_exact_match"] is True
    assert payload["input_request_count"] == 1

    binary_path = Path(payload["loaded_cpp_binary_path"])
    assert binary_path == _binary_path()
    observed_binary_sha256 = hashlib.sha256(
        binary_path.read_bytes()
    ).hexdigest()
    assert payload["loaded_cpp_binary_sha256"] == (
        observed_binary_sha256
    )
    assert payload["binary"] == {
        "path": str(binary_path),
        "sha256": observed_binary_sha256,
    }

    state_components = payload["state_components"]
    assert set(state_components) == set(REQUIRED_STATE_COMPONENTS)
    assert state_components == payload[
        "baseline_start_state_components"
    ]
    assert state_components == payload["clone_start_state_components"]
    runtime_state_sha256 = canonical_state_component_sha256(
        state_components
    )
    assert runtime_state_sha256 == payload["runtime_state_sha256"]
    assert runtime_state_sha256 == payload[
        "baseline_start_state_sha256"
    ]
    assert runtime_state_sha256 == payload["clone_start_state_sha256"]

    boundary = payload["boundary"]
    assert boundary["kind"] == "queue_top_pre_pop"
    assert boundary["processed_event_count"] == 0
    assert boundary["queue_top_not_popped"] is True
    assert boundary["staged_event_sink_empty"] is True
    assert boundary["runtime_state_sha256"] == runtime_state_sha256

    source_hashes = payload["source_replay_hashes"]
    assert set(source_hashes) == set(REQUIRED_FIDELITY_HASHES)
    assert source_hashes == payload["baseline_replay_hashes"]
    assert source_hashes == payload["clone_replay_hashes"]

    source_invariants = payload["source_invariants"]
    assert source_invariants == payload["baseline_invariants"]
    assert source_invariants == payload["clone_invariants"]
    assert source_invariants["requested_count"] == 1
    assert source_invariants["completed_count"] == 1
    assert source_invariants["failed_segment_count"] == 0
    assert (
        source_invariants[
            "g4irsf14_i2_live_eligible_multi_request_boundary_count"
        ]
        == 0
    )
    assert (
        source_invariants[
            "g4irsf14_i5_prefilter_candidate_count"
        ]
        >= source_invariants[
            "g4irsf14_i5_applicable_ready_slice_boundary_count"
        ]
        >= 0
    )
    assert source_invariants["runtime_full_astar_call_count"] == 0
    assert source_invariants["runtime_global_scan_count"] == 0
    assert source_invariants["runtime_future_route_read_count"] == 0
    assert source_invariants["runtime_future_schedule_read_count"] == 0
    assert source_invariants["teacher_input_count"] == 0
    assert source_invariants["unsafe_entry_count"] == 0
    assert source_invariants["reservation_conflict_count"] == 0
    assert source_invariants["reservation_depth"] == 1
    assert source_invariants["two_step_reservation_count"] == 0
    assert source_invariants["event_limit_reached"] is False
    assert source_invariants["time_limit_reached"] is False
    assert source_invariants["merge_grant_stale_arbitration_count"] == 0
    assert source_invariants["merge_grant_lifecycle_complete"] is True
    assert source_invariants[
        "merge_grant_active_state_integrity_pass"
    ] is True
    assert source_invariants["merge_grant_protocol_integrity_pass"] is True


def test_non_formal_unit_rerun_reaches_noninitial_preregistered_boundary() -> None:
    payload = _run(event_ordinal=7, bag_count=2)
    boundary = payload["boundary"]
    assert boundary["processed_event_count"] == 7
    assert boundary["next_event_seq"] > 0
    assert boundary["runtime_state_sha256"] == payload[
        "runtime_state_sha256"
    ]
    assert payload["source_invariants"]["completed_count"] == 2


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_noop_rerun_rejects_non_integer_boundary_ordinal(
    value: object,
) -> None:
    nodes, edges, heuristic = canonical_graph_records()
    with pytest.raises(TypeError, match="must be an integer"):
        cpp_backend.g4irsf14_state_clone_noop_rerun_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=_non_formal_unit_bags(),
            preregistered_event_ordinal=value,  # type: ignore[arg-type]
        )


def test_noop_rerun_fails_closed_when_boundary_is_not_live() -> None:
    binary_path = _binary_path()
    nodes, edges, heuristic = canonical_graph_records()
    with pytest.raises(ValueError, match="live pre-pop boundary"):
        cpp_backend.g4irsf14_state_clone_noop_rerun_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=_non_formal_unit_bags(),
            preregistered_event_ordinal=1_000_000,
            search_path=binary_path.parent,
        )


def test_noop_rerun_binds_actual_loaded_binary_path() -> None:
    binary_path = _binary_path()
    nodes, edges, heuristic = canonical_graph_records()
    with pytest.raises(
        cpp_backend.CppBackendUnavailable,
        match="does not match expected_binary_path",
    ):
        cpp_backend.g4irsf14_state_clone_noop_rerun_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=_non_formal_unit_bags(),
            preregistered_event_ordinal=0,
            expected_binary_path=binary_path.with_name(
                "not-the-loaded-binary.pyd"
            ),
            search_path=binary_path.parent,
        )


def test_python_verifier_rejects_raw_hash_mismatch_even_if_native_bool_is_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = _run()
    tampered = deepcopy(valid)
    tampered["clone_replay_hashes"][
        "deterministic_result_sha256"
    ] = "0" * 64
    tampered["native_three_way_exact_match"] = True
    binary_path = _binary_path()
    fake_module = SimpleNamespace(
        __file__=str(binary_path),
        g4irsf14_state_clone_noop_rerun_from_records=(
            lambda *_args: tampered
        ),
    )
    monkeypatch.setattr(
        cpp_backend,
        "load_cpp_module",
        lambda _search_path=None: fake_module,
    )
    nodes, edges, heuristic = canonical_graph_records()
    with pytest.raises(
        RuntimeError,
        match="fidelity is below 100%",
    ):
        cpp_backend.g4irsf14_state_clone_noop_rerun_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=_non_formal_unit_bags(),
            preregistered_event_ordinal=0,
        )


@pytest.mark.parametrize(
    "field",
    ["unsafe_entry_count", "merge_grant_stale_arbitration_count"],
)
def test_python_verifier_rejects_three_way_zero_gate_tamper(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    valid = _run()
    tampered = deepcopy(valid)
    for branch in ("source", "baseline", "clone"):
        tampered[f"{branch}_invariants"][field] = 1
    # Keep all self-reported attestations positive.  Acceptance must still be
    # driven by the raw invariant fields above.
    tampered["native_three_way_exact_match"] = True
    binary_path = _binary_path()
    fake_module = SimpleNamespace(
        __file__=str(binary_path),
        g4irsf14_state_clone_noop_rerun_from_records=(
            lambda *_args: tampered
        ),
    )
    monkeypatch.setattr(
        cpp_backend,
        "load_cpp_module",
        lambda _search_path=None: fake_module,
    )
    nodes, edges, heuristic = canonical_graph_records()
    with pytest.raises(
        RuntimeError,
        match="zero-valued production hard gate",
    ):
        cpp_backend.g4irsf14_state_clone_noop_rerun_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=_non_formal_unit_bags(),
            preregistered_event_ordinal=0,
        )


def test_python_verifier_rejects_inconsistent_lifecycle_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = _run()
    tampered = deepcopy(valid)
    for branch in ("source", "baseline", "clone"):
        tampered[f"{branch}_invariants"][
            "merge_grant_lifecycle_dropped_count"
        ] = 1
    binary_path = _binary_path()
    fake_module = SimpleNamespace(
        __file__=str(binary_path),
        g4irsf14_state_clone_noop_rerun_from_records=(
            lambda *_args: tampered
        ),
    )
    monkeypatch.setattr(
        cpp_backend,
        "load_cpp_module",
        lambda _search_path=None: fake_module,
    )
    nodes, edges, heuristic = canonical_graph_records()
    with pytest.raises(
        RuntimeError,
        match="inconsistent merge protocol attestations",
    ):
        cpp_backend.g4irsf14_state_clone_noop_rerun_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=_non_formal_unit_bags(),
            preregistered_event_ordinal=0,
        )


def test_python_verifier_accepts_coherent_passive_lifecycle_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = _run()
    truncated = deepcopy(valid)
    for branch in ("source", "baseline", "clone"):
        invariants = truncated[f"{branch}_invariants"]
        invariants["merge_grant_lifecycle_dropped_count"] = 1
        invariants["merge_grant_lifecycle_complete"] = False
        invariants["merge_grant_protocol_integrity_pass"] = False
    binary_path = _binary_path()
    fake_module = SimpleNamespace(
        __file__=str(binary_path),
        g4irsf14_state_clone_noop_rerun_from_records=(
            lambda *_args: truncated
        ),
    )
    monkeypatch.setattr(
        cpp_backend,
        "load_cpp_module",
        lambda _search_path=None: fake_module,
    )
    nodes, edges, heuristic = canonical_graph_records()
    payload = cpp_backend.g4irsf14_state_clone_noop_rerun_from_records(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=_non_formal_unit_bags(),
        preregistered_event_ordinal=0,
    )
    assert payload["source_invariants"][
        "merge_grant_lifecycle_dropped_count"
    ] == 1
    assert payload["source_invariants"][
        "merge_grant_active_state_integrity_pass"
    ] is True

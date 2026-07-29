from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import struct

import pytest

from scripts.eval import g4irsf14_state_clone_validation as clone


ROOT = Path(__file__).resolve().parents[1]


def _sha(value: int) -> str:
    return f"{value:064x}"


def test_native_v2_cross_language_golden_vectors() -> None:
    digits = [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "0",
        "1",
    ]
    components = {
        name: digit * 64
        for name, digit in zip(clone.REQUIRED_STATE_COMPONENTS, digits)
    }
    state_sha = clone.canonical_state_component_sha256(components)
    assert state_sha == (
        "9f0b94609fe67626b80f2f7af88d895f"
        "daccbf69ef8baf807fd34da1074b5aac"
    )
    boundary = {
        "decision_boundary_kind": "source_arbitration",
        "decision_time_bits": "40d5180800000000",
        "decision_event_seq": 42,
        "node": 52,
        "runtime_bag_id": 101,
        "baseline_next_node": 53,
        "baseline_release": True,
        "baseline_pibt_enabled": False,
        "pibt_owner_runtime_bag_id": 101,
        "source_ready_order": [101, 102, 103],
        "pending_merge_request_order": [9001, 9002, 9003],
        "legal_next_edges": [51, 53],
        "runtime_state_sha256": state_sha,
        "queue_top_not_popped": True,
        "staged_event_sink_empty": True,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "reservation_depth": 1,
        "max_selected_edges_per_bag": 1,
    }
    boundary["clone_group_id"] = clone.expected_clone_group_id(boundary)
    assert boundary["clone_group_id"] == (
        "6651d8a2f2d69c967f163185899b7257"
        "03318c23ed16219929c659f259cfd575"
    )
    boundary["boundary_sha256"] = clone.expected_boundary_sha256(boundary)
    assert boundary["boundary_sha256"] == (
        "0d798e3b0d42088b7d25c0e1d699f13"
        "9947bd96d2d193dc4e9b50e2fed20c946"
    )
    intervention = {
        **boundary,
        "intervention_kind": "I1_source_order_swap",
        "horizon": "H_bag",
        "intervention": {
            "runtime_bag_id": 101,
            "peer_runtime_bag_id": 102,
            "merge_request_id": 0,
            "peer_merge_request_id": 0,
            "selected_next_node": -1,
            "selected_boolean": False,
        },
    }
    assert clone.expected_intervention_id(intervention) == (
        "8bc39b5db5c37ceb9996054fc8d22fe5"
        "8f623a939e06cae9686e6c794f565cea"
    )


def _boundary(kind: str, seed: int = 1) -> dict[str, object]:
    components = {
        name: _sha(seed * 100 + index)
        for index, name in enumerate(clone.REQUIRED_STATE_COMPONENTS)
    }
    row = {
        "decision_boundary_kind": kind,
        "decision_time_bits": struct.pack(">d", float(seed)).hex(),
        "decision_event_seq": seed,
        "node": seed + 10,
        "runtime_bag_id": seed * 10 + 1,
        "baseline_next_node": 53,
        "baseline_release": True,
        "baseline_pibt_enabled": False,
        "pibt_owner_runtime_bag_id": -1,
        "source_ready_order": [
            seed * 10 + 1,
            seed * 10 + 2,
            seed * 10 + 3,
        ],
        "pending_merge_request_order": [
            seed * 100 + 1,
            seed * 100 + 2,
            seed * 100 + 3,
        ],
        "legal_next_edges": [51, 53],
        "runtime_state_sha256": clone.canonical_state_component_sha256(
            components
        ),
        "state_components": components,
        "queue_top_not_popped": True,
        "staged_event_sink_empty": True,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "reservation_depth": 1,
        "max_selected_edges_per_bag": 1,
    }
    row["ready_set_sha256"] = clone.canonical_ready_set_sha256(row)
    row["clone_group_id"] = clone.expected_clone_group_id(row)
    row["boundary_sha256"] = clone.expected_boundary_sha256(row)
    return row


def _seal_fidelity(row: dict[str, object]) -> dict[str, object]:
    row["fidelity_id"] = clone.expected_fidelity_id(row)
    row["evidence_row_sha256"] = clone.canonical_sha256(
        {
            key: value
            for key, value in row.items()
            if key != "evidence_row_sha256"
        }
    )
    return row


def _fidelity(seed: int = 1) -> dict[str, object]:
    hashes = {
        name: _sha(seed * 10000 + index)
        for index, name in enumerate(clone.REQUIRED_FIDELITY_HASHES)
    }
    action = _sha(seed * 20000)
    return _seal_fidelity(
        {
            "schema": clone.FIDELITY_SCHEMA,
            **_boundary("source_arbitration", seed),
            "original_action_sha256": action,
            "clone_action_sha256": action,
            "original_hashes": hashes,
            "clone_hashes": deepcopy(hashes),
        }
    )


def _branch_invariants(
    *, treatment: bool, horizon_count: int
) -> dict[str, object]:
    return {
        "intervention_hit_count": int(treatment),
        "completed_affected_bag_count": 2,
        "completed_horizon_entity_count": horizon_count,
        "unsafe_entry_count": 0,
        "reservation_conflict_count": 0,
        "runtime_full_astar_call_count": 0,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "max_selected_edges_per_bag": 1,
        "reservation_depth": 1,
        "failed_segment_count": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
    }


def _metrics(offset: str) -> dict[str, str]:
    base = Decimal(offset)
    metrics = {
        name: clone.canonical_decimal(base + Decimal(index))
        for index, name in enumerate(clone.METRICS)
    }
    metrics["deadline_miss_count"] = "0"
    return metrics


def _seal_intervention(row: dict[str, object]) -> dict[str, object]:
    row["intervention_token_sha256"] = (
        clone.expected_intervention_token_sha256(row)
    )
    row["intervention_id"] = clone.expected_intervention_id(row)
    row["baseline_outcome_sha256"] = clone.canonical_sha256(
        {
            "schema": clone.OUTCOME_SCHEMA,
            "metrics": row["baseline_metrics"],
            "invariants": row["baseline_invariants"],
        }
    )
    row["treatment_outcome_sha256"] = clone.canonical_sha256(
        {
            "schema": clone.OUTCOME_SCHEMA,
            "metrics": row["treatment_metrics"],
            "invariants": row["treatment_invariants"],
        }
    )
    row["evidence_row_sha256"] = clone.canonical_sha256(
        {
            key: value
            for key, value in row.items()
            if key != "evidence_row_sha256"
        }
    )
    return row


def _intervention(
    kind: str,
    seed: int = 1,
    *,
    horizon: str = "H_bag",
    split: str = "train",
) -> dict[str, object]:
    boundary = _boundary(clone.INTERVENTION_BOUNDARY_KIND[kind], seed)
    intervention = {
        "runtime_bag_id": -1,
        "peer_runtime_bag_id": -1,
        "merge_request_id": 0,
        "peer_merge_request_id": 0,
        "selected_next_node": -1,
        "selected_boolean": False,
    }
    if kind == "I1_source_order_swap":
        intervention["runtime_bag_id"] = boundary["source_ready_order"][0]
        intervention["peer_runtime_bag_id"] = boundary[
            "source_ready_order"
        ][1]
    elif kind == "I2_merge_request_order_swap":
        intervention["merge_request_id"] = boundary[
            "pending_merge_request_order"
        ][0]
        intervention["peer_merge_request_id"] = boundary[
            "pending_merge_request_order"
        ][1]
    elif kind == "I3_next_edge":
        intervention["runtime_bag_id"] = boundary["runtime_bag_id"]
        intervention["selected_next_node"] = 51
    elif kind == "I4_hold_release":
        intervention["runtime_bag_id"] = boundary["runtime_bag_id"]
        intervention["selected_boolean"] = False
    elif kind == "I5_pibt_trigger":
        intervention["runtime_bag_id"] = boundary["runtime_bag_id"]
        intervention["selected_boolean"] = True
    baseline_metrics = _metrics("10")
    treatment_metrics = _metrics("9.5")
    deltas = {
        f"{name}_delta": clone.canonical_decimal(
            Decimal(treatment_metrics[name]) - Decimal(baseline_metrics[name])
        )
        for name in clone.METRICS
    }
    row = {
        "schema": clone.INTERVENTION_SCHEMA,
        **boundary,
        "intervention_kind": kind,
        "horizon": horizon,
        "split": split,
        "raw_bag_ids": [f"bag-{seed}-a", f"bag-{seed}-b"],
        "raw_task_ids": [f"task-{seed}"],
        "segment_ids": [f"segment-{seed}"],
        "baseline_start_state_sha256": boundary["runtime_state_sha256"],
        "treatment_start_state_sha256": boundary["runtime_state_sha256"],
        "intervention": intervention,
        "affected_bag_count": 2,
        "baseline_metrics": baseline_metrics,
        "treatment_metrics": treatment_metrics,
        "deltas": deltas,
    }
    row["horizon_entity_ids"] = list(row["raw_bag_ids"])
    if horizon == "H_system":
        row["horizon_entity_ids"].append(f"bag-{seed}-system-extra")
        row["horizon_entity_ids"].sort()
    row["required_horizon_completion_count"] = len(
        row["horizon_entity_ids"]
    )
    row["baseline_invariants"] = _branch_invariants(
        treatment=False,
        horizon_count=len(row["horizon_entity_ids"]),
    )
    row["treatment_invariants"] = _branch_invariants(
        treatment=True,
        horizon_count=len(row["horizon_entity_ids"]),
    )
    row["horizon_entity_set_sha256"] = clone.canonical_sha256(
        {
            "schema": clone.INTERVENTION_SCHEMA,
            "horizon": horizon,
            "horizon_entity_ids": row["horizon_entity_ids"],
        }
    )
    return _seal_intervention(row)


def _reseal(row: dict[str, object]) -> None:
    row.pop("evidence_row_sha256", None)
    _seal_intervention(row)


def test_fidelity_is_recomputed_from_five_raw_hashes() -> None:
    result = clone.validate_fidelity_rows([_fidelity()])
    assert result["clone_replay_fidelity"] == "1"
    assert result["fidelity_exact_match_count"] == 1

    bad = _fidelity()
    bad["clone_hashes"]["junction_state_sha256"] = _sha(999)
    bad = _seal_fidelity(bad)
    with pytest.raises(clone.CloneValidationError, match="below 100%"):
        clone.validate_fidelity_rows([bad])


def test_complete_state_inventory_is_exact_and_content_addressed() -> None:
    bad = _fidelity()
    del bad["state_components"]["merge_grants_sha256"]
    bad = _seal_fidelity(bad)
    with pytest.raises(clone.CloneValidationError, match="inventory"):
        clone.validate_fidelity_row(bad)

    bad = _fidelity()
    bad["clone_group_id"] = _sha(77)
    bad = _seal_fidelity(bad)
    with pytest.raises(clone.CloneValidationError, match="clone_group_id"):
        clone.validate_fidelity_row(bad)


@pytest.mark.parametrize("kind", sorted(clone.INTERVENTION_ACTION_FIELD))
def test_each_intervention_is_one_local_action_and_one_shot(kind: str) -> None:
    clone.validate_intervention_row(_intervention(kind))

    bad = _intervention(kind)
    bad["intervention"]["peer_merge_request_id"] = 999
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="one legal native"):
        clone.validate_intervention_row(bad)

    bad = _intervention(kind)
    bad["treatment_invariants"]["intervention_hit_count"] = 2
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="exactly once"):
        clone.validate_intervention_row(bad)


def test_deltas_and_outcomes_are_recomputed_not_self_reported() -> None:
    bad = _intervention("I3_next_edge")
    bad["deltas"]["network_wait_seconds_delta"] = "0"
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="treatment minus"):
        clone.validate_intervention_row(bad)

    bad = _intervention("I4_hold_release")
    bad["baseline_outcome_sha256"] = _sha(999)
    bad["evidence_row_sha256"] = clone.canonical_sha256(
        {
            key: value
            for key, value in bad.items()
            if key != "evidence_row_sha256"
        }
    )
    with pytest.raises(clone.CloneValidationError, match="outcome hash"):
        clone.validate_intervention_row(bad)


def test_csv_numbers_must_use_canonical_decimal_text() -> None:
    assert clone._require_decimal("value", "1.25") == Decimal("1.25")
    with pytest.raises(clone.CloneValidationError, match="canonical decimal"):
        clone._require_decimal("value", "1.250")
    with pytest.raises(clone.CloneValidationError, match="canonical decimal"):
        clone._require_decimal("value", "1e0")


def test_h_local_and_incomplete_or_unsafe_branches_are_not_labels() -> None:
    bad = _intervention("I1_source_order_swap", horizon="H_local")
    with pytest.raises(clone.CloneValidationError, match="screening-only"):
        clone.validate_intervention_row(bad)

    bad = _intervention("I2_merge_request_order_swap")
    bad["treatment_invariants"]["completed_horizon_entity_count"] = 1
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="incomplete"):
        clone.validate_intervention_row(bad)

    bad = _intervention("I5_pibt_trigger")
    bad["treatment_invariants"]["unsafe_entry_count"] = 1
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="unsafe_entry_count"):
        clone.validate_intervention_row(bad)


def test_horizon_denominators_are_bound_to_real_identity_sets() -> None:
    bad = _intervention("I3_next_edge")
    bad["affected_bag_count"] = 1
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="raw_bag_ids"):
        clone.validate_intervention_row(bad)

    bad = _intervention("I4_hold_release")
    bad["horizon_entity_ids"] = ["unrelated-bag"]
    bad["horizon_entity_set_sha256"] = clone.canonical_sha256(
        {
            "schema": clone.INTERVENTION_SCHEMA,
            "horizon": "H_bag",
            "horizon_entity_ids": bad["horizon_entity_ids"],
        }
    )
    bad["required_horizon_completion_count"] = 1
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="affected bag set"):
        clone.validate_intervention_row(bad)

    bad = _intervention("I5_pibt_trigger", horizon="H_system")
    bad["horizon_entity_ids"] = list(bad["raw_bag_ids"])
    bad["required_horizon_completion_count"] = len(bad["raw_bag_ids"])
    bad["baseline_invariants"]["completed_horizon_entity_count"] = 2
    bad["treatment_invariants"]["completed_horizon_entity_count"] = 2
    bad["horizon_entity_set_sha256"] = clone.canonical_sha256(
        {
            "schema": clone.INTERVENTION_SCHEMA,
            "horizon": "H_system",
            "horizon_entity_ids": bad["horizon_entity_ids"],
        }
    )
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="strictly exceed"):
        clone.validate_intervention_row(bad)


def test_metrics_are_nonnegative_and_deadline_count_is_integral() -> None:
    bad = _intervention("I1_source_order_swap")
    bad["treatment_metrics"]["network_wait_seconds"] = "-1"
    bad["deltas"]["network_wait_seconds_delta"] = "-17"
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="non-negative"):
        clone.validate_intervention_row(bad)

    bad = _intervention("I2_merge_request_order_swap")
    bad["treatment_metrics"]["deadline_miss_count"] = "1.5"
    bad["deltas"]["deadline_miss_count_delta"] = "-0.5"
    _reseal(bad)
    with pytest.raises(clone.CloneValidationError, match="integer"):
        clone.validate_intervention_row(bad)


def test_campaign_gate_cannot_be_lowered_and_duplicates_are_rejected() -> None:
    rows = [
        _intervention(kind, seed=index + 1)
        for index, kind in enumerate(sorted(clone.INTERVENTION_ACTION_FIELD))
    ]
    with pytest.raises(clone.CloneValidationError, match="< 2000"):
        clone.validate_campaign([_fidelity()], rows)

    normalized = [clone.validate_intervention_row(row) for row in rows]
    duplicate = [*normalized, normalized[0]]
    with pytest.raises(clone.CloneValidationError, match="duplicate"):
        clone._campaign_summary(duplicate)


def test_every_intervention_clone_requires_its_own_noop_fidelity() -> None:
    fidelity = [clone.validate_fidelity_row(_fidelity(seed=1))]
    rows = [
        clone.validate_intervention_row(
            _intervention("I1_source_order_swap", seed=1)
        ),
        clone.validate_intervention_row(
            _intervention("I2_merge_request_order_swap", seed=2)
        ),
    ]
    with pytest.raises(clone.CloneValidationError, match="lack matched"):
        clone._validate_fidelity_coverage(fidelity, rows)


def test_union_find_rejects_indirect_cross_split_leakage() -> None:
    first = clone.validate_intervention_row(
        _intervention("I1_source_order_swap", seed=1, split="train")
    )
    second_raw = _intervention(
        "I2_merge_request_order_swap", seed=2, split="train"
    )
    second_raw["raw_task_ids"] = list(first["raw_task_ids"])
    _reseal(second_raw)
    second = clone.validate_intervention_row(second_raw)
    third_raw = _intervention(
        "I3_next_edge", seed=3, split="audit"
    )
    third_raw["segment_ids"] = list(second["segment_ids"])
    _reseal(third_raw)
    third = clone.validate_intervention_row(third_raw)
    with pytest.raises(clone.CloneValidationError, match="split leakage"):
        clone.validate_split_disjointness([first, second, third])


def test_ledger_is_recomputed_from_raw_rows() -> None:
    rows = [
        clone.validate_intervention_row(_intervention(kind, seed=index + 1))
        for index, kind in enumerate(sorted(clone.INTERVENTION_ACTION_FIELD))
    ]
    ledger = clone.expected_ledger_rows(rows)
    result = clone.validate_ledger_rows(ledger, rows)
    assert result["ledger_row_count"] == 5

    tampered = deepcopy(ledger)
    tampered[0]["mean_network_wait_seconds_delta"] = "99"
    with pytest.raises(clone.CloneValidationError, match="does not recompute"):
        clone.validate_ledger_rows(tampered, rows)


def test_provenance_is_exact_canonical_g13_frozen_and_one_x() -> None:
    expected = clone._expected_provenance()
    assert expected["workload"] == {
        "demand_scale": "1.0",
        "expanded_workload_used": False,
    }
    assert expected["g4irsf13_associative_delay_ledger"] == {
        "path": "outputs/tables/g4irsf13_delay_component_ledger.csv",
        "file_sha256": (
            "cd90509cdd134f4e1cc2653438e0ca61"
            "e0366f7ca0f166c40d79ab18fbdef847"
        ),
    }
    bad = deepcopy(expected)
    bad["workload"]["demand_scale"] = "1.1"
    with pytest.raises(clone.CloneValidationError, match="canonical <=1x"):
        clone._validate_provenance(bad, ROOT)


def test_canonical_task_membership_is_rebuilt_not_self_reported() -> None:
    row = {
        "raw_bag_ids": ["0"],
        "raw_task_ids": ["0"],
        "segment_ids": ["0:storage_in", "0:storage_out"],
        "horizon_entity_ids": ["0"],
    }
    clone.validate_input_identity_bindings([row], ROOT)

    bad = deepcopy(row)
    bad["segment_ids"] = ["0:storage_in"]
    with pytest.raises(clone.CloneValidationError, match="segment_ids omit"):
        clone.validate_input_identity_bindings([bad], ROOT)


def test_preregistration_requires_embedded_complete_registry() -> None:
    row = clone.validate_intervention_row(
        _intervention("I5_pibt_trigger", horizon="H_system")
    )
    registered = [
        {
            "clone_group_id": row["clone_group_id"],
            "intervention_id": row["intervention_id"],
            "intervention_token_sha256": row[
                "intervention_token_sha256"
            ],
            "horizon": row["horizon"],
            "split": row["split"],
            "horizon_entity_set_sha256": row[
                "horizon_entity_set_sha256"
            ],
        }
    ]
    preregistration = {
        "opportunity_manifest_sha256": clone.canonical_sha256(registered),
        "campaign_seed_sha256": _sha(123),
        "requested_matched_intervention_count": 1,
        "requested_system_horizon_count": 1,
        "registered_opportunities": registered,
    }
    with pytest.raises(clone.CloneValidationError, match="below 2000"):
        clone._validate_preregistration(preregistration)


def test_csv_contract_rejects_missing_or_extra_columns(tmp_path) -> None:
    path = tmp_path / "fidelity.csv"
    path.write_text("schema,extra\nx,y\n", encoding="utf-8")
    with pytest.raises(clone.CloneValidationError, match="columns mismatch"):
        clone._read_csv(
            path,
            clone.FIDELITY_COLUMNS,
            clone._decode_fidelity_csv_row,
        )


def test_manifest_validator_fails_closed_when_artifacts_are_absent(
    tmp_path,
) -> None:
    with pytest.raises(clone.CloneValidationError, match="required artifact"):
        clone.validate_artifacts(tmp_path)


def test_formal_entrypoint_retains_causal_evidence_blocker(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        clone,
        "validate_artifact_protocol",
        lambda _root: {
            "status": clone.PROTOCOL_STATUS,
            "noop_exact_binary_fidelity_mechanism": "AVAILABLE",
            # Self-reported causal/formal claims cannot override the hard
            # blocker in the independent formal entrypoint.
            "formal_exact_binary_i1_i5_one_shot_reruns": "ESTABLISHED",
            "original_task_2000_h_system_formal_evidence": "ESTABLISHED",
            "formal_pass_claimed": True,
        },
    )
    with pytest.raises(
        clone.CloneValidationError,
        match=clone.FORMAL_CAUSAL_BLOCKER,
    ):
        clone.validate_artifacts(ROOT)

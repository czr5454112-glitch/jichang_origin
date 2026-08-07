from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from czr005 import cpp_backend
from czr005.g4irsf17.features import (
    CANDIDATE_FEATURES,
    CONTEXT_FEATURES,
    PAIRWISE_FEATURES,
)
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records


ROOT = Path(__file__).resolve().parents[1]


def _artifact(kind: str, *, authorized: bool = True) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema": "czr005.g4irsf17.source_policy.v1",
        "kind": kind,
        "authorized": authorized,
        "supervisor_authorized": True,
        "top_k": 2,
    }
    if kind == "pairwise_linear_selective":
        weights = [0.0] * len(PAIRWISE_FEATURES)
        weights[PAIRWISE_FEATURES.index("delta_candidate_deadline_slack_seconds")] = -1.0
        artifact.update(
            {
                "feature_names": list(PAIRWISE_FEATURES),
                "weights": weights,
                "bias": 0.0,
                "feature_lower": [-1.0e6] * len(PAIRWISE_FEATURES),
                "feature_upper": [1.0e6] * len(PAIRWISE_FEATURES),
                "evidence": {
                    "benefit_probability_lcb": 0.9,
                    "harmful_probability_ucb": 0.01,
                    "utility_lcb_seconds": 1.0,
                    "calibration_ece": 0.01,
                },
                "thresholds": {
                    "benefit_probability_lcb_min": 0.6,
                    "harmful_probability_ucb_max": 0.05,
                    "utility_lcb_min_seconds": 0.0,
                    "calibration_ece_max": 0.08,
                },
            }
        )
    return artifact


def _ensemble_artifact(
    *,
    runtime_authorized: bool,
    ood_zero_envelope: bool = False,
    authorized: bool = True,
    benefit_bias: float = 2.0,
) -> dict[str, Any]:
    names = list(PAIRWISE_FEATURES)
    artifact_set_id = "g4irsf17-i1-pytest-set"

    def member(family: str, bias: float) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family": family,
            "feature_names": names,
            "mean": [0.0] * len(names),
            "scale": [1.0] * len(names),
            "weights": [0.0] * len(names),
            "bias": bias,
            "identity_features_used": False,
        }
        if family == "pairwise_linear_logistic":
            payload["objective"] = "logistic"
        return payload

    lower = [0.0] * len(names) if ood_zero_envelope else [-1.0e6] * len(names)
    upper = [0.0] * len(names) if ood_zero_envelope else [1.0e6] * len(names)
    pairwise = {
        "schema": "czr005.g4irsf17.i1_pairwise_ensemble.v1",
        "artifact_set_id": artifact_set_id,
        "benefit_members": [
            member("pairwise_linear_logistic", benefit_bias) for _ in range(3)
        ],
        "harm_members": [
            member("pairwise_linear_logistic", -5.0) for _ in range(3)
        ],
        "utility_members": [
            member("linear_ridge_utility", 1.0) for _ in range(3)
        ],
        "benefit_calibrators": [
            {"family": "platt_logistic", "slope": 1.0, "intercept": 0.0}
            for _ in range(3)
        ],
        "harm_calibrators": [
            {"family": "platt_logistic", "slope": 1.0, "intercept": 0.0}
            for _ in range(3)
        ],
        "utility_residual_q05_seconds": 0.0,
        "ood_envelope": {
            "family": "quantile_feature_envelope",
            "feature_names": names,
            "lower": lower,
            "upper": upper,
            "identity_features_used": False,
        },
        "identity_features_used": False,
        "outcome_features_used": False,
    }
    gate = {
        "schema": "czr005.g4irsf17.i1_selective_gate.v1",
        "artifact_set_id": artifact_set_id,
        "authorized": authorized,
        "runtime_closed_loop_authorized": runtime_authorized,
        "identity_features_used": False,
        "calibration": {"available": True, "promotion_ece": 0.01},
        "selector": {
            "benefit_probability_lcb_min": 0.6,
            "harm_probability_ucb_max": 0.05,
            "utility_lcb_min_seconds": 0.0,
            "calibration_ece_max": 0.08,
            "lower_quantile": 0.05,
            "upper_quantile": 0.95,
            "ensemble_size": 3,
            "supervisor_authorization_required": True,
            "ood_abstention_required": True,
        },
    }
    return cpp_backend.g4irsf17_pairwise_ensemble_source_policy_artifact(
        pairwise,
        gate,
        supervisor_authorized=True,
    )


def _run(*, mode: str = "off", artifact: dict[str, Any] | None = None) -> dict:
    nodes, edges, heuristic = canonical_graph_records()
    bags = [
        ("g17-a:direct", 1, 0.0, 1000.0, 3, 47, "typed-direct"),
        ("g17-b:storage_out", 2, 0.0, 10.0, 3, 47, "typed-storage"),
    ]
    module = cpp_backend.load_cpp_module()
    return dict(
        module.g4irsf11_event_runtime_from_records(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=bags,
            fault_windows=[],
            queue_discipline="fifo",
            event_semantics="E1",
            minimum_service_seconds=0.25,
            local_queue_capacity=8,
            admission_mode="off",
            enable_source_admission=False,
            scenario="pytest_g4irsf17_source_policy",
            g4irsf17_source_policy_mode=mode,
            g4irsf17_source_policy_artifact=artifact or {},
            g4irsf17_source_policy_trace_limit=100,
        )
    )


def test_native_source_front_schema_rule_and_exact_off() -> None:
    disabled = _run()
    assert "g4irsf17_source_policy_decisions" not in disabled
    assert not any(
        key.startswith("g4irsf17_source_policy") for key in disabled["summary"]
    )

    shadow = _run(mode="shadow", artifact=_artifact("localized_thesis_rule"))
    assert [row["admitted_time"] for row in shadow["bags"]] == [
        row["admitted_time"] for row in disabled["bags"]
    ]
    assert shadow["summary"]["g4irsf17_source_policy_activation_count"] == 0

    closed = _run(
        mode="closed_loop", artifact=_artifact("localized_thesis_rule")
    )
    row = closed["g4irsf17_source_policy_decisions"][0]
    assert row["activated"] is True
    assert row["baseline_candidate_index"] == 0
    assert row["treatment_candidate_index"] == 1
    assert row["chosen_candidate_index"] == 1
    assert row["candidate_feature_names"] == list(CANDIDATE_FEATURES)
    assert row["context_feature_names"] == list(CONTEXT_FEATURES)
    assert row["pairwise_feature_names"] == list(PAIRWISE_FEATURES)
    assert len(row["candidate_features"]) == 2
    assert all(len(item) == 10 for item in row["candidate_features"])
    assert len(row["shared_context_features"]) == 29
    assert len(row["pairwise_features"]) == 39
    assert all(
        len(item) == 39 for item in row["canonical_candidate_observations"]
    )
    assert row["identity_fields_are_trace_only"] is True
    summary = closed["summary"]
    assert summary["g4irsf17_source_policy_runtime_global_scan_count"] == 0
    assert summary["g4irsf17_source_policy_future_route_input_count"] == 0
    assert summary["g4irsf17_source_policy_future_schedule_input_count"] == 0
    assert summary["g4irsf17_source_policy_full_astar_call_count"] == 0


def test_native_learned_policy_activates_and_abstains_ood() -> None:
    activated = _run(
        mode="closed_loop",
        artifact=_ensemble_artifact(runtime_authorized=True),
    )
    row = activated["g4irsf17_source_policy_decisions"][0]
    assert row["activated"] is True
    assert row["reason"] == "ACTIVATE_PAIRWISE_ENSEMBLE"
    assert row["benefit_probability_lcb"] > 0.8
    assert row["harmful_probability_ucb"] < 0.01
    assert (
        activated["summary"][
            "g4irsf17_source_policy_runtime_closed_loop_authorized"
        ]
        is True
    )

    abstained = _run(
        mode="closed_loop",
        artifact=_ensemble_artifact(
            runtime_authorized=True, ood_zero_envelope=True
        ),
    )
    row = abstained["g4irsf17_source_policy_decisions"][0]
    assert row["activated"] is False
    assert row["chosen_candidate_index"] == 0
    assert row["reason"] == "OOD_GATE"

    offline_only = _run(
        mode="closed_loop",
        artifact=_ensemble_artifact(runtime_authorized=False),
    )
    row = offline_only["g4irsf17_source_policy_decisions"][0]
    assert row["activated"] is False
    assert row["chosen_candidate_index"] == 0
    assert row["reason"] == "RUNTIME_CLOSED_LOOP_NOT_AUTHORIZED"


def test_unauthorized_low_score_keeps_baseline_but_exports_exact_treatment() -> None:
    payload = _run(
        mode="closed_loop",
        artifact=_ensemble_artifact(
            runtime_authorized=False,
            authorized=False,
            benefit_bias=-2.0,
        ),
    )
    row = payload["g4irsf17_source_policy_decisions"][0]
    assert row["activated"] is False
    assert row["reason"] == "ARTIFACT_NOT_AUTHORIZED"
    assert row["baseline_candidate_index"] == 0
    assert row["proposed_candidate_index"] == 0
    assert row["treatment_candidate_index"] == 1
    assert row["chosen_candidate_index"] == 0
    assert row["pairwise_features"][0] == pytest.approx(
        row["canonical_candidate_observations"][1][0]
        - row["canonical_candidate_observations"][0][0]
    )
    assert row["pairwise_features"] != [0.0] * len(PAIRWISE_FEATURES)


def test_artifact_set_id_rejects_cross_run_splicing() -> None:
    bundle = _ensemble_artifact(runtime_authorized=False)
    assert bundle["artifact_set_id"] == bundle["pairwise_artifact"][
        "artifact_set_id"
    ]
    assert bundle["artifact_set_id"] == bundle["gate_artifact"][
        "artifact_set_id"
    ]

    mismatched_gate = copy.deepcopy(bundle["gate_artifact"])
    mismatched_gate["artifact_set_id"] = "g4irsf17-i1-other-run"
    with pytest.raises(ValueError, match="artifact_set_id mismatch"):
        cpp_backend.g4irsf17_pairwise_ensemble_source_policy_artifact(
            bundle["pairwise_artifact"], mismatched_gate
        )

    native_mismatch = copy.deepcopy(bundle)
    native_mismatch["gate_artifact"]["artifact_set_id"] = (
        "g4irsf17-i1-other-run"
    )
    with pytest.raises(ValueError, match="artifact_set_id mismatch"):
        _run(mode="shadow", artifact=native_mismatch)


def test_published_model_gate_bundle_is_fail_closed_in_native_shadow() -> None:
    pairwise_path = (
        ROOT / "artifacts/models/g4irsf17_i1_pairwise_linear.json"
    )
    gate_path = ROOT / "artifacts/gates/g4irsf17_i1_selective_gate.json"
    bundle = cpp_backend.g4irsf17_pairwise_ensemble_source_policy_artifact(
        pairwise_path,
        gate_path,
        supervisor_authorized=True,
    )

    artifact_set_id = bundle["artifact_set_id"]
    assert artifact_set_id == bundle["pairwise_artifact"]["artifact_set_id"]
    assert artifact_set_id == bundle["gate_artifact"]["artifact_set_id"]
    assert bundle["authorized"] is False
    assert bundle["runtime_closed_loop_authorized"] is False

    # The repository can run pure-Python tests without a compiled extension.
    # Whenever a native module is present (CI CMake job or developer build),
    # this same test also exercises the final pybind parser and shadow runtime.
    if not cpp_backend.is_available():
        return
    payload = _run(mode="shadow", artifact=bundle)
    summary = payload["summary"]
    assert summary["g4irsf17_source_policy_artifact_set_id"] == artifact_set_id
    assert summary["g4irsf17_source_policy_authorized"] is False
    assert summary["g4irsf17_source_policy_runtime_closed_loop_authorized"] is False
    assert summary["g4irsf17_source_policy_activation_count"] == 0
    decisions = payload["g4irsf17_source_policy_decisions"]
    assert decisions
    assert all(row["activated"] is False for row in decisions)
    assert all(row["reason"] == "ARTIFACT_NOT_AUTHORIZED" for row in decisions)
    assert all(row["artifact_set_id"] == artifact_set_id for row in decisions)


def test_python_wrapper_materializes_append_only_policy_tail() -> None:
    nodes, edges, heuristic = canonical_graph_records()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=[
            ("g17-a:direct", 1, 0.0, 1000.0, 3, 47, "typed-direct"),
            ("g17-b:storage_out", 2, 0.0, 10.0, 3, 47, "typed-storage"),
        ],
        queue_discipline="fifo",
        event_semantics="E1",
        minimum_service_seconds=0.25,
        local_queue_capacity=8,
        admission_mode="off",
        enable_source_admission=False,
        enable_g4irsf17_source_wait_telemetry=True,
        g4irsf17_source_wait_trace_limit=100,
        g4irsf17_source_policy_mode="closed_loop",
        g4irsf17_source_policy_artifact=_artifact("localized_thesis_rule"),
        g4irsf17_source_policy_trace_limit=100,
    )
    assert payload["summary"]["g4irsf17_source_policy_activation_count"] > 0
    assert payload["summary"]["g4irsf17_source_wait_telemetry_enabled"] is True
    assert payload["g4irsf17_source_policy_decisions"][0]["activated"] is True


def test_python_wrapper_append_only_positional_tail_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    common = {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": [
            ("g17-tail:direct", 1, 0.0, 1000.0, 3, 47, "typed-direct")
        ],
    }

    cpp_backend.g4irsf11_event_runtime_from_records(**common)
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        enable_g4irsf17_source_wait_telemetry=True,
        g4irsf17_source_wait_trace_limit=17,
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        g4irsf17_source_policy_mode="shadow",
        g4irsf17_source_policy_artifact=_artifact("localized_thesis_rule"),
        g4irsf17_source_policy_trace_limit=23,
    )
    cpp_backend.g4irsf11_event_runtime_from_records(
        **common,
        enable_g4irsf17_source_wait_telemetry=True,
        g4irsf17_source_wait_trace_limit=19,
        g4irsf17_source_policy_mode="shadow",
        g4irsf17_source_policy_artifact=_artifact("localized_thesis_rule"),
        g4irsf17_source_policy_trace_limit=29,
    )

    assert [len(args) for args in captured] == [58, 67, 70, 70]
    assert captured[0][55:] == (
        "E0_immediate_dispatch_f2",
        False,
        200_000,
    )
    assert captured[1][58:] == (
        "M1",
        64,
        1024,
        "off",
        {},
        {},
        {},
        True,
        17,
    )
    assert captured[2][65:67] == (False, 200_000)
    assert captured[2][67] == "shadow"
    assert captured[2][69] == 23
    assert captured[3][65:67] == (True, 19)
    assert captured[3][67] == "shadow"
    assert captured[3][69] == 29

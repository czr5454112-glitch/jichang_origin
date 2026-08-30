from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

import pytest

from czr005 import cpp_backend
from czr005.datasets.decision_trace import canonicalise_decision_row
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_PATH,
    assert_canonical_map,
    canonical_graph_records,
)
from scripts.eval import g4irsf12_frozen_g4e_adapter as frozen_adapter


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MODEL_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)


def _backend_binary() -> Path:
    loaded = sys.modules.get(cpp_backend.CPP_MODULE_NAME)
    loaded_file = getattr(loaded, "__file__", None)
    if loaded_file:
        return Path(loaded_file).resolve()
    directories = (
        ROOT / "build_g4irsf12" / "python",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
    )
    for directory in directories:
        matches = sorted(
            path
            for pattern in ("czr005_cpp*.pyd", "czr005_cpp*.so")
            for path in directory.glob(pattern)
            if path.is_file()
        )
        if matches:
            return matches[0].resolve()
    pytest.skip("a built czr005_cpp extension is required for backend integration")


def _run_real_map(
    *,
    scorer_mode: str,
    summary_only: bool,
    binary: Path,
    scorer_model_path: Path | None = None,
) -> dict[str, object]:
    assert assert_canonical_map() == CANONICAL_MAP_PATH
    nodes, edges, heuristic = canonical_graph_records()
    return cpp_backend.g4irsf11_event_runtime_from_records(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        # This is a real map2 branch and goal used by the frozen-event audit.
        # The one-bag motif isolates scorer semantics without inventing topology.
        bag_records=[
            (
                "5023:direct:g4irsf11_c1:trace_highflow_2p5",
                5023,
                0.0,
                10_000.0,
                9,
                50,
                "g4irsf12_frozen_trace_motif",
            )
        ],
        resource_semantics="R3_java_node_window_compatible",
        framework_mode="event_loop_one_step",
        scorer_mode=scorer_mode,
        scorer_model_path=scorer_model_path,
        pibt_mode="P0",
        pibt_max_depth=0,
        pressure_mode="off",
        admission_mode="off",
        enable_backpressure=False,
        enable_source_admission=False,
        enable_pibt_lite=False,
        local_queue_capacity=32,
        max_events=20_000_000,
        max_simulation_time=10_000.0,
        trace_limit=64,
        summary_only=summary_only,
        expected_binary_path=binary,
        search_path=binary.parent,
        scenario=f"g4irsf12_backend_{scorer_mode}",
    )


@pytest.mark.parametrize(
    ("mode", "scorer_id", "uses_frozen_model"),
    [
        ("S0_current_handwritten", "S0_current_handwritten_static_score", False),
        (
            "S1_frozen_g4e_legal_local_adapter",
            "S1_frozen_g4e_legal_local_adapter",
            True,
        ),
        (
            "S2_frozen_g4e_without_absolute_node_ids",
            "S2_frozen_g4e_without_absolute_node_ids",
            True,
        ),
        ("S3_shortest_potential_only", "S3_shortest_potential_only", False),
        ("S4_queue_aware_rule_only", "S4_queue_aware_rule_only", False),
        (
            "S4_uncovered_local_work_seconds_rule_only",
            "S4_uncovered_local_work_seconds_rule_only",
            False,
        ),
        (
            "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only",
            "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only",
            False,
        ),
        (
            "S4_typed_service_dominance_rule_only",
            "S4_typed_service_dominance_rule_only",
            False,
        ),
    ],
)
def test_s0_s4_real_backend_identity_echo_and_summary_only(
    mode: str,
    scorer_id: str,
    uses_frozen_model: bool,
) -> None:
    binary = _backend_binary()
    payload = _run_real_map(
        scorer_mode=mode,
        summary_only=True,
        binary=binary,
    )
    summary = payload["summary"]
    assert isinstance(summary, dict)
    expected_binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert Path(str(payload["loaded_cpp_binary_path"])).resolve() == binary
    assert payload["loaded_cpp_binary_sha256"] == expected_binary_sha
    assert Path(str(summary["loaded_cpp_binary_path"])).resolve() == binary
    assert summary["loaded_cpp_binary_sha256"] == expected_binary_sha
    assert summary["resource_semantics_id"] == "R3_java_node_window_compatible"
    assert summary["framework_mode"] == "event_loop_one_step"
    assert summary["scorer_mode"] == mode
    assert summary["scorer_id"] == scorer_id
    assert summary["pressure_mode_echo"] == "off"
    assert summary["admission_mode"] == "off"
    assert summary["pibt_mode"] == "P0"
    assert summary["scorer_model_sha256"] == (
        FROZEN_MODEL_SHA256 if uses_frozen_model else ""
    )
    assert summary["completed_count"] == 1
    assert summary["failed_count"] == 0
    assert summary["runtime_full_astar_calls"] == 0
    assert summary["global_reservation_scan_count"] == 0
    assert summary["max_edges_selected_per_bag_per_decision"] == 1
    for key in (
        "events",
        "decisions",
        "decision_trace",
        "hold_attempts",
        "fault_events",
        "credit_events",
        "pibt_events",
    ):
        assert payload[key] == []
    assert summary["decision_trace_stored_count"] == 0
    assert summary["hold_trace_stored_count"] == 0


def test_s1_risk_abstention_preserves_raw_prediction_and_uses_exact_s0() -> None:
    binary = _backend_binary()
    payload = _run_real_map(
        scorer_mode="S1_frozen_g4e_legal_local_adapter",
        summary_only=False,
        binary=binary,
    )
    decisions = payload["decision_trace"]
    assert isinstance(decisions, list) and decisions
    first = decisions[0]
    assert first["current_node"] == 9
    assert first["goal_node"] == 50
    assert first["candidate_next_nodes"] == [7, 10]
    assert first["risk_gate_triggered"] is True
    assert first["metadata"]["scorer_risk_abstain"] is True
    assert first["metadata"]["scorer_raw_prediction"] == 10
    assert first["model_prediction"] == 7
    assert first["selected_next"] == 7
    assert first["scorer_raw_fallback_disagreement"] is True
    assert first["metadata"]["scorer_raw_fallback_disagreement"] is True
    assert first["decision_source"] == "scorer_risk_s0_fallback"
    assert first["rule_reason"].startswith(
        "frozen_scorer_risk_abstain_exact_s0_fallback;"
    )
    candidates = {row["next_node"]: row for row in first["candidate_records"]}
    assert set(candidates) == {7, 10}
    assert all("scorer_raw_score" in row for row in candidates.values())
    assert all("scorer_raw_bottleneck" in row for row in candidates.values())
    assert candidates[10]["scorer_raw_score"] > candidates[7]["scorer_raw_score"]
    assert candidates[7]["model_score"] < candidates[10]["model_score"]
    canonical = canonicalise_decision_row(first)
    assert canonical["scorer_raw_fallback_disagreement"] is True


@pytest.mark.parametrize(
    ("mode", "adapter_mode"),
    [
        ("S1_frozen_g4e_legal_local_adapter", "S1"),
        ("S2_frozen_g4e_without_absolute_node_ids", "S2"),
    ],
)
def test_live_frozen_scorer_raw_scores_match_audited_python_adapter(
    mode: str,
    adapter_mode: str,
) -> None:
    binary = _backend_binary()
    payload = _run_real_map(
        scorer_mode=mode,
        summary_only=False,
        binary=binary,
    )
    first = payload["decision_trace"][0]
    # The live trace deliberately contains additional pressure/credit audit
    # features.  Project only the frozen G4E feature contract; the scorer is
    # forbidden from consuming the additional fields.
    projected: dict[str, Any] = dict(first)
    projected_records = []
    for record in first["candidate_records"]:
        projected_record = dict(record)
        projected_record["features"] = {
            name: record["features"][name]
            for name in frozen_adapter.FROZEN_TRACE_FEATURE_NAMES
        }
        projected_records.append(projected_record)
    projected["candidate_records"] = projected_records

    context = frozen_adapter.load_map_context(ROOT)
    model = frozen_adapter.load_frozen_model(ROOT)
    expected = frozen_adapter.score_frozen_g4e(
        projected,
        context,
        model,
        adapter_mode,
    )
    assert first["metadata"]["scorer_raw_prediction"] == expected.prediction
    assert float(first["metadata"]["scorer_raw_margin"]) == pytest.approx(
        expected.margin,
        rel=1.0e-12,
        abs=1.0e-12,
    )
    for record, expected_score in zip(
        first["candidate_records"], expected.candidate_scores
    ):
        assert record["scorer_raw_score"] == pytest.approx(
            expected_score,
            rel=1.0e-12,
            abs=1.0e-12,
        )
    s0_prediction = frozen_adapter.score_rule(
        projected,
        context,
        "S3",
    ).prediction
    expected_effective = s0_prediction if expected.risk_abstain else expected.prediction
    assert first["model_prediction"] == expected_effective
    assert first["metadata"]["scorer_risk_abstain"] is expected.risk_abstain


def test_expected_binary_path_fails_closed_before_runtime_execution() -> None:
    binary = _backend_binary()
    loaded = cpp_backend.load_cpp_module(binary.parent)
    assert Path(str(loaded.__file__)).resolve() == binary
    wrong_binary = ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json"
    assert wrong_binary.is_file()
    with pytest.raises(
        cpp_backend.CppBackendUnavailable,
        match="does not match expected_binary_path",
    ):
        _run_real_map(
            scorer_mode="S0_current_handwritten",
            summary_only=True,
            binary=wrong_binary,
        )


def test_tampered_frozen_model_bytes_fail_closed(tmp_path: Path) -> None:
    binary = _backend_binary()
    source = ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json"
    tampered = tmp_path / source.name
    tampered.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="model SHA256 mismatch"):
        _run_real_map(
            scorer_mode="S1_frozen_g4e_legal_local_adapter",
            summary_only=True,
            binary=binary,
            scorer_model_path=tampered,
        )


def test_frozen_scorer_rejects_noncanonical_graph_fingerprint() -> None:
    binary = _backend_binary()
    nodes, edges, heuristic = canonical_graph_records()
    modified_edges = list(edges)
    start, end, length, speed = modified_edges[0]
    modified_edges[0] = (start, end, length + 1.0e-6, speed)
    with pytest.raises(ValueError, match="canonical map2 runtime graph identity"):
        cpp_backend.g4irsf11_event_runtime_from_records(
            node_records=nodes,
            edge_records=modified_edges,
            heuristic_time=heuristic,
            bag_records=[("fingerprint-rejection", 1, 0.0, 100.0, 9, 50, "audit")],
            scorer_mode="S1_frozen_g4e_legal_local_adapter",
            framework_mode="event_loop_one_step",
            pressure_mode="off",
            admission_mode="off",
            enable_backpressure=False,
            enable_source_admission=False,
            expected_binary_path=binary,
            search_path=binary.parent,
            summary_only=True,
        )

from __future__ import annotations

from collections import Counter
import io
import json
from pathlib import Path

import pytest

from czr005.g4irsf16.model import DEPLOYMENT_FEATURES, SelectiveEnsembleModel
from scripts.eval import g4irsf16_full_shadow as shadow


def _model(
    kind: str,
    action: str,
    *,
    benefit_intercept: float = 10.0,
    harmful_intercept: float = -10.0,
    utility_intercept: float = 1.0,
    bound: float = 1_000_000.0,
) -> SelectiveEnsembleModel:
    width = len(DEPLOYMENT_FEATURES)
    return SelectiveEnsembleModel(
        kind=kind,
        action=action,
        feature_names=DEPLOYMENT_FEATURES,
        means=(0.0,) * width,
        scales=(1.0,) * width,
        feature_min=(-bound,) * width,
        feature_max=(bound,) * width,
        benefit_weights=((benefit_intercept, *((0.0,) * width)),),
        harmful_weights=((harmful_intercept, *((0.0,) * width)),),
        utility_weights=((utility_intercept, *((0.0,) * width)),),
        benefit_probability_lcb_threshold=0.5,
        harmful_probability_ucb_budget=0.5,
        utility_lcb_margin_seconds=0.0,
        artifact_sha256=f"sha-{kind}",
    )


def _models(
    *,
    i4: SelectiveEnsembleModel | None = None,
    i3: SelectiveEnsembleModel | None = None,
    i3_authorized: bool = False,
) -> shadow.LoadedModels:
    i4_model = i4 or _model("I4", shadow.I4_ACTION)
    return shadow.LoadedModels(
        i4=i4_model,
        i4_path=Path("i4.json"),
        i3=i3,
        i3_path=(None if i3 is None else Path("i3.json")),
        i3_authorized=i3_authorized,
        i3_status=(
            "I3_RARE_OVERRIDE_MODEL_AUTHORIZED"
            if i3_authorized
            else shadow.I3_NOT_AUTHORIZED
        ),
    )


@pytest.fixture(scope="module")
def static_context() -> shadow.StaticContext:
    return shadow.StaticContext.load(144)


def _candidate(next_node: int, travel_time: float) -> dict[str, object]:
    return {
        "next_node": next_node,
        "features": {
            "target_queue_length": 2,
            "target_scheduled_incoming": 1,
            "target_next_available": 8_280.0,
            "travel_time": travel_time,
            "advertised_fault": False,
        },
        "scorer_raw_score": 3.0 - next_node / 100.0,
        "shield_allowed": True,
        "shield_reason": "allowed",
    }


def _trace_row(static_context: shadow.StaticContext) -> dict[str, object]:
    task = static_context.tasks[0]
    event_time = float(task["pass_time"]) + 10.0
    baseline = _candidate(24, static_context.edge_time(22, 24))
    intervention = _candidate(26, static_context.edge_time(22, 26))
    baseline["features"]["target_next_available"] = (  # type: ignore[index]
        event_time + static_context.edge_time(22, 24) + 3.0
    )
    intervention["features"]["target_next_available"] = (  # type: ignore[index]
        event_time + static_context.edge_time(22, 26) + 5.0
    )
    return {
        "task_id": int(task["task_id"]),
        "segment_id": str(task["segment_id"]),
        "event_time": event_time,
        "current_node": 22,
        "goal_node": int(task["goal"]),
        "candidate_records": [baseline, intervention],
        "model_prediction": 24,
        "selected_next": 24,
        "model_margin": 2.0,
        "decision_source": "S1_frozen_g4e_legal_local_adapter",
        "local_snapshot": {
            "junction_queue_length": 3,
            "downstream_pressure": 4,
            "next_available_time": event_time + 2.0,
        },
        "short_history": [3, 22, 3],
        "metadata": {
            "runtime_bag_id": 0,
            "decision_ordinal": 7,
            "trace_kind": "committed_edge_action",
        },
    }


def test_exact_feature_projection_preserves_i3_i4_action_semantics(
    static_context: shadow.StaticContext,
) -> None:
    row = _trace_row(static_context)
    task = static_context.tasks[0]
    candidates = shadow._candidate_index(row)  # noqa: SLF001
    i3 = shadow._feature_mapping(  # noqa: SLF001
        trace_row=row,
        task=task,
        context=static_context,
        baseline=candidates[24],
        intervention=candidates[26],
        kind="I3",
        alternative_count=1,
        legal_count=2,
    )
    i4 = shadow._feature_mapping(  # noqa: SLF001
        trace_row=row,
        task=task,
        context=static_context,
        baseline=candidates[24],
        intervention=candidates[24],
        kind="I4",
        alternative_count=1,
        legal_count=2,
    )

    assert tuple(i3) == DEPLOYMENT_FEATURES
    assert tuple(i4) == DEPLOYMENT_FEATURES
    assert i3["baseline_release"] == 0.0
    assert i3["intervention_edge_travel_seconds"] == static_context.edge_time(22, 26)
    assert i4["baseline_release"] == 1.0
    assert i4["intervention_edge_travel_seconds"] == 0.0
    assert i4["static_remaining_intervention_seconds"] == i4["static_remaining_current_seconds"]
    assert i3["wait_age_seconds"] == pytest.approx(10.0)
    assert i3["target_next_available_wait_seconds"] == pytest.approx(5.0)
    assert i4["target_next_available_wait_seconds"] == pytest.approx(3.0)
    assert i3["short_history_repeat_count"] == 1.0


def test_model_input_contract_is_measured_from_the_actual_feature_object() -> None:
    exact = {name: 0.0 for name in DEPLOYMENT_FEATURES}
    leaked = {**exact, "task_id": 17.0}
    boolean_drift = {**exact, DEPLOYMENT_FEATURES[0]: True}

    assert shadow._feature_contract_violation(exact) is False  # noqa: SLF001
    assert shadow._feature_contract_violation(leaked) is True  # noqa: SLF001
    assert shadow._feature_contract_violation(boolean_drift) is True  # noqa: SLF001


def test_i4_scores_while_unavailable_i3_is_never_promoted(
    static_context: shadow.StaticContext,
) -> None:
    prediction = shadow.evaluate_trace_row(
        _trace_row(static_context),
        context=static_context,
        models=_models(),
    )

    assert prediction["f2"]["selected_next_before_shadow"] == 24
    assert prediction["f2"]["selected_next_after_shadow"] == 24
    assert prediction["f2"]["action_unchanged"] is True
    assert prediction["i4"]["proposal"] is True
    assert prediction["i4"]["causal_action_counts"] == {
        "baseline_release": 1,
        "alternative_action_count": 1,
        "total_legal_action_count": 2,
    }
    assert prediction["i3"]["opportunity"] is True
    assert prediction["i3"]["model_eligible"] is False
    assert prediction["i3"]["status"] == shadow.I3_NOT_AUTHORIZED
    assert prediction["i3"]["candidate_scores"] == []
    assert prediction["i3"]["proposal"] is False
    assert prediction["combined_shadow_proposal"]["state"] == "I4_SELECTIVE_HOLD"
    assert prediction["illegal_proposal"] is False


def test_i4_action_domain_includes_native_hold_attempt_via_tentative_release(
    static_context: shadow.StaticContext,
) -> None:
    row = _trace_row(static_context)
    row["selected_next"] = None
    row["decision_source"] = "destination_merge_grant_hold"
    row["metadata"]["trace_kind"] = "hold_attempt"  # type: ignore[index]

    prediction = shadow.evaluate_trace_row(
        row,
        context=static_context,
        models=_models(),
    )

    assert prediction["trace_kind"] == "hold_attempt"
    assert prediction["f2"]["selected_next_before_shadow"] is None
    assert prediction["f2"]["selected_next_after_shadow"] is None
    assert prediction["f2"]["tentative_release_next"] == 24
    assert prediction["i4"]["model_eligible"] is True
    assert prediction["i4"]["tentative_f2_release"] is True
    assert prediction["i4"]["causal_action_counts"] == {
        "baseline_release": 1,
        "alternative_action_count": 1,
        "total_legal_action_count": 2,
    }
    assert prediction["i4"]["score"] is not None


def test_i4_action_counts_are_release_vs_hold_not_outgoing_edge_count(
    static_context: shadow.StaticContext,
) -> None:
    row = _trace_row(static_context)
    row["candidate_records"] = [row["candidate_records"][0]]  # type: ignore[index]

    prediction = shadow.evaluate_trace_row(
        row,
        context=static_context,
        models=_models(),
    )

    assert prediction["legal_next_nodes"] == [24]
    assert prediction["i4"]["model_eligible"] is True
    assert prediction["i4"]["causal_action_counts"]["alternative_action_count"] == 1
    assert prediction["i4"]["causal_action_counts"]["total_legal_action_count"] == 2


def test_outside_i4_domain_does_not_call_model_or_create_model_abstention(
    static_context: shadow.StaticContext,
) -> None:
    row = _trace_row(static_context)
    row["selected_next"] = None
    row["model_prediction"] = None
    row["decision_source"] = "destination_merge_grant_hold"
    row["metadata"]["trace_kind"] = "hold_attempt"  # type: ignore[index]
    models = _models()

    prediction = shadow.evaluate_trace_row(
        row,
        context=static_context,
        models=models,
    )
    accumulator = shadow.ShadowAccumulator(models)
    accumulator.observe(prediction)
    summary = accumulator.summary()["by_kind"]["I4"]

    assert prediction["i4"]["model_eligible"] is False
    assert prediction["i4"]["score"] is None
    assert prediction["i4"]["reason"] == shadow.OUTSIDE_I4_DOMAIN
    assert summary["outside_causal_action_domain_states"] == 1
    assert summary["abstention_count"] == 0
    assert summary["ood_states"] == 0
    assert summary["causal_action_domain_exclusion_reasons"] == {
        shadow.OUTSIDE_I4_DOMAIN: 1
    }


def test_authorized_i3_selects_only_a_legal_alternative_when_i4_abstains(
    static_context: shadow.StaticContext,
) -> None:
    i4 = _model("I4", shadow.I4_ACTION, benefit_intercept=-10.0)
    i3 = _model("I3", "MOVE_ONE_EDGE")
    prediction = shadow.evaluate_trace_row(
        _trace_row(static_context),
        context=static_context,
        models=_models(i4=i4, i3=i3, i3_authorized=True),
    )

    assert prediction["i4"]["proposal"] is False
    assert prediction["i4"]["score"]["abstention_reason"] == "BENEFIT_CONFIDENCE_ABSTAIN"
    assert prediction["i3"]["proposal"] is True
    assert prediction["i3"]["proposal_next_node"] == 26
    assert prediction["i3"]["proposal_next_node"] in prediction["i3"]["legal_alternatives"]
    assert prediction["combined_shadow_proposal"] == {
        "state": "I3_RARE_OVERRIDE",
        "action": "MOVE_ONE_EDGE",
        "next_node": 26,
    }
    assert prediction["f2"]["selected_next_after_shadow"] == 24
    assert prediction["illegal_proposal"] is False


def test_ood_fails_closed_and_is_counted(
    static_context: shadow.StaticContext,
) -> None:
    i4 = _model("I4", shadow.I4_ACTION, bound=0.0)
    models = _models(i4=i4)
    prediction = shadow.evaluate_trace_row(
        _trace_row(static_context), context=static_context, models=models
    )
    accumulator = shadow.ShadowAccumulator(models)
    accumulator.observe(prediction)
    summary = accumulator.summary()

    assert prediction["i4"]["score"]["ood"] is True
    assert prediction["i4"]["score"]["abstention_reason"] == "OOD_ABSTAIN"
    assert prediction["i4"]["proposal"] is False
    assert summary["by_kind"]["I4"]["ood_states"] == 1
    assert summary["by_kind"]["I4"]["activation_proposals"] == 0
    assert summary["by_kind"]["I3"]["not_authorized_states"] == 1
    assert summary["by_kind"]["I3"]["activation_proposals"] == 0
    assert summary["f2_action_mutation_count"] == 0
    assert summary["illegal_proposal_count"] == 0


def _artifact(kind: str, action: str) -> dict[str, object]:
    from czr005.g4irsf16.model import MODEL_SCHEMA, with_self_sha256

    width = len(DEPLOYMENT_FEATURES)
    return with_self_sha256(
        {
            "schema": MODEL_SCHEMA,
            "kind": kind,
            "action": action,
            "feature_names": list(DEPLOYMENT_FEATURES),
            "normalization": {"mean": [0.0] * width, "scale": [1.0] * width},
            "training_bounds": {"min": [-1e6] * width, "max": [1e6] * width},
            "heads": {
                "benefit_logit": [[10.0, *([0.0] * width)]],
                "harmful_logit": [[-10.0, *([0.0] * width)]],
                "risk_adjusted_utility_seconds": [[1.0, *([0.0] * width)]],
            },
            "thresholds": {
                "benefit_probability_lcb": 0.5,
                "harmful_probability_ucb": 0.5,
                "utility_lcb_margin_seconds": 0.0,
            },
        }
    )


def test_i3_risk_veto_artifact_loads_as_diagnostic_not_action_authority(
    tmp_path: Path,
) -> None:
    i4_path = tmp_path / "i4.json"
    i3_path = tmp_path / "i3.json"
    i4_path.write_text(
        json.dumps(_artifact("I4", shadow.I4_ACTION)), encoding="utf-8"
    )
    i3_path.write_text(
        json.dumps(
            _artifact(
                shadow.I3_DIAGNOSTIC_KIND,
                "ALLOW_PREREGISTERED_ALTERNATIVE_IF_RISK_PASS",
            )
        ),
        encoding="utf-8",
    )

    models = shadow.load_models(i4_path, i3_path)

    assert models.i3 is not None
    assert models.i3.kind == shadow.I3_DIAGNOSTIC_KIND
    assert models.i3_authorized is False
    assert models.i3_status == shadow.I3_NOT_AUTHORIZED


def test_offline_gate_keeps_i4_no_go_i3_unauthorized_and_audit_sealed() -> None:
    gate = shadow._offline_authorization(shadow.ROOT)  # noqa: SLF001

    assert gate["path"] == "artifacts/gates/g4irsf16_offline_model_gate.json"
    assert gate["overall_status"] == "CAUSAL_LEARNING_MODEL_NO_GO"
    assert gate["i4_status"] == "I4_SELECTIVE_MODEL_NO_GO"
    assert gate["i3_status"] == shadow.I3_NOT_AUTHORIZED
    assert gate["final_audit_status"] == "SEALED_NOT_CONSUMED"
    assert gate["aggregate_gate_metadata_is_model_input"] is False


def test_repo_internal_evidence_paths_are_root_relative_posix() -> None:
    artifact = shadow.ROOT / "artifacts" / "models" / "i4.json"
    output = shadow.ROOT / "outputs" / "reports" / "shadow.json"

    assert shadow._portable_path(artifact, root=shadow.ROOT) == (  # noqa: SLF001
        "artifacts/models/i4.json"
    )
    assert shadow._portable_path(output, root=shadow.ROOT) == (  # noqa: SLF001
        "outputs/reports/shadow.json"
    )


def test_model_summary_uses_portable_repo_paths() -> None:
    models = shadow.LoadedModels(
        i4=_model("I4", shadow.I4_ACTION),
        i4_path=shadow.ROOT / "artifacts/models/i4.json",
        i3=_model("I3", "MOVE_ONE_EDGE"),
        i3_path=shadow.ROOT / "artifacts/models/i3.json",
        i3_authorized=True,
        i3_status="I3_RARE_OVERRIDE_MODEL_AUTHORIZED",
    )

    summary = shadow._model_summary(models, root=shadow.ROOT)  # noqa: SLF001

    assert summary["I4"]["path"] == "artifacts/models/i4.json"
    assert summary["I3"]["path"] == "artifacts/models/i3.json"


def test_formal_i4_runtime_support_spans_commits_and_native_holds() -> None:
    zstandard = pytest.importorskip("zstandard")
    path = (
        shadow.ROOT
        / "outputs/runtime/g4irsf16/"
        "g4irsf16_f2_off_e4_m0_43603_shards4.matched_features.jsonl.zst"
    )
    trace_kinds: Counter[str] = Counter()
    candidate_counts: Counter[int] = Counter()
    with path.open("rb") as raw:
        with zstandard.ZstdDecompressor().stream_reader(raw) as stream:
            with io.TextIOWrapper(stream, encoding="utf-8") as text:
                for line in text:
                    row = json.loads(line)
                    if row["target"]["kind"] != "I4":
                        continue
                    trace_kinds[row["runtime_match"]["trace_kind"]] += 1
                    candidate_counts[len(row["features"]["candidates"])] += 1

    assert trace_kinds == Counter(
        {"committed_edge_action": 699, "hold_attempt": 387}
    )
    # The formal action count is release+hold; it is intentionally unrelated
    # to whether map2 exposes one or two local outgoing edge candidates.
    assert candidate_counts == Counter({1: 629, 2: 457})


def test_full_original_shadow_needs_explicit_authorization() -> None:
    with pytest.raises(shadow.FullShadowError, match="--allow-full"):
        shadow.run_full_shadow(
            binary=Path("missing.pyd"),
            i4_model=Path("missing.json"),
            segments=shadow.native_trace.FULL_SEGMENTS,
            trace_shards=4,
            allow_full=False,
        )

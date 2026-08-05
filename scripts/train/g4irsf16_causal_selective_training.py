"""Train and gate the small G4IRSF16 causal-selective models.

The script is intentionally a single deterministic evidence pass: train fits
weights, calibration chooses thresholds, validation decides promotion, and the
sealed final-audit partition is not consumed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from czr005.g4irsf16.model import (  # noqa: E402
    DEPLOYMENT_FEATURES,
    SelectiveEnsembleModel,
    expected_calibration_error,
    with_self_sha256,
)
from czr005.g4irsf16.offline import (  # noqa: E402
    I3_GATE,
    I4_GATE,
    RISK_BUDGETS,
    activation_summary,
    authorization,
    choose_rule,
    deployment_matrix,
    evaluate_rules,
    gate_i4,
    i3_rules,
    i4_rules,
    observed_utility,
    oracle_rows,
    selectable_rows,
)
from czr005.g4irsf16.training import (  # noqa: E402
    build_model_artifact,
    choose_selective_thresholds,
    fit_linear_ensemble,
    score_linear_heads,
)


I3_DATASET = Path("artifacts/datasets/g4irsf16_i3_route_dataset.parquet")
I4_DATASET = Path("artifacts/datasets/g4irsf16_i4_hold_dataset.parquet")
HSYSTEM_DATASET = Path("artifacts/datasets/g4irsf16_hsystem_externality_dataset.parquet")


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--ensemble-size", type=int, default=16)
    return parser.parse_args()


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return [dict(row) for row in pq.read_table(path).to_pylist()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"EMPTY_OUTPUT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_md(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _json_safe(value: Any) -> Any:
    """Replace diagnostic non-finite sentinels before canonical JSON export."""

    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _labels(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    beneficial = np.asarray([row["signed_class"] == "BENEFICIAL" for row in rows], dtype=int)
    harmful = np.asarray([row["signed_class"] == "HARMFUL" for row in rows], dtype=int)
    utility = np.asarray([observed_utility(row) for row in rows], dtype=float)
    return beneficial, harmful, utility


def _groups(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(row["component_id"]) for row in rows]


def _features(row: Mapping[str, Any]) -> OrderedDict[str, float]:
    projected: OrderedDict[str, float] = OrderedDict()
    for name in DEPLOYMENT_FEATURES:
        value = row.get(name)
        if value is None:
            raise ValueError(f"RUNTIME_FEATURE_CACHE_INCOMPLETE:{row.get('target_key')}:{name}")
        projected[name] = float(value)
    return projected


def _model_predictions(
    model: SelectiveEnsembleModel,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    activations: list[bool] = []
    for row in rows:
        score = model.score(_features(row))
        activations.append(score.activation)
        predictions.append(
            {
                "descriptor_id": row["descriptor_id"],
                "target_key": row["target_key"],
                "split": row["split"],
                "signed_class": row["signed_class"],
                "direct_benefit_seconds": row["direct_benefit_seconds"],
                "observed_utility_seconds": observed_utility(row),
                "activation": score.activation,
                "abstention_reason": score.abstention_reason,
                "benefit_probability_mean": score.benefit_probability_mean,
                "benefit_probability_lcb": score.benefit_probability_lcb,
                "harmful_probability_mean": score.harmful_probability_mean,
                "harmful_probability_ucb": score.harmful_probability_ucb,
                "utility_mean_seconds": score.utility_mean_seconds,
                "utility_lcb_seconds": score.utility_lcb_seconds,
                "ood": score.ood,
            }
        )
    return predictions, activation_summary(rows, activations)


def _calibration_rows(
    rows: Sequence[Mapping[str, Any]],
    diagnostics: Mapping[str, np.ndarray],
    activations: Sequence[bool],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, (row, activation) in enumerate(zip(rows, activations, strict=True)):
        output.append(
            {
                "schema": "czr005.g4irsf16.calibration.v1",
                "descriptor_id": row["descriptor_id"],
                "split": row["split"],
                "signed_class": row["signed_class"],
                "beneficial_label": int(row["signed_class"] == "BENEFICIAL"),
                "harmful_label": int(row["signed_class"] == "HARMFUL"),
                "benefit_probability_mean": float(diagnostics["benefit_probability_mean"][index]),
                "benefit_probability_lcb": float(diagnostics["benefit_probability_lcb"][index]),
                "harmful_probability_mean": float(diagnostics["harmful_probability_mean"][index]),
                "harmful_probability_ucb": float(diagnostics["harmful_probability_ucb"][index]),
                "utility_mean_seconds": float(diagnostics["utility_mean_seconds"][index]),
                "utility_lcb_seconds": float(diagnostics["utility_lcb_seconds"][index]),
                "activation": bool(activation),
            }
        )
    return output


def _train_selective(
    rows: Sequence[Mapping[str, Any]],
    *,
    kind: str,
    action: str,
    maximum_harmful_activation_rate: float,
    ensemble_size: int,
) -> tuple[dict[str, Any], SelectiveEnsembleModel, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    train = selectable_rows(rows, "train")
    calibration = selectable_rows(rows, "calibration")
    validation = selectable_rows(rows, "validation")
    train_y_good, train_y_bad, train_utility = _labels(train)
    cal_y_good, cal_y_bad, cal_utility = _labels(calibration)
    prepared, heads = fit_linear_ensemble(
        deployment_matrix(train),
        train_y_good,
        train_y_bad,
        train_utility,
        _groups(train),
        x_calibration_raw=deployment_matrix(calibration),
        beneficial_calibration=cal_y_good,
        harmful_calibration=cal_y_bad,
        ensemble_size=ensemble_size,
        seed=16,
    )
    cal_diagnostics = score_linear_heads(prepared, heads, deployment_matrix(calibration))
    thresholds, threshold_metrics = choose_selective_thresholds(
        cal_diagnostics,
        [str(row["signed_class"]) for row in calibration],
        cal_utility,
        minimum_coverage=I4_GATE["activation_coverage_min"] if kind == "I4" else 0.0,
        maximum_coverage=I4_GATE["activation_coverage_max"],
        maximum_harmful_activation_rate=maximum_harmful_activation_rate,
    )
    artifact = build_model_artifact(
        kind=kind,
        action=action,
        prepared=prepared,
        heads=heads,
        thresholds=thresholds,
        training_metadata={
            "schema": "czr005.g4irsf16.training_metadata.v1",
            "fit_split": "train",
            "threshold_split": "calibration",
            "promotion_split": "validation",
            "final_audit_consumed": False,
            "train_row_count": len(train),
            "calibration_row_count": len(calibration),
            "validation_row_count": len(validation),
            "cluster_bootstrap_ensemble_size": ensemble_size,
            "threshold_selection_metrics": _json_safe(threshold_metrics),
        },
    )
    model = SelectiveEnsembleModel.from_artifact(artifact)
    cal_predictions, cal_summary = _model_predictions(model, calibration)
    validation_predictions, validation_summary = _model_predictions(model, validation)
    validation_diagnostics = score_linear_heads(prepared, heads, deployment_matrix(validation))
    beneficial_validation = [int(row["signed_class"] == "BENEFICIAL") for row in validation]
    benefit_ece = expected_calibration_error(
        validation_diagnostics["benefit_probability_mean"].tolist(),
        beneficial_validation,
        bin_count=10,
    )
    evidence = {
        "calibration": cal_summary,
        "validation": validation_summary,
        "validation_benefit_ece": benefit_ece,
        "validation_ood_count": sum(bool(row["ood"]) for row in validation_predictions),
    }
    cal_activations = [bool(row["activation"]) for row in cal_predictions]
    calibration_table = _calibration_rows(calibration, cal_diagnostics, cal_activations)
    return artifact, model, evidence, calibration_table, validation_predictions


def _externality_table(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    # Tail outcomes in final_audit remain sealed; only selectable partitions
    # may publish realized externality statistics.
    for split in ("train", "calibration", "validation"):
        part = [row for row in rows if row["split"] == split]
        for kind in ("I3", "I4", "ALL"):
            selected = part if kind == "ALL" else [row for row in part if row["kind"] == kind]
            if not selected:
                continue
            nonempty = sum(bool(row["externality_nonempty"]) for row in selected)
            cvar = [float(row["other_bag_cvar95_harm_seconds"]) for row in selected]
            output.append(
                {
                    "schema": "czr005.g4irsf16.externality_risk.v1",
                    "split": split,
                    "kind": kind,
                    "row_count": len(selected),
                    "externality_nonempty_count": nonempty,
                    "externality_nonempty_rate": nonempty / len(selected),
                    "affected_count_mean": float(np.mean([row["external_affected_count"] for row in selected])),
                    "affected_count_max": max(row["external_affected_count"] for row in selected),
                    "other_bag_max_harm_max_seconds": max(float(row["other_bag_max_harm_seconds"]) for row in selected),
                    "other_bag_cvar95_mean_seconds": float(np.mean(cvar)),
                    "other_bag_cvar95_max_seconds": max(cvar),
                    "extra_deadline_miss_count": sum(int(row["extra_deadline_miss_count"]) for row in selected),
                    "selection_allowed": split != "final_audit",
                }
            )
    return output


def _train_externality(
    rows: Sequence[Mapping[str, Any]],
    *,
    ensemble_size: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    train = selectable_rows(rows, "train")
    calibration = selectable_rows(rows, "calibration")
    validation = selectable_rows(rows, "validation")
    train_good = np.asarray([observed_utility(row) > 0.0 for row in train], dtype=int)
    train_bad = np.asarray([bool(row["externality_nonempty"]) for row in train], dtype=int)
    cal_good = np.asarray([observed_utility(row) > 0.0 for row in calibration], dtype=int)
    cal_bad = np.asarray([bool(row["externality_nonempty"]) for row in calibration], dtype=int)
    train_utility = np.asarray([observed_utility(row) for row in train], dtype=float)
    prepared, heads = fit_linear_ensemble(
        deployment_matrix(train),
        train_good,
        train_bad,
        train_utility,
        _groups(train),
        x_calibration_raw=deployment_matrix(calibration),
        beneficial_calibration=cal_good,
        harmful_calibration=cal_bad,
        ensemble_size=ensemble_size,
        seed=1606,
    )
    diagnostics = score_linear_heads(prepared, heads, deployment_matrix(validation))
    b1 = RISK_BUDGETS["B1_balanced"]
    thresholds = {
        "benefit_probability_lcb": 0.50,
        "harmful_probability_ucb": float(b1["externality_probability_ucb"]),
        "utility_lcb_margin_seconds": 0.0,
    }
    artifact = build_model_artifact(
        kind="H_SYSTEM_EXTERNALITY",
        action="PASS_BALANCED_EXTERNALITY_BUDGET",
        prepared=prepared,
        heads=heads,
        thresholds=thresholds,
        training_metadata={
            "fit_split": "train",
            "calibration_split": "calibration",
            "evaluation_split": "validation",
            "final_audit_consumed": False,
            "risk_budgets": RISK_BUDGETS,
            "b1_tail_budget_status": "NOT_EVALUATED_NO_CVAR_UCB_HEAD",
            "promotion_authorized": False,
            "deadline_miss_head_status": "NOT_TRAINABLE_DEGENERATE_ZERO_LABEL",
        },
    )
    model = SelectiveEnsembleModel.from_artifact(artifact)
    predictions, metrics = _model_predictions(model, validation)
    externality_ece = expected_calibration_error(
        diagnostics["harmful_probability_mean"].tolist(),
        [int(bool(row["externality_nonempty"])) for row in validation],
        bin_count=10,
    )
    return artifact, {
        "validation": metrics,
        "externality_nonempty_ece": externality_ece,
        "risk_budgets": RISK_BUDGETS,
        "status": "DIAGNOSTIC_SMALL_HEAD_NOT_INDEPENDENTLY_PROMOTED",
        "b1_tail_budget_status": "NOT_EVALUATED_NO_CVAR_UCB_HEAD",
        "promotion_authorized": False,
        "final_audit": "SEALED_NOT_CONSUMED",
    }, predictions


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    first = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(value) for value in row) + " |" for row in rows]
    return "\n".join([first, divider, *body])


def main() -> int:
    args = _args()
    root = args.root.resolve()
    i3 = _read_rows(root / I3_DATASET)
    i4 = _read_rows(root / I4_DATASET)
    hsystem = _read_rows(root / HSYSTEM_DATASET)
    if len(i3) != 1086 or len(i4) != 1086 or len(hsystem) != 256:
        raise ValueError("FORMAL_DATASET_SIZE_MISMATCH")
    if any(not bool(row["runtime_dynamic_feature_complete"]) for row in [*i3, *i4]):
        raise ValueError("FULL_MATCHED_RUNTIME_FEATURE_CACHE_REQUIRED")

    auth = authorization(i3, i4)
    _write_json(root / "artifacts/gates/g4irsf16_learning_task_authorization.json", auth)

    oracle = [*oracle_rows(i3, kind="I3"), *oracle_rows(i4, kind="I4")]
    _write_csv(root / "outputs/tables/g4irsf16_oracle_coverage.csv", oracle)
    externality = _externality_table(hsystem)
    _write_csv(root / "outputs/tables/g4irsf16_externality_risk.csv", externality)

    i3_rule_defs = i3_rules(selectable_rows(i3, "train"))
    i4_rule_defs = i4_rules(selectable_rows(i4, "train"))
    i3_rule_rows = evaluate_rules(i3, i3_rule_defs, kind="I3")
    i4_rule_rows = evaluate_rules(i4, i4_rule_defs, kind="I4")
    _write_csv(root / "outputs/tables/g4irsf16_i3_rule_ab.csv", i3_rule_rows)
    _write_csv(root / "outputs/tables/g4irsf16_i4_rule_ab.csv", i4_rule_rows)
    evaluated_i3_rule, i3_rule_pass = choose_rule(i3_rule_rows, kind="I3")
    evaluated_i4_rule, i4_rule_pass = choose_rule(i4_rule_rows, kind="I4")
    formal_i3_rule = evaluated_i3_rule if i3_rule_pass else "R0"
    formal_i4_rule = evaluated_i4_rule if i4_rule_pass else "H0"
    i4_rule_definition = next(rule for rule in i4_rule_defs if rule.name == evaluated_i4_rule)
    rule_bundle = with_self_sha256(
        {
            "schema": "czr005.g4irsf16.rule_bundle.v1",
            "default_action": "F2_EXACT",
            "i3": {
                "selected_rule": formal_i3_rule,
                "evaluated_candidate": evaluated_i3_rule,
                "promotion_authorized": i3_rule_pass,
            },
            "i4": {
                "selected_rule": formal_i4_rule,
                "evaluated_candidate": evaluated_i4_rule,
                "promotion_authorized": i4_rule_pass,
                "diagnostic_canary": (
                    {
                        "rule": evaluated_i4_rule,
                        "parameters": dict(i4_rule_definition.parameters),
                        "authorization": "8192_DIAGNOSTIC_ONLY_NOT_PROMOTED",
                    }
                    if not i4_rule_pass and evaluated_i4_rule != "H0"
                    else None
                ),
            },
            "parameters_from": "train",
            "selection_from": "calibration",
            "promotion_from": "validation",
            "final_audit_consumed": False,
            "runtime_constraints": {
                "i4_action": "HOLD_ONE_NATURAL_SERVICE_OPPORTUNITY",
                "i3_action": "AT_MOST_ONE_LEGAL_NEXT_EDGE_OVERRIDE_PER_SEGMENT",
                "fallback": "F2_EXACT",
            },
        }
    )
    _write_json(root / "artifacts/policies/g4irsf16_best_rule_bundle.json", rule_bundle)

    i4_artifact, _, i4_evidence, i4_calibration, i4_validation_predictions = _train_selective(
        i4,
        kind="I4",
        action="HOLD_ONE_NATURAL_SERVICE_OPPORTUNITY",
        maximum_harmful_activation_rate=I4_GATE["harmful_activation_rate_max"],
        ensemble_size=args.ensemble_size,
    )
    i4_artifact["training_metadata"]["support_authorization_status"] = auth[
        "i4_selective_hold"
    ]["status"]
    i4_artifact["training_metadata"]["deployment_status"] = (
        "VALIDATION_GATE_REQUIRED"
        if auth["i4_selective_hold"]["status"]
        == "AUTHORIZED_FOR_OFFLINE_TRAINING"
        else "SUPPORT_DIAGNOSTIC_ONLY_NOT_AUTHORIZED"
    )
    i4_artifact = with_self_sha256(i4_artifact)
    i4_model_path = root / "artifacts/models/g4irsf16_i4_d0_calibrated_logistic.json"
    _write_json(i4_model_path, i4_artifact)
    _write_csv(root / "outputs/tables/g4irsf16_i4_calibration.csv", i4_calibration)
    i4_gate = gate_i4(i4_evidence["validation"], ece=i4_evidence["validation_benefit_ece"])
    i4_gate["training_authorization_status"] = auth["i4_selective_hold"]["status"]
    i4_gate["deployment_authorized"] = (
        auth["i4_selective_hold"]["status"]
        == "AUTHORIZED_FOR_OFFLINE_TRAINING"
        and i4_gate["status"] == "PASS_I4_OFFLINE_GATE"
    )
    i4_ab = [
        {"schema": "czr005.g4irsf16.i4_offline_ab.v1", "candidate": "D0_calibrated_logistic", "split": split, **i4_evidence[split]}
        for split in ("calibration", "validation")
    ]
    _write_csv(root / "outputs/tables/g4irsf16_i4_offline_ab.csv", i4_ab)

    i3_artifact, _, i3_evidence, _, _ = _train_selective(
        i3,
        kind="I3_RISK_VETO_DIAGNOSTIC",
        action="ALLOW_PREREGISTERED_ALTERNATIVE_IF_RISK_PASS",
        maximum_harmful_activation_rate=I3_GATE["harmful_activation_rate_max"],
        ensemble_size=args.ensemble_size,
    )
    i3_artifact["training_metadata"]["rare_override_authorized"] = False
    i3_artifact["training_metadata"]["deployment_status"] = "RISK_VETO_ONLY_DIAGNOSTIC"
    i3_artifact = with_self_sha256(i3_artifact)
    _write_json(root / "artifacts/models/g4irsf16_i3_risk_veto.json", i3_artifact)
    i3_ab = [
        {"schema": "czr005.g4irsf16.i3_offline_ab.v1", "candidate": "risk_veto_linear", "split": split, **i3_evidence[split]}
        for split in ("calibration", "validation")
    ]
    _write_csv(root / "outputs/tables/g4irsf16_i3_offline_ab.csv", i3_ab)

    externality_artifact, externality_evidence, _ = _train_externality(
        hsystem,
        ensemble_size=args.ensemble_size,
    )
    _write_json(root / "artifacts/models/g4irsf16_externality_risk_balanced.json", externality_artifact)
    _write_csv(
        root / "outputs/tables/g4irsf16_externality_calibration.csv",
        [
            {
                "schema": "czr005.g4irsf16.externality_calibration.v1",
                "split": "validation",
                "status": externality_evidence["status"],
                "externality_nonempty_ece": externality_evidence["externality_nonempty_ece"],
                **externality_evidence["validation"],
            }
        ],
    )

    model_gate = {
        "schema": "czr005.g4irsf16.offline_model_gate.v1",
        "i4": i4_gate,
        "i3_rare_override": auth["i3_rare_override"],
        "i3_risk_veto": {
            "status": "TRAINED_DIAGNOSTIC_NOT_AN_OVERRIDE_AUTHORIZATION",
            "validation": i3_evidence["validation"],
        },
        "externality": externality_evidence,
        "final_audit": auth["final_audit"],
        "overall_status": (
            "PASS_OFFLINE_MODEL_GATE"
            if i4_gate["deployment_authorized"]
            else "CAUSAL_LEARNING_MODEL_NO_GO"
        ),
    }
    _write_json(root / "artifacts/gates/g4irsf16_offline_model_gate.json", model_gate)

    _write_md(
        root / "outputs/reports/g4irsf16_learnability_and_oracle_report.md",
        [
            "# G4IRSF16 learnability and oracle report",
            "",
            "## Decision",
            "",
            f"- I3 rare override: `{auth['i3_rare_override']['status']}`; risk-veto-only remains trainable.",
            f"- I4 support authorization: `{auth['i4_selective_hold']['status']}`. D0 is retained only as a strict support/validation diagnostic and has no deployment authority.",
            "- Final audit remains `SEALED_NOT_CONSUMED`; its label support did not enter authorization, fitting, threshold selection, rule selection, or promotion.",
            "",
            "## Support",
            "",
            _table(
                ["Kind", "Split", "Beneficial", "Neutral", "Harmful"],
                [
                    [kind, split, counts.get("BENEFICIAL", 0), counts.get("NEUTRAL", 0), counts.get("HARMFUL", 0)]
                    for kind, section in (("I3", auth["i3_rare_override"]), ("I4", auth["i4_selective_hold"]))
                    for split, counts in section["support"].items()
                ],
            ),
            "",
            "## Oracle boundary",
            "",
            "Oracle rows use realized outcomes only as a non-deployable upper bound on train+calibration+validation. They never enter runtime features, and final audit remains sealed. The risk-constrained oracle activates only rows with observed utility above zero.",
            "",
            "Implemented: all selectable-state outcome oracle, top 0.25/0.5/1/2/5% outcome oracles, and the risk-constrained positive-utility oracle. Separate no-node-ID, held-out-source, and held-out-time generalization oracles are `NOT_EVALUATED_SUPPORT_NO_GO`; they are not treated as passes after the pre-audit support gate failed.",
            "",
            "## New evidence",
            "",
            "The selectable partitions contain only 19 beneficial I3 rows (13/3/3), below the preregistered 24/6/6 pre-audit minima. I4 contains only 20 selectable positives (14/3/3), below the 24-row support gate. The four final-audit positives are sealed and cannot flip authorization. D0 nevertheless provides a deterministic strict-gate diagnostic; it has zero validation activations and remains a formal no-go.",
        ],
    )
    _write_md(
        root / "outputs/reports/g4irsf16_rule_baselines.md",
        [
            "# G4IRSF16 local rule baselines",
            "",
            f"I3 evaluated `{evaluated_i3_rule}`; formal rule `{formal_i3_rule}`; promotion authorized: `{i3_rule_pass}`.",
            f"I4 evaluated `{evaluated_i4_rule}`; formal rule `{formal_i4_rule}`; promotion authorized: `{i4_rule_pass}`.",
            "",
            "Parameters are derived from train, candidates are ranked on calibration, and promotion is checked on validation. All rules are ID-free and preserve F2 on abstention. I4 means one natural service opportunity only; I3 means at most one legal alternative per segment.",
        ],
    )
    _write_md(
        root / "outputs/reports/g4irsf16_i4_training.md",
        [
            "# G4IRSF16 I4 selective-hold training",
            "",
            f"Offline result: `{i4_gate['status']}`.",
            "",
            f"Validation metrics: `{json.dumps(i4_gate['metrics'], sort_keys=True, allow_nan=False)}`",
            "",
            f"Validation benefit ECE: `{i4_gate['ece']:.9f}`.",
            "",
            "D0 is a cluster-bootstrap ensemble of calibrated linear heads with utility LCB, harmful UCB, OOD abstention, and an exact ID-free feature schema. Failure of any preregistered check is a formal no-go, not a request to tune on validation or audit.",
        ],
    )
    _write_md(
        root / "outputs/reports/g4irsf16_i3_training.md",
        [
            "# G4IRSF16 I3 risk-veto training",
            "",
            "`I3_REROUTE_MODEL_NOT_AUTHORIZED` is binding. A small harmfulness/risk diagnostic was trained, but it cannot authorize an override and no candidate-complete or listwise campaign was started.",
            "",
            f"Validation diagnostic: `{json.dumps(i3_evidence['validation'], sort_keys=True, allow_nan=False)}`",
        ],
    )
    _write_md(
        root / "outputs/reports/g4irsf16_externality_model.md",
        [
            "# G4IRSF16 sparse externality model",
            "",
            f"Status: `{externality_evidence['status']}`.",
            "",
            "The 232 selectable H_system rows support a small local-proxy diagnostic only. B0/B1/B2 budgets are fixed in the model metadata; B2 is diagnostic-only. Extra deadline miss is zero throughout the selectable panel, so that head is explicitly not trainable.",
            "",
            "The B1 CVaR95 threshold is preregistered metadata, not a passed gate: this release has no calibrated CVaR upper-bound head. Status is `NOT_EVALUATED_NO_CVAR_UCB_HEAD`, so externality promotion remains forbidden.",
            "",
            "Final-audit externality outcomes are excluded from the published risk table and remain `SEALED_NOT_CONSUMED`.",
            "",
            f"Validation externality ECE: `{externality_evidence['externality_nonempty_ece']:.9f}`.",
        ],
    )

    print(json.dumps({
        "status": model_gate["overall_status"],
        "i4_gate": i4_gate["status"],
        "i3_gate": auth["i3_rare_override"]["status"],
        "i4_model": str(i4_model_path),
        "final_audit": "SEALED_NOT_CONSUMED",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

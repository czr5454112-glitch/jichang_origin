from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.eval import finalize_g4irsf16_decision as finalizer


def _dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _offline() -> dict[str, object]:
    return {
        "schema": "czr005.g4irsf16.offline_model_gate.v1",
        "overall_status": "CAUSAL_LEARNING_MODEL_NO_GO",
        "final_audit": {
            "status": "SEALED_NOT_CONSUMED",
            "row_level_outcomes_used_for_selection": False,
        },
        "i4": {"status": "I4_SELECTIVE_MODEL_NO_GO"},
        "i3_rare_override": {"status": "I3_REROUTE_MODEL_NOT_AUTHORIZED"},
        "externality": {
            "status": "DIAGNOSTIC_SMALL_HEAD_NOT_INDEPENDENTLY_PROMOTED"
        },
    }


def _shadow() -> dict[str, object]:
    return {
        "schema": "czr005.g4irsf16.full_shadow.v1",
        "status": "PASS_FROZEN_F2_FULL_SHADOW",
        "segments": 43_603,
        "hard_gates": {
            "all_native_live_hard_gates_pass": True,
            "completed_segments": 43_603,
        },
        "shadow": {
            "f2_action_mutation_count": 0,
            "illegal_proposal_count": 0,
            "model_feature_leakage_count": 0,
        },
        "scientific_boundary": {
            "model_actions_executed": False,
            "closed_loop_claim_allowed": False,
        },
        "offline_authorization": {
            "overall_status": "CAUSAL_LEARNING_MODEL_NO_GO",
            "final_audit_status": "SEALED_NOT_CONSUMED",
        },
    }


def _rule_bundle() -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "czr005.g4irsf16.rule_bundle.v1",
        "default_action": "F2_EXACT",
        "final_audit_consumed": False,
        "i3": {"selected_rule": "R0", "promotion_authorized": False},
        "i4": {
            "selected_rule": "H0",
            "promotion_authorized": False,
            "diagnostic_canary": {
                "rule": "H5",
                "authorization": "8192_DIAGNOSTIC_ONLY_NOT_PROMOTED",
            },
        },
    }
    value["self_sha256"] = finalizer._canonical_sha256(value)  # noqa: SLF001
    return value


def _contract() -> dict[str, object]:
    return {
        "schema": "czr005.g4irsf16.supervisor_contract_regression.v1",
        "overall_pass": True,
        "evaluation_scope": "SUPERVISOR_CONTRACT_REGRESSION_NOT_FULL_CLOSED_LOOP_TTH",
        "invariants": {
            "full_astar_forbidden": True,
            "pibt_atomic_all_or_none": True,
            "repair_reentry_once_per_fault_episode": True,
            "stale_action_rejected": True,
            "unsafe_zero": True,
        },
        "fault": {"contract_pass": True, "unsafe_entry_count": 0},
        "tail_pibt": {"contract_pass": True, "unsafe_entry_count": 0},
    }


def _historical() -> dict[str, object]:
    return {
        "schema": "czr005.g4irsf14.final_candidate_bundle.v1",
        "performance": {
            "f2_frozen_reference_mean_minutes": 41.514218717973414,
            "v2_safe_frozen_reference_mean_minutes": 41.49530698780892,
        },
    }


def _model(kind: str) -> dict[str, object]:
    if kind == "I4":
        training = {
            "fit_split": "train",
            "threshold_split": "calibration",
            "promotion_split": "validation",
            "final_audit_consumed": False,
            "deployment_status": "SUPPORT_DIAGNOSTIC_ONLY_NOT_AUTHORIZED",
            "support_authorization_status": "NOT_AUTHORIZED",
        }
    elif kind == "I3_RISK_VETO_DIAGNOSTIC":
        training = {
            "fit_split": "train",
            "threshold_split": "calibration",
            "promotion_split": "validation",
            "final_audit_consumed": False,
            "deployment_status": "RISK_VETO_ONLY_DIAGNOSTIC",
        }
    else:
        training = {"fit_split": "train", "final_audit_consumed": False}
    actions = {
        "I4": "HOLD_ONE_NATURAL_SERVICE_OPPORTUNITY",
        "I3_RISK_VETO_DIAGNOSTIC": "ALLOW_PREREGISTERED_ALTERNATIVE_IF_RISK_PASS",
        "H_SYSTEM_EXTERNALITY": "PASS_BALANCED_EXTERNALITY_BUDGET",
    }
    width = len(finalizer.DEPLOYMENT_FEATURES)
    value: dict[str, object] = {
        "schema": "czr005.g4irsf16.selective_linear_ensemble.v1",
        "kind": kind,
        "action": actions[kind],
        "feature_names": list(finalizer.DEPLOYMENT_FEATURES),
        "normalization": {"mean": [0.0] * width, "scale": [1.0] * width},
        "training_bounds": {"min": [-1.0] * width, "max": [1.0] * width},
        "heads": {
            "benefit_logit": [[0.0] * (width + 1)],
            "harmful_logit": [[0.0] * (width + 1)],
            "risk_adjusted_utility_seconds": [[0.0] * (width + 1)],
        },
        "training_metadata": training,
        "thresholds": {
            "benefit_probability_lcb": 0.8,
            "harmful_probability_ucb": 0.2,
            "utility_lcb_margin_seconds": 0.0,
        },
    }
    value["self_sha256"] = finalizer._canonical_sha256(value)  # noqa: SLF001
    return value


def _canary(segments: int) -> dict[str, object]:
    if segments == 8_192:
        delta = 0.0015
        source_delta = 0.0025
        network_delta = -0.001
        improved, regressed, unchanged = 141, 297, 7_754
    elif segments == 2_048:
        delta = 0.00001
        source_delta = 0.00001
        network_delta = 0.0
        improved, regressed, unchanged = 1, 2, 2_045
    else:
        delta = source_delta = network_delta = 0.0
        improved, regressed, unchanged = 0, 0, segments
    off_mean = 57.0 + segments / 1_000_000.0
    off_source = 0.5
    off_network = 4.0
    return {
        "schema": "czr005.g4irsf16.closed_loop_canary.v1",
        "segments": segments,
        "mode": "closed_loop",
        "execution_semantics": "REAL_NATIVE_EVENT_RUNTIME_NOT_OFFLINE_REPLAY",
        "status": "PASS",
        "binary": {"sha256": "a" * 64},
        "frozen_scorer_model": {"sha256": "b" * 64},
        "policy": {
            "diagnostic_canary": "H5",
            "authorization": "8192_DIAGNOSTIC_ONLY_NOT_PROMOTED",
            "promotion_authorized": False,
            "selected_rule": "H0",
            "rule_bundle_sha256": "c" * 64,
        },
        "hard_gates": {
            "segments": segments,
            "mode": "closed_loop",
            "canary_pass": True,
            "safety_pass": True,
            "gates": {name: True for name in finalizer.REQUIRED_CANARY_GATES},
        },
        "off_comparison": {
            "enabled": True,
            "off_completed_count": segments,
            "off_failed_count": 0,
            "off_hard_gates": {
                "segments": segments,
                "mode": "off",
                "safety_pass": True,
                "gates": {name: True for name in finalizer.REQUIRED_OFF_GATES},
            },
            "paired_tth_summary": {
                "paired_complete_count": segments,
                "improved_bag_count": improved,
                "regressed_bag_count": regressed,
                "unchanged_bag_count": unchanged,
            },
        },
        "raw_bag_performance": {
            "denominator": "raw_bag_original_entry_time_tth",
            "early_gate_evaluated": True,
            "early_gate_pass": True,
            "candidate": {
                "original_entry_mean_minutes": off_mean + delta,
                "original_entry_p95_seconds": 100.0,
                "original_entry_p99_seconds": 120.0,
                "source_wait_mean_minutes": off_source + source_delta,
                "network_time_mean_minutes": off_network + network_delta,
            },
            "off": {
                "original_entry_mean_minutes": off_mean,
                "original_entry_p95_seconds": 100.0,
                "original_entry_p99_seconds": 120.0,
                "source_wait_mean_minutes": off_source,
                "network_time_mean_minutes": off_network,
            },
            "candidate_minus_off": {
                "original_entry_mean_minutes": delta,
                "source_wait_mean_minutes": source_delta,
                "network_time_mean_minutes": network_delta,
                "original_entry_p95_seconds": 0.0,
                "original_entry_p99_seconds": 0.0,
            },
        },
        "telemetry": {"action_change_count": max(1, segments // 4)},
    }


def _fixture(tmp_path: Path) -> tuple[finalizer.EvidencePaths, finalizer.OutputPaths]:
    evidence = tmp_path / "evidence"
    closed_loop = evidence / "closed_loop"
    paths = finalizer.EvidencePaths(
        offline_gate=evidence / "offline.json",
        full_shadow=evidence / "shadow.json",
        rule_bundle=evidence / "rules.json",
        i4_model=evidence / "i4.json",
        i3_model=evidence / "i3.json",
        externality_model=evidence / "externality.json",
        closed_loop_dir=closed_loop,
        contract_summary=evidence / "contract.json",
        historical_bundle=evidence / "historical.json",
        mechanism_boundary_report=evidence / "boundary.md",
    )
    _dump(paths.offline_gate, _offline())
    _dump(paths.rule_bundle, _rule_bundle())
    i4 = _model("I4")
    _dump(paths.i4_model, i4)
    _dump(paths.i3_model, _model("I3_RISK_VETO_DIAGNOSTIC"))
    _dump(paths.externality_model, _model("H_SYSTEM_EXTERNALITY"))
    shadow = _shadow()
    shadow["models"] = {
        "I4": {
            "path": finalizer._repo_path(paths.i4_model),  # noqa: SLF001
            "artifact_sha256": i4["self_sha256"],
            "harmful_probability_ucb_budget": 0.2,
        }
    }
    _dump(paths.full_shadow, shadow)
    _dump(paths.contract_summary, _contract())
    _dump(paths.historical_bundle, _historical())
    paths.mechanism_boundary_report.write_text(
        "The formal causal labels and the new runtime trace use E4. "
        "The historical F2 and v2-safe headline means were produced under E0. "
        "These must not be presented as a direct win.\n",
        encoding="utf-8",
    )
    for segments in finalizer.LADDER_SEGMENTS:
        _dump(
            closed_loop / f"g4irsf16_closed_loop_h5_{segments}.metadata.json",
            _canary(segments),
        )
    output_dir = tmp_path / "derived"
    outputs = finalizer.OutputPaths(
        final_gate=output_dir / "final.json",
        ladder_csv=output_dir / "ladder.csv",
        joint_csv=output_dir / "joint.csv",
        ladder_report=output_dir / "ladder.md",
        joint_report=output_dir / "joint.md",
    )
    return paths, outputs


def test_finalizer_publishes_honest_no_go_and_leaves_sources_unchanged(
    tmp_path: Path,
) -> None:
    inputs, outputs = _fixture(tmp_path)
    before = {path: path.read_bytes() for path in inputs.source_files()}

    decision = finalizer.finalize(
        inputs,
        outputs,
        scan_predictions=False,
        validate_canary_payloads=False,
    )

    assert {path: path.read_bytes() for path in inputs.source_files()} == before
    assert decision["status"] == "CAUSAL_LEARNING_NO_GO_WITH_ACTIONABLE_PIVOT"
    assert decision["decision"]["final_audit"] == "SEALED_NOT_CONSUMED"
    assert decision["decision"]["learned_expansion"] == "CLOSED"
    assert (
        decision["decision"]["full_43603_closed_loop_candidate"]["status"]
        == "NOT_RUN_FORMAL_OFFLINE_MODEL_NO_GO"
    )
    assert decision["h5_diagnostic_canary"]["promotion_authorized"] is False
    assert decision["h5_diagnostic_canary"][
        "largest_scale_delta_seconds_per_raw_bag"
    ] == pytest.approx(0.09)
    assert decision["actionable_pivot"]["priority"] == "I1_SOURCE_ORDERING"
    assert (
        decision["actionable_pivot"]["g2"]["status"]
        == "BLOCKED_PENDING_CAUSAL_CONCENTRATION_GATE"
    )
    assert decision["mechanism_boundary"]["cross_mechanism_strict_win_allowed"] is False

    ladder_rows = list(
        csv.DictReader(outputs.ladder_csv.read_text(encoding="utf-8").splitlines())
    )
    assert [int(row["segments"]) for row in ladder_rows] == [144, 512, 2_048, 8_192]
    joint = outputs.joint_csv.read_text(encoding="utf-8")
    assert "HISTORICAL_F2_E0" in joint
    assert "NOT_COMPARABLE_AS_STRICT_WIN_EVENT_SEMANTICS_MISMATCH" in joint
    assert "NOT_RUN_FORMAL_OFFLINE_MODEL_NO_GO" in joint
    report = outputs.joint_report.read_text(encoding="utf-8")
    assert "not a performance win" in report
    assert "G2 remains blocked" in report


def test_finalizer_fails_closed_if_final_audit_was_consumed(tmp_path: Path) -> None:
    inputs, outputs = _fixture(tmp_path)
    offline = _offline()
    offline["final_audit"] = {
        "status": "CONSUMED",
        "row_level_outcomes_used_for_selection": True,
    }
    _dump(inputs.offline_gate, offline)

    with pytest.raises(finalizer.FinalizationError, match="final audit"):
        finalizer.finalize(inputs, outputs)
    assert not any(path.exists() for path in outputs.files())


def test_finalizer_fails_closed_on_missing_or_failed_formal_scale(
    tmp_path: Path,
) -> None:
    inputs, outputs = _fixture(tmp_path)
    metadata = (
        inputs.closed_loop_dir / "g4irsf16_closed_loop_h5_8192.metadata.json"
    )
    broken = _canary(8_192)
    broken["status"] = "FAIL_HARD_GATE"
    _dump(metadata, broken)
    with pytest.raises(finalizer.FinalizationError, match="status is not PASS"):
        finalizer.finalize(inputs, outputs)

    _dump(metadata, _canary(8_192))
    missing = inputs.closed_loop_dir / "g4irsf16_closed_loop_h5_2048.metadata.json"
    missing.unlink()
    with pytest.raises(finalizer.FinalizationError, match="required evidence is missing"):
        finalizer.finalize(inputs, outputs)


def test_finalizer_rejects_any_output_that_aliases_source_evidence(
    tmp_path: Path,
) -> None:
    inputs, outputs = _fixture(tmp_path)
    aliased = finalizer.OutputPaths(
        final_gate=inputs.offline_gate,
        ladder_csv=outputs.ladder_csv,
        joint_csv=outputs.joint_csv,
        ladder_report=outputs.ladder_report,
        joint_report=outputs.joint_report,
    )
    with pytest.raises(finalizer.FinalizationError, match="aliases source evidence"):
        finalizer.finalize(inputs, aliased)


def test_finalizer_rejects_internally_inconsistent_performance_delta(
    tmp_path: Path,
) -> None:
    inputs, outputs = _fixture(tmp_path)
    metadata = (
        inputs.closed_loop_dir / "g4irsf16_closed_loop_h5_8192.metadata.json"
    )
    inconsistent = _canary(8_192)
    inconsistent["raw_bag_performance"]["candidate_minus_off"][  # type: ignore[index]
        "original_entry_mean_minutes"
    ] = 0.0
    _dump(metadata, inconsistent)
    with pytest.raises(finalizer.FinalizationError, match="internally inconsistent"):
        finalizer.finalize(inputs, outputs)


def test_pivot_ordering_is_unknown_when_decomposition_does_not_support_i1() -> None:
    rows = [
        {
            "segments": 8_192,
            "delta_seconds_per_raw_bag": 0.09,
            "source_wait_delta_seconds_per_raw_bag": -0.01,
            "network_delta_seconds_per_raw_bag": 0.10,
        }
    ]
    pivot = finalizer._derive_pivot(rows)  # noqa: SLF001
    assert pivot["priority"] == "UNKNOWN"
    assert pivot["status"] == "PIVOT_ORDERING_UNKNOWN"


def test_build_decision_does_not_accept_promoted_h5(tmp_path: Path) -> None:
    inputs, _ = _fixture(tmp_path)
    promoted = deepcopy(_rule_bundle())
    promoted["i4"]["promotion_authorized"] = True  # type: ignore[index]
    promoted.pop("self_sha256")
    promoted["self_sha256"] = finalizer._canonical_sha256(promoted)  # noqa: SLF001
    _dump(inputs.rule_bundle, promoted)
    with pytest.raises(finalizer.FinalizationError, match="promotion unexpectedly"):
        finalizer.build_decision(inputs)


def test_build_decision_rejects_stale_full_shadow_model_sha(tmp_path: Path) -> None:
    inputs, _ = _fixture(tmp_path)
    shadow = json.loads(inputs.full_shadow.read_text(encoding="utf-8"))
    shadow["models"]["I4"]["artifact_sha256"] = "0" * 64
    _dump(inputs.full_shadow, shadow)
    with pytest.raises(finalizer.FinalizationError, match="shadow I4 SHA is stale"):
        finalizer.build_decision(inputs)


def test_build_decision_rejects_mixed_native_binaries_across_ladder(
    tmp_path: Path,
) -> None:
    inputs, _ = _fixture(tmp_path)
    metadata = (
        inputs.closed_loop_dir / "g4irsf16_closed_loop_h5_8192.metadata.json"
    )
    mixed = _canary(8_192)
    mixed["binary"] = {"sha256": "d" * 64}
    _dump(metadata, mixed)
    with pytest.raises(finalizer.FinalizationError, match="more than one native binary"):
        finalizer.build_decision(inputs)


def test_portable_path_validator_rejects_windows_or_parent_escape() -> None:
    with pytest.raises(finalizer.FinalizationError, match="backslash"):
        finalizer._portable_repo_artifact(  # noqa: SLF001
            r"outputs\reports\local.json", "artifact", must_exist=False
        )
    with pytest.raises(finalizer.FinalizationError, match="escapes"):
        finalizer._portable_repo_artifact(  # noqa: SLF001
            "../outside.json", "artifact", must_exist=False
        )
    assert (
        finalizer._portable_external_binary(  # noqa: SLF001
            "EXTERNAL_NATIVE_BINARY/runtime.pyd", "binary"
        )
        == "runtime.pyd"
    )


def test_full_zstd_scan_checks_rows_bytes_and_final_newline(tmp_path: Path) -> None:
    import zstandard

    rows = [
        {
            "schema": "czr005.g4irsf16.shadow_prediction.v1",
            "decision_ordinal": ordinal,
            "model_feature_leakage": False,
            "illegal_proposal": False,
            "f2": {"action_unchanged": True},
            "i4": {
                "tentative_f2_next": (ordinal if ordinal != 30 else None),
                "causal_action_counts": {
                    "alternative_action_count": (0 if ordinal == 30 else 1),
                    "total_legal_action_count": (1 if ordinal == 30 else 2),
                },
            },
        }
        for ordinal in (10, 20, 30)
    ]
    payload = b"".join(
        json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n"
        for row in rows
    )
    path = tmp_path / "predictions.jsonl.zst"
    path.write_bytes(zstandard.ZstdCompressor(level=1).compress(payload))
    result = finalizer._scan_zstd_jsonl(  # noqa: SLF001
        path, expected_rows=3, expected_uncompressed_bytes=len(payload)
    )
    assert result == {
        "row_count": 3,
        "unique_decision_ordinal_count": 3,
        "uncompressed_byte_count": len(payload),
        "compressed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "uncompressed_sha256": hashlib.sha256(payload).hexdigest(),
    }
    with pytest.raises(finalizer.FinalizationError, match="row count mismatch"):
        finalizer._scan_zstd_jsonl(  # noqa: SLF001
            path, expected_rows=4, expected_uncompressed_bytes=len(payload)
        )

    bad_counts = deepcopy(rows)
    bad_counts[0]["i4"]["causal_action_counts"][  # type: ignore[index]
        "total_legal_action_count"
    ] = 1
    bad_payload = b"".join(
        json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n"
        for row in bad_counts
    )
    bad_path = tmp_path / "bad-counts.jsonl.zst"
    bad_path.write_bytes(zstandard.ZstdCompressor(level=1).compress(bad_payload))
    with pytest.raises(finalizer.FinalizationError, match="causal action-count mismatch"):
        finalizer._scan_zstd_jsonl(  # noqa: SLF001
            bad_path,
            expected_rows=3,
            expected_uncompressed_bytes=len(bad_payload),
        )

    no_newline = tmp_path / "no-newline.jsonl.zst"
    raw = json.dumps(rows[0], separators=(",", ":")).encode("utf-8")
    no_newline.write_bytes(zstandard.ZstdCompressor(level=1).compress(raw))
    with pytest.raises(finalizer.FinalizationError, match="lacks newline"):
        finalizer._scan_zstd_jsonl(  # noqa: SLF001
            no_newline, expected_rows=0, expected_uncompressed_bytes=len(raw)
        )


def test_validate_only_cli_flag_is_explicit() -> None:
    parsed = finalizer._parser().parse_args(["--validate-only"])  # noqa: SLF001
    assert parsed.validate_only is True


def test_derived_output_validation_rejects_tampered_table_or_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(finalizer, "ROOT", tmp_path)
    inputs, outputs = _fixture(tmp_path)
    decision = finalizer.finalize(
        inputs,
        outputs,
        scan_predictions=False,
        validate_canary_payloads=False,
    )
    expected_decision, ladder, joint = finalizer.build_decision(inputs)
    assert decision == expected_decision
    finalizer._validate_derived_outputs(  # noqa: SLF001
        expected_decision, ladder, joint, outputs
    )

    outputs.ladder_csv.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(finalizer.FinalizationError, match="stale or modified"):
        finalizer._validate_derived_outputs(  # noqa: SLF001
            expected_decision, ladder, joint, outputs
        )

    finalizer._write_csv(outputs.ladder_csv, ladder)  # noqa: SLF001
    outputs.joint_report.write_text("stale report\n", encoding="utf-8")
    with pytest.raises(finalizer.FinalizationError, match="stale or modified"):
        finalizer._validate_derived_outputs(  # noqa: SLF001
            expected_decision, ladder, joint, outputs
        )

from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf32_v3r3_p0_campaign as campaign


def test_content_hash_normalizes_to_json_domain_and_rejects_collisions(
    tmp_path: Path,
) -> None:
    source = {
        "schema": "json-domain-fixture",
        "nested": {7: (tmp_path / "evidence", {9: (1, 2, 3)})},
    }
    expected_content_sha = campaign.canonical_sha256(source)

    artifact = campaign.with_content_hash(source)
    output = tmp_path / "artifact.json"
    output.write_bytes(campaign._json_bytes(artifact, pretty=True))
    reread = campaign.read_strict_json(output)

    assert reread == artifact
    assert artifact["nested"] == {
        "7": [str(tmp_path / "evidence"), {"9": [1, 2, 3]}]
    }
    assert artifact["artifact_content_sha256"] == expected_content_sha
    assert campaign.verify_content_hash(reread) == expected_content_sha

    with pytest.raises(campaign.CampaignError, match="key collision"):
        campaign.with_content_hash({"nested": {1: "integer", "1": "string"}})
    with pytest.raises(campaign.CampaignError, match="non-finite"):
        campaign.with_content_hash({"value": float("nan")})


def test_registered_cli_bootstraps_from_its_script_path() -> None:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/eval/run_g4irsf32_v3r3_p0_campaign.py"), "--help"],
        cwd=str(campaign.ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Compose the sole V3R11 P0 FINAL_GO" in completed.stdout


def test_v3r11_composer_binds_the_v3r7_prearrival_overlap_control() -> None:
    assert campaign.SCHEMA.endswith(".v3r11")
    assert campaign.CANDIDATE_SCHEMA.endswith(".v3r11")
    assert campaign.PROTOCOL_ID == campaign.synthetic.PROTOCOL_ID
    assert campaign.PROTOCOL_ID == campaign.nanning.PROTOCOL_ID
    assert campaign.CONTROL_REVISION_ID == campaign.nanning.CONTROL_REVISION_ID
    assert (
        campaign.synthetic.COMMIT_ALIGNED_ADDENDUM_ID
        == campaign.CONTROL_REVISION_ID
    )
    assert campaign.CAMPAIGN_REVISION_ID == campaign.synthetic.CAMPAIGN_REVISION_ID
    assert campaign.FINAL_GO.startswith("GO_V3R11_")
    assert campaign.FINAL_GO != campaign.nanning.FINAL_GO
    assert campaign.TEST_ONLY_PASS.startswith("PASS_TEST_ONLY_V3R11_")
    assert campaign.NO_GO_PREFLIGHT.startswith("NO_GO_V3R11_")
    assert campaign.NO_GO_SYNTHETIC.startswith("NO_GO_V3R11_")
    assert campaign.NO_GO_IMMUTABILITY.startswith("NO_GO_V3R11_")
    assert campaign.NO_GO_SHADOW.startswith("NO_GO_V3R11_")
    assert campaign.NO_GO_INTERNAL.startswith("NO_GO_V3R11_")
    assert campaign._FORMAL_CONTROL_PATH == Path(campaign.nanning.OUTPUT_PATH)
    assert "v3r7" in campaign._FORMAL_CONTROL_PATH.name
    assert campaign._FORMAL_CONTROL_LOADER is campaign.nanning.load_and_validate_control_artifact
    assert campaign._FORMAL_SHADOW_RUNNER is campaign.nanning.run_g32_shadow_gate
    assert (
        campaign._FORMAL_SHADOW_VALIDATOR
        is campaign.nanning._deep_validate_g32_shadow_result_mapping
    )


HEAD = "1" * 40


def _identity() -> dict[str, Any]:
    return {
        "pass": True,
        "head": HEAD,
        "changed_paths": ["scripts/eval/frozen.py"],
        "unexpected_changed_paths": [],
        "dirty_source_paths": [],
        "gates": [{"name": "implementation_clean", "pass": True, "evidence": None}],
    }


def _source() -> dict[str, Any]:
    files = [{"path": "scripts/eval/frozen.py", "sha256": "2" * 64}]
    return {"files": files, "sha256": campaign.canonical_sha256(files)}


def _synthetic_pass(binary_sha: str) -> dict[str, Any]:
    safety_protocol_cases = [
        {"case_id": f"case-{index:03d}", "ordinal": index} for index in range(120)
    ]
    identification_protocol_cases = [
        {"case_id": f"identification-{index:02d}", "ordinal": index}
        for index in range(24)
    ]
    safety_case_summaries = [
        {"case_id": row["case_id"], "hard_gate_pass": True}
        for row in safety_protocol_cases
    ]
    identification_case_summaries = [
        {"case_id": row["case_id"], "hard_gate_pass": True}
        for row in identification_protocol_cases
    ]
    safety_observations = [{"cohort": "safety_regression", "observation_ordinal": 1}]
    identification_observations = [{"cohort": "identification", "observation_ordinal": 1}]
    safety_pairs = [{"cohort": "safety_regression", "runtime_bag_id": 1}]
    identification_pairs = [{"cohort": "identification", "runtime_bag_id": 2}]
    source = _source()
    identity = _identity()
    safety_protocol_sha = campaign.canonical_sha256(safety_protocol_cases)
    identification_protocol_sha = campaign.canonical_sha256(
        identification_protocol_cases
    )
    protocol_cohorts = {
        "safety_regression": {
            "case_count": 120,
            "cases": safety_protocol_cases,
            "cases_sha256": safety_protocol_sha,
        },
        "identification": {
            "case_count": 24,
            "cases": identification_protocol_cases,
            "cases_sha256": identification_protocol_sha,
        },
    }
    cohorts_sha = campaign.canonical_sha256(protocol_cohorts)
    return {
        "schema": campaign.synthetic.SCHEMA,
        "synthetic_revision_id": campaign.synthetic.SYNTHETIC_REVISION_ID,
        "campaign_revision_id": campaign.CAMPAIGN_REVISION_ID,
        "historical_control_revision_id": campaign.CONTROL_REVISION_ID,
        "status": campaign.synthetic.SYNTHETIC_PASS,
        "decision": campaign.synthetic.SYNTHETIC_PASS,
        "synthetic_pass": True,
        "nanning_p0_status": "PENDING_NOT_RUN_BY_SYNTHETIC_RUNNER",
        "p1_review_authorized": False,
        "protocol": {
            "schema": campaign.synthetic.SCHEMA,
            "protocol_id": campaign.PROTOCOL_ID,
            "synthetic_revision_id": campaign.synthetic.SYNTHETIC_REVISION_ID,
            "campaign_revision_id": campaign.CAMPAIGN_REVISION_ID,
            "historical_control_revision_id": campaign.CONTROL_REVISION_ID,
            "case_count": 144,
            "cohorts": protocol_cohorts,
            "cohorts_sha256": cohorts_sha,
        },
        "source_bundle": source,
        "source_bundle_checkpoints": {
            "start": source,
            "after_stage0": source,
            "after_stage1": source,
        },
        "implementation": identity,
        "implementation_head": HEAD,
        "g32_binary_sha256": binary_sha,
        "stage0": {
            "pass": True,
            "status": campaign.synthetic.STAGE0_PASS,
            "gates": [{"name": "stage0", "pass": True, "evidence": None}],
            "native_proof": {
                "pass": True,
                "g32_binary_sha256": binary_sha,
                "build_head": HEAD,
                "source_bundle": source,
            },
        },
        "stage1": {
            "pass": True,
            "status": "V3R11_STAGE1_PASS",
            "gates": [{"name": "stage1", "pass": True, "evidence": None}],
            "manifest_sha256": cohorts_sha,
            "safety_regression": {
                "pass": True,
                "manifest_sha256": safety_protocol_sha,
                "cases": safety_case_summaries,
                "observation_count": len(safety_observations),
                "observations_sha256": campaign.canonical_sha256(safety_observations),
                "observations": safety_observations,
                "pair_count": len(safety_pairs),
                "pairs_sha256": campaign.canonical_sha256(safety_pairs),
                "pairs": safety_pairs,
            },
            "identification": {
                "pass": True,
                "manifest_sha256": identification_protocol_sha,
                "cases": identification_case_summaries,
                "observation_count": len(identification_observations),
                "observations_sha256": campaign.canonical_sha256(identification_observations),
                "observations": identification_observations,
                "pair_count": len(identification_pairs),
                "pairs_sha256": campaign.canonical_sha256(identification_pairs),
                "pairs": identification_pairs,
            },
        },
    }


def _shadow(
    *,
    passed: bool,
    control_sha: str,
    synthetic_sha: str,
    binary_sha: str,
) -> dict[str, Any]:
    scales = {
        "1x": {"pass": passed},
        "2x": {"pass": passed},
    }
    status = (
        campaign.nanning.SHADOW_PASS
        if passed
        else campaign.nanning.SHADOW_NO_EVENT
    )
    return campaign.with_content_hash(
        {
            "schema": campaign.nanning.SHADOW_GATE_SCHEMA,
            "protocol_id": campaign.PROTOCOL_ID,
            "campaign_revision_id": campaign.CAMPAIGN_REVISION_ID,
            "control_revision_id": campaign.CONTROL_REVISION_ID,
            "status": status,
            "pass": passed,
            "control_artifact_content_sha256": "3" * 64,
            "control_artifact_file_sha256": control_sha,
            "synthetic_artifact_file_sha256": synthetic_sha,
            "synthetic_decision": campaign.synthetic.SYNTHETIC_PASS,
            "synthetic_implementation_head": HEAD,
            "g32_binary_sha256": binary_sha,
            "scales": scales,
        }
    )


def _inputs(tmp_path: Path) -> dict[str, Any]:
    control = tmp_path / "control.json"
    control.write_text("{}\n", encoding="utf-8")
    binary = tmp_path / "g32.pyd"
    binary.write_bytes(b"g32-formal-binary")
    return {
        "control_artifact": control,
        "expected_control_file_sha256": campaign.file_sha256(control),
        "synthetic_artifact": tmp_path / "synthetic.json",
        "g32_binary": binary,
        "expected_g32_binary_sha256": campaign.file_sha256(binary),
        "executor": lambda **_request: {},
        "output_json": tmp_path / "final.json",
        "output_md": tmp_path / "final.md",
    }


def _dependencies(
    inputs: Mapping[str, Any], calls: dict[str, int], order: list[str] | None = None
) -> dict[str, Any]:
    control_sha = inputs["expected_control_file_sha256"]
    binary_sha = inputs["expected_g32_binary_sha256"]

    def control_loader(
        path: Path, *, expected_file_sha256: str, auditor: Any
    ) -> tuple[dict[str, Any], str]:
        calls["control"] += 1
        if order is not None:
            order.append("control")
        assert path == inputs["control_artifact"]
        assert expected_file_sha256 == control_sha
        assert auditor is campaign.synthetic
        return (
            {
                "artifact_content_sha256": "3" * 64,
                "schema": campaign.nanning.SCHEMA,
                "protocol_id": campaign.PROTOCOL_ID,
                "control_revision_id": campaign.CONTROL_REVISION_ID,
                "status": campaign.nanning.PASS,
            },
            control_sha,
        )

    def synthetic_runner(**kwargs: Any) -> Mapping[str, Any]:
        calls["synthetic"] += 1
        if order is not None:
            order.append("synthetic")
        assert kwargs["g32_binary"] == inputs["g32_binary"].resolve()
        assert kwargs["identity_runner"]() == _identity()
        return _synthetic_pass(binary_sha)

    def synthetic_loader(
        path: Path,
        *,
        expected_file_sha256: str,
        expected_g32_binary_sha256: str,
        auditor: Any,
    ) -> tuple[dict[str, Any], str]:
        calls["deep"] += 1
        if order is not None:
            order.append("deep")
        assert path == inputs["synthetic_artifact"]
        assert expected_file_sha256 == campaign.file_sha256(path)
        assert expected_g32_binary_sha256 == binary_sha
        assert auditor is campaign.synthetic
        return campaign.read_strict_json(path), expected_file_sha256

    def shadow_runner(
        control_artifact: Path,
        g32_binary: Path,
        executor: Any,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        calls["shadow"] += 1
        if order is not None:
            order.append("shadow")
        assert control_artifact == inputs["control_artifact"]
        assert g32_binary == inputs["g32_binary"].resolve()
        assert executor is inputs["executor"]
        frozen = campaign.read_strict_json(inputs["synthetic_artifact"])
        campaign.verify_content_hash(frozen)
        return _shadow(
            passed=True,
            control_sha=control_sha,
            synthetic_sha=kwargs["expected_synthetic_file_sha256"],
            binary_sha=kwargs["expected_g32_binary_sha256"],
        )

    return {
        "control_loader": control_loader,
        "synthetic_runner": synthetic_runner,
        "synthetic_loader": synthetic_loader,
        "shadow_runner": shadow_runner,
        "identity_runner": _identity,
        "source_manifest_reader": _source,
        "build_head_reader": lambda _path: HEAD,
    }


def _registered_paths(inputs: Mapping[str, Any]) -> dict[str, Path]:
    return {
        name: inputs[name]
        for name in (
            "control_artifact",
            "synthetic_artifact",
            "g32_binary",
            "output_json",
            "output_md",
        )
    }


def _run_core(
    inputs: Mapping[str, Any], dependencies: Mapping[str, Any]
) -> dict[str, Any]:
    return campaign._run_p0_campaign_core(
        **inputs,
        **dependencies,
        registered_paths=_registered_paths(inputs),
        _test_only=True,
    )


def _executor_binding(executor: Any) -> dict[str, Any]:
    return {
        "module": getattr(executor, "__module__", None),
        "qualname": getattr(executor, "__qualname__", None),
    }


def test_full_mock_pipeline_is_only_a_neutral_candidate(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    order: list[str] = []
    result = _run_core(inputs, _dependencies(inputs, calls, order))

    assert result["decision"] == campaign.TEST_ONLY_PASS
    assert result["pipeline_candidate_pass"] is True
    assert result["pass"] is False
    assert result["p1_review_authorized"] is False
    assert result["authority"] == "TEST_ONLY_NO_FINAL_GO_AUTHORITY"
    assert result["registered_paths"]["g32_binary"] == str(
        inputs["g32_binary"].resolve()
    )
    assert calls == {"control": 1, "synthetic": 1, "deep": 1, "shadow": 1}
    assert order == ["control", "synthetic", "deep", "shadow"]
    assert result["sequence"] == list(campaign.CAMPAIGN_SEQUENCE)
    assert campaign.verify_content_hash(result) == result["artifact_content_sha256"]
    frozen = campaign.read_strict_json(inputs["synthetic_artifact"])
    assert campaign.verify_content_hash(frozen) == result["synthetic_artifact"]["content_sha256"]
    assert all(
        checkpoint["validation"]["pass"] is True
        for checkpoint in result["checkpoints"].values()
    )
    assert not inputs["output_json"].exists()
    assert not inputs["output_md"].exists()

    promotion = campaign.validate_p0_candidate_for_promotion(
        result,
        registered_paths=_registered_paths(inputs),
        expected_executor_binding=_executor_binding(inputs["executor"]),
    )
    assert promotion["pass"] is True
    registered_promotion = campaign._promote_registered_candidate(
        result, _test_only=True
    )
    assert registered_promotion["decision"] != campaign.FINAL_GO
    assert registered_promotion["p1_review_authorized"] is False


def test_formal_promotion_rejects_two_shallow_scale_pass_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)
    candidate = _run_core(inputs, dependencies)
    assert candidate["pipeline_candidate_pass"] is True
    assert candidate["nanning_shadow"]["scales"] == {
        "1x": {"pass": True},
        "2x": {"pass": True},
    }
    pure = campaign.validate_p0_candidate_for_promotion(
        candidate,
        registered_paths=_registered_paths(inputs),
        expected_executor_binding=_executor_binding(inputs["executor"]),
    )
    assert pure["pass"] is True

    monkeypatch.setattr(campaign, "_FORMAL_CPP_EXECUTOR", inputs["executor"])
    monkeypatch.setattr(campaign, "_FORMAL_REGISTERED_PATHS", _registered_paths(inputs))
    monkeypatch.setattr(campaign, "_FORMAL_CONTROL_PATH", inputs["control_artifact"])
    monkeypatch.setattr(campaign, "_FORMAL_SYNTHETIC_PATH", inputs["synthetic_artifact"])

    def trusted_scale(scale_number: int) -> dict[str, Any]:
        count = campaign.nanning.EXPECTED_SELECTION_COUNTS[scale_number]["total"]
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

    def registered_control_loader(
        path: Path, *, expected_file_sha256: str, auditor: Any
    ) -> tuple[dict[str, Any], str]:
        calls["control"] += 1
        assert path == inputs["control_artifact"]
        assert expected_file_sha256 == inputs["expected_control_file_sha256"]
        assert auditor is campaign.synthetic
        return (
            {
                "artifact_content_sha256": "3" * 64,
                "control_revision_id": campaign.CONTROL_REVISION_ID,
                "scales": {"1x": trusted_scale(1), "2x": trusted_scale(2)},
            },
            expected_file_sha256,
        )

    class RequestAuditor:
        @staticmethod
        def ordinary_request_sha256(request: Mapping[str, Any]) -> str:
            ignored = {
                "expected_binary_path",
                "search_path",
                "source_aware_destination_service_mode",
                "source_aware_destination_service_trace_limit",
            }
            return campaign.canonical_sha256(
                {key: value for key, value in request.items() if key not in ignored}
            )

        @staticmethod
        def assert_request_projection(*_args: Any, **_kwargs: Any) -> None:
            return None

    deep_validation_calls = 0

    def registered_shadow_validator(
        value: Mapping[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        nonlocal deep_validation_calls
        deep_validation_calls += 1
        assert value["scales"] == {
            "1x": {"pass": True},
            "2x": {"pass": True},
        }
        kwargs["auditor"] = RequestAuditor
        return campaign.nanning._deep_validate_g32_shadow_result_mapping(
            value, **kwargs
        )

    monkeypatch.setattr(
        campaign, "_FORMAL_CONTROL_LOADER", registered_control_loader
    )
    monkeypatch.setattr(
        campaign, "_FORMAL_SYNTHETIC_LOADER", dependencies["synthetic_loader"]
    )
    monkeypatch.setattr(
        campaign, "_FORMAL_SHADOW_VALIDATOR", registered_shadow_validator
    )

    promoted = campaign._promote_registered_candidate(
        candidate, g32_binary=inputs["g32_binary"], _test_only=True
    )

    formal = promoted["promotion_validation"]
    assert promoted["p1_review_authorized"] is False
    assert promoted["nanning_shadow_validation"]["pass"] is False
    assert deep_validation_calls == 1
    assert calls["control"] == 2
    assert calls["deep"] == 2
    assert formal["checks"]["formal_registered_shadow_deep_replay"] is False
    assert formal["formal_shadow_deep_validation"]["pass"] is False


def test_promotion_rejects_control_status_or_sequence_drift(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    candidate = _run_core(inputs, _dependencies(inputs, calls))
    assert candidate["decision"] == campaign.TEST_ONLY_PASS

    status_drift = deepcopy(candidate)
    status_drift.pop("artifact_content_sha256")
    status_drift["control_artifact"]["status"] = campaign.nanning.NO_EVENT
    status_drift = campaign.with_content_hash(status_drift)

    sequence_drift = deepcopy(candidate)
    sequence_drift.pop("artifact_content_sha256")
    sequence_drift["sequence"] = list(reversed(campaign.CAMPAIGN_SEQUENCE))
    sequence_drift = campaign.with_content_hash(sequence_drift)

    status_validation = campaign.validate_p0_candidate_for_promotion(
        status_drift,
        registered_paths=_registered_paths(inputs),
        expected_executor_binding=_executor_binding(inputs["executor"]),
    )
    sequence_validation = campaign.validate_p0_candidate_for_promotion(
        sequence_drift,
        registered_paths=_registered_paths(inputs),
        expected_executor_binding=_executor_binding(inputs["executor"]),
    )

    assert status_validation["pass"] is False
    assert status_validation["checks"]["control_bound"] is False
    assert sequence_validation["pass"] is False
    assert sequence_validation["checks"]["sequence_exact"] is False


def test_preflight_rejection_makes_zero_runtime_calls(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)

    def reject(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], str]:
        calls["control"] += 1
        raise campaign.nanning.SelectionError("deep control replay failed")

    dependencies["control_loader"] = reject
    result = _run_core(inputs, dependencies)

    assert result["decision"] == campaign.NO_GO_PREFLIGHT
    assert calls == {"control": 1, "synthetic": 0, "deep": 0, "shadow": 0}
    assert result["failure"]["stage"] == "preflight"
    assert not inputs["synthetic_artifact"].exists()


def test_legacy_control_revision_is_rejected_before_stage0(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)

    def legacy_control(
        _path: Path, *, expected_file_sha256: str, auditor: Any
    ) -> tuple[dict[str, Any], str]:
        calls["control"] += 1
        assert auditor is campaign.synthetic
        return (
            {
                "artifact_content_sha256": "3" * 64,
                "schema": campaign.nanning.SCHEMA,
                "protocol_id": campaign.PROTOCOL_ID,
                "control_revision_id": "G4IRSF32_V3R3_LEGACY_CONTROL",
                "status": campaign.nanning.PASS,
            },
            expected_file_sha256,
        )

    dependencies["control_loader"] = legacy_control
    result = _run_core(inputs, dependencies)

    assert result["decision"] == campaign.NO_GO_PREFLIGHT
    assert result["failure"]["stage"] == "preflight"
    assert "exact frozen V3R7 PASS contract" in result["failure"]["error"]
    assert "revision" in result["failure"]["error"]
    assert calls == {"control": 1, "synthetic": 0, "deep": 0, "shadow": 0}
    assert not inputs["synthetic_artifact"].exists()


def test_non_pass_v3r7_control_is_rejected_before_stage0(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)

    def failed_control(
        _path: Path, *, expected_file_sha256: str, auditor: Any
    ) -> tuple[dict[str, Any], str]:
        calls["control"] += 1
        assert auditor is campaign.synthetic
        return (
            {
                "artifact_content_sha256": "3" * 64,
                "schema": campaign.nanning.SCHEMA,
                "protocol_id": campaign.PROTOCOL_ID,
                "control_revision_id": campaign.CONTROL_REVISION_ID,
                "status": campaign.nanning.NO_EVENT,
            },
            expected_file_sha256,
        )

    dependencies["control_loader"] = failed_control
    result = _run_core(inputs, dependencies)

    assert result["decision"] == campaign.NO_GO_PREFLIGHT
    assert result["failure"]["stage"] == "preflight"
    assert "status" in result["failure"]["error"]
    assert calls == {"control": 1, "synthetic": 0, "deep": 0, "shadow": 0}
    assert not inputs["synthetic_artifact"].exists()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema", "czr005.g4irsf32.nanning_p0_control_selection.v3r3"),
        ("protocol_id", "G4IRSF32_WRONG_PROTOCOL"),
    ],
)
def test_control_schema_or_protocol_drift_is_rejected_before_stage0(
    tmp_path: Path, field: str, replacement: str
) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)

    def drifted_control(
        _path: Path, *, expected_file_sha256: str, auditor: Any
    ) -> tuple[dict[str, Any], str]:
        calls["control"] += 1
        assert auditor is campaign.synthetic
        artifact = {
            "artifact_content_sha256": "3" * 64,
            "schema": campaign.nanning.SCHEMA,
            "protocol_id": campaign.PROTOCOL_ID,
            "control_revision_id": campaign.CONTROL_REVISION_ID,
            "status": campaign.nanning.PASS,
        }
        artifact[field] = replacement
        return artifact, expected_file_sha256

    dependencies["control_loader"] = drifted_control
    result = _run_core(inputs, dependencies)

    assert result["decision"] == campaign.NO_GO_PREFLIGHT
    assert result["failure"]["stage"] == "preflight"
    assert field.removesuffix("_id") in result["failure"]["error"]
    assert calls == {"control": 1, "synthetic": 0, "deep": 0, "shadow": 0}
    assert not inputs["synthetic_artifact"].exists()


def test_public_wrapper_has_no_dependency_hooks_and_aliases_are_fixed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parameters = set(inspect.signature(campaign.run_p0_campaign).parameters)
    assert not parameters & {
        "executor",
        "synthetic_runner",
        "control_loader",
        "synthetic_loader",
        "shadow_runner",
        "identity_runner",
        "source_manifest_reader",
        "build_head_reader",
        "registered_paths",
    }
    assert "formal_authority" not in inspect.signature(
        campaign._run_p0_campaign_core
    ).parameters
    fixed = campaign._FORMAL_SYNTHETIC_RUNNER
    monkeypatch.setattr(campaign.synthetic, "run_campaign", lambda **_kwargs: {})
    assert campaign._FORMAL_SYNTHETIC_RUNNER is fixed


def test_formal_entrypoint_rejects_a_preloaded_native_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert campaign.FORMAL_EXECUTION_BLOCKED_REASON == ""
    monkeypatch.setitem(sys.modules, "czr005_cpp", object())
    with pytest.raises(campaign.CampaignError, match="requires a fresh process"):
        campaign.run_p0_campaign(
            control_artifact=tmp_path / "control.json",
            expected_control_file_sha256="1" * 64,
            synthetic_artifact=tmp_path / "synthetic.json",
            g32_binary=tmp_path / "g32.pyd",
            expected_g32_binary_sha256="2" * 64,
        )


def test_formal_entrypoint_and_cli_use_registered_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert campaign.FORMAL_EXECUTION_BLOCKED_REASON == ""
    monkeypatch.delitem(sys.modules, "czr005_cpp", raising=False)
    binary = tmp_path / "g32.pyd"
    binary.write_bytes(b"g32")
    candidate = {"status": campaign.TEST_ONLY_PASS}
    final = {"status": campaign.FINAL_GO, "decision": campaign.FINAL_GO}
    core_calls: list[dict[str, Any]] = []
    promotion_calls: list[tuple[Mapping[str, Any], Path | None]] = []
    publications: list[dict[str, Any]] = []
    monkeypatch.setattr(
        campaign,
        "_run_p0_campaign_core",
        lambda **kwargs: core_calls.append(kwargs) or candidate,
    )
    monkeypatch.setattr(
        campaign,
        "_promote_registered_candidate",
        lambda value, *, g32_binary=None: promotion_calls.append((value, g32_binary)) or final,
    )
    monkeypatch.setattr(
        campaign,
        "_publish_final_artifacts",
        lambda **kwargs: publications.append(kwargs),
    )
    result = campaign.run_p0_campaign(
        control_artifact=tmp_path / "control.json",
        expected_control_file_sha256="1" * 64,
        synthetic_artifact=tmp_path / "synthetic.json",
        g32_binary=binary,
        expected_g32_binary_sha256="2" * 64,
    )
    assert result is final
    assert len(core_calls) == len(promotion_calls) == len(publications) == 1
    assert core_calls[0]["executor"] is campaign._FORMAL_CPP_EXECUTOR
    assert core_calls[0]["synthetic_runner"] is campaign._FORMAL_SYNTHETIC_RUNNER
    assert core_calls[0]["control_loader"] is campaign._FORMAL_CONTROL_LOADER
    assert core_calls[0]["shadow_runner"] is campaign._FORMAL_SHADOW_RUNNER
    assert core_calls[0]["registered_paths"]["g32_binary"] == binary.resolve()
    assert promotion_calls == [(candidate, binary.resolve())]

    cli_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(campaign, "_default_g32_binary", lambda: binary)
    monkeypatch.setattr(
        campaign,
        "run_p0_campaign",
        lambda **kwargs: cli_calls.append(kwargs) or final,
    )
    exit_code = campaign.main(
        [
            "--expected-control-file-sha256", "1" * 64,
            "--expected-g32-binary-sha256", "2" * 64,
        ]
    )
    assert exit_code == 0
    assert len(cli_calls) == 1
    assert cli_calls[0]["g32_binary"] == binary


def test_low_level_core_formal_path_executes_registered_pipeline(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)

    result = campaign._run_p0_campaign_core(
        **inputs,
        **dependencies,
        registered_paths=_registered_paths(inputs),
    )

    assert result["decision"] == campaign.TEST_ONLY_PASS
    assert result["pipeline_candidate_pass"] is True
    assert result["p1_review_authorized"] is False
    assert calls == {"control": 1, "synthetic": 1, "deep": 1, "shadow": 1}
    assert not inputs["output_json"].exists()
    assert not inputs["output_md"].exists()


def test_low_level_promotion_calls_validation_and_fails_closed_on_invalid_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def invalid_validation(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return {"pass": False, "checks": {"candidate": False}, "error": "invalid candidate"}

    monkeypatch.setattr(
        campaign, "validate_p0_candidate_for_promotion", invalid_validation
    )
    result = campaign._promote_registered_candidate({})
    assert calls == 1
    assert result["decision"] == campaign.NO_GO_INTERNAL
    assert result["p1_review_authorized"] is False
    assert result["promotion_validation"]["checks"] == {
        "candidate": False,
        "formal_registered_shadow_deep_replay": False,
    }


@pytest.mark.parametrize("failure_kind", ["fake_pass", "binary_drift"])
def test_fake_synthetic_pass_or_drift_blocks_shadow(
    tmp_path: Path, failure_kind: str
) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)
    valid = _synthetic_pass(inputs["expected_g32_binary_sha256"])

    def bad_synthetic(**_kwargs: Any) -> Mapping[str, Any]:
        calls["synthetic"] += 1
        if failure_kind == "binary_drift":
            inputs["g32_binary"].write_bytes(b"drifted")
            return valid
        fake = deepcopy(valid)
        fake["stage1"]["identification"]["cases"] = fake["stage1"]["identification"]["cases"][:-1]
        return fake

    dependencies["synthetic_runner"] = bad_synthetic
    result = _run_core(inputs, dependencies)

    assert result["pass"] is False
    assert calls["shadow"] == 0
    assert inputs["synthetic_artifact"].exists()
    expected_stage = "after_synthetic_checkpoint" if failure_kind == "binary_drift" else "synthetic"
    assert result["failure"]["stage"] == expected_stage


def test_selector_deep_rejection_blocks_shadow(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)

    def reject_deep(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], str]:
        calls["deep"] += 1
        raise campaign.nanning.SelectionError("synthetic deep replay failed")

    dependencies["synthetic_loader"] = reject_deep
    result = _run_core(inputs, dependencies)

    assert result["decision"] == campaign.NO_GO_SYNTHETIC
    assert result["p1_review_authorized"] is False
    assert result["synthetic_artifact"]["selector_deep_validation"]["pass"] is False
    assert calls["shadow"] == 0


def test_shadow_no_go_is_retained_and_never_authorizes_p1(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)

    def failed_shadow(*_args: Any, **kwargs: Any) -> Mapping[str, Any]:
        calls["shadow"] += 1
        return _shadow(
            passed=False,
            control_sha=inputs["expected_control_file_sha256"],
            synthetic_sha=kwargs["expected_synthetic_file_sha256"],
            binary_sha=inputs["expected_g32_binary_sha256"],
        )

    dependencies["shadow_runner"] = failed_shadow
    result = _run_core(inputs, dependencies)

    assert result["decision"] == campaign.nanning.SHADOW_NO_EVENT
    assert result["pipeline_candidate_pass"] is False
    assert result["p1_review_authorized"] is False
    assert result["nanning_shadow_validation"]["pass"] is False
    assert result["nanning_shadow"]["status"] == campaign.nanning.SHADOW_NO_EVENT
    assert result["checkpoints"]["after_nanning_shadow"]["validation"]["pass"] is True


def test_shadow_revision_drift_never_authorizes_p1(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)

    def wrong_revision_shadow(*_args: Any, **kwargs: Any) -> Mapping[str, Any]:
        calls["shadow"] += 1
        result = _shadow(
            passed=True,
            control_sha=inputs["expected_control_file_sha256"],
            synthetic_sha=kwargs["expected_synthetic_file_sha256"],
            binary_sha=inputs["expected_g32_binary_sha256"],
        )
        unhashed = {
            key: value
            for key, value in result.items()
            if key != "artifact_content_sha256"
        }
        unhashed["control_revision_id"] = "G4IRSF32_V3R3_LEGACY_CONTROL"
        return campaign.with_content_hash(unhashed)

    dependencies["shadow_runner"] = wrong_revision_shadow
    result = _run_core(inputs, dependencies)

    assert result["decision"] == campaign.NO_GO_SHADOW
    assert result["p1_review_authorized"] is False
    assert result["failure"]["stage"] == "nanning_shadow"
    assert "control_revision" in result["failure"]["error"]


def test_existing_valid_synthetic_is_replayed_and_matches_fresh_result_exactly(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    proof_executable = tmp_path / "native-proof.exe"
    g31_binary = tmp_path / "g31.pyd"
    inputs["synthetic_run_kwargs"] = {
        "proof_executable": proof_executable,
        "g31_binary": g31_binary,
    }
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    order: list[str] = []
    dependencies = _dependencies(inputs, calls, order)
    base_runner = dependencies["synthetic_runner"]
    runner_bindings: list[dict[str, Any]] = []

    def recording_runner(**kwargs: Any) -> Mapping[str, Any]:
        runner_bindings.append(
            {
                "executor": kwargs["executor"],
                "g32_binary": kwargs["g32_binary"],
                "identity": kwargs["identity_runner"](),
                "proof_executable": kwargs["proof_executable"],
                "g31_binary": kwargs["g31_binary"],
            }
        )
        return base_runner(**kwargs)

    dependencies["synthetic_runner"] = recording_runner
    first = _run_core(inputs, dependencies)
    before = inputs["synthetic_artifact"].read_bytes()
    second = _run_core(inputs, dependencies)

    assert second["decision"] == campaign.TEST_ONLY_PASS
    assert second == first
    assert second["checkpoints"]["start"]["synthetic_artifact_file_sha256"] is None
    assert inputs["synthetic_artifact"].read_bytes() == before
    assert calls == {"control": 2, "synthetic": 2, "deep": 2, "shadow": 2}
    assert order == [
        "control",
        "synthetic",
        "deep",
        "shadow",
        "control",
        "deep",
        "synthetic",
        "shadow",
    ]
    expected_runner_binding = {
        "executor": inputs["executor"],
        "g32_binary": inputs["g32_binary"].resolve(),
        "identity": _identity(),
        "proof_executable": proof_executable,
        "g31_binary": g31_binary,
    }
    assert runner_bindings == [expected_runner_binding, expected_runner_binding]
    fresh_final = campaign._promote_registered_candidate(first, _test_only=True)
    resumed_final = campaign._promote_registered_candidate(second, _test_only=True)
    assert campaign._json_bytes(resumed_final, pretty=True) == campaign._json_bytes(
        fresh_final, pretty=True
    )
    assert campaign.render_report(resumed_final) == campaign.render_report(fresh_final)


def test_process_interrupt_after_synthetic_freeze_resumes_at_shadow(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    interrupted = _dependencies(inputs, calls)

    def interrupt_shadow(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
        calls["shadow"] += 1
        raise KeyboardInterrupt("injected process interruption")

    interrupted["shadow_runner"] = interrupt_shadow
    with pytest.raises(KeyboardInterrupt, match="process interruption"):
        _run_core(inputs, interrupted)
    frozen_before = inputs["synthetic_artifact"].read_bytes()

    resumed = _run_core(inputs, _dependencies(inputs, calls))

    assert resumed["decision"] == campaign.TEST_ONLY_PASS
    assert "resumed_existing" not in resumed["synthetic_artifact"]
    assert inputs["synthetic_artifact"].read_bytes() == frozen_before
    assert calls == {"control": 2, "synthetic": 2, "deep": 2, "shadow": 2}


def test_process_interrupt_after_shadow_resumes_deterministically(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    baseline_calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    baseline = _run_core(inputs, _dependencies(inputs, baseline_calls))
    inputs["synthetic_artifact"].unlink()

    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    interrupted = _dependencies(inputs, calls)
    source_calls = 0

    def interrupt_after_shadow() -> Mapping[str, Any]:
        nonlocal source_calls
        source_calls += 1
        if source_calls == 4:
            raise KeyboardInterrupt("injected interruption after shadow")
        return _source()

    interrupted["source_manifest_reader"] = interrupt_after_shadow
    with pytest.raises(KeyboardInterrupt, match="after shadow"):
        _run_core(inputs, interrupted)
    frozen_before = inputs["synthetic_artifact"].read_bytes()

    resumed = _run_core(inputs, _dependencies(inputs, calls))

    assert resumed == baseline
    assert inputs["synthetic_artifact"].read_bytes() == frozen_before
    assert calls == {"control": 2, "synthetic": 2, "deep": 2, "shadow": 2}


def test_existing_noncanonical_synthetic_is_blocked_by_byte_exact_replay(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    forged = campaign.with_content_hash(
        _synthetic_pass(inputs["expected_g32_binary_sha256"])
    )
    campaign._append_only_write(
        inputs["synthetic_artifact"], campaign._json_bytes(forged)
    )
    before = inputs["synthetic_artifact"].read_bytes()
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    result = _run_core(inputs, _dependencies(inputs, calls))

    assert result["decision"] == campaign.NO_GO_SYNTHETIC
    assert result["failure"]["stage"] == "synthetic"
    assert "replay bytes differ" in result["failure"]["error"]
    assert result["p1_review_authorized"] is False
    assert calls == {"control": 1, "synthetic": 1, "deep": 1, "shadow": 0}
    assert inputs["synthetic_artifact"].read_bytes() == before


def test_nondeterministic_resume_result_is_blocked_before_shadow(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    calls = {"control": 0, "synthetic": 0, "deep": 0, "shadow": 0}
    dependencies = _dependencies(inputs, calls)
    first = _run_core(inputs, dependencies)
    before = inputs["synthetic_artifact"].read_bytes()

    def nondeterministic_replay(**kwargs: Any) -> Mapping[str, Any]:
        calls["synthetic"] += 1
        assert kwargs["g32_binary"] == inputs["g32_binary"].resolve()
        assert kwargs["identity_runner"]() == _identity()
        replay = _synthetic_pass(inputs["expected_g32_binary_sha256"])
        replay["nondeterministic_extension"] = {"nonce": "second-run"}
        return replay

    dependencies["synthetic_runner"] = nondeterministic_replay
    resumed = _run_core(inputs, dependencies)

    assert first["decision"] == campaign.TEST_ONLY_PASS
    assert resumed["decision"] == campaign.NO_GO_SYNTHETIC
    assert resumed["failure"]["stage"] == "synthetic"
    assert "replay mapping differs" in resumed["failure"]["error"]
    assert resumed["p1_review_authorized"] is False
    assert calls == {"control": 2, "synthetic": 2, "deep": 2, "shadow": 1}
    assert inputs["synthetic_artifact"].read_bytes() == before


def test_final_second_link_failure_leaves_no_partial_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = tmp_path / "final.json"
    report = tmp_path / "final.md"
    real_link = campaign.os.link
    calls = 0
    destinations: list[Path] = []

    def fail_second(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        destinations.append(destination)
        if calls == 2:
            raise OSError("injected second-link race")
        real_link(source, destination)

    monkeypatch.setattr(campaign.os, "link", fail_second)
    with pytest.raises(OSError, match="second-link race"):
        campaign._publish_final_artifacts(
            json_path=authority,
            json_payload=b'{"ok":true}\n',
            report_path=report,
            report_payload=b"report\n",
        )

    assert not authority.exists()
    assert not report.exists()
    assert destinations == [report, authority]
    assert not list(tmp_path.glob(".*.tmp"))


def test_exact_report_orphan_is_recovered_and_json_is_commit_marker(
    tmp_path: Path,
) -> None:
    authority = tmp_path / "final.json"
    report = tmp_path / "final.md"
    json_payload = b'{"status":"GO"}\n'
    report_payload = b"frozen report\n"
    report.write_bytes(report_payload)

    campaign._publish_final_artifacts(
        json_path=authority,
        json_payload=json_payload,
        report_path=report,
        report_payload=report_payload,
    )

    assert authority.read_bytes() == json_payload
    assert report.read_bytes() == report_payload
    with pytest.raises(FileExistsError, match="authoritative final JSON"):
        campaign._publish_final_artifacts(
            json_path=authority,
            json_payload=json_payload,
            report_path=report,
            report_payload=report_payload,
        )


def test_process_interrupt_after_report_link_recovers_exact_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = tmp_path / "final.json"
    report = tmp_path / "final.md"
    json_payload = b'{"status":"GO","stable":true}\n'
    report_payload = b"deterministic scientific report\n"
    real_link = campaign.os.link
    calls = 0

    def interrupt_json_commit(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("crash after report link")
        real_link(source, destination)

    monkeypatch.setattr(campaign.os, "link", interrupt_json_commit)
    with pytest.raises(KeyboardInterrupt, match="after report link"):
        campaign._publish_final_artifacts(
            json_path=authority,
            json_payload=json_payload,
            report_path=report,
            report_payload=report_payload,
        )
    assert report.read_bytes() == report_payload
    assert not authority.exists()

    monkeypatch.setattr(campaign.os, "link", real_link)
    campaign._publish_final_artifacts(
        json_path=authority,
        json_payload=json_payload,
        report_path=report,
        report_payload=report_payload,
    )
    assert authority.read_bytes() == json_payload
    assert report.read_bytes() == report_payload


def test_unverified_report_orphan_is_not_deleted(tmp_path: Path) -> None:
    authority = tmp_path / "final.json"
    report = tmp_path / "final.md"
    report.write_bytes(b"unrelated report\n")
    with pytest.raises(FileExistsError, match="unverified report orphan"):
        campaign._publish_final_artifacts(
            json_path=authority,
            json_payload=b"{}\n",
            report_path=report,
            report_payload=b"expected report\n",
        )
    assert report.read_bytes() == b"unrelated report\n"
    assert not authority.exists()


def test_read_strict_json_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"a":1,"nested":{"b":2,"b":3}}', encoding="utf-8")
    with pytest.raises(campaign.CampaignError, match="duplicate JSON object key"):
        campaign.read_strict_json(path)

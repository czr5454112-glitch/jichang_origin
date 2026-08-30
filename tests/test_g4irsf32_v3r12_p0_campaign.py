from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf32_v3r12_p0_campaign as campaign


def _prerequisite(binary_sha: str) -> dict[str, Any]:
    return campaign._with_content_hash(
        {
            "schema": campaign.v3r11_auditor.SCHEMA,
            "synthetic_revision_id": campaign.v3r11_auditor.SYNTHETIC_REVISION_ID,
            "campaign_revision_id": campaign.v3r11_auditor.CAMPAIGN_REVISION_ID,
            "historical_control_revision_id": campaign.HISTORICAL_CONTROL_REVISION_ID,
            "status": campaign.v3r11_auditor.SYNTHETIC_PASS,
            "decision": campaign.v3r11_auditor.SYNTHETIC_PASS,
            "synthetic_pass": True,
            "nanning_p0_status": "PENDING_NOT_RUN_BY_SYNTHETIC_RUNNER",
            "p1_review_authorized": False,
            "implementation": {
                "head": campaign.FROZEN_V3R11_IMPLEMENTATION_HEAD,
                "pass": True,
            },
            "implementation_head": campaign.FROZEN_V3R11_IMPLEMENTATION_HEAD,
            "g32_binary_sha256": binary_sha,
            "source_bundle": {"files": [], "sha256": "frozen-source"},
            "stage0": {
                "pass": True,
                "status": campaign.v3r11_auditor.STAGE0_PASS,
            },
            "stage1": {
                "pass": True,
                "status": "V3R11_STAGE1_PASS",
                "safety_regression": {"cases": [{}] * 120},
                "identification": {"cases": [{}] * 24},
            },
        }
    )


def _control() -> dict[str, Any]:
    scale = {
        "status": campaign.active.PASS,
        "pass": True,
        "selection": {"selected_segment_count": 62},
        "control": {"audit": {"qualifying_event_count": 1}},
    }
    return {
        "artifact_content_sha256": "c" * 64,
        "status": campaign.active.PASS,
        "pass": True,
        "control_revision_id": campaign.ACTIVE_CONTROL_REVISION_ID,
        "historical_control_revision_id": campaign.HISTORICAL_CONTROL_REVISION_ID,
        "selection_basis": campaign.active.SELECTION_BASIS,
        "formal_inference_eligible": False,
        "scales": {"1x": deepcopy(scale), "2x": deepcopy(scale)},
    }


def _shadow(
    *,
    synthetic_sha: str,
    binary_sha: str,
    admitted: bool = True,
) -> dict[str, Any]:
    scale = {
        "pass": admitted,
        "checks": {
            "loaded_g32_binary": True,
            "ordinary_request_exact": True,
            "node49_upstream53_admitted": admitted,
        },
        "admitted_node49_upstream53_count": 1 if admitted else 0,
    }
    return campaign._with_content_hash(
        {
            "schema": campaign.active.SHADOW_GATE_SCHEMA,
            "protocol_id": campaign.active.PROTOCOL_ID,
            "campaign_revision_id": campaign.CAMPAIGN_REVISION_ID,
            "active_control_revision_id": campaign.ACTIVE_CONTROL_REVISION_ID,
            "historical_control_revision_id": campaign.HISTORICAL_CONTROL_REVISION_ID,
            "status": (
                campaign.active.SHADOW_PASS
                if admitted
                else campaign.active.SHADOW_NO_EVENT
            ),
            "pass": admitted,
            "selection_basis": campaign.active.SELECTION_BASIS,
            "selection_role": campaign.active.SELECTION_ROLE,
            "diagnostic_origin": campaign.active.DIAGNOSTIC_ORIGIN,
            "formal_inference_eligible": False,
            "control_artifact_content_sha256": "c" * 64,
            "control_artifact_file_sha256": "d" * 64,
            "prerequisite_artifact_content_sha256": "e" * 64,
            "prerequisite_artifact_file_sha256": synthetic_sha,
            "prerequisite_decision": campaign.v3r11_auditor.SYNTHETIC_PASS,
            "prerequisite_implementation_head": campaign.FROZEN_V3R11_IMPLEMENTATION_HEAD,
            "g32_binary_sha256": binary_sha,
            "scales": {"1x": deepcopy(scale), "2x": deepcopy(scale)},
        }
    )


def _case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    binary = tmp_path / "g32.pyd"
    binary.write_bytes(b"registered-g32")
    binary_sha = campaign._file_sha256(binary)
    monkeypatch.setattr(campaign, "FROZEN_G32_BINARY_SHA256", binary_sha)

    prerequisite = _prerequisite(binary_sha)
    synthetic = tmp_path / "v3r11.json"
    synthetic.write_bytes(campaign._json_bytes(prerequisite))
    synthetic_sha = campaign._file_sha256(synthetic)
    monkeypatch.setattr(campaign, "FROZEN_SYNTHETIC_FILE_SHA256", synthetic_sha)

    control_path = tmp_path / "control.json"
    control_path.write_bytes(b"active-control")
    control = _control()
    calls = {"synthetic_loader": 0, "control_loader": 0, "shadow": 0, "executor": 0}

    def synthetic_loader(
        path: Path,
        *,
        expected_file_sha256: str,
        expected_g32_binary_sha256: str,
        auditor: Any,
    ) -> tuple[dict[str, Any], str]:
        calls["synthetic_loader"] += 1
        assert path == synthetic
        assert expected_file_sha256 == synthetic_sha
        assert expected_g32_binary_sha256 == binary_sha
        assert auditor.source_bundle_manifest() == prerequisite["source_bundle"]
        return deepcopy(prerequisite), synthetic_sha

    def control_loader(
        path: Path, *, expected_file_sha256: str
    ) -> tuple[dict[str, Any], str]:
        calls["control_loader"] += 1
        assert path == control_path
        return deepcopy(control), expected_file_sha256

    def executor(**_request: Any) -> Mapping[str, Any]:
        calls["executor"] += 1
        return {}

    def shadow_runner(
        _control_path: Path,
        _binary: Path,
        bound_executor: Any,
        **_bindings: Any,
    ) -> Mapping[str, Any]:
        calls["shadow"] += 1
        bound_executor()
        bound_executor()
        return _shadow(synthetic_sha=synthetic_sha, binary_sha=binary_sha)

    def shadow_validator(value: Mapping[str, Any], **_bindings: Any) -> Mapping[str, Any]:
        return deepcopy(dict(value))

    inputs = {
        "synthetic_artifact": synthetic,
        "control_artifact": control_path,
        "g32_binary": binary,
        "expected_synthetic_file_sha256": synthetic_sha,
        "expected_g32_binary_sha256": binary_sha,
        "expected_implementation_head": campaign.FROZEN_V3R11_IMPLEMENTATION_HEAD,
        "executor": executor,
        "synthetic_loader": synthetic_loader,
        "control_loader": control_loader,
        "shadow_runner": shadow_runner,
        "shadow_validator": shadow_validator,
    }
    return {
        "inputs": inputs,
        "calls": calls,
        "prerequisite": prerequisite,
        "synthetic": synthetic,
        "binary": binary,
        "synthetic_sha": synthetic_sha,
        "binary_sha": binary_sha,
    }


def _run(case: Mapping[str, Any]) -> dict[str, Any]:
    return campaign._run_p0_campaign_core(**case["inputs"])


def _assert_not_go(result: Mapping[str, Any]) -> None:
    formal = campaign._promote_formal_candidate(result)
    assert formal["pass"] is False
    assert formal["p1_review_authorized"] is False
    assert formal["decision"] != campaign.FINAL_GO


def test_missing_prerequisite_stops_before_any_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    case["synthetic"].unlink()
    result = _run(case)
    assert result["failure"]["stage"] == "v3r11_prerequisite"
    assert case["calls"] == {
        "synthetic_loader": 0,
        "control_loader": 0,
        "shadow": 0,
        "executor": 0,
    }
    _assert_not_go(result)


def test_wrong_prerequisite_file_identity_stops_before_any_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    case["synthetic"].write_bytes(case["synthetic"].read_bytes() + b" ")
    result = _run(case)
    assert "file identity changed" in result["failure"]["error"]
    assert case["calls"]["synthetic_loader"] == 0
    assert case["calls"]["executor"] == 0
    _assert_not_go(result)


def test_stage1_false_stops_before_deep_loader_and_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    failed = deepcopy(case["prerequisite"])
    failed.pop("artifact_content_sha256")
    failed["stage1"]["pass"] = False
    failed = campaign._with_content_hash(failed)
    case["synthetic"].write_bytes(campaign._json_bytes(failed))
    changed_sha = campaign._file_sha256(case["synthetic"])
    monkeypatch.setattr(campaign, "FROZEN_SYNTHETIC_FILE_SHA256", changed_sha)
    case["inputs"]["expected_synthetic_file_sha256"] = changed_sha
    result = _run(case)
    assert result["failure"]["stage"] == "v3r11_prerequisite"
    assert case["calls"]["synthetic_loader"] == 0
    assert case["calls"]["executor"] == 0
    _assert_not_go(result)


def test_wrong_binary_stops_before_active_control_and_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    case["binary"].write_bytes(b"different-binary")
    result = _run(case)
    assert result["failure"]["stage"] == "g32_binary"
    assert case["calls"]["synthetic_loader"] == 1
    assert case["calls"]["control_loader"] == 0
    assert case["calls"]["executor"] == 0
    _assert_not_go(result)


def test_active_shadow_failure_never_signs_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)

    def failing_shadow(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
        case["calls"]["shadow"] += 1
        case["inputs"]["executor"]()
        case["inputs"]["executor"]()
        return _shadow(
            synthetic_sha=case["synthetic_sha"],
            binary_sha=case["binary_sha"],
            admitted=False,
        )

    case["inputs"]["shadow_runner"] = failing_shadow
    result = _run(case)
    assert result["failure"]["stage"] == "active_shadow"
    assert case["calls"]["executor"] == 2
    _assert_not_go(result)


def test_positive_reuse_only_candidate_can_be_formally_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path, monkeypatch)
    candidate = _run(case)
    assert candidate["pipeline_candidate_pass"] is True
    assert candidate["synthetic_prerequisite"]["case_count"] == 144
    assert candidate["synthetic_prerequisite"]["synthetic_executor_call_count"] == 0
    assert candidate["active_control"]["scales"]["1x"]["selected_count"] == 62
    assert case["calls"] == {
        "synthetic_loader": 1,
        "control_loader": 1,
        "shadow": 1,
        "executor": 2,
    }
    result = campaign._promote_formal_candidate(candidate)
    assert result["decision"] == campaign.FINAL_GO
    assert result["pass"] is True
    assert result["p1_review_authorized"] is True
    assert result["canary_scope"]["effect_estimate"] is False
    assert result["canary_scope"]["formal_inference_eligible"] is False


def test_formal_entrypoint_has_fixed_paths_and_no_synthetic_runner() -> None:
    assert inspect.signature(campaign.run_p0_campaign).parameters == {}
    parameters = inspect.signature(campaign._run_p0_campaign_core).parameters
    assert "synthetic_runner" not in parameters
    assert campaign.SYNTHETIC_ARTIFACT.name == "g4irsf32_v3r11_synthetic_stage01.json"
    assert campaign.CONTROL_ARTIFACT == campaign.active.OUTPUT_PATH
    assert campaign.OUTPUT_JSON.name == "g4irsf32_v3r12_p0_campaign.json"
    assert campaign.OUTPUT_MD.name == "g4irsf32_v3r12_p0_campaign.md"


def test_append_only_bundle_rolls_back_if_second_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    decision = tmp_path / "decision.json"
    real_link = campaign.os.link
    calls = 0

    def fail_second(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second-link failure")
        real_link(source, destination)

    monkeypatch.setattr(campaign.os, "link", fail_second)
    with pytest.raises(OSError, match="second-link"):
        campaign._append_only_publish_bundle(
            {report: b"report", decision: b"decision"}
        )
    assert not report.exists()
    assert not decision.exists()

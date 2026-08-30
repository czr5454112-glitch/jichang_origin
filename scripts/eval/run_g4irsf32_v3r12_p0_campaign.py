#!/usr/bin/env python3
"""Compose the reuse-only V3R12 Nanning P0 engineering decision.

V3R12 deliberately reuses the immutable, fully passing V3R11 Stage 0/1
artifact.  It never invokes the 144-case synthetic executor.  The historical
artifact is replayed through the V3R11 selector's full loader, then the active
V3R12 control and G32 canary are validated before P1 review can be allowed.

The active cohort is outcome-informed.  A pass therefore establishes only
that the intended real mixed-origin path was exercised safely; it is not an
effect estimate and is not presented as outcome-blind evidence.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import (  # noqa: E402
    run_g4irsf32_v3r2_external_commit_local_virtual_shadow as v3r11_auditor,
)
from scripts.eval import (  # noqa: E402
    run_g4irsf32_v3r3_nanning_p0_selection as v3r11_loader,
)
from scripts.eval import (  # noqa: E402
    run_g4irsf32_v3r12_nanning_p0_canary as active,
)


SCHEMA = "czr005.g4irsf32.p0_campaign.v3r12"
CANDIDATE_SCHEMA = "czr005.g4irsf32.p0_campaign_candidate.v3r12"
CAMPAIGN_REVISION_ID = active.CAMPAIGN_REVISION_ID
HISTORICAL_CONTROL_REVISION_ID = active.HISTORICAL_CONTROL_REVISION_ID
ACTIVE_CONTROL_REVISION_ID = active.CONTROL_REVISION_ID

FINAL_GO = "GO_V3R12_NANNING_P0_ENGINEERING_CANARY_P1_REVIEW_ALLOWED"
TEST_ONLY_PASS = "PASS_TEST_ONLY_V3R12_P0_CANDIDATE_NO_AUTHORITY"
NO_GO_PREREQUISITE = "NO_GO_V3R12_P0_V3R11_PREREQUISITE"
NO_GO_BINARY = "NO_GO_V3R12_P0_G32_BINARY"
NO_GO_CONTROL = "NO_GO_V3R12_P0_ACTIVE_CONTROL"
NO_GO_SHADOW = "NO_GO_V3R12_P0_ACTIVE_SHADOW"
NO_GO_INTERNAL = "NO_GO_V3R12_P0_COMPOSER_INTERNAL"

FROZEN_SYNTHETIC_FILE_SHA256 = (
    "b7d55f1c52a245a74454cc5dba268dc2b72eab946030c5a219722227d39d76d2"
)
FROZEN_G32_BINARY_SHA256 = (
    "76b5e2f130491572d6e522654e6772ee10be01bf6800a2cf295efaba29b5e994"
)
FROZEN_V3R11_IMPLEMENTATION_HEAD = "18d92c1505e8a210d6dca61979e0183c3227ed5d"

SYNTHETIC_ARTIFACT = (
    ROOT / "outputs/tables/g4irsf32_v3r11_synthetic_stage01.json"
)
CONTROL_ARTIFACT = Path(active.OUTPUT_PATH)
G32_BINARY = (
    ROOT
    / "build_g32_v3r2/python/Release/czr005_cpp.cp311-win_amd64.pyd"
)
OUTPUT_JSON = ROOT / "outputs/tables/g4irsf32_v3r12_p0_campaign.json"
OUTPUT_MD = ROOT / "outputs/reports/g4irsf32_v3r12_p0_campaign.md"

CAMPAIGN_SEQUENCE = (
    "deep_replay_frozen_v3r11_stage0_stage1",
    "bind_same_historical_g32_binary",
    "deep_validate_active_v3r12_control",
    "run_and_deep_validate_active_v3r12_shadow",
    "compose_p1_review_decision",
)

Executor = Callable[..., Mapping[str, Any]]
SyntheticLoader = Callable[..., tuple[dict[str, Any], str]]
ControlLoader = Callable[..., tuple[dict[str, Any], str]]
ShadowRunner = Callable[..., Mapping[str, Any]]
ShadowValidator = Callable[..., Mapping[str, Any]]

_FORMAL_EXECUTOR = v3r11_auditor.cpp_executor
_FORMAL_SYNTHETIC_LOADER = v3r11_loader.load_and_validate_synthetic_artifact
_FORMAL_CONTROL_LOADER = active.load_and_validate_control_artifact
_FORMAL_SHADOW_RUNNER = active.run_g32_shadow_gate
_FORMAL_SHADOW_VALIDATOR = active.deep_validate_g32_shadow_result_mapping


class CampaignError(RuntimeError):
    """A V3R12 campaign gate failed closed."""


class FrozenSourceAuditorProxy:
    """Replay V3R11 logic against the source bundle frozen in its artifact."""

    def __init__(
        self,
        auditor: Any,
        source_bundle: Mapping[str, Any],
        artifact_path: Path,
    ) -> None:
        self._auditor = auditor
        self._source_bundle = deepcopy(dict(source_bundle))
        self.OUTPUT_JSON = artifact_path

    def __getattr__(self, name: str) -> Any:
        return getattr(self._auditor, name)

    def source_bundle_manifest(self) -> dict[str, Any]:
        return deepcopy(self._source_bundle)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CampaignError(f"{label} must be an object")
    return value


def _file_sha256(path: Path) -> str:
    return v3r11_loader.file_sha256(path)


def _read_json(path: Path) -> dict[str, Any]:
    value = v3r11_loader.read_strict_json(path)
    return dict(_mapping(value, str(path)))


def _with_content_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    return v3r11_loader.with_content_hash(value)


def _failure(stage: str, error: Exception | str) -> dict[str, Any]:
    return {
        "stage": stage,
        "error_type": type(error).__name__ if isinstance(error, Exception) else None,
        "error": str(error),
        "handling": (
            "stop before any later gate; retain the immutable prerequisite and "
            "correct only the failing bound input or active canary"
        ),
    }


def _status_for_stage(stage: str) -> str:
    return {
        "v3r11_prerequisite": NO_GO_PREREQUISITE,
        "g32_binary": NO_GO_BINARY,
        "active_control": NO_GO_CONTROL,
        "active_shadow": NO_GO_SHADOW,
    }.get(stage, NO_GO_INTERNAL)


def _validate_prerequisite_identity(value: Mapping[str, Any]) -> None:
    implementation = _mapping(value.get("implementation"), "implementation")
    stage0 = _mapping(value.get("stage0"), "stage0")
    stage1 = _mapping(value.get("stage1"), "stage1")
    if (
        value.get("schema") != v3r11_auditor.SCHEMA
        or value.get("synthetic_revision_id")
        != v3r11_auditor.SYNTHETIC_REVISION_ID
        or value.get("campaign_revision_id")
        != v3r11_auditor.CAMPAIGN_REVISION_ID
        or value.get("historical_control_revision_id")
        != HISTORICAL_CONTROL_REVISION_ID
        or value.get("status") != v3r11_auditor.SYNTHETIC_PASS
        or value.get("decision") != v3r11_auditor.SYNTHETIC_PASS
        or value.get("synthetic_pass") is not True
        or value.get("p1_review_authorized") is not False
        or value.get("implementation_head") != FROZEN_V3R11_IMPLEMENTATION_HEAD
        or implementation.get("head") != FROZEN_V3R11_IMPLEMENTATION_HEAD
        or value.get("g32_binary_sha256") != FROZEN_G32_BINARY_SHA256
        or stage0.get("pass") is not True
        or stage0.get("status") != v3r11_auditor.STAGE0_PASS
        or stage1.get("pass") is not True
        or stage1.get("status") != "V3R11_STAGE1_PASS"
    ):
        raise CampaignError("frozen V3R11 identity or Stage 0/1 PASS changed")


def _synthetic_summary(
    value: Mapping[str, Any], file_sha256: str, path: Path
) -> dict[str, Any]:
    stage0 = _mapping(value.get("stage0"), "stage0")
    stage1 = _mapping(value.get("stage1"), "stage1")
    safety = _mapping(stage1.get("safety_regression"), "stage1.safety")
    identification = _mapping(
        stage1.get("identification"), "stage1.identification"
    )
    return {
        "path": str(path),
        "file_sha256": file_sha256,
        "artifact_content_sha256": value.get("artifact_content_sha256"),
        "synthetic_revision_id": value.get("synthetic_revision_id"),
        "historical_control_revision_id": value.get(
            "historical_control_revision_id"
        ),
        "implementation_head": value.get("implementation_head"),
        "g32_binary_sha256": value.get("g32_binary_sha256"),
        "status": value.get("status"),
        "stage0_status": stage0.get("status"),
        "stage1_status": stage1.get("status"),
        "case_count": len(safety.get("cases", []))
        + len(identification.get("cases", [])),
        "safety_case_count": len(safety.get("cases", [])),
        "identification_case_count": len(identification.get("cases", [])),
        "validation": "V3R11_SELECTOR_FULL_DEEP_REPLAY_PASS",
        "reuse_only": True,
        "synthetic_executor_call_count": 0,
    }


def _control_summary(
    value: Mapping[str, Any], file_sha256: str, path: Path
) -> dict[str, Any]:
    scales = _mapping(value.get("scales"), "active control scales")
    scale_summary: dict[str, Any] = {}
    for name in ("1x", "2x"):
        scale = _mapping(scales.get(name), f"active control {name}")
        selection = _mapping(scale.get("selection"), f"active control {name} selection")
        control = _mapping(scale.get("control"), f"active control {name} payload")
        audit = _mapping(control.get("audit"), f"active control {name} audit")
        scale_summary[name] = {
            "status": scale.get("status"),
            "pass": scale.get("pass"),
            "selected_count": selection.get("selected_segment_count"),
            "qualifying_event_count": audit.get("qualifying_event_count"),
        }
    return {
        "path": str(path),
        "file_sha256": file_sha256,
        "artifact_content_sha256": value.get("artifact_content_sha256"),
        "status": value.get("status"),
        "pass": value.get("pass"),
        "active_control_revision_id": value.get("control_revision_id"),
        "historical_control_revision_id": value.get(
            "historical_control_revision_id"
        ),
        "selection_basis": value.get("selection_basis"),
        "formal_inference_eligible": value.get("formal_inference_eligible"),
        "scales": scale_summary,
        "validation": "V3R12_ACTIVE_CONTROL_FULL_DEEP_REPLAY_PASS",
    }


def _validate_shadow_pass(value: Mapping[str, Any]) -> dict[str, Any]:
    scales = _mapping(value.get("scales"), "active shadow scales")
    scale_checks: dict[str, Any] = {}
    passed = (
        value.get("schema") == active.SHADOW_GATE_SCHEMA
        and value.get("protocol_id") == active.PROTOCOL_ID
        and value.get("campaign_revision_id") == CAMPAIGN_REVISION_ID
        and value.get("active_control_revision_id") == ACTIVE_CONTROL_REVISION_ID
        and value.get("historical_control_revision_id")
        == HISTORICAL_CONTROL_REVISION_ID
        and value.get("status") == active.SHADOW_PASS
        and value.get("pass") is True
        and value.get("selection_basis") == active.SELECTION_BASIS
        and value.get("selection_role") == active.SELECTION_ROLE
        and value.get("diagnostic_origin") == active.DIAGNOSTIC_ORIGIN
        and value.get("formal_inference_eligible") is False
        and value.get("prerequisite_artifact_file_sha256")
        == FROZEN_SYNTHETIC_FILE_SHA256
        and value.get("prerequisite_implementation_head")
        == FROZEN_V3R11_IMPLEMENTATION_HEAD
        and value.get("g32_binary_sha256") == FROZEN_G32_BINARY_SHA256
        and set(scales) == {"1x", "2x"}
    )
    for name in ("1x", "2x"):
        scale = _mapping(scales.get(name), f"active shadow {name}")
        checks = _mapping(scale.get("checks"), f"active shadow {name} checks")
        admission_count = scale.get("admitted_node49_upstream53_count")
        admitted = (
            isinstance(admission_count, int)
            and not isinstance(admission_count, bool)
            and admission_count >= 1
            and checks.get("node49_upstream53_admitted") is True
        )
        all_checks = bool(checks) and all(check is True for check in checks.values())
        scale_pass = scale.get("pass") is True and all_checks and admitted
        scale_checks[name] = {
            "pass": scale_pass,
            "all_checks_pass": all_checks,
            "node49_upstream53_admitted": admitted,
            "admitted_node49_upstream53_count": admission_count,
        }
        passed = passed and scale_pass
    if not passed:
        raise CampaignError("active V3R12 shadow did not pass every 1x/2x check and admission gate")
    return {"pass": True, "scales": scale_checks}


def _run_p0_campaign_core(
    *,
    synthetic_artifact: Path,
    control_artifact: Path,
    g32_binary: Path,
    expected_synthetic_file_sha256: str,
    expected_g32_binary_sha256: str,
    expected_implementation_head: str,
    executor: Executor,
    synthetic_loader: SyntheticLoader,
    control_loader: ControlLoader,
    shadow_runner: ShadowRunner,
    shadow_validator: ShadowValidator,
    historical_auditor: Any = v3r11_auditor,
) -> dict[str, Any]:
    """Collect a candidate with injectable dependencies and no signing authority."""

    failure: dict[str, Any] | None = None
    synthetic_summary: dict[str, Any] | None = None
    control_summary: dict[str, Any] | None = None
    shadow_result: dict[str, Any] | None = None
    shadow_validation: Mapping[str, Any] | None = None
    control_file_sha256: str | None = None

    stage = "v3r11_prerequisite"
    try:
        if (
            expected_synthetic_file_sha256 != FROZEN_SYNTHETIC_FILE_SHA256
            or expected_g32_binary_sha256 != FROZEN_G32_BINARY_SHA256
            or expected_implementation_head != FROZEN_V3R11_IMPLEMENTATION_HEAD
        ):
            raise CampaignError("composer prerequisite constants are not the registered V3R11 identity")
        if not synthetic_artifact.is_file():
            raise CampaignError("registered V3R11 synthetic artifact is missing")
        actual_synthetic_sha = _file_sha256(synthetic_artifact)
        if actual_synthetic_sha != expected_synthetic_file_sha256:
            raise CampaignError("registered V3R11 synthetic artifact file identity changed")

        preloaded = _read_json(synthetic_artifact)
        _validate_prerequisite_identity(preloaded)
        source_bundle = _mapping(preloaded.get("source_bundle"), "source_bundle")
        proxy = FrozenSourceAuditorProxy(
            historical_auditor, source_bundle, synthetic_artifact
        )
        loaded_synthetic, replayed_file_sha = synthetic_loader(
            synthetic_artifact,
            expected_file_sha256=expected_synthetic_file_sha256,
            expected_g32_binary_sha256=expected_g32_binary_sha256,
            auditor=proxy,
        )
        if replayed_file_sha != expected_synthetic_file_sha256:
            raise CampaignError("V3R11 deep loader returned a different file identity")
        _validate_prerequisite_identity(loaded_synthetic)
        synthetic_summary = _synthetic_summary(
            loaded_synthetic, replayed_file_sha, synthetic_artifact
        )

        stage = "g32_binary"
        if not g32_binary.is_file():
            raise CampaignError("registered historical G32 binary is missing")
        actual_binary_sha = _file_sha256(g32_binary)
        if actual_binary_sha != expected_g32_binary_sha256:
            raise CampaignError("active shadow binary differs from the V3R11 synthetic binary")

        stage = "active_control"
        if not control_artifact.is_file():
            raise CampaignError("registered V3R12 active control artifact is missing")
        control_file_sha256 = _file_sha256(control_artifact)
        loaded_control, replayed_control_sha = control_loader(
            control_artifact,
            expected_file_sha256=control_file_sha256,
        )
        if replayed_control_sha != control_file_sha256:
            raise CampaignError("active control deep loader returned a different file identity")
        control_summary = _control_summary(
            loaded_control, replayed_control_sha, control_artifact
        )

        stage = "active_shadow"
        shadow_result = dict(
            _mapping(
                shadow_runner(
                    control_artifact,
                    g32_binary,
                    executor,
                    expected_control_file_sha256=control_file_sha256,
                    prerequisite=loaded_synthetic,
                    prerequisite_file_sha256=expected_synthetic_file_sha256,
                    expected_g32_binary_sha256=expected_g32_binary_sha256,
                ),
                "active shadow result",
            )
        )
        deep_shadow = _mapping(
            shadow_validator(
                shadow_result,
                expected_control_file_sha256=control_file_sha256,
                expected_prerequisite_file_sha256=expected_synthetic_file_sha256,
                expected_g32_binary_sha256=expected_g32_binary_sha256,
            ),
            "active shadow deep validation",
        )
        if dict(deep_shadow) != shadow_result:
            raise CampaignError("active shadow deep replay returned different evidence")
        local_shadow_validation = _validate_shadow_pass(shadow_result)
        shadow_validation = {
            **local_shadow_validation,
            "validation": "V3R12_ACTIVE_SHADOW_FULL_DEEP_REPLAY_PASS",
        }
    except Exception as error:
        failure = _failure(stage, error)

    pipeline_pass = failure is None
    status = TEST_ONLY_PASS if pipeline_pass else _status_for_stage(stage)
    return _with_content_hash(
        {
            "schema": CANDIDATE_SCHEMA,
            "protocol_id": active.PROTOCOL_ID,
            "campaign_revision_id": CAMPAIGN_REVISION_ID,
            "historical_control_revision_id": HISTORICAL_CONTROL_REVISION_ID,
            "active_control_revision_id": ACTIVE_CONTROL_REVISION_ID,
            "status": status,
            "decision": status,
            "pass": False,
            "pipeline_candidate_pass": pipeline_pass,
            "p1_review_authorized": False,
            "authority": "TEST_ONLY_NO_FINAL_GO_AUTHORITY",
            "sequence": list(CAMPAIGN_SEQUENCE),
            "canary_scope": {
                "selection_basis": active.SELECTION_BASIS,
                "selection_role": active.SELECTION_ROLE,
                "diagnostic_origin": active.DIAGNOSTIC_ORIGIN,
                "selection_outcome_blind": False,
                "formal_inference_eligible": False,
                "effect_estimate": False,
                "interpretation": (
                    "real-path engineering canary; not an outcome-blind cohort or effect estimate"
                ),
            },
            "synthetic_prerequisite": synthetic_summary,
            "g32_binary": {
                "path": str(g32_binary),
                "expected_sha256": expected_g32_binary_sha256,
            },
            "active_control": control_summary,
            "active_shadow": shadow_result,
            "active_shadow_validation": deepcopy(dict(shadow_validation))
            if shadow_validation is not None
            else None,
            "failure": failure,
        }
    )


def _promote_formal_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    unhashed = {key: deepcopy(item) for key, item in candidate.items() if key != "artifact_content_sha256"}
    passed = candidate.get("pipeline_candidate_pass") is True and candidate.get("failure") is None
    unhashed.update(
        {
            "schema": SCHEMA,
            "status": FINAL_GO
            if passed
            else candidate.get("status", NO_GO_INTERNAL),
            "decision": FINAL_GO
            if passed
            else candidate.get("decision", NO_GO_INTERNAL),
            "pass": passed,
            "p1_review_authorized": passed,
            "authority": (
                "FORMAL_FIXED_PATH_REUSE_ONLY_COMPOSER"
                if passed
                else "FORMAL_FAIL_CLOSED_COMPOSER"
            ),
        }
    )
    return _with_content_hash(unhashed)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")


def _append_only_publish_bundle(artifacts: Mapping[Path, bytes]) -> None:
    """Publish JSON and report together, rolling back files linked by this call."""

    existing = [str(path) for path in artifacts if path.exists()]
    if existing:
        raise CampaignError(f"append-only output already exists: {existing}")
    staged: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for destination, payload in artifacts.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            )
            temporary = Path(handle.name)
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temporary, destination))
        if any(destination.exists() for _temporary, destination in staged):
            raise CampaignError("append-only output appeared during staging")
        for temporary, destination in staged:
            os.link(temporary, destination)
            published.append(destination)
    except Exception:
        for destination in reversed(published):
            destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _destination in staged:
            temporary.unlink(missing_ok=True)


def render_report(result: Mapping[str, Any]) -> str:
    synthetic = result.get("synthetic_prerequisite") or {}
    control = result.get("active_control") or {}
    shadow = result.get("active_shadow") or {}
    lines = [
        "# G4IRSF32 V3R12 P0 campaign",
        "",
        f"- Decision: `{result.get('decision')}`",
        f"- P1 review allowed: `{str(result.get('p1_review_authorized')).lower()}`",
        f"- Historical control revision: `{HISTORICAL_CONTROL_REVISION_ID}`",
        f"- Active control revision: `{ACTIVE_CONTROL_REVISION_ID}`",
        "",
        "The 144 synthetic cases were not executed again. The fixed V3R11 artifact "
        "was fully replayed through the established deep loader, and only its "
        "validation summary is included here.",
        "",
        f"- V3R11 Stage 0: `{synthetic.get('stage0_status')}`",
        f"- V3R11 Stage 1: `{synthetic.get('stage1_status')}`",
        f"- Reused case count: `{synthetic.get('case_count')}`",
        f"- Active control: `{control.get('status')}`",
        f"- Active shadow: `{shadow.get('status')}`",
        "",
        "The active selection is an outcome-informed engineering canary. It confirms "
        "real-path exercise and safety when passing, but it is neither outcome-blind "
        "evidence nor an effect estimate.",
    ]
    failure = result.get("failure")
    if isinstance(failure, Mapping):
        lines.extend(
            [
                "",
                "## Blocking issue and handling",
                "",
                f"- Stage: `{failure.get('stage')}`",
                f"- Issue: {failure.get('error')}",
                f"- Handling: {failure.get('handling')}",
            ]
        )
    return "\n".join(lines) + "\n"


def run_p0_campaign() -> dict[str, Any]:
    """Run only the registered formal paths and append the two formal outputs."""

    if OUTPUT_JSON.exists() or OUTPUT_MD.exists():
        raise CampaignError("V3R12 campaign output is append-only and already exists")
    candidate = _run_p0_campaign_core(
        synthetic_artifact=SYNTHETIC_ARTIFACT,
        control_artifact=CONTROL_ARTIFACT,
        g32_binary=G32_BINARY,
        expected_synthetic_file_sha256=FROZEN_SYNTHETIC_FILE_SHA256,
        expected_g32_binary_sha256=FROZEN_G32_BINARY_SHA256,
        expected_implementation_head=FROZEN_V3R11_IMPLEMENTATION_HEAD,
        executor=_FORMAL_EXECUTOR,
        synthetic_loader=_FORMAL_SYNTHETIC_LOADER,
        control_loader=_FORMAL_CONTROL_LOADER,
        shadow_runner=_FORMAL_SHADOW_RUNNER,
        shadow_validator=_FORMAL_SHADOW_VALIDATOR,
    )
    result = _promote_formal_candidate(candidate)
    _append_only_publish_bundle(
        {
            OUTPUT_MD: render_report(result).encode("utf-8"),
            OUTPUT_JSON: _json_bytes(result),
        }
    )
    return result


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    _parser().parse_args(argv)
    try:
        result = run_p0_campaign()
    except Exception as error:
        print(f"V3R12 campaign failed before append: {type(error).__name__}: {error}")
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("pass") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())

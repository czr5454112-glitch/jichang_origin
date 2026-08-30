#!/usr/bin/env python3
"""Compose the sole V3R11 P0 FINAL_GO from frozen synthetic and Nanning gates.

The control artifact is an input, never generated here.  A formal invocation
deep-validates that artifact and the clean G32 identity before it invokes the
synthetic runner.  It freezes the synthetic result append-only, then (and only
then) invokes the Nanning G32 shadow gate.  The final JSON and report are also
append-only; failures retain the last completed checkpoint and any separately
frozen synthetic evidence.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
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
    run_g4irsf32_v3r2_external_commit_local_virtual_shadow as synthetic,
)
from scripts.eval import run_g4irsf32_v3r3_nanning_p0_selection as nanning  # noqa: E402


SCHEMA = "czr005.g4irsf32.p0_campaign.v3r11"
CANDIDATE_SCHEMA = "czr005.g4irsf32.p0_campaign_candidate.v3r11"
PROTOCOL_ID = synthetic.PROTOCOL_ID
CONTROL_REVISION_ID = nanning.CONTROL_REVISION_ID
CAMPAIGN_REVISION_ID = synthetic.CAMPAIGN_REVISION_ID
if synthetic.COMMIT_ALIGNED_ADDENDUM_ID != CONTROL_REVISION_ID:
    raise RuntimeError(
        "synthetic and Nanning modules bind different V3R7 control revisions"
    )
FINAL_GO = synthetic.FINAL_GO
TEST_ONLY_PASS = "PASS_TEST_ONLY_V3R11_P0_CANDIDATE_NO_AUTHORITY"
NO_GO_PREFLIGHT = "NO_GO_V3R11_P0_COMPOSER_PREFLIGHT"
NO_GO_SYNTHETIC = "NO_GO_V3R11_P0_SYNTHETIC_VALIDATION"
NO_GO_IMMUTABILITY = "NO_GO_V3R11_P0_SOURCE_OR_BINARY_DRIFT"
NO_GO_SHADOW = "NO_GO_V3R11_P0_NANNING_SHADOW"
NO_GO_INTERNAL = "NO_GO_V3R11_P0_COMPOSER_INTERNAL_ERROR"
CAMPAIGN_SEQUENCE = (
    "load_v3r7_control_through_compatibility_bridge",
    "run_and_validate_v3r8_synthetic_stage0_stage1",
    "append_only_freeze_and_deep_replay_synthetic",
    "run_bound_v3r7_nanning_g32_shadow",
    "compose_v3r8_final_go",
)

OUTPUT_JSON = ROOT / "outputs/tables/g4irsf32_v3r11_p0_campaign.json"
OUTPUT_MD = ROOT / "outputs/reports/g4irsf32_v3r11_p0_campaign.md"
SYNTHETIC_ARTIFACT = synthetic.OUTPUT_JSON

# Formal dependencies and static registered paths are captured once at import.
# The public wrapper adds its one explicit resolved G32 path to that boundary;
# the injectable core below never owns FINAL_GO authority.
_FORMAL_CPP_EXECUTOR = synthetic.cpp_executor
_FORMAL_SYNTHETIC_RUNNER = synthetic.run_campaign
_FORMAL_CONTROL_LOADER = nanning.load_and_validate_control_artifact
_FORMAL_SYNTHETIC_LOADER = nanning.load_and_validate_synthetic_artifact
_FORMAL_SHADOW_RUNNER = nanning.run_g32_shadow_gate
_FORMAL_SHADOW_VALIDATOR = nanning._deep_validate_g32_shadow_result_mapping
_FORMAL_IDENTITY_RUNNER = synthetic.implementation_identity
_FORMAL_SOURCE_READER = synthetic.source_bundle_manifest
_FORMAL_BUILD_HEAD_READER = synthetic.read_g32_build_head
_FORMAL_CONTROL_PATH = Path(nanning.OUTPUT_PATH)
_FORMAL_SYNTHETIC_PATH = Path(synthetic.OUTPUT_JSON)
_FORMAL_OUTPUT_JSON = Path(OUTPUT_JSON)
_FORMAL_OUTPUT_MD = Path(OUTPUT_MD)
_FORMAL_G31_BINARY = Path(synthetic.G31_BINARY)
_FORMAL_PROOF_EXECUTABLE = Path(synthetic.NATIVE_PROOF_EXE)
_FORMAL_G32_BINARY_GLOB = Path(synthetic.G32_BINARY_GLOB)
_FORMAL_G31_BINARY_SHA256 = str(
    nanning.FROZEN_SOURCE_HASHES[nanning.G31_BINARY]
)
_FORMAL_REGISTERED_PATHS = {
    "control_artifact": _FORMAL_CONTROL_PATH,
    "synthetic_artifact": _FORMAL_SYNTHETIC_PATH,
    "output_json": _FORMAL_OUTPUT_JSON,
    "output_md": _FORMAL_OUTPUT_MD,
}

Executor = Callable[..., Mapping[str, Any]]
FORMAL_EXECUTION_BLOCKED_REASON = synthetic.FORMAL_EXECUTION_BLOCKED_REASON
if nanning.FORMAL_EXECUTION_BLOCKED_REASON != FORMAL_EXECUTION_BLOCKED_REASON:
    raise RuntimeError("synthetic and Nanning formal execution blocks differ")


class CampaignError(RuntimeError):
    """A fail-closed P0 composition error."""


def _portable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            portable_key = str(key)
            if portable_key in result:
                raise CampaignError(
                    f"JSON object key collision after string conversion: {portable_key!r}"
                )
            result[portable_key] = _portable(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise CampaignError("non-finite numeric evidence is forbidden")
    return value


def _json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    options: dict[str, Any] = {
        "sort_keys": True,
        "ensure_ascii": False,
        "allow_nan": False,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    suffix = "\n" if pretty else ""
    return (json.dumps(_portable(value), **options) + suffix).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _head_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _reject_json_constant(value: str) -> None:
    raise CampaignError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CampaignError(f"duplicate JSON object key is forbidden: {key!r}")
        result[key] = value
    return result


def read_strict_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_object,
    )


def with_content_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    if "artifact_content_sha256" in value:
        raise CampaignError("artifact already contains a content hash")
    result = _portable(deepcopy(dict(value)))
    if not isinstance(result, dict):
        raise CampaignError("artifact must normalize to a JSON object")
    result["artifact_content_sha256"] = canonical_sha256(result)
    return result


def verify_content_hash(value: Mapping[str, Any]) -> str:
    expected = value.get("artifact_content_sha256")
    if not _sha256_text(expected):
        raise CampaignError("artifact lacks a lowercase canonical content hash")
    unhashed = {
        key: item for key, item in value.items() if key != "artifact_content_sha256"
    }
    actual = canonical_sha256(unhashed)
    if actual != expected:
        raise CampaignError("artifact canonical content hash mismatch")
    return actual


def _append_only_write(path: Path, payload: bytes) -> None:
    """Atomically publish a new file without replacing an existing artifact."""

    _append_only_publish_bundle({path: payload})


def _append_only_publish_bundle(artifacts: Mapping[Path, bytes]) -> None:
    """Publish an append-only bundle and roll back only files linked by this call."""

    if not artifacts:
        raise CampaignError("append-only publication bundle must not be empty")
    existing = [str(path) for path in artifacts if path.exists()]
    if existing:
        raise FileExistsError(f"append-only evidence already exists: {existing}")
    staged: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for destination, payload in artifacts.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
            )
            temporary = Path(handle.name)
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temporary, destination))
        if any(destination.exists() for _temporary, destination in staged):
            raise FileExistsError("append-only evidence target appeared during staging")
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


def _publish_final_artifacts(
    *,
    json_path: Path,
    json_payload: bytes,
    report_path: Path,
    report_payload: bytes,
) -> None:
    """Publish report first and authoritative JSON last as the commit marker.

    An exact report orphan is recoverable because it is byte-identical to the
    report being published now.  A different orphan or any existing authority
    JSON is never overwritten.
    """

    if json_path.exists():
        raise FileExistsError(f"authoritative final JSON already exists: {json_path}")
    if report_path.exists():
        if report_path.is_symlink() or report_path.read_bytes() != report_payload:
            raise FileExistsError(
                f"unverified report orphan cannot be replaced: {report_path}"
            )
        report_path.unlink()

    staged: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for destination, payload in (
            (report_path, report_payload),
            (json_path, json_payload),
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
            )
            temporary = Path(handle.name)
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temporary, destination))
        if json_path.exists() or report_path.exists():
            raise FileExistsError("final evidence target appeared during staging")
        for temporary, destination in staged:  # JSON is deliberately second.
            os.link(temporary, destination)
            published.append(destination)
    except Exception:
        for destination in reversed(published):
            destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _destination in staged:
            temporary.unlink(missing_ok=True)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CampaignError(f"{label} must be an object")
    return value


def _object_rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise CampaignError(f"{label} must be an array of objects")
    return list(value)


def _gate(name: str, passed: bool, evidence: Any = None) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed), "evidence": _portable(evidence)}


def _validate_source_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    files = _object_rows(value.get("files"), "source_bundle.files")
    paths = [row.get("path") for row in files]
    if (
        not files
        or len(paths) != len(set(paths))
        or any(not isinstance(path, str) or not path for path in paths)
        or any(not _sha256_text(row.get("sha256")) for row in files)
        or value.get("sha256") != canonical_sha256(files)
    ):
        raise CampaignError("source bundle manifest is incomplete or self-inconsistent")
    return deepcopy(dict(value))


def _all_gates_pass(value: Any, label: str) -> bool:
    gates = _object_rows(value, label)
    return bool(gates) and all(gate.get("pass") is True for gate in gates)


def validate_synthetic_result(
    value: Mapping[str, Any],
    *,
    expected_identity: Mapping[str, Any],
    expected_source_bundle: Mapping[str, Any],
    expected_g32_binary_sha256: str,
    auditor: Any = synthetic,
) -> dict[str, Any]:
    """Deeply reject a merely labelled or internally drifting synthetic pass."""

    result = _mapping(value, "synthetic result")
    protocol = _mapping(result.get("protocol"), "synthetic.protocol")
    stage0 = _mapping(result.get("stage0"), "synthetic.stage0")
    stage1 = _mapping(result.get("stage1"), "synthetic.stage1")
    identity = _mapping(result.get("implementation"), "synthetic.implementation")
    source = _mapping(result.get("source_bundle"), "synthetic.source_bundle")
    checkpoints = _mapping(
        result.get("source_bundle_checkpoints"), "synthetic.source checkpoints"
    )
    native_proof = _mapping(stage0.get("native_proof"), "synthetic.native proof")
    protocol_cohorts = _mapping(protocol.get("cohorts"), "synthetic.protocol.cohorts")
    safety_protocol = _mapping(
        protocol_cohorts.get("safety_regression"),
        "synthetic.protocol.cohorts.safety_regression",
    )
    identification_protocol = _mapping(
        protocol_cohorts.get("identification"),
        "synthetic.protocol.cohorts.identification",
    )
    safety_stage = _mapping(
        stage1.get("safety_regression"), "synthetic.stage1.safety_regression"
    )
    identification_stage = _mapping(
        stage1.get("identification"), "synthetic.stage1.identification"
    )
    safety_protocol_cases = _object_rows(
        safety_protocol.get("cases"), "synthetic.protocol.safety.cases"
    )
    identification_protocol_cases = _object_rows(
        identification_protocol.get("cases"),
        "synthetic.protocol.identification.cases",
    )
    safety_cases = _object_rows(
        safety_stage.get("cases"), "synthetic.stage1.safety.cases"
    )
    identification_cases = _object_rows(
        identification_stage.get("cases"),
        "synthetic.stage1.identification.cases",
    )
    safety_observations = _object_rows(
        safety_stage.get("observations"), "synthetic.stage1.safety.observations"
    )
    identification_observations = _object_rows(
        identification_stage.get("observations"),
        "synthetic.stage1.identification.observations",
    )
    safety_pairs = _object_rows(
        safety_stage.get("pairs"), "synthetic.stage1.safety.pairs"
    )
    identification_pairs = _object_rows(
        identification_stage.get("pairs"),
        "synthetic.stage1.identification.pairs",
    )
    safety_protocol_ids = [row.get("case_id") for row in safety_protocol_cases]
    identification_protocol_ids = [
        row.get("case_id") for row in identification_protocol_cases
    ]
    safety_case_ids = [row.get("case_id") for row in safety_cases]
    identification_case_ids = [row.get("case_id") for row in identification_cases]
    head = expected_identity.get("head")

    checks = {
        "synthetic_only_status": (
            result.get("schema") == auditor.SCHEMA
            and result.get("synthetic_revision_id") == auditor.SYNTHETIC_REVISION_ID
            and result.get("campaign_revision_id") == CAMPAIGN_REVISION_ID
            and result.get("historical_control_revision_id") == CONTROL_REVISION_ID
            and result.get("status") == auditor.SYNTHETIC_PASS
            and result.get("decision") == auditor.SYNTHETIC_PASS
            and result.get("synthetic_pass") is True
            and result.get("nanning_p0_status")
            == "PENDING_NOT_RUN_BY_SYNTHETIC_RUNNER"
            and result.get("p1_review_authorized") is False
            and result.get("decision") != FINAL_GO
        ),
        "protocol_exact": (
            protocol.get("schema") == auditor.SCHEMA
            and protocol.get("protocol_id") == PROTOCOL_ID
            and protocol.get("synthetic_revision_id") == auditor.SYNTHETIC_REVISION_ID
            and protocol.get("campaign_revision_id") == CAMPAIGN_REVISION_ID
            and protocol.get("historical_control_revision_id") == CONTROL_REVISION_ID
            and protocol.get("case_count") == 144
            and set(protocol_cohorts) == {"safety_regression", "identification"}
            and safety_protocol.get("case_count") == 120
            and identification_protocol.get("case_count") == 24
            and len(safety_protocol_cases) == 120
            and len(identification_protocol_cases) == 24
            and len(set(safety_protocol_ids)) == 120
            and len(set(identification_protocol_ids)) == 24
            and not set(safety_protocol_ids) & set(identification_protocol_ids)
            and safety_protocol.get("cases_sha256")
            == canonical_sha256(safety_protocol_cases)
            and identification_protocol.get("cases_sha256")
            == canonical_sha256(identification_protocol_cases)
            and protocol.get("cohorts_sha256") == canonical_sha256(protocol_cohorts)
        ),
        "stage0_exact_pass": (
            stage0.get("pass") is True
            and stage0.get("status") == auditor.STAGE0_PASS
            and _all_gates_pass(stage0.get("gates"), "synthetic.stage0.gates")
        ),
        "stage1_exact_pass": (
            stage1.get("pass") is True
            and stage1.get("status") == "V3R11_STAGE1_PASS"
            and _all_gates_pass(stage1.get("gates"), "synthetic.stage1.gates")
            and safety_stage.get("pass") is True
            and identification_stage.get("pass") is True
            and len(safety_cases) == 120
            and len(identification_cases) == 24
            and len(set(safety_case_ids)) == 120
            and len(set(identification_case_ids)) == 24
            and safety_case_ids == safety_protocol_ids
            and identification_case_ids == identification_protocol_ids
            and stage1.get("manifest_sha256") == protocol.get("cohorts_sha256")
            and safety_stage.get("manifest_sha256")
            == safety_protocol.get("cases_sha256")
            and identification_stage.get("manifest_sha256")
            == identification_protocol.get("cases_sha256")
        ),
        "stage1_evidence_self_hashes": (
            safety_stage.get("observation_count") == len(safety_observations)
            and safety_stage.get("observations_sha256")
            == canonical_sha256(safety_observations)
            and safety_stage.get("pair_count") == len(safety_pairs)
            and safety_stage.get("pairs_sha256") == canonical_sha256(safety_pairs)
            and identification_stage.get("observation_count")
            == len(identification_observations)
            and identification_stage.get("observations_sha256")
            == canonical_sha256(identification_observations)
            and identification_stage.get("pair_count") == len(identification_pairs)
            and identification_stage.get("pairs_sha256")
            == canonical_sha256(identification_pairs)
        ),
        "clean_identity_exact": (
            identity == expected_identity
            and identity.get("pass") is True
            and _head_text(head)
            and _all_gates_pass(
                identity.get("gates"), "synthetic.implementation.gates"
            )
            and result.get("implementation_head") == head
        ),
        "source_checkpoints_exact": (
            source == expected_source_bundle
            and checkpoints.get("start") == expected_source_bundle
            and checkpoints.get("after_stage0") == expected_source_bundle
            and checkpoints.get("after_stage1") == expected_source_bundle
        ),
        "binary_and_build_head_exact": (
            result.get("g32_binary_sha256") == expected_g32_binary_sha256
            and native_proof.get("pass") is True
            and native_proof.get("g32_binary_sha256")
            == expected_g32_binary_sha256
            and native_proof.get("build_head") == head
            and native_proof.get("source_bundle") == expected_source_bundle
        ),
    }
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise CampaignError(f"synthetic pass failed deep validation: {failed}")
    return {
        "pass": True,
        "checks": checks,
        "status": result.get("status"),
        "implementation_head": head,
        "case_count": len(safety_cases) + len(identification_cases),
        "safety_case_count": len(safety_cases),
        "identification_case_count": len(identification_cases),
        "observation_count": len(safety_observations) + len(identification_observations),
        "pair_count": len(safety_pairs) + len(identification_pairs),
    }


def validate_shadow_result(
    value: Mapping[str, Any],
    *,
    expected_control_file_sha256: str,
    expected_synthetic_file_sha256: str,
    expected_g32_binary_sha256: str,
    expected_implementation_head: str,
) -> dict[str, Any]:
    """Validate the compositional bindings even when the shadow gate is NO-GO."""

    result = _mapping(value, "Nanning shadow result")
    content_sha = verify_content_hash(result)
    scales = _mapping(result.get("scales"), "Nanning shadow scales")
    scale_keys_ok = set(scales).issubset({"1x", "2x"})
    both_pass = set(scales) == {"1x", "2x"} and all(
        _mapping(scales[name], f"shadow.{name}").get("pass") is True
        for name in ("1x", "2x")
    )
    declared_pass = result.get("pass") is True
    bindings = {
        "schema": result.get("schema") == nanning.SHADOW_GATE_SCHEMA,
        "protocol": result.get("protocol_id") == PROTOCOL_ID,
        "campaign_revision": result.get("campaign_revision_id")
        == CAMPAIGN_REVISION_ID,
        "control_revision": result.get("control_revision_id")
        == CONTROL_REVISION_ID,
        "control_file": result.get("control_artifact_file_sha256")
        == expected_control_file_sha256,
        "synthetic_file": result.get("synthetic_artifact_file_sha256")
        == expected_synthetic_file_sha256,
        "synthetic_decision": result.get("synthetic_decision")
        == synthetic.SYNTHETIC_PASS,
        "implementation_head": result.get("synthetic_implementation_head")
        == expected_implementation_head,
        "g32_binary": result.get("g32_binary_sha256")
        == expected_g32_binary_sha256,
        "scale_structure": scale_keys_ok,
        "pass_consistency": declared_pass == both_pass,
        "status_consistency": (
            result.get("status") == nanning.SHADOW_PASS
            if declared_pass
            else result.get("status") in {nanning.SHADOW_NO_EVENT, nanning.SHADOW_NO_GO}
        ),
    }
    if not all(bindings.values()):
        failed = sorted(name for name, passed in bindings.items() if not passed)
        raise CampaignError(f"Nanning shadow result binding failed: {failed}")
    return {
        "pass": declared_pass,
        "checks": bindings,
        "status": result.get("status"),
        "content_sha256": content_sha,
        "attempted_scales": sorted(scales),
    }


def _capture_checkpoint(
    *,
    name: str,
    g32_binary: Path,
    control_artifact: Path,
    synthetic_artifact: Path,
    source_manifest_reader: Callable[[], Mapping[str, Any]],
    build_head_reader: Callable[[Path], str],
) -> dict[str, Any]:
    source = _validate_source_bundle(
        _mapping(source_manifest_reader(), f"{name} source bundle")
    )
    return {
        "name": name,
        "source_bundle": source,
        "g32_binary_path": str(g32_binary),
        "g32_binary_sha256": file_sha256(g32_binary),
        "g32_build_head": build_head_reader(g32_binary),
        "control_artifact_file_sha256": file_sha256(control_artifact),
        "synthetic_artifact_file_sha256": (
            file_sha256(synthetic_artifact) if synthetic_artifact.exists() else None
        ),
    }


def _checkpoint_validation(
    checkpoint: Mapping[str, Any],
    *,
    start: Mapping[str, Any],
    expected_g32_binary_sha256: str,
    expected_control_file_sha256: str,
    expected_synthetic_file_sha256: str | None,
) -> dict[str, Any]:
    checks = {
        "source_bundle_unchanged": checkpoint.get("source_bundle")
        == start.get("source_bundle"),
        "g32_binary_unchanged": checkpoint.get("g32_binary_sha256")
        == expected_g32_binary_sha256,
        "g32_build_head_unchanged": checkpoint.get("g32_build_head")
        == start.get("g32_build_head"),
        "control_artifact_unchanged": checkpoint.get(
            "control_artifact_file_sha256"
        )
        == expected_control_file_sha256,
        "synthetic_artifact_exact": checkpoint.get(
            "synthetic_artifact_file_sha256"
        )
        == expected_synthetic_file_sha256,
    }
    return {"pass": all(checks.values()), "checks": checks}


def _failure(stage: str, error: BaseException | str) -> dict[str, Any]:
    if isinstance(error, BaseException):
        error_type = type(error).__name__
        message = str(error)
    else:
        error_type = "GateFailure"
        message = error
    return {
        "stage": stage,
        "error_type": error_type,
        "error": message,
    }


def _status_for_failure(
    failure: Mapping[str, Any],
    synthetic_result: Mapping[str, Any] | None,
    shadow_result: Mapping[str, Any] | None,
) -> str:
    stage = failure.get("stage")
    if stage == "preflight":
        return NO_GO_PREFLIGHT
    if stage == "synthetic":
        candidate = synthetic_result.get("status") if synthetic_result else None
        return candidate if isinstance(candidate, str) and candidate.startswith("NO_GO_") else NO_GO_SYNTHETIC
    if stage in {"after_synthetic_checkpoint", "after_shadow_checkpoint"}:
        return NO_GO_IMMUTABILITY
    if stage == "nanning_shadow":
        candidate = shadow_result.get("status") if shadow_result else None
        return candidate if isinstance(candidate, str) and candidate.startswith("NO_GO_") else NO_GO_SHADOW
    return NO_GO_INTERNAL


def _run_p0_campaign_core(
    *,
    control_artifact: Path,
    expected_control_file_sha256: str,
    synthetic_artifact: Path,
    g32_binary: Path,
    expected_g32_binary_sha256: str,
    executor: Executor,
    output_json: Path = OUTPUT_JSON,
    output_md: Path = OUTPUT_MD,
    synthetic_run_kwargs: Mapping[str, Any] | None = None,
    synthetic_runner: Callable[..., Mapping[str, Any]] | None = None,
    control_loader: Callable[..., tuple[dict[str, Any], str]] | None = None,
    synthetic_loader: Callable[..., tuple[dict[str, Any], str]] | None = None,
    shadow_runner: Callable[..., Mapping[str, Any]] | None = None,
    identity_runner: Callable[[], Mapping[str, Any]] | None = None,
    source_manifest_reader: Callable[[], Mapping[str, Any]] | None = None,
    build_head_reader: Callable[[Path], str] | None = None,
    registered_paths: Mapping[str, Path] | None = None,
    _test_only: bool = False,
) -> dict[str, Any]:
    """Collect a test-only candidate; this function can never issue FINAL_GO."""

    if FORMAL_EXECUTION_BLOCKED_REASON and not _test_only:
        raise CampaignError(FORMAL_EXECUTION_BLOCKED_REASON)
    if _test_only:
        supplied = (
            (executor, _FORMAL_CPP_EXECUTOR),
            (synthetic_runner, _FORMAL_SYNTHETIC_RUNNER),
            (control_loader, _FORMAL_CONTROL_LOADER),
            (synthetic_loader, _FORMAL_SYNTHETIC_LOADER),
            (shadow_runner, _FORMAL_SHADOW_RUNNER),
            (identity_runner, _FORMAL_IDENTITY_RUNNER),
            (source_manifest_reader, _FORMAL_SOURCE_READER),
            (build_head_reader, _FORMAL_BUILD_HEAD_READER),
        )
        if registered_paths is None or any(
            actual is None or actual is formal for actual, formal in supplied
        ):
            raise CampaignError(
                "test-only core requires explicit non-formal dependencies and paths"
            )

    for label, path in {
        "control_artifact": control_artifact,
        "synthetic_artifact": synthetic_artifact,
        "g32_binary": g32_binary,
        "output_json": output_json,
        "output_md": output_md,
    }.items():
        if not isinstance(path, Path):
            raise TypeError(f"{label} must be an explicit pathlib.Path")
    required_paths = dict(
        registered_paths
        or {
            "control_artifact": nanning.OUTPUT_PATH,
            "synthetic_artifact": synthetic.OUTPUT_JSON,
            "g32_binary": g32_binary,
            "output_json": OUTPUT_JSON,
            "output_md": OUTPUT_MD,
        }
    )
    actual_paths = {
        "control_artifact": control_artifact,
        "synthetic_artifact": synthetic_artifact,
        "g32_binary": g32_binary,
        "output_json": output_json,
        "output_md": output_md,
    }
    if _test_only and any(
        name in _FORMAL_REGISTERED_PATHS
        and path.resolve() == _FORMAL_REGISTERED_PATHS[name].resolve()
        for name, path in actual_paths.items()
    ):
        raise CampaignError("test-only core cannot use registered formal paths")
    if set(required_paths) != set(actual_paths) or any(
        actual_paths[name].resolve() != required_paths[name].resolve()
        for name in actual_paths
    ):
        raise CampaignError("formal artifact paths differ from the registered paths")
    if output_json.exists():
        raise FileExistsError(
            f"append-only authoritative final evidence already exists: {output_json}"
        )

    selected_synthetic_runner = synthetic_runner or synthetic.run_campaign
    selected_control_loader = (
        control_loader or nanning.load_and_validate_control_artifact
    )
    selected_synthetic_loader = (
        synthetic_loader or nanning.load_and_validate_synthetic_artifact
    )
    selected_shadow_runner = shadow_runner or nanning.run_g32_shadow_gate
    selected_identity_runner = identity_runner or synthetic.implementation_identity
    selected_source_reader = source_manifest_reader or synthetic.source_bundle_manifest
    selected_build_head_reader = build_head_reader or synthetic.read_g32_build_head
    run_kwargs = dict(synthetic_run_kwargs or {})

    preflight_gates: list[dict[str, Any]] = []
    checkpoints: dict[str, Any] = {
        "start": None,
        "after_synthetic_freeze": None,
        "after_nanning_shadow": None,
    }
    control_binding: dict[str, Any] = {
        "path": str(control_artifact),
        "expected_file_sha256": expected_control_file_sha256,
        "file_sha256": None,
        "content_sha256": None,
        "schema": None,
        "protocol_id": None,
        "revision_id": None,
        "status": None,
    }
    synthetic_binding: dict[str, Any] = {
        "path": str(synthetic_artifact),
        "file_sha256": None,
        "content_sha256": None,
        "validation": None,
        "selector_deep_validation": None,
        "partial_summary": None,
    }
    synthetic_result: Mapping[str, Any] | None = None
    shadow_result: Mapping[str, Any] | None = None
    shadow_validation: Mapping[str, Any] | None = None
    identity: Mapping[str, Any] | None = None
    source_start: Mapping[str, Any] | None = None
    binary: Path | None = None
    resumed_frozen_synthetic: Mapping[str, Any] | None = None
    failure: dict[str, Any] | None = None
    resume_existing_synthetic = synthetic_artifact.exists()

    # Preflight must complete before either runtime executor can be reached.
    try:
        executor_ok = callable(executor)
        preflight_gates.append(
            _gate(
                "candidate_executor_recorded",
                executor_ok,
                {
                    "module": getattr(executor, "__module__", None),
                    "qualname": getattr(executor, "__qualname__", None),
                },
            )
        )
        if not executor_ok:
            raise CampaignError("candidate executor is not callable")
        if not _sha256_text(expected_control_file_sha256):
            raise CampaignError("expected control SHA-256 must be explicit lowercase hex")
        if not _sha256_text(expected_g32_binary_sha256):
            raise CampaignError("expected G32 SHA-256 must be explicit lowercase hex")
        if resume_existing_synthetic and synthetic_artifact.is_symlink():
            raise CampaignError("existing synthetic evidence must not be a symlink")
        forbidden = {"executor", "g32_binary", "identity_runner"} & set(run_kwargs)
        if forbidden:
            raise CampaignError(
                f"synthetic_run_kwargs may not override composer bindings: {sorted(forbidden)}"
            )
        control, control_file_sha = selected_control_loader(
            control_artifact,
            expected_file_sha256=expected_control_file_sha256,
            auditor=synthetic,
        )
        if control_file_sha != expected_control_file_sha256:
            raise CampaignError("control loader returned a different file SHA-256")
        control_binding.update(
            file_sha256=control_file_sha,
            content_sha256=control.get("artifact_content_sha256"),
            schema=control.get("schema"),
            protocol_id=control.get("protocol_id"),
            revision_id=control.get("control_revision_id"),
            status=control.get("status"),
        )
        control_contract = {
            "schema": control_binding["schema"] == nanning.SCHEMA,
            "protocol": control_binding["protocol_id"] == PROTOCOL_ID
            == nanning.PROTOCOL_ID,
            "revision": control_binding["revision_id"] == CONTROL_REVISION_ID,
            "status": control_binding["status"] == nanning.PASS,
        }
        for name, passed in control_contract.items():
            preflight_gates.append(
                _gate(
                    f"v3r7_control_{name}_exact",
                    passed,
                    {
                        "schema": control_binding["schema"],
                        "protocol_id": control_binding["protocol_id"],
                        "revision_id": control_binding["revision_id"],
                        "status": control_binding["status"],
                    },
                )
            )
        if not all(control_contract.values()):
            failed_contract = sorted(
                name for name, passed in control_contract.items() if not passed
            )
            raise CampaignError(
                "control artifact is not the exact frozen V3R7 PASS contract: "
                f"{failed_contract}"
            )
        preflight_gates.append(_gate("control_artifact_deep_valid", True, control_binding))

        binary = g32_binary.resolve(strict=True)
        actual_binary_sha = file_sha256(binary)
        binary_ok = (
            actual_binary_sha == expected_g32_binary_sha256
            and actual_binary_sha != _FORMAL_G31_BINARY_SHA256
        )
        preflight_gates.append(
            _gate(
                "explicit_g32_binary_exact",
                binary_ok,
                {
                    "path": str(binary),
                    "expected": expected_g32_binary_sha256,
                    "actual": actual_binary_sha,
                },
            )
        )
        if not binary_ok:
            raise CampaignError("G32 binary hash is wrong or equals frozen G31")

        identity = _mapping(selected_identity_runner(), "implementation identity")
        identity_ok = (
            identity.get("pass") is True
            and _head_text(identity.get("head"))
            and _all_gates_pass(identity.get("gates"), "implementation gates")
        )
        preflight_gates.append(_gate("clean_committed_implementation", identity_ok, identity))
        if not identity_ok:
            raise CampaignError("implementation is not a clean committed allowed HEAD")

        source_start = _validate_source_bundle(
            _mapping(selected_source_reader(), "preflight source bundle")
        )
        preflight_gates.append(
            _gate("source_bundle_self_consistent", True, source_start.get("sha256"))
        )
        build_head = selected_build_head_reader(binary)
        build_ok = _head_text(build_head) and build_head == identity.get("head")
        preflight_gates.append(
            _gate(
                "g32_build_head_matches_clean_head",
                build_ok,
                {"build_head": build_head, "implementation_head": identity.get("head")},
            )
        )
        if not build_ok:
            raise CampaignError("G32 embedded build HEAD does not match implementation HEAD")

        if resume_existing_synthetic:
            synthetic_file_sha = file_sha256(synthetic_artifact)
            deep_loaded, deep_file_sha = selected_synthetic_loader(
                synthetic_artifact,
                expected_file_sha256=synthetic_file_sha,
                expected_g32_binary_sha256=expected_g32_binary_sha256,
                auditor=synthetic,
            )
            if deep_file_sha != synthetic_file_sha:
                raise CampaignError(
                    "resumed synthetic loader returned a different file SHA-256"
                )
            synthetic_content_sha = verify_content_hash(deep_loaded)
            resumed_frozen_synthetic = deepcopy(dict(deep_loaded))
            resumed_unhashed = {
                key: item
                for key, item in deep_loaded.items()
                if key != "artifact_content_sha256"
            }
            synthetic_result = _mapping(
                resumed_unhashed, "resumed synthetic result"
            )
            local_validation = validate_synthetic_result(
                synthetic_result,
                expected_identity=identity,
                expected_source_bundle=source_start,
                expected_g32_binary_sha256=expected_g32_binary_sha256,
                auditor=synthetic,
            )
            synthetic_binding.update(
                file_sha256=synthetic_file_sha,
                content_sha256=synthetic_content_sha,
                status=synthetic_result.get("status"),
                validation=local_validation,
                selector_deep_validation={
                    "pass": True,
                    "file_sha256": deep_file_sha,
                    "content_sha256": synthetic_content_sha,
                },
                partial_summary={
                    "schema": synthetic_result.get("schema"),
                    "status": synthetic_result.get("status"),
                    "decision": synthetic_result.get("decision"),
                    "synthetic_pass": synthetic_result.get("synthetic_pass"),
                    "stage0_status": synthetic_result.get("stage0", {}).get("status"),
                    "stage1_status": synthetic_result.get("stage1", {}).get("status"),
                },
            )

        checkpoints["start"] = _capture_checkpoint(
            name="start",
            g32_binary=binary,
            control_artifact=control_artifact,
            synthetic_artifact=synthetic_artifact,
            source_manifest_reader=selected_source_reader,
            build_head_reader=selected_build_head_reader,
        )
        # This is the logical pre-synthetic boundary.  On resume the physical
        # file already exists, but selector-deep validation above proves that
        # it is the exact immutable output of this boundary.  Normalising this
        # field keeps fresh and resumed scientific evidence byte-identical.
        checkpoints["start"]["synthetic_artifact_file_sha256"] = None
        start_validation = _checkpoint_validation(
            checkpoints["start"],
            start=checkpoints["start"],
            expected_g32_binary_sha256=expected_g32_binary_sha256,
            expected_control_file_sha256=expected_control_file_sha256,
            expected_synthetic_file_sha256=None,
        )
        start_validation["checks"].update(
            source_bundle_matches_preflight=(
                checkpoints["start"]["source_bundle"] == source_start
            ),
            build_head_matches_clean_head=(
                checkpoints["start"]["g32_build_head"] == identity.get("head")
            ),
        )
        start_validation["pass"] = all(start_validation["checks"].values())
        checkpoints["start"]["validation"] = start_validation
        if not start_validation["pass"]:
            raise CampaignError("start checkpoint does not match explicit inputs")
    except Exception as error:
        preflight_gates.append(
            _gate(
                "preflight_exception",
                False,
                {"type": type(error).__name__, "error": str(error)},
            )
        )
        failure = _failure("preflight", error)

    # The synthetic runner cannot issue FINAL_GO.  Its output is frozen even
    # when it is a well-formed NO-GO or a malformed claimed pass.
    if failure is None and not resume_existing_synthetic:
        assert binary is not None and identity is not None and source_start is not None
        validation_error: Exception | None = None
        try:
            synthetic_result = _mapping(
                selected_synthetic_runner(
                    executor=executor,
                    g32_binary=binary,
                    identity_runner=lambda: deepcopy(dict(identity)),
                    **run_kwargs,
                ),
                "synthetic runner result",
            )
            synthetic_binding["partial_summary"] = {
                "schema": synthetic_result.get("schema"),
                "status": synthetic_result.get("status"),
                "decision": synthetic_result.get("decision"),
                "synthetic_pass": synthetic_result.get("synthetic_pass"),
                "stage0_status": (
                    synthetic_result.get("stage0", {}).get("status")
                    if isinstance(synthetic_result.get("stage0"), Mapping)
                    else None
                ),
                "stage1_status": (
                    synthetic_result.get("stage1", {}).get("status")
                    if isinstance(synthetic_result.get("stage1"), Mapping)
                    else None
                ),
            }
            try:
                synthetic_binding["validation"] = validate_synthetic_result(
                    synthetic_result,
                    expected_identity=identity,
                    expected_source_bundle=source_start,
                    expected_g32_binary_sha256=expected_g32_binary_sha256,
                    auditor=synthetic,
                )
            except Exception as error:
                validation_error = error

            frozen_synthetic = with_content_hash(synthetic_result)
            _append_only_write(
                synthetic_artifact, _json_bytes(frozen_synthetic, pretty=True)
            )
            reread = _mapping(
                read_strict_json(synthetic_artifact), "frozen synthetic artifact"
            )
            synthetic_content_sha = verify_content_hash(reread)
            if reread != frozen_synthetic:
                raise CampaignError("frozen synthetic artifact changed on strict reread")
            synthetic_file_sha = file_sha256(synthetic_artifact)
            synthetic_binding.update(
                file_sha256=synthetic_file_sha,
                content_sha256=synthetic_content_sha,
                status=synthetic_result.get("status"),
            )
            try:
                deep_loaded, deep_file_sha = selected_synthetic_loader(
                    synthetic_artifact,
                    expected_file_sha256=synthetic_file_sha,
                    expected_g32_binary_sha256=expected_g32_binary_sha256,
                    auditor=synthetic,
                )
                if deep_file_sha != synthetic_file_sha or deep_loaded != reread:
                    raise CampaignError(
                        "selector synthetic deep loader returned different evidence"
                    )
                synthetic_binding["selector_deep_validation"] = {
                    "pass": True,
                    "file_sha256": deep_file_sha,
                    "content_sha256": deep_loaded.get("artifact_content_sha256"),
                }
            except Exception as error:
                synthetic_binding["selector_deep_validation"] = {
                    "pass": False,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
                if validation_error is None:
                    validation_error = error

            checkpoints["after_synthetic_freeze"] = _capture_checkpoint(
                name="after_synthetic_freeze",
                g32_binary=binary,
                control_artifact=control_artifact,
                synthetic_artifact=synthetic_artifact,
                source_manifest_reader=selected_source_reader,
                build_head_reader=selected_build_head_reader,
            )
            checkpoint_validation = _checkpoint_validation(
                checkpoints["after_synthetic_freeze"],
                start=checkpoints["start"],
                expected_g32_binary_sha256=expected_g32_binary_sha256,
                expected_control_file_sha256=expected_control_file_sha256,
                expected_synthetic_file_sha256=synthetic_file_sha,
            )
            checkpoints["after_synthetic_freeze"]["validation"] = checkpoint_validation
            if not checkpoint_validation["pass"]:
                failure = _failure(
                    "after_synthetic_checkpoint",
                    "source, binary, build HEAD, control, or synthetic artifact drifted",
                )
            elif validation_error is not None:
                failure = _failure("synthetic", validation_error)
        except Exception as error:
            failure = _failure("synthetic", error)

    # Resume never trusts a previously frozen result merely because it passes
    # the selector's deep loader.  Re-run Stage 0/1 with the same bound inputs,
    # canonicalise it exactly as on the fresh path, and require both the full
    # mapping and the on-disk bytes to match.  The frozen artifact remains
    # append-only and is never rewritten during this replay.
    if failure is None and resume_existing_synthetic:
        assert binary is not None and identity is not None and source_start is not None
        assert resumed_frozen_synthetic is not None
        try:
            replayed_synthetic = _mapping(
                selected_synthetic_runner(
                    executor=executor,
                    g32_binary=binary,
                    identity_runner=lambda: deepcopy(dict(identity)),
                    **run_kwargs,
                ),
                "resumed synthetic replay result",
            )
            validate_synthetic_result(
                replayed_synthetic,
                expected_identity=identity,
                expected_source_bundle=source_start,
                expected_g32_binary_sha256=expected_g32_binary_sha256,
                auditor=synthetic,
            )
            replayed_frozen = with_content_hash(replayed_synthetic)
            if replayed_frozen != resumed_frozen_synthetic:
                raise CampaignError(
                    "resumed synthetic replay mapping differs from frozen evidence"
                )
            if _json_bytes(replayed_frozen, pretty=True) != synthetic_artifact.read_bytes():
                raise CampaignError(
                    "resumed synthetic replay bytes differ from frozen evidence"
                )
        except Exception as error:
            failure = _failure("synthetic", error)

    if failure is None and resume_existing_synthetic:
        assert binary is not None and synthetic_binding["file_sha256"] is not None
        try:
            checkpoints["after_synthetic_freeze"] = _capture_checkpoint(
                name="after_synthetic_freeze",
                g32_binary=binary,
                control_artifact=control_artifact,
                synthetic_artifact=synthetic_artifact,
                source_manifest_reader=selected_source_reader,
                build_head_reader=selected_build_head_reader,
            )
            checkpoint_validation = _checkpoint_validation(
                checkpoints["after_synthetic_freeze"],
                start=checkpoints["start"],
                expected_g32_binary_sha256=expected_g32_binary_sha256,
                expected_control_file_sha256=expected_control_file_sha256,
                expected_synthetic_file_sha256=synthetic_binding["file_sha256"],
            )
            checkpoints["after_synthetic_freeze"]["validation"] = (
                checkpoint_validation
            )
            if not checkpoint_validation["pass"]:
                failure = _failure(
                    "after_synthetic_checkpoint",
                    "resumed source, binary, build HEAD, control, or synthetic artifact drifted",
                )
        except Exception as error:
            failure = _failure("after_synthetic_checkpoint", error)

    # The selector re-loads and deep-validates both bound artifacts before its
    # first G32 executor call.  No compatibility fallback is allowed here.
    if failure is None:
        assert binary is not None and identity is not None
        assert synthetic_binding["file_sha256"] is not None
        shadow_error: Exception | None = None
        try:
            shadow_result = _mapping(
                selected_shadow_runner(
                    control_artifact,
                    binary,
                    executor,
                    expected_control_file_sha256=expected_control_file_sha256,
                    synthetic_artifact=synthetic_artifact,
                    expected_synthetic_file_sha256=synthetic_binding["file_sha256"],
                    expected_g32_binary_sha256=expected_g32_binary_sha256,
                    auditor=synthetic,
                ),
                "Nanning shadow result",
            )
            shadow_validation = validate_shadow_result(
                shadow_result,
                expected_control_file_sha256=expected_control_file_sha256,
                expected_synthetic_file_sha256=synthetic_binding["file_sha256"],
                expected_g32_binary_sha256=expected_g32_binary_sha256,
                expected_implementation_head=str(identity["head"]),
            )
            if shadow_validation.get("pass") is not True:
                shadow_error = CampaignError(
                    f"Nanning shadow gate returned {shadow_validation.get('status')}"
                )
        except Exception as error:
            shadow_error = error
        try:
            checkpoints["after_nanning_shadow"] = _capture_checkpoint(
                name="after_nanning_shadow",
                g32_binary=binary,
                control_artifact=control_artifact,
                synthetic_artifact=synthetic_artifact,
                source_manifest_reader=selected_source_reader,
                build_head_reader=selected_build_head_reader,
            )
            checkpoint_validation = _checkpoint_validation(
                checkpoints["after_nanning_shadow"],
                start=checkpoints["start"],
                expected_g32_binary_sha256=expected_g32_binary_sha256,
                expected_control_file_sha256=expected_control_file_sha256,
                expected_synthetic_file_sha256=synthetic_binding["file_sha256"],
            )
            checkpoints["after_nanning_shadow"]["validation"] = checkpoint_validation
            if not checkpoint_validation["pass"]:
                failure = _failure(
                    "after_shadow_checkpoint",
                    "source, binary, build HEAD, control, or synthetic artifact drifted",
                )
            elif shadow_error is not None:
                failure = _failure("nanning_shadow", shadow_error)
        except Exception as error:
            failure = _failure("after_shadow_checkpoint", error)

    pipeline_pass = failure is None
    status = (
        TEST_ONLY_PASS
        if pipeline_pass
        else _status_for_failure(failure or {}, synthetic_result, shadow_result)
    )
    ledger_path = synthetic.LEDGER_PATH
    try:
        ledger_binding = {
            "path": ledger_path.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(ledger_path),
        }
    except OSError as error:
        ledger_binding = {
            "path": str(ledger_path),
            "sha256": None,
            "error": f"{type(error).__name__}: {error}",
        }
    candidate_unhashed = {
        "schema": CANDIDATE_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "campaign_revision_id": CAMPAIGN_REVISION_ID,
        "synthetic_revision_id": synthetic.SYNTHETIC_REVISION_ID,
        "control_revision_id": CONTROL_REVISION_ID,
        "status": status,
        "decision": status,
        "pass": False,
        "pipeline_candidate_pass": pipeline_pass,
        "p1_review_authorized": False,
        "authority": "TEST_ONLY_NO_FINAL_GO_AUTHORITY",
        "registered_paths": {
            name: str(path.resolve()) for name, path in actual_paths.items()
        },
        "executor_binding": {
            "module": getattr(executor, "__module__", None),
            "qualname": getattr(executor, "__qualname__", None),
        },
        "sequence": list(CAMPAIGN_SEQUENCE),
        "preflight": {
            "pass": bool(preflight_gates) and all(
                gate.get("pass") is True for gate in preflight_gates
            ),
            "gates": preflight_gates,
            "implementation_head": identity.get("head") if identity else None,
            "source_bundle_sha256": source_start.get("sha256")
            if source_start
            else None,
            "g32_binary_path": str(binary) if binary else str(g32_binary),
            "g32_binary_sha256": expected_g32_binary_sha256,
        },
        "control_artifact": control_binding,
        "synthetic_artifact": synthetic_binding,
        "nanning_shadow": _portable(shadow_result) if shadow_result else None,
        "nanning_shadow_validation": _portable(shadow_validation)
        if shadow_validation
        else None,
        "checkpoints": checkpoints,
        "failure": failure,
        "issue_remediation_ledger_file": ledger_binding,
    }
    return with_content_hash(candidate_unhashed)


def validate_p0_candidate_for_promotion(
    candidate: Mapping[str, Any],
    *,
    registered_paths: Mapping[str, Path],
    expected_executor_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Purely validate a neutral candidate; this function performs no I/O."""

    try:
        verify_content_hash(candidate)
        preflight = _mapping(candidate.get("preflight"), "candidate.preflight")
        control = _mapping(
            candidate.get("control_artifact"), "candidate.control_artifact"
        )
        frozen = _mapping(
            candidate.get("synthetic_artifact"), "candidate.synthetic_artifact"
        )
        shadow = _mapping(candidate.get("nanning_shadow"), "candidate.shadow")
        shadow_validation = _mapping(
            candidate.get("nanning_shadow_validation"),
            "candidate.shadow_validation",
        )
        checkpoints = _mapping(candidate.get("checkpoints"), "candidate.checkpoints")
        recorded_paths = _mapping(
            candidate.get("registered_paths"), "candidate.registered_paths"
        )
        expected_paths = {
            name: str(path.resolve()) for name, path in registered_paths.items()
        }
        checkpoint_rows = [
            _mapping(checkpoints.get(name), f"candidate.checkpoints.{name}")
            for name in (
                "start",
                "after_synthetic_freeze",
                "after_nanning_shadow",
            )
        ]
        start, after_synthetic, after_shadow = checkpoint_rows
        start_source = _validate_source_bundle(
            _mapping(start.get("source_bundle"), "candidate.start.source_bundle")
        )
        shadow_content_sha = verify_content_hash(shadow)
        replayed_shadow_validation = validate_shadow_result(
            shadow,
            expected_control_file_sha256=control.get("file_sha256"),
            expected_synthetic_file_sha256=frozen.get("file_sha256"),
            expected_g32_binary_sha256=preflight.get("g32_binary_sha256"),
            expected_implementation_head=preflight.get("implementation_head"),
        )
        deep = _mapping(
            frozen.get("selector_deep_validation"),
            "candidate.synthetic.selector_deep_validation",
        )
        checks = {
            "neutral_candidate_schema": candidate.get("schema") == CANDIDATE_SCHEMA,
            "neutral_candidate_no_authority": (
                candidate.get("status") == TEST_ONLY_PASS
                and candidate.get("decision") == TEST_ONLY_PASS
                and candidate.get("pass") is False
                and candidate.get("p1_review_authorized") is False
                and candidate.get("authority") == "TEST_ONLY_NO_FINAL_GO_AUTHORITY"
            ),
            "pipeline_candidate_pass": candidate.get("pipeline_candidate_pass") is True,
            "protocol_exact": candidate.get("protocol_id") == PROTOCOL_ID,
            "revision_exact": (
                candidate.get("campaign_revision_id") == CAMPAIGN_REVISION_ID
                and candidate.get("synthetic_revision_id")
                == synthetic.SYNTHETIC_REVISION_ID
                and candidate.get("control_revision_id") == CONTROL_REVISION_ID
            ),
            "sequence_exact": candidate.get("sequence") == list(CAMPAIGN_SEQUENCE),
            "registered_paths_exact": recorded_paths == expected_paths,
            "executor_exact": candidate.get("executor_binding")
            == dict(expected_executor_binding),
            "preflight_exact": (
                preflight.get("pass") is True
                and _all_gates_pass(preflight.get("gates"), "candidate.preflight.gates")
                and Path(str(preflight.get("g32_binary_path"))).resolve()
                == registered_paths["g32_binary"].resolve()
            ),
            "control_bound": (
                _sha256_text(control.get("expected_file_sha256"))
                and control.get("file_sha256") == control.get("expected_file_sha256")
                and _sha256_text(control.get("content_sha256"))
                and control.get("schema") == nanning.SCHEMA
                and control.get("protocol_id") == PROTOCOL_ID
                == nanning.PROTOCOL_ID
                and control.get("revision_id") == CONTROL_REVISION_ID
                and control.get("status") == nanning.PASS
                and candidate.get("control_revision_id") == CONTROL_REVISION_ID
                and Path(str(control.get("path"))).resolve()
                == registered_paths["control_artifact"].resolve()
            ),
            "synthetic_locally_and_deep_valid": (
                _mapping(frozen.get("validation"), "candidate.synthetic.validation").get(
                    "pass"
                )
                is True
                and deep.get("pass") is True
                and _sha256_text(frozen.get("file_sha256"))
                and _sha256_text(frozen.get("content_sha256"))
                and deep.get("file_sha256") == frozen.get("file_sha256")
                and deep.get("content_sha256") == frozen.get("content_sha256")
                and Path(str(frozen.get("path"))).resolve()
                == registered_paths["synthetic_artifact"].resolve()
            ),
            "three_integrity_checkpoints": all(
                _mapping(row.get("validation"), "checkpoint.validation").get("pass")
                is True
                for row in checkpoint_rows
            )
            and start.get("source_bundle") == after_synthetic.get("source_bundle")
            == after_shadow.get("source_bundle")
            and start_source.get("sha256") == preflight.get("source_bundle_sha256")
            and start.get("g32_binary_sha256")
            == after_synthetic.get("g32_binary_sha256")
            == after_shadow.get("g32_binary_sha256")
            == preflight.get("g32_binary_sha256")
            and start.get("g32_build_head")
            == after_synthetic.get("g32_build_head")
            == after_shadow.get("g32_build_head")
            == preflight.get("implementation_head")
            and start.get("control_artifact_file_sha256")
            == after_synthetic.get("control_artifact_file_sha256")
            == after_shadow.get("control_artifact_file_sha256")
            == control.get("file_sha256")
            and start.get("synthetic_artifact_file_sha256") is None
            and after_synthetic.get("synthetic_artifact_file_sha256")
            == after_shadow.get("synthetic_artifact_file_sha256")
            == frozen.get("file_sha256"),
            "shadow_exact_pass": (
                shadow.get("pass") is True
                and shadow.get("status") == nanning.SHADOW_PASS
                and shadow.get("schema") == nanning.SHADOW_GATE_SCHEMA
                and shadow.get("protocol_id") == PROTOCOL_ID
                and shadow.get("campaign_revision_id") == CAMPAIGN_REVISION_ID
                and shadow.get("control_revision_id") == CONTROL_REVISION_ID
                and replayed_shadow_validation == shadow_validation
                and replayed_shadow_validation.get("pass") is True
                and shadow_validation.get("pass") is True
                and shadow_validation.get("status") == nanning.SHADOW_PASS
                and shadow_validation.get("content_sha256") == shadow_content_sha
                and shadow.get("control_artifact_file_sha256")
                == control.get("file_sha256")
                and shadow.get("synthetic_artifact_file_sha256")
                == frozen.get("file_sha256")
                and shadow.get("g32_binary_sha256")
                == preflight.get("g32_binary_sha256")
            ),
            "no_failure": candidate.get("failure") is None,
        }
    except Exception as error:
        return {
            "pass": False,
            "checks": {},
            "error_type": type(error).__name__,
            "error": str(error),
        }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "error_type": None,
        "error": None,
    }


def _deep_replay_registered_candidate_shadow(
    candidate: Mapping[str, Any], *, g32_binary: Path
) -> dict[str, Any]:
    """Reload registered evidence and replay retained shadow payloads only."""

    if not isinstance(g32_binary, Path):
        raise TypeError("formal promotion requires the explicit G32 binary Path")
    if g32_binary.is_symlink():
        raise CampaignError("formal promotion G32 binary must not be a symlink")
    preflight = _mapping(candidate.get("preflight"), "candidate.preflight")
    control_binding = _mapping(
        candidate.get("control_artifact"), "candidate.control_artifact"
    )
    synthetic_binding = _mapping(
        candidate.get("synthetic_artifact"), "candidate.synthetic_artifact"
    )
    shadow = _mapping(candidate.get("nanning_shadow"), "candidate.shadow")
    control_file_sha = control_binding.get("file_sha256")
    synthetic_file_sha = synthetic_binding.get("file_sha256")
    binary_sha = preflight.get("g32_binary_sha256")
    implementation_head = preflight.get("implementation_head")
    if not all(
        _sha256_text(value)
        for value in (control_file_sha, synthetic_file_sha, binary_sha)
    ):
        raise CampaignError("formal replay candidate hashes are invalid")
    binary = g32_binary.resolve(strict=True)
    if Path(str(preflight.get("g32_binary_path"))).resolve() != binary:
        raise CampaignError("formal G32 binary path differs from candidate preflight")

    control, reloaded_control_sha = _FORMAL_CONTROL_LOADER(
        _FORMAL_CONTROL_PATH,
        expected_file_sha256=str(control_file_sha),
        auditor=synthetic,
    )
    reloaded_synthetic, reloaded_synthetic_sha = _FORMAL_SYNTHETIC_LOADER(
        _FORMAL_SYNTHETIC_PATH,
        expected_file_sha256=str(synthetic_file_sha),
        expected_g32_binary_sha256=str(binary_sha),
        auditor=synthetic,
    )
    if (
        reloaded_control_sha != control_file_sha
        or reloaded_synthetic_sha != synthetic_file_sha
    ):
        raise CampaignError("formal registered loader returned a different file hash")
    return _FORMAL_SHADOW_VALIDATOR(
        shadow,
        control=control,
        control_file_sha256=reloaded_control_sha,
        synthetic=reloaded_synthetic,
        synthetic_file_sha256=reloaded_synthetic_sha,
        g32_binary=binary,
        expected_g32_binary_sha256=str(binary_sha),
        expected_implementation_head=str(implementation_head),
        auditor=synthetic,
    )


def _promote_registered_candidate(
    candidate: Mapping[str, Any],
    *,
    g32_binary: Path | None = None,
    _test_only: bool = False,
) -> dict[str, Any]:
    """Promote only a candidate satisfying the import-time registered boundary."""

    if FORMAL_EXECUTION_BLOCKED_REASON and not _test_only:
        raise CampaignError(FORMAL_EXECUTION_BLOCKED_REASON)

    executor_binding = {
        "module": getattr(_FORMAL_CPP_EXECUTOR, "__module__", None),
        "qualname": getattr(_FORMAL_CPP_EXECUTOR, "__qualname__", None),
    }
    formal_registered_paths = dict(_FORMAL_REGISTERED_PATHS)
    if g32_binary is not None:
        formal_registered_paths["g32_binary"] = g32_binary.resolve(strict=True)
    promotion = validate_p0_candidate_for_promotion(
        candidate,
        registered_paths=formal_registered_paths,
        expected_executor_binding=executor_binding,
    )
    formal_shadow_validation: dict[str, Any]
    if promotion.get("pass") is True and not FORMAL_EXECUTION_BLOCKED_REASON:
        try:
            if g32_binary is None:
                raise CampaignError(
                    "formal promotion requires an explicit registered-run G32 binary"
                )
            replayed = _deep_replay_registered_candidate_shadow(
                candidate, g32_binary=g32_binary
            )
            formal_shadow_validation = deepcopy(dict(replayed))
        except Exception as error:
            formal_shadow_validation = {
                "pass": False,
                "checks": {},
                "error_type": type(error).__name__,
                "error": str(error),
            }
    elif FORMAL_EXECUTION_BLOCKED_REASON:
        formal_shadow_validation = {
            "pass": False,
            "checks": {},
            "error_type": "FormalExecutionBlocked",
            "error": FORMAL_EXECUTION_BLOCKED_REASON,
        }
    else:
        formal_shadow_validation = {
            "pass": False,
            "checks": {},
            "error_type": "CandidateValidationError",
            "error": "neutral candidate validation failed before registered replay",
        }
    promotion = deepcopy(dict(promotion))
    promotion_checks = dict(
        _mapping(promotion.get("checks"), "promotion.checks")
    )
    promotion_checks["formal_registered_shadow_deep_replay"] = (
        formal_shadow_validation.get("pass") is True
    )
    promotion["checks"] = promotion_checks
    promotion["formal_shadow_deep_validation"] = formal_shadow_validation
    promotion["pass"] = all(promotion_checks.values())
    if not promotion["pass"] and promotion.get("error") is None:
        promotion["error"] = formal_shadow_validation.get("error")
    eligible = (
        promotion["pass"] is True and not FORMAL_EXECUTION_BLOCKED_REASON
    )
    candidate_content_sha = candidate.get("artifact_content_sha256")
    result = deepcopy(dict(candidate))
    result.pop("artifact_content_sha256", None)
    result.update(
        {
            "schema": SCHEMA,
            "status": (
                FINAL_GO
                if eligible
                else (
                    candidate.get("status")
                    if isinstance(candidate.get("status"), str)
                    and str(candidate.get("status")).startswith("NO_GO_")
                    else NO_GO_INTERNAL
                )
            ),
            "pass": eligible,
            "pipeline_candidate_pass": candidate.get("pipeline_candidate_pass")
            is True,
            "p1_review_authorized": eligible,
            "authority": "SOLE_V3R11_P0_FINAL_GO_COMPOSER",
            "candidate_content_sha256": candidate_content_sha,
            "nanning_shadow_validation": formal_shadow_validation,
            "promotion_validation": promotion,
        }
    )
    result["decision"] = result["status"]
    if not eligible and result.get("failure") is None:
        result["failure"] = _failure(
            "formal_promotion", promotion.get("error") or "promotion checks failed"
        )
    return with_content_hash(result)


def run_p0_campaign(
    *,
    control_artifact: Path,
    expected_control_file_sha256: str,
    synthetic_artifact: Path,
    g32_binary: Path,
    expected_g32_binary_sha256: str,
    g31_binary: Path = _FORMAL_G31_BINARY,
    proof_executable: Path = _FORMAL_PROOF_EXECUTABLE,
) -> dict[str, Any]:
    """Run the registered campaign with fixed real executors and output paths."""

    if FORMAL_EXECUTION_BLOCKED_REASON:
        raise CampaignError(FORMAL_EXECUTION_BLOCKED_REASON)
    if "czr005_cpp" in sys.modules:
        raise CampaignError(
            "formal campaign requires a fresh process before loading czr005_cpp"
        )
    if not isinstance(g32_binary, Path):
        raise TypeError("formal campaign G32 binary must be supplied as a Path")
    if g32_binary.is_symlink():
        raise CampaignError("formal campaign G32 binary must not be a symlink")
    registered_g32_binary = g32_binary.resolve(strict=True)
    formal_registered_paths = {
        **_FORMAL_REGISTERED_PATHS,
        "g32_binary": registered_g32_binary,
    }

    candidate = _run_p0_campaign_core(
        control_artifact=control_artifact,
        expected_control_file_sha256=expected_control_file_sha256,
        synthetic_artifact=synthetic_artifact,
        g32_binary=registered_g32_binary,
        expected_g32_binary_sha256=expected_g32_binary_sha256,
        executor=_FORMAL_CPP_EXECUTOR,
        output_json=_FORMAL_OUTPUT_JSON,
        output_md=_FORMAL_OUTPUT_MD,
        synthetic_run_kwargs={
            "proof_executable": proof_executable,
            "g31_binary": g31_binary,
        },
        synthetic_runner=_FORMAL_SYNTHETIC_RUNNER,
        control_loader=_FORMAL_CONTROL_LOADER,
        synthetic_loader=_FORMAL_SYNTHETIC_LOADER,
        shadow_runner=_FORMAL_SHADOW_RUNNER,
        identity_runner=_FORMAL_IDENTITY_RUNNER,
        source_manifest_reader=_FORMAL_SOURCE_READER,
        build_head_reader=_FORMAL_BUILD_HEAD_READER,
        registered_paths=formal_registered_paths,
    )
    final = _promote_registered_candidate(
        candidate, g32_binary=registered_g32_binary
    )
    report = render_report(final).encode("utf-8")
    _publish_final_artifacts(
        json_path=_FORMAL_OUTPUT_JSON,
        json_payload=_json_bytes(final, pretty=True),
        report_path=_FORMAL_OUTPUT_MD,
        report_payload=report,
    )
    return final


def render_report(result: Mapping[str, Any]) -> str:
    """Render the Markdown view solely from the final hashed artifact."""

    lines = [
        "# G4IRSF32 V3R11 source-aware shadow P0 evidence",
        "",
        f"Status: `{result.get('status')}`",
        "",
        f"P1 review authorized: `{result.get('p1_review_authorized')}`",
        "",
        f"Control revision: `{result.get('control_revision_id')}`",
        "",
        "Synthetic artifact SHA-256: "
        f"`{result.get('synthetic_artifact', {}).get('file_sha256') if isinstance(result.get('synthetic_artifact'), Mapping) else None}`",
        "Nanning shadow content SHA-256: "
        f"`{result.get('nanning_shadow_validation', {}).get('content_sha256') if isinstance(result.get('nanning_shadow_validation'), Mapping) else None}`",
        "",
        "## Ordered phases",
        "",
    ]
    preflight = result.get("preflight")
    synthetic_binding = result.get("synthetic_artifact")
    shadow = result.get("nanning_shadow_validation")
    lines.extend(
        [
            f"1. Control/identity preflight: `{'PASS' if isinstance(preflight, Mapping) and preflight.get('pass') else 'NO-GO'}`",
            f"2. Synthetic Stage 0/1 freeze and selector deep replay: `{'PASS' if isinstance(synthetic_binding, Mapping) and isinstance(synthetic_binding.get('validation'), Mapping) and synthetic_binding['validation'].get('pass') and isinstance(synthetic_binding.get('selector_deep_validation'), Mapping) and synthetic_binding['selector_deep_validation'].get('pass') else 'NO-GO/NOT-RUN'}`",
            f"3. Nanning G32 shadow: `{'PASS' if isinstance(shadow, Mapping) and shadow.get('pass') else 'NO-GO/NOT-RUN'}`",
            "",
            "## Hard gates",
            "",
        ]
    )
    if isinstance(preflight, Mapping):
        for gate in preflight.get("gates", []):
            if isinstance(gate, Mapping):
                mark = "x" if gate.get("pass") is True else " "
                lines.append(f"- [{mark}] `{gate.get('name')}`")
    lines.extend(["", "## Integrity checkpoints", ""])
    checkpoints = result.get("checkpoints")
    if isinstance(checkpoints, Mapping):
        for name in ("start", "after_synthetic_freeze", "after_nanning_shadow"):
            checkpoint = checkpoints.get(name)
            validation = (
                checkpoint.get("validation") if isinstance(checkpoint, Mapping) else None
            )
            state = (
                "PASS"
                if isinstance(validation, Mapping) and validation.get("pass") is True
                else "NO-GO/NOT-RUN"
            )
            lines.append(f"- `{name}`: `{state}`")
    lines.extend(["", "## Problems and handling", ""])
    failure = result.get("failure")
    if isinstance(failure, Mapping):
        lines.append(
            f"- `{failure.get('stage')}` / `{failure.get('error_type')}`: "
            f"{failure.get('error')}"
        )
    else:
        lines.append("- No composer gate failed; FINAL_GO was issued only after all three phases.")
    ledger = result.get("issue_remediation_ledger_file")
    if isinstance(ledger, Mapping):
        lines.extend(
            [
                "- Full append-only issue/root-cause/remediation history: "
                f"[G4IRSF32 execution ledger](../../{ledger.get('path')}) "
                f"(SHA-256 `{ledger.get('sha256')}`).",
                "",
            ]
        )
    return "\n".join(lines)


def _default_g32_binary() -> Path:
    candidates = sorted(_FORMAL_G32_BINARY_GLOB.glob("czr005_cpp*.pyd"))
    if len(candidates) != 1:
        raise CampaignError(
            f"expected exactly one G32 Release binary, found {len(candidates)}"
        )
    return candidates[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-artifact", type=Path, default=_FORMAL_CONTROL_PATH)
    parser.add_argument("--expected-control-file-sha256", required=True)
    parser.add_argument("--synthetic-artifact", type=Path, default=_FORMAL_SYNTHETIC_PATH)
    parser.add_argument("--g32-binary", type=Path)
    parser.add_argument("--expected-g32-binary-sha256", required=True)
    parser.add_argument("--g31-binary", type=Path, default=_FORMAL_G31_BINARY)
    parser.add_argument(
        "--native-proof-exe", type=Path, default=_FORMAL_PROOF_EXECUTABLE
    )
    arguments = parser.parse_args(argv)
    if FORMAL_EXECUTION_BLOCKED_REASON:
        raise CampaignError(FORMAL_EXECUTION_BLOCKED_REASON)
    result = run_p0_campaign(
        control_artifact=arguments.control_artifact,
        expected_control_file_sha256=arguments.expected_control_file_sha256,
        synthetic_artifact=arguments.synthetic_artifact,
        g32_binary=arguments.g32_binary or _default_g32_binary(),
        expected_g32_binary_sha256=arguments.expected_g32_binary_sha256,
        proof_executable=arguments.native_proof_exe,
        g31_binary=arguments.g31_binary,
    )
    print(result["decision"])
    return 0 if result["decision"] == FINAL_GO else 2


if __name__ == "__main__":
    raise SystemExit(main())

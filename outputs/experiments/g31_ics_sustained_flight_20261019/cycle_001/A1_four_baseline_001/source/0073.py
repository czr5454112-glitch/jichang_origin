"""Closed native025 timing ABI, separate from accepted native022 evidence.

The native wire schema still says v1. Its externally pinned compiled ABI is
therefore essential. A build-only contract permits preparation/acceptance probes,
but never reports runtime-accepted phase timing. Unknown tags remain unknown.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from types import FunctionType

from . import native_request_timing as legacy
from .capture_native_request_timing import API_METHODS


SCHEMA = "g31.native025_timing_contract.v1"
ABI022 = {"RequestTimingPhase": legacy.PHASES, "RequestTimingMethod": legacy.METHODS,
          "RequestTimingIdentity": legacy.IDENTITIES}
ABI025 = {**ABI022, "RequestTimingIdentity": (*legacy.IDENTITIES, "planning_snapshot_v2")}
ENDPOINTS025 = {**API_METHODS, "protocol_planning_snapshots_v2": "planning_snapshots"}
RUNTIME_GATES = ("v1_ordered_public_behavior_exact", "v1_native_seal_exact",
    "timing_off_on_ordered_behavior_exact", "timing_off_on_native_seal_exact",
    "v2_query_endpoint_covered", "v2_publication_identity_resolved",
    "overflow_exception_fail_closed", "native_phase_conservation")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact_header_abi(text):
    actual = {}
    for name in ABI025:
        match = re.search(r"enum class " + name + r"\s*:[^{]+\{([^}]+)\}", text)
        if match is None:
            raise ValueError("native025_timing:missing_enum:" + name)
        actual[name] = tuple(x.strip() for x in match.group(1).split(",") if x.strip())
    if actual == ABI022:
        return "native022", actual
    if actual == ABI025:
        return "native025", actual
    raise ValueError("native025_timing:unsupported_or_reordered_abi")


def _require(value, reason):
    if not value:
        raise ValueError("native025_timing:" + reason)


def _source_path(root, relative):
    relative = relative.replace("\\", "/")
    path = Path(relative)
    _require(not path.is_absolute() and ".." not in path.parts, "invalid_archive_path")
    return root/path


def verify_contract(reference, *, require_runtime=False):
    """Reference hashes are supplied by the campaign, not discovered by a glob."""
    contract_path = Path(reference["path"])
    _require(sha(contract_path) == reference["sha256"], "contract_changed")
    contract = json.loads(contract_path.read_bytes())
    _require(contract["schema"] == SCHEMA and contract["abi_name"] == "native025", "wrong_contract")
    _require(contract["abi"] == {key: list(value) for key, value in ABI025.items()}, "contract_abi_mismatch")
    _require(contract["endpoint_methods"] == ENDPOINTS025, "endpoint_inventory_mismatch")
    build_path, archive, binary = (Path(contract[key]) for key in ("build_receipt", "source_archive", "binary"))
    _require(sha(build_path) == contract["build_receipt_sha256"], "build_receipt_changed")
    build = json.loads(build_path.read_bytes())
    _require(build.get("schema") == "g31.circulation.build_only.v1" and
        build.get("status") == "build_passed_tests_held" and not build.get("source_changed") and
        bool(build.get("source_after")) and build.get("source_before") == build["source_after"], "unverified_build")
    _require(sha(binary) == contract["binary_sha256"] and any(
        Path(path).resolve() == binary.resolve() and digest == contract["binary_sha256"]
        for path, digest in build["binary_sha256"].items()), "binary_identity_mismatch")
    _require(contract["source_sha256"] == build["source_after"], "source_manifest_mismatch")
    for relative, expected in build["source_after"].items():
        _require(sha(_source_path(archive, relative)) == expected, "archive_changed:"+relative)
    header = archive/"cpp/ics_core/runtime/request_timing_recorder.hpp"
    _require(exact_header_abi(header.read_text(encoding="utf-8"))[0] == "native025", "not_native025_abi")
    _require(contract["legacy_validator_sha256"] == sha(Path(legacy.__file__)) and
        contract["versioned_validator_sha256"] == sha(Path(__file__)), "validator_source_changed")
    accepted, attested = False, False
    acceptance_ref = contract.get("runtime_acceptance")
    if acceptance_ref is not None:
        acceptance_path = Path(acceptance_ref["path"])
        _require(sha(acceptance_path) == acceptance_ref["sha256"], "runtime_acceptance_changed")
        acceptance = json.loads(acceptance_path.read_bytes())
        if acceptance.get("schema") == "g31.native025_timing_raw_gate.v1":
            from .native025_timing_gate import verify_saved_gate
            checked = verify_saved_gate(acceptance_ref, contract)
            _require(checked["runtime_accepted"] is True, "raw_runtime_gate_failed")
            return {"contract": contract, "reference": dict(reference), "runtime_accepted": True,
                "runtime_gates_externally_attested": False,
                "independent_runtime_gate_verification_implemented": True}
        _require(acceptance.get("schema") == "g31.native025_timing_acceptance.v1" and
            acceptance.get("status") == "passed" and
            acceptance.get("binary_sha256") == contract["binary_sha256"] and
            acceptance.get("build_receipt_sha256") == contract["build_receipt_sha256"] and
            acceptance.get("versioned_validator_sha256") == contract["versioned_validator_sha256"] and
            acceptance.get("source_changed") == [], "invalid_runtime_acceptance")
        _require(set(acceptance.get("gates", {})) == set(RUNTIME_GATES) and
            all(acceptance["gates"][gate] is True for gate in RUNTIME_GATES), "runtime_gate_missing_or_failed")
        _require(set(acceptance.get("evidence", {})) == set(RUNTIME_GATES), "runtime_evidence_missing")
        for gate, evidence in acceptance["evidence"].items():
            _require(bool(evidence) and isinstance(evidence, list), "runtime_evidence_missing:"+gate)
            for item in evidence:
                _require(sha(Path(item["path"])) == item["sha256"], "runtime_evidence_changed:"+gate)
                report = json.loads(Path(item["path"]).read_bytes())
                _require(report.get("schema") == "g31.native025_timing_gate_attestation.v1" and
                    report.get("gate") == gate and report.get("status") == "passed" and
                    report.get("binary_sha256") == contract["binary_sha256"] and
                    report.get("build_receipt_sha256") == contract["build_receipt_sha256"] and
                    report.get("versioned_validator_sha256") == contract["versioned_validator_sha256"] and
                    report.get("source_changed") == [] and isinstance(report.get("checks"), dict) and
                    bool(report["checks"]) and all(isinstance(name, str) and name and value is True
                        for name, value in report["checks"].items()), "invalid_runtime_evidence:"+gate)
        # Hashes/status/check flags authenticate a claimed result, not the
        # underlying native executions. Only the closed raw gate above can
        # enable acceptance. Complete external attestations cannot do so.
        attested = True
    _require(not require_runtime or accepted, "runtime_acceptance_pending")
    return {"contract": contract, "reference": dict(reference), "runtime_accepted": accepted,
        "runtime_gates_externally_attested": attested,
        "independent_runtime_gate_verification_implemented": False}


def prepare_contract(build_receipt, source_archive, binary, output):
    """Pin a build for review; deliberately creates no runtime acceptance."""
    build_receipt, source_archive, binary, output = map(Path, (build_receipt, source_archive, binary, output))
    build = json.loads(build_receipt.read_bytes())
    contract = {"schema": SCHEMA, "abi_name": "native025",
        "abi": {key: list(value) for key, value in ABI025.items()}, "endpoint_methods": ENDPOINTS025,
        "build_receipt": str(build_receipt.resolve()), "build_receipt_sha256": sha(build_receipt),
        "source_archive": str(source_archive.resolve()), "source_sha256": build["source_after"],
        "binary": str(binary.resolve()), "binary_sha256": sha(binary),
        "legacy_validator_sha256": sha(Path(legacy.__file__)), "versioned_validator_sha256": sha(Path(__file__)),
        "runtime_acceptance": None, "runtime_gates_required": list(RUNTIME_GATES),
        "complete_request_100ms_certified": False}
    with output.open("x", encoding="utf-8") as handle:
        json.dump(contract, handle, indent=2)
    reference = {"path": str(output.resolve()), "sha256": sha(output)}
    verify_contract(reference)
    return reference


# Reuse the exact audited algorithm with an isolated, closed ABI environment.
# No monkeypatch, eval, raw-row translation, or change to legacy module globals.
# Its source hash is part of every025 contract, so this is not an unpinned plugin.
_analyze025 = FunctionType(legacy.analyze_native_timing.__code__,
    {**legacy.analyze_native_timing.__globals__, "IDENTITIES": ABI025["RequestTimingIdentity"]},
    name="_analyze_native025_closed_abi")


def analyze_candidate_partition(batches, envelopes):
    """Pure structural check; never a runtime-accepted result on its own."""
    try:
        for envelope in envelopes:
            endpoint = envelope.get("api_endpoint")
            _require(endpoint in ENDPOINTS025 and envelope.get("method") ==
                legacy.METHODS.index(ENDPOINTS025[endpoint]), "actual_endpoint_missing_or_mismatched")
        result = _analyze025(batches, envelopes)
        result["runtime_accepted"] = False
        result["abi_name"] = "native025"
        if result["status"] == "validated_partial_native_phase_partition":
            result["status"] = "structurally_valid_native025_candidate_partition"
        return result
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        return {"status": "unknown", "errors": [str(error)], "runtime_accepted": False,
            "complete_request_100ms_certified": False, "physics_subtracted_ns": 0}


def analyze_native025_timing(batches, envelopes, reference):
    """Pinned025 build + separately accepted runtime gates, otherwise unknown."""
    try:
        verified = verify_contract(reference)
        partition = analyze_candidate_partition(batches, envelopes)
        if not verified["runtime_accepted"]:
            return {"status": "unknown_runtime_acceptance_pending", "candidate_partition": partition,
                "contract_reference": dict(reference), "complete_request_100ms_certified": False,
                "physics_subtracted_ns": 0, "runtime_accepted": False,
                "runtime_gates_externally_attested": verified["runtime_gates_externally_attested"],
                "independent_runtime_gate_verification_implemented": False}
        if partition["status"] == "structurally_valid_native025_candidate_partition":
            partition["status"] = "validated_partial_native025_phase_partition"
            partition["runtime_accepted"] = True
        partition["contract_reference"] = dict(reference)
        return partition
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return {"status": "unknown", "errors": [str(error)], "runtime_accepted": False,
            "complete_request_100ms_certified": False, "physics_subtracted_ns": 0}

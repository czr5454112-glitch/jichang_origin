"""Closed candidate ABI for opt-in v3; runtime acceptance is still pending.

Old022/025 validators remain unchanged. A build-only pin and structurally valid
phase partition cannot by themselves establish actual timing instrumentation.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from types import FunctionType
from . import native_request_timing as legacy
from . import native025_request_timing as previous

SCHEMA = "g31.native027_timing_contract.v1"
ABI027 = {**previous.ABI025, "RequestTimingIdentity": (*previous.ABI025["RequestTimingIdentity"], "planning_snapshot_v3")}
ENDPOINTS027 = {**previous.ENDPOINTS025, "protocol_planning_snapshots_v3": "planning_snapshots"}
REQUIRED_GATES = ("legacy_v1_v2_ordered_behavior", "legacy_no_v3_native_seals",
    "v3_timing_off_on_ordered_behavior", "v3_timing_off_on_native_seals",
    "v3_actual_query_endpoint", "v3_publication_identity_resolved",
    "v3_overflow_exception_fail_closed", "native_phase_conservation")

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value, reason):
    if not value: raise ValueError("native027_timing:" + reason)


def exact_header_abi(text):
    actual = {}
    for name in ABI027:
        match = re.search(r"enum class " + name + r"\s*:[^{]+\{([^}]+)\}", text)
        require(match is not None, "missing_enum:" + name)
        actual[name] = tuple(x.strip() for x in match.group(1).split(",") if x.strip())
    require(actual == ABI027, "unsupported_or_reordered_abi")
    return actual


def verify_contract(reference, *, require_runtime=False):
    path = Path(reference["path"])
    require(sha(path) == reference["sha256"], "contract_changed")
    contract = json.loads(path.read_bytes())
    require(contract["schema"] == SCHEMA and contract["abi_name"] == "native027", "wrong_contract")
    require(contract["abi"] == {k: list(v) for k, v in ABI027.items()}, "abi_mismatch")
    require(contract["endpoint_methods"] == ENDPOINTS027, "endpoint_inventory_changed")
    require(contract["runtime_gates_required"] == list(REQUIRED_GATES), "runtime_gate_denominator_changed")
    build_path, archive, binary = (Path(contract[k]) for k in ("build_receipt", "source_archive", "binary"))
    require(sha(build_path) == contract["build_receipt_sha256"], "build_receipt_changed")
    build = json.loads(build_path.read_bytes())
    require(build.get("schema") == "g31.circulation.build_only.v1"
        and build.get("status") == "build_passed_tests_held" and build.get("source_changed") == []
        and bool(build.get("source_after")) and build["source_before"] == build["source_after"], "unverified_build")
    require(sha(binary) == contract["binary_sha256"] and any(Path(p).resolve() == binary.resolve()
        and h == contract["binary_sha256"] for p, h in build["binary_sha256"].items()), "binary_changed")
    require(contract["source_sha256"] == build["source_after"], "source_manifest_changed")
    for relative, digest in contract["source_sha256"].items():
        relative = Path(relative.replace("\\", "/"))
        require(not relative.is_absolute() and ".." not in relative.parts, "invalid_archive_path")
        source = (archive/relative).resolve()
        require(source.is_relative_to(archive.resolve()) and sha(source) == digest, "archived_source_changed")
    exact_header_abi((archive/"cpp/ics_core/runtime/request_timing_recorder.hpp").read_text(encoding="utf-8"))
    require(contract["validator_source_sha256"] == {str(Path(module.__file__).resolve()): sha(module.__file__)
        for module in (legacy, previous)} | {str(Path(__file__).resolve()): sha(__file__)}, "validator_source_changed")
    # Only the closed saved-raw verifier can admit runtime instrumentation.
    # External Boolean attestations, even hash-pinned, cannot enable this path.
    acceptance = contract.get("runtime_acceptance")
    if acceptance is not None:
        require(isinstance(acceptance, dict) and set(acceptance) == {"path", "sha256"}, "invalid_raw_acceptance_reference")
        from . import native027_timing_gate as gate
        require(contract.get("raw_gate_verifier_source_sha256") == sha(gate.__file__), "raw_gate_verifier_changed")
        result = gate.verify_saved_gate(acceptance, contract)
        require(result.get("runtime_accepted") is True, "raw_runtime_gate_failed")
        return {"contract": contract, "reference": dict(reference), "runtime_accepted": True,
            "independent_runtime_gate_verification_implemented": True}
    require(not require_runtime, "runtime_acceptance_pending")
    return {"contract": contract, "reference": dict(reference), "runtime_accepted": False,
        "independent_runtime_gate_verification_implemented": False}


def prepare_contract(build_receipt, source_archive, binary, output):
    build_receipt, source_archive, binary, output = map(Path, (build_receipt, source_archive, binary, output))
    build = json.loads(build_receipt.read_bytes())
    contract = {"schema": SCHEMA, "abi_name": "native027", "abi": {k: list(v) for k, v in ABI027.items()},
        "endpoint_methods": ENDPOINTS027, "build_receipt": str(build_receipt.resolve()),
        "build_receipt_sha256": sha(build_receipt), "source_archive": str(source_archive.resolve()),
        "source_sha256": build["source_after"], "binary": str(binary.resolve()), "binary_sha256": sha(binary),
        "validator_source_sha256": {str(Path(module.__file__).resolve()): sha(module.__file__)
            for module in (legacy, previous)} | {str(Path(__file__).resolve()): sha(__file__)},
        "runtime_acceptance": None, "runtime_gates_required": list(REQUIRED_GATES),
        "complete_request_100ms_certified": False}
    with output.open("x", encoding="utf-8") as stream: json.dump(contract, stream, indent=2, allow_nan=False)
    reference = {"path": str(output.resolve()), "sha256": sha(output)}
    verify_contract(reference)
    return reference


_analyze027 = FunctionType(legacy.analyze_native_timing.__code__,
    {**legacy.analyze_native_timing.__globals__, "IDENTITIES": ABI027["RequestTimingIdentity"]},
    name="_analyze_native027_closed_abi")


def analyze_candidate_partition(batches, envelopes):
    try:
        for envelope in envelopes:
            endpoint = envelope.get("api_endpoint")
            require(endpoint in ENDPOINTS027 and envelope.get("method") == legacy.METHODS.index(ENDPOINTS027[endpoint]),
                    "actual_endpoint_missing_or_mismatched")
        result = _analyze027(batches, envelopes)
        result.update(runtime_accepted=False, abi_name="native027")
        if result["status"] == "validated_partial_native_phase_partition":
            result["status"] = "structurally_valid_native027_candidate_partition"
        return result
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        return {"status": "unknown", "errors": [str(error)], "runtime_accepted": False,
            "complete_request_100ms_certified": False, "physics_subtracted_ns": 0}


def analyze_native027_timing(batches, envelopes, reference):
    try:
        verified = verify_contract(reference)
        partition = analyze_candidate_partition(batches, envelopes)
        if not verified["runtime_accepted"]:
            return {"status": "unknown_runtime_acceptance_pending", "candidate_partition": partition,
                "contract_reference": dict(reference), "runtime_accepted": False,
                "complete_request_100ms_certified": False, "physics_subtracted_ns": 0}
        if partition["status"] == "structurally_valid_native027_candidate_partition":
            partition.update(status="validated_partial_native027_phase_partition", runtime_accepted=True)
        partition["contract_reference"] = dict(reference)
        return partition
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return {"status": "unknown", "errors": [str(error)], "runtime_accepted": False,
            "complete_request_100ms_certified": False, "physics_subtracted_ns": 0}

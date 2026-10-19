"""Closed native027 evidence admission scoped to one bounded worker invocation.

The full saved 44-case and 21-test verifiers run at entry and exit. Every
branch rehashes their entire file evidence and the campaign's frozen closure.
This never caches messages, observations, ownership, session state or choices.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import time

from . import native027_request_timing as timing
from . import run_native027_semantic_gate as semantic

_TOKEN = object()
ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def require(value, reason):
    if not value:
        raise ValueError("native027_run_acceptance:" + reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def inventory(contract_reference, semantic_reference, campaign_reference):
    """Explicit closure of every file consulted by the two closed verifiers.

The initial closed verifiers establish meaning; this list only binds bytes.
It also includes both compiled artifacts, both archived C++ closures, actual
worker metadata, all raw cases and source imports, and the campaign archive.
"""
    pins = {}

    def add(path, expected=None):
        path = Path(path).resolve(strict=True)
        digest = sha(path)
        require(expected is None or expected == digest, "pin_mismatch:" + str(path))
        require(str(path) not in pins or pins[str(path)] == digest, "conflicting_pin")
        pins[str(path)] = digest
        return read(path) if path.suffix == ".json" else None

    def reference(ref):
        require(type(ref) is dict and set(ref) == {"path", "sha256"}, "reference_shape")
        return add(ref["path"], ref["sha256"])

    def build(receipt_path, archive, binary, expected):
        receipt = add(receipt_path)
        add(binary, expected)
        for relative, digest in receipt["source_after"].items():
            relative = Path(relative.replace("\\", "/"))
            require(not relative.is_absolute() and ".." not in relative.parts, "archive_path")
            add(Path(archive) / relative, digest)

    contract = reference(contract_reference)
    build(contract["build_receipt"], contract["source_archive"], contract["binary"], contract["binary_sha256"])
    gate_ref = contract["runtime_acceptance"]
    gate = reference(gate_ref)
    gate_dir = Path(gate_ref["path"]).resolve().parent
    plan = add(gate_dir / "plan.json", gate["plan_sha256"])
    candidate = reference(plan["contract_reference"])
    add(gate_dir / "contract_reference.json")
    add(gate_dir / "candidate_contract.json", plan["contract_reference"]["sha256"])
    build(candidate["build_receipt"], candidate["source_archive"], candidate["binary"], candidate["binary_sha256"])
    build(plan["native026_build"], plan["native026_source_archive"], plan["native026_binary"], plan["native026_sha256"])
    for path, digest in plan["source_sha256"].items():
        add(path, digest)
        add(gate_dir / "source" / Path(path).relative_to(ROOT), digest)
    for case, digest in plan["input_sha256"].items():
        add(gate_dir / "inputs" / (case + ".json.gz"), digest)
    for arm, cases in gate["raw"].items():
        add(gate_dir / (arm + ".process.json"), gate["process_sha256"][arm])
        add(gate_dir / arm / "completion.json", gate["completion_sha256"][arm])
        for case, digest in cases.items():
            add(gate_dir / arm / (case + ".json.gz"), digest)
    semantic_receipt = reference(semantic_reference)
    semantic_dir = Path(semantic_reference["path"]).resolve().parent
    for name, digest in semantic_receipt["evidence_sha256"].items():
        add(semantic_dir / name, digest)
    semantic_plan = read(semantic_dir / "plan.json")
    add(semantic_plan["interpreter"], semantic_plan["interpreter_sha256"])
    build(semantic_plan["build_receipt"], Path(semantic_plan["build_receipt"]).parent / "source",
          semantic_plan["binary"], semantic_plan["binary_sha256"])
    for path, digest in semantic_plan["source_sha256"].items():
        add(path, digest)
        add(semantic_dir / "source" / Path(path).relative_to(ROOT), digest)
    campaign = reference(campaign_reference)
    campaign_dir = Path(campaign_reference["path"]).resolve().parent
    require(set(campaign["source_archive"]) == set(campaign["source_sha256"]), "campaign_source_domain")
    for path, digest in campaign["source_sha256"].items():
        add(path, digest)
        archived = (campaign_dir / campaign["source_archive"][path]).resolve()
        require(archived.is_relative_to(campaign_dir / "source"), "campaign_archive_escape")
        add(archived, digest)
    for key, digest in campaign["input_file_sha256"].items():
        add(campaign_dir / "inputs" / (key + ".json"), digest)
    add(__file__)
    return pins


class RunAcceptance:
    __slots__ = ("_token", "_pid", "_run", "_contract_ref", "_semantic_ref", "_campaign_ref",
                 "_pins", "_verified", "_semantic", "_active", "_invalid", "_branch", "_used", "_costs", "_closed", "_rows")

    def __init__(self, token, contract_ref, semantic_ref, campaign_ref, pins, verified, semantics, costs, rows):
        require(token is _TOKEN, "closed_factory_required")
        self._token, self._pid = token, os.getpid()
        self._run = canonical(campaign_ref)
        self._contract_ref, self._semantic_ref, self._campaign_ref = map(copy.deepcopy,
            (contract_ref, semantic_ref, campaign_ref))
        self._pins, self._verified, self._semantic = dict(pins), copy.deepcopy(verified), copy.deepcopy(semantics)
        self._active, self._invalid, self._branch, self._used, self._costs = True, [], None, set(), list(costs)
        self._closed = False
        self._rows = copy.deepcopy(rows)

    def __reduce__(self):
        raise TypeError("native027_run_acceptance:not_serializable")

    def _identity(self):
        require(type(self) is RunAcceptance and self._token is _TOKEN and self._pid == os.getpid(), "wrong_process_or_token")

    def _check_pins(self, phase):
        start = time.perf_counter()
        changed = []
        for path, digest in self._pins.items():
            try:
                if sha(path) != digest:
                    changed.append(path)
            except OSError:
                changed.append(path)
        self._costs.append({"phase": phase, "wall_seconds": time.perf_counter() - start, "file_count": len(self._pins)})
        if changed:
            self._invalid.extend(changed)
            self._active = False
            raise ValueError("native027_run_acceptance:evidence_changed:" + changed[0])

    def enter_branch(self, key, campaign_reference):
        self._identity()
        require(self._active and not self._invalid and self._branch is None, "inactive_or_overlapping_branch")
        require(canonical(campaign_reference) == self._run, "wrong_run")
        require(type(key) is str and key in self._rows and key not in self._used, "duplicate_or_missing_branch")
        self._check_pins("branch_entry:" + key)
        self._branch = key
        self._used.add(key)

    def active_for(self, key):
        try:
            self._identity()
            return self._active and not self._invalid and self._branch == key
        except (ValueError, AttributeError):
            return False

    def finish_branch(self, key):
        self._identity()
        require(self.active_for(key), "wrong_or_inactive_branch")
        try:
            self._check_pins("branch_exit:" + key)
        finally:
            self._branch = None

    def contract_copy(self, key):
        require(self.active_for(key), "inactive_branch_contract")
        return copy.deepcopy(self._verified)

    def branch_specification(self, key):
        require(self.active_for(key), "inactive_branch_specification")
        return copy.deepcopy(self._rows[key])

    def audit_copy(self):
        return {"run_reference": copy.deepcopy(self._campaign_ref), "contract_reference": copy.deepcopy(self._contract_ref),
                "semantic_reference": copy.deepcopy(self._semantic_ref), "pid": self._pid,
                "evidence_sha256": dict(self._pins), "costs": copy.deepcopy(self._costs),
                "active": self._active, "invalid": list(self._invalid), "branch_keys": sorted(self._used)}

    def close(self):
        self._identity()
        require(not self._closed, "already_closed")
        if self._branch is not None:
            self._invalid.append("unfinished_branch:" + self._branch)
        # Revoke all branch/collector capability before any potentially failing
        # end validation. A failed finalizer can never leave reusable admission.
        self._active, self._branch, self._closed = False, None, True
        try:
            self._check_pins("run_exit_before_closed_verifiers")
            start = time.perf_counter()
            verified = timing.verify_contract(self._contract_ref, require_runtime=True)
            semantics = semantic.verify_saved_semantic_gate(self._semantic_ref,
                expected_binary_sha256=verified["contract"]["binary_sha256"])
            require(verified == self._verified and semantics == self._semantic, "closed_verifier_result_changed")
            require(inventory(self._contract_ref, self._semantic_ref, self._campaign_ref) == self._pins, "evidence_inventory_changed")
            self._costs.append({"phase": "run_exit_closed_verifiers", "wall_seconds": time.perf_counter() - start})
            self._check_pins("run_exit_after_closed_verifiers")
        except Exception as error:
            self._invalid.append(str(error))
        result = self.audit_copy()
        result["status"] = "invalidated_acceptance_evidence" if self._invalid else "closed_run_acceptance_passed"
        result["native_calls"] = 0
        return result


def open_run(contract_reference, semantic_reference, campaign_reference):
    start = time.perf_counter()
    before = inventory(contract_reference, semantic_reference, campaign_reference)
    verified = timing.verify_contract(contract_reference, require_runtime=True)
    semantics = semantic.verify_saved_semantic_gate(semantic_reference,
        expected_binary_sha256=verified["contract"]["binary_sha256"])
    require(verified["runtime_accepted"] is True
            and semantics["status"] == "validated_native027_finite_semantic_regression"
            and semantics["passed"] == 21, "closed_runtime_gate_missing")
    require(inventory(contract_reference, semantic_reference, campaign_reference) == before, "entry_inventory_changed")
    require(all(sha(path) == digest for path, digest in before.items()), "entry_bytes_changed")
    rows = read(campaign_reference["path"])["rows"]
    require(type(rows) is dict and bool(rows), "missing_declared_branch_domain")
    return RunAcceptance(_TOKEN, contract_reference, semantic_reference, campaign_reference, before, verified, semantics,
                         [{"phase": "run_entry_closed_verifiers", "wall_seconds": time.perf_counter() - start}], rows)

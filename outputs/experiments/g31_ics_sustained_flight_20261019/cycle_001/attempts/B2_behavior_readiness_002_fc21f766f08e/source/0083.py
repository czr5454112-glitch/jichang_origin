"""Finite, source-pinned native027 parity and timing gate; no latency certificate.

Preparation and saved-file verification never construct NativeSession. Native
execution is an explicit serial campaign; failed and unrun cells stay visible.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

from . import native027_request_timing as abi
from . import native025_timing_gate as old_gate
from .capture_native027_request_timing import Native027TimingCapture
from . import native_host
from .native_request_timing import PHASES
from .planning_capture_v3_contract import capture_digest_v3

ROOT = Path(__file__).resolve().parents[3]
MODULE = "scripts.experiments.g31_ics_circulation.native027_timing_gate"
SCHEMA = "g31.native027_timing_raw_gate.v1"
PLAN_SCHEMA = "g31.native027_timing_gate_plan.v1"
NATIVE026_SHA = "c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943"
LEGACY_CASES = old_gate.V1_CASES + old_gate.V2_CASES
V3_CASES = ("reserved_before_entry", "observed_entry", "lost_ack_retry", "source_outage",
    "target_outage", "expiry_tombstone", "overflow", "exception")
NEGATIVE_CASES = ("overflow", "exception")
ARMS = {"native026_plain": LEGACY_CASES, "native027_plain": LEGACY_CASES + V3_CASES,
    "native027_timed": V3_CASES}


def require(value, reason):
    if not value: raise ValueError("native027_gate:" + reason)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())


def write(path, value):
    path = Path(path)
    encoded = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode()
    if path.suffix == ".gz": encoded = gzip.compress(encoded, compresslevel=1, mtime=0)
    with path.open("xb") as stream: stream.write(encoded)


def stable(value):
    """Exclude only the existing native diagnostic clock keys; retain order."""
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items()
            if k not in {"wall_seconds", "compute_wall_ms", "compute_cpu_ms", "submit_compute_ms", "wall_ms", "cpu_ms"}}
    if isinstance(value, (list, tuple)): return [stable(v) for v in value]
    return value


def ordered(value): return json.dumps(stable(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def exact(value): return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def source_paths():
    """Transitive local AST imports, including package initializers and src."""
    pending, found = [Path(__file__).resolve()], set()
    def enqueue(target):
        for candidate in (target.with_suffix(".py"), target / "__init__.py"):
            if not candidate.is_file() or not candidate.resolve().is_relative_to(ROOT): continue
            pending.append(candidate)
            for parent in candidate.parents:
                if parent == ROOT: break
                if (parent / "__init__.py").is_file(): pending.append(parent / "__init__.py")
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom):
                for base in ([path.parent] if node.level else [ROOT, ROOT / "src"]):
                    for _ in range(max(0, node.level - 1)): base = base.parent
                    if node.module: base = base.joinpath(*node.module.split(".")); enqueue(base)
                    for alias in node.names:
                        if alias.name != "*": enqueue(base.joinpath(*alias.name.split(".")))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for base in (ROOT, ROOT / "src"): enqueue(base.joinpath(*alias.name.split(".")))
    return sorted(found)


def loaded_project_sources():
    paths = set()
    for name, module in list(sys.modules.items()):
        location = getattr(module, "__file__", None)
        if not location: continue
        path = Path(location).resolve()
        if path.suffix != ".py" or path.is_relative_to(ROOT / "tests"): continue
        if path.is_relative_to(ROOT) or name == "czr005" or name.startswith(("scripts.", "czr005.")):
            paths.add(path)
    return {str(path): sha(path) for path in sorted(paths)}


def unarchived_loaded_sources(plan):
    return sorted(set(loaded_project_sources()) - set(plan["source_sha256"]))


def source_changes(plan):
    return [name for name, digest in plan["source_sha256"].items()
        if not Path(name).is_file() or sha(name) != digest]


def scene(case):
    if case in LEGACY_CASES: return old_gate.scene(case)
    require(case in V3_CASES, "unknown_case")
    protocol = {"enabled": True, "timeout": .2, "ack_delay": .01}
    if case == "lost_ack_retry": protocol["drop_ack_packets"] = 1
    if case in ("source_outage", "target_outage"):
        protocol["owner_outages"] = [{"owner": "A" if case == "source_outage" else "B", "start": 1.2, "end": 1.4}]
    return native_host.prepare_input({"schema": "g31.circulation.input.v1",
        "model_scope": "synthetic long edge; native027 finite timing/parity acceptance",
        "node_records": [(0, 1, 1., 0, 0, [1]), (1, 1, .05, 1, 0, [])],
        "edge_records": [(0, 1, 10., 1.)],
        "node_contracts": [{"node": n, "zone": owner, "resource_owner": owner, "capacity": 1}
            for n, owner in ((0, "A"), (1, "B"))],
        "edge_contracts": [{"from": 0, "to": 1, "capacity": 1, "entry_headway": .2}],
        "trays": [{"tray_id": "T0", "node": 0}],
        "jobs": [{"business_bag_id": "B1", "origin": 0, "destination": 1, "arrival": 0.,
            "deadline": 40., "load_seconds": .1, "unload_seconds": .5, "hold_seconds": .2}],
        "transfers": [], "faults": [], "options": {"max_simulation_time": 80.},
        "owner_protocol": protocol, "owner_notifications": {"enabled": True}})


def request(identity="one", **changes):
    return {"request_id": "live:1:A:planning_snapshot_v3:" + identity, "owner_id": "A",
        "kind": "planning_snapshot_v3", "target_owner": "B", "message_delay": 0.,
        "publication_delay": .01, "expiry": 60., **changes}


def v3_tape(case):
    """Every submitted field and read/advance argument is declared in advance."""
    require(case in V3_CASES, "unknown_v3_case")
    def call(endpoint, *args, **kwargs): return {"endpoint": endpoint, "args": list(args), "kwargs": kwargs}
    if case == "exception": return [call("advance_to", -1.)]
    at = 1.1 if case == "reserved_before_entry" else 1.3
    # Diagnostic002 established this exact bounded event prefix. The partial
    # timestamp is only a negative capture fixture, not a policy admission cut.
    rows = ([call("advance_to", 1.)] + [call("advance_to", 1.1, max_events=1) for _ in range(5)]
        if case == "reserved_before_entry" else [call("advance_to", at)])
    rows.append(call("observe_protocol", "A"))
    if case == "expiry_tombstone":
        old, new = request("old", publication_delay=.5), request("new", expiry=1.4)
        rows += [call("submit_protocol_command", old), call("advance_to", 1.305),
            call("submit_protocol_command", old), call("advance_to", 1.32),
            call("protocol_command", "A", old["request_id"]), call("submit_protocol_command", new),
            call("advance_to", 1.37), call("protocol_command", "A", new["request_id"]),
            call("protocol_planning_snapshots_v3", "B"), call("advance_to", 1.9),
            call("protocol_command", "A", old["request_id"]), call("protocol_planning_snapshots_v3", "B"),
            call("observe_protocol", "A"), call("result_at", 1.9)]
        return rows
    payload = request()
    rows.append(call("submit_protocol_command", payload))
    if case == "lost_ack_retry":
        rows += [call("advance_to", 1.35), call("protocol_command", "A", payload["request_id"]),
            call("protocol_planning_snapshots_v3", "B"), call("submit_protocol_command", payload), call("advance_to", 1.4)]
        finish = 1.4
    elif case in ("source_outage", "target_outage"):
        rows += [call("advance_to", 1.35), call("protocol_command", "A", payload["request_id"]),
            call("protocol_planning_snapshots_v3", "B"), call("advance_to", 1.45)]
        finish = 1.45
    else:
        finish = at + .03
        rows.append(call("advance_to", finish))
    return rows + [call("protocol_command", "A", payload["request_id"]),
        call("protocol_planning_snapshots_v3", "B"), call("result_at", finish)]


def run_case(native, case, *, timed, reference, identity):
    if case in LEGACY_CASES:
        require(not timed, "legacy_timed_outside_declared_domain")
        tape = []
        class RecordedSession:
            def __init__(self, data): self.session = native.NativeSession(data)
            def __getattr__(self, name):
                value = getattr(self.session, name)
                if name not in abi.ENDPOINTS027: return value
                def invoke(*args, **kwargs):
                    entry = {"endpoint": name, "args": deepcopy(args), "kwargs": deepcopy(kwargs)}
                    try:
                        result = value(*args, **kwargs); entry["returned"] = deepcopy(result); return result
                    except Exception as error:
                        entry["exception"] = {"type": type(error).__name__, "message": str(error)}; raise
                    finally: tape.append(entry)
                return invoke
        wrapped = SimpleNamespace(NativeSession=RecordedSession, _g31_native_artifact_identity=native._g31_native_artifact_identity)
        try: return old_gate.run_case(wrapped, case, timed=False, reference=None, identity=identity)
        except Exception as error:
            error.gate_partial = {"input": scene(case), "outputs": tape, "native_binary": native._g31_native_artifact_identity}
            raise
    data = scene(case); raw = native.NativeSession(data)
    session = Native027TimingCapture(raw, native_module=native, contract_reference=reference,
        acceptance_probe=True, session_identity=identity, capacity=2 if case == "overflow" else 100000) if timed else raw
    outputs = []
    for spec in v3_tape(case):
        entry = deepcopy(spec)
        try: entry["returned"] = deepcopy(getattr(session, spec["endpoint"])(*spec["args"], **spec["kwargs"]))
        except Exception as error:
            entry["exception"] = {"type": type(error).__name__, "message": str(error)}
            outputs.append(entry)
            if case == "exception" and spec == v3_tape(case)[0]: break
            error.gate_partial = {"input": data, "outputs": outputs, "native_binary": native._g31_native_artifact_identity}
            raise
        outputs.append(entry)
    result = {"case": case, "status": "captured", "input": data, "outputs": outputs,
        "native_binary": deepcopy(native._g31_native_artifact_identity),
        "native_seal": raw.offline_state_sha256(), "checkpoint_seal": raw.checkpoint().offline_state_sha256}
    if timed:
        session.take_completed()
        result["timing"] = {"batches": session.batches, "envelopes": session.envelopes, "capture_errors": session.errors}
    return result


def check_v3_outcome(case, outputs):
    require(exact([{k: r[k] for k in ("endpoint", "args", "kwargs")} for r in outputs]) == exact(v3_tape(case)), "v3_declared_tape:" + case)
    if case == "exception":
        require(set(outputs[0]) == {"endpoint", "args", "kwargs", "exception"}
            and outputs[0]["exception"]["type"] in ("ValueError", "RuntimeError"), "native_exception_missing")
        return
    require(all("returned" in row and "exception" not in row for row in outputs), "unexpected_service_exception")
    queries = [r["returned"] for r in outputs if r["endpoint"] == "protocol_command"]
    peers = [r["returned"] for r in outputs if r["endpoint"] == "protocol_planning_snapshots_v3"]
    require(all(r["returned"]["status"] == "pending" for r in outputs if r["endpoint"] == "submit_protocol_command"), "submission_not_pending")
    if case == "lost_ack_retry":
        require("last_delivered_ack" not in queries[0] and len(peers[0]) == 1, "dropped_ack_not_observed")
        require(queries[-1]["attempt"] == 2 and ordered(peers[0]) == ordered(peers[-1]), "retry_recaptured")
    if case in ("source_outage", "target_outage"):
        require(peers[0] == [] and "last_delivered_ack" not in queries[0], "outage_not_observed")
    if case == "expiry_tombstone":
        pending = queries[0]["last_delivered_ack"]
        require(pending["status"] == "pending_delivery" and "planning_snapshot_v3" not in pending, "pending_ack_contains_capture")
        require(len(peers[0]) == len(peers[-1]) == 1 and peers[0][0]["status"] == "conditional"
            and peers[-1][0]["status"] == "expired" and ordered(peers[0][0]["capture"]) == ordered(peers[-1][0]["capture"]), "latest_expired_tombstone_lost")
        history = outputs[-2]["returned"]["delivered_command_acks"]
        require(all("planning_snapshot_v3" not in r for r in history if
            r["request_id"] == request("old")["request_id"] and r["sequence"] == pending["sequence"]), "pending_ack_gained_later_payload")
        envelope = peers[-1][0]
        ack = queries[1]["last_delivered_ack"]
    else:
        require(len(peers[-1]) == 1, "v3_peer_missing")
        envelope = peers[-1][0]; ack = queries[-1]["last_delivered_ack"]
    require(ack["status"] == "delivered" and ordered(ack["planning_snapshot_v3"]["capture"]) == ordered(envelope["capture"]), "v3_final_selfcopy_mismatch")
    require(envelope["schema"] == "g31.planning_snapshot.v3" and envelope["kind"] == "planning_snapshot_v3"
        and envelope["digest_format"] == "g31.planning_capture_digest.v3", "v3_envelope_schema")
    body = envelope["capture"]; extension = body["extension"]
    require(set(body) == {"schema", "capture_v2", "extension"} and capture_digest_v3(body) == envelope["payload_sha256"], "v3_typed_digest")
    local = body["capture_v2"]["local_capture"]
    expected_capture = 1.4 if case == "source_outage" else 1.32 if case == "expiry_tombstone" else 1.1 if case == "reserved_before_entry" else 1.3
    expected_delivery = 1.4 if case == "target_outage" else expected_capture + .01
    require(local["captured_at"] == extension["captured_at"] == expected_capture
        and envelope["delivered_at"] == expected_delivery, "capture_delivery_chronology")
    coverage = extension["coverage"]
    require(coverage["source_owned_inflight_tray_ids"] == ["T0"] and coverage["uses_future_event_heap"] is False, "v3_inflight_population")
    observed = next(r["returned"] for r in outputs if r["endpoint"] == "observe_protocol")["trays"][0]
    if case == "reserved_before_entry":
        require(outputs[0]["returned"]["status"] == "reached" and outputs[0]["returned"]["horizon_complete"] is True
            and outputs[0]["returned"]["physical_time"] == 1.
            and all(r["returned"]["status"] == "budget_exhausted" and r["returned"]["horizon_complete"] is False
                and r["returned"]["physical_time"] == 1.1 for r in outputs[1:6]), "reservation_event_prefix_not_observed")
        require(observed["edge_to"] == 1 and "edge_exit_at" not in observed
            and extension["source_observed_inflight"] == [] and coverage["unmatched_tray_ids"] == ["T0"]
            and coverage["complete_for_declared_source_inflight"] is False, "reservation_misrepresented_as_entry")
        entered = [r for r in outputs[-1]["returned"]["receipts"] if r["event"] == "EDGE_ENTER" and r["tray_id"] == "T0"]
        require(len(entered) == 1 and entered[0]["time"] == 1.1, "reservation_never_became_actual_entry")
    else:
        require(len(extension["source_observed_inflight"]) == 1 and coverage["unmatched_tray_ids"] == []
            and coverage["complete_for_declared_source_inflight"] is True, "actual_entry_missing")
        row = extension["source_observed_inflight"][0]
        receipts = outputs[-1]["returned"]["receipts"]
        entered = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["tray_id"] == "T0"]
        require(len(entered) == 1 and row["entered_at"] == entered[0]["time"]
            and row["static_edge_travel_seconds"] == 10. and row["derived_edge_exit_at"] == row["entered_at"] + 10.
            and row["derived_edge_exit_at"] == observed["edge_exit_at"], "entry_not_observed_native_fact")
        require(all(row[k] == observed[k] for k in ("tray_id", "business_bag_id", "generation", "traversal_id", "edge_from", "edge_to")), "public_entry_identity_changed")
        require(not {"internal_traversal_id", "transport_leg_id", "event_seq", "runtime_id"} & set(row), "private_identity_exposed")


def replay_legacy(row):
    """Re-execute the frozen legacy scenario against every actual returned read.

This validates its dynamically derived route identity and every retry/input;
it does not reconstruct native hidden state or authenticate a supplied seal.
"""
    class TapeSession:
        def __init__(self, data):
            require(exact(data) == exact(row["input"]), "legacy_replay_input")
            self.cursor, self.physical_time = 0, 0.

        def __getattr__(self, endpoint):
            def invoke(*args, **kwargs):
                require(self.cursor < len(row["outputs"]), "legacy_replay_extra_call")
                item = row["outputs"][self.cursor]; self.cursor += 1
                require(item["endpoint"] == endpoint and exact(item["args"]) == exact(args)
                    and exact(item["kwargs"]) == exact(kwargs) and "exception" not in item, "legacy_replay_call_changed")
                returned = deepcopy(item["returned"])
                if endpoint == "advance_to": self.physical_time = returned["physical_time"]
                elif endpoint == "result_at": self.physical_time = returned["advance"]["physical_time"]
                return returned
            return invoke

        def offline_state_sha256(self): return row["native_seal"]
        def checkpoint(self): return SimpleNamespace(offline_state_sha256=row["checkpoint_seal"])
    sessions = []
    def factory(data):
        session = TapeSession(data); sessions.append(session); return session
    native = SimpleNamespace(NativeSession=factory, _g31_native_artifact_identity=row["native_binary"])
    replayed = old_gate.run_case(native, row["case"], timed=False, reference=None, identity=1)
    require(len(sessions) == 1 and sessions[0].cursor == len(row["outputs"])
        and ordered(replayed["outputs"]) == ordered(row["outputs"]), "legacy_replay_incomplete")


def check_records(records):
    require(set(records) == set(ARMS), "arm_domain")
    for arm, cases in ARMS.items():
        require(set(records[arm]) == set(cases), "case_domain:" + arm)
        for case, row in records[arm].items():
            require(row.get("status") == "captured" and row.get("case") == case, "case_status")
            require(exact(row["input"]) == exact(scene(case)), "predeclared_input:" + case)
            require(all(type(row.get(k)) is str and re.fullmatch("[0-9a-f]{64}", row[k]) for k in ("native_seal", "checkpoint_seal"))
                and row["native_seal"] == row["checkpoint_seal"], "invalid_native_seal:" + case)
            if case in LEGACY_CASES:
                require([r["endpoint"] for r in row["outputs"]] == old_gate.endpoints(case), "legacy_endpoint_tape:" + case)
                old_gate.check_outcome(case, row["outputs"])
                replay_legacy(row)
            else: check_v3_outcome(case, row["outputs"])
    for case in LEGACY_CASES:
        old, new = (records[arm][case] for arm in ("native026_plain", "native027_plain"))
        require(ordered(old["outputs"]) == ordered(new["outputs"]), "legacy_ordered_transcript:" + case)
        require(old["native_seal"] == new["native_seal"], "legacy_seal:" + case)
    for case in V3_CASES:
        plain, timed = (records[arm][case] for arm in ("native027_plain", "native027_timed"))
        require(ordered(plain["outputs"]) == ordered(timed["outputs"]), "v3_ordered_transcript:" + case)
        require(plain["native_seal"] == timed["native_seal"], "v3_timing_seal:" + case)
        timing = timed["timing"]; envelopes = timing["envelopes"]
        require([e["api_endpoint"] for e in envelopes] == [r["endpoint"] for r in timed["outputs"]], "envelope_tape:" + case)
        for entry, envelope in zip(timed["outputs"], envelopes, strict=True):
            if entry["endpoint"] == "submit_protocol_command":
                require(envelope.get("protocol_request_id") == entry["args"][0]["request_id"], "submit_identity_tape")
            elif entry["endpoint"] == "protocol_command":
                require(envelope.get("protocol_request_id") == entry["args"][1], "query_identity_tape")
        submitted = list(dict.fromkeys(r["args"][0]["request_id"] for r in timed["outputs"] if r["endpoint"] == "submit_protocol_command"))
        for batch in timing["batches"]:
            for command in batch["command_identities"]:
                require(command["kind"] == "planning_snapshot_v3" and command["request_id"] in submitted
                    and command["index"] == submitted.index(command["request_id"])
                    and command["native_index"] in (-1, command["index"]), "v3_command_identity_not_actual_submission")
            for span in batch["rows"]:
                if span["identity_kind"] == 11:
                    require(type(span["identity_index"]) is int and 0 <= span["identity_index"] < len(submitted), "v3_identity_not_actual_publication")
        report = abi.analyze_candidate_partition(timing["batches"], envelopes)
        if case in NEGATIVE_CASES:
            require(report["status"] == "unknown", "negative_not_unknown:" + case)
            if case == "overflow":
                require(any(type(b["errors"]) is int and b["errors"] & 1 for b in timing["batches"]), "overflow_not_recorded")
            else:
                require(timing["capture_errors"] and "exception" in timed["outputs"][0]
                    and any(span.get("exception_exit") is True for b in timing["batches"] for span in b["rows"]), "exception_not_recorded")
            continue
        require(not timing["capture_errors"] and report["status"] == "structurally_valid_native027_candidate_partition", "phase_conservation:" + case)
        rows = [r for batch in timing["batches"] for r in batch["rows"]]
        require({"source_execution", "ack_create", "ack_delivery"} <= {PHASES[r["phase"]] for r in rows}, "missing_protocol_phases:" + case)
        require(any(e["api_endpoint"] == "protocol_planning_snapshots_v3" and e["method"] == 10 for e in envelopes), "v3_endpoint_missing")
        require(any(r["identity_kind"] == 11 and PHASES[r["phase"]] == "publication_delivery" for r in rows), "v3_publication_identity_missing")
        require(any(c["kind"] == "planning_snapshot_v3" for b in timing["batches"] for c in b["command_identities"]), "v3_identity_table_missing")
    return {name: True for name in abi.REQUIRED_GATES}


def verify_build(receipt_path, archive, binary, expected):
    receipt_path, archive, binary = map(Path, (receipt_path, archive, binary))
    build = read(receipt_path)
    require(build.get("schema") == "g31.circulation.build_only.v1" and build.get("status") == "build_passed_tests_held"
        and build.get("source_changed") == [] and build.get("source_before") == build.get("source_after")
        and bool(build.get("source_before")) and len(build.get("commands", [])) == 2
        and all(type(c.get("exit_code")) is int and c["exit_code"] == 0 for c in build["commands"]), "unverified_build")
    require(sha(binary) == expected and any(Path(p).resolve() == binary.resolve() and h == expected
        for p, h in build["binary_sha256"].items()), "build_binary_mismatch")
    for relative, digest in build["source_before"].items():
        relative = Path(relative.replace("\\", "/"))
        target = (archive / relative).resolve()
        require(not relative.is_absolute() and ".." not in relative.parts and target.is_relative_to(archive.resolve())
            and sha(target) == digest, "build_archive_mismatch")
    return build


def verify_plan(directory, plan, *, loaded=False):
    directory = Path(directory)
    require(plan["schema"] == PLAN_SCHEMA and plan["cases"] == {k: list(v) for k, v in ARMS.items()}
        and plan["abi"] == {k: list(v) for k, v in abi.ABI027.items()}
        and plan["maximum_native_workers"] == 1 and plan["worker_timeout_seconds"] == 120.
        and plan["total_declared_sessions"] == sum(map(len, ARMS.values())), "plan_domain")
    require(set(plan["source_sha256"]) == {str(p) for p in source_paths()} and not source_changes(plan), "source_inventory_changed")
    for name, digest in plan["source_sha256"].items():
        require(sha(directory / "source" / Path(name).relative_to(ROOT)) == digest, "source_archive_changed")
    require(not loaded or not unarchived_loaded_sources(plan), "unarchived_loaded_sources")
    reference = plan["contract_reference"]
    require(read(directory / "contract_reference.json") == reference
        and sha(directory / "candidate_contract.json") == reference["sha256"], "candidate_contract_archive_changed")
    require(read(directory / "candidate_contract.json").get("runtime_acceptance") is None, "candidate_contract_must_be_preacceptance")
    checked = abi.verify_contract(reference)["contract"]
    require(checked["binary_sha256"] == plan["binary_sha256"] and checked["binary"] == plan["binary"]
        and checked["build_receipt_sha256"] == plan["build_receipt_sha256"], "candidate_contract_changed")
    require(plan["native026_sha256"] == NATIVE026_SHA and sha(plan["native026_build"]) == plan["native026_build_sha256"], "legacy_authority_changed")
    verify_build(plan["native026_build"], plan["native026_source_archive"], plan["native026_binary"], NATIVE026_SHA)
    verify_build(checked["build_receipt"], checked["source_archive"], checked["binary"], checked["binary_sha256"])
    require(set(plan["input_sha256"]) == set(LEGACY_CASES + V3_CASES), "input_inventory_changed")
    for case, digest in plan["input_sha256"].items():
        path = directory / "inputs" / (case + ".json.gz")
        require(sha(path) == digest and exact(read(path)) == exact(scene(case)), "input_archive_changed:" + case)
    return checked


def prepare(directory, reference, native026, native026_build):
    directory, native026, native026_build = map(lambda p: Path(p).resolve(), (directory, native026, native026_build))
    checked = abi.verify_contract(reference)["contract"]
    verify_build(native026_build, native026_build.parent / "source", native026, NATIVE026_SHA)
    directory.mkdir(parents=True, exist_ok=False)
    paths = source_paths()
    for path in paths:
        target = directory / "source" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
    (directory / "inputs").mkdir()
    for case in LEGACY_CASES + V3_CASES: write(directory / "inputs" / (case + ".json.gz"), scene(case))
    write(directory / "contract_reference.json", reference)
    shutil.copyfile(reference["path"], directory / "candidate_contract.json")
    plan = {"schema": PLAN_SCHEMA, "cases": {k: list(v) for k, v in ARMS.items()},
        "abi": {k: list(v) for k, v in abi.ABI027.items()}, "contract_reference": reference,
        "binary": checked["binary"], "binary_sha256": checked["binary_sha256"],
        "build_receipt_sha256": checked["build_receipt_sha256"],
        "native026_binary": str(native026), "native026_sha256": NATIVE026_SHA,
        "native026_build": str(native026_build), "native026_build_sha256": sha(native026_build),
        "native026_source_archive": str(native026_build.parent / "source"),
        "source_sha256": {str(p): sha(p) for p in paths},
        "input_sha256": {case: sha(directory / "inputs" / (case + ".json.gz")) for case in LEGACY_CASES + V3_CASES},
        "maximum_native_workers": 1, "worker_timeout_seconds": 120., "total_declared_sessions": sum(map(len, ARMS.values())),
        "complete_request_100ms_certified": False, "physics_subtracted_ns": 0}
    write(directory / "plan.json", plan); verify_plan(directory, plan)
    return plan


def worker(directory, arm):
    plan = read(directory / "plan.json"); verify_plan(directory, plan, loaded=True)
    native = native_host.load_native(plan["native026_binary"] if arm == "native026_plain" else plan["binary"])
    expected = NATIVE026_SHA if arm == "native026_plain" else plan["binary_sha256"]
    require(native._g31_native_artifact_identity["sha256"] == expected, "loaded_binary_mismatch")
    target = directory / arm; target.mkdir(exist_ok=False)
    for index, case in enumerate(ARMS[arm], 1):
        try:
            raw = run_case(native, case, timed=arm == "native027_timed", reference=plan["contract_reference"], identity=index)
            write(target / (case + ".json.gz"), raw)
        except BaseException as error:
            write(target / (case + ".failure.json"), {"status": "unknown_case_failure", "case": case,
                "error": traceback.format_exc(), "raw_prefix": getattr(error, "gate_partial", None)})
            raise
    verify_plan(directory, plan, loaded=True)
    write(target / "completion.json", {"schema": SCHEMA, "status": "completed_declared_arm", "arm": arm,
        "cases": list(ARMS[arm]), "native_binary_sha256": expected, "source_changed": source_changes(plan),
        "runtime_loaded_sha256": loaded_project_sources(), "unarchived_loaded_sources": unarchived_loaded_sources(plan)})


def verify_saved_gate(reference, contract=None):
    """Re-read all raw files; an external passed Boolean is never sufficient."""
    path = Path(reference["path"])
    require(sha(path) == reference["sha256"], "receipt_changed")
    directory = path.parent; receipt = read(path); plan = read(directory / "plan.json")
    require(receipt["schema"] == SCHEMA and receipt["status"] == "captured_pending_independent_verification"
        and receipt["source_changed"] == [] and sha(directory / "plan.json") == receipt["plan_sha256"], "receipt_or_plan_changed")
    checked = verify_plan(directory, plan)
    if contract is not None:
        require(all(contract[k] == checked[k] for k in ("binary", "binary_sha256", "build_receipt_sha256", "abi", "endpoint_methods")), "acceptance_contract_mismatch")
    require(set(receipt["raw"]) == set(receipt["process_sha256"]) == set(receipt["completion_sha256"]) == set(ARMS), "receipt_arm_domain")
    records = {}
    for arm, cases in ARMS.items():
        process_path = directory / (arm + ".process.json")
        require(sha(process_path) == receipt["process_sha256"][arm], "process_receipt_changed")
        process = read(process_path)
        require(process["status"] == "process_exited" and type(process["exit_code"]) is int and process["exit_code"] == 0, "worker_failed:" + arm)
        require(process["command"] == [sys.executable, "-m", MODULE, "--output", str(directory.resolve()), "--arm", arm], "process_command_changed")
        completion_path = directory / arm / "completion.json"
        require(sha(completion_path) == receipt["completion_sha256"][arm], "worker_completion_changed")
        completion = read(completion_path)
        require(completion["schema"] == SCHEMA and completion["status"] == "completed_declared_arm"
            and completion["arm"] == arm and completion["cases"] == list(cases)
            and not completion["source_changed"] and not completion["unarchived_loaded_sources"]
            and completion["native_binary_sha256"] == (NATIVE026_SHA if arm == "native026_plain" else plan["binary_sha256"]), "worker_closure_or_domain_changed")
        loaded = completion["runtime_loaded_sha256"]
        required_loaded = {str(Path(__file__).resolve()), str(Path(native_host.__file__).resolve()),
            str(Path(__file__).with_name("capture_native027_request_timing.py").resolve())}
        require(required_loaded <= set(loaded) <= set(plan["source_sha256"])
            and all(plan["source_sha256"][p] == digest for p, digest in loaded.items()), "runtime_loaded_source_changed")
        require(set(receipt["raw"][arm]) == set(cases), "raw_case_domain")
        records[arm] = {}
        for case in cases:
            raw_path = directory / arm / (case + ".json.gz")
            require(sha(raw_path) == receipt["raw"][arm][case], "raw_changed:" + arm + ":" + case)
            record = read(raw_path); records[arm][case] = record
            expected_binary = plan["native026_binary"] if arm == "native026_plain" else plan["binary"]
            require(record["native_binary"]["sha256"] == (NATIVE026_SHA if arm == "native026_plain" else plan["binary_sha256"])
                and Path(record["native_binary"]["resolved_path"]).resolve() == Path(expected_binary).resolve(), "raw_binary_identity")
    return {"status": "verified_raw_runtime_gate", "gates": check_records(records), "runtime_accepted": True,
        "complete_request_100ms_certified": False, "physics_subtracted_ns": 0, "declared_sessions": sum(map(len, ARMS.values()))}


def execute(directory):
    plan = read(directory / "plan.json"); verify_plan(directory, plan)
    require(not (directory / "receipt.json").exists(), "campaign_already_attempted")
    processes = {}
    for arm in ARMS:
        command = [sys.executable, "-m", MODULE, "--output", str(directory.resolve()), "--arm", arm]
        started = time.perf_counter(); process = {"command": command, "status": "unknown_launch_failure", "exit_code": None}
        try:
            with (directory / (arm + ".stdout.log")).open("xb") as stdout, (directory / (arm + ".stderr.log")).open("xb") as stderr:
                child = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=plan["worker_timeout_seconds"], check=False)
            process.update(status="process_exited", exit_code=child.returncode)
        except subprocess.TimeoutExpired: process["status"] = "hard_timeout"
        except OSError as error: process["error"] = repr(error)
        process["wall_seconds"] = time.perf_counter() - started
        write(directory / (arm + ".process.json"), process); processes[arm] = process
    receipt = {"schema": SCHEMA, "status": "captured_pending_independent_verification", "plan_sha256": sha(directory / "plan.json"),
        "source_changed": source_changes(plan), "process_sha256": {arm: sha(directory / (arm + ".process.json")) for arm in ARMS},
        "completion_sha256": {arm: sha(directory / arm / "completion.json") if (directory / arm / "completion.json").is_file() else None for arm in ARMS},
        "raw": {arm: {case: sha(directory / arm / (case + ".json.gz")) if (directory / arm / (case + ".json.gz")).is_file() else None
            for case in cases} for arm, cases in ARMS.items()}}
    write(directory / "receipt.json", receipt)
    reference = {"path": str((directory / "receipt.json").resolve()), "sha256": sha(directory / "receipt.json")}
    try: report = verify_saved_gate(reference)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        report = {"status": "unknown_invalid_or_incomplete_gate", "error": str(error), "runtime_accepted": False}
    write(directory / "independent_verification.json", report)
    return 0 if report["status"] == "verified_raw_runtime_gate" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--reference", type=Path)
    parser.add_argument("--native026", type=Path); parser.add_argument("--native026-build", type=Path)
    parser.add_argument("--prepared", action="store_true"); parser.add_argument("--execute", action="store_true")
    parser.add_argument("--arm", choices=ARMS); args = parser.parse_args(); directory = args.output.resolve()
    if args.arm: worker(directory, args.arm); return 0
    if not args.prepared:
        require(args.reference is not None and args.native026 is not None and args.native026_build is not None, "preparation_arguments_required")
        prepare(directory, read(args.reference), args.native026, args.native026_build)
    if args.execute: return execute(directory)
    verify_plan(directory, read(directory / "plan.json")); return 0


if __name__ == "__main__": sys.exit(main())

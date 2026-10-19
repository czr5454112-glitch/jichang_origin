"""One predeclared, source-local waiting112->113 executability gate.

The unchanged original input is an explicit suffix-reroute research domain.
No earlier four-command chain, hidden result, future arrival or native fork
feeds the decision. This script does not assess benefit or protection.
"""
from __future__ import annotations

import argparse
import ast
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from .event_protocol_control import run_event_protocol_control
from .native_host import load_native
from .protocol_control import ProtocolClient

ROOT = Path(__file__).resolve().parents[3]
OUTPUTS = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
SCHEMA = "g31.original_waiting112_gate.v1"
BINARY_SHA = "c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943"
INPUT_SHA = "eb4f9baab3dc772d4812134341a2741187fc8258756f304020d719f771e62b68"
ACCEPTANCE_SHA = "ec0bf85b9a4be4030ed13209c75656ee2b83910235f76bec652943ae98ba99df"
HORIZON = 12000.
WIRE = 2.
PROBE_PERIOD = 60.
SHARD_ACTIVATIONS = 500
MAX_ACTIVATIONS = 100000
TERMINAL = {"updated_ack_and_actual_edge", "delivered_rejection", "updated_but_other_edge", "submission_rejected"}


def require(ok, reason):
    if not ok: raise ValueError("waiting112:" + reason)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def gzread(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream: return json.load(stream)
def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    # Windows readers/antivirus can briefly deny atomic replacement. Retain
    # the complete temp file on permanent failure; never silently drop data.
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 5: raise
            time.sleep(.01 * (attempt + 1))
def gzwrite(path, value):
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)


def source_paths():
    """Static repo import closure plus package initializers; no basename collapse."""
    pending, found = [Path(__file__)], set()
    def enqueue(target):
        for candidate in (target.with_suffix(".py"), target / "__init__.py"):
            if candidate.is_file() and candidate.resolve().is_relative_to(ROOT):
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
                bases = [path.parent] if node.level else [ROOT, ROOT / "src"]
                for base in bases:
                    for _ in range(max(0, node.level - 1)): base = base.parent
                    if node.module: base = base.joinpath(*node.module.split(".")); enqueue(base)
                    for alias in node.names:
                        if alias.name != "*": enqueue(base.joinpath(*alias.name.split(".")))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for base in (ROOT, ROOT / "src"): enqueue(base.joinpath(*alias.name.split(".")))
    return sorted(found)


def positive_suffix(view):
    """Public static positive-capacity reachability, excluding a return to112."""
    nodes = {r["node"]: r for r in view["node_contracts"]}
    allowed = {(r["from"], r["to"]) for r in view["edge_contracts"] if r["capacity"] > 0}
    graph = {}
    for u, v, length, speed in view["edge_records"]:
        require(math.isfinite(length) and math.isfinite(speed) and length > 0 and speed > 0,
                "invalid_static_edge")
        if (u, v) in allowed and v != 112 and nodes[v]["capacity"] > 0:
            graph.setdefault(u, []).append(v)
    queue, seen = [(113,)], {113}
    for path in queue:
        if path[-1] == 53: return list(path)
        for target in sorted(graph.get(path[-1], [])):
            if target not in seen: seen.add(target); queue.append((*path, target))
    return None


def eligible(view):
    """Only currently local, stationary, loaded, pre-Storage jobs are eligible."""
    now, owner = view["now"], view["owner_id"]
    require(math.isfinite(now) and now >= 0, "invalid_clock")
    contracts = {row["node"]: row for row in view["node_contracts"]}
    source, receiver = contracts[112], contracts[113]
    require(source["resource_owner"] == owner, "wrong_source_owner")
    # This gate deliberately admits no remote-occupancy inference.
    require(receiver["resource_owner"] == owner and "occupancy" in receiver, "receiver_not_local")
    require(isinstance(receiver["occupancy"], int) and 0 <= receiver["occupancy"] <= receiver["capacity"],
            "invalid_receiver_occupancy")
    service = next(row[2] for row in view["node_records"] if row[0] == 112)
    require(math.isfinite(service) and service >= 0, "invalid_source_service")
    jobs = {j["business_bag_id"]: j for j in view["jobs"]}
    require(len(jobs) == len(view["jobs"]), "duplicate_visible_job")
    require(len({t["tray_id"] for t in view["trays"]}) == len(view["trays"]), "duplicate_visible_tray")
    rows = []
    for tray in view["trays"]:
        job = jobs.get(tray["business_bag_id"])
        if (tray["node"] != 112 or tray["edge_to"] >= 0 or tray["mode"] != "loaded" or not job or
                job["status"] != "in_transit" or job["storage_node"] != 53 or
                job["storage_entered_at"] >= 0 or job["storage_released_at"] >= 0 or
                not job["allow_suffix_reroute"] or not 0 <= job["arrival"] <= now or job["loaded_at"] < 0):
            continue
        require(tray["committed_prefix"] and tray["committed_prefix"][-1] == 112, "prefix_not_current_node")
        require(all(type(tray[k]) is int and tray[k] >= 0 for k in ("generation", "traversal_id")), "invalid_identity")
        rows.append((job["arrival"], job["business_bag_id"], tray["tray_id"], tray, job))
    return sorted(rows, key=lambda row: row[:3]), service, receiver


def tray_identity(tray):
    return (tray["tray_id"], tray["business_bag_id"], tray["generation"], tray["traversal_id"],
            tuple(tray["committed_prefix"]))


class WaitingIntent:
    def __init__(self):
        self.status = "waiting_for_two_current_observations"
        self.candidates = {}
        self.decision = None
        self.edge = None
        self.reservation = None
        self.ack = None
        self.last_now = -1.
        self.observation_count = 0

    def snapshot(self):
        return copy.deepcopy({k: v for k, v in vars(self).items() if k != "candidates"})

    def observe(self, view, client):
        if self.status in TERMINAL: return
        now = view["now"]
        require(now >= self.last_now, "observation_clock_regressed")
        self.last_now = now; self.observation_count += 1
        if self.decision is not None:
            decision = self.decision
            row = client.state["outbox"][decision["request_id"]]
            ack = row.get("client_view", {}).get("last_delivered_ack", {})
            if ack:
                require(ack["delivered_at"] <= now, "future_ack")
                self.ack = copy.deepcopy(ack)
            before = decision["local_tray"]
            for tray in view["trays"]:
                if (tray["tray_id"] != before["tray_id"] or tray["business_bag_id"] != before["business_bag_id"] or
                        tray["generation"] != before["generation"]): continue
                base = before["committed_prefix"]
                prefix = list(tray["committed_prefix"])
                evidence = "completed_committed_prefix"
                if tray["edge_to"] >= 0:
                    self.reservation = {"observed_at": now, "owner": view["owner_id"], "local_tray": copy.deepcopy(tray)}
                    # edge_to is set at reservation publication, potentially
                    # before future EDGE_ENTER. The public edge_exit_at field
                    # exists only after a matching actual EDGE_ENTER receipt.
                    # Otherwise only completed EDGE_EXIT prefix entries count.
                    exit_at = tray.get("edge_exit_at")
                    if (len(prefix) == len(base) and type(exit_at) in (int, float) and
                            math.isfinite(exit_at) and now < exit_at and tray["edge_from"] == base[-1]):
                        prefix.append(tray["edge_to"])
                        evidence = "matched_observed_entry_inflight"
                if prefix[:len(base)] == base and len(prefix) > len(base) and self.edge is None:
                    require(tray["traversal_id"] > before["traversal_id"], "edge_without_new_traversal")
                    self.edge = {"from": 112, "to": prefix[len(base)], "observed_at": now,
                                 "owner": view["owner_id"], "local_tray": copy.deepcopy(tray),
                                 "evidence": evidence}
            if self.ack and self.ack.get("status") in {"rejected", "expired", "failed", "cancelled"}:
                self.status = "delivered_rejection"
            elif self.ack and self.ack.get("status") == "updated" and self.edge:
                self.status = "updated_ack_and_actual_edge" if self.edge["to"] == 113 else "updated_but_other_edge"
            return
        rows, service, receiver = eligible(view)
        keys = {tray_identity(row[3]) for row in rows}
        self.candidates = {key: value for key, value in self.candidates.items() if key in keys}
        for _, _, _, tray, job in rows:
            key = tray_identity(tray)
            first = self.candidates.setdefault(key, {"at": now, "local_tray": copy.deepcopy(tray),
                "local_job": copy.deepcopy(job), "source_owner": view["owner_id"]})
            if now - first["at"] < WIRE + service: continue
            if receiver["occupancy"] >= receiver["capacity"]: continue
            if now + WIRE + .2 > HORIZON: continue
            if not any(r["from"] == 112 and r["to"] == 113 and r["capacity"] > 0 for r in view["edge_contracts"]): continue
            suffix = positive_suffix(view)
            if suffix is None: continue
            owner = view["owner_id"]
            payload = {"business_bag_id": job["business_bag_id"], "tray_id": tray["tray_id"], "from": 112, "next": 113,
                "expected_generation": tray["generation"], "expected_traversal": tray["traversal_id"],
                "expiry": now + 120., "message_delay": WIRE}
            identity = f"live:{len(owner.encode('utf-8'))}:{owner}:waiting112-once"
            identity, reply = client.submit(owner, "route", payload, request_id=identity)
            self.decision = {"at": now, "request_id": identity, "owner": owner, "first_observation": copy.deepcopy(first),
                "local_tray": copy.deepcopy(tray), "local_job": copy.deepcopy(job), "source_service_seconds": service,
                "receiver_local_contract": copy.deepcopy(receiver), "positive_static_suffix_avoiding112": suffix,
                "request": copy.deepcopy(payload), "submission_reply": copy.deepcopy(reply)}
            self.status = "submission_rejected" if reply.get("status") == "rejected" else "awaiting_delivered_ack_and_edge"
            return


class GateTape:
    """Separate lossless online API tape; written before returning to the caller."""
    def __init__(self, native, directory):
        self.native, self.directory, self.count = native, directory, 0
        directory.mkdir()
        self.rows = []
    @property
    def physical_time(self): return self.native.physical_time
    def call(self, method, *args):
        row = {"ordinal": self.count, "method": method, "args": copy.deepcopy(args), "physical_before": self.physical_time}
        self.count += 1
        try:
            value = getattr(self.native, method)(*args)
            row["result"] = copy.deepcopy(value)
            return value
        except BaseException as error:
            row["error"] = type(error).__name__ + ":" + str(error)
            raise
        finally:
            row["physical_after"] = self.physical_time
            path = self.directory / f"{row['ordinal']:06d}.json.gz"
            gzwrite(path, row)
            self.rows.append({"path": path.name, "sha256": sha(path), "method": method})
            write(self.directory / "manifest.json", {"schema": SCHEMA, "rows": self.rows})
    def submit_protocol_command(self, payload): return self.call("submit_protocol_command", payload)
    def protocol_command(self, owner, identity): return self.call("protocol_command", owner, identity)
    def observe_protocol_control_policy_recent(self, owner, validity):
        return self.call("observe_protocol_control_policy_recent", owner, validity)


class Boundary:
    def __init__(self, native, owner, tape):
        self.native, self.owner, self.tape = native, owner, tape
        self.client, self.intent = ProtocolClient(tape, retry_period=60.), WaitingIntent()
        self.next_probe = 0.
    def __getattr__(self, name): return getattr(self.native, name)
    # Explicit capabilities preserve the ordinary controller's accepted projection.
    def observe_protocol_control_policy(self, owner): return self.native.observe_protocol_control_policy(owner)
    def observe_protocol_control_policy_recent(self, owner, validity):
        return self.native.observe_protocol_control_policy_recent(owner, validity)
    def advance_until_owner_notification(self, owners, after, horizon, *, max_events):
        response = self.native.advance_until_owner_notification(owners, after, horizon, max_events=max_events)
        now = self.native.physical_time
        pending = self.intent.decision is not None
        if (response.get("timestamp_complete") and self.intent.status not in TERMINAL and
                (now >= self.next_probe or pending and self.owner in response.get("notifications", {}))):
            if pending: self.client.refresh(owner_id=self.owner)
            view = self.tape.observe_protocol_control_policy_recent(self.owner, 120.)
            self.intent.observe(view, self.client)
            self.next_probe = now + PROBE_PERIOD
        return response


def verify_input(data):
    require(len(data["jobs"]) == 28506 and len(data["trays"]) == 22, "original_population")
    require(all(j["allow_suffix_reroute"] is True for j in data["jobs"]), "research_permission_domain")
    require(data["owner_notifications"]["enabled"] is True and data["owner_protocol"]["enabled"] is True,
            "native_notifications_protocol_required")
    require(data["owner_protocol"]["ack_delay"] == .2, "original_ack_delay")
    contracts = {r["node"]: r for r in data["node_contracts"]}
    require(contracts[112]["resource_owner"] == contracts[113]["resource_owner"], "source_receiver_not_same_owner")
    require(positive_suffix(data) is not None, "no_positive_static_suffix")
    return contracts[112]["resource_owner"]


def prepare(output, source, binary, timeout):
    require(math.isfinite(timeout) and 0 < timeout <= 1200., "bounded_parent_timeout_required")
    require(sha(source / "input.json.gz") == INPUT_SHA, "source_input_identity")
    data = gzread(source / "input.json.gz"); owner = verify_input(data)
    build_path = OUTPUTS / "native026_build_001/receipt.json"
    acceptance_path = OUTPUTS / "native026_acceptance_001/receipt.json"
    assessment_path = acceptance_path.parent / "late/assessment.json"
    build, accepted, assessment = read(build_path), read(acceptance_path), read(assessment_path)
    require(sha(binary) == BINARY_SHA and build["binary_sha256"].get(str(binary.resolve())) == BINARY_SHA, "compiled_binary_authority")
    require(build["status"] == "build_passed_tests_held" and build["source_changed"] == [] and
            all(c["exit_code"] == 0 for c in build["commands"]), "build_not_successful")
    require(sha(acceptance_path) == ACCEPTANCE_SHA and accepted["status"] == "passed" and
            accepted["source_changed"] == [] and accepted["input_changed"] == [] and
            all(row["exit_code"] == 0 for row in accepted["arms"]), "acceptance_not_verified")
    require(assessment["status"] == "passed" and assessment["entry_seal_verified_against_original_native024"] and
            assessment["ordered_saved_continuation_exact"] and assessment["reference_indexed_exit_seals_exact"], "late_gate_missing")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source / "input.json.gz", output / "input.json.gz")
    sources = {str(path): sha(path) for path in source_paths()}
    for path, digest in sources.items():
        target = output / "source_archive" / Path(path).relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        require(sha(target) == digest, "source_copy_changed")
    for relative, digest in build["source_before"].items():
        source_file = build_path.parent / "source" / relative
        require(sha(source_file) == digest, "compiled_archive_changed")
        target = output / "compiled_source_archive" / relative
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source_file, target)
    for path in (build_path, acceptance_path, assessment_path):
        shutil.copyfile(path, output / (path.parent.name + "_" + path.name))
    plan = {"schema": SCHEMA, "status": "prepared_native_unexecuted", "source_input_sha256": INPUT_SHA,
        "source_input_path": str((source / "input.json.gz").resolve()), "input_business_count": 28506, "trays": 22,
        "native_binary": str(binary.resolve()), "native_binary_sha256": BINARY_SHA, "source_before": sources,
        "authority_pins": {str(path): sha(path) for path in (build_path, acceptance_path, assessment_path)},
        "compiled_source_sha256": build["source_before"], "source_owner": owner, "horizon": HORIZON,
        "max_activations": MAX_ACTIVATIONS, "event_budget_per_boundary": 100000, "shard_activations": SHARD_ACTIVATIONS,
        "parent_timeout_seconds": timeout, "native_branch_budget": 1,
        "rule": "At complete native boundaries sample this owner's fresh policy view at most every60 physical seconds before submission. Select the first qualified snapshot; within it use arrival,business ID,tray ID order. Require two observed stationary matching identities/prefixes separated by2+source service seconds, pre-Storage53 loaded state, suffix permission, current local113 occupancy belowcapacity and a public positive-capacity static113→53 path avoiding112. Submit one immutable2s route request; retry only same request if necessary.",
        "continuation": "Unchanged event R2, routes=False, forecasts/predictive/prebalance=True;60speriod,.5spublication,60sretry,120slease. No earlier chain intents.",
        "completion": "Delivered updatedACK and actual112→113 entry: either inflight with native edge_exit_at derived from its matching observed EDGE_ENTER receipt, or a newly completed EDGE_EXIT committed prefix. Reservation-only edge_to or ACKalone is insufficient; FIFO/shield/capacity remain native.",
        "stop": "After the first completed raw500-activation shard containing a terminal gate outcome; otherwise H12000/100000activations/nativebudget/hardparenttimeout. Subsequent ordinaryR2 diagnostics in that shard are retained.",
        "comparison_admitted": False, "benefit": None, "strict_protection": "not_assessed", "complete_100ms_certified": False}
    write(output / "preregistered_protocol.json", plan)
    write(output / "branch_ledger.json", {"single_waiting_gate": {"status": "unknown_unexecuted"}})
    return plan


def verify_pins(output, plan, *, runtime=False):
    require(sha(output / "input.json.gz") == plan["source_input_sha256"], "input_changed")
    require(sha(plan["native_binary"]) == plan["native_binary_sha256"] == BINARY_SHA, "binary_changed")
    for path, digest in plan["source_before"].items():
        require(sha(path) == digest and sha(output / "source_archive" / Path(path).relative_to(ROOT)) == digest, "python_source_changed")
    for path, digest in plan["authority_pins"].items(): require(sha(path) == digest, "authority_changed")
    for path, digest in plan["compiled_source_sha256"].items():
        require(sha(output / "compiled_source_archive" / path) == digest, "compiled_archive_changed")
    if runtime:
        imported = {str(Path(m.__file__).resolve()) for m in list(sys.modules.values()) if
                    getattr(m, "__file__", None) and Path(m.__file__).suffix == ".py" and Path(m.__file__).resolve().is_relative_to(ROOT)}
        require(imported <= set(plan["source_before"]), "unrecorded_runtime_import")


def assess(intent, calls):
    """Narrow gate evidence check; never translates success into business benefit."""
    decision, edge, ack = intent.get("decision"), intent.get("edge"), intent.get("ack")
    if not decision: return {"status": "unknown_no_qualifying_observed_wait", "executable": None}
    first, before, payload = decision["first_observation"], decision["local_tray"], decision["request"]
    require(tray_identity(first["local_tray"]) == tray_identity(before), "wait_identity_changed")
    require(decision["at"] - first["at"] >= WIRE + decision["source_service_seconds"], "wait_not_proved")
    require(payload["from"] == 112 and payload["next"] == 113 and payload["message_delay"] == WIRE and
            payload["expected_generation"] == before["generation"] and payload["expected_traversal"] == before["traversal_id"], "request_scope_changed")
    require(calls and sum(not row["retry"] for row in calls) == 1 and
            all(row["kind"] == "route" and row["request"] == calls[0]["request"] for row in calls), "more_than_one_immutable_request")
    require(calls[0]["at"] == decision["at"] and calls[0]["request"]["request_id"] == decision["request_id"], "submission_identity")
    if ack:
        require(decision["at"] <= ack["delivered_at"] <= intent["last_now"], "ack_delivery_chronology")
        if ack.get("status") in {"updated", "rejected", "expired", "failed", "cancelled"}:
            require(decision["at"] + WIRE <= ack["completed_at"] <= ack["delivered_at"], "ack_chronology")
    passed = intent["status"] == "updated_ack_and_actual_edge"
    if passed:
        require(ack and ack["status"] == "updated" and edge and edge["from"] == 112 and edge["to"] == 113,
                "missing_actual_edge_or_ack")
        require(decision["at"] + WIRE <= edge["observed_at"] <= HORIZON, "edge_chronology")
    return {"status": "passed_executability_only" if passed else intent["status"], "executable": True if passed else None,
            "benefit": None, "strict_protection": "not_assessed", "complete_100ms_certified": False}


class ReplayGateTape:
    """Pure exact endpoint replay; never creates or consults a native session."""
    def __init__(self, rows): self.rows, self.position, self.now = rows, 0, rows[0]["physical_before"]
    @property
    def physical_time(self): return self.now
    def call(self, method, *args):
        require(self.position < len(self.rows), "missing_api_row")
        row = self.rows[self.position]
        require(row["ordinal"] == self.position and row["method"] == method and row["args"] == list(args), "api_tape_mismatch")
        require(row["physical_before"] == row["physical_after"] == self.now and "error" not in row, "invalid_gate_read_or_submit")
        self.position += 1
        return copy.deepcopy(row["result"])
    def submit_protocol_command(self, payload): return self.call("submit_protocol_command", payload)
    def protocol_command(self, owner, identity): return self.call("protocol_command", owner, identity)


def replay_gate_rows(rows, expected_intent, expected_calls):
    require(rows, "missing_gate_tape")
    replay = ReplayGateTape(rows)
    client, intent = ProtocolClient(replay, retry_period=60.), WaitingIntent()
    while replay.position < len(rows):
        row = rows[replay.position]
        require(row["physical_before"] >= replay.now, "api_clock_regressed")
        replay.now = row["physical_before"]
        if row["method"] == "protocol_command":
            require(intent.decision is not None, "query_before_submission")
            client.refresh(owner_id=intent.decision["owner"])
            row = rows[replay.position]
        require(row["method"] == "observe_protocol_control_policy_recent" and len(row["args"]) == 2 and row["args"][1] == 120., "unexpected_gate_endpoint")
        view = replay.call(row["method"], *row["args"])
        require(view["now"] == row["physical_before"] and view["owner_id"] == row["args"][0], "observation_identity")
        intent.observe(view, client)
    strip_clocks = lambda calls: [{key: value for key, value in call.items() if key != "submit_compute_ms"} for call in calls]
    require(intent.snapshot() == expected_intent, "replayed_intent_mismatch")
    require(strip_clocks(client.calls) == strip_clocks(expected_calls), "replayed_calls_mismatch")
    return assess(intent.snapshot(), client.calls)


def verify_evidence(output):
    plan = read(output / "preregistered_protocol.json"); verify_pins(output, plan)
    raw = gzread(output / "raw_final.json.gz")
    manifest = read(output / "gate_api/manifest.json")
    rows = []
    for index, item in enumerate(manifest["rows"]):
        require(item["path"] == f"{index:06d}.json.gz", "gate_path_or_order")
        path = output / "gate_api" / item["path"]
        require(sha(path) == item["sha256"], "gate_row_changed")
        row = gzread(path)
        require(row["method"] == item["method"], "gate_method_changed")
        rows.append(row)
    require(len(list((output / "gate_api").glob("*.json.gz"))) == len(rows), "gate_row_omitted")
    assessment = replay_gate_rows(rows, raw["intent"], raw["gate_calls"])
    require(assessment == raw["assessment"] == read(output / "assessment.json"), "assessment_changed")
    source_owner = plan["source_owner"]
    require(all(row["args"][0] == source_owner for row in rows if row["method"] != "submit_protocol_command"), "foreign_owner_read")
    require(raw["native_binary_sha256"] == BINARY_SHA and raw["input_sha256"] == INPUT_SHA and raw["source_changed"] == [], "raw_identity")
    require(0 <= raw["physical_time"] <= HORIZON and raw["owner_activations"] <= MAX_ACTIVATIONS, "gate_budget_exceeded")
    trace_offset = 0; activation_count = 0; final_part = None
    for index, item in enumerate(read(output / "shards.json")["shards"]):
        require(Path(item["path"]).as_posix() == f"segments/{index:04d}.json.gz", "shard_path_or_order")
        path = output / item["path"]
        require(sha(path) == item["sha256"], "raw_shard_changed")
        final_part = gzread(path)["run"]
        trace = sorted(row["trace_sequence"] for key in ("control_records", "native_batches") for row in final_part[key])
        require(trace == list(range(trace_offset, trace_offset + len(trace))), "controller_trace_gap")
        trace_offset += len(trace); activation_count += len(final_part["control_records"])
    require(final_part is not None and final_part["controller_state"] == raw["controller_state"] and final_part["result"] == raw["result"]
            and activation_count == raw["owner_activations"], "final_raw_mismatch")
    return {"status": "passed", "assessment": assessment, "gate_api_rows": len(rows), "controller_trace_rows": trace_offset,
            "proof_scope": "Saved source-local API decisions replay exactly; native edge witness remains the actual captured public native observation. No business benefit or protection proof."}


def worker(output):
    plan = read(output / "preregistered_protocol.json"); verify_pins(output, plan)
    data = gzread(output / "input.json.gz")
    session = load_native(plan["native_binary"]).NativeSession(data)
    tape = GateTape(session, output / "gate_api")
    boundary = Boundary(session, plan["source_owner"], tape)
    owners = sorted({row["resource_owner"] for row in data["node_contracts"]})
    state = result = None; offset = activations = 0
    manifest = {"schema": SCHEMA, "shards": [], "all_returned_controller_records_retained": True}
    (output / "segments").mkdir()
    started = time.perf_counter()
    try:
        while activations < MAX_ACTIVATIONS:
            part = run_event_protocol_control(boundary, owners, horizon=HORIZON, control_period=60., command_delay=WIRE,
                publication_delay=.5, retry_period=60., lease_seconds=120., routes=False, forecasts=True, predictive=True,
                prebalance=True, event_budget=100000, max_activations=min(SHARD_ACTIVATIONS, MAX_ACTIVATIONS-activations),
                state=state, _consume_state=True)
            for key in ("control_records", "native_batches"):
                for row in part[key]: row["trace_sequence"] += offset
            offset += len(part["control_records"]) + len(part["native_batches"])
            activations += len(part["control_records"])
            path = output / "segments" / f"{len(manifest['shards']):04d}.json.gz"
            gzwrite(path, {"run": part, "intent": boundary.intent.snapshot(), "gate_calls": boundary.client.calls,
                           "gate_outbox": boundary.client.state})
            manifest["shards"].append({"path": str(path.relative_to(output)), "sha256": sha(path),
                "physical_time": session.physical_time, "status": part["status"], "gate_status": boundary.intent.status})
            write(output / "shards.json", manifest)
            write(output / "heartbeat.json", {"stage": "raw_shard_saved", "physical_time": session.physical_time,
                "activations": activations, "gate_status": boundary.intent.status, "wall_seconds": time.perf_counter()-started})
            state, result, status = part["controller_state"], part["result"], part["status"]
            part = None
            if status != "control_budget_exhausted" or boundary.intent.status in TERMINAL: break
        verify_pins(output, plan, runtime=True)
        assessment = assess(boundary.intent.snapshot(), boundary.client.calls)
        raw = {"schema": SCHEMA, "status": status, "assessment": assessment, "intent": boundary.intent.snapshot(),
            "gate_calls": boundary.client.calls, "gate_outbox": boundary.client.state, "controller_state": state,
            "result": result, "physical_time": session.physical_time, "native_state_sha256": session.offline_state_sha256(),
            "owner_activations": activations, "wall_seconds": time.perf_counter()-started,
            "source_changed": [], "native_binary_sha256": BINARY_SHA, "input_sha256": INPUT_SHA}
        gzwrite(output / "raw_final.json.gz", raw)
        write(output / "assessment.json", assessment)
    except BaseException as error:
        gzwrite(output / "error_prefix.json.gz", {"status": "unknown_worker_exception", "error": repr(error),
            "traceback": traceback.format_exc(), "physical_time": session.physical_time,
            "intent": boundary.intent.snapshot(), "gate_calls": boundary.client.calls,
            "gate_outbox": boundary.client.state, "last_returned_controller_state": state, "last_returned_result": result,
            "incomplete_current_controller_call": True})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=OUTPUTS / "original_tie_streamed_native_002")
    parser.add_argument("--binary", type=Path, default=ROOT / "build_lt_session_026/python/czr005_circulation.cp311-win_amd64.pyd")
    parser.add_argument("--timeout-seconds", type=float, default=600.)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--prepared", action="store_true", help="Execute an unchanged already prepared plan.")
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker: worker(output); return
    plan = read(output / "preregistered_protocol.json") if args.prepared else prepare(output, args.source, args.binary, args.timeout_seconds)
    verify_pins(output, plan)
    if not args.execute: print("prepared_native_unexecuted:one_waiting112_intent"); return
    require(not (output / "parent_receipt.json").exists(), "execution_already_attempted")
    command = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.research_original_waiting112",
               "--output", str(output), "--worker"]
    receipt = {"schema": SCHEMA, "status": "running", "command": command, "plan_sha256": sha(output / "preregistered_protocol.json")}
    write(output / "parent_receipt.json", receipt)
    started = time.perf_counter()
    with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        try:
            process = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=plan["parent_timeout_seconds"])
            receipt.update(exit_code=process.returncode, status="worker_completed" if process.returncode == 0 else "unknown_worker_failure")
            if process.returncode == 0:
                require((output / "assessment.json").is_file() and (output / "raw_final.json.gz").is_file(), "missing_worker_output")
                receipt["assessment"] = read(output / "assessment.json")
                validation = verify_evidence(output)
                write(output / "independent_validation.json", validation)
                receipt["saved_evidence_validation"] = validation["status"]
        except subprocess.TimeoutExpired:
            receipt["status"] = "unknown_hard_timeout"
        except BaseException as error:
            receipt.update(status="unknown_parent_verification_failure", error=repr(error))
    try: verify_pins(output, plan)
    except BaseException as error: receipt.update(status="unknown_identity_failure", identity_error=repr(error))
    receipt.update(wall_seconds=time.perf_counter()-started, native_binary_sha256=BINARY_SHA, input_sha256=INPUT_SHA,
                   business_benefit=None, strict_protection="not_assessed", complete_100ms_certified=False)
    write(output / "parent_receipt.json", receipt)
    write(output / "branch_ledger.json", {"single_waiting_gate": receipt})
    print(json.dumps({key: receipt[key] for key in ("status", "wall_seconds")}))
    if receipt["status"] != "worker_completed": raise SystemExit(1)


if __name__ == "__main__": main()

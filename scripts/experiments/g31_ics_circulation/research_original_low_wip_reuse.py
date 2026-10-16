"""A separate, bounded second supply using the original finite tray token.

The frozen low-WIP005 startup and first-supply controller executes unchanged.
Afterwards only the original token owner may reuse that same tray, following
its own delivered typed completion self-copy AND a fresh local empty view.
All original jobs, permissions, FIFO and native admission rules remain intact.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from . import research_original_low_wip as base

ROOT, OUT = base.ROOT, base.OUT
SCHEMA = "g31.original_low_wip_second_supply.v1"
HORIZON, MAX_TICKS, MAX_PHYSICAL = 28800., 2882, 24
PARENT_SECONDS = 600.
BASE_SHA = "729cbbdd03ecff3a85bd5324653db424bd601632a5fbecdc72c02bb83c3c7bc9"
BaseOwner, _base_verify_pins = base.Owner, base.verify_pins
_installed = False
AMENDMENT = {
    "predecessor": "original_low_wip_prepare_005",
    "first_phase": "Unchanged frozen005 Owner activation through parking and first supply.",
    "second_phase": "After first supply the token owner checks its own current token and publishes a native v2 invitation only once its first transfer has a received ACK and the token is locally empty, stationary and available again. The peer resumes native v2 replies only after an actual delivered invitation contains that empty token, its source-local completion receipt and the first transfer's received ACK. Only original token owner may issue one second supply, after its own delivered v2 self-copy proves the exact first job destination UNLOAD_COMPLETE and its current local same token is empty, stationary, available and not reserved for reception. Select only latest delivered peer per-source FIFO heads with positive-capacity mandatory paths. No same-owner or skipped-head fallback. Once the peer observes the actual second-supply action it permanently stops new publications but continues its own ACK/retry processing.",
    "limits": {"physical_requests": 24, "horizon": 28800., "parent_timeout_seconds": 600., "offered": 28506, "trays": 22},
    "assessment": "Require exactly two distinct jobs' chronological LOAD_START/LOAD_COMPLETE/UNLOAD_COMPLETE/HOLD_COMPLETE on the same token, two actual supplies, 22 parking receipts, all physical received ACKs, complete horizon and final empty token. No paired protection, deadline success or full-request100ms claim.",
    "execution_budget": "One shared600s budget starts before execute-time preparation/pin review/claim; native worker and separate pure verification child each receive only the remaining time. Any child timeout, failed verification, source drift or observed total deadline exceedance stays unknown. Receipt publication/OS scheduling may itself finish later; the limit is not a real-time OS guarantee.",
}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def current_empty(view, token):
    rows = [t for t in view["trays"] if t["tray_id"] == token]
    return (len(rows) == 1 and rows[0]["mode"] == "empty" and not rows[0]["business_bag_id"]
        and rows[0]["edge_to"] < 0 and rows[0]["reception_node"] < 0
        and finite(rows[0]["available_at"]) and rows[0]["available_at"] <= view["now"])


def returned_invitation(envelope, token, source, nodes):
    """A received source fact can trigger a reply, never an inferred return ETA."""
    if envelope is None:
        return False
    body = envelope["capture"]; local = body["local_capture"]
    base.require(local["source_owner"] == source, "reuse_invitation_source")
    if not current_empty({"trays": local["trays"], "now": local["captured_at"]}, token):
        return False
    actions = [r for r in body["extension"]["submitted_physical_actions"]
        if r["request_id"] == base.owner_request_id(source, "single-supply")]
    if len(actions) != 1:
        return False
    action = actions[0]; ack = action.get("last_delivered_ack") or {}
    if (action["kind"] != "transfer" or ack.get("status") != "received"
            or not finite(ack.get("delivered_at")) or not 0 <= ack["delivered_at"] <= local["captured_at"]):
        return False
    return any(r["tray_id"] == token and r["source_owner"] == source and r["event"] == "UNLOAD_COMPLETE"
        and r["status"] == "completed" and nodes[r["destination"]]["resource_owner"] == source
        and finite(r["completed_at"]) and ack["delivered_at"] <= r["completed_at"] <= local["captured_at"]
        for r in body["extension"]["terminal_receipts"])


def latest_own_capture(outbox, owner, peer, now, nodes):
    """Only ACK-delivered immutable source self-copies; newest known revision first."""
    candidates = []
    for request_id, row in outbox.items():
        if row["kind"] != "planning_snapshot_v2":
            continue
        ack = row.get("client_view", {}).get("last_delivered_ack") or {}
        envelope = ack.get("planning_snapshot_v2")
        if envelope is None:
            continue
        payload = row["payload"]
        local = envelope["capture"]["local_capture"]
        base.require(row["terminal"] and ack.get("status") in ("delivered", "expired")
            and payload["request_id"] == request_id and payload["owner_id"] == owner
            and payload["target_owner"] == peer and local["source_owner"] == owner
            and local["target_owner"] == peer and ack["result_id"] == local["message_id"], "reuse_self_ack_identity")
        base.require(all(finite(t) for t in (ack["delivered_at"], ack["executed_at"], ack["completed_at"]))
            and ack["executed_at"] == local["captured_at"]
            and ack["completed_at"] == envelope["delivered_at"]
            and envelope["delivered_at"] <= ack["delivered_at"] <= now, "reuse_self_ack_clock")
        sequence = local["publication_sequence"]
        base.require(type(sequence) is int and sequence > 0, "reuse_self_sequence")
        candidates.append((sequence, local["captured_at"], request_id, envelope, ack))
    if not candidates:
        return None
    base.require(len({r[0] for r in candidates}) == len(candidates), "reuse_duplicate_self_revision")
    _, _, request_id, envelope, ack = max(candidates, key=lambda r: (r[0], r[1]))
    # Selecting first prevents an expired newest revision resurrecting an older
    # conditional body. Native self-copy read_at is immutable; check expiry now.
    valid = base.delivered_peer([envelope], peer, owner, now, nodes)
    if valid is None:
        return None
    return {"request_id": request_id, "ack": deepcopy(ack), "envelope": deepcopy(valid)}


def return_proof(supply, outbox, view, owner, peer, token):
    if supply is None:
        return None
    base.require(view["owner_id"] == owner and finite(view["now"]), "reuse_view_scope")
    now = view["now"]
    first_row = outbox.get(supply["request_id"], {})
    first_ack = first_row.get("client_view", {}).get("last_delivered_ack") or {}
    if first_ack.get("status") != "received":
        return None
    base.require(finite(first_ack.get("delivered_at")) and first_ack["delivered_at"] <= now, "reuse_first_ack_clock")
    current = [t for t in view["trays"] if t["tray_id"] == token]
    if len(current) != 1:
        return None
    tray = current[0]
    if (tray["mode"] != "empty" or tray["business_bag_id"] or tray["edge_to"] >= 0
            or tray["reception_node"] >= 0 or not finite(tray["available_at"]) or tray["available_at"] > now):
        return None
    nodes = {r["node"]: r for r in view["node_contracts"]}
    base.require(nodes[tray["node"]]["resource_owner"] == owner, "reuse_nonlocal_token")
    selected = latest_own_capture(outbox, owner, peer, now, nodes)
    if selected is None:
        return None
    body = selected["envelope"]["capture"]
    first_job = supply["choice"]["job"]
    receipts = [r for r in body["extension"]["terminal_receipts"]
                if r["business_bag_id"] == first_job["business_bag_id"]]
    if len(receipts) != 1:
        return None
    receipt = receipts[0]
    base.require(receipt["event"] == "UNLOAD_COMPLETE" and receipt["status"] == "completed" and receipt["source_owner"] == owner
        and receipt["tray_id"] == token and receipt["destination"] == first_job["destination"]
        and nodes[receipt["destination"]]["resource_owner"] == owner
        and finite(receipt["completed_at"])
        and supply["at"] <= receipt["completed_at"] <= body["local_capture"]["captured_at"] <= now,
        "reuse_completion_identity_or_clock")
    # UNLOAD alone does not prove the hold ended: the separate current local
    # native empty/available observation above supplies that requirement.
    base.require(receipt["completed_at"] <= tray["available_at"], "reuse_empty_before_completion")
    return {"first_supply_request_id": supply["request_id"], "first_received_ack": deepcopy(first_ack),
            "own_delivered_self_copy": selected, "terminal_receipt": deepcopy(receipt),
            "current_token": deepcopy(tray), "observed_at": now}


class ReuseOwner(BaseOwner):
    def __init__(self, session, owner, plan):
        super().__init__(session, owner, plan)
        self.second_supply = None
        self.second_seen = False
        self._reuse_nodes = None

    def activate(self):
        was_quiet = self.quiet
        super().activate()
        # Preserve the full first phase and its exact API order, including the
        # activation that first submits the supply or first observes its peer.
        if not was_quiet or self.failure or self.index != len(self.rows) or self.second_supply is not None or self.second_seen:
            return
        view = None
        if self.owner == self.plan["token_owner"] or self._reuse_nodes is None:
            view = self.session.observe_protocol_control_policy_recent(self.owner, base.VALIDITY)
            base.require(view["owner_id"] == self.owner and view["now"] == self.session.physical_time, "reuse_owner_or_clock")
            self._reuse_nodes = {r["node"]: deepcopy(r) for r in view["node_contracts"]}
        now, nodes = self.session.physical_time, self._reuse_nodes
        peer = base.delivered_peer(self.session.protocol_planning_snapshots_v2(self.owner), self.owner, self.peer, now, nodes)
        if peer and any(r["request_id"] == base.owner_request_id(self.peer, "second-supply")
                        for r in peer["capture"]["extension"]["submitted_physical_actions"]):
            self.second_seen = True
            return
        if self.owner == self.plan["token_owner"]:
            if self.supply is None or not current_empty(view, self.plan["token_tray_id"]):
                return
            ack = self.client.state["outbox"][self.supply["request_id"]].get("client_view", {}).get("last_delivered_ack") or {}
            if ack.get("status") != "received":
                return
        elif not returned_invitation(peer, self.plan["token_tray_id"], self.peer, nodes):
            return
        if now >= self.next_publication:
            self.client.submit(self.owner, "planning_snapshot_v2", {"target_owner": self.peer, "message_delay": base.WIRE,
                "publication_delay": base.WIRE, "expiry": now + base.VALIDITY},
                request_id=base.owner_request_id(self.owner, f"snapshot:{self.publications}"))
            self.publications += 1
            self.next_publication = now + base.PERIOD
        if self.owner != self.plan["token_owner"] or self.supply is None:
            return
        proof = return_proof(self.supply, self.client.state["outbox"], view, self.owner, self.peer, self.plan["token_tray_id"])
        if proof is None:
            return
        choice = base.eligible_head(peer, view, self.plan["token_tray_id"])
        if choice is None:
            return
        base.require(choice["job"]["business_bag_id"] != self.supply["choice"]["job"]["business_bag_id"], "reuse_same_job_selected")
        request = {"tray_id": self.plan["token_tray_id"], "source": choice["tray"]["node"], "destination": choice["job"]["origin"],
            "message_delay": base.WIRE, "earliest_departure": now, "expiry": min(HORIZON, now + 2000.)}
        self.second_supply = {"request_id": base.owner_request_id(self.owner, "second-supply"),
            "request": deepcopy(request), "at": now, "choice": choice, "return_proof": proof}
        self.decisions.append(deepcopy(self.second_supply))
        self.client.submit(self.owner, "transfer", request, request_id=self.second_supply["request_id"])

    def summary(self):
        return {**super().summary(), "second_supply": self.second_supply, "second_seen": self.second_seen}


def assess(raw, plan):
    token = plan["parking_plan"]["token_tray_id"]
    sources = [o for o in raw["owners"] if o["supply"] is not None]
    first = sources[0]["supply"] if len(sources) == 1 else None
    seconds = [o["second_supply"] for o in raw["owners"] if o.get("second_supply") is not None]
    second = seconds[0] if len(seconds) == 1 else None
    rows = raw["result"].get("receipts", [])
    witnesses = []
    for supply in (first, second):
        if supply is None:
            continue
        job = supply["choice"]["job"]
        matching = {event: [r for r in rows if r.get("event") == event and r.get("tray_id") == token
            and r.get("business_bag_id") == job["business_bag_id"]]
            for event in ("LOAD_START", "LOAD_COMPLETE", "UNLOAD_COMPLETE", "HOLD_COMPLETE")}
        if not all(len(v) == 1 for v in matching.values()):
            continue
        load, loaded, unload, hold = [matching[k][0] for k in matching]
        if (all(finite(r["time"]) for r in (load, loaded, unload, hold))
                and supply["at"] <= load["time"] <= loaded["time"] <= unload["time"] <= hold["time"] <= HORIZON
                and load["node"] == loaded["node"] == job["origin"]
                and unload["node"] == hold["node"] == job["destination"]):
            witnesses.append({"job": job["business_bag_id"], "tray_id": token, "load": load,
                "load_complete": loaded, "unload": unload, "hold_complete": hold})
    reuse = (len(witnesses) == 2 and witnesses[0]["job"] != witnesses[1]["job"]
        and witnesses[0]["hold_complete"]["time"] <= second["at"] <= witnesses[1]["load"]["time"])
    loaded_jobs = [(r["business_bag_id"], r["tray_id"]) for r in rows if r.get("event") == "LOAD_START"]
    only_two = bool(reuse) and loaded_jobs == [(w["job"], token) for w in witnesses]
    physical = [r for o in raw["owners"] for r in o["outbox"]["outbox"].values() if r["kind"] == "transfer"]
    received = len(physical) == MAX_PHYSICAL and all(r.get("client_view", {}).get("last_delivered_ack", {}).get("status") == "received" for r in physical)
    empty = [t for t in raw["result"]["trays"] if t["tray_id"] == token and t["mode"] == "empty"
        and t["job"] == -1 and t["edge_to"] < 0 and t.get("reception_node", -1) < 0
        and finite(t["available_at"]) and t["available_at"] <= raw["physical_time"]]
    closed = raw["status"] == "horizon_complete" and raw["physical_time"] == HORIZON and raw["result"]["advance"]["horizon_complete"] is True
    parking = sum(o["index"] for o in raw["owners"])
    complete = closed and reuse and only_two and received and len(empty) == 1 and parking == 22 and raw["physical_audit"]["status"] == "passed"
    return {"schema": SCHEMA, "status": "observed_two_completions_same_token_and_empty" if complete else "unknown_or_no_second_complete_witness",
        "offered": 28506, "observed_horizon_complete": closed, "completion_witnesses": witnesses,
        "completed_parking": parking, "actual_supply_count": int(first is not None) + len(seconds),
        "all_physical_received_acks": received, "final_token_empty": len(empty) == 1,
        "only_two_declared_jobs_loaded": only_two, "second_reuse_proved": bool(complete),
        "strict_protection": "not_assessed", "complete_100ms_certified": False}


def source_paths():
    pending, found = [Path(__file__)], set()
    def enqueue(target):
        for p in (target.with_suffix(".py"), target / "__init__.py"):
            if p.is_file() and p.resolve().is_relative_to(ROOT):
                pending.append(p)
                for parent in p.parents:
                    if parent == ROOT: break
                    if (parent / "__init__.py").is_file(): pending.append(parent / "__init__.py")
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        found.add(path)
        for n in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(n, ast.ImportFrom):
                for origin in ([path.parent] if n.level else [ROOT, ROOT / "src"]):
                    for _ in range(max(0, n.level - 1)): origin = origin.parent
                    if n.module: origin = origin.joinpath(*n.module.split(".")); enqueue(origin)
                    for alias in n.names:
                        if alias.name != "*": enqueue(origin / alias.name)
            elif isinstance(n, ast.Import):
                for alias in n.names:
                    for origin in (ROOT, ROOT / "src"): enqueue(origin.joinpath(*alias.name.split(".")))
    return sorted(found)


def verify_pins(output, plan, runtime=False):
    base.require(base.sha(base.__file__) == BASE_SHA, "reuse_frozen_base_changed")
    base.require(plan["schema"] == SCHEMA and plan["horizon"] == HORIZON and plan["max_ticks"] == MAX_TICKS
        and plan["max_physical_requests"] == MAX_PHYSICAL and plan["parent_timeout_seconds"] == 600.
        and plan["tick_seconds"] == base.PERIOD and plan["event_budget_per_advance"] == 100000
        and plan["offered"] == 28506 and plan["trays"] == 22 and plan["native_branch_budget"] == 1
        and plan["original_r1_permission"] is False and plan["reuse_amendment"] == AMENDMENT,
        "reuse_declared_scope_changed")
    base.require(set(plan["source_before"]) == {str(p) for p in source_paths()}, "reuse_source_closure_changed")
    _base_verify_pins(output, plan, runtime)


@contextmanager
def installed():
    """Serial child-process-only opt-in; original module bytes are unchanged."""
    global _installed
    base.require(not _installed, "reuse_overlapping_context")
    replacements = {"Owner": ReuseOwner, "assess": assess, "source_paths": source_paths,
        "verify_pins": verify_pins, "SCHEMA": SCHEMA, "HORIZON": HORIZON,
        "MAX_TICKS": MAX_TICKS, "MAX_PHYSICAL": MAX_PHYSICAL}
    previous = {key: getattr(base, key) for key in replacements}
    _installed = True
    try:
        for key, value in replacements.items(): setattr(base, key, value)
        yield
    finally:
        for key, value in previous.items(): setattr(base, key, value)
        _installed = False


def prepare(output, source, binary):
    base.require(base.sha(base.__file__) == BASE_SHA, "reuse_frozen_base_changed")
    with installed():
        plan = base.prepare(output, source, binary)
        plan["reuse_amendment"] = deepcopy(AMENDMENT)
        plan["execution_amendment"] = "New independent two-supply domain; preserve005 unchanged. Inherit its bounded PermissionError IO retry and exclusive one-attempt claims."
        plan["policy_contract"] += " " + AMENDMENT["second_phase"]
        plan["conditional_quiescence"] = "Only this controller submits physical operations; after parking21 trays remain at nonloaders. One token may carry at most two distinct jobs. Native snapshots do not certify absence of future Python plans."
        plan["assessment"] = AMENDMENT["assessment"]
        base.write(output / "preregistered_protocol.json", plan)
        verify_pins(output, plan)
    return plan


def run_remaining(command, log_path, started):
    """Bound each child by the same parent deadline, including pure replay."""
    began = time.perf_counter() - started
    remaining = PARENT_SECONDS - began
    if remaining <= 0:
        return {"status": "unknown_parent_budget_before_child", "exit_code": None,
            "command": command, "started_elapsed_seconds": began, "allowed_seconds": 0.}
    with Path(log_path).open("xb") as log:
        try:
            child = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=remaining, cwd=ROOT)
            code = child.returncode
            status = "child_finished" if code == 0 else "unknown_child_nonzero"
        except subprocess.TimeoutExpired:
            code, status = None, "unknown_shared_parent_timeout"
    finished = time.perf_counter() - started
    if finished > PARENT_SECONDS:
        status = "unknown_shared_parent_timeout"
    return {"status": status, "exit_code": code, "command": command,
        "started_elapsed_seconds": began, "finished_elapsed_seconds": finished, "allowed_seconds": remaining}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source", type=Path, default=OUT / "full_stream_native024_001/full1x/input.json.gz")
    p.add_argument("--binary", type=Path, default=ROOT / "build_lt_session_026/python/czr005_circulation.cp311-win_amd64.pyd")
    p.add_argument("--worker", action="store_true"); p.add_argument("--execute", action="store_true"); p.add_argument("--verify", action="store_true")
    p.add_argument("--verification-output", type=Path)
    args = p.parse_args()
    started = time.perf_counter() if args.execute else None
    base.require(sum((args.worker, args.execute, args.verify)) <= 1, "reuse_conflicting_modes")
    base.require(args.verification_output is None or args.verify, "reuse_verification_output_mode")
    if args.worker:
        with installed(): base.worker(args.output)
        return
    if args.verify:
        with installed(): result = base.verify_saved(args.output)
        if args.verification_output is not None:
            base.require(args.verification_output.resolve() == (args.output / "independent_verification.json").resolve()
                and not args.verification_output.exists(), "reuse_verification_output_identity")
            base.write(args.verification_output, result)
        print(json.dumps(result, ensure_ascii=False)); return
    plan = base.read(args.output / "preregistered_protocol.json") if args.output.exists() else prepare(args.output, args.source, args.binary)
    verify_pins(args.output, plan)
    if not args.execute:
        print(json.dumps({"status": "prepared_native_unexecuted", "horizon": HORIZON, "physical_budget": MAX_PHYSICAL})); return
    with installed(): base.claim_execution(args.output, plan)
    base.write(args.output / "branch_ledger.json", {"single_candidate": {"status": "unknown_in_progress"}})
    command = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.research_original_low_wip_reuse", "--worker", "--output", str(args.output)]
    execution = run_remaining(command, args.output / "worker.log", started)
    code = execution["exit_code"]
    status = "worker_finished" if execution["status"] == "child_finished" else execution["status"]
    changed = [s for s, digest in plan["source_before"].items() if base.sha(s) != digest]
    assessment = base.read(args.output / "assessment.json") if (args.output / "assessment.json").is_file() else None
    verification = None
    verification_process = None
    if execution["status"] == "child_finished" and not changed:
        verify_command = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.research_original_low_wip_reuse",
            "--verify", "--output", str(args.output), "--verification-output", str(args.output / "independent_verification.json")]
        verification_process = run_remaining(verify_command, args.output / "verification.log", started)
        if verification_process["status"] == "child_finished":
            try:
                verification = base.read(args.output / "independent_verification.json")
                base.require(verification["status"] == "passed_saved_raw_replay", "reuse_verification_result")
            except (OSError, ValueError, KeyError) as error:
                status, verification = "unknown_verification_failed", {"error": repr(error)}
        else:
            status = "unknown_verification_failed_or_budget_exhausted"
    changed = [s for s, digest in plan["source_before"].items() if base.sha(s) != digest]
    if changed: status = "unknown_source_changed"
    elapsed = time.perf_counter() - started
    if elapsed > PARENT_SECONDS: status = "unknown_shared_parent_timeout"
    receipt = {"schema": SCHEMA, "status": status, "exit_code": code, "command": command,
        "wall_seconds": elapsed, "execution_process": execution, "verification_process": verification_process,
        "parent_budget_seconds": PARENT_SECONDS, "source_changed": changed, "assessment": assessment,
        "verification": verification, "offered": 28506, "strict_protection": "not_assessed", "complete_100ms_certified": False}
    receipt["artifact_sha256"] = {name: base.sha(args.output / name) for name in
        ("preregistered_protocol.json", "raw_final.json.gz", "assessment.json", "api/manifest.jsonl", "worker.log", "verification.log", "independent_verification.json", "error_prefix.json.gz") if (args.output / name).is_file()}
    final_elapsed = time.perf_counter() - started
    receipt["wall_seconds"] = final_elapsed
    if final_elapsed > PARENT_SECONDS: receipt["status"] = "unknown_shared_parent_timeout"
    base.write(args.output / "receipt.json", receipt)
    base.write(args.output / "branch_ledger.json", {"single_candidate": receipt})
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()

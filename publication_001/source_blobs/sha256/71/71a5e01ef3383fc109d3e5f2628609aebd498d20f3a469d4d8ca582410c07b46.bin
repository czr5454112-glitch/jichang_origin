"""One additional owner-local supply after the frozen two-cycle experiment.

No job or loader is selected from offline results. The existing FIFO selector
receives only the latest actually delivered v2 peer body and the local view.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import time

from . import research_original_low_wip as base
from . import research_original_low_wip_reuse as reuse

ROOT, OUT = base.ROOT, base.OUT
SCHEMA = "g31.original_low_wip_third_supply.v1"
HORIZON, MAX_TICKS, MAX_PHYSICAL = 28800., 2882, 25
PARENT_SECONDS = 600.
BASE_SHA = reuse.BASE_SHA
REUSE_SHA = "e91ada16a9f6089ffb49ac79e06fff492be467e54ee8074bd46c3c47e1742a02"
_base_verify_pins = base.verify_pins
_installed = False
PREDECESSOR = OUT / "original_low_wip_reuse_prepare_002"
PREDECESSOR_PINS = {
    "preregistered_protocol.json": "ff9336193a45e74651f8f1e466fada4bf4067830b6084316da1964c1c245aadb",
    "receipt.json": "561fcc16c494055f20a48ab5e90692cf39eed796d331791384145d2c432b4df6",
    "raw_final.json.gz": "1b63d0c56b8819d946cdcbe38747b1f77cd6068946ab9ef871fc6814a944aa09",
    "assessment.json": "a03299733e435ef3b430671e475dcf0a09270bcf6b7acaffacdf3caa2315dfbd",
    "api/manifest.jsonl": "6053c1a312b37210f47b350cd8656fdfaff4ff7c79bc52bd18032b816ee1b7be",
}
AMENDMENT = {
    "predecessor": "original_low_wip_reuse_prepare_002",
    "unchanged_prefix": "Call frozen ReuseOwner through second supply and its peer observation. Only after that local state is present may the extra phase read or publish.",
    "third_phase": "Only original token owner may issue one third supply. Require its second transfer's delivered received ACK, fresh own token empty/stationary/available/no reception, latest delivered own v2 self-copy containing exact second-job destination completion, and latest actual peer v2 FIFO capture no older than that own invitation capture. Peer replies only to an actual second-return invitation with second-supply received ACK and a later source-owned token completion. Existing per-source FIFO/positive-capacity/cross-zone selector chooses the job; no job/loader ID is hardcoded. Rejection or missing evidence never selects a replacement. Peer stops new publications once the actual third-supply action is delivered; both owners continue ACK/retry processing. No fourth supply.",
    "limits": {"physical_requests": 25, "horizon": 28800., "parent_timeout_seconds": 600., "offered": 28506, "trays": 22},
    "assessment": "Require three distinct jobs' actual LOAD_START/LOAD_COMPLETE/UNLOAD_COMPLETE/HOLD_COMPLETE in order on the same token, 22 parked trays, exactly25 received physical requests, full horizon and final empty token. Retain all28506, unfinished jobs and failed/open operations. No per-job protection, general performance, deadline or100ms claim.",
    "selection_bias": "A finite follow-up chosen after two observed successes and offline necessary-path screening. This is not an unbiased full-workload policy evaluation or proof that the39 relaxed zero-bad bound is achievable.",
    "execution_budget": reuse.AMENDMENT["execution_budget"],
}


def second_return_invitation(envelope, token, source, nodes):
    """Reply trigger only; exact selected-job proof remains source-local."""
    if envelope is None:
        return False
    body = envelope["capture"]; local = body["local_capture"]
    base.require(local["source_owner"] == source, "third_invitation_source")
    if not reuse.current_empty({"trays": local["trays"], "now": local["captured_at"]}, token):
        return False
    actions = [a for a in body["extension"]["submitted_physical_actions"]
        if a["request_id"] == base.owner_request_id(source, "second-supply")]
    if len(actions) != 1:
        return False
    action = actions[0]; ack = action.get("last_delivered_ack") or {}
    if (action["kind"] != "transfer" or ack.get("status") != "received"
            or not reuse.finite(ack.get("delivered_at"))
            or not 0 <= ack["delivered_at"] <= local["captured_at"]):
        return False
    return any(r["tray_id"] == token and r["source_owner"] == source
        and r["event"] == "UNLOAD_COMPLETE" and r["status"] == "completed"
        and nodes[r["destination"]]["resource_owner"] == source
        and reuse.finite(r["completed_at"])
        and ack["delivered_at"] <= r["completed_at"] <= local["captured_at"]
        for r in body["extension"]["terminal_receipts"])


class ThirdOwner(reuse.ReuseOwner):
    def __init__(self, session, owner, plan):
        super().__init__(session, owner, plan)
        self.third_supply = None
        self.third_seen = False
        self.third_observations = 0

    def activate(self):
        was_second = self.second_supply is not None or self.second_seen
        super().activate()
        if (not was_second or self.failure or self.index != len(self.rows)
                or self.third_supply is not None or self.third_seen):
            return
        now = self.session.physical_time
        view = None
        if self.owner == self.plan["token_owner"]:
            view = self.session.observe_protocol_control_policy_recent(self.owner, base.VALIDITY)
            base.require(view["owner_id"] == self.owner and view["now"] == now, "third_owner_or_clock")
            self._reuse_nodes = {r["node"]: deepcopy(r) for r in view["node_contracts"]}
            if not reuse.current_empty(view, self.plan["token_tray_id"]):
                return
            ack = self.client.state["outbox"][self.second_supply["request_id"]].get("client_view", {}).get("last_delivered_ack") or {}
            if ack.get("status") != "received":
                return
        base.require(self._reuse_nodes is not None, "third_missing_prior_local_contract")
        peer = base.delivered_peer(self.session.protocol_planning_snapshots_v2(self.owner), self.owner,
            self.peer, now, self._reuse_nodes)
        self.third_observations += 1
        if peer and any(a["request_id"] == base.owner_request_id(self.peer, "third-supply")
                        for a in peer["capture"]["extension"]["submitted_physical_actions"]):
            self.third_seen = True
            return
        if self.owner != self.plan["token_owner"] and not second_return_invitation(
                peer, self.plan["token_tray_id"], self.peer, self._reuse_nodes):
            return
        if now >= self.next_publication:
            self.client.submit(self.owner, "planning_snapshot_v2", {"target_owner": self.peer,
                "message_delay": base.WIRE, "publication_delay": base.WIRE, "expiry": now + base.VALIDITY},
                request_id=base.owner_request_id(self.owner, f"snapshot:{self.publications}"))
            self.publications += 1
            self.next_publication = now + base.PERIOD
        if self.owner != self.plan["token_owner"]:
            return
        proof = reuse.return_proof(self.second_supply, self.client.state["outbox"], view,
            self.owner, self.peer, self.plan["token_tray_id"])
        if proof is None or peer is None:
            return
        invited_at = proof["own_delivered_self_copy"]["envelope"]["capture"]["local_capture"]["captured_at"]
        if peer["capture"]["local_capture"]["captured_at"] < invited_at:
            return
        choice = base.eligible_head(peer, view, self.plan["token_tray_id"])
        if choice is None:
            return
        base.require(choice["job"]["business_bag_id"] not in {
            self.supply["choice"]["job"]["business_bag_id"],
            self.second_supply["choice"]["job"]["business_bag_id"]}, "third_repeat_completed_job")
        request = {"tray_id": self.plan["token_tray_id"], "source": choice["tray"]["node"],
            "destination": choice["job"]["origin"], "message_delay": base.WIRE,
            "earliest_departure": now, "expiry": min(HORIZON, now + 2000.)}
        self.third_supply = {"request_id": base.owner_request_id(self.owner, "third-supply"),
            "request": deepcopy(request), "at": now, "choice": choice, "return_proof": proof}
        self.decisions.append(deepcopy(self.third_supply))
        self.client.submit(self.owner, "transfer", request, request_id=self.third_supply["request_id"])

    def summary(self):
        return {**super().summary(), "third_supply": self.third_supply,
            "third_seen": self.third_seen, "third_observations": self.third_observations}


def assess(raw, plan):
    token = plan["parking_plan"]["token_tray_id"]
    supplies = []
    for field in ("supply", "second_supply", "third_supply"):
        selected = [o[field] for o in raw["owners"] if o.get(field) is not None]
        supplies.append(selected[0] if len(selected) == 1 else None)
    rows = raw["result"].get("receipts", [])
    witnesses = []
    for supply in supplies:
        if supply is None:
            continue
        job = supply["choice"]["job"]
        matches = {e: [r for r in rows if r.get("event") == e and r.get("tray_id") == token
            and r.get("business_bag_id") == job["business_bag_id"]]
            for e in ("LOAD_START", "LOAD_COMPLETE", "UNLOAD_COMPLETE", "HOLD_COMPLETE")}
        if not all(len(v) == 1 for v in matches.values()):
            continue
        load, loaded, unload, hold = [matches[e][0] for e in matches]
        if (reuse.finite(supply["at"]) and all(reuse.finite(r["time"]) for r in (load, loaded, unload, hold))
                and 0 <= supply["at"] <= load["time"] <= loaded["time"] <= unload["time"] <= hold["time"] <= HORIZON
                and load["node"] == loaded["node"] == job["origin"]
                and unload["node"] == hold["node"] == job["destination"]):
            witnesses.append({"job": job["business_bag_id"], "tray_id": token, "load": load,
                "load_complete": loaded, "unload": unload, "hold_complete": hold})
    sequential = (all(supplies) and len(witnesses) == 3 and len({w["job"] for w in witnesses}) == 3
        and all(witnesses[i]["hold_complete"]["time"] <= supplies[i+1]["at"] for i in range(2)))
    loaded_jobs = [(r["business_bag_id"], r["tray_id"]) for r in rows if r.get("event") == "LOAD_START"]
    only_three = bool(sequential) and loaded_jobs == [(w["job"], token) for w in witnesses]
    physical = [r for o in raw["owners"] for r in o["outbox"]["outbox"].values() if r["kind"] == "transfer"]
    received = len(physical) == MAX_PHYSICAL and all(
        r.get("client_view", {}).get("last_delivered_ack", {}).get("status") == "received" for r in physical)
    empty = [t for t in raw["result"]["trays"] if t["tray_id"] == token and t["mode"] == "empty"
        and t["job"] == -1 and t["edge_to"] < 0 and t.get("reception_node", -1) < 0
        and reuse.finite(t["available_at"]) and t["available_at"] <= raw["physical_time"]]
    closed = raw["status"] == "horizon_complete" and raw["physical_time"] == HORIZON and raw["result"]["advance"]["horizon_complete"] is True
    parking = sum(o["index"] for o in raw["owners"])
    complete = closed and sequential and only_three and received and len(empty) == 1 and parking == 22 and raw["physical_audit"]["status"] == "passed"
    return {"schema": SCHEMA, "status": "observed_three_completions_same_token_and_empty" if complete else "unknown_or_no_third_complete_witness",
        "offered": 28506, "observed_horizon_complete": closed, "completion_witnesses": witnesses,
        "completed_parking": parking, "actual_supply_count": sum(s is not None for s in supplies),
        "all_physical_received_acks": received, "final_token_empty": len(empty) == 1,
        "only_three_declared_jobs_loaded": only_three, "third_cycle_proved": bool(complete),
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
    base.require(base.sha(base.__file__) == BASE_SHA and base.sha(reuse.__file__) == REUSE_SHA, "third_frozen_predecessor_changed")
    base.require(all(plan["authority_pins"].get(str(PREDECESSOR / name)) == digest
        for name, digest in PREDECESSOR_PINS.items()), "third_predecessor_pins_missing")
    base.require(plan["schema"] == SCHEMA and plan["horizon"] == HORIZON and plan["max_ticks"] == MAX_TICKS
        and plan["max_physical_requests"] == MAX_PHYSICAL and plan["parent_timeout_seconds"] == 600.
        and plan["tick_seconds"] == base.PERIOD and plan["event_budget_per_advance"] == 100000
        and plan["offered"] == 28506 and plan["trays"] == 22 and plan["native_branch_budget"] == 1
        and plan["original_r1_permission"] is False and plan["third_amendment"] == AMENDMENT,
        "reuse_declared_scope_changed")
    base.require(set(plan["source_before"]) == {str(p) for p in source_paths()}, "reuse_source_closure_changed")
    _base_verify_pins(output, plan, runtime)


@contextmanager
def installed():
    """Serial child-process-only opt-in; original module bytes are unchanged."""
    global _installed
    base.require(not _installed, "reuse_overlapping_context")
    replacements = {"Owner": ThirdOwner, "assess": assess, "source_paths": source_paths,
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
    base.require(base.sha(base.__file__) == BASE_SHA and base.sha(reuse.__file__) == REUSE_SHA, "third_frozen_predecessor_changed")
    with installed():
        plan = base.prepare(output, source, binary)
        plan["third_amendment"] = deepcopy(AMENDMENT)
        for name, digest in PREDECESSOR_PINS.items():
            path = PREDECESSOR / name
            base.require(base.sha(path) == digest, "third_predecessor_evidence_changed")
            plan["authority_pins"][str(path)] = digest
        plan["execution_amendment"] = "New independent three-supply domain; preserve005 and reuse002 unchanged. Inherit its bounded PermissionError IO retry and exclusive one-attempt claims."
        plan["policy_contract"] += " " + AMENDMENT["third_phase"]
        plan["conditional_quiescence"] = "Only this controller submits physical operations; after parking21 trays remain at nonloaders. One token may carry at most three distinct jobs. Native snapshots do not certify absence of future Python plans."
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
    command = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.research_original_low_wip_third", "--worker", "--output", str(args.output)]
    execution = run_remaining(command, args.output / "worker.log", started)
    code = execution["exit_code"]
    status = "worker_finished" if execution["status"] == "child_finished" else execution["status"]
    changed = [s for s, digest in plan["source_before"].items() if base.sha(s) != digest]
    assessment = base.read(args.output / "assessment.json") if (args.output / "assessment.json").is_file() else None
    verification = None
    verification_process = None
    if execution["status"] == "child_finished" and not changed:
        verify_command = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.research_original_low_wip_third",
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

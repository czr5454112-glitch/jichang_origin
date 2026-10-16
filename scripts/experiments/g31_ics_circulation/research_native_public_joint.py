"""Twelve preregistered native020 initial joint-proposal/readiness branches.

Normal branches independently plan at each owner from actual delivered native
captures. No native fork or outcome table is available to the proposal code.
The common later continuation remains v2.1, not a rolling optimizer.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from . import native_planning_adapter as adapter
from . import public_reuse_model as model
from . import research_synthetic_reuse_chain as v1
from . import research_synthetic_reuse_v2 as v2
from .native_host import load_native


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan():
    rows = {f"gate{int(gate)}/{policy}": {"gate": gate, "policy": policy, "fault": None,
            "status": "unknown_unexecuted", "scope": "normal_business_comparison"}
            for gate in v1.GATES for policy in ("incumbent", "fixed_route_model", "joint_model")}
    for fault in ("lost_A_self_ack", "late_publication", "expired_capture"):
        rows["readiness/" + fault] = {"gate": 6., "policy": "joint_model", "fault": fault,
            "status": "unknown_unexecuted", "scope": "first_action_readiness_only"}
    return {"schema": "g31.lt2.native_public_initial_joint.v1", "native_branch_budget": 12,
        "rows": rows, "source_capture_at": .05 + .01, "normal_recipient_delivery_at": .07,
        "normal_source_self_ack_at": .09000000000000001, "decision_at": .11,
        "capture_expiry": .21, "source_input": "unchanged synthetic v2.1 two trays/four obligations; gates0/6/12",
        "policy_information": "each owner independently reads own current observation, own delivered planning ACK and its received peer snapshot; public durations only",
        "age_semantics": "committed load completion .1 projected from source capture while loading; fresh own state checked; peer projection conditional",
        "candidate_domain": "incumbent route1/window1; fixedroute31 public-duration timings; joint those31 plus route2 fouroldtimings",
        "action_execution": "A issues route2 only when independently selected; route1 keeps native route; B issues its independently selected transfer timing; missing input withholds that owner's first action",
        "no_atomic_agreement": "two delivered snapshots are not a ready/commit barrier; mismatch/asymmetry retained",
        "continuation": "same v2.1 explicit desired later route plus receiving_full recovery for all nine normal branches",
        "protection": "all four physical completions <= same-gate incumbent, strict zero tolerance; unknown if any missing/unfinished",
        "fault_scope": "three additional first-action readiness probes stop at.5 with no later controller; no business/protection comparison",
        "faults": {"lost_A_self_ack": "drop first3 ACK packets (two demandACKs then A planningACK); no retries before first-action observation",
                   "late_publication": "planning publication delay.1 => delivery.16 after fixed decision.11",
                   "expired_capture": "planning expiry.08 => recipient readtime expired tombstone at.11"},
        "failures": "retain every unsupported capture, asymmetric action, native rejection, unfinished branch and source drift",
        "claim_limits": ["SYNTHETIC conditional executed prototype", "first action only, not full rolling MPC", "no novel solver", "no calibrated model protection", "no full-request100ms certification"]}


def choose(receipt: dict, policy: str) -> dict:
    if receipt["status"] != "conditional_native_delivered_model_input" or not receipt["native_delivery_verified"]:
        return {"status": "withheld_missing_verified_input", "selected_action": None}
    bundle = receipt["bundle"]
    actions, incumbent = model.candidates_from_durations(bundle)
    if policy == "incumbent":
        return {"status": "declared_incumbent", "selected_action": incumbent,
                "native_protection_certified": False}
    if policy == "fixed_route_model": actions = [a for a in actions if a["initial_next"] == 1]
    elif policy != "joint_model": raise ValueError("online_joint:undeclared_policy")
    return model.propose(bundle, actions, incumbent)


def owner_first_action(native, session, client, owner, planning_id, policy):
    started = time.perf_counter()
    information = adapter.collect_native(native, session, owner, planning_id)
    collected = time.perf_counter()
    decision = choose(information, policy)
    proposed = time.perf_counter()
    action = decision.get("selected_action")
    identity = None
    state = session.observe_protocol(owner)
    if action:
        if owner == "A":
            tray = next((t for t in state["trays"] if t["tray_id"] == "L" and t["node"] == 0
                         and t["mode"] == "loaded" and t["business_bag_id"] == "loaded" and t["edge_to"] < 0), None)
            if tray is None:
                decision = {"status": "withheld_local_route_precondition", "selected_action": None}
            elif action["initial_next"] == 2:
                identity = v1.request_route(client, owner, tray, 2, "initial-route")
        else:
            tray = next((t for t in state["trays"] if t["tray_id"] == "E" and t["node"] == 5
                         and t["mode"] == "empty" and t["edge_to"] < 0 and t["available_at"] <= state["now"]), None)
            if tray is None:
                decision = {"status": "withheld_local_supply_precondition", "selected_action": None}
            else:
                identity = client.submit(owner, "transfer", "initial-supply", tray_id="E", source=5, destination=1,
                    earliest_departure=action["departure"], expiry=v1.HORIZON - 1., message_delay=.01)
    return {"owner": owner, "at": state["now"], "information": information, "decision": decision,
            "native_request_id": identity, "local_action_view": state,
            "capture_validation_wall_ms": (collected - started) * 1000,
            "model_proposal_wall_ms": (proposed - collected) * 1000,
            "whole_initial_owner_call_wall_ms": (time.perf_counter() - started) * 1000}


def run_branch(native, row):
    data = v1.scene(row["gate"])
    fault = row["fault"]
    if fault == "lost_A_self_ack": data["owner_protocol"]["drop_ack_packets"] = 3
    session = native.NativeSession(data)
    session.advance_to(.05)
    client = v1.Transport(session)
    channels = {owner: client.submit(owner, "demand", "seed-demand", target_owner=peer,
                    message_delay=.01, publication_delay=.01) for owner, peer in (("A", "B"), ("B", "A"))}
    planning = {owner: client.submit(owner, "planning_snapshot", "initial-planning", target_owner=peer,
                    message_delay=.01, publication_delay=.1 if fault == "late_publication" else .01,
                    expiry=.08 if fault == "expired_capture" else .21) for owner, peer in (("A", "B"), ("B", "A"))}
    session.advance_to(v1.START)
    client.refresh(retry=False)
    # Sequential orchestration does not share decisions/readiness between owners.
    owners = {owner: owner_first_action(native, session, client, owner, planning[owner], row["policy"])
              for owner in ("A", "B")}
    selections = {o: r["decision"].get("selected_action") for o, r in owners.items()}
    actions_match = selections["A"] is not None and selections["A"] == selections["B"]
    if fault:
        session.advance_to(.5)
        client.refresh(retry=False)
        result = session.result_at(.5)
        summary = {"status": "readiness_observed", "at": .5, "selected_actions": selections,
            "actions_match": actions_match, "both_inputs_delivered": all(r["information"]["native_delivery_verified"] for r in owners.values()),
            "business_metrics": None, "strict_protection": "not_assessed", "comparison_scope": "first_action_readiness_only"}
        continuation = None
    elif not actions_match or owners["B"]["native_request_id"] is None:
        # No hindsight repair or shared fallback to rescue a split decision.
        session.advance_to(v1.HORIZON)
        client.refresh(retry=False)
        result = session.result_at(v1.HORIZON)
        summary = {"status": "unknown_missing_or_disagreeing_first_action", "selected_actions": selections,
                   "actions_match": actions_match, "business_metrics": None}
        continuation = None
    else:
        continuation = v2.continue_v2(session, client, channels, owners["B"]["native_request_id"], "adaptive")
        result = session.result_at(v1.HORIZON)
        summary = v2.assess_cell(data, result, client, continuation, selections["A"])
        summary["actions_match"] = actions_match
        summary["both_inputs_delivered"] = all(r["information"]["native_delivery_verified"] for r in owners.values())
    return {"specification": copy.deepcopy(row), "input": data, "owners": owners, "calls": client.calls,
            "outbox": client.rows, "continuation": continuation, "result": result, "summary": summary}


def assess_normal(rows):
    groups = {}
    for gate in v1.GATES:
        keys = [f"gate{int(gate)}/{p}" for p in ("incumbent", "fixed_route_model", "joint_model")]
        if any(rows[k]["status"] != "assessed" for k in keys):
            groups[str(gate)] = {"status": "unknown_incomplete_three_arm_comparison", "all_three_rows": keys}
            continue
        base, fixed, joint = [rows[k]["summary"]["completion"] for k in keys]
        protected = lambda times: all(times[j] <= base[j] for j in base)
        groups[str(gate)] = {"status": "assessed", "all_offered_count": 4,
            "completion": {p: rows[k]["summary"]["completion"] for p, k in zip(("incumbent", "fixed_route_model", "joint_model"), keys)},
            "fixed_strict_protected": protected(fixed), "joint_strict_protected": protected(joint),
            "fixed_gain_vs_incumbent": sum(base.values()) - sum(fixed.values()),
            "joint_gain_vs_incumbent": sum(base.values()) - sum(joint.values()),
            "joint_gain_vs_fixed_model": sum(fixed.values()) - sum(joint.values()),
            "joint_vs_fixed_per_job": {j: joint[j] - fixed[j] for j in base}}
    return groups


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    protocol = plan()
    sources = [Path(p.__file__) for p in (adapter, model, v1, v2)] + [Path(__file__)]
    protocol["source_sha256"] = {str(p.resolve()): sha(p) for p in sources}
    archive = output / "source_archive"
    archive.mkdir()
    for p in sources: (archive / p.name).write_bytes(p.read_bytes())
    write(output / "preregistered_protocol.json", protocol)
    write(output / "branch_ledger.json", protocol["rows"])
    return protocol


def worker(args):
    protocol = json.loads((args.output / "preregistered_protocol.json").read_text())
    if any(sha(Path(p)) != h for p, h in protocol["source_sha256"].items()):
        raise ValueError("online_joint:source_changed_before_execution")
    if sha(args.binary) != args.expected_binary_sha256: raise ValueError("online_joint:binary_identity")
    native = load_native(args.binary)
    rows = copy.deepcopy(protocol["rows"])
    started = time.perf_counter()
    for key, row in rows.items():
        row["status"] = "unknown_in_progress"
        write(args.output / "branch_ledger.json", rows)
        try:
            raw = run_branch(native, row)
            path = args.output / (key + ".json.gz")
            path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "wt", encoding="utf-8") as stream: json.dump(raw, stream, allow_nan=False)
            row.update(status=raw["summary"]["status"], summary=raw["summary"])
        except Exception:
            row.update(status="unknown_failed", exception=traceback.format_exc())
        write(args.output / "branch_ledger.json", rows)
    changed = [p for p, h in protocol["source_sha256"].items() if sha(Path(p)) != h]
    report = {"status": "executed" if not changed and all(r["status"] in {"assessed", "readiness_observed"} for r in rows.values()) else "completed_with_unknowns",
        "schema": "g31.lt2.native_public_initial_joint_receipt.v1", "native_branches": len(rows),
        "native_binary_sha256": args.expected_binary_sha256, "source_changed": changed,
        "normal_comparisons": assess_normal(rows), "readiness": {k: r for k, r in rows.items() if k.startswith("readiness/")},
        "branch_status_counts": {s: sum(r["status"] == s for r in rows.values()) for s in sorted({r["status"] for r in rows.values()})},
        "wall_seconds": time.perf_counter() - started, "native_forks_used": 0, "native_results_used_for_policy": False,
        "rolling_joint_optimizer_implemented": False, "atomic_agreement_implemented": False,
        "calibrated_model_protection_certified": False, "complete_request_100ms_certified": False}
    write(args.output / "receipt.json", report)
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--expected-binary-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=90.)
    args = parser.parse_args()
    if args.worker: worker(args); return
    protocol = prepare(args.output)
    if not args.execute:
        print(json.dumps({"status": "prepared_no_native_calls", "branches": len(protocol["rows"])})); return
    if not args.binary or not args.expected_binary_sha256: parser.error("exact binary identity required")
    command = [sys.executable, "-m", __spec__.name, "--worker", "--output", str(args.output),
               "--binary", str(args.binary), "--expected-binary-sha256", args.expected_binary_sha256]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_seconds)
        (args.output / "worker.stdout.log").write_text(done.stdout, encoding="utf-8")
        (args.output / "worker.stderr.log").write_text(done.stderr, encoding="utf-8")
        if done.returncode: write(args.output / "worker_failure.json", {"status": "unknown_worker_failed", "returncode": done.returncode})
    except subprocess.TimeoutExpired:
        write(args.output / "worker_failure.json", {"status": "unknown_hard_timeout", "timeout_seconds": args.timeout_seconds})


if __name__ == "__main__": main()

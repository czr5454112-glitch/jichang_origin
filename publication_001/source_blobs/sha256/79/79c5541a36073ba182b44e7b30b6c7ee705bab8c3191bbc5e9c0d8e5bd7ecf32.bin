"""Prespecified original-flow FIFO-head arrival interference, with delay audit.

The three-hop hypothesis is separate from the isolated reachable-job census.
The unchanged 2-second command delay already exceeds the first node's normal
1.5-second service window. Preparation retains this negative preflight; only
an explicit --execute invocation runs the two full-input native prefix arms.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from .original_workload import ProxyContract, build_input, research_r1_authorized, digest, json_digest, summarize_execution, write_json
from .protocol_control import ProtocolClient
from .event_protocol_control import run_event_protocol_control
from .run_original_protocol import add_protocol_contract
from .native_host import load_native

HORIZON = 22200.
COMMAND_DELAY = 2.
PLAN = ((112, 113), (141, 145), (35, 11))
TARGET = "projected:1x:0"
BENEFICIARY = "projected:1x:2"


def prepare_input():
    data, manifest, _ = build_input(scale=1,
        contract=ProxyContract("nanning-on-carrier-proxy-v1-n4-s4-t2", 4, 4, 2, 1., 1., 0., "finite_berth_waiting_research_proxy"),
        horizon=HORIZON, max_events=1000000, trace_limit=0)
    authorized, permission = research_r1_authorized(data)
    authorized = add_protocol_contract(authorized)
    authorized["owner_notifications"] = {"enabled": True}
    if len(authorized["jobs"]) != 28506 or len(authorized["trays"]) != 22:
        raise ValueError("interference:population_changed")
    return authorized, manifest, permission


def timing_preflight(data):
    service = {n[0]: max(.001, n[2]) for n in data["node_records"]}
    owner = {n["node"]: n["resource_owner"] for n in data["node_contracts"]}
    stages = [{"stage": i, "from": source, "next": target, "owner": owner[source],
        "uncongested_service_seconds": service[source], "command_delay_seconds": COMMAND_DELAY,
        "normal_window_margin_seconds": service[source] - COMMAND_DELAY,
        "normal_window_status": "too_short" if service[source] < COMMAND_DELAY else
                                "native_same_timestamp_tie_required" if service[source] == COMMAND_DELAY else "long_enough"}
        for i, (source, target) in enumerate(PLAN)]
    return {"status": "conditional_uncongested_first_stage_blocked" if stages[0]["normal_window_status"] == "too_short" else "unknown_native_execution",
        "stages": stages, "first_blocking_stage": 0 if stages[0]["normal_window_status"] == "too_short" else None,
        "incoming_first_stage": {"from": 29, "to": 112, "source_owner": owner[29], "destination_owner": owner[112],
            "same_owner": owner[29] == owner[112]},
        "observability": "Destination owner first sees this tray on actual arrival; current-node owner filters native tray visibility. No fabricated remote generation or pre-issued future-from command.",
        "scope": "Static service-window screen only: congestion could extend a live window. It is not a universal impossibility proof.",
        "message_delay_reduced": False, "native_calls": 0}


class ObservedIntent:
    """One immutable three-hop program driven only by actual local views/ACKs."""
    def __init__(self):
        self.stage = 0
        self.request_id = None
        self.status = "waiting_for_local_stage"
        self.decisions = []

    def observe(self, view, client, *, allow_submit=True):
        if self.status in ("complete_intents", "rejected_intent"):
            return
        if self.request_id:
            row = client.state["outbox"][self.request_id]
            ack = row.get("client_view", {}).get("last_delivered_ack", {})
            if ack.get("delivered_at", float("inf")) > view["now"]:
                return
            if ack.get("status") == "updated":
                self.decisions[-1]["delivered_ack"] = copy.deepcopy(ack)
                self.stage += 1
                self.request_id = None
                self.status = "complete_intents" if self.stage == len(PLAN) else "waiting_for_local_stage"
            elif ack.get("status") in ("rejected", "expired", "failed", "cancelled"):
                self.decisions[-1]["delivered_ack"] = copy.deepcopy(ack)
                self.status = "rejected_intent"
                return
            else:
                return
        if self.stage == len(PLAN) or not allow_submit: return
        source, target = PLAN[self.stage]
        node = next(n for n in view["node_contracts"] if n["node"] == source)
        if node["resource_owner"] != view["owner_id"]: return
        tray = next((t for t in view["trays"] if t["business_bag_id"] == TARGET and t["node"] == source
            and t["mode"] == "loaded" and t["edge_to"] < 0), None)
        if tray is None: return
        job = next((j for j in view["jobs"] if j["business_bag_id"] == TARGET), None)
        if not job or job["storage_node"] != 53 or job["storage_released_at"] >= 0:
            return
        owner = view["owner_id"]
        payload = {"business_bag_id": TARGET, "tray_id": tray["tray_id"], "from": source, "next": target,
            "expected_generation": tray["generation"], "expected_traversal": tray["traversal_id"],
            "expiry": view["now"] + 120., "message_delay": COMMAND_DELAY}
        identity = f"live:{len(owner.encode('utf-8'))}:{owner}:interference-route-{self.stage}"
        self.request_id, reply = client.submit(owner, "route", payload, request_id=identity)
        self.status = "awaiting_delivered_ack"
        self.decisions.append({"stage": self.stage, "at": view["now"], "owner": owner, "request_id": identity,
            "local_tray": copy.deepcopy(tray), "local_job": copy.deepcopy(job), "request": copy.deepcopy(payload),
            "submission_reply": copy.deepcopy(reply)})


class OwnerBoundarySession:
    """Observe actual notified owners before the unchanged R2 activation.

    No native future clock, queue or result enters route selection. The hook
    introduces only a future 2-second command, never a physics pause or a
    zero-delay hidden action. Control and candidate use the same wrapper.
    """
    def __init__(self, native, enabled, *, feasibility_only=False):
        self.native, self.enabled = native, enabled
        self.intent = ObservedIntent()
        self.client = ProtocolClient(native, retry_period=60.)
        self.feasibility_only = feasibility_only
        self.observed_target_edges = []

    def __getattr__(self, name): return getattr(self.native, name)

    def observe_protocol_control_policy(self, owner):
        return self.native.observe_protocol_control_policy(owner)

    def advance_until_owner_notification(self, owners, after, horizon, *, max_events):
        response = self.native.advance_until_owner_notification(owners, after, horizon, max_events=max_events)
        if response.get("timestamp_complete"):
            for owner in sorted(response.get("notifications", {})):
                self.client.refresh(owner_id=owner)
                if self.enabled:
                    view = self.native.observe_protocol(owner)
                    for tray in view["trays"]:
                        if tray["business_bag_id"] == TARGET and tray["edge_to"] >= 0 and tray["edge_from"] in {p[0] for p in PLAN}:
                            key = (tray["generation"], tray["traversal_id"])
                            if not any(tuple(e["identity"]) == key for e in self.observed_target_edges):
                                self.observed_target_edges.append({"at": view["now"], "owner": owner, "identity": key,
                                    "from": tray["edge_from"], "to": tray["edge_to"], "local_tray": copy.deepcopy(tray)})
                    self.intent.observe(view, self.client)
            if self.feasibility_only:
                status = feasibility_status(self.intent, self.observed_target_edges)
                if status in ("rejected_intervention_not_admitted", "three_intents_and_edges_observed"):
                    raise FeasibilityResolved(status)
        return response


class FeasibilityResolved(Exception):
    """Stop only after a complete native timestamp and lawful delivered facts."""


def feasibility_status(intent, observed_edges):
    if intent.status == "rejected_intent":
        return "rejected_intervention_not_admitted"
    edges = {(e["from"], e["to"]) for e in observed_edges}
    if intent.status == "complete_intents" and all(edge in edges for edge in PLAN):
        return "three_intents_and_edges_observed"
    return "unknown_pending_or_missing_execution"


def compare(data, arms):
    expected = {j["business_bag_id"] for j in data["jobs"]}
    summary = {"offered_denominator": len(expected), "common_horizon": HORIZON,
        "full_day_complete": False, "complete_request_100ms_certified": False,
        "strict_protection_status": "unknown_unfinished_offered_jobs", "mechanism_status": "unknown"}
    if set(arms) != {"control", "candidate"} or any(a.get("status") != "reached" for a in arms.values()):
        summary["mechanism_status"] = "unknown_missing_or_censored_arm"
        return summary
    jobs = {a: {j["business_bag_id"]: j for j in r["result"]["jobs"]} for a, r in arms.items()}
    if any(set(j) != expected or len(arms[a]["result"]["jobs"]) != len(expected) for a, j in jobs.items()):
        summary["mechanism_status"] = "unknown_denominator_mismatch"
        return summary
    if any(r["result"]["advance"]["status"] != "reached" or r["result"]["advance"]["physical_time"] != HORIZON or not r["result"]["advance"]["horizon_complete"] for r in arms.values()):
        summary["mechanism_status"] = "unknown_horizon"
        return summary
    if all(all(j["completed_at"] >= 0 for j in by.values()) for by in jobs.values()):
        summary["strict_protection_status"] = "passed" if all(jobs["candidate"][j]["completed_at"] <= jobs["control"][j]["completed_at"] for j in expected) else "failed"
    completed_both = {j for j in expected if min(jobs[a][j]["completed_at"] for a in jobs) >= 0}
    summary["comparable_completed_both_count"] = len(completed_both)
    summary["comparable_completion_deltas"] = {j: jobs["candidate"][j]["completed_at"] - jobs["control"][j]["completed_at"] for j in sorted(completed_both)}
    summary["all_population"] = {a: summarize_execution(data, r["result"]) for a, r in arms.items()}
    summary["beneficiary"] = {a: {"completed_at": jobs[a][BENEFICIARY]["completed_at"],
        "deadline_met": jobs[a][BENEFICIARY]["deadline_met"]} for a in arms}
    receipts = arms["candidate"]["result"]["receipts"]
    enters = {j: [r["time"] for r in receipts if r["business_bag_id"] == j and r["event"] == "STORAGE_ENTER"] for j in (TARGET, BENEFICIARY)}
    reordered = len(enters[TARGET]) == len(enters[BENEFICIARY]) == 1 and enters[BENEFICIARY][0] < enters[TARGET][0]
    chosen = [(r["from"], r["to"]) for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == TARGET and r["from"] in {p[0] for p in PLAN}]
    intent = arms["candidate"]["intent"]
    decisions = intent["decisions"]
    actions = intent["status"] == "complete_intents" and len(decisions) == len(PLAN) and all(p in chosen for p in PLAN)
    for index, decision in enumerate(decisions[:len(PLAN)]):
        ack = decision.get("delivered_ack", {})
        request = decision["request"]
        edges = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == TARGET
            and (r["from"], r["to"]) == PLAN[index] and r["time"] >= decision["at"] + COMMAND_DELAY]
        actions = actions and (ack.get("status") == "updated" and ack.get("delivered_at", float("inf")) <= HORIZON
            and request["message_delay"] == COMMAND_DELAY and (request["from"], request["next"]) == PLAN[index]
            and request["expected_generation"] == decision["local_tray"]["generation"]
            and request["expected_traversal"] == decision["local_tray"]["traversal_id"]
            and bool(edges) and ack.get("executed_at", float("inf")) <= edges[0]["time"])
    summary.update(actual_storage_enter=enters, beneficiary_enters_before_target=reordered,
        all_three_intents_executed=actions, actual_selected_source_edges=chosen,
        candidate_intent_status=intent["status"], candidate_decisions=intent["decisions"])
    completed = jobs["candidate"][BENEFICIARY]["completed_at"] >= 0
    summary["mechanism_status"] = "witness" if actions and reordered and completed else "not_demonstrated"
    return summary


def gzip_json(path, value):
    with gzip.open(path, "wt", encoding="utf-8") as stream: json.dump(value, stream, allow_nan=False)


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    data, manifest, permission = prepare_input()
    protocol = {"schema": "g31.lt2.original_interference.v1", "hypothesis": "Three observed-owner pre-Storage intents delay unreachable bag0 behind reachable bag2 without changing FIFO or business contracts",
        "target": TARGET, "beneficiary": BENEFICIARY, "route_program": PLAN, "command_delay": COMMAND_DELAY,
        "horizon": HORIZON, "native_branch_budget": 3, "input_business_count": len(data["jobs"]), "tray_count": len(data["trays"]),
        "feasibility_gate": {"native_branch_budget": 1, "stop_on": "first delivered rejection or allthree updated ACKs plus actualownerlocal selectededges",
            "comparison_admitted_only_if": "allthree selected intentsandactualedges observed underunchanged2s delay",
            "on_rejection": "stopatactualnativeclock; nobusinessmetrics; bothH22200 comparisonarms notadmitted",
            "incomplete_or_timeout": "unknownfeasibility; comparisonnotadmitted"},
        "conditional_comparison_branch_budget": 2,
        "same_permission_all_arms": True, "same_r2_continuation": "event predictive forecasts+prebalance; automatic R1 disabled in both arms",
        "population_scope": "All28506 original source obligations retained; common22200 prefix, not full day",
        "primary_evidence": "three delivered updated ACKs + three actual edges + bag2 Storage beforebag0 + bag2 physicalcompletion",
        "strict_protection": "unknown if any offered job unfinished in either arm; never interpret -1 as a completion time",
        "branch_ledger": {"control": {"status": "unknown_unexecuted"}, "candidate": {"status": "unknown_unexecuted"}},
        "timing_preflight": timing_preflight(data), "input_sha256": json_digest(data),
        "driver_sha256": digest(Path(__file__))}
    gzip_json(output / "input.json.gz", data)
    write_json(output / "input_manifest.json", manifest)
    write_json(output / "permission_manifest.json", permission)
    write_json(output / "preregistered_protocol.json", protocol)
    write_json(output / "branch_ledger.json", protocol["branch_ledger"])
    return protocol


def worker(args):
    data = json.load(gzip.open(args.output / "input.json.gz", "rt"))
    protocol = json.loads((args.output / "preregistered_protocol.json").read_text())
    if (json_digest(data) != protocol["input_sha256"] or digest(args.binary) != args.expected_binary_sha256
            or digest(Path(__file__)) != protocol["driver_sha256"]):
        raise ValueError("interference:frozen_identity")
    sources = [Path(__file__), *[Path(__file__).with_name(n + ".py") for n in ("original_workload", "protocol_control", "event_protocol_control", "analytic_control", "regional_control", "native_host", "run_original_protocol")]]
    source_before = {str(p): digest(p) for p in sources}
    archive = args.output / "source_archive"
    archive.mkdir(exist_ok=False)
    for source in sources: (archive / source.name).write_bytes(source.read_bytes())
    native = load_native(args.binary)
    seed = native.NativeSession(data)
    checkpoint = seed.offline_state_sha256()
    arms = {}
    ledger = copy.deepcopy(protocol["branch_ledger"])
    started = time.perf_counter()
    owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
    gate = OwnerBoundarySession(seed.fork(), True, feasibility_only=True)
    gate_status = "unknown_pending_or_missing_execution"
    try:
        run_event_protocol_control(gate, owners, horizon=HORIZON, control_period=60., command_delay=COMMAND_DELAY,
            publication_delay=.5, retry_period=60., lease_seconds=120., routes=False, forecasts=True,
            predictive=True, prebalance=True, event_budget=100000, max_activations=100000)
    except FeasibilityResolved as stop:
        gate_status = str(stop)
    gate_report = {"schema": "g31.lt2.original_interference_feasibility.v1", "status": gate_status,
        "input_business_count": len(data["jobs"]), "tray_count": len(data["trays"]),
        "actual_native_clock": gate.physical_time, "input_sha256": protocol["input_sha256"],
        "checkpoint_identity": checkpoint, "intent": vars(gate.intent), "route_outbox": gate.client.state,
        "route_calls": gate.client.calls, "owner_observed_actual_edges": gate.observed_target_edges,
        "business_metrics": None, "business_metric_scope": "not measured by feasibility gate",
        "comparison_admitted": gate_status == "three_intents_and_edges_observed",
        "source_changed": [p for p, expected in source_before.items() if digest(Path(p)) != expected]}
    if gate_report["source_changed"]:
        gate_report["status"], gate_report["comparison_admitted"] = "unknown_source_changed", False
    write_json(args.output / "feasibility_gate.json", gate_report)
    if not gate_report["comparison_admitted"]:
        for row in ledger.values():
            row.update(status="not_admitted", reason=gate_report["status"])
        write_json(args.output / "branch_ledger.json", ledger)
        write_json(args.output / "receipt.json", {"status": "comparison_not_admitted", "feasibility": gate_report,
            "branch_ledger": ledger, "business_metrics": None, "gain": None, "strict_protection_status": "not_assessed",
            "native_branches_executed": 1, "source_before": source_before, "source_changed": gate_report["source_changed"],
            "binary_sha256": args.expected_binary_sha256, "wall_seconds": time.perf_counter() - started})
        return
    for label in ("control", "candidate"):
        ledger[label]["status"] = "unknown_in_progress"
        write_json(args.output / "branch_ledger.json", ledger)
        session = seed.fork()
        if session.offline_state_sha256() != checkpoint: raise ValueError("interference:checkpoint_mismatch")
        wrapped = OwnerBoundarySession(session, label == "candidate")
        run = run_event_protocol_control(wrapped, owners, horizon=HORIZON, control_period=60.,
            command_delay=COMMAND_DELAY, publication_delay=.5, retry_period=60., lease_seconds=120.,
            routes=False, forecasts=True, predictive=True, prebalance=True, event_budget=100000, max_activations=100000)
        wrapped.client.refresh(retry=False)
        # Reconcile final delivered ACK without observing any private state.
        if wrapped.intent.request_id:
            owner = wrapped.client.state["outbox"][wrapped.intent.request_id]["payload"]["owner_id"]
            wrapped.intent.observe(session.observe_protocol(owner), wrapped.client, allow_submit=False)
        row = {"status": run["status"], "result": run["result"], "controller_state": run["controller_state"],
            "intent": vars(wrapped.intent), "route_outbox": wrapped.client.state, "route_calls": wrapped.client.calls,
            "control_calls": run["client_calls"], "checkpoint_identity": checkpoint}
        gzip_json(args.output / f"{label}.json.gz", row)
        arms[label] = row
        ledger[label] = {"status": "executed" if run["status"] == "reached" else "unknown_censored", "native_status": run["status"]}
        write_json(args.output / "branch_ledger.json", ledger)
    report = compare(data, arms)
    report.update(wall_seconds=time.perf_counter() - started, source_before=source_before,
        source_changed=[p for p, expected in source_before.items() if digest(Path(p)) != expected],
        binary_sha256=args.expected_binary_sha256, branch_ledger=ledger)
    if report["source_changed"]:
        report["mechanism_status"] = "unknown_source_changed"
    write_json(args.output / "receipt.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--expected-binary-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=180.)
    a = parser.parse_args()
    if a.worker: worker(a); return
    protocol = prepare(a.output)
    if not a.execute:
        print(json.dumps({"status": "prepared_no_native_calls", "timing_preflight": protocol["timing_preflight"]}, indent=2))
        return
    if not a.binary or not a.expected_binary_sha256: parser.error("--execute requires exact native binary identity")
    command = [sys.executable, "-m", __package__ + ".research_original_interference", "--worker", "--output", str(a.output),
        "--binary", str(a.binary), "--expected-binary-sha256", a.expected_binary_sha256]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=a.timeout_seconds)
        (a.output / "worker.stdout.log").write_text(done.stdout, encoding="utf-8")
        (a.output / "worker.stderr.log").write_text(done.stderr, encoding="utf-8")
        if done.returncode: write_json(a.output / "worker_failure.json", {"status": "unknown_worker_failed", "returncode": done.returncode})
    except subprocess.TimeoutExpired:
        write_json(a.output / "worker_failure.json", {"status": "unknown_hard_timeout", "timeout_seconds": a.timeout_seconds,
            "branch_ledger_preserved": True, "partial_population_is_not_complete": True})


if __name__ == "__main__": main()

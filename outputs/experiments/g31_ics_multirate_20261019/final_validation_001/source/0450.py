"""Prepared matched full-input prefix comparison, admitted only by native gate.

Unfinished job completion differences remain undefined. Reordering a Storage
head may be a local mechanism witness without proving all-job protection.
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
from . import research_original_tie_chain as chain
from .original_workload import digest, json_digest, write_json
from .native_host import audit_result

HORIZON = 22200.
BENEFICIARY = "projected:1x:2"


class ComparisonBoundary(chain.OwnerBoundary):
    def __init__(self, native, path, commands, enabled):
        super().__init__(native, path, commands)
        self.enabled = enabled

    def advance_until_owner_notification(self, owners, after, horizon, *, max_events):
        response = self.native.advance_until_owner_notification(owners, after, horizon, max_events=max_events)
        if response.get("timestamp_complete"):
            for owner in sorted(response.get("notifications", {})):
                self.client.refresh(owner_id=owner)
                view = self.native.observe_protocol(owner)
                if self.enabled: self.intent.observe(view, self.client)
        return response


def assess(data, arms):
    contracts = {j["business_bag_id"]: j for j in data["jobs"]}
    offered = {j for j, c in contracts.items() if c["arrival"] <= HORIZON}
    report = {"offered_full_input_denominator": len(contracts), "arrived_by_common_horizon": len(offered),
        "not_arrived_by_common_horizon": len(contracts) - len(offered), "common_horizon": HORIZON,
        "scope": "full input, common prefix horizon; no full-day claim", "status": "unknown_missing_or_censored_arm",
        "strict_full_population_protection": "unknown_unfinished_or_unobserved_jobs",
        "strict_horizon_offered_protection": "unknown_unfinished_or_unobserved_jobs", "gain_all_jobs": None,
        "storage_order_mechanism": "unknown", "unfinished_completion_delta": "undefined, never zero or infinity",
        "business_contracts_changed": False, "permission_symmetric": True, "arms": {}}
    jobs = {}
    for label, arm in arms.items():
        result = arm.get("result")
        if not result: continue
        rows = result["jobs"]
        indexed = {j["business_bag_id"]: j for j in rows}
        if len(indexed) != len(rows) or not set(indexed) <= set(contracts):
            report["status"] = "unknown_denominator_mismatch"; return report
        jobs[label] = indexed
        complete = {j for j, r in indexed.items() if r["completed_at"] >= 0}
        due = {j for j in offered if 0 <= contracts[j]["deadline"] <= HORIZON}
        report["arms"][label] = {"native_reported_job_rows": len(indexed), "completed": len(complete),
            "unfinished_arrived": len(offered - complete), "missing_arrived_rows": len(offered - set(indexed)),
            "due_by_horizon": len(due), "due_unfinished": len(due - complete),
            "completed_due_on_time": sum(j in complete and indexed[j]["completed_at"] <= contracts[j]["deadline"] for j in due),
            "native_advance": result.get("advance"), "native_population": result.get("population"),
            "physical_audit": arm.get("physical_audit", {"status": "unknown"})}
    if set(arms) != {"control", "candidate"} or set(jobs) != set(arms): return report
    for arm in arms.values():
        advance = arm["result"].get("advance", {})
        if arm["status"] != "reached" or not advance.get("horizon_complete") or advance.get("physical_time") != HORIZON:
            return report
    if any(not offered <= set(rows) for rows in jobs.values()):
        report["status"] = "unknown_missing_arrived_population"; return report
    if any(a.get("physical_audit", {}).get("status") != "passed" for a in arms.values()):
        report["status"] = "unknown_physical_audit"; return report
    report["status"] = "assessed_common_prefix"
    completed_both = {j for j in offered if all(jobs[a][j]["completed_at"] >= 0 for a in jobs)}
    report["completion_deltas_defined_subset"] = {j: jobs["candidate"][j]["completed_at"] - jobs["control"][j]["completed_at"] for j in sorted(completed_both)}
    report["completion_delta_defined_count"] = len(completed_both)
    if any(d > 0 for d in report["completion_deltas_defined_subset"].values()):
        report["strict_horizon_offered_protection"] = "failed"
        report["strict_full_population_protection"] = "failed"
    if completed_both == offered:
        report["strict_horizon_offered_protection"] = "passed" if all(d <= 0 for d in report["completion_deltas_defined_subset"].values()) else "failed"
    if completed_both == set(contracts):
        report["strict_full_population_protection"] = report["strict_horizon_offered_protection"]
        report["gain_all_jobs"] = -sum(report["completion_deltas_defined_subset"].values())
    entries = {}
    for label, arm in arms.items():
        entries[label] = {j: [r["time"] for r in arm["result"]["receipts"] if r["event"] == "STORAGE_ENTER" and r["business_bag_id"] == j]
                         for j in (chain.TARGET, BENEFICIARY)}
    report["actual_storage_entries"] = entries
    target = chain.TARGET
    ordered = all(len(entries[a][j]) == 1 for a in arms for j in (target, BENEFICIARY))
    ordered = ordered and entries["control"][target][0] < entries["control"][BENEFICIARY][0] and entries["candidate"][BENEFICIARY][0] < entries["candidate"][target][0]
    intent = arms["candidate"]["intent"]
    decisions = intent["decisions"]
    expected = [(1, 2), (5, 33), (33, 51), (29, 146)]
    accepted = len(decisions) == 4 and intent["status"] == "all_four_intents_and_edges_observed"
    for decision, edge in zip(decisions, expected):
        ack = decision.get("delivered_ack", {}); request = decision["request"]
        accepted = accepted and (request["from"], request["next"]) == edge and request["message_delay"] == 2.
        accepted = accepted and ack.get("status") == "updated" and ack.get("delivered_at", float("inf")) <= HORIZON
        accepted = accepted and request["expected_generation"] == decision["local_tray"]["generation"] and request["expected_traversal"] == decision["local_tray"]["traversal_id"]
        actual = [r for r in arms["candidate"]["result"]["receipts"] if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == target and (r["from"], r["to"]) == edge]
        accepted = accepted and len(actual) == 1 and decision["at"] + 2. <= ack.get("executed_at", -1.) <= actual[0]["time"]
    edges = [r for r in arms["candidate"]["result"]["receipts"] if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == target and ":storage_in:" in r["transport_leg_id"]]
    actual_path = [edges[0]["from"]] + [r["to"] for r in edges] if edges else []
    path_matches = actual_path == intent["path"]
    beneficiary = {a: jobs[a].get(BENEFICIARY, {}).get("completed_at", -1.) for a in arms}
    report.update(actual_target_storage_path=actual_path, four_command_acks_accepted=bool(accepted), planned_path_executed=path_matches,
        beneficiary_completion=beneficiary, actual_storage_order_reversed=bool(ordered))
    report["storage_order_mechanism"] = "witness_with_full_protection_unknown" if accepted and path_matches and ordered and beneficiary["candidate"] >= 0 else "not_demonstrated"
    return report


def validate_gate(gate, protocol, binary_sha):
    if gate.get("status") != "all_four_intents_and_edges_observed" or gate.get("source_changed"):
        return False
    if gate.get("input_sha256") != protocol["input_sha256"] or gate.get("binary_sha256") != binary_sha:
        return False
    intent = gate.get("intent", {})
    if intent.get("commands") != protocol["hypothesis"]["commands"] or intent.get("path") != protocol["hypothesis"]["path"]:
        return False
    decisions = intent.get("decisions", [])
    edges = {(r["from"], r["to"]) for r in intent.get("observed_edges", [])}
    if len(decisions) != 4: return False
    for decision, command in zip(decisions, protocol["hypothesis"]["commands"]):
        request = decision.get("request", {}); ack = decision.get("delivered_ack", {})
        if (request.get("from"), request.get("next")) != (command["from"], command["next"]) or request.get("message_delay") != 2.:
            return False
        if ack.get("status") != "updated" or ack.get("delivered_at", float("inf")) > gate["actual_native_clock"]:
            return False
        if not decision["at"] + 2. <= ack.get("executed_at", -1.) <= ack.get("delivered_at", -1.): return False
        if request.get("expected_generation") != decision["local_tray"]["generation"] or request.get("expected_traversal") != decision["local_tray"]["traversal_id"]: return False
        if (command["from"], command["next"]) not in edges: return False
    return True


def prepare(output, input_file, paths):
    output.mkdir(parents=True, exist_ok=False)
    data = json.load(gzip.open(input_file, "rt"))
    prior = json.loads((paths / "preregistered_protocol.json").read_text())
    summary = json.loads((paths / "summary.json").read_text())
    chosen = next(s["selected_offline_hypothesis"] for s in summary["selected_hypotheses"] if s["business_bag_id"] == chain.TARGET)
    if digest(input_file) != prior["source_input_sha256"]: raise ValueError("tie_comparison:input_identity")
    sources = [Path(__file__), Path(chain.__file__), *[Path(__file__).with_name(n + ".py") for n in (
        "original_workload", "protocol_control", "event_protocol_control", "analytic_control", "regional_control", "native_host")]]
    archive = output / "source_archive"; archive.mkdir()
    for source in sources: (archive / source.name).write_bytes(source.read_bytes())
    protocol = {"schema": "g31.lt2.original_two_second_matched_prefix.v1", "native_branch_budget": 2,
        "admission": "sameinput/samebinary four-stage nativegate withallupdatedACKs+actualedges; otherwisebotharmsnotadmitted",
        "input_sha256": json_digest(data), "source_input_file_sha256": digest(input_file), "input_business_count": len(data["jobs"]),
        "tray_count": len(data["trays"]), "horizon": HORIZON, "hypothesis": chosen,
        "source_path_census_sha256": digest(paths / "summary.json"),
        "source_sha256": {str(p.resolve()): digest(p) for p in sources},
        "paired_conditions": "samecompleteinput/checkpoint/22trays/researchR1permission/FIFO/capacity/gates/deadlines/exogenousfaults; sameeventR2forecast/predictive/prebalance continuation; controlnativeR1 vsfouractualcandidatecommands",
        "order": ["control", "candidate"], "no_selection_after_outcomes": True,
        "protection": "all28506 retained; not-yet-arrived explicit; eachunfinishedcompletiondifferenceundefined, includingbag0; nofullprotectionunlessallcompleteboth; reportall3998horizon-arrivals separately",
        "primary_mechanism": "fouractualACKedcommands+actualsimplepath, Storagearrivalorderbag2beforebag0, actualbag2completion; commonHcontrolcounterfactual; mechanismdoesnotcertifyprotection",
        "censoring": "hardtimeout180sperarm or native/event/activationbound retainsunknown; no0gain/failedprotection substitution",
        "native_calls_at_preparation": 0, "complete_request_100ms_certified": False}
    chain.old.gzip_json(output / "input.json.gz", data)
    write_json(output / "preregistered_protocol.json", protocol)
    write_json(output / "branch_ledger.json", {a: {"status": "unknown_unexecuted_waiting_gate"} for a in protocol["order"]})
    return protocol


def worker(args):
    protocol = json.loads((args.output / "preregistered_protocol.json").read_text())
    data = json.load(gzip.open(args.output / "input.json.gz", "rt"))
    gate = json.loads(args.gate_receipt.read_text())
    if not validate_gate(gate, protocol, args.expected_binary_sha256):
        write_json(args.output / "branch_ledger.json", {a: {"status": "not_admitted", "reason": "native_gate_not_verified"} for a in protocol["order"]})
        write_json(args.output / "receipt.json", {"status": "comparison_not_admitted", "native_branches_executed": 0, "business_metrics": None})
        return
    if json_digest(data) != protocol["input_sha256"] or digest(args.binary) != args.expected_binary_sha256:
        raise ValueError("tie_comparison:frozen_input_or_binary")
    if any(digest(Path(s)) != h for s, h in protocol["source_sha256"].items()): raise ValueError("tie_comparison:source_drift")
    native = chain.load_native(args.binary); seed = native.NativeSession(data); checkpoint = seed.offline_state_sha256()
    session = seed.fork()
    if session.offline_state_sha256() != checkpoint: raise ValueError("tie_comparison:checkpoint_identity")
    chosen = protocol["hypothesis"]
    wrapped = ComparisonBoundary(session, chosen["path"], chosen["commands"], args.arm == "candidate")
    owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
    started = time.perf_counter()
    result = chain.run_event_protocol_control(wrapped, owners, horizon=HORIZON, control_period=60., command_delay=2.,
        publication_delay=.5, retry_period=60., lease_seconds=120., routes=False, forecasts=True,
        predictive=True, prebalance=True, event_budget=100000, max_activations=100000)
    physical_audit = {"status": "unknown_missing_or_censored_result"}
    if result.get("result"):
        replay = copy.deepcopy(data)
        replay["transfers"] += [{**c["request"], "issued_at": c["at"]} for c in result["client_calls"] if c["kind"] == "transfer" and not c["retry"]]
        try: physical_audit = audit_result(replay, result["result"])
        except (AssertionError, ValueError, KeyError) as error:
            physical_audit = {"status": "failed", "reason": str(error)}
    raw = {"status": result["status"], "result": result["result"], "controller_state": result["controller_state"],
        "control_calls": result["client_calls"], "intent": vars(wrapped.intent), "route_calls": wrapped.client.calls,
        "route_outbox": wrapped.client.state, "checkpoint_identity": checkpoint, "input_sha256": protocol["input_sha256"],
        "binary_sha256": args.expected_binary_sha256, "gate_receipt_sha256": digest(args.gate_receipt),
        "physical_audit": physical_audit,
        "source_changed": [s for s, h in protocol["source_sha256"].items() if digest(Path(s)) != h],
        "wall_seconds": time.perf_counter() - started}
    chain.old.gzip_json(args.output / f"{args.arm}.json.gz", raw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--input", type=Path); p.add_argument("--paths", type=Path)
    p.add_argument("--gate-receipt", type=Path); p.add_argument("--binary", type=Path); p.add_argument("--expected-binary-sha256")
    p.add_argument("--execute", action="store_true"); p.add_argument("--worker", action="store_true"); p.add_argument("--arm", choices=("control", "candidate"))
    p.add_argument("--timeout-seconds", type=float, default=180.)
    a = p.parse_args()
    if a.worker: worker(a); return
    protocol = prepare(a.output, a.input, a.paths)
    if not a.execute: print("prepared_no_native_calls:twoarms_require_prior_nativegate"); return
    if not a.binary or not a.expected_binary_sha256 or not a.gate_receipt: p.error("exact_binary_and_prior_gate_required")
    gate = json.loads(a.gate_receipt.read_text())
    if not validate_gate(gate, protocol, a.expected_binary_sha256):
        write_json(a.output / "branch_ledger.json", {arm: {"status": "not_admitted"} for arm in protocol["order"]})
        return
    ledger, arms = {}, {}
    for arm in protocol["order"]:
        command = [sys.executable, "-m", __spec__.name, "--worker", "--output", str(a.output), "--gate-receipt", str(a.gate_receipt),
            "--binary", str(a.binary), "--expected-binary-sha256", a.expected_binary_sha256, "--arm", arm]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=a.timeout_seconds)
            (a.output / f"{arm}.stdout.log").write_text(done.stdout, encoding="utf-8")
            (a.output / f"{arm}.stderr.log").write_text(done.stderr, encoding="utf-8")
            if done.returncode or not (a.output / f"{arm}.json.gz").exists(): ledger[arm] = {"status": "unknown_failed"}
            else:
                arms[arm] = json.load(gzip.open(a.output / f"{arm}.json.gz", "rt"))
                ledger[arm] = {"status": arms[arm]["status"]}
        except subprocess.TimeoutExpired: ledger[arm] = {"status": "unknown_hard_timeout"}
        write_json(a.output / "branch_ledger.json", ledger)
    data = json.load(gzip.open(a.output / "input.json.gz", "rt"))
    report = assess(data, arms)
    report["branch_ledger"] = ledger
    report["source_changed"] = sorted({s for row in arms.values() for s in row["source_changed"]})
    if report["source_changed"] or len({r["checkpoint_identity"] for r in arms.values()}) > 1:
        report["status"] = "unknown_source_or_checkpoint_mismatch"
        report["storage_order_mechanism"] = "unknown"
        report["strict_full_population_protection"] = "unknown"
        report["strict_horizon_offered_protection"] = "unknown"
        report["gain_all_jobs"] = None
    write_json(a.output / "receipt.json", report)


if __name__ == "__main__": main()

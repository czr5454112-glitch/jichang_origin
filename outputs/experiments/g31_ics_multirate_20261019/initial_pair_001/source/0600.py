"""Compare periodic and lawful event activation on common native contracts."""
from __future__ import annotations

import argparse
import copy
import gzip
import json
from pathlib import Path
import time
import traceback

from .assess_joint_window_protection import compare
from .event_protocol_control import run_event_protocol_control
from .finite_reference import _horizon_completion, outcome_cost
from .native_host import audit_result, load_native
from .original_mechanism import select_input
from .original_workload import digest, write_json
from .protocol_control import run_protocol_control
from .run_original_protocol import (CONTROLLER, add_protocol_contract, assess_execution,
                                    expected_digest, request_ledger)
from .validate_protocol_control import replay_input, scenarios


POLICIES = {
    "periodic_reactive": ("periodic", dict(routes=False, forecasts=False, prebalance=True, predictive=False)),
    "periodic_predictive": ("periodic", dict(routes=False, forecasts=True, prebalance=True, predictive=True)),
    "event_reactive": ("event", dict(routes=False, forecasts=False, prebalance=True, predictive=False)),
    "event_predictive": ("event", dict(routes=False, forecasts=True, prebalance=True, predictive=True)),
    "event_joint": ("event", dict(routes=True, forecasts=True, prebalance=True, predictive=True)),
}


def gz(path, value):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)


def execute(session, owners, mode, options, horizon, *, max_seconds, event_budget, controller):
    started = time.perf_counter()
    aggregate = {"status": "running", "result": None, "controller_state": None,
        "control_records": [], "client_calls": [], "native_batches": [], "segments": []}
    target = min(3600., horizon)
    while True:
        runner = run_event_protocol_control if mode == "event" else run_protocol_control
        run = runner(session, owners, horizon=target, event_budget=event_budget,
            state=aggregate["controller_state"], **controller, **options)
        for key in ("control_records", "client_calls", "native_batches"):
            aggregate[key].extend(run[key])
        for key in ("controller_state", "result", "status", "control_continuation"):
            aggregate[key] = run[key]
        aggregate["segments"].append({"horizon": target, "status": run["status"],
            "physical_time": session.physical_time, "wall_seconds": time.perf_counter()-started})
        if run["status"] != "reached" or target == horizon:
            break
        if time.perf_counter()-started >= max_seconds:
            aggregate["status"] = "wall_budget_exhausted"
            aggregate["result"] = None
            break
        target = min(target+3600., horizon)
    aggregate["wall_seconds"] = time.perf_counter()-started
    return aggregate


def assess_synthetic(data, run, session, horizon):
    if not isinstance(run.get("result"), dict):
        return {"status": "unknown_incomplete_execution", "metrics": None,
            "completion": {"status": "unknown", "problems": ["no_complete_native_result"]}}
    completion = _horizon_completion(run["result"], session, horizon, run["status"])
    if completion["status"] != "reached":
        return {"status": "unknown_incomplete_execution", "metrics": None, "completion": completion}
    audit = audit_result(replay_input(data, run["client_calls"]), run["result"])
    return {"status": "verified_complete_execution", "audit": audit, "completion": completion,
        "metrics": outcome_cost(run["result"], data["jobs"], horizon)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", type=expected_digest, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", choices=("synthetic", "original24"), required=True)
    parser.add_argument("--max-seconds-per-policy", type=float, default=180.)
    parser.add_argument("--event-budget", type=int, default=100000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), *(Path(__file__).parent/name for name in (
        "event_protocol_control.py", "protocol_control.py", "analytic_control.py", "regional_control.py",
        "native_host.py", "original_mechanism.py", "original_workload.py", "finite_reference.py",
        "run_original_protocol.py", "validate_protocol_control.py", "validate_known_service_control.py",
        "validate_coupled_control.py", "assess_joint_window_protection.py"))]
    before = {str(p): digest(p) for p in paths}
    archive = args.output/"source_archive"
    archive.mkdir()
    for p in paths:
        (archive/p.name).write_bytes(p.read_bytes())
    receipt = {"schema": "g31.event_protocol_comparison.v1", "status": "preparing", "cases": {},
        "source_before": before, "binary_sha256": digest(args.binary), "suite": args.suite,
        "complete_100ms_requirement_certified": False, "global_optimality": "unknown",
        "novelty": "notification/remaining-service correctness and public analytic baselines; no novel-method claim"}
    write_json(args.output/"receipt.json", receipt)
    try:
        if receipt["binary_sha256"] != args.expected_binary_sha256:
            raise ValueError("event_campaign:binary_identity_mismatch")
        if args.suite == "original24":
            original, selection, lineage = select_input(24, horizon=86400.)
            data = add_protocol_contract(original)
            fixed = [("original24", data, sorted({n.get("resource_owner", n["zone"]) for n in data["node_contracts"]}))]
            horizon, controller = 86400., CONTROLLER
            write_json(args.output/"selection.json", selection)
            gz(args.output/"mother_crosswalk.json.gz", lineage)
        else:
            fixed = scenarios()
            horizon = 50.
            controller = dict(control_period=.5, command_delay=.01, publication_delay=.02,
                retry_period=.5, compact=True, lease_seconds=120.)
        fixed = [(name, {**copy.deepcopy(data), "owner_notifications": {"enabled": True}}, owners)
                 for name, data, owners in fixed]
        write_json(args.output/"protocol.json", {"policies": POLICIES, "horizon": horizon,
            "controller": controller, "cases": [name for name, _, _ in fixed],
            "event_budget_per_advance": args.event_budget, "max_seconds_per_policy": args.max_seconds_per_policy,
            "wall_budget_scope": "checked between common one-hour physical segments; no background stop guarantee",
            "selection": "all cases and policies fixed before executing native; no result selection",
            "common_contract": "same enabled native notifications, owner messages, physical tasks, tray stock and permissions for every policy",
            "information_ablation": "event versus periodic compares lawful activation timing; predictive versus reactive also changes allowed forecast use",
            "timing_scope": "diagnostic wall times; no full request or deployment SLA claim"})
        native = load_native(args.binary)
        for name, data, owners in fixed:
            folder = args.output/name
            folder.mkdir()
            write_json(folder/"input.json", data)
            case = {"policies": {}}
            for policy, (mode, options) in POLICIES.items():
                directory = folder/policy
                directory.mkdir()
                try:
                    session = native.NativeSession(data)
                    run = execute(session, owners, mode, options, horizon,
                        max_seconds=args.max_seconds_per_policy, event_budget=args.event_budget, controller=controller)
                    gz(directory/"run.json.gz", run)
                    if args.suite == "original24":
                        row = assess_execution(data, run, session)
                    else:
                        row = assess_synthetic(data, run, session, horizon)
                    row["controller_status"] = run["status"]
                    row["wall_seconds"] = run["wall_seconds"]
                    row["control_record_count"] = len(run["control_records"])
                    row["owner_activation_count"] = (len(run["control_records"]) if mode == "event" else
                        sum(len(record["owner_decisions"]) for record in run["control_records"]))
                    if row["status"] == "verified_complete_execution":
                        views = {owner: session.observe_protocol(owner) for owner in owners}
                        ledger = request_ledger(run["client_calls"], views)
                        gz(directory/"delivered_views.json.gz", views)
                        gz(directory/"request_ack_ledger.json.gz", ledger)
                        row["ledger_summary"] = {k: v for k, v in ledger.items()
                            if k not in ("requests", "delivered_transfer_acks", "delivered_command_acks")}
                        forecasts = [r for r in ledger["requests"] if r["kind"] == "service_forecast"]
                        row["forecast_final_status"] = {s: sum((r["last_delivered_ack"] or {}).get("status", "unknown") == s for r in forecasts)
                            for s in ("delivered", "rejected", "unknown")}
                        row["offline_final_state_sha256"] = session.offline_state_sha256()
                except Exception:
                    row = {"status": "failed_execution", "exception": traceback.format_exc(), "metrics": None}
                row["declared_business_ids"] = sorted(j["business_bag_id"] for j in data["jobs"] if j["arrival"] <= horizon)
                row["declared_offered"] = len(row["declared_business_ids"])
                write_json(directory/"assessment.json", row)
                case["policies"][policy] = row
                receipt["cases"][name] = case
                write_json(args.output/"receipt.json", receipt)
            case["comparisons"] = {}
            for candidate, baseline in (("event_reactive", "periodic_reactive"),
                ("event_predictive", "periodic_predictive"), ("event_predictive", "event_reactive"),
                ("event_joint", "event_predictive")):
                a, b = case["policies"][candidate]["metrics"], case["policies"][baseline]["metrics"]
                case["comparisons"][candidate+"__vs__"+baseline] = ({"status": "unknown"} if a is None or b is None else
                    {**compare(a, b, sorted(j["business_bag_id"] for j in data["jobs"])), "cost_delta": a["cost"]-b["cost"]})
        receipt["status"] = ("executed_comparison_not_research_gate" if all(row["status"] == "verified_complete_execution"
            for c in receipt["cases"].values() for row in c["policies"].values()) else "incomplete_or_failed_comparison")
    except Exception:
        receipt["status"] = "failed_preparation"
        receipt["exception"] = traceback.format_exc()
    receipt["source_after"] = {str(p): digest(p) for p in paths}
    receipt["source_changed"] = [p for p in before if before[p] != receipt["source_after"][p]]
    if receipt["source_changed"]:
        receipt["status"] = "source_changed_unfrozen_execution"
    write_json(args.output/"receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "source_changed": receipt["source_changed"],
        "cases": {name: {p: {k: row.get(k) for k in ("status", "forecast_final_status", "wall_seconds")}
            for p, row in case["policies"].items()} for name, case in receipt["cases"].items()}}))
    return int(receipt["status"] != "executed_comparison_not_research_gate" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())

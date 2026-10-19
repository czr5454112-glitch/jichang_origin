"""Run actual R1/R2 public protocol factors with complete native ledgers."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

from .finite_reference import outcome_cost, service_dominates
from .native_host import audit_result, load_native, tiny_cycle
from .original_workload import write_json
from .protocol_control import complete_protocol_route, run_protocol_control
from .validate_known_service_control import known_service_input


def scenarios():
    base = tiny_cycle(); base["transfers"] = []
    for job in base["jobs"]:
        job["allow_suffix_reroute"] = True
    fault_specs = [
        ("ordinary", {}), ("lost_ack", {"drop_ack_packets": 1}),
        ("duplicate_ack", {"duplicate_acks": True, "duplicate_ack_delay": .5}),
        ("source_unavailable", {"owner_outages": [{"owner": "B", "start": .2, "end": 12.}]}),
        ("receiver_unavailable", {"owner_outages": [{"owner": "A", "start": 9., "end": 12.}]}),
    ]
    cases = []
    for name, changes in fault_specs:
        data = copy.deepcopy(base)
        data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .02, **changes}
        cases.append((name, data, ["A", "B"]))
    refused = copy.deepcopy(cases[0][1])
    next(n for n in refused["node_contracts"] if n["node"] == 0)["allow_receive"] = False
    cases.append(("receiver_refuses", refused, ["A", "B"]))
    known = known_service_input()
    known["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .02, "drop_ack_packets": 1}
    # Independent authorized-routing research factor, shared by every policy;
    # does not alter the frozen known_service campaign or its old conclusions.
    for job in known["jobs"]:
        job["allow_suffix_reroute"] = True
    known["model_scope"] += "; common explicit suffix permission and native ACK-loss factor"
    cases.append(("known_service_ack_loss", known, ["A", "B", "C"]))
    return cases


POLICIES = {
    "r1_only": {"routes": True, "forecasts": True, "prebalance": False, "predictive": False},
    "reactive_r2": {"routes": False, "forecasts": False, "prebalance": True, "predictive": False},
    "predictive_r2": {"routes": False, "forecasts": True, "prebalance": True, "predictive": True},
    "joint_r1_r2": {"routes": True, "forecasts": True, "prebalance": True, "predictive": True},
}


def replay_input(data, calls):
    replay = copy.deepcopy(data)
    requests = {}
    for call in calls:
        if call["kind"] != "transfer" or call["retry"] or call["reply"].get("status") != "pending":
            continue
        payload = copy.deepcopy(call["request"])
        payload["issued_at"] = call["at"]
        assert payload["request_id"] not in requests
        requests[payload["request_id"]] = payload
    replay["transfers"] = list(requests.values())
    return replay


def gz(path, value):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, allow_nan=False)


def snapshot():
    here = Path(__file__).parent
    names = [__file__, here/"protocol_control.py", here/"analytic_control.py", here/"regional_control.py",
             here/"native_host.py", here/"finite_reference.py", here/"validate_known_service_control.py",
             here/"validate_coupled_control.py"]
    return {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    before = snapshot()
    receipt = {"schema": "g31.protocol_control_campaign.v1", "status": "running", "cases": [],
               "source_before": before, "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
               "scope": "synthetic authorized R1/R2 factors; common native physical and communication contract within each factor",
               "complete_100ms_requirement_certified": False, "novelty": "engineering integration and strong analytic baselines"}
    fixed = scenarios()
    write_json(args.output/"protocol.json", {"horizon": 50., "start": .11, "control_period": .5,
        "command_delay": .01, "publication_delay": .02, "retry_period": .5, "policies": POLICIES,
        "cases": [n for n, _, _ in fixed], "selection": "declared before native execution; all outcomes retained"})
    write_json(args.output/"receipt.json", receipt)
    started = time.perf_counter()
    try:
        native = load_native(args.binary)
        for name, data, owners in fixed:
            folder = args.output/name; folder.mkdir()
            write_json(folder/"input.json", data)
            case = {"name": name, "policies": {}}
            for policy, options in POLICIES.items():
                target = folder/policy; target.mkdir()
                session = native.NativeSession(data); session.advance_to(.11)
                run = run_protocol_control(session, owners, horizon=50., **options)
                gz(target/"run.json.gz", run)
                assert run["status"] == "reached", (name, policy, run["status"])
                replay = replay_input(data, run["client_calls"])
                write_json(target/"audit_input.json", replay)
                audit = audit_result(replay, run["result"])
                assert audit["status"] == "passed", audit
                write_json(target/"audit.json", audit)
                metrics = outcome_cost(run["result"], data["jobs"], 50.)
                calls = run["client_calls"]
                ack_views = {owner: session.observe_protocol(owner) for owner in owners}
                gz(target/"delivered_views.json.gz", ack_views)
                case["policies"][policy] = {"status": "reached", "metrics": metrics, "audit": audit,
                    "requests_by_kind": {kind: sum(c["kind"] == kind and not c["retry"] for c in calls)
                        for kind in ("route", "transfer", "demand", "service_forecast", "withdraw_service_forecast")},
                    "retry_calls": sum(c["retry"] for c in calls),
                    "completed": sum(j["status"] == "completed" for j in run["result"]["jobs"]),
                    "offered": len(data["jobs"]), "physical_transfers": len(run["result"]["transfers"]),
                    "offline_final_state_sha256": session.offline_state_sha256()}
                assert case["policies"][policy]["requests_by_kind"]["demand"] > 0
            baseline = case["policies"]["reactive_r2"]["metrics"]
            for row in case["policies"].values():
                row["paired_service_vs_reactive_r2"] = service_dominates(row["metrics"], baseline)
            receipt["cases"].append(case)
            write_json(args.output/"receipt.json", receipt)
        # Complete single-request timings retain refusal/unknown and all
        # intervening physical work. They cannot certify loaded whole-day SLA.
        complete = []
        for name, changes, delay, window in [
            ("allowed", {}, .01, 1.), ("stale", {}, .2, 1.),
            ("lost_ack", {"drop_ack_packets": 1}, .01, 1.),
            ("no_ack_within_window", {"drop_ack_packets": 100}, .01, .3),
            ("source_unavailable", {"owner_outages": [{"owner": "A", "start": .1, "end": .5}]}, .01, 1.),
        ]:
            data = copy.deepcopy(fixed[0][1]); data["owner_protocol"].update(changes)
            session = native.NativeSession(data); session.advance_to(.11)
            measured = complete_protocol_route(session, "A", "T0", "live:1:A:full-query", command_delay=delay,
                                               confirmation_window=window)
            complete.append({"name": name, **measured})
        write_json(args.output/"complete_route_requests.json", complete)
        receipt["complete_route_sample_count"] = len(complete)
        receipt["complete_route_sample_max_ms"] = max(r["compute_wall_ms"] for r in complete)
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"; receipt["exception"] = traceback.format_exc()
    receipt["source_after"] = snapshot()
    receipt["source_changed"] = [p for p in before if before[p] != receipt["source_after"][p]]
    receipt["wall_seconds"] = time.perf_counter()-started
    write_json(args.output/"receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "source_changed", "wall_seconds", "exception") if k in receipt}))
    return int(receipt["status"] != "passed" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())

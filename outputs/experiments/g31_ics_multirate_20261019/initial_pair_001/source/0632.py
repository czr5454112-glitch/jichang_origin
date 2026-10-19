"""R1 on-demand integration and native finite route reference, with raw receipts.

This campaign certifies only the declared synthetic engineering contracts. Its
Storage slack example deliberately has no business improvement to learn.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
import traceback

from .finite_reference import Intervention, enumerate_interventions, headroom, outcome_cost
from .native_host import audit_result, load_native, tiny_cycle
from .regional_control import complete_on_demand, decode_route


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    native = load_native(args.binary)
    files = [Path(__file__), Path(__file__).with_name("regional_control.py"),
             Path(__file__).with_name("finite_reference.py"), Path(__file__).with_name("native_host.py")]
    snapshot = lambda: {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    receipt = {"schema": "g31.regional_native_campaign.v1", "status": "running", "cases": [],
               "source_before": snapshot(), "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
               "scope": "synthetic R1 integration and finite offline reference; not research gain or full 100ms validation"}
    start = time.perf_counter()
    base = tiny_cycle(); base["transfers"] = []; base["jobs"][0]["allow_suffix_reroute"] = True
    scenarios = [("asynchronous_nonperiodic", base, .11, .01, 5., "allowed"),
                 ("already_executed_prefix", base, 1.16, .01, 5., "allowed"),
                 ("stale_computation", base, .11, .2, 5., "stale_executed_prefix"),
                 ("expired_message", base, .11, .01, .001, "request_expired")]
    denied = copy.deepcopy(base); denied["jobs"][0]["allow_suffix_reroute"] = False
    scenarios.append(("permission_refusal", denied, .11, .01, 5., "route:service_obligation_disallows_reroute"))
    fault = copy.deepcopy(base); fault["faults"] = [{"from": 0, "to": 1, "start": 0., "end": 20., "message_delay": .03}]
    scenarios.append(("delivered_fault_detour", fault, .11, .01, 5., "allowed"))
    try:
        for name, data, at, delay, lease, expected in scenarios:
            folder = args.output / name; folder.mkdir()
            write(folder / "input.json", data)
            session = native.NativeSession(data); session.advance_to(at)
            observation = session.observe("A"); write(folder / "observation.json", observation)
            baseline = session.fork().result_at(30)
            measured = complete_on_demand(session, "A", "T0", name,
                                          logical_compute_delay=delay, lease_seconds=lease)
            request = measured["submission"]
            result = session.result_at(30)
            delivered = session.observe("A")["route_requests"]
            final = delivered[-1] if delivered else request["response"]
            write(folder / "request.json", request); write(folder / "final_response.json", final)
            write(folder / "complete_compute_measurement.json", measured)
            write(folder / "result.json", result); write(folder / "baseline_result.json", baseline)
            audits = {"candidate": audit_result(data, result), "baseline": audit_result(data, baseline)}
            write(folder / "audits.json", audits)
            assert final["reason"] == expected, (name, final)
            if name == "delivered_fault_detour":
                assert decode_route(request["encoded_route"]).replaceable_suffix == (0, 6, 2)
                assert next(r for r in result["receipts"] if r["event"] == "EDGE_ENTER")["to"] == 6
            if name == "already_executed_prefix":
                assert decode_route(request["encoded_route"]).committed_prefix == (0, 1)
            receipt["cases"].append({"name": name, "response": final,
                                     "compute_wall_ms": measured["compute_wall_ms"],
                                     "compute_cpu_ms": measured["compute_cpu_ms"],
                                     "meets_measured_100ms": measured["meets_measured_100ms"],
                                     "cost": outcome_cost(result, data["jobs"], 30),
                                     "baseline_cost": outcome_cost(baseline, data["jobs"], 30)})
        # Compare actual alternative paths at one real boundary. Both reach
        # Storage before its fixed release, so raw movement differs but the
        # release slack absorbs the business-time difference.
        session = native.NativeSession(base); session.advance_to(.11)
        visible = session.observe("A"); tray = visible["trays"][0]
        actions = [Intervention("WAIT", "wait")]
        for next_node in (1, 6):
            request = {"request_id": f"suffix-{next_node}", "owner_id": "A", "business_bag_id": "B1", "tray_id": "T0",
                       "from": 0, "next": next_node, "expected_generation": tray["generation"],
                       "expected_traversal": tray["traversal_id"], "expiry": 2., "message_delay": .01}
            actions.append(Intervention(f"route-{next_node}", "route", request))
        reference = enumerate_interventions(session, actions, horizon=30., job_contracts=base["jobs"],
                                             baseline_action_id="route-1", validate=lambda r, a: audit_result(base, r))
        write(args.output / "slack_absorption_reference.json", reference)
        comparison = headroom(reference, [a.action_id for a in actions], "route-1", "route-1")
        write(args.output / "headroom.json", comparison)
        assert reference["optimality"] == "optimal_in_enumerated_domain"
        assert reference["distinct_verified_physical_outcomes"] == 2
        assert comparison["reference_headroom"] == 0
        receipt["reference"] = {k: v for k, v in reference.items() if k != "rows"}
        receipt["headroom"] = comparison
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"; receipt["traceback"] = traceback.format_exc()
    finally:
        receipt["source_after"] = snapshot()
        receipt["source_changed"] = [p for p, h in receipt["source_before"].items() if receipt["source_after"][p] != h]
        if receipt["source_changed"]:
            receipt["status"] = "source_changed_development_only"
        receipt["wall_seconds"] = time.perf_counter() - start
        write(args.output / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "headroom", "traceback") if k in receipt}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

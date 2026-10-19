"""A native R1 x R2 causal probe, including service regressions if they occur.

The alternate suffix is a predeclared legal causal intervention, not a claimed
optimal regional algorithm. Both transfer policies are actual same-information
controllers. This synthetic probe cannot establish main-method innovation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import traceback

from .analytic_control import run_online_matching
from .finite_reference import outcome_cost, service_dominates
from .native_host import audit_result, load_native, prepare_input
from .regional_control import RoutePacket, decode_route, encode_route
from .validate_analytic_control import replay_input, write


def coupled_input(source_min_stock: int = 1):
    edges = [(0, 1, 1., 1.), (1, 3, 4., 1.), (0, 2, 1.3, 1.), (2, 3, 4., 1.),
             (3, 6, .4, 1.), (6, 1, .4, 1.), (1, 4, .4, 1.), (4, 5, 1., 1.), (5, 0, 1., 1.)]
    nodes = [{"node": n, "zone": "A" if n == 0 else "C" if n in (4, 5) else "B",
              "capacity": 2 if n == 0 else 1} for n in range(7)]
    nodes[0]["export_min_stock"] = source_min_stock
    return prepare_input({"schema": "g31.circulation.input.v1",
        "model_scope": "synthetic declared coupled shared-junction causal probe; not an original airport map",
        "node_records": [(n, 1, .05, n, 0, [v for u, v, _, _ in edges if u == n]) for n in range(7)],
        "edge_records": edges, "node_contracts": nodes,
        "edge_contracts": [{"from": u, "to": v, "capacity": 1, "entry_headway": .2} for u, v, _, _ in edges],
        "trays": [{"tray_id": "T0", "node": 0}, {"tray_id": "T1", "node": 0}],
        "jobs": [{"business_bag_id": name, "origin": origin, "destination": destination,
                  "arrival": arrival, "deadline": 40, "load_seconds": .1, "unload_seconds": .3,
                  "hold_seconds": .2, "protected_service": True, "allow_suffix_reroute": True}
                 for name, origin, destination, arrival in [("B1", 0, 3, 0), ("B2", 0, 3, 6.2), ("B3", 4, 5, .5)]],
        "transfers": [], "faults": [], "options": {"max_simulation_time": 50}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-min-stock", type=int, default=1)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    data = coupled_input(args.source_min_stock)
    write(args.output / "input.json", data)
    native = load_native(args.binary)
    paths = [Path(__file__), Path(__file__).with_name("analytic_control.py"),
             Path(__file__).with_name("regional_control.py"), Path(__file__).with_name("finite_reference.py")]
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    receipt = {"status": "running", "schema": "g31.coupled_causal_probe.v1", "cases": {},
               "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(), "source_before": sources,
               "scope": "predeclared synthetic causal intervention; same information and physical contract; all negatives retained"}
    write(args.output / "receipt.json", receipt)
    try:
        for alternate in (False, True):
            for predictive in (False, True):
                key = f"{'alternate' if alternate else 'S4'}_{'predictive' if predictive else 'reactive'}"
                folder = args.output / key
                folder.mkdir()
                session = native.NativeSession(data)
                session.advance_to(.11)
                route_response = None
                if alternate:
                    observation = session.observe("A")
                    tray = next(t for t in observation["trays"] if t["business_bag_id"] == "B1")
                    packet = RoutePacket("g31.route_intent.v1", "B1", tray["tray_id"], "A", tray["generation"],
                        tray["traversal_id"], "storage_out_or_direct", 3, (0,), (0, 2, 3), observation["now"])
                    decoded = decode_route(encode_route(packet))
                    request = {"request_id": "causal-B1-alternate", "owner_id": decoded.owner_id,
                        "business_bag_id": decoded.business_bag_id, "tray_id": decoded.tray_id,
                        "from": decoded.replaceable_suffix[0], "next": decoded.replaceable_suffix[1],
                        "expected_generation": decoded.generation, "expected_traversal": decoded.traversal_id,
                        "expiry": 1, "message_delay": 0}
                    route_response = session.submit_route_intent(request)
                    write(folder / "route_request.json", {"packet": encode_route(packet), "request": request,
                                                           "submission_reply": route_response})
                run = run_online_matching(session, ["A", "B", "C"], horizon=40, predictive=predictive,
                                          message_delay=1., demand_delay=.2)
                write(folder / "raw.json", run)
                if run["status"] != "reached":
                    raise RuntimeError(key + ":native_event_budget_exhausted")
                final_routes = session.observe("A")["route_requests"]
                write(folder / "route_resolution.json", final_routes)
                if alternate:
                    assert final_routes[0]["status"] == "updated", final_routes
                replay = replay_input(data, run["submitted"])
                write(folder / "replay_input.json", replay)
                audit = audit_result(replay, run["result"])
                write(folder / "audit.json", audit)
                value = outcome_cost(run["result"], data["jobs"], 40)
                write(folder / "metrics.json", value)
                first_hops = {}
                for event in run["result"]["receipts"]:
                    if event["event"] == "EDGE_ENTER" and event["business_bag_id"]:
                        first_hops.setdefault(event["business_bag_id"], event["to"])
                receipt["cases"][key] = {"metrics": value, "first_hops": first_hops,
                    "requests": run["submitted"], "route_resolution": final_routes,
                    "release_events": [r for r in run["result"]["receipts"] if r["event"] == "HOLD_COMPLETE"]}
                write(args.output / "receipt.json", receipt)
        rows = receipt["cases"]
        # The experiment is successful when the intended causal effects are
        # actually identified; service deterioration is retained, not asserted away.
        route_effect = rows["S4_predictive"]["first_hops"]["B1"] != rows["alternate_predictive"]["first_hops"]["B1"]
        transfer_effect = rows["S4_reactive"]["first_hops"]["B2"] != rows["S4_predictive"]["first_hops"]["B2"]
        receipt["causal_observation"] = {"route_intent_changed_B1_physical_first_hop": route_effect,
            "transfer_policy_changed_B2_physical_first_hop": transfer_effect,
            "predictive_service_preserved_under_S4": service_dominates(rows["S4_predictive"]["metrics"], rows["S4_reactive"]["metrics"]),
            "alternate_service_preserved_under_predictive": service_dominates(rows["alternate_predictive"]["metrics"], rows["S4_predictive"]["metrics"]),
            "main_method_novelty": "not_established"}
        receipt["status"] = "passed" if route_effect and transfer_effect else "causal_effect_not_identified"
    except Exception:
        receipt["status"] = "failed"
        receipt["traceback"] = traceback.format_exc()
        raise
    finally:
        receipt["source_after"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        receipt["source_changed"] = [p for p in sources if sources[p] != receipt["source_after"][p]]
        write(args.output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "causal_observation": receipt["causal_observation"]}))


if __name__ == "__main__":
    main()

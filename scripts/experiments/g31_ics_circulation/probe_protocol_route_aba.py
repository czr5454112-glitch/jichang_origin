"""Actual native route A/B/A lifecycle probe with unchanged fault knowledge.

The second tray physically enters and leaves a local branch. Its occupancy
changes the public A* preference while the main tray remains at one stage.
Historical successful ACKs must not stand for the latest installed intent.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

from . import protocol_control
from .native_host import audit_result, load_native, prepare_input, tiny_cycle
from .original_workload import write_json
from .regional_control import public_astar


def scene():
    data = tiny_cycle()
    data["transfers"] = []
    data["jobs"] = data["jobs"][:1]
    data["jobs"][0]["allow_suffix_reroute"] = True
    edges = [(u, v, 1.02 if (u, v) == (0, 6) else length, speed)
             for u, v, length, speed in data["edge_records"]]
    edges += [(7, 1, .1, 1.), (1, 8, .2, 1.)]
    data["edge_records"] = edges
    data["node_records"] = [
        (n, 3 if n == 2 else 1, 10. if n == 0 else .5 if n in (1, 6) else .05,
         n, 0, [v for u, v, _, _ in edges if u == n]) for n in range(9)]
    data["node_contracts"] += [{"node": n, "zone": "A", "capacity": 1} for n in (7, 8)]
    data["edge_contracts"] = [{"from": u, "to": v, "capacity": 1, "entry_headway": .2}
                              for u, v, *_ in edges]
    data["trays"].append({"tray_id": "T_OCC", "node": 7})
    for bag, origin, destination, arrival in [("OCC_ENTER", 7, 1, .2), ("OCC_LEAVE", 1, 8, 1.)]:
        data["jobs"].append({"business_bag_id": bag, "origin": origin, "destination": destination,
            "arrival": arrival, "deadline": 40., "load_seconds": .01, "unload_seconds": .05,
            "hold_seconds": .05, "protected_service": True, "allow_suffix_reroute": True})
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .02}
    data["model_scope"] = "native same-stage route A/B/A from actual local occupancy; no fault changes"
    return prepare_input(data)


class CapturePublic:
    def __init__(self, session):
        self.session = session
        self.observations = []

    def __getattr__(self, name):
        return getattr(self.session, name)

    def observe_protocol_control(self, owner):
        observation = self.session.observe_protocol_control(owner)
        if owner == "A":
            self.observations.append(copy.deepcopy(observation))
        return observation


def execute(module, native, output):
    data = scene()
    write_json(output / "input.json", data)
    raw = native.NativeSession(data)
    raw.advance_to(.11)
    captured = CapturePublic(raw)
    run = module.run_protocol_control(captured, ["A", "B"], horizon=2.6,
                                     forecasts=False, prebalance=False, lease_seconds=5.)
    audit = audit_result(data, run["result"])
    calls = [c for c in run["client_calls"] if c["kind"] == "route" and not c["retry"]
             and c["request"]["tray_id"] == "T0"]
    ids = {c["request"]["request_id"] for c in calls}
    acks = [a for a in raw.observe_protocol("A")["delivered_command_acks"] if a["request_id"] in ids]
    observations = []
    for observed in captured.observations:
        tray = next(t for t in observed["trays"] if t["tray_id"] == "T0")
        path = public_astar(observed, tray["node"], 2)
        observations.append({"at": observed["now"], "path": list(path),
            "stage_identity": [tray[k] for k in ("node", "generation", "traversal_id", "business_bag_id")],
            "known_faults": observed["known_faults"],
            "branch_occupancy": {str(n["node"]): n.get("occupancy") for n in observed["node_contracts"]
                                 if n["node"] in (1, 6)}})
    transitions = []
    for observed in observations:
        nxt = observed["path"][1]
        if not transitions or transitions[-1]["next"] != nxt:
            transitions.append({"at": observed["at"], "next": nxt})
    fixture_valid = (run["status"] == "reached" and audit["status"] == "passed"
        and [r["next"] for r in transitions] == [1, 6, 1]
        and len({tuple(o["stage_identity"]) for o in observations}) == 1
        and all(o["known_faults"] == [] for o in observations))
    first = next((c for c in calls if c["request"]["next"] == 1), None)
    b = next((c for c in calls if c["request"]["next"] == 6), None)
    first_updated = first is not None and any(a["request_id"] == first["request"]["request_id"]
        and a["status"] == "updated" for a in acks)
    b_updated = b is not None and any(a["request_id"] == b["request"]["request_id"]
        and a["status"] == "updated" for a in acks)
    last_a = [c for c in calls if c["request"]["next"] == 1 and b and c["at"] > b["at"]]
    fresh_a_updated = any(a["request_id"] in {c["request"]["request_id"] for c in last_a}
        and a["status"] == "updated" for a in acks)
    old_lease_still_live = bool(first and len(transitions) == 3
        and first["request"]["expiry"] > transitions[2]["at"])
    receipt = {"name": "native_same_stage_route_aba", "fixture_valid": fixture_valid,
        "transitions": transitions, "first_a_updated": first_updated, "b_updated": b_updated,
        "first_a_lease_live_on_return": old_lease_still_live, "fresh_a_updated_on_return": fresh_a_updated,
        "fixed": fixture_valid and first_updated and b_updated and old_lease_still_live and fresh_a_updated,
        "route_calls": [{"at": c["at"], **c["request"]} for c in calls], "route_acks": acks,
        "audit": audit, "public_observations": observations}
    with gzip.open(output / "raw.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"run": run, "public_observations": captured.observations}, stream, allow_nan=False)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controller-source", type=Path)
    parser.add_argument("--require-fixed", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    module = protocol_control
    source = args.controller_source or Path(protocol_control.__file__)
    if args.controller_source:
        name = "scripts.experiments.g31_ics_circulation._frozen_route_aba_controller"
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt = {"schema": "g31.protocol_route_aba_probe.v1", "status": "running",
        "controller_source": str(source), "source_before": before,
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest()}
    try:
        receipt["case"] = execute(module, load_native(args.binary), args.output)
        receipt["status"] = "passed" if receipt["case"]["fixed"] else "failed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["source_after"] = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt["source_changed"] = [] if receipt["source_after"] == before else [str(source)]
    write_json(args.output / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "source_changed", "exception") if k in receipt}))
    return int(bool(receipt["source_changed"]) or (args.require_fixed and receipt["status"] != "passed"))


if __name__ == "__main__":
    raise SystemExit(main())

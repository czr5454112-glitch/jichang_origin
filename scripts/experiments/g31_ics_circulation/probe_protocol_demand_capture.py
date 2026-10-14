"""Native delayed demand capture can differ from its client's cached signature.

Y arrives between controller ticks and waits for an actually occupied tray.
The delayed native publication captures Y before the tray becomes available;
Y is then physically loaded before the next tick. The queue is empty at both
client sampling ticks, but the receiver must eventually receive a correction.
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


def scene():
    data = tiny_cycle()
    data["transfers"] = []
    data["trays"] = [{"tray_id": "T0", "node": 5}]
    data["edge_records"] = [(u, v, .1 if (u, v) == (5, 0) else length, speed)
                            for u, v, length, speed in data["edge_records"]]
    y = copy.deepcopy(data["jobs"][0])
    y.update(business_bag_id="Y", arrival=.1, load_seconds=10.)
    data["jobs"] = [{"business_bag_id": "P", "origin": 5, "destination": 0,
        "arrival": 0., "deadline": 40., "load_seconds": .01, "unload_seconds": .05,
        "hold_seconds": .1, "protected_service": True}, y]
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .02}
    data["model_scope"] = "native delayed demand capture of transient real waiting queue; no client future input"
    return prepare_input(data)


class CapturePublic:
    def __init__(self, session):
        self.session = session
        self.signatures = []
        self.observations = []

    def __getattr__(self, name):
        return getattr(self.session, name)

    def protocol_demand_signature(self, owner):
        value = self.session.protocol_demand_signature(owner)
        self.signatures.append({"at": self.session.physical_time, "owner": owner, "signature": copy.deepcopy(value)})
        return value

    def observe_protocol_control(self, owner):
        value = self.session.observe_protocol_control(owner)
        if owner == "B":
            self.observations.append(copy.deepcopy(value))
        return value


def execute(module, native, output):
    data = scene()
    write_json(output / "input.json", data)
    raw = native.NativeSession(data)
    raw.advance_to(.02)
    captured = CapturePublic(raw)
    run = module.run_protocol_control(captured, ["A", "B"], horizon=2.9, control_period=1.,
        command_delay=.2, publication_delay=.02, routes=False, forecasts=False, prebalance=False)
    final_observation = raw.observe_protocol("B")
    audit = audit_result(data, run["result"])
    loads = [r for r in run["result"]["receipts"] if r["event"] == "LOAD_START" and r["business_bag_id"] == "Y"]
    a_signatures = [s for s in captured.signatures if s["owner"] == "A"]
    messages = [m for o in captured.observations for m in o["delivered_messages"]
                if m["kind"] == "demand" and m["source_owner"] == "A"]
    # Compact observations intentionally omit message job identities; the
    # exact count remains a lawful receiver observation.
    transient = [m for m in messages if m.get("snapshot_waiting_count", len(m["jobs"])) > 0]
    latest = next((m for m in final_observation["delivered_messages"]
                   if m["kind"] == "demand" and m["source_owner"] == "A"), None)
    source_now = raw.protocol_demand_signature("A")
    fixture_valid = (run["status"] == "reached" and audit["status"] == "passed" and len(loads) == 1
        and bool(transient) and all(s["signature"]["waiting_count"] == 0 for s in a_signatures)
        and source_now["waiting_count"] == 0 and all(m["observed_at"] < loads[0]["time"] for m in transient))
    corrected = bool(latest and not latest["jobs"] and loads and latest["observed_at"] > loads[0]["time"])
    result = {"name": "delayed_capture_transient_queue", "fixture_valid": fixture_valid,
        "fixed": fixture_valid and corrected, "receiver_corrected_after_real_load": corrected,
        "source_sampled_signatures": a_signatures, "actual_y_load": loads,
        "transient_receiver_messages": transient, "final_receiver_message": latest,
        "final_source_signature": source_now,
        "demand_calls": [c for c in run["client_calls"] if c["kind"] == "demand"], "audit": audit}
    with gzip.open(output / "raw.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"run": run, "receiver_observations": captured.observations,
                   "final_receiver_observation": final_observation}, stream, allow_nan=False)
    return result


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
        name = "scripts.experiments.g31_ics_circulation._frozen_demand_capture_controller"
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt = {"schema": "g31.protocol_demand_capture_probe.v1", "status": "running",
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

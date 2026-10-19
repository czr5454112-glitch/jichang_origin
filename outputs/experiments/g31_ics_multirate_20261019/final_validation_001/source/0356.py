"""Actual before/after probes for budget and same-stage controller lifecycles."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

from . import protocol_control
from .native_host import load_native, prepare_input, tiny_cycle
from .original_workload import write_json


class BudgetGuard:
    def __init__(self, session):
        self.session = session
        self.cut_hash = None
        self.extra_result_calls = 0

    def __getattr__(self, name):
        return getattr(self.session, name)

    def advance_to(self, *args, **kwargs):
        reply = self.session.advance_to(*args, **kwargs)
        if reply["status"] == "budget_exhausted":
            self.cut_hash = self.session.offline_state_sha256()
        return reply

    def result_at(self, *args, **kwargs):
        if self.cut_hash is not None:
            self.extra_result_calls += 1
        return self.session.result_at(*args, **kwargs)


def base():
    data = tiny_cycle(); data["transfers"] = []
    data["jobs"][0]["allow_suffix_reroute"] = True
    data["jobs"][1]["arrival"] = 40.
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .02}
    return data


def execute(module, native, output):
    rows = []
    data = base(); raw = native.NativeSession(data); raw.advance_to(.11)
    guarded = BudgetGuard(raw)
    cut = module.run_protocol_control(guarded, ["A", "B"], horizon=3., event_budget=1)
    rows.append({"name": "budget_cut", "fixed": guarded.cut_hash is not None and
                 guarded.cut_hash == raw.offline_state_sha256() and guarded.extra_result_calls == 0,
                 "status": cut["status"], "cut_state": guarded.cut_hash,
                 "returned_state": raw.offline_state_sha256(), "extra_result_calls": guarded.extra_result_calls})
    write_json(output/"budget_probe.json", rows[-1])

    data = base(); data["jobs"][0]["load_seconds"] = 20.
    data["faults"] = [{"from": 0, "to": v, "start": 1., "end": 2.} for v in (1, 6)]
    session = native.NativeSession(data); session.advance_to(.11)
    run = module.run_protocol_control(session, ["A", "B"], horizon=3., routes=False, prebalance=False)
    calls = [c for c in run["client_calls"] if c["kind"] == "service_forecast" and not c["retry"]]
    withdrawals = [c for c in run["client_calls"] if c["kind"] == "withdraw_service_forecast" and not c["retry"]]
    acks = session.observe_protocol("A")["delivered_command_acks"]
    late = {c["request"]["request_id"] for c in calls if c["at"] >= 2.}
    rows.append({"name": "same_stage_forecast_recovery", "fixed": bool(late) and
                 any(a["request_id"] in late and a["status"] == "delivered" for a in acks),
                 "publication_times": [c["at"] for c in calls], "withdrawal_times": [c["at"] for c in withdrawals],
                 "late_publication_ids": sorted(late)})
    write_json(output/"forecast_input.json", data)
    with gzip.open(output/"forecast_run.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"run": run, "acks": acks}, f)

    data = base()
    data["node_records"] = [(n, kind, 10. if n == 0 else service, x, y, successors)
        for n, kind, service, x, y, successors in data["node_records"]]
    data["faults"] = [{"from": 0, "to": 1, "start": .15, "end": 1.}]
    data = prepare_input(data)
    session = native.NativeSession(data); session.advance_to(.11)
    run = module.run_protocol_control(session, ["A", "B"], horizon=3., command_delay=.2,
                                      forecasts=False, prebalance=False)
    routes = [c for c in run["client_calls"] if c["kind"] == "route" and not c["retry"]]
    acks = session.observe_protocol("A")["delivered_command_acks"]
    alternatives = {c["request"]["request_id"] for c in routes if c["request"]["next"] == 6}
    rows.append({"name": "same_stage_route_public_path_change", "fixed": bool(alternatives) and
                 any(a["request_id"] in alternatives and a["status"] == "updated" for a in acks),
                 "routes": [{"at": c["at"], "next": c["request"]["next"], "reply": c["reply"]} for c in routes]})
    write_json(output/"route_input.json", data)
    with gzip.open(output/"route_run.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"run": run, "acks": acks}, f)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controller-source", type=Path)
    parser.add_argument("--require-fixed", action="store_true")
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    module = protocol_control
    source = args.controller_source or Path(protocol_control.__file__)
    if args.controller_source:
        name = "scripts.experiments.g31_ics_circulation._frozen_protocol_controller_probe"
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module
        spec.loader.exec_module(module)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt = {"schema": "g31.protocol_controller_probes.v1", "status": "running",
               "controller_source": str(source), "source_before": before,
               "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest()}
    try:
        receipt["cases"] = execute(module, load_native(args.binary), args.output)
        receipt["status"] = "passed" if all(r["fixed"] for r in receipt["cases"]) else "failed"
    except Exception:
        receipt["status"] = "failed"; receipt["exception"] = traceback.format_exc()
    receipt["source_after"] = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt["source_changed"] = [] if receipt["source_after"] == before else [str(source)]
    write_json(args.output/"receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    return int(bool(receipt["source_changed"]) or (args.require_fixed and receipt["status"] != "passed"))


if __name__ == "__main__":
    raise SystemExit(main())

"""Native nextafter horizon and strict controller continuation probes."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import traceback

from . import protocol_control
from .native_host import load_native, tiny_cycle
from .original_workload import write_json


def scene():
    data = tiny_cycle()
    data["transfers"] = []
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": .02}
    return data


def execute(module, native, output):
    data = scene()
    write_json(output / "input.json", data)
    options = {"routes": False, "forecasts": False, "prebalance": False}
    boundary = math.nextafter(.61, -math.inf)
    split = native.NativeSession(data)
    split.advance_to(.11)
    result = {"requested_split_horizon": boundary, "next_control_tick": .11 + .5,
              "horizon_hex": boundary.hex(), "tick_hex": (.11 + .5).hex()}
    artifacts = {}
    try:
        prefix = module.run_protocol_control(split, ["A", "B"], horizon=boundary, **options)
        result["split_status"] = prefix["status"]
        result["physical_time_at_return"] = split.physical_time
        saved = split.checkpoint()
        parent_hash = split.offline_state_sha256()
        state = json.loads(json.dumps(prefix["controller_state"], allow_nan=False))
        before_state = copy.deepcopy(state)
        resumed_native = native.NativeSession(data)
        resumed_native.restore(saved)
        resumed = module.run_protocol_control(resumed_native, ["A", "B"], horizon=1.3, state=state, **options)
        full_native = native.NativeSession(data)
        full_native.advance_to(.11)
        full = module.run_protocol_control(full_native, ["A", "B"], horizon=1.3, **options)
        equality = {key: resumed["result"][key] == full["result"][key]
                    for key in ("jobs", "trays", "transfers", "receipts", "leg_identities")}
        equality.update(controller_state=resumed["controller_state"] == full["controller_state"],
            native_state=resumed_native.offline_state_sha256() == full_native.offline_state_sha256(),
            parent_unchanged=split.offline_state_sha256() == parent_hash,
            input_state_unchanged=state == before_state)
        result["continuation_equalities"] = equality
        artifacts.update(prefix=prefix, resumed=resumed, full=full)
        result["split_fixed"] = (prefix["status"] == resumed["status"] == full["status"] == "reached"
                                 and result["physical_time_at_return"] == boundary and all(equality.values()))
    except Exception as error:
        result.update(split_fixed=False, split_exception_type=type(error).__name__, split_exception=str(error),
                      physical_time_at_return=split.physical_time, split_exception_trace=traceback.format_exc())
    result["native_advanced_past_requested_horizon"] = result["physical_time_at_return"] > boundary

    past = native.NativeSession(data)
    past.advance_to(.11)
    before = past.offline_state_sha256()
    try:
        artifacts["past_horizon_run"] = module.run_protocol_control(past, ["A", "B"],
            horizon=math.nextafter(.11, -math.inf), **options)
        result["past_horizon_rejected"] = False
    except ValueError as error:
        result["past_horizon_rejected"] = True
        result["past_horizon_error"] = str(error)
    result["past_horizon_state_unchanged"] = past.offline_state_sha256() == before
    result["fixed"] = result["split_fixed"] and result["past_horizon_rejected"] and result["past_horizon_state_unchanged"]
    with gzip.open(output / "raw.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(artifacts, stream, allow_nan=False)
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
        name = "scripts.experiments.g31_ics_circulation._frozen_tick_boundary_controller"
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    receipt = {"schema": "g31.protocol_tick_boundary_probe.v1", "status": "running",
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

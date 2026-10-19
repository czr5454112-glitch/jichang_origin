"""Executed full/compact G31 controller equivalence; no new policy mechanism."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

from .analytic_control import run_online_matching
from .native_host import audit_result, load_native
from .validate_analytic_control import replay_input, scenarios, write
from .validate_known_service_control import known_service_input, prefix


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_gzip(path, value):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)


def compare(full, compact):
    assert full["status"] == compact["status"] == "reached"
    assert full["submitted"] == compact["submitted"]
    assert full["controller_state"] == compact["controller_state"]
    decisions = 0
    keys = ("intents", "supplies", "forecasts", "exact_waiting_count", "exact_demand_count",
            "clearing_pressure_without_available_source", "assignment_demand_count")
    for a, b in zip(full["control_records"], compact["control_records"], strict=True):
        assert a["owner_id"] == b["owner_id"] and a["replies"] == b["replies"]
        for da, db in zip([a["decision"]]+a["replans"], [b["decision"]]+b["replans"], strict=True):
            for key in keys:
                assert da[key] == db[key], (a["owner_id"], da["now"], key)
            decisions += 1
    fields = ("receipts", "jobs", "trays", "transfers", "population", "leg_identities")
    for field in fields:
        assert full["result"][field] == compact["result"][field], field
    return {"equal_decisions_including_residual": decisions, "physical_fields_equal": list(fields),
            "submitted_requests": len(full["submitted"]), "all_offered_jobs_retained": len(full["result"]["jobs"]),
            "status": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__), Path(__file__).with_name("analytic_control.py"),
             Path(__file__).with_name("validate_analytic_control.py"),
             Path(__file__).with_name("validate_known_service_control.py")]
    before = {str(p): _hash(p) for p in files}
    receipt = {"schema": "g31.compact_control_equivalence.v1", "status": "running", "cases": [],
               "source_before": before, "binary_sha256": _hash(args.binary),
               "scope": "same lawful information and exact equivalent FIFO assignment; synthetic mechanisms plus real native/controller continuation",
               "novelty": "engineering_optimization_only", "complete_100ms_requirement_certified": False}
    write(args.output/"receipt.json", receipt)
    started = time.perf_counter()
    try:
        native = load_native(args.binary)
        for name, (data, delay, demand_delay) in scenarios().items():
            for predictive in (False, True):
                case = name+("_predictive" if predictive else "_reactive")
                parent = native.NativeSession(data)
                before_parent = parent.offline_state_sha256()
                runs = [run_online_matching(parent.fork(), ["A", "B"], horizon=80., predictive=predictive,
                         message_delay=delay, demand_delay=demand_delay, compact_projection=compact)
                        for compact in (False, True)]
                _write_gzip(args.output/(case+".json.gz"), {"input": data, "full": runs[0], "compact": runs[1]})
                row = compare(*runs)
                assert parent.offline_state_sha256() == before_parent
                row.update(case=case, parent_unchanged=True,
                           audit=audit_result(replay_input(data, runs[1]["submitted"]), runs[1]["result"]))
                receipt["cases"].append(row)
                write(args.output/"receipt.json", receipt)
        data = known_service_input()
        parent, pre = prefix(native, data, predictive=True, windows=True)
        state = json.loads(json.dumps(pre["controller_state"]))
        runs = [run_online_matching(parent.fork(), ["A", "B", "C"], horizon=40., predictive=True,
                message_delay=1., demand_delay=.2, respect_service_forecasts=True,
                controller_state=copy.deepcopy(state), compact_projection=compact) for compact in (False, True)]
        _write_gzip(args.output/"forecast_json_continuation.json.gz", {"input": data, "prefix": pre,
                    "full": runs[0], "compact": runs[1]})
        row = compare(*runs)
        row.update(case="delivered_service_forecast_native_and_json_controller_forks", saved_controller_state=state)
        receipt["cases"].append(row)
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["source_changed"] = [str(p) for p in files if _hash(p) != before[str(p)]]
    receipt["wall_seconds"] = time.perf_counter()-started
    write(args.output/"receipt.json", receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return int(receipt["status"] != "passed" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())

"""Independent completion review, using real native branches and corrupting metadata only."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle, audit_result
from scripts.experiments.g31_ics_circulation.analytic_control import run_online_matching
from scripts.experiments.g31_ics_circulation.finite_reference import Intervention, enumerate_interventions

p = argparse.ArgumentParser()
p.add_argument("--binary", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
native = load_native(args.binary)
paths = [ROOT / "scripts/experiments/g31_ics_circulation/analytic_control.py",
         ROOT / "scripts/experiments/g31_ics_circulation/finite_reference.py"]
snapshot = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
receipt = {"schema": "g31.independent.completion_review.v1", "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
           "source_before": snapshot(), "cases": []}
actions = [Intervention("WAIT", "wait"), Intervention("other-wait", "wait")]
try:
    for horizon in (.1, 20):
        for wrapper in ("raw", "stripped", "envelope"):
            data = tiny_cycle(); data["transfers"] = []; data["options"]["max_events"] = 5
            audit_calls = []
            def continue_budget(branch, target):
                run = run_online_matching(branch, ["A", "B"], horizon=target, predictive=False, publish=False)
                if wrapper == "stripped":
                    run["result"].pop("control_continuation", None)
                return run if wrapper == "envelope" else run["result"]
            def validate(result, action):
                audit_calls.append(action.action_id)
                return audit_result(data, result)
            ref = enumerate_interventions(native.NativeSession(data), actions, horizon=horizon, job_contracts=data["jobs"],
                                          continuation=continue_budget, validate=validate)
            assert ref["optimality"] == "unknown" and not ref["exhaustive"] and ref["best_cost"] is None
            assert audit_calls == [] and all("metrics" not in row for row in ref["rows"])
            receipt["cases"].append({"case": f"native_budget_{horizon}_{wrapper}", "reference": ref, "audit_calls": audit_calls})

    variants = {
        "valid_complete_native": lambda r: r,
        "missing_horizon": lambda r: (r.pop("horizon"), r)[1],
        "short_horizon": lambda r: (r.update(horizon=.9), r)[1],
        "missing_physical_clock": lambda r: (r.pop("physical_clock"), r)[1],
        "nan_physical_clock": lambda r: (r.update(physical_clock=float("nan")), r)[1],
        "missing_advance": lambda r: (r.pop("advance"), r)[1],
        "null_advance": lambda r: (r.update(advance=None), r)[1],
        "short_advance_time": lambda r: (r["advance"].update(physical_time=.9), r)[1],
        "infinite_advance_time": lambda r: (r["advance"].update(physical_time=float("inf")), r)[1],
        "advance_budget": lambda r: (r["advance"].update(status="budget_exhausted"), r)[1],
        "missing_advance_status": lambda r: (r["advance"].pop("status"), r)[1],
        "false_native_complete": lambda r: (r["advance"].update(horizon_complete=False), r)[1],
        "missing_native_complete": lambda r: (r["advance"].pop("horizon_complete"), r)[1],
        "integer_native_complete": lambda r: (r["advance"].update(horizon_complete=1), r)[1],
        "result_budget": lambda r: (r.update(status="budget_exhausted"), r)[1],
        "controller_budget": lambda r: (r.update(control_continuation=dict(status="budget_exhausted", requested_horizon=1, physical_time=1)), r)[1],
        "controller_missing_horizon": lambda r: (r.update(control_continuation=dict(status="reached", physical_time=1)), r)[1],
        "controller_wrong_time": lambda r: (r.update(control_continuation=dict(status="reached", requested_horizon=1, physical_time=.9)), r)[1],
        "empty_controller": lambda r: (r.update(control_continuation={}), r)[1],
        "null_controller": lambda r: (r.update(control_continuation=None), r)[1],
        "envelope_budget": lambda r: dict(status="budget_exhausted", result=r),
        "envelope_missing_status": lambda r: dict(result=r),
        "envelope_null_status": lambda r: dict(status=None, result=r),
    }
    for name, alter in variants.items():
        data = tiny_cycle(); data["transfers"] = []
        audit_calls = []
        def validate(result, action):
            audit_calls.append(action.action_id)
            return audit_result(data, result)
        ref = enumerate_interventions(native.NativeSession(data), actions, horizon=1, job_contracts=data["jobs"],
                                      continuation=lambda branch, target: alter(branch.result_at(target)), validate=validate)
        receipt["cases"].append({"case": name, "optimality": ref["optimality"], "exhaustive": ref["exhaustive"],
                                 "audit_calls": audit_calls, "completion": [r.get("completion") for r in ref["rows"]]})
        if name == "valid_complete_native":
            assert ref["exhaustive"] and ref["optimality"] == "optimal_in_enumerated_domain" and len(audit_calls) == 2
        else:
            assert ref["optimality"] == "unknown" and not ref["exhaustive"] and ref["best_cost"] is None
            assert audit_calls == [] and all("metrics" not in row for row in ref["rows"])
    receipt["status"] = "passed"
except Exception as error:
    receipt["status"] = "failed";receipt["exception"] = repr(error)
    raise
finally:
    receipt["source_after"] = snapshot()
    receipt["source_changed"] = [p for p in receipt["source_before"] if receipt["source_before"][p] != receipt["source_after"][p]]
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps({"status": receipt["status"], "case_count": len(receipt["cases"]), "source_changed": receipt["source_changed"]}))

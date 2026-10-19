"""Independent saved-data audit; no model evaluation or native calls."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

FIELDS = ("initial_next", "departure", "first_return_delay", "reuse_next")
JOBS = {"loaded", "receiver", "reuse1", "reuse2", "blocker"}


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def key(action): return tuple(action[field] for field in FIELDS)


def times(row):
    values = row.get("completion", {})
    if row.get("status") != "conditional_prediction" or set(values) != JOBS: return None
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values.values()): return None
    return values


def audit(directory):
    directory = Path(directory); plan = json.loads((directory / "preregistered_protocol.json").read_text())
    checks, output = {}, []
    checks["all_archived_sources_match"] = all(digest(directory / "source" / Path(path).name) == wanted for path, wanted in plan["source_sha256"].items())
    for case in plan["cases"]:
        name = case["case_id"]; config = json.loads((directory / "inputs" / (name + ".json")).read_text())
        checks[name + ":config_hash"] = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() == case["configuration_sha256"]
        raw_path = directory / (name + ".json"); raw = json.loads(raw_path.read_text())
        lookup = {key(row["action"]): row["prediction"] for row in raw["cells"]}
        expected = {key(action) for action in case["domain"]["actions"]}
        checks[name + ":complete_unique_action_denominator"] = len(raw["cells"]) == 32 and set(lookup) == expected
        base = times(lookup[key(case["domain"]["incumbent"])])
        protected = lambda value: base is not None and value is not None and all(value[j] <= base[j] for j in JOBS)
        eligible = [(action, times(p)) for action, p in lookup.items() if protected(times(p))]
        score = lambda pair: (sum(pair[1].values()), pair[0])
        best = min(eligible, key=score, default=None)
        fixed = min((pair for pair in eligible if pair[0][0] == 1), key=score, default=None)
        checks[name + ":all_five_completions_known"] = all(times(row) is not None for row in lookup.values())
        checks[name + ":coverage_preserved"] = len(raw["assessment"]["coverage"]) == 32 and all(
            row["model_protected"] == (protected(times(lookup[key(row["action"])])) if times(lookup[key(row["action"])]) is not None and base is not None else None)
            for row in raw["assessment"]["coverage"])
        methods = []
        for method in raw["assessment"]["methods"]:
            label = name + ":" + method["method"]
            evaluated = [row for row in method["rows"] if row["evaluation_status"] == "evaluated"]
            checks[label + ":evaluation_budget"] = len(evaluated) == method["evaluations"] <= method["budget"] == 32
            checks[label + ":retained_denominator"] = len(method["rows"]) == 32 and {key(row["action"]) for row in method["rows"]} == expected
            checks[label + ":predictions_match_raw"] = all(row["prediction"] == lookup[key(row["action"])] for row in evaluated)
            selected = key(method["selected_action"]) if method["selected_action"] else None
            known = selected is not None and times(lookup[selected]) is not None and base is not None
            checks[label + ":selection_and_gain"] = known and selected in {key(row["action"]) for row in evaluated} and protected(times(lookup[selected])) and method["model_gain"] == sum(base.values()) - sum(times(lookup[selected]).values())
            methods.append({"method": method["method"], "selected_action": method["selected_action"], "gain_vs_incumbent": method["model_gain"],
                "matches_complete_model_reference": selected == best[0] if best else None})
        selected_times = best[1] if best else None
        no_later_key = (*best[0][:3], 3) if best else None
        no_later = times(lookup[no_later_key]) if no_later_key else None
        output.append({"case": {k: case[k] for k in ("case_id", "blocker_load", "receiver_load")},
            "raw_sha256": digest(raw_path), "conditional_cells": sum(times(p) is not None for p in lookup.values()),
            "protected_cells": len(eligible), "methods": methods,
            "best_finite_action": dict(zip(FIELDS, best[0])) if best else None,
            "best_finite_fixed_initial_action": dict(zip(FIELDS, fixed[0])) if fixed else None,
            "selected_minus_fixed_by_job": {j: selected_times[j] - fixed[1][j] for j in sorted(JOBS)} if selected_times and fixed else None,
            "fixed3_minus_selected_by_job": {j: no_later[j] - selected_times[j] for j in sorted(JOBS)} if no_later and selected_times else None,
            "fixed3_still_protected_vs_finite_fixed_initial": all(no_later[j] <= fixed[1][j] for j in JOBS) if no_later and fixed else None})
    checks["exact_six_cases_192_cells"] = len(output) == 6 and sum(row["conditional_cells"] for row in output) == 192
    return {"schema": "g31.lt2.independent_saved_occupancy_audit.v1", "status": "passed" if all(checks.values()) else "failed",
        "input_directory": str(directory.resolve()), "preregistration_sha256": digest(directory / "preregistered_protocol.json"),
        "checks": checks, "results": output, "native_calls": 0, "model_evaluations": 0,
        "limits": ["checks saved projections/source/configuration, not model physics accuracy", "no native or online business evidence"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    args.output.write_text(json.dumps(audit(args.input), indent=2, allow_nan=False), encoding="utf-8")

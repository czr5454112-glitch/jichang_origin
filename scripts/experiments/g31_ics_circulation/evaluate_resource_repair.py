"""Preregistered pure model-only comparator; native labels read after proposals."""
from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
import time
from . import public_resource_repair as repair
from . import research_native_public_joint as common


def evaluate(evidence, output):
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "source_archive"; archive.mkdir()
    sources = [Path(repair.__file__), Path(repair.model.__file__), Path(__file__)]
    hashes = {str(p.resolve()): common.sha(p) for p in sources}
    for p in sources: (archive / p.name).write_bytes(p.read_bytes())
    protocol = {"schema": "g31.lt2.resource_repair_model_comparison.v1", "native_budget": 0,
        "methods": list(repair.METHODS), "model_evaluation_budgets": [8, 16, 35], "regimes": [0, 6, 12],
        "candidate_domain": "same35 initial route/window pairs; same adaptive latercontinuation; baseline countswithinbudget and cached exactly once",
        "strict_coordinate": "best strict one-variable improvement; no neutralmove; retainbestprotected incumbent",
        "plateau_coordinate": "best-first nonworsening one-variable component, including neutralsteps; deterministic lexicographic tieorder",
        "resource_pair": "public path-resource overlap expands destroyset tobothinitialvariables; exhaustive boundedrepair over same35domain",
        "candidate_order": "lexicographic(initial_next,departure,later_mode); fixed before reading native labels",
        "objective": "sum allfour predictedcompletion; eachjob<=same modelincumbent withzero tolerance; invalid/unfinishedunknown",
        "information": "offline validation using archivedactual020 deliveredcapturebundles, never resulttableinputs to proposal",
        "primary_source_mapping": "minimal LNS-style destroy/repair adaptation; noassignment/regret/SIPPS/fullrollingimplementation; no novelalgorithmclaim",
        "source_sha256": hashes, "stop": "declared evaluationbudget, exhausted resource neighborhood or nonworseningcoordinatecomponent",
        "unknown": "all unexecuted candidates retained, no feasibility/optimality inference from bounded failure"}
    common.write(output / "preregistered_protocol.json", protocol)
    proposals, bundles = {}, {}
    for gate in protocol["regimes"]:
        # Read only the stored owner's model input before any business labels.
        source = evidence / f"gate{gate}/incumbent.json.gz"
        data = json.load(gzip.open(source, "rt"))
        bundle = data["owners"]["A"]["information"]["bundle"]
        bundles[str(gate)] = {"source_file": str(source.resolve()), "source_sha256": common.sha(source), "bundle": bundle}
        actions, incumbent = repair.model.candidates_from_durations(bundle)
        for budget in protocol["model_evaluation_budgets"]:
            for method in protocol["methods"]:
                started = time.perf_counter()
                result = repair.repair(bundle, actions, incumbent, method=method, evaluation_budget=budget)
                proposals[f"gate{gate}/budget{budget}/{method}"] = {"proposal": result, "model_only_wall_ms": (time.perf_counter() - started) * 1000}
    common.write(output / "frozen_proposals.json", proposals)
    common.write(output / "capture_inputs.json", bundles)
    native = {}
    for gate in protocol["regimes"]:
        native[str(gate)] = [json.load(gzip.open(evidence / f"gate{gate}/{policy}.json.gz", "rt")) for policy in ("incumbent", "fixed_route_model", "joint_model")]
    rows = {}
    for label, item in proposals.items():
        result = item["proposal"]; gate = label.split("/")[0][4:]
        selected = result["selected_action"]
        matches = [r for r in native[gate] if r["owners"]["A"]["decision"]["selected_action"] == selected]
        baseline = native[gate][0]["summary"]["completion"]
        validation = {"status": "unknown_no_matching_native020_action", "native_protection_certified": False}
        if matches and all(m["summary"]["status"] == "assessed" for m in matches):
            completion = matches[0]["summary"]["completion"]
            if all(m["summary"]["completion"] == completion for m in matches):
                validation = {"status": "matching_native020_initial_action_and_continuation", "completion": completion,
                    "strict_physical_protected": all(completion[j] <= baseline[j] for j in baseline),
                    "physical_gain_vs_incumbent": sum(baseline.values()) - sum(completion.values()),
                    "scope": "offline action-matched evidence; not a new native execution of this repair strategy"}
        rows[label] = {"selected_action": selected, "evaluations": result["evaluations"], "stop_reason": result["stop_reason"],
            "model_gain": result["model_gain"], "model_only_wall_ms": item["model_only_wall_ms"], "native_action_match": validation}
    report = {"schema": protocol["schema"], "status": "completed_model_only_comparison", "solver_calls": len(rows),
        "rows": rows, "source_changed": [p for p, h in hashes.items() if common.sha(Path(p)) != h],
        "native_calls": 0, "new_native_strategy_execution": False, "full_B4_or_paper_replica": False,
        "rolling_joint_optimizer_implemented": False, "native_model_error_bound_certified": False,
        "complete_request_100ms_certified": False}
    common.write(output / "receipt.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    evaluate(a.evidence, a.output)

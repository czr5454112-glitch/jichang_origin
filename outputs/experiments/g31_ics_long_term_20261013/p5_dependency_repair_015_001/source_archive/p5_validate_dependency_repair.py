"""Frozen causal intervention of two observed dependency boundaries on native006."""
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
from .assess_joint_window_protection import compare
from .finite_reference import _horizon_completion, outcome_cost
from .joint_window_feedback import repair_observed_source_change
from .joint_window_repair import build_domain, submit_action
from .native_host import audit_result, load_native
from .p5_dependency_repair import publish_observed_loaded_dependencies, repair_observed_occupancy
from .validate_analytic_control import replay_input, write
from .validate_joint_circulation_factor import HORIZON, OWNERS, common_prefix, circulation_factor_input
from .validate_joint_window_repair import SCENARIOS


POLICIES = ("continuous_strong", "source_only_without_publication",
            "source_only_with_publication", "two_boundary_dependency")


def causal_events(result):
    """Offline event extraction only, never returned to the online decisions."""
    events = result["receipts"]
    return {"shared_receiving_entry_order": [r for r in events if r["event"] == "EDGE_ENTER" and r["to"] == 2],
            "shared_receiving_departures": [r for r in events if r["event"] == "EDGE_ENTER" and r["from"] == 2],
            "terminal_departures": [r for r in events if r["event"] == "EDGE_ENTER" and r["from"] == 10],
            "load_unload": [r for r in events if r["event"] in ("LOAD_START", "UNLOAD_COMPLETE")],
            "waits": [r for r in events if r["event"] == "RESOURCE_WAIT"]}


def execute_branch(native, data, initial_name, policy):
    session, state, prefix = common_prefix(native, data)
    observation = session.observe("A")
    domain = build_domain(observation)
    action = next(a for a in domain["actions"] if a["action_id"] == domain["selected"][initial_name])
    initial = submit_action(session, action, observation)
    session.advance_to(.91)
    before = {owner: session.observe(owner) for owner in OWNERS}
    publications = publish_observed_loaded_dependencies(session, OWNERS, .02) \
        if policy != "source_only_without_publication" else []
    session.advance_to(.91 + .02)
    owned = [r["request"]["request_id"] for r in initial["submissions"]]
    if policy == "source_only_without_publication":
        source_repair = repair_observed_source_change(session, "A", owned)
    elif policy in ("source_only_with_publication", "two_boundary_dependency"):
        source_repair = repair_observed_occupancy(session, "A", owned, trigger="source")
    else:
        source_repair = {"status": "not_requested", "submissions": [], "cancellations": []}
    owned += [r["request"]["request_id"] for r in source_repair["submissions"]]
    session.advance_to(10.11)
    second_before = {owner: session.observe(owner) for owner in OWNERS}
    resource_repair = repair_observed_occupancy(session, "A", owned) \
        if policy == "two_boundary_dependency" else {"status": "not_requested", "submissions": [], "cancellations": []}
    follow = run_online_matching(session, OWNERS, horizon=HORIZON, predictive=True, control_period=10.,
                                 message_delay=.1, demand_delay=.02, respect_service_forecasts=True,
                                 controller_state=state, compact_projection=False)
    result = follow["result"]
    completion = _horizon_completion(result, session, HORIZON, follow["status"])
    row = {"initial_policy": initial_name, "policy": policy, "completion": completion,
           "source_repair_status": source_repair["status"], "resource_repair_status": resource_repair["status"],
           "publications": publications, "source_repair_cancellations": source_repair.get("cancellations", []),
           "resource_repair_cancellations": resource_repair.get("cancellations", []),
           "status": "unknown", "causal_events": causal_events(result)}
    all_submissions = initial["submissions"] + source_repair["submissions"] + resource_repair["submissions"] + follow["submitted"]
    if completion["status"] == "reached":
        row["metrics"] = outcome_cost(result, data["jobs"], HORIZON)
        row["audit"] = audit_result(replay_input(data, all_submissions), result)
        row["status"] = "verified_complete_execution"
        row["transfers_by_status"] = {status: sum(t["status"] == status for t in result["transfers"])
                                      for status in sorted({t["status"] for t in result["transfers"]})}
        cancelled = {c["request_id"] for repair in (source_repair, resource_repair)
                     for c in repair.get("cancellations", []) if c["reply"]["status"] == "cancelled"}
        intervention = initial["submissions"] + source_repair["submissions"] + resource_repair["submissions"]
        required = {s["request"]["request_id"] for s in intervention} - cancelled
        resolved = [t for t in result["transfers"] if t["request_id"] in required]
        row["required_intervention_transfers"] = resolved
        row["request_protocol_status"] = "verified" if len(resolved) == len(required) and all(
            t["status"] == "received" for t in resolved) and not any(
            repair["status"].startswith("unknown") for repair in (source_repair, resource_repair)) else "not_verified"
    raw = {"prefix": prefix, "initial": initial, "first_boundary_before": before,
           "source_repair": source_repair, "second_boundary_before": second_before,
           "resource_repair": resource_repair, "controller_run": follow, "assessment": row}
    return row, raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-seconds", type=float, default=180.)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), *(Path(__file__).with_name(name) for name in (
        "p5_dependency_repair.py", "joint_window_repair.py", "joint_window_feedback.py",
        "analytic_control.py", "native_host.py", "finite_reference.py", "boundary_reference.py",
        "validate_joint_circulation_factor.py", "validate_joint_window_repair.py", "validate_analytic_control.py"))]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    archived = args.output / "source_archive"
    archived.mkdir()
    for path in paths:
        (archived / path.name).write_bytes(path.read_bytes())
    protocol = {"schema": "g31.p5_dependency_repair_protocol.v1", "scenarios": [SCENARIOS[1], SCENARIOS[3]],
        "physical_contract": "EXACT existing independent circulation factor; no edge/task/capacity/tray changes",
        "initial_policies": ["ordinary_public_windows", "joint_conditional_repair"], "policies": POLICIES,
        "first_boundary": {"observed": .91, "publication_delay": .02, "decision": .91+.02,
                           "scope": "actual local loaded service to lawful next resource owner; source change repair"},
        "second_boundary": {"observed": 10.11, "scope": "already common control epoch; actual local in-flight minimum occupancy repair"},
        "continuation": "same existing A/B/C strong public-window continuation, first decision10.11, period10",
        "candidate_budget": "two owned soft dependencies; same incumbent assignments; no new native authority",
        "conditional_prediction_semantics": "report inconsistent exterior point estimates separately; proposals conservatively avoid each forecast; never certify exterior feasibility",
        "reference": "all four predetermined interventions per initial policy; same finite budget, offline only",
        "information_ablation": "source_only_without_publication has less information; never claim it is the matched-info strongest comparator",
        "matched_information": ["continuous_strong", "source_only_with_publication", "two_boundary_dependency"],
        "horizon": HORIZON, "max_seconds": args.max_seconds, "max_events": 100000,
        "planned_branches": 16, "protection": "all offered vs frozen factor ordinary and WAIT; precommitted P/U0/U1",
        "global_optimality": "unknown", "novelty": "not_established; bounded dependency repair is a hypothesis"}
    write(args.output / "protocol.json", protocol)
    receipt = {"schema": "g31.p5_dependency_repair_receipt.v1", "status": "running", "source_before": before,
               "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(), "cases": [],
               "protocol_sha256": hashlib.sha256((args.output / "protocol.json").read_bytes()).hexdigest()}
    write(args.output / "receipt.json", receipt)
    native = load_native(args.binary)
    started = time.perf_counter()
    try:
        for spec in protocol["scenarios"]:
            data = circulation_factor_input(spec)
            directory = args.output / spec["name"]
            directory.mkdir()
            old = Path("outputs/experiments/g31_ics_long_term_20261013/p5_joint_circulation_factor_006_001") / spec["name"]
            reference = json.loads((old / "summary.json").read_text(encoding="utf-8"))
            old_input = json.loads((old / "input.json").read_text(encoding="utf-8"))
            assert json.loads(json.dumps(data)) == old_input, "original_factor_contract_changed"
            write(directory / "input.json", data)
            rows = []
            for initial in protocol["initial_policies"]:
                for policy in POLICIES:
                    if time.perf_counter() - started >= args.max_seconds:
                        raise TimeoutError("native_campaign_budget_unknown")
                    row, raw = execute_branch(native, data, initial, policy)
                    all_ids = sorted(j["business_bag_id"] for j in data["jobs"])
                    if "metrics" in row:
                        for name, baseline in (("ordinary", "ordinary_public_windows"), ("WAIT", "WAIT")):
                            row["relative_to_frozen_" + name] = compare(row["metrics"], reference["policies"][baseline]["metrics"], all_ids)
                        row["precommitted_vs_frozen_WAIT"] = compare(row["metrics"], reference["policies"]["WAIT"]["metrics"], ["P", "U0", "U1"])
                    filename = f"branch_{len(rows):03d}.json.gz"
                    with gzip.open(directory / filename, "wt", encoding="utf-8") as handle:
                        json.dump(raw, handle, allow_nan=False)
                    row["raw_file"] = filename
                    row["raw_sha256"] = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
                    rows.append(row)
            for initial in protocol["initial_policies"]:
                subset = [r for r in rows if r["initial_policy"] == initial]
                strong = next(r for r in subset if r["policy"] == "continuous_strong")
                for row in subset:
                    row["relative_to_matched_info_strong"] = compare(row["metrics"], strong["metrics"], all_ids)
            finite_reference = []
            for initial in protocol["initial_policies"]:
                subset = [r for r in rows if r["initial_policy"] == initial and r["policy"] in protocol["matched_information"]]
                strong = next(r for r in subset if r["policy"] == "continuous_strong")
                qualified = [r for r in subset if r["request_protocol_status"] == "verified"
                             and r["relative_to_matched_info_strong"]["preserved"]]
                best = min(qualified, key=lambda r: r["metrics"]["cost"], default=None)
                finite_reference.append({"initial_policy": initial, "evaluated": len(subset), "domain_size": 3,
                    "qualified_policies": [r["policy"] for r in qualified], "best_policy": best["policy"] if best else None,
                    "headroom_relative_to_strong": strong["metrics"]["cost"] - best["metrics"]["cost"] if best else None,
                    "baseline_request_protocol_status": strong["request_protocol_status"],
                    "scope": "only three matched-information, predetermined two-boundary interventions; no online future selection",
                    "global_native_optimality": "unknown"})
            case = {"scenario": spec, "rows": rows, "frozen_reference_sha256": hashlib.sha256((old / "summary.json").read_bytes()).hexdigest(),
                    "complete_branches": sum(r["status"] == "verified_complete_execution" for r in rows),
                    "finite_reference": finite_reference,
                    "global_optimality": "unknown", "reference_scope": "four interventions, fixed two boundaries and continuation only"}
            write(directory / "summary.json", case)
            receipt["cases"].append(case)
            write(args.output / "receipt.json", receipt)
        receipt["status"] = "passed_execution_not_research_gate"
    except Exception:
        receipt["status"] = "failed"
        receipt["traceback"] = traceback.format_exc()
        raise
    finally:
        receipt["elapsed_seconds"] = time.perf_counter() - started
        receipt["source_after"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        receipt["source_changed"] = [p for p in before if before[p] != receipt["source_after"][p]]
        write(args.output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "source_changed": receipt["source_changed"],
        "cases": [{"name": c["scenario"]["name"], "rows": [{"initial": r["initial_policy"], "policy": r["policy"],
                   "cost": r["metrics"]["cost"], "source": r["source_repair_status"], "resource": r["resource_repair_status"],
                   "vs_ordinary": r["relative_to_frozen_ordinary"]["preserved"], "vs_WAIT": r["relative_to_frozen_WAIT"]["preserved"]}
                  for r in c["rows"]]} for c in receipt["cases"]]}))


if __name__ == "__main__":
    main()

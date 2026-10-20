"""Actual on-demand R1 request on the original graph and predeclared source subset.

The common route-authorization factor is explicit. This is not a field-granted
permission or a new method. A public first-branch rule selects the checkpoint;
no alternative's future outcome is inspected to choose the boundary.
"""
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
from .finite_reference import Intervention, enumerate_interventions, headroom, outcome_cost, service_dominates
from .native_host import audit_result, load_native
from .original_mechanism import select_input
from .original_workload import json_digest, write_json
from .regional_control import complete_on_demand, public_astar
from .validate_analytic_control import replay_input


def first_public_branch(session, owners, *, max_events=5000):
    """Stop at first observed loaded tray with two public stage continuations."""
    for inspected in range(max_events + 1):
        for owner in owners:
            observation = session.observe(owner)
            jobs = {j["business_bag_id"]: j for j in observation["jobs"]}
            for tray in sorted(observation["trays"], key=lambda t: t["tray_id"]):
                job = jobs.get(tray["business_bag_id"])
                if tray["mode"] != "loaded" or tray["edge_to"] >= 0 or not job:
                    continue
                storage = job["storage_node"]
                goal = storage if storage >= 0 and job["storage_released_at"] < 0 else job["destination"]
                choices = sorted(e["to"] for e in observation["edge_contracts"]
                    if e["from"] == tray["node"] and e["capacity"] > 0
                    and public_astar(observation, e["to"], goal))
                if len(choices) >= 2:
                    return {"owner": owner, "tray_id": tray["tray_id"], "observation": observation,
                            "public_next_choices": choices, "inspected_event_boundaries": inspected,
                            "selection": "first observed loaded, unentered tray with two positive-capacity public stage continuations"}
        if not session.step():
            break
    raise RuntimeError("no qualifying public route boundary within declared event budget")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--reference", action="store_true",
                        help="enumerate every public next choice at the same declared first boundary")
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), *[Path(__file__).with_name(n + ".py") for n in
             ("original_mechanism", "original_workload", "analytic_control", "finite_reference",
              "regional_control", "native_host", "validate_analytic_control")]]
    snapshot = lambda: {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    receipt = {"status": "running", "source_before": snapshot(),
               "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
               "claim": "original graph R1 integration and request timing; common research authorization factor; no novelty or full-flow claim"}
    start = time.perf_counter()
    try:
        data, selection, lineage = select_input(args.count, horizon=args.horizon)
        # Both baseline and candidate have identical service and route authority.
        # Original source has no field route-authority column: this is a factor.
        for job in data["jobs"]:
            job["allow_suffix_reroute"] = True
        selection["base_selected_input_sha256"] = selection["input_sha256"]
        selection["input_sha256"] = json_digest(data)
        selection["common_research_factor"] = {"allow_suffix_reroute": True,
            "applies_to": "both S4 baseline and R1 candidate", "field_permission_claim": False,
            "business_destination_arrival_storage_deadline_changed": False}
        write_json(args.output / "input.json", data)
        write_json(args.output / "selection.json", selection)
        with gzip.open(args.output / "mother_crosswalk.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in lineage:
                stream.write(json.dumps(row) + "\n")
        native = load_native(args.binary); session = native.NativeSession(data)
        owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
        boundary = first_public_branch(session, owners)
        write_json(args.output / "boundary.json", boundary)
        parent_hash = session.offline_state_sha256()
        baseline, candidate = session.fork(), session.fork()
        measurement = complete_on_demand(candidate, boundary["owner"], boundary["tray_id"],
            "original-r1-first-public-branch", logical_compute_delay=.001, lease_seconds=5.)
        write_json(args.output / "complete_request.json", measurement)
        # Synchronize common continuation phase after the same native interval.
        baseline.advance_to(candidate.physical_time)
        outcomes = {}
        for label, branch in (("S4", baseline), ("regional_Astar", candidate)):
            run = run_online_matching(branch, owners, horizon=args.horizon, predictive=True,
                control_period=60., message_delay=2., demand_delay=.5)
            if run["status"] != "reached" or run["result"]["horizon"] != args.horizon:
                raise RuntimeError("original regional continuation incomplete")
            audit = audit_result(replay_input(data, run["submitted"]), run["result"])
            with gzip.open(args.output / (label + "_raw.json.gz"), "wt", encoding="utf-8") as stream:
                json.dump(run, stream)
            write_json(args.output / (label + "_audit.json"), audit)
            outcomes[label] = outcome_cost(run["result"], data["jobs"], args.horizon)
            write_json(args.output / (label + "_metrics.json"), outcomes[label])
        receipt["measurement"] = {k: v for k, v in measurement.items() if k != "submission"}
        receipt["request_submission"] = measurement["submission"]["response"]
        receipt["boundary"] = {k: v for k, v in boundary.items() if k != "observation"}
        receipt["strict_paired_service_preserved"] = service_dominates(outcomes["regional_Astar"], outcomes["S4"])
        receipt["cost_regional_minus_S4"] = outcomes["regional_Astar"]["cost"] - outcomes["S4"]["cost"]
        receipt["outcomes"] = {k: {name: value for name, value in row.items() if name != "per_job"}
                               for k, row in outcomes.items()}
        if args.reference:
            template = measurement["submission"]["request"]
            if template is None:
                raise RuntimeError("no route template for public-domain reference")
            actions = [Intervention("WAIT", "wait")]
            for next_node in boundary["public_next_choices"]:
                request = dict(template, request_id=f"original-route-reference-{next_node}", next=next_node)
                actions.append(Intervention(f"route-{next_node}", "route", request))
            # All branches share the post-delivery controller start and its phase.
            # The real common future is used only in this offline diagnostic.
            continuation_start = session.physical_time + .001

            def continuation(branch, horizon):
                branch.advance_to(continuation_start)
                run = run_online_matching(branch, owners, horizon=horizon, predictive=True,
                    control_period=60., message_delay=2., demand_delay=.5)
                run["result"]["offline_continuation_submitted"] = run["submitted"]
                return run

            def validate(result, action):
                return audit_result(replay_input(data, result["offline_continuation_submitted"]), result)

            baseline_id = f"route-{template['next']}"
            reference = enumerate_interventions(session, actions, horizon=args.horizon,
                job_contracts=data["jobs"], baseline_action_id=baseline_id,
                max_branches=len(actions), max_seconds=120., continuation=continuation, validate=validate)
            with gzip.open(args.output / "route_reference_raw.json.gz", "wt", encoding="utf-8") as stream:
                json.dump(reference, stream)
            receipt["reference"] = {k: v for k, v in reference.items() if k != "rows"}
            receipt["headroom"] = headroom(reference, [a.action_id for a in actions], baseline_id, baseline_id)
            receipt["candidate_summary"] = [{"action": row["action"], "status": row["status"],
                "completion": row.get("completion"), "cost": row.get("metrics", {}).get("cost"),
                "paired_service_preserved": row.get("paired_service_preserved")}
                for row in reference["rows"]]
            receipt["reference_limit"] = "all current public next hops plus WAIT only; subsequent requests/routes and transfer assignment not exhaustively optimized"
        receipt["parent_unchanged"] = session.offline_state_sha256() == parent_hash
        assert receipt["parent_unchanged"]
        receipt["status"] = "executed"
    except Exception:
        receipt["status"] = "failed"; receipt["traceback"] = traceback.format_exc()
    finally:
        receipt["source_after"] = snapshot()
        receipt["source_changed"] = [p for p, h in receipt["source_before"].items() if receipt["source_after"][p] != h]
        if receipt["source_changed"]:
            receipt["status"] = "source_changed"
        receipt["wall_seconds"] = time.perf_counter() - start
        write_json(args.output / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    return int(receipt["status"] != "executed")


if __name__ == "__main__":
    raise SystemExit(main())

"""Predeclared six-action reference at the original map's first public return.

Boundary selection reads only actual owner observations at fixed control ticks.
It does not inspect outcomes of candidate continuations or future input jobs.
All branches replace the same one control epoch, preserve its next-tick phase,
and use identical reactive continuation with actual delayed demand messages.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import copy
import gzip
import json
from pathlib import Path
import time
import traceback

from .analytic_control import run_online_matching, transfer_candidates
from .finite_reference import Intervention, enumerate_interventions, headroom
from .native_host import audit_result, load_native
from .original_mechanism import select_input
from .original_workload import digest, write_json
from .validate_analytic_control import replay_input


def first_public_return(session, owners, *, horizon, period=60.):
    state, submitted, inspected = None, [], 0
    for tick in range(int(horizon // period) + 1):
        target = tick * period
        advance = session.advance_to(target)
        if advance["status"] != "reached":
            raise RuntimeError("original_reference:prefix_censored")
        for owner in owners:
            observation = session.observe(owner)
            decision = transfer_candidates(observation, predictive=False, message_delay=2.,
                                           request_prefix="original-first-public-reference")
            inspected += 1
            if decision["intents"]:
                if len(decision["intents"]) != 1 or state is None or state["next_tick"] != tick:
                    raise RuntimeError("original_reference:undeclared_multi_action_or_phase")
                # The finite intervention replaces this complete epoch. No
                # branch reruns this tick or publishes a different demand tape.
                continuation_state = copy.deepcopy(state)
                continuation_state["next_tick"] = tick + 1
                return {"observation": observation, "decision": decision, "owner": owner,
                        "tick": tick, "time": target, "inspected_owner_boundaries": inspected,
                        "prefix_submitted": submitted, "controller_state_before_epoch": state,
                        "controller_state_for_continuation": continuation_state,
                        "rule": "first fixed 60-second tick with public actual-empty reactive return intent; owner order sorted; no outcome search",
                        "epoch_replacement": "one whole current epoch, no current-epoch demand republish; next epoch and cached publication signatures shared by every branch"}
        prefix = run_online_matching(session, owners, horizon=target, predictive=False,
            control_period=period, message_delay=2., demand_delay=.5, controller_state=state)
        if prefix["status"] != "reached":
            raise RuntimeError("original_reference:prefix_controller_censored")
        state = prefix["controller_state"]
        submitted.extend(prefix["submitted"])
    raise RuntimeError("original_reference:no_qualifying_boundary")


def finite_actions(boundary):
    request = boundary["decision"]["intents"][0]
    actions = [Intervention("WAIT", "wait"), Intervention("analytic", "transfer", request)]
    for offset in (1., 15., 30., 60.):
        delayed = dict(request, request_id=request["request_id"] + f":offset:{offset:g}",
                       earliest_departure=request["earliest_departure"] + offset,
                       expiry=request["expiry"] + offset)
        actions.append(Intervention(f"delay-{offset:g}", "transfer", delayed))
    return actions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--max-seconds", type=float, default=120.)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), *[Path(__file__).with_name(name + ".py") for name in
             ("analytic_control", "finite_reference", "original_mechanism", "original_workload", "native_host", "validate_analytic_control")]]
    snapshot = lambda: {str(path): digest(path) for path in paths}
    receipt = {"schema": "g31.original_finite_reference.v1", "status": "running",
               "source_before": snapshot(), "binary_sha256": digest(args.binary),
               "scope": "24 complete original-source bags on unchanged full graph; offline finite intervention, not global optimum or method innovation",
               "declared_domain": ["WAIT", "analytic", "delay-1", "delay-15", "delay-30", "delay-60"]}
    write_json(args.output / "receipt.json", receipt)
    start = time.perf_counter()
    try:
        data, selection, lineage = select_input(24, horizon=args.horizon)
        write_json(args.output / "input.json", data); write_json(args.output / "selection.json", selection)
        with gzip.open(args.output / "mother_crosswalk.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in lineage:
                stream.write(json.dumps(row) + "\n")
        session = load_native(args.binary).NativeSession(data)
        owners = sorted({node["resource_owner"] for node in data["node_contracts"]})
        boundary = first_public_return(session, owners, horizon=args.horizon)
        actions = finite_actions(boundary)
        write_json(args.output / "public_boundary_and_domain.json", {**boundary, "actions": [asdict(action) for action in actions]})
        parent_hash = session.offline_state_sha256()

        def continuation(branch, horizon):
            run = run_online_matching(branch, owners, horizon=horizon, predictive=False,
                control_period=60., message_delay=2., demand_delay=.5,
                controller_state=copy.deepcopy(boundary["controller_state_for_continuation"]))
            run["result"]["offline_continuation_submitted"] = run["submitted"]
            return run

        def validate(result, action):
            submissions = boundary["prefix_submitted"] + result["offline_continuation_submitted"]
            if action.kind == "transfer":
                submissions = submissions + [{"request": action.request, "reply": {"status": "pending"}}]
            return audit_result(replay_input(data, submissions), result)

        reference = enumerate_interventions(session, actions, horizon=args.horizon, job_contracts=data["jobs"],
            baseline_action_id="analytic", max_branches=6, max_seconds=args.max_seconds,
            continuation=continuation, validate=validate, strict_paired_service=True)
        with gzip.open(args.output / "finite_reference_raw.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(reference, stream)
        receipt["reference"] = {key: value for key, value in reference.items() if key != "rows"}
        receipt["headroom"] = headroom(reference, ["WAIT", "analytic"], "analytic", "analytic")
        receipt["candidates"] = [{key: value for key, value in row.items() if key not in ("result", "audit")}
                                 for row in reference["rows"]]
        receipt["boundary"] = {key: boundary[key] for key in ("owner", "tick", "time", "inspected_owner_boundaries", "rule", "epoch_replacement")}
        receipt["parent_unchanged"] = session.offline_state_sha256() == parent_hash
        if not receipt["parent_unchanged"]:
            raise RuntimeError("original_reference:fork_changed_parent")
        receipt["status"] = "executed"
    except Exception:
        receipt["status"] = "failed"; receipt["traceback"] = traceback.format_exc()
    finally:
        receipt["source_after"] = snapshot()
        receipt["source_changed"] = [path for path, value in receipt["source_before"].items() if receipt["source_after"][path] != value]
        receipt["wall_seconds"] = time.perf_counter() - start
        if receipt["source_changed"]:
            receipt["status"] = "source_changed"
        write_json(args.output / "receipt.json", receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != "candidates"}, indent=2))
    return int(receipt["status"] != "executed")


if __name__ == "__main__":
    raise SystemExit(main())

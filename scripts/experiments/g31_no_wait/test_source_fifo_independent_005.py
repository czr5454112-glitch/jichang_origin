"""Independent 005 native source-order, three-clock and resource micro probes."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_no_wait.headway_audit import audit_headway
from scripts.experiments.g31_no_wait.rolling_replay import replay_rolling
from scripts.experiments.g31_no_wait.tht_metrics import audit_tht


def task(sid, business, start, goal, release=0, leg="direct"):
    return dict(segment_id=sid, task_id=business, start=start, goal=goal,
                release=release, deadline=1000, leg=leg)


def config(**changes):
    return dict(end_time=100, source_fifo=True, source_generation_interval=1,
                release_quantum=1, completion_quantum=1, source_fifo_order="canonical",
                interval_mode="half_open", strict_endpoint_resources=True,
                edge_entry_headway_seconds=2, enable_inroute_replanning=True,
                enable_ebs_predecessor_gate=True, congestion_weight=0,
                adaptive=False, min_depth=1, max_depth=1, max_expansions=256,
                max_score_expansions=64, max_retries=1000, max_events=100000,
                retry_mode="calendar_jump", **changes)


def inspect(request, payload, canonical_fifo=True):
    first = {}
    for t in request["tasks"]:
        first[t["task_id"]] = min(first.get(t["task_id"], float("inf")), t["release"])
    rows = [dict(segment_id=t["segment_id"], task_id=t["task_id"], start=t["start"],
                 goal=t["goal"], pass_time=t["release"], leg=t["leg"],
                 original_entry_time=first[t["task_id"]]) for t in request["tasks"]]
    profile = dict(nodes=[dict(location=n, service_time=s) for n, s in request["nodes"]],
                   edges=[dict(start=u, end=v, length=travel*2) for u, v, travel in request["edges"]])
    bags = payload["bags"]
    horizon = payload["summary"]["executed_horizon"]
    audits = dict(headway=audit_headway(rows, bags, profile),
                  rolling=replay_rolling(rows, bags, profile, payload["rolling_events"],
                                         horizon=horizon, require_nonincreasing_finish=True),
                  tht=audit_tht(rows, bags, horizon=horizon))
    assert all(a["passed"] for a in audits.values()), audits
    actual = {b["segment_id"]: b for b in bags}
    if canonical_fifo:
        queues = defaultdict(list)
        # Stable raw nominal order, not ceil(release), ID or activation order.
        for t in sorted(request["tasks"], key=lambda t: t["release"]):
            queues[t["start"]].append(actual[t["segment_id"]])
        for queue in queues.values():
            prior = None
            blocked = False
            for bag in queue:
                attempt = bag["first_planning_attempt_time"]
                if blocked:
                    assert attempt is None, ("bypassed_unadmitted_predecessor", bag)
                if attempt is not None and prior is not None:
                    assert attempt >= prior + 1, ("source_attempt_before_previous_success_plus_tick", bag)
                if bag["admission"] is None:
                    blocked = True
                else:
                    prior = bag["admission"]
    return audits


def run(module):
    records = []

    def execute(name, request, canonical=True):
        payload = module.plan(**request)
        audits = inspect(request, payload, canonical)
        records.append(dict(case=name, request=request, payload=payload, audits=audits))
        return {b["segment_id"]: b for b in payload["bags"]}

    tasks = [task("b_in", 11, 1, 2, leg="storage_in"),
             task("b_out", 11, 2, 3, 2.9, "storage_out"),
             task("a_in", 10, 0, 2, leg="storage_in"),
             task("a_out", 10, 2, 3, 2.1, "storage_out")]
    request = dict(nodes=[(0, 0), (1, 0), (2, 2), (3, 0)],
                   edges=[(0, 2, 10.25), (1, 2, 1), (2, 3, 1)],
                   tasks=tasks, config=config())
    b = execute("later_ready_outbound_cannot_pass_nominal_earlier_gated_head", request)
    assert (b["a_out"]["activation_time"], b["a_out"]["first_planning_attempt_time"], b["a_out"]["admission"]) == (11, 11, 13)
    assert (b["b_out"]["activation_time"], b["b_out"]["first_planning_attempt_time"], b["b_out"]["admission"]) == (4, 14, 15)
    assert b["b_out"]["preplanning_hold_seconds"] == 10
    assert b["b_out"]["planning_wait_seconds"] == 1
    alternate = {**request, "config": {**request["config"], "source_fifo_order": "activation"}}
    old = execute("activation_order_is_explicitly_a_different_policy", alternate, False)
    assert old["b_out"]["admission"] == 4 < old["a_out"]["admission"]

    request = dict(nodes=[(0, 0), (1, 0)], edges=[(0, 1, 3)],
                   tasks=[task("9", 9, 0, 1, 5.9), task("4", 4, 0, 1, 5.1), task("2", 2, 0, 1, 5.1)],
                   config=config())
    b = execute("raw_nominal_fraction_order_and_equal_release_input_order", request)
    assert [b[k]["first_planning_attempt_time"] for k in ("4", "2", "9")] == [6, 7, 9]
    assert [b[k]["admission"] for k in ("4", "2", "9")] == [6, 8, 10]

    request = dict(nodes=[(0, 0), (1, 0), (2, 2), (3, 0)],
                   edges=[(1, 2, 1), (2, 3, 1)], tasks=tasks,
                   config={**config(), "end_time": 20, "max_retries": 0})
    b = execute("unreachable_inbound_keeps_later_ready_outbound_unattempted", request)
    assert b["a_out"]["first_planning_attempt_time"] is None
    assert b["b_out"]["activation_time"] == 4
    assert b["b_out"]["first_planning_attempt_time"] is None
    assert b["b_out"]["admission"] is None

    request = dict(nodes=[(0, 2)], edges=[], tasks=[task("a", 1, 0, 0), task("b", 2, 0, 0)], config=config())
    b = execute("same_source_goal_residual_device_occupancy_survives_fifo_progress", request)
    assert (b["b"]["first_planning_attempt_time"], b["b"]["admission"], b["b"]["finish"]) == (1, 2, 2)

    invalid = dict(request, config={**request["config"], "source_fifo": False})
    try:
        module.plan(**invalid)
        raise AssertionError("canonical ordering accepted without source FIFO")
    except ValueError:
        pass
    return dict(passed=True, native_cases=len(records), invalid_config_rejected=True, records=records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    spec = importlib.util.spec_from_file_location("g31_nowait", args.binary.resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = run(module)
    result["binary_sha256"] = hashlib.sha256(args.binary.read_bytes()).hexdigest()
    result["independent_test_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["comparison_boundary"] = "Tests canonical source order and one-tick pacing, not identity of all cross-source tie ordering or Java event propagation. No performance winner claim."
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}))

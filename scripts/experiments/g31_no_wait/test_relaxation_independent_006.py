"""Independent source retry-budget probes for native006; no full benchmark."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_no_wait.headway_audit import audit_headway
from scripts.experiments.g31_no_wait.rolling_replay import replay_rolling
from scripts.experiments.g31_no_wait.source_policy_audit import audit_source_policy
from scripts.experiments.g31_no_wait.tht_metrics import audit_tht


def task(sid, source, goal, release=0):
    business = {"block1": 1, "block2": 2, "block3": 3, "leader": 4,
                "head": 5, "block4": 6, "leader_block": 7}[sid]
    return dict(segment_id=sid, task_id=business, start=source, goal=goal,
                release=release, deadline=100, leg="direct")


def fixture(*, leader=False, release=0, extra_microseconds=2000001):
    # All three independent blockers enter at t=0 and reserve device4 at
    # [1,3), [3,5), [5,7). The head's shortest route takes4s; the alternative
    # bypasses device4 and differs by an exact integer number of microseconds.
    nodes = [(n, 2 if n == 4 else 0) for n in (0, 4, 5, 6, 10, 11, 12, 13)]
    edges = [(11, 4, 1), (12, 4, 3), (13, 4, 5), (0, 4, 1), (4, 10, 1),
             (0, 5, 2), (5, 10, (2000000 + extra_microseconds) / 1000000), (0, 6, .5)]
    tasks = [task("block1", 11, 4), task("block2", 12, 4), task("block3", 13, 4)]
    if leader:
        nodes = [(n, 2 if n == 6 else s) for n, s in nodes] + [(14, 0), (15, 0)]
        edges.extend([(14, 4, 7), (15, 6, .25)])
        tasks.extend([task("block4", 14, 4), task("leader_block", 15, 6)])
        tasks.append(task("leader", 0, 6))
    tasks.append(task("head", 0, 10, release))
    config = dict(end_time=30, source_fifo=True, source_fifo_order="canonical",
                  source_generation_interval=1, release_quantum=1, completion_quantum=1,
                  interval_mode="half_open", strict_endpoint_resources=True,
                  edge_entry_headway_seconds=2, time_grid_seconds=1e-6,
                  enable_inroute_replanning=True, enable_ebs_predecessor_gate=True,
                  congestion_weight=0, adaptive=False, min_depth=1, max_depth=1,
                  max_expansions=256, max_score_expansions=64, max_retries=1000,
                  max_events=10000, retry_mode="1s", max_route_excess_seconds=0,
                  audit_failed_calendar_hash=True)
    return dict(nodes=nodes, edges=edges, tasks=tasks, config=config)


def cases():
    return [
        ("fifo_delayed_first_attempt_and_one_microsecond_cap_boundary",
         fixture(leader=True), [(0, 8), (1, 6), (2, 5)]),
        ("raw_fractional_release_is_not_first_attempt",
         fixture(release=.25), [(0, 6), (1, 4), (2, 3)]),
        ("half_microsecond_growth_rounds_down_not_to_nearest",
         fixture(extra_microseconds=1), [(0, 6), (.0000005, 2)]),
    ]


def rank_cases():
    """Tied/nearby static costs with a blocked smallest-ID successor."""
    base = fixture()
    base["nodes"] = [(0, 0), (4, 2), (8, 2), (10, 0), (11, 0)]
    base["edges"] = [(0, 10, 4), (0, 8, 1.000001), (8, 10, .999999),
                     (0, 4, 1), (4, 10, 1), (11, 4, 1)]
    base["tasks"] = [task("block1", 11, 4), task("head", 0, 10)]
    base["config"]["skip_scoring_single_choice"] = False
    cases = []
    for budget, depth, weight in [(0, 1, 0), (1, 1, 0), (2, 1, 0), (3, 2, 0), (3, 1, 2)]:
        request = deepcopy(base)
        request["config"].update(max_score_expansions=budget, min_depth=depth,
                                 max_depth=depth, congestion_weight=weight)
        cases.append((f"static_ranking_budget{budget}_depth{depth}_weight{weight}", request))
    return cases


def inspect(request, payload):
    rows = [dict(segment_id=t["segment_id"], task_id=t["task_id"], start=t["start"],
                 goal=t["goal"], pass_time=t["release"], original_entry_time=t["release"],
                 leg=t["leg"], std=t["deadline"]) for t in request["tasks"]]
    profile = dict(nodes=[dict(location=n, service_time=s) for n, s in request["nodes"]],
                   edges=[dict(start=u, end=v, length=travel * 2) for u, v, travel in request["edges"]])
    bags = payload["bags"]
    audits = dict(headway=audit_headway(rows, bags, profile),
                  rolling=replay_rolling(rows, bags, profile, payload["rolling_events"],
                                         horizon=payload["summary"]["executed_horizon"],
                                         require_nonincreasing_finish=True),
                  source=audit_source_policy(rows, bags),
                  tht=audit_tht(rows, bags, horizon=payload["summary"]["executed_horizon"]))
    assert all(a["passed"] for a in audits.values()), audits
    assert audits["tht"]["user_tht_full_population_available"], audits["tht"]
    return audits


def run(module, *, baseline=False):
    records = []
    for name, base_request, arms in cases():
        for rate, expected in (arms[:1] if baseline else arms):
            request = deepcopy(base_request)
            if not baseline:
                request["config"]["route_excess_retry_relaxation_rate"] = rate
            payload = module.plan(**request)
            audits = inspect(request, payload)
            head = next(b for b in payload["bags"] if b["segment_id"] == "head")
            assert head["admission"] == expected, (name, rate, expected, head)
            first = 3 if "fifo_delayed" in name else (0 if "half_microsecond" in name else 1)
            assert head["first_planning_attempt_time"] == first, (name, head)
            assert head["planning_wait_seconds"] == expected - first, (name, head)
            if "fifo_delayed" in name:
                assert head["activation_time"] == 1, head
                assert head["preplanning_hold_seconds"] == 2, head
            if "fractional" in name:
                assert head["activation_time"] == 1, head
            expected_route = [0, 4, 10] if rate == 0 else [0, 5, 10]
            assert [step[0] for step in head["route"]] == expected_route, head
            # The retry policy acts only before admission; physical execution
            # and all owner generations must still pass independent replay.
            assert head["route_generation"] == 1, head
            records.append(dict(case=name, rate=rate, request=request, payload=payload, audits=audits))
    for name, request in rank_cases():
        payload = module.plan(**request)
        audits = inspect(request, payload)
        head = next(b for b in payload["bags"] if b["segment_id"] == "head")
        assert head["admission"] == 0 and head["finish"] == 4, (name, head)
        assert [step[0] for step in head["route"]] == [0, 8, 10], (name, head)
        records.append(dict(case=name, rate=0, request=request, payload=payload, audits=audits))
    return dict(status="passed", native_cases=len(records), records=records)


def compare_previous(module, prior):
    old = json.loads(Path(prior).read_text(encoding="utf-8"))
    fields = ledgers = decisions = 0
    for record in old["records"]:
        new = module.plan(**record["request"])
        previous = record["payload"]
        assert len(previous["bags"]) == len(new["bags"]), record["case"]
        for a, b in zip(previous["bags"], new["bags"]):
            for key, value in a.items():
                if key in ("score_expansions", "local_scoring_calendar_queries"):
                    continue
                if key == "route_decisions":
                    assert len(value) == len(b[key]), (record["case"], key)
                    for old_decision, new_decision in zip(value, b[key]):
                        assert [old_decision[i] for i in (0, 1, 4)] == [new_decision[i] for i in (0, 1, 4)], (record["case"], old_decision, new_decision)
                        decisions += 1
                    continue
                assert json.dumps(value, sort_keys=True) == json.dumps(b[key], sort_keys=True), (record["case"], a["segment_id"], key, value, b[key])
                fields += 1
        assert json.dumps(previous["rolling_events"], sort_keys=True) == json.dumps(new["rolling_events"], sort_keys=True), record["case"]
        ledgers += len(previous["rolling_events"])
    return dict(passed=True, cases=len(old["records"]), old_bag_fields_exact=fields,
                logical_decision_tuples_exact=decisions, ledger_records_exact=ledgers,
                allowed_diagnostic_changes=["score_expansions", "local_scoring_calendar_queries",
                                            "route_decisions.actual_query_depth", "route_decisions.actual_query_count"],
                prior_sha256=hashlib.sha256(Path(prior).read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--prior", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    spec = importlib.util.spec_from_file_location("g31_nowait", args.binary.resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = run(module, baseline=args.baseline)
    if args.prior:
        result["default_zero_compatibility"] = compare_previous(module, args.prior)
    result["binary_sha256"] = hashlib.sha256(args.binary.read_bytes()).hexdigest()
    result["independent_test_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["comparison_boundary"] = "Independent micro fixtures; no throughput, mean-THT or starvation theorem. All cases keep one-second retries, canonical source FIFO, and the inroute no-later rule."
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}))

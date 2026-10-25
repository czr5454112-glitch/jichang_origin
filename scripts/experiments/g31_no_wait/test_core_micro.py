"""Small independent physical/transaction regressions for the isolated prototype."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def task(sid, start, goal, release=0.0, *, task_id=None, leg="direct"):
    return dict(segment_id=str(sid), task_id=int(task_id if task_id is not None else sid),
                release=release, deadline=1e15, start=start, goal=goal, leg=leg)


def verify(payload, nodes, edges):
    service = dict(nodes)
    travel = {(u, v): dt for u, v, dt in edges}
    intervals = {}
    for bag in payload["bags"]:
        route = bag["route"]
        assert len({n for n, _, _ in route}) == len(route), "cyclic certificate"
        if not route:
            assert bag["admission"] is None and not bag["completed"]
            continue
        assert bag["admission"] >= bag["release"]
        assert bag["admission"] == route[0][1]
        assert bag["finish"] == route[-1][1]
        for j, (node, arrival, departure) in enumerate(route):
            if j + 1 < len(route):
                assert departure == arrival + service[node]
            if j:
                previous = route[j - 1]
                assert arrival == previous[2] + travel[previous[0], node], "internal wait or teleport"
            if 0 < j < len(route) - 1:
                intervals.setdefault(node, []).append((arrival, departure, bag["segment_id"]))
    for node, occupied in intervals.items():
        occupied.sort()
        for previous, current in zip(occupied, occupied[1:]):
            assert previous[1] < current[0], ("closed interval overlap", node, previous, current)


def run(module):
    records = []

    def case(label, nodes, edges, tasks, **config):
        options = dict(end_time=1000.0, min_depth=1, max_depth=4, adaptive=True,
                       source_fifo=True, source_generation_interval=1.0,
                       release_quantum=1.0, completion_quantum=1.0,
                       audit_failed_calendar_hash=True)
        options.update(config)
        payload = module.plan(nodes, edges, tasks, options)
        assert len(payload["bags"]) == len(tasks)
        verify(payload, nodes, edges)
        records.append(dict(case=label, summary=payload["summary"],
                            bags=payload["bags"]))
        return payload

    nodes = [(0, 0), (1, 0), (2, 2), (3, 2)]
    edges = [(0, 2, 1), (1, 2, 1), (2, 3, 1)]
    p = case("two_sources_closed_service2", nodes, edges, [task(0, 0, 3), task(1, 1, 3)])
    assert [b["admission"] for b in p["bags"]] == [0, 3]
    assert p["summary"]["failed_search_hash_checks"] >= 1

    p = case("future_release_not_reserved", nodes, edges,
             [task(1, 1, 3, 1), task(0, 0, 3, 0)])
    assert p["bags"][1]["commit_order"] == 1
    assert p["bags"][1]["admission"] == 0

    rounding_nodes = [(i, 2) for i in range(6)]
    rounding_edges = [(0, 1, .4), (2, 1, .4), (4, 1, .4), (1, 3, 10), (1, 5, 1)]
    p = case("duplicate_start_short_goal_cannot_hide_internal", rounding_nodes, rounding_edges,
             [task(0, 0, 3), task(1, 2, 1), task(2, 4, 5, 2)],
             terminal_reservation_service=False)
    assert p["bags"][2]["admission"] > 2

    nodes2 = [(0, 0), (1, 0), (2, 2), (3, 2), (4, 0), (5, 0)]
    edges2 = [(1, 2, 1), (0, 2, 1), (2, 4, 1), (0, 3, 1), (3, 5, 1)]
    p = case("source_fifo_paces_after_blocked_head", nodes2, edges2,
             [task(9, 1, 4), task(10, 0, 4), task(11, 0, 5, 1)])
    assert [b["admission"] for b in p["bags"]] == [0, 3, 4]

    nodes3 = [(0, 0), (1, 0), (2, 0)]
    edges3 = [(0, 1, 5), (1, 2, 1)]
    legs = [task(0, 0, 1, task_id=4, leg="storage_in"),
            task(1, 1, 2, task_id=4, leg="storage_out")]
    p = case("ebs_causal_gate", nodes3, edges3, legs, enable_ebs_predecessor_gate=True)
    assert p["bags"][1]["admission"] == p["bags"][0]["finish"] == 5
    assert p["bags"][1]["release"] == 0
    p = case("ebs_gate_disabled", nodes3, edges3, legs, enable_ebs_predecessor_gate=False)
    assert p["bags"][1]["admission"] == 0
    p = case("ebs_unreachable_predecessor_retained", nodes3, [(1, 2, 1)], legs,
             enable_ebs_predecessor_gate=True)
    assert all(not b["admitted"] for b in p["bags"])
    assert p["bags"][1]["status"] == "predecessor_unplanned"
    try:
        module.plan(nodes3, edges3, legs[1:], {"enable_ebs_predecessor_gate": True})
    except ValueError:
        pass
    else:
        raise AssertionError("missing EBS predecessor accepted")

    zero_nodes = [(0, 0), (1, 0), (2, 0), (3, 0)]
    p = case("closed_zero_service_point", zero_nodes, edges,
             [task(0, 0, 3), task(1, 1, 3)], release_quantum=0, completion_quantum=0)
    assert p["bags"][1]["route"][1][1] > p["bags"][0]["route"][1][2]
    huge = [(0, 2, 1e12), (1, 2, 1e12), (2, 3, 1)]
    p = case("nextafter_large_travel_recomposition", zero_nodes, huge,
             [task(0, 0, 3), task(1, 1, 3)], release_quantum=0,
             completion_quantum=0, end_time=1e12 + 100)
    assert p["summary"]["planning_attempts"] < 10

    chain_nodes = [(i, 2 if 0 < i < 101 else 0) for i in range(102)]
    chain_edges = [(i, i + 1, 1) for i in range(101)]
    p = case("score_budget_is_per_node", chain_nodes, chain_edges, [task(0, 0, 101)],
             adaptive=False, max_score_expansions=4, max_expansions=200)
    b = p["bags"][0]
    assert b["score_expansions"] > 4
    assert all(decision[3] > 0 for decision in b["route_decisions"][:-1])

    p = case("search_cap_retains_unfinished", chain_nodes, chain_edges, [task(0, 0, 101)],
             max_expansions=2, max_retries=0)
    assert not p["bags"][0]["completed"] and p["bags"][0]["route"] == []
    assert p["summary"]["search_budget_failures"] == 1

    cyclic_edges = [(0, 1, 1), (1, 2, 1), (2, 0, 1), (2, 3, 1)]
    p = case("acyclic_certificate_on_cyclic_graph", zero_nodes, cyclic_edges, [task(0, 0, 3)])
    assert [n for n, _, _ in p["bags"][0]["route"]] == [0, 1, 2, 3]

    for invalid in ({"not_a_config": 1}, {"pressure_window": float("nan")},
                    {"max_depth": 0}, {"retry_mode": "invented"}):
        try:
            module.plan(nodes, edges, [], invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid config accepted: {invalid}")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    spec = importlib.util.spec_from_file_location("g31_nowait", args.binary.resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = run(module)
    source = Path(__file__).with_name("core.cpp")
    receipt = dict(status="passed", cases=len(records), records=records,
                   binary=str(args.binary.resolve()),
                   binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                   source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "cases": len(records), "output": str(args.output)}))


if __name__ == "__main__":
    main()

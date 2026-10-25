"""Integer-microsecond headway regressions plus exact legacy bag parity."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from test_core_micro import run as legacy_cases
from test_core_micro import task


def ticks(value):
    return round(value * 1_000_000)


def verify(payload, nodes, edges):
    service = {n: ticks(s) for n, s in nodes}
    travel = {(u, v): ticks(t) for u, v, t in edges}
    node_windows, edge_windows = {}, {}
    for bag in payload["bags"]:
        route = bag["route"]
        if not route:
            continue
        assert bag["admission"] >= bag["release"]
        assert len({r[0] for r in route}) == len(route)
        for i, (node, arrival, departure) in enumerate(route):
            a, d = ticks(arrival), ticks(departure)
            assert arrival == a / 1_000_000 and departure == d / 1_000_000
            assert d - a == service[node]
            if d > a:
                node_windows.setdefault(node, []).append((a, d, bag["segment_id"]))
            if i:
                prior = route[i - 1]
                assert a == ticks(prior[2]) + travel[prior[0], node]
                entry = ticks(prior[2])
                edge_windows.setdefault((prior[0], node), []).append((entry, entry + 2_000_000, bag["segment_id"]))
        expected_cleanup = max(bag["completion_epoch"], route[-1][2],
                               *(r[3] for r in bag["edge_resource_intervals"]))
        import math
        assert bag["resource_cleanup_epoch"] == math.ceil(expected_cleanup)
    for ledger in (node_windows, edge_windows):
        for resource, windows in ledger.items():
            windows.sort()
            for previous, current in zip(windows, windows[1:]):
                assert previous[1] <= current[0], (resource, previous, current)


def run(module):
    records = []

    def case(label, nodes, edges, tasks, **overrides):
        config = dict(end_time=100, interval_mode="half_open", strict_endpoint_resources=True,
                      edge_entry_headway_seconds=2, release_quantum=0, completion_quantum=1,
                      source_fifo=False, source_generation_interval=0,
                      audit_failed_calendar_hash=True, enable_ebs_predecessor_gate=False)
        config.update(overrides)
        result = module.plan(nodes, edges, tasks, config)
        verify(result, nodes, edges)
        records.append(dict(case=label, config=config, payload=result))
        return result

    p = case("touching_internal_2s_allowed", [(0,0),(1,0),(2,2),(3,0)],
             [(0,2,1),(1,2,1),(2,3,1)], [task(0,0,3),task(1,1,3)])
    assert [b["admission"] for b in p["bags"]] == [0,2]

    p = case("edge_entry_headway_is_not_whole_edge_capacity", [(0,0),(1,0)],
             [(0,1,10)], [task(0,0,1),task(1,0,1)])
    assert [b["admission"] for b in p["bags"]] == [0,2]
    assert p["bags"][1]["admission"] < p["bags"][0]["finish"]
    assert p["summary"]["failed_search_hash_checks"] >= 1

    p = case("positive_source_not_exempt", [(0,2),(1,0),(2,0)],
             [(0,1,1),(0,2,1)], [task(0,0,1),task(1,0,2)])
    assert [b["admission"] for b in p["bags"]] == [0,2]
    assert p["summary"]["source_resource_queries"] >= 3

    p = case("goal_kept_after_business_finish", [(0,0),(1,0),(2,2)],
             [(0,2,1),(1,2,1)], [task(0,0,2),task(1,1,2,1)])
    assert [b["admission"] for b in p["bags"]] == [0,2]
    assert p["bags"][0]["finish"] == 1 and p["bags"][0]["resource_cleanup_epoch"] == 3

    p = case("source_equals_goal_still_occupies_2s", [(0,2)], [],
             [task(0,0,0),task(1,0,0,1)])
    assert [b["admission"] for b in p["bags"]] == [0,2]
    assert p["bags"][0]["finish"] == 0 and p["bags"][0]["resource_cleanup_epoch"] == 2

    p = case("short_edge_tail_not_deleted_at_finish", [(0,0),(1,0)], [(0,1,.5)],
             [task(0,0,1),task(1,0,1,1)])
    assert [b["admission"] for b in p["bags"]] == [0,2]
    assert p["bags"][0]["finish"] == .5 and p["bags"][0]["resource_cleanup_epoch"] == 2

    p = case("zero_connector_no_node_occupancy", [(i,0) for i in range(5)],
             [(0,2,1),(1,2,1),(2,3,1),(2,4,1)], [task(0,0,3),task(1,1,4)])
    assert [b["admission"] for b in p["bags"]] == [0,0]
    assert all(not r[5] for b in p["bags"] for r in b["node_resource_intervals"])

    for release in (1.999999, 2.0):
        p = case(f"one_tick_boundary_{release}", [(0,0),(1,0)], [(0,1,10)],
                 [task(0,0,1),task(1,0,1,release)])
        assert p["bags"][1]["admission"] == 2
        assert p["bags"][1]["retries"] == (1 if release < 2 else 0)

    p = case("ebs_gate_and_shared_positive_storage_resource", [(0,0),(1,2),(2,0)],
             [(0,1,5),(1,2,1)],
             [task(0,0,1,task_id=7,leg="storage_in"),task(1,1,2,task_id=7,leg="storage_out")],
             enable_ebs_predecessor_gate=True)
    assert p["bags"][0]["finish"] == 5 and p["bags"][1]["admission"] == 7

    nodes = [(i, 2 if 0 < i < 8 else 0) for i in range(9)]
    edges = [(i,i+1,1) for i in range(8)]
    ordinary = case("single_choice_scoring_original", nodes, edges, [task(0,0,8)])
    skipped = case("single_choice_scoring_skipped", nodes, edges, [task(0,0,8)], skip_scoring_single_choice=True)
    assert ordinary["bags"][0]["route"] == skipped["bags"][0]["route"]
    assert skipped["summary"]["local_scoring_calendar_queries"] == 0

    try:
        module.plan([(0,0),(1,0)], [(0,1,.0000001)], [task(0,0,1)], {"interval_mode":"half_open"})
    except ValueError:
        pass
    else:
        raise AssertionError("sub-microsecond physical travel accepted")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--legacy-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    spec = importlib.util.spec_from_file_location("g31_nowait", args.binary.resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old_records = json.loads(args.legacy_receipt.read_text(encoding="utf-8"))["records"]
    new_records = legacy_cases(module)
    assert len(new_records) == len(old_records)
    fields = 0
    for old, new in zip(old_records, new_records):
        assert old["case"] == new["case"]
        for a, b in zip(old["bags"], new["bags"]):
            for key, value in a.items():
                assert json.dumps(b[key], sort_keys=True) == json.dumps(value, sort_keys=True), (old["case"], key, value, b[key])
                fields += 1
    records = run(module)
    source = Path(__file__).with_name("core.cpp")
    receipt = dict(status="passed", half_open_cases=len(records), legacy_cases=len(new_records),
                   legacy_old_bag_fields_exact=fields, records=records,
                   source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                   test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status":"passed", "half_open_cases":len(records), "legacy_old_bag_fields_exact":fields}))


if __name__ == "__main__":
    main()

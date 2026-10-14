"""Read raw window events and query receipts; no physics or controller calls."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
output = BASE / sys.argv[1]
output.mkdir()
cpu, wall = time.process_time(), time.perf_counter()
bindings = {}
checks = 0


def check(value, description):
    global checks
    checks += 1
    if not value:
        raise AssertionError(description)


def read(path):
    bindings[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_bytes())


def audit_raw(raw, tape, expected_trays):
    current = raw["final_snapshot"]
    now = current["now"]
    expected = {bag["bag_id"]: bag for bag in tape}
    observed = {key for key, bag in expected.items() if bag["arrival"] <= now}
    check(set(current["trays"]) == expected_trays, "original carrier identities")
    check(set(current["bags"]) == observed, "no hidden future/omitted observed bag")
    check(set(raw["completed"]) <= observed, "completion visibility")
    check(set(raw["uncompleted_bag_ids"]) == observed - set(raw["completed"]), "runtime observed unfinished identities")
    unobserved = set(expected) - observed
    check(set(raw["uncompleted_bag_ids"]) | unobserved == set(expected) - set(raw["completed"]), "full 44 denominator with explicit future scope")
    check(current["completed"] == raw["completed"], "raw completion agreement")
    load, ingress, depart, completed = {}, {}, {}, {}
    last_tick = -1
    ticks = []
    for event in raw["trace"]:
        at, kind = event["time"], event["event"]
        check(last_tick <= at <= now, "monotone trace")
        last_tick = at
        if kind == "tick":
            ticks.append(at)
        if "bag_id" in event:
            check(event["bag_id"] in observed and expected[event["bag_id"]]["arrival"] <= at, "public bag event")
        if "tray_id" in event:
            check(event["tray_id"] in expected_trays, "physical carrier event")
        if kind == "load":
            bag_id = event["bag_id"]
            check(bag_id not in load, "load once")
            load[bag_id] = event
        if kind == "storage_arrival":
            bag_id = event["bag_id"]
            check(bag_id in load and load[bag_id]["tray_id"] == event["tray_id"], "ingress same carrier")
            check(bag_id not in ingress, "one ingress event")
            ingress[bag_id] = event
        if kind == "storage_departure":
            bag_id = event["bag_id"]
            check(bag_id in ingress and ingress[bag_id]["tray_id"] == event["tray_id"], "departure actual ingress identity")
            check(at >= max(ingress[bag_id]["time"], expected[bag_id]["storage"]["release_at"]), "public release")
            check(bag_id not in depart, "one departure event")
            depart[bag_id] = event
        if kind == "unload_complete":
            bag_id = event["bag_id"]
            check(bag_id in depart and depart[bag_id]["tray_id"] == event["tray_id"], "completion follows real storage")
            check(at >= depart[bag_id]["time"] and bag_id not in completed, "final completion chronology")
            completed[bag_id] = at
    check(ticks == list(range(now + 1)), "every physical tick retained from epoch zero")
    check(completed == raw["completed"], "raw events prove completions")
    for bag_id, progress in current["storage_progress"].items():
        check(progress["arrived_at"] == ingress[bag_id]["time"], "saved ingress bound to actual event")
        check(progress["departed_at"] == (depart[bag_id]["time"] if bag_id in depart else None), "saved departure bound to event")
        check(progress["tray_id"] == load[bag_id]["tray_id"], "saved same carrier")
    return {"now": now, "expected": len(expected), "observed": len(observed),
            "unobserved": len(unobserved), "full_window_unfinished": len(expected) - len(completed),
            "loaded": len(load), "completed": len(completed), "ingress": len(ingress), "departure": len(depart),
            "cost": raw["total_cost"], "events": dict(Counter(event["event"] for event in raw["trace"]))}


rows = []
try:
    for name in sys.argv[2:]:
        folder = BASE / name
        report = read(folder / "results.json")
        check(report["success"] and not report["source_changed"], "execution and frozen source")
        check(read(folder / "before.json") == read(folder / "after.json"), "all bound source bytes unchanged")
        scope = read(folder / "scope.json")
        check(scope["included_count"] == 44 and scope["full_source_count"] == 28506, "declared scope")
        tape = read(folder / "environment_tape.json")
        check(len(tape) == 44 and len({b["bag_id"] for b in tape}) == 44, "full identity set")
        check(all(b.get("storage") for b in tape), "all first-hour tasks early")
        initial = read(folder / "initial_snapshot.json")
        trays = set(initial["trays"])
        check(len(trays) == 11, "finite inventory")
        raw = read(folder / "final_result.json.gz")
        row = {"name": name, "status": report["status"], "final": audit_raw(raw, tape, trays), "matched": []}
        for tick, old_name in ((10080, "business_window_h21600_003"), (11760, "business_window_h80_003")):
            path = folder / f"matched_{tick}.json.gz"
            if path.exists():
                at = read(path)
                summary = audit_raw(at, tape, trays)
                baseline = read(BASE.parent / "phase4_round9_storage_lifecycle_20261011" / old_name / "final_result.json.gz")
                check(baseline["final_snapshot"]["now"] == tick == summary["now"], "same physical comparison tick")
                row["matched"].append({"new": summary, "old_name": old_name,
                    "same_horizon": ("h21600" in name) == ("h21600" in old_name),
                    "old_completed": len(baseline["completed"]), "old_cost": baseline["total_cost"],
                    "qualification": "descriptive development comparison, not independent confirmation or full-window quality"})
        statuses, per_bag = Counter(), defaultdict(Counter)
        actual, reused, expansions = Counter(), Counter(), 0
        query_path = folder / "queries.jsonl.gz"
        bindings[query_path.relative_to(ROOT).as_posix()] = hashlib.sha256(query_path.read_bytes()).hexdigest()
        with gzip.open(query_path, "rt", encoding="utf-8") as stream:
            for line in stream:
                q = json.loads(line)
                statuses[q["status"]] += 1
                per_bag[q["bag_id"] or "empty"][q["status"]] += 1
                check(q["now"] <= raw["final_snapshot"]["now"], "query chronology")
                if q["bag_id"]:
                    check(q["bag_id"] in {b["bag_id"] for b in tape}, "query identity")
                    check(q["now"] >= next(b["arrival"] for b in tape if b["bag_id"] == q["bag_id"]), "no future query")
                d = q["diagnostics"]
                if d.get("storage_mode"):
                    check(sum(d["work_units_by_stage"].values()) == q["expansions"], "storage logical budget accounted")
                c = d.get("cache_accounting", {})
                actual.update(c.get("actual_preprocessing_work", {}))
                reused.update(c.get("reused_preprocessing_work", {}))
                expansions += q["expansions"]
        check(dict(statuses) == report["search_status_counts"], "raw query totals")
        check(sum(statuses.values()) + report.get("initial_generation_calls", 0) == raw["policy_stats"]["generation_calls"], "all new generation calls logged")
        row.update(query_statuses=dict(statuses), per_bag={k: dict(v) for k, v in per_bag.items()},
                   actual_preprocessing=dict(actual), reused_preprocessing=dict(reused), logical_expansions=expansions)
        rows.append(row)
    outcome = {"status": "passed", "rows": rows}
except Exception:
    outcome = {"status": "failed", "rows": rows, "exception": traceback.format_exc()}
outcome.update(checks=checks, physical_runs=0, cpu_seconds=time.process_time()-cpu,
               wall_seconds=time.perf_counter()-wall, input_sha256=bindings,
               source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               resource_scope="read-only process; final receipt serialization excluded")
(output / "results.json").write_text(json.dumps(outcome, indent=2))
print(json.dumps({k: v for k, v in outcome.items() if k not in ("rows", "input_sha256")}, indent=2))
raise SystemExit(0 if outcome["status"] == "passed" else 1)

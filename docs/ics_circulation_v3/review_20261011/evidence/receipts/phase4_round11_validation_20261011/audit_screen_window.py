"""Read raw window events and query receipts; no physics or controller calls."""
from collections import Counter, defaultdict
from itertools import zip_longest
import math
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
(output / "audit_source.py").write_bytes(Path(__file__).read_bytes())
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
        variant = read(folder / "protocol.json")["only_variant"]
        projection_evidence = read(folder / "projection_runtime_evidence.json") if variant == "projected" else None
        old_base = BASE.parent / "phase4_round10_validation_20261011"
        horizon = read(folder / "protocol.json")["search_horizon"]
        original_tape = read(old_base / f"business_window_h{horizon}_001" / "environment_tape.json")
        original_tasks = read(old_base / f"business_window_h{horizon}_001" / "full_window_source_tasks.json")
        source_tasks = read(folder / "full_window_source_tasks.json")
        check(source_tasks == original_tasks, "all original task/provenance fields preserved")
        check(initial == read(old_base / f"business_window_h{horizon}_001" / "initial_snapshot.json"), "same full initial physical state")
        old_by_id = {b["bag_id"]: b for b in original_tape}
        if variant == "projected":
            groups = read(BASE.parent / "phase4_round10_business_projection_20261011/full_audit_002/flight_projection_1x.json")
            expected_final = {bid: g["projected_destination"] for g in groups for bid in g["business_bag_ids"]}
            changed = 0
            for bag in tape:
                old_bag = old_by_id[bag["bag_id"]]
                check(bag["destination"] == expected_final[bag["bag_id"]], "frozen full-parent projection final")
                check({k: v for k, v in bag.items() if k != "destination"} ==
                      {k: v for k, v in old_bag.items() if k != "destination"}, "runtime changes only declared final")
                changed += bag["destination"] != old_bag["destination"]
            row["changed_destination_count"] = changed
            row["qualification"] = "Different declared input version, not same-OD algorithm improvement"
        else:
            check(tape == original_tape, "old runtime input tape unchanged")
        for tick in (10080, 11640, 11760, 24180, 28500):
            path = folder / f"matched_{tick}.json.gz"
            if path.exists():
                at = read(path)
                summary = audit_raw(at, tape, trays)
                prior = old_base / f"business_window_h{horizon}_001" / f"matched_{tick}.json.gz"
                if tick == 24180 and horizon == 21600:
                    prior = old_base / "business_window_h21600_001/final_result.json.gz"
                elif tick == 28500 and horizon == 21600:
                    prior = old_base / "business_window_h21600_tail_001/final_result.json.gz"
                baseline = read(prior) if prior.exists() else None
                if baseline is not None and variant == "original":
                    check(at == baseline, "strict old/new original physical result at common tick")
                row["matched"].append({"new": summary,
                    "old_completed": len(baseline["completed"]) if baseline else None,
                    "old_cost": baseline["total_cost"] if baseline else None,
                    "strict_same_original": at == baseline if variant == "original" and baseline else None,
                    "qualification": "Same tick descriptive comparison; projected final version differs"})
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
                c = d.get("cache_accounting") or {}
                actual.update(c.get("actual_preprocessing_work", {}))
                reused.update(c.get("reused_preprocessing_work", {}))
                expansions += q["expansions"]
        check(dict(statuses) == report["search_status_counts"], "raw query totals")
        check(sum(statuses.values()) + report.get("initial_generation_calls", 0) == raw["policy_stats"]["generation_calls"], "all new generation calls logged")
        row.update(query_statuses=dict(statuses), per_bag={k: dict(v) for k, v in per_bag.items()},
                   actual_preprocessing=dict(actual), reused_preprocessing=dict(reused), logical_expansions=expansions)
        check(report["screen_accounting"]["rows_streamed"], "streaming declared")
        work, screened, row_count, screen_cpu, observation_cpu = 0, 0, 0, 0., 0.
        screen_path = folder / "screen_rows.jsonl.gz"
        bindings[screen_path.relative_to(ROOT).as_posix()] = hashlib.sha256(screen_path.read_bytes()).hexdigest()
        with gzip.open(query_path, "rt", encoding="utf-8") as qf, gzip.open(screen_path, "rt", encoding="utf-8") as sf:
            for index, (ql, sl) in enumerate(zip_longest(qf, sf), 1):
                check(ql is not None and sl is not None, "one screen row per runtime query")
                q, s = json.loads(ql), json.loads(sl)
                check(q["query_id"] == s["query_id"] == index, "continuous joined query IDs")
                check(q["now"] == s["time"] and q["tray_id"] == s["tray_id"] and q["bag_id"] == s["bag_id"], "joined query identity")
                check(s["requested_k"] == 1 and s["phase"] == "returned" and s["error"] is None, "actual original K1 and successful return")
                check(s["search_status"] == q["status"] and s["search_work"] == q["expansions"], "joined search receipt")
                check(s["certificate"] == q["diagnostics"]["terminal_screen"], "joined certificate")
                check(0 <= s["search_work"] <= 10000, "unchanged inner search budget")
                check(q["candidate_count"] <= len(s["options"]) <= 1, "raw and authorized K1 counts")
                cert = s["certificate"]
                if cert["certified"]:
                    screened += 1
                    check(s["search_work"] == 0 and not s["options"] and q["candidate_count"] == 0, "certificate skips only empty query")
                    check(q["status"] == "terminal_capacity_certificate", "certified status")
                work += cert["screen_work"]
                screen_cpu += cert["screen_cpu_seconds"]
                observation_cpu += s["observation_cpu_seconds"]
                row_count += 1
        check(work == report["screen_accounting"]["screen_work"], "complete extra work total")
        check(math.isclose(screen_cpu, report["screen_accounting"]["screen_cpu_seconds_nested"]), "complete nested screen CPU")
        check(math.isclose(observation_cpu, report["screen_accounting"]["observation_cpu_seconds_nested"]), "complete nested observation CPU")
        prior_folder = BASE / "projected_h21600_001"
        bridge = []
        for tick, prior_name in ((10080, "matched_10080.json.gz"), (11640, "final_result.json.gz")):
            same_tick = folder / f"matched_{tick}.json.gz"
            if same_tick.exists():
                current_raw = read(same_tick)
                prior_raw = read(prior_folder / prior_name)
                check(current_raw == prior_raw, "same projected input, full physical result equality at " + str(tick))
                bridge.append(dict(tick=tick, strict_equal=True, field_scope="all physical_result fields; only policy *_ms excluded by producer"))
        row.update(screen_rows=row_count, certified_queries=screened, additional_screen_work=work,
                   screen_cpu_seconds_nested=screen_cpu, observation_cpu_seconds_nested=observation_cpu,
                   same_input_physical_bridges=bridge)
        prior_query_path = prior_folder / "queries.jsonl.gz"
        bindings[prior_query_path.relative_to(ROOT).as_posix()] = hashlib.sha256(prior_query_path.read_bytes()).hexdigest()
        common_queries = old_work = new_work = prefix_screen_work = replaced_queries = 0
        replacement_statuses = Counter()
        with gzip.open(prior_query_path, "rt", encoding="utf-8") as old_stream, gzip.open(query_path, "rt", encoding="utf-8") as new_stream:
            for line in old_stream:
                old_q = json.loads(line)
                new_line = next(new_stream, None)
                check(new_line is not None, "entire old query prefix preserved")
                new_q = json.loads(new_line)
                check(all(new_q[k] == old_q[k] for k in ("now", "tray_id", "bag_id", "destination", "candidate_count")), "same prefix query and authorized candidate count")
                check(new_q["now"] <= 11640, "common prefix tick bound")
                cert = new_q["diagnostics"]["terminal_screen"]
                if cert["certified"]:
                    check(old_q["candidate_count"] == new_q["candidate_count"] == 0, "screen only replaces old empty return")
                    replaced_queries += 1
                    replacement_statuses[old_q["status"]] += 1
                else:
                    check(old_q["status"] == new_q["status"] and old_q["expansions"] == new_q["expansions"], "delegated prefix logical result unchanged")
                common_queries += 1
                old_work += old_q["expansions"]
                new_work += new_q["expansions"]
                prefix_screen_work += cert["screen_work"]
        row["common_prefix_query_bridge"] = dict(through_tick=11640, queries=common_queries,
            original_search_work=old_work, screened_search_work=new_work, additional_screen_work=prefix_screen_work,
            replaced_empty_queries=replaced_queries, replaced_statuses=dict(replacement_statuses),
            qualification="identical query identities/times/authorized counts and entire physical_result at saved ticks; old stream lacks raw ordered candidates, so this is not a full raw-candidate stream identity claim; no equal-instrument timing benchmark")
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

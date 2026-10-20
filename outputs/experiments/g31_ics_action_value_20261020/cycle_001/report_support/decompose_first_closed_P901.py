"""Read only the six explicitly released P901 runs; never launch native or fit."""
import collections
import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path

CYCLE = Path(__file__).resolve().parent.parent
NAMES = ["D_N22_C00_P901_001", "D_N22_C10_P901_001"] + [
    f"D_N22_C01_S{s}_P901_001" for s in (17, 29, 43)
] + ["D_N22_C11_S17_P901_001"]
START, END, POPULATION = 7200.0, 59400.0, 28506
BINS = ((7200, 14400), (14400, 28800), (28800, 43200), (43200, 59400))


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def semantic_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def integral(arrival, finish, start=START, end=END):
    return max(0.0, min(finish, end) - max(arrival, start))


def population_metrics(specs, loads, ends, start=START, end=END):
    total = math.fsum(integral(s["arrival"], ends.get(k, math.inf), start, end)
                      for k, s in specs.items())
    waiting = math.fsum(integral(s["arrival"], loads.get(k, math.inf), start, end)
                        for k, s in specs.items())
    return {
        "offered": len(specs),
        "arrived": sum(s["arrival"] <= end for s in specs.values()),
        "J_bag_seconds": total,
        "waiting_integral_bag_seconds": waiting,
        "loaded_or_processing_integral_bag_seconds": total - waiting,
        "completed": sum(ends.get(k, math.inf) <= end for k in specs),
        "on_time": sum(ends.get(k, math.inf) <= min(s["deadline"], end) for k, s in specs.items()),
        "arrived_unfinished_past_deadline": sum(
            s["arrival"] <= end and s["deadline"] < end and ends.get(k, math.inf) > end
            for k, s in specs.items()),
    }


def load_run(name):
    directory = CYCLE / name
    receipt, plan = read(directory / "receipt.json"), read(directory / "plan.json")
    assert receipt["status"] == "complete"
    data, result = read(directory / "input.json"), read(directory / "final_result.json.gz")
    assert result["physical_clock"] == END
    assert result["advance"]["status"] == "reached" and result["advance"]["horizon_complete"]
    specs = {s["business_bag_id"]: s for s in data["jobs"]}
    jobs = {s["business_bag_id"]: s for s in result["jobs"]}
    assert len(specs) == len(data["jobs"]) == len(jobs) == len(result["jobs"]) == POPULATION
    assert set(specs) == set(jobs)
    events = {}
    for event in ("BAG_ARRIVAL", "LOAD_START", "UNLOAD_COMPLETE"):
        rows = [r for r in result["receipts"] if r["event"] == event]
        mapping = {r["business_bag_id"]: r["time"] for r in rows}
        assert len(mapping) == len(rows)
        assert all(k in specs and 0 <= t <= END for k, t in mapping.items())
        events[event] = mapping
    arrivals, loads, ends = (events[e] for e in ("BAG_ARRIVAL", "LOAD_START", "UNLOAD_COMPLETE"))
    for identity, spec in specs.items():
        assert (identity in arrivals) == (spec["arrival"] <= END)
        if identity in arrivals:
            assert arrivals[identity] == spec["arrival"]
        exported = jobs[identity]["completed_at"]
        assert (identity in ends) == (exported >= 0) == (jobs[identity]["status"] == "completed")
        if identity in ends:
            assert spec["arrival"] <= loads[identity] <= ends[identity] == exported <= END
        if jobs[identity]["status"] not in ("waiting_for_tray", "unreleased"):
            assert identity in loads
    total = population_metrics(specs, loads, ends)
    saved = read(directory / "evaluation.json")["cost"]
    for derived, field in (
        ("J_bag_seconds", "backlog_integral_bag_seconds"),
        ("waiting_integral_bag_seconds", "waiting_for_tray_integral_bag_seconds"),
        ("loaded_or_processing_integral_bag_seconds", "loaded_or_processing_integral_bag_seconds"),
        ("completed", "completed_by_end"), ("on_time", "on_time_by_end"),
    ):
        assert abs(total[derived] - saved[field]) < 1e-6, (name, field)
    origins = sorted({s["origin"] for s in specs.values()})
    calls = read(directory / "client_calls.json.gz")
    transfers = [x for x in calls if x["kind"] == "transfer" and not x.get("retry", False)]
    transfers.sort(key=lambda x: (x["at"], x["request"]["owner_id"],
                                 x["request"]["tray_id"], x["request"]["request_id"]))
    return {
        "name": name, "specs": specs, "loads": loads, "ends": ends, "result": result,
        "transfers": transfers, "execution": read(directory / "execution_evidence.json.gz"),
        "total": total,
        "origins": {o: population_metrics({k: s for k, s in specs.items() if s["origin"] == o},
                                         loads, ends) for o in origins},
        "bins": [{"start": a, "end": b, **population_metrics(specs, loads, ends, a, b)}
                 for a, b in BINS],
        "bindings": {
            "binary_sha256": plan["binary"]["sha256"], "sources": plan["sources"],
            "input_jobs_semantic_sha256": semantic_digest(data["jobs"]),
            "initial_trays_semantic_sha256": semantic_digest(data["trays"]),
            "input": pin(directory / "input.json"),
            "final_result": pin(directory / "final_result.json.gz"),
            "evaluation": pin(directory / "evaluation.json"),
            "actual_client_calls": pin(directory / "client_calls.json.gz"),
            "execution_evidence": pin(directory / "execution_evidence.json.gz"),
            "plan": pin(directory / "plan.json"), "receipt": pin(directory / "receipt.json"),
        },
    }


def improvement(reference, candidate):
    return {
        "J_gain_bag_seconds": reference["J_bag_seconds"] - candidate["J_bag_seconds"],
        "waiting_gain_bag_seconds": reference["waiting_integral_bag_seconds"]
            - candidate["waiting_integral_bag_seconds"],
        "loaded_or_processing_gain_bag_seconds": reference["loaded_or_processing_integral_bag_seconds"]
            - candidate["loaded_or_processing_integral_bag_seconds"],
        "completed_delta": candidate["completed"] - reference["completed"],
        "on_time_delta": candidate["on_time"] - reference["on_time"],
        "arrived_unfinished_past_deadline_delta": candidate["arrived_unfinished_past_deadline"]
            - reference["arrived_unfinished_past_deadline"],
    }


def actual_waiting(run, time, origin=None):
    return sum(s["arrival"] <= time < run["loads"].get(k, math.inf)
               for k, s in run["specs"].items() if origin is None or s["origin"] == origin)


def request_semantics(call):
    r = call["request"]
    return {k: r[k] for k in (
        "owner_id", "tray_id", "source", "destination", "transfer_scope", "earliest_departure")}


def first_divergence(reference, candidate):
    groups = []
    for run in (reference, candidate):
        grouped = collections.defaultdict(list)
        for call in run["transfers"]:
            grouped[call["at"]].append(call)
        groups.append(grouped)
    for at in sorted(set(groups[0]) | set(groups[1])):
        calls = [g.get(at, []) for g in groups]
        signatures = [[request_semantics(x) for x in group] for group in calls]
        if signatures[0] == signatures[1]:
            continue
        return {
            "first_actual_transfer_difference_at": at,
            "selection": "Earliest chronological non-retry actual transfer batch difference; no outcome-selected witness.",
            "reference_actual_submissions": calls[0], "candidate_actual_submissions": calls[1],
            "reference_waiting_bags_at_difference": actual_waiting(reference, at),
            "candidate_waiting_bags_at_difference": actual_waiting(candidate, at),
            "candidate_destinations_waiting_at_difference": {
                str(call["request"]["destination"]): actual_waiting(candidate, at, call["request"]["destination"])
                for call in calls[1]},
            "single_action_causal_attribution": False,
        }
    return {"status": "no_actual_transfer_difference"}


def per_job(reference, candidate):
    counts = collections.Counter()
    for identity in reference["specs"]:
        a, b = reference["ends"].get(identity), candidate["ends"].get(identity)
        category = "unknown_incomplete" if a is None or b is None else (
            "harmed" if b-a > 1e-6 else "improved" if a-b > 1e-6 else "equal")
        counts[category] += 1
    assert sum(counts.values()) == POPULATION
    return {k: counts[k] for k in ("improved", "harmed", "equal", "unknown_incomplete")}


def direct_service_diagnostic(run, baselines):
    counters = collections.Counter()
    rows, all_changed = [], []
    for selected in sorted(run["execution"]["rows"],
                           key=lambda x: (x["observed_at"], x["audit_sequence"])):
        if not selected["decision_differs"]:
            continue
        counters["changed_decision_rows"] += 1
        for attempt in selected["attempts"]:
            request = attempt["actual_request"]
            row = {"audit_sequence": selected["audit_sequence"], "observed_at": selected["observed_at"],
                   "request_id": request["request_id"], "tray_id": request["tray_id"],
                   "source": request["source"], "destination": request["destination"],
                   "received_at": attempt.get("received_at"), "next_load": attempt.get("next_load"),
                   "saved_complete_G1_execution_chain": attempt.get("complete_G1_execution_chain"),
                   "global_waiting_at_decision": actual_waiting(run, selected["observed_at"]),
                   "destination_waiting_at_decision": actual_waiting(
                       run, selected["observed_at"], request["destination"])}
            all_changed.append(row)
            if attempt.get("complete_G1_execution_chain") is not True:
                counters["attempt_without_saved_complete_entity_chain"] += 1
                continue
            received, load = attempt.get("received_at"), attempt.get("next_load")
            if received is None or not load:
                counters["missing_receipt_or_next_load"] += 1
                continue
            if load["node"] != request["destination"]:
                counters["next_load_at_different_destination"] += 1
                continue
            intervening = [x for x in run["result"]["receipts"]
                           if x["event"] == "LEG_START" and x["tray_id"] == request["tray_id"]
                           and received < x["time"] < load["time"]
                           and ":empty_return:" in x.get("transport_leg_id", "")]
            if intervening:
                counters["intervening_empty_reposition_before_load"] += 1
                continue
            identity = load["business_bag_id"]
            arrival = run["specs"][identity]["arrival"]
            phase = "received_before_next_served_bag_arrival" if received < arrival else "received_after_bag_arrival"
            counters[phase] += 1
            row = dict(row, business_bag_id=identity, arrival=arrival,
                       direct_service_phase=phase, own_wait_seconds=load["time"]-arrival,
                       baseline_wait_comparisons={})
            for baseline in baselines:
                base_load = baseline["loads"].get(identity)
                row["baseline_wait_comparisons"][baseline["name"]] = {
                    "reference_load_time": base_load,
                    "wait_gain_seconds": None if base_load is None else base_load-load["time"],
                    "status": "known_actual_load_times" if base_load is not None else "unknown_reference_not_loaded"}
            rows.append(row)
    return {
        "counts": dict(counters), "all_strict_direct_service_rows": rows,
        "first_changed_actual_attempt": all_changed[0] if all_changed else None,
        "first_change_selection_is_chronological": True,
        "definition": "Changed executed allocations only; actual receipt then first load at the requested destination, without an intervening empty-return leg. Prearrival is a timing fact, not a causal or aggregate gain claim.",
        "saved_chain_flags_independently_reaudited_here": False,
        "full_native_chain_audit_owner": "prepared_features independent audit",
    }


def main():
    runs = {name: load_run(name) for name in NAMES}
    reference = runs[NAMES[0]]
    for run in runs.values():
        for key in ("binary_sha256", "sources", "input_jobs_semantic_sha256",
                    "initial_trays_semantic_sha256"):
            assert run["bindings"][key] == reference["bindings"][key], key
    candidate = runs[NAMES[-1]]
    comparisons = []
    pairs = [(runs[NAMES[0]], candidate), (runs[NAMES[1]], candidate)] + [
        (reference, runs[f"D_N22_C01_S{s}_P901_001"]) for s in (17, 29, 43)]
    for ref, cand in pairs:
        total = improvement(ref["total"], cand["total"])
        comparisons.append({
            "reference": ref["name"], "candidate": cand["name"], "total": total,
            "relative_J_gain": total["J_gain_bag_seconds"] / ref["total"]["J_bag_seconds"],
            "per_origin": [{"origin": o, **improvement(ref["origins"][o], cand["origins"][o])}
                           for o in ref["origins"]],
            "fixed_time_bins": [{"start": a["start"], "end": a["end"], **improvement(a, b)}
                               for a, b in zip(ref["bins"], cand["bins"])],
            "per_job_completion_comparison": per_job(ref, cand),
            "first_actual_allocation_divergence": first_divergence(ref, cand),
            "interpretation": "Whole-policy rollout comparison after possible repeated allocations; not a single-action causal contrast.",
        })
    report = {
        "schema": "g31.airport.first_closed_P901_operational_decomposition.v1",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "script": pin(Path(__file__)), "status": "exploratory_partial_grid_closed_run_decomposition",
        "allowed_runs": NAMES, "other_DG_outcomes_read": False,
        "population": POPULATION, "cost_window": [START, END],
        "metric_scope": "Full offered population. Waiting ends at actual LOAD_START; loaded_or_processing includes transport/storage/service until actual UNLOAD_COMPLETE and is not merely moving time. Unknown completions are right-censored only for finite-window integrals.",
        "same_frozen_source_binary_jobs_and_tray_initialization_verified": True,
        "runs": [{"name": x["name"], "total": x["total"],
                  "per_origin": [{"origin": o, **m} for o, m in x["origins"].items()],
                  "fixed_time_bins": x["bins"], "bindings": x["bindings"]} for x in runs.values()],
        "comparisons": comparisons,
        "C11_seed17_direct_service_diagnostic": direct_service_diagnostic(
            candidate, [runs[NAMES[0]], runs[NAMES[1]]]),
        "conclusions": [
            "C11S17 reduces total unfinished integral and increases completions versus both C10 and C00 on this parent, but on-time completions fall by1 and2 respectively.",
            "The largest gain occurs at origin149, accompanied by large loss at origin57 and smaller losses at26/95. This is a service allocation tradeoff, not uniform improvement.",
            "Most net J gain is reduced waiting-for-tray integral; loaded/processing changes are smaller. Higher completions at one origin do not certify individual service nonharm.",
            "First C11 changed transfer occurs at7200 before current backlog, but its next load is at another node after further movement; that first hop alone does not show direct prearrival service benefit.",
            "Direct prearrival receipt and same-bag wait comparison are reported separately. Already-waiting bags served after reallocation are not labeled anticipatory benefit.",
            "All three released C01 seeds are retained as context; no best seed is selected. All findings remain exploratory until the registered grid is closed and reviewed.",
        ],
        "independent_real_airport_days": 0, "conditional_synthetic_parent_count": 1,
        "new_fits": 0, "native_starts": 0, "policy_changes": False,
        "strict_nonharm_certified": False, "single_action_causal_attribution": False,
    }
    output = CYCLE / "report_support/D_P901_first_closed_operational_decomposition_001.json"
    with output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"artifact": pin(output),
                      "direct_service_counts": report["C11_seed17_direct_service_diagnostic"]["counts"],
                      "comparisons": [{"reference": x["reference"], "candidate": x["candidate"],
                                       **x["total"]} for x in comparisons]}, indent=2))


if __name__ == "__main__":
    main()

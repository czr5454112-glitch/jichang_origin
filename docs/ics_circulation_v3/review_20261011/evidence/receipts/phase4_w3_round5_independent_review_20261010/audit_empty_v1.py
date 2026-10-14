"""Independent raw-file audit for all empty-control comparison cases."""
from collections import Counter
from hashlib import sha256
import argparse
import gzip
import json
from pathlib import Path
from time import perf_counter, process_time

from audit_round5_full_cycle import Audit, ROOT, read, file_hash


def public_proxy(forecasts, observed, now, horizon):
    latest = {}
    for forecast in forecasts:
        if forecast["published_at"] <= now:
            old = latest.get(forecast["forecast_id"])
            if old is None or old["published_at"] < forecast["published_at"]:
                latest[forecast["forecast_id"]] = forecast
    result = []
    for forecast in latest.values():
        if now - forecast["published_at"] > 60:
            continue
        at = max(now + 1, forecast["at"])
        if at > horizon:
            continue
        identities = forecast["unit_ids"] or [forecast["forecast_id"] + ":" + str(i) for i in range(forecast["count"])]
        for identity in identities:
            if identity not in observed:
                result.append({"bag_id": identity, "origin": forecast["node"], "destination": forecast["destination"],
                    "arrival": at, "deadline": forecast["deadline"], "protected": False})
    return sorted(result, key=lambda b: (b["arrival"], b["bag_id"]))


def action_key(sequence):
    return sorted((p["tray_id"], p["destination_node"],
        tuple((leg["edge_id"], leg["depart"], leg["arrive"]) for leg in p["legs"]), p["usable_at"]) for p in sequence)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    folder = args.run.resolve()
    wall, cpu = perf_counter(), process_time()
    audit = Audit()
    protocol, inputs, summary = [read(folder / name) for name in ("protocol.json", "inputs.json", "summary.json")]
    audit.bind(folder / "protocol.json", summary["protocol_sha256"])
    audit.bind(folder / "inputs.json", summary["inputs_sha256"])
    audit.bind(folder / "summary.json")
    for name, expected in protocol["source_sha256"].items():
        audit.bind(folder / "source_snapshot" / name, expected)
        audit.bind(ROOT / "scripts/experiments/ics_circulation_v3" / name, expected)
    sources = {(r["scene"], r["tape"]): r for r in inputs}
    expected_ids = {f"s{r['scene_index']}_t{r['tape_index']}_{p}" for r in inputs for p in protocol["policies"]}
    rows = summary["rows"]
    audit.check(len(rows) == len(expected_ids) == protocol["planned_episodes"] == summary["recorded_episodes"], folder, "episode denominator mismatch")
    audit.check({r["identity"] for r in rows} == expected_ids, folder, "predeclared episode identities differ")
    audit.check(summary["statuses"] == dict(Counter(r["status"] for r in rows)), folder, "status counts differ")
    legacy_failed, true_slow_calls, proxy_rows = 0, 0, 0
    for row in rows:
        where = row["identity"]
        source = sources[row["scene"], row["tape"]]
        path = folder / "cases" / row["file"]
        audit.bind(path, row["sha256"])
        body = read(path)
        audit.check(all(body[k] == row[k] for k in ("identity", "scene", "tape", "policy")), where, "case identity differs")
        if row["status"] in {"execution_failure", "worker_failure"}:
            audit.check("failure" in body and "final" not in row, where, "failed episode hides failure or invents final metrics")
            continue
        ledger = dict(source["initial"]["bags"])
        ledger.update((b["bag_id"], b) for b in source["actual_tasks_event_engine_only"])
        expiry = max((f["published_at"] + 61 for f in source["published_forecasts"]), default=source["initial"]["now"])
        audit.check(body["forecast_expired_at"] == expiry, where, "forecast cutoff differs")
        for name, endpoint in body["endpoints"].items():
            audit.result(endpoint["result"], ledger, where + ":" + name)
            metrics, result = endpoint["metrics"], endpoint["result"]
            complete = result["completed"]
            audit.check(row[name] == metrics and body["metrics"][name] == metrics, where, "summary endpoint differs from raw metrics")
            audit.check(metrics["scheduled"] == len(ledger) and metrics["completed"] == len(complete), where, "completion denominator differs")
            audit.check(metrics["on_time"] == sum(k in complete and complete[k] <= b["deadline"] for k, b in ledger.items()), where, "on-time count differs")
            audit.check(set(metrics["unfinished"]) == set(ledger) - set(complete), where, "full unfinished denominator differs")
        if row["status"] == "controller_quiescent":
            marker = body["milestones"]["controller_quiescent"]
            adapted = {"result": body["endpoints"]["final"]["result"],
                "last_cycle_state": body["endpoints"]["final"]["cycle"], "stopped_at": row["stopped_at"],
                "milestones": {"controller_quiescent": {**marker, "actual_slow_triggers_since": marker["actual_slow_triggers"]}}}
            audit.drained(adapted, ledger, expiry, where)
        for item in body["slow_history"]:
            diag, now = item["diagnostics"], item["trigger_time"]
            calls = diag.get("rollout_calls", 0)
            true_slow_calls += calls
            if row["policy"] == "legacy_empty12":
                failed = len(diag.get("failed_proxy_rollouts", []))
                legacy_failed += failed
                audit.check(calls == len(diag.get("scored_actions", [])) + failed, where, "legacy attempted rollout count differs")
            if not row["policy"].startswith("empty"):
                continue
            settings = diag["settings"]
            expected_publications = [f for f in source["published_forecasts"] if f["published_at"] <= now]
            audit.check(diag["published_forecasts"] == expected_publications, where, "new control received wrong/unpublished forecasts")
            audit.check(diag["next_slow_trigger_at"] == now + protocol["spec"]["slow_period"], where, "slow phase reset/duplicate")
            expected_stage = 4 if protocol["spec"]["coordination_order"] == "route_then_prebalance" else 2
            audit.check(diag["cursor"]["stage_index"] == expected_stage and diag["cursor"]["pending_options"] is None, where, "incorrect post-slow public cursor")
            scored = diag["scored_actions"]
            if diag["status"] == "identical_no_demand_action":
                audit.check(not scored and calls == 0 and diag["selected_proxy_cost"] is None and not item["proposals"], where, "no-demand omission invents a scored outcome")
                continue
            observed = {k for k, b in ledger.items() if b["arrival"] <= now}
            expected_proxy = public_proxy(source["published_forecasts"], observed, now, now + settings["score_horizon"])
            audit.check(diag["proxy_bags"] == expected_proxy, where, "proxy is not reconstructed solely from published inputs")
            audit.check(len(scored) == calls and 2 <= calls <= settings["max_rollouts"], where, "mandatory/equal rollout budget differs")
            audit.check(scored[0]["kind"] == "greedy_incumbent" and scored[1]["kind"] == "no_transfer" and scored[1]["proposals"] == [], where, "mandatory alternatives absent")
            selected = diag["selected_action_index"]
            expected_selected = 0
            if scored[0]["status"] == "complete":
                best = scored[0]["proxy_cost"]
                for index, candidate in enumerate(scored[1:], 1):
                    if candidate["status"] == "complete" and candidate["proxy_cost"] < best - 1e-9:
                        expected_selected, best = index, candidate["proxy_cost"]
                audit.check(not diag["fallback_to_greedy"] and diag["selected_proxy_cost"] == scored[selected]["proxy_cost"], where, "complete incumbent selection reports wrong value")
            else:
                audit.check(diag["fallback_to_greedy"] and diag["selected_proxy_cost"] is None, where, "incomplete incumbent not safely retained")
            audit.check(selected == expected_selected and item["proposals"] == scored[selected]["proposals"], where, "selected sequence differs from legal recorded candidate/score rule")
            audit.check(diag["actual_sequence_changed"] == (action_key(item["proposals"]) != action_key(scored[0]["proposals"])), where, "reported incumbent change differs")
            for candidate in scored:
                proxy_rows += 1
                audit.check(candidate["search_calls"] == len(candidate["searches"]) <= settings["branch_search_calls"], where, "proxy call budget differs")
                audit.check(candidate["search_work"] == sum(q["work"] for q in candidate["searches"]), where, "proxy work ledger differs")
                audit.check(candidate["search_work"] - (candidate["searches"][-1]["work"] if candidate["searches"] else 0) < settings["branch_search_work"], where, "work cap failed before final allowed query")
                if candidate["status"] != "complete":
                    audit.check(candidate["proxy_cost"] is None, where, "censored projection used an objective")
        if row["policy"] == "public_fast4":
            for item in body["public_rollouts"]:
                now = item["time"]
                observed = {k for k, b in ledger.items() if b["arrival"] <= now}
                audit.check(item["proxy_bags"] == public_proxy(source["published_forecasts"], observed, now, item["horizon"]), where, "public-fast comparator proxy differs")
                audit.check(len(item["rollouts"]) == item["candidate_count"], where, "public-fast skipped K candidates")
    # Recompute pair summaries from retained raw case metrics, without using the
    # experiment's summarize function or re-running a policy.
    by_key = {(r["scene"], r["tape"], r["policy"]): r for r in rows}
    quiescent_only = {}
    for policy in protocol["policies"][1:]:
        for end in ("h80", "final"):
            pairs = [(r, by_key.get((r["scene"], r["tape"], "greedy"))) for r in rows if r["policy"] == policy]
            pairs = [(a, b) for a, b in pairs if b is not None and end in a and end in b]
            deltas = [a[end]["total_cost"] - b[end]["total_cost"] for a, b in pairs]
            expected = {"pairs": len(pairs), "better": sum(d < -1e-8 for d in deltas),
                "equal": sum(abs(d) <= 1e-8 for d in deltas), "worse": sum(d > 1e-8 for d in deltas),
                "cost_delta": sum(deltas), "completed_delta": sum(a[end]["completed"]-b[end]["completed"] for a,b in pairs),
                "on_time_delta": sum(a[end]["on_time"]-b[end]["on_time"] for a,b in pairs),
                "both_quiescent": sum(a["status"] == b["status"] == "controller_quiescent" for a,b in pairs)}
            audit.check(summary["pairs"][policy+":"+end] == expected, folder, "paired summary differs")
            complete = [(a,b) for a,b in pairs if a["status"] == b["status"] == "controller_quiescent"]
            quiescent_only[policy+":"+end] = {"pairs": len(complete),
                "cost_delta": sum(a[end]["total_cost"]-b[end]["total_cost"] for a,b in complete)}
    changed = [path for path, expected in audit.files.items() if file_hash(path) != expected]
    audit.check(not changed, folder, "bound files changed during audit")
    result = {"schema": "ics_v3_round5_empty_independent_audit_v1", "run": str(folder),
        "checks": audit.count, "failed_checks": len(audit.errors), "errors": audit.errors,
        "episodes": len(rows), "new_method_proxy_rows": proxy_rows,
        "actual_slow_rollout_attempts_from_diagnostics": true_slow_calls,
        "legacy_failed_proxy_rollouts": legacy_failed, "quiescent_only_pairs": quiescent_only,
        "bound_files": len(audit.files), "all_bound_files_unchanged": not changed,
        "wall_seconds": perf_counter()-wall, "cpu_seconds": process_time()-cpu,
        "script_sha256": file_hash(__file__), "helper_sha256": file_hash(Path(__file__).with_name("audit_round5_full_cycle.py")),
        "scope": "Pure original-file audit of input/true-ledger/forecast-only proxy, all mandatory candidates and budgets, costs and drained denominators. No new simulation or optimality guarantee."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("checks", "failed_checks", "episodes", "new_method_proxy_rows", "legacy_failed_proxy_rollouts", "wall_seconds")}))
    return int(bool(audit.errors))


if __name__ == "__main__":
    raise SystemExit(main())

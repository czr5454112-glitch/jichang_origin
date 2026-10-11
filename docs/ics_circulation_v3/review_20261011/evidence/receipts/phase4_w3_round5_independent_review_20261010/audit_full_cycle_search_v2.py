"""Read-only independent full-cycle artifact audit; imports no simulator code."""
from collections import Counter
from hashlib import sha256
import argparse
import gzip
import json
from pathlib import Path
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = {"tray_wait": 1., "nonprotected_tardiness": 1., "empty_distance": .1,
           "terminal_backlog": 10., "terminal_inflight": 2.}
INFINITY = 10**12


def read(path):
    path = Path(path)
    if path.name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def physical(value):
    value = json.loads(json.dumps(value))
    value["policy_stats"] = {k: v for k, v in value.get("policy_stats", {}).items() if not k.endswith("_ms")}
    return value


class Audit:
    def __init__(self):
        self.count, self.errors, self.files = 0, [], {}

    def check(self, okay, where, message):
        self.count += 1
        if not okay:
            self.errors.append({"where": str(where), "message": message})

    def bind(self, path, expected=None):
        path = Path(path).resolve()
        current = file_hash(path)
        self.files[str(path)] = current
        if expected is not None:
            self.check(current == expected, path, "byte SHA differs from frozen reference")
        return current

    def manifest(self, folder):
        folder = Path(folder)
        self.bind(folder / "manifest.json")
        for name, expected in read(folder / "manifest.json").items():
            self.bind(folder / name, expected)

    def result(self, result, ledger, where):
        state, cost, complete = result["final_snapshot"], result["cost_components"], result["completed"]
        now = state["now"]
        observed = {k for k, bag in ledger.items() if bag["arrival"] <= now}
        self.check(set(state["bags"]) == observed, where, "true bag ledger differs from observed original tape")
        self.check(result["final_trays"] == state["trays"] and complete == state["completed"], where, "result snapshot differs")
        unfinished = set(state["bags"]) - set(complete)
        self.check(set(result["uncompleted_bag_ids"]) == unfinished, where, "unfinished IDs differ")
        self.check(cost["terminal_backlog"] == len(unfinished), where, "terminal backlog differs")
        self.check(cost["terminal_inflight"] == sum(t["mode"] == "in_transit" for t in state["trays"].values()), where, "terminal inflight differs")
        tardiness = sum(max(0, complete.get(k, now) - b["deadline"]) for k, b in state["bags"].items() if not b["protected"])
        self.check(cost["nonprotected_tardiness"] == tardiness, where, "tardiness differs from identity ledger")
        self.check(abs(result["total_cost"] - sum(WEIGHTS[k] * v for k, v in cost.items())) < 1e-8, where, "weighted objective differs")

    def drained(self, outcome, ledger, expiry, where):
        state, cycle = outcome["result"]["final_snapshot"], outcome["last_cycle_state"]
        now = state["now"]
        self.check(set(ledger) == set(state["completed"]) == set(state["bags"]), where, "entire ledger not complete")
        self.check(not state["plans"] and not state["empty_targets"] and not state["old_in_transit"], where, "transport obligations remain")
        self.check(all(t["mode"] == "empty" and t["bag_id"] is None and t["node"] is not None and t["available_at"] <= now for t in state["trays"].values()), where, "tray not released")
        stock = []
        for reservation in state["reservations"]:
            if reservation["end"] <= now:
                continue
            tray = state["trays"].get(reservation["tray_id"])
            okay = (tray is not None and reservation["resource"] == "node:" + str(tray["node"])
                    and reservation["start"] <= now and reservation["end"] == INFINITY)
            self.check(okay, where, "active reservation is not physical current-node idle stock")
            stock.append(reservation)
        self.check(cycle["stationary_occupancy_reservations"] == stock, where, "stock occupancy classification differs")
        self.check(cycle["expected_task_count"] == len(ledger) and cycle["forecast_expired_at"] == expiry, where, "termination ledger/forecast expiry differs")
        self.check(not cycle["pending_arrival_ids"] and not cycle["unobserved_task_ids"] and not cycle["uncompleted_task_ids"], where, "certificate hides pending tasks")
        marker = outcome["milestones"]["controller_quiescent"]
        self.check(now == outcome["stopped_at"] == marker["time"] and now >= expiry, where, "quiescence endpoint/TTL differs")
        self.check(now - marker["quiet_since"] >= 2 and marker["actual_slow_triggers_since"] >= 1, where, "full slow period or actual trigger missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    wall, cpu = perf_counter(), process_time()
    audit = Audit()
    folder = args.run.resolve()
    protocol, summary = read(folder / "protocol.json"), read(folder / "summary.json")
    audit.manifest(folder)
    prior = ROOT / "outputs/experiments/ics_circulation_v3/phase4_w3_network_role_complete_20261009"
    audit.bind(prior / "manifest.json", protocol["prior_manifest_sha256"])
    audit.manifest(prior)
    old_audit = read(prior / "audit.json")
    primary = Path(old_audit["primary"])
    audit.bind(primary / "manifest.json", old_audit["primary_manifest_sha256"])
    for reference in old_audit["supplement_references"]:
        audit.bind(Path(reference["path"]) / "manifest.json", reference["manifest_sha256"])
        audit.manifest(reference["path"])
    old_rows = read(prior / "resolved_request_ledger.json")
    samples, labels, forecasts = {}, {}, {}
    for scene in ("cross_cycle", "counterflow", "near_full"):
        old_folder = primary / scene
        audit.manifest(old_folder)
        saved_input = read(old_folder / (scene + "_input.json"))
        forecasts[scene] = saved_input["forecasts"]
        for entry in read(old_folder / "summary.json")["samples"]:
            samples[entry["identity"]] = read(old_folder / entry["file"])
            labels[entry["identity"]] = read(old_folder / entry["labels"][0])
    for frozen in folder.rglob("protocol.json"):
        body = read(frozen)
        for name, expected in body.get("source_sha256", {}).items():
            audit.bind(frozen.parent / "source_snapshot" / name, expected)
            audit.bind(ROOT / "scripts/experiments/ics_circulation_v3" / name, expected)
    for name, expected in read(folder / "test_manifest.json").items():
        audit.bind(folder / "test_snapshot" / name, expected)
        audit.bind(ROOT / "tests" / name, expected)
    rows = summary["rows"]
    audit.check(len(rows) == protocol["selected_request_count"] == len({r["request_key"] for r in rows}), folder, "planned/retained request denominator differs")
    if protocol["mode"] == "full":
        audit.check({r["request_key"] for r in rows} == set(old_rows), folder, "full old 2176 request identity set differs")
    audit.check(summary["status_counts"] == dict(Counter(r["status"] for r in rows)), folder, "status denominator differs")
    audit.check(summary["actual_branches"] == sum(r.get("physical_call", False) for r in rows), folder, "physical call count differs")
    audit.check(summary["cache_reused"] == sum(r.get("cache_hit", False) for r in rows), folder, "memo count differs")
    seen = {}
    for row in rows:
        key, where = row["request_key"], row["request_key"]
        original = old_rows[key]
        audit.check(all(row.get(k) == original[k] for k in ("scene", "sample", "candidate", "group", "draw", "future_sha256")), where, "request identity changed")
        if "file" not in row:
            audit.check(row["status"] != "controller_quiescent", where, "successful row lacks physical evidence")
            continue
        audit.bind(row["file"], row["artifact_sha256"])
        outcome = read(row["file"])
        audit.check(outcome["request"]["request_key"] == row["physical_call_request_key"], where, "memo owner request mismatch")
        memo_key = (row["sample"], row["candidate"], row["future_sha256"])
        audit.check(all(outcome["request"][k] == row[k] for k in ("sample", "candidate", "future_sha256")), where, "memo crosses sample/candidate/full future")
        audit.check(row["status"] == outcome["status"] and row["total_cost"] == outcome["result"]["total_cost"] and row["cost_components"] == outcome["result"]["cost_components"], where, "row is not its physical evidence")
        if row["file"] in seen:
            audit.check(seen[row["file"]] == memo_key, where, "physical file reused across different memo keys")
            continue
        seen[row["file"]] = memo_key
        sample, label = samples[row["sample"]], labels[row["sample"]]
        tape = label["future_groups_offline_only"][row["group"]]["tapes"][row["draw"]]
        audit.check(digest(tape) == row["future_sha256"], where, "future tape SHA differs")
        ledger = dict(sample["state"]["bags"])
        ledger.update((b["bag_id"], b) for b in tape)
        audit.check(set(outcome["expected_task_ids"]) == set(ledger), where, "full expected task set differs")
        old_path = outcome["old80_file"]
        audit.bind(old_path, outcome["old80_file_sha256"])
        old_envelope = read(old_path)
        old_result = old_envelope["result"]
        audit.check(physical(old_result) == physical(outcome["endpoints"][str(outcome["old80_at"])]["result"]), where, "old h80 raw physics differs")
        first_queries = [q for q in outcome["searches"] if q["time"] < outcome["old80_at"]]
        audit.check(first_queries == old_envelope["searches"], where, "old h80 individual search ledger differs")
        audit.check(sum(q["work"] for q in first_queries) == old_envelope["search_work"], where, "old h80 search work differs")
        audit.check(len(first_queries) == old_envelope["search_calls"], where, "old h80 search call count differs")
        audit.check(outcome["cache_before"] == old_envelope["cache_before"], where, "old branch initial private cache differs")
        audit.check(outcome["search_calls"] == len(outcome["searches"]) and outcome["search_work"] == sum(q["work"] for q in outcome["searches"]), where, "full-cycle search ledger differs")
        for tick, endpoint in outcome["endpoints"].items():
            audit.result(endpoint["result"], ledger, where + ":" + tick)
        audit.result(outcome["result"], ledger, where + ":final")
        if row["status"] == "controller_quiescent":
            expiry = max((f["published_at"] + 61 for f in forecasts[row["scene"]]), default=sample["time"])
            audit.drained(outcome, ledger, expiry, where)
    unchanged = []
    for path, expected in audit.files.items():
        if file_hash(path) != expected:
            unchanged.append(path)
    audit.check(not unchanged, folder, "input/output bytes changed during independent audit")
    result = {"schema": "ics_v3_round5_full_cycle_independent_audit_v1", "run": str(folder),
        "checks": audit.count, "errors": audit.errors, "failed_checks": len(audit.errors),
        "request_count": len(rows), "unique_physical_files": len(seen), "bound_files": len(audit.files),
        "all_bound_files_unchanged": not unchanged, "wall_seconds": perf_counter() - wall,
        "cpu_seconds": process_time() - cpu, "script_sha256": file_hash(__file__),
        "scope": "Pure file audit; original h80 raw result equality, immutable dependencies, identity denominators and independently recomputed costs/drain. No new simulations or method quality certification."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("checks", "failed_checks", "request_count", "unique_physical_files", "bound_files", "wall_seconds")}))
    return int(bool(audit.errors))


if __name__ == "__main__":
    raise SystemExit(main())

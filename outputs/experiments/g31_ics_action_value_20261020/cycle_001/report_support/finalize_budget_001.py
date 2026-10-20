"""Read-only campaign accounting, run only after all 72 registered branches close."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cycle, repo = args.cycle.resolve(), args.repository.resolve()
    manifest = read(cycle / "manifest.json")
    ledger = [json.loads(line) for line in (cycle / "ledger.jsonl").read_text().splitlines()]
    events = {event: [row for row in ledger if row["event"] == event]
              for event in {row["event"] for row in ledger}}
    launches, closed = events["long_native_launch"], events["long_native_closed"]
    names = [row["name"] for row in launches]
    require(len(names) == len(set(names)) == 72, "72 unique launches required")
    require(Counter(names) == Counter(row["name"] for row in closed), "unclosed launch")
    native_attempts, statuses, walls, source_sets = 0, Counter(), [], []
    rows = []
    for launch in launches:
        name = launch["name"]
        directory = cycle / name
        plan, receipt = read(directory / "plan.json"), read(directory / "receipt.json")
        require(receipt["plan_sha256"] == sha(directory / "plan.json") == launch["plan_sha256"],
                "launch/receipt/plan mismatch: " + name)
        ending = next(row for row in closed if row["name"] == name)
        require(ending["status"] == receipt["status"], "ledger status mismatch: " + name)
        attempts = receipt["worker"]["native_constructor_attempts"]
        native_attempts += attempts
        statuses[receipt["status"]] += 1
        walls.append(receipt["worker"]["wall_seconds"])
        rows.append({"name": name, "batch": launch["batch"], "status": receipt["status"],
                     "native_constructor_attempts": attempts,
                     "receipt_sha256": sha(directory / "receipt.json")})
        if launch["batch"] in ("D", "G"):
            source_sets.append(plan["sources"])
    require(native_attempts == 72, "unexpected native constructor count")
    require(all(sources == source_sets[0] for sources in source_sets), "D/G source drift")
    for relative, expected in source_sets[0].items():
        require(sha(repo / relative) == expected, "current frozen source drift: " + relative)
    short_rows = [json.loads(line) for line in
                  (cycle / "native029_gate_ledger.jsonl").read_text().splitlines()]
    short_counts = Counter(row["event"] for row in short_rows)
    short_attempts = short_counts["native_constructor_attempt"]
    require(short_attempts == events["short_native_summary"][0]["count"], "short accounting")
    require(short_counts["native_result"] + short_counts["native_constructor_failed"]
            == short_attempts, "unclosed short attempt")
    training = events["training_chain_closed"]
    require(len(training) == len(events["training_chain_launch"]) == 12, "training count")
    require(len({row["chain_id"] for row in training}) == 12, "duplicate training chain")
    freeze = read(cycle / "all_models_frozen_001.json")
    fit_started = sum(row["fit_calls_started"] for row in training)
    fit_completed = sum(row["fit_calls_completed"] for row in training)
    require(fit_started == fit_completed == freeze["primary_fit_calls_completed"] == 24,
            "fit count disagreement")
    first_test = min(datetime.fromisoformat(row["at"]).timestamp()
                     for row in launches if row["batch"] in ("D", "G"))
    require(freeze["frozen_epoch_seconds"] < first_test, "model freeze must precede test")
    now = datetime.now(timezone.utc)
    elapsed = (now - datetime.fromisoformat(manifest["created_at"])).total_seconds()
    limits = manifest["limits"]
    require(native_attempts <= limits["long_native"]
            and short_attempts <= limits["short_native"]
            and len(training) <= limits["training_chains"], "budget exceeded")
    require(elapsed <= 3600 * manifest["total_hours"], "whole-task time exceeded")
    result = {
        "schema": "g31.action_campaign_closed_budget_audit.v1",
        "status": "all_registered_runs_closed_and_within_limits",
        "recorded_at": now.isoformat(), "campaign_started_at": manifest["created_at"],
        "elapsed_hours_through_this_audit": elapsed / 3600,
        "whole_task_limit_hours": manifest["total_hours"],
        "publication_time_is_recorded_separately": True,
        "limits": limits, "long_native_attempts": native_attempts,
        "long_statuses": dict(statuses), "long_batch_counts": dict(Counter(r["batch"] for r in rows)),
        "sum_native_branch_wall_seconds_not_elapsed": sum(walls),
        "short_native_attempts": short_attempts, "short_events": dict(short_counts),
        "training_chains": len(training), "policy_fit_calls_started": fit_started,
        "policy_fit_calls_completed": fit_completed,
        "diagnostic_fit_calls_completed": freeze["control_fit_calls_completed"],
        "all_models_frozen_before_first_test_launch": True,
        "DG_identical_source_manifests": len(source_sets),
        "current_frozen_source_files_verified": len(source_sets[0]),
        "ledger_sha256": sha(cycle / "ledger.jsonl"),
        "all_models_frozen_sha256": sha(cycle / "all_models_frozen_001.json"),
        "runs": rows,
    }
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

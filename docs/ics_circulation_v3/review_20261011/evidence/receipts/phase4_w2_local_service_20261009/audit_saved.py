"""Recompute saved artifact claims using stdlib only; no simulator imports/runs."""
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def main():
    checks = []
    def check(name, okay):
        checks.append({"check": name, "passed": bool(okay)})
    summary, rows, inputs = read("summary.json"), read("rows.json"), read("inputs.json")
    manifest = read("manifest.json")
    check("all_manifest_hashes", all(sha256((HERE / p).read_bytes()).hexdigest() == h for p, h in manifest.items()))
    check("source_snapshot_hashes", all(sha256((HERE / "source_snapshot" / p).read_bytes()).hexdigest() == h
                                       for p, h in summary["source_sha256"].items()))
    check("current_source_hashes", all(sha256((ROOT / p).read_bytes()).hexdigest() == h
                                      for p, h in summary["source_sha256"].items()))
    check("declared_seven_runs", len(rows) == summary["run_count"] == 7)
    for item in inputs:
        canonical = {k: v for k, v in item.items() if k != "input_sha256"}
        check(item["case_id"] + ":input_hash", sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == item["input_sha256"])
    data_by_id = {v["case_id"]: v for v in inputs}
    request_totals, commit_totals, task_totals, complete_totals = 0, 0, 0, 0
    all_outcomes = Counter()
    for row in rows:
        name = row["case_id"] + ("__local_on" if row["local_dispatch"] else "__local_off")
        raw = read("raw/" + name + ".json")
        result, fixture = raw["result"], data_by_id[row["case_id"]]
        physical, records = result["physical"], result["requests"]
        bags = physical["final_snapshot"]["bags"]
        completed = physical["completed"]
        outcomes = Counter(r["outcome"] or "pending" for r in records.values())
        commits = [e for e in result["trace"] if e["event"] == "physical_commit"]
        check(name + ":input_link", raw["input_sha256"] == row["input_sha256"] == fixture["input_sha256"])
        check(name + ":task_identity_denominator", sorted(bags) == row["bag_ids"] == sorted(b["bag_id"] for b in fixture["bags"]))
        check(name + ":completed_and_uncompleted", len(completed) == row["completed_count"] and len(completed) + len(physical["uncompleted_bag_ids"]) == row["bag_count"])
        check(name + ":on_time", sum(t <= bags[b]["deadline"] for b, t in completed.items()) == row["on_time_count"])
        check(name + ":request_denominator", len(records) == row["request_count"] == sum(outcomes.values()))
        check(name + ":outcomes", dict(outcomes) == row["outcome_counts"] == result["outcome_counts"])
        check(name + ":atomic_commit_count", len(commits) == row["owner_commit_count"] == sum(r["owner_committed"] for r in records.values()))
        check(name + ":no_duplicate_commit", len({e["request_id"] for e in commits}) == len(commits))
        components = physical["cost_components"]
        recomputed = (components["tray_wait"] + components["nonprotected_tardiness"] + .1 * components["empty_distance"]
                      + 10 * components["terminal_backlog"] + 2 * components["terminal_inflight"])
        check(name + ":cost", math.isclose(recomputed, row["total_cost"]) and components == row["components"])
        check(name + ":real_tray_identity", sorted(physical["final_trays"]) == sorted(fixture["state"]["trays"]))
        guards = [e for events in raw["source_owner_local_guard"].values() for e in events if e["accepted"]]
        check(name + ":all_approved_other_prefixes_preserved", all(p["other_after"] >= p["other_before"]
              for e in guards for p in e.get("prefixes", ())))
        check(name + ":no_early_target_credit", all(p["target_credit"] == 0 or p["tick"] >= e["usable_at"]
              for e in guards for p in e.get("prefixes", ())))
        request_totals += len(records)
        commit_totals += len(commits)
        task_totals += len(bags)
        complete_totals += len(completed)
        all_outcomes.update(outcomes)
    for case_id in ("sustained_local_and_cross_owner", "mixed_reversal_and_lost_ack"):
        pair = [r for r in rows if r["case_id"] == case_id]
        check(case_id + ":matched_switch_only", len(pair) == 2 and {r["local_dispatch"] for r in pair} == {False, True}
              and len({r["input_sha256"] for r in pair}) == 1 and pair[0]["bag_ids"] == pair[1]["bag_ids"])
    for label, totals in summary["mixed_aggregates"].items():
        chosen = [r for r in rows if r["kind"] == "mixed_continuous" and r["local_dispatch"] == (label == "local_on")]
        check(label + ":saved_aggregate", all(math.isclose(sum(r[k] for r in chosen), v) for k, v in totals.items()))
    ack = read("raw/local_lost_ack__local_on.json")["result"]
    empty = [r for r in ack["requests"].values() if r["request"]["intent"] == "empty_transfer"]
    check("lost_ack_single_empty_receipt_recovery", len(empty) == 1 and empty[0]["reason"] == "receipt_recovered" and empty[0]["owner_committed"])
    result = {"audit": "Read-only stdlib recomputation of saved local-service fixtures; no simulation executed",
              "check_count": len(checks), "all_passed": all(c["passed"] for c in checks), "checks": checks,
              "totals": {"bag_instances": task_totals, "completed": complete_totals, "requests": request_totals,
                         "physical_commits": commit_totals, "outcomes": dict(all_outcomes)},
              "caveats": ["Two hand-constructed development comparisons, not independent held-out evidence.",
                          "Three regressions have different horizons; do not pool their costs as a policy score.",
                          "Checkpoint exactness is a recorded runner assertion plus dedicated tests; this audit does not replay simulation.",
                          "Source matching is conservative; no proof of general scheduling liveness or real distributed deployment."]}
    (HERE / "audit_saved.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "checks"}, indent=2))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

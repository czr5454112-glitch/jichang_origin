"""Re-run the frozen handoff experiment against an explicitly identified native build.

The existing runner and policies are not edited. Only its artifact identity
constant is substituted, after verifying all ten archived Python source hashes.
Comparison is exact: nearby but different departure times are different actions.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import traceback

from . import p5_handoff_run as frozen


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def identity(action):
    """Preserve submission order and physical/owner contract, excluding revision IDs."""
    requests = [{k: v for k, v in candidate["request"].items()
                 if k not in {"request_id", "expected_version"}}
                for candidate in action["candidates"]]
    return json.dumps(requests, sort_keys=True, separators=(",", ":"), allow_nan=False)


def domain_index(domain):
    by_payload, by_id = {}, {}
    for action in domain["actions"]:
        key = identity(action)
        if key in by_payload or action["action_id"] in by_id:
            raise ValueError("handoff_recheck:duplicate_domain_identity")
        by_payload[key] = action
        by_id[action["action_id"]] = key
    return by_payload, by_id


def load_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    by_id = {row["action_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("handoff_recheck:duplicate_executed_identity")
    return by_id


def chronology(result):
    answer = {}
    for name, time_key in (("native_events", "time"), ("receipts", "time"), ("decisions", "event_time")):
        entries = result.get(name, [])
        regressions = [{"index": i, "previous": entries[i-1][time_key], "current": row[time_key],
                        "previous_event": entries[i-1].get("event"), "current_event": row.get("event")}
                       for i, row in enumerate(entries) if i and row[time_key] < entries[i-1][time_key]]
        answer[name] = {"count": len(entries), "regressions": regressions,
                        "max_regression": max((r["previous"]-r["current"] for r in regressions), default=0.)}
    return answer


def compared_metrics(old, new):
    if old is None or new is None:
        return {"exact_equal": old == new, "status": "unknown_missing_metrics"}
    old_jobs = {job["business_bag_id"]: job for job in old["per_job"]}
    new_jobs = {job["business_bag_id"]: job for job in new["per_job"]}
    return {"exact_equal": old == new, "cost_delta": new["cost"]-old["cost"],
            "offered_equal": old["offered"] == new["offered"],
            "completed_before": old["completed"], "completed_after": new["completed"],
            "changed_jobs": [{"business_bag_id": key, "before": old_jobs.get(key), "after": new_jobs.get(key)}
                             for key in sorted(old_jobs.keys() | new_jobs.keys()) if old_jobs.get(key) != new_jobs.get(key)]}


def normalized_resolutions(row):
    # A public-read revision may change request names; retain every status, time,
    # reason and tray in order. Identity/name changes remain recorded separately.
    return [{k: v for k, v in r.items() if k != "request_id"} for r in row.get("resolutions", [])]


def compare_phase(old_path, new_path):
    old_domain, new_domain = read(old_path/"domain.json"), read(new_path/"domain.json")
    old_payload, old_id = domain_index(old_domain)
    new_payload, new_id = domain_index(new_domain)
    old_rows, new_rows = load_rows(old_path/"native_branches.jsonl.gz"), load_rows(new_path/"native_branches.jsonl.gz")
    old_assessment, new_assessment = read(old_path/"assessment.json"), read(new_path/"assessment.json")
    shared = sorted(old_payload.keys() & new_payload.keys())
    branches = []
    for key in shared:
        old_action, new_action = old_payload[key], new_payload[key]
        old, new = old_rows.get(old_action["action_id"]), new_rows.get(new_action["action_id"])
        if old is None or new is None:
            branches.append({"physical_requests": json.loads(key), "status": "unknown_unexecuted"})
            continue
        branches.append({"physical_requests": json.loads(key), "action_id_before": old["action_id"],
            "action_id_after": new["action_id"], "status_before": old["status"], "status_after": new["status"],
            "metrics": compared_metrics(old.get("metrics"), new.get("metrics")),
            "resolutions_equal_without_request_names": normalized_resolutions(old) == normalized_resolutions(new),
            "resolutions_before": old.get("resolutions"), "resolutions_after": new.get("resolutions"),
            "audit_before": old.get("audit"), "audit_after": new.get("audit"),
            "completion_equal": old.get("completion") == new.get("completion"),
            "chronology_before": chronology(old.get("result", {})), "chronology_after": chronology(new.get("result", {})),
            "offline_physical_hash_equal": old.get("physical_sha256") == new.get("physical_sha256")})
    policies = {}
    for name in sorted(old_domain["selected"].keys() | new_domain["selected"].keys()):
        old_key = old_id.get(old_domain["selected"].get(name))
        new_key = new_id.get(new_domain["selected"].get(name))
        old = old_assessment["policies"].get(name, {})
        new = new_assessment["policies"].get(name, {})
        policies[name] = {"physical_action_equal": old_key == new_key,
            "action_before": json.loads(old_key) if old_key is not None else None,
            "action_after": json.loads(new_key) if new_key is not None else None,
            "metrics": compared_metrics(old.get("metrics"), new.get("metrics")),
            "protection_before": old.get("comparisons"), "protection_after": new.get("comparisons"),
            "protection_exact_equal": old.get("comparisons") == new.get("comparisons"),
            "protection_preserved_status_equal": {k: v["preserved"] for k,v in old.get("comparisons", {}).items()}
                == {k: v["preserved"] for k,v in new.get("comparisons", {}).items()},
            "original_ordinary_protection_before": old.get("compared_with_original_ordinary"),
            "original_ordinary_protection_after": new.get("compared_with_original_ordinary")}
    return {"declared_domain_before": len(old_payload), "declared_domain_after": len(new_payload),
        "executed_before": len(old_rows), "executed_after": len(new_rows),
        "physical_domain_equal": old_payload.keys() == new_payload.keys(),
        "removed_physical_actions": [json.loads(k) for k in sorted(old_payload.keys()-new_payload.keys())],
        "added_physical_actions": [json.loads(k) for k in sorted(new_payload.keys()-old_payload.keys())],
        "shared_executed_branches": branches, "policies": policies,
        "reference_before": old_assessment["reference"], "reference_after": new_assessment["reference"],
        "parent_unchanged_before": old_assessment.get("parent_state_unchanged"),
        "parent_unchanged_after": new_assessment.get("parent_state_unchanged")}


def compare_campaigns(baseline, current):
    old, new = read(baseline/"receipt.json"), read(current/"receipt.json")
    cases = {}
    for name in sorted(old["predeclared_input_sha256"].keys() | new["predeclared_input_sha256"].keys()):
        old_path, new_path = baseline/name, current/name
        case = {"input_sha256_before": frozen.sha(old_path/"input.json"),
                "input_sha256_after": frozen.sha(new_path/"input.json"), "phases": {}}
        for phase, relative in (("initial", Path(".")), ("rolling", Path("rolling"))):
            if not (old_path/relative/"assessment.json").exists() or not (new_path/relative/"assessment.json").exists():
                case["phases"][phase] = {"status": "unknown_missing_phase"}
            else:
                case["phases"][phase] = compare_phase(old_path/relative, new_path/relative)
        cases[name] = case
    phases = [p for c in cases.values() for p in c["phases"].values()]
    branches = [r for p in phases for r in p.get("shared_executed_branches", [])]
    policies = [r for p in phases for r in p.get("policies", {}).values()]
    return {"schema": "g31.handoff.native_recheck.v1", "baseline": str(baseline), "current": str(current),
        "receipt_sha256_before": frozen.sha(baseline/"receipt.json"), "receipt_sha256_after": frozen.sha(current/"receipt.json"),
        "binary_sha256_before": old["binary_sha256"], "binary_sha256_after": new["binary_sha256"],
        "runner_status_before": old["status"], "runner_status_after": new["status"],
        "source_changed_before": old.get("source_changed"), "source_changed_after": new.get("source_changed"),
        "summary": {"same_all_inputs": all(c["input_sha256_before"] == c["input_sha256_after"] for c in cases.values()),
            "same_all_physical_domains": all(p.get("physical_domain_equal") is True for p in phases),
            "shared_executed_branch_count": len(branches),
            "changed_metrics_branches": sum(r.get("metrics", {}).get("exact_equal") is False for r in branches),
            "changed_policy_actions": sum(not p["physical_action_equal"] for p in policies),
            "changed_policy_metrics": sum(p["metrics"].get("exact_equal") is False for p in policies),
            "changed_policy_protection_status": sum(not p["protection_preserved_status_equal"] for p in policies),
            "clock_regressions_before": sum(len(v["regressions"]) for r in branches for v in r.get("chronology_before", {}).values()),
            "clock_regressions_after": sum(len(v["regressions"]) for r in branches for v in r.get("chronology_after", {}).values())},
        "cases": cases, "interpretation": "exact comparison, no rounding of times; partial domains or executions remain explicit; not a performance benchmark"}


def preflight(baseline, binary, expected):
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("handoff_recheck:invalid_expected_sha256")
    old = read(baseline/"receipt.json")
    if old["status"] != "executed_finite_diagnostic" or old.get("source_changed"):
        raise ValueError("handoff_recheck:baseline_not_frozen_complete")
    actual_binary = frozen.sha(binary)
    if actual_binary != expected:
        raise ValueError("handoff_recheck:unexpected_binary")
    current_sources = {p: frozen.sha(Path(p)) for p in old["source_before"]}
    if current_sources != old["source_before"]:
        raise ValueError("handoff_recheck:research_source_differs_from_baseline")
    for factor in frozen.FACTORS:
        encoded = (json.dumps(frozen.scenario_input(factor), ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")
        # Existing Windows text files use CRLF. Compare parsed input contracts,
        # then also require byte-for-byte input hashes after the real run.
        if json.loads(encoded) != read(baseline/factor["name"]/"input.json"):
            raise ValueError("handoff_recheck:input_contract_changed")
    return {"baseline_receipt_sha256": frozen.sha(baseline/"receipt.json"), "research_sources": current_sources,
        "baseline_binary_sha256": old["binary_sha256"], "new_binary_sha256": actual_binary,
        "expected_binary_sha256": expected, "frozen_runner_expected_before_substitution": frozen.EXPECTED,
        "substitution_scope": "only frozen runner EXPECTED artifact identity; no solver/input/physical fields modified",
        "wrapper_sha256": frozen.sha(Path(__file__)), "native_not_yet_executed": True}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--baseline", type=Path, required=True)
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--expected-binary-sha256", required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--max-seconds", type=float, default=180.)
    compare = sub.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--current", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "compare":
        if args.output.exists():
            raise ValueError("handoff_recheck:comparison_output_exists")
        result = compare_campaigns(args.baseline, args.current)
        frozen.write(args.output, result)
        print(json.dumps(result["summary"]))
        return 0
    if args.output.exists():
        raise ValueError("handoff_recheck:run_output_exists")
    declaration = preflight(args.baseline, args.binary, args.expected_binary_sha256)
    context = args.output.with_name(args.output.name+"_recheck_context")
    context.mkdir(parents=True, exist_ok=False)
    frozen.write(context/"prerun.json", declaration)
    (context/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    previous_expected, previous_argv = frozen.EXPECTED, sys.argv
    final = {"status": "starting", "prerun_sha256": frozen.sha(context/"prerun.json")}
    try:
        frozen.EXPECTED = args.expected_binary_sha256
        sys.argv = [str(Path(frozen.__file__)), "--binary", str(args.binary), "--output", str(args.output),
                    "--max-seconds", str(args.max_seconds)]
        code = frozen.main()
        final.update({"status": "executed" if code == 0 else "runner_incomplete", "runner_exit_code": code})
        comparison = compare_campaigns(args.baseline, args.output)
        frozen.write(context/"comparison.json", comparison)
        final["comparison_sha256"] = frozen.sha(context/"comparison.json")
        print(json.dumps(comparison["summary"]))
        return code
    except Exception:
        final.update({"status": "exception", "exception": traceback.format_exc()})
        raise
    finally:
        frozen.EXPECTED, sys.argv = previous_expected, previous_argv
        final["wrapper_unchanged"] = frozen.sha(Path(__file__)) == declaration["wrapper_sha256"]
        frozen.write(context/"final.json", final)


if __name__ == "__main__":
    raise SystemExit(main())

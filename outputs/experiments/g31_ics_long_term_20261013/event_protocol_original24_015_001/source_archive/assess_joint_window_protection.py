"""Independent denominator-explicit protection assessment of frozen P5 branches.

This reads immutable actual native receipts; it never selects a new online
action, changes the completed experiment, or advances another simulator.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from .finite_reference import outcome_cost, service_dominates
from .validate_analytic_control import write


def compare(candidate: dict, baseline: dict, ids: list[str]) -> dict:
    a = {j["business_bag_id"]: j for j in candidate["per_job"]}
    b = {j["business_bag_id"]: j for j in baseline["per_job"]}
    if a.keys() != b.keys() or not set(ids) <= a.keys():
        raise ValueError("joint_protection:population_mismatch")
    kept_a, kept_b = {"per_job": [a[i] for i in ids]}, {"per_job": [b[i] for i in ids]}
    return {"preserved": service_dominates(kept_a, kept_b), "denominator": len(ids),
            "business_bag_ids": ids, "per_job": [{"business_bag_id": i,
                "restricted_time_delta": a[i]["restricted_time"] - b[i]["restricted_time"],
                "candidate": a[i], "baseline": b[i]} for i in ids],
            "guarantee_scope": "post_run_paired_restricted_horizon_only; no future or universal guarantee"}


def assess(root: Path) -> dict:
    receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
    if receipt["status"] != "passed" or receipt["source_changed"]:
        raise ValueError("joint_protection:unfrozen_or_failed_campaign")
    sources = [root / "receipt.json", root / "protocol.json"]
    assessed = []
    for case in receipt["cases"]:
        folder = root / case["scenario"]["name"]
        paths = [folder / "input.json", folder / "public_observation.json", folder / "domain.json",
                 folder / "native_branches.json.gz"]
        sources.extend(paths)
        data, observation, domain = [json.loads(p.read_text(encoding="utf-8")) for p in paths[:3]]
        with gzip.open(paths[3], "rt", encoding="utf-8") as handle:
            rows = json.load(handle)
        # This audit cohort is fixed by the actual visible prefix: locally
        # committed loaded trays and legally delivered service announcements.
        # It is not the full business protection denominator and never replaces it.
        committed = {t["business_bag_id"] for t in observation["trays"]
                     if t.get("business_bag_id") and t["mode"] in ("loading", "loaded", "storage", "unloading", "hold")}
        committed.update(m["business_bag_id"] for m in observation["delivered_messages"]
                         if m.get("kind") == "service_forecast" and m.get("status") == "conditional")
        by_id = {r["action_id"]: r for r in rows}
        wait = by_id["WAIT"]
        ordinary = by_id[domain["selected"]["ordinary_public_windows"]]
        all_ids = sorted(j["business_bag_id"] for j in data["jobs"] if j["arrival"] <= 5000)
        details = []
        for row in rows:
            if "metrics" not in row:
                details.append({"action_id": row["action_id"], "status": row["status"], "protection": "unknown_no_complete_metrics"})
                continue
            recalculated = outcome_cost(row["result"], data["jobs"], 5000)
            if recalculated != row["metrics"]:
                raise ValueError("joint_protection:recorded_metrics_not_reproducible")
            details.append({"action_id": row["action_id"], "status": row["status"],
                "relative_to_ordinary_all_offered": compare(recalculated, ordinary["metrics"], all_ids),
                "relative_to_wait_all_offered": compare(recalculated, wait["metrics"], all_ids),
                "relative_to_wait_precommitted_prefix": compare(recalculated, wait["metrics"], sorted(committed))})
        assessed_by_id = {r["action_id"]: r for r in details}
        policies = {"WAIT": assessed_by_id["WAIT"]}
        policies.update({name: assessed_by_id[action_id] for name, action_id in domain["selected"].items() if action_id})
        unseen = {name: next((r["candidate"] for r in row["relative_to_wait_all_offered"]["per_job"]
                             if r["business_bag_id"] == "UNSEEN"), None) for name, row in policies.items()}
        assessed.append({"scenario": case["scenario"], "full_offered_denominator": len(all_ids),
                         "prefix_committed_ids": sorted(committed), "all_rows": details,
                         "policy_comparisons": policies, "UNSEEN_by_policy": unseen,
                         "interpretation": "ordinary-relative preservation is not an independent normal-service certificate; WAIT and full-offered checks retained"})
    return {"schema": "g31.joint_window_protection_assessment.v1", "status": "passed", "cases": assessed,
            "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            "source_campaign_not_modified": True, "native_executions_added": 0,
            "novelty": "not_established", "strict_future_service_guarantee": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = assess(args.campaign)
    write(args.output, result)
    print(json.dumps({"status": result["status"], "cases": [{"name": c["scenario"]["name"],
        "prefix": c["prefix_committed_ids"], "denominator": c["full_offered_denominator"],
        "policy_wait_protection": {p: r["relative_to_wait_all_offered"]["preserved"]
                                   for p, r in c["policy_comparisons"].items()}}
        for c in result["cases"]]}))


if __name__ == "__main__":
    main()

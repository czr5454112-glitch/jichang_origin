"""Offline R1 x R2-policy contrast, not same-continuation joint-action kappa."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .original_workload import write_json


COMPARISON_SCOPE = "R1_next_hop_by_R2_continuation_policy_factorial_contrast"


def assess(receipt: dict, *, selection: dict | None = None) -> dict:
    """Fail closed on missing cells or denominators; never infer zero from censoring.

    The R2 factor changes the continuing policy. Its four-cell contrast cannot
    establish joint-action nonseparability under a common continuation policy.
    A receipt may declare expected_business_ids/offered_business_ids, or embed
    its selection. The CLI also reads the adjacent saved selection manifest.
    """
    def unknown(reason, **details):
        return {"status": "unknown", "reason": reason, "comparison_scope": COMPARISON_SCOPE,
                "same_continuation_joint_action_kappa": False, **details}

    if receipt.get("status") != "executed" or receipt.get("source_changed"):
        return unknown("source_identity_or_execution_not_valid")
    branches = receipt.get("branches")
    if not isinstance(branches, dict):
        return unknown("missing_factorial_action_domain")
    if any(name not in branches for name in ("reactive_control", "predictive_control")):
        return unknown("missing_factorial_control_cell")
    actions = {name.removeprefix("reactive_") for name in branches if name.startswith("reactive_next_")}
    predictive_actions = {name.removeprefix("predictive_") for name in branches if name.startswith("predictive_next_")}
    if not actions or actions != predictive_actions:
        return unknown("missing_factorial_action_domain")
    cells = {policy + "_" + action for policy in ("reactive", "predictive") for action in actions | {"control"}}
    if set(branches) != cells:
        return unknown("unexpected_factorial_cell")
    declared = []
    declarations = [("receipt", receipt), ("receipt.selection", receipt.get("selection")), ("selection", selection)]
    for source, manifest in declarations:
        if manifest is None:
            continue
        if not isinstance(manifest, dict):
            return unknown("invalid_offered_business_manifest", source=source)
        for key in ("expected_business_ids", "offered_business_ids", "selected_business_ids"):
            if key not in manifest:
                continue
            ids = manifest[key]
            if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids)
                    or len(set(ids)) != len(ids)):
                return unknown("invalid_offered_business_ids", source=source + "." + key)
            if "witness_offered" in manifest and manifest["witness_offered"] != len(ids):
                return unknown("offered_business_count_mismatch", source=source)
            declared.append((source + "." + key, ids))
    if declared and any(set(ids) != set(declared[0][1]) for _, ids in declared):
        return unknown("conflicting_offered_business_ids")
    expected_ids = declared[0][1] if declared else None
    costs = {}
    for name, branch in branches.items():
        if not isinstance(branch, dict):
            return unknown("unequal_or_incomplete_business_contract", branch=name)
        jobs = branch.get("jobs", [])
        if (branch.get("status") != "reached" or branch.get("horizon_complete") is False
                or not isinstance(jobs, list) or not jobs or any(not isinstance(j, dict) for j in jobs)):
            return unknown("unequal_or_incomplete_business_contract", branch=name)
        ids = [j.get("business_bag_id") for j in jobs]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            return unknown("duplicate_or_invalid_business_identity", branch=name)
        if expected_ids is None:
            expected_ids = ids
        if set(ids) != set(expected_ids):
            return unknown("unequal_or_incomplete_business_contract", branch=name)
        for job in jobs:
            completion = job.get("completed_at")
            times = [completion] + [v for key, v in job.items() if key.endswith("_at") or key in ("arrival", "deadline")]
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in times):
                return unknown("missing_or_nonfinite_business_time", branch=name)
            if completion < 0 or job.get("status", "completed") != "completed":
                return unknown("unequal_or_incomplete_business_contract", branch=name)
        if "_next_" in name and (branch.get("R1_ack") or {}).get("status") != "updated":
            return unknown("action_not_executable", branch=name)
        costs[name] = sum(j["completed_at"] for j in jobs)
        if not math.isfinite(costs[name]):
            return unknown("nonfinite_completion_sum", branch=name)
    rows = []
    for name in sorted(branches):
        if not name.startswith("reactive_next_"):
            continue
        action = name.removeprefix("reactive_")
        other = "predictive_" + action
        if other not in costs:
            return unknown("missing_factorial_cell", action=action)
        kappa = (costs[other] - costs[name] - costs["predictive_control"] + costs["reactive_control"])
        if not math.isfinite(kappa):
            return unknown("nonfinite_factorial_contrast", action=action)
        rows.append({"action": action, "factorial_completion_sum_seconds": kappa,
                     "kappa_completion_sum_seconds": kappa,
                     "comparison_scope": COMPARISON_SCOPE,
                     "same_continuation_joint_action_kappa": False,
                     "four_complete_executable_cells": True})
    gaps = {policy: min(cost for name, cost in costs.items() if name.startswith(policy + "_"))
            - costs[policy + "_control"] for policy in ["reactive", "predictive"]}
    return {"status": "assessed", "business_ids": expected_ids, "costs_completion_sum": costs,
            "comparison_scope": COMPARISON_SCOPE, "same_continuation_joint_action_kappa": False,
            "legacy_kappa_field": "numeric alias for the R1 x R2-policy factorial contrast, not joint-action kappa",
            "business_denominator_scope": "declared_offered_ids" if declared else "observed_branch_ids_only_no_offered_manifest",
            "business_denominator_sources": [source for source, _ in declared],
            "arrival_constants_cancel_in_paired_differences": True, "factorial": rows,
            "best_enumerated_minus_control_seconds": gaps,
            "predictive_minus_reactive_control_seconds": costs["predictive_control"] - costs["reactive_control"],
            "enumerated_R1_action_count": len(actions),
            "scope": "Prespecified R1 next-hop alternatives crossed with reactive/predictive R2 continuation policies "
                     "at one original checkpoint. R2 policies differ across cells; this is not a same-continuation joint-action kappa.",
            "joint_nonseparability_claim": False, "higher_order_coupling": "unknown",
            "new_solver_innovation": "not_established"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--selection", type=Path, help="offered-ID manifest; defaults to adjacent selection.json when present")
    args = p.parse_args()
    if args.output.exists():
        p.error("output must be new")
    selection_path = args.selection if args.selection is not None else args.receipt.with_name("selection.json")
    selection = (json.loads(selection_path.read_text(encoding="utf-8"))
                 if args.selection is not None or selection_path.exists() else None)
    result = assess(json.loads(args.receipt.read_text(encoding="utf-8")), selection=selection)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

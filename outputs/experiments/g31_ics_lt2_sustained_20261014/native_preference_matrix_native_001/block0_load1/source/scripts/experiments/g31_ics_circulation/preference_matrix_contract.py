"""Preregistered finite native-action matrix contract; no execution or solver.

All six existing cases and all 32 action vectors are declared together. A
future bounded runner must leave missing/censored/failed cells in this exact
denominator. Comparison here consumes assessed supplied summaries only; it is
not an authentication, native audit, online oracle or calibrated predictor.
"""
from __future__ import annotations
import copy
import math

from . import public_executable_preference_actions as vocabulary
from . import research_preexisting_occupancy_domain as cases

JOBS = frozenset(("loaded", "receiver", "reuse1", "reuse2", "blocker"))


def key_for(vector):
    return (vector["initial_action"], vector["empty_departure"],
            vector["return_delay"], vector["later_action"])


def matrix_protocol():
    rows, groups, incumbents = {}, {}, {}
    for case in cases.cases():
        old = cases.domain(case)
        windows = sorted({r["departure"] for r in old["actions"]})
        vectors = vocabulary.domain(windows)["actions"]
        group = []
        for index, vector in enumerate(vectors):
            key = case["case_id"] + f"/vector_{index:02d}"
            rows[key] = {"case": copy.deepcopy(case), "vector": copy.deepcopy(vector),
                         "method": "fixed_counterfactual", "fault": None,
                         "status": "unknown_unexecuted"}
            group.append(key)
            if key_for(vector) == ("native_default", old["incumbent"]["departure"], 0., "native_default"):
                incumbents[case["case_id"]] = key
        groups[case["case_id"]] = group
    assert len(rows) == 192 and all(len(v) == 32 for v in groups.values()) and len(incumbents) == 6
    return {"schema": "g31.native_preference_matrix.protocol.v1", "rows": rows,
        "case_order": [c["case_id"] for c in cases.cases()], "case_groups": groups,
        "incumbent_keys": incumbents, "native_branch_budget": 192,
        "per_case_branch_budget": 32, "per_case_parent_timeout_seconds": 180.,
        "total_parent_timeout_budget_seconds": 1080., "max_native_workers": 1,
        "same_input_within_case": True, "same_common_continuation_within_case": True,
        "information": "Actual initial/later source-local delivered captures and current own view retain the bound-runner guards. Predeclared vector supplies the choice, never another branch's outcomes.",
        "initial_default": "No route command and no requested physical next; actual native edge must be recorded.",
        "later_default": "No new first-reuse preference and no requested next; actual edge3 or8 must be recorded.",
        "preferences": "Initial prefer2 and first-reuse prefer8 are actual immutable source-local commands. Require delivered updated ACK and the requested actual EDGE_ENTER to assess the selected physical action; also retain all rejections and mismatches.",
        "common_continuation": "Existing immutable supply/recovery and two same-L returns; second return delay0 and actual second-reuse next3 command unchanged for every vector. No native physics pause or source permission change.",
        "capture_unknown": "Keep existing strict capture/state guards. Missing or unsupported later input uses a recorded common fallback and leaves that selected counterfactual unexecuted/unknown.",
        "references": "Within each case both initial families retain all four E windows, both first-return delays and both later actions. This is an offline finite reference, not an online choice oracle.",
        "witness": "A preference updated ACK alone is not a causal routing witness. Compare its actual edge to the matched default cell with all other coordinates fixed; identical edges are no-effect for that routing contrast.",
        "protection": "All five finite native completions at commonH40, exact per-job<=0, actual physical/FIFO/stock/transfer/route audits. Missing or unfinished comparisons remain unknown.",
        "unexecuted_policy": "All192 listed before first execution. Timeouts/failures/unrun cases remain unknown; no positive-case selection.",
        "complete_public_predictor": False, "online_model_claim": False, "method_novelty_claim": False}


def valid(row):
    summary = row.get("summary", {})
    times = summary.get("completion", {})
    vector = row.get("vector", {})
    first, later = summary.get("initial_actual_next"), summary.get("first_reuse_actual_next")
    return (row.get("status") == "assessed" and summary.get("business_complete") is True
        and summary.get("common_horizon_complete") is True and summary.get("audit", {}).get("status") == "passed"
        and summary.get("selected_actions_executed") is True and summary.get("all_required_inputs_verified") is True
        and type(first) is int and first in ((2,) if vector.get("initial_action") == "prefer_2" else (1, 2))
        and type(later) is int and later in ((8,) if vector.get("later_action") == "prefer_8" else (3, 8))
        and set(times) == JOBS and all(type(t) in (int, float) and math.isfinite(t) and 0 <= t <= 40. for t in times.values())
        and summary.get("completion_sum") == sum(times.values()))


def compare(rows):
    plan = matrix_protocol()
    declared = plan["rows"]
    if (set(rows) != set(declared) or any(any(row.get(field) != declared[key][field]
            for field in ("case", "vector", "method", "fault")) for key, row in rows.items())):
        return {"status": "unknown_incomplete_or_misbound_denominator", "expected_rows": 192}
    groups = {}
    for case_id, keys in plan["case_groups"].items():
        base = rows[plan["incumbent_keys"][case_id]]
        mapped = {key_for(rows[k]["vector"]): k for k in keys}
        comparison = {}
        for key in keys:
            row = rows[key]
            known = valid(base) and valid(row)
            times = row.get("summary", {}).get("completion", {})
            vector = row["vector"]
            contrasts = {}
            for coordinate, default, field in (("initial_action", "native_default", "initial_actual_next"),
                                                ("later_action", "native_default", "first_reuse_actual_next")):
                if vector[coordinate] == default: continue
                control_vector = {**vector, coordinate: default}
                control_key = mapped[key_for(control_vector)]; control = rows[control_key]
                pair_known = valid(row) and valid(control)
                actual, control_actual = row.get("summary", {}).get(field), control.get("summary", {}).get(field)
                has_edges = type(actual) is int and type(control_actual) is int
                contrasts[coordinate] = {"matched_default_key": control_key,
                    "status": "actual_edge_changed" if pair_known and has_edges and actual != control_actual else
                              "no_actual_edge_change" if pair_known and has_edges else "unknown",
                    "candidate_actual_next": actual, "default_actual_next": control_actual,
                    "strict_all_five_protection": all(times[j] <= control["summary"]["completion"][j] for j in JOBS) if pair_known else None}
            comparison[key] = {"status": "assessed" if known else "unknown",
                "strict_protected_vs_incumbent": all(times[j] <= base["summary"]["completion"][j] for j in JOBS) if known else None,
                "gain_vs_incumbent": base["summary"]["completion_sum"] - row["summary"]["completion_sum"] if known else None,
                "paired_route_contrasts": contrasts}
        family = {}
        for initial in vocabulary.INITIAL:
            members = [k for k in keys if rows[k]["vector"]["initial_action"] == initial]
            complete = valid(base) and all(valid(rows[k]) for k in members)
            eligible = [k for k in members if complete and all(rows[k]["summary"]["completion"][j] <= base["summary"]["completion"][j] for j in JOBS)]
            best = min(eligible, key=lambda k: (rows[k]["summary"]["completion_sum"], k), default=None)
            family[initial] = {"status": "complete_assessed_finite_reference" if complete else "unknown_incomplete_reference",
                "member_count": len(members), "required_member_keys": members, "best_protected_key": best,
                "offline_only_not_policy_input": True}
        groups[case_id] = {"rows": comparison, "fixed_initial_families": family}
    return {"status": "complete_declared_denominator", "row_count": 192, "cases": groups,
            "native_results_authenticated_here": False, "online_model_claim": False}

"""Finite intervention reference on genuine native checkpoint continuations.

This tool is offline: continuation may see the real common future, whereas
candidate construction must consume only the public observation. Results must
never be used as online policy features. Optimality refers only to a fully
enumerated supplied action domain at this one boundary, under one fixed future
and continuation policy. It is not an optimal continuous circulation solution.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
import copy
import hashlib
import json
import math
import time
from typing import Any, Protocol


class NativeBranch(Protocol):
    physical_time: float
    def fork(self) -> "NativeBranch": ...
    def submit_transfer_intent(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def submit_route_intent(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def result_at(self, horizon: float) -> dict[str, Any]: ...
    def observe(self, owner_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Intervention:
    action_id: str
    kind: str
    request: dict[str, Any] | None = None


def outcome_cost(result: dict[str, Any], job_contracts: list[dict[str, Any]],
                 horizon: float) -> dict[str, Any]:
    """All offered arrivals by H; unfinished jobs contribute restricted time.

    The transparent objective is sum of arrival-to-unload time truncated at H.
    Failed and unfinished tasks remain in the denominator; deadline and failure
    counts are separate, never silently priced as a small successful latency.
    """
    outcomes = {j["business_bag_id"]: j for j in result["jobs"]}
    if len(outcomes) != len(result["jobs"]):
        raise ValueError("finite_reference:duplicate_job_result")
    offered = [j for j in job_contracts if j["arrival"] <= horizon]
    if not {j["business_bag_id"] for j in offered} <= outcomes.keys():
        raise ValueError("finite_reference:missing_offered_job")
    restricted, completed, late, failed, pending, per_job = 0.0, 0, 0, 0, 0, []
    for contract in offered:
        job = outcomes[contract["business_bag_id"]]
        finish = float(job["completed_at"])
        done = 0 <= finish <= horizon
        cost = (finish if done else horizon) - float(contract["arrival"])
        if cost < -1e-8:
            raise ValueError("finite_reference:completion_before_arrival")
        restricted += max(0, cost)
        completed += done
        failed += job["status"] in ("failed", "quarantined")
        pending += not done
        deadline = float(contract.get("deadline", -1))
        violated = deadline >= 0 and ((done and finish > deadline + 1e-8) or
                                      (not done and horizon > deadline + 1e-8))
        late += violated
        per_job.append({"business_bag_id": contract["business_bag_id"],
                        "restricted_time": max(0, cost), "completed": done,
                        "completed_at": finish if done else None,
                        "deadline_violated_by_horizon": violated, "status": job["status"]})
    return {"objective": "sum_restricted_arrival_to_unload_time", "horizon": horizon,
            "cost": restricted, "offered": len(offered), "completed": completed,
            "unfinished": pending, "failed": failed, "deadline_violations": late,
            "per_job": per_job}


def service_dominates(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    """Post-run strict paired protection on the same offered population.

    It is evidence under this future, not an advance guarantee for all futures.
    """
    a = {j["business_bag_id"]: j for j in candidate["per_job"]}
    b = {j["business_bag_id"]: j for j in baseline["per_job"]}
    if a.keys() != b.keys():
        raise ValueError("finite_reference:incomparable_population")
    return all(a[k]["restricted_time"] <= b[k]["restricted_time"] + 1e-8
               and not (a[k]["deadline_violated_by_horizon"] and not b[k]["deadline_violated_by_horizon"])
               and not (a[k]["status"] in ("failed", "quarantined")
                        and b[k]["status"] not in ("failed", "quarantined"))
               for k in a)


def _horizon_completion(result: dict[str, Any], branch: NativeBranch, horizon: float,
                        outer_status: str | None = None) -> dict[str, Any]:
    """Fail closed before pricing a prefix as a complete common-horizon result."""
    raw_advance = result.get("advance", {})
    advance = raw_advance if isinstance(raw_advance, dict) else {}
    has_control = "control_continuation" in result
    raw_control = result.get("control_continuation", {})
    control = raw_control if isinstance(raw_control, dict) else {}
    values = {"requested_horizon": horizon, "result_horizon": result.get("horizon"),
              "physical_clock": result.get("physical_clock"),
              "advance_physical_time": advance.get("physical_time"),
              "branch_physical_time": getattr(branch, "physical_time", None)}
    if has_control:
        values["controller_requested_horizon"] = control.get("requested_horizon")
        values["controller_physical_time"] = control.get("physical_time")
    problems = []
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            problems.append(name + ":missing_or_nonfinite")
        elif abs(value - horizon) > 1e-8:
            problems.append(name + ":does_not_equal_requested_horizon")
    if advance.get("status") != "reached":
        problems.append("advance_not_reached")
    if outer_status is not None and outer_status != "reached":
        problems.append("outer_continuation_not_reached")
    if has_control and control.get("status") != "reached":
        problems.append("controller_continuation_not_reached")
    if result.get("status") in ("budget_exhausted", "censored", "failed", "timeout_unknown"):
        problems.append("result_explicitly_censored")
    if advance.get("horizon_complete") is not True or result.get("native_summary", {}).get("event_limit_reached"):
        problems.append("native_horizon_incomplete")
    return {"status": "reached" if not problems else "unknown", "problems": problems,
            "evidence": values, "advance_status": advance.get("status"), "outer_status": outer_status}


def enumerate_interventions(session: NativeBranch, actions: Iterable[Intervention], *,
                            horizon: float, job_contracts: list[dict[str, Any]],
                            baseline_action_id: str = "WAIT", max_branches: int = 128,
                            max_seconds: float = 30,
                            continuation: Callable[[NativeBranch, float], dict[str, Any]] | None = None,
                            validate: Callable[[dict[str, Any], Intervention], Any] | None = None,
                            strict_paired_service: bool = True) -> dict[str, Any]:
    """Fork once per alternative; replace one intervention, then same policy.

    Validate must independently replay receipts/physical invariants before an
    optimal-domain claim can be made. Without it all solutions stay unverified.
    Native rejection is recorded, not replaced by a silent successful WAIT.
    """
    if not math.isfinite(horizon) or horizon < session.physical_time or max_branches < 1 or max_seconds <= 0:
        raise ValueError("finite_reference:invalid_domain")
    alternatives = list(actions)
    ids = [a.action_id for a in alternatives]
    if len(set(ids)) != len(ids) or baseline_action_id not in ids:
        raise ValueError("finite_reference:invalid_action_identity_or_missing_baseline")
    if not any(a.kind == "wait" for a in alternatives):
        raise ValueError("finite_reference:wait_required")
    # Evaluate the actual baseline before optional branches when budget-limited.
    alternatives.sort(key=lambda a: (a.action_id != baseline_action_id, a.action_id))
    start = time.perf_counter()
    rows = []
    for action in alternatives:
        if len(rows) >= max_branches or time.perf_counter() - start >= max_seconds:
            break
        tick = time.perf_counter()
        branch = session.fork()
        reply: dict[str, Any] = {"status": "accepted", "reason": "wait"}
        if action.kind == "transfer":
            reply = branch.submit_transfer_intent(copy.deepcopy(action.request))
        elif action.kind == "route":
            reply = branch.submit_route_intent(copy.deepcopy(action.request))
        elif action.kind != "wait":
            raise ValueError("finite_reference:unknown_intervention")
        if reply.get("status") in ("rejected", "failed_no_safe_continuation", "timeout_unknown"):
            # A native permission rejection resolves this requested action.
            # Budget/solver inability does not prove the action infeasible.
            classification = "rejected" if reply["status"] == "rejected" else "unresolved_submission"
            rows.append({"action": asdict(action), "reply": reply, "status": classification,
                         "elapsed_seconds": time.perf_counter() - tick})
            continue
        continued = continuation(branch, horizon) if continuation else branch.result_at(horizon)
        outer_status = None
        if "result" in continued and "jobs" not in continued:
            declared_status = continued.get("status", "missing")
            outer_status = declared_status if isinstance(declared_status, str) else "invalid_status_type"
            result = continued["result"]
        else:
            result = continued
        completion = _horizon_completion(result, branch, horizon, outer_status)
        if completion["status"] != "reached":
            rows.append({"action": asdict(action), "reply": reply, "status": "incomplete_horizon",
                         "completion": completion,
                         "result": result, "elapsed_seconds": time.perf_counter() - tick})
            continue
        metrics = outcome_cost(result, job_contracts, horizon)
        audit = validate(result, action) if validate else None
        if validate and (not isinstance(audit, dict) or audit.get("status") != "passed"):
            raise ValueError("finite_reference:independent_audit_did_not_pass")
        resolution: dict[str, Any] = {"status": "wait", "reason": "no_intervention"}
        status = "verified" if validate else "unverified"
        if action.kind != "wait":
            request_id = action.request["request_id"]
            requests = (result["transfers"] if action.kind == "transfer" else
                        branch.observe(action.request["owner_id"])["route_requests"])
            resolved = next((r for r in requests if r["request_id"] == request_id), None)
            if resolved is None:
                raise ValueError("finite_reference:submitted_request_missing_from_resolution_ledger")
            resolution = {key: resolved.get(key) for key in ("status", "reason", "request_id")}
            success = {"received"} if action.kind == "transfer" else {"updated"}
            if resolved["status"] in ("rejected", "cancelled", "failed", "expired"):
                status = "asynchronous_rejected"
            elif resolved["status"] not in success:
                status = "unresolved_at_horizon"
        physical_events = {"EDGE_ENTER", "EDGE_EXIT", "LOAD_START", "LOAD_COMPLETE", "STORAGE_ENTER",
                           "STORAGE_RELEASE", "UNLOAD_START", "UNLOAD_COMPLETE", "HOLD_COMPLETE",
                           "EXPORT_GRANTED", "EMPTY_RECEIVED", "UNUSED_RECEIVING_RELEASED", "LEG_FAILED"}
        physical_trace = [{k: r[k] for k in ("time", "event", "tray_id", "business_bag_id", "node", "from", "to") if k in r}
                          for r in result.get("receipts", []) if r["event"] in physical_events]
        physical_identity = hashlib.sha256(json.dumps(physical_trace, sort_keys=True).encode()).hexdigest()
        rows.append({"action": asdict(action), "reply": reply,
                     "status": status, "execution_resolution": resolution,
                     "completion": completion,
                     "physical_outcome_sha256": physical_identity,
                     "metrics": metrics, "audit": audit, "result": result,
                     "elapsed_seconds": time.perf_counter() - tick})
    baseline = next((r for r in rows if r["action"]["action_id"] == baseline_action_id), None)
    eligible = []
    for row in rows:
        if "metrics" not in row or not baseline or "metrics" not in baseline:
            continue
        row["paired_service_preserved"] = service_dominates(row["metrics"], baseline["metrics"])
        if row["status"] == "verified" and (not strict_paired_service or row["paired_service_preserved"]):
            eligible.append(row)
    best = min(eligible, key=lambda r: (r["metrics"]["cost"], r["action"]["action_id"]), default=None)
    complete = len(rows) == len(alternatives) and all(
        r["status"] in ("verified", "rejected", "asynchronous_rejected") for r in rows)
    return {"schema": "g31.finite_intervention_reference.v1", "rows": rows,
            "domain_size": len(alternatives), "evaluated": len(rows), "exhaustive": complete,
            "best_action_id": best["action"]["action_id"] if best else None,
            "best_cost": best["metrics"]["cost"] if best else None,
            "optimality": "optimal_in_enumerated_domain" if complete and validate and best else "unknown",
            "global_native_optimality": "unknown", "elapsed_seconds": time.perf_counter() - start,
            "distinct_verified_physical_outcomes": len({r["physical_outcome_sha256"] for r in rows if r["status"] == "verified"}),
            "information_track": "offline_common_real_future_diagnostic",
            "strict_paired_service": strict_paired_service,
            "domain": "one intervention at this checkpoint; supplied finite actions; fixed continuation and future"}


def headroom(reference: dict[str, Any], deployed_action_ids: Iterable[str],
             selected_action_id: str, baseline_action_id: str) -> dict[str, Any]:
    costs = {r["action"]["action_id"]: r["metrics"]["cost"] for r in reference["rows"]
             if r["status"] == "verified" and r.get("paired_service_preserved", False)}
    pool = set(deployed_action_ids)
    if not costs or selected_action_id not in costs or baseline_action_id not in costs:
        return {"status": "not_comparable", "verified_candidate_count": len(costs)}
    pool_costs = [costs[a] for a in pool if a in costs]
    if not pool_costs:
        return {"status": "zero_deployment_candidates", "verified_candidate_count": len(costs)}
    best, pool_best = min(costs.values()), min(pool_costs)
    if selected_action_id not in pool:
        raise ValueError("finite_reference:selected_action_outside_deployment_pool")
    return {"status": "finite_domain_comparison", "verified_candidate_count": len(costs),
            "deployment_candidate_count": len(pool_costs),
            "reference_headroom": costs[baseline_action_id] - best,
            "pool_loss": pool_best - best, "ranking_loss": costs[selected_action_id] - pool_best,
            "complete_reference_domain": reference["exhaustive"],
            "global_lower_bound": None}

"""Observed-source-change repair of an owned, still-uncommitted return bundle.

This conventional one-round feedback is a strong comparator for P5, not a
novelty claim. It never cancels business tasks, hard grants or other owners'
commands. Valid incumbent return assignments are frozen while their obsolete
joint timing can be recomputed after an observed source promise disappears.
"""
from __future__ import annotations

import copy

from .analytic_control import release_forecasts
from .joint_window_repair import build_domain, digest, proposal_order, submit_action


def repair_observed_source_change(session, owner: str, owned_bundle_ids: list[str]) -> dict:
    observed = session.observe(owner)
    forecasts = {f.tray_id: f for f in release_forecasts(observed)}
    active = [r for r in observed["transfers"] if r["request_id"] in owned_bundle_ids
              and r["status"] in ("pending", "undelivered")]
    changed = [r for r in active if r["tray_id"] not in forecasts
               or forecasts[r["tray_id"]].node != r["source"]]
    if not changed:
        return {"status": "no_observed_source_change", "submissions": [], "cancellations": [],
                "observation": observed, "normal_service_guarantee": False}
    obsolete = {r["request_id"] for r in changed}
    retained = {(r["tray_id"], r["source"], r["destination"]) for r in active if r["request_id"] not in obsolete}
    cancellations = []
    for request in active:
        reply = session.cancel_transfer_intent(request["request_id"], owner)
        cancellations.append({"request_id": request["request_id"], "reply": reply,
                              "reason": "observed_source_changed" if request["request_id"] in obsolete
                                        else "retime_same_assignment_after_dependency_changed"})
        if reply["status"] != "cancelled":
            return {"status": "unknown_partial_repair", "submissions": [], "cancellations": cancellations,
                    "reason": "native_refused_soft_cancellation; no_hard_right_overridden"}
    fresh = session.observe(owner)
    domain = build_domain(fresh)
    if domain["status"] != "complete_finite_public_domain":
        return {"status": "unknown_partial_repair", "submissions": [], "cancellations": cancellations,
                "reason": domain["status"]}
    eligible = [a for a in domain["actions"] if not a["conditional_conflicts"] and
                {(c["request"]["tray_id"], c["request"]["source"], c["request"]["destination"])
                 for c in a["candidates"]} == retained]
    if not eligible:
        return {"status": "unknown_partial_repair", "submissions": [], "cancellations": cancellations,
                "reason": "retained_assignments_not_in_conditional_domain; not_physical_infeasibility"}
    action = copy.deepcopy(min(eligible, key=proposal_order))
    for candidate in action["candidates"]:
        candidate["request"]["request_id"] += ":repair:" + digest(fresh)[:16]
    submitted = submit_action(session, action, fresh)
    return {"status": "repair_submitted" if submitted["status"] == "submitted" else "unknown_partial_repair",
            "observation": observed, "fresh_observation": fresh, "changed_source_promises": changed,
            "retained_assignments": sorted(retained), "cancellations": cancellations,
            "selected_action": action, "submissions": submitted["submissions"],
            "normal_service_guarantee": False, "atomic": False,
            "scope": "one observed boundary; same incumbent valid assignments; conditional windows; native revalidation"}

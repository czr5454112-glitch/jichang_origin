"""Continuous post-priority selectors over the shared current-only menu."""
from __future__ import annotations

import copy

from .foundation_airport_batch_patch import SCHEMA as PATCH_SCHEMA, apply_patch, digest
from .foundation_airport_joint_opportunities import (
    SCHEMA, assert_prepared_current, build_joint_catalog, prepare_current, require)

CONTROL_CONTRACT = "post_priority_continuous_one_new_attempt_per_owner_tick_v1"


def select_joint_bridge(prepared, catalog):
    """Old eligibility/category; compare every source within the same category.

    The ordering retains observed-stock preference and ordinary-return priority,
    then minimizes public ETA, removing the previous source-node ID bias.
    """
    moves = [row for row in catalog["candidates"]
        if row["action_type"] == "transfer" and row["bridge_eligible"]]
    def key(row):
        known = row["destination_inventory_known"]
        return (row["source_category"] != "ordinary_return", not known,
            row["destination_actual_empty"] if known else 0,
            row["static_arrival_estimate"], row["source"], row["tray_id"], row["destination"])
    selected = min(moves, key=key) if moves else catalog["candidates"][0]
    return {"action_id": selected["action_id"], "catalog_id": catalog["catalog_id"],
        "policy": "R0_joint_bridge_v1", "reason": "joint_stock_return" if moves else "no_current_stock_return",
        "behavior_reference": "R0_joint_bridge_v1", "comparison_reference": "R0_joint_bridge_v1",
        "selection_probability": 1.}


def select_post_priority_action(prepared, catalog, policy, forecast=None):
    """A policy returns a canonical member ID; it never obtains submit authority."""
    return policy(prepared, catalog) if forecast is None else policy(prepared, catalog, forecast=forecast)


def apply_selected_action(prepared, catalog, choice):
    assert_prepared_current(prepared)
    require(catalog.get("schema") == SCHEMA, "catalog_schema")
    require(catalog["public_state_digest"] == prepared.public_state_digest
        and catalog["priority_baseline_digest"] == prepared.priority_baseline_digest
        and catalog["immutable_prefix_digest"] == prepared.immutable_prefix_digest, "catalog_binding")
    require(catalog["catalog_id"] == digest({key: value for key, value in catalog.items()
        if key not in ("reference_candidate_id", "catalog_id")}), "catalog_changed")
    choice = {"action_id": choice} if isinstance(choice, str) else choice
    require(choice.get("catalog_id", catalog["catalog_id"]) == catalog["catalog_id"], "choice_catalog_binding")
    candidates = {row["action_id"]: row for row in catalog["candidates"]}
    require(choice["action_id"] in candidates, "choice_outside_catalog")
    candidate = candidates[choice["action_id"]]
    if candidate["action_type"] == "noop":
        result = copy.deepcopy(prepared.baseline)
    else:
        action = {"schema": PATCH_SCHEMA, "kind": "add_optional",
            "action_id": candidate["action_id"], "tray_id": candidate["tray_id"],
            "intent": candidate["intent"], "public_state_digest": prepared.public_state_digest,
            "baseline_batch_digest": digest(prepared.baseline["intents"]),
            "immutable_request_prefix_digest": prepared.immutable_prefix_digest}
        result = apply_patch(prepared.observation, prepared.baseline, action)
    require(len(result["intents"]) <= 1, "single_addition_required")
    result["inventory_return"] = {"method": choice.get("policy", "joint_selector"),
        "selected": bool(result["intents"]), "added_intents": len(result["intents"]),
        "reason": choice.get("reason", "joint_transfer" if result["intents"] else "joint_noop")}
    result["joint_selection"] = {"control_contract": CONTROL_CONTRACT,
        "catalog_id": catalog["catalog_id"], "catalog_version": catalog["catalog_version"],
        "canonical_action": copy.deepcopy(candidate), "choice": copy.deepcopy(choice),
        "K": catalog["K"], "candidate_source_tray_count": catalog["candidate_source_tray_count"],
        "candidate_source_node_count": catalog["candidate_source_node_count"],
        "candidate_destination_count": catalog["candidate_destination_count"],
        "exclusions": catalog["exclusions"], "strict_nonharm_certified": False}
    return result


class JointPostPrioritySelector:
    """Adapter for the controller's versioned callback, with JSON-owned state.

    ``policy`` may be a closure over frozen weights, but any changing behavior
    state (including exploration RNG) must live in the passed ``policy_state``.
    ``decision_sink`` observes every legal selection, including no-op; it must
    not mutate the prepared view or override the selected action.
    """
    def __init__(self, policy=None, *, decision_sink=None):
        self.policy = policy
        self.decision_sink = decision_sink

    def on_submission(self, **kwargs):
        callback = getattr(self.policy, "on_submission", None)
        if callback is not None:
            callback(**kwargs)

    def on_priority_submission(self, **kwargs):
        callback = getattr(self.policy, "on_priority_submission", None)
        if callback is not None:
            callback(**kwargs)

    def __call__(self, observation, baseline, *, message_delay, request_prefix,
                 policy_state, decision_context):
        prepared = prepare_current(observation, baseline, message_delay=message_delay)
        catalog = build_joint_catalog(prepared)
        choice = (select_joint_bridge(prepared, catalog) if self.policy is None else
            self.policy(prepared, catalog, policy_state=policy_state, decision_context=decision_context))
        decision = apply_selected_action(prepared, catalog, choice)
        policy_state["decision_count"] = policy_state.get("decision_count", 0) + 1
        policy_state["last_decision_context"] = copy.deepcopy(decision_context)
        decision["joint_selection"]["decision_context"] = copy.deepcopy(decision_context)
        if self.decision_sink is not None:
            action_binding = digest({"intents": decision["intents"],
                "joint_selection": decision["joint_selection"]})
            self.decision_sink(prepared=prepared, catalog=catalog, choice=choice,
                decision=decision, decision_context=decision_context)
            require(action_binding == digest({"intents": decision["intents"],
                "joint_selection": decision["joint_selection"]}), "decision_sink_modified_selection")
        return decision

"""Actual joint proposals and same-owner finite-horizon cost transitions.

This is an offline evidence layer. Native arrival/completion truth is never an
actor input. A rejected proposal is data; an unclosed execution is not a zero
cost terminal. Each owner's intervals describe the same team cost and must not
be summed across owners to reconstruct the unique system objective.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from bisect import bisect_right
from collections import defaultdict

SCHEMA = "g31.foundation.airport_joint_trajectory.v1"
PAIR_SCHEMA = "g31.foundation.airport_joint_pair.v1"
DECISION_SCHEMA = "g31.foundation.airport_joint_decision.v1"


def require(condition, reason):
    if not condition:
        raise ValueError("airport_joint_dataset:" + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "finite_number")
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def validate_manifest(manifest):
    result = copy.deepcopy(manifest)
    for key in ("trajectory_id", "parent_uid", "lineage_family", "template_family",
                "execution_source_id", "native_domain_id", "joint_policy_version"):
        require(type(result.get(key)) is str and bool(result[key]), "manifest_" + key)
    require(result.get("split") in ("train", "dev", "test"), "parent_split")
    for key in ("environment_seed", "behavior_seed"):
        require(type(result.get(key)) is int, "manifest_" + key)
    start, end = number(result["physical_start"]), number(result["physical_end"])
    require(0 <= start < end and number(result["calendar_start_epoch_seconds"]) > 0,
            "declared_physical_and_absolute_calendar")
    return result


def validate_decision(row, manifest):
    """Validate recorded proposal identity without requiring successful effect."""
    result = copy.deepcopy(row)
    for key in ("decision_id", "owner_id", "phase", "public_observation_ref",
                "legal_catalog_ref", "reference_candidate_id", "action_support_key"):
        require(type(result.get(key)) is str and bool(result[key]), "decision_" + key)
    require(result.get("current_version") is not None, "decision_current_version")
    at = number(result["decision_time"])
    require(manifest["physical_start"] <= at < manifest["physical_end"], "decision_window")
    calendar = manifest["calendar_start_epoch_seconds"] + at
    require(number(result.get("calendar_time", calendar)) == calendar, "decision_calendar_binding")
    require(result.get("joint_policy_version", manifest["joint_policy_version"])
            == manifest["joint_policy_version"], "joint_policy_frozen_within_trajectory")
    action = result.get("requested_action")
    if type(action) is dict and "kind" not in action and "action_type" in action:
        action["kind"] = action["action_type"]
    require(type(action) is dict and type(action.get("action_id")) is str
            and bool(action["action_id"]) and action.get("kind") in ("noop", "transfer"),
            "actual_proposed_action")
    if action["kind"] == "transfer":
        require(all(action.get(key) is not None for key in ("tray_id", "source", "destination"))
                and action["source"] != action["destination"], "transfer_identity")
    mechanism = result.get("selection_mechanism")
    require(mechanism in ("randomized", "deterministic"), "recorded_selection_mechanism")
    probability = result.get("selection_probability")
    if mechanism == "randomized":
        require(probability is not None and 0 < number(probability) <= 1,
                "actual_randomized_proposal_probability")
    else:
        require(probability is None or number(probability) == 1.,
                "deterministic_is_not_randomized_propensity")
    execution_probability = result.get("execution_probability")
    require(execution_probability is None or 0 <= number(execution_probability) <= 1,
            "execution_probability_separate_from_proposal")
    require(type(result.get("features_current")) is dict and result["features_current"],
            "actual_current_feature_record")
    require(type(result.get("physical_failure", False)) is bool, "physical_failure_boolean")
    result.update(schema=DECISION_SCHEMA, calendar_time=calendar,
                  joint_policy_version=manifest["joint_policy_version"])
    for key in ("actual_submission", "fallback_reason", "request_id", "reply_or_rejection",
                "ack", "first_leg", "received_event", "forecast_id", "mapping_id",
                "model_available_at", "message_coverage"):
        result.setdefault(key, None)
    result.setdefault("physical_failure", False)
    result.setdefault("features_forecast", {})
    return result


def validate_cost_events(events, physical_clock):
    """Validate one row per bag, including not-yet-arrived offered business."""
    clock = number(physical_clock)
    result, identities = [], set()
    for raw in events:
        row = copy.deepcopy(raw)
        identity = row.get("business_bag_id")
        require(identity is not None and identity not in identities, "unique_business_population")
        identities.add(identity)
        arrival = number(row["arrival"])
        require(arrival >= 0, "nonnegative_arrival")
        completion = row.get("completion")
        if completion is not None:
            completion = number(completion)
            require(arrival <= completion <= clock, "observed_completion_clock")
        result.append(dict(business_bag_id=identity, arrival=arrival, completion=completion))
    return result


def interval_cost(events, start, end):
    """Exact nonnegative arrived-unfinished bag seconds on [start, end]."""
    start, end = number(start), number(end)
    require(0 <= start <= end, "cost_interval")
    return math.fsum(max(0., min(end, row["completion"] if row["completion"] is not None else end)
                         - max(start, row["arrival"])) for row in events)


class CostIntegral:
    """One event-area sweep, then O(log N) queries; no early future backlog."""

    def __init__(self, events):
        deltas = defaultdict(int)
        for row in events:
            deltas[row["arrival"]] += 1
            if row["completion"] is not None:
                deltas[row["completion"]] -= 1
        self.times, self.areas, self.counts = [], [], []
        area, count, previous = 0., 0, 0.
        for at in sorted(deltas):
            area += count*(at-previous)
            count += deltas[at]
            require(count >= 0, "cost_curve_nonnegative_population")
            self.times.append(at)
            self.areas.append(area)
            self.counts.append(count)
            previous = at

    def at(self, at):
        at = number(at)
        require(at >= 0, "nonnegative_cost_curve_query")
        index = bisect_right(self.times, at)-1
        return (self.areas[index]+self.counts[index]*(at-self.times[index])) if index >= 0 else 0.

    def between(self, start, end):
        require(number(start) <= number(end), "cost_interval")
        return self.at(end)-self.at(start)


def build_trajectory(manifest, decisions, cost_events, *, physical_clock,
                     process_status, logs_complete=True, business_population_complete=False):
    """Build MC labels and actual SARSA links; no ACK/success admission filter.

    ``completed`` means the process/export finished, not that all business bags
    completed. Reaching the preregistered physical end closes this finite
    evaluation even when some bags remain unfinished. A timeout does not.
    """
    manifest = validate_manifest(manifest)
    clock = number(physical_clock)
    require(clock >= 0 and type(logs_complete) is bool
            and type(business_population_complete) is bool, "execution_observation_status")
    require(process_status in ("completed", "crashed", "timeout", "interrupted", "missing"),
            "process_status")
    rows = [validate_decision(row, manifest) for row in decisions]
    require(len({row["decision_id"] for row in rows}) == len(rows), "unique_decision_identity")
    require(all(row["decision_time"] <= clock for row in rows), "decisions_actually_observed")
    events = validate_cost_events(cost_events, clock)
    curve = CostIntegral(events)
    closed = (process_status == "completed" and logs_complete and business_population_complete
              and clock >= manifest["physical_end"])
    end = manifest["physical_end"]
    groups = defaultdict(list)
    for row in rows:
        groups[row["owner_id"]].append(row)
    for owner_rows in groups.values():
        owner_rows.sort(key=lambda row: (row["decision_time"], row["decision_id"]))
        require(all(a["decision_time"] < b["decision_time"]
                    for a, b in zip(owner_rows, owner_rows[1:])), "one_decision_per_owner_tick")
        for index, row in enumerate(owner_rows):
            successor = owner_rows[index+1] if index+1 < len(owner_rows) else None
            next_time = successor["decision_time"] if successor else (end if closed else None)
            row.update(next_decision_id=successor["decision_id"] if successor else None,
                       next_decision_time=next_time,
                       next_public_observation=successor["public_observation_ref"] if successor else None,
                       actual_next_action=copy.deepcopy(successor["requested_action"]) if successor else None,
                       next_owner_id=successor["owner_id"] if successor else None,
                       next_joint_policy_version=successor["joint_policy_version"] if successor else None,
                       next_features_current=copy.deepcopy(successor["features_current"]) if successor else None,
                       next_features_forecast=copy.deepcopy(successor["features_forecast"]) if successor else None,
                       interval_cost=(curve.between(row["decision_time"], next_time)
                                      if closed else None),
                       closed_mc_cost=(curve.between(row["decision_time"], end) if closed else None),
                       elapsed_time=(next_time-row["decision_time"] if next_time is not None else None),
                       terminated=bool(closed and successor is None), truncated=not closed,
                       target_status="observed_closed" if closed else "censored_unknown",
                       bootstrap_eligible=bool(closed and successor is not None),
                       unexecuted_candidate_label=False)
    rows.sort(key=lambda row: (row["decision_time"], row["owner_id"], row["decision_id"]))
    result = dict(schema=SCHEMA, manifest=manifest, process_status=process_status,
                  scientific_status="closed_finite_horizon" if closed else "censored_unknown",
                  physical_clock=clock, logs_complete=logs_complete,
                  business_population_complete=business_population_complete,
                  population_count=len(events), cost_events_sha256=digest(events), rows=rows,
                  system_J=curve.between(manifest["physical_start"], end) if closed else None,
                  system_J_computation="one_unique_native_population_integral",
                  owner_interval_costs_may_overlap=True, success_filter_applied=False,
                  estimated_optimal_Q=False)
    result["dataset_id"] = digest(result)
    return result


def validate_split_lineage(trajectories):
    """Branches/replays of one parent cannot migrate to a different split."""
    splits = {}
    for trajectory in trajectories:
        manifest = validate_manifest(trajectory["manifest"])
        key = manifest["parent_uid"]
        identity = (manifest["split"], manifest["lineage_family"], manifest["template_family"])
        require(key not in splits or splits[key] == identity, "parent_lineage_split_collision")
        splits[key] = identity
    return splits


def make_paired_label(reference, alternative, *, reference_decision_id,
                      alternative_decision_id, pairing):
    """Only measured common-root branches yield a signed alternative-minus-ref label."""
    for trajectory in (reference, alternative):
        require(trajectory.get("schema") == SCHEMA
                and trajectory["scientific_status"] == "closed_finite_horizon", "closed_actual_pair")
    left, right = reference["manifest"], alternative["manifest"]
    fields = ("parent_uid", "lineage_family", "template_family", "split", "environment_seed",
              "execution_source_id", "native_domain_id", "joint_policy_version", "physical_start",
              "physical_end", "calendar_start_epoch_seconds")
    require(all(left[key] == right[key] for key in fields), "same_parent_domain_continuation_and_window")
    require(left["trajectory_id"] != right["trajectory_id"], "distinct_actual_branch_executions")
    for key in ("root_id", "physical_control_prefix_sha256", "delivered_messages_sha256",
                "exogenous_input_sha256", "continuation_policy_version"):
        require(type(pairing.get(key)) is str and bool(pairing[key]), "pair_evidence_"+key)
        require(left.get("pairing", {}).get(key) == right.get("pairing", {}).get(key) == pairing[key],
                "actual_branch_pair_binding_"+key)
    require(pairing["continuation_policy_version"] == left["joint_policy_version"], "pair_continuation")
    lrows = {row["decision_id"]: row for row in reference["rows"]}
    rrows = {row["decision_id"]: row for row in alternative["rows"]}
    require(reference_decision_id in lrows and alternative_decision_id in rrows, "actual_paired_decisions")
    a, b = lrows[reference_decision_id], rrows[alternative_decision_id]
    require(all(a[key] == b[key] for key in ("owner_id", "decision_time", "current_version",
                "public_observation_ref", "legal_catalog_ref")), "same_public_root")
    require(a["requested_action"] != b["requested_action"], "actual_root_action_difference")
    require(a["requested_action"]["action_id"] == a["reference_candidate_id"], "actual_reference_action")
    result = dict(schema=PAIR_SCHEMA, parent_uid=left["parent_uid"], split=left["split"],
                  pairing=copy.deepcopy(pairing), continuation_policy_version=left["joint_policy_version"],
                  reference_dataset_id=reference["dataset_id"], alternative_dataset_id=alternative["dataset_id"],
                  reference_decision_id=reference_decision_id, alternative_decision_id=alternative_decision_id,
                  reference_features_current=a["features_current"], alternative_features_current=b["features_current"],
                  reference_features_forecast=a["features_forecast"], alternative_features_forecast=b["features_forecast"],
                  reference_J=reference["system_J"], alternative_J=alternative["system_J"],
                  delta_J=alternative["system_J"]-reference["system_J"],
                  delta_continuation_cost=b["closed_mc_cost"]-a["closed_mc_cost"],
                  unexecuted_winner_claimed=False)
    residual = result["delta_J"]-result["delta_continuation_cost"]
    tolerance = max(1e-8, 16.*max(math.ulp(abs(number(value))) for value in
        (reference["system_J"], alternative["system_J"], a["closed_mc_cost"], b["closed_mc_cost"])))
    result["equal_prefix_cost_residual"] = residual
    result["equal_prefix_cost_roundoff_tolerance"] = tolerance
    require(abs(residual) <= tolerance,
            "equal_prefix_cost_required")
    result["pair_id"] = digest(result)
    return result

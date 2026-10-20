"""Prospective isolated R2 decisions from shared current public candidates.

No evaluator state, future workload, labels or conditional native rollout is
accepted. Native source/receiver admission still decides each real submission;
the shared-resource per-job protection gap precludes protected deployment.
"""
from __future__ import annotations

from collections import Counter
import copy
import math
import time

from .analytic_control import transfer_candidates
from .foundation_airport_batch_patch import (
    actual_uncommitted, apply_patch, digest, require)
from .foundation_airport_opportunities import build_opportunity
from .foundation_airport_paired_continuation import validate_parent


SCHEMA = "g31.foundation.airport_prospective_control.v1"
VARIANTS = ("C00", "C01", "C10", "C11")


def current_candidate_rows(observation, baseline, opportunity, *, parent,
                           information_variant, forecast_evidence=None, patch_rank=1,
                           copy_inputs=True):
    """Build two inference inputs with no rollout result or target fields."""
    require(information_variant in VARIANTS, "prospective_information_variant")
    require(opportunity["public_state_digest"] == digest(observation)
        and opportunity["baseline_batch_digest"] == digest(baseline["intents"])
        and opportunity["owner_id"] == observation["owner_id"]
        and opportunity["observed_at"] == observation["now"], "prospective_current_binding")
    require(opportunity["catalog_uses_future_plan"] is False
        and 1 <= patch_rank < opportunity["K"] <= 13, "common_plan_independent_bounded_catalog")
    parent = validate_parent(parent)
    action = opportunity["candidates"][patch_rank]
    target = action["tray_id"]
    supplies = {row["tray_id"]: row for row in actual_uncommitted(observation, baseline)}
    require(target in supplies, "prospective_tray_must_be_current_actual_surplus")
    decisions = (apply_patch(observation, baseline, opportunity["candidates"][0]),
                 apply_patch(observation, baseline, action))
    clone = copy.deepcopy if copy_inputs else lambda value: value
    rows = []
    for index, decision in enumerate(decisions):
        allocation = next((row for row in decision["intents"] if row.get("tray_id") == target), None)
        semantic = {"tray_id": target, "kind": "transfer" if allocation else "hold_optional",
            "source": supplies[target]["node"], "destination": allocation["destination"] if allocation else None,
            "earliest_departure": allocation["earliest_departure"] if allocation else None,
            "transfer_scope": allocation.get("transfer_scope", "cross_zone_transfer") if allocation else None}
        row = {"schema": SCHEMA, "parent": clone(parent),
            "branch": "a_ref" if index == 0 else "a_patch",
            "observation": clone(observation), "opportunity": clone(opportunity),
            "baseline_decision": clone(baseline),
            "action": clone(opportunity["candidates"][0 if index == 0 else patch_rank]),
            "semantic_action": semantic, "information_variant": information_variant}
        if information_variant in ("C10", "C11"):
            require(isinstance(forecast_evidence, dict), "plan_variant_requires_actual_forecast_receipt")
            row["forecast_evidence"] = clone(forecast_evidence)
        rows.append(row)
    if information_variant in ("C10", "C11"):
        from .foundation_airport_pair_ranker import _forecast
        # Both candidates share the same evidence object contents/current.
        # Validate the actual owner preload, absolute clock and model lineage.
        _forecast(rows[0])
    return rows


class ProspectivePlanner:
    """Score exactly reference versus one patch on each fresh initial callback."""

    def __init__(self, base_planner=None, *, parent, policy_id, information_variant,
                 selector=None, forecast_at=None, activate_at=7200., patch_rank=1,
                 continuation_version="airport_local_return_analytic_v1", k_max=3,
                 record_sink=None, retain_records=True, capture_all_callbacks=False,
                 deployment_contract=None, score_all_candidates=False, reference_champion=False):
        require(information_variant in VARIANTS, "prospective_information_variant")
        require(isinstance(policy_id, str) and policy_id, "prospective_policy_identity")
        require(type(activate_at) in (float, int) and math.isfinite(activate_at) and activate_at >= 0,
            "prospective_activation_time")
        require(information_variant == "C00" or reference_champion or callable(selector), "explicit_prospective_selector")
        require(information_variant not in ("C10", "C11") or reference_champion or callable(forecast_at),
            "actual_preloaded_forecast_provider")
        require(type(patch_rank) is int and 1 <= patch_rank < k_max <= 13, "prospective_candidate_bound")
        self.base_planner = base_planner or transfer_candidates
        self.parent = validate_parent(parent)
        self.policy_id, self.information_variant = policy_id, information_variant
        self.selector, self.forecast_at = selector, forecast_at
        self.activate_at, self.patch_rank, self.k_max = activate_at, patch_rank, k_max
        self.continuation_version = continuation_version
        self.record_sink = record_sink
        self.retain_records = retain_records
        self.capture_all_callbacks = capture_all_callbacks
        self.deployment_contract = copy.deepcopy(deployment_contract)
        if deployment_contract is not None:
            require(deployment_contract["max_policy_replacements"] == 1
                and deployment_contract["continuation_policy_id"] == continuation_version
                and deployment_contract["label_horizon_seconds"] == 1800.,
                "prospective_one_replacement_matches_label_continuation")
        self.score_all_candidates = bool(score_all_candidates)
        self.reference_champion = bool(reference_champion)
        self._policy_replacements = 0
        self.records = []
        self.counts = Counter()
        self._held = {}
        self._last_evaluated = {}

    def _emit(self, record, observation, baseline, result, began, options):
        record.update(planning_wall_ms=1000.*(time.perf_counter()-began),
            observation=observation, baseline_decision=baseline, chosen_decision=result,
            planner_options=options)
        self.counts["recorded_callbacks"] += 1
        if self.record_sink is not None:
            self.record_sink(record)
        if self.retain_records:
            self.records.append(copy.deepcopy(record))

    def __call__(self, observation, **options):
        began = time.perf_counter()
        baseline = self.base_planner(observation, **options)
        owner, now = observation["owner_id"], observation["now"]
        self.counts["callbacks"] += 1
        held = self._held.get(owner)
        if held is not None and held[0] == now:
            baseline = copy.deepcopy(baseline)
            baseline["intents"] = [row for row in baseline["intents"] if row.get("tray_id") != held[1]]
        residual = str(options.get("request_prefix", "")).endswith(":residual")
        if residual:
            self.counts["residual_callbacks_without_scoring"] += 1
            return baseline
        if now < self.activate_at:
            self.counts["warmup_callbacks"] += 1
            if self.capture_all_callbacks:
                self._emit({"schema": SCHEMA, "policy_id": self.policy_id, "owner_id": owner,
                    "observed_at": now, "status": "ordinary_warmup", "information_variant": self.information_variant,
                    "selected_action_id": "a_ref"}, observation, baseline, baseline, began, options)
            return baseline
        if self._last_evaluated.get(owner) == now:
            self.counts["duplicate_owner_timestamp_without_scoring"] += 1
            return baseline
        self._last_evaluated[owner] = now
        record = {"schema": SCHEMA, "policy_id": self.policy_id,
            "information_variant": self.information_variant, "owner_id": owner, "observed_at": now,
            "public_state_digest": digest(observation), "baseline_batch_digest": digest(baseline["intents"]),
            "selected_action_id": "a_ref", "proposed_patch_submitted": False,
            "native_execution_authority": False, "strict_nonharm_certified": False,
            "mode": "isolated_evaluation_only", "model_generalization_validated": False}
        result = baseline
        try:
            opportunity = build_opportunity(observation, baseline,
                continuation_version=self.continuation_version, k_max=self.k_max,
                message_delay=options.get("message_delay", 0.),
                respect_service_forecasts=options.get("respect_service_forecasts", False))
            record["opportunity"] = opportunity
            if self.reference_champion:
                self.counts["reference_champion_callbacks"] += 1
                record["status"] = "reference_champion"
            elif self.deployment_contract is not None and self._policy_replacements >= 1:
                self.counts["fixed_continuation_after_one_replacement"] += 1
                record["status"] = "fixed_continuation_after_one_replacement"
            elif self.information_variant == "C00":
                self.counts["reference_rule_callbacks"] += 1
                record["status"] = "reference_rule"
            elif opportunity["K"] <= self.patch_rank:
                self.counts["singleton_or_unsupported_patch"] += 1
                record["status"] = "reference_no_distinct_current_candidate"
            else:
                forecast_evidence = (self.forecast_at(observation=observation, parent=self.parent)
                    if self.information_variant in ("C10", "C11") else None)
                selector_started = time.perf_counter()
                ranked = []
                best = None
                ranks = range(1, opportunity["K"]) if self.score_all_candidates else (self.patch_rank,)
                for patch_rank in ranks:
                    rows = current_candidate_rows(observation, baseline, opportunity,
                        parent=self.parent, information_variant=self.information_variant,
                        forecast_evidence=forecast_evidence, patch_rank=patch_rank, copy_inputs=False)
                    require(record["public_state_digest"] == digest(observation),
                        "current_observation_mutated_during_forecast")
                    score = self.selector(*rows)
                    explanation = score if isinstance(score, dict) else None
                    gain = score["advantage"] if explanation is not None else score
                    require(type(gain) in (int, float) and math.isfinite(gain), "finite_prospective_advantage")
                    if explanation is not None and explanation.get("supported") is not True:
                        gain = 0.
                    ranked.append({"patch_rank": patch_rank, "advantage": gain, "support": explanation})
                    if best is None or gain > best[0]:
                        best = gain, patch_rank, rows
                gain, chosen_rank, rows = best
                record["candidate_scores"] = ranked
                record["selector_wall_ms"] = 1000.*(time.perf_counter()-selector_started)
                record["selector_timing_scope"] = (
                    "current validation, feature construction and fixed selector inference; excludes native and audit")
                require(type(gain) in (int, float) and math.isfinite(gain), "finite_prospective_advantage")
                self.counts["actual_scored_callbacks"] += 1
                choose_patch = gain > 0.
                action = opportunity["candidates"][chosen_rank if choose_patch else 0]
                result = apply_patch(observation, baseline, action)
                record.update(status="isolated_current_patch_proposed" if choose_patch else "reference_selected",
                    predicted_patch_advantage=float(gain), selected_action_id=action["action_id"],
                    selected_semantic_action=rows[1 if choose_patch else 0]["semantic_action"],
                    inference_rows=rows)
                if choose_patch:
                    self.counts["proposed_patch_callbacks"] += 1
                    self._policy_replacements += 1
                    if action["kind"] == "hold_optional":
                        self._held[owner] = now, action["tray_id"]
        except (ValueError, KeyError, TypeError) as exc:
            self.counts["invalid_current_or_model_reference_fallback"] += 1
            record.update(status="reference_fallback", reason=str(exc))
        record["policy_replacements_proposed"] = self._policy_replacements
        record["deployment_contract"] = self.deployment_contract
        self._emit(record, observation, baseline, result, began, options)
        return result

    def report(self):
        return {"schema": SCHEMA, "policy_id": self.policy_id, "parent": self.parent,
            "information_variant": self.information_variant, "activation_at": self.activate_at,
            "counts": dict(self.counts), "records": copy.deepcopy(self.records),
            "records_retained_in_memory": self.retain_records,
            "state": self.state_snapshot(),
            "deployment_contract": copy.deepcopy(self.deployment_contract),
            "strict_nonharm_certified": False, "native_jobs_started_by_planner": 0,
            "scope": "prospective isolated one-patch controller; actual submit/ACK evidence is separate"}

    def state_snapshot(self):
        return {"held_optional": copy.deepcopy(self._held),
            "last_evaluated_at_by_owner": copy.deepcopy(self._last_evaluated),
            "policy_replacements_proposed": self._policy_replacements}


def make_prospective_planner(base_planner=None, **options):
    return ProspectivePlanner(base_planner, **options)


def make_ranker_planner(model, base_planner=None, **options):
    """A frozen paired ranker proposes a real action; caller owns native submit."""
    from .foundation_airport_pair_ranker import prepare_predictor
    frozen = copy.deepcopy(model)
    variant = frozen["information_variant"]
    require(variant in ("C01", "C11"), "independently_fitted_C01_or_C11_required")
    if frozen.get("schema") == "g31.foundation.airport_supported_difference_ranker.v1":
        options.setdefault("deployment_contract", frozen["contract"]["policy_alignment"])
        options.setdefault("continuation_version", frozen["contract"]["policy_alignment"]["continuation_policy_id"])
        options.setdefault("score_all_candidates", True)
        options.setdefault("k_max", 13)
        options.setdefault("reference_champion", frozen["reference_champion"])
    return ProspectivePlanner(base_planner, information_variant=variant,
        policy_id=frozen["model_id"],
        selector=prepare_predictor(frozen), **options)

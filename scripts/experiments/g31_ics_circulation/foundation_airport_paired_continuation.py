"""Public bounded interventions plus evaluator-only exact replay-prefix binds.

This module neither restores checkpoints nor starts native processes. The
campaign owns two budgeted full replays from physical zero and all deadlines.
"""
from __future__ import annotations

from collections import Counter
import copy
import math

from .analytic_control import transfer_candidates
from .foundation_airport_batch_patch import apply_patch, digest, require
from .foundation_airport_opportunities import build_opportunity


SCHEMA = "g31.foundation.airport_paired_continuation.v1"
PARENT_SPLITS = {701: "train", 702: "train", 801: "dev", 802: "dev", 901: "test", 902: "test"}


def validate_parent(parent):
    require(isinstance(parent, dict) and parent.get("split") in
        ("train", "dev", "test", "mechanism", "historical_development"),
        "explicit_parent_split")
    seed = parent.get("parent_seed", parent.get("seed"))
    if seed is not None and seed in PARENT_SPLITS:
        require(parent["split"] == PARENT_SPLITS[seed], "parent_split_cannot_be_reassigned")
    require(parent.get("parent_group") or parent.get("parent_id") or seed is not None,
        "physical_parent_identity")
    return copy.deepcopy(parent)


def exact_prefix(native_state_sha256, controller_state, observation):
    """Hash full native checkpoint state plus controller/client, never actor input.

    Native state SHA covers physical state, queued messages, pending leases,
    RNG and irreversible requests. The separate client/controller SHA covers
    the outbox, delivered ACK views, retry timing and control phase.
    """
    require(isinstance(native_state_sha256, str) and len(native_state_sha256) == 64
        and all(c in "0123456789abcdef" for c in native_state_sha256), "native_full_state_sha256")
    client = controller_state.get("client")
    require(isinstance(client, dict) and isinstance(client.get("outbox"), dict)
        and isinstance(client.get("sequences"), dict), "full_controller_client_state_required")
    result = {"native_state_sha256": native_state_sha256,
        "controller_state_sha256": digest(controller_state),
        "client_state_sha256": digest(client), "public_state_sha256": digest(observation),
        "physical_time": observation["now"], "owner_id": observation["owner_id"],
        "native_hash_scope": "full_native_state_including_protocol_pending_and_rng",
        "state_access_scope": "offline_evaluator_only", "replay_mode": "full_warmup_from_zero"}
    result["complete_prefix_sha256"] = digest(result)
    return result


class PairedPlanner:
    """Change at most one opportunity, then continue the same fixed baseline."""

    def __init__(self, base_planner=None, *, branch, window, parent,
                 continuation_version, anchor_rank=0, patch_rank=1, k_max=3):
        require(branch in ("a_ref", "a_patch"), "branch_must_be_a_ref_or_a_patch")
        require(len(window) == 2 and all(type(v) in (int, float) and math.isfinite(v) for v in window)
            and 0 <= window[0] <= window[1], "registered_anchor_window")
        require(type(anchor_rank) is int and anchor_rank >= 0
            and type(patch_rank) is int and 1 <= patch_rank < k_max <= 3, "bounded_fixed_ranks")
        require(isinstance(continuation_version, str) and continuation_version, "fixed_continuation_version")
        self.base_planner = base_planner or transfer_candidates
        self.branch, self.window = branch, tuple(window)
        self.parent, self.continuation_version = validate_parent(parent), continuation_version
        self.anchor_rank, self.patch_rank, self.k_max = anchor_rank, patch_rank, k_max
        self.records = []
        self.selected = None
        self.successor = None
        self.counts = Counter()
        self.mask_reasons = Counter()
        self._pending_record = None
        self._held = None

    @property
    def needs_prefix(self):
        return self._pending_record is not None

    @property
    def label_end(self):
        return None if self.selected is None else self.selected["observed_at"] + 1800.

    def bind_prefix(self, *, native_state_sha256, controller_state, observation):
        """Call only from a campaign evaluator after planning, before submit."""
        require(self._pending_record is not None, "no_pending_prefix_binding")
        row = self._pending_record
        require(row["opportunity"]["public_state_digest"] == digest(observation),
            "prefix_observation_changed")
        bound_controller = dict(controller_state,
            paired_selector_state=row["selector_state_before_action"])
        row["prefix"] = exact_prefix(native_state_sha256, bound_controller, observation)
        self._pending_record = None
        return copy.deepcopy(row["prefix"])

    def _opportunity(self, observation, baseline, options):
        return build_opportunity(observation, baseline,
            continuation_version=self.continuation_version, k_max=self.k_max,
            message_delay=options.get("message_delay", 0.),
            respect_service_forecasts=options.get("respect_service_forecasts", False))

    def _selector_state(self, *, selected):
        # This is controller memory, distinct from the chosen intervention.
        # The two branch modes may differ only after the common anchor state.
        return {"window": list(self.window), "anchor_rank": self.anchor_rank,
            "patch_rank": self.patch_rank, "k_max": self.k_max, "parent": self.parent,
            "continuation_version": self.continuation_version,
            "eligible_opportunities_seen": self.counts["eligible_opportunities"],
            "intervention_already_applied": selected,
            "held_optional_tray": (self.selected["chosen_action"]["tray_id"]
                if selected and self._held else None), "hold_owner_timestamp": self._held}

    def __call__(self, observation, **options):
        # Planner has no session/native/evaluator interface.
        baseline = self.base_planner(observation, **options)
        now, owner = observation["now"], observation["owner_id"]
        residual = str(options.get("request_prefix", "")).endswith(":residual")
        self.counts["callbacks"] += 1
        if self._held == (owner, now):
            baseline = copy.deepcopy(baseline)
            baseline["intents"] = [row for row in baseline["intents"]
                if row.get("tray_id") != self.selected["chosen_action"]["tray_id"]]
        if residual:
            self.counts["residual_callbacks"] += 1
            return baseline
        require(self._pending_record is None, "evaluator_must_bind_prefix_before_next_callback")
        if self.selected is not None:
            if self.successor is None and owner == self.selected["owner_id"] and now > self.selected["observed_at"]:
                opportunity = self._opportunity(observation, baseline, options)
                self.successor = {"schema": SCHEMA, "kind": "actual_natural_successor",
                    "owner_id": owner, "observed_at": now, "opportunity": opportunity,
                    "observation": copy.deepcopy(observation), "baseline_decision": copy.deepcopy(baseline),
                    "options": copy.deepcopy(options), "parent": self.parent,
                    "selector_state_before_action": self._selector_state(selected=True),
                    "actual_elapsed_seconds": now - self.selected["observed_at"],
                    "candidate_labels": None, "supported_actions": [],
                    "support_status": "requires_actual_submission_or_wait_binding"}
                self.records.append(self.successor)
                self._pending_record = self.successor
            return baseline
        if not self.window[0] <= now <= self.window[1]:
            return baseline
        self.counts["in_window_initial_callbacks"] += 1
        opportunity = self._opportunity(observation, baseline, options)
        self.mask_reasons.update(opportunity["mask_reasons"])
        if len(opportunity["candidates"]) <= self.patch_rank:
            self.counts["insufficient_distinct_candidates"] += 1
            return baseline
        rank = self.counts["eligible_opportunities"]
        self.counts["eligible_opportunities"] += 1
        if rank != self.anchor_rank:
            return baseline
        chosen = opportunity["candidates"][0 if self.branch == "a_ref" else self.patch_rank]
        result = apply_patch(observation, baseline, chosen)
        self.selected = {"schema": SCHEMA, "kind": "paired_intervention", "branch": self.branch,
            "owner_id": owner, "observed_at": now, "opportunity": opportunity,
            "observation": copy.deepcopy(observation), "baseline_decision": copy.deepcopy(baseline),
            "options": copy.deepcopy(options), "parent": self.parent,
            "selector_state_before_action": self._selector_state(selected=False),
            "chosen_action": copy.deepcopy(chosen), "chosen_decision": copy.deepcopy(result),
            "continuation_version": self.continuation_version,
            "registered_window": list(self.window), "eligible_rank": rank,
            "patch_rank": self.patch_rank, "candidate_labels": None,
            "label_start": now, "label_end": now + 1800.,
            "strict_nonharm_certified": False, "protected_takeover": False}
        self.records.append(self.selected)
        self._pending_record = self.selected
        if chosen["kind"] == "hold_optional":
            self._held = owner, now
        return result

    def report(self):
        return {"schema": SCHEMA, "branch": self.branch, "parent": self.parent,
            "window": list(self.window), "anchor_rank": self.anchor_rank, "patch_rank": self.patch_rank,
            "continuation_version": self.continuation_version, "counts": dict(self.counts),
            "mask_reasons": dict(self.mask_reasons), "selected": copy.deepcopy(self.selected),
            "successor": copy.deepcopy(self.successor),
            "status": "anchor_selected" if self.selected is not None else "no_eligible_anchor",
            "native_processes_started_by_planner": 0, "counterfactual_labels_generated": 0}


def make_paired_planner(base_planner=None, **options):
    return PairedPlanner(base_planner, **options)

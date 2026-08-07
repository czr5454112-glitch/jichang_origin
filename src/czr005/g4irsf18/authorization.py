"""Fail-closed authorization and control telemetry for G18 experiments."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .features import DecisionHead


class ClosedLoopMode(str, Enum):
    SHADOW = "shadow"
    RESEARCH_CLOSED_LOOP = "research_closed_loop"
    PRODUCTION_CLOSED_LOOP = "production_closed_loop"


class AuthorizationReason(str, Enum):
    APPLIED = "APPLIED"
    NO_TRUE_OPPORTUNITY = "NO_TRUE_OPPORTUNITY"
    KILL_SWITCH = "KILL_SWITCH"
    SHADOW_MODE = "SHADOW_MODE"
    RESEARCH_NOT_AUTHORIZED = "RESEARCH_NOT_AUTHORIZED"
    RESEARCH_WORKLOAD_NOT_FIXED = "RESEARCH_WORKLOAD_NOT_FIXED"
    PRODUCTION_OFFLINE_GATE = "PRODUCTION_OFFLINE_GATE"
    PRODUCTION_NOT_AUTHORIZED = "PRODUCTION_NOT_AUTHORIZED"
    INELIGIBLE = "INELIGIBLE"
    OOD = "OOD"
    SUPERVISOR_REJECT = "SUPERVISOR_REJECT"
    SHIELD_REJECT = "SHIELD_REJECT"
    HOLD_CAP = "HOLD_CAP"
    OVERRIDE_CAP = "OVERRIDE_CAP"
    COVERAGE_CAP = "COVERAGE_CAP"


@dataclass(frozen=True)
class AuthorizationGrants:
    """Independent grants; research evidence never mutates production state."""

    research_closed_loop: bool = False
    production_closed_loop: bool = False
    offline_gate_passed: bool = False


@dataclass(frozen=True)
class ClosedLoopLimits:
    coverage_cap: float = 0.05
    max_consecutive_holds: int = 1
    max_overrides_per_segment: int = 2

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.coverage_cap)) or not 0.0 <= self.coverage_cap <= 1.0:
            raise ValueError("COVERAGE_CAP_OUT_OF_RANGE")
        if self.max_consecutive_holds < 0:
            raise ValueError("HOLD_CAP_MUST_BE_NONNEGATIVE")
        if self.max_overrides_per_segment < 0:
            raise ValueError("OVERRIDE_CAP_MUST_BE_NONNEGATIVE")


@dataclass(frozen=True)
class DecisionAuthorizationRequest:
    """Runtime facts for one proposed local action.

    Segment counters are supplied by the local owner.  No segment/task/bag ID
    is passed to the model or retained by this authorizer.
    """

    head: DecisionHead
    baseline_index: int
    proposed_index: int
    legal_action_count: int
    eligible: bool = True
    normal_flow: bool = True
    ood: bool = False
    supervisor_authorized: bool = True
    shield_authorized: bool = True
    proposed_is_hold: bool = False
    consecutive_hold_count: int = 0
    segment_override_count: int = 0
    fallback_family: str = "F2"
    terminal_safety_event: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.head, DecisionHead):
            raise ValueError("UNKNOWN_DECISION_HEAD")
        if self.legal_action_count <= 0:
            raise ValueError("LEGAL_ACTION_COUNT_MUST_BE_POSITIVE")
        for name, value in (
            ("BASELINE_INDEX", self.baseline_index),
            ("PROPOSED_INDEX", self.proposed_index),
        ):
            if value < 0 or value >= self.legal_action_count:
                raise ValueError(f"{name}_OUT_OF_RANGE")
        if self.consecutive_hold_count < 0:
            raise ValueError("CONSECUTIVE_HOLD_COUNT_MUST_BE_NONNEGATIVE")
        if self.segment_override_count < 0:
            raise ValueError("SEGMENT_OVERRIDE_COUNT_MUST_BE_NONNEGATIVE")
        if not str(self.fallback_family).strip():
            raise ValueError("FALLBACK_FAMILY_REQUIRED")
        if self.terminal_safety_event is not None and not str(self.terminal_safety_event).strip():
            raise ValueError("TERMINAL_SAFETY_EVENT_INVALID")

    @property
    def true_opportunity(self) -> bool:
        return self.legal_action_count > 1

    @property
    def action_mutation(self) -> bool:
        return self.proposed_index != self.baseline_index


@dataclass(frozen=True)
class AuthorizedDecision:
    mode: ClosedLoopMode
    chosen_index: int
    baseline_index: int
    proposed_index: int
    model_applied: bool
    action_mutation: bool
    fallback_used: bool
    reason: AuthorizationReason
    kill_switch_tripped: bool


_HEAD_COUNTER_FIELDS: tuple[str, ...] = (
    "true_opportunities",
    "eligible",
    "proposals",
    "applied",
    "action_mutations",
    "fallbacks",
    "f2_fallbacks",
    "ood",
    "supervisor_rejects",
    "shield_rejects",
)


@dataclass
class ControlTelemetry:
    """Counts proposal, mutation, fallback, and ownership without identities."""

    totals: Counter[str] = field(default_factory=Counter)
    fallback_reasons: Counter[str] = field(default_factory=Counter)
    fallback_families: Counter[str] = field(default_factory=Counter)
    terminal_safety_events: Counter[str] = field(default_factory=Counter)
    by_head: dict[DecisionHead, Counter[str]] = field(
        default_factory=lambda: {head: Counter() for head in DecisionHead}
    )

    def increment(
        self,
        name: str,
        request: DecisionAuthorizationRequest | None = None,
        amount: int = 1,
    ) -> None:
        self.totals[name] += int(amount)
        if request is not None and request.normal_flow:
            self.by_head[request.head][name] += int(amount)

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return float(numerator / denominator) if denominator else 0.0

    def snapshot(self) -> dict[str, Any]:
        totals = dict(self.totals)
        heads: dict[str, dict[str, Any]] = {}
        for head in DecisionHead:
            raw = self.by_head[head]
            values = {name: int(raw[name]) for name in _HEAD_COUNTER_FIELDS}
            values["ownership_count"] = values["applied"]
            values["ownership_rate"] = self._ratio(values["applied"], values["eligible"])
            values["mutation_rate"] = self._ratio(
                values["action_mutations"], values["applied"]
            )
            values["fallback_rate"] = self._ratio(values["fallbacks"], values["eligible"])
            heads[head.value] = values
        normal_flow_totals = {
            name: sum(int(self.by_head[head][name]) for head in DecisionHead)
            for name in _HEAD_COUNTER_FIELDS
        }
        eligible = normal_flow_totals["eligible"]
        applied = normal_flow_totals["applied"]
        return {
            "totals": totals,
            "normal_flow_totals": normal_flow_totals,
            "fallback_reasons": dict(self.fallback_reasons),
            "fallback_families": dict(self.fallback_families),
            "terminal_safety_events": dict(self.terminal_safety_events),
            "by_head": heads,
            "ownership_rate": self._ratio(applied, eligible),
            "mutation_rate": self._ratio(normal_flow_totals["action_mutations"], applied),
            "f2_fallback_rate": self._ratio(normal_flow_totals["f2_fallbacks"], eligible),
        }


class ClosedLoopAuthorizer:
    """Apply model actions only inside the explicitly granted safety envelope.

    Coverage uses a deterministic cumulative quota: after ``n`` eligible
    decisions at cap ``c``, at most ``floor(n*c)`` model actions may have been
    applied.  This keeps every prefix within the configured cap and avoids an
    ID/hash-based canary sampler.
    """

    def __init__(
        self,
        mode: ClosedLoopMode | str,
        *,
        grants: AuthorizationGrants | None = None,
        limits: ClosedLoopLimits | None = None,
        fixed_research_workload: bool = False,
        telemetry: ControlTelemetry | None = None,
    ) -> None:
        self.mode = ClosedLoopMode(mode)
        self.grants = grants or AuthorizationGrants()
        self.limits = limits or ClosedLoopLimits()
        self.fixed_research_workload = bool(fixed_research_workload)
        self.telemetry = telemetry or ControlTelemetry()
        self._coverage_eligible_seen = 0
        self._coverage_applied = 0
        self._kill_switch_reason: str | None = None

    @property
    def kill_switch_tripped(self) -> bool:
        return self._kill_switch_reason is not None

    @property
    def kill_switch_reason(self) -> str | None:
        return self._kill_switch_reason

    def trip_kill_switch(self, reason: str) -> None:
        normalized = str(reason).strip()
        if not normalized:
            raise ValueError("KILL_SWITCH_REASON_REQUIRED")
        if self._kill_switch_reason is None:
            self._kill_switch_reason = normalized
            self.telemetry.totals["kill_switch_trips"] += 1

    def observe_terminal_safety_event(self, event: str) -> None:
        normalized = str(event).strip().upper()
        if not normalized:
            raise ValueError("TERMINAL_SAFETY_EVENT_INVALID")
        self.telemetry.terminal_safety_events[normalized] += 1
        self.trip_kill_switch(f"TERMINAL_SAFETY_EVENT:{normalized}")

    def _fallback(
        self,
        request: DecisionAuthorizationRequest,
        reason: AuthorizationReason,
    ) -> AuthorizedDecision:
        self.telemetry.increment("fallbacks", request)
        family = str(request.fallback_family)
        self.telemetry.fallback_reasons[reason.value] += 1
        self.telemetry.fallback_families[family] += 1
        if family.upper().startswith("F2"):
            self.telemetry.increment("f2_fallbacks", request)
        return AuthorizedDecision(
            mode=self.mode,
            chosen_index=request.baseline_index,
            baseline_index=request.baseline_index,
            proposed_index=request.proposed_index,
            model_applied=False,
            action_mutation=False,
            fallback_used=True,
            reason=reason,
            kill_switch_tripped=self.kill_switch_tripped,
        )

    def _mode_gate(self) -> AuthorizationReason | None:
        if self.mode is ClosedLoopMode.SHADOW:
            return AuthorizationReason.SHADOW_MODE
        if self.mode is ClosedLoopMode.RESEARCH_CLOSED_LOOP:
            if not self.grants.research_closed_loop:
                return AuthorizationReason.RESEARCH_NOT_AUTHORIZED
            if not self.fixed_research_workload:
                return AuthorizationReason.RESEARCH_WORKLOAD_NOT_FIXED
            return None
        if not self.grants.offline_gate_passed:
            return AuthorizationReason.PRODUCTION_OFFLINE_GATE
        if not self.grants.production_closed_loop:
            return AuthorizationReason.PRODUCTION_NOT_AUTHORIZED
        return None

    def decide(self, request: DecisionAuthorizationRequest) -> AuthorizedDecision:
        if not isinstance(request, DecisionAuthorizationRequest):
            raise TypeError("DECISION_AUTHORIZATION_REQUEST_REQUIRED")
        if request.true_opportunity:
            self.telemetry.increment("true_opportunities", request)
        else:
            return self._fallback(request, AuthorizationReason.NO_TRUE_OPPORTUNITY)
        self.telemetry.increment("proposals", request)

        # Eligibility is a property of the decision state and must remain
        # observable even in shadow or fail-closed authorization modes.
        if not request.eligible:
            return self._fallback(request, AuthorizationReason.INELIGIBLE)
        self.telemetry.increment("eligible", request)

        if request.terminal_safety_event is not None:
            self.observe_terminal_safety_event(request.terminal_safety_event)
        if self.kill_switch_tripped:
            return self._fallback(request, AuthorizationReason.KILL_SWITCH)

        mode_reason = self._mode_gate()
        if mode_reason is not None:
            return self._fallback(request, mode_reason)

        self._coverage_eligible_seen += 1
        if request.ood:
            self.telemetry.increment("ood", request)
            return self._fallback(request, AuthorizationReason.OOD)
        if not request.supervisor_authorized:
            self.telemetry.increment("supervisor_rejects", request)
            return self._fallback(request, AuthorizationReason.SUPERVISOR_REJECT)
        if not request.shield_authorized:
            self.telemetry.increment("shield_rejects", request)
            return self._fallback(request, AuthorizationReason.SHIELD_REJECT)
        if (
            request.proposed_is_hold
            and request.consecutive_hold_count >= self.limits.max_consecutive_holds
        ):
            self.telemetry.increment("repeated_hold_fallbacks", request)
            return self._fallback(request, AuthorizationReason.HOLD_CAP)
        if (
            request.action_mutation
            and request.segment_override_count >= self.limits.max_overrides_per_segment
        ):
            self.telemetry.increment("override_cap_fallbacks", request)
            return self._fallback(request, AuthorizationReason.OVERRIDE_CAP)

        allowed_total = math.floor(
            self._coverage_eligible_seen * self.limits.coverage_cap + 1e-12
        )
        if self._coverage_applied >= allowed_total:
            self.telemetry.increment("coverage_cap_fallbacks", request)
            return self._fallback(request, AuthorizationReason.COVERAGE_CAP)

        self._coverage_applied += 1
        self.telemetry.increment("applied", request)
        mutation = request.action_mutation
        if mutation:
            self.telemetry.increment("action_mutations", request)
        if request.proposed_is_hold:
            self.telemetry.increment("holds_applied", request)
        return AuthorizedDecision(
            mode=self.mode,
            chosen_index=request.proposed_index,
            baseline_index=request.baseline_index,
            proposed_index=request.proposed_index,
            model_applied=True,
            action_mutation=mutation,
            fallback_used=False,
            reason=AuthorizationReason.APPLIED,
            kill_switch_tripped=False,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "research_closed_loop_authorized": self.grants.research_closed_loop,
            "production_closed_loop_authorized": self.grants.production_closed_loop,
            "offline_gate_passed": self.grants.offline_gate_passed,
            "fixed_research_workload": self.fixed_research_workload,
            "limits": {
                "coverage_cap": self.limits.coverage_cap,
                "max_consecutive_holds": self.limits.max_consecutive_holds,
                "max_overrides_per_segment": self.limits.max_overrides_per_segment,
            },
            "kill_switch_tripped": self.kill_switch_tripped,
            "kill_switch_reason": self.kill_switch_reason,
            "coverage_eligible_seen": self._coverage_eligible_seen,
            "coverage_applied": self._coverage_applied,
            "telemetry": self.telemetry.snapshot(),
            "research_evidence_promotes_production": False,
        }


__all__ = [
    "AuthorizationGrants",
    "AuthorizationReason",
    "AuthorizedDecision",
    "ClosedLoopAuthorizer",
    "ClosedLoopLimits",
    "ClosedLoopMode",
    "ControlTelemetry",
    "DecisionAuthorizationRequest",
]

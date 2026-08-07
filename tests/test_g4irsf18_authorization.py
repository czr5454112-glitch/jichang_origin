from __future__ import annotations

from czr005.g4irsf18 import (
    AuthorizationGrants,
    AuthorizationReason,
    ClosedLoopAuthorizer,
    ClosedLoopLimits,
    ClosedLoopMode,
    DecisionAuthorizationRequest,
    DecisionHead,
)


def _request(head: DecisionHead = DecisionHead.ROUTE, **updates):
    values = {
        "head": head,
        "baseline_index": 0,
        "proposed_index": 1,
        "legal_action_count": 2,
    }
    values.update(updates)
    return DecisionAuthorizationRequest(**values)


def _research(*, coverage: float = 1.0, **limit_updates):
    return ClosedLoopAuthorizer(
        ClosedLoopMode.RESEARCH_CLOSED_LOOP,
        grants=AuthorizationGrants(research_closed_loop=True),
        limits=ClosedLoopLimits(coverage_cap=coverage, **limit_updates),
        fixed_research_workload=True,
    )


def test_research_and_production_authorization_are_independent_and_fail_closed() -> None:
    shadow = ClosedLoopAuthorizer(ClosedLoopMode.SHADOW)
    assert shadow.decide(_request()).reason is AuthorizationReason.SHADOW_MODE

    # Research may execute inside the fixed experiment envelope without a
    # production/offline promotion grant.
    research = _research()
    research_decision = research.decide(_request())
    assert research_decision.model_applied is True
    assert research_decision.action_mutation is True

    production = ClosedLoopAuthorizer(
        ClosedLoopMode.PRODUCTION_CLOSED_LOOP,
        grants=AuthorizationGrants(research_closed_loop=True),
        limits=ClosedLoopLimits(coverage_cap=1.0),
    )
    assert production.decide(_request()).reason is AuthorizationReason.PRODUCTION_OFFLINE_GATE
    gated_only = ClosedLoopAuthorizer(
        ClosedLoopMode.PRODUCTION_CLOSED_LOOP,
        grants=AuthorizationGrants(offline_gate_passed=True),
        limits=ClosedLoopLimits(coverage_cap=1.0),
    )
    assert gated_only.decide(_request()).reason is AuthorizationReason.PRODUCTION_NOT_AUTHORIZED
    authorized = ClosedLoopAuthorizer(
        ClosedLoopMode.PRODUCTION_CLOSED_LOOP,
        grants=AuthorizationGrants(
            production_closed_loop=True,
            offline_gate_passed=True,
        ),
        limits=ClosedLoopLimits(coverage_cap=1.0),
    )
    assert authorized.decide(_request()).model_applied is True
    assert authorized.snapshot()["research_evidence_promotes_production"] is False


def test_research_requires_fixed_workload_and_explicit_research_grant() -> None:
    no_grant = ClosedLoopAuthorizer(
        ClosedLoopMode.RESEARCH_CLOSED_LOOP,
        limits=ClosedLoopLimits(coverage_cap=1.0),
        fixed_research_workload=True,
    )
    assert no_grant.decide(_request()).reason is AuthorizationReason.RESEARCH_NOT_AUTHORIZED
    not_fixed = ClosedLoopAuthorizer(
        ClosedLoopMode.RESEARCH_CLOSED_LOOP,
        grants=AuthorizationGrants(research_closed_loop=True),
        limits=ClosedLoopLimits(coverage_cap=1.0),
    )
    assert not_fixed.decide(_request()).reason is AuthorizationReason.RESEARCH_WORKLOAD_NOT_FIXED


def test_coverage_hold_and_override_caps_have_distinct_fallback_reasons() -> None:
    capped = _research(coverage=0.5)
    decisions = [capped.decide(_request()) for _ in range(4)]
    assert [decision.model_applied for decision in decisions] == [False, True, False, True]
    assert decisions[0].reason is AuthorizationReason.COVERAGE_CAP
    assert capped.snapshot()["coverage_applied"] == 2

    hold = _research(max_consecutive_holds=1)
    hold_decision = hold.decide(
        _request(proposed_is_hold=True, consecutive_hold_count=1)
    )
    assert hold_decision.reason is AuthorizationReason.HOLD_CAP

    override = _research(max_overrides_per_segment=2)
    override_decision = override.decide(_request(segment_override_count=2))
    assert override_decision.reason is AuthorizationReason.OVERRIDE_CAP


def test_supervisor_shield_ood_and_kill_switch_are_visible_in_telemetry() -> None:
    authorizer = _research()
    assert authorizer.decide(_request(ood=True)).reason is AuthorizationReason.OOD
    assert (
        authorizer.decide(_request(supervisor_authorized=False)).reason
        is AuthorizationReason.SUPERVISOR_REJECT
    )
    assert (
        authorizer.decide(_request(shield_authorized=False)).reason
        is AuthorizationReason.SHIELD_REJECT
    )
    terminal = authorizer.decide(
        _request(terminal_safety_event="unsafe")
    )
    assert terminal.reason is AuthorizationReason.KILL_SWITCH
    assert terminal.kill_switch_tripped is True
    assert authorizer.decide(_request()).reason is AuthorizationReason.KILL_SWITCH

    snapshot = authorizer.snapshot()
    telemetry = snapshot["telemetry"]
    assert snapshot["kill_switch_reason"] == "TERMINAL_SAFETY_EVENT:UNSAFE"
    assert telemetry["totals"]["kill_switch_trips"] == 1
    assert telemetry["totals"]["ood"] == 1
    assert telemetry["totals"]["supervisor_rejects"] == 1
    assert telemetry["totals"]["shield_rejects"] == 1
    assert telemetry["terminal_safety_events"] == {"UNSAFE": 1}


def test_action_mutation_ownership_and_f2_fallback_are_reported_by_head() -> None:
    authorizer = _research()
    source = authorizer.decide(_request(DecisionHead.SOURCE))
    route = authorizer.decide(_request(DecisionHead.ROUTE, ood=True))
    merge = authorizer.decide(
        _request(
            DecisionHead.MERGE,
            proposed_index=0,
            fallback_family="J2",
        )
    )
    assert source.action_mutation is True
    assert route.fallback_used is True
    assert merge.model_applied is True and merge.action_mutation is False

    telemetry = authorizer.snapshot()["telemetry"]
    assert telemetry["totals"]["true_opportunities"] == 3
    assert telemetry["totals"]["applied"] == 2
    assert telemetry["totals"]["action_mutations"] == 1
    assert telemetry["totals"]["f2_fallbacks"] == 1
    assert telemetry["by_head"]["source"]["ownership_rate"] == 1.0
    assert telemetry["by_head"]["route"]["ownership_rate"] == 0.0
    assert telemetry["by_head"]["merge"]["ownership_count"] == 1
    assert telemetry["by_head"]["merge"]["mutation_rate"] == 0.0


def test_single_legal_action_is_not_misreported_as_policy_control() -> None:
    authorizer = _research()
    decision = authorizer.decide(
        _request(baseline_index=0, proposed_index=0, legal_action_count=1)
    )
    assert decision.reason is AuthorizationReason.NO_TRUE_OPPORTUNITY
    telemetry = authorizer.snapshot()["telemetry"]
    assert telemetry["totals"].get("true_opportunities", 0) == 0
    assert telemetry["totals"].get("applied", 0) == 0

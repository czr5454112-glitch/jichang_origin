from __future__ import annotations

from dataclasses import replace
import math

import pytest

from czr005.policies.g4irsf16_supervisor import (
    FULL_ASTAR_FALLBACK_ALLOWED,
    ActionKind,
    ActionSource,
    DecisionContext,
    G4IRSF16Supervisor,
    PibtMove,
    PibtRequestSource,
    SupervisorConfig,
    SupervisorState,
)


def _context(**updates: object) -> DecisionContext:
    values: dict[str, object] = {
        "runtime_bag_id": "bag-1",
        "segment_id": "segment-1",
        "node": 8,
        "generation": 3,
        "physical_fault_generation": 0,
        "f2_action": 11,
        "legal_alternatives": (11, 12),
        "service_opportunity_available": True,
        "shield_safe": True,
    }
    values.update(updates)
    return DecisionContext(**values)  # type: ignore[arg-type]


def _pibt_batch(fault_generation: int = 0) -> tuple[PibtMove, ...]:
    return (
        PibtMove(
            owner_bag_id="bag-1",
            segment_id="segment-1",
            from_node=8,
            to_node=12,
            generation=3,
            physical_fault_generation=fault_generation,
            legal=True,
            shield_safe=True,
        ),
        PibtMove(
            owner_bag_id="blocker",
            segment_id="blocker-segment",
            from_node=12,
            to_node=15,
            generation=9,
            physical_fault_generation=fault_generation,
            legal=True,
            shield_safe=True,
        ),
    )


def _strict_pibt_context(**updates: object) -> DecisionContext:
    values: dict[str, object] = {
        "f2_action": None,
        "legal_alternatives": (),
        "shield_safe": False,
        "pibt_requested": True,
        "pibt_request_source": PibtRequestSource.LOCAL_BLOCKER,
        "pibt_applicable": True,
        "pibt_owner_movable": True,
        "pibt_safe_alternative": True,
        "pibt_atomic_possible": True,
        "pibt_batch": _pibt_batch(),
    }
    values.update(updates)
    return _context(**values)


def test_default_and_learned_abstention_preserve_exact_f2() -> None:
    supervisor = G4IRSF16Supervisor()
    default = supervisor.evaluate(_context())
    assert default.state is SupervisorState.F2_NORMAL
    assert default.action is ActionKind.MOVE_ONE_EDGE
    assert default.source is ActionSource.FROZEN_F2
    assert default.selected_next_node == 11

    low_confidence = supervisor.evaluate(
        _context(
            i4_proposed=True,
            i4_model_authorized=True,
            i4_confidence=None,
            i4_risk=0.0,
            i3_action=12,
            i3_model_authorized=True,
            i3_confidence=0.949,
            i3_risk=0.0,
        )
    )
    assert low_confidence.state is SupervisorState.F2_NORMAL
    assert low_confidence.action is ActionKind.MOVE_ONE_EDGE
    assert low_confidence.selected_next_node == 11
    assert "confidence" in low_confidence.reason
    assert low_confidence.counters.safe_hold_count == 0


def test_i4_holds_exactly_one_natural_opportunity_per_node_generation() -> None:
    supervisor = G4IRSF16Supervisor()
    proposal = _context(
        i4_proposed=True,
        i4_model_authorized=True,
        i4_confidence=0.99,
        i4_risk=0.001,
    )

    first = supervisor.evaluate(proposal)
    assert first.state is SupervisorState.I4_SELECTIVE_HOLD
    assert first.action is ActionKind.HOLD_ONE_NATURAL_OPPORTUNITY
    assert first.selected_next_node is None
    assert first.reevaluation_required is True
    assert first.counters.hold_count == 1

    # The same node/generation is re-evaluated and cannot hold again.
    second = supervisor.evaluate(proposal)
    assert second.state is SupervisorState.F2_NORMAL
    assert second.selected_next_node == proposal.f2_action
    assert "opportunity_consumed" in second.reason
    assert second.counters.hold_count == 1

    # A new local generation is a new natural opportunity, not a duration.
    third = supervisor.evaluate(replace(proposal, generation=4))
    assert third.state is SupervisorState.I4_SELECTIVE_HOLD
    assert third.counters.hold_count == 2
    assert "seconds" not in first.as_audit_dict()


@pytest.mark.parametrize(
    "updates",
    [
        {"i4_model_authorized": False},
        {"service_opportunity_available": False},
        {"i4_confidence": math.nan},
        {"i4_risk": None},
        {"i4_risk": 0.006},
    ],
)
def test_i4_gate_failures_abstain_to_f2(updates: dict[str, object]) -> None:
    values: dict[str, object] = {
        "i4_proposed": True,
        "i4_model_authorized": True,
        "i4_confidence": 0.99,
        "i4_risk": 0.001,
    }
    values.update(updates)
    context = _context(**values)
    decision = G4IRSF16Supervisor().evaluate(context)
    assert decision.state is SupervisorState.F2_NORMAL
    assert decision.selected_next_node == context.f2_action
    assert decision.counters.hold_count == 0


def test_i3_requires_authorized_high_confidence_legal_risk_pass() -> None:
    supervisor = G4IRSF16Supervisor()
    proposal = _context(
        i3_action=12,
        i3_model_authorized=True,
        i3_confidence=0.99,
        i3_risk=0.001,
    )
    selected = supervisor.evaluate(proposal)
    assert selected.state is SupervisorState.I3_RARE_OVERRIDE
    assert selected.action is ActionKind.MOVE_ONE_EDGE
    assert selected.source is ActionSource.I3_MODEL
    assert selected.selected_next_node == 12
    assert selected.counters.override_count == 1

    # The latch blocks a second override and therefore also blocks A<->B
    # learned oscillation within this segment.
    reverse = supervisor.evaluate(
        replace(
            proposal,
            node=12,
            f2_action=15,
            legal_alternatives=(8, 15),
            i3_action=8,
        )
    )
    assert reverse.state is SupervisorState.F2_NORMAL
    assert reverse.selected_next_node == 15
    assert "oscillation" in reverse.reason
    assert reverse.counters.override_count == 1


def test_i3_cannot_reverse_the_previous_selected_edge() -> None:
    supervisor = G4IRSF16Supervisor()
    moved = supervisor.evaluate(
        _context(node=8, f2_action=12, legal_alternatives=(11, 12))
    )
    assert moved.selected_next_node == 12

    reverse_proposal = supervisor.evaluate(
        _context(
            node=12,
            f2_action=15,
            legal_alternatives=(8, 15),
            i3_action=8,
            i3_model_authorized=True,
            i3_confidence=1.0,
            i3_risk=0.0,
        )
    )
    assert reverse_proposal.state is SupervisorState.F2_NORMAL
    assert reverse_proposal.selected_next_node == 15
    assert "oscillation" in reverse_proposal.reason


@pytest.mark.parametrize(
    ("updates", "reason_fragment"),
    [
        ({"i3_model_authorized": False}, "not_authorized"),
        ({"i3_action": 99}, "illegal_alternative"),
        ({"i3_action": 11}, "not_an_alternative"),
        ({"i3_confidence": None}, "confidence"),
        ({"i3_confidence": 0.90}, "confidence"),
        ({"i3_risk": None}, "risk"),
        ({"i3_risk": 0.003}, "risk"),
    ],
)
def test_i3_gate_failures_fail_closed_to_f2(
    updates: dict[str, object], reason_fragment: str
) -> None:
    values: dict[str, object] = {
        "i3_action": 12,
        "i3_model_authorized": True,
        "i3_confidence": 0.99,
        "i3_risk": 0.001,
    }
    values.update(updates)
    decision = G4IRSF16Supervisor().evaluate(_context(**values))
    assert decision.state is SupervisorState.F2_NORMAL
    assert decision.selected_next_node == 11
    assert reason_fragment in decision.reason
    assert decision.counters.override_count == 0


def test_strict_pibt_returns_the_whole_atomic_batch() -> None:
    context = _strict_pibt_context()
    supervisor = G4IRSF16Supervisor()
    decision = supervisor.evaluate(context)
    assert decision.state is SupervisorState.PIBT_RECOVERY
    assert decision.action is ActionKind.ATOMIC_ONE_STEP_BATCH
    assert decision.source is ActionSource.STRICT_LOCAL_PIBT
    assert decision.atomic is True
    assert decision.atomic_batch == context.pibt_batch
    assert decision.counters.pibt_count == 1

    forged = replace(
        decision,
        atomic_batch=(
            replace(context.pibt_batch[0], to_node=99),
            context.pibt_batch[1],
        ),
    )
    assert supervisor.consume_atomic_batch(forged, context) is None
    assert supervisor.token_is_current(decision.token, context)
    assert supervisor.consume_atomic_batch(decision, context) == context.pibt_batch
    assert supervisor.consume_atomic_batch(decision, context) is None


@pytest.mark.parametrize(
    "updates",
    [
        {"pibt_requested": False},
        {"pibt_request_source": PibtRequestSource.MODEL_ABSTENTION},
        {"pibt_applicable": False},
        {"pibt_owner_movable": False},
        {"pibt_safe_alternative": False},
        {"pibt_atomic_possible": False},
        {"pibt_batch": ()},
        {
            "pibt_batch": (
                replace(_pibt_batch()[0], legal=False),
                _pibt_batch()[1],
            )
        },
        {
            "pibt_batch": (
                _pibt_batch()[0],
                replace(_pibt_batch()[1], to_node=12),
            )
        },
    ],
)
def test_pibt_requires_every_strict_and_atomic_condition(
    updates: dict[str, object],
) -> None:
    decision = G4IRSF16Supervisor().evaluate(
        _strict_pibt_context(**updates)
    )
    assert decision.state is SupervisorState.SAFE_HOLD
    assert decision.action is ActionKind.SAFE_HOLD
    assert decision.atomic_batch == ()
    assert decision.counters.pibt_count == 0


def test_model_abstention_cannot_directly_trigger_pibt() -> None:
    decision = G4IRSF16Supervisor().evaluate(
        _strict_pibt_context(
            i3_action=12,
            i3_model_authorized=True,
            i3_confidence=0.5,
            i3_risk=0.0,
            pibt_request_source=PibtRequestSource.MODEL_ABSTENTION,
        )
    )
    assert decision.state is SupervisorState.SAFE_HOLD
    assert decision.source is ActionSource.LOCAL_SAFETY
    assert decision.counters.pibt_count == 0


def test_fault_revokes_token_repairs_once_and_preserves_i4_latch() -> None:
    supervisor = G4IRSF16Supervisor()
    proposal = _context(
        i4_proposed=True,
        i4_model_authorized=True,
        i4_confidence=0.99,
        i4_risk=0.0,
    )
    held = supervisor.evaluate(proposal)
    assert supervisor.token_is_current(held.token, proposal)

    fault = replace(proposal, physical_fault_generation=1, fault_active=True)
    during_fault = supervisor.evaluate(fault)
    assert during_fault.state is SupervisorState.FAULT_RECOVERY
    assert during_fault.action is ActionKind.FAULT_HOLD
    assert during_fault.token is None
    assert not supervisor.token_is_current(held.token, fault)

    repaired_context = replace(fault, fault_active=False)
    repaired = supervisor.evaluate(repaired_context)
    assert repaired.state is SupervisorState.F2_NORMAL
    assert repaired.selected_next_node == 11
    assert repaired.repair_reentry is True
    assert repaired.counters.repair_reentry_count == 1

    # A later event in the same node generation cannot consume I4 again.
    after_repair = supervisor.evaluate(repaired_context)
    assert after_repair.state is SupervisorState.F2_NORMAL
    assert after_repair.counters.hold_count == 1
    assert after_repair.counters.repair_reentry_count == 1


def test_stale_fault_and_node_generations_are_rejected() -> None:
    supervisor = G4IRSF16Supervisor()
    current = _context(generation=5, physical_fault_generation=2)
    issued = supervisor.evaluate(current)
    assert issued.token is not None

    stale_fault = supervisor.evaluate(
        replace(current, physical_fault_generation=1)
    )
    assert stale_fault.state is SupervisorState.FAULT_RECOVERY
    assert stale_fault.stale_generation_rejected is True
    assert "stale_physical" in stale_fault.reason
    assert not supervisor.token_is_current(issued.token, current)

    recovered = supervisor.evaluate(current)
    assert recovered.state is SupervisorState.F2_NORMAL
    stale_node = supervisor.evaluate(replace(current, generation=4))
    assert stale_node.state is SupervisorState.FAULT_RECOVERY
    assert "stale_node" in stale_node.reason
    assert stale_node.counters.stale_generation_rejection_count == 2


def test_token_is_exactly_bound_and_consumed_once() -> None:
    supervisor = G4IRSF16Supervisor()
    context = _context()
    decision = supervisor.evaluate(context)
    assert supervisor.token_is_current(decision.token, context)
    assert not supervisor.token_is_current(
        decision.token, replace(context, generation=4)
    )
    assert supervisor.consume_token(decision.token, context)
    assert not supervisor.consume_token(decision.token, context)


def test_safe_hold_is_used_only_when_no_safe_f2_or_strict_pibt() -> None:
    supervisor = G4IRSF16Supervisor()
    no_action = _context(
        f2_action=None,
        legal_alternatives=(),
        shield_safe=False,
        service_opportunity_available=False,
    )
    decision = supervisor.evaluate(no_action)
    assert decision.state is SupervisorState.SAFE_HOLD
    assert decision.action is ActionKind.SAFE_HOLD
    assert decision.selected_next_node is None
    assert decision.counters.safe_hold_count == 1
    assert decision.reevaluation_required is True


def test_full_astar_fallback_is_unrepresentable_as_an_action_source() -> None:
    assert FULL_ASTAR_FALLBACK_ALLOWED is False
    assert all("ASTAR" not in source.value for source in ActionSource)

    decision = G4IRSF16Supervisor().evaluate(
        _context(astar_fallback_requested=True)
    )
    assert decision.state is SupervisorState.SAFE_HOLD
    assert decision.reason == "full_astar_fallback_forbidden"
    assert decision.used_full_astar is False
    assert decision.selected_next_node is None

    # A real fault remains the dominant state even if a forbidden request is
    # also present; neither path can invoke A*.
    fault = G4IRSF16Supervisor().evaluate(
        _context(astar_fallback_requested=True, fault_active=True)
    )
    assert fault.state is SupervisorState.FAULT_RECOVERY
    assert fault.used_full_astar is False


def test_audit_records_all_six_states_and_latch_counters() -> None:
    observed: set[SupervisorState] = set()

    f2 = G4IRSF16Supervisor().evaluate(_context())
    observed.add(f2.state)
    i4 = G4IRSF16Supervisor().evaluate(
        _context(
            i4_proposed=True,
            i4_model_authorized=True,
            i4_confidence=1.0,
            i4_risk=0.0,
        )
    )
    observed.add(i4.state)
    i3 = G4IRSF16Supervisor().evaluate(
        _context(
            i3_action=12,
            i3_model_authorized=True,
            i3_confidence=1.0,
            i3_risk=0.0,
        )
    )
    observed.add(i3.state)
    observed.add(G4IRSF16Supervisor().evaluate(_strict_pibt_context()).state)
    observed.add(
        G4IRSF16Supervisor()
        .evaluate(_context(f2_action=None, legal_alternatives=()))
        .state
    )
    observed.add(
        G4IRSF16Supervisor()
        .evaluate(_context(fault_active=True))
        .state
    )
    assert observed == set(SupervisorState)

    supervisor = G4IRSF16Supervisor()
    supervisor.evaluate(_context())
    supervisor.evaluate(
        _context(
            i4_proposed=True,
            i4_model_authorized=True,
            i4_confidence=1.0,
            i4_risk=0.0,
        )
    )
    audit = supervisor.audit_dicts()
    assert [row["sequence"] for row in audit] == [1, 2]
    assert audit[-1]["to_state"] == "I4_SELECTIVE_HOLD"
    assert audit[-1]["reason"] == "i4_high_confidence_risk_pass"
    assert audit[-1]["counters"]["activation_count"] == 1


def test_segment_boundary_resets_latches_but_retired_segment_cannot_replay() -> None:
    supervisor = G4IRSF16Supervisor()
    proposal = _context(
        i3_action=12,
        i3_model_authorized=True,
        i3_confidence=1.0,
        i3_risk=0.0,
    )
    assert supervisor.evaluate(proposal).state is SupervisorState.I3_RARE_OVERRIDE

    next_segment = replace(proposal, segment_id="segment-2")
    second = supervisor.evaluate(next_segment)
    assert second.state is SupervisorState.I3_RARE_OVERRIDE
    assert second.counters.override_count == 1

    replay = supervisor.evaluate(proposal)
    assert replay.state is SupervisorState.FAULT_RECOVERY
    assert replay.stale_generation_rejected is True
    assert replay.reason == "retired_segment_replay_rejected"


def test_context_and_threshold_boundary_validation() -> None:
    with pytest.raises(ValueError, match="runtime_bag_id"):
        _context(runtime_bag_id="")
    with pytest.raises(ValueError, match="generation"):
        _context(generation=-1)
    with pytest.raises(TypeError, match="i3_action"):
        _context(i3_action="12")
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        SupervisorConfig(i3_max_risk=1.1)

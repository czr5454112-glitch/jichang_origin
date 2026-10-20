"""Deterministic Stage-16K/L supervisor contract regressions.

This module exercises :class:`G4IRSF16Supervisor` directly.  It is a small,
synthetic state-machine regression corpus, not a runtime simulator and not a
closed-loop TTH experiment.  The tail/PIBT table therefore reports capability
and safety-contract outcomes only; it must not be used to claim mean, p99,
maximum, throughput, or causal improvements.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from czr005.policies.g4irsf16_supervisor import (
    FULL_ASTAR_FALLBACK_ALLOWED,
    ActionKind,
    ActionSource,
    DecisionContext,
    G4IRSF16Supervisor,
    PibtMove,
    PibtRequestSource,
    SupervisorDecision,
    SupervisorState,
)


SUMMARY_SCHEMA = "czr005.g4irsf16.supervisor_contract_regression.v1"
EVALUATION_SCOPE = "SUPERVISOR_CONTRACT_REGRESSION_NOT_FULL_CLOSED_LOOP_TTH"
TAIL_TABLE_OUTPUT = Path("outputs/tables/g4irsf16_tail_pibt_ab.csv")
FAULT_TABLE_OUTPUT = Path("outputs/tables/g4irsf16_fault_regression.csv")
TAIL_REPORT_OUTPUT = Path("outputs/reports/g4irsf16_tail_pibt_ab.md")
FAULT_REPORT_OUTPUT = Path("outputs/reports/g4irsf16_fault_regression.md")
SUMMARY_OUTPUT = Path(
    "outputs/reports/g4irsf16_tail_pibt_fault_contract_summary.json"
)


class ContractRegressionError(RuntimeError):
    """Raised before publishing an incomplete or unsafe regression result."""


@dataclass(frozen=True)
class TailTier:
    tier: str
    feature_stack: str
    local_rule_enabled: bool
    safe_hold_credited: bool
    strict_pibt_enabled: bool


TAIL_TIERS: tuple[TailTier, ...] = (
    TailTier("T0", "learned only", False, False, False),
    TailTier(
        "T1",
        "learned + local rule fallback (authorization veto -> F2)",
        True,
        False,
        False,
    ),
    TailTier(
        "T2",
        "learned + local rule fallback (authorization veto -> F2) + safe hold",
        True,
        True,
        False,
    ),
    TailTier(
        "T3",
        (
            "learned + local rule fallback (authorization veto -> F2) + "
            "strict PIBT + safe hold"
        ),
        True,
        True,
        True,
    ),
)

TAIL_CASES: tuple[str, ...] = (
    "learned_i4_high_confidence",
    "learned_i3_high_confidence",
    "local_rule_authorization_veto",
    "no_safe_f2",
    "strict_local_blocker",
    "model_abstention_cannot_trigger_pibt",
    "invalid_pibt_batch",
    "full_astar_request_forbidden",
)

REQUIRED_FAULT_CASES: tuple[str, ...] = (
    "no_fault",
    "physical_shield",
    "delayed_message",
    "dropped_message",
    "repair_reopen",
    "i4_hold_fault",
    "i3_prepare_fault",
    "pibt_transaction_fault",
    "full_astar_request_forbidden",
)

TAIL_COLUMNS: tuple[str, ...] = (
    "schema",
    "evaluation_scope",
    "tier",
    "feature_stack",
    "case_id",
    "local_rule_enabled",
    "safe_hold_credited",
    "strict_pibt_enabled",
    "local_rule_veto_applied",
    "capability_credited_to_tier",
    "supervisor_state",
    "action",
    "source",
    "reason",
    "selected_next_node",
    "pibt_requested",
    "pibt_request_source",
    "pibt_applicable",
    "prepared_batch_size",
    "committed_batch_size",
    "second_atomic_consume_rejected",
    "atomic_all_or_none",
    "unsafe_entry_count",
    "used_full_astar_count",
    "contract_pass",
)

FAULT_COLUMNS: tuple[str, ...] = (
    "schema",
    "evaluation_scope",
    "case_id",
    "event_count",
    "terminal_state",
    "terminal_action",
    "terminal_reason",
    "stale_generation_rejection_count",
    "revoked_token_count",
    "repair_expected",
    "repair_reentry_count",
    "repair_once",
    "old_token_rejection_tested",
    "old_token_rejected",
    "pibt_prepared_batch_size",
    "pibt_aborted_commit_size",
    "pibt_successful_commit_size",
    "second_atomic_consume_rejected",
    "atomic_all_or_none",
    "unsafe_entry_count",
    "used_full_astar_count",
    "audit_sequence_contiguous",
    "message_generation_gap",
    "event_trace",
    "contract_pass",
)


def _context(case_id: str, **updates: object) -> DecisionContext:
    values: dict[str, object] = {
        "runtime_bag_id": f"bag-{case_id}",
        "segment_id": f"segment-{case_id}",
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


def _pibt_batch(
    case_id: str,
    *,
    physical_fault_generation: int = 0,
    generation: int = 3,
) -> tuple[PibtMove, ...]:
    return (
        PibtMove(
            owner_bag_id=f"bag-{case_id}",
            segment_id=f"segment-{case_id}",
            from_node=8,
            to_node=12,
            generation=generation,
            physical_fault_generation=physical_fault_generation,
            legal=True,
            shield_safe=True,
        ),
        PibtMove(
            owner_bag_id=f"blocker-{case_id}",
            segment_id=f"blocker-segment-{case_id}",
            from_node=12,
            to_node=15,
            generation=generation + 4,
            physical_fault_generation=physical_fault_generation,
            legal=True,
            shield_safe=True,
        ),
    )


def _strict_pibt_context(
    case_id: str,
    *,
    physical_fault_generation: int = 0,
    generation: int = 3,
    requested: bool = True,
    request_source: PibtRequestSource = PibtRequestSource.LOCAL_BLOCKER,
    batch: tuple[PibtMove, ...] | None = None,
) -> DecisionContext:
    return _context(
        case_id,
        generation=generation,
        physical_fault_generation=physical_fault_generation,
        f2_action=None,
        legal_alternatives=(),
        shield_safe=False,
        pibt_requested=requested,
        pibt_request_source=request_source,
        pibt_applicable=True,
        pibt_owner_movable=True,
        pibt_safe_alternative=True,
        pibt_atomic_possible=True,
        pibt_batch=(
            _pibt_batch(
                case_id,
                physical_fault_generation=physical_fault_generation,
                generation=generation,
            )
            if batch is None
            else batch
        ),
    )


def _decision_unsafe_entry_count(
    decision: SupervisorDecision,
    context: DecisionContext,
) -> int:
    """Count a prepared action that could violate the local safety contract."""

    if decision.action is ActionKind.MOVE_ONE_EDGE:
        return int(
            context.fault_active
            or not context.shield_safe
            or decision.selected_next_node is None
            or decision.selected_next_node not in context.legal_alternatives
        )
    if decision.action is ActionKind.ATOMIC_ONE_STEP_BATCH:
        return int(
            context.fault_active
            or not decision.atomic_batch
            or any(
                not move.legal
                or not move.shield_safe
                or move.physical_fault_generation
                != context.physical_fault_generation
                for move in decision.atomic_batch
            )
        )
    return 0


def _tail_case(tier: TailTier, case_id: str) -> dict[str, Any]:
    scenario = f"tail-{tier.tier.lower()}-{case_id}"
    supervisor = G4IRSF16Supervisor()
    local_rule_veto = False
    committed_batch_size = 0
    second_consume_rejected = True
    capability_credited = True

    if case_id == "learned_i4_high_confidence":
        context = _context(
            scenario,
            i4_proposed=True,
            i4_model_authorized=True,
            i4_confidence=0.99,
            i4_risk=0.001,
        )
        expected = (
            SupervisorState.I4_SELECTIVE_HOLD,
            ActionKind.HOLD_ONE_NATURAL_OPPORTUNITY,
            ActionSource.I4_MODEL,
        )
    elif case_id == "learned_i3_high_confidence":
        context = _context(
            scenario,
            i3_action=12,
            i3_model_authorized=True,
            i3_confidence=0.99,
            i3_risk=0.001,
        )
        expected = (
            SupervisorState.I3_RARE_OVERRIDE,
            ActionKind.MOVE_ONE_EDGE,
            ActionSource.I3_MODEL,
        )
    elif case_id == "local_rule_authorization_veto":
        local_rule_veto = tier.local_rule_enabled
        context = _context(
            scenario,
            i3_action=12,
            i3_model_authorized=not local_rule_veto,
            i3_confidence=0.99,
            i3_risk=0.001,
        )
        expected = (
            (
                SupervisorState.F2_NORMAL,
                ActionKind.MOVE_ONE_EDGE,
                ActionSource.FROZEN_F2,
            )
            if local_rule_veto
            else (
                SupervisorState.I3_RARE_OVERRIDE,
                ActionKind.MOVE_ONE_EDGE,
                ActionSource.I3_MODEL,
            )
        )
    elif case_id == "no_safe_f2":
        context = _context(
            scenario,
            f2_action=None,
            legal_alternatives=(),
            shield_safe=False,
            service_opportunity_available=False,
        )
        expected = (
            SupervisorState.SAFE_HOLD,
            ActionKind.SAFE_HOLD,
            ActionSource.LOCAL_SAFETY,
        )
        capability_credited = tier.safe_hold_credited
    elif case_id == "strict_local_blocker":
        context = _strict_pibt_context(
            scenario,
            requested=tier.strict_pibt_enabled,
        )
        expected = (
            (
                SupervisorState.PIBT_RECOVERY,
                ActionKind.ATOMIC_ONE_STEP_BATCH,
                ActionSource.STRICT_LOCAL_PIBT,
            )
            if tier.strict_pibt_enabled
            else (
                SupervisorState.SAFE_HOLD,
                ActionKind.SAFE_HOLD,
                ActionSource.LOCAL_SAFETY,
            )
        )
        capability_credited = tier.safe_hold_credited
    elif case_id == "model_abstention_cannot_trigger_pibt":
        context = _strict_pibt_context(
            scenario,
            requested=True,
            request_source=PibtRequestSource.MODEL_ABSTENTION,
        )
        expected = (
            SupervisorState.SAFE_HOLD,
            ActionKind.SAFE_HOLD,
            ActionSource.LOCAL_SAFETY,
        )
        capability_credited = tier.safe_hold_credited
    elif case_id == "invalid_pibt_batch":
        valid = _pibt_batch(scenario)
        invalid = (valid[0], replace(valid[1], to_node=valid[0].to_node))
        context = _strict_pibt_context(
            scenario,
            requested=tier.strict_pibt_enabled,
            batch=invalid,
        )
        expected = (
            SupervisorState.SAFE_HOLD,
            ActionKind.SAFE_HOLD,
            ActionSource.LOCAL_SAFETY,
        )
        capability_credited = tier.safe_hold_credited
    elif case_id == "full_astar_request_forbidden":
        context = _context(scenario, astar_fallback_requested=True)
        expected = (
            SupervisorState.SAFE_HOLD,
            ActionKind.SAFE_HOLD,
            ActionSource.LOCAL_SAFETY,
        )
        capability_credited = tier.safe_hold_credited
    else:  # pragma: no cover - guarded by TAIL_CASES
        raise ContractRegressionError(f"UNKNOWN_TAIL_CASE:{case_id}")

    decision = supervisor.evaluate(context)
    prepared_batch_size = len(decision.atomic_batch)
    if decision.action is ActionKind.ATOMIC_ONE_STEP_BATCH:
        committed = supervisor.consume_atomic_batch(decision, context)
        committed_batch_size = 0 if committed is None else len(committed)
        second_consume_rejected = (
            supervisor.consume_atomic_batch(decision, context) is None
        )
    atomic_all_or_none = committed_batch_size in {0, prepared_batch_size}
    unsafe_count = _decision_unsafe_entry_count(decision, context)
    contract_pass = bool(
        (decision.state, decision.action, decision.source) == expected
        and unsafe_count == 0
        and decision.used_full_astar is False
        and atomic_all_or_none
        and second_consume_rejected
        and (
            not tier.strict_pibt_enabled
            or case_id != "strict_local_blocker"
            or committed_batch_size == prepared_batch_size == 2
        )
    )
    return {
        "schema": SUMMARY_SCHEMA,
        "evaluation_scope": EVALUATION_SCOPE,
        "tier": tier.tier,
        "feature_stack": tier.feature_stack,
        "case_id": case_id,
        "local_rule_enabled": tier.local_rule_enabled,
        "safe_hold_credited": tier.safe_hold_credited,
        "strict_pibt_enabled": tier.strict_pibt_enabled,
        "local_rule_veto_applied": local_rule_veto,
        "capability_credited_to_tier": capability_credited,
        "supervisor_state": decision.state.value,
        "action": decision.action.value,
        "source": decision.source.value,
        "reason": decision.reason,
        "selected_next_node": decision.selected_next_node,
        "pibt_requested": context.pibt_requested,
        "pibt_request_source": context.pibt_request_source.value,
        "pibt_applicable": context.pibt_applicable,
        "prepared_batch_size": prepared_batch_size,
        "committed_batch_size": committed_batch_size,
        "second_atomic_consume_rejected": second_consume_rejected,
        "atomic_all_or_none": atomic_all_or_none,
        "unsafe_entry_count": unsafe_count,
        "used_full_astar_count": int(decision.used_full_astar),
        "contract_pass": contract_pass,
    }


def build_tail_pibt_rows() -> list[dict[str, Any]]:
    """Build the T0--T3 capability ladder against the real supervisor."""

    rows = [
        _tail_case(tier, case_id)
        for tier in TAIL_TIERS
        for case_id in TAIL_CASES
    ]
    if len(rows) != len(TAIL_TIERS) * len(TAIL_CASES):
        raise ContractRegressionError("TAIL_MATRIX_INCOMPLETE")
    return rows


def _trace(decisions: Sequence[SupervisorDecision]) -> str:
    return " -> ".join(
        f"{decision.state.value}/{decision.action.value}/{decision.reason}"
        for decision in decisions
    )


def _fault_row(
    *,
    case_id: str,
    supervisor: G4IRSF16Supervisor,
    decisions: Sequence[SupervisorDecision],
    contexts: Sequence[DecisionContext],
    repair_expected: bool = False,
    old_token_rejection_tested: bool = False,
    old_token_rejected: bool = True,
    pibt_prepared_batch_size: int = 0,
    pibt_aborted_commit_size: int = 0,
    pibt_successful_commit_size: int = 0,
    second_atomic_consume_rejected: bool = True,
    message_generation_gap: int = 0,
    scenario_checks: Sequence[bool] = (),
) -> dict[str, Any]:
    if not decisions or len(decisions) != len(contexts):
        raise ContractRegressionError(f"FAULT_TRACE_INVALID:{case_id}")
    audit = supervisor.audit_log()
    audit_contiguous = [row.sequence for row in audit] == list(
        range(1, len(audit) + 1)
    )
    unsafe_count = sum(
        _decision_unsafe_entry_count(decision, context)
        for decision, context in zip(decisions, contexts, strict=True)
    )
    unsafe_count += int(old_token_rejection_tested and not old_token_rejected)
    unsafe_count += int(pibt_aborted_commit_size != 0)
    unsafe_count += int(
        pibt_successful_commit_size not in {0, pibt_prepared_batch_size}
    )
    unsafe_count += int(
        pibt_prepared_batch_size > 0 and not second_atomic_consume_rejected
    )
    used_astar_count = sum(int(decision.used_full_astar) for decision in decisions)
    stale_count = sum(
        int(decision.stale_generation_rejected) for decision in decisions
    )
    repair_count = sum(int(decision.repair_reentry) for decision in decisions)
    repair_once = repair_count == (1 if repair_expected else 0)
    prepared = pibt_prepared_batch_size
    atomic_all_or_none = bool(
        pibt_aborted_commit_size == 0
        and pibt_successful_commit_size in {0, prepared}
        and second_atomic_consume_rejected
    )
    final = decisions[-1]
    contract_pass = bool(
        all(scenario_checks)
        and unsafe_count == 0
        and used_astar_count == 0
        and audit_contiguous
        and repair_once
        and (not old_token_rejection_tested or old_token_rejected)
        and atomic_all_or_none
    )
    return {
        "schema": SUMMARY_SCHEMA,
        "evaluation_scope": EVALUATION_SCOPE,
        "case_id": case_id,
        "event_count": len(decisions),
        "terminal_state": final.state.value,
        "terminal_action": final.action.value,
        "terminal_reason": final.reason,
        "stale_generation_rejection_count": stale_count,
        "revoked_token_count": final.counters.revoked_token_count,
        "repair_expected": repair_expected,
        "repair_reentry_count": repair_count,
        "repair_once": repair_once,
        "old_token_rejection_tested": old_token_rejection_tested,
        "old_token_rejected": old_token_rejected,
        "pibt_prepared_batch_size": prepared,
        "pibt_aborted_commit_size": pibt_aborted_commit_size,
        "pibt_successful_commit_size": pibt_successful_commit_size,
        "second_atomic_consume_rejected": second_atomic_consume_rejected,
        "atomic_all_or_none": atomic_all_or_none,
        "unsafe_entry_count": unsafe_count,
        "used_full_astar_count": used_astar_count,
        "audit_sequence_contiguous": audit_contiguous,
        "message_generation_gap": message_generation_gap,
        "event_trace": _trace(decisions),
        "contract_pass": contract_pass,
    }


def _fault_no_fault() -> dict[str, Any]:
    case_id = "no_fault"
    supervisor = G4IRSF16Supervisor()
    context = _context(case_id)
    decision = supervisor.evaluate(context)
    first_consume = supervisor.consume_token(decision.token, context)
    second_consume_rejected = not supervisor.consume_token(decision.token, context)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[decision],
        contexts=[context],
        second_atomic_consume_rejected=True,
        scenario_checks=[
            decision.state is SupervisorState.F2_NORMAL,
            decision.source is ActionSource.FROZEN_F2,
            first_consume,
            second_consume_rejected,
        ],
    )


def _fault_physical_shield() -> dict[str, Any]:
    case_id = "physical_shield"
    supervisor = G4IRSF16Supervisor()
    context = _context(
        case_id,
        physical_fault_generation=1,
        fault_active=True,
    )
    decision = supervisor.evaluate(context)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[decision],
        contexts=[context],
        scenario_checks=[
            decision.state is SupervisorState.FAULT_RECOVERY,
            decision.action is ActionKind.FAULT_HOLD,
            decision.source is ActionSource.PHYSICAL_FAULT_SHIELD,
            decision.token is None,
        ],
    )


def _fault_delayed_message() -> dict[str, Any]:
    case_id = "delayed_message"
    supervisor = G4IRSF16Supervisor()
    current = _context(case_id, generation=5, physical_fault_generation=2)
    first = supervisor.evaluate(current)
    delayed_fault = replace(current, physical_fault_generation=1)
    second = supervisor.evaluate(delayed_fault)
    old_rejected = not supervisor.token_is_current(first.token, current)
    third = supervisor.evaluate(current)
    delayed_node = replace(current, generation=4)
    fourth = supervisor.evaluate(delayed_node)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[first, second, third, fourth],
        contexts=[current, delayed_fault, current, delayed_node],
        old_token_rejection_tested=True,
        old_token_rejected=old_rejected,
        scenario_checks=[
            second.stale_generation_rejected,
            "stale_physical" in second.reason,
            fourth.stale_generation_rejected,
            "stale_node" in fourth.reason,
        ],
    )


def _fault_dropped_message() -> dict[str, Any]:
    case_id = "dropped_message"
    supervisor = G4IRSF16Supervisor()
    initial = _context(case_id)
    first = supervisor.evaluate(initial)
    # Generation 1 is intentionally absent: the newest generation must still
    # invalidate all actions prepared against generation 0.
    jumped_fault = replace(
        initial,
        physical_fault_generation=2,
        fault_active=True,
    )
    second = supervisor.evaluate(jumped_fault)
    old_rejected = not supervisor.token_is_current(first.token, initial)
    repaired_context = replace(jumped_fault, fault_active=False)
    third = supervisor.evaluate(repaired_context)
    fourth = supervisor.evaluate(repaired_context)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[first, second, third, fourth],
        contexts=[initial, jumped_fault, repaired_context, repaired_context],
        repair_expected=True,
        old_token_rejection_tested=True,
        old_token_rejected=old_rejected,
        message_generation_gap=2,
        scenario_checks=[
            second.action is ActionKind.FAULT_HOLD,
            third.repair_reentry,
            not fourth.repair_reentry,
            fourth.counters.repair_reentry_count == 1,
        ],
    )


def _fault_repair_reopen() -> dict[str, Any]:
    case_id = "repair_reopen"
    supervisor = G4IRSF16Supervisor()
    fault = _context(
        case_id,
        physical_fault_generation=1,
        fault_active=True,
    )
    first = supervisor.evaluate(fault)
    repaired = replace(fault, fault_active=False)
    second = supervisor.evaluate(repaired)
    third = supervisor.evaluate(repaired)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[first, second, third],
        contexts=[fault, repaired, repaired],
        repair_expected=True,
        scenario_checks=[
            second.repair_reentry,
            second.source is ActionSource.FROZEN_F2,
            not third.repair_reentry,
            third.counters.repair_reentry_count == 1,
        ],
    )


def _fault_i4_hold() -> dict[str, Any]:
    case_id = "i4_hold_fault"
    supervisor = G4IRSF16Supervisor()
    proposal = _context(
        case_id,
        i4_proposed=True,
        i4_model_authorized=True,
        i4_confidence=0.99,
        i4_risk=0.001,
    )
    first = supervisor.evaluate(proposal)
    fault = replace(
        proposal,
        physical_fault_generation=1,
        fault_active=True,
    )
    second = supervisor.evaluate(fault)
    old_rejected = not supervisor.consume_token(first.token, proposal)
    repaired = replace(fault, fault_active=False)
    third = supervisor.evaluate(repaired)
    fourth = supervisor.evaluate(repaired)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[first, second, third, fourth],
        contexts=[proposal, fault, repaired, repaired],
        repair_expected=True,
        old_token_rejection_tested=True,
        old_token_rejected=old_rejected,
        scenario_checks=[
            first.action is ActionKind.HOLD_ONE_NATURAL_OPPORTUNITY,
            second.action is ActionKind.FAULT_HOLD,
            third.repair_reentry,
            fourth.state is SupervisorState.F2_NORMAL,
            "opportunity_consumed" in fourth.reason,
            fourth.counters.hold_count == 1,
        ],
    )


def _fault_i3_prepare() -> dict[str, Any]:
    case_id = "i3_prepare_fault"
    supervisor = G4IRSF16Supervisor()
    proposal = _context(
        case_id,
        i3_action=12,
        i3_model_authorized=True,
        i3_confidence=0.99,
        i3_risk=0.001,
    )
    first = supervisor.evaluate(proposal)
    fault = replace(
        proposal,
        physical_fault_generation=1,
        fault_active=True,
    )
    second = supervisor.evaluate(fault)
    old_rejected = not supervisor.consume_token(first.token, proposal)
    repaired = replace(fault, fault_active=False)
    third = supervisor.evaluate(repaired)
    fourth = supervisor.evaluate(repaired)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[first, second, third, fourth],
        contexts=[proposal, fault, repaired, repaired],
        repair_expected=True,
        old_token_rejection_tested=True,
        old_token_rejected=old_rejected,
        scenario_checks=[
            first.state is SupervisorState.I3_RARE_OVERRIDE,
            second.action is ActionKind.FAULT_HOLD,
            third.repair_reentry,
            fourth.state is SupervisorState.F2_NORMAL,
            "override_consumed" in fourth.reason,
            fourth.counters.override_count == 1,
        ],
    )


def _fault_pibt_transaction() -> dict[str, Any]:
    case_id = "pibt_transaction_fault"
    supervisor = G4IRSF16Supervisor()
    prepared_context = _strict_pibt_context(case_id)
    first = supervisor.evaluate(prepared_context)
    fault = replace(
        prepared_context,
        physical_fault_generation=1,
        fault_active=True,
    )
    second = supervisor.evaluate(fault)
    aborted = supervisor.consume_atomic_batch(first, prepared_context)
    old_rejected = aborted is None
    repair = _context(
        case_id,
        generation=3,
        physical_fault_generation=1,
        fault_active=False,
    )
    third = supervisor.evaluate(repair)
    retry = _strict_pibt_context(
        case_id,
        physical_fault_generation=1,
        generation=4,
    )
    fourth = supervisor.evaluate(retry)
    committed = supervisor.consume_atomic_batch(fourth, retry)
    second_consume_rejected = (
        supervisor.consume_atomic_batch(fourth, retry) is None
    )
    prepared_size = len(fourth.atomic_batch)
    committed_size = 0 if committed is None else len(committed)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[first, second, third, fourth],
        contexts=[prepared_context, fault, repair, retry],
        repair_expected=True,
        old_token_rejection_tested=True,
        old_token_rejected=old_rejected,
        pibt_prepared_batch_size=prepared_size,
        pibt_aborted_commit_size=0 if aborted is None else len(aborted),
        pibt_successful_commit_size=committed_size,
        second_atomic_consume_rejected=second_consume_rejected,
        scenario_checks=[
            first.action is ActionKind.ATOMIC_ONE_STEP_BATCH,
            second.action is ActionKind.FAULT_HOLD,
            third.repair_reentry,
            fourth.action is ActionKind.ATOMIC_ONE_STEP_BATCH,
            prepared_size == committed_size == 2,
        ],
    )


def _fault_full_astar() -> dict[str, Any]:
    case_id = "full_astar_request_forbidden"
    supervisor = G4IRSF16Supervisor()
    context = _context(case_id, astar_fallback_requested=True)
    decision = supervisor.evaluate(context)
    return _fault_row(
        case_id=case_id,
        supervisor=supervisor,
        decisions=[decision],
        contexts=[context],
        scenario_checks=[
            decision.state is SupervisorState.SAFE_HOLD,
            decision.reason == "full_astar_fallback_forbidden",
            not decision.used_full_astar,
        ],
    )


def build_fault_rows() -> list[dict[str, Any]]:
    """Build delayed/dropped/fault/repair transaction regressions."""

    rows = [
        _fault_no_fault(),
        _fault_physical_shield(),
        _fault_delayed_message(),
        _fault_dropped_message(),
        _fault_repair_reopen(),
        _fault_i4_hold(),
        _fault_i3_prepare(),
        _fault_pibt_transaction(),
        _fault_full_astar(),
    ]
    if tuple(row["case_id"] for row in rows) != REQUIRED_FAULT_CASES:
        raise ContractRegressionError("FAULT_MATRIX_INCOMPLETE")
    return rows


def build_summary(
    tail_rows: Sequence[Mapping[str, Any]],
    fault_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate strict pass/fail invariants without performance claims."""

    tail_unsafe = sum(int(row["unsafe_entry_count"]) for row in tail_rows)
    fault_unsafe = sum(int(row["unsafe_entry_count"]) for row in fault_rows)
    astar_count = sum(
        int(row["used_full_astar_count"])
        for row in tuple(tail_rows) + tuple(fault_rows)
    )
    stale_rejections = sum(
        int(row["stale_generation_rejection_count"]) for row in fault_rows
    )
    repair_rows = [row for row in fault_rows if row["repair_expected"] is True]
    repair_once = bool(
        repair_rows
        and all(
            int(row["repair_reentry_count"]) == 1
            and row["repair_once"] is True
            for row in repair_rows
        )
    )
    t3_pibt = next(
        row
        for row in tail_rows
        if row["tier"] == "T3" and row["case_id"] == "strict_local_blocker"
    )
    pibt_fault = next(
        row for row in fault_rows if row["case_id"] == "pibt_transaction_fault"
    )
    atomic = bool(
        t3_pibt["atomic_all_or_none"] is True
        and int(t3_pibt["prepared_batch_size"])
        == int(t3_pibt["committed_batch_size"])
        == 2
        and pibt_fault["atomic_all_or_none"] is True
        and int(pibt_fault["pibt_aborted_commit_size"]) == 0
        and int(pibt_fault["pibt_prepared_batch_size"])
        == int(pibt_fault["pibt_successful_commit_size"])
        == 2
    )
    tail_pass = all(row["contract_pass"] is True for row in tail_rows)
    fault_pass = all(row["contract_pass"] is True for row in fault_rows)
    invariants = {
        "unsafe_zero": tail_unsafe + fault_unsafe == 0,
        "stale_action_rejected": stale_rejections >= 2,
        "repair_reentry_once_per_fault_episode": repair_once,
        "pibt_atomic_all_or_none": atomic,
        "full_astar_forbidden": (
            FULL_ASTAR_FALLBACK_ALLOWED is False and astar_count == 0
        ),
    }
    overall_pass = tail_pass and fault_pass and all(invariants.values())
    summary: dict[str, Any] = {
        "schema": SUMMARY_SCHEMA,
        "evaluation_scope": EVALUATION_SCOPE,
        "disclaimer": (
            "Synthetic supervisor state-machine contract regression only; not "
            "a full closed-loop run, not TTH evidence, and not a tail-performance "
            "or causal-improvement claim."
        ),
        "supervisor_contract_source": (
            "src/czr005/policies/g4irsf16_supervisor.py"
        ),
        "unsafe_definition": (
            "Any prepared/committed move while a physical fault is active, any "
            "illegal or shield-unsafe edge, any stale-token acceptance, or any "
            "partial PIBT batch."
        ),
        "output_files": {
            "tail_pibt_table": TAIL_TABLE_OUTPUT.as_posix(),
            "fault_table": FAULT_TABLE_OUTPUT.as_posix(),
            "tail_pibt_report": TAIL_REPORT_OUTPUT.as_posix(),
            "fault_report": FAULT_REPORT_OUTPUT.as_posix(),
            "summary": SUMMARY_OUTPUT.as_posix(),
        },
        "tail_pibt": {
            "tier_count": len({str(row["tier"]) for row in tail_rows}),
            "case_count_per_tier": len(TAIL_CASES),
            "row_count": len(tail_rows),
            "contract_pass": tail_pass,
            "unsafe_entry_count": tail_unsafe,
            "strict_pibt_commit_count": sum(
                int(row["committed_batch_size"] > 0) for row in tail_rows
            ),
            "capability_credit_note": (
                "SAFE_HOLD remains a hard supervisor invariant at every tier; "
                "T0/T1 safe holds are not credited as tier capabilities."
            ),
        },
        "fault": {
            "required_cases": list(REQUIRED_FAULT_CASES),
            "row_count": len(fault_rows),
            "contract_pass": fault_pass,
            "unsafe_entry_count": fault_unsafe,
            "stale_generation_rejection_count": stale_rejections,
            "repair_episode_count": len(repair_rows),
        },
        "invariants": invariants,
        "overall_pass": overall_pass,
    }
    if not overall_pass:
        failed = [name for name, passed in invariants.items() if not passed]
        raise ContractRegressionError(
            "CONTRACT_REGRESSION_FAILED:" + ",".join(failed or ["ROW_CHECK"])
        )
    return summary


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def render_tail_report(
    rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]
) -> str:
    aggregate = []
    for tier in TAIL_TIERS:
        members = [row for row in rows if row["tier"] == tier.tier]
        aggregate.append(
            [
                tier.tier,
                tier.feature_stack,
                len(members),
                sum(row["capability_credited_to_tier"] is True for row in members),
                sum(row["action"] == ActionKind.SAFE_HOLD.value for row in members),
                sum(
                    row["action"] == ActionKind.ATOMIC_ONE_STEP_BATCH.value
                    for row in members
                ),
                sum(int(row["unsafe_entry_count"]) for row in members),
                all(row["contract_pass"] is True for row in members),
            ]
        )
    return "\n".join(
        [
            "# G4IRSF16 Stage 16K tail/PIBT supervisor contract A/B",
            "",
            "## Scope",
            "",
            "This is a deterministic supervisor state-machine contract regression. "
            "It is **not** a full closed-loop run and does not measure TTH, mean, "
            "p99, maximum, throughput, or causal improvement. The A/B matrix tests "
            "which contract capability receives credit; it is not a performance "
            "ablation.",
            "",
            "T1's local rule is represented only as a local authorization veto "
            "that preserves frozen F2. No unrepresented rule movement source is "
            "invented. SAFE_HOLD remains a hard supervisor invariant in every row; "
            "T0/T1 occurrences are deliberately not credited to those tiers.",
            "",
            "## Contract matrix",
            "",
            _markdown_table(
                [
                    "Tier",
                    "Feature stack",
                    "Cases",
                    "Tier-credited",
                    "Safe holds",
                    "PIBT batches",
                    "Unsafe",
                    "Pass",
                ],
                aggregate,
            ),
            "",
            "## Evidence",
            "",
            "- High-confidence I3 and I4 proposals traverse the learned supervisor "
            "states; the local rule veto preserves exact frozen F2.",
            "- Strict PIBT is credited only for T3 and only when the local-blocker, "
            "movability, safe-alternative, and atomic-batch gates all pass.",
            "- Model abstention cannot directly trigger PIBT. Invalid batches and "
            "forbidden full-A* requests fail closed to SAFE_HOLD.",
            f"- Unsafe entries: {summary['tail_pibt']['unsafe_entry_count']}; "
            "full-A* uses: 0; all prepared PIBT batches commit all-or-none.",
            "",
            "## Interpretation boundary",
            "",
            "No tail-performance conclusion can be drawn until the same tiers are "
            "run in the original-scale closed loop with preregistered TTH and tail "
            "metrics. This artifact only proves the supervisor contract exercised "
            "here is fail-closed and attribution-safe.",
            "",
        ]
    )


def render_fault_report(
    rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]
) -> str:
    table = [
        [
            row["case_id"],
            row["event_count"],
            row["terminal_state"],
            row["stale_generation_rejection_count"],
            row["repair_reentry_count"],
            row["pibt_successful_commit_size"],
            row["unsafe_entry_count"],
            row["contract_pass"],
        ]
        for row in rows
    ]
    return "\n".join(
        [
            "# G4IRSF16 Stage 16L fault supervisor contract regression",
            "",
            "## Scope",
            "",
            "This is a synthetic, deterministic state-machine regression against "
            "the real Python supervisor contract. It is not a native runtime fault "
            "campaign, full closed-loop experiment, TTH measurement, or active "
            "multi-fault benefit claim.",
            "",
            "## Results",
            "",
            _markdown_table(
                [
                    "Case",
                    "Events",
                    "Terminal state",
                    "Stale rejects",
                    "Repair entries",
                    "PIBT commit",
                    "Unsafe",
                    "Pass",
                ],
                table,
            ),
            "",
            "## Enforced invariants",
            "",
            f"- `unsafe = {summary['fault']['unsafe_entry_count']}` under the "
            "published local contract definition.",
            "- Delayed physical-fault and node-generation messages are rejected; "
            "a dropped intermediate generation cannot keep an old token alive.",
            "- Repair re-entry occurs exactly once per simulated fault episode, "
            "including I4 hold, I3 prepare, and PIBT transaction interruption.",
            "- A fault between PIBT prepare and consume aborts the whole old batch; "
            "a fresh post-repair batch commits completely and can be consumed once.",
            "- Full A* is not an action source and every request is rejected to "
            "SAFE_HOLD with `used_full_astar = false`.",
            "",
            "## Interpretation boundary",
            "",
            "Passing this report establishes only the listed supervisor-level "
            "fault contracts. Native event transport, BTI/DDI integration, traffic "
            "performance, and original-scale closed-loop safety still require their "
            "separate campaigns.",
            "",
        ]
    )


def _write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_contract_regression(output_root: Path) -> dict[str, Any]:
    """Run, validate, and publish the complete deterministic regression."""

    root = Path(output_root)
    tail_rows = build_tail_pibt_rows()
    fault_rows = build_fault_rows()
    summary = build_summary(tail_rows, fault_rows)
    _write_csv(root / TAIL_TABLE_OUTPUT, TAIL_COLUMNS, tail_rows)
    _write_csv(root / FAULT_TABLE_OUTPUT, FAULT_COLUMNS, fault_rows)
    tail_report = render_tail_report(tail_rows, summary)
    fault_report = render_fault_report(fault_rows, summary)
    (root / TAIL_REPORT_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    (root / TAIL_REPORT_OUTPUT).write_text(
        tail_report,
        encoding="utf-8",
        newline="\n",
    )
    (root / FAULT_REPORT_OUTPUT).write_text(
        fault_report,
        encoding="utf-8",
        newline="\n",
    )
    (root / SUMMARY_OUTPUT).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


__all__ = [
    "ContractRegressionError",
    "EVALUATION_SCOPE",
    "FAULT_COLUMNS",
    "FAULT_REPORT_OUTPUT",
    "FAULT_TABLE_OUTPUT",
    "REQUIRED_FAULT_CASES",
    "SUMMARY_OUTPUT",
    "SUMMARY_SCHEMA",
    "TAIL_CASES",
    "TAIL_COLUMNS",
    "TAIL_REPORT_OUTPUT",
    "TAIL_TABLE_OUTPUT",
    "TAIL_TIERS",
    "build_fault_rows",
    "build_summary",
    "build_tail_pibt_rows",
    "render_fault_report",
    "render_tail_report",
    "write_contract_regression",
]

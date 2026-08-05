"""Fail-closed G4IRSF16 selective-action supervisor contract.

The supervisor is deliberately independent from model loading and the C++
runtime.  A caller supplies already-computed, runtime-local proposals and the
contract decides whether one of them may replace the frozen F2 one-edge
action.  It never plans a route, reads future state, or invokes a fallback
planner.

The stateful latches are scoped to one active segment per runtime bag:

* I4 may consume one natural service opportunity per ``(node, generation)``;
* I3 may replace F2 at most once per segment;
* a PIBT decision contains the complete validated one-step batch or none of it;
* fault/node generation changes revoke previously issued action tokens.

Unknown, unauthorised, low-confidence, or high-risk learned proposals abstain.
Abstention preserves a legal and shield-safe F2 action; it does *not* create a
hold.  If F2 is unavailable, only a strictly applicable local-blocker PIBT
batch may run, otherwise the result is a safe hold.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum
import math
from typing import Any, Iterable


FULL_ASTAR_FALLBACK_ALLOWED = False


class SupervisorState(str, Enum):
    """The six preregistered Stage-16G supervisor states."""

    F2_NORMAL = "F2_NORMAL"
    I4_SELECTIVE_HOLD = "I4_SELECTIVE_HOLD"
    I3_RARE_OVERRIDE = "I3_RARE_OVERRIDE"
    PIBT_RECOVERY = "PIBT_RECOVERY"
    SAFE_HOLD = "SAFE_HOLD"
    FAULT_RECOVERY = "FAULT_RECOVERY"


class ActionKind(str, Enum):
    MOVE_ONE_EDGE = "MOVE_ONE_EDGE"
    HOLD_ONE_NATURAL_OPPORTUNITY = "HOLD_ONE_NATURAL_OPPORTUNITY"
    ATOMIC_ONE_STEP_BATCH = "ATOMIC_ONE_STEP_BATCH"
    SAFE_HOLD = "SAFE_HOLD"
    FAULT_HOLD = "FAULT_HOLD"


class ActionSource(str, Enum):
    FROZEN_F2 = "FROZEN_F2"
    I4_MODEL = "I4_MODEL"
    I3_MODEL = "I3_MODEL"
    STRICT_LOCAL_PIBT = "STRICT_LOCAL_PIBT"
    LOCAL_SAFETY = "LOCAL_SAFETY"
    PHYSICAL_FAULT_SHIELD = "PHYSICAL_FAULT_SHIELD"


class PibtRequestSource(str, Enum):
    """PIBT cannot be reached merely because a learned model abstained."""

    NONE = "NONE"
    LOCAL_BLOCKER = "LOCAL_BLOCKER"
    MODEL_ABSTENTION = "MODEL_ABSTENTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SupervisorConfig:
    """Preregistered activation thresholds.

    Scores are probabilities/risk rates in ``[0, 1]``.  Missing or non-finite
    scores always fail their gate.
    """

    i4_min_confidence: float = 0.90
    i4_max_risk: float = 0.005
    i3_min_confidence: float = 0.95
    i3_max_risk: float = 0.0025

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a real number")
            if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class PibtMove:
    """One member of a prepared bounded-local PIBT transaction."""

    owner_bag_id: str
    segment_id: str
    from_node: int
    to_node: int
    generation: int
    physical_fault_generation: int
    legal: bool
    shield_safe: bool

    def structurally_valid(self, expected_fault_generation: int) -> bool:
        return (
            _nonempty_id(self.owner_bag_id)
            and _nonempty_id(self.segment_id)
            and _plain_int(self.from_node)
            and _plain_int(self.to_node)
            and self.from_node != self.to_node
            and _nonnegative_int(self.generation)
            and _nonnegative_int(self.physical_fault_generation)
            and self.physical_fault_generation == expected_fault_generation
            and self.legal is True
            and self.shield_safe is True
        )


@dataclass(frozen=True)
class DecisionContext:
    """Runtime-local inputs for one supervisor evaluation.

    ``legal_alternatives`` contains every next node currently legal for this
    owner, including F2 when F2 is executable.  ``shield_safe`` is the final
    physical-shield verdict for ordinary one-edge actions.  PIBT moves carry
    their own per-move legality and shield verdicts because a batch can have
    multiple owners.
    """

    runtime_bag_id: str
    segment_id: str
    node: int
    generation: int
    physical_fault_generation: int
    f2_action: int | None
    legal_alternatives: tuple[int, ...]
    service_opportunity_available: bool
    shield_safe: bool

    i4_proposed: bool = False
    i4_model_authorized: bool = False
    i4_confidence: float | None = None
    i4_risk: float | None = None

    i3_action: int | None = None
    i3_model_authorized: bool = False
    i3_confidence: float | None = None
    i3_risk: float | None = None

    pibt_requested: bool = False
    pibt_request_source: PibtRequestSource | str = PibtRequestSource.NONE
    pibt_applicable: bool = False
    pibt_owner_movable: bool = False
    pibt_safe_alternative: bool = False
    pibt_atomic_possible: bool = False
    pibt_batch: tuple[PibtMove, ...] = ()

    fault_active: bool = False
    astar_fallback_requested: bool = False

    def __post_init__(self) -> None:
        if not _nonempty_id(self.runtime_bag_id):
            raise ValueError("runtime_bag_id must be a non-empty string")
        if not _nonempty_id(self.segment_id):
            raise ValueError("segment_id must be a non-empty string")
        if not _plain_int(self.node):
            raise TypeError("node must be an integer")
        if not _nonnegative_int(self.generation):
            raise ValueError("generation must be a non-negative integer")
        if not _nonnegative_int(self.physical_fault_generation):
            raise ValueError(
                "physical_fault_generation must be a non-negative integer"
            )
        if self.f2_action is not None and not _plain_int(self.f2_action):
            raise TypeError("f2_action must be an integer or None")
        if self.i3_action is not None and not _plain_int(self.i3_action):
            raise TypeError("i3_action must be an integer or None")

        legal = tuple(self.legal_alternatives)
        if any(not _plain_int(value) for value in legal):
            raise TypeError("legal_alternatives must contain only integers")
        object.__setattr__(self, "legal_alternatives", tuple(dict.fromkeys(legal)))

        batch = tuple(self.pibt_batch)
        if any(not isinstance(move, PibtMove) for move in batch):
            raise TypeError("pibt_batch must contain only PibtMove records")
        object.__setattr__(self, "pibt_batch", batch)

        source = self.pibt_request_source
        if not isinstance(source, PibtRequestSource):
            try:
                source = PibtRequestSource(str(source))
            except ValueError:
                source = PibtRequestSource.UNKNOWN
            object.__setattr__(self, "pibt_request_source", source)

        for name in (
            "service_opportunity_available",
            "shield_safe",
            "i4_proposed",
            "i4_model_authorized",
            "i3_model_authorized",
            "pibt_requested",
            "pibt_applicable",
            "pibt_owner_movable",
            "pibt_safe_alternative",
            "pibt_atomic_possible",
            "fault_active",
            "astar_fallback_requested",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")


@dataclass(frozen=True)
class LatchCounters:
    decision_count: int = 0
    transition_count: int = 0
    activation_count: int = 0
    hold_count: int = 0
    override_count: int = 0
    pibt_count: int = 0
    safe_hold_count: int = 0
    fault_recovery_count: int = 0
    stale_generation_rejection_count: int = 0
    revoked_token_count: int = 0
    repair_reentry_count: int = 0


@dataclass(frozen=True)
class ActionToken:
    """Generation-bound token returned for a non-fault action."""

    token_id: int
    runtime_bag_id: str
    segment_id: str
    node: int
    generation: int
    physical_fault_generation: int
    state_generation: int
    action: ActionKind
    source: ActionSource
    selected_next_node: int | None
    atomic_batch: tuple[PibtMove, ...]


@dataclass(frozen=True)
class SupervisorDecision:
    state: SupervisorState
    action: ActionKind
    source: ActionSource
    reason: str
    selected_next_node: int | None
    atomic_batch: tuple[PibtMove, ...]
    token: ActionToken | None
    state_generation: int
    counters: LatchCounters
    reevaluation_required: bool = False
    stale_generation_rejected: bool = False
    repair_reentry: bool = False
    used_full_astar: bool = False

    @property
    def atomic(self) -> bool:
        return self.action is ActionKind.ATOMIC_ONE_STEP_BATCH

    def as_audit_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["action"] = self.action.value
        payload["source"] = self.source.value
        return payload


@dataclass(frozen=True)
class TransitionRecord:
    sequence: int
    runtime_bag_id: str
    segment_id: str
    node: int
    node_generation: int
    physical_fault_generation: int
    from_state: SupervisorState
    to_state: SupervisorState
    state_generation: int
    action: ActionKind
    source: ActionSource
    reason: str
    counters: LatchCounters

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for name in ("from_state", "to_state", "action", "source"):
            payload[name] = getattr(self, name).value
        return payload


@dataclass
class _BagState:
    segment_id: str
    state: SupervisorState = SupervisorState.F2_NORMAL
    state_generation: int = 0
    counters: LatchCounters = field(default_factory=LatchCounters)
    consumed_i4: set[tuple[int, int]] = field(default_factory=set)
    i3_override_edge: tuple[int, int] | None = None
    last_selected_edge: tuple[int, int] | None = None
    latest_node_generation: dict[int, int] = field(default_factory=dict)
    physical_fault_generation: int = 0
    fault_active: bool = False
    active_tokens: set[int] = field(default_factory=set)


class G4IRSF16Supervisor:
    """Stateful, audit-logged Stage-16G policy supervisor."""

    def __init__(self, config: SupervisorConfig | None = None) -> None:
        self.config = config or SupervisorConfig()
        self._bags: dict[str, _BagState] = {}
        self._tokens: dict[int, ActionToken] = {}
        self._audit: list[TransitionRecord] = []
        self._seen_segments: dict[str, set[str]] = {}
        self._next_token_id = 1

    def evaluate(self, context: DecisionContext) -> SupervisorDecision:
        """Evaluate proposals in safety-first order and append one audit row."""

        if not isinstance(context, DecisionContext):
            raise TypeError("context must be a DecisionContext")

        existing = self._bags.get(context.runtime_bag_id)
        if (
            existing is not None
            and context.segment_id != existing.segment_id
            and context.segment_id
            in self._seen_segments.get(context.runtime_bag_id, set())
        ):
            from_state = existing.state
            self._revoke_tokens(existing)
            existing.counters = replace(
                existing.counters,
                stale_generation_rejection_count=(
                    existing.counters.stale_generation_rejection_count + 1
                ),
            )
            return self._finish(
                existing,
                context,
                from_state,
                state=SupervisorState.FAULT_RECOVERY,
                action=ActionKind.FAULT_HOLD,
                source=ActionSource.PHYSICAL_FAULT_SHIELD,
                reason="retired_segment_replay_rejected",
                stale_generation_rejected=True,
            )

        bag = self._state_for(context)
        from_state = bag.state

        stale_reason = self._stale_generation_reason(bag, context)
        if stale_reason is not None:
            self._revoke_tokens(bag)
            bag.counters = replace(
                bag.counters,
                stale_generation_rejection_count=(
                    bag.counters.stale_generation_rejection_count + 1
                ),
            )
            return self._finish(
                bag,
                context,
                from_state,
                state=SupervisorState.FAULT_RECOVERY,
                action=ActionKind.FAULT_HOLD,
                source=ActionSource.PHYSICAL_FAULT_SHIELD,
                reason=stale_reason,
                stale_generation_rejected=True,
            )

        # Advancing either generation invalidates actions prepared against the
        # previous local/fault view before any new proposal can be considered.
        previous_node_generation = bag.latest_node_generation.get(context.node)
        if (
            previous_node_generation is not None
            and context.generation > previous_node_generation
        ):
            self._revoke_tokens(bag)
        if context.physical_fault_generation > bag.physical_fault_generation:
            self._revoke_tokens(bag)
            bag.physical_fault_generation = context.physical_fault_generation
        bag.latest_node_generation[context.node] = context.generation

        if context.fault_active:
            self._revoke_tokens(bag)
            bag.fault_active = True
            return self._finish(
                bag,
                context,
                from_state,
                state=SupervisorState.FAULT_RECOVERY,
                action=ActionKind.FAULT_HOLD,
                source=ActionSource.PHYSICAL_FAULT_SHIELD,
                reason="physical_fault_active",
                increment="fault_recovery_count",
            )

        if bag.fault_active:
            # The repair boundary clears transient fault state once.  Learned
            # actions supplied with the repair event are intentionally ignored;
            # re-entry uses exact F2 or a safe hold, then later events may learn.
            bag.fault_active = False
            bag.counters = replace(
                bag.counters,
                repair_reentry_count=bag.counters.repair_reentry_count + 1,
            )
            self._revoke_tokens(bag)
            if self._f2_executable(context):
                return self._finish(
                    bag,
                    context,
                    from_state,
                    state=SupervisorState.F2_NORMAL,
                    action=ActionKind.MOVE_ONE_EDGE,
                    source=ActionSource.FROZEN_F2,
                    reason="fault_repair_reentry_f2",
                    selected_next_node=context.f2_action,
                    repair_reentry=True,
                )
            return self._finish(
                bag,
                context,
                from_state,
                state=SupervisorState.SAFE_HOLD,
                action=ActionKind.SAFE_HOLD,
                source=ActionSource.LOCAL_SAFETY,
                reason="fault_repair_reentry_no_safe_f2",
                increment="safe_hold_count",
                repair_reentry=True,
            )

        if context.astar_fallback_requested:
            self._revoke_tokens(bag)
            return self._finish(
                bag,
                context,
                from_state,
                state=SupervisorState.SAFE_HOLD,
                action=ActionKind.SAFE_HOLD,
                source=ActionSource.LOCAL_SAFETY,
                reason="full_astar_fallback_forbidden",
                increment="safe_hold_count",
            )

        f2_executable = self._f2_executable(context)
        abstention_reason: str | None = None

        if context.i4_proposed:
            i4_reason = self._i4_rejection_reason(bag, context, f2_executable)
            if i4_reason is None:
                bag.consumed_i4.add((context.node, context.generation))
                return self._finish(
                    bag,
                    context,
                    from_state,
                    state=SupervisorState.I4_SELECTIVE_HOLD,
                    action=ActionKind.HOLD_ONE_NATURAL_OPPORTUNITY,
                    source=ActionSource.I4_MODEL,
                    reason="i4_high_confidence_risk_pass",
                    increment="hold_count",
                    activate=True,
                    reevaluation_required=True,
                )
            abstention_reason = i4_reason

        if context.i3_action is not None:
            i3_reason = self._i3_rejection_reason(bag, context, f2_executable)
            if i3_reason is None:
                bag.i3_override_edge = (context.node, context.i3_action)
                return self._finish(
                    bag,
                    context,
                    from_state,
                    state=SupervisorState.I3_RARE_OVERRIDE,
                    action=ActionKind.MOVE_ONE_EDGE,
                    source=ActionSource.I3_MODEL,
                    reason="i3_high_confidence_legal_risk_pass",
                    selected_next_node=context.i3_action,
                    increment="override_count",
                    activate=True,
                )
            abstention_reason = i3_reason

        if f2_executable:
            return self._finish(
                bag,
                context,
                from_state,
                state=SupervisorState.F2_NORMAL,
                action=ActionKind.MOVE_ONE_EDGE,
                source=ActionSource.FROZEN_F2,
                reason=abstention_reason or "f2_default",
                selected_next_node=context.f2_action,
            )

        pibt_reason = self._pibt_rejection_reason(context)
        if pibt_reason is None:
            return self._finish(
                bag,
                context,
                from_state,
                state=SupervisorState.PIBT_RECOVERY,
                action=ActionKind.ATOMIC_ONE_STEP_BATCH,
                source=ActionSource.STRICT_LOCAL_PIBT,
                reason="pibt_strict_applicable_atomic_batch",
                atomic_batch=context.pibt_batch,
                increment="pibt_count",
                activate=True,
            )

        safe_reason = abstention_reason or pibt_reason or "no_legal_f2_action"
        return self._finish(
            bag,
            context,
            from_state,
            state=SupervisorState.SAFE_HOLD,
            action=ActionKind.SAFE_HOLD,
            source=ActionSource.LOCAL_SAFETY,
            reason=safe_reason,
            increment="safe_hold_count",
        )

    # ``decide`` is an explicit compatibility alias for integration code that
    # names the contract operation after its returned object.
    decide = evaluate

    def token_is_current(
        self, token: ActionToken | None, context: DecisionContext
    ) -> bool:
        """Return whether a prepared action is still generation-current."""

        if token is None or not isinstance(token, ActionToken):
            return False
        bag = self._bags.get(token.runtime_bag_id)
        return bool(
            bag is not None
            and token.token_id in bag.active_tokens
            and self._tokens.get(token.token_id) == token
            and token.runtime_bag_id == context.runtime_bag_id
            and token.segment_id == context.segment_id
            and token.node == context.node
            and token.generation == context.generation
            and token.physical_fault_generation
            == context.physical_fault_generation
            and token.state_generation == bag.state_generation
            and not context.fault_active
            and not bag.fault_active
        )

    def consume_token(
        self, token: ActionToken | None, context: DecisionContext
    ) -> bool:
        """Atomically consume a current action token; stale tokens do nothing."""

        if not self.token_is_current(token, context):
            return False
        assert token is not None  # narrowed by token_is_current
        bag = self._bags[token.runtime_bag_id]
        bag.active_tokens.discard(token.token_id)
        self._tokens.pop(token.token_id, None)
        return True

    def consume_atomic_batch(
        self,
        decision: SupervisorDecision,
        context: DecisionContext,
    ) -> tuple[PibtMove, ...] | None:
        """Consume a PIBT token and return the complete batch, never a prefix."""

        if (
            not isinstance(decision, SupervisorDecision)
            or decision.action is not ActionKind.ATOMIC_ONE_STEP_BATCH
            or not decision.atomic_batch
            or decision.token is None
            or decision.token.action is not decision.action
            or decision.token.source is not decision.source
            or decision.token.atomic_batch != decision.atomic_batch
            or not self.consume_token(decision.token, context)
        ):
            return None
        return decision.atomic_batch

    def audit_log(self) -> tuple[TransitionRecord, ...]:
        return tuple(self._audit)

    def audit_dicts(self) -> tuple[dict[str, Any], ...]:
        return tuple(record.as_dict() for record in self._audit)

    def counters_for(self, runtime_bag_id: str) -> LatchCounters | None:
        bag = self._bags.get(runtime_bag_id)
        return None if bag is None else bag.counters

    validate_action_token = token_is_current

    def reset_for_new_segment(
        self,
        runtime_bag_id: str,
        new_segment_id: str,
        *,
        physical_fault_generation: int,
    ) -> None:
        """Explicitly reset latches only at a different segment boundary."""

        if not _nonempty_id(runtime_bag_id) or not _nonempty_id(new_segment_id):
            raise ValueError("runtime_bag_id and new_segment_id must be non-empty")
        if not _nonnegative_int(physical_fault_generation):
            raise ValueError("physical_fault_generation must be non-negative")
        previous = self._bags.get(runtime_bag_id)
        if previous is not None and previous.segment_id == new_segment_id:
            raise ValueError("cannot reset latches within the same segment")
        if previous is not None and previous.fault_active:
            raise ValueError("cannot reset segment latches while a fault is active")
        if new_segment_id in self._seen_segments.get(runtime_bag_id, set()):
            raise ValueError("cannot reactivate a retired segment")
        if (
            previous is not None
            and physical_fault_generation < previous.physical_fault_generation
        ):
            raise ValueError("cannot reset to a stale physical fault generation")
        if previous is not None:
            self._revoke_tokens(previous)
        self._bags[runtime_bag_id] = _BagState(
            segment_id=new_segment_id,
            physical_fault_generation=physical_fault_generation,
        )
        self._seen_segments.setdefault(runtime_bag_id, set()).add(new_segment_id)

    reset = reset_for_new_segment

    def _state_for(self, context: DecisionContext) -> _BagState:
        bag = self._bags.get(context.runtime_bag_id)
        if bag is None:
            bag = _BagState(
                segment_id=context.segment_id,
                physical_fault_generation=context.physical_fault_generation,
            )
            self._bags[context.runtime_bag_id] = bag
            self._seen_segments.setdefault(context.runtime_bag_id, set()).add(
                context.segment_id
            )
        elif bag.segment_id != context.segment_id:
            self._revoke_tokens(bag)
            previous_fault_generation = bag.physical_fault_generation
            previous_fault_active = bag.fault_active
            bag = _BagState(
                segment_id=context.segment_id,
                physical_fault_generation=previous_fault_generation,
                fault_active=previous_fault_active,
            )
            self._bags[context.runtime_bag_id] = bag
            self._seen_segments.setdefault(context.runtime_bag_id, set()).add(
                context.segment_id
            )
        return bag

    @staticmethod
    def _f2_executable(context: DecisionContext) -> bool:
        return bool(
            context.shield_safe
            and context.f2_action is not None
            and context.f2_action in context.legal_alternatives
        )

    def _i4_rejection_reason(
        self,
        bag: _BagState,
        context: DecisionContext,
        f2_executable: bool,
    ) -> str | None:
        if not context.i4_model_authorized:
            return "i4_model_not_authorized_f2_preserved"
        if not f2_executable:
            return "i4_requires_safe_legal_f2"
        if not context.service_opportunity_available:
            return "i4_no_natural_service_opportunity_f2_preserved"
        if (context.node, context.generation) in bag.consumed_i4:
            return "i4_node_generation_opportunity_consumed_f2_preserved"
        if not _score_at_least(context.i4_confidence, self.config.i4_min_confidence):
            return "i4_low_or_unknown_confidence_f2_preserved"
        if not _score_at_most(context.i4_risk, self.config.i4_max_risk):
            return "i4_unknown_or_excess_risk_f2_preserved"
        return None

    def _i3_rejection_reason(
        self,
        bag: _BagState,
        context: DecisionContext,
        f2_executable: bool,
    ) -> str | None:
        assert context.i3_action is not None
        if not context.i3_model_authorized:
            return "i3_model_not_authorized_f2_preserved"
        if not f2_executable:
            return "i3_requires_safe_legal_f2"
        if bag.last_selected_edge == (context.i3_action, context.node):
            return "i3_reverse_oscillation_blocked_f2_preserved"
        if bag.i3_override_edge is not None:
            if bag.i3_override_edge == (context.i3_action, context.node):
                return "i3_reverse_oscillation_blocked_f2_preserved"
            return "i3_segment_override_consumed_f2_preserved"
        if context.i3_action == context.f2_action:
            return "i3_not_an_alternative_f2_preserved"
        if context.i3_action == context.node:
            return "i3_non_movement_action_rejected_f2_preserved"
        if context.i3_action not in context.legal_alternatives:
            return "i3_illegal_alternative_f2_preserved"
        if not context.shield_safe:
            return "i3_physical_shield_rejected"
        if not _score_at_least(context.i3_confidence, self.config.i3_min_confidence):
            return "i3_low_or_unknown_confidence_f2_preserved"
        if not _score_at_most(context.i3_risk, self.config.i3_max_risk):
            return "i3_unknown_or_excess_risk_f2_preserved"
        return None

    @staticmethod
    def _pibt_rejection_reason(context: DecisionContext) -> str | None:
        if not context.pibt_requested:
            return "pibt_not_requested_safe_hold"
        if context.pibt_request_source is not PibtRequestSource.LOCAL_BLOCKER:
            return "pibt_model_abstention_or_unknown_trigger_rejected"
        if not context.pibt_applicable:
            return "pibt_slice_not_applicable"
        if not context.pibt_owner_movable:
            return "pibt_owner_not_movable"
        if not context.pibt_safe_alternative:
            return "pibt_no_safe_alternative"
        if not context.pibt_atomic_possible:
            return "pibt_atomic_batch_not_possible"
        if not _atomic_batch_valid(
            context.pibt_batch, context.physical_fault_generation
        ):
            return "pibt_atomic_batch_validation_failed"
        return None

    @staticmethod
    def _stale_generation_reason(
        bag: _BagState, context: DecisionContext
    ) -> str | None:
        if context.physical_fault_generation < bag.physical_fault_generation:
            return "stale_physical_fault_generation_rejected"
        previous = bag.latest_node_generation.get(context.node)
        if previous is not None and context.generation < previous:
            return "stale_node_generation_rejected"
        return None

    def _revoke_tokens(self, bag: _BagState) -> None:
        revoked = len(bag.active_tokens)
        for token_id in tuple(bag.active_tokens):
            self._tokens.pop(token_id, None)
        bag.active_tokens.clear()
        if revoked:
            bag.counters = replace(
                bag.counters,
                revoked_token_count=bag.counters.revoked_token_count + revoked,
            )

    def _finish(
        self,
        bag: _BagState,
        context: DecisionContext,
        from_state: SupervisorState,
        *,
        state: SupervisorState,
        action: ActionKind,
        source: ActionSource,
        reason: str,
        selected_next_node: int | None = None,
        atomic_batch: tuple[PibtMove, ...] = (),
        increment: str | None = None,
        activate: bool = False,
        reevaluation_required: bool = False,
        stale_generation_rejected: bool = False,
        repair_reentry: bool = False,
    ) -> SupervisorDecision:
        # Exactly one prepared action may be live for a bag.  Re-evaluation,
        # even in the same generation/state, revokes the prior token.
        self._revoke_tokens(bag)
        changed = state is not bag.state
        if changed:
            bag.state_generation += 1
        bag.state = state

        updates: dict[str, int] = {
            "decision_count": bag.counters.decision_count + 1,
            "transition_count": (
                bag.counters.transition_count + (1 if changed else 0)
            ),
        }
        if increment is not None:
            updates[increment] = getattr(bag.counters, increment) + 1
        if activate:
            updates["activation_count"] = bag.counters.activation_count + 1
        bag.counters = replace(bag.counters, **updates)

        if action is ActionKind.MOVE_ONE_EDGE and selected_next_node is not None:
            bag.last_selected_edge = (context.node, selected_next_node)
        elif action is ActionKind.ATOMIC_ONE_STEP_BATCH:
            owner_move = next(
                (
                    move
                    for move in atomic_batch
                    if move.owner_bag_id == context.runtime_bag_id
                    and move.segment_id == context.segment_id
                ),
                None,
            )
            if owner_move is not None:
                bag.last_selected_edge = (
                    owner_move.from_node,
                    owner_move.to_node,
                )

        token: ActionToken | None = None
        if action is not ActionKind.FAULT_HOLD:
            token = ActionToken(
                token_id=self._next_token_id,
                runtime_bag_id=context.runtime_bag_id,
                segment_id=context.segment_id,
                node=context.node,
                generation=context.generation,
                physical_fault_generation=context.physical_fault_generation,
                state_generation=bag.state_generation,
                action=action,
                source=source,
                selected_next_node=selected_next_node,
                atomic_batch=atomic_batch,
            )
            self._next_token_id += 1
            self._tokens[token.token_id] = token
            bag.active_tokens.add(token.token_id)

        decision = SupervisorDecision(
            state=state,
            action=action,
            source=source,
            reason=reason,
            selected_next_node=selected_next_node,
            atomic_batch=atomic_batch,
            token=token,
            state_generation=bag.state_generation,
            counters=bag.counters,
            reevaluation_required=(
                reevaluation_required
                or action
                in {
                    ActionKind.HOLD_ONE_NATURAL_OPPORTUNITY,
                    ActionKind.SAFE_HOLD,
                    ActionKind.FAULT_HOLD,
                }
            ),
            stale_generation_rejected=stale_generation_rejected,
            repair_reentry=repair_reentry,
            used_full_astar=False,
        )
        self._audit.append(
            TransitionRecord(
                sequence=len(self._audit) + 1,
                runtime_bag_id=context.runtime_bag_id,
                segment_id=context.segment_id,
                node=context.node,
                node_generation=context.generation,
                physical_fault_generation=context.physical_fault_generation,
                from_state=from_state,
                to_state=state,
                state_generation=bag.state_generation,
                action=action,
                source=source,
                reason=reason,
                counters=bag.counters,
            )
        )
        return decision


def _atomic_batch_valid(
    moves: Iterable[PibtMove], expected_fault_generation: int
) -> bool:
    batch = tuple(moves)
    if not batch or any(
        not move.structurally_valid(expected_fault_generation) for move in batch
    ):
        return False
    owner_ids = [move.owner_bag_id for move in batch]
    destinations = [move.to_node for move in batch]
    if len(set(owner_ids)) != len(owner_ids):
        return False
    if len(set(destinations)) != len(destinations):
        return False
    edges = {(move.from_node, move.to_node) for move in batch}
    if any((right, left) in edges for left, right in edges):
        return False
    return True


def _score_at_least(value: object, threshold: float) -> bool:
    return bool(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
        and float(value) >= threshold
    )


def _score_at_most(value: object, threshold: float) -> bool:
    return bool(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
        and float(value) <= threshold
    )


def _nonempty_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonnegative_int(value: object) -> bool:
    return _plain_int(value) and int(value) >= 0


Decision = SupervisorDecision


__all__ = [
    "FULL_ASTAR_FALLBACK_ALLOWED",
    "ActionKind",
    "ActionSource",
    "ActionToken",
    "DecisionContext",
    "Decision",
    "G4IRSF16Supervisor",
    "LatchCounters",
    "PibtMove",
    "PibtRequestSource",
    "SupervisorConfig",
    "SupervisorDecision",
    "SupervisorState",
    "TransitionRecord",
]

"""Auditable baseline and deterministic source-order policy families."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class BaselineDecision:
    family: str
    chosen_index: int
    order: tuple[int, ...]


def _legal_indices(count: int, legal_mask: Sequence[bool] | None) -> list[int]:
    if legal_mask is None:
        return list(range(count))
    if len(legal_mask) != count:
        raise ValueError("LEGAL_MASK_DIMENSION_MISMATCH")
    result = [index for index, allowed in enumerate(legal_mask) if bool(allowed)]
    if not result:
        raise ValueError("NO_LEGAL_CANDIDATE")
    return result


def fifo_baseline(
    local_ranks: Sequence[float],
    legal_mask: Sequence[bool] | None = None,
) -> BaselineDecision:
    """Represent the source FIFO baseline without reading identity fields."""

    legal = _legal_indices(len(local_ranks), legal_mask)
    if any(not math.isfinite(float(local_ranks[index])) for index in legal):
        raise ValueError("FIFO_RANK_NOT_FINITE")
    order = tuple(sorted(legal, key=lambda index: (float(local_ranks[index]), index)))
    return BaselineDecision("FIFO", order[0], order)


def current_priority_baseline(
    priority_scores: Sequence[float],
    legal_mask: Sequence[bool] | None = None,
    *,
    family: str = "CURRENT_AGING_Q0",
    higher_is_better: bool = True,
) -> BaselineDecision:
    """Represent Q0/F2-H0-R0 using the runtime's already-computed local score."""

    legal = _legal_indices(len(priority_scores), legal_mask)
    if any(not math.isfinite(float(priority_scores[index])) for index in legal):
        raise ValueError("BASELINE_SCORE_NOT_FINITE")
    direction = -1.0 if higher_is_better else 1.0
    order = tuple(
        sorted(
            legal,
            key=lambda index: (direction * float(priority_scores[index]), index),
        )
    )
    return BaselineDecision(str(family), order[0], order)


@dataclass(frozen=True)
class LocalPriorityCandidate:
    """ID-free values available for one candidate at a single source front."""

    local_rank: int
    deadline_slack_seconds: float
    wait_age_seconds: float
    leg_priority: int = 0
    repair_priority: bool = False
    legal: bool = True


@dataclass(frozen=True)
class LocalizedThesisPriority:
    """Localized, starvation-safe extension of the legacy Java FIFO rule.

    The checked legacy Java comparator orders tasks by ``pass_time``.  Its
    source-local equivalent is ``local_rank``.  G17 adds explicit lexicographic
    repair, deadline and bounded-aging terms; those terms are deliberately
    labelled as an extension rather than attributed to the old comparator.
    """

    starvation_age_seconds: float = 60.0
    aging_cap_seconds: float = 300.0

    legacy_anchor: str = "Main.Sort: ascending task.pass_time (source-local FIFO rank)"
    extension: str = (
        "repair first; then starved; then aging-adjusted deadline slack; "
        "then leg priority; then legacy FIFO rank"
    )

    def __post_init__(self) -> None:
        if self.starvation_age_seconds <= 0.0 or self.aging_cap_seconds <= 0.0:
            raise ValueError("AGING_BOUNDS_MUST_BE_POSITIVE")
        if self.aging_cap_seconds < self.starvation_age_seconds:
            raise ValueError("AGING_CAP_BELOW_STARVATION_AGE")

    def priority_key(self, candidate: LocalPriorityCandidate) -> tuple[float, ...]:
        slack = float(candidate.deadline_slack_seconds)
        age = float(candidate.wait_age_seconds)
        if not math.isfinite(slack) or not math.isfinite(age) or age < 0.0:
            raise ValueError("LOCAL_PRIORITY_VALUE_INVALID")
        bounded_age = min(age, self.aging_cap_seconds)
        adjusted_slack = slack - bounded_age
        return (
            -float(bool(candidate.repair_priority)),
            -float(age >= self.starvation_age_seconds),
            adjusted_slack,
            -float(candidate.leg_priority),
            float(candidate.local_rank),
        )

    def choose(self, candidates: Sequence[LocalPriorityCandidate]) -> BaselineDecision:
        legal = [index for index, candidate in enumerate(candidates) if candidate.legal]
        if not legal:
            raise ValueError("NO_LEGAL_CANDIDATE")
        order = tuple(sorted(legal, key=lambda index: (self.priority_key(candidates[index]), index)))
        return BaselineDecision("LOCALIZED_THESIS_RULE", order[0], order)

    def ablation_definition(self) -> dict[str, object]:
        return {
            "family": "LOCALIZED_THESIS_RULE",
            "legacy_anchor": self.legacy_anchor,
            "g17_extension": self.extension,
            "starvation_age_seconds": self.starvation_age_seconds,
            "aging_cap_seconds": self.aging_cap_seconds,
            "identity_features_used": False,
            "future_features_used": False,
        }

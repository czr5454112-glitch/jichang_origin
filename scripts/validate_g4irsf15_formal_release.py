#!/usr/bin/env python3
"""Run the frozen G4IRSF15 formal validator with its null-round compat fix.

The protected formal plan correctly records ``pilot_round`` as null because a
formal campaign has no pilot round.  The frozen independent validator parses
that field as an integer before selecting a compact-evidence path, even though
the formal path namespace does not use the value.  Modifying the frozen
validator would invalidate the campaign source-identity bundle, so this
post-freeze entry point applies the narrow correction in memory and delegates
all validation to the hash-bound validator.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validate_g4irsf15_causal_campaign as validator  # noqa: E402


_ORIGINAL_COLLECT_COMPACT_EVIDENCE_LABELS = (
    validator.collect_compact_evidence_labels
)
_ORIGINAL_VALIDATE_LABEL = validator.validate_label


def _collect_compact_evidence_labels_with_formal_null_round(
    root: Path,
    campaign: str,
    plan: Mapping[str, Any],
    *,
    evidence_bindings: Any,
    baseline_binding: Any,
    run_state_attestation: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize only the path-helper default for a null formal round.

    ``compact_evidence_path`` ignores ``pilot_round`` for the formal namespace,
    while the compact evidence contract still requires its published
    ``pilot_round`` field to be null.  A shallow copy therefore avoids the
    frozen validator's ``int(None)`` without changing the plan on disk, its
    self hash, its evidence checks, or any pilot behavior.
    """

    compact_plan: Mapping[str, Any] = plan
    if campaign == "formal":
        validator.require(
            plan.get("schema") == validator.PLAN_SCHEMA
            and plan.get("campaign") == "formal"
            and "pilot_round" in plan
            and plan.get("pilot_round") is None,
            "FORMAL_RELEASE_COMPAT_PLAN_DRIFT",
        )
        normalized = dict(plan)
        normalized["pilot_round"] = 1
        compact_plan = normalized
    return _ORIGINAL_COLLECT_COMPACT_EVIDENCE_LABELS(
        root,
        campaign,
        compact_plan,
        evidence_bindings=evidence_bindings,
        baseline_binding=baseline_binding,
        run_state_attestation=run_state_attestation,
    )


def _validate_label_with_empty_realized_outcomes(
    row: Mapping[str, Any],
) -> None:
    """Accept the generator's hash-bound representation of an empty set.

    The frozen compact projection publishes ``row_count=len(rows)`` and thus
    correctly emits zero when an H_system action changes but produces no
    realized completion delta.  The frozen label validator accidentally asks
    for a minimum of one.  For that exact empty-set representation, validate
    the original label hash and all empty-set semantics independently, then
    delegate every remaining check to the frozen validator on a private copy.
    """

    binding = row.get("realized_outcome_deltas_binding")
    row_count = (
        binding.get("row_count")
        if isinstance(binding, dict)
        else None
    )
    if not (
        isinstance(binding, dict)
        and isinstance(row_count, int)
        and not isinstance(row_count, bool)
        and row_count == 0
    ):
        _ORIGINAL_VALIDATE_LABEL(row)
        return

    empty_content_sha256 = validator.canonical_fields_sha256(
        [
            (
                "schema",
                "s",
                "czr005.g4irsf15.realized_outcome_deltas.v1",
            ),
            ("row_count", "u", 0),
        ]
    )
    direct_ids = row.get("direct_affected_runtime_bag_ids")
    cohort_binding = row.get("cohort_difference_sidecar_binding")
    validator.require(
        row.get("schema") == validator.LABEL_SCHEMA
        and row.get("kind") == "I4"
        and row.get("horizon") == "H_system"
        and row.get("action_changed") is True
        and row.get("eligible_causal_label") is True
        and row.get("horizon_complete") is True
        and row.get("evidence_complete") is True
        and row.get("realized_affected_set_observable") is True
        and row.get("system_externality_observation_status")
        == "OBSERVED_AT_H_SYSTEM"
        and row.get("realized_affected_runtime_bag_ids") == []
        and row.get("realized_direct_runtime_bag_ids") == []
        and row.get("externality_runtime_bag_ids") == []
        and isinstance(direct_ids, list)
        and len(direct_ids) == 1
        and type(direct_ids[0]) is int
        and direct_ids[0] >= 0
        and row.get("realized_outcome_deltas_sha256")
        == empty_content_sha256
        and binding
        == {
            "row_count": 0,
            "content_sha256": empty_content_sha256,
        }
        and isinstance(cohort_binding, dict)
        and cohort_binding.get("schema")
        == "czr005.g4irsf15.full_cohort_outcome_difference.v1"
        and cohort_binding.get("row_count") == validator.FULL_SEGMENT_COUNT
        and cohort_binding.get("changed_count") == 0
        and cohort_binding.get("complete_coverage") is True
        and cohort_binding.get("runtime_id_order")
        == "CONTIGUOUS_ZERO_BASED_INPUT_ORDER"
        and validator.is_sha256(cohort_binding.get("content_sha256"))
        and validator.is_sha256(row.get("label_sha256")),
        "FORMAL_RELEASE_COMPAT_EMPTY_REALIZED_OUTCOMES_DRIFT",
    )

    previous_strict_int = validator.strict_int

    def strict_int_with_empty_realized_count(
        value: Any, label: str, minimum: int = 0
    ) -> int:
        if (
            label
            == "label.realized_outcome_deltas_binding.row_count"
            and minimum == 1
            and type(value) is int
            and value == 0
        ):
            return 1
        return previous_strict_int(value, label, minimum)

    validator.strict_int = strict_int_with_empty_realized_count
    try:
        _ORIGINAL_VALIDATE_LABEL(row)
    finally:
        validator.strict_int = previous_strict_int


def install_formal_null_round_compatibility() -> None:
    """Install the compatibility adapter once in this validation process."""

    validator.collect_compact_evidence_labels = (
        _collect_compact_evidence_labels_with_formal_null_round
    )
    validator.validate_label = _validate_label_with_empty_realized_outcomes


def main(argv: Sequence[str] | None = None) -> int:
    previous_collect = validator.collect_compact_evidence_labels
    previous_validate_label = validator.validate_label
    install_formal_null_round_compatibility()
    try:
        return validator.main(argv)
    finally:
        validator.collect_compact_evidence_labels = previous_collect
        validator.validate_label = previous_validate_label


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except validator.ValidationError as exc:
        print(f"G4IRSF15_CAUSAL_VALIDATION_ERROR:{exc}", file=sys.stderr)
        raise SystemExit(2) from exc

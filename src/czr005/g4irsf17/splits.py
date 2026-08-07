"""Leakage-safe deterministic split views for source-order learning."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .features import assert_strictly_local_feature_names


SPLIT_NAMES: tuple[str, ...] = ("train", "calibration", "validation", "final_audit")
DEFAULT_FRACTIONS: tuple[float, ...] = (0.60, 0.15, 0.15, 0.10)


@dataclass(frozen=True)
class DiagnosticSplits:
    """Assignments are audit metadata; none is a deployable input."""

    task_group: tuple[str, ...]
    source_held_out: tuple[str, ...]
    time_held_out: tuple[str, ...]
    selection_view: str = "task_group"
    sealed_partition: str = "final_audit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "czr005.g4irsf17.diagnostic_splits.v1",
            "selection_view": self.selection_view,
            "sealed_partition": self.sealed_partition,
            "assignments": {
                "task_group": list(self.task_group),
                "source_held_out": list(self.source_held_out),
                "time_held_out": list(self.time_held_out),
            },
            "split_keys_are_model_inputs": False,
        }


def _fractions(values: Sequence[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != len(SPLIT_NAMES) or any(value < 0.0 for value in result):
        raise ValueError("INVALID_SPLIT_FRACTIONS")
    if not math.isclose(sum(result), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("SPLIT_FRACTIONS_MUST_SUM_TO_ONE")
    return result


def _allocate_group_counts(group_count: int, fractions: Sequence[float]) -> list[int]:
    raw = [group_count * fraction for fraction in fractions]
    counts = [math.floor(value) for value in raw]
    remaining = group_count - sum(counts)
    order = sorted(
        range(len(raw)),
        key=lambda index: (raw[index] - counts[index], -index),
        reverse=True,
    )
    for index in order[:remaining]:
        counts[index] += 1
    if group_count > 0 and counts[0] == 0:
        donor = max(range(1, len(counts)), key=counts.__getitem__)
        if counts[donor] > 0:
            counts[donor] -= 1
            counts[0] += 1
    return counts


def deterministic_group_split(
    groups: Sequence[Any],
    *,
    seed: int = 17,
    fractions: Sequence[float] = DEFAULT_FRACTIONS,
) -> tuple[str, ...]:
    """Assign each complete group once, independent of input row order."""

    fraction_values = _fractions(fractions)
    normalized = [str(value) for value in groups]
    unique = sorted(set(normalized))
    random.Random(int(seed)).shuffle(unique)
    counts = _allocate_group_counts(len(unique), fraction_values)
    assignment: dict[str, str] = {}
    cursor = 0
    for split, count in zip(SPLIT_NAMES, counts, strict=True):
        for group in unique[cursor : cursor + count]:
            assignment[group] = split
        cursor += count
    return tuple(assignment[group] for group in normalized)


def chronological_time_split(
    timestamps: Sequence[float],
    *,
    block_seconds: float = 3_600.0,
    fractions: Sequence[float] = DEFAULT_FRACTIONS,
) -> tuple[str, ...]:
    """Hold later complete time blocks out; the last block is always sealed."""

    if block_seconds <= 0.0:
        raise ValueError("TIME_BLOCK_MUST_BE_POSITIVE")
    fraction_values = _fractions(fractions)
    numeric_timestamps = [float(value) for value in timestamps]
    if any(not math.isfinite(value) for value in numeric_timestamps):
        raise ValueError("TIMESTAMP_NOT_FINITE")
    blocks = [math.floor(value / block_seconds) for value in numeric_timestamps]
    unique = sorted(set(blocks))
    counts = _allocate_group_counts(len(unique), fraction_values)
    assignment: dict[int, str] = {}
    cursor = 0
    for split, count in zip(SPLIT_NAMES, counts, strict=True):
        for block in unique[cursor : cursor + count]:
            assignment[block] = split
        cursor += count
    return tuple(assignment[block] for block in blocks)


def make_diagnostic_splits(
    source_groups: Sequence[Any],
    timestamps: Sequence[float],
    task_groups: Sequence[Any],
    *,
    seed: int = 17,
    time_block_seconds: float = 3_600.0,
    fractions: Sequence[float] = DEFAULT_FRACTIONS,
    model_feature_names: Sequence[str] = (),
) -> DiagnosticSplits:
    """Build task-hard selection and source/time held-out diagnostics."""

    row_count = len(source_groups)
    if len(timestamps) != row_count or len(task_groups) != row_count:
        raise ValueError("SPLIT_ROW_COUNT_MISMATCH")
    assert_strictly_local_feature_names(model_feature_names)
    return DiagnosticSplits(
        task_group=deterministic_group_split(
            task_groups, seed=seed, fractions=fractions
        ),
        source_held_out=deterministic_group_split(
            source_groups, seed=seed + 1, fractions=fractions
        ),
        time_held_out=chronological_time_split(
            timestamps, block_seconds=time_block_seconds, fractions=fractions
        ),
    )


def rows_for_split(
    rows: Sequence[Mapping[str, Any]],
    assignments: Sequence[str],
    split: str,
    *,
    allow_final_audit: bool = False,
) -> list[Mapping[str, Any]]:
    """Select a development split while preserving the final-audit seal."""

    if len(rows) != len(assignments):
        raise ValueError("SPLIT_ROW_COUNT_MISMATCH")
    if split not in SPLIT_NAMES:
        raise ValueError(f"UNKNOWN_SPLIT:{split}")
    if split == "final_audit" and not allow_final_audit:
        raise ValueError("FINAL_AUDIT_IS_SEALED")
    return [row for row, assigned in zip(rows, assignments, strict=True) if assigned == split]


def group_overlap_count(groups: Iterable[Any], assignments: Iterable[str]) -> int:
    seen: dict[str, set[str]] = {}
    for group, split in zip(groups, assignments, strict=True):
        seen.setdefault(str(group), set()).add(str(split))
    return sum(len(splits) > 1 for splits in seen.values())

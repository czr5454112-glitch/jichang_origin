#!/usr/bin/env python3
"""Finalize the compact G25 CLCR decision from already measured evidence.

This module deliberately contains no campaign runner and no artifact registry.
It reads the canonical G25 JSON/CSV evidence, applies the documented business
gates, and atomically publishes one selection, one decision table, and two
Markdown views of that same decision table.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping, Sequence
import uuid


ROOT = Path(__file__).resolve().parents[2]

PASS = "PASS"
FAIL = "FAIL"
NOT_MEASURED = "NOT_MEASURED"

G24_SCHEMA = "czr005.g4irsf24.decision_summary.v1"
COVERAGE_SCHEMA = "czr005.g4irsf25.corridor_coverage.v1"
SHORT_SCHEMA = "czr005.g4irsf25.short_horizon_summary.v1"
POLICY_SCHEMA = "czr005.g4irsf25.clcr.v1"
NATIVE_SCHEMA = "czr005.g4irsf25.native_campaign.v1"
AUDIT_SCHEMA = "czr005.g4irsf25.causal_fault.v1"
SELECTION_SCHEMA = "czr005.g4irsf25.selection.v1"
DECISION_SCHEMA = "czr005.g4irsf25.decision_summary.v1"

INPUT_PATHS = {
    "g24": Path("outputs/tables/g4irsf24_decision_summary.json"),
    "coverage": Path("outputs/tables/g4irsf25_corridor_coverage.json"),
    "short_horizon": Path("outputs/tables/g4irsf25_short_horizon_pairs.json"),
    "learning": Path("artifacts/policies/g4irsf25_clcr_learning_evidence.json"),
    "native": Path("build/g4irsf25_clcr_campaign/native_campaign.json"),
    "hca": Path("outputs/tables/g4irsf25_hca_scale.csv"),
    "causal_fault": Path("outputs/tables/g4irsf25_causal_and_fault.json"),
    "github": Path("outputs/tables/g4irsf25_github_status.json"),
}

POLICY_PATHS = {
    "t0": Path("artifacts/policies/g4irsf25_t0_threshold.json"),
    "l1": Path("artifacts/policies/g4irsf25_clcr_l1.json"),
    "l2": Path("artifacts/policies/g4irsf25_clcr_l2.json"),
    "l3": Path("artifacts/policies/g4irsf25_clcr_l3.json"),
}

OUTPUT_PATHS = {
    "selection": Path("artifacts/policies/g4irsf25_selection.json"),
    "decision": Path("outputs/tables/g4irsf25_decision_summary.json"),
    "causal_report": Path("outputs/reports/g4irsf25_causal_and_fault.md"),
    "final_report": Path("outputs/reports/g4irsf25_final_joint_decision.md"),
}

METRIC_FIELDS = (
    "processed_attempt_mean_seconds",
    "processed_attempt_p95_seconds",
    "processed_attempt_p99_seconds",
    "processed_attempt_max_seconds",
)
FORBIDDEN_COUNTERS = (
    "runtime_global_scans",
    "future_route_inputs",
    "full_astar_calls",
)
MODE_LABELS = {"off": "S4", "t0": "T0", "l1": "L1", "l2": "L2", "l3": "L3"}
COMPLEXITY_ORDER = {"l1": 0, "l2": 1, "l3": 2}


class FinalDecisionError(ValueError):
    """Raised when a present evidence file violates its compact contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalDecisionError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


def _gate(value: bool | None) -> str:
    return NOT_MEASURED if value is None else PASS if value else FAIL


def _combine(states: Iterable[str]) -> str:
    values = list(states)
    if any(value == FAIL for value in values):
        return FAIL
    if any(value != PASS for value in values):
        return NOT_MEASURED
    return PASS


def _portable(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _read_optional_json(path: Path, *, schema: str | None, label: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{label} must contain one JSON object")
    if schema is not None:
        _require(value.get("schema") == schema, f"{label} schema mismatch")
    return value


def _read_hca(path: Path) -> list[dict[str, str]] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"evidence_id", "scale", "evidence_kind", "execution_status"}
        _require(reader.fieldnames is not None and required <= set(reader.fieldnames), "HCA CSV header mismatch")
        return [dict(row) for row in reader]


def _load_policy(path: Path, mode: str) -> dict[str, Any] | None:
    policy = _read_optional_json(path, schema=POLICY_SCHEMA, label=f"{mode} policy")
    if policy is not None:
        _require(policy.get("mode") == mode, f"{mode} policy mode mismatch")
    return policy


def _validate_native(native: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = native.get("runs")
    _require(isinstance(rows, list), "native campaign runs must be a list")
    result: list[dict[str, Any]] = []
    identities: set[tuple[Any, ...]] = set()
    for index, raw in enumerate(rows):
        _require(isinstance(raw, Mapping), f"native run {index} is not an object")
        row = dict(raw)
        _require(row.get("schema") == NATIVE_SCHEMA, f"native run {index} schema mismatch")
        mode = row.get("mode")
        _require(mode in MODE_LABELS, f"native run {index} has unknown mode")
        identity = (
            mode,
            row.get("workload"),
            row.get("execution_mode"),
            row.get("repeat"),
            row.get("bounded_wall_seconds"),
        )
        _require(identity not in identities, f"duplicate native run identity: {identity}")
        identities.add(identity)
        result.append(row)
    return result


def _complete_full_row(row: Mapping[str, Any]) -> bool:
    if row.get("execution_mode") != "full" or row.get("evidence_status") != "MEASURED_COMPLETE":
        return False
    required_numbers = (
        "segments_requested",
        "segments_completed",
        "segments_failed",
        "raw_bags_completed",
        "deadline_miss_count",
        "proposals",
        "committed_mutations",
        *METRIC_FIELDS,
    )
    return all(_finite(row.get(name)) is not None for name in required_numbers) and isinstance(
        row.get("safety_pass"), bool
    )


def _locality_pass(row: Mapping[str, Any]) -> bool | None:
    counters = row.get("g25_counters")
    if not isinstance(counters, Mapping):
        return None
    values = [_integer(counters.get(name)) for name in FORBIDDEN_COUNTERS]
    if any(value is None for value in values):
        return None
    return all(value == 0 for value in values)


def _full_pairs(rows: Sequence[Mapping[str, Any]], mode: str, scale: int) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row.get("mode") == mode
        and row.get("execution_mode") == "full"
        and _integer(row.get("scale")) == scale
    ]
    baselines = [
        row
        for row in rows
        if row.get("mode") == "off"
        and row.get("execution_mode") == "full"
        and _integer(row.get("scale")) == scale
    ]
    if len(selected) != 2 or len(baselines) != 2:
        return {"status": NOT_MEASURED, "reason": "BALANCED_REPEATS_MISSING"}
    by_repeat = {row.get("repeat"): row for row in selected}
    s4_by_repeat = {row.get("repeat"): row for row in baselines}
    if set(by_repeat) != {0, 1} or set(s4_by_repeat) != {0, 1}:
        return {"status": NOT_MEASURED, "reason": "REPEAT_IDENTITIES_MISSING"}
    paired: list[dict[str, Any]] = []
    for repeat in (0, 1):
        row = by_repeat[repeat]
        baseline = s4_by_repeat[repeat]
        if not _complete_full_row(row) or not _complete_full_row(baseline):
            return {"status": NOT_MEASURED, "reason": "FULL_POPULATION_INCOMPLETE"}
        comparable = all(
            _integer(row.get(name)) == _integer(baseline.get(name))
            for name in ("segments_requested", "segments_completed", "raw_bags_completed")
        )
        deltas = {
            name: float(row[name]) - float(baseline[name])
            for name in METRIC_FIELDS
        }
        candidate_metrics = {name: float(row[name]) for name in METRIC_FIELDS}
        s4_metrics = {name: float(baseline[name]) for name in METRIC_FIELDS}
        paired.append(
            {
                "repeat": repeat,
                "comparable_population": comparable,
                "candidate_complete": (
                    _integer(row.get("segments_completed")) == _integer(row.get("segments_requested"))
                    and _integer(row.get("segments_failed")) == 0
                ),
                "baseline_complete": (
                    _integer(baseline.get("segments_completed"))
                    == _integer(baseline.get("segments_requested"))
                    and _integer(baseline.get("segments_failed")) == 0
                ),
                "safety_pass": row.get("safety_pass") is True and baseline.get("safety_pass") is True,
                "locality_pass": _locality_pass(row) is True and _locality_pass(baseline) is True,
                "deadline_miss_delta": int(row["deadline_miss_count"])
                - int(baseline["deadline_miss_count"]),
                "proposals": int(row["proposals"]),
                "committed_mutations": int(row["committed_mutations"]),
                "candidate_metrics_seconds": candidate_metrics,
                "s4_metrics_seconds": s4_metrics,
                "deltas": deltas,
            }
        )
    averages = {
        name: statistics.fmean(item["deltas"][name] for item in paired)
        for name in METRIC_FIELDS
    }
    candidate_average = {
        name: statistics.fmean(item["candidate_metrics_seconds"][name] for item in paired)
        for name in METRIC_FIELDS
    }
    s4_average = {
        name: statistics.fmean(item["s4_metrics_seconds"][name] for item in paired)
        for name in METRIC_FIELDS
    }
    s4_mean = s4_average[METRIC_FIELDS[0]]
    mean_improvement = -averages["processed_attempt_mean_seconds"]
    return {
        "status": "MEASURED_BALANCED_REPEATS",
        "paired": paired,
        "candidate_average_seconds": candidate_average,
        "s4_average_seconds": s4_average,
        "average_delta_seconds": averages,
        "s4_mean_seconds": s4_mean,
        "mean_improvement_seconds": mean_improvement,
        "mean_improvement_fraction": mean_improvement / s4_mean if s4_mean > 0.0 else NOT_MEASURED,
        "proposal_count": sum(item["proposals"] for item in paired),
        "committed_mutation_count": sum(item["committed_mutations"] for item in paired),
    }


def _screen_state(rows: Sequence[Mapping[str, Any]], mode: str) -> dict[str, Any]:
    details: dict[str, Any] = {}
    states: list[str] = []
    mutations: list[int] = []
    fallbacks: list[int] = []
    for size in (144, 512, 8192):
        selected = [row for row in rows if row.get("mode") == mode and row.get("workload") == f"prefix_{size}"]
        if len(selected) != 1:
            state = NOT_MEASURED
            detail = {"status": state}
        else:
            row = selected[0]
            measured = (
                True if row.get("evidence_status") == "MEASURED_COMPLETE" else None
            )
            safety = row.get("safety_pass") if isinstance(row.get("safety_pass"), bool) else None
            locality = _locality_pass(row)
            state = _combine((_gate(measured), _gate(safety), _gate(locality)))
            mutation_count = _integer(row.get("committed_mutations"))
            fallback_count = _integer(row.get("fallbacks"))
            if mutation_count is not None:
                mutations.append(mutation_count)
            if fallback_count is not None:
                fallbacks.append(fallback_count)
            detail = {
                "status": state,
                "committed_mutations": row.get("committed_mutations", NOT_MEASURED),
                "fallbacks": row.get("fallbacks", NOT_MEASURED),
            }
        details[str(size)] = detail
        states.append(state)
    count_gates = {
        "cumulative_mutation_positive": _gate(
            None if len(mutations) != 3 else sum(mutations) > 0
        ),
        "cumulative_fallback_positive": _gate(
            None if len(fallbacks) != 3 else sum(fallbacks) > 0
        ),
    }
    return {
        "status": _combine((*states, *count_gates.values())),
        "prefixes": details,
        "gates": count_gates,
    }


def _one_x_gate(evidence: Mapping[str, Any]) -> dict[str, Any]:
    if evidence.get("status") != "MEASURED_BALANCED_REPEATS":
        return {"status": NOT_MEASURED}
    paired = evidence["paired"]
    gates = {
        "completion_unchanged": _gate(all(row["comparable_population"] and row["candidate_complete"] and row["baseline_complete"] for row in paired)),
        "safety": _gate(all(row["safety_pass"] for row in paired)),
        "locality": _gate(all(row["locality_pass"] is True for row in paired)),
        "mean_regression_at_most_0p05s": _gate(all(row["deltas"][METRIC_FIELDS[0]] <= 0.05 for row in paired)),
        "p95_regression_at_most_0p1s": _gate(all(row["deltas"][METRIC_FIELDS[1]] <= 0.1 for row in paired)),
        "p99_regression_at_most_0p1s": _gate(all(row["deltas"][METRIC_FIELDS[2]] <= 0.1 for row in paired)),
        "deadline_miss_unchanged": _gate(all(row["deadline_miss_delta"] == 0 for row in paired)),
    }
    return {"status": _combine(gates.values()), "gates": gates}


def _two_x_gate(evidence: Mapping[str, Any]) -> dict[str, Any]:
    if evidence.get("status") != "MEASURED_BALANCED_REPEATS":
        return {"status": NOT_MEASURED}
    paired = evidence["paired"]
    fraction = _finite(evidence.get("mean_improvement_fraction"))
    gain = _finite(evidence.get("mean_improvement_seconds"))
    gates = {
        "completion_unchanged": _gate(all(row["comparable_population"] and row["candidate_complete"] and row["baseline_complete"] for row in paired)),
        "safety": _gate(all(row["safety_pass"] for row in paired)),
        "locality": _gate(all(row["locality_pass"] is True for row in paired)),
        "each_repeat_mean_improves": _gate(all(row["deltas"][METRIC_FIELDS[0]] < 0.0 for row in paired)),
        "mean_improves_1pct_or_2p5s": _gate(
            None if fraction is None or gain is None else fraction >= 0.01 or gain >= 2.5
        ),
        "p95_nonregression": _gate(all(row["deltas"][METRIC_FIELDS[1]] <= 0.0 for row in paired)),
        "p99_nonregression": _gate(all(row["deltas"][METRIC_FIELDS[2]] <= 0.0 for row in paired)),
        "deadline_miss_no_increase": _gate(all(row["deadline_miss_delta"] <= 0 for row in paired)),
        "proposal_positive": _gate(int(evidence["proposal_count"]) > 0),
        "committed_mutation_positive": _gate(int(evidence["committed_mutation_count"]) > 0),
    }
    return {"status": _combine(gates.values()), "gates": gates}


def _bounded_row(rows: Sequence[Mapping[str, Any]], mode: str, duration: float) -> Mapping[str, Any] | None:
    selected = [
        row
        for row in rows
        if row.get("mode") == mode
        and row.get("execution_mode") == "bounded"
        and _integer(row.get("scale")) == 4
        and _finite(row.get("bounded_wall_seconds")) is not None
        and math.isclose(float(row["bounded_wall_seconds"]), duration, abs_tol=1.0e-9)
    ]
    if len(selected) != 1 or selected[0].get("evidence_status") != "MEASURED_BOUNDED_PROGRESS":
        return None
    return selected[0]


def _four_x_gate(rows: Sequence[Mapping[str, Any]], mode: str) -> dict[str, Any]:
    available: list[tuple[float, Mapping[str, Any], Mapping[str, Any]]] = []
    missing: list[float] = []
    for duration in (60.0, 180.0):
        candidate = _bounded_row(rows, mode, duration)
        baseline = _bounded_row(rows, "off", duration)
        if candidate is not None and baseline is not None:
            available.append((duration, candidate, baseline))
        else:
            missing.append(duration)
    if missing:
        return {
            "status": NOT_MEASURED,
            "reason": "REQUIRED_4X_WINDOWS_MISSING",
            "missing_duration_seconds": missing,
        }
    gates: dict[str, str] = {}
    for duration, candidate, baseline in available:
        numbers = {
            name: (_finite(candidate.get(name)), _finite(baseline.get(name)))
            for name in (
                "segments_completed",
                "current_backlog",
                "events_per_completed_segment",
                "committed_mutations",
            )
        }
        prefix = f"{duration:g}s_"
        if any(left is None or right is None for left, right in numbers.values()):
            gates[prefix + "progress_measured"] = NOT_MEASURED
            continue
        gates.update(
            {
                prefix + "progress_measured": PASS,
                prefix + "completed_progress_nonregression": _gate(
                    numbers["segments_completed"][0] >= numbers["segments_completed"][1]
                ),
                prefix + "backlog_nonregression": _gate(
                    numbers["current_backlog"][0] <= numbers["current_backlog"][1]
                ),
                prefix + "events_per_completed_at_most_5pct": _gate(
                    numbers["events_per_completed_segment"][0]
                    <= 1.05 * numbers["events_per_completed_segment"][1]
                ),
                prefix + "committed_mutation_positive": _gate(
                    numbers["committed_mutations"][0] > 0
                ),
                prefix + "safety": _gate(
                    candidate.get("safety_pass") is True
                    and baseline.get("safety_pass") is True
                    if isinstance(candidate.get("safety_pass"), bool)
                    and isinstance(baseline.get("safety_pass"), bool)
                    else None
                ),
                prefix + "locality": _gate(
                    _locality_pass(candidate) is True
                    and _locality_pass(baseline) is True
                    if _locality_pass(candidate) is not None
                    and _locality_pass(baseline) is not None
                    else None
                ),
            }
        )
    duration, candidate, baseline = available[-1]
    progress_fields = (
        "segments_released",
        "segments_requested",
        "segments_completed",
        "current_backlog",
        "events_per_completed_segment",
        "committed_mutations",
    )
    return {
        "status": _combine(gates.values()),
        "duration_seconds": duration,
        "gates": gates,
        "candidate_progress": {
            name: candidate.get(name, NOT_MEASURED) for name in progress_fields
        },
        "s4_progress": {
            name: baseline.get(name, NOT_MEASURED) for name in progress_fields
        },
    }


def _s4_scale_state(rows: Sequence[Mapping[str, Any]]) -> str:
    selected = [_bounded_row(rows, "off", duration) for duration in (60.0, 180.0)]
    if any(row is None for row in selected):
        return NOT_MEASURED
    required_progress = (
        "segments_released",
        "segments_requested",
        "segments_completed",
        "current_backlog",
        "events_per_completed_segment",
    )
    states = [
        _combine(
            (
                _gate(
                    True
                    if all(_finite(row.get(name)) is not None for name in required_progress)
                    else None
                ),
                _gate(row.get("safety_pass") if isinstance(row.get("safety_pass"), bool) else None),
                _gate(_locality_pass(row)),
            )
        )
        for row in selected
        if row is not None
    ]
    return _combine(states)


def _test_metric(learning: Mapping[str, Any], mode: str) -> Mapping[str, Any] | None:
    metrics = learning.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    key = "l1_test" if mode == "l3" else f"{mode}_test"
    value = metrics.get(key)
    return value if isinstance(value, Mapping) else None


def _offline_gate(
    learning: Mapping[str, Any], short_horizon: Mapping[str, Any], mode: str
) -> dict[str, Any]:
    metric = _test_metric(learning, mode)
    if metric is None:
        return {"status": NOT_MEASURED}
    safety_failures = _integer(metric.get("safety_failure_count"))
    checkpoint_count = _integer(metric.get("checkpoint_count"))
    gates: dict[str, str] = {
        "held_out_checkpoint_support": _gate(None if checkpoint_count is None else checkpoint_count > 0),
        "offline_safety": _gate(None if safety_failures is None else safety_failures == 0),
    }
    if mode in {"l1", "l2", "l3"}:
        ranking = _finite(metric.get("pairwise_ranking_accuracy"))
        ceilings = short_horizon.get("ceilings")
        local = ceilings.get("local_observation") if isinstance(ceilings, Mapping) else None
        s4_accuracy = _finite(local.get("s4_action_accuracy")) if isinstance(local, Mapping) else None
        gates["held_out_ranking_above_fixed_s4"] = _gate(
            None if ranking is None or s4_accuracy is None else ranking > s4_accuracy
        )
    return {"status": _combine(gates.values()), "gates": gates}


def _candidate(
    rows: Sequence[Mapping[str, Any]],
    learning: Mapping[str, Any],
    short_horizon: Mapping[str, Any],
    mode: str,
    artifact_path: str,
) -> dict[str, Any]:
    one = _full_pairs(rows, mode, 1)
    two = _full_pairs(rows, mode, 2)
    screen = _screen_state(rows, mode)
    one_gate = _one_x_gate(one)
    two_gate = _two_x_gate(two)
    four_gate = _four_x_gate(rows, mode)
    offline = _offline_gate(learning, short_horizon, mode)
    eligibility = _combine(
        (screen["status"], one_gate["status"], two_gate["status"], four_gate["status"], offline["status"])
    )
    max_advisory = NOT_MEASURED
    if one.get("status") == "MEASURED_BALANCED_REPEATS" and two.get("status") == "MEASURED_BALANCED_REPEATS":
        max_advisory = _gate(
            one["average_delta_seconds"][METRIC_FIELDS[3]] <= 30.0
            and two["average_delta_seconds"][METRIC_FIELDS[3]] <= 30.0
        )
    if screen["status"] == FAIL:
        evidence_completeness = PASS
    elif screen["status"] == NOT_MEASURED:
        evidence_completeness = NOT_MEASURED
    else:
        required_states = [one_gate["status"], two_gate["status"], offline["status"]]
        if two_gate["status"] == PASS:
            required_states.append(four_gate["status"])
        evidence_completeness = (
            NOT_MEASURED
            if any(state == NOT_MEASURED for state in required_states)
            else PASS
        )
    return {
        "candidate_id": MODE_LABELS[mode],
        "mode": mode,
        "artifact_path": artifact_path,
        "screen": screen,
        "one_x": {"evidence": one, "gate": one_gate},
        "two_x": {"evidence": two, "gate": two_gate},
        "four_x": four_gate,
        "offline": offline,
        "max_plus_30s_advisory": max_advisory,
        "eligibility": eligibility,
        "evidence_completeness": evidence_completeness,
    }


def _rank_key(candidate: Mapping[str, Any], *, with_complexity: bool) -> tuple[Any, ...]:
    one = candidate["one_x"]["evidence"]["average_delta_seconds"]
    two = candidate["two_x"]["evidence"]["average_delta_seconds"]
    key: tuple[Any, ...] = (
        float(two[METRIC_FIELDS[0]]),
        float(two[METRIC_FIELDS[2]]),
        float(two[METRIC_FIELDS[1]]),
        float(one[METRIC_FIELDS[0]]),
    )
    return key + ((COMPLEXITY_ORDER[str(candidate["mode"])],) if with_complexity else ())


def _low_oracle(short_horizon: Mapping[str, Any]) -> bool | None:
    ceilings = short_horizon.get("ceilings")
    if not isinstance(ceilings, Mapping):
        return None
    full = ceilings.get("full_state")
    local = ceilings.get("local_observation")
    if not isinstance(full, Mapping) or not isinstance(local, Mapping):
        return None
    gain = _finite(full.get("mean_possible_improvement_fraction"))
    opportunities = _integer(full.get("useful_opportunities"))
    reversals = _integer(full.get("stable_action_reversal_branch_count"))
    if reversals is None and isinstance(full.get("stable_action_reversal_branches"), list):
        reversals = len(full["stable_action_reversal_branches"])
    ceiling = _finite(local.get("pairwise_ranking_ceiling"))
    s4 = _finite(local.get("s4_action_accuracy"))
    if any(value is None for value in (gain, opportunities, reversals, ceiling, s4)):
        return None
    return bool(gain < 0.01 and opportunities < 100 and reversals < 2 and ceiling <= s4 + 0.02)


def _summarize_hca(rows: Sequence[Mapping[str, str]] | None) -> dict[str, Any]:
    if rows is None:
        return {"status": NOT_MEASURED, "scales": {}}
    fresh = [row for row in rows if row.get("evidence_kind") == "FRESH_LOCAL_RUN"]
    by_scale: dict[str, Any] = {}
    for scale in (2, 4):
        candidates = [row for row in fresh if _integer(row.get("scale")) == scale]
        if not candidates:
            by_scale[str(scale)] = {"status": NOT_MEASURED}
            continue
        row = sorted(candidates, key=lambda item: item.get("evidence_id", ""))[-1]
        released = _integer(row.get("released_segment_count"))
        completed = _integer(row.get("completed_segment_count"))
        complete_bags = _integer(row.get("canonical_complete_raw_bag_count"))
        incomplete_bags = _integer(row.get("canonical_incomplete_raw_bag_count"))
        counts = (released, completed, complete_bags, incomplete_bags)
        measured = (
            row.get("execution_status") == "COMPLETE"
            and all(value is not None and value >= 0 for value in counts)
            and completed is not None
            and released is not None
            and completed <= released
        )
        by_scale[str(scale)] = {
            "status": "MEASURED_CAPACITY" if measured else NOT_MEASURED,
            "execution_status": row.get("execution_status", NOT_MEASURED),
            "released_segment_count": released if released is not None else NOT_MEASURED,
            "completed_segment_count": completed if completed is not None else NOT_MEASURED,
            "canonical_complete_raw_bag_count": (
                complete_bags if complete_bags is not None else NOT_MEASURED
            ),
            "canonical_incomplete_raw_bag_count": (
                incomplete_bags if incomplete_bags is not None else NOT_MEASURED
            ),
            "full_population_tth": row.get("full_population_tth", NOT_MEASURED),
        }
    return {
        "status": PASS if all(by_scale.get(str(scale), {}).get("status") == "MEASURED_CAPACITY" for scale in (2, 4)) else NOT_MEASURED,
        "scales": by_scale,
    }


def _source_states(
    g24: Mapping[str, Any] | None,
    coverage: Mapping[str, Any] | None,
    short_horizon: Mapping[str, Any] | None,
    learning: Mapping[str, Any] | None,
    native: Mapping[str, Any] | None,
    hca: Mapping[str, Any],
) -> dict[str, str]:
    raw_scales = coverage.get("measured_scales") if isinstance(coverage, Mapping) else None
    measured_scales = set(raw_scales) if isinstance(raw_scales, list) else set()
    coverage_ready = (
        isinstance(coverage, Mapping)
        and coverage.get("status") == "MEASURED"
        and {1, 2} <= measured_scales
        and (_integer(coverage.get("trajectory_count")) or 0) > 0
    )
    coverage_unsafe = _integer(coverage.get("unsafe_count")) if isinstance(coverage, Mapping) else None
    coverage_loops = _integer(coverage.get("loop_count")) if isinstance(coverage, Mapping) else None
    coverage_safe = (
        None
        if coverage_unsafe is None or coverage_loops is None
        else coverage_unsafe == 0 and coverage_loops == 0
    )
    short_scales = short_horizon.get("complete_checkpoint_count_by_scale") if isinstance(short_horizon, Mapping) else None
    short_ready = (
        isinstance(short_horizon, Mapping)
        and short_horizon.get("status") == "TARGET_MET"
        and isinstance(short_scales, Mapping)
        and all((_integer(short_scales.get(str(scale))) or 0) > 0 for scale in (1, 2))
    )
    short_unsafe = _integer(short_horizon.get("unsafe_arm_count")) if isinstance(short_horizon, Mapping) else None
    short_safe = None if short_unsafe is None else short_unsafe == 0
    learning_ready = (
        isinstance(learning, Mapping)
        and isinstance(learning.get("metrics"), Mapping)
        and isinstance(learning.get("l2_trigger"), Mapping)
        and isinstance(learning.get("l3_trigger"), Mapping)
    )
    coverage_state = (
        NOT_MEASURED
        if coverage is None or not coverage_ready or coverage_safe is None
        else PASS if coverage_safe else FAIL
    )
    short_state = (
        NOT_MEASURED
        if short_horizon is None or not short_ready or short_safe is None
        else PASS if short_safe else FAIL
    )
    return {
        "g24": _gate(None if g24 is None else True),
        "coverage_1x_2x": coverage_state,
        "short_horizon_1x_2x": short_state,
        "learning": PASS if learning_ready else NOT_MEASURED,
        "native": _gate(None if native is None else True),
        "hca_2x_4x": str(hca["status"]),
    }


def _branch_arm_key(row: Mapping[str, Any]) -> tuple[str | int, str | int] | None:
    branch_node = row.get("branch_node")
    first_edge = row.get("first_edge")
    values = (branch_node, first_edge)
    if not all(
        isinstance(value, (str, int))
        and not isinstance(value, bool)
        and value != ""
        for value in values
    ):
        return None
    return branch_node, first_edge


def _audit_summary(
    audit: Mapping[str, Any] | None,
    provisional: Mapping[str, Any] | None,
    *,
    core_state: str,
) -> dict[str, Any]:
    if provisional is None:
        if core_state == PASS:
            return {
                "status": "NOT_APPLICABLE_NO_CHANGED_ACTION_WINNER",
                "required_group_count": NOT_MEASURED,
                "complete_group_count": NOT_MEASURED,
                "system_effect": NOT_MEASURED,
                "private_fairness": NOT_MEASURED,
                "fault": {"status": "NOT_APPLICABLE_NO_CHANGED_ACTION_WINNER"},
            }
        return {
            "status": "NOT_MEASURED_CANDIDATE_SELECTION_INCOMPLETE",
            "required_group_count": NOT_MEASURED,
            "complete_group_count": NOT_MEASURED,
            "system_effect": NOT_MEASURED,
            "private_fairness": NOT_MEASURED,
            "fault": {"status": "NOT_MEASURED_CANDIDATE_SELECTION_INCOMPLETE"},
        }
    if audit is None:
        return {
            "status": "NOT_MEASURED_FINAL_AUDIT_PENDING",
            "candidate_id": provisional["candidate_id"],
            "candidate_mode": provisional["mode"],
            "required_group_count": 64,
            "complete_group_count": NOT_MEASURED,
            "system_effect": NOT_MEASURED,
            "private_fairness": NOT_MEASURED,
            "fault": {"status": "NOT_MEASURED_FINAL_AUDIT_PENDING"},
        }
    if audit.get("candidate_mode") != provisional.get("mode"):
        return {"status": FAIL, "reason": "FINAL_AUDIT_CANDIDATE_MISMATCH", "fault": {"status": FAIL}}
    groups = audit.get("groups")
    _require(isinstance(groups, list), "causal/fault groups must be a list")
    _require(all(isinstance(row, Mapping) for row in groups), "causal/fault group is not an object")
    ids = [row.get("group_id") for row in groups]
    complete_count = len(groups)
    if complete_count < 64:
        return {
            "status": "NOT_MEASURED_INSUFFICIENT_CHANGED_ACTIONS",
            "candidate_id": provisional["candidate_id"],
            "candidate_mode": provisional["mode"],
            "required_group_count": 64,
            "complete_group_count": complete_count,
            "system_effect": NOT_MEASURED,
            "private_fairness": NOT_MEASURED,
            "fault": {"status": "NOT_MEASURED_INSUFFICIENT_CHANGED_ACTIONS"},
        }
    valid_ids = all(
        isinstance(value, (str, int)) and not isinstance(value, bool) and value != ""
        for value in ids
    )
    integrity_states: list[str] = [PASS if complete_count <= 128 else FAIL]
    integrity_states.append(
        NOT_MEASURED
        if not valid_ids
        else _gate(len(ids) == len(set(ids)))
    )
    branch_arms: list[tuple[str | int, str | int]] = []
    for row in groups:
        horizon = row.get("horizon")
        integrity_states.append(
            NOT_MEASURED
            if not isinstance(horizon, str)
            else _gate(horizon == "H_system")
        )
        for name in (
            "same_state_start",
            "action_changed",
            "pair_complete",
            "horizon_complete",
            "raw_bag_comparison_eligible",
            "safety_pass",
        ):
            value = row.get(name)
            integrity_states.append(_gate(value if isinstance(value, bool) else None))
        changed_count = _integer(row.get("changed_action_count"))
        integrity_states.append(
            NOT_MEASURED if changed_count is None else _gate(changed_count == 1)
        )
        for name in (
            "runtime_global_scan_count",
            "future_route_input_count",
            "full_astar_call_count",
        ):
            count = _integer(row.get(name))
            integrity_states.append(
                NOT_MEASURED if count is None else _gate(count == 0)
            )
        branch_arm = _branch_arm_key(row)
        if branch_arm is None:
            integrity_states.append(NOT_MEASURED)
        else:
            branch_arms.append(branch_arm)
    branch_arms_measured = len(branch_arms) == complete_count
    changed_branch_arms = set(branch_arms)
    integrity_states.append(
        NOT_MEASURED
        if not branch_arms_measured
        else _gate(1 <= len(changed_branch_arms) <= 8)
    )
    integrity_state = _combine(integrity_states)
    metric_names = (
        "system_mean_delta_seconds",
        "system_p95_delta_seconds",
        "system_p99_delta_seconds",
        "system_max_delta_seconds",
        "current_bag_added_delay_seconds",
        "deadline_miss_delta",
    )
    values = {
        name: [_finite(row.get(name)) for row in groups]
        for name in metric_names
    }
    metrics_measured = bool(groups) and all(
        all(value is not None for value in items) for items in values.values()
    )
    aggregates: dict[str, Any] = {}
    if metrics_measured:
        aggregates = {
            "mean_system_mean_delta_seconds": statistics.fmean(float(value) for value in values["system_mean_delta_seconds"] if value is not None),
            "mean_system_p95_delta_seconds": statistics.fmean(float(value) for value in values["system_p95_delta_seconds"] if value is not None),
            "mean_system_p99_delta_seconds": statistics.fmean(float(value) for value in values["system_p99_delta_seconds"] if value is not None),
            "system_max_delta_seconds_diagnostic": max(float(value) for value in values["system_max_delta_seconds"] if value is not None),
            "current_bag_added_delay_mean_seconds": statistics.fmean(float(value) for value in values["current_bag_added_delay_seconds"] if value is not None),
            "current_bag_added_delay_max_seconds": max(float(value) for value in values["current_bag_added_delay_seconds"] if value is not None),
            "deadline_miss_delta_max": max(float(value) for value in values["deadline_miss_delta"] if value is not None),
        }
    effect_pass = metrics_measured and aggregates["mean_system_mean_delta_seconds"] <= 0.0 and aggregates["mean_system_p95_delta_seconds"] <= 0.0 and aggregates["mean_system_p99_delta_seconds"] <= 0.0
    fairness_pass = metrics_measured and aggregates["current_bag_added_delay_max_seconds"] <= 60.0 and aggregates["deadline_miss_delta_max"] <= 0.0
    no_fault = audit.get("no_fault_full")
    no_fault_state = NOT_MEASURED
    if isinstance(no_fault, Mapping) and no_fault.get("status") == "MEASURED":
        safety = no_fault.get("safety_pass")
        full_population = no_fault.get("full_population_complete")
        no_fault_states = [
            _gate(safety if isinstance(safety, bool) else None),
            _gate(full_population if isinstance(full_population, bool) else None),
        ]
        for name in (
            "runtime_global_scan_count",
            "future_route_input_count",
            "full_astar_call_count",
        ):
            count = _integer(no_fault.get(name))
            no_fault_states.append(
                NOT_MEASURED if count is None else _gate(count == 0)
            )
        no_fault_state = _combine(no_fault_states)
    fault = audit.get("fault")
    fault_state = NOT_MEASURED
    fault_summary: dict[str, Any] = {"status": NOT_MEASURED}
    if isinstance(fault, Mapping):
        target_count = _integer(fault.get("target_count"))
        fallback_count = _integer(fault.get("exact_s4_fallback_count"))
        recovery_count = _integer(fault.get("lease_recovery_count"))
        raw_targets = fault.get("target_branch_arms")
        target_branch_arms = (
            [_branch_arm_key(row) for row in raw_targets]
            if isinstance(raw_targets, list)
            and all(isinstance(row, Mapping) for row in raw_targets)
            else None
        )
        targets_measured = (
            target_branch_arms is not None
            and all(value is not None for value in target_branch_arms)
        )
        target_keys = (
            [value for value in target_branch_arms if value is not None]
            if targets_measured and target_branch_arms is not None
            else []
        )
        zero_fields = [
            _integer(fault.get(name))
            for name in (
                "physical_fault_edge_entry_violation_count",
                "runtime_global_scan_count",
                "future_route_input_count",
                "full_astar_call_count",
            )
        ]
        safety = fault.get("safety_pass")
        fault_measured = (
            fault.get("status") == "MEASURED"
            and target_count is not None
            and fallback_count is not None
            and recovery_count is not None
            and branch_arms_measured
            and targets_measured
            and all(value is not None for value in zero_fields)
            and isinstance(safety, bool)
        )
        if fault_measured:
            fault_state = _gate(
                target_count > 0
                and target_count == len(target_keys)
                and len(target_keys) == len(set(target_keys))
                and set(target_keys) == changed_branch_arms
                and fallback_count == target_count
                and recovery_count == target_count
                and all(value == 0 for value in zero_fields)
                and safety is True
            )
        fault_summary = {
            "status": fault_state,
            "target_count": target_count if target_count is not None else NOT_MEASURED,
            "exact_s4_fallback_count": fallback_count if fallback_count is not None else NOT_MEASURED,
            "lease_recovery_count": recovery_count if recovery_count is not None else NOT_MEASURED,
            "target_branch_arm_count": (
                len(target_keys) if targets_measured else NOT_MEASURED
            ),
        }
    gates = {
        "coverage_and_integrity": integrity_state,
        "metrics_measured": PASS if metrics_measured else NOT_MEASURED,
        "system_mean_p95_p99_nonregression": _gate(effect_pass if metrics_measured else None),
        "changed_bag_max_at_most_60s_and_deadline_safe": _gate(fairness_pass if metrics_measured else None),
        "no_fault_full": no_fault_state,
        "targeted_fault_exact_fallback": fault_state,
    }
    return {
        "status": _combine(gates.values()),
        "candidate_id": provisional["candidate_id"],
        "candidate_mode": provisional["mode"],
        "required_group_count": 64,
        "complete_group_count": complete_count,
        "changed_branch_arm_count": (
            len(changed_branch_arms) if branch_arms_measured else NOT_MEASURED
        ),
        "gates": gates,
        "system_effect": aggregates if metrics_measured else NOT_MEASURED,
        "private_fairness": (
            {
                "mean_added_delay_seconds": aggregates["current_bag_added_delay_mean_seconds"],
                "max_added_delay_seconds": aggregates["current_bag_added_delay_max_seconds"],
                "deadline_miss_delta_max": aggregates["deadline_miss_delta_max"],
            }
            if metrics_measured
            else NOT_MEASURED
        ),
        "fault": fault_summary,
    }


def _question(status: str, answer: str) -> dict[str, str]:
    return {"status": status, "answer": answer}


def _measured_github_section(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping) or value.get("status") != "MEASURED":
        return None
    return value


def _questions(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    final = summary["final"]
    inputs = summary["inputs"]
    hca = summary["hca"]["scales"]
    trajectory = summary["trajectory"] if isinstance(summary["trajectory"], Mapping) else {}
    short = summary["short_horizon"] if isinstance(summary["short_horizon"], Mapping) else {}
    ceilings = short.get("ceilings", {}) if isinstance(short, Mapping) else {}
    full = ceilings.get("full_state", {}) if isinstance(ceilings, Mapping) else {}
    local = ceilings.get("local_observation", {}) if isinstance(ceilings, Mapping) else {}
    audit = summary["final_audit"]
    candidates = summary["native"]["candidates"]
    github = summary.get("github") if isinstance(summary.get("github"), Mapping) else {}
    g24_github = _measured_github_section(github.get("g24"))
    g25_github = _measured_github_section(github.get("g25"))
    accounting: dict[str, Any] = {}
    one_x: dict[str, Any] = {}
    two_x: dict[str, Any] = {}
    four_x: dict[str, Any] = {}
    for candidate in candidates.values():
        label = str(candidate["candidate_id"])
        one_evidence = candidate.get("one_x", {}).get("evidence", {})
        two_evidence = candidate.get("two_x", {}).get("evidence", {})
        accounting[label] = {
            "proposals_2x": two_evidence.get("proposal_count", NOT_MEASURED),
            "mutations_2x": two_evidence.get(
                "committed_mutation_count", NOT_MEASURED
            ),
        }
        one_x[label] = {
            "candidate_seconds": one_evidence.get(
                "candidate_average_seconds", NOT_MEASURED
            ),
            "delta_s4_seconds": one_evidence.get(
                "average_delta_seconds", NOT_MEASURED
            ),
        }
        two_x[label] = {
            "candidate_seconds": two_evidence.get(
                "candidate_average_seconds", NOT_MEASURED
            ),
            "delta_s4_seconds": two_evidence.get(
                "average_delta_seconds", NOT_MEASURED
            ),
        }
        four_x[label] = candidate.get("four_x", NOT_MEASURED)
    t0 = candidates.get("t0", {})
    l1 = candidates.get("l1", {})
    l2_trigger = summary["offline"]["l2_trigger"]
    l3_trigger = summary["offline"]["l3_trigger"]
    answers = [
        _question(
            "MEASURED" if g24_github else NOT_MEASURED,
            f"PR #9 / Run #73 and current GitHub snapshot: "
            f"{g24_github or NOT_MEASURED}",
        ),
        _question(
            "MEASURED" if g25_github else NOT_MEASURED,
            f"G25 branch/commit/PR/CI: {g25_github or NOT_MEASURED}",
        ),
        _question(hca.get("2", {}).get("status", NOT_MEASURED), f"HCA 2x: {hca.get('2', NOT_MEASURED)}"),
        _question(hca.get("4", {}).get("status", NOT_MEASURED), f"HCA 4x: {hca.get('4', NOT_MEASURED)}"),
        _question(
            inputs["s4_4x_60_180"],
            f"S4 4x: {summary['native']['s4_four_x']}; full TTH: "
            f"{summary['native']['s4_four_x_full_population_tth']}",
        ),
        _question(inputs["coverage_1x_2x"], f"Real trajectories: {trajectory.get('trajectory_count', NOT_MEASURED)}"),
        _question(inputs["coverage_1x_2x"], f"Registered arm coverage: {trajectory.get('observed_registered_arm_fraction', NOT_MEASURED)}"),
        _question(inputs["short_horizon_1x_2x"], f"Paired checkpoints: {short.get('complete_checkpoint_count', NOT_MEASURED)}"),
        _question(inputs["short_horizon_1x_2x"], f"Full-state oracle: {full or NOT_MEASURED}"),
        _question(inputs["short_horizon_1x_2x"], f"Local-observation ceiling: {local or NOT_MEASURED}"),
        _question(inputs["short_horizon_1x_2x"], f"Opportunity mass: {ceilings.get('opportunity_mass', NOT_MEASURED) if isinstance(ceilings, Mapping) else NOT_MEASURED}"),
        _question(
            t0.get("eligibility", NOT_MEASURED),
            f"T0 eligibility={t0.get('eligibility', NOT_MEASURED)}, "
            f"1x={t0.get('one_x', {}).get('gate', {}).get('status', NOT_MEASURED)}, "
            f"2x={t0.get('two_x', {}).get('gate', {}).get('status', NOT_MEASURED)}",
        ),
        _question(
            l1.get("eligibility", NOT_MEASURED),
            f"L1 eligibility={l1.get('eligibility', NOT_MEASURED)}; "
            f"learning_additive={summary['native'].get('learning_additive', NOT_MEASURED)}",
        ),
        _question(
            "MEASURED" if isinstance(l2_trigger, Mapping) else NOT_MEASURED,
            f"L2 trigger: {l2_trigger}",
        ),
        _question(
            "MEASURED" if isinstance(l3_trigger, Mapping) else NOT_MEASURED,
            f"L3 trigger: {l3_trigger}",
        ),
        _question(inputs["native"], f"Proposal/mutation accounting: {accounting}"),
        _question(inputs["native"], f"1x candidate-minus-S4 mean/p95/p99/max seconds: {one_x}"),
        _question(inputs["native"], f"2x candidate-minus-S4 mean/p95/p99/max seconds: {two_x}"),
        _question(inputs["native"], f"4x candidate progress/gates: {four_x}"),
        _question(audit["status"] if audit["status"] in {PASS, FAIL} else NOT_MEASURED, f"Private fairness: {audit.get('private_fairness', NOT_MEASURED)}"),
        _question(audit["status"], f"H_system changed-action result: {audit.get('system_effect', NOT_MEASURED)}"),
        _question(audit.get("fault", {}).get("status", NOT_MEASURED), f"Fault result: {audit.get('fault', NOT_MEASURED)}"),
        _question(inputs["native"], "Runtime locality is gated by zero global-scan and future-route counters."),
        _question(inputs["native"], "Runtime full A* calls are gated at zero."),
        _question("MEASURED", f"Active policy: {final['active_policy']}"),
        _question("MEASURED", f"Learning promoted: {final['learning_promoted']}"),
        _question(
            "MEASURED" if final["decision"] != NOT_MEASURED else NOT_MEASURED,
            f"Paper claim boundary: {final['decision']}",
        ),
        _question("MEASURED", f"Still NOT_MEASURED: {summary['not_measured'] or 'none'}"),
    ]
    return [{"number": index + 1, **row} for index, row in enumerate(answers)]


def _render_causal(summary: Mapping[str, Any]) -> str:
    audit = summary["final_audit"]
    lines = [
        "# G4IRSF25 causal and fault",
        "",
        f"Status: `{audit['status']}`",
        "",
        f"- Candidate: `{audit.get('candidate_id', NOT_MEASURED)}`",
        f"- Required/complete H_system groups: `{audit.get('required_group_count', NOT_MEASURED)}` / `{audit.get('complete_group_count', NOT_MEASURED)}`",
        f"- System effect: `{audit.get('system_effect', NOT_MEASURED)}`",
        f"- Private fairness: `{audit.get('private_fairness', NOT_MEASURED)}`",
        f"- Fault: `{audit.get('fault', NOT_MEASURED)}`",
        "",
    ]
    if audit["status"] == "NOT_APPLICABLE_NO_CHANGED_ACTION_WINNER":
        lines.extend(
            [
                "No H_system/fault campaign was authorized because the complete native evidence had no changed-action winner.",
                "Counts and effects are N/A, not observed zeros; effect fields remain `NOT_MEASURED`.",
                "",
            ]
        )
    elif audit["status"] == "NOT_MEASURED_FINAL_AUDIT_PENDING":
        lines.extend(
            [
                "A provisional winner exists. Promotion remains disabled until 64 unique real changed actions and the targeted fault fallback are measured.",
                "",
            ]
        )
    return "\n".join(lines)


def _render_final(summary: Mapping[str, Any]) -> str:
    final = summary["final"]
    lines = [
        "# G4IRSF25 final joint decision",
        "",
        f"Decision: `{final['decision']}`",
        f"Active policy: `{final['active_policy']}`",
        f"Status: `{final['status']}`",
        f"Reason: `{final['reason']}`",
        "",
        "## Candidate gates",
        "",
        "| candidate | eligibility | 1x | 2x | 4x | offline | max +30s advisory |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode, candidate in summary["native"]["candidates"].items():
        lines.append(
            f"| {candidate['candidate_id']} | `{candidate['eligibility']}` "
            f"| `{candidate['one_x']['gate']['status']}` | `{candidate['two_x']['gate']['status']}` "
            f"| `{candidate['four_x']['status']}` | `{candidate['offline']['status']}` "
            f"| `{candidate['max_plus_30s_advisory']}` |"
        )
    lines.extend(
        [
            "",
            "## Required questions",
            "",
            "| # | status | answer |",
            "|---:|---|---|",
        ]
    )
    for row in summary["questions"]:
        answer = str(row["answer"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['number']} | `{row['status']}` | {answer} |")
    lines.extend(["", "Missing experiments remain literal `NOT_MEASURED`; bounded progress is never relabeled as complete-population TTH.", ""])
    return "\n".join(lines)


def _atomic_publish(payloads: Mapping[Path, str]) -> None:
    temporary: dict[Path, Path] = {}
    try:
        for path, text in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            with temp.open("x", encoding="utf-8", newline="") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            temporary[path] = temp
        for path, temp in temporary.items():
            os.replace(temp, path)
    finally:
        for temp in temporary.values():
            if temp.exists():
                temp.unlink()


def finalize(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    paths = {name: root / relative for name, relative in INPUT_PATHS.items()}
    g24 = _read_optional_json(paths["g24"], schema=G24_SCHEMA, label="G24 decision")
    coverage = _read_optional_json(paths["coverage"], schema=COVERAGE_SCHEMA, label="trajectory coverage")
    short_horizon = _read_optional_json(paths["short_horizon"], schema=SHORT_SCHEMA, label="short-horizon summary")
    learning = _read_optional_json(paths["learning"], schema=None, label="learning evidence")
    native = _read_optional_json(paths["native"], schema=NATIVE_SCHEMA, label="native campaign")
    hca_rows = _read_hca(paths["hca"])
    audit = _read_optional_json(paths["causal_fault"], schema=AUDIT_SCHEMA, label="causal/fault audit")
    github = _read_optional_json(paths["github"], schema=None, label="GitHub status")

    l2_trigger = learning.get("l2_trigger") if isinstance(learning, Mapping) else None
    l3_trigger = learning.get("l3_trigger") if isinstance(learning, Mapping) else None
    _require(l2_trigger is None or isinstance(l2_trigger, Mapping), "L2 trigger must be an object")
    _require(l3_trigger is None or isinstance(l3_trigger, Mapping), "L3 trigger must be an object")
    if isinstance(l2_trigger, Mapping):
        _require(isinstance(l2_trigger.get("triggered"), bool), "L2 triggered must be boolean")
    if isinstance(l3_trigger, Mapping):
        _require(isinstance(l3_trigger.get("triggered"), bool), "L3 triggered must be boolean")
    trigger_states = {
        "l2": l2_trigger.get("triggered") is True if isinstance(l2_trigger, Mapping) else False,
        "l3": l3_trigger.get("triggered") is True if isinstance(l3_trigger, Mapping) else False,
    }
    required_modes = ["t0", "l1", *[mode for mode in ("l2", "l3") if trigger_states[mode]]]
    # Untriggered optional artifacts are evidence leftovers, not inputs.  Do
    # not even parse a stale L2/L3 file when its measured trigger is false.
    policies = {
        mode: _load_policy(root / path, mode) if mode in required_modes else None
        for mode, path in POLICY_PATHS.items()
    }
    hca = _summarize_hca(hca_rows)
    native_rows = _validate_native(native) if native is not None else []
    source_states = _source_states(g24, coverage, short_horizon, learning, native, hca)
    source_states["s4_4x_60_180"] = (
        _s4_scale_state(native_rows) if native is not None else NOT_MEASURED
    )

    artifact_states: dict[str, str] = {}
    for mode in ("t0", "l1", "l2", "l3"):
        if mode in required_modes:
            artifact_states[mode] = _gate(None if policies[mode] is None else True)
        else:
            artifact_states[mode] = "NOT_APPLICABLE_NOT_TRIGGERED"

    candidates: dict[str, Any] = {}
    if learning is not None and short_horizon is not None:
        for mode in required_modes:
            if policies[mode] is None:
                candidates[mode] = {
                    "candidate_id": MODE_LABELS[mode],
                    "mode": mode,
                    "artifact_path": _portable(root, root / POLICY_PATHS[mode]),
                    "eligibility": NOT_MEASURED,
                    "evidence_completeness": NOT_MEASURED,
                    "reason": "REQUIRED_ARTIFACT_MISSING",
                    "one_x": {"gate": {"status": NOT_MEASURED}},
                    "two_x": {"gate": {"status": NOT_MEASURED}},
                    "four_x": {"status": NOT_MEASURED},
                    "offline": {"status": NOT_MEASURED},
                    "max_plus_30s_advisory": NOT_MEASURED,
                }
            else:
                candidates[mode] = _candidate(
                    native_rows,
                    learning,
                    short_horizon,
                    mode,
                    _portable(root, root / POLICY_PATHS[mode]),
                )

    core_state = _combine(
        [*source_states.values(), *(artifact_states[mode] for mode in required_modes)]
    )
    candidate_completeness = [
        candidate.get("evidence_completeness", NOT_MEASURED)
        for candidate in candidates.values()
    ]
    if core_state == PASS and any(
        state == NOT_MEASURED for state in candidate_completeness
    ):
        core_state = NOT_MEASURED

    eligible_t0 = candidates.get("t0") if candidates.get("t0", {}).get("eligibility") == PASS else None
    eligible_learning = [
        candidate
        for mode, candidate in candidates.items()
        if mode in {"l1", "l2", "l3"} and candidate.get("eligibility") == PASS
    ]
    best_learning = min(eligible_learning, key=lambda row: _rank_key(row, with_complexity=True)) if eligible_learning else None
    learning_additive: bool | str = NOT_MEASURED
    if best_learning is not None:
        learning_additive = eligible_t0 is None or _rank_key(best_learning, with_complexity=False) < _rank_key(eligible_t0, with_complexity=False)

    provisional: Mapping[str, Any] | None = None
    if core_state == PASS:
        if best_learning is not None and learning_additive is True:
            provisional = best_learning
        elif eligible_t0 is not None:
            provisional = eligible_t0

    final_audit = _audit_summary(audit, provisional, core_state=core_state)
    fresh_hca_beaten = (
        g24.get("final", {}).get("fresh_hca_beaten") is True
        if isinstance(g24, Mapping) and isinstance(g24.get("final"), Mapping)
        else False
    )
    oracle_low = _low_oracle(short_horizon) if short_horizon is not None else None

    if core_state != PASS:
        final = {
            "status": "INCOMPLETE_EVIDENCE",
            "decision": NOT_MEASURED,
            "active_policy": "S4",
            "active_mode": "off",
            "selected_candidate_id": None,
            "policy_artifact_path": None,
            "provisional_candidate_id": None,
            "provisional_policy_artifact_path": None,
            "learning_promoted": False,
            "threshold_promoted": False,
            "reason": "REQUIRED_G25_EVIDENCE_NOT_MEASURED",
        }
    elif provisional is not None and final_audit["status"] == PASS:
        learning_winner = provisional["mode"] in {"l1", "l2", "l3"}
        final = {
            "status": "PROMOTED",
            "decision": (
                "LOAD_CONDITIONAL_DECENTRALIZED_LEARNING_PROMOTED"
                if learning_winner
                else "LOAD_CONDITIONAL_DECENTRALIZED_THRESHOLD_PROMOTED_LEARNING_NOT_ADDITIVE"
            ),
            "active_policy": provisional["candidate_id"],
            "active_mode": provisional["mode"],
            "selected_candidate_id": provisional["candidate_id"],
            "policy_artifact_path": provisional["artifact_path"],
            "provisional_candidate_id": provisional["candidate_id"],
            "provisional_policy_artifact_path": provisional["artifact_path"],
            "learning_promoted": learning_winner,
            "threshold_promoted": not learning_winner,
            "reason": "CORE_BUSINESS_AND_FINAL_AUDIT_PASS",
        }
    elif provisional is not None and final_audit["status"] not in {FAIL, PASS}:
        final = {
            "status": "FINAL_AUDIT_REQUIRED",
            "decision": NOT_MEASURED,
            "active_policy": "S4",
            "active_mode": "off",
            "selected_candidate_id": None,
            "policy_artifact_path": None,
            "provisional_candidate_id": provisional["candidate_id"],
            "provisional_policy_artifact_path": provisional["artifact_path"],
            "learning_promoted": False,
            "threshold_promoted": False,
            "reason": str(final_audit["status"]),
        }
    else:
        decision = (
            "CORRIDOR_ACTION_OPPORTUNITY_CEILING_MEASURED"
            if oracle_low is True
            else (
                "DECENTRALIZED_RULE_BASED_TAKEOVER_CONFIRMED_LEARNING_NOT_YET_ADDITIVE"
                if fresh_hca_beaten
                else NOT_MEASURED
            )
        )
        final = {
            "status": "KEEP_S4",
            "decision": decision,
            "active_policy": "S4",
            "active_mode": "off",
            "selected_candidate_id": None,
            "policy_artifact_path": None,
            "provisional_candidate_id": provisional["candidate_id"] if provisional else None,
            "provisional_policy_artifact_path": provisional["artifact_path"] if provisional else None,
            "learning_promoted": False,
            "threshold_promoted": False,
            "reason": "FINAL_AUDIT_FAILED" if provisional else "NO_ELIGIBLE_CHANGED_ACTION_WINNER",
        }

    missing = [name for name, state in source_states.items() if state == NOT_MEASURED]
    missing.extend(f"artifact:{mode}" for mode in required_modes if artifact_states[mode] == NOT_MEASURED)
    missing.extend(
        f"candidate:{mode}:required_native_evidence"
        for mode, candidate in candidates.items()
        if candidate.get("evidence_completeness") == NOT_MEASURED
    )
    if final_audit["status"].startswith("NOT_MEASURED"):
        missing.append("final_audit")
    if github is None or _measured_github_section(github.get("g24")) is None:
        missing.append("github_g24_status")
    if github is None or _measured_github_section(github.get("g25")) is None:
        missing.append("github_g25_status")
    for scale in (2, 4):
        if hca["scales"].get(str(scale), {}).get("full_population_tth") == NOT_MEASURED:
            missing.append(f"hca_{scale}x_full_population_tth")
    complete_s4_four_x = any(
        row.get("mode") == "off"
        and _integer(row.get("scale")) == 4
        and row.get("execution_mode") == "full"
        and row.get("evidence_status") == "MEASURED_COMPLETE"
        for row in native_rows
    )
    if not complete_s4_four_x:
        missing.append("native_4x_full_population_tth")

    s4_four_x: dict[str, Any] = {}
    for duration in (60.0, 180.0):
        row = _bounded_row(native_rows, "off", duration)
        s4_four_x[f"{duration:g}s"] = (
            {
                name: row.get(name, NOT_MEASURED)
                for name in (
                    "segments_released",
                    "segments_requested",
                    "segments_completed",
                    "current_backlog",
                    "events_per_completed_segment",
                    "safety_pass",
                )
            }
            if row is not None
            else NOT_MEASURED
        )

    summary: dict[str, Any] = {
        "schema": DECISION_SCHEMA,
        "inputs": source_states,
        "trajectory": dict(coverage) if coverage is not None else NOT_MEASURED,
        "short_horizon": dict(short_horizon) if short_horizon is not None else NOT_MEASURED,
        "offline": {
            "artifact_states": artifact_states,
            "l2_trigger": dict(l2_trigger) if isinstance(l2_trigger, Mapping) else NOT_MEASURED,
            "l3_trigger": dict(l3_trigger) if isinstance(l3_trigger, Mapping) else NOT_MEASURED,
        },
        "native": {
            "core_state": core_state,
            "candidates": candidates,
            "best_learning_candidate_id": best_learning["candidate_id"] if best_learning else None,
            "learning_additive": learning_additive,
            "provisional_winner_candidate_id": provisional["candidate_id"] if provisional else None,
            "s4_four_x": s4_four_x,
            "s4_four_x_full_population_tth": (
                "MEASURED_COMPLETE" if complete_s4_four_x else NOT_MEASURED
            ),
        },
        "hca": hca,
        "g24_static_corridor": (
            dict(g24.get("reconvergent_corridor", {})) if isinstance(g24, Mapping) else NOT_MEASURED
        ),
        "github": dict(github) if github is not None else NOT_MEASURED,
        "final_audit": final_audit,
        "final": final,
        "not_measured": missing,
    }
    summary["questions"] = _questions(summary)

    selection = {
        "schema": SELECTION_SCHEMA,
        **final,
        "final_audit_status": final_audit["status"],
        "required_h_system_group_count": final_audit.get(
            "required_group_count", NOT_MEASURED
        ),
    }
    payloads = {
        root / OUTPUT_PATHS["decision"]: json.dumps(_plain(summary), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        root / OUTPUT_PATHS["causal_report"]: _render_causal(summary),
        root / OUTPUT_PATHS["final_report"]: _render_final(summary),
        # The selection is runtime authority, so promote it only after all
        # explanatory views have been promoted successfully.
        root / OUTPUT_PATHS["selection"]: json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
    }
    _atomic_publish(payloads)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = finalize(args.root)
        print(
            json.dumps(
                {
                    "status": summary["final"]["status"],
                    "active_policy": summary["final"]["active_policy"],
                    "decision": summary["final"]["decision"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (FinalDecisionError, OSError, json.JSONDecodeError, csv.Error) as exc:
        print(f"G25 final decision failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

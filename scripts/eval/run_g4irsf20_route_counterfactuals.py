#!/usr/bin/env python3
"""Build the compact G4IRSF20 exact Route counterfactual dataset.

This is intentionally a thin orchestration layer over the G15 native clone
engine.  The native engine owns same-state replay, intervention legality and
horizon execution; this file only performs an outcome-free I3 census sample,
assigns horizons, resumes completed shards, and writes training-sized rows.
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import math
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


RESEARCH_PROFILE = "G20_S4_J2"
COMPLETE_STATUS = "ACTION_CHANGED_HORIZON_COMPLETE"
DEFERRED_TARGET_SCHEMA = "czr005.g4irsf20.route_target.v1"
CAMPAIGN_REVISION = "g20-primary-pair-r2"
_WORKER_CACHE: tuple[str, str, Any, list[Any]] | None = None


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_plain(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(_plain(row), sort_keys=True) + "\n")
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError(f"{path}:{line_number}: expected object")
            rows.append(value)
    return rows


def _load_native(binary: Path) -> Any:
    binary = binary.resolve(strict=True)
    specification = importlib.util.spec_from_file_location("czr005_cpp", binary)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load native extension: {binary}")
    module = importlib.util.module_from_spec(specification)
    sys.modules["czr005_cpp"] = module
    specification.loader.exec_module(module)
    return module


def _native_arguments(root: Path) -> list[Any]:
    sys.path[:0] = [str(root), str(root / "src")]
    from scripts.eval import g4irsf15_causal_campaign as g15

    arguments, _, _ = g15._native_arguments(root)  # Reuse the frozen input seam.
    return arguments


def _route_observation(row: Mapping[str, Any], *, context: str) -> dict[str, Any]:
    observation = row.get("route_observation")
    if not isinstance(observation, Mapping):
        raise RuntimeError(f"{context}: missing G20 Route observation sidecar")
    names = observation.get("feature_names")
    vectors = observation.get("canonical_candidate_observations")
    nodes = observation.get("candidate_next_nodes")
    if not isinstance(names, list) or not names:
        raise RuntimeError(f"{context}: empty Route feature schema")
    if not isinstance(vectors, list) or not isinstance(nodes, list) or len(vectors) != len(nodes):
        raise RuntimeError(f"{context}: Route candidate shape mismatch")
    if len(vectors) < 2 or any(not isinstance(vector, list) or len(vector) != len(names) for vector in vectors):
        raise RuntimeError(f"{context}: incomplete Route candidate features")
    baseline = observation.get("baseline_candidate_index")
    treatment = observation.get("treatment_candidate_index")
    if not isinstance(baseline, int) or not 0 <= baseline < len(vectors):
        raise RuntimeError(f"{context}: invalid baseline candidate index")
    if not isinstance(treatment, int) or not 0 <= treatment < len(vectors) or treatment == baseline:
        raise RuntimeError(f"{context}: invalid treatment candidate index")
    for forbidden_counter in (
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
        "runtime_full_astar_call_count",
    ):
        if observation.get(forbidden_counter) != 0:
            raise RuntimeError(f"{context}: non-local read reported by {forbidden_counter}")
    return dict(_plain(observation))


def _wait_age(row: Mapping[str, Any]) -> float:
    value = row.get("wait_age_seconds")
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise RuntimeError("census I3: priority_age_seconds is not finite")
    return float(value)


def _selection_identity(row: Mapping[str, Any], *, context: str) -> dict[str, Any]:
    """Normalize current census rows and already-written G20 selections.

    The legacy aliases are read only so an interrupted pre-materialization run
    can resume.  New targets use plain semantic IDs and never manufacture or
    validate digests in Python.
    """
    nested = row.get("selection", row.get("skeleton", row))
    if not isinstance(nested, Mapping):
        raise RuntimeError(f"{context}: selection identity is not an object")

    def text(*names: str) -> str:
        for name in names:
            value = nested.get(name)
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"{context}: missing {'/'.join(names)}")

    kind = text("kind")
    if kind not in {"I3", "I3_NEXT_EDGE"}:
        raise RuntimeError(f"{context}: expected I3_NEXT_EDGE, got {kind}")
    skeleton_id = text("skeleton_id", "descriptor_id")
    population_selection_id = text(
        "population_selection_id", "skeleton_selection_sha256", "skeleton_id"
    )
    identity = {
        "schema_id": text("schema_id", "schema"),
        "descriptor_id": skeleton_id,
        "skeleton_id": skeleton_id,
        "population_group_id": text(
            "population_group_id", "population_group_sha256"
        ),
        "population_selection_id": population_selection_id,
        "kind": "I3_NEXT_EDGE",
        "event_ordinal": int(nested["event_ordinal"]),
    }
    return identity


def deferred_plan(
    plan: Sequence[Mapping[str, Any]], *, long_wait_seconds: float = 30.0
) -> list[dict[str, Any]]:
    """Convert compact census selections directly to lazy native targets."""
    result: list[dict[str, Any]] = []
    for row in plan:
        group_index = int(row["group_index"])
        identity = _selection_identity(row, context=f"selection group {group_index}")
        horizon = str(row["planned_horizon"])
        if horizon not in {"H_bag", "H_system"}:
            raise RuntimeError(f"selection group {group_index}: invalid horizon")
        # This five-field address is the complete native G20 contract.  Kind
        # and the primary alternative are fixed by the schema and therefore
        # are not repeated as knobs.
        target = {
            "schema": DEFERRED_TARGET_SCHEMA,
            "population_group_id": identity["population_group_id"],
            "population_selection_id": identity["population_selection_id"],
            "event_ordinal": identity["event_ordinal"],
            "horizon": horizon,
        }
        result.append(
            {
                "group_index": group_index,
                "long_wait": float(row["wait_age_seconds"]) >= long_wait_seconds,
                "wait_age_seconds": float(row["wait_age_seconds"]),
                "target": target,
            }
        )
    return result


def _target_identity(row: Mapping[str, Any], *, context: str) -> tuple[Any, ...]:
    target = row.get("target", row)
    if not isinstance(target, Mapping):
        raise RuntimeError(f"{context}: target identity is not an object")
    fields = (
        "schema",
        "population_group_id",
        "population_selection_id",
        "event_ordinal",
        "horizon",
    )
    missing = [field for field in fields if field not in target]
    if missing:
        raise RuntimeError(f"{context}: target identity missing {missing}")
    return tuple(target[field] for field in fields)


def _even_sample(rows: Sequence[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Select across event order without a random/hash ranking."""
    if count <= 0:
        return []
    if count >= len(rows):
        return list(rows)
    return [rows[(index * len(rows)) // count] for index in range(count)]


def _oversampled_target(target: int, multiplier: float) -> int:
    if target <= 0:
        raise RuntimeError("eligible target must be positive")
    if not math.isfinite(multiplier) or multiplier < 1.0:
        raise RuntimeError("screening oversample must be finite and at least 1.0")
    return int(math.ceil(target * multiplier))


def select_route_skeletons(
    scan: Mapping[str, Any],
    *,
    target_groups: int,
    long_wait_target: int,
    h_system_target: int,
    long_wait_seconds: float,
    allow_shortfall: bool = False,
) -> list[dict[str, Any]]:
    if scan.get("census_complete") is not True:
        raise RuntimeError("native full census did not complete its terminal gate")
    population = scan.get("skeletons")
    if not isinstance(population, list):
        raise RuntimeError("native census omitted skeletons")
    route = [
        row
        for row in population
        if isinstance(row, Mapping) and row.get("kind") in {"I3", "I3_NEXT_EDGE"}
    ]
    route.sort(key=lambda row: (int(row["event_ordinal"]), int(row.get("runtime_bag_id", -1))))

    required_groups = min(target_groups, len(route))
    long_pool = [row for row in route if _wait_age(row) >= long_wait_seconds]
    required_long = min(long_wait_target, required_groups)
    if not allow_shortfall and len(route) < target_groups:
        raise RuntimeError(f"I3 census has {len(route)} groups, below target {target_groups}")
    if not allow_shortfall and len(long_pool) < required_long:
        raise RuntimeError(
            f"I3 census has {len(long_pool)} waits >= {long_wait_seconds:g}s, below target {required_long}"
        )

    long_selected = _even_sample(long_pool, min(required_long, len(long_pool)))
    def selection_id(row: Mapping[str, Any]) -> str:
        return str(
            _selection_identity(row, context="census I3")["population_selection_id"]
        )

    chosen_ids = {selection_id(row) for row in long_selected}
    remaining = [row for row in route if selection_id(row) not in chosen_ids]
    selected = long_selected + _even_sample(remaining, required_groups - len(long_selected))
    selected.sort(key=lambda row: (int(row["event_ordinal"]), int(row.get("runtime_bag_id", -1))))

    h_system_count = min(h_system_target, len(selected))
    if not allow_shortfall and h_system_count < h_system_target:
        raise RuntimeError(f"only {h_system_count} groups are available for H_system")
    long_ids = {selection_id(row) for row in long_selected}
    h_candidates = [row for row in selected if selection_id(row) in long_ids]
    h_candidates += [row for row in selected if selection_id(row) not in long_ids]
    h_selected = _even_sample(h_candidates, h_system_count)
    h_ids = {selection_id(row) for row in h_selected}

    plan: list[dict[str, Any]] = []
    for group_index, row in enumerate(selected):
        plan.append(
            {
                "group_index": group_index,
                "event_ordinal": int(row["event_ordinal"]),
                "wait_age_seconds": _wait_age(row),
                "long_wait": _wait_age(row) >= long_wait_seconds,
                "planned_horizon": "H_system" if selection_id(row) in h_ids else "H_bag",
                "selection": _selection_identity(row, context="selected census I3"),
            }
        )
    return plan


def scan_full_census(module: Any, native_arguments: Sequence[Any]) -> dict[str, Any]:
    payload = module.g4irsf15_scan_causal_skeletons_from_records(
        *native_arguments, RESEARCH_PROFILE
    )
    if not isinstance(payload, Mapping):
        raise RuntimeError("native scan returned a non-object")
    return dict(_plain(payload))


def _branch_outcome(branch: Any) -> dict[str, Any] | None:
    if not isinstance(branch, Mapping):
        return None
    invariants = branch.get("invariants")
    safety = None
    if isinstance(invariants, Mapping):
        safety = {
            "live_safety_pass": invariants.get("live_safety_pass"),
            "formal_hard_gate_pass": invariants.get("formal_hard_gate_pass"),
            "failed_segment_count": invariants.get("failed_segment_count"),
            "unsafe_entry_count": invariants.get("unsafe_entry_count"),
            "reservation_conflict_count": invariants.get("reservation_conflict_count"),
            "unresolved_deadlock_count": invariants.get("unresolved_deadlock_count"),
        }
    return {
        "horizon_complete": branch.get("horizon_complete"),
        "blocked": branch.get("blocked"),
        "stop_reason": branch.get("stop_reason"),
        "elapsed_event_count": branch.get("elapsed_event_count"),
        "affected_bag_outcomes": _plain(branch.get("affected_bag_outcomes")),
        "cohort_metrics": _plain(branch.get("cohort_metrics")),
        "raw_bag_cohort_metrics": _plain(branch.get("raw_bag_cohort_metrics")),
        "safety": safety,
    }


def _signed_label(delta_seconds: float) -> str:
    if delta_seconds < -1e-9:
        return "BENEFICIAL"
    if delta_seconds > 1e-9:
        return "HARMFUL"
    return "NEUTRAL_WITHIN_TOLERANCE"


def compact_pair(pair: Mapping[str, Any], planned: Mapping[str, Any]) -> dict[str, Any]:
    target = planned["target"]
    complete = (
        pair.get("pair_status") == COMPLETE_STATUS
        and pair.get("action_changed") is True
        and pair.get("same_state_start") is True
        and pair.get("pair_complete") is True
        and pair.get("live_safety_pass") is True
    )
    common = {
        "schema": "czr005.g4irsf20.route_counterfactual.v1",
        "campaign_revision": CAMPAIGN_REVISION,
        "group_index": int(planned["group_index"]),
        "target_identity": dict(_plain(target)),
        "population_group_id": str(target["population_group_id"]),
        "population_selection_id": str(target["population_selection_id"]),
        "event_ordinal": int(target["event_ordinal"]),
        "horizon": str(target["horizon"]),
        "long_wait": bool(planned["long_wait"]),
        "wait_age_seconds": float(planned["wait_age_seconds"]),
        "pair_status": pair.get("pair_status"),
        "same_state_start": pair.get("same_state_start") is True,
        "action_changed": pair.get("action_changed") is True,
        "safety_equivalent": pair.get("safety_equivalent") is True,
        "failure_reason": (
            None
            if complete
            else (
                pair.get("false_positive_reason")
                or pair.get("pair_status")
                or "UNKNOWN"
            )
        ),
    }
    if not complete:
        return {
            **common,
            "runtime_bag_id": None,
            "task_id": None,
            "baseline_next_node": None,
            "treatment_next_node": None,
            "legal_next_edges": [],
            "route_observation": None,
            "baseline_outcome": None,
            "treatment_outcome": None,
            "direct_completion_delta_seconds": None,
            "segment_cohort_completion_mean_delta_seconds": None,
            "raw_bag_system_tth_mean_delta_seconds": None,
            "signed_causal_label": "NOT_ELIGIBLE",
            "eligible_causal_label": False,
        }

    descriptor = pair.get("resolved_execution_descriptor")
    if not isinstance(descriptor, Mapping):
        raise RuntimeError(
            f"pair group {planned['group_index']}: resolved descriptor missing"
        )
    observation = pair.get("route_observation") or descriptor.get("route_observation")
    observation = _route_observation(
        {"route_observation": observation}, context=f"pair group {planned['group_index']}"
    )
    deltas = pair.get("affected_bag_deltas")
    direct_delta: float | None = None
    if isinstance(deltas, list) and deltas:
        values = [float(row["completion_delta_seconds"]) for row in deltas if isinstance(row, Mapping)]
        if values:
            direct_delta = sum(values) / len(values)
    label = _signed_label(direct_delta) if complete and direct_delta is not None else "NOT_ELIGIBLE"
    baseline = _branch_outcome(pair.get("baseline"))
    treatment = _branch_outcome(pair.get("treatment"))
    segment_system_delta: float | None = None
    raw_bag_system_delta: float | None = None
    if target["horizon"] == "H_system" and baseline and treatment:
        left = baseline.get("cohort_metrics")
        right = treatment.get("cohort_metrics")
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            if isinstance(left.get("completion_mean_seconds"), (int, float)) and isinstance(right.get("completion_mean_seconds"), (int, float)):
                segment_system_delta = float(right["completion_mean_seconds"]) - float(left["completion_mean_seconds"])
        raw_left = baseline.get("raw_bag_cohort_metrics")
        raw_right = treatment.get("raw_bag_cohort_metrics")
        if isinstance(raw_left, Mapping) and isinstance(raw_right, Mapping):
            left_minutes = raw_left.get("original_entry_mean_minutes")
            right_minutes = raw_right.get("original_entry_mean_minutes")
            if isinstance(left_minutes, (int, float)) and isinstance(
                right_minutes, (int, float)
            ):
                raw_bag_system_delta = (
                    float(right_minutes) - float(left_minutes)
                ) * 60.0
    runtime_bag_id = int(descriptor["runtime_bag_id"])
    task_id = descriptor.get("task_id")
    if not isinstance(task_id, int) and baseline:
        outcomes = baseline.get("affected_bag_outcomes")
        if isinstance(outcomes, list):
            match = next(
                (
                    outcome
                    for outcome in outcomes
                    if isinstance(outcome, Mapping)
                    and outcome.get("runtime_bag_id") == runtime_bag_id
                    and isinstance(outcome.get("task_id"), int)
                ),
                None,
            )
            if match is not None:
                task_id = match["task_id"]
    return {
        **common,
        "runtime_bag_id": runtime_bag_id,
        "task_id": int(task_id) if isinstance(task_id, int) else None,
        "baseline_next_node": int(descriptor["baseline_next_node"]),
        "treatment_next_node": int(descriptor["selected_next_node"]),
        "legal_next_edges": _plain(descriptor["legal_next_edges"]),
        "route_observation": observation,
        "baseline_outcome": baseline,
        "treatment_outcome": treatment,
        "direct_completion_delta_seconds": direct_delta,
        "segment_cohort_completion_mean_delta_seconds": segment_system_delta,
        "raw_bag_system_tth_mean_delta_seconds": raw_bag_system_delta,
        "signed_causal_label": label,
        "eligible_causal_label": complete and direct_delta is not None,
    }


def compact_training_row(exact: Mapping[str, Any]) -> dict[str, Any]:
    """Project one eligible exact pair into the learning runner contract.

    Outcomes remain only labels/diagnostics.  The model-visible dictionaries
    are copied exclusively from the pre-action native Route observation.
    """
    if exact.get("eligible_causal_label") is not True:
        raise RuntimeError(
            f"group {exact.get('group_index')}: ineligible evidence cannot enter training"
        )
    delta = exact.get("direct_completion_delta_seconds")
    if not isinstance(delta, (int, float)) or not math.isfinite(float(delta)):
        raise RuntimeError(f"group {exact.get('group_index')}: causal utility missing")
    observation = _route_observation(
        exact, context=f"compact group {exact.get('group_index')}"
    )
    candidates = observation.get("candidate_observations")
    baseline_index = int(observation["baseline_candidate_index"])
    treatment_index = int(observation["treatment_candidate_index"])
    if not isinstance(candidates, list):
        raise RuntimeError(f"group {exact.get('group_index')}: candidate mappings missing")
    selected_native: list[dict[str, Any]] = []
    for candidate_index in (baseline_index, treatment_index):
        candidate = candidates[candidate_index]
        if not isinstance(candidate, Mapping):
            raise RuntimeError(
                f"group {exact.get('group_index')}: candidate mapping missing"
            )
        selected_native.append(dict(_plain(candidate)))
    native_normal_flow = observation.get("normal_flow")
    if native_normal_flow is not None and type(native_normal_flow) is not bool:
        raise RuntimeError(
            f"group {exact.get('group_index')}: native normal_flow must be boolean"
        )
    fault_free_fallback = all(
        isinstance(candidate, Mapping)
        and candidate.get("advertised_fault") is False
        for candidate in candidates
    )
    # New binaries provide the scorer-owned normal-flow classification.  The
    # fallback keeps old diagnostic binaries readable, but is deliberately
    # narrower and never overrides a native False.
    normal_flow = exact.get("safety_equivalent") is True and (
        native_normal_flow
        if type(native_normal_flow) is bool
        else fault_free_fallback
    )
    return {
        "schema_id": "czr005.g4irsf20.route_counterfactual.compact.v1",
        "choice_group_id": f"g20-route-{int(exact['group_index'])}",
        # Split metadata is deliberately outside native_features and therefore
        # cannot be consumed by the model projection.
        "split_group": int(
            exact["task_id"]
            if isinstance(exact.get("task_id"), int)
            else exact["runtime_bag_id"]
        ),
        "normal_flow": normal_flow,
        # G20 deliberately starts with one exact alternative per boundary.
        # The full legal edge set and legal WAIT remain visible diagnostics,
        # but are not falsely marked as labeled training actions.
        "primary_pair_labeled": True,
        "full_legal_action_set_labeled": False,
        "wait_action_labeled": False,
        "label_scope": "AFFECTED_RUNTIME_SEGMENT_COMPLETION_PRIMARY_PAIR",
        "source_scale": 1,
        "s4_index": 0,
        "candidates": [
            {
                "legal": True,
                "native_features": selected_native[0],
                "utility": 0.0,
            },
            {
                "legal": True,
                "native_features": selected_native[1],
                "utility": -float(delta),
            },
        ],
        "horizon": exact.get("horizon"),
        "direct_completion_delta_seconds": float(delta),
        "segment_cohort_completion_mean_delta_seconds": exact.get(
            "segment_cohort_completion_mean_delta_seconds"
        ),
        "raw_bag_system_tth_mean_delta_seconds": exact.get(
            "raw_bag_system_tth_mean_delta_seconds"
        ),
        "system_diagnostic_delta_seconds": (
            exact.get("raw_bag_system_tth_mean_delta_seconds")
            if isinstance(
                exact.get("raw_bag_system_tth_mean_delta_seconds"),
                (int, float),
            )
            else exact.get("segment_cohort_completion_mean_delta_seconds")
        ),
        "system_diagnostic_scope": (
            "NOT_APPLICABLE_H_BAG"
            if exact.get("horizon") != "H_system"
            else (
                "RAW_BAG_ORIGINAL_ENTRY_TTH_MEAN"
                if isinstance(
                    exact.get("raw_bag_system_tth_mean_delta_seconds"),
                    (int, float),
                )
                else "SEGMENT_COHORT_COMPLETION_MEAN"
            )
        ),
        "signed_causal_label": exact.get("signed_causal_label"),
    }


def run_native_shard(
    module: Any,
    native_arguments: Sequence[Any],
    planned: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    targets = [row["target"] for row in planned]
    payload = module.g4irsf15_run_causal_target_pairs_from_records(
        *native_arguments, targets, RESEARCH_PROFILE
    )
    pairs = payload.get("pairs") if isinstance(payload, Mapping) else None
    if not isinstance(pairs, list) or len(pairs) != len(planned):
        raise RuntimeError("native pair count mismatch")
    def pair_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
        echoed = {
            "schema": row.get("target_schema"),
            "population_group_id": row.get("population_group_id"),
            "population_selection_id": row.get("population_selection_id"),
            "event_ordinal": row.get("event_ordinal"),
            "horizon": row.get("horizon"),
        }
        return _target_identity(echoed, context="native pair echo")

    by_target = {
        pair_identity(row): row for row in pairs if isinstance(row, Mapping)
    }
    if len(by_target) != len(pairs):
        raise RuntimeError("native pair target identities are not unique")
    compact: list[dict[str, Any]] = []
    for row in planned:
        expected = _target_identity(row, context=f"planned group {row['group_index']}")
        pair = by_target.get(expected)
        if pair is None:
            raise RuntimeError(
                f"pair output omitted or changed target identity for group {row['group_index']}"
            )
        selection_id = str(row["target"]["population_selection_id"])
        if (
            str(pair.get("descriptor_id")) != selection_id
            or str(pair.get("target_address_id")) != selection_id
            or pair.get("kind") != "I3"
        ):
            raise RuntimeError(
                f"pair group {row['group_index']}: native resolved identity drifted"
            )
        compact.append(compact_pair(pair, row))
    return compact


def _process_shard_task(
    root_text: str,
    binary_text: str,
    planned: list[dict[str, Any]],
    output_text: str,
) -> str:
    global _WORKER_CACHE
    root = Path(root_text)
    cache_key = (str(root.resolve()), str(Path(binary_text).resolve()))
    if _WORKER_CACHE is None or _WORKER_CACHE[:2] != cache_key:
        _WORKER_CACHE = (
            cache_key[0],
            cache_key[1],
            _load_native(Path(binary_text)),
            _native_arguments(root),
        )
    module = _WORKER_CACHE[2]
    native_arguments = _WORKER_CACHE[3]
    rows = run_native_shard(module, native_arguments, planned)
    _atomic_jsonl(Path(output_text), rows)
    return output_text


def _valid_shard(path: Path, expected: Sequence[Mapping[str, Any]]) -> bool:
    if not path.is_file():
        return False
    try:
        rows = _read_jsonl(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if [int(row.get("group_index", -1)) for row in rows] != [
        int(row["group_index"]) for row in expected
    ]:
        return False
    try:
        observed_identities = [
            _target_identity(row.get("target_identity", {}), context="resumed shard")
            for row in rows
        ]
        expected_identities = [
            _target_identity(row, context="expected shard") for row in expected
        ]
    except (KeyError, RuntimeError, TypeError, ValueError):
        return False
    evidence_shapes = all(
        bool(row.get("route_observation"))
        if row.get("eligible_causal_label") is True
        else (
            row.get("pair_status") != COMPLETE_STATUS
            and isinstance(row.get("failure_reason"), str)
            and bool(row.get("failure_reason"))
        )
        for row in rows
    )
    return (
        observed_identities == expected_identities
        and all(row.get("campaign_revision") == CAMPAIGN_REVISION for row in rows)
        and evidence_shapes
    )


def execute_shards(
    *,
    root: Path,
    binary: Path,
    output_dir: Path,
    planned: Sequence[dict[str, Any]],
    workers: int,
    shard_size: int,
    module: Any | None = None,
    native_arguments: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    shards = [list(planned[index : index + shard_size]) for index in range(0, len(planned), shard_size)]
    shard_dir = output_dir / "shards"
    pending: list[tuple[list[dict[str, Any]], Path]] = []
    paths: list[Path] = []
    for index, shard in enumerate(shards):
        path = shard_dir / f"route_pairs_{index:05d}.jsonl"
        paths.append(path)
        if not _valid_shard(path, shard):
            pending.append((shard, path))
    if workers == 1:
        if module is None:
            module = _load_native(binary)
        if native_arguments is None:
            native_arguments = _native_arguments(root)
        for shard, path in pending:
            _atomic_jsonl(path, run_native_shard(module, native_arguments, shard))
    elif pending:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_process_shard_task, str(root), str(binary), shard, str(path))
                for shard, path in pending
            ]
            for future in as_completed(futures):
                future.result()
    rows = [row for path in paths for row in _read_jsonl(path)]
    rows.sort(key=lambda row: int(row["group_index"]))
    long_wait_by_group = {
        int(row["group_index"]): bool(row["long_wait"]) for row in planned
    }
    for row in rows:
        row["long_wait"] = long_wait_by_group[int(row["group_index"])]
    return rows


def _write_report(path: Path, summary: Mapping[str, Any]) -> None:
    counts = summary["signed_causal_label_counts"]
    text = f"""# G4IRSF20 Route counterfactual campaign

This campaign reuses the G15 exact same-state clone engine with the `G20_S4_J2`
profile. Sampling is a simple event-order/long-wait stratification; it does not
introduce a hash-ranked sample or a separate checksum manifest.

Selected compact census rows are passed back as five-field deferred targets.
The former full descriptor-materialization pass is not run.

- Full-census I3 population: {summary['i3_census_count']:,}
- Screened candidates submitted: {summary['screened_candidate_count']:,}
- Screened long-wait candidates: {summary['screened_long_wait_candidate_count']:,}
- Screened H_system candidates: {summary['screened_h_system_candidate_count']:,}
- Complete eligible pairs: {summary['eligible_pair_count']:,}
- Eligible long-wait pairs: {summary['eligible_long_wait_pair_count']:,}
- Eligible H_system pairs: {summary['eligible_h_system_pair_count']:,}
- Pair failures/incomplete: {summary['ineligible_pair_count']:,}
- Labels: beneficial={counts.get('BENEFICIAL', 0):,}, neutral={counts.get('NEUTRAL_WITHIN_TOLERANCE', 0):,}, harmful={counts.get('HARMFUL', 0):,}

`NOT_APPLICABLE_ACTION_PRECONDITION_FAILED` means the cheap census candidate
was removed by exact replay screening. It is not a hard-safety failure and it
does not enter the compact training rows.

The published JSONL contains the complete pre-action local observation set and
one exact S4-versus-primary-alternative label per sampled boundary. It does not
claim that every legal edge or WAIT is labeled. The primary label is affected
runtime-segment completion, not a complete raw-bag or order objective. H_system
raw-bag TTH is a diagnostic; raw-bag or order-level benefit is not yet proven.
Absolute IDs are split/trace metadata and are not model features.
No future route, global reservation scan, full A*, or post-hoc outcome is
present in the observation sidecar. The source distribution is protected 1x.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_campaign(
    *,
    root: Path,
    binary: Path,
    output_dir: Path,
    target_groups: int = 5000,
    long_wait_target: int = 1000,
    h_system_target: int = 500,
    long_wait_seconds: float = 30.0,
    screening_oversample: float = 1.5,
    workers: int = 1,
    shard_size: int = 64,
    allow_shortfall: bool = False,
    module: Any | None = None,
    native_arguments: Sequence[Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_groups = _oversampled_target(target_groups, screening_oversample)
    candidate_long_wait = _oversampled_target(
        long_wait_target, screening_oversample
    )
    candidate_h_system = _oversampled_target(
        h_system_target, screening_oversample
    )
    resume_contract = {
        "campaign_revision": CAMPAIGN_REVISION,
        "research_profile": RESEARCH_PROFILE,
        "target_groups": target_groups,
        "long_wait_target": long_wait_target,
        "h_system_target": h_system_target,
        "long_wait_seconds": long_wait_seconds,
        "screening_oversample": screening_oversample,
        "screened_candidate_targets": {
            "groups": candidate_groups,
            "long_wait_groups": candidate_long_wait,
            "h_system_groups": candidate_h_system,
        },
        "shard_size": shard_size,
    }
    contract_path = output_dir / "resume_contract.json"
    if contract_path.is_file():
        recorded = json.loads(contract_path.read_text(encoding="utf-8"))
        if recorded != resume_contract:
            raise RuntimeError(
                "output directory belongs to different campaign parameters"
            )
    else:
        _atomic_json(contract_path, resume_contract)

    selection_path = output_dir / "route_selection.jsonl"
    if selection_path.is_file():
        plan = _read_jsonl(selection_path)
        scan_count = int(json.loads((output_dir / "census_summary.json").read_text(encoding="utf-8"))["i3_census_count"])
    else:
        if module is None:
            module = _load_native(binary)
        if native_arguments is None:
            native_arguments = _native_arguments(root)
        scan = scan_full_census(module, native_arguments)
        scan_count = sum(
            1
            for row in scan["skeletons"]
            if row.get("kind") in {"I3", "I3_NEXT_EDGE"}
        )
        plan = select_route_skeletons(
            scan,
            target_groups=candidate_groups,
            long_wait_target=candidate_long_wait,
            h_system_target=candidate_h_system,
            long_wait_seconds=long_wait_seconds,
            allow_shortfall=allow_shortfall,
        )
        _atomic_json(output_dir / "census_summary.json", {"i3_census_count": scan_count, "census_complete": True})
        _atomic_jsonl(selection_path, plan)
        del scan
        gc.collect()

    planned = deferred_plan(plan, long_wait_seconds=long_wait_seconds)

    rows = execute_shards(
        root=root,
        binary=binary,
        output_dir=output_dir,
        planned=planned,
        workers=workers,
        shard_size=shard_size,
        module=module if workers == 1 else None,
        native_arguments=native_arguments if workers == 1 else None,
    )
    _atomic_jsonl(output_dir / "route_counterfactuals.jsonl", rows)
    compact_rows = [
        compact_training_row(row)
        for row in rows
        if row.get("eligible_causal_label") is True
    ]
    _atomic_jsonl(
        output_dir / "route_counterfactual_compact.jsonl", compact_rows
    )
    labels = Counter(str(row["signed_causal_label"]) for row in rows)
    failure_reasons = Counter(
        str(row.get("failure_reason") or row.get("pair_status") or "UNKNOWN")
        for row in rows
        if row.get("eligible_causal_label") is not True
    )
    eligible_rows = [
        row for row in rows if row.get("eligible_causal_label") is True
    ]
    eligible_long_wait = sum(bool(row["long_wait"]) for row in eligible_rows)
    eligible_h_system = sum(
        row["horizon"] == "H_system" for row in eligible_rows
    )
    summary = {
        "schema": "czr005.g4irsf20.route_counterfactual_summary.v1",
        "research_profile": RESEARCH_PROFILE,
        "execution_design": {
            "campaign_revision": CAMPAIGN_REVISION,
            "deferred_target_schema": DEFERRED_TARGET_SCHEMA,
            "descriptor_materialization_stage": "SKIPPED",
            "label_scope": "AFFECTED_RUNTIME_SEGMENT_COMPLETION_PRIMARY_PAIR",
            "source_scale": 1,
            "full_legal_action_set_labeled": False,
            "wait_action_labeled": False,
            "screening_oversample": screening_oversample,
        },
        "i3_census_count": scan_count,
        "screened_candidate_count": len(rows),
        "screened_long_wait_candidate_count": sum(
            bool(row["long_wait"]) for row in rows
        ),
        "screened_h_system_candidate_count": sum(
            row["horizon"] == "H_system" for row in rows
        ),
        "eligible_pair_count": len(eligible_rows),
        "eligible_long_wait_pair_count": eligible_long_wait,
        "eligible_h_system_pair_count": eligible_h_system,
        "ineligible_pair_count": len(rows) - len(eligible_rows),
        "screening_failure_reason_counts": dict(sorted(failure_reasons.items())),
        "compact_training_group_count": len(compact_rows),
        "signed_causal_label_counts": dict(sorted(labels.items())),
        "targets": {
            "eligible_pairs": target_groups,
            "eligible_long_wait_pairs": long_wait_target,
            "eligible_h_system_pairs": h_system_target,
            "long_wait_seconds": long_wait_seconds,
            "screening_oversample": screening_oversample,
            "screened_candidates": candidate_groups,
            "screened_long_wait_candidates": candidate_long_wait,
            "screened_h_system_candidates": candidate_h_system,
        },
        "all_targets_met": (
            len(eligible_rows) >= target_groups
            and eligible_long_wait >= long_wait_target
            and eligible_h_system >= h_system_target
        ),
    }
    _atomic_json(output_dir / "route_counterfactual_summary.json", summary)
    _write_report(output_dir / "g4irsf20_route_counterfactuals.md", summary)
    if not allow_shortfall and summary["all_targets_met"] is not True:
        raise RuntimeError("counterfactual campaign completed with a target shortfall; inspect summary")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-groups", type=int, default=5000)
    parser.add_argument("--long-wait-target", type=int, default=1000)
    parser.add_argument("--h-system-target", type=int, default=500)
    parser.add_argument("--long-wait-seconds", type=float, default=30.0)
    parser.add_argument("--screening-oversample", type=float, default=1.5)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--shard-size", type=int, default=64)
    parser.add_argument("--allow-shortfall", action="store_true")
    arguments = parser.parse_args(argv)
    if min(arguments.target_groups, arguments.long_wait_target, arguments.h_system_target, arguments.workers, arguments.shard_size) <= 0:
        parser.error("targets, workers, and shard size must be positive")
    summary = run_campaign(
        root=arguments.root,
        binary=arguments.binary,
        output_dir=arguments.output_dir,
        target_groups=arguments.target_groups,
        long_wait_target=arguments.long_wait_target,
        h_system_target=arguments.h_system_target,
        long_wait_seconds=arguments.long_wait_seconds,
        screening_oversample=arguments.screening_oversample,
        workers=arguments.workers,
        shard_size=arguments.shard_size,
        allow_shortfall=arguments.allow_shortfall,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

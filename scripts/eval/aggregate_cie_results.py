#!/usr/bin/env python3
"""Aggregate CIE full-population runs without survivor-timing leakage."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


NOT_REPORTED = "NOT_REPORTED"
FORMAL_TIMING = "FORMAL_SAME_HCA_FULL_POPULATION"
TIMING_NAMES = ("min", "mean", "p95", "p99", "max")
SAFETY_ALIASES = {
    "illegal_edge_moves": ("illegal_edge_moves", "illegal_edge_move_count"),
    "failed_edge_commits": ("failed_edge_commits", "failed_edge_commit_count"),
    "physical_capacity_violations": (
        "physical_capacity_violations",
        "physical_capacity_violation_count",
    ),
    "mutual_resource_conflicts": (
        "mutual_resource_conflicts",
        "mutual_resource_conflict_count",
    ),
    "wrong_terminal_completions": (
        "wrong_terminal_completions",
        "wrong_terminal_completion_count",
    ),
    "partial_P2_commits": ("partial_P2_commits", "partial_p2_commit_count"),
    "stale_commit_accepted": (
        "stale_commit_accepted",
        "stale_commit_accepted_count",
    ),
}
_ABSENT = object()


class AggregationError(RuntimeError):
    """Raised when an input could contaminate a formal aggregate."""


def _pick(root: Mapping[str, Any], *paths: Sequence[str]) -> Any:
    for path in paths:
        value: Any = root
        for key in path:
            if not isinstance(value, Mapping) or key not in value:
                break
            value = value[key]
        else:
            return value
    return _ABSENT


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    return int(value) if isinstance(value, int) else result


def _cell(value: Any) -> Any:
    if value is _ABSENT or value is None:
        return NOT_REPORTED
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def _blank_cell(value: Any) -> Any:
    """Return a CSV-safe value while leaving unreported scaling fields blank."""

    if value is _ABSENT or value is None or value == NOT_REPORTED:
        return ""
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def _recursive_value(value: Any, aliases: Sequence[str]) -> Any:
    if isinstance(value, Mapping):
        for alias in aliases:
            if alias in value:
                return value[alias]
        for child in value.values():
            found = _recursive_value(child, aliases)
            if found is not _ABSENT:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _recursive_value(child, aliases)
            if found is not _ABSENT:
                return found
    return _ABSENT


def _reject_survivor_timing(value: Any, source: Path) -> None:
    markers = {
        "survivor_or_common_cohort_used",
        "survivor_subset_used",
        "common_completed_cohort_used",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in markers and child is True:
                raise AggregationError(f"survivor/common-cohort timing rejected: {source}")
            _reject_survivor_timing(child, source)
    elif isinstance(value, list):
        for child in value:
            _reject_survivor_timing(child, source)


def _map_name(data: Mapping[str, Any]) -> Any:
    value = _pick(data, ("map",), ("case", "map"))
    if value is not _ABSENT:
        return value
    map_id = str(_pick(data, ("map_id",), ("map_profile", "map_id")))
    if "map2" in map_id.casefold():
        return "map2"
    if "nanning" in map_id.casefold():
        return "nanning"
    return NOT_REPORTED


def _arm(data: Mapping[str, Any]) -> Any:
    value = _pick(data, ("arm",), ("algorithm", "arm"))
    if value is not _ABSENT:
        return value
    schema = str(data.get("schema", ""))
    protocol = str(data.get("protocol", ""))
    return "g31" if "g4irsf31" in schema or protocol.startswith("G31_") else NOT_REPORTED


def _cie_ablation_variant(source: Path) -> str:
    """Return the preregistered same-HCA ablation directory name, if any."""

    try:
        if (
            source.parent.parent.name.casefold() == "same_hca"
            and source.parent.parent.parent.name.casefold() == "cie_ablations"
        ):
            return source.parent.name
    except IndexError:
        pass
    return ""


def _coordination(data: Mapping[str, Any]) -> Any:
    explicit = _pick(
        data,
        ("coordination",),
        ("coordination_id",),
        ("algorithm", "coordination"),
        ("algorithm", "coordination_id"),
    )
    if explicit is not _ABSENT:
        return _cell(explicit)
    policy = _pick(data, ("request_contract", "policy"))
    if isinstance(policy, Mapping):
        keys = (
            "queue_discipline",
            "merge_grant_rule",
            "merge_grant_timing_mode",
            "event_hotpath_policy",
        )
        reported = {key: policy[key] for key in keys if key in policy}
        if reported:
            return _cell(reported)
    delta = _pick(data, ("release_protocol", "request_delta_from_g31"))
    if isinstance(delta, Mapping):
        coordination_keys = (
            "coordination",
            "queue_discipline",
            "merge_grant_rule",
            "merge_grant_timing_mode",
            "admission_mode",
            "pibt_mode",
        )
        changed = {key: delta[key] for key in coordination_keys if key in delta}
        return _cell(changed) if changed else "G31_BASE_COORDINATION_UNCHANGED"
    return NOT_REPORTED


def _capacity(data: Mapping[str, Any]) -> dict[str, Any]:
    block = _pick(data, ("paper_subjects", "fixed_horizon_capacity"))
    if isinstance(block, Mapping):
        denominator = _number(block.get("denominator_raw_bags"))
        completed = _number(block.get("completed_raw_bag_count"))
        rate = _number(block.get("completion_rate"))
        eligible = block.get("formal_fixed_horizon_eligible") is True
        finish = block.get("finish_le_std", {})
    else:
        success = _pick(data, ("outcome", "success"))
        success = success if isinstance(success, Mapping) else {}
        primary = success.get("primary_completed_raw_bags", {})
        primary = primary if isinstance(primary, Mapping) else {}
        denominator = _number(success.get("denominator_raw_bags"))
        completed = _number(primary.get("count"))
        rate = _number(primary.get("rate"))
        eligible = completed is not None and denominator is not None
        finish = success.get("finish_le_std", {})
    if denominator is not None and completed is not None and completed > denominator:
        raise AggregationError("completed_raw_bags exceeds its fixed denominator")
    if rate is None and denominator not in (None, 0) and completed is not None:
        rate = completed / denominator
    unfinished = (
        denominator - completed
        if denominator is not None and completed is not None
        else None
    )
    finish = finish if isinstance(finish, Mapping) else {}
    return {
        "capacity_eligible": eligible,
        "denominator_raw_bags": denominator,
        "completed_raw_bags": completed,
        "completion_rate": rate,
        "unfinished_raw_bags": unfinished,
        "deadline_success_count": _number(finish.get("count")),
        "deadline_success_rate": _number(finish.get("rate")),
    }


def _formal_timing(
    data: Mapping[str, Any], capacity: Mapping[str, Any], source: Path
) -> dict[str, Any]:
    blank = {f"formal_timing_{name}_seconds": None for name in TIMING_NAMES}
    timing = _pick(data, ("paper_subjects", "full_population_raw_bag_timing"))
    if not isinstance(timing, Mapping):
        return {"formal_timing_status": "TIMING_NOT_REPORTED", **blank}
    metrics = timing.get("metrics_seconds")
    if isinstance(metrics, Mapping) and timing.get("survivor_or_common_cohort_used") is not False:
        raise AggregationError(f"full-population timing provenance is not explicit: {source}")
    release = _pick(data, ("release_protocol",))
    release = release if isinstance(release, Mapping) else {}
    formal = (
        release.get("formal_same_hca_release_input") is True
        and timing.get("formal_same_hca_release_arm_eligible") is True
    )
    complete = (
        capacity.get("denominator_raw_bags") is not None
        and capacity.get("completed_raw_bags") == capacity.get("denominator_raw_bags")
        and timing.get("raw_bag_count") == capacity.get("denominator_raw_bags")
    )
    if not complete:
        return {"formal_timing_status": "INCOMPLETE_POPULATION", **blank}
    if not formal:
        return {"formal_timing_status": "NOT_FORMAL_SAME_HCA", **blank}
    series = metrics.get("paper_network_from_admission") if isinstance(metrics, Mapping) else None
    if not isinstance(series, Mapping):
        return {"formal_timing_status": "FORMAL_TIMING_NOT_REPORTED", **blank}
    values = {
        f"formal_timing_{name}_seconds": _number(
            series.get(name, series.get(f"{name}_seconds"))
        )
        for name in TIMING_NAMES
    }
    if any(value is None for value in values.values()):
        return {"formal_timing_status": "FORMAL_TIMING_INCOMPLETE", **blank}
    return {"formal_timing_status": FORMAL_TIMING, **values}


def _safety(data: Mapping[str, Any]) -> dict[str, Any]:
    scopes = [
        _pick(data, ("safety_audit",)),
        _pick(data, ("paper_subjects", "safety_audit")),
        _pick(data, ("safety",)),
        _pick(data, ("runtime", "safety")),
        _pick(data, ("runtime",)),
        _pick(data, ("summary",)),
    ]
    values: dict[str, Any] = {}
    numeric: list[float] = []
    missing = 0
    for field, aliases in SAFETY_ALIASES.items():
        found = _ABSENT
        for scope in scopes:
            if isinstance(scope, (Mapping, list)):
                found = _recursive_value(scope, aliases)
                if found is not _ABSENT:
                    break
        if found is _ABSENT or found is None:
            values[field] = NOT_REPORTED
            missing += 1
            continue
        values[field] = found
        if isinstance(found, bool):
            numeric.append(1.0 if found else 0.0)
        elif _number(found) is not None:
            numeric.append(float(found))
    if any(value != 0.0 for value in numeric):
        status = "FAIL_REPORTED_VIOLATION"
    elif missing == len(SAFETY_ALIASES):
        status = NOT_REPORTED
    elif missing:
        status = "PARTIAL_NOT_REPORTED"
    else:
        status = "PASS_REPORTED_FIELDS"
    reported_pass = _pick(data, ("safety", "pass"), ("execution_integrity", "pass"))
    reservation_conflicts = _pick(data, ("runtime", "reservation_conflicts"))
    return {
        "safety_status": status,
        "reported_integrity_or_safety_pass": _cell(reported_pass),
        "reservation_conflicts": _cell(reservation_conflicts),
        **values,
    }


def _run_row(data: Mapping[str, Any], source: Path) -> dict[str, Any]:
    _reject_survivor_timing(data, source)
    capacity = _capacity(data)
    timing = _formal_timing(data, capacity, source)
    safety = _safety(data)
    algorithm = data.get("algorithm")
    algorithm = algorithm if isinstance(algorithm, Mapping) else {}
    config = _pick(
        data,
        ("config",),
        ("algorithm", "config"),
        ("algorithm", "request_delta_from_g31"),
        ("request_contract", "policy"),
    )
    requested_sha = _pick(data, ("binary", "sha256"))
    loaded_sha = _pick(data, ("runtime", "loaded_cpp_binary_sha256"))
    binary_sha = loaded_sha if loaded_sha is not _ABSENT else requested_sha
    population = _pick(data, ("population",))
    population = population if isinstance(population, Mapping) else {}
    whole_population = _pick(
        data,
        ("population", "whole_population"),
        ("selection", "whole_population_fixed_denominator"),
    )
    row = {
        "source_file": str(source.resolve()),
        "schema": data.get("schema", NOT_REPORTED),
        "case_id": _cell(_pick(data, ("case_id",), ("case", "case_id"))),
        "map": _map_name(data),
        "scale": _cell(_pick(data, ("scale",), ("case", "scale"), ("selection", "scale"))),
        "speed_mps": _cell(
            _pick(
                data,
                ("fixed_window", "speed_mps"),
                ("case", "speed_mps"),
                ("comparison_contract", "capacity", "speed_mps"),
            )
        ),
        "arm": _arm(data),
        "arm_label": _cell(_pick(data, ("arm_label",), ("algorithm", "label"))),
        "family": _cell(_pick(data, ("family",), ("algorithm", "family"))),
        "ablation": _cell(_pick(data, ("ablation",), ("algorithm", "ablation"))),
        # Internal fields used by the two raw/pairwise outputs.  They are not
        # added to the existing summary/effect field lists, so those tables
        # retain their established schemas and meaning.
        "variant": _cie_ablation_variant(source),
        "s4_ablation": _blank_cell(_pick(data, ("algorithm", "s4_ablation"))),
        "coordination_protocol": _blank_cell(
            _pick(data, ("algorithm", "coordination_protocol"))
        ),
        "config": _cell(config),
        "release": _cell(_pick(data, ("release_protocol", "mode"))),
        "coordination": _coordination(data),
        "status": data.get("status", NOT_REPORTED),
        "whole_population": _cell(whole_population),
        "raw_bag_population": _cell(
            _pick(
                data,
                ("population", "raw_bag_count"),
                ("selection", "selected_raw_bag_count"),
            )
        ),
        "segment_population": _cell(
            _pick(
                data,
                ("population", "segment_count"),
                ("selection", "selected_segment_count"),
            )
        ),
        "binary_sha256": _cell(binary_sha),
        "requested_binary_sha256": _cell(requested_sha),
        "wall_seconds": _cell(_pick(data, ("runtime", "wall_seconds"))),
        "cpu_seconds": _blank_cell(_pick(data, ("runtime", "cpu_seconds"))),
        "event_count": _cell(_pick(data, ("runtime", "event_count"))),
        "decision_count": _blank_cell(_pick(data, ("runtime", "decision_count"))),
        "completed_segment_count": _blank_cell(
            _pick(data, ("runtime", "completed_count"))
        ),
        "failed_segment_count": _blank_cell(
            _pick(data, ("runtime", "failed_count"))
        ),
        "event_limit_reached": _blank_cell(
            _pick(data, ("runtime", "event_limit_reached"))
        ),
        "time_limit_reached": _blank_cell(
            _pick(data, ("runtime", "time_limit_reached"))
        ),
        "loop_count": _blank_cell(_pick(data, ("runtime", "loop_count"))),
        "runtime_full_astar_calls": _blank_cell(
            _pick(data, ("runtime", "runtime_full_astar_calls"))
        ),
        "scorer_runtime_global_scan_count": _blank_cell(
            _pick(data, ("runtime", "scorer_runtime_global_scan_count"))
        ),
        **capacity,
        **timing,
        **safety,
    }
    return row


def _discover(input_roots: Iterable[Path]) -> list[tuple[Path, Mapping[str, Any]]]:
    paths: dict[Path, None] = {}
    for root in input_roots:
        resolved = root.resolve(strict=True)
        candidates = [resolved] if resolved.is_file() else resolved.rglob("*.json")
        for path in candidates:
            paths[path.resolve()] = None
    runs: list[tuple[Path, Mapping[str, Any]]] = []
    for path in sorted(paths, key=lambda item: str(item).casefold()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AggregationError(f"cannot read JSON {path}: {exc}") from exc
        if not isinstance(data, Mapping) or data.get("native_execution_started") is not True:
            continue
        if not (
            isinstance(_pick(data, ("paper_subjects", "fixed_horizon_capacity")), Mapping)
            or isinstance(_pick(data, ("outcome", "success")), Mapping)
        ):
            continue
        runs.append((path, data))
    return runs


def _is_g31(row: Mapping[str, Any]) -> bool:
    fields = (row.get("arm"), row.get("arm_label"), row.get("family"))
    return any(str(value).casefold() in {"g31", "g31_s4"} for value in fields)


def _relative(candidate: Any, reference: Any) -> tuple[Any, Any]:
    left, right = _number(candidate), _number(reference)
    if left is None or right is None:
        return "", ""
    delta = left - right
    return delta, "" if right == 0 else delta / right


def _effect_columns(
    output: dict[str, Any], candidate: Mapping[str, Any], reference: Mapping[str, Any],
    key: str, prefix: str,
) -> None:
    left, right = candidate.get(key), reference.get(key)
    delta, relative = _relative(left, right)
    output[f"{prefix}_candidate"] = "" if _number(left) is None else left
    output[f"{prefix}_reference"] = "" if _number(right) is None else right
    output[f"{prefix}_delta"] = delta
    output[f"{prefix}_relative_delta"] = relative


def _effects(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    group_names = ("binary_sha256", "map", "scale", "release", "coordination")
    references: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        if _is_g31(row):
            references.setdefault(tuple(row[name] for name in group_names), []).append(row)
    effects: list[dict[str, Any]] = []
    for candidate in rows:
        if _is_g31(candidate):
            continue
        base = {
            "source_file": candidate["source_file"],
            "case_id": candidate["case_id"],
            "map": candidate["map"],
            "scale": candidate["scale"],
            "speed_mps": candidate["speed_mps"],
            "release": candidate["release"],
            "coordination": candidate["coordination"],
            "binary_sha256": candidate["binary_sha256"],
            "arm": candidate["arm"],
            "arm_label": candidate["arm_label"],
            "family": candidate["family"],
            "ablation": candidate["ablation"],
            "config": candidate["config"],
        }
        if candidate["binary_sha256"] == NOT_REPORTED:
            effects.append({**base, "comparison_status": "BINARY_NOT_REPORTED"})
            continue
        key = tuple(candidate[name] for name in group_names)
        matches = references.get(key, [])
        exact_case = [
            row for row in matches
            if row["case_id"] == candidate["case_id"]
            and row["speed_mps"] == candidate["speed_mps"]
        ]
        if len(exact_case) == 1:
            reference = exact_case[0]
        elif len(matches) == 1:
            reference = matches[0]
        else:
            status = "NO_MATCHING_G31_REFERENCE" if not matches else "AMBIGUOUS_G31_REFERENCE"
            effects.append({**base, "comparison_status": status})
            continue
        formal_timing = (
            candidate["formal_timing_status"] == FORMAL_TIMING
            and reference["formal_timing_status"] == FORMAL_TIMING
        )
        effect = {
            **base,
            "comparison_status": (
                "MATCHED_CAPACITY_AND_FORMAL_SAME_HCA_TIMING"
                if formal_timing
                else "MATCHED_CAPACITY_TIMING_NOT_ELIGIBLE"
            ),
            "reference_source_file": reference["source_file"],
            "reference_arm": reference["arm"],
        }
        _effect_columns(effect, candidate, reference, "completed_raw_bags", "capacity_completed_raw_bags")
        _effect_columns(effect, candidate, reference, "completion_rate", "capacity_completion_rate")
        _effect_columns(effect, candidate, reference, "wall_seconds", "wall_seconds")
        _effect_columns(effect, candidate, reference, "event_count", "event_count")
        for name in TIMING_NAMES:
            prefix = f"formal_timing_{name}_seconds"
            if formal_timing:
                _effect_columns(effect, candidate, reference, prefix, prefix)
            else:
                for suffix in ("candidate", "reference", "delta", "relative_delta"):
                    effect[f"{prefix}_{suffix}"] = ""
        effects.append(effect)
    return effects


def _pair_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Identity shared by a same-map ablation and its exact A4 execution."""

    return tuple(
        row.get(name)
        for name in (
            "binary_sha256",
            "case_id",
            "map",
            "scale",
            "speed_mps",
            "release",
        )
    )


def _ablation_pairwise(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Pair every formal 1x CIE ablation with same-map, same-SHA A4."""

    candidates = [
        row
        for row in rows
        if row.get("variant")
        and row.get("scale") == 1
        and row.get("release") == "same_hca"
    ]
    seen: set[tuple[Any, ...]] = set()
    for row in candidates:
        identity = (row.get("variant"), *_pair_key(row))
        if identity in seen:
            raise AggregationError(
                "duplicate same-HCA CIE ablation identity: "
                f"variant={row.get('variant')} map={row.get('map')}"
            )
        seen.add(identity)

    references: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in candidates:
        if row.get("variant") == "a4_full":
            references.setdefault(_pair_key(row), []).append(row)

    paired: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_coordination = (
            candidate.get("coordination_protocol") or candidate.get("coordination")
        )
        base = {
            "source_file": candidate.get("source_file", ""),
            "variant": candidate.get("variant", ""),
            "reference_variant": "a4_full",
            "case_id": candidate.get("case_id", ""),
            "map": candidate.get("map", ""),
            "scale": candidate.get("scale", ""),
            "speed_mps": candidate.get("speed_mps", ""),
            "release": candidate.get("release", ""),
            "candidate_coordination": candidate_coordination,
            "binary_sha256": candidate.get("binary_sha256", ""),
        }
        matches = references.get(_pair_key(candidate), [])
        if len(matches) != 1:
            paired.append(
                {
                    **base,
                    "comparison_status": (
                        "NO_SAME_SHA_A4_REFERENCE"
                        if not matches
                        else "AMBIGUOUS_SAME_SHA_A4_REFERENCE"
                    ),
                }
            )
            continue
        reference = matches[0]
        formal_timing = (
            candidate.get("formal_timing_status") == FORMAL_TIMING
            and reference.get("formal_timing_status") == FORMAL_TIMING
        )
        pair = {
            **base,
            "reference_source_file": reference.get("source_file", ""),
            "reference_coordination": (
                reference.get("coordination_protocol")
                or reference.get("coordination")
            ),
            "comparison_status": (
                "MATCHED_SAME_SHA_A4_CAPACITY_AND_FORMAL_1X_TIMING"
                if formal_timing
                else "MATCHED_SAME_SHA_A4_CAPACITY_TIMING_NOT_ELIGIBLE"
            ),
        }
        for key, prefix in (
            ("denominator_raw_bags", "capacity_denominator_raw_bags"),
            ("completed_raw_bags", "capacity_completed_raw_bags"),
            ("completion_rate", "capacity_completion_rate"),
            ("wall_seconds", "runtime_wall_seconds"),
            ("cpu_seconds", "runtime_cpu_seconds"),
            ("event_count", "runtime_event_count"),
            ("decision_count", "runtime_decision_count"),
        ):
            _effect_columns(pair, candidate, reference, key, prefix)
        for name in ("mean", "p95", "p99", "max"):
            key = f"formal_timing_{name}_seconds"
            if formal_timing:
                _effect_columns(pair, candidate, reference, key, key)
            else:
                for suffix in ("candidate", "reference", "delta", "relative_delta"):
                    pair[f"{key}_{suffix}"] = ""
        paired.append(pair)

    paired.sort(
        key=lambda row: tuple(
            str(row.get(name, "")) for name in ("map", "variant", "source_file")
        )
    )
    return paired


def _runtime_scaling(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Expose raw runtime-cost fields without inventing unavailable metrics."""

    scaling: list[dict[str, Any]] = []
    for row in rows:
        coordination = row.get("coordination_protocol") or row.get("coordination")
        scaling.append(
            {
                "source_file": _blank_cell(row.get("source_file")),
                "schema": _blank_cell(row.get("schema")),
                "case_id": _blank_cell(row.get("case_id")),
                "map": _blank_cell(row.get("map")),
                "scale": _blank_cell(row.get("scale")),
                "speed_mps": _blank_cell(row.get("speed_mps")),
                "release": _blank_cell(row.get("release")),
                "coordination": _blank_cell(coordination),
                "arm": _blank_cell(row.get("arm")),
                "arm_label": _blank_cell(row.get("arm_label")),
                "family": _blank_cell(row.get("family")),
                "variant": _blank_cell(row.get("variant")),
                "s4_ablation": _blank_cell(row.get("s4_ablation")),
                "status": _blank_cell(row.get("status")),
                "binary_sha256": _blank_cell(row.get("binary_sha256")),
                "raw_bag_population": _blank_cell(row.get("raw_bag_population")),
                "segment_population": _blank_cell(row.get("segment_population")),
                "completed_segment_count": _blank_cell(
                    row.get("completed_segment_count")
                ),
                "failed_segment_count": _blank_cell(row.get("failed_segment_count")),
                "wall_seconds": _blank_cell(row.get("wall_seconds")),
                "cpu_seconds": _blank_cell(row.get("cpu_seconds")),
                "event_count": _blank_cell(row.get("event_count")),
                "decision_count": _blank_cell(row.get("decision_count")),
                "event_limit_reached": _blank_cell(row.get("event_limit_reached")),
                "time_limit_reached": _blank_cell(row.get("time_limit_reached")),
                "loop_count": _blank_cell(row.get("loop_count")),
                "reservation_conflicts": _blank_cell(
                    row.get("reservation_conflicts")
                ),
                "runtime_full_astar_calls": _blank_cell(
                    row.get("runtime_full_astar_calls")
                ),
                "scorer_runtime_global_scan_count": _blank_cell(
                    row.get("scorer_runtime_global_scan_count")
                ),
            }
        )
    scaling.sort(
        key=lambda row: tuple(
            str(row.get(name, ""))
            for name in (
                "arm",
                "map",
                "scale",
                "release",
                "coordination",
                "variant",
                "source_file",
            )
        )
    )
    if len(scaling) != len(rows):
        raise AggregationError("runtime scaling row count drift")
    return scaling


SUMMARY_FIELDS = [
    "source_file", "schema", "case_id", "map", "scale", "speed_mps", "arm",
    "arm_label", "family", "ablation", "config", "release", "coordination",
    "status", "whole_population", "raw_bag_population", "segment_population",
    "capacity_eligible", "denominator_raw_bags", "completed_raw_bags",
    "completion_rate", "unfinished_raw_bags", "deadline_success_count",
    "deadline_success_rate", "formal_timing_status",
    *[f"formal_timing_{name}_seconds" for name in TIMING_NAMES],
    "binary_sha256", "requested_binary_sha256", "wall_seconds", "event_count",
    "safety_status",
]
SAFETY_FIELDS = [
    "source_file", "case_id", "map", "scale", "release", "coordination", "arm",
    "family", "ablation", "config", "binary_sha256", "safety_status",
    "reported_integrity_or_safety_pass", "reservation_conflicts",
    *SAFETY_ALIASES,
]
EFFECT_FIELDS = [
    "source_file", "reference_source_file", "comparison_status", "case_id", "map",
    "scale", "speed_mps", "release", "coordination", "binary_sha256", "arm",
    "arm_label", "family", "ablation", "config", "reference_arm",
    *[
        f"{metric}_{suffix}"
        for metric in (
            "capacity_completed_raw_bags", "capacity_completion_rate",
            "wall_seconds", "event_count",
            *[f"formal_timing_{name}_seconds" for name in TIMING_NAMES],
        )
        for suffix in ("candidate", "reference", "delta", "relative_delta")
    ],
]
PAIRWISE_EFFECT_METRICS = (
    "capacity_denominator_raw_bags",
    "capacity_completed_raw_bags",
    "capacity_completion_rate",
    "formal_timing_mean_seconds",
    "formal_timing_p95_seconds",
    "formal_timing_p99_seconds",
    "formal_timing_max_seconds",
    "runtime_wall_seconds",
    "runtime_cpu_seconds",
    "runtime_event_count",
    "runtime_decision_count",
)
PAIRWISE_FIELDS = [
    "source_file",
    "reference_source_file",
    "comparison_status",
    "variant",
    "reference_variant",
    "case_id",
    "map",
    "scale",
    "speed_mps",
    "release",
    "candidate_coordination",
    "reference_coordination",
    "binary_sha256",
    *[
        f"{metric}_{suffix}"
        for metric in PAIRWISE_EFFECT_METRICS
        for suffix in ("candidate", "reference", "delta", "relative_delta")
    ],
]
RUNTIME_SCALING_FIELDS = [
    "source_file",
    "schema",
    "case_id",
    "map",
    "scale",
    "speed_mps",
    "release",
    "coordination",
    "arm",
    "arm_label",
    "family",
    "variant",
    "s4_ablation",
    "status",
    "binary_sha256",
    "raw_bag_population",
    "segment_population",
    "completed_segment_count",
    "failed_segment_count",
    "wall_seconds",
    "cpu_seconds",
    "event_count",
    "decision_count",
    "event_limit_reached",
    "time_limit_reached",
    "loop_count",
    "reservation_conflicts",
    "runtime_full_astar_calls",
    "scorer_runtime_global_scan_count",
]


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    os.replace(temporary, path)


def aggregate(input_roots: Sequence[Path], output_dir: Path) -> tuple[int, int]:
    rows = [_run_row(data, path) for path, data in _discover(input_roots)]
    rows.sort(key=lambda row: tuple(str(row[key]) for key in ("map", "scale", "release", "arm", "source_file")))
    effects = _effects(rows)
    pairwise = _ablation_pairwise(rows)
    runtime_scaling = _runtime_scaling(rows)
    safety_rows = [{field: row.get(field, "") for field in SAFETY_FIELDS} for row in rows]
    _write_csv(output_dir / "cie_baseline_summary.csv", SUMMARY_FIELDS, rows)
    _write_csv(output_dir / "cie_safety_audit.csv", SAFETY_FIELDS, safety_rows)
    _write_csv(output_dir / "cie_ablation_main_effects.csv", EFFECT_FIELDS, effects)
    _write_csv(output_dir / "cie_ablation_pairwise.csv", PAIRWISE_FIELDS, pairwise)
    _write_csv(
        output_dir / "cie_runtime_scaling.csv",
        RUNTIME_SCALING_FIELDS,
        runtime_scaling,
    )
    return len(rows), len(effects)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run_count, effect_count = aggregate(args.input_root, args.output_dir)
    except (AggregationError, OSError) as exc:
        parser.error(str(exc))
    print(f"aggregated_runs={run_count} main_effect_rows={effect_count} output_dir={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

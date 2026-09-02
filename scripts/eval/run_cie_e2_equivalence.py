#!/usr/bin/env python3
"""Run and aggregate the strict 1x G31 E0/E2 compute comparison.

This is deliberately a measurement harness, not an algorithm variant.  It
builds the current G31 request through the common map adapter, disables the
optional activation counters, and changes only the existing G20 event-hotpath
policy.  A pair is called physically equivalent only when the complete,
untruncated move/hold trace and every segment terminal/timing projection agree.

The public executor does not expose a peak size for its internal event queue.
That metric is therefore reported as ``N/M`` rather than inferred from another
queue.  Peak RSS is a process-lifetime measurement and paired arms should be
launched as separate CLI processes.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import run_cie_component_activation as activation  # noqa: E402


SCHEMA_RUN = "czr005.cie_e2_equivalence.run.v2"
SCHEMA_AGGREGATE = "czr005.cie_e2_equivalence.aggregate.v2"
MAPS = ("map2", "nanning")
POLICIES = ("E0", "E2")
LOAD_FACTOR = 1.0
TRACE_LIMIT = activation.MAX_EVENTS
TIME_ABS_TOLERANCE_SECONDS = 1.0e-9
NOT_MEASURED = "N/M"

PHYSICAL_CAUSAL_EVENT_COMPONENTS = (
    "bag_release_event_count",
    "arrive_junction_event_count",
    "junction_service_complete_event_count",
    "edge_enter_event_count",
    "edge_exit_event_count",
    "fault_event_count",
    "repair_event_count",
)
PHYSICAL_CAUSAL_EVENT_TOTAL = "physical_causal_event_count_total"
STALE_EVENT_COMPONENTS = (
    "stale_arbitration_event_count",
    "merge_grant_stale_arbitration_count",
    "merge_grant_stale_wakeup_count",
)
STALE_EVENT_TOTAL = "stale_event_count_total"
WAKEUP_EVENT_METRICS = (
    "merge_grant_wakeup_scheduled_count",
    "merge_grant_wakeup_coalesced_count",
    "merge_grant_duplicate_wakeup_prevented_count",
)
BEACON_SUPPRESSION_METRICS = (
    "redundant_beacon_suppressed_count",
    "same_state_beacon_suppressed_count",
)
BEACON_SUPPRESSION_SEMANTICS = "beacon_suppression_count_semantics"

DEFAULT_NANNING_PROFILE = activation.DEFAULT_NANNING_PROFILE
DEFAULT_RESULT_ROOT = ROOT / "outputs/runtime/cie_revision/e2_equivalence"
DEFAULT_AGGREGATE = DEFAULT_RESULT_ROOT / "aggregate.json"
DEFAULT_CSV = ROOT / "outputs/tables/cie_e2_equivalence.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/cie_e2_equivalence_report.md"

Executor = Callable[..., Mapping[str, Any]]
RssReader = Callable[[], tuple[int | str, str]]


class E2EquivalenceError(RuntimeError):
    """Raised when the requested comparison violates its fixed contract."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_text(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _integer(value: Any) -> int | None:
    return value if type(value) is int else None


def _measured(source: Mapping[str, Any], key: str) -> Any:
    value = source.get(key, NOT_MEASURED)
    return NOT_MEASURED if value is None else value


def _counter_total(values: Mapping[str, Any], names: Sequence[str]) -> int | str:
    measured = [_integer(values.get(name)) for name in names]
    if any(value is None for value in measured):
        return NOT_MEASURED
    return sum(value for value in measured if value is not None)


def _beacon_suppression_count(
    summary: Mapping[str, Any], native_name: str, policy: str
) -> int | str:
    if policy == "E0":
        # The binding omits G20 counters under E0.  The policy performs no
        # suppression, so zero is a definition-level value rather than an
        # imputation from a missing runtime field.
        return 0
    return _measured(summary, native_name)


def _normalized_pair_request(request: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(request)
    normalized["g4irsf20_event_hotpath_policy"] = "E0_OR_E2"
    return normalized


def prepare_e2_request(
    *,
    map_name: str,
    policy: str,
    canonical_path: Path,
    binary: Path,
    nanning_profile_path: Path = DEFAULT_NANNING_PROFILE,
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any], dict[str, Any]]:
    """Build the current G31 request and isolate the existing E0/E2 switch."""

    if map_name not in MAPS:
        raise E2EquivalenceError(f"map must be one of {MAPS}")
    if policy not in POLICIES:
        raise E2EquivalenceError(f"policy must be one of {POLICIES}")
    rows, request, source_contract = activation.prepare_runtime_request(
        map_name=map_name,
        canonical_path=canonical_path,
        binary=binary,
        nanning_profile_path=nanning_profile_path,
        scenario=f"cie_e2_equivalence_{map_name}_1x",
    )
    request.update(
        enable_cie_component_activation=False,
        g4irsf20_event_hotpath_policy=policy,
        trace_limit=TRACE_LIMIT,
        trace_shard_count=1,
        trace_shard_index=0,
        event_trace_limit=0,
        summary_only=False,
    )
    potential = source_contract.get("potential_contract")
    gates = {
        "scorer": request.get("scorer_mode") == "S4_queue_aware_rule_only",
        # The binding's historical default is the full four-component mask;
        # current G31 requests may omit the field when using that default.
        "full_dynamic_mask": int(request.get("s4_score_component_mask", 15)) == 15,
        "service_aware_potential": isinstance(potential, Mapping)
        and potential.get("mode") == "SERVICE_AWARE_STATIC_LOCAL_POTENTIAL",
        "m3": request.get("merge_grant_rule") == "M3",
        "jit_fair": request.get("merge_grant_timing_mode")
        == "jit_fair_aging_deadline",
        "strict_descent": request.get(
            "enable_s4_local_potential_descent_guard"
        )
        is True,
        "direct_calendar": request.get(
            "enable_s4_direct_neighbor_merge_calendar_visibility"
        )
        is True,
        "goal_arrival": request.get("complete_on_goal_arrival") is True,
        "activation_disabled": request.get("enable_cie_component_activation")
        is False,
        "fixed_horizon": request.get("max_simulation_time")
        == activation.FIXED_END_EPOCH,
        "event_budget": request.get("max_events") == activation.MAX_EVENTS,
        "selected_existing_hotpath_policy": request.get(
            "g4irsf20_event_hotpath_policy"
        )
        == policy,
        "complete_decision_trace_budget": request.get("trace_limit")
        == TRACE_LIMIT,
        "single_trace_shard": request.get("trace_shard_count") == 1
        and request.get("trace_shard_index") == 0,
        "generic_event_trace_disabled": request.get("event_trace_limit") == 0,
        "bag_results_enabled": request.get("summary_only") is False,
    }
    if not all(gates.values()):
        raise E2EquivalenceError(f"G31 E0/E2 request identity failed: {gates}")
    contract = {
        "map": map_name,
        "nominal_load_factor": LOAD_FACTOR,
        "policy": policy,
        "comparison_variable": "g4irsf20_event_hotpath_policy_only",
        "node_count": len(request["node_records"]),
        "directed_edge_count": len(request["edge_records"]),
        "raw_bag_count": len({int(row["task_id"]) for row in rows}),
        "segment_count": len(rows),
        "scorer_mode": request["scorer_mode"],
        "s4_score_component_mask": int(request.get("s4_score_component_mask", 15)),
        "static_potential": "H_SA",
        "potential_contract": potential,
        "merge_grant_rule": request["merge_grant_rule"],
        "merge_grant_timing_mode": request["merge_grant_timing_mode"],
        "strict_descent": True,
        "direct_neighbor_calendar_visibility": True,
        "goal_arrival_completion": True,
        "component_activation": False,
        "fixed_end_epoch": activation.FIXED_END_EPOCH,
        "max_events": activation.MAX_EVENTS,
        "trace_limit": TRACE_LIMIT,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
        "event_trace_limit": 0,
        "identity_gates": gates,
    }
    return rows, request, contract


def _peak_rss_bytes() -> tuple[int | str, str]:
    """Return an honest process-lifetime peak, or an explicit N/M."""

    if os.name == "nt":
        try:
            import psutil

            memory = psutil.Process(os.getpid()).memory_info()
            peak = getattr(memory, "peak_wset", None)
            if type(peak) is int and peak >= 0:
                return peak, "WINDOWS_PSUTIL_PROCESS_LIFETIME_PEAK_WORKING_SET"
            return NOT_MEASURED, "PSUTIL_DOES_NOT_EXPOSE_WINDOWS_PEAK_WSET"
        except (ImportError, OSError):
            return NOT_MEASURED, "WINDOWS_PEAK_RSS_READER_UNAVAILABLE"
    try:
        import resource

        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        multiplier = 1 if sys.platform == "darwin" else 1024
        return peak * multiplier, "GETRUSAGE_PROCESS_LIFETIME_RU_MAXRSS"
    except (ImportError, OSError, ValueError):
        return NOT_MEASURED, "RU_MAXRSS_UNAVAILABLE"


def _bag_projection(
    rows: Sequence[Mapping[str, Any]],
    bags: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, bool], list[str]]:
    expected_goals = {str(row["segment_id"]): int(row["goal"]) for row in rows}
    blockers: list[str] = []
    actual_ids = [str(row.get("segment_id", "")) for row in bags]
    unique = len(set(actual_ids)) == len(actual_ids)
    if not unique:
        blockers.append("DUPLICATE_RUNTIME_SEGMENT_ID")
    projection: list[dict[str, Any]] = []
    required = (
        "task_id",
        "completed",
        "final_node",
        "arrival_time",
        "release_time",
        "admitted_time",
        "finish_time",
        "goal_completion_time_seconds",
        "failure_reason",
        "decision_count",
        "retry_count",
        "loop_count",
    )
    all_required = True
    for bag in bags:
        segment_id = str(bag.get("segment_id", ""))
        item: dict[str, Any] = {"segment_id": segment_id}
        for key in required:
            item[key] = _measured(bag, key)
            if item[key] == NOT_MEASURED:
                all_required = False
                blockers.append(f"BAG_FIELD_NOT_MEASURED:{segment_id}:{key}")
        projection.append(item)
    projection.sort(key=lambda row: row["segment_id"])
    completed_correctly = all(
        item["completed"] is not True
        or (
            item["segment_id"] in expected_goals
            and item["final_node"] == expected_goals[item["segment_id"]]
        )
        for item in projection
    )
    completed = _integer(summary.get("completed_count"))
    failed = _integer(summary.get("failed_count"))
    gates = {
        "unique_runtime_segment_ids": unique,
        "exact_segment_identity": sorted(actual_ids) == sorted(expected_goals),
        "all_terminal_fields_measured": all_required,
        "terminal_partition": completed is not None
        and failed is not None
        and completed + failed == len(rows),
        "completed_at_correct_goal": completed_correctly,
    }
    return projection, gates, blockers


def _trace_projection(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_segment_ids: Sequence[str],
) -> dict[str, Any]:
    blockers: list[str] = []
    decisions_raw = payload.get("decisions")
    holds_raw = payload.get("hold_attempts")
    decisions = decisions_raw if isinstance(decisions_raw, list) else []
    holds = holds_raw if isinstance(holds_raw, list) else []
    if not isinstance(decisions_raw, list):
        blockers.append("PAYLOAD_DECISIONS_NOT_MEASURED")
    if not isinstance(holds_raw, list):
        blockers.append("PAYLOAD_HOLD_ATTEMPTS_NOT_MEASURED")

    seen = _integer(summary.get("decision_trace_seen_count"))
    shard_seen = _integer(summary.get("decision_trace_shard_seen_count"))
    stored_moves = _integer(summary.get("decision_trace_stored_count"))
    stored_holds = _integer(summary.get("hold_trace_stored_count"))
    gates = {
        "decision_trace_not_truncated": summary.get(
            "decision_trace_truncated"
        )
        is False,
        "single_shard_echo": summary.get("trace_shard_count") == 1
        and summary.get("trace_shard_index") == 0,
        "trace_limit_echo": summary.get("trace_limit") == TRACE_LIMIT,
        "all_seen_rows_in_single_shard": seen is not None
        and shard_seen is not None
        and seen == shard_seen,
        "move_stored_count_matches": stored_moves is not None
        and stored_moves == len(decisions),
        "hold_stored_count_matches": stored_holds is not None
        and stored_holds == len(holds),
        "stored_union_is_complete": seen is not None
        and seen == len(decisions) + len(holds),
        "trace_arrays_present": isinstance(decisions_raw, list)
        and isinstance(holds_raw, list),
    }
    for name, passed in gates.items():
        if not passed:
            blockers.append(f"TRACE_GATE_FAILED:{name}")

    expected = set(expected_segment_ids)
    grouped: dict[str, list[tuple[int, dict[str, Any], dict[str, Any]]]] = {
        segment_id: [] for segment_id in expected
    }
    ordinals: set[int] = set()
    valid_rows = True
    for kind, source in (("MOVE", decisions), ("HOLD", holds)):
        for index, raw in enumerate(source):
            if not isinstance(raw, Mapping):
                valid_rows = False
                blockers.append(f"TRACE_ROW_NOT_OBJECT:{kind}:{index}")
                continue
            metadata = raw.get("metadata")
            if not isinstance(metadata, Mapping):
                valid_rows = False
                blockers.append(f"TRACE_METADATA_NOT_OBJECT:{kind}:{index}")
                continue
            ordinal = _integer(metadata.get("decision_ordinal"))
            segment_id = str(raw.get("segment_id", ""))
            event_time = _number(raw.get("event_time"))
            current = _integer(raw.get("current_node"))
            goal = _integer(raw.get("goal_node"))
            selected = raw.get("selected_next")
            selected_valid = selected is None or _integer(selected) is not None
            if (
                ordinal is None
                or ordinal in ordinals
                or segment_id not in expected
                or event_time is None
                or current is None
                or goal is None
                or not selected_valid
                or (kind == "MOVE" and selected is None)
                or (kind == "HOLD" and selected is not None)
            ):
                valid_rows = False
                blockers.append(f"INVALID_TRACE_ROW:{kind}:{index}:{segment_id}")
                continue
            ordinals.add(ordinal)
            physical = {
                "kind": kind,
                "event_time": event_time,
                "current_node": current,
                "goal_node": goal,
                "selected_next": selected,
            }
            controller = {
                **physical,
                "decision_source": _measured(raw, "decision_source"),
                "rule_reason": _measured(raw, "rule_reason"),
            }
            grouped[segment_id].append((ordinal, physical, controller))
    gates["all_trace_rows_valid_and_unique"] = valid_rows
    if not valid_rows:
        blockers.append("TRACE_ROWS_CANNOT_PROVE_COMPLETE_PHYSICAL_SEQUENCE")

    per_segment: list[dict[str, Any]] = []
    for segment_id in sorted(grouped):
        sequence = sorted(grouped[segment_id], key=lambda item: item[0])
        physical = [item[1] for item in sequence]
        controller = [item[2] for item in sequence]
        times = [float(item["event_time"]) for item in physical]
        per_segment.append(
            {
                "segment_id": segment_id,
                "attempt_count": len(sequence),
                "move_count": sum(item["kind"] == "MOVE" for item in physical),
                "hold_count": sum(item["kind"] == "HOLD" for item in physical),
                "first_event_time": min(times) if times else NOT_MEASURED,
                "last_event_time": max(times) if times else NOT_MEASURED,
                "physical_sequence_sha256": _json_sha256(physical),
                "controller_sequence_sha256": _json_sha256(controller),
            }
        )
    complete = all(gates.values())
    return {
        "complete_capture": complete,
        "gates": gates,
        "blockers": sorted(set(blockers)),
        "seen_attempt_count": _measured(summary, "decision_trace_seen_count"),
        "stored_move_count": len(decisions),
        "stored_hold_count": len(holds),
        "unique_decision_ordinal_count": len(ordinals),
        "per_segment": per_segment,
        "physical_projection_sha256": _json_sha256(
            [
                {
                    key: value
                    for key, value in item.items()
                    if key != "controller_sequence_sha256"
                }
                for item in per_segment
            ]
        ),
        "controller_projection_sha256": _json_sha256(per_segment),
        "claim_boundary": (
            "complete committed-move plus hold-attempt physical sequence; "
            "candidate/scorer internals are not part of physical equivalence"
        ),
    }


def _safety_projection(
    summary: Mapping[str, Any], bag_gates: Mapping[str, bool]
) -> dict[str, Any]:
    keys = (
        "safe_execution_pass",
        "event_limit_reached",
        "physical_fault_edge_entry_violation_count",
        "reservation_conflicts",
        "merge_grant_conservation_holds",
        "merge_grant_active_bijection_holds",
        "fault_event_count",
        "repair_event_count",
    )
    measurements = {key: _measured(summary, key) for key in keys}
    gates = {
        **dict(bag_gates),
        "native_safe_execution_pass": measurements["safe_execution_pass"] is True,
        "event_limit_not_reached": measurements["event_limit_reached"] is False,
        "physical_fault_edge_entry_violations_zero": measurements[
            "physical_fault_edge_entry_violation_count"
        ]
        == 0,
        "reservation_conflicts_zero": measurements["reservation_conflicts"] == 0,
        "merge_grant_conservation": measurements[
            "merge_grant_conservation_holds"
        ]
        is True,
        "merge_grant_active_bijection": measurements[
            "merge_grant_active_bijection_holds"
        ]
        is True,
        "stable_fault_events_zero": measurements["fault_event_count"] == 0,
        "stable_repair_events_zero": measurements["repair_event_count"] == 0,
    }
    missing = [key for key, value in measurements.items() if value == NOT_MEASURED]
    return {
        "pass": all(gates.values()),
        "gates": gates,
        "measurements": measurements,
        "not_measured": missing,
        "additional_not_measured": {
            "reverse_or_unknown_edge_use_count": {
                "value": NOT_MEASURED,
                "reason": "CURRENT_PUBLIC_RESPONSE_DOES_NOT_EXPOSE_THIS_FIELD",
            }
        },
    }


def _policy_echo_matches(summary: Mapping[str, Any], policy: str) -> bool:
    echo = summary.get("g4irsf20_event_hotpath_policy")
    return echo == policy if policy == "E2" else echo in (None, "E0")


def execute_run(
    *,
    map_name: str,
    policy: str,
    canonical_path: Path,
    binary: Path,
    nanning_profile_path: Path = DEFAULT_NANNING_PROFILE,
    dry_run: bool = False,
    executor: Executor | None = None,
    rss_reader: RssReader = _peak_rss_bytes,
) -> dict[str, Any]:
    canonical_path = canonical_path.resolve(strict=True)
    binary = binary.resolve(strict=True)
    rows, request, contract = prepare_e2_request(
        map_name=map_name,
        policy=policy,
        canonical_path=canonical_path,
        binary=binary,
        nanning_profile_path=nanning_profile_path,
    )
    request_sha256 = _json_sha256(request)
    pair_control_sha256 = _json_sha256(_normalized_pair_request(request))
    common = {
        "schema": SCHEMA_RUN,
        "status": "READY_CIE_E2_EQUIVALENCE_DRY_RUN" if dry_run else None,
        "map": map_name,
        "nominal_load_factor": LOAD_FACTOR,
        "policy": policy,
        "population": {
            "raw_bag_denominator": len({int(row["task_id"]) for row in rows}),
            "segment_count": len(rows),
            "whole_population": True,
        },
        "request_contract": contract,
        "provenance": {
            "git_commit": _git_value("rev-parse", "HEAD"),
            "git_branch": _git_value("branch", "--show-current"),
            "binary_path": str(binary),
            "binary_sha256": _file_sha256(binary),
            "canonical_path": str(canonical_path),
            "canonical_sha256": _file_sha256(canonical_path),
            "request_sha256": request_sha256,
            "pair_control_sha256": pair_control_sha256,
            "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
            "baseline_family": "G31_S4_NATIVE",
            "release_protocol": "canonical_complete_flight_population_1x",
            "coordination_protocol": "J2_M3_JIT_FAIR_AGING_DEADLINE",
            "comparison_scope": "WITHIN_MAP_E0_VS_E2_ONLY",
            "survivor_or_common_cohort_timing_used": False,
        },
        "native_execution_started": not dry_run,
    }
    if dry_run:
        return common

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**request)
    cpu_seconds = time.process_time() - cpu_started
    wall_seconds = time.perf_counter() - wall_started
    try:
        peak_rss, peak_rss_method = rss_reader()
    except Exception as exc:  # RSS is optional evidence, never a run blocker.
        peak_rss = NOT_MEASURED
        peak_rss_method = f"PEAK_RSS_READER_FAILED:{type(exc).__name__}"
    if not isinstance(payload, Mapping):
        raise E2EquivalenceError("native executor did not return an object")
    summary = payload.get("summary")
    bags_raw = payload.get("bags")
    if not isinstance(summary, Mapping) or not isinstance(bags_raw, list):
        raise E2EquivalenceError("native executor did not return summary and bags")
    if any(not isinstance(row, Mapping) for row in bags_raw):
        raise E2EquivalenceError("native executor returned a non-object bag row")
    bags = list(bags_raw)
    bag_projection, bag_gates, bag_blockers = _bag_projection(rows, bags, summary)
    trace = _trace_projection(
        payload, summary, [str(row["segment_id"]) for row in rows]
    )
    safety = _safety_projection(summary, bag_gates)
    loaded_path = summary.get("loaded_cpp_binary_path")
    expected_binary_sha256 = _file_sha256(binary)
    identity_gates = {
        "fixed_horizon_echo": summary.get("declared_max_simulation_time")
        == activation.FIXED_END_EPOCH,
        "event_budget_echo": summary.get("declared_max_events")
        == activation.MAX_EVENTS,
        "loaded_expected_binary": isinstance(loaded_path, str)
        and Path(loaded_path).resolve() == Path(request["expected_binary_path"]).resolve(),
        "loaded_expected_binary_sha256": summary.get(
            "loaded_cpp_binary_sha256"
        )
        == expected_binary_sha256,
        "scorer_mode_echo": summary.get("scorer_mode_echo")
        == request.get("scorer_mode"),
        "m3_echo": summary.get("merge_grant_rule") == "M3",
        "jit_fair_echo": summary.get("merge_grant_timing_mode")
        == "jit_fair_aging_deadline",
        "hotpath_policy_echo": _policy_echo_matches(summary, policy),
    }
    integrity_pass = safety["pass"] and all(identity_gates.values())
    blockers = list(bag_blockers) + list(trace["blockers"])
    blockers.extend(
        f"EXECUTION_IDENTITY_GATE_FAILED:{name}"
        for name, passed in identity_gates.items()
        if not passed
    )
    blockers.extend(
        f"SAFETY_GATE_FAILED:{name}"
        for name, passed in safety["gates"].items()
        if not passed
    )
    if not trace["complete_capture"]:
        status = "BLOCKED_INSUFFICIENT_TRACE"
    elif not integrity_pass:
        status = "FAILED_EXECUTION_INTEGRITY"
    else:
        status = "COMPLETE_TRACE_CAPTURE"

    physical_causal_events = {
        name: _measured(summary, name) for name in PHYSICAL_CAUSAL_EVENT_COMPONENTS
    }
    stale_events = {name: _measured(summary, name) for name in STALE_EVENT_COMPONENTS}
    wakeup_events = {name: _measured(summary, name) for name in WAKEUP_EVENT_METRICS}
    runtime = {
        "event_count": _measured(summary, "event_count"),
        "decision_count": _measured(summary, "decision_count"),
        "decision_attempt_count": _measured(
            summary, "decision_trace_seen_count"
        ),
        "congestion_beacon_update_event_count": _measured(
            summary, "congestion_beacon_update_event_count"
        ),
        "redundant_beacon_suppressed_count": _beacon_suppression_count(
            summary, "g4irsf20_redundant_beacon_suppressed_count", policy
        ),
        "same_state_beacon_suppressed_count": _beacon_suppression_count(
            summary, "g4irsf20_same_state_beacon_suppressed_count", policy
        ),
        BEACON_SUPPRESSION_SEMANTICS: (
            "DEFINITIONALLY_ZERO_UNDER_E0_POLICY;NATIVE_BINDING_OMITS_COUNTERS"
            if policy == "E0"
            else "NATIVE_E2_SUMMARY_COUNTERS"
        ),
        **physical_causal_events,
        PHYSICAL_CAUSAL_EVENT_TOTAL: _counter_total(
            physical_causal_events, PHYSICAL_CAUSAL_EVENT_COMPONENTS
        ),
        **stale_events,
        STALE_EVENT_TOTAL: _counter_total(stale_events, STALE_EVENT_COMPONENTS),
        **wakeup_events,
        "max_junction_queue_length": _measured(
            summary, "max_junction_queue_length"
        ),
        "max_source_queue_length": _measured(summary, "max_source_queue_length"),
        "event_queue_peak": NOT_MEASURED,
        "event_queue_peak_not_measured_reason": (
            "CURRENT_PUBLIC_RESPONSE_DOES_NOT_EXPOSE_EVENT_QUEUE_PEAK"
        ),
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "peak_rss_bytes": peak_rss,
        "peak_rss_method": peak_rss_method,
        "peak_rss_semantics": (
            "process-lifetime peak after native return; run each arm in a fresh "
            "CLI process for a paired comparison"
        ),
        "instrumentation_scope": (
            "complete decision/hold trace enabled identically in both arms; "
            "wall/CPU/RSS are not trace-disabled production benchmarks"
        ),
    }
    return {
        **common,
        "status": status,
        "blockers": sorted(set(blockers)),
        "execution_integrity": {
            "pass": integrity_pass,
            "identity_gates": identity_gates,
            "safety": safety,
        },
        "per_segment_terminal_timing": bag_projection,
        "full_action_attempt_trace": trace,
        "runtime_compute": runtime,
        "claim_boundary": (
            "One run captures evidence only. Physical equivalence and compute "
            "differences require the paired within-map aggregate; no cross-map "
            "or capacity ranking follows from this artifact."
        ),
    }


def _close(left: Any, right: Any) -> bool:
    if _number(left) is None or _number(right) is None:
        return left == right
    return math.isclose(
        float(left),
        float(right),
        rel_tol=0.0,
        abs_tol=TIME_ABS_TOLERANCE_SECONDS,
    )


def _compare_segments(
    left: Sequence[Mapping[str, Any]], right: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    left_by_id = {str(row["segment_id"]): row for row in left}
    right_by_id = {str(row["segment_id"]): row for row in right}
    identity = set(left_by_id) == set(right_by_id)
    timing_fields = (
        "arrival_time",
        "release_time",
        "admitted_time",
        "finish_time",
        "goal_completion_time_seconds",
    )
    exact_fields = (
        "task_id",
        "completed",
        "final_node",
        "failure_reason",
        "decision_count",
        "retry_count",
        "loop_count",
    )
    mismatch_count = 0
    timing_mismatch_count = 0
    max_abs_time_difference = 0.0
    examples: list[str] = []
    for segment_id in sorted(set(left_by_id) | set(right_by_id)):
        a = left_by_id.get(segment_id)
        b = right_by_id.get(segment_id)
        if a is None or b is None:
            mismatch_count += 1
            examples.append(f"{segment_id}:missing_arm")
            continue
        for field in exact_fields:
            if a.get(field) != b.get(field):
                mismatch_count += 1
                if len(examples) < 10:
                    examples.append(f"{segment_id}:{field}")
        for field in timing_fields:
            if not _close(a.get(field), b.get(field)):
                timing_mismatch_count += 1
                if len(examples) < 10:
                    examples.append(f"{segment_id}:{field}")
            av = _number(a.get(field))
            bv = _number(b.get(field))
            if av is not None and bv is not None:
                max_abs_time_difference = max(
                    max_abs_time_difference, abs(float(av) - float(bv))
                )
    return {
        "pass": identity and mismatch_count == 0 and timing_mismatch_count == 0,
        "exact_segment_identity": identity,
        "non_timing_mismatch_count": mismatch_count,
        "timing_mismatch_count": timing_mismatch_count,
        "max_abs_time_difference_seconds": max_abs_time_difference,
        "mismatch_examples": examples,
    }


def _compare_traces(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    left_rows = {
        str(row["segment_id"]): row for row in left.get("per_segment", [])
    }
    right_rows = {
        str(row["segment_id"]): row for row in right.get("per_segment", [])
    }
    identity = set(left_rows) == set(right_rows)
    physical_mismatches = 0
    controller_mismatches = 0
    examples: list[str] = []
    for segment_id in sorted(set(left_rows) | set(right_rows)):
        a = left_rows.get(segment_id)
        b = right_rows.get(segment_id)
        if a is None or b is None:
            physical_mismatches += 1
            examples.append(f"{segment_id}:missing_arm")
            continue
        physical_fields = (
            "attempt_count",
            "move_count",
            "hold_count",
            "physical_sequence_sha256",
        )
        if any(a.get(field) != b.get(field) for field in physical_fields):
            physical_mismatches += 1
            if len(examples) < 10:
                examples.append(f"{segment_id}:physical_sequence")
        if a.get("controller_sequence_sha256") != b.get(
            "controller_sequence_sha256"
        ):
            controller_mismatches += 1
    return {
        "pass": identity and physical_mismatches == 0,
        "exact_segment_identity": identity,
        "physical_sequence_mismatch_count": physical_mismatches,
        "controller_diagnostic_mismatch_count": controller_mismatches,
        "mismatch_examples": examples,
    }


COMPUTE_METRICS = (
    "event_count",
    "decision_count",
    "decision_attempt_count",
    "congestion_beacon_update_event_count",
    *BEACON_SUPPRESSION_METRICS,
    *PHYSICAL_CAUSAL_EVENT_COMPONENTS,
    PHYSICAL_CAUSAL_EVENT_TOTAL,
    *STALE_EVENT_COMPONENTS,
    STALE_EVENT_TOTAL,
    *WAKEUP_EVENT_METRICS,
    "max_junction_queue_length",
    "max_source_queue_length",
    "event_queue_peak",
    "wall_seconds",
    "cpu_seconds",
    "peak_rss_bytes",
)

CSV_RUNTIME_FIELDS = (*COMPUTE_METRICS, BEACON_SUPPRESSION_SEMANTICS)


def _compute_comparison(e0: Mapping[str, Any], e2: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric in COMPUTE_METRICS:
        baseline = e0.get(metric, NOT_MEASURED)
        treatment = e2.get(metric, NOT_MEASURED)
        left = _number(baseline)
        right = _number(treatment)
        if left is None or right is None:
            delta: Any = NOT_MEASURED
            reduction: Any = NOT_MEASURED
        else:
            delta = float(right) - float(left)
            if float(left) == 0.0:
                reduction = 0.0 if float(right) == 0.0 else NOT_MEASURED
            else:
                reduction = (float(left) - float(right)) / float(left)
        result[metric] = {
            "E0": baseline,
            "E2": treatment,
            "E2_minus_E0": delta,
            "E2_reduction_fraction": reduction,
        }
    return result


def _physical_causal_event_comparison(
    e0: Mapping[str, Any], e2: Mapping[str, Any]
) -> dict[str, Any]:
    fields = (*PHYSICAL_CAUSAL_EVENT_COMPONENTS, PHYSICAL_CAUSAL_EVENT_TOTAL)
    counts: dict[str, dict[str, Any]] = {}
    mismatched_fields: list[str] = []
    all_fields_measured = True
    for name in fields:
        left = _integer(e0.get(name))
        right = _integer(e2.get(name))
        measured = left is not None and right is not None
        equal = measured and left == right
        counts[name] = {
            "E0": left if left is not None else NOT_MEASURED,
            "E2": right if right is not None else NOT_MEASURED,
            "equal": equal,
        }
        all_fields_measured = all_fields_measured and measured
        if not equal:
            mismatched_fields.append(name)

    e0_component_values = [
        _integer(e0.get(name)) for name in PHYSICAL_CAUSAL_EVENT_COMPONENTS
    ]
    e2_component_values = [
        _integer(e2.get(name)) for name in PHYSICAL_CAUSAL_EVENT_COMPONENTS
    ]
    e0_total = _integer(e0.get(PHYSICAL_CAUSAL_EVENT_TOTAL))
    e2_total = _integer(e2.get(PHYSICAL_CAUSAL_EVENT_TOTAL))
    e0_total_consistent = (
        e0_total is not None
        and all(value is not None for value in e0_component_values)
        and e0_total == sum(value for value in e0_component_values if value is not None)
    )
    e2_total_consistent = (
        e2_total is not None
        and all(value is not None for value in e2_component_values)
        and e2_total == sum(value for value in e2_component_values if value is not None)
    )
    passed = (
        all_fields_measured
        and not mismatched_fields
        and e0_total_consistent
        and e2_total_consistent
    )
    return {
        "pass": passed,
        "all_fields_measured": all_fields_measured,
        "E0_total_consistent": e0_total_consistent,
        "E2_total_consistent": e2_total_consistent,
        "mismatched_fields": mismatched_fields,
        "counts": counts,
        "claim_boundary": (
            "Only physical-causal event components are an equivalence diagnostic; "
            "stale and wakeup counters are compute telemetry and are not gates."
        ),
    }


def _pair_result(map_name: str, e0: Mapping[str, Any], e2: Mapping[str, Any]) -> dict[str, Any]:
    terminal = _compare_segments(
        e0.get("per_segment_terminal_timing", []),
        e2.get("per_segment_terminal_timing", []),
    )
    traces = _compare_traces(
        e0.get("full_action_attempt_trace", {}),
        e2.get("full_action_attempt_trace", {}),
    )
    e0_safety = e0.get("execution_integrity", {}).get("safety", {})
    e2_safety = e2.get("execution_integrity", {}).get("safety", {})
    safety_equal = e0_safety.get("measurements") == e2_safety.get("measurements")
    physical_causal_events = _physical_causal_event_comparison(
        e0.get("runtime_compute", {}), e2.get("runtime_compute", {})
    )
    e0_pair_hash = e0.get("provenance", {}).get("pair_control_sha256")
    e2_pair_hash = e2.get("provenance", {}).get("pair_control_sha256")
    e0_provenance = e0.get("provenance", {})
    e2_provenance = e2.get("provenance", {})

    def same_nonempty_provenance_value(name: str, *, sha256: bool = False) -> bool:
        left = e0_provenance.get(name)
        right = e2_provenance.get(name)
        if not isinstance(left, str) or not isinstance(right, str):
            return False
        if not left or left == "UNAVAILABLE" or left != right:
            return False
        return len(left) == 64 if sha256 else True

    gates = {
        "both_complete_trace_capture": e0.get("status")
        == "COMPLETE_TRACE_CAPTURE"
        and e2.get("status") == "COMPLETE_TRACE_CAPTURE",
        "same_pair_control_request": isinstance(e0_pair_hash, str)
        and bool(e0_pair_hash)
        and e0_pair_hash == e2_pair_hash,
        "same_git_commit": same_nonempty_provenance_value("git_commit"),
        "same_binary_sha256": same_nonempty_provenance_value(
            "binary_sha256", sha256=True
        ),
        "same_canonical_sha256": same_nonempty_provenance_value(
            "canonical_sha256", sha256=True
        ),
        "same_executor_identity": same_nonempty_provenance_value(
            "executor_identity"
        ),
        "same_map_and_1x": e0.get("map") == e2.get("map") == map_name
        and e0.get("nominal_load_factor")
        == e2.get("nominal_load_factor")
        == LOAD_FACTOR,
        "complete_untruncated_trace_both": e0.get(
            "full_action_attempt_trace", {}
        ).get("complete_capture")
        is True
        and e2.get("full_action_attempt_trace", {}).get("complete_capture") is True,
        "terminal_and_timing_equal": terminal["pass"],
        "full_physical_action_attempt_sequence_equal": traces["pass"],
        "physical_causal_event_counts_equal": physical_causal_events["pass"],
        "safety_pass_both": e0_safety.get("pass") is True
        and e2_safety.get("pass") is True,
        "safety_measurements_equal": safety_equal,
    }
    if not gates["complete_untruncated_trace_both"]:
        status = "BLOCKED_INSUFFICIENT_TRACE"
    elif all(gates.values()):
        status = "STRICT_PHYSICAL_EQUIVALENCE_PASS"
    else:
        status = "STRICT_PHYSICAL_EQUIVALENCE_FAIL"
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "map": map_name,
        "status": status,
        "strict_physical_equivalence": status
        == "STRICT_PHYSICAL_EQUIVALENCE_PASS",
        "gates": gates,
        "blockers": blockers,
        "terminal_timing_comparison": terminal,
        "action_attempt_trace_comparison": traces,
        "physical_causal_event_comparison": physical_causal_events,
        "compute_comparison": _compute_comparison(
            e0.get("runtime_compute", {}), e2.get("runtime_compute", {})
        ),
        "claim_boundary": (
            "Within-map G31 E0/E2 1x physical equivalence and compute only; "
            "wall/CPU/RSS are descriptive single-run measurements."
        ),
    }


def _csv_rows(
    pairs: Sequence[Mapping[str, Any]], runs: Mapping[tuple[str, str], Mapping[str, Any]]
) -> list[dict[str, Any]]:
    pair_by_map = {str(pair["map"]): pair for pair in pairs}
    rows: list[dict[str, Any]] = []
    for map_name in MAPS:
        pair = pair_by_map.get(map_name)
        if pair is None:
            continue
        for policy in POLICIES:
            run = runs[(map_name, policy)]
            runtime = run.get("runtime_compute", {})
            row = {
                "map": map_name,
                "load_factor": LOAD_FACTOR,
                "policy": policy,
                "run_status": run.get("status"),
                "pair_status": pair.get("status"),
                "strict_physical_equivalence": pair.get(
                    "strict_physical_equivalence"
                ),
                "pair_control_sha256": run.get("provenance", {}).get(
                    "pair_control_sha256"
                ),
            }
            row.update(
                {
                    metric: runtime.get(metric, NOT_MEASURED)
                    for metric in CSV_RUNTIME_FIELDS
                }
            )
            rows.append(row)
    return rows


def aggregate_results(
    results: Sequence[Mapping[str, Any]],
    *,
    expected_maps: Sequence[str] = MAPS,
) -> dict[str, Any]:
    runs: dict[tuple[str, str], Mapping[str, Any]] = {}
    for result in results:
        if result.get("schema") != SCHEMA_RUN:
            raise E2EquivalenceError("aggregate input schema mismatch")
        key = (str(result.get("map")), str(result.get("policy")))
        if key[0] not in expected_maps or key[1] not in POLICIES:
            raise E2EquivalenceError(f"unregistered E0/E2 cell: {key}")
        if key in runs:
            raise E2EquivalenceError(f"duplicate E0/E2 cell: {key}")
        runs[key] = result
    missing = [
        f"{map_name}:{policy}"
        for map_name in expected_maps
        for policy in POLICIES
        if (map_name, policy) not in runs
    ]
    pairs = [
        _pair_result(map_name, runs[(map_name, "E0")], runs[(map_name, "E2")])
        for map_name in expected_maps
        if (map_name, "E0") in runs and (map_name, "E2") in runs
    ]
    if missing:
        status = "INCOMPLETE_REQUIRED_PAIRS"
    elif all(pair["status"] == "STRICT_PHYSICAL_EQUIVALENCE_PASS" for pair in pairs):
        status = "COMPLETE_STRICT_PHYSICAL_EQUIVALENCE"
    elif any(pair["status"] == "BLOCKED_INSUFFICIENT_TRACE" for pair in pairs):
        status = "BLOCKED_INSUFFICIENT_TRACE"
    else:
        status = "PHYSICAL_EQUIVALENCE_FAILED"
    return {
        "schema": SCHEMA_AGGREGATE,
        "status": status,
        "required_maps": list(expected_maps),
        "required_policies": list(POLICIES),
        "missing_cells": missing,
        "pairs": pairs,
        "rows": _csv_rows(pairs, runs),
        "measurement_limitations": {
            "event_queue_peak": (
                "N/M: current public response does not expose event-queue peak"
            ),
            "beacon_suppression_E0": (
                "definitionally zero under E0; native binding omits G20 "
                "suppression counters for that policy"
            ),
            "physical_causal_event_total": (
                "sum of release, arrival, service-complete, edge-enter, "
                "edge-exit, fault and repair event counts"
            ),
            "stale_and_wakeup_counters": (
                "paired compute diagnostics only; they are not physical-"
                "equivalence gates"
            ),
            "peak_rss": (
                "process-lifetime peak; arms must be separate CLI processes"
            ),
            "runtime_repeats": (
                "single-run descriptive compute values; no variance claim"
            ),
            "instrumentation": (
                "complete action/hold trace enabled in both arms; wall/CPU/RSS "
                "are not trace-disabled production benchmarks"
            ),
        },
        "claim_boundary": (
            "No cross-protocol ranking, capacity improvement, or cross-map "
            "generalization is supported by this E0/E2 compute specialty."
        ),
    }


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _report_text(aggregate: Mapping[str, Any]) -> str:
    lines = [
        "# CIE E2 strict physical-equivalence and compute specialty",
        "",
        f"Status: `{aggregate['status']}`.",
        "",
        "| Map | Pair status | Physical equivalence | E0 events | E2 events | "
        "Event reduction | E0 wall s | E2 wall s |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for pair in aggregate["pairs"]:
        compute = pair["compute_comparison"]
        events = compute["event_count"]
        wall = compute["wall_seconds"]
        lines.append(
            f"| {pair['map']} | {pair['status']} | "
            f"{pair['strict_physical_equivalence']} | {events['E0']} | "
            f"{events['E2']} | {events['E2_reduction_fraction']} | "
            f"{wall['E0']} | {wall['E2']} |"
        )
    lines.extend(
        [
            "",
            "## Physical-causal event count audit",
            "",
            "Each count is shown as `E0 / E2`.",
            "",
            "| Map | Release | Arrive | Service complete | Edge enter | "
            "Edge exit | Fault | Repair | Total | Equality gate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for pair in aggregate["pairs"]:
        compute = pair["compute_comparison"]

        def paired(metric: str) -> str:
            values = compute[metric]
            return f"{values['E0']} / {values['E2']}"

        lines.append(
            f"| {pair['map']} | {paired('bag_release_event_count')} | "
            f"{paired('arrive_junction_event_count')} | "
            f"{paired('junction_service_complete_event_count')} | "
            f"{paired('edge_enter_event_count')} | "
            f"{paired('edge_exit_event_count')} | {paired('fault_event_count')} | "
            f"{paired('repair_event_count')} | "
            f"{paired(PHYSICAL_CAUSAL_EVENT_TOTAL)} | "
            f"{pair['gates']['physical_causal_event_counts_equal']} |"
        )
    lines.extend(
        [
            "",
            "The physical-causal total is the sum of release, arrival, "
            "service-complete, edge-enter, edge-exit, fault and repair events. "
            "Equality of these components is a strict paired diagnostic gate.",
            "",
            "## Beacon, stale-event and wakeup telemetry",
            "",
            "Each count is shown as `E0 / E2`.",
            "",
            "| Map | Redundant beacon suppressed | Same-state beacon suppressed | "
            "Stale arbitration | Merge stale arbitration | Merge stale wakeup | "
            "Stale total | Wakeup scheduled | Wakeup coalesced | "
            "Duplicate wakeup prevented |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for pair in aggregate["pairs"]:
        compute = pair["compute_comparison"]

        def paired(metric: str) -> str:
            values = compute[metric]
            return f"{values['E0']} / {values['E2']}"

        lines.append(
            f"| {pair['map']} | {paired('redundant_beacon_suppressed_count')} | "
            f"{paired('same_state_beacon_suppressed_count')} | "
            f"{paired('stale_arbitration_event_count')} | "
            f"{paired('merge_grant_stale_arbitration_count')} | "
            f"{paired('merge_grant_stale_wakeup_count')} | "
            f"{paired(STALE_EVENT_TOTAL)} | "
            f"{paired('merge_grant_wakeup_scheduled_count')} | "
            f"{paired('merge_grant_wakeup_coalesced_count')} | "
            f"{paired('merge_grant_duplicate_wakeup_prevented_count')} |"
        )
    lines.extend(
        [
            "",
            "E0 performs no G20 beacon suppression, so both E0 suppression "
            "counts are definitionally zero; the native binding omits those "
            "counters under E0. Stale and wakeup counts are paired compute "
            "diagnostics and are not physical-equivalence gates.",
            "",
            "Strict equivalence requires identical per-segment terminal states, "
            "completion/admission/release times (absolute tolerance 1e-9 s), and "
            "the complete untruncated move/hold physical sequence.",
            "",
            "`event_queue_peak` is `N/M`: the current public executor response "
            "does not expose that quantity. Junction/source queue peaks are not "
            "used as substitutes. Wall, CPU, and process-lifetime peak RSS are "
            "descriptive single-run values under complete-trace instrumentation, "
            "not variance-controlled production speed claims.",
            "",
            "This specialty compares E0 and E2 only within the same map, current "
            "G31 coordination/release protocol, and 1x workload. It does not "
            "support a cross-protocol ranking or capacity claim.",
            "",
        ]
    )
    if aggregate["missing_cells"]:
        lines.append("Missing cells: " + ", ".join(aggregate["missing_cells"]) + ".")
        lines.append("")
    return "\n".join(lines)


def _read_results(paths: Sequence[Path], result_root: Path) -> list[Mapping[str, Any]]:
    candidates = list(paths)
    if not candidates and result_root.exists():
        candidates = sorted(result_root.rglob("*.json"))
    results: list[Mapping[str, Any]] = []
    for path in candidates:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, Mapping) and value.get("schema") == SCHEMA_RUN:
            results.append(value)
    return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--map", choices=MAPS, required=True)
    run.add_argument("--policy", choices=POLICIES, required=True)
    run.add_argument("--canonical", type=Path, required=True)
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--nanning-map-profile", type=Path, default=DEFAULT_NANNING_PROFILE)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--force", action="store_true")

    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("--result", type=Path, action="append", default=[])
    aggregate.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    aggregate.add_argument("--aggregate-json", type=Path, default=DEFAULT_AGGREGATE)
    aggregate.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    aggregate.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        output = _rooted(args.output)
        if output.exists() and not args.force:
            raise E2EquivalenceError(f"output exists; pass --force: {output}")
        result = execute_run(
            map_name=args.map,
            policy=args.policy,
            canonical_path=_rooted(args.canonical),
            binary=_rooted(args.binary),
            nanning_profile_path=_rooted(args.nanning_map_profile),
            dry_run=args.dry_run,
        )
        _atomic_json(output, result)
        print(json.dumps({"status": result["status"], "output": str(output)}))
        return 0 if result["status"] in {
            "READY_CIE_E2_EQUIVALENCE_DRY_RUN",
            "COMPLETE_TRACE_CAPTURE",
        } else 2

    paths = [_rooted(path) for path in args.result]
    aggregate = aggregate_results(
        _read_results(paths, _rooted(args.result_root))
    )
    _atomic_json(_rooted(args.aggregate_json), aggregate)
    _atomic_text(_rooted(args.csv), _csv_text(aggregate["rows"]))
    _atomic_text(_rooted(args.report), _report_text(aggregate))
    print(
        json.dumps(
            {
                "status": aggregate["status"],
                "pair_count": len(aggregate["pairs"]),
                "report": str(_rooted(args.report)),
            }
        )
    )
    return 0 if aggregate["status"] == "COMPLETE_STRICT_PHYSICAL_EQUIVALENCE" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (E2EquivalenceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CIE E2 equivalence failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

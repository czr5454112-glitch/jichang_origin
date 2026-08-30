#!/usr/bin/env python3
"""Run the frozen V3R13 Candidate-A pre-Stage-2 action gate.

The cohort is intentionally small.  It exercises only the DIRECT/J2
mixed-origin action seam and the controls registered before implementation.
Importing this module neither loads the native extension nor writes evidence;
tests can inject an executor and inspect the complete decision in memory.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import g4irsf31_map_adapter as map_adapter  # noqa: E402
from scripts.eval import (  # noqa: E402
    run_g4irsf32_v3r2_external_commit_local_virtual_shadow as historical,
)


PROTOCOL_ID = "G4IRSF32_V3R13_CANDIDATE_A_CLOSED_LOOP_STAGE2_20260829"
SCHEMA = "czr005.g4irsf32.candidate_a_closed_loop_stage01.v3r13"
PASS = "PASS_V3R13_CANDIDATE_A_PRE_STAGE2_ACTION_GATE"
NO_GO = "NO_GO_V3R13_CANDIDATE_A_PRE_STAGE2_ACTION_GATE"
OUTPUT_JSON = ROOT / "outputs/tables/g4irsf32_v3r13_closed_loop_stage01.json"
OUTPUT_MD = ROOT / "outputs/reports/g4irsf32_v3r13_closed_loop_stage01.md"
PREREGISTRATION_PATH = (
    ROOT / "docs/G4IRSF32_v3r13_candidate_a_closed_loop_stage2_preregistration.md"
)

NS = "source_aware_destination_service_"
ACTION_REASON = "source_closed_loop_future_slot"
SERVICE_NODE = 1
SERVICE_SECONDS = 1.0
TRACE_LIMIT = 200_000
RESOURCE_RATIO_LIMIT = 1.10
MODES = ("off", "shadow", "closed_loop")

Executor = Callable[..., Mapping[str, Any]]


@dataclass(frozen=True)
class ActionCase:
    case_id: str
    topology: str
    rows: tuple[tuple[str, int, float, float, int, str], ...]
    expected_action: bool | None
    control_kind: str | None = None
    local_task_id: int | None = None
    priority_external_task_id: int | None = None

    @property
    def scenario(self) -> str:
        return f"g4irsf32_v3r13_{self.case_id}"

    @property
    def j2(self) -> bool:
        return self.topology == "j2"


def _row(
    segment_id: str,
    task_id: int,
    release: float,
    deadline: float,
    start: int,
    source: str,
) -> tuple[str, int, float, float, int, str]:
    return (segment_id, task_id, release, deadline, start, source)


def registered_cases() -> tuple[ActionCase, ...]:
    direct = (
        _row("direct:blocker", 33_013_000, 0.0, 100.0, 0, "external"),
        _row("direct:local", 33_013_001, 0.01, 20.0, 1, "local"),
        _row("direct:contender", 33_013_002, 0.02, 100.0, 0, "external"),
    )
    j2_action = (
        _row("j2:blocker", 33_013_100, 0.0, 100.0, 0, "external"),
        _row("j2:local_urgent", 33_013_101, 0.01, 20.0, 1, "local"),
        _row("j2:external_later", 33_013_102, 0.005, 100.0, 4, "external"),
    )
    j2_reverse = (
        _row("j2_reverse:blocker", 33_013_200, 0.0, 100.0, 0, "external"),
        _row("j2_reverse:local_later", 33_013_201, 0.01, 100.0, 1, "local"),
        _row("j2_reverse:external_urgent", 33_013_202, 0.005, 20.0, 4, "external"),
    )
    no_local = (
        _row("no_local:e0", 33_013_300, 0.0, 100.0, 0, "external"),
        _row("no_local:e1", 33_013_301, 0.02, 100.0, 0, "external"),
    )
    no_external = (
        _row("no_external:l0", 33_013_400, 0.0, 100.0, 1, "local"),
        _row("no_external:l1", 33_013_401, 0.01, 100.0, 1, "local"),
    )
    immediate = (
        _row("immediate:local", 33_013_500, 0.0, 100.0, 1, "local"),
        _row("immediate:future_external", 33_013_501, 2.0, 100.0, 0, "external"),
    )
    future_core = (
        _row("future:blocker", 33_013_600, 0.0, 100.0, 0, "external"),
        _row("future:local", 33_013_601, 0.01, 20.0, 1, "local"),
        _row("future:contender", 33_013_602, 0.02, 100.0, 0, "external"),
    )
    future_base = future_core + (
        _row("future:changed", 33_013_603, 5.0, 100.0, 0, "external"),
    )
    future_perturbed = future_core + (
        _row("future:changed", 33_013_603, 9.0, 100.0, 0, "external"),
    )
    return (
        ActionCase(
            "direct_mixed_contention",
            "direct",
            direct,
            True,
            local_task_id=33_013_001,
        ),
        ActionCase(
            "j2_mixed_contention",
            "j2",
            j2_action,
            True,
            local_task_id=33_013_101,
        ),
        ActionCase(
            "j2_reverse_priority_external",
            "j2",
            j2_reverse,
            None,
            control_kind="reverse_priority",
            local_task_id=33_013_201,
            priority_external_task_id=33_013_202,
        ),
        ActionCase("no_local", "direct", no_local, False, "no_local"),
        ActionCase("no_external", "direct", no_external, False, "no_external"),
        ActionCase(
            "immediately_available",
            "direct",
            immediate,
            False,
            "immediately_available",
        ),
        ActionCase(
            "future_release_base",
            "direct",
            future_base,
            True,
            "future_release_base",
            local_task_id=33_013_601,
        ),
        ActionCase(
            "future_release_perturbed",
            "direct",
            future_perturbed,
            True,
            "future_release_perturbed",
            local_task_id=33_013_601,
        ),
    )


def motif_profile(case: ActionCase) -> map_adapter.RuntimeMapProfile:
    nodes: tuple[tuple[Any, ...], ...] = (
        (0, 7, 0.0, 0, 0, (1,)),
        (1, 1, SERVICE_SECONDS, 1, 0, (2,)),
        (2, 4, 0.0, 2, 0, (3,)),
        (3, 2, 0.0, 3, 0, ()),
    )
    edges: tuple[tuple[Any, ...], ...] = (
        (0, 1, 0.05, 1.0),
        (1, 2, 0.05, 1.0),
        (2, 3, 0.05, 1.0),
    )
    starts = (0, 1)
    storage = (0,)
    if case.j2:
        nodes += ((4, 7, 0.0, 0, 1, (1,)),)
        edges += ((4, 1, 0.05, 1.0),)
        starts = (0, 1, 4)
        storage = (0, 4)
    return map_adapter.RuntimeMapProfile(
        name=case.scenario,
        source_path=PREREGISTRATION_PATH,
        node_records=nodes,
        edge_records=edges,
        start_nodes=starts,
        goal_nodes=(3,),
        storage_source_nodes=storage,
    )


def bag_rows(case: ActionCase) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": segment_id,
            "task_id": task_id,
            "pass_time": release,
            "std": deadline,
            "start": start,
            "goal": 3,
            "source": source,
        }
        for segment_id, task_id, release, deadline, start, source in case.rows
    ]


def _without_extension(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in request.items()
        if key not in {
            "source_aware_destination_service_mode",
            "source_aware_destination_service_trace_limit",
        }
    }


def _validate_g31_call_shape(request: Mapping[str, Any]) -> None:
    extension = {
        "source_aware_destination_service_mode",
        "source_aware_destination_service_trace_limit",
    }
    locator = set(historical.REQUEST_BINARY_LOCATOR_KEYS) & set(request)
    expected_keys = (
        set(historical.REQUEST_PROJECTION)
        | set(historical.REQUEST_DATA_KEYS)
        | locator
    ) - extension
    if set(request) != expected_keys:
        raise ValueError("default-off request no longer matches the frozen G31 call shape")
    for key, expected in historical.REQUEST_PROJECTION.items():
        if key not in extension and request.get(key) != expected:
            raise ValueError(f"default-off request changed frozen field {key!r}")


def build_case_request(
    case: ActionCase,
    *,
    mode: str,
    binary: Path | None = None,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unsupported V3R13 mode: {mode!r}")
    profile = motif_profile(case)
    request, potential = map_adapter.build_s4_request(
        profile,
        bag_rows(case),
        binary=binary,
        scenario=case.scenario,
        max_events=2_000_000,
        max_simulation_time=-1.0,
        trace_limit=200_000,
        event_trace_limit=200_000,
        summary_only=False,
        edge_speed_mps=None,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
        complete_on_goal_arrival=True,
    )
    if (
        potential.get("runtime_full_astar_required") is not False
        or potential.get("future_route_materialized") is not False
        or potential.get("global_reservation_table_required") is not False
    ):
        raise ValueError(f"{case.case_id} has a non-local static potential")
    request["fault_windows"] = []
    # Omitted mode is the actual default-off arm.  Only the two G32 modes add
    # the narrow append-only request fields.
    if mode != "off":
        request.update(
            source_aware_destination_service_mode=mode,
            source_aware_destination_service_trace_limit=TRACE_LIMIT,
        )
    if mode == "off":
        _validate_g31_call_shape(request)
    return request


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be a sequence of mappings")
    return list(value)


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _finite(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


NONDETERMINISTIC_SUMMARY_KEYS = frozenset(
    {
        "runtime_seconds",
        "event_throughput_per_second",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
        "cpp_internal_accounted_bytes",
        "internal_state_bytes",
        "loaded_cpp_binary_path",
        "loaded_cpp_binary_sha256",
    }
)


def ordinary_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only runtime identity/timing and the append-only G32 surface."""
    projected: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"loaded_cpp_binary_path", "loaded_cpp_binary_sha256", "binary"}:
            continue
        if isinstance(key, str) and key.startswith(NS):
            continue
        if key == "summary":
            summary = _mapping(value, "payload.summary")
            projected[key] = {
                name: item
                for name, item in summary.items()
                if name not in NONDETERMINISTIC_SUMMARY_KEYS
                and not (isinstance(name, str) and name.startswith(NS))
            }
        elif key == "trace_context":
            context = _mapping(value, "payload.trace_context")
            projected[key] = {
                name: item
                for name, item in context.items()
                if not (isinstance(name, str) and name.startswith(NS))
            }
        else:
            projected[key] = value
    return projected


def extension_absent(payload: Mapping[str, Any]) -> bool:
    summary = _mapping(payload.get("summary"), "payload.summary")
    context = _mapping(payload.get("trace_context", {}), "payload.trace_context")
    return not any(
        isinstance(key, str) and key.startswith(NS)
        for mapping in (payload, summary, context)
        for key in mapping
    )


SAFETY_ZERO_KEYS = (
    "failed_count",
    "reservation_conflicts",
    "physical_fault_edge_entry_violation_count",
    "runtime_full_astar_calls",
    "runtime_full_cie_astar_calls",
    "unresolved_deadlock_count",
    "global_reservation_scan_count",
    "priority_global_scan_count",
    "scorer_runtime_global_scan_count",
    "microphase_runtime_global_scan_count",
    "first_edge_credit_global_scan_count",
    "scorer_future_route_input_count",
    "priority_future_route_input_count",
    "first_edge_credit_future_route_count",
    "scorer_future_schedule_input_count",
    "priority_teacher_input_count",
    "scorer_teacher_input_count",
    "two_step_reservation_count",
    "merge_grant_stale_arbitration_count",
    "stale_arbitration_event_count",
)

MODEL_ZERO_KEYS = (
    "g4irsf16_i3_applied_count",
    "g4irsf16_i4_applied_count",
    "g4irsf18_merge_model_applied_count",
)


def _hard_safety(summary: Mapping[str, Any]) -> dict[str, bool]:
    zero = {
        key: _integer(summary.get(key), f"summary.{key}") == 0
        for key in SAFETY_ZERO_KEYS
    }
    for key in MODEL_ZERO_KEYS:
        if key in summary:
            zero[key] = _integer(summary[key], f"summary.{key}") == 0
    return {
        "zero_safety_counters": all(zero.values()),
        "safe_execution": summary.get("safe_execution_pass") is True,
        "one_hop_only": _integer(
            summary.get("max_edges_selected_per_bag_per_decision"),
            "summary.max_edges_selected_per_bag_per_decision",
        )
        <= 1,
        "limits_not_reached": summary.get("event_limit_reached") is False
        and summary.get("time_limit_reached") is False,
        "no_artificial_batch_delay": _finite(
            summary.get("artificial_batch_delay_seconds"),
            "summary.artificial_batch_delay_seconds",
        )
        == 0.0,
        "merge_integrity": summary.get("merge_grant_conservation_holds") is True
        and summary.get("merge_grant_active_bijection_holds") is True
        and summary.get("merge_grant_protocol_integrity_pass") is True,
    }


def _service_episodes(
    payload: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    records = request.get("bag_records")
    if not isinstance(records, (list, tuple)):
        raise ValueError("request.bag_records must be a sequence")
    events = _rows(payload.get("events"), "payload.events")
    episodes = []
    for event in events:
        if event.get("event") != "JUNCTION_SERVICE_COMPLETE" or event.get(
            "node"
        ) != SERVICE_NODE:
            continue
        runtime_id = _integer(event.get("runtime_bag_id"), "completion owner")
        if runtime_id < 0 or runtime_id >= len(records):
            raise ValueError("completion owner is outside the request")
        complete = _finite(event.get("time"), "completion time")
        episodes.append(
            {
                "runtime_bag_id": runtime_id,
                "task_id": _integer(event.get("task_id"), "completion task"),
                "node": SERVICE_NODE,
                "start": complete - SERVICE_SECONDS,
                "end": complete,
            }
        )
    episodes.sort(key=lambda row: (row["start"], row["end"], row["runtime_bag_id"]))
    return episodes


def _completion_and_calendar_audit(
    payload: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    summary = _mapping(payload.get("summary"), "payload.summary")
    bags = _rows(payload.get("bags"), "payload.bags")
    records = request.get("bag_records")
    if not isinstance(records, (list, tuple)):
        raise ValueError("request.bag_records must be a sequence")
    episodes = _service_episodes(payload, request)
    owners = [row["runtime_bag_id"] for row in episodes]
    no_overlap = all(
        right["start"] >= left["end"] - 1e-9
        for left, right in zip(episodes, episodes[1:])
    )
    bag_by_id = {
        _integer(bag.get("runtime_bag_id"), "bag owner"): bag for bag in bags
    }
    completed_origins = Counter(
        str(bag.get("source")) for bag in bags if bag.get("completed") is True
    )
    requested_origins = Counter(str(record[6]) for record in records)
    junctions = _rows(payload.get("junction_state"), "payload.junction_state")
    service_state = [row for row in junctions if row.get("node") == SERVICE_NODE]
    calendar_count = (
        _integer(service_state[0].get("service_reservation_count"), "calendar count")
        if len(service_state) == 1
        else -1
    )
    checks = {
        "all_completed": _integer(summary.get("requested_count"), "requested")
        == len(records)
        == _integer(summary.get("completed_count"), "completed")
        == len(bags)
        and len(bag_by_id) == len(records)
        and all(bag.get("completed") is True for bag in bags),
        "service_exactly_once": len(owners) == len(records)
        and set(owners) == set(range(len(records)))
        and len(owners) == len(set(owners)),
        "origins_complete": completed_origins == requested_origins,
        "one_owner_intervals": no_overlap,
        "calendar_count_exact": calendar_count == len(records),
        "terminal_empty": _integer(
            summary.get("final_active_bag_count"), "final active"
        )
        == 0
        and all(
            _integer(row.get("final_source_queue_length"), "source queue") == 0
            and _integer(row.get("final_junction_queue_length"), "junction queue")
            == 0
            and _integer(row.get("scheduled_incoming"), "scheduled incoming")
            == 0
            for row in junctions
        ),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "episodes": episodes,
        "requested_origins": dict(sorted(requested_origins.items())),
        "completed_origins": dict(sorted(completed_origins.items())),
    }


def _action_audit(
    case: ActionCase,
    payload: Mapping[str, Any],
    service: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _mapping(payload.get("summary"), "payload.summary")
    events = _rows(payload.get("events"), "payload.events")
    bags = _rows(payload.get("bags"), "payload.bags")
    by_owner = {
        _integer(bag.get("runtime_bag_id"), "bag owner"): bag for bag in bags
    }
    completions = {
        row["runtime_bag_id"]: row for row in service.get("episodes", [])
    }
    action_events = [
        event
        for event in events
        if event.get("event") == "LOCAL_QUEUE_UPDATE"
        and event.get("reason") == ACTION_REASON
    ]
    actions = []
    valid = True
    for event in action_events:
        owner = _integer(event.get("runtime_bag_id"), "action owner")
        start = _finite(event.get("time"), "action start")
        bag = by_owner.get(owner)
        completion = completions.get(owner)
        valid = valid and bag is not None and completion is not None
        if bag is None or completion is None:
            continue
        valid = valid and bag.get("source") == "local"
        valid = valid and event.get("task_id") == bag.get("task_id")
        valid = valid and event.get("segment_id") == bag.get("segment_id")
        valid = valid and event.get("node") == SERVICE_NODE
        valid = valid and _finite(bag.get("admitted_time"), "bag admitted_time") == start
        valid = valid and abs(float(completion["start"]) - start) <= 1e-9
        actions.append(
            {
                "runtime_bag_id": owner,
                "task_id": _integer(event.get("task_id"), "action task"),
                "segment_id": event.get("segment_id"),
                "node": _integer(event.get("node"), "action node"),
                "start": start,
                "end": float(completion["end"]),
            }
        )
    action_count = _integer(summary.get(NS + "action_change_count"), "action count")
    calendar_count = _integer(
        summary.get(NS + "calendar_mutation_count"), "calendar mutation count"
    )
    future_reads = _integer(
        summary.get(NS + "future_release_read_count"), "future release reads"
    )
    global_scans = _integer(summary.get(NS + "global_scan_count"), "global scans")
    owner_ids = [row["runtime_bag_id"] for row in actions]
    expected = (
        True
        if case.expected_action is None
        else bool(actions) == case.expected_action
    )
    checks = {
        "mode_closed_loop": summary.get(NS + "mode") == "closed_loop",
        "counter_event_exact": action_count == calendar_count == len(actions),
        "expected_action": expected,
        "action_identity_interval_exact": valid
        and len(owner_ids) == len(set(owner_ids))
        and all(row["node"] == SERVICE_NODE for row in actions),
        "future_and_global_zero": future_reads == 0 and global_scans == 0,
        "no_shadow_sidecar": NS + "shadow" not in payload,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "action_count": action_count,
        "calendar_mutation_count": calendar_count,
        "actions": actions,
    }


def _resources(payload: Mapping[str, Any]) -> dict[str, float]:
    summary = _mapping(payload.get("summary"), "payload.summary")
    completed = _integer(summary.get("completed_count"), "completed count")
    events = _integer(summary.get("event_count"), "event count")
    junctions = _rows(payload.get("junction_state"), "payload.junction_state")
    local = math.fsum(
        _finite(row.get("peak_local_state_accounted_bytes"), "local memory")
        for row in junctions
    )
    if completed <= 0 or events < 0 or local < 0.0:
        raise ValueError("resource accounting is invalid")
    return {
        "events_per_completed": events / completed,
        "junction_local_accounted_bytes": local,
    }


def _ratio(candidate: float, control: float) -> float:
    if control > 0.0:
        return candidate / control
    return 1.0 if candidate == 0.0 else math.inf


def run_case(
    case: ActionCase,
    *,
    executor: Executor,
    binary: Path | None = None,
) -> dict[str, Any]:
    requests = {
        mode: build_case_request(case, mode=mode, binary=binary) for mode in MODES
    }
    ordinary_requests = [_without_extension(requests[mode]) for mode in MODES]
    if not ordinary_requests[0] == ordinary_requests[1] == ordinary_requests[2]:
        raise ValueError(f"{case.case_id} arms do not have the same ordinary request")
    payloads = {mode: executor(**requests[mode]) for mode in MODES}
    if not all(isinstance(payload, Mapping) for payload in payloads.values()):
        raise ValueError("executor must return mappings")

    audits = {
        mode: _completion_and_calendar_audit(payloads[mode], requests[mode])
        for mode in MODES
    }
    safety = {
        mode: _hard_safety(
            _mapping(payloads[mode].get("summary"), f"{mode}.summary")
        )
        for mode in MODES
    }
    off_exact = extension_absent(payloads["off"])
    shadow_summary = _mapping(payloads["shadow"].get("summary"), "shadow.summary")
    shadow_inert = (
        shadow_summary.get(NS + "mode") == "shadow"
        and all(
            _integer(shadow_summary.get(NS + name), f"shadow {name}") == 0
            for name in (
                "action_change_count",
                "calendar_mutation_count",
                "future_release_read_count",
                "global_scan_count",
            )
        )
        and ordinary_projection(payloads["off"])
        == ordinary_projection(payloads["shadow"])
    )
    action = _action_audit(case, payloads["closed_loop"], audits["closed_loop"])
    closed_noop = (
        ordinary_projection(payloads["off"])
        == ordinary_projection(payloads["closed_loop"])
        if case.expected_action is False
        else True
    )

    resources = {mode: _resources(payloads[mode]) for mode in MODES}
    ratios = {
        mode: {
            key: _ratio(value, resources["off"][key])
            for key, value in resources[mode].items()
        }
        for mode in ("shadow", "closed_loop")
    }
    resource_pass = all(
        ratio <= RESOURCE_RATIO_LIMIT
        for arm in ratios.values()
        for ratio in arm.values()
    )

    priority_pass = True
    if case.control_kind == "reverse_priority":
        starts = {
            row["task_id"]: row["start"] for row in audits["closed_loop"]["episodes"]
        }
        priority_pass = (
            case.local_task_id in starts
            and case.priority_external_task_id in starts
            and starts[case.priority_external_task_id] < starts[case.local_task_id]
        )

    checks = {
        "default_off_exact": off_exact,
        "shadow_action_inert_exact": shadow_inert,
        "all_complete_calendar_safe": all(
            audit.get("pass") is True for audit in audits.values()
        ),
        "hard_safety_zero": all(all(values.values()) for values in safety.values()),
        "closed_loop_action_contract": action["pass"],
        "registered_noop_exact": closed_noop,
        "reverse_priority_external_wins": priority_pass,
        "resources_within_1p10": resource_pass,
    }
    return {
        "case_id": case.case_id,
        "topology": case.topology,
        "control_kind": case.control_kind,
        "expected_action": case.expected_action,
        "pass": all(checks.values()),
        "checks": checks,
        "action": action,
        "completion_calendar": audits,
        "safety": safety,
        "resources": resources,
        "resource_ratios": ratios,
    }


def _action_signature(case_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    action = _mapping(case_result.get("action"), "case.action")
    return [
        {
            key: row.get(key)
            for key in ("task_id", "node", "start", "end")
        }
        for row in _rows(action.get("actions"), "case.action.actions")
    ]


def run_campaign(
    *, executor: Executor, binary: Path | None = None
) -> dict[str, Any]:
    cases = [run_case(case, executor=executor, binary=binary) for case in registered_cases()]
    indexed = {str(case["case_id"]): case for case in cases}
    future_exact = _action_signature(indexed["future_release_base"]) == _action_signature(
        indexed["future_release_perturbed"]
    )
    gates = {
        "exact_registered_case_population": len(cases) == len(registered_cases())
        and set(indexed) == {case.case_id for case in registered_cases()},
        "all_case_gates": all(case.get("pass") is True for case in cases),
        "direct_action_observed": indexed["direct_mixed_contention"]["action"][
            "action_count"
        ]
        >= 1,
        "j2_action_observed": indexed["j2_mixed_contention"]["action"][
            "action_count"
        ]
        >= 1,
        "future_release_perturbation_exact": future_exact,
    }
    passed = all(gates.values())
    return {
        "schema": SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "preregistration": PREREGISTRATION_PATH.relative_to(ROOT).as_posix(),
        "status": PASS if passed else NO_GO,
        "pass": passed,
        "stage2_authorized": passed,
        "case_count": len(cases),
        "execution_count": len(cases) * len(MODES),
        "modes": list(MODES),
        "resource_ratio_limit": RESOURCE_RATIO_LIMIT,
        "gates": gates,
        "cases": cases,
    }


def render_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF32 V3R13 Candidate A pre-Stage-2 action gate",
        "",
        f"Status: `{result.get('status')}`.",
        "",
        "This is the frozen small DIRECT/J2 action suite. It does not report a real-map effect.",
        "",
        "| case | topology | action | calendar mutations | events ratio | local-memory ratio | pass |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case in result.get("cases", []):
        action = case["action"]
        ratios = case["resource_ratios"]["closed_loop"]
        lines.append(
            "| {case_id} | {topology} | {actions} | {calendar} | {events:.3f} | {memory:.3f} | {passed} |".format(
                case_id=case["case_id"],
                topology=case["topology"],
                actions=action["action_count"],
                calendar=action["calendar_mutation_count"],
                events=ratios["events_per_completed"],
                memory=ratios["junction_local_accounted_bytes"],
                passed="PASS" if case["pass"] else "FAIL",
            )
        )
    failed = [name for name, passed in result.get("gates", {}).items() if not passed]
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "Stage 2 is authorized." if result.get("stage2_authorized") else "Stage 2 is not authorized.",
            "",
            "Failed gates: " + (", ".join(failed) if failed else "none"),
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence(
    result: Mapping[str, Any],
    *,
    json_path: Path = OUTPUT_JSON,
    markdown_path: Path = OUTPUT_MD,
) -> None:
    if json_path.exists() or markdown_path.exists():
        raise FileExistsError("V3R13 registered pre-Stage-2 evidence is append-only")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    with markdown_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(render_report(result))


def cpp_executor(**request: Any) -> Mapping[str, Any]:
    from czr005.cpp_backend import g4irsf11_event_runtime_from_records

    return g4irsf11_event_runtime_from_records(**request)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=OUTPUT_MD)
    arguments = parser.parse_args(argv)
    try:
        result = run_campaign(executor=cpp_executor, binary=arguments.binary)
    except Exception as error:
        result = {
            "schema": SCHEMA,
            "protocol_id": PROTOCOL_ID,
            "status": NO_GO,
            "pass": False,
            "stage2_authorized": False,
            "error_type": type(error).__name__,
            "error": str(error),
        }
    write_evidence(
        result, json_path=arguments.output_json, markdown_path=arguments.output_md
    )
    print(result["status"])
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

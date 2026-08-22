#!/usr/bin/env python3
"""Run the compact G25 corridor-observation and native CLCR campaign.

The runner deliberately reuses the frozen G24/G20 workload and timing
parsers.  It adds only three pieces of orchestration:

* convert the eight measured G24 split/rejoin arms into the G25 observe ABI;
* collect real per-bag corridor trajectories at 1x/2x (and optional bounded
  4x) without changing S4 actions;
* execute S4/T0/L1/L2/L3 artifacts through one common native run-row schema.

No uncompleted run is reported as measured.  Full-run timing fields and all
bounded-run TTH fields remain the literal ``NOT_MEASURED`` until the native
runtime has produced the required population.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import io
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import canonical_graph_records
from scripts.eval import run_g4irsf19_bounded_capacity as capacity
from scripts.eval import run_g4irsf19_route_campaign as route
from scripts.eval import run_g4irsf20_event_hotpath as hotpath
from scripts.eval import run_g4irsf24_dlp_campaign as g24_campaign
from scripts.eval import run_g4irsf24_native_race as native_race


SCHEMA = "czr005.g4irsf25.native_campaign.v1"
OBSERVE_SCHEMA = "czr005.g4irsf25.clcr.v1"
TRAJECTORY_COVERAGE_SCHEMA = "czr005.g4irsf25.corridor_coverage.v1"
NOT_MEASURED = "NOT_MEASURED"
MEASURED_EVIDENCE_STATUSES = frozenset(
    {"MEASURED_COMPLETE", "MEASURED_BOUNDED_PROGRESS"}
)

DEFAULT_G24_CORRIDORS = ROOT / "outputs/tables/g4irsf24_decision_summary.json"
DEFAULT_OBSERVE_ARTIFACT = ROOT / "artifacts/policies/g4irsf25_observe.json"
DEFAULT_TRAJECTORY_RAW = ROOT / "build/g4irsf25_clcr_campaign/corridor_trajectories.jsonl"
DEFAULT_COVERAGE = ROOT / "outputs/tables/g4irsf25_corridor_coverage.json"
DEFAULT_TRAJECTORY_REPORT = ROOT / "outputs/reports/g4irsf25_corridor_trajectory.md"
DEFAULT_RUN_JSON = ROOT / "build/g4irsf25_clcr_campaign/native_campaign.json"
DEFAULT_RUN_CSV = ROOT / "outputs/tables/g4irsf25_closed_loop.csv"
DEFAULT_NATIVE_REPORT = ROOT / "outputs/reports/g4irsf25_native_closed_loop.md"
DEFAULT_SCALE_CSV = ROOT / "outputs/tables/g4irsf25_scale.csv"
DEFAULT_SCALE_REPORT = ROOT / "outputs/reports/g4irsf25_scale.md"

SCREEN_SIZES = (144, 512, 8192)
FULL_SCALES = (1, 2)
BOUNDED_SCALE = 4
EXPECTED_BRANCHES = (6, 9, 16, 19)
POLICY_MODES = (
    ("S4", "off"),
    ("T0", "t0"),
    ("L1", "l1"),
    ("L2", "l2"),
    ("L3", "l3"),
)


class G25CampaignError(RuntimeError):
    pass


Executor = Callable[..., Mapping[str, Any]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise G25CampaignError(message)


def _is_measured_row(row: Mapping[str, Any]) -> bool:
    return row.get("evidence_status") in MEASURED_EVIDENCE_STATUSES


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
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _quantile(values: Sequence[float], probability: float) -> float:
    _require(bool(values), "cannot summarize an empty population")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _portable(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"expected one JSON object: {path}")
    return value


def _json_text(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"


def _atomic_publish_texts(payloads: Sequence[tuple[Path, str]]) -> None:
    """Stage every file beside its destination, then replace the snapshot."""

    targets = [path.resolve() for path, _text in payloads]
    _require(len(targets) == len(set(targets)), "snapshot output paths must be distinct")
    staged: list[tuple[Path, Path]] = []
    nonce = f"{os.getpid()}.{time.time_ns()}"
    try:
        for index, (path, text) in enumerate(payloads):
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{nonce}.{index}.tmp")
            temporary.write_text(text, encoding="utf-8", newline="")
            staged.append((temporary, path))
        for temporary, path in staged:
            os.replace(temporary, path)
    finally:
        for temporary, _path in staged:
            if temporary.exists():
                temporary.unlink()


def _write_json(path: Path, value: Any) -> None:
    _atomic_publish_texts(((path, _json_text(value)),))


def _run_csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    fields: list[str] = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        encoded = {
            name: (
                json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
                if isinstance(value, (dict, list, tuple))
                else value
            )
            for name, value in row.items()
        }
        writer.writerow(encoded)
    return handle.getvalue()


def _write_run_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _atomic_publish_texts(((path, _run_csv_text(rows)),))


def build_observe_artifact(
    source_path: Path = DEFAULT_G24_CORRIDORS,
) -> dict[str, Any]:
    """Build and verify the eight-arm observe artifact from measured G24 data."""

    source = _read_json(source_path)
    corridor_section = source.get("reconvergent_corridor")
    _require(isinstance(corridor_section, Mapping), "G24 decision summary lacks corridor evidence")
    raw_corridors = corridor_section.get("corridors")
    _require(isinstance(raw_corridors, list), "G24 corridor evidence is not a list")

    _nodes, edge_records, _heuristic = canonical_graph_records()
    edge_seconds = {
        (int(start), int(end)): float(length) / float(speed)
        for start, end, length, speed in edge_records
    }
    arms: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_corridors):
        _require(isinstance(raw, Mapping), f"G24 corridor row {index} is not an object")
        path = raw.get("path")
        _require(
            isinstance(path, list) and len(path) >= 3 and all(isinstance(node, int) for node in path),
            f"G24 corridor row {index} has no exact split/rejoin path",
        )
        branch = int(raw.get("from", -1))
        first_edge = int(raw.get("to", -1))
        rejoin = int(raw.get("reconvergence", -1))
        _require(
            path[0] == branch and path[1] == first_edge and path[-1] == rejoin,
            f"G24 corridor row {index} path endpoints disagree",
        )
        missing_edges = [
            (start, end)
            for start, end in zip(path, path[1:])
            if (start, end) not in edge_seconds
        ]
        _require(not missing_edges, f"G24 corridor row {index} is not legal on the canonical map")
        static_seconds = sum(edge_seconds[(start, end)] for start, end in zip(path, path[1:]))
        source_static = _finite(raw.get("static_duration_seconds"))
        _require(
            source_static is not None and math.isclose(static_seconds, source_static, abs_tol=1.0e-9),
            f"G24 corridor row {index} static duration disagrees with the canonical map",
        )
        support = _integer(raw.get("support"))
        _require(support is not None and support > 0, f"G24 corridor row {index} has no measured support")
        arms.append(
            {
                "branch_node": branch,
                "first_edge": first_edge,
                "rejoin_node": rejoin,
                "corridor_nodes": list(path),
                "support": support,
                "training_support": 0,
                "static_duration_seconds": static_seconds,
                "t0_system_delta_seconds": 0.0,
                "t0_private_delta_seconds": 0.0,
                "system_intercept": 0.0,
                "private_intercept": 0.0,
            }
        )

    arms.sort(key=lambda row: (row["branch_node"], row["first_edge"]))
    keys = [(row["branch_node"], row["first_edge"]) for row in arms]
    branch_counts = Counter(row["branch_node"] for row in arms)
    _require(len(arms) == 8 and len(keys) == len(set(keys)), "G24 evidence must yield eight unique arms")
    _require(
        tuple(sorted(branch_counts)) == EXPECTED_BRANCHES
        and all(branch_counts[branch] == 2 for branch in EXPECTED_BRANCHES),
        "G24 evidence must yield two arms for each registered branch",
    )
    return {
        "schema": OBSERVE_SCHEMA,
        "mode": "observe",
        "feature_names": list(cpp_backend.G4IRSF25_CLCR_FEATURE_NAMES),
        "record_trajectories": True,
        "trajectory_max_seconds": 600.0,
        "min_support": 8,
        "margin_seconds": 0.5,
        "private_cap_seconds": 60.0,
        "t0_metric": "target_queue_plus_incoming",
        "arms": arms,
        "training_metadata": {
            "source": _portable(source_path),
            "source_schema": corridor_section.get("schema"),
            "support_semantics": "G24 minimum marginal directed-edge support along the fitted path",
            "static_duration_semantics": "sum of canonical directed-edge length/speed",
            "policy_effect": "observe_only_exact_S4_actions",
        },
    }


def _load_artifact_specs(
    values: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    artifacts: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    modes: set[str] = set()
    for value in values:
        if "=" not in value:
            raise G25CampaignError("--artifact must be LABEL=PATH")
        label, raw_path = value.split("=", 1)
        label = label.strip()
        _require(label and label.upper() not in {"S4", "OBSERVE"}, "artifact label is reserved or empty")
        path = Path(raw_path).expanduser().resolve(strict=True)
        artifact = _read_json(path)
        mode = str(artifact.get("mode", ""))
        _require(
            artifact.get("schema") == OBSERVE_SCHEMA and mode in {"t0", "l1", "l2", "l3"},
            f"{label} is not an active G25 CLCR artifact",
        )
        _require(label not in artifacts, f"duplicate artifact label: {label}")
        _require(mode not in modes, f"more than one {mode} artifact supplied")
        artifacts[label] = artifact
        paths[label] = path
        modes.add(mode)
    return artifacts, paths


def _family(mode: str) -> str:
    if mode == "off":
        return "BASELINE"
    if mode == "observe":
        return "OBSERVATION"
    if mode == "t0":
        return "THRESHOLD"
    return "LEARNING"


def build_run_plan(
    artifact_modes: Mapping[str, str],
    *,
    screen_sizes: Sequence[int] = SCREEN_SIZES,
    full_scales: Sequence[int] = FULL_SCALES,
    bounded_seconds: Sequence[float] = (60.0, 180.0),
) -> list[dict[str, Any]]:
    """Return the balanced run order with explicit unmeasured placeholders."""

    _require(all(size > 0 for size in screen_sizes), "screen sizes must be positive")
    _require(all(scale in FULL_SCALES for scale in full_scales), "full scales must be 1 or 2")
    _require(all(value > 0.0 for value in bounded_seconds), "bounded durations must be positive")
    candidates = list(artifact_modes)
    modes = {"S4": "off", **{label: str(mode) for label, mode in artifact_modes.items()}}
    specs: list[dict[str, Any]] = []

    def add(
        arm: str,
        workload: str,
        scale: int,
        execution_mode: str,
        repeat: int,
        order_index: int,
        bounded: float | None = None,
    ) -> None:
        run_id = f"{workload}_r{repeat}_{order_index:02d}_{arm}"
        specs.append(
            {
                "run_id": run_id,
                "arm": arm,
                "mode": modes[arm],
                "family": _family(modes[arm]),
                "workload": workload,
                "scale": scale,
                "execution_mode": execution_mode,
                "repeat": repeat,
                "order_index": order_index,
                "bounded_wall_seconds": bounded if bounded is not None else NOT_MEASURED,
            }
        )

    all_arms = ["S4", *candidates]
    for ordinal, size in enumerate(screen_sizes):
        order = all_arms if ordinal % 2 == 0 else list(reversed(all_arms))
        for order_index, arm in enumerate(order):
            add(arm, f"prefix_{size}", 1, "screen_full", 0, order_index)

    for scale in full_scales:
        if scale == 1:
            orders = (["S4", *candidates], [*reversed(candidates), "S4"])
        else:
            orders = ([*candidates, "S4"], ["S4", *reversed(candidates)])
        for repeat, order in enumerate(orders):
            for order_index, arm in enumerate(order):
                add(arm, f"scale_{scale}x", scale, "full", repeat, order_index)

    for duration_index, duration in enumerate(bounded_seconds):
        order = all_arms if duration_index % 2 == 0 else list(reversed(all_arms))
        for order_index, arm in enumerate(order):
            add(
                arm,
                f"scale_4x_{duration:g}s",
                4,
                "bounded",
                duration_index,
                order_index,
                float(duration),
            )
    return specs


_UNMEASURED_FIELDS = (
    "segments_requested",
    "segments_released",
    "segments_completed",
    "segments_failed",
    "current_backlog",
    "raw_bags_completed",
    "processed_attempt_count",
    "processed_attempt_min_seconds",
    "processed_attempt_mean_seconds",
    "processed_attempt_median_seconds",
    "processed_attempt_p95_seconds",
    "processed_attempt_p99_seconds",
    "processed_attempt_max_seconds",
    "java_release_mean_seconds",
    "original_entry_mean_seconds",
    "deadline_miss_count",
    "route_evaluations",
    "eligible_candidates",
    "proposals",
    "committed_mutations",
    "fallbacks",
    "fairness_fallbacks",
    "fault_fallbacks",
    "event_count",
    "events_per_completed_segment",
    "max_junction_queue_length",
    "max_source_queue_length",
    "wall_seconds",
    "cpu_seconds",
    "safety_pass",
)


def _unmeasured_run(spec: Mapping[str, Any]) -> dict[str, Any]:
    row = {
        "schema": SCHEMA,
        **dict(spec),
        "status": NOT_MEASURED,
        "evidence_status": NOT_MEASURED,
        "not_measured_reason": "PENDING_EXECUTION",
        "release_csv": NOT_MEASURED,
        "artifact_label": str(spec.get("arm", NOT_MEASURED)),
        "artifact_mode": str(spec.get("mode", NOT_MEASURED)),
        "artifact_path": NOT_MEASURED,
        "workload_descriptor": NOT_MEASURED,
        "safety": {},
        "g25_counters": {},
        "committed_mutations_by_branch": {},
        "error": "",
    }
    row.update({name: NOT_MEASURED for name in _UNMEASURED_FIELDS})
    return row


def _prefix_rows(size: int, release_csv: Path) -> tuple[list[dict[str, Any]], route.RouteCase]:
    case = route.build_cases(prefixes=(size,), evidence_prefixes=(size,), scales=())[0]
    rows, _descriptor = route.load_case_input(case, root=ROOT)
    return g24_campaign._exact_release_rows(rows, release_csv), case


def _load_workload(
    spec: Mapping[str, Any], release_csv: Path
) -> tuple[list[dict[str, Any]], dict[str, Any], route.RouteCase | None]:
    workload = str(spec["workload"])
    if workload.startswith("prefix_"):
        size = int(workload.removeprefix("prefix_"))
        rows, prefix_case = _prefix_rows(size, release_csv)
        return rows, {
            "protocol": "canonical_prefix_exact_hca_release",
            "segments": len(rows),
            "scale": 1,
            "topology_changed": False,
        }, prefix_case
    scale = int(spec["scale"])
    rows, descriptor = capacity.load_g18_scale_input(scale, ROOT)
    if scale == 1:
        rows = g24_campaign._exact_release_rows(rows, release_csv)
        descriptor = {**dict(descriptor), "release_semantics": "exact_hca_release_epoch"}
    return rows, dict(descriptor), None


def _runtime_request(
    spec: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    prefix_case: route.RouteCase | None,
    binary: Path,
    artifact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if prefix_case is not None:
        request = route.build_runtime_request(
            prefix_case,
            route.ARM_BY_ID["S4"],
            rows=rows,
            graph=route.load_fixed_graph(),
            binary=binary,
            model_path=ROOT / "artifacts/models/g4e_risk_calibrated_policy.json",
            decision_trace_limit=1,
        )
        request.update(
            summary_only=False,
            trace_limit=0,
            event_trace_limit=0,
            g4irsf20_event_hotpath_policy="E2",
        )
    else:
        bounded = _finite(spec.get("bounded_wall_seconds")) or 60.0
        request = hotpath.build_native_request(
            rows,
            scale=int(spec["scale"]),
            policy="E2",
            binary=binary,
            root=ROOT,
            bounded_wall_seconds=bounded,
            check_events=65_536,
        )
        request.update(trace_limit=0, event_trace_limit=0)
    request["scenario"] = f"g4irsf25_{spec['run_id']}"
    if artifact is not None:
        request["g4irsf25_clcr_artifact"] = dict(artifact)
    return request


def _g25_counters(summary: Mapping[str, Any], active: bool) -> dict[str, Any]:
    names = {
        "route_evaluations": "g4irsf25_clcr_route_evaluation_count",
        "eligible_candidates": "g4irsf25_clcr_eligible_candidate_count",
        "supported_candidates": "g4irsf25_clcr_supported_candidate_count",
        "proposals": "g4irsf25_clcr_proposal_count",
        "committed_mutations": "g4irsf25_clcr_committed_mutation_count",
        "fallbacks": "g4irsf25_clcr_fallback_s4_count",
        "same_actions": "g4irsf25_clcr_same_action_count",
        "low_support_fallbacks": "g4irsf25_clcr_low_support_fallback_count",
        "ood_fallbacks": "g4irsf25_clcr_ood_fallback_count",
        "margin_fallbacks": "g4irsf25_clcr_margin_fallback_count",
        "threshold_fallbacks": "g4irsf25_clcr_threshold_fallback_count",
        "fairness_fallbacks": "g4irsf25_clcr_fairness_fallback_count",
        "fault_fallbacks": "g4irsf25_clcr_fault_shield_fallback_count",
        "non_corridor_fallbacks": "g4irsf25_clcr_non_corridor_fallback_count",
        "feedback_count": "g4irsf25_clcr_feedback_count",
        "online_bias_updates": "g4irsf25_clcr_online_bias_update_count",
        "trajectory_started": "g4irsf25_corridor_trajectory_started_count",
        "trajectory_completed": "g4irsf25_corridor_trajectory_completed_count",
        "trajectory_timeout": "g4irsf25_corridor_trajectory_timeout_count",
        "runtime_global_scans": "g4irsf25_runtime_global_scan_count",
        "future_route_inputs": "g4irsf25_future_route_input_count",
        "full_astar_calls": "g4irsf25_full_astar_call_count",
    }
    if not active:
        return {name: 0 for name in names}
    missing = [source for source in names.values() if source not in summary]
    _require(not missing, f"active G25 run lacks counters: {', '.join(missing)}")
    return {name: int(summary[source]) for name, source in names.items()}


def _bounded_safety(summary: Mapping[str, Any]) -> dict[str, Any]:
    safety = hotpath._bounded_safety(summary)
    gates = dict(safety["gates"])
    for name in (
        "g4irsf25_runtime_global_scan_count",
        "g4irsf25_future_route_input_count",
        "g4irsf25_full_astar_call_count",
    ):
        if name in summary:
            gates[f"{name}_zero"] = int(summary[name]) == 0
    return {"pass": all(gates.values()), "gates": gates}


def _timing_fields(
    timings: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result = {
        "raw_bags_completed": NOT_MEASURED,
        "processed_attempt_count": NOT_MEASURED,
        "processed_attempt_min_seconds": NOT_MEASURED,
        "processed_attempt_mean_seconds": NOT_MEASURED,
        "processed_attempt_median_seconds": NOT_MEASURED,
        "processed_attempt_p95_seconds": NOT_MEASURED,
        "processed_attempt_p99_seconds": NOT_MEASURED,
        "processed_attempt_max_seconds": NOT_MEASURED,
        "java_release_mean_seconds": NOT_MEASURED,
        "original_entry_mean_seconds": NOT_MEASURED,
    }
    if timings is None:
        return result
    processed = timings.get("processed_attempt")
    java = timings.get("java_release")
    original = timings.get("original_entry")
    _require(
        isinstance(processed, Mapping)
        and isinstance(java, Mapping)
        and isinstance(original, Mapping),
        "complete timing parser omitted one denominator",
    )
    result.update(
        raw_bags_completed=int(processed["count"]),
        processed_attempt_count=int(processed["count"]),
        processed_attempt_min_seconds=float(processed["min_seconds"]),
        processed_attempt_mean_seconds=float(processed["mean_seconds"]),
        processed_attempt_median_seconds=float(processed["median_seconds"]),
        processed_attempt_p95_seconds=float(processed["p95_seconds"]),
        processed_attempt_p99_seconds=float(processed["p99_seconds"]),
        processed_attempt_max_seconds=float(processed["max_seconds"]),
        java_release_mean_seconds=float(java["mean_seconds"]),
        original_entry_mean_seconds=float(original["mean_seconds"]),
    )
    return result


def _summarize_payload(
    spec: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
    wall_seconds: float,
    cpu_seconds: float,
    active: bool,
) -> dict[str, Any]:
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    counters = _g25_counters(summary, active)
    mutations_by_branch = summary.get("g4irsf25_clcr_committed_mutations_by_branch", {})
    _require(isinstance(mutations_by_branch, Mapping), "G25 branch mutation counter is not an object")

    if spec["execution_mode"] == "bounded":
        history, history_source = capacity.progress_history_from_payload(
            payload, requested=len(rows), wall_seconds=wall_seconds
        )
        frontier = history[-1]
        completed = int(frontier.get("completed_bags", 0))
        released = int(frontier.get("released_bags", 0))
        failed = int(frontier.get("failed_bags", 0))
        backlog = int(frontier.get("current_backlog", 0))
        event_count = int(frontier.get("event_total", summary.get("event_count", 0)))
        safety = _bounded_safety(summary)
        native_status = str(payload.get("execution_status", ""))
        complete = completed == len(rows) and failed == 0
        status = "COMPLETE" if complete and safety["pass"] else (
            "BOUNDED_PROGRESS" if native_status == "BOUNDED_PROGRESS" and safety["pass"] else "BOUNDED_GATE_FAILED"
        )
        timing_fields = _timing_fields(None)
        deadline_miss: Any = NOT_MEASURED
        evidence_status = "MEASURED_BOUNDED_PROGRESS"
    else:
        bags = payload.get("bags")
        _require(isinstance(bags, list), "full native payload lacks bag rows")
        completed = int(summary.get("completed_count", 0))
        released = int(summary.get("bag_release_event_count", len(rows)))
        failed = int(summary.get("failed_count", 0))
        backlog = int(summary.get("final_active_bag_count", max(len(rows) - completed, 0)))
        event_count = int(summary.get("event_count", 0))
        safety = g24_campaign._strict_summary_safety(summary, len(rows))
        complete = (
            completed == len(rows)
            and failed == 0
            and len(bags) == len(rows)
            and all(isinstance(bag, Mapping) and bag.get("completed") is True for bag in bags)
        )
        if complete:
            timings, _raw = native_race.timing_distributions(rows, bags)
            timing_fields = _timing_fields(timings)
            deadline_miss = sum(
                1
                for bag in bags
                if isinstance(bag, Mapping)
                and isinstance(bag.get("deadline"), (int, float))
                and float(bag["deadline"]) >= 0.0
                and float(bag.get("finish_time", -1.0)) > float(bag["deadline"])
            )
            evidence_status = "MEASURED_COMPLETE"
        else:
            timing_fields = _timing_fields(None)
            deadline_miss = NOT_MEASURED
            evidence_status = "INCOMPLETE_TTH_NOT_MEASURED"
        status = "COMPLETE" if complete and safety["pass"] else "FULL_GATE_FAILED"

    row = _unmeasured_run(spec)
    row.update(
        status=status,
        evidence_status=evidence_status,
        not_measured_reason=(
            "" if evidence_status in MEASURED_EVIDENCE_STATUSES else "FULL_POPULATION_INCOMPLETE"
        ),
        segments_requested=len(rows),
        segments_released=released,
        segments_completed=completed,
        segments_failed=failed,
        current_backlog=backlog,
        deadline_miss_count=deadline_miss,
        route_evaluations=counters["route_evaluations"],
        eligible_candidates=counters["eligible_candidates"],
        proposals=counters["proposals"],
        committed_mutations=counters["committed_mutations"],
        fallbacks=counters["fallbacks"],
        fairness_fallbacks=counters["fairness_fallbacks"],
        fault_fallbacks=counters["fault_fallbacks"],
        event_count=event_count,
        events_per_completed_segment=(event_count / completed if completed else NOT_MEASURED),
        max_junction_queue_length=summary.get("max_junction_queue_length", NOT_MEASURED),
        max_source_queue_length=summary.get("max_source_queue_length", NOT_MEASURED),
        wall_seconds=wall_seconds,
        cpu_seconds=cpu_seconds,
        safety_pass=bool(safety["pass"]),
        safety=safety,
        g25_counters=counters,
        committed_mutations_by_branch={str(key): int(value) for key, value in mutations_by_branch.items()},
        **timing_fields,
    )
    return row


def _execute_native(
    spec: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    prefix_case: route.RouteCase | None,
    binary: Path,
    artifact: Mapping[str, Any] | None,
    executor: Executor,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    request = _runtime_request(
        spec,
        rows=rows,
        prefix_case=prefix_case,
        binary=binary,
        artifact=artifact,
    )
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = executor(**request)
    cpu_seconds = time.process_time() - cpu_started
    wall_seconds = time.perf_counter() - wall_started
    _require(isinstance(payload, Mapping), "native executor returned a non-object")
    row = _summarize_payload(
        spec,
        rows=rows,
        payload=payload,
        wall_seconds=wall_seconds,
        cpu_seconds=cpu_seconds,
        active=artifact is not None,
    )
    raw_trajectories = payload.get("g4irsf25_corridor_trajectories", [])
    _require(isinstance(raw_trajectories, list), "native trajectory payload is not a list")
    trajectories = [
        _compact_trajectory(item, scale=int(spec["scale"]), run_id=str(spec["run_id"]))
        for item in raw_trajectories
        if isinstance(item, Mapping)
    ]
    _require(len(trajectories) == len(raw_trajectories), "native trajectory payload contains a non-object")
    return row, trajectories


def _screen_stage_gates(
    rows: Sequence[Mapping[str, Any]], active_labels: Sequence[str]
) -> dict[str, dict[str, Any]]:
    gates: dict[str, dict[str, Any]] = {}
    for label in ("S4", *active_labels):
        reasons: list[str] = []
        measured_rows: list[Mapping[str, Any]] = []
        for size in SCREEN_SIZES:
            matches = [
                row
                for row in rows
                if row.get("arm") == label and row.get("workload") == f"prefix_{size}"
            ]
            if not matches:
                reasons.append(f"MISSING_PREFIX_{size}")
                continue
            if len(matches) != 1:
                reasons.append(f"DUPLICATE_PREFIX_{size}")
                continue
            row = matches[0]
            if row.get("evidence_status") != "MEASURED_COMPLETE":
                reasons.append(f"PREFIX_{size}_NOT_MEASURED_COMPLETE")
                continue
            measured_rows.append(row)
            if row.get("safety_pass") is not True:
                reasons.append(f"PREFIX_{size}_SAFETY_FAILED")

        mutations = [_integer(row.get("committed_mutations")) for row in measured_rows]
        fallbacks = [_integer(row.get("fallbacks")) for row in measured_rows]
        mutation_total: Any = (
            sum(int(value) for value in mutations if value is not None)
            if len(measured_rows) == len(SCREEN_SIZES) and all(value is not None for value in mutations)
            else NOT_MEASURED
        )
        fallback_total: Any = (
            sum(int(value) for value in fallbacks if value is not None)
            if len(measured_rows) == len(SCREEN_SIZES) and all(value is not None for value in fallbacks)
            else NOT_MEASURED
        )
        if label != "S4" and len(measured_rows) == len(SCREEN_SIZES):
            mutation_count = _integer(mutation_total)
            fallback_count = _integer(fallback_total)
            if mutation_count is None:
                reasons.append("MUTATIONS_NOT_MEASURED")
            elif mutation_count <= 0:
                reasons.append("ZERO_MUTATIONS")
            if fallback_count is None:
                reasons.append("FALLBACKS_NOT_MEASURED")
            elif fallback_count <= 0:
                reasons.append("ZERO_FALLBACKS")
        reason = "" if not reasons else "SCREEN_GATE_FAILED:" + ",".join(reasons)
        gates[label] = {
            "status": "PASS" if not reasons else "FAIL",
            "passed": not reasons,
            "required_screen_sizes": list(SCREEN_SIZES),
            "measured_complete_screen_count": len(measured_rows),
            "cumulative_mutations": mutation_total,
            "cumulative_fallbacks": fallback_total,
            "not_measured_reason": reason,
        }
    return gates


def _campaign_document(
    rows: Sequence[Mapping[str, Any]], binary: Path, release_csv: Path
) -> dict[str, Any]:
    attempted = [row for row in rows if row.get("status") != NOT_MEASURED]
    measured = [row for row in rows if _is_measured_row(row)]
    labels = list(
        dict.fromkeys(str(row.get("arm")) for row in rows if row.get("arm") != "S4")
    )
    artifact_provenance = []
    for label in labels:
        row = next(item for item in rows if item.get("arm") == label)
        artifact_provenance.append(
            {
                "label": label,
                "mode": row.get("artifact_mode", NOT_MEASURED),
                "path": row.get("artifact_path", NOT_MEASURED),
            }
        )
    return {
        "schema": SCHEMA,
        "binary": _portable(binary),
        "release_csv": _portable(release_csv),
        "artifacts": artifact_provenance,
        "denominator_primary": "processed_attempt",
        "run_count": len(rows),
        "attempted_run_count": len(attempted),
        "measured_run_count": len(measured),
        "error_run_count": sum(row.get("status") == "ERROR" for row in rows),
        "not_measured_run_count": len(rows) - len(measured),
        "screen_stage_gates": _screen_stage_gates(rows, labels),
        "runs": list(rows),
    }


_FULL_REPORT_FIELDS = (
    "processed_attempt_mean_seconds",
    "processed_attempt_p95_seconds",
    "processed_attempt_p99_seconds",
    "processed_attempt_max_seconds",
)


def _balanced_full_summary(
    rows: Sequence[Mapping[str, Any]], *, mode: str, scale: int
) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row.get("mode") == mode
        and row.get("execution_mode") == "full"
        and _integer(row.get("scale")) == scale
    ]
    result: dict[str, Any] = {
        "status": NOT_MEASURED,
        "planned_repeat_count": len(selected),
        "complete_repeat_count": sum(
            row.get("evidence_status") == "MEASURED_COMPLETE" for row in selected
        ),
        "committed_mutations": NOT_MEASURED,
        "safety": NOT_MEASURED,
        **{name: NOT_MEASURED for name in _FULL_REPORT_FIELDS},
    }
    balanced = len(selected) == 2 and {_integer(row.get("repeat")) for row in selected} == {0, 1}
    complete = balanced and all(
        row.get("evidence_status") == "MEASURED_COMPLETE" for row in selected
    )
    metric_values = {
        name: [_finite(row.get(name)) for row in selected]
        for name in _FULL_REPORT_FIELDS
    }
    if not complete or any(
        any(value is None for value in values) for values in metric_values.values()
    ):
        return result
    mutations = [_integer(row.get("committed_mutations")) for row in selected]
    safety = [row.get("safety_pass") for row in selected]
    if any(value is None for value in mutations) or not all(isinstance(value, bool) for value in safety):
        return result
    result.update(
        status="MEASURED_BALANCED_REPEATS",
        committed_mutations=sum(int(value) for value in mutations if value is not None),
        safety="PASS" if all(safety) else "FAIL",
    )
    for name, values in metric_values.items():
        result[name] = statistics.mean(float(value) for value in values if value is not None)
    return result


def _metric_delta(value: Any, baseline: Any) -> Any:
    left = _finite(value)
    right = _finite(baseline)
    return left - right if left is not None and right is not None else NOT_MEASURED


def _markdown_number(value: Any, digits: int = 3) -> str:
    number = _finite(value)
    return f"{number:.{digits}f}" if number is not None else f"`{NOT_MEASURED}`"


def _screen_cell(rows: Sequence[Mapping[str, Any]], *, mode: str, size: int) -> str:
    selected = [
        row
        for row in rows
        if row.get("mode") == mode and row.get("workload") == f"prefix_{size}"
    ]
    if len(selected) != 1 or selected[0].get("evidence_status") != "MEASURED_COMPLETE":
        return f"`{NOT_MEASURED}`"
    row = selected[0]
    safety = row.get("safety_pass")
    mutations = _integer(row.get("committed_mutations"))
    if not isinstance(safety, bool) or mutations is None:
        return f"`{NOT_MEASURED}`"
    return f"{'PASS' if safety else 'FAIL'}; mutations={mutations}"


def _native_closed_loop_report(rows: Sequence[Mapping[str, Any]]) -> str:
    summaries = {
        (mode, scale): _balanced_full_summary(rows, mode=mode, scale=scale)
        for _policy, mode in POLICY_MODES
        for scale in FULL_SCALES
    }
    lines = [
        "# G4IRSF25 native closed loop",
        "",
        "This report is derived only from G25 native campaign run rows. HCA and G24 static-corridor results are not inferred here.",
        "A 1x/2x value is measured only when repeat 0 and repeat 1 both contain complete timing populations; negative deltas are faster than S4.",
        "",
        "| policy | scale | balanced evidence | mean s | p95 s | p99 s | max s | mean ΔS4 s | p95 ΔS4 s | p99 ΔS4 s | max ΔS4 s | mutations | safety |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for policy, mode in POLICY_MODES:
        for scale in FULL_SCALES:
            summary = summaries[(mode, scale)]
            baseline = summaries[("off", scale)]
            lines.append(
                f"| {policy} | {scale}x | `{summary['status']}` "
                f"| {_markdown_number(summary['processed_attempt_mean_seconds'])} "
                f"| {_markdown_number(summary['processed_attempt_p95_seconds'])} "
                f"| {_markdown_number(summary['processed_attempt_p99_seconds'])} "
                f"| {_markdown_number(summary['processed_attempt_max_seconds'])} "
                f"| {_markdown_number(_metric_delta(summary['processed_attempt_mean_seconds'], baseline['processed_attempt_mean_seconds']))} "
                f"| {_markdown_number(_metric_delta(summary['processed_attempt_p95_seconds'], baseline['processed_attempt_p95_seconds']))} "
                f"| {_markdown_number(_metric_delta(summary['processed_attempt_p99_seconds'], baseline['processed_attempt_p99_seconds']))} "
                f"| {_markdown_number(_metric_delta(summary['processed_attempt_max_seconds'], baseline['processed_attempt_max_seconds']))} "
                f"| {summary['committed_mutations']} | `{summary['safety']}` |"
            )
    lines.extend(
        [
            "",
            "## Native prefix screens",
            "",
            "| policy | 144 | 512 | 8192 |",
            "|---|---|---|---|",
        ]
    )
    for policy, mode in POLICY_MODES:
        lines.append(
            f"| {policy} | {_screen_cell(rows, mode=mode, size=144)} "
            f"| {_screen_cell(rows, mode=mode, size=512)} "
            f"| {_screen_cell(rows, mode=mode, size=8192)} |"
        )
    lines.extend(
        [
            "",
            "Incomplete or absent populations remain literal `NOT_MEASURED`; they are never converted to zero benefit, zero mutation, or a tail statistic.",
            "",
        ]
    )
    return "\n".join(lines)


def _bounded_scale_summary(
    rows: Sequence[Mapping[str, Any]], *, mode: str, duration: float
) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row.get("mode") == mode
        and row.get("execution_mode") == "bounded"
        and _integer(row.get("scale")) == BOUNDED_SCALE
        and _finite(row.get("bounded_wall_seconds")) is not None
        and math.isclose(float(row["bounded_wall_seconds"]), duration, abs_tol=1.0e-9)
    ]
    unmeasured = {
        "status": NOT_MEASURED,
        "released": NOT_MEASURED,
        "requested": NOT_MEASURED,
        "completed": NOT_MEASURED,
        "backlog": NOT_MEASURED,
        "completion_fraction": NOT_MEASURED,
        "events_per_completed_segment": NOT_MEASURED,
        "committed_mutations": NOT_MEASURED,
        "safety": NOT_MEASURED,
        **{name: NOT_MEASURED for name in _FULL_REPORT_FIELDS},
    }
    if len(selected) != 1 or selected[0].get("evidence_status") != "MEASURED_BOUNDED_PROGRESS":
        return unmeasured
    row = selected[0]
    requested = _integer(row.get("segments_requested"))
    released = _integer(row.get("segments_released"))
    completed = _integer(row.get("segments_completed"))
    backlog = _integer(row.get("current_backlog"))
    mutations = _integer(row.get("committed_mutations"))
    safety = row.get("safety_pass")
    if any(value is None for value in (requested, released, completed, backlog, mutations)) or not isinstance(safety, bool):
        return unmeasured
    return {
        "status": str(row.get("status", NOT_MEASURED)),
        "released": released,
        "requested": requested,
        "completed": completed,
        "backlog": backlog,
        "completion_fraction": completed / requested if requested else NOT_MEASURED,
        "events_per_completed_segment": row.get("events_per_completed_segment", NOT_MEASURED),
        "committed_mutations": mutations,
        "safety": "PASS" if safety else "FAIL",
        **{name: NOT_MEASURED for name in _FULL_REPORT_FIELDS},
    }


def _scale_report(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# G4IRSF25 native scale",
        "",
        "This report contains only native G25 rows. The independent HCA scale report may be cross-referenced later; no HCA or G24-static value is synthesized here.",
        "Bounded 4x rows report progress counters, mutations, and safety. Their processed-attempt TTH distribution remains `NOT_MEASURED` unless a separate complete-population protocol supplies it.",
        "",
        "## Balanced full 1x/2x status",
        "",
        "| policy | 1x evidence | 1x safety | 2x evidence | 2x safety |",
        "|---|---|---|---|---|",
    ]
    for policy, mode in POLICY_MODES:
        one = _balanced_full_summary(rows, mode=mode, scale=1)
        two = _balanced_full_summary(rows, mode=mode, scale=2)
        lines.append(
            f"| {policy} | `{one['status']}` | `{one['safety']}` | `{two['status']}` | `{two['safety']}` |"
        )
    lines.extend(
        [
            "",
            "## Bounded 4x progress",
            "",
            "| policy | window | status | released/requested | completed/requested | backlog | completion | events/completed | mutations | safety | mean/p95/p99/max TTH s |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for policy, mode in POLICY_MODES:
        for duration in (60.0, 180.0):
            summary = _bounded_scale_summary(rows, mode=mode, duration=duration)
            released = (
                f"{summary['released']}/{summary['requested']}"
                if _integer(summary["released"]) is not None and _integer(summary["requested"]) is not None
                else f"`{NOT_MEASURED}`"
            )
            completed = (
                f"{summary['completed']}/{summary['requested']}"
                if _integer(summary["completed"]) is not None and _integer(summary["requested"]) is not None
                else f"`{NOT_MEASURED}`"
            )
            completion_fraction = _finite(summary["completion_fraction"])
            completion = (
                f"{completion_fraction:.3%}" if completion_fraction is not None else f"`{NOT_MEASURED}`"
            )
            tails = "/".join(
                _markdown_number(summary[name]) for name in _FULL_REPORT_FIELDS
            )
            lines.append(
                f"| {policy} | {duration:g}s | `{summary['status']}` | {released} | {completed} "
                f"| {summary['backlog']} | {completion} | {_markdown_number(summary['events_per_completed_segment'])} "
                f"| {summary['committed_mutations']} | `{summary['safety']}` | {tails} |"
            )
    lines.extend(
        [
            "",
            "For incomplete or absent full populations, latency and tail claims remain literal `NOT_MEASURED`.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_campaign(
    *,
    binary: Path,
    release_csv: Path,
    artifacts: Mapping[str, Mapping[str, Any]],
    artifact_paths: Mapping[str, Path] | None = None,
    output_json: Path = DEFAULT_RUN_JSON,
    output_csv: Path = DEFAULT_RUN_CSV,
    native_report: Path = DEFAULT_NATIVE_REPORT,
    scale_csv: Path = DEFAULT_SCALE_CSV,
    scale_report: Path = DEFAULT_SCALE_REPORT,
    screen_sizes: Sequence[int] = SCREEN_SIZES,
    full_scales: Sequence[int] = FULL_SCALES,
    bounded_seconds: Sequence[float] = (60.0, 180.0),
    plan_only: bool = False,
    executor: Executor = cpp_backend.g4irsf11_event_runtime_from_records,
) -> dict[str, Any]:
    modes = {label: str(artifact["mode"]) for label, artifact in artifacts.items()}
    specs = build_run_plan(
        modes,
        screen_sizes=screen_sizes,
        full_scales=full_scales,
        bounded_seconds=bounded_seconds,
    )
    rows = [_unmeasured_run(spec) for spec in specs]
    artifact_paths = artifact_paths or {}

    def apply_provenance(
        row: dict[str, Any], spec: Mapping[str, Any], workload: Mapping[str, Any] | str
    ) -> None:
        label = str(spec["arm"])
        source = artifact_paths.get(label)
        row.update(
            release_csv=_portable(release_csv),
            artifact_label=label,
            artifact_mode=str(spec["mode"]),
            artifact_path=(
                "NOT_APPLICABLE"
                if label == "S4"
                else (_portable(Path(source)) if source is not None else NOT_MEASURED)
            ),
            workload_descriptor=(dict(workload) if isinstance(workload, Mapping) else workload),
        )

    for row, spec in zip(rows, specs):
        apply_provenance(row, spec, NOT_MEASURED)

    def persist() -> None:
        document = _campaign_document(rows, binary, release_csv)
        scale_rows = [row for row in rows if str(row.get("workload", "")).startswith("scale_")]
        _atomic_publish_texts(
            (
                (output_json, _json_text(document)),
                (output_csv, _run_csv_text(rows)),
                (native_report, _native_closed_loop_report(rows)),
                (scale_csv, _run_csv_text(scale_rows)),
                (scale_report, _scale_report(rows)),
            )
        )

    if plan_only:
        for row in rows:
            row["not_measured_reason"] = "PLAN_ONLY"
        persist()
        return _campaign_document(rows, binary, release_csv)

    loaded_workload: str | None = None
    workload_rows: list[dict[str, Any]] = []
    descriptor: dict[str, Any] = {}
    prefix_case: route.RouteCase | None = None

    def run_index(index: int) -> None:
        nonlocal loaded_workload, workload_rows, descriptor, prefix_case
        spec = specs[index]
        try:
            if spec["workload"] != loaded_workload:
                workload_rows, descriptor, prefix_case = _load_workload(spec, release_csv)
                _require(descriptor.get("topology_changed") is False, "workload changed the canonical topology")
                loaded_workload = str(spec["workload"])
            artifact = artifacts.get(str(spec["arm"]))
            rows[index], _trajectories = _execute_native(
                spec,
                rows=workload_rows,
                prefix_case=prefix_case,
                binary=binary,
                artifact=artifact,
                executor=executor,
            )
            apply_provenance(rows[index], spec, descriptor)
            if _is_measured_row(rows[index]):
                persist()
        except Exception as exc:
            rows[index]["status"] = "ERROR"
            rows[index]["evidence_status"] = NOT_MEASURED
            rows[index]["not_measured_reason"] = "EXECUTION_ERROR"
            rows[index]["error"] = f"{type(exc).__name__}: {exc}"
            raise

    screen_indices = [
        index for index, spec in enumerate(specs) if spec["execution_mode"] == "screen_full"
    ]
    later_indices = [
        index for index, spec in enumerate(specs) if spec["execution_mode"] != "screen_full"
    ]
    for index in screen_indices:
        run_index(index)

    gates = _screen_stage_gates(rows, list(artifacts))
    for index in later_indices:
        gate = gates[str(specs[index]["arm"])]
        if not gate["passed"]:
            rows[index]["not_measured_reason"] = gate["not_measured_reason"]
    if any(_is_measured_row(rows[index]) for index in screen_indices):
        persist()

    for index in later_indices:
        if gates[str(specs[index]["arm"])]["passed"]:
            run_index(index)
    return _campaign_document(rows, binary, release_csv)


_TRAJECTORY_FIELDS = (
    "schema_id",
    "runtime_bag_id",
    "task_id",
    "segment_id",
    "leg",
    "task_class",
    "goal_node",
    "branch_node",
    "s4_first_edge",
    "selected_first_edge",
    "rejoin_node",
    "decision_time",
    "arrival_time",
    "actual_corridor_duration",
    "private_bag_cost_seconds",
    "corridor_wait_seconds",
    "local_queue_area_bag_seconds",
    "scheduled_incoming_area_bag_seconds",
    "peak_local_queue",
    "peak_local_queue_semantics",
    "intermediate_decision_count",
    "actual_path",
    "selected_features",
    "feedback_sample_count",
    "feedback_short_ewma_seconds",
    "feedback_long_ewma_seconds",
    "feedback_trend_seconds",
    "feedback_timeout_rate",
    "feedback_short_local_system_cost",
    "feedback_long_local_system_cost",
    "applied_online_bias",
    "completed_rejoin",
    "timeout",
    "censored",
    "censor_reason",
    "loop",
    "safe",
)


def _compact_trajectory(
    row: Mapping[str, Any], *, scale: int, run_id: str
) -> dict[str, Any]:
    missing = [name for name in _TRAJECTORY_FIELDS if name not in row]
    if missing:
        raise G25CampaignError(f"native trajectory lacks {missing[0]}")
    return {"scale": scale, "run_id": run_id, **{name: row[name] for name in _TRAJECTORY_FIELDS}}


def _trajectory_stats(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean": NOT_MEASURED,
            "median": NOT_MEASURED,
            "p95": NOT_MEASURED,
            "p99": NOT_MEASURED,
            "max": NOT_MEASURED,
        }
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": _quantile(values, 0.95),
        "p99": _quantile(values, 0.99),
        "max": max(values),
    }


def aggregate_trajectories(
    rows: Iterable[Mapping[str, Any]],
    *,
    expected_arms: Sequence[Mapping[str, Any]],
    run_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups: dict[tuple[int, int, int, int], dict[str, Any]] = {}

    def group_for(key: tuple[int, int, int, int]) -> dict[str, Any]:
        if key not in groups:
            groups[key] = {
                "trajectory_count": 0,
                "completed_rejoin_count": 0,
                "timeout_count": 0,
                "censored_count": 0,
                "censor_reasons": Counter(),
                "loop_count": 0,
                "unsafe_count": 0,
                "intermediate_redecision_count": 0,
                "paths": Counter(),
                "durations": [],
                "private_costs": [],
                "corridor_waits": [],
                "queue_areas": [],
            }
        return groups[key]

    for row in rows:
        key = (
            int(row["scale"]),
            int(row["branch_node"]),
            int(row["selected_first_edge"]),
            int(row["rejoin_node"]),
        )
        group = group_for(key)
        group["trajectory_count"] += 1
        group["completed_rejoin_count"] += int(row.get("completed_rejoin") is True)
        group["timeout_count"] += int(row.get("timeout") is True)
        group["censored_count"] += int(row.get("censored") is True)
        if row.get("censored") is True:
            group["censor_reasons"][str(row.get("censor_reason") or "UNSPECIFIED")] += 1
        group["loop_count"] += int(row.get("loop") is True)
        group["unsafe_count"] += int(row.get("safe") is not True)
        group["intermediate_redecision_count"] += int(row.get("intermediate_decision_count", 0))
        path = row.get("actual_path")
        if isinstance(path, list):
            group["paths"][">".join(str(node) for node in path)] += 1
        for source, target in (
            ("actual_corridor_duration", "durations"),
            ("private_bag_cost_seconds", "private_costs"),
            ("corridor_wait_seconds", "corridor_waits"),
            ("local_queue_area_bag_seconds", "queue_areas"),
        ):
            value = _finite(row.get(source))
            if value is not None:
                group[target].append(value)

    measured_scales = {
        int(row["scale"])
        for row in run_rows
        if _is_measured_row(row)
    }
    for scale in measured_scales:
        for arm in expected_arms:
            group_for(
                (
                    scale,
                    int(arm["branch_node"]),
                    int(arm["first_edge"]),
                    int(arm["rejoin_node"]),
                )
            )

    coverage_rows: list[dict[str, Any]] = []
    for (scale, branch, first_edge, rejoin), values in sorted(groups.items()):
        coverage_rows.append(
            {
                "scale": scale,
                "branch_node": branch,
                "first_edge": first_edge,
                "rejoin_node": rejoin,
                "trajectory_count": values["trajectory_count"],
                "completed_rejoin_count": values["completed_rejoin_count"],
                "timeout_count": values["timeout_count"],
                "censored_count": values["censored_count"],
                "censor_reasons": dict(sorted(values["censor_reasons"].items())),
                "loop_count": values["loop_count"],
                "unsafe_count": values["unsafe_count"],
                "intermediate_redecision_count": values["intermediate_redecision_count"],
                "distinct_actual_path_count": len(values["paths"]),
                "actual_path_counts": dict(sorted(values["paths"].items())),
                "actual_corridor_duration_seconds": _trajectory_stats(values["durations"]),
                "private_bag_cost_seconds": _trajectory_stats(values["private_costs"]),
                "corridor_wait_seconds": _trajectory_stats(values["corridor_waits"]),
                "local_queue_area_bag_seconds": _trajectory_stats(values["queue_areas"]),
            }
        )

    total = sum(row["trajectory_count"] for row in coverage_rows)
    classified = sum(
        row["completed_rejoin_count"] + row["timeout_count"] + row["censored_count"]
        for row in coverage_rows
    )
    _require(classified == total, "trajectory terminal classification is not exhaustive")
    expected_keys = {
        (scale, int(arm["branch_node"]), int(arm["first_edge"]))
        for scale in measured_scales
        for arm in expected_arms
    }
    observed_keys = {
        (row["scale"], row["branch_node"], row["first_edge"])
        for row in coverage_rows
        if row["trajectory_count"] > 0
    }
    return {
        "schema": TRAJECTORY_COVERAGE_SCHEMA,
        "status": "MEASURED" if measured_scales else NOT_MEASURED,
        "registered_branch_count": len({int(arm["branch_node"]) for arm in expected_arms}),
        "registered_arm_count": len(expected_arms),
        "measured_scales": sorted(measured_scales),
        "trajectory_count": total,
        "completed_rejoin_count": sum(row["completed_rejoin_count"] for row in coverage_rows),
        "timeout_count": sum(row["timeout_count"] for row in coverage_rows),
        "censored_count": sum(row["censored_count"] for row in coverage_rows),
        "loop_count": sum(row["loop_count"] for row in coverage_rows),
        "unsafe_count": sum(row["unsafe_count"] for row in coverage_rows),
        "observed_registered_arm_fraction": (
            len(expected_keys & observed_keys) / len(expected_keys) if expected_keys else NOT_MEASURED
        ),
        "runs": list(run_rows),
        "coverage": coverage_rows,
    }


def _trajectory_report(coverage: Mapping[str, Any], raw_path: Path) -> str:
    lines = [
        "# G4IRSF25 real corridor trajectories",
        "",
        f"- Status: `{coverage['status']}`.",
        f"- Compact raw rows: `{_portable(raw_path)}` (build evidence; identity is trace-only).",
        f"- Registered branches/arms: {coverage['registered_branch_count']} / {coverage['registered_arm_count']}.",
        f"- Real trajectories / completed rejoin / timeout / censored / loop / unsafe: "
        f"{coverage['trajectory_count']} / {coverage['completed_rejoin_count']} / "
        f"{coverage['timeout_count']} / {coverage['censored_count']} / "
        f"{coverage['loop_count']} / {coverage['unsafe_count']}.",
        "- Absolute time and bag/task/segment identity are excluded from every exported policy artifact.",
        "",
        "| scale | branch | edge | rejoin | trajectories | completed | timeout | censored | paths | redecisions |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in coverage["coverage"]:
        lines.append(
            f"| {row['scale']}x | {row['branch_node']} | {row['first_edge']} | {row['rejoin_node']} "
            f"| {row['trajectory_count']} | {row['completed_rejoin_count']} | {row['timeout_count']} "
            f"| {row['censored_count']} | {row['distinct_actual_path_count']} "
            f"| {row['intermediate_redecision_count']} |"
        )
    lines.extend(
        [
            "",
            "A zero row means the registered arm was genuinely not selected in a measured observe run; "
            "an absent/unrun scale is `NOT_MEASURED`, not a zero-support claim.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            _require(isinstance(value, dict), f"trajectory JSONL line {line_number} is not an object")
            yield value


def collect_observe_trajectories(
    *,
    binary: Path,
    release_csv: Path,
    artifact: Mapping[str, Any],
    raw_output: Path = DEFAULT_TRAJECTORY_RAW,
    coverage_output: Path = DEFAULT_COVERAGE,
    report_output: Path = DEFAULT_TRAJECTORY_REPORT,
    scales: Sequence[int] = (1, 2),
    bounded_seconds: Sequence[float] = (),
    executor: Executor = cpp_backend.g4irsf11_event_runtime_from_records,
) -> dict[str, Any]:
    _require(artifact.get("mode") == "observe", "trajectory collection requires an observe artifact")
    _require(all(scale in FULL_SCALES for scale in scales), "observe full scales must be 1 and/or 2")
    specs: list[dict[str, Any]] = []
    for scale in scales:
        specs.append(
            {
                "run_id": f"observe_{scale}x",
                "arm": "OBSERVE",
                "mode": "observe",
                "family": "OBSERVATION",
                "workload": f"scale_{scale}x",
                "scale": scale,
                "execution_mode": "full",
                "repeat": 0,
                "order_index": 0,
                "bounded_wall_seconds": NOT_MEASURED,
            }
        )
    for ordinal, duration in enumerate(bounded_seconds):
        _require(duration > 0.0, "observe bounded duration must be positive")
        specs.append(
            {
                "run_id": f"observe_4x_{duration:g}s",
                "arm": "OBSERVE",
                "mode": "observe",
                "family": "OBSERVATION",
                "workload": f"scale_4x_{duration:g}s",
                "scale": 4,
                "execution_mode": "bounded",
                "repeat": ordinal,
                "order_index": 0,
                "bounded_wall_seconds": float(duration),
            }
        )

    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text("", encoding="utf-8")
    run_rows: list[dict[str, Any]] = []
    for spec in specs:
        rows, descriptor, prefix_case = _load_workload(spec, release_csv)
        _require(descriptor.get("topology_changed") is False, "observe workload changed topology")
        run_row, trajectories = _execute_native(
            spec,
            rows=rows,
            prefix_case=prefix_case,
            binary=binary,
            artifact=artifact,
            executor=executor,
        )
        run_rows.append(run_row)
        with raw_output.open("a", encoding="utf-8") as handle:
            for trajectory in trajectories:
                handle.write(json.dumps(trajectory, sort_keys=True, allow_nan=False) + "\n")

    expected_arms = artifact.get("arms")
    _require(isinstance(expected_arms, list), "observe artifact lacks arms")
    coverage = aggregate_trajectories(
        _read_jsonl(raw_output), expected_arms=expected_arms, run_rows=run_rows
    )
    coverage["raw_trajectory_path"] = _portable(raw_output)
    _write_json(coverage_output, coverage)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(_trajectory_report(coverage, raw_output), encoding="utf-8")
    return coverage


def _csv_integers(value: str) -> tuple[int, ...]:
    if not value.strip():
        return ()
    try:
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc


def _csv_numbers(value: str) -> tuple[float, ...]:
    if not value.strip():
        return ()
    try:
        return tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated numbers") from exc


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    artifact = subparsers.add_parser("artifact", help="build the verified eight-arm observe artifact")
    artifact.add_argument("--source", type=Path, default=DEFAULT_G24_CORRIDORS)
    artifact.add_argument("--output", type=Path, default=DEFAULT_OBSERVE_ARTIFACT)

    observe = subparsers.add_parser("observe", help="collect real S4 corridor trajectories")
    observe.add_argument("--binary", type=Path, required=True)
    observe.add_argument("--release-csv", type=Path, required=True)
    observe.add_argument("--artifact", type=Path, default=DEFAULT_OBSERVE_ARTIFACT)
    observe.add_argument("--scales", type=_csv_integers, default=(1, 2))
    observe.add_argument("--bounded-seconds", type=_csv_numbers, default=())
    observe.add_argument("--raw-output", type=Path, default=DEFAULT_TRAJECTORY_RAW)
    observe.add_argument("--coverage-output", type=Path, default=DEFAULT_COVERAGE)
    observe.add_argument("--report-output", type=Path, default=DEFAULT_TRAJECTORY_REPORT)

    campaign = subparsers.add_parser("campaign", help="run or materialize the balanced native campaign")
    campaign.add_argument("--binary", type=Path, required=True)
    campaign.add_argument("--release-csv", type=Path, required=True)
    campaign.add_argument("--artifact", action="append", default=[], metavar="LABEL=PATH")
    campaign.add_argument("--screen-sizes", type=_csv_integers, default=SCREEN_SIZES)
    campaign.add_argument("--full-scales", type=_csv_integers, default=FULL_SCALES)
    campaign.add_argument("--bounded-seconds", type=_csv_numbers, default=(60.0, 180.0))
    campaign.add_argument("--output-json", type=Path, default=DEFAULT_RUN_JSON)
    campaign.add_argument("--output-csv", type=Path, default=DEFAULT_RUN_CSV)
    campaign.add_argument("--native-report", type=Path, default=DEFAULT_NATIVE_REPORT)
    campaign.add_argument("--scale-csv", type=Path, default=DEFAULT_SCALE_CSV)
    campaign.add_argument("--scale-report", type=Path, default=DEFAULT_SCALE_REPORT)
    campaign.add_argument("--plan-only", action="store_true")
    return parser.parse_args(argv)


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "artifact":
        output = _rooted(args.output)
        payload = build_observe_artifact(_rooted(args.source).resolve(strict=True))
        _write_json(output, payload)
        print(json.dumps({"status": "PASS", "arms": len(payload["arms"]), "output": str(output)}))
        return 0
    if args.command == "observe":
        artifact = _read_json(_rooted(args.artifact).resolve(strict=True))
        payload = collect_observe_trajectories(
            binary=args.binary.resolve(strict=True),
            release_csv=args.release_csv.resolve(strict=True),
            artifact=artifact,
            raw_output=_rooted(args.raw_output),
            coverage_output=_rooted(args.coverage_output),
            report_output=_rooted(args.report_output),
            scales=args.scales,
            bounded_seconds=args.bounded_seconds,
        )
        print(json.dumps({"status": payload["status"], "trajectories": payload["trajectory_count"]}))
        return 0
    artifacts, artifact_paths = _load_artifact_specs(args.artifact)
    payload = execute_campaign(
        binary=args.binary.resolve(strict=True),
        release_csv=args.release_csv.resolve(strict=True),
        artifacts=artifacts,
        artifact_paths=artifact_paths,
        output_json=_rooted(args.output_json),
        output_csv=_rooted(args.output_csv),
        native_report=_rooted(args.native_report),
        scale_csv=_rooted(args.scale_csv),
        scale_report=_rooted(args.scale_report),
        screen_sizes=args.screen_sizes,
        full_scales=args.full_scales,
        bounded_seconds=args.bounded_seconds,
        plan_only=args.plan_only,
    )
    print(
        json.dumps(
            {
                "status": "PLAN_ONLY" if args.plan_only else "COMPLETE",
                "measured_runs": payload["measured_run_count"],
                "not_measured_runs": payload["not_measured_run_count"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

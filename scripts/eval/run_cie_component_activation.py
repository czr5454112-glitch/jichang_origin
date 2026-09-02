#!/usr/bin/env python3
"""Build and run the activation-first G31 load scan.

Intermediate loads are generated at the flight-manifest level.  The original
day is retained and a deterministic subset of the G29 inserted flights is
added; already-expanded transport segments are never sampled or copied.
The selected flight keys are projected onto map2 and Nanning identically.

The ``run`` command executes the complete G31 S4 policy (service-aware static
potential, strict descent, direct-neighbour calendar visibility, M3/J2 and E2)
with bounded streaming activation counters enabled.  The ``aggregate``
command classifies activation without treating survivor timing as evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from czr005.io.legacy_tasks import (  # noqa: E402
    RawLegacyTask,
    expand_tasks,
    parse_legacy_tasks,
    write_task_jsonl,
)
from scripts.eval import cie_fixed_denominator_business as cie_business  # noqa: E402
from scripts.eval import g4irsf31_map_adapter as map_adapter  # noqa: E402
from scripts.eval import run_g4irsf24_native_race as g24  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402
from scripts.eval import run_g4irsf29_workload as g29  # noqa: E402
from scripts.eval import run_g4irsf31_map2_native as map2_native  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_native as nanning_native  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_workload as nanning_workload  # noqa: E402


SCHEMA_LOADS = "czr005.cie_component_activation.loads.v1"
SCHEMA_RUN = "czr005.cie_component_activation.run.v1"
INTERMEDIATE_FACTORS = (1.25, 1.50, 1.75)
SCAN_FACTORS = (1.0, 1.25, 1.50, 1.75, 2.0)
MAPS = ("map2", "nanning")
SPEED_MPS = 2.5
FIXED_END_EPOCH = 98_259.0
MAX_EVENTS = 60_000_000
COMPONENTS = ("Q", "I", "wc", "ws")

DEFAULT_SOURCE_RAW = ROOT / "legacy/jichang_origin_readonly/inputdata.txt"
DEFAULT_NANNING_PROFILE = ROOT / "data/processed/maps/nanning_airport_profile.json"
DEFAULT_LOAD_DIR = ROOT / "artifacts/tasks/cie_component_activation"
DEFAULT_LOAD_MANIFEST = DEFAULT_LOAD_DIR / "load_manifest.json"
DEFAULT_RESULT_ROOT = ROOT / "outputs/runtime/cie_component_activation"
DEFAULT_REVISION_MANIFEST = ROOT / "configs/eval/cie_revision_manifest.yaml"
DEFAULT_ACTIVATION_CSV = ROOT / "outputs/tables/cie_component_activation.csv"
DEFAULT_CHANGES_CSV = (
    ROOT / "outputs/tables/cie_component_counterfactual_action_changes.csv"
)
DEFAULT_REPORT = ROOT / "outputs/reports/cie_component_activation_audit.md"

FlightKey = tuple[float, int, str]
StreamKey = tuple[int, str]


class ActivationError(RuntimeError):
    """Raised when a load or activation artifact violates its contract."""


def _factor_label(value: float | str) -> str:
    factor = float(value)
    if not math.isfinite(factor):
        raise ActivationError("load factor must be finite")
    return f"{factor:.2f}"


def _flight_key(task: RawLegacyTask) -> FlightKey:
    if task.unloader is None:
        raise ActivationError("flight grouping requires Unloader")
    return float(task.std), int(task.end), str(task.unloader)


def _stream_key(flight: FlightKey) -> StreamKey:
    return int(flight[1]), str(flight[2])


def _flight_record(flight: FlightKey) -> dict[str, Any]:
    return {"std": flight[0], "end": flight[1], "unloader": flight[2]}


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


def _portable(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                   allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _atomic_raw(header: str, rows: Sequence[RawLegacyTask], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    g29.write_raw_tasks(header, rows, temporary)
    os.replace(temporary, path)


def _atomic_jsonl(rows: Iterable[Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    write_task_jsonl(rows, temporary)
    os.replace(temporary, path)


def largest_remainder_quotas(
    counts: Mapping[StreamKey, int], selected_total: int
) -> dict[StreamKey, int]:
    """Allocate ``selected_total`` proportionally with deterministic ties."""

    if selected_total < 0 or selected_total > sum(counts.values()):
        raise ActivationError("selected flight count is outside the source range")
    total = sum(counts.values())
    if total <= 0:
        raise ActivationError("at least one source flight is required")
    exact = {
        stream: selected_total * int(count) / total
        for stream, count in counts.items()
    }
    quotas = {stream: math.floor(value) for stream, value in exact.items()}
    remaining = selected_total - sum(quotas.values())
    order = sorted(
        counts,
        key=lambda stream: (-(exact[stream] - quotas[stream]), stream),
    )
    for stream in order[:remaining]:
        quotas[stream] += 1
    if any(quotas[key] > counts[key] for key in counts):
        raise ActivationError("largest-remainder allocation exceeded a stream")
    return quotas


def _uniform_indices(count: int, selected: int) -> tuple[int, ...]:
    if selected < 0 or selected > count:
        raise ActivationError("uniform selection size is outside its stream")
    if selected == 0:
        return ()
    # Midpoint systematic sampling avoids a permanent first/last-flight bias.
    indices = tuple(math.floor((rank + 0.5) * count / selected)
                    for rank in range(selected))
    if len(set(indices)) != selected or any(index >= count for index in indices):
        raise ActivationError("uniform flight selection was not one-to-one")
    return indices


def select_inserted_flights(
    raw_tasks: Sequence[RawLegacyTask], factor: float
) -> tuple[tuple[FlightKey, ...], dict[str, Any]]:
    """Select complete parent flights for one intermediate nominal factor."""

    if factor < 1.0 or factor > 2.0:
        raise ActivationError("factor must be within [1, 2]")
    by_flight: dict[FlightKey, list[RawLegacyTask]] = defaultdict(list)
    for task in raw_tasks:
        by_flight[_flight_key(task)].append(task)
    by_stream: dict[StreamKey, list[FlightKey]] = defaultdict(list)
    for flight in by_flight:
        by_stream[_stream_key(flight)].append(flight)
    for flights in by_stream.values():
        flights.sort()

    selected_total = round((factor - 1.0) * len(by_flight))
    counts = {stream: len(flights) for stream, flights in by_stream.items()}
    quotas = largest_remainder_quotas(counts, selected_total)
    selected: list[FlightKey] = []
    per_stream: dict[str, Any] = {}
    for stream in sorted(by_stream):
        indices = _uniform_indices(len(by_stream[stream]), quotas[stream])
        chosen = [by_stream[stream][index] for index in indices]
        selected.extend(chosen)
        label = f"{stream[0]}|{stream[1]}"
        per_stream[label] = {
            "source_flight_count": len(by_stream[stream]),
            "quota": quotas[stream],
            "selected_indices_zero_based": list(indices),
            "selected_flight_keys": [_flight_record(value) for value in chosen],
        }
    selected.sort()
    records = [_flight_record(value) for value in selected]
    return tuple(selected), {
        "method": "largest_remainder_by_stream_then_midpoint_systematic_within_stream",
        "nominal_factor": factor,
        "source_flight_count": len(by_flight),
        "stream_count": len(by_stream),
        "selected_inserted_flight_count": len(selected),
        "target_inserted_flight_count": selected_total,
        "selected_flight_keys": records,
        "selected_flight_keys_sha256": _json_sha256(records),
        "per_stream": per_stream,
    }


def build_factor_raw_tasks(
    raw_tasks: Sequence[RawLegacyTask], factor: float
) -> tuple[tuple[RawLegacyTask, ...], dict[str, Any], int]:
    """Return the full original day plus selected complete inserted flights."""

    selected, selection = select_inserted_flights(raw_tasks, factor)
    selected_set = set(selected)
    full, _flight_rows, generation = g29.densify_flight_timetable(raw_tasks)
    offset = int(generation["inserted_id_offset"])
    parent_by_inserted_id = {
        offset + rank: _flight_key(task) for rank, task in enumerate(raw_tasks)
    }
    generated = tuple(
        task
        for task in full
        if task.task_id < offset
        or parent_by_inserted_id.get(task.task_id) in selected_set
    )
    source_ids = {task.task_id for task in raw_tasks}
    inserted = [task for task in generated if task.task_id not in source_ids]
    by_source_flight = Counter(_flight_key(task) for task in raw_tasks)
    by_inserted_parent = Counter(parent_by_inserted_id[task.task_id]
                                 for task in inserted)
    if set(by_inserted_parent) != selected_set:
        raise ActivationError("one or more selected flights lost its inserted manifest")
    if any(by_inserted_parent[key] != by_source_flight[key]
           for key in selected_set):
        raise ActivationError("an inserted flight is not a complete source manifest")
    if len(generated) != len(raw_tasks) + len(inserted):
        raise ActivationError("generated population partition failed")
    selection = {
        **selection,
        "source_raw_bag_count": len(raw_tasks),
        "inserted_raw_bag_count": len(inserted),
        "generated_raw_bag_count": len(generated),
        "realized_raw_bag_factor": len(generated) / len(raw_tasks),
        "whole_flight_manifest_invariant": True,
        "expanded_segment_sampling_or_duplication": False,
    }
    return generated, selection, offset


def _artifact_description(
    raw_path: Path,
    canonical_path: Path,
    reparsed: Sequence[RawLegacyTask],
    expanded: Sequence[Any],
    selection_sha: str,
) -> dict[str, Any]:
    return {
        "raw_path": _portable(raw_path),
        "canonical_path": _portable(canonical_path),
        "raw_sha256": _file_sha256(raw_path),
        "canonical_sha256": _file_sha256(canonical_path),
        "raw_bag_count": len(reparsed),
        "expanded_segment_count": len(expanded),
        "flight_selection_sha256": selection_sha,
        "whole_flights_only": True,
    }


def generate_loads(
    *,
    source_raw_path: Path = DEFAULT_SOURCE_RAW,
    nanning_profile_path: Path = DEFAULT_NANNING_PROFILE,
    output_dir: Path = DEFAULT_LOAD_DIR,
    manifest_path: Path = DEFAULT_LOAD_MANIFEST,
) -> dict[str, Any]:
    """Generate the three intermediate factors for both registered maps."""

    source_raw_path = source_raw_path.resolve(strict=True)
    nanning_profile_path = nanning_profile_path.resolve(strict=True)
    header, source_raw = parse_legacy_tasks(source_raw_path)
    if len({task.task_id for task in source_raw}) != len(source_raw):
        raise ActivationError("source task IDs must be unique")
    source_stream_count = len(
        {_stream_key(_flight_key(task)) for task in source_raw}
    )
    if source_stream_count != 13:
        raise ActivationError(
            f"registered timetable must contain 13 streams, got {source_stream_count}"
        )

    profile = nanning_workload.load_map_profile(nanning_profile_path)
    projection = nanning_workload.build_original_projection(source_raw, profile)
    projected_original = nanning_workload._project_generated_tasks(
        source_raw, source_raw, projection, profile, inserted_id_offset=None
    )
    storage = nanning_workload.select_storage_pair(projected_original, profile)

    loads: dict[str, Any] = {}
    for factor in INTERMEDIATE_FACTORS:
        label = _factor_label(factor)
        generated, selection, inserted_offset = build_factor_raw_tasks(
            source_raw, factor
        )
        selected_sha = str(selection["selected_flight_keys_sha256"])

        map2_raw = output_dir / f"map2_{label}x_raw.txt"
        map2_canonical = output_dir / f"map2_{label}x_canonical.jsonl"
        _atomic_raw(header, generated, map2_raw)
        _header, reparsed_map2 = parse_legacy_tasks(map2_raw)
        expanded_map2 = expand_tasks(reparsed_map2)
        _atomic_jsonl(expanded_map2, map2_canonical)

        projected = nanning_workload._project_generated_tasks(
            source_raw,
            generated,
            projection,
            profile,
            inserted_id_offset=inserted_offset,
        )
        nanning_raw = output_dir / f"nanning_{label}x_raw.txt"
        nanning_canonical = output_dir / f"nanning_{label}x_canonical.jsonl"
        _atomic_raw(header, projected, nanning_raw)
        _header, reparsed_nanning = parse_legacy_tasks(nanning_raw)
        expanded_nanning = expand_tasks(
            reparsed_nanning,
            storage_in_goal=int(storage["storage_in_goal"]),
            storage_out_start=int(storage["storage_out_start"]),
        )
        _atomic_jsonl(expanded_nanning, nanning_canonical)

        map2_ids = {int(row.task_id) for row in expanded_map2}
        nanning_ids = {int(row.task_id) for row in expanded_nanning}
        if map2_ids != nanning_ids:
            raise ActivationError("map projections do not contain the same raw bags")
        loads[label] = {
            "selection": selection,
            "maps": {
                "map2": _artifact_description(
                    map2_raw, map2_canonical, reparsed_map2, expanded_map2,
                    selected_sha,
                ),
                "nanning": {
                    **_artifact_description(
                        nanning_raw,
                        nanning_canonical,
                        reparsed_nanning,
                        expanded_nanning,
                        selected_sha,
                    ),
                    "storage_pair": storage,
                },
            },
            "same_flight_selection_projected_to_both_maps": True,
            "same_raw_task_id_population_on_both_maps": True,
        }

    manifest = {
        "schema": SCHEMA_LOADS,
        "status": "COMPLETE",
        "protocol": "WHOLE_FLIGHT_INTERMEDIATE_DENSIFICATION",
        "source": {
            "path": _portable(source_raw_path),
            "sha256": _file_sha256(source_raw_path),
            "raw_bag_count": len(source_raw),
            "flight_count": len({_flight_key(task) for task in source_raw}),
            "stream_count": source_stream_count,
        },
        "nanning_map_profile": {
            "path": _portable(nanning_profile_path),
            "sha256": _file_sha256(nanning_profile_path),
        },
        "factors": [_factor_label(value) for value in INTERMEDIATE_FACTORS],
        "loads": loads,
        "invariants": {
            "complete_flight_manifests_only": True,
            "no_expanded_segment_sampling": True,
            "no_expanded_segment_duplication": True,
            "same_selected_flights_for_map2_and_nanning": True,
            "stream_quota_method": "largest_remainder",
            "within_stream_method": "midpoint_systematic",
        },
    }
    _atomic_json(manifest_path, manifest)
    return manifest


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ActivationError(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    required = {"segment_id", "task_id", "pass_time", "std", "start", "goal"}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not required.issubset(value):
                raise ActivationError(
                    f"canonical row {line_number} lacks required fields: {path}"
                )
            rows.append(value)
    segment_ids = [str(row["segment_id"]) for row in rows]
    if not rows or len(segment_ids) != len(set(segment_ids)):
        raise ActivationError("canonical population is empty or has duplicate segments")
    return tuple(rows)


def _manifest_reference(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve(strict=True)
    rooted = ROOT / path
    if rooted.exists():
        return rooted.resolve(strict=True)
    return (manifest_path.parent / path).resolve(strict=True)


def canonical_from_load_manifest(
    manifest_path: Path, factor: float, map_name: str
) -> tuple[Path, dict[str, Any]]:
    manifest_path = manifest_path.resolve(strict=True)
    manifest = _read_json(manifest_path)
    label = _factor_label(factor)
    if manifest.get("schema") != SCHEMA_LOADS:
        raise ActivationError("load manifest schema mismatch")
    try:
        cell = manifest["loads"][label]["maps"][map_name]
    except (KeyError, TypeError) as exc:
        raise ActivationError(f"manifest has no {map_name} {label}x cell") from exc
    if not isinstance(cell, Mapping):
        raise ActivationError("load manifest map cell must be an object")
    path = _manifest_reference(str(cell["canonical_path"]), manifest_path)
    if _file_sha256(path) != cell.get("canonical_sha256"):
        raise ActivationError("canonical workload hash differs from load manifest")
    return path, dict(cell)


def _profile_for_map(
    map_name: str, nanning_profile_path: Path
) -> map_adapter.RuntimeMapProfile:
    if map_name == "map2":
        return map2_native.map2_profile()
    if map_name == "nanning":
        return map_adapter.load_map_profile(
            nanning_profile_path.resolve(strict=True),
            storage_source_nodes=[nanning_native.STORAGE_NODE],
        )
    raise ActivationError(f"unsupported map: {map_name}")


def prepare_runtime_request(
    *,
    map_name: str,
    canonical_path: Path,
    binary: Path,
    nanning_profile_path: Path = DEFAULT_NANNING_PROFILE,
    scenario: str = "cie_component_activation",
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any], dict[str, Any]]:
    """Build the unchanged complete G31 request with activation counters."""

    canonical_path = canonical_path.resolve(strict=True)
    binary = binary.resolve(strict=True)
    rows = _read_jsonl(canonical_path)
    profile = _profile_for_map(map_name, nanning_profile_path)
    request, potential = map_adapter.build_s4_request(
        profile,
        rows,
        binary=binary,
        scenario=scenario,
        max_events=MAX_EVENTS,
        max_simulation_time=FIXED_END_EPOCH,
        trace_limit=0,
        event_trace_limit=0,
        summary_only=False,
        edge_speed_mps=SPEED_MPS,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
        complete_on_goal_arrival=True,
    )
    request["enable_cie_component_activation"] = True
    gates = {
        "scorer": request.get("scorer_mode") == "S4_queue_aware_rule_only",
        "service_aware_potential": potential.get("mode")
        == "SERVICE_AWARE_STATIC_LOCAL_POTENTIAL",
        "full_dynamic_mask": int(request.get("s4_score_component_mask", 15)) == 15,
        "m3": request.get("merge_grant_rule") == "M3",
        "jit_fair": request.get("merge_grant_timing_mode")
        == "jit_fair_aging_deadline",
        "strict_descent": request.get(
            "enable_s4_local_potential_descent_guard"
        ) is True,
        "direct_calendar": request.get(
            "enable_s4_direct_neighbor_merge_calendar_visibility"
        ) is True,
        "goal_arrival": request.get("complete_on_goal_arrival") is True,
        "activation": request.get("enable_cie_component_activation") is True,
        "fixed_horizon": request.get("max_simulation_time") == FIXED_END_EPOCH,
        "event_budget": request.get("max_events") == MAX_EVENTS,
        "e2": request.get("g4irsf20_event_hotpath_policy") == "E2",
    }
    if not all(gates.values()):
        raise ActivationError(f"G31 activation request identity failed: {gates}")
    contract = {
        "map": map_name,
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
        "event_hotpath_policy": request["g4irsf20_event_hotpath_policy"],
        "strict_descent": True,
        "direct_neighbor_calendar_visibility": True,
        "goal_arrival_completion": True,
        "component_activation": True,
        "fixed_end_epoch": FIXED_END_EPOCH,
        "max_events": MAX_EVENTS,
        "identity_gates": gates,
    }
    return rows, request, contract


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _request_sha256(request: Mapping[str, Any]) -> str:
    identity = {
        key: request.get(key)
        for key in (
            "node_records", "edge_records", "heuristic_time", "bag_records",
            "scorer_mode", "s4_score_component_mask", "queue_time_scaling",
            "merge_grant_rule", "merge_grant_timing_mode",
            "g4irsf20_event_hotpath_policy",
            "enable_s4_local_potential_descent_guard",
            "enable_s4_direct_neighbor_merge_calendar_visibility",
            "complete_on_goal_arrival", "enable_cie_component_activation",
            "max_simulation_time", "max_events",
        )
    }
    return _json_sha256(identity)


def _execution_integrity(
    summary: Mapping[str, Any],
    bags: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    expected = sorted(str(row["segment_id"]) for row in rows)
    actual = sorted(str(row.get("segment_id", "")) for row in bags)
    completed = int(summary.get("completed_count", -1))
    failed = int(summary.get("failed_count", -1))
    goals = {str(row["segment_id"]): int(row["goal"]) for row in rows}
    completed_at_correct_goal = all(
        not bool(row.get("completed"))
        or (
            str(row.get("segment_id", "")) in goals
            and int(row.get("final_node", -1))
            == goals[str(row.get("segment_id", ""))]
        )
        for row in bags
    )
    gates = {
        "terminal_partition": completed + failed == len(rows),
        "exact_segment_identity": actual == expected,
        "fixed_horizon_echo": float(summary.get(
            "declared_max_simulation_time", math.nan
        )) == FIXED_END_EPOCH,
        "event_budget_echo": int(summary.get("declared_max_events", -1))
        == MAX_EVENTS,
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "completed_at_correct_goal": completed_at_correct_goal,
        "fault_edge_violation_zero": summary.get(
            "physical_fault_edge_entry_violation_count"
        ) == 0,
        "reservation_conflicts_zero": summary.get("reservation_conflicts") == 0,
        "merge_grant_conservation": summary.get(
            "merge_grant_conservation_holds"
        ) is True,
        "merge_grant_active_bijection": summary.get(
            "merge_grant_active_bijection_holds"
        ) is True,
        "stable_fault_events_zero": summary.get("fault_event_count") == 0,
        "stable_repair_events_zero": summary.get("repair_event_count") == 0,
        "loaded_expected_binary": Path(
            str(summary.get("loaded_cpp_binary_path", ""))
        ).resolve()
        == Path(str(request["expected_binary_path"])).resolve(),
        "scorer_mode_echo": summary.get("scorer_mode_echo")
        == request.get("scorer_mode"),
        "activation_present": isinstance(
            summary.get("cie_component_activation"), Mapping
        ),
        "m3_echo": summary.get("merge_grant_rule") == "M3",
        "e2_echo": summary.get("g4irsf20_event_hotpath_policy") == "E2",
    }
    return {
        "pass": all(gates.values()),
        "gates": gates,
        "not_measured": [
            "reverse_or_unknown_edge_use_count",
            "peak_rss_bytes",
            "ebs_lifecycle_conservation",
            "p2_atomic_commit_rollback_conservation",
        ],
    }


def _timing_payload(
    rows: Sequence[Mapping[str, Any]],
    bags: Sequence[Mapping[str, Any]],
    *,
    complete: bool,
    factor: float,
) -> dict[str, Any]:
    """Apply the frozen full-population timing protocol to one scan cell."""

    if float(factor) == 2.0:
        return {
            "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
            "raw_bag_count": None,
            "survivor_or_common_cohort_used": False,
            "distributions": None,
        }
    if complete:
        distributions, raw = g24.timing_distributions(rows, bags)
        return {
            "status": "FULL_POPULATION_RAW_BAG_TIMING",
            "raw_bag_count": len(raw),
            "survivor_or_common_cohort_used": False,
            "distributions": distributions,
        }
    return {
        "status": "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
        "raw_bag_count": None,
        "survivor_or_common_cohort_used": False,
        "distributions": None,
    }


def execute_run(
    *,
    map_name: str,
    factor: float,
    canonical_path: Path,
    binary: Path,
    nanning_profile_path: Path = DEFAULT_NANNING_PROFILE,
    dry_run: bool = False,
    executor: Any | None = None,
    load_manifest_path: Path | None = None,
) -> dict[str, Any]:
    rows, request, contract = prepare_runtime_request(
        map_name=map_name,
        canonical_path=canonical_path,
        binary=binary,
        nanning_profile_path=nanning_profile_path,
        scenario=f"cie_activation_{map_name}_{_factor_label(factor)}x",
    )
    raw_count = len({int(row["task_id"]) for row in rows})
    provenance = {
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "binary_path": str(binary.resolve()),
        "binary_sha256": _file_sha256(binary.resolve()),
        "canonical_path": str(canonical_path.resolve()),
        "canonical_sha256": _file_sha256(canonical_path.resolve()),
        "load_manifest_path": (
            str(load_manifest_path.resolve()) if load_manifest_path else None
        ),
        "load_manifest_sha256": (
            _file_sha256(load_manifest_path.resolve()) if load_manifest_path else None
        ),
        "revision_manifest_path": str(DEFAULT_REVISION_MANIFEST.resolve()),
        "revision_manifest_sha256": _file_sha256(
            DEFAULT_REVISION_MANIFEST.resolve()
        ),
        "request_sha256": _request_sha256(request),
        "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
        "baseline_family": "G31_S4_NATIVE",
        "reproduction_or_adaptation_label": "NATIVE_CURRENT_SYSTEM",
        "release_protocol": "canonical_complete_flight_population",
        "coordination_protocol": "J2_M3_JIT_FAIR_AGING_DEADLINE",
        "random_seed": None,
        "peak_rss_bytes": "NOT_MEASURED",
        "survivor_timing_used": False,
    }
    common = {
        "schema": SCHEMA_RUN,
        "status": "READY_CIE_COMPONENT_ACTIVATION_DRY_RUN" if dry_run else None,
        "map": map_name,
        "nominal_load_factor": float(factor),
        "population": {
            "raw_bag_denominator": raw_count,
            "segment_count": len(rows),
            "whole_population": True,
        },
        "request_contract": contract,
        "provenance": provenance,
        "native_execution_started": not dry_run,
    }
    if dry_run:
        return common

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise ActivationError("native executor did not return summary and bags")
    if any(not isinstance(row, Mapping) for row in bags):
        raise ActivationError("native executor returned a non-object bag row")
    integrity = _execution_integrity(summary, bags, rows, request)
    outcome = g26.summarize_paper_outcome(
        rows, bags, total_raw_bags=raw_count
    )
    complete = (
        integrity["pass"]
        and int(summary.get("completed_count", -1)) == len(rows)
        and int(outcome["completed_raw_bag_count"]) == raw_count
    )
    timing = _timing_payload(rows, bags, complete=complete, factor=factor)
    on_time = outcome["success"]["finish_le_std"]
    fixed_business = cie_business.summarize(
        rows, bags, fixed_horizon=FIXED_END_EPOCH
    )
    return {
        **common,
        "status": "COMPLETE" if integrity["pass"] else "FAILED_INTEGRITY",
        "fixed_denominator_business": {
            "capacity": outcome["success"]["primary_completed_raw_bags"],
            "on_time": on_time,
            "missed_bag_count": raw_count - int(on_time["count"]),
            "missed_bag_rate": 1.0 - float(on_time["rate"]),
            "literal_early_margin": outcome["success"][
                "finish_le_std_minus_2700_literal"
            ],
            "detailed": fixed_business,
        },
        "full_population_timing": timing,
        "execution_integrity": integrity,
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "event_count": int(summary.get("event_count", 0)),
            "decision_count": int(summary.get("decision_count", 0)),
            "summary": dict(summary),
        },
    }


def _nested(value: Mapping[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _integer(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _classification_thresholds(path: Path) -> dict[str, float | int]:
    text = path.read_text(encoding="utf-8")
    rate_match = re.search(r"action_change_rate_lt:\s*([0-9.eE+-]+)", text)
    count_match = re.search(r"action_change_count_lt:\s*(\d+)", text)
    if not rate_match or not count_match:
        raise ActivationError("revision manifest lacks activation thresholds")
    return {
        "action_change_rate_lt": float(rate_match.group(1)),
        "action_change_count_lt": int(count_match.group(1)),
    }


def classify_component(
    opportunity_count: int,
    action_change_count: int,
    thresholds: Mapping[str, float | int],
) -> str:
    if opportunity_count <= 0:
        return "NOT_ACTIVATED"
    rate = action_change_count / opportunity_count
    if (
        rate < float(thresholds["action_change_rate_lt"])
        and action_change_count < int(thresholds["action_change_count_lt"])
    ):
        return "RARELY_ACTIVATED"
    return "ACTIVATED_NO_CLEAR_OUTCOME_EFFECT"


def _result_paths(result_root: Path, explicit: Sequence[Path]) -> list[Path]:
    paths = [path.resolve(strict=True) for path in explicit]
    if result_root.exists():
        paths.extend(path.resolve() for path in result_root.glob("*.json"))
    return sorted(set(paths))


def _mechanism_projection(summary: Mapping[str, Any]) -> dict[str, int]:
    names = (
        "merge_grant_service_opportunity_count",
        "merge_grant_multi_candidate_opportunity_count",
        "merge_grant_true_competition_count",
        "merge_grant_order_mutation_count",
        "merge_grant_contended_loser_retry_count",
        "merge_grant_expired_count",
        "merge_grant_stale_arbitration_count",
        "bounded_local_pibt_applicability_count",
        "bounded_local_pibt_activation_count",
        "bounded_local_pibt_prepare_count",
        "bounded_local_pibt_validate_count",
        "bounded_local_pibt_commit_count",
        "bounded_local_pibt_rollback_count",
        "g4irsf20_redundant_beacon_suppressed_count",
        "g4irsf20_same_state_beacon_suppressed_count",
        "stale_event_count",
        "event_count",
    )
    return {name: _integer(summary.get(name)) for name in names}


def aggregate_results(
    *,
    result_paths: Sequence[Path],
    revision_manifest_path: Path = DEFAULT_REVISION_MANIFEST,
) -> dict[str, Any]:
    thresholds = _classification_thresholds(revision_manifest_path)
    by_cell: dict[tuple[str, str], dict[str, Any]] = {}
    for path in result_paths:
        value = _read_json(path)
        if value.get("schema") != SCHEMA_RUN:
            continue
        if value.get("native_execution_started") is not True:
            continue
        map_name = str(value.get("map"))
        factor = _factor_label(value.get("nominal_load_factor"))
        key = (map_name, factor)
        if key in by_cell:
            raise ActivationError(f"duplicate activation result cell: {key}")
        by_cell[key] = value

    activation_rows: list[dict[str, Any]] = []
    change_rows: list[dict[str, Any]] = []
    for (map_name, factor), value in sorted(by_cell.items()):
        summary = _nested(value, "runtime", "summary", default={})
        if not isinstance(summary, Mapping):
            summary = {}
        activation = summary.get("cie_component_activation", {})
        if not isinstance(activation, Mapping):
            activation = {}
        components = activation.get("components", {})
        if not isinstance(components, Mapping):
            components = {}
        strict = activation.get("strict_descent", {})
        if not isinstance(strict, Mapping):
            strict = {}
        base = {
            "map": map_name,
            "nominal_load_factor": factor,
            "status": value.get("status"),
            "raw_bag_denominator": _nested(
                value, "population", "raw_bag_denominator"
            ),
            "completed_raw_bag_count": _nested(
                value, "fixed_denominator_business", "capacity", "count"
            ),
            "completion_rate": _nested(
                value, "fixed_denominator_business", "capacity", "rate"
            ),
            "on_time_count": _nested(
                value, "fixed_denominator_business", "on_time", "count"
            ),
            "on_time_rate": _nested(
                value, "fixed_denominator_business", "on_time", "rate"
            ),
            "wall_seconds": _nested(value, "runtime", "wall_seconds"),
            "cpu_seconds": _nested(value, "runtime", "cpu_seconds"),
            "decision_count": _integer(activation.get("decision_count")),
            "multi_candidate_decision_count": _integer(
                activation.get("multi_candidate_decision_count")
            ),
            "strict_evaluation_count": _integer(strict.get("evaluation_count")),
            "strict_filtered_candidate_count": _integer(
                strict.get("filtered_candidate_count")
            ),
            "strict_filtered_decision_count": _integer(
                strict.get("filtered_decision_count")
            ),
            "strict_empty_ranking_count": _integer(
                strict.get("empty_ranking_count")
            ),
            **_mechanism_projection(summary),
        }
        base["strict_classification"] = classify_component(
            base["strict_filtered_candidate_count"],
            base["strict_filtered_decision_count"],
            thresholds,
        )
        base["j2_m3_classification"] = classify_component(
            base["merge_grant_true_competition_count"],
            base["merge_grant_order_mutation_count"],
            thresholds,
        )
        base["p2_classification"] = classify_component(
            base["bounded_local_pibt_applicability_count"],
            base["bounded_local_pibt_commit_count"],
            thresholds,
        )
        e2_suppressed = (
            base["g4irsf20_redundant_beacon_suppressed_count"]
            + base["g4irsf20_same_state_beacon_suppressed_count"]
        )
        base["e2_suppressed_event_count"] = e2_suppressed
        base["e2_classification"] = (
            "NOT_ACTIVATED" if e2_suppressed == 0
            else "ACTIVATED_NO_CLEAR_OUTCOME_EFFECT"
        )
        for component_name in COMPONENTS:
            component = components.get(component_name, {})
            if not isinstance(component, Mapping):
                component = {}
            prefix = component_name.lower()
            for name in (
                "candidate_nonzero_count",
                "decision_any_candidate_nonzero_count",
                "raw_argmin_nonzero_count",
                "counterfactual_any_ranking_change_count",
                "counterfactual_raw_argmin_change_count",
                "value_sum",
                "value_max",
            ):
                base[f"{prefix}_{name}"] = component.get(name, 0)
            opportunities = _integer(
                component.get("decision_any_candidate_nonzero_count")
            )
            changes = _integer(
                component.get("counterfactual_raw_argmin_change_count")
            )
            classification = classify_component(
                opportunities, changes, thresholds
            )
            change_rows.append(
                {
                    "map": map_name,
                    "nominal_load_factor": factor,
                    "component": component_name,
                    "opportunity_count": opportunities,
                    "any_ranking_change_count": _integer(component.get(
                        "counterfactual_any_ranking_change_count"
                    )),
                    "raw_argmin_action_change_count": changes,
                    "raw_argmin_action_change_rate": (
                        changes / opportunities if opportunities else 0.0
                    ),
                    "classification": classification,
                }
            )
        activation_rows.append(base)

    expected = {(map_name, _factor_label(factor))
                for map_name in MAPS for factor in SCAN_FACTORS}
    missing = sorted(expected - set(by_cell))
    # Upgrade materially active components to load-dependent when neither map
    # has material activation at 1x but a later factor does.  This is a scan
    # classification, not a performance-benefit claim.
    for component in COMPONENTS:
        rows = [row for row in change_rows if row["component"] == component]
        material = [row for row in rows
                    if row["classification"] == "ACTIVATED_NO_CLEAR_OUTCOME_EFFECT"]
        active_at_one = any(
            row["nominal_load_factor"] == "1.00" for row in material
        )
        if material and not active_at_one:
            for row in material:
                row["classification"] = "LOAD_DEPENDENT"

    return {
        "status": "COMPLETE" if not missing and len(by_cell) == 10 else "PARTIAL",
        "expected_cell_count": 10,
        "observed_cell_count": len(by_cell),
        "missing_cells": [f"{map_name}:{factor}" for map_name, factor in missing],
        "thresholds": thresholds,
        "activation_rows": activation_rows,
        "counterfactual_rows": change_rows,
        "survivor_timing_used": False,
    }


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _report_text(aggregate: Mapping[str, Any]) -> str:
    lines = [
        "# CIE component activation audit",
        "",
        f"Status: **{aggregate['status']}**; observed "
        f"{aggregate['observed_cell_count']}/{aggregate['expected_cell_count']} "
        "registered map-load cells.",
        "",
        "The scan uses complete G31 S4 with H_SA, M3/J2, strict descent, "
        "direct-neighbour calendar visibility, E2 and goal-arrival completion. "
        "Counters are same-state streaming diagnostics; no candidate trace or "
        "survivor-only timing is used.",
        "",
        "| Map | Load | Component | Opportunities | Action changes | Rate | Classification |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for row in aggregate["counterfactual_rows"]:
        lines.append(
            f"| {row['map']} | {row['nominal_load_factor']} | "
            f"{row['component']} | {row['opportunity_count']} | "
            f"{row['raw_argmin_action_change_count']} | "
            f"{row['raw_argmin_action_change_rate']:.6f} | "
            f"{row['classification']} |"
        )
    lines.extend([
        "",
        "`ACTIVATED_NO_CLEAR_OUTCOME_EFFECT` means that the component changes "
        "the raw local argmin often enough to justify a paired ablation; it is "
        "not itself evidence of business benefit. `LOAD_DEPENDENT` means the "
        "material threshold was first crossed above 1x.",
        "",
    ])
    if aggregate["missing_cells"]:
        lines.append("Missing cells: " + ", ".join(aggregate["missing_cells"]) + ".")
        lines.append("")
    return "\n".join(lines)


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate-loads")
    generate.add_argument("--source-raw", type=Path, default=DEFAULT_SOURCE_RAW)
    generate.add_argument(
        "--nanning-map-profile", type=Path, default=DEFAULT_NANNING_PROFILE
    )
    generate.add_argument("--output-dir", type=Path, default=DEFAULT_LOAD_DIR)
    generate.add_argument("--manifest", type=Path, default=DEFAULT_LOAD_MANIFEST)

    run = commands.add_parser("run")
    run.add_argument("--map", choices=MAPS, required=True)
    run.add_argument("--factor", type=float, choices=SCAN_FACTORS, required=True)
    run.add_argument("--load-manifest", type=Path)
    run.add_argument("--canonical", type=Path)
    run.add_argument(
        "--nanning-map-profile", type=Path, default=DEFAULT_NANNING_PROFILE
    )
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--force", action="store_true")

    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("--result", type=Path, action="append", default=[])
    aggregate.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    aggregate.add_argument(
        "--revision-manifest", type=Path, default=DEFAULT_REVISION_MANIFEST
    )
    aggregate.add_argument(
        "--activation-csv", type=Path, default=DEFAULT_ACTIVATION_CSV
    )
    aggregate.add_argument("--changes-csv", type=Path, default=DEFAULT_CHANGES_CSV)
    aggregate.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate-loads":
        result = generate_loads(
            source_raw_path=_rooted(args.source_raw),
            nanning_profile_path=_rooted(args.nanning_map_profile),
            output_dir=_rooted(args.output_dir),
            manifest_path=_rooted(args.manifest),
        )
        print(json.dumps({"status": result["status"], "manifest": str(_rooted(args.manifest))}))
        return 0

    if args.command == "run":
        output = _rooted(args.output)
        if output.exists() and not args.force:
            raise ActivationError(f"output exists; pass --force: {output}")
        load_manifest: Path | None = (
            _rooted(args.load_manifest) if args.load_manifest else None
        )
        if args.canonical:
            canonical = _rooted(args.canonical).resolve(strict=True)
        elif load_manifest:
            canonical, _cell = canonical_from_load_manifest(
                load_manifest, args.factor, args.map
            )
        else:
            raise ActivationError("run requires --canonical or --load-manifest")
        result = execute_run(
            map_name=args.map,
            factor=args.factor,
            canonical_path=canonical,
            binary=_rooted(args.binary),
            nanning_profile_path=_rooted(args.nanning_map_profile),
            dry_run=args.dry_run,
            load_manifest_path=load_manifest,
        )
        _atomic_json(output, result)
        print(json.dumps({"status": result["status"], "output": str(output)}))
        return 0 if result["status"] in {
            "COMPLETE", "READY_CIE_COMPONENT_ACTIVATION_DRY_RUN"
        } else 2

    paths = _result_paths(
        _rooted(args.result_root), [_rooted(path) for path in args.result]
    )
    result = aggregate_results(
        result_paths=paths,
        revision_manifest_path=_rooted(args.revision_manifest).resolve(strict=True),
    )
    _atomic_text(_rooted(args.activation_csv), _csv_text(result["activation_rows"]))
    _atomic_text(_rooted(args.changes_csv), _csv_text(result["counterfactual_rows"]))
    _atomic_text(_rooted(args.report), _report_text(result))
    print(json.dumps({
        "status": result["status"],
        "observed_cell_count": result["observed_cell_count"],
        "report": str(_rooted(args.report)),
    }))
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ActivationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CIE component activation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

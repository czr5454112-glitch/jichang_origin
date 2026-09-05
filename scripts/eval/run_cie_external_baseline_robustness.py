"""Prepare and aggregate paired external-baseline robustness experiments.

Each map's frozen 1x raw task file is the authority for every seed/load cell.
HCA and the Feng-paper-environment DH reconstruction read that map-local raw
file.  The G31 JSONL is a deterministic expansion of the same raw bytes and is
audited back against them before a command plan is eligible.  Scaled cells use
the same flight timetable and raw-task-ID mask on both maps while retaining
each map's own projected physical origins, destinations, and storage node.

Arrival jitter is applied at raw-bag level.  Bags within five seconds of the
4800-second direct/EBS boundary may therefore change segment class naturally;
the raw-bag population is frozen while each cell's segment population is
derived from, and audited against, its jittered raw file.

This module owns task generation, identity audit, command planning, and paired
aggregation.  It does not implement any of the three routing algorithms.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from czr005.io.legacy_tasks import (  # noqa: E402
    RawLegacyTask,
    expand_tasks,
    parse_legacy_tasks,
    write_task_jsonl,
)
from scripts.eval import run_cie_component_activation as activation  # noqa: E402
from scripts.eval import run_cie_random_robustness as internal_random  # noqa: E402
from scripts.eval import run_g4irsf29_workload as g29  # noqa: E402


SCHEMA = "czr005.cie_external_baseline_robustness.v1"
WORKLOAD_SCHEMA = "czr005.cie_external_baseline_workload.v1"
RESULT_SCHEMA = "czr005.cie_external_baseline_result.v1"
AGGREGATE_SCHEMA = "czr005.cie_external_baseline_paired_aggregate.v1"

SEEDS = (
    104729,
    130363,
    155921,
    181081,
    205759,
    232003,
    257053,
    283303,
    308081,
    333667,
)
LOAD_FACTORS = (1.0, 1.75, 2.0)
METHODS = (
    "FENG_NATIVE_HCA",
    "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION",
    "G31_S4_NATIVE_SYSTEM",
)
REFERENCE_METHOD = "G31_S4_NATIVE_SYSTEM"
NANNING_DH_REPORTING_METHOD = "FENG_PAPER_ENV_CIE_DH_NANNING_PORTED"
FIXED_HORIZON_SECONDS = 98_259.0
DEFAULT_MAP_NAME = "map2"
MAPS = ("map2", "nanning")
DEFAULT_SOURCE = ROOT / "legacy" / "jichang_origin_readonly" / "inputdata.txt"
DEFAULT_MAP = ROOT / "legacy" / "jichang_origin_readonly" / "map2.txt"
DEFAULT_NANNING_TASK_DIR = ROOT / "artifacts" / "tasks" / "g4irsf31_nanning"
DEFAULT_NANNING_SOURCE = DEFAULT_NANNING_TASK_DIR / "nanning_1x_raw.txt"
DEFAULT_NANNING_MAP = ROOT / "data" / "processed" / "maps" / "nanning_legacy.txt"
DEFAULT_NANNING_PROFILE = (
    ROOT / "data" / "processed" / "maps" / "nanning_airport_profile.json"
)
DEFAULT_WORKLOAD_ROOT = (
    ROOT / "data" / "processed" / "workloads" / "cie_external_robustness"
)
DEFAULT_RESULT_ROOT = ROOT / "outputs" / "runtime" / "cie_external_baseline_robustness"
DEFAULT_DH_CLASSES_DIR = ROOT / "build" / "feng_cie_dh_java"
EXPECTED_SOURCE_SHA256 = "0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87"
EXPECTED_MAP_SHA256 = "55f578cb4b8fcc61f5b13963fcb8546aca91e517ea6f8ff4a7361670f1b03f8f"
EXPECTED_NANNING_SOURCE_SHA256 = (
    "5fc1a834f1cf03d28417d3e5a6c16114967a7f9f352af9b795f25a00df983ae6"
)
EXPECTED_NANNING_MAP_SHA256 = (
    "daf51cf339862872ec1e6ce86fbdffccd326d83ebd80ebef0e926917c61ac0df"
)
EXPECTED_G31_BINARY_SHA256 = (
    "b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5"
)
EXPECTED_DH_SOURCE_SHA256 = (
    "99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8"
)
EXPECTED_DH_CLASS_SHA256 = (
    "d611967f0433dfc08f67d92c89e9b13dcb5b8ac5ace3d3abec9c098dba360286"
)
EXPECTED_POPULATIONS = {
    1.0: (28_506, 43_603),
    1.75: (49_765, 76_108),
    2.0: (57_012, 87_206),
}


@dataclass(frozen=True)
class MapProtocol:
    name: str
    map_path: Path
    source_path: Path
    expected_map_sha256: str
    expected_source_sha256: str
    storage_in_goal: int
    storage_out_start: int
    source_protocol: str


MAP_PROTOCOLS = {
    "map2": MapProtocol(
        name="map2",
        map_path=DEFAULT_MAP,
        source_path=DEFAULT_SOURCE,
        expected_map_sha256=EXPECTED_MAP_SHA256,
        expected_source_sha256=EXPECTED_SOURCE_SHA256,
        storage_in_goal=47,
        storage_out_start=52,
        source_protocol="FROZEN_FENG_ORIGINAL_RAW_1X",
    ),
    "nanning": MapProtocol(
        name="nanning",
        map_path=DEFAULT_NANNING_MAP,
        source_path=DEFAULT_NANNING_SOURCE,
        expected_map_sha256=EXPECTED_NANNING_MAP_SHA256,
        expected_source_sha256=EXPECTED_NANNING_SOURCE_SHA256,
        storage_in_goal=53,
        storage_out_start=53,
        source_protocol="FROZEN_NANNING_OD_PROJECTED_RAW_1X",
    ),
}

HIGHER_IS_BETTER = {
    "completed_raw_bag_count",
    "completion_rate",
    "on_time_raw_bag_count",
    "on_time_rate",
}
LOWER_IS_BETTER = {
    "missed_bag_count",
    "missed_bag_rate",
    "tardiness_sum_seconds",
    "tardiness_mean_seconds",
    "tardiness_p95_seconds",
    "tardiness_p99_seconds",
    "tardiness_max_seconds",
    "source_backlog_area_seconds",
    "network_backlog_area_seconds",
    "total_backlog_area_seconds",
    "time_to_90_percent_seconds",
    "time_to_95_percent_seconds",
    "time_to_99_percent_seconds",
    "population_latency_mean_seconds",
    "population_latency_p95_seconds",
    "population_latency_p99_seconds",
    "population_latency_max_seconds",
}
TIMING_METRICS = {
    "population_latency_mean_seconds",
    "population_latency_p95_seconds",
    "population_latency_p99_seconds",
    "population_latency_max_seconds",
}


def reporting_method(map_name: str, runtime_method: str) -> str:
    """Return the evidence-layer label without changing the runtime identity."""

    if (
        map_name == "nanning"
        and runtime_method == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"
    ):
        return NANNING_DH_REPORTING_METHOD
    return runtime_method


class ExternalBaselineError(RuntimeError):
    """Raised when paired workload/result identity is not defensible."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_value(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def map_protocol(map_name: str) -> MapProtocol:
    try:
        return MAP_PROTOCOLS[str(map_name)]
    except KeyError as exc:
        raise ExternalBaselineError(f"unsupported map: {map_name}") from exc


def prepare_frozen_source(map_name: str, override: Path | None = None) -> Path:
    """Resolve one map's frozen 1x raw authority, materializing Nanning if absent."""

    protocol = map_protocol(map_name)
    source = override if override is not None else protocol.source_path
    if map_name == "nanning" and override is None and not source.is_file():
        from scripts.eval import run_g4irsf31_nanning_workload as nanning_workload

        manifest = nanning_workload.build_workload(
            scale=1,
            source_raw_path=DEFAULT_SOURCE,
            map_profile_path=DEFAULT_NANNING_PROFILE,
            output_dir=DEFAULT_NANNING_TASK_DIR,
        )
        storage = manifest.get("lifecycle", {})
        if (
            manifest.get("status") != "COMPLETE"
            or int(manifest.get("raw_task_count", -1)) != EXPECTED_POPULATIONS[1.0][0]
            or int(storage.get("storage_in_goal", -1)) != protocol.storage_in_goal
            or int(storage.get("storage_out_start", -1)) != protocol.storage_out_start
        ):
            raise ExternalBaselineError("Nanning frozen 1x projection failed its manifest gate")
    source = source.resolve(strict=True)
    if _sha256_file(source) != protocol.expected_source_sha256:
        raise ExternalBaselineError(f"frozen {map_name} 1x source identity drift")
    map_path = protocol.map_path.resolve(strict=True)
    if _sha256_file(map_path) != protocol.expected_map_sha256:
        raise ExternalBaselineError(f"frozen {map_name} map identity drift")
    return source


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _atomic_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    write_task_jsonl(rows, temporary)
    os.replace(temporary, path)


def _load_token(load_factor: float) -> str:
    return format(float(load_factor), ".2f").replace(".", "p")


def cell_dir(
    root: Path,
    load_factor: float,
    seed: int,
    map_name: str = DEFAULT_MAP_NAME,
) -> Path:
    map_protocol(map_name)
    return root / f"{map_name}_{_load_token(load_factor)}x" / f"seed_{seed}"


def _derived_rng(seed: int) -> random.Random:
    digest = hashlib.sha256(f"cie-external-v1|{seed}|arrival-integer".encode("ascii")).digest()
    return random.Random(int.from_bytes(digest, "big"))


def integer_jitter(seed: int, task_ids: Iterable[int]) -> dict[int, int]:
    if seed not in SEEDS:
        raise ExternalBaselineError(f"seed is not frozen: {seed}")
    ordered = sorted(set(int(value) for value in task_ids))
    if not ordered:
        raise ExternalBaselineError("cannot jitter an empty workload")
    rng = _derived_rng(seed)
    return {task_id: rng.randint(-5, 5) for task_id in ordered}


def _project_generated_timetable_by_raw_task_id(
    *,
    selection_source_tasks: Sequence[RawLegacyTask],
    target_source_tasks: Sequence[RawLegacyTask],
    generated_selection: Sequence[RawLegacyTask],
    inserted_id_offset: int,
) -> tuple[RawLegacyTask, ...]:
    authority_by_id = {task.task_id: task for task in selection_source_tasks}
    target_by_id = {task.task_id: task for task in target_source_tasks}
    if set(authority_by_id) != set(target_by_id):
        raise ExternalBaselineError(
            "cross-map schedule authorities have different raw task IDs"
        )
    if len(authority_by_id) != len(selection_source_tasks) or len(target_by_id) != len(
        target_source_tasks
    ):
        raise ExternalBaselineError("cross-map schedule authority has duplicate raw task IDs")
    for rank, (authority, target) in enumerate(
        zip(selection_source_tasks, target_source_tasks, strict=True)
    ):
        if authority.task_id != target.task_id:
            raise ExternalBaselineError(
                f"cross-map source order differs at raw task rank {rank}"
            )
        if (authority.entry_time, authority.std) != (target.entry_time, target.std):
            raise ExternalBaselineError(
                "cross-map schedule authorities have different timetables"
            )

    projected: list[RawLegacyTask] = []
    for generated in generated_selection:
        if generated.task_id in target_by_id:
            projected.append(target_by_id[generated.task_id])
            continue
        parent_rank = generated.task_id - inserted_id_offset
        if parent_rank < 0 or parent_rank >= len(target_source_tasks):
            raise ExternalBaselineError(
                "cross-map generated task cannot be bound to a frozen 1x parent"
            )
        target_parent = target_source_tasks[parent_rank]
        projected.append(
            replace(
                target_parent,
                task_id=generated.task_id,
                entry_time=generated.entry_time,
                std=generated.std,
                source_line=generated.source_line,
            )
        )
    if {task.task_id for task in projected} != {
        task.task_id for task in generated_selection
    }:
        raise ExternalBaselineError(
            "cross-map generated schedule does not map one-to-one by raw task ID"
        )
    return tuple(projected)


def build_base_raw_tasks(
    source_tasks: Sequence[RawLegacyTask],
    load_factor: float,
    *,
    selection_source_tasks: Sequence[RawLegacyTask] | None = None,
) -> tuple[tuple[RawLegacyTask, ...], dict[str, Any]]:
    factor = float(load_factor)
    if factor == 1.0:
        return tuple(source_tasks), {
            "protocol": "ORIGINAL_FENG_RAW_DAY_1X",
            "whole_flight_population": True,
        }
    if factor == 1.75:
        selection_authority = (
            source_tasks
            if selection_source_tasks is None
            else tuple(selection_source_tasks)
        )
        authority_generated, selection, offset = activation.build_factor_raw_tasks(
            selection_authority, factor
        )
        if selection_source_tasks is None:
            generated = authority_generated
        else:
            generated = _project_generated_timetable_by_raw_task_id(
                selection_source_tasks=selection_authority,
                target_source_tasks=source_tasks,
                generated_selection=authority_generated,
                inserted_id_offset=offset,
            )
        return generated, {
            "protocol": "WHOLE_FLIGHT_SCHEDULE_PRESERVING_1P75X",
            "whole_flight_population": True,
            "selection_sha256": selection["selected_flight_keys_sha256"],
            "realized_raw_bag_factor": selection["realized_raw_bag_factor"],
            "cross_map_schedule_projection_by_raw_task_id": (
                selection_source_tasks is not None
            ),
        }
    if factor == 2.0:
        schedule_authority = (
            source_tasks
            if selection_source_tasks is None
            else tuple(selection_source_tasks)
        )
        authority_generated, _flight_rows, metadata = g29.densify_flight_timetable(
            schedule_authority
        )
        generated = (
            authority_generated
            if selection_source_tasks is None
            else _project_generated_timetable_by_raw_task_id(
                selection_source_tasks=schedule_authority,
                target_source_tasks=source_tasks,
                generated_selection=authority_generated,
                inserted_id_offset=int(metadata["inserted_id_offset"]),
            )
        )
        return generated, {
            "protocol": "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_2X",
            "whole_flight_population": True,
            "inserted_id_offset": metadata["inserted_id_offset"],
            "cross_map_schedule_projection_by_raw_task_id": (
                selection_source_tasks is not None
            ),
        }
    raise ExternalBaselineError(f"unsupported load factor: {load_factor}")


def jitter_raw_tasks(
    tasks: Sequence[RawLegacyTask], *, seed: int
) -> tuple[tuple[RawLegacyTask, ...], dict[int, int]]:
    offsets = integer_jitter(seed, (task.task_id for task in tasks))
    shifted: list[RawLegacyTask] = []
    for task in tasks:
        delta = offsets[task.task_id]
        updated = replace(task, entry_time=task.entry_time + delta)
        if updated.entry_time < 0.0:
            raise ExternalBaselineError(f"arrival jitter made task {task.task_id} negative")
        shifted.append(updated)
    return tuple(shifted), offsets


def _raw_semantics(task: RawLegacyTask) -> tuple[Any, ...]:
    return (
        task.task_id,
        format(float(task.entry_time), ".15g"),
        format(float(task.std), ".15g"),
        task.start,
        task.end,
        task.unloader,
        task.loader,
    )


def _write_raw(header: str, tasks: Sequence[RawLegacyTask], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    g29.write_raw_tasks(header, tasks, temporary)
    os.replace(temporary, path)


def generate_cell(
    *,
    source_path: Path,
    output_root: Path,
    load_factor: float,
    seed: int,
    map_name: str = DEFAULT_MAP_NAME,
    map_path: Path | None = None,
    storage_in_goal: int | None = None,
    storage_out_start: int | None = None,
    selection_source_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    protocol = map_protocol(map_name)
    source_path = source_path.resolve(strict=True)
    resolved_map_path = (map_path or protocol.map_path).resolve(strict=True)
    storage_in = (
        protocol.storage_in_goal if storage_in_goal is None else int(storage_in_goal)
    )
    storage_out = (
        protocol.storage_out_start if storage_out_start is None else int(storage_out_start)
    )
    header, original = parse_legacy_tasks(source_path)
    selection_source: Sequence[RawLegacyTask] | None = None
    resolved_selection_source_path: Path | None = None
    if selection_source_path is not None:
        resolved_selection_source_path = selection_source_path.resolve(strict=True)
        _selection_header, selection_source = parse_legacy_tasks(
            resolved_selection_source_path
        )
    base, load_identity = build_base_raw_tasks(
        original,
        load_factor,
        selection_source_tasks=selection_source,
    )
    load_identity = {
        **load_identity,
        "source_map": map_name,
        "source_protocol": protocol.source_protocol,
        "selection_authority": (
            None
            if resolved_selection_source_path is None
            else {
                "path": str(resolved_selection_source_path),
                "sha256": _sha256_file(resolved_selection_source_path),
                "map": "map2",
            }
        ),
        "base_raw_bag_count": len(base),
        "base_segment_count": len(
            expand_tasks(
                base,
                storage_in_goal=storage_in,
                storage_out_start=storage_out,
            )
        ),
    }
    shifted, offsets = jitter_raw_tasks(base, seed=seed)
    destination = cell_dir(output_root, load_factor, seed, map_name)
    raw_path = destination / "inputdata.txt"
    canonical_path = destination / "canonical.jsonl"
    identity_path = destination / "identity.json"
    existing = [path for path in (raw_path, canonical_path, identity_path) if path.exists()]
    if existing and not force:
        raise ExternalBaselineError(
            f"workload cell already exists; pass --force for {destination}"
        )
    _write_raw(header, shifted, raw_path)
    _header, reparsed = parse_legacy_tasks(raw_path)
    if tuple(map(_raw_semantics, reparsed)) != tuple(map(_raw_semantics, shifted)):
        raise ExternalBaselineError("raw workload failed exact write/reparse identity")
    expanded = expand_tasks(
        reparsed,
        storage_in_goal=storage_in,
        storage_out_start=storage_out,
    )
    _atomic_jsonl(canonical_path, expanded)
    records = [[task_id, offsets[task_id]] for task_id in sorted(offsets)]
    class_crossing_count = sum(
        (before.slack_at_entry < 4800.0) != (after.slack_at_entry < 4800.0)
        for before, after in zip(base, shifted, strict=True)
    )
    early_to_direct_count = sum(
        before.slack_at_entry >= 4800.0 and after.slack_at_entry < 4800.0
        for before, after in zip(base, shifted, strict=True)
    )
    direct_to_early_count = class_crossing_count - early_to_direct_count
    identity = {
        "schema": WORKLOAD_SCHEMA,
        "status": "COMPLETE",
        "map": map_name,
        "map_path": str(resolved_map_path),
        "map_sha256": _sha256_file(resolved_map_path),
        "storage_in_goal": storage_in,
        "storage_out_start": storage_out,
        "load_factor": float(load_factor),
        "seed": seed,
        "arrival_jitter": {
            "distribution": "UniformInteger[-5,5] seconds per raw bag",
            "algorithm": "PYTHON_MT19937_SHA256_DERIVED_STREAM_V1",
            "offset_records_sha256": _sha256_value(records),
            "min": min(offsets.values()),
            "max": max(offsets.values()),
            "direct_ebs_class_crossing_count": class_crossing_count,
            "early_to_direct_count": early_to_direct_count,
            "direct_to_early_count": direct_to_early_count,
            "class_crossings_are_natural_jitter_effects": True,
        },
        "source": {
            "path": str(source_path),
            "sha256": _sha256_file(source_path),
            "map": map_name,
            "protocol": protocol.source_protocol,
        },
        "load_construction": load_identity,
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": _sha256_file(raw_path),
        "canonical_path": str(canonical_path.resolve()),
        "canonical_sha256": _sha256_file(canonical_path),
        "raw_bag_count": len(reparsed),
        "segment_count": len(expanded),
        "fixed_horizon_seconds": FIXED_HORIZON_SECONDS,
        "raw_task_ids_sha256": _sha256_value(sorted(task.task_id for task in reparsed)),
        "segment_ids_sha256": _sha256_value(sorted(task.segment_id for task in expanded)),
        "consumer_contract": {
            "FENG_NATIVE_HCA": "raw_path",
            "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION": "raw_path",
            "G31_S4_NATIVE_SYSTEM": "canonical_path_deterministically_expanded_from_raw_path",
        },
        "segment_population_policy": (
            "DERIVE_FROM_JITTERED_RAW; DO_NOT_FREEZE_UNJITTERED_SEGMENT_COUNT"
        ),
        "seed_removal_forbidden": True,
    }
    _atomic_json(identity_path, identity)
    return identity


def audit_cell(identity_path: Path) -> dict[str, Any]:
    identity_path = identity_path.resolve(strict=True)
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if identity.get("schema") != WORKLOAD_SCHEMA:
        raise ExternalBaselineError(f"unexpected workload identity schema: {identity_path}")
    map_name = str(identity.get("map", ""))
    map_protocol(map_name)
    raw_path = Path(identity["raw_path"])
    canonical_path = Path(identity["canonical_path"])
    map_path = Path(identity["map_path"])
    source_path = Path(identity["source"]["path"])
    if _sha256_file(raw_path) != identity["raw_sha256"]:
        raise ExternalBaselineError(f"raw workload drift: {raw_path}")
    if _sha256_file(canonical_path) != identity["canonical_sha256"]:
        raise ExternalBaselineError(f"canonical workload drift: {canonical_path}")
    if _sha256_file(map_path) != identity["map_sha256"]:
        raise ExternalBaselineError(f"map identity drift: {map_path}")
    if _sha256_file(source_path) != identity["source"]["sha256"]:
        raise ExternalBaselineError(f"source workload drift: {source_path}")
    _header, raw = parse_legacy_tasks(raw_path)
    storage_in = int(identity["storage_in_goal"])
    storage_out = int(identity["storage_out_start"])
    expanded = expand_tasks(
        raw,
        storage_in_goal=storage_in,
        storage_out_start=storage_out,
    )
    serialized = [json.loads(line) for line in canonical_path.read_text(encoding="utf-8").splitlines() if line]
    expected = [row.to_dict() for row in expanded]
    _source_header, source_raw = parse_legacy_tasks(source_path)
    selection_authority_record = identity.get("load_construction", {}).get(
        "selection_authority"
    )
    selection_source: Sequence[RawLegacyTask] | None = None
    selection_authority_sha_ok = selection_authority_record is None
    if isinstance(selection_authority_record, Mapping):
        selection_path = Path(str(selection_authority_record["path"]))
        selection_authority_sha_ok = (
            _sha256_file(selection_path) == selection_authority_record.get("sha256")
        )
        _selection_header, selection_source = parse_legacy_tasks(selection_path)
    rebuilt_base, rebuilt_load_identity = build_base_raw_tasks(
        source_raw,
        float(identity["load_factor"]),
        selection_source_tasks=selection_source,
    )
    rebuilt_raw, rebuilt_offsets = jitter_raw_tasks(
        rebuilt_base, seed=int(identity["seed"])
    )
    rebuilt_offset_records = [
        [task_id, rebuilt_offsets[task_id]] for task_id in sorted(rebuilt_offsets)
    ]
    load_identity_keys = (
        "protocol",
        "whole_flight_population",
        "selection_sha256",
        "realized_raw_bag_factor",
        "inserted_id_offset",
        "cross_map_schedule_projection_by_raw_task_id",
    )
    checks = {
        "raw_bag_count": len(raw) == int(identity["raw_bag_count"]),
        "segment_count": len(expanded) == int(identity["segment_count"]),
        "canonical_exact_projection": serialized == expected,
        "raw_task_ids": _sha256_value(sorted(task.task_id for task in raw))
        == identity["raw_task_ids_sha256"],
        "segment_ids": _sha256_value(sorted(task.segment_id for task in expanded))
        == identity["segment_ids_sha256"],
        "seed_frozen": int(identity["seed"]) in SEEDS,
        "load_frozen": float(identity["load_factor"]) in LOAD_FACTORS,
        "map_frozen": map_name in MAPS,
        "map_sha256": _sha256_file(map_path) == identity["map_sha256"],
        "source_map": identity.get("source", {}).get("map") == map_name,
        "load_source_map": identity.get("load_construction", {}).get("source_map")
        == map_name,
        "storage_identity": storage_in >= 0 and storage_out >= 0,
        "cell_paths_local": raw_path.resolve().parent == identity_path.parent
        and canonical_path.resolve().parent == identity_path.parent,
        "selection_authority_sha256": selection_authority_sha_ok,
        "deterministic_raw_materialization": tuple(map(_raw_semantics, raw))
        == tuple(map(_raw_semantics, rebuilt_raw)),
        "deterministic_arrival_jitter": identity.get("arrival_jitter", {}).get(
            "offset_records_sha256"
        )
        == _sha256_value(rebuilt_offset_records),
        "load_construction_identity": all(
            identity.get("load_construction", {}).get(key)
            == rebuilt_load_identity.get(key)
            for key in load_identity_keys
        ),
        "fixed_horizon": math.isclose(
            float(identity.get("fixed_horizon_seconds", math.nan)),
            FIXED_HORIZON_SECONDS,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ),
    }
    if not all(checks.values()):
        raise ExternalBaselineError(f"workload identity audit failed: {checks}")
    return {"identity_path": str(identity_path.resolve()), "pass": True, "checks": checks}


def audit_campaign(
    root: Path, *, maps: Sequence[str] = MAPS
) -> dict[str, Any]:
    audits: list[dict[str, Any]] = []
    missing: list[str] = []
    selected_maps = _selection(maps, MAPS)
    for map_name in selected_maps:
        protocol = map_protocol(map_name)
        map_path = protocol.map_path.resolve(strict=True)
        map_sha256 = _sha256_file(map_path)
        if map_sha256 != protocol.expected_map_sha256:
            raise ExternalBaselineError(f"frozen {map_name} map identity drift")
        for load_factor in LOAD_FACTORS:
            for seed in SEEDS:
                path = cell_dir(root, load_factor, seed, map_name) / "identity.json"
                if not path.is_file():
                    missing.append(str(path))
                    continue
                audit = audit_cell(path)
                identity = json.loads(path.read_text(encoding="utf-8"))
                expected_raw, expected_segments = EXPECTED_POPULATIONS[load_factor]
                formal_checks = {
                    "frozen_source_sha256": identity["source"]["sha256"]
                    == protocol.expected_source_sha256,
                    "frozen_map_sha256": identity["map_sha256"]
                    == protocol.expected_map_sha256,
                    "storage_in_goal": int(identity["storage_in_goal"])
                    == protocol.storage_in_goal,
                    "storage_out_start": int(identity["storage_out_start"])
                    == protocol.storage_out_start,
                    "expected_raw_bag_population": identity["raw_bag_count"]
                    == expected_raw,
                    "expected_unjittered_segment_population": identity[
                        "load_construction"
                    ]["base_segment_count"]
                    == expected_segments,
                    "jittered_segment_population_exact_projection": audit["checks"][
                        "segment_count"
                    ]
                    and audit["checks"]["canonical_exact_projection"],
                    "cross_map_scaled_schedule_authority": (
                        float(load_factor) not in {1.75, 2.0}
                        or map_name != "nanning"
                        or (
                            identity["load_construction"].get(
                                "cross_map_schedule_projection_by_raw_task_id"
                            )
                            is True
                            and identity["load_construction"].get(
                                "selection_authority", {}
                            ).get("sha256")
                            == EXPECTED_SOURCE_SHA256
                        )
                    ),
                    "no_unexpected_selection_authority": (
                        identity["load_construction"].get("selection_authority")
                        is not None
                    )
                    == (map_name == "nanning" and float(load_factor) in {1.75, 2.0}),
                }
                if not all(formal_checks.values()):
                    raise ExternalBaselineError(
                        f"formal workload population/source audit failed: {formal_checks}"
                    )
                audit["map"] = map_name
                audit["formal_checks"] = formal_checks
                audits.append(audit)
    expected_count = len(selected_maps) * len(LOAD_FACTORS) * len(SEEDS)
    return {
        "schema": SCHEMA,
        "status": (
            "COMPLETE"
            if not missing and len(audits) == expected_count
            else "INCOMPLETE"
        ),
        "maps": list(selected_maps),
        "expected_cell_count": expected_count,
        "audited_cell_count": len(audits),
        "missing": missing,
        "cells": audits,
    }


def build_dry_run_plan(
    *,
    workload_root: Path,
    result_root: Path,
    python: str,
    java: str,
    javac: str,
    binary: Path,
    maps: Sequence[str] = MAPS,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    selected_maps = _selection(maps, MAPS)
    for map_name in selected_maps:
        protocol = map_protocol(map_name)
        map_path = protocol.map_path.resolve(strict=True)
        map_sha256 = _sha256_file(map_path)
        if map_sha256 != protocol.expected_map_sha256:
            raise ExternalBaselineError(f"frozen {map_name} map identity drift")
        for load_factor in LOAD_FACTORS:
            for seed in SEEDS:
                workload = cell_dir(workload_root, load_factor, seed, map_name)
                raw = workload / "inputdata.txt"
                canonical = workload / "canonical.jsonl"
                result = cell_dir(result_root, load_factor, seed, map_name)
                commands = {
                    "FENG_NATIVE_HCA": [
                        python,
                        str(ROOT / "scripts/eval/run_g4irsf24_fresh_hca.py"),
                        "run",
                        "--profile",
                        "full",
                        "--repeats",
                        "1",
                        "--map-path",
                        str(map_path),
                        "--storage-in-goal",
                        str(protocol.storage_in_goal),
                        "--storage-out-start",
                        str(protocol.storage_out_start),
                        "--input-path",
                        str(raw),
                        "--canonical-input",
                        str(canonical),
                        "--output-root",
                        str(result / "hca_native"),
                        "--java",
                        java,
                        "--javac",
                        javac,
                        "--cleanup-epoch-files",
                    ],
                    "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION": [
                        python,
                        str(ROOT / "scripts/eval/run_feng_paper_env_cie_dh.py"),
                        "run",
                        "--map-path",
                        str(map_path),
                        "--input-path",
                        str(raw),
                        "--allow-external-workload",
                        "--external-workload-identity",
                        str(workload / "identity.json"),
                        "--seed",
                        str(seed),
                        "--horizon-seconds",
                        format(FIXED_HORIZON_SECONDS, ".1f"),
                        "--trace-sample-modulo",
                        "0",
                        "--output-dir",
                        str(result / "feng_env_dh"),
                        "--classes-dir",
                        str(DEFAULT_DH_CLASSES_DIR),
                        "--skip-compile",
                        "--java",
                        java,
                        "--javac",
                        javac,
                    ],
                    "G31_S4_NATIVE_SYSTEM": [
                        python,
                        str(ROOT / "scripts/eval/run_cie_component_activation.py"),
                        "run",
                        "--map",
                        map_name,
                        "--factor",
                        str(load_factor),
                        "--canonical",
                        str(canonical),
                        "--binary",
                        str(binary),
                        "--output",
                        str(result / "g31_native.json"),
                    ],
                }
                entries.append(
                    {
                        "map": map_name,
                        "map_path": str(map_path),
                        "map_sha256": map_sha256,
                        "storage_in_goal": protocol.storage_in_goal,
                        "storage_out_start": protocol.storage_out_start,
                        "load_factor": load_factor,
                        "seed": seed,
                        "raw_workload": str(raw),
                        "canonical_projection": str(canonical),
                        "identity": str(workload / "identity.json"),
                        "commands": commands,
                        "normalized_result_targets": {
                            method: str(result / f"{method}.json")
                            for method in METHODS
                        },
                    }
                )
    return {
        "schema": SCHEMA,
        "status": "READY_EXTERNAL_BASELINE_DRY_RUN",
        "generated_at": _utc_now(),
        "execution_started": False,
        "maps": list(selected_maps),
        "map_count": len(selected_maps),
        "seed_count": len(SEEDS),
        "load_factors": list(LOAD_FACTORS),
        "method_count": len(METHODS),
        "command_count": len(entries) * len(METHODS),
        "segment_population_policy": (
            "DERIVE_FROM_JITTERED_RAW; SAME CELL IDENTITY FOR ALL METHODS"
        ),
        "entries": entries,
        "normalization_note": (
            "Native outputs must be normalized to RESULT_SCHEMA without changing "
            "the recorded workload hashes before aggregate."
        ),
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _csv_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _optional_csv_metric(value: Any, label: str) -> float | None:
    text = str(value).strip()
    if text.lower() in {"", "n/a", "na", "null", "none"}:
        return None
    return _finite_metric(float(text), label)


def _metric_template() -> dict[str, float | int | None]:
    return {name: None for name in sorted(HIGHER_IS_BETTER | LOWER_IS_BETTER)}


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ExternalBaselineError("quantile requires at least one value")
    return float(internal_random._quantile(sorted(values), probability))


def _distribution_metrics(values: Sequence[float], prefix: str) -> dict[str, float]:
    if not values:
        return {}
    finite = [_finite_metric(value, prefix) for value in values]
    return {
        f"{prefix}_sum_seconds": sum(finite),
        f"{prefix}_mean_seconds": statistics.fmean(finite),
        f"{prefix}_p95_seconds": _quantile(finite, 0.95),
        f"{prefix}_p99_seconds": _quantile(finite, 0.99),
        f"{prefix}_max_seconds": max(finite),
    }


def _identity_payload(identity_path: Path) -> tuple[Path, dict[str, Any]]:
    identity_path = identity_path.resolve(strict=True)
    audit_cell(identity_path)
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if float(identity["load_factor"]) not in LOAD_FACTORS:
        raise ExternalBaselineError("normalization identity load is not frozen")
    if int(identity["seed"]) not in SEEDS:
        raise ExternalBaselineError("normalization identity seed is not frozen")
    return identity_path, identity


def _native_evidence(paths: Sequence[Path]) -> list[dict[str, Any]]:
    evidence = []
    for path in paths:
        resolved = path.resolve(strict=True)
        evidence.append(
            {
                "path": str(resolved),
                "sha256": _sha256_file(resolved),
                "size_bytes": resolved.stat().st_size,
            }
        )
    return evidence


def _raw_business_metrics(
    identity: Mapping[str, Any],
    *,
    completion_by_task: Mapping[int, float | None],
    admission_by_task: Mapping[int, float | None],
) -> tuple[dict[str, float | int | None], bool]:
    """Compute fixed-denominator metrics from exact raw/lifecycle evidence.

    Source backlog ends when every segment of a raw bag has entered the network;
    network backlog then ends at final segment completion.  Incomplete intervals
    are integrated to the frozen observation horizon.  No survivor cohort is
    ever used.
    """

    raw_path = Path(str(identity["raw_path"])).resolve(strict=True)
    _header, raw_tasks = parse_legacy_tasks(raw_path)
    expected_ids = {int(task.task_id) for task in raw_tasks}
    if set(completion_by_task) != expected_ids or set(admission_by_task) != expected_ids:
        raise ExternalBaselineError("native lifecycle does not cover exact raw-bag identity")

    horizon = FIXED_HORIZON_SECONDS
    first_arrival = min(float(task.entry_time) for task in raw_tasks)
    completed_times: list[float] = []
    on_time_count = 0
    tardiness: list[float] = []
    source_area = 0.0
    network_area = 0.0
    total_area = 0.0
    for task in raw_tasks:
        task_id = int(task.task_id)
        arrival = float(task.entry_time)
        deadline = float(task.std)
        completion = completion_by_task[task_id]
        admission = admission_by_task[task_id]
        if completion is not None:
            completion = _finite_metric(completion, "completion_time")
            if completion > horizon + 1.0e-9:
                raise ExternalBaselineError("completion occurs beyond the fixed horizon")
            completed_times.append(completion)
            if completion <= deadline + 1.0e-9:
                on_time_count += 1
        terminal = horizon if completion is None else completion
        tardiness.append(max(0.0, terminal - deadline))

        admitted = None if admission is None else _finite_metric(admission, "admission_time")
        source_end = horizon if admitted is None else min(admitted, horizon)
        source_area += max(0.0, source_end - arrival)
        if admitted is not None and admitted <= horizon:
            network_area += max(0.0, terminal - admitted)
        total_area += max(0.0, terminal - arrival)

    raw_count = len(raw_tasks)
    completed_count = len(completed_times)
    metrics = _metric_template()
    metrics.update(
        {
            "completed_raw_bag_count": completed_count,
            "completion_rate": completed_count / raw_count,
            "on_time_raw_bag_count": on_time_count,
            "on_time_rate": on_time_count / raw_count,
            "missed_bag_count": raw_count - on_time_count,
            "missed_bag_rate": 1.0 - (on_time_count / raw_count),
            "source_backlog_area_seconds": source_area,
            "network_backlog_area_seconds": network_area,
            "total_backlog_area_seconds": total_area,
            **_distribution_metrics(tardiness, "tardiness"),
        }
    )
    ordered = sorted(completed_times)
    for percentage in (90, 95, 99):
        required = math.ceil(raw_count * percentage / 100.0)
        name = f"time_to_{percentage}_percent_seconds"
        metrics[name] = (
            ordered[required - 1] - first_arrival
            if len(ordered) >= required
            else None
        )
    return metrics, completed_count == raw_count


def _group_lifecycle(
    rows: Sequence[Mapping[str, str]],
    identity: Mapping[str, Any],
    *,
    task_key: str,
    admission_key: str,
    completion_key: str,
    complete_key: str,
    complete_value: str | None = None,
    allow_missing: bool = False,
    segment_key: str | None = None,
) -> tuple[dict[int, float | None], dict[int, float | None]]:
    raw_path = Path(str(identity["raw_path"]))
    _header, raw_tasks = parse_legacy_tasks(raw_path)
    expected_segments: dict[int, int] = {}
    expected_segment_ids: set[str] = set()
    for segment in expand_tasks(
        raw_tasks,
        storage_in_goal=int(identity["storage_in_goal"]),
        storage_out_start=int(identity["storage_out_start"]),
    ):
        task_id = int(segment.task_id)
        expected_segments[task_id] = expected_segments.get(task_id, 0) + 1
        expected_segment_ids.add(str(segment.segment_id))
    grouped: dict[int, list[Mapping[str, str]]] = {task_id: [] for task_id in expected_segments}
    observed_segment_ids: set[str] = set()
    for row in rows:
        task_id = int(row[task_key])
        if task_id not in grouped:
            raise ExternalBaselineError(f"native lifecycle has foreign raw bag {task_id}")
        if segment_key is not None:
            segment_id = str(row.get(segment_key, ""))
            if not segment_id or segment_id not in expected_segment_ids:
                raise ExternalBaselineError("native lifecycle has a foreign segment")
            if segment_id in observed_segment_ids:
                raise ExternalBaselineError("native lifecycle has a duplicate segment")
            observed_segment_ids.add(segment_id)
        grouped[task_id].append(row)
    observed_count = sum(len(rows_for_task) for rows_for_task in grouped.values())
    if observed_count > int(identity["segment_count"]) or (
        not allow_missing and observed_count != int(identity["segment_count"])
    ):
        raise ExternalBaselineError("native lifecycle segment count differs from workload")

    completion: dict[int, float | None] = {}
    admission: dict[int, float | None] = {}
    for task_id, task_rows in grouped.items():
        if len(task_rows) > expected_segments[task_id] or (
            not allow_missing and len(task_rows) != expected_segments[task_id]
        ):
            raise ExternalBaselineError(f"native lifecycle segment multiplicity mismatch: {task_id}")
        admissions = [
            value
            for row in task_rows
            if (value := _optional_csv_metric(row.get(admission_key), admission_key))
            is not None
        ]
        admission[task_id] = (
            max(admissions)
            if len(task_rows) == expected_segments[task_id]
            and len(admissions) == len(task_rows)
            else None
        )
        finishes = [
            value
            for row in task_rows
            if (
                str(row.get(complete_key, "")) == complete_value
                if complete_value is not None
                else _csv_bool(row.get(complete_key))
            )
            if (value := _optional_csv_metric(row.get(completion_key), completion_key))
            is not None
        ]
        completion[task_id] = (
            max(finishes)
            if len(task_rows) == expected_segments[task_id]
            and len(finishes) == len(task_rows)
            else None
        )
    return completion, admission


def _timing_from_seconds(
    metrics: dict[str, float | int | None],
    seconds: Mapping[str, Any],
    *,
    full_population_complete: bool,
    load_factor: float,
    expected_count: int,
) -> None:
    if load_factor == 2.0 or not full_population_complete:
        return
    if int(seconds.get("count", -1)) != expected_count:
        raise ExternalBaselineError("full-population timing count differs from workload")
    mapping = {
        "mean": "population_latency_mean_seconds",
        "p95": "population_latency_p95_seconds",
        "p99": "population_latency_p99_seconds",
        "max": "population_latency_max_seconds",
    }
    for native_name, normalized_name in mapping.items():
        value = seconds.get(native_name, seconds.get(f"{native_name}_seconds"))
        if value is None:
            raise ExternalBaselineError(
                f"native full-population timing lacks {native_name}"
            )
        metrics[normalized_name] = _finite_metric(value, normalized_name)


def _dh_full_population_timing(
    summary: Mapping[str, str], *, expected_count: int
) -> tuple[dict[str, float], str]:
    """Read the one full-population DH timing family without imputing values."""

    prefixes = (
        "diagnostic_first_admission_to_completion",
        "historical_processed_attempt",
    )
    for prefix in prefixes:
        keys = {
            suffix: f"{prefix}_{suffix}_seconds"
            for suffix in ("mean", "p95", "p99", "max")
        }
        if not any(key in summary for key in keys.values()):
            continue
        if prefix == "diagnostic_first_admission_to_completion":
            eligible = summary.get("full_population_timing_eligible")
            if eligible is not None and not _csv_bool(eligible):
                raise ExternalBaselineError(
                    "Feng DH marked full-population timing ineligible"
                )
            completed = summary.get("completed_raw_bags")
            if completed is not None and int(completed) != expected_count:
                raise ExternalBaselineError("Feng DH timing population differs from workload")
        else:
            if int(summary.get(f"{prefix}_count", -1)) != expected_count:
                raise ExternalBaselineError("Feng DH timing count differs from workload")
        values: dict[str, float] = {}
        for suffix, key in keys.items():
            parsed = _optional_csv_metric(summary.get(key), key)
            if parsed is None:
                raise ExternalBaselineError(f"Feng DH full-population timing lacks {key}")
            values[suffix] = parsed
        return values, prefix
    raise ExternalBaselineError("Feng DH summary lacks full-population timing fields")


def _normalize_hca(
    identity: Mapping[str, Any], native_dir: Path
) -> tuple[dict[str, float | int | None], bool, list[Path], dict[str, Any]]:
    campaign_path = native_dir / "fresh_hca_summary.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    if campaign.get("schema") != "g4irsf24.fresh_hca.campaign.v1":
        raise ExternalBaselineError("unexpected fresh HCA campaign schema")
    runs = [
        run
        for run in campaign.get("runs", [])
        if isinstance(run, Mapping) and run.get("status") == "complete"
    ]
    if not runs:
        raise ExternalBaselineError("fresh HCA has no completed fixed-horizon run")
    run = runs[0]
    run_dir = native_dir / str(run["run_id"])
    status_path = run_dir / "run_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("status") != "complete" or int(status.get("returncode", -1)) != 0:
        raise ExternalBaselineError("fresh HCA native process is not complete")
    command_paths = []
    for token in status.get("command", []):
        try:
            candidate = Path(str(token))
            if candidate.exists():
                command_paths.append(candidate.resolve())
        except OSError:
            continue
    if Path(str(identity["raw_path"])).resolve() not in command_paths:
        raise ExternalBaselineError("fresh HCA command did not consume identity raw workload")
    if Path(str(identity["map_path"])).resolve() not in command_paths:
        raise ExternalBaselineError("fresh HCA command did not consume identity map")
    benchmark = run.get("benchmark_summary", {})
    if float(benchmark.get("last_epoch", math.nan)) != FIXED_HORIZON_SECONDS:
        raise ExternalBaselineError("fresh HCA did not execute the shared fixed horizon")
    if int(run.get("canonical_raw_bag_count", -1)) != int(identity["raw_bag_count"]):
        raise ExternalBaselineError("fresh HCA raw population differs from workload")
    if int(run.get("canonical_segment_count", -1)) != int(identity["segment_count"]):
        raise ExternalBaselineError("fresh HCA segment population differs from workload")

    lifecycle_path = run_dir / "segment_lifecycle.csv"
    lifecycle = _read_csv_rows(lifecycle_path)
    completion, admission = _group_lifecycle(
        lifecycle,
        identity,
        task_key="task_id",
        admission_key="processed_attempt_epoch",
        completion_key="finish_epoch",
        complete_key="complete",
        allow_missing=True,
        segment_key="segment_id",
    )
    metrics, full = _raw_business_metrics(
        identity, completion_by_task=completion, admission_by_task=admission
    )
    timing_native = run.get("denominators", {}).get("processed_attempt", {})
    timing = dict(timing_native.get("seconds", {}))
    timing["count"] = timing_native.get("count", timing.get("count"))
    _timing_from_seconds(
        metrics,
        timing,
        full_population_complete=full,
        load_factor=float(identity["load_factor"]),
        expected_count=int(identity["raw_bag_count"]),
    )
    metrics_path = run_dir / "metrics.json"
    raw_bag_path = run_dir / "raw_bag_timings.csv"
    evidence = [campaign_path, status_path, metrics_path, lifecycle_path, raw_bag_path]
    contract = {
        "native_schema": campaign.get("schema"),
        "native_run_id": run["run_id"],
        "fixed_horizon_native_contract": "DECLARED_LAST_EPOCH",
        "timing_denominator": "processed_attempt",
    }
    return metrics, full, evidence, contract


def _normalize_dh(
    identity_path: Path,
    identity: Mapping[str, Any],
    native_dir: Path,
) -> tuple[dict[str, float | int | None], bool, list[Path], dict[str, Any]]:
    status_path = native_dir / "runner_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("schema") != "czr005.feng_paper_env_cie_dh.run.v1":
        raise ExternalBaselineError("unexpected Feng DH runner schema")
    if status.get("status") != "complete" or int(status.get("returncode", -1)) != 0:
        raise ExternalBaselineError("Feng DH native process is not complete")
    native_identity = status.get("identity", {})
    if native_identity.get("method") != "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION":
        raise ExternalBaselineError("Feng DH method identity mismatch")
    external = native_identity.get("external_workload_identity", {})
    if external.get("sha256") != _sha256_file(identity_path):
        raise ExternalBaselineError("Feng DH external workload identity hash mismatch")
    if native_identity.get("input_sha256") != identity["raw_sha256"]:
        raise ExternalBaselineError("Feng DH raw workload hash mismatch")
    if native_identity.get("map_sha256") != identity["map_sha256"]:
        raise ExternalBaselineError("Feng DH map hash mismatch")
    if (
        native_identity.get("reconstruction_java_source_aggregate_sha256")
        != EXPECTED_DH_SOURCE_SHA256
    ):
        raise ExternalBaselineError("Feng DH reconstruction source identity is not final")
    if (
        native_identity.get("compiled_java_class_aggregate_sha256")
        != EXPECTED_DH_CLASS_SHA256
    ):
        raise ExternalBaselineError("Feng DH compiled class identity is not final")

    summary_path = native_dir / "summary.csv"
    summaries = _read_csv_rows(summary_path)
    if len(summaries) != 1:
        raise ExternalBaselineError("Feng DH summary must contain exactly one row")
    summary = summaries[0]
    native_status = summary.get("status")
    if native_status not in {"COMPLETE", "HORIZON_REACHED"}:
        raise ExternalBaselineError("Feng DH summary did not terminate cleanly")
    if int(summary["raw_bag_count"]) != int(identity["raw_bag_count"]):
        raise ExternalBaselineError("Feng DH raw population differs from workload")
    if int(summary["segment_count"]) != int(identity["segment_count"]):
        raise ExternalBaselineError("Feng DH segment population differs from workload")

    segments_path = native_dir / "segments.csv"
    segments = _read_csv_rows(segments_path)
    completion, admission = _group_lifecycle(
        segments,
        identity,
        task_key="source_raw_bag_id",
        admission_key="admission_time_seconds",
        completion_key="completion_time_seconds",
        complete_key="status",
        complete_value="COMPLETED",
    )

    metrics, full = _raw_business_metrics(
        identity, completion_by_task=completion, admission_by_task=admission
    )
    timing_denominator = "NOT_FORMALLY_REPORTED"
    if full and float(identity["load_factor"]) != 2.0:
        timing_values, timing_denominator = _dh_full_population_timing(
            summary, expected_count=int(identity["raw_bag_count"])
        )
        for suffix, value in timing_values.items():
            metrics[f"population_latency_{suffix}_seconds"] = _finite_metric(
                value,
                f"population_latency_{suffix}_seconds",
            )

    declared_horizon = float(native_identity.get("horizon_seconds", 0.0))
    simulation_end = float(summary["simulation_end_seconds"])
    if native_status == "HORIZON_REACHED" and (
        declared_horizon != FIXED_HORIZON_SECONDS
        or not math.isclose(simulation_end, FIXED_HORIZON_SECONDS, abs_tol=0.21)
    ):
        raise ExternalBaselineError("Feng DH horizon termination does not match protocol")
    if declared_horizon == FIXED_HORIZON_SECONDS:
        horizon_contract = "DECLARED_FIXED_HORIZON"
    elif declared_horizon == 0.0 and full and simulation_end <= FIXED_HORIZON_SECONDS:
        horizon_contract = "FULL_COMPLETION_BEFORE_SHARED_HORIZON"
    else:
        raise ExternalBaselineError("Feng DH run is not compatible with the shared horizon")
    bags_path = native_dir / "bags.csv"
    evidence = [status_path, summary_path, segments_path, bags_path]
    contract = {
        "native_schema": status.get("schema"),
        "fixed_horizon_native_contract": horizon_contract,
        "declared_horizon_seconds": declared_horizon,
        "simulation_end_seconds": simulation_end,
        "native_terminal_status": native_status,
        "timing_denominator": timing_denominator,
        "reproduction_level": summary.get("reproduction_level"),
        "reconstruction_java_source_sha256": native_identity.get(
            "reconstruction_java_source_aggregate_sha256"
        ),
        "compiled_java_class_sha256": native_identity.get(
            "compiled_java_class_aggregate_sha256"
        ),
        "legacy_java_source_sha256": native_identity.get(
            "legacy_java_source_aggregate_sha256"
        ),
    }
    return metrics, full, evidence, contract


def _normalize_g31(
    identity: Mapping[str, Any], native_path: Path
) -> tuple[dict[str, float | int | None], bool, list[Path], dict[str, Any]]:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    if native.get("status") != "COMPLETE":
        raise ExternalBaselineError("G31 native result is not complete")
    if native.get("execution_integrity", {}).get("pass") is not True:
        raise ExternalBaselineError("G31 native integrity gate failed")
    if native.get("map") != identity["map"]:
        raise ExternalBaselineError("G31 map identity mismatch")
    population = native.get("population", {})
    if int(population.get("raw_bag_denominator", -1)) != int(identity["raw_bag_count"]):
        raise ExternalBaselineError("G31 raw population differs from workload")
    if int(population.get("segment_count", -1)) != int(identity["segment_count"]):
        raise ExternalBaselineError("G31 segment population differs from workload")
    provenance = native.get("provenance", {})
    if provenance.get("canonical_sha256") != identity["canonical_sha256"]:
        raise ExternalBaselineError("G31 canonical workload hash mismatch")
    if provenance.get("binary_sha256") != EXPECTED_G31_BINARY_SHA256:
        raise ExternalBaselineError("G31 native binary identity is not final b00")
    contract = native.get("request_contract", {})
    if float(contract.get("fixed_end_epoch", math.nan)) != FIXED_HORIZON_SECONDS:
        raise ExternalBaselineError("G31 did not declare the shared fixed horizon")

    business = native.get("fixed_denominator_business", {}).get("detailed", {})
    completed = int(business.get("completed_raw_bag_count", -1))
    raw_count = int(identity["raw_bag_count"])
    full = completed == raw_count
    metrics = _metric_template()
    for name in (
        "completed_raw_bag_count",
        "completion_rate",
        "on_time_raw_bag_count",
        "on_time_rate",
        "missed_bag_count",
        "missed_bag_rate",
    ):
        value = business.get(name)
        metrics[name] = None if value is None else _finite_metric(value, name)
    tardiness = business.get("tardiness_seconds", {}).get(
        "fixed_horizon_all_population_lower_bound", {}
    )
    for suffix in ("sum", "mean", "p95", "p99", "max"):
        value = tardiness.get(suffix)
        metrics[f"tardiness_{suffix}_seconds"] = (
            None if value is None else _finite_metric(value, f"tardiness_{suffix}")
        )
    backlog = business.get("backlog", {})
    backlog_paths = {
        "source_backlog_area_seconds": "raw_bag_source_until_all_segments_admitted",
        "network_backlog_area_seconds": "raw_bag_network_after_all_segments_admitted",
        "total_backlog_area_seconds": "raw_bag_total",
    }
    for metric_name, native_name in backlog_paths.items():
        value = backlog.get(native_name, {}).get("backlog_area_seconds")
        metrics[metric_name] = None if value is None else _finite_metric(value, metric_name)
    completion_targets = business.get("completion_targets") or {}
    for percentage in (90, 95, 99):
        target = completion_targets.get(f"time_to_{percentage}_percent") or {}
        value = target.get("elapsed_from_first_arrival_seconds") if target.get("reached") else None
        metrics[f"time_to_{percentage}_percent_seconds"] = (
            None if value is None else _finite_metric(value, f"time_to_{percentage}_percent")
        )
    # Native fixed-horizon runs deliberately emit null when the full raw-bag
    # population does not complete.  That is the expected 2x representation,
    # not a missing-evidence error: formal survivor timing must remain N/A.
    timing = native.get("full_population_timing") or {}
    distributions = timing.get("distributions") or {}
    seconds = distributions.get("processed_attempt") or {}
    if float(identity["load_factor"]) != 2.0 and full:
        _timing_from_seconds(
            metrics,
            seconds,
            full_population_complete=True,
            load_factor=float(identity["load_factor"]),
            expected_count=raw_count,
        )
    result_contract = {
        "native_schema": native.get("schema"),
        "fixed_horizon_native_contract": "DECLARED_FIXED_HORIZON",
        "timing_denominator": "processed_attempt",
        "native_executor_identity": provenance.get("executor_identity"),
        "native_binary_sha256": provenance.get("binary_sha256"),
    }
    return metrics, full, [native_path], result_contract


def normalize_native_result(
    *,
    method: str,
    identity_path: Path,
    result_dir: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Normalize one method without changing or imputing native evidence."""

    identity_path, identity = _identity_payload(identity_path)
    result_dir = result_dir.resolve()
    if method == "FENG_NATIVE_HCA":
        metrics, full, evidence_paths, contract = _normalize_hca(
            identity, result_dir / "hca_native"
        )
    elif method == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION":
        metrics, full, evidence_paths, contract = _normalize_dh(
            identity_path, identity, result_dir / "feng_env_dh"
        )
    elif method == "G31_S4_NATIVE_SYSTEM":
        metrics, full, evidence_paths, contract = _normalize_g31(
            identity, result_dir / "g31_native.json"
        )
    else:
        raise ExternalBaselineError(f"unknown normalization method: {method}")

    load_factor = float(identity["load_factor"])
    if load_factor == 2.0:
        for name in TIMING_METRICS:
            metrics[name] = None
    elif not full:
        for name in TIMING_METRICS:
            metrics[name] = None
    payload = {
        "schema": RESULT_SCHEMA,
        "status": "COMPLETE",
        "method": method,
        "map": identity["map"],
        "load_factor": load_factor,
        "seed": int(identity["seed"]),
        "fixed_horizon_seconds": FIXED_HORIZON_SECONDS,
        "workload_identity_path": str(identity_path),
        "workload_identity_sha256": _sha256_file(identity_path),
        "workload_raw_sha256": identity["raw_sha256"],
        "workload_canonical_sha256": identity["canonical_sha256"],
        "workload_map_sha256": identity["map_sha256"],
        "storage_in_goal": int(identity["storage_in_goal"]),
        "storage_out_start": int(identity["storage_out_start"]),
        "raw_bag_denominator": int(identity["raw_bag_count"]),
        "segment_denominator": int(identity["segment_count"]),
        "full_population_complete": full,
        "survivor_timing_used": False,
        "formal_timing_status": (
            "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
            if load_factor == 2.0
            else (
                "FULL_POPULATION_RAW_BAG_TIMING"
                if full
                else "NOT_MEASURED_FULL_POPULATION_INCOMPLETE"
            )
        ),
        "normalization_contract": {
            **contract,
            "fixed_denominator": True,
            "null_means_not_derivable_from_native_evidence": True,
            "survivor_or_common_cohort_forbidden": True,
        },
        "native_evidence": _native_evidence(evidence_paths),
        "metrics": metrics,
        "normalized_at": _utc_now(),
    }
    target = output_path or result_dir / f"{method}.json"
    _atomic_json(target, payload)
    load_normalized_result(target)
    return payload


def _finite_metric(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExternalBaselineError(f"metric {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ExternalBaselineError(f"metric {label} must be finite")
    return result


def load_normalized_result(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != RESULT_SCHEMA:
        raise ExternalBaselineError(f"unexpected external result schema: {path}")
    if value.get("method") not in METHODS:
        raise ExternalBaselineError(f"unknown external method: {path}")
    seed = int(value.get("seed"))
    load_factor = float(value.get("load_factor"))
    map_name = str(value.get("map", ""))
    if seed not in SEEDS or load_factor not in LOAD_FACTORS:
        raise ExternalBaselineError(f"result coordinates are not frozen: {path}")
    map_protocol(map_name)
    identity_path = Path(value["workload_identity_path"])
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if identity.get("schema") != WORKLOAD_SCHEMA:
        raise ExternalBaselineError(f"unexpected workload identity schema: {identity_path}")
    if value.get("workload_identity_sha256") != _sha256_file(identity_path):
        raise ExternalBaselineError(f"result/workload identity hash mismatch: {path}")
    if (
        value.get("seed") != identity.get("seed")
        or float(value.get("load_factor")) != float(identity.get("load_factor"))
        or map_name != identity.get("map")
    ):
        raise ExternalBaselineError(f"result workload coordinates mismatch: {path}")
    if value.get("survivor_timing_used") is not False:
        raise ExternalBaselineError(f"survivor timing is forbidden: {path}")
    if "fixed_horizon_seconds" in value and float(
        value["fixed_horizon_seconds"]
    ) != FIXED_HORIZON_SECONDS:
        raise ExternalBaselineError(f"result fixed horizon mismatch: {path}")
    if "workload_raw_sha256" in value and value["workload_raw_sha256"] != identity.get(
        "raw_sha256"
    ):
        raise ExternalBaselineError(f"result raw workload hash mismatch: {path}")
    if "workload_canonical_sha256" in value and value[
        "workload_canonical_sha256"
    ] != identity.get("canonical_sha256"):
        raise ExternalBaselineError(f"result canonical workload hash mismatch: {path}")
    if value.get("workload_map_sha256") != identity.get("map_sha256"):
        raise ExternalBaselineError(f"result map workload hash mismatch: {path}")
    if int(value.get("storage_in_goal", -1)) != int(
        identity.get("storage_in_goal", -2)
    ) or int(value.get("storage_out_start", -1)) != int(
        identity.get("storage_out_start", -2)
    ):
        raise ExternalBaselineError(f"result storage identity mismatch: {path}")
    if "raw_bag_denominator" in value and int(value["raw_bag_denominator"]) != int(
        identity.get("raw_bag_count", -1)
    ):
        raise ExternalBaselineError(f"result raw denominator mismatch: {path}")
    if "segment_denominator" in value and int(value["segment_denominator"]) != int(
        identity.get("segment_count", -1)
    ):
        raise ExternalBaselineError(f"result segment denominator mismatch: {path}")
    evidence = value.get("native_evidence", [])
    if evidence is not None and not isinstance(evidence, list):
        raise ExternalBaselineError(f"native evidence must be a list: {path}")
    for record in evidence or []:
        if not isinstance(record, Mapping):
            raise ExternalBaselineError(f"malformed native evidence record: {path}")
        evidence_path = Path(str(record.get("path", "")))
        if not evidence_path.is_file() or _sha256_file(evidence_path) != record.get(
            "sha256"
        ):
            raise ExternalBaselineError(f"native evidence hash mismatch: {evidence_path}")
    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ExternalBaselineError(f"result lacks metrics: {path}")
    for name, metric in metrics.items():
        if metric is not None:
            _finite_metric(metric, str(name))
    full = value.get("full_population_complete") is True
    contract = value.get("normalization_contract")
    if not isinstance(contract, Mapping):
        raise ExternalBaselineError(f"result lacks normalization contract: {path}")
    if value["method"] == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION":
        if contract.get("reconstruction_java_source_sha256") != EXPECTED_DH_SOURCE_SHA256:
            raise ExternalBaselineError(f"normalized DH source is not final: {path}")
        if contract.get("compiled_java_class_sha256") != EXPECTED_DH_CLASS_SHA256:
            raise ExternalBaselineError(f"normalized DH classes are not final: {path}")
    if value["method"] == "G31_S4_NATIVE_SYSTEM" and contract.get(
        "native_binary_sha256"
    ) != EXPECTED_G31_BINARY_SHA256:
        raise ExternalBaselineError(f"normalized G31 binary is not final b00: {path}")
    if float(value["load_factor"]) == 2.0:
        if any(metrics.get(name) is not None for name in TIMING_METRICS):
            raise ExternalBaselineError(f"formal 2x timing must be N/A: {path}")
    elif not full and any(metrics.get(name) is not None for name in TIMING_METRICS):
        raise ExternalBaselineError(f"incomplete-population timing must be N/A: {path}")
    return value


def paired_bootstrap_ci(
    deltas: Sequence[float], *, replicates: int, seed_key: str
) -> tuple[float, float]:
    if not deltas or replicates < 1:
        raise ExternalBaselineError("paired bootstrap requires deltas and replicates")
    seed = int.from_bytes(hashlib.sha256(seed_key.encode("utf-8")).digest(), "big")
    rng = random.Random(seed)
    means = sorted(
        statistics.fmean(deltas[rng.randrange(len(deltas))] for _ in deltas)
        for _ in range(replicates)
    )
    return (
        internal_random._quantile(means, 0.025),
        internal_random._quantile(means, 0.975),
    )


def aggregate_results(
    result_paths: Iterable[Path], *, bootstrap_replicates: int = 10_000
) -> dict[str, Any]:
    indexed: dict[tuple[str, float, int, str], dict[str, Any]] = {}
    for path in result_paths:
        value = load_normalized_result(path)
        key = (
            str(value["map"]),
            float(value["load_factor"]),
            int(value["seed"]),
            str(value["method"]),
        )
        if key in indexed:
            raise ExternalBaselineError(f"duplicate external result: {key}")
        indexed[key] = value

    for map_name in MAPS:
        for load_factor in LOAD_FACTORS:
            for seed in SEEDS:
                hashes = {
                    indexed[(map_name, load_factor, seed, method)][
                        "workload_identity_sha256"
                    ]
                    for method in METHODS
                    if (map_name, load_factor, seed, method) in indexed
                }
                if len(hashes) > 1:
                    raise ExternalBaselineError(
                        "methods in one paired cell reference different workload identities: "
                        f"map={map_name}, load={load_factor}, seed={seed}"
                    )

    rows: list[dict[str, Any]] = []
    for map_name in MAPS:
        for load_factor in LOAD_FACTORS:
            for comparison in METHODS:
                if comparison == REFERENCE_METHOD:
                    continue
                pairs = [
                    (
                        indexed.get((map_name, load_factor, seed, comparison)),
                        indexed.get((map_name, load_factor, seed, REFERENCE_METHOD)),
                    )
                    for seed in SEEDS
                ]
                complete_pairs = [(left, right) for left, right in pairs if left and right]
                metric_names = sorted(HIGHER_IS_BETTER | LOWER_IS_BETTER)
                for metric in metric_names:
                    common = {
                        "map": map_name,
                        "load_factor": load_factor,
                        "comparison": reporting_method(map_name, comparison),
                        "runtime_comparison": comparison,
                        "reference": REFERENCE_METHOD,
                        "metric": metric,
                    }
                    if metric in TIMING_METRICS and load_factor == 2.0:
                        rows.append(
                            {
                                **common,
                                "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
                                "paired_seed_count": 0,
                            }
                        )
                        continue
                    values: list[tuple[int, float, float]] = []
                    for left, right in complete_pairs:
                        left_value = left["metrics"].get(metric)
                        right_value = right["metrics"].get(metric)
                        if left_value is None or right_value is None:
                            continue
                        values.append(
                            (
                                int(left["seed"]),
                                _finite_metric(left_value, metric),
                                _finite_metric(right_value, metric),
                            )
                        )
                    status = "COMPLETE" if len(values) == len(SEEDS) else "INCOMPLETE"
                    if not values:
                        rows.append(
                            {
                                **common,
                                "status": status,
                                "paired_seed_count": 0,
                            }
                        )
                        continue
                    deltas = [reference - baseline for _seed, baseline, reference in values]
                    direction = "higher" if metric in HIGHER_IS_BETTER else "lower"
                    oriented = (
                        deltas if direction == "higher" else [-value for value in deltas]
                    )
                    wins = sum(value > 1.0e-12 for value in oriented)
                    ties = sum(abs(value) <= 1.0e-12 for value in oriented)
                    losses = sum(value < -1.0e-12 for value in oriented)
                    low, high = paired_bootstrap_ci(
                        deltas,
                        replicates=bootstrap_replicates,
                        seed_key=(
                            f"external|{map_name}|{load_factor}|{comparison}|{metric}"
                        ),
                    )
                    rows.append(
                        {
                            **common,
                            "preferred_direction": direction,
                            "status": status,
                            "paired_seed_count": len(values),
                            "missing_seed_count": len(SEEDS) - len(values),
                            "baseline_mean": statistics.fmean(
                                value for _seed, value, _ref in values
                            ),
                            "reference_mean": statistics.fmean(
                                value for _seed, _base, value in values
                            ),
                            "mean_delta_reference_minus_baseline": statistics.fmean(
                                deltas
                            ),
                            "bootstrap_ci_low": low,
                            "bootstrap_ci_high": high,
                            "reference_win_count": wins,
                            "tie_count": ties,
                            "reference_loss_count": losses,
                        }
                    )
    expected_count = len(MAPS) * len(LOAD_FACTORS) * len(SEEDS) * len(METHODS)
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": "COMPLETE" if len(indexed) == expected_count else "INCOMPLETE",
        "maps": list(MAPS),
        "expected_result_count": expected_count,
        "observed_result_count": len(indexed),
        "bootstrap_replicates": bootstrap_replicates,
        "confidence_level": 0.95,
        "rows": rows,
    }


def _write_aggregate_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _execute_one_method(
    *,
    method: str,
    map_name: str,
    load_factor: float,
    seed: int,
    entry: Mapping[str, Any],
    identity_path: Path,
    result_dir: Path,
    force: bool,
    normalize_only: bool,
) -> tuple[dict[str, Any], bool]:
    normalized_path = result_dir / f"{method}.json"
    failure_path = result_dir / f"{method}.failure.json"
    coordinate = {
        "method": method,
        "map": map_name,
        "load_factor": load_factor,
        "seed": seed,
        "normalized_result": str(normalized_path.resolve()),
    }
    if normalized_path.is_file() and not force:
        try:
            existing = load_normalized_result(normalized_path)
            if existing["method"] != method or existing["map"] != map_name:
                raise ExternalBaselineError("normalized result coordinate mismatch")
        except (
            ExternalBaselineError,
            OSError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ):
            pass
        else:
            if failure_path.exists():
                failure_path.unlink()
            return {**coordinate, "status": "SKIPPED_SUCCESS"}, False

    native_normalization_error: str | None = None
    if not force:
        try:
            normalize_native_result(
                method=method,
                identity_path=identity_path,
                result_dir=result_dir,
                output_path=normalized_path,
            )
        except (
            ExternalBaselineError,
            OSError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            native_normalization_error = str(exc)
        else:
            if failure_path.exists():
                failure_path.unlink()
            return {**coordinate, "status": "NORMALIZED_EXISTING_NATIVE"}, False

    if normalize_only:
        failure = {
            "schema": SCHEMA,
            **coordinate,
            "status": "FAILED_NATIVE_EVIDENCE_NOT_NORMALIZABLE",
            "normalization_error": (
                native_normalization_error
                or "--force and --normalize-only cannot execute a native rerun"
            ),
            "recorded_at": _utc_now(),
        }
        _atomic_json(failure_path, failure)
        return failure, True

    command = list(entry["commands"][method])
    if force and "--force" not in command:
        command.append("--force")
    started_at = _utc_now()
    wall_started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        completed = None
        launch_error = str(exc)
    else:
        launch_error = None
    execution = {
        "command": command,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "wall_seconds": time.perf_counter() - wall_started,
        "returncode": None if completed is None else completed.returncode,
        "stdout_tail": "" if completed is None else completed.stdout[-4000:],
        "stderr_tail": "" if completed is None else completed.stderr[-4000:],
        "launch_error": launch_error,
        "pre_execution_normalization_error": native_normalization_error,
    }
    if completed is not None and completed.returncode == 0:
        try:
            normalize_native_result(
                method=method,
                identity_path=identity_path,
                result_dir=result_dir,
                output_path=normalized_path,
            )
        except (
            ExternalBaselineError,
            OSError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            execution["normalization_error"] = str(exc)
        else:
            if failure_path.exists():
                failure_path.unlink()
            return {
                **coordinate,
                "status": "EXECUTED_AND_NORMALIZED",
                **execution,
            }, False
    failure = {
        "schema": SCHEMA,
        **coordinate,
        "status": "FAILED_EXECUTION_OR_NORMALIZATION",
        **execution,
        "recorded_at": _utc_now(),
    }
    _atomic_json(failure_path, failure)
    return failure, True


def execute_campaign(
    *,
    workload_root: Path,
    result_root: Path,
    python: str,
    java: str,
    javac: str,
    binary: Path,
    methods: Sequence[str],
    load_factors: Sequence[float],
    seeds: Sequence[int],
    maps: Sequence[str] = (DEFAULT_MAP_NAME,),
    force: bool = False,
    normalize_only: bool = False,
    status_output: Path | None = None,
) -> dict[str, Any]:
    """Resume selected cells, normalizing existing successful native evidence first."""

    plan = build_dry_run_plan(
        workload_root=workload_root,
        result_root=result_root,
        python=python,
        java=java,
        javac=javac,
        binary=binary,
        maps=maps,
    )
    selected = {
        (str(entry["map"]), float(entry["load_factor"]), int(entry["seed"])): entry
        for entry in plan["entries"]
        if str(entry["map"]) in maps
        and float(entry["load_factor"]) in load_factors
        and int(entry["seed"]) in seeds
    }
    records: list[dict[str, Any]] = []
    failure_count = 0
    for map_name in maps:
        for load_factor in load_factors:
            for seed in seeds:
                entry = selected[(str(map_name), float(load_factor), int(seed))]
                identity_path = Path(entry["identity"])
                audit_cell(identity_path)
                result_dir = cell_dir(
                    result_root, float(load_factor), int(seed), str(map_name)
                )
                result_dir.mkdir(parents=True, exist_ok=True)
                for method in methods:
                    record, failed = _execute_one_method(
                        method=method,
                        map_name=str(map_name),
                        load_factor=float(load_factor),
                        seed=int(seed),
                        entry=entry,
                        identity_path=identity_path,
                        result_dir=result_dir,
                        force=force,
                        normalize_only=normalize_only,
                    )
                    records.append(record)
                    failure_count += int(failed)

    summary = {
        "schema": SCHEMA,
        "status": "COMPLETE" if failure_count == 0 else "INCOMPLETE_WITH_FAILURES",
        "generated_at": _utc_now(),
        "selected_map_count": len(maps),
        "selected_method_count": len(methods),
        "selected_load_count": len(load_factors),
        "selected_seed_count": len(seeds),
        "selected_run_count": (
            len(maps) * len(methods) * len(load_factors) * len(seeds)
        ),
        "failure_count": failure_count,
        "records": records,
    }
    _atomic_json(status_output or result_root / "execution_status.json", summary)
    return summary


def write_markdown_report(
    path: Path,
    aggregate: Mapping[str, Any],
    normalized_results: Sequence[Mapping[str, Any]],
) -> None:
    lines = [
        "# CIE external-baseline robustness report",
        "",
        f"Status: `{aggregate['status']}` ({aggregate['observed_result_count']}/"
        f"{aggregate['expected_result_count']} normalized results).",
        "",
        "All cells use the exact per-seed workload identity and a 98259-second "
        "fixed observation horizon. Population latency is reported only for a "
        "complete full population; formal 2x timing is always N/A. Null means "
        "the metric was not derivable from native evidence.",
        "",
        "Identity boundary: the map2 CIE-DH values reported in Feng et al. are "
        "historical literature evidence only and are not represented by the "
        "native cells below. `FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION` is a "
        "cross-map executable partial reconstruction in the archived Java "
        "environment, not the paper's original CIE-DH implementation. Its "
        "results may be optimistically biased and must not support a claim "
        "about the original algorithm or a leading-performance claim.",
        "",
        "For Nanning rows the report uses "
        "`FENG_PAPER_ENV_CIE_DH_NANNING_PORTED` as a reporting-scope alias. "
        "The runtime method remains the unchanged map2 partial reconstruction; "
        "the alias prevents the port from being back-attributed to Feng's "
        "paper.",
        "",
        "Execution accounting is based on validated normalized cells and the "
        "latest successful batch manifests. Superseded repair-attempt status "
        "files are retained as provenance and are not counted as current "
        "cell failures.",
        "",
        "## Normalized native cells",
        "",
        "| map | load | seed | method | completed | full | on-time | latency mean (s) |",
        "|---|---:|---:|---|---:|:---:|---:|---:|",
    ]
    for result in sorted(
        normalized_results,
        key=lambda row: (
            str(row["map"]),
            float(row["load_factor"]),
            int(row["seed"]),
            str(row["method"]),
        ),
    ):
        metrics = result["metrics"]
        latency = metrics.get("population_latency_mean_seconds")
        lines.append(
            "| {map} | {load:g} | {seed} | {method} | {completed} | {full} | {on_time} | {latency} |".format(
                map=result["map"],
                load=float(result["load_factor"]),
                seed=int(result["seed"]),
                method=reporting_method(str(result["map"]), str(result["method"])),
                completed=metrics.get("completed_raw_bag_count"),
                full="yes" if result.get("full_population_complete") else "no",
                on_time=metrics.get("on_time_raw_bag_count"),
                latency="N/A" if latency is None else f"{float(latency):.6f}",
            )
        )
    lines.extend(
        [
            "",
            "## Paired aggregate",
            "",
            "| map | load | comparison | metric | seeds | status | ref wins/ties/losses |",
            "|---|---:|---|---|---:|---|---:|",
        ]
    )
    for row in aggregate["rows"]:
        if int(row.get("paired_seed_count", 0)) == 0:
            continue
        lines.append(
            "| {map} | {load:g} | {comparison} | {metric} | {count} | {status} | {wins}/{ties}/{losses} |".format(
                map=row["map"],
                load=float(row["load_factor"]),
                comparison=row["comparison"],
                metric=row["metric"],
                count=int(row["paired_seed_count"]),
                status=row["status"],
                wins=int(row.get("reference_win_count", 0)),
                ties=int(row.get("tie_count", 0)),
                losses=int(row.get("reference_loss_count", 0)),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _selection(values: Sequence[Any] | None, expected: Sequence[Any]) -> tuple[Any, ...]:
    if not values:
        return tuple(expected)
    selected = tuple(values)
    if any(value not in expected for value in selected) or len(set(selected)) != len(selected):
        raise ExternalBaselineError(f"selection differs from frozen values: {selected}")
    return selected


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("--map", choices=MAPS, action="append")
    generate.add_argument("--source", type=Path)
    generate.add_argument("--nanning-source", type=Path)
    generate.add_argument("--output-root", type=Path, default=DEFAULT_WORKLOAD_ROOT)
    generate.add_argument("--load-factor", type=float, action="append")
    generate.add_argument("--seed", type=int, action="append")
    generate.add_argument("--force", action="store_true")

    audit = commands.add_parser("audit")
    audit.add_argument("--map", choices=MAPS, action="append")
    audit.add_argument("--workload-root", type=Path, default=DEFAULT_WORKLOAD_ROOT)
    audit.add_argument("--output", type=Path)

    dry = commands.add_parser("dry-run")
    dry.add_argument("--map", choices=MAPS, action="append")
    dry.add_argument("--workload-root", type=Path, default=DEFAULT_WORKLOAD_ROOT)
    dry.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    dry.add_argument("--binary", type=Path, required=True)
    dry.add_argument("--python", default=sys.executable)
    dry.add_argument("--java", default="java")
    dry.add_argument("--javac", default="javac")
    dry.add_argument("--output", type=Path, required=True)

    execute = commands.add_parser("execute", aliases=["run"])
    execute.add_argument("--map", choices=MAPS, action="append")
    execute.add_argument("--workload-root", type=Path, default=DEFAULT_WORKLOAD_ROOT)
    execute.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    execute.add_argument("--binary", type=Path, required=True)
    execute.add_argument("--python", default=sys.executable)
    execute.add_argument("--java", default="java")
    execute.add_argument("--javac", default="javac")
    execute.add_argument("--method", choices=METHODS, action="append")
    execute.add_argument("--load-factor", type=float, action="append")
    execute.add_argument("--seed", type=int, action="append")
    execute.add_argument("--force", action="store_true")
    execute.add_argument("--normalize-only", action="store_true")
    execute.add_argument(
        "--status-output",
        type=Path,
        help="optional per-batch status path; useful for concurrent load partitions",
    )

    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    aggregate.add_argument("--output-json", type=Path, required=True)
    aggregate.add_argument("--output-csv", type=Path, required=True)
    aggregate.add_argument("--output-report", type=Path)
    aggregate.add_argument("--bootstrap-replicates", type=int, default=10_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        maps = _selection(args.map, MAPS)
        loads = _selection(args.load_factor, LOAD_FACTORS)
        seeds = _selection(args.seed, SEEDS)
        sources = {
            map_name: prepare_frozen_source(
                map_name,
                args.source if map_name == "map2" else args.nanning_source,
            )
            for map_name in maps
        }
        map2_selection_source = (
            sources.get("map2")
            or prepare_frozen_source("map2", args.source)
            if "nanning" in maps and any(float(load) in {1.75, 2.0} for load in loads)
            else None
        )
        identities = []
        for map_name in maps:
            for load in loads:
                for seed in seeds:
                    identities.append(
                        generate_cell(
                            source_path=sources[map_name],
                            output_root=args.output_root,
                            load_factor=float(load),
                            seed=int(seed),
                            map_name=map_name,
                            selection_source_path=(
                                map2_selection_source
                                if map_name == "nanning"
                                and float(load) in {1.75, 2.0}
                                else None
                            ),
                            force=args.force,
                        )
                    )
        print(json.dumps({"status": "COMPLETE", "generated": len(identities)}))
        return 0
    if args.command == "audit":
        audit = audit_campaign(
            args.workload_root, maps=_selection(args.map, MAPS)
        )
        if args.output:
            _atomic_json(args.output, audit)
        print(json.dumps({"status": audit["status"], "audited": audit["audited_cell_count"]}))
        return 0 if audit["status"] == "COMPLETE" else 2
    if args.command == "dry-run":
        plan = build_dry_run_plan(
            workload_root=args.workload_root,
            result_root=args.result_root,
            python=args.python,
            java=args.java,
            javac=args.javac,
            binary=args.binary,
            maps=_selection(args.map, MAPS),
        )
        _atomic_json(args.output, plan)
        print(json.dumps({"status": plan["status"], "commands": plan["command_count"]}))
        return 0
    if args.command in {"execute", "run"}:
        methods = _selection(args.method, METHODS)
        maps = _selection(args.map, MAPS)
        loads = _selection(args.load_factor, LOAD_FACTORS)
        seeds = _selection(args.seed, SEEDS)
        summary = execute_campaign(
            workload_root=args.workload_root,
            result_root=args.result_root,
            python=args.python,
            java=args.java,
            javac=args.javac,
            binary=args.binary,
            methods=methods,
            load_factors=loads,
            seeds=seeds,
            maps=maps,
            force=args.force,
            normalize_only=args.normalize_only,
            status_output=args.status_output,
        )
        print(
            json.dumps(
                {
                    "status": summary["status"],
                    "selected": summary["selected_run_count"],
                    "failures": summary["failure_count"],
                }
            )
        )
        return 0 if summary["failure_count"] == 0 else 2

    paths = sorted(args.result_root.rglob("*.json"))
    normalized = []
    normalized_values = []
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, Mapping) and value.get("schema") == RESULT_SCHEMA:
            normalized.append(path)
            normalized_values.append(load_normalized_result(path))
    aggregate = aggregate_results(
        normalized, bootstrap_replicates=args.bootstrap_replicates
    )
    _atomic_json(args.output_json, aggregate)
    _write_aggregate_csv(args.output_csv, aggregate["rows"])
    if args.output_report:
        write_markdown_report(args.output_report, aggregate, normalized_values)
    print(
        json.dumps(
            {"status": aggregate["status"], "results": aggregate["observed_result_count"]}
        )
    )
    return 0 if aggregate["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ExternalBaselineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"external baseline robustness failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

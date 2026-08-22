#!/usr/bin/env python3
"""Run a small, whole-bag Nanning smoke through HCA* and S4.

This is a portability smoke, not a paper-result campaign.  It takes the
earliest N raw bags from either generated Nanning workload, keeps a direct
bag's one canonical segment or an early bag's two storage segments together,
and runs both real implementations at the same 2.5 m/s edge speed.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from czr005.io.legacy_tasks import RawLegacyTask, parse_legacy_tasks  # noqa: E402
from scripts.eval import g4irsf31_map_adapter as map_adapter  # noqa: E402
from scripts.eval import run_g4irsf24_fresh_hca as fresh_hca  # noqa: E402
from scripts.eval import run_g4irsf29_workload as workload_2x  # noqa: E402


SCHEMA = "czr005.g4irsf31.nanning_smoke.v1"
SPEED_MPS = 2.5
DEFAULT_TASK_DIR = ROOT / "artifacts/tasks/g4irsf31_nanning"
DEFAULT_MAP_PROFILE = ROOT / "data/processed/maps/nanning_airport_profile.json"
DEFAULT_LEGACY_MAP = ROOT / "data/processed/maps/nanning_legacy.txt"
DEFAULT_CLASSES = ROOT / "build/g4irsf31_nanning_java"
DEFAULT_BINARY_DIR = ROOT / "build/g4irsf24_dlp_release/python"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs/runtime/g4irsf31_nanning_smoke"


@dataclass(frozen=True)
class SmokeSelection:
    scale: int
    manifest_path: Path
    manifest: Mapping[str, Any]
    raw_header: str
    raw_tasks: tuple[RawLegacyTask, ...]
    canonical_rows: tuple[Mapping[str, Any], ...]

    @property
    def task_ids(self) -> tuple[int, ...]:
        return tuple(task.task_id for task in self.raw_tasks)


def _json_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _manifest_reference(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    root_relative = ROOT / path
    if root_relative.exists():
        return root_relative
    return manifest_path.parent / path


def load_selection(
    *,
    scale: int,
    earliest_raw_bags: int,
    task_dir: Path = DEFAULT_TASK_DIR,
) -> SmokeSelection:
    """Load one generated workload and retain complete raw-bag lifecycles."""

    if scale not in (1, 2):
        raise ValueError("scale must be 1 or 2")
    if earliest_raw_bags <= 0:
        raise ValueError("earliest_raw_bags must be positive")
    manifest_path = task_dir / f"nanning_{scale}x_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("scale", -1)) != scale:
        raise ValueError("workload manifest scale does not match the requested scale")

    raw_path = _manifest_reference(str(manifest["raw_output"]), manifest_path)
    canonical_path = _manifest_reference(
        str(manifest["canonical_output"]), manifest_path
    )
    raw_header, all_raw = parse_legacy_tasks(raw_path)
    selected_raw = tuple(
        sorted(all_raw, key=lambda row: (row.entry_time, row.task_id))[
            :earliest_raw_bags
        ]
    )
    selected_ids = {row.task_id for row in selected_raw}
    canonical = tuple(
        row for row in _json_rows(canonical_path) if int(row["task_id"]) in selected_ids
    )

    by_task: dict[int, list[Mapping[str, Any]]] = {
        task_id: [] for task_id in selected_ids
    }
    for row in canonical:
        by_task[int(row["task_id"])].append(row)
    threshold = float(manifest["lifecycle"]["early_bag_threshold_seconds"])
    for raw in selected_raw:
        expected_legs = (
            {"direct"}
            if raw.std - raw.entry_time < threshold
            else {"storage_in", "storage_out"}
        )
        actual_legs = {str(row["leg"]) for row in by_task[raw.task_id]}
        if actual_legs != expected_legs:
            raise ValueError(
                f"canonical lifecycle for raw bag {raw.task_id} is incomplete: "
                f"{sorted(actual_legs)}"
            )
    return SmokeSelection(
        scale=scale,
        manifest_path=manifest_path,
        manifest=manifest,
        raw_header=raw_header,
        raw_tasks=selected_raw,
        canonical_rows=canonical,
    )


def write_selection(selection: SmokeSelection, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "selected_raw.txt"
    canonical_path = output_dir / "selected_canonical.jsonl"
    workload_2x.write_raw_tasks(selection.raw_header, selection.raw_tasks, raw_path)
    with canonical_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in selection.canonical_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return raw_path, canonical_path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _int(row: Mapping[str, Any], name: str) -> int:
    return int(row.get(name, 0))


def _route_topology_check(
    route_rows: Sequence[Mapping[str, str]], profile_path: Path
) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    nodes = {int(row["location"]) for row in profile["nodes"]}
    edges = {(int(row["start"]), int(row["end"])) for row in profile["edges"]}
    invalid = 0
    for row in route_rows:
        path = [int(value) for value in str(row["path"]).split(";") if value]
        valid = (
            bool(path)
            and path[0] == int(row["start"])
            and path[-1] == int(row["goal"])
            and all(node in nodes for node in path)
            and all(pair in edges for pair in zip(path, path[1:]))
        )
        invalid += not valid
    return {
        "planned_route_count": len(route_rows),
        "invalid_route_count": invalid,
        "all_planned_routes_follow_selected_map": invalid == 0,
    }


def run_hca(
    selection: SmokeSelection,
    *,
    selected_raw_path: Path,
    legacy_map_path: Path,
    map_profile_path: Path,
    run_dir: Path,
    classes_dir: Path,
    java: str,
    javac: str,
    compile_java: bool,
    completion_padding_seconds: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    if compile_java:
        fresh_hca.compile_java(javac, classes_dir)

    start_epoch = max(0, math.floor(min(row.entry_time for row in selection.raw_tasks)) - 1)
    last_release = max(float(row["pass_time"]) for row in selection.canonical_rows)
    max_epochs = math.ceil(last_release - start_epoch) + completion_padding_seconds
    lifecycle = selection.manifest["lifecycle"]
    command = fresh_hca.java_run_command(
        java=java,
        classes_dir=classes_dir,
        map_path=legacy_map_path,
        input_path=selected_raw_path,
        start_epoch=start_epoch,
        max_epochs=max_epochs,
        max_new_tasks=0,
        run_dir=run_dir,
        speed_mps=SPEED_MPS,
        storage_in_goal=int(lifecycle["storage_in_goal"]),
        storage_out_start=int(lifecycle["storage_out_start"]),
        early_threshold_seconds=float(lifecycle["early_bag_threshold_seconds"]),
        storage_lead_seconds=float(lifecycle["storage_out_lead_seconds"]),
    )
    completed = subprocess.run(
        command,
        cwd=run_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=None if timeout_seconds <= 0 else timeout_seconds,
    )
    (run_dir / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
    summary_rows = _read_csv(run_dir / "summary.csv") if (run_dir / "summary.csv").exists() else []
    route_rows = _read_csv(run_dir / "routes.csv") if (run_dir / "routes.csv").exists() else []
    release_rows = _read_csv(run_dir / "release.csv") if (run_dir / "release.csv").exists() else []
    summary = summary_rows[0] if summary_rows else {}
    expected = len(selection.canonical_rows)
    topology = _route_topology_check(route_rows, map_profile_path)
    no_fault = all(
        _int(summary, field) == 0
        for field in ("fault_event_count", "repair_event_count", "active_fault_count")
    )
    counts = {
        "expected_segment_count": expected,
        "released_segment_count": len(release_rows),
        "planned_segment_count": _int(summary, "planned_count"),
        "completed_segment_count": _int(summary, "completed_count"),
        "unfinished_segment_count": _int(summary, "unfinished_count"),
    }
    all_complete = (
        completed.returncode == 0
        and counts["released_segment_count"] == expected
        and counts["planned_segment_count"] == expected
        and counts["completed_segment_count"] == expected
    )
    # The Java benchmark exposes route/reservation results but no standalone
    # collision counter, so the smoke reports exactly the checks it can make.
    safety = {
        "no_fault_injected": no_fault,
        **topology,
        "reservation_collision_counter_exposed": False,
        "pass": completed.returncode == 0
        and no_fault
        and topology["all_planned_routes_follow_selected_map"],
    }
    fresh_hca._cleanup_epoch_files(run_dir)
    return {
        "implementation": "original_java_hca_star",
        "returncode": completed.returncode,
        "start_epoch": start_epoch,
        "max_epochs": max_epochs,
        "speed_mps": SPEED_MPS,
        "storage_in_goal": int(lifecycle["storage_in_goal"]),
        "storage_out_start": int(lifecycle["storage_out_start"]),
        "counts": counts,
        "all_selected_segments_completed": all_complete,
        "safety": safety,
    }


def discover_native_binary(binary: Path | None = None) -> Path:
    if binary is not None:
        return binary.resolve(strict=True)
    candidates = sorted(DEFAULT_BINARY_DIR.glob("czr005_cpp*.pyd"))
    if not candidates:
        raise FileNotFoundError(f"no native module found in {DEFAULT_BINARY_DIR}")
    return candidates[-1].resolve()


def run_s4(
    selection: SmokeSelection,
    *,
    map_profile_path: Path,
    binary: Path,
    max_events: int,
) -> dict[str, Any]:
    lifecycle = selection.manifest["lifecycle"]
    storage_node = int(lifecycle["storage_out_start"])
    profile = map_adapter.load_map_profile(
        map_profile_path, storage_source_nodes=[storage_node]
    )
    request, _potential_contract = map_adapter.build_s4_request(
        profile,
        selection.canonical_rows,
        binary=binary,
        scenario=f"g4irsf31_nanning_{selection.scale}x_smoke",
        max_events=max_events,
        summary_only=True,
        edge_speed_mps=SPEED_MPS,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
        complete_on_goal_arrival=True,
    )
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    summary = dict(payload["summary"])
    expected = len(selection.canonical_rows)
    counts = {
        "expected_segment_count": expected,
        "requested_segment_count": _int(summary, "requested_count"),
        "completed_segment_count": _int(summary, "completed_count"),
        "failed_segment_count": _int(summary, "failed_count"),
    }
    all_complete = (
        counts["requested_segment_count"] == expected
        and counts["completed_segment_count"] == expected
        and counts["failed_segment_count"] == 0
        and not bool(summary.get("event_limit_reached", False))
        and not bool(summary.get("time_limit_reached", False))
    )
    safety_fields = (
        "reservation_conflicts",
        "physical_fault_edge_entry_violation_count",
        "unresolved_deadlock_count",
    )
    safety = {field: _int(summary, field) for field in safety_fields}
    safety["pass"] = all(value == 0 for value in safety.values())
    return {
        "implementation": "s4_j2_e2_node_local_fifo",
        "speed_mps": SPEED_MPS,
        "storage_source_nodes": [storage_node],
        "counts": counts,
        "all_selected_segments_completed": all_complete,
        "safety": safety,
        "runtime": {
            "event_count": _int(summary, "event_count"),
            "decision_count": _int(summary, "decision_count"),
            "event_limit_reached": bool(summary.get("event_limit_reached", False)),
            "time_limit_reached": bool(summary.get("time_limit_reached", False)),
        },
    }


def run_smoke(
    *,
    scale: int,
    earliest_raw_bags: int,
    task_dir: Path = DEFAULT_TASK_DIR,
    map_profile_path: Path = DEFAULT_MAP_PROFILE,
    legacy_map_path: Path = DEFAULT_LEGACY_MAP,
    output_dir: Path | None = None,
    classes_dir: Path = DEFAULT_CLASSES,
    java: str = "java",
    javac: str = "javac",
    compile_java: bool = True,
    binary: Path | None = None,
    completion_padding_seconds: int = 1_800,
    timeout_seconds: int = 600,
    max_events: int = 2_000_000,
) -> dict[str, Any]:
    selection = load_selection(
        scale=scale,
        earliest_raw_bags=earliest_raw_bags,
        task_dir=task_dir,
    )
    active_output = output_dir or (
        DEFAULT_OUTPUT_ROOT / f"{scale}x_earliest_{earliest_raw_bags}"
    )
    selected_raw, _selected_canonical = write_selection(selection, active_output)
    selected_binary = discover_native_binary(binary)
    hca = run_hca(
        selection,
        selected_raw_path=selected_raw,
        legacy_map_path=legacy_map_path,
        map_profile_path=map_profile_path,
        run_dir=active_output / "hca",
        classes_dir=classes_dir,
        java=java,
        javac=javac,
        compile_java=compile_java,
        completion_padding_seconds=completion_padding_seconds,
        timeout_seconds=timeout_seconds,
    )
    s4 = run_s4(
        selection,
        map_profile_path=map_profile_path,
        binary=selected_binary,
        max_events=max_events,
    )
    expected_segments = len(selection.canonical_rows)
    pass_gate = all(
        (
            hca["all_selected_segments_completed"],
            hca["safety"]["pass"],
            s4["all_selected_segments_completed"],
            s4["safety"]["pass"],
        )
    )
    report = {
        "schema": SCHEMA,
        "status": "PASS" if pass_gate else "INCOMPLETE_OR_UNSAFE",
        "scope": "PORTABILITY_SMOKE_NOT_PAPER_RESULT",
        "scale": scale,
        "speed_mps": SPEED_MPS,
        "selection": {
            "rule": "earliest raw entry_time then task_id; retain every canonical leg",
            "selected_raw_bag_count": len(selection.raw_tasks),
            "selected_segment_count": expected_segments,
            "whole_raw_bags_retained": True,
            "task_ids": list(selection.task_ids),
        },
        "storage_role": {
            "storage_in_goal": int(
                selection.manifest["lifecycle"]["storage_in_goal"]
            ),
            "storage_out_start": int(
                selection.manifest["lifecycle"]["storage_out_start"]
            ),
            "same_node": (
                int(selection.manifest["lifecycle"]["storage_in_goal"])
                == int(selection.manifest["lifecycle"]["storage_out_start"])
            ),
        },
        "hca": hca,
        "s4": s4,
    }
    active_output.mkdir(parents=True, exist_ok=True)
    (active_output / "smoke.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=int, choices=(1, 2), default=1)
    parser.add_argument("--earliest-bags", type=int, default=4)
    parser.add_argument("--task-dir", type=Path, default=DEFAULT_TASK_DIR)
    parser.add_argument("--map-profile", type=Path, default=DEFAULT_MAP_PROFILE)
    parser.add_argument("--legacy-map", type=Path, default=DEFAULT_LEGACY_MAP)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--classes-dir", type=Path, default=DEFAULT_CLASSES)
    parser.add_argument("--java", default=shutil.which("java") or "java")
    parser.add_argument("--javac", default=shutil.which("javac") or "javac")
    parser.add_argument("--skip-java-compile", action="store_true")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--completion-padding-seconds", type=int, default=1_800)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-events", type=int, default=2_000_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_smoke(
        scale=args.scale,
        earliest_raw_bags=args.earliest_bags,
        task_dir=args.task_dir,
        map_profile_path=args.map_profile,
        legacy_map_path=args.legacy_map,
        output_dir=args.output_dir,
        classes_dir=args.classes_dir,
        java=args.java,
        javac=args.javac,
        compile_java=not args.skip_java_compile,
        binary=args.binary,
        completion_padding_seconds=args.completion_padding_seconds,
        timeout_seconds=args.timeout_seconds,
        max_events=args.max_events,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

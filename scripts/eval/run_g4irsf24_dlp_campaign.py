#!/usr/bin/env python3
"""Collect, fit, and test the small G24 decentralized delay potential.

The campaign keeps A0+S4+J2+E2 fixed.  DLP is only an immutable residual
table passed to the existing one-step Route MOVE scorer.  Collection uses
task shards so dense evidence remains manageable; all performance arms are
fresh unsharded native runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend
from scripts.eval import g4irsf24_dlp_learning as learning
from scripts.eval import run_g4irsf19_bounded_capacity as capacity
from scripts.eval import run_g4irsf19_route_campaign as route
from scripts.eval import run_g4irsf20_event_hotpath as hotpath
from scripts.eval import run_g4irsf24_native_race as native_race


SCHEMA = "czr005.g4irsf24.dlp_campaign.v1"
DEFAULT_WORK = ROOT / "build/g4irsf24_dlp_campaign"
DEFAULT_SCREEN = ROOT / "outputs/tables/g4irsf24_dlp_screen.json"
DEFAULT_LADDER = ROOT / "outputs/tables/g4irsf24_dlp_native_ladder.json"
DEFAULT_SCALE = ROOT / "outputs/tables/g4irsf24_dlp_4x_abba.json"
DEFAULT_POLICY = ROOT / "artifacts/policies/g4irsf24_dlp_selected.json"
DEFAULT_SELECTION = ROOT / "artifacts/policies/g4irsf24_dlp_selection.json"


class DLPCampaignError(RuntimeError):
    pass


CANDIDATE_SPECS: tuple[dict[str, Any], ...] = (
    {"id": "DLP_EWMA_A", "mode": "ewma", "alpha": 0.10, "beta": 0.5, "min_support": 8, "margin_seconds": 0.5},
    {"id": "DLP_EWMA_B", "mode": "ewma", "alpha": 0.10, "beta": 1.0, "min_support": 8, "margin_seconds": 0.5},
    {"id": "DLP_EWMA_C", "mode": "ewma", "alpha": 0.10, "beta": 0.5, "min_support": 32, "margin_seconds": 2.0},
    {"id": "DLP_EWMA_D", "mode": "ewma", "alpha": 0.20, "beta": 1.0, "min_support": 32, "margin_seconds": 2.0},
    {"id": "DLP_TD_A", "mode": "td", "alpha": 0.05, "beta": 0.5, "min_support": 8, "margin_seconds": 0.5},
    {"id": "DLP_TD_B", "mode": "td", "alpha": 0.10, "beta": 1.0, "min_support": 8, "margin_seconds": 0.5},
    {"id": "DLP_TD_C", "mode": "td", "alpha": 0.10, "beta": 0.5, "min_support": 32, "margin_seconds": 2.0},
    {"id": "DLP_TD_D", "mode": "td", "alpha": 0.20, "beta": 1.0, "min_support": 32, "margin_seconds": 2.0},
)


STRICT_ZERO_SUMMARY_FIELDS = (
    "failed_count",
    "reservation_conflicts",
    "physical_fault_edge_entry_violation_count",
    "unresolved_deadlock_count",
    "runtime_full_astar_calls",
    "global_reservation_scan_count",
    "priority_global_scan_count",
    "scorer_runtime_global_scan_count",
    "microphase_runtime_global_scan_count",
    "first_edge_credit_global_scan_count",
    "priority_future_route_input_count",
    "scorer_future_route_input_count",
    "first_edge_credit_future_route_count",
    "scorer_future_schedule_input_count",
    "full_future_routes_stored",
)
STRICT_FALSE_SUMMARY_FIELDS = (
    "event_limit_reached",
    "time_limit_reached",
    "bag_future_path_field_present",
    "full_cie_astar_runtime_fallback",
)
STRICT_SUMMARY_ECHOES = {
    "scorer_mode": capacity.SCORER_MODES["S4"],
    "merge_grant_timing_mode": "jit_fair_aging_deadline",
    "g4irsf20_event_hotpath_policy": "E2",
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DLPCampaignError(f"expected one JSON object: {path}")
    return value


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _stored_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _campaign_binding(
    *, binary: Path, work: Path, release_csv: Path
) -> dict[str, str]:
    return {
        "binary": _portable_path(binary),
        "work": _portable_path(work),
        "exact_1x_release_csv": _portable_path(release_csv),
    }


def _require_campaign_binding(
    payload: Mapping[str, Any],
    *,
    binary: Path,
    work: Path,
    release_csv: Path,
    label: str,
) -> None:
    expected = _campaign_binding(binary=binary, work=work, release_csv=release_csv)
    mismatches = [
        name for name, value in expected.items() if payload.get(name) != value
    ]
    if mismatches:
        raise DLPCampaignError(
            f"{label} campaign binding mismatch: {', '.join(mismatches)}"
        )


def _strict_summary_safety(
    summary: Mapping[str, Any], requested: int
) -> dict[str, Any]:
    required = (
        "completed_count",
        *STRICT_ZERO_SUMMARY_FIELDS,
        *STRICT_FALSE_SUMMARY_FIELDS,
        *STRICT_SUMMARY_ECHOES,
    )
    missing = [name for name in required if name not in summary]

    def zero(name: str) -> bool:
        value = summary.get(name)
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) == 0.0
        )

    completed = summary.get("completed_count")
    gates = {
        "all_required_fields_present": not missing,
        "all_segments_completed": (
            isinstance(completed, (int, float))
            and not isinstance(completed, bool)
            and float(completed) == float(requested)
        ),
        **{f"{name}_zero": zero(name) for name in STRICT_ZERO_SUMMARY_FIELDS},
        **{
            f"{name}_false": summary.get(name) is False
            for name in STRICT_FALSE_SUMMARY_FIELDS
        },
        **{
            f"{name}_echo": summary.get(name) == expected
            for name, expected in STRICT_SUMMARY_ECHOES.items()
        },
    }
    return {
        "pass": all(gates.values()),
        "gates": gates,
        "missing_fields": missing,
    }


def _artifact_contract(artifact: Mapping[str, Any]) -> dict[str, Any]:
    if artifact.get("schema") != learning.ARTIFACT_SCHEMA:
        raise DLPCampaignError("DLP artifact schema mismatch")
    mode = artifact.get("mode")
    if mode not in learning.MODES:
        raise DLPCampaignError("DLP artifact mode mismatch")

    def finite_nonnegative(name: str) -> float:
        value = artifact.get(name)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            raise DLPCampaignError(f"DLP artifact {name} must be finite and non-negative")
        return float(value)

    min_support = artifact.get("min_support")
    if not isinstance(min_support, int) or isinstance(min_support, bool) or min_support <= 0:
        raise DLPCampaignError("DLP artifact min_support must be a positive integer")
    edges = artifact.get("edge_residuals")
    values = artifact.get("value_residuals")
    if not isinstance(edges, list) or not isinstance(values, list):
        raise DLPCampaignError("DLP artifact residual tables must be lists")
    return {
        "schema": learning.ARTIFACT_SCHEMA,
        "mode": str(mode),
        "beta": finite_nonnegative("beta"),
        "min_support": min_support,
        "margin_seconds": finite_nonnegative("margin_seconds"),
        "detour_allowance_seconds": finite_nonnegative(
            "detour_allowance_seconds"
        ),
        "edge_residual_count": len(edges),
        "value_residual_count": len(values),
    }


def _candidate_ids(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise DLPCampaignError(f"{label} must be a list")
    result = [str(item) for item in value]
    if any(not item for item in result):
        raise DLPCampaignError(f"{label} contains an empty candidate id")
    if len(result) != len(set(result)):
        raise DLPCampaignError(f"{label} contains duplicate candidate ids")
    if len(result) > 2:
        raise DLPCampaignError(f"{label} contains more than two native candidates")
    return result


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _exact_release_rows(
    rows: Sequence[Mapping[str, Any]], release_csv: Path
) -> list[dict[str, Any]]:
    with release_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"segment_id", "release_epoch"}
        missing_columns = required - set(reader.fieldnames or ())
        if missing_columns:
            raise DLPCampaignError(
                "exact HCA release input must be the aggregated "
                f"segment_lifecycle.csv and is missing columns: "
                f"{', '.join(sorted(missing_columns))}"
            )
        releases: dict[str, float] = {}
        for line_number, row in enumerate(reader, start=2):
            segment_id = str(row.get("segment_id", "")).strip()
            if not segment_id:
                raise DLPCampaignError(
                    f"exact HCA release input has an empty segment_id at line {line_number}"
                )
            if segment_id in releases:
                raise DLPCampaignError(
                    f"exact HCA release input repeats segment_id {segment_id!r}"
                )
            try:
                release = float(row.get("release_epoch", ""))
            except (TypeError, ValueError) as exc:
                raise DLPCampaignError(
                    f"exact HCA release input has an invalid release_epoch at line {line_number}"
                ) from exc
            if not math.isfinite(release):
                raise DLPCampaignError(
                    f"exact HCA release input has a non-finite release_epoch at line {line_number}"
                )
            releases[segment_id] = release
    if not releases:
        raise DLPCampaignError("exact HCA release input contains no lifecycle rows")
    missing = {str(row["segment_id"]) for row in rows} - releases.keys()
    if missing:
        raise DLPCampaignError(
            f"exact HCA release trace lacks {len(missing)} selected segments"
        )
    return [
        {**row, "pass_time": releases[str(row["segment_id"])]}
        for row in rows
    ]


def _collection_request(
    rows: Sequence[Mapping[str, Any]],
    *,
    scale: int,
    repeat: int,
    binary: Path,
    shard_count: int,
) -> dict[str, Any]:
    request = hotpath.build_native_request(
        rows,
        scale=scale,
        policy="E2",
        binary=binary,
        root=ROOT,
        bounded_wall_seconds=60.0,
        check_events=65_536,
    )
    request.update(
        scenario=f"g4irsf24_transition_{scale}x_r{repeat}",
        summary_only=False,
        trace_limit=-1,
        event_trace_limit=0,
        trace_shard_count=shard_count,
        trace_shard_index=repeat % shard_count,
    )
    request.pop("bounded_wall_seconds", None)
    request.pop("bounded_check_every_events", None)
    return request


def collect(
    *,
    binary: Path,
    work: Path,
    release_csv: Path,
    repeats: int = 2,
    shard_count: int = 2,
) -> dict[str, Any]:
    if repeats < 2 or shard_count < repeats:
        raise DLPCampaignError("collection needs two repeats and distinct task shards")
    campaign_clock = 0.0
    transitions: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for scale in (1, 2):
        rows, descriptor = capacity.load_g18_scale_input(scale, ROOT)
        if scale == 1:
            rows = _exact_release_rows(rows, release_csv)
        for repeat in range(repeats):
            request = _collection_request(
                rows,
                scale=scale,
                repeat=repeat,
                binary=binary,
                shard_count=shard_count,
            )
            started = time.perf_counter()
            payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
            elapsed = time.perf_counter() - started
            decisions = payload.get("decisions")
            bags = payload.get("bags")
            summary = payload.get("summary")
            if not isinstance(decisions, list) or not isinstance(bags, list) or not isinstance(summary, Mapping):
                raise DLPCampaignError("transition run lacks decisions, bags, or summary")
            holds = payload.get("hold_attempts", [])
            if not isinstance(holds, list):
                raise DLPCampaignError("transition run hold_attempts is not a list")
            safety = _strict_summary_safety(summary, len(rows))
            active_dlp_fields = [
                str(name)
                for name in summary
                if str(name).startswith("g4irsf24_dlp_")
            ]
            if active_dlp_fields:
                raise DLPCampaignError(
                    "S4 transition collection unexpectedly activated G24 DLP fields"
                )
            trace_complete = (
                summary.get("decision_trace_truncated") is False
                and int(summary.get("trace_shard_count", -1)) == shard_count
                and int(summary.get("trace_shard_index", -1)) == repeat % shard_count
                and int(summary.get("decision_trace_stored_count", -1)) == len(decisions)
                and int(summary.get("hold_trace_stored_count", -1)) == len(holds)
                and int(summary.get("decision_trace_shard_seen_count", -1))
                == len(decisions) + len(holds)
            )
            if not safety["pass"] or not trace_complete:
                raise DLPCampaignError(
                    f"transition run failed safety/complete-trace gate: "
                    f"safety={safety['pass']} trace_complete={trace_complete}"
                )
            part = learning.build_transitions(decisions, bags)
            if not part:
                raise DLPCampaignError("transition shard produced no usable transitions")
            minimum = min(float(row["t0"]) for row in part)
            shifted: list[dict[str, Any]] = []
            for row in part:
                item = dict(row)
                item["t0"] = campaign_clock + float(row["t0"]) - minimum
                item["t1"] = item["t0"] + float(row["duration"])
                shifted.append(item)
            transitions.extend(shifted)
            campaign_clock = max(float(row["t1"]) for row in shifted) + 1.0
            sources.append(
                {
                    "scale": scale,
                    "repeat": repeat,
                    "trace_shard_count": shard_count,
                    "trace_shard_index": repeat % shard_count,
                    "input_segments": len(rows),
                    "stored_decisions": len(decisions),
                    "transition_count": len(part),
                    "wall_seconds": elapsed,
                    "completed_segments": int(summary.get("completed_count", -1)),
                    "safety": safety,
                    "trace_complete": trace_complete,
                    "decision_trace_seen": int(
                        summary.get("decision_trace_seen_count", 0)
                    ),
                    "decision_trace_shard_seen": int(
                        summary.get("decision_trace_shard_seen_count", 0)
                    ),
                    "input_descriptor": dict(descriptor),
                }
            )
            del payload, decisions, bags, part, shifted

    split = learning.chronological_split(transitions)
    transition_path = work / "transitions.jsonl"
    _write_jsonl(transition_path, transitions)
    artifacts: dict[str, str] = {}
    candidates: list[dict[str, Any]] = []
    for spec in CANDIDATE_SPECS:
        artifact = learning.build_artifact(
            split["train"],
            mode=str(spec["mode"]),
            alpha=float(spec["alpha"]),
            beta=float(spec["beta"]),
            min_support=int(spec["min_support"]),
            margin_seconds=float(spec["margin_seconds"]),
            detour_allowance_seconds=2.0,
        )
        artifact_path = work / "artifacts" / f"{spec['id']}.json"
        _write_json(artifact_path, artifact)
        artifacts[str(spec["id"])] = str(artifact_path)
        candidates.append(
            {
                **spec,
                "detour_allowance_seconds": 2.0,
                "edge_residual_count": len(artifact["edge_residuals"]),
                "value_residual_count": len(artifact["value_residuals"]),
            }
        )
    validation = _offline_residual_ranking(
        split["validation"], candidates, artifacts
    )
    held_out_test = _offline_residual_ranking(
        split["test"], candidates, artifacts
    )
    native_candidate_ids: list[str] = []
    for mode in ("ewma", "td"):
        family = [row for row in validation if row["mode"] == mode]
        if family:
            native_candidate_ids.append(str(family[0]["candidate_id"]))
    state = {
        "schema": SCHEMA,
        "stage": "COLLECTED_AND_FIT",
        **_campaign_binding(binary=binary, work=work, release_csv=release_csv),
        "sources": sources,
        "transition_path": _portable_path(transition_path),
        "transition_count": len(transitions),
        "split_counts": {name: len(rows) for name, rows in split.items()},
        "feature_exclusions": [
            "task_id",
            "runtime_bag_id",
            "decision_id",
            "absolute_event_time_as_model_feature",
        ],
        "candidates": candidates,
        "artifacts": {
            candidate_id: _portable_path(Path(path))
            for candidate_id, path in artifacts.items()
        },
        "offline_validation": validation,
        "offline_test": held_out_test,
        "native_candidate_ids": native_candidate_ids,
    }
    _write_json(work / "state.json", state)
    return state


def _offline_residual_ranking(
    rows: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    artifacts: Mapping[str, str],
) -> list[dict[str, Any]]:
    ranking: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate["id"])
        artifact = _read_json(Path(artifacts[candidate_id]))
        mode = str(candidate["mode"])
        edge = {
            (int(row["from"]), int(row["to"])): float(row["residual_seconds"])
            for row in artifact["edge_residuals"]
        }
        value = {
            (int(row["node"]), int(row["goal"])): float(row["residual_seconds"])
            for row in artifact["value_residuals"]
        }
        absolute_errors: list[float] = []
        baseline_errors: list[float] = []
        covered = 0
        bellman_errors: list[float] = []
        bellman_baseline_errors: list[float] = []
        bellman_covered = 0
        for row in rows:
            current = int(row["current"])
            selected = int(row["selected"])
            goal = int(row["goal"])
            observed_edge = float(row["duration"]) - float(row["travel_time"])
            edge_prediction = edge.get((current, selected))
            downstream = (
                0.0 if mode == "td" and selected == goal
                else value.get((selected, goal)) if mode == "td"
                else 0.0
            )
            runtime_supported = edge_prediction is not None and downstream is not None
            target = observed_edge + (downstream if downstream is not None else 0.0)
            prediction = (
                float(edge_prediction) + float(downstream)
                if runtime_supported
                else 0.0
            )
            baseline_errors.append(abs(target))
            absolute_errors.append(abs(target - prediction))
            if runtime_supported:
                covered += 1

            if mode == "td" and downstream is not None:
                current_value = value.get((current, goal))
                if current_value is not None:
                    bellman_target = (
                        float(row["duration"])
                        + float(row["static_potential_selected"])
                        + float(downstream)
                        - float(row["static_potential_current"])
                    )
                    bellman_covered += 1
                    bellman_errors.append(abs(float(current_value) - bellman_target))
                    bellman_baseline_errors.append(abs(bellman_target))
        result = {
                "candidate_id": candidate_id,
                "mode": mode,
                "coverage": covered / len(rows) if rows else 0.0,
                "runtime_lookup_coverage": covered / len(rows) if rows else 0.0,
                "mae_seconds_with_s4_fallback": (
                    statistics.fmean(absolute_errors) if absolute_errors else None
                ),
                "static_zero_residual_mae_seconds": (
                    statistics.fmean(baseline_errors) if baseline_errors else None
                ),
            }
        if mode == "td":
            result.update(
                td_bellman_coverage=(
                    bellman_covered / len(rows) if rows else 0.0
                ),
                td_bellman_mae_seconds=(
                    statistics.fmean(bellman_errors) if bellman_errors else None
                ),
                td_zero_value_mae_seconds=(
                    statistics.fmean(bellman_baseline_errors)
                    if bellman_baseline_errors
                    else None
                ),
            )
        ranking.append(result)
    ranking.sort(
        key=lambda row: (
            str(row["mode"]),
            -float(row.get("td_bellman_coverage", row["coverage"])),
            float(
                row.get(
                    "td_bellman_mae_seconds",
                    row["mae_seconds_with_s4_fallback"],
                )
            ),
            str(row["candidate_id"]),
        )
    )
    return ranking


def _prefix_rows(
    size: int, release_csv: Path
) -> tuple[route.RouteCase, list[dict[str, Any]]]:
    case = route.build_cases(prefixes=(size,), evidence_prefixes=(size,), scales=())[0]
    rows, _descriptor = route.load_case_input(case, root=ROOT)
    return case, _exact_release_rows(rows, release_csv)


def _run_complete(
    *,
    binary: Path,
    case_id: str,
    rows: Sequence[Mapping[str, Any]],
    artifact: Mapping[str, Any] | None,
    prefix_case: route.RouteCase | None = None,
    scale: int | None = None,
) -> dict[str, Any]:
    if (prefix_case is None) == (scale is None):
        raise DLPCampaignError("complete case must be exactly one prefix or scale")
    artifact_contract = _artifact_contract(artifact) if artifact is not None else None
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
        request.update(trace_limit=0, event_trace_limit=0, g4irsf20_event_hotpath_policy="E2")
    else:
        assert scale is not None
        request = hotpath.build_native_request(
            rows,
            scale=scale,
            policy="E2",
            binary=binary,
            root=ROOT,
            bounded_wall_seconds=60.0,
            check_events=65_536,
        )
        request.update(trace_limit=0, event_trace_limit=0)
    request["scenario"] = f"g4irsf24_{case_id}"
    if artifact is not None:
        request["g4irsf24_dlp_artifact"] = artifact
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    wall = time.perf_counter() - wall_started
    cpu = time.process_time() - cpu_started
    summary = payload.get("summary")
    bags = payload.get("bags")
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise DLPCampaignError("complete native case lacks summary or bags")
    safety = _strict_summary_safety(summary, len(rows))
    dlp = {
        key: summary.get(key, 0)
        for key in summary
        if str(key).startswith("g4irsf24_dlp_")
    }
    complete = (
        int(summary.get("completed_count", -1)) == len(rows)
        and int(summary.get("failed_count", -1)) == 0
        and len(bags) == len(rows)
        and all(bool(row.get("completed", False)) for row in bags if isinstance(row, Mapping))
    )
    if artifact_contract is None:
        if dlp:
            raise DLPCampaignError("S4 arm unexpectedly emitted active G24 DLP fields")
        artifact_echo = {
            "pass": True,
            "active": False,
            "native_echo_fields": [],
        }
    else:
        native_echo = {
            "mode": summary.get("g4irsf24_dlp_mode"),
            "edge_residual_count": summary.get(
                "g4irsf24_dlp_edge_residual_count"
            ),
            "value_residual_count": summary.get(
                "g4irsf24_dlp_value_residual_count"
            ),
        }
        artifact_echo_pass = (
            native_echo["mode"] == artifact_contract["mode"]
            and native_echo["edge_residual_count"]
            == artifact_contract["edge_residual_count"]
            and native_echo["value_residual_count"]
            == artifact_contract["value_residual_count"]
        )
        if not artifact_echo_pass:
            raise DLPCampaignError("native DLP artifact echo mismatch")
        artifact_echo = {
            "pass": True,
            "active": True,
            "artifact_contract": artifact_contract,
            "native_echo": native_echo,
            "native_echo_fields": [
                "mode",
                "edge_residual_count",
                "value_residual_count",
            ],
            "boundary": (
                "schema and scalar controls are validated in the immutable "
                "Python artifact contract; the native ABI echoes mode and row counts"
            ),
        }
    if complete:
        timing, raw = native_race.timing_distributions(rows, bags)
    else:
        timing, raw = {}, []
    return {
        "case": case_id,
        "status": "PASS" if complete and safety["pass"] else "FAILED_ARM",
        "segments": len(rows),
        "raw_bags": len(raw),
        "timing": timing,
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "event_count": int(summary.get("event_count", 0)),
        "events_per_completed": (
            int(summary.get("event_count", 0)) / len(rows) if complete else None
        ),
        "deadline_miss_count": sum(
            1
            for row in bags
            if isinstance(row, Mapping)
            and row.get("completed") is True
            and isinstance(row.get("deadline"), (int, float))
            and float(row["deadline"]) >= 0.0
            and float(row.get("finish_time", -1.0)) > float(row["deadline"])
        ),
        "events_per_wall_second": int(summary.get("event_count", 0)) / wall,
        "safety": safety,
        "dlp": dlp,
        "artifact_echo": artifact_echo,
    }


def screen(
    *, binary: Path, work: Path, release_csv: Path,
    output: Path = DEFAULT_SCREEN
) -> dict[str, Any]:
    state = _read_json(work / "state.json")
    if (
        state.get("schema") != SCHEMA
        or state.get("stage") != "COLLECTED_AND_FIT"
    ):
        raise DLPCampaignError("collection state schema/stage mismatch")
    _require_campaign_binding(
        state,
        binary=binary,
        work=work,
        release_csv=release_csv,
        label="collection state",
    )
    native_ids = _candidate_ids(
        state.get("native_candidate_ids", []), label="offline native candidate ids"
    )
    artifact_paths = state.get("artifacts")
    if not isinstance(artifact_paths, Mapping):
        raise DLPCampaignError("collection state lacks artifact paths")
    if not set(native_ids).issubset(artifact_paths):
        raise DLPCampaignError("offline native candidate is absent from artifacts")
    artifacts = {
        name: _read_json(_stored_path(str(artifact_paths[name])))
        for name in native_ids
    }
    runs: list[dict[str, Any]] = []
    for size in (144, 512):
        case, rows = _prefix_rows(size, release_csv)
        for candidate_id, artifact in (("S4", None), *artifacts.items()):
            row = _run_complete(
                binary=binary,
                case_id=f"screen_{size}_{candidate_id}",
                rows=rows,
                artifact=artifact,
                prefix_case=case,
            )
            row["candidate_id"] = candidate_id
            row["size"] = size
            runs.append(row)
    by_key = {(int(row["size"]), str(row["candidate_id"])): row for row in runs}
    ranking: list[dict[str, Any]] = []
    for candidate_id in artifacts:
        candidate_runs = [by_key[(size, candidate_id)] for size in (144, 512)]
        baselines = [by_key[(size, "S4")] for size in (144, 512)]
        valid = all(
            candidate["status"] == "PASS" and baseline["status"] == "PASS"
            for candidate, baseline in zip(candidate_runs, baselines)
        )
        deltas = (
            [
                (candidate["timing"]["processed_attempt"]["mean_seconds"] - baseline["timing"]["processed_attempt"]["mean_seconds"])
                / baseline["timing"]["processed_attempt"]["mean_seconds"]
                for candidate, baseline in zip(candidate_runs, baselines)
            ]
            if valid
            else []
        )
        mutation_count = sum(
            int(run["dlp"].get("g4irsf24_dlp_committed_mutation_count", 0))
            for run in candidate_runs
        )
        ranking.append(
            {
                "candidate_id": candidate_id,
                "mean_relative_delta": statistics.fmean(deltas) if deltas else None,
                "committed_mutation_count": mutation_count,
                "safety_pass": valid and all(run["safety"]["pass"] for run in candidate_runs),
            }
        )
    ranking.sort(
        key=lambda row: (
            not bool(row["safety_pass"]),
            int(row["committed_mutation_count"]) == 0,
            float(row["mean_relative_delta"]) if row["mean_relative_delta"] is not None else 1.0e9,
            str(row["candidate_id"]),
        )
    )
    selected = [
        str(row["candidate_id"])
        for row in ranking
        if row["safety_pass"] and int(row["committed_mutation_count"]) > 0
    ][:2]
    payload = {
        "schema": SCHEMA,
        "stage": "SCREEN",
        **_campaign_binding(binary=binary, work=work, release_csv=release_csv),
        "runs": runs,
        "ranking": ranking,
        "selected_candidate_ids": selected,
    }
    _write_json(output, payload)
    return payload


def evaluate(
    *, binary: Path, work: Path, release_csv: Path,
    screen_path: Path = DEFAULT_SCREEN, output: Path = DEFAULT_LADDER,
    s4_already_beats_fresh_hca: bool = False,
) -> dict[str, Any]:
    state = _read_json(work / "state.json")
    screening = _read_json(screen_path)
    if (
        state.get("schema") != SCHEMA
        or state.get("stage") != "COLLECTED_AND_FIT"
        or screening.get("schema") != SCHEMA
        or screening.get("stage") != "SCREEN"
    ):
        raise DLPCampaignError("state/screen schema or stage mismatch")
    _require_campaign_binding(
        state,
        binary=binary,
        work=work,
        release_csv=release_csv,
        label="collection state",
    )
    _require_campaign_binding(
        screening,
        binary=binary,
        work=work,
        release_csv=release_csv,
        label="screen",
    )
    offline_ids = _candidate_ids(
        state.get("native_candidate_ids", []), label="offline native candidate ids"
    )
    selected = _candidate_ids(
        screening.get("selected_candidate_ids"), label="screen selected candidate ids"
    )
    if not set(selected).issubset(offline_ids):
        raise DLPCampaignError(
            "screen selected candidate is not an offline native candidate"
        )
    artifact_paths = state.get("artifacts")
    if not isinstance(artifact_paths, Mapping) or not set(selected).issubset(
        artifact_paths
    ):
        raise DLPCampaignError("screen selected candidate lacks a fitted artifact")
    artifacts = {
        name: _read_json(_stored_path(str(artifact_paths[name]))) for name in selected
    }
    runs: list[dict[str, Any]] = []
    orders = {1: ["S4", *selected], 2: [*reversed(selected), "S4"]}
    for scale in (1, 2):
        rows, _descriptor = capacity.load_g18_scale_input(scale, ROOT)
        if scale == 1:
            rows = _exact_release_rows(rows, release_csv)
        for candidate_id in orders[scale]:
            run = _run_complete(
                binary=binary,
                case_id=f"ladder_{scale}x_{candidate_id}",
                rows=rows,
                artifact=artifacts.get(candidate_id),
                scale=scale,
            )
            run["candidate_id"] = candidate_id
            run["scale"] = scale
            runs.append(run)
    by_key = {(int(row["scale"]), str(row["candidate_id"])): row for row in runs}
    decisions: list[dict[str, Any]] = []
    for candidate_id in selected:
        rows = [by_key[(scale, candidate_id)] for scale in (1, 2)]
        baselines = [by_key[(scale, "S4")] for scale in (1, 2)]
        valid = all(
            row["status"] == "PASS" and baseline["status"] == "PASS"
            for row, baseline in zip(rows, baselines)
        )
        mean_deltas = (
            [
                row["timing"]["processed_attempt"]["mean_seconds"]
                - baseline["timing"]["processed_attempt"]["mean_seconds"]
                for row, baseline in zip(rows, baselines)
            ]
            if valid
            else [None, None]
        )
        p95_deltas = (
            [
                row["timing"]["processed_attempt"]["p95_seconds"]
                - baseline["timing"]["processed_attempt"]["p95_seconds"]
                for row, baseline in zip(rows, baselines)
            ]
            if valid
            else [None, None]
        )
        tail_deltas = (
            [
                row["timing"]["processed_attempt"]["p99_seconds"]
                - baseline["timing"]["processed_attempt"]["p99_seconds"]
                for row, baseline in zip(rows, baselines)
            ]
            if valid
            else [None, None]
        )
        mutations = sum(
            int(row["dlp"].get("g4irsf24_dlp_committed_mutation_count", 0))
            for row in rows
        )
        mutation_by_scale = [
            int(row["dlp"].get("g4irsf24_dlp_committed_mutation_count", 0))
            for row in rows
        ]
        baseline_means = [
            baseline["timing"]["processed_attempt"]["mean_seconds"]
            for baseline in baselines
        ] if valid else [0.0, 0.0]
        mean_improvements = [
            -float(value) if value is not None else -1.0e9
            for value in mean_deltas
        ]
        event_increases = [
            row["events_per_completed"] / baseline["events_per_completed"] - 1.0
            for row, baseline in zip(rows, baselines)
        ] if valid else [1.0e9, 1.0e9]
        positive_baselines = valid and all(float(value) > 0.0 for value in baseline_means)
        one_x_standard_gain = positive_baselines and (
            mean_improvements[0] / baseline_means[0] >= 0.01
            or mean_improvements[0] >= 2.0
        )
        one_x_regression_tolerance = (
            max(2.0, 0.01 * float(baseline_means[0]))
            if positive_baselines
            else 0.0
        )
        one_x_hca_route_nonregression = (
            bool(s4_already_beats_fresh_hca)
            and positive_baselines
            and float(mean_deltas[0]) <= one_x_regression_tolerance
        )
        one_x_business_route = (
            one_x_standard_gain or one_x_hca_route_nonregression
        )
        gates = {
            "all_runs_complete_and_safe": valid and all(row["safety"]["pass"] for row in rows),
            "one_x_real_mutations_at_least_20": mutation_by_scale[0] >= 20,
            "two_x_real_mutations_at_least_20": mutation_by_scale[1] >= 20,
            "one_x_business_route_pass": one_x_business_route,
            "one_x_mean_improves_1pct_or_2s": one_x_standard_gain,
            "one_x_hca_winner_mean_nonobvious_regression": (
                one_x_hca_route_nonregression
            ),
            "one_x_p95_nonregression_0p1pct": (
                valid and float(p95_deltas[0]) <= 0.001 * baselines[0]["timing"]["processed_attempt"]["p95_seconds"]
            ),
            "one_x_p99_nonregression_0p1pct": (
                valid and float(tail_deltas[0]) <= 0.001 * baselines[0]["timing"]["processed_attempt"]["p99_seconds"]
            ),
            "one_x_events_per_completed_increase_at_most_3pct": event_increases[0] <= 0.03,
            "two_x_mean_improves_2pct_or_5s": (
                positive_baselines and (
                    mean_improvements[1] / baseline_means[1] >= 0.02
                    or mean_improvements[1] >= 5.0
                )
            ),
            "two_x_p95_nonregression": valid and float(p95_deltas[1]) <= 0.0,
            "two_x_p99_nonregression": valid and float(tail_deltas[1]) <= 0.0,
            "two_x_events_per_completed_increase_at_most_5pct": event_increases[1] <= 0.05,
            "deadline_miss_no_regression": valid and all(
                row["deadline_miss_count"] <= baseline["deadline_miss_count"]
                for row, baseline in zip(rows, baselines)
            ),
        }
        required_gate_names = (
            "all_runs_complete_and_safe",
            "one_x_real_mutations_at_least_20",
            "two_x_real_mutations_at_least_20",
            "one_x_business_route_pass",
            "one_x_p95_nonregression_0p1pct",
            "one_x_p99_nonregression_0p1pct",
            "one_x_events_per_completed_increase_at_most_3pct",
            "two_x_mean_improves_2pct_or_5s",
            "two_x_p95_nonregression",
            "two_x_p99_nonregression",
            "two_x_events_per_completed_increase_at_most_5pct",
            "deadline_miss_no_regression",
        )
        eligible = all(bool(gates[name]) for name in required_gate_names)
        one_x_business_route_name = (
            "STANDARD_1X_GAIN"
            if one_x_standard_gain
            else (
                "S4_ALREADY_BEATS_FRESH_HCA_1X_HOLD"
                if one_x_hca_route_nonregression
                else None
            )
        )
        promotion_route = one_x_business_route_name if eligible else None
        decisions.append(
            {
                "candidate_id": candidate_id,
                "eligible": eligible,
                "promotion_route": promotion_route,
                "one_x_business_route": one_x_business_route_name,
                "s4_already_beats_fresh_hca": bool(
                    s4_already_beats_fresh_hca
                ),
                "one_x_mean_regression_tolerance_seconds": (
                    one_x_regression_tolerance
                ),
                "mean_delta_seconds": mean_deltas,
                "p95_delta_seconds": p95_deltas,
                "p99_delta_seconds": tail_deltas,
                "committed_mutation_count": mutations,
                "mutation_count_by_scale": mutation_by_scale,
                "events_per_completed_relative_increase": event_increases,
                "gates": gates,
                "required_gate_names": list(required_gate_names),
                "objective": (
                    statistics.fmean(float(value) for value in mean_deltas)
                    if valid
                    else 1.0e9
                ),
            }
        )
    eligible = sorted(
        (row for row in decisions if row["eligible"]),
        key=lambda row: (float(row["objective"]), str(row["candidate_id"])),
    )
    winner = str(eligible[0]["candidate_id"]) if eligible else None
    payload = {
        "schema": SCHEMA,
        "stage": "NATIVE_1X_2X",
        **_campaign_binding(binary=binary, work=work, release_csv=release_csv),
        "runs": runs,
        "decisions": decisions,
        "winner_candidate_id": winner,
        "active_policy": winner or "S4",
        "status": "GO" if winner else "NO_GO_KEEP_S4",
        "dlp_ladder_status": (
            "DLP_LADDER_GO" if winner else "DLP_LADDER_NO_GO_KEEP_S4"
        ),
        "decision_scope": "DLP_VS_S4_ONLY",
        "fresh_hca_project_conclusion": "NOT_EVALUATED_BY_DLP_LADDER",
        "s4_already_beats_fresh_hca": bool(s4_already_beats_fresh_hca),
    }
    _write_json(output, payload)
    return payload


def _publish_final_selection(
    *,
    candidate_id: str | None,
    artifact: Mapping[str, Any] | None,
    scale_status: str,
    reason: str,
    policy_output: Path,
    selection_output: Path,
) -> dict[str, Any]:
    """Publish one authoritative selection and prevent a stale DLP policy."""

    stale_policy_removed = False
    if candidate_id is None:
        if policy_output.exists():
            policy_output.unlink()
            stale_policy_removed = True
        policy_path: str | None = None
    else:
        if artifact is None:
            raise DLPCampaignError("selected DLP candidate lacks its artifact")
        _write_json(policy_output, artifact)
        policy_path = str(policy_output)
    selection = {
        "schema": "czr005.g4irsf24.dlp_selection.v1",
        "active_policy": candidate_id or "S4",
        "selected_candidate_id": candidate_id,
        "policy_artifact_path": policy_path,
        "scale_status": scale_status,
        "reason": reason,
        "stale_policy_removed": stale_policy_removed,
    }
    _write_json(selection_output, selection)
    return selection


def scale_abba(
    *,
    binary: Path,
    work: Path,
    ladder_path: Path = DEFAULT_LADDER,
    output: Path = DEFAULT_SCALE,
    bounded_wall_seconds: float = 60.0,
    policy_output: Path = DEFAULT_POLICY,
    selection_output: Path = DEFAULT_SELECTION,
) -> dict[str, Any]:
    state = _read_json(work / "state.json")
    ladder = _read_json(ladder_path)
    if (
        state.get("schema") != SCHEMA
        or state.get("stage") != "COLLECTED_AND_FIT"
        or ladder.get("schema") != SCHEMA
        or ladder.get("stage") != "NATIVE_1X_2X"
    ):
        raise DLPCampaignError("state/ladder schema or stage mismatch")
    expected_runtime_binding = {
        "binary": _portable_path(binary),
        "work": _portable_path(work),
    }
    runtime_mismatches = [
        name
        for name, expected in expected_runtime_binding.items()
        if state.get(name) != expected
    ]
    release_binding = state.get("exact_1x_release_csv")
    if runtime_mismatches or not isinstance(release_binding, str) or not release_binding:
        mismatches = runtime_mismatches or ["exact_1x_release_csv"]
        raise DLPCampaignError(
            f"state scale binding mismatch: {', '.join(mismatches)}"
        )
    ladder_mismatches = [
        name
        for name in ("binary", "work", "exact_1x_release_csv")
        if ladder.get(name) != state.get(name)
    ]
    if ladder_mismatches:
        raise DLPCampaignError(
            f"state/ladder campaign binding mismatch: {', '.join(ladder_mismatches)}"
        )

    ladder_status = ladder.get("status")
    winner = ladder.get("winner_candidate_id")
    if ladder_status not in {"GO", "NO_GO_KEEP_S4"}:
        raise DLPCampaignError("1x/2x ladder has an unknown decision status")
    if (ladder_status == "GO") != isinstance(winner, str):
        raise DLPCampaignError("1x/2x ladder status and winner disagree")
    if not isinstance(winner, str):
        selection = _publish_final_selection(
            candidate_id=None,
            artifact=None,
            scale_status="NO_EXTEND",
            reason="NO_1X_2X_WINNER",
            policy_output=policy_output,
            selection_output=selection_output,
        )
        payload = {
            "schema": SCHEMA,
            "stage": "4X_ABBA",
            "status": "NO_EXTEND",
            "reason": "NO_1X_2X_WINNER",
            "active_policy": "S4",
            "runs": [],
            "selection": selection,
        }
        _write_json(output, payload)
        return payload
    artifact_paths = state.get("artifacts")
    if not isinstance(artifact_paths, Mapping) or winner not in artifact_paths:
        raise DLPCampaignError("1x/2x winner is absent from collection artifacts")
    artifact = _read_json(_stored_path(str(artifact_paths[winner])))
    rows, descriptor = capacity.load_g18_scale_input(4, ROOT)
    runs: list[dict[str, Any]] = []
    for ordinal, arm in enumerate(("S4", winner, winner, "S4")):
        request = hotpath.build_native_request(
            rows,
            scale=4,
            policy="E2",
            binary=binary,
            root=ROOT,
            bounded_wall_seconds=bounded_wall_seconds,
            check_events=65_536,
        )
        request["scenario"] = f"g4irsf24_4x_abba_{ordinal}_{arm}"
        if arm != "S4":
            request["g4irsf24_dlp_artifact"] = artifact
        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        native = cpp_backend.g4irsf11_event_runtime_from_records(**request)
        cpu = time.process_time() - cpu_started
        wall = time.perf_counter() - wall_started
        result, _semantic = hotpath._bounded_result(
            native,
            rows=rows,
            descriptor=descriptor,
            policy="E2",
            wall_seconds=wall,
            cpu_seconds=cpu,
            bounded_wall_seconds=bounded_wall_seconds,
            check_events=65_536,
        )
        summary = native.get("summary", {})
        result["arm"] = arm
        result["ordinal"] = ordinal
        result["dlp"] = (
            {
                key: summary.get(key, 0)
                for key in summary
                if str(key).startswith("g4irsf24_dlp_")
            }
            if isinstance(summary, Mapping)
            else {}
        )
        runs.append(result)

    def finite(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    def median_value(
        arm_rows: Sequence[Mapping[str, Any]], section: str, name: str
    ) -> float | None:
        values: list[float] = []
        for row in arm_rows:
            source = row.get(section)
            value = finite(source.get(name)) if isinstance(source, Mapping) else None
            if value is None:
                return None
            values.append(value)
        return float(statistics.median(values)) if values else None

    acceptable_statuses = {"BOUNDED_PROGRESS", "COMPLETE"}
    run_checks: list[dict[str, Any]] = []
    for run in runs:
        arm = str(run["arm"])
        progress = run.get("progress")
        safety = run.get("hard_safety")
        dlp = run.get("dlp")
        mutation_count = (
            int(dlp.get("g4irsf24_dlp_committed_mutation_count", 0))
            if isinstance(dlp, Mapping)
            else 0
        )
        dlp_echo = arm == "S4" or (
            isinstance(dlp, Mapping)
            and dlp.get("g4irsf24_dlp_mode") == artifact.get("mode")
            and int(dlp.get("g4irsf24_dlp_edge_residual_count", -1))
            == len(artifact.get("edge_residuals", []))
            and int(dlp.get("g4irsf24_dlp_value_residual_count", -1))
            == len(artifact.get("value_residuals", []))
        )
        check = {
            "ordinal": int(run["ordinal"]),
            "arm": arm,
            "status_ok": str(run.get("status")) in acceptable_statuses,
            "safety_pass": isinstance(safety, Mapping) and safety.get("pass") is True,
            "failed_bags_zero": (
                isinstance(progress, Mapping)
                and int(progress.get("failed_bags", -1)) == 0
            ),
            "dlp_echo_ok": dlp_echo,
            "committed_mutation_count": mutation_count,
            "candidate_mutation_positive": arm == "S4" or mutation_count > 0,
        }
        check["pass"] = all(
            bool(check[name])
            for name in (
                "status_ok",
                "safety_pass",
                "failed_bags_zero",
                "dlp_echo_ok",
                "candidate_mutation_positive",
            )
        )
        run_checks.append(check)

    by_arm = {
        arm: [row for row in runs if row["arm"] == arm]
        for arm in ("S4", winner)
    }
    median_fields = {
        "completed_bags": ("progress", "completed_bags"),
        "released_bags": ("progress", "released_bags"),
        "current_backlog": ("progress", "current_backlog"),
        "simulated_time": ("progress", "simulated_time"),
        "events_per_completed_bag": ("metrics", "events_per_completed_bag"),
        "events_per_wall_second": ("metrics", "events_per_wall_second"),
        "native_wall_seconds": ("resources", "native_wall_seconds"),
        "native_process_cpu_seconds": ("resources", "native_process_cpu_seconds"),
    }
    medians = {
        arm: {
            name: median_value(arm_rows, section, field)
            for name, (section, field) in median_fields.items()
        }
        for arm, arm_rows in by_arm.items()
    }

    baseline = medians["S4"]
    candidate = medians[winner]

    def higher_gain(name: str) -> float | None:
        before = baseline[name]
        after = candidate[name]
        if before is None or after is None or before <= 0.0:
            return None
        return after / before - 1.0

    def lower_gain(name: str) -> float | None:
        before = baseline[name]
        after = candidate[name]
        if before is None or after is None or before <= 0.0:
            return None
        return 1.0 - after / before

    improvements = {
        "completed_bags_gain_fraction": higher_gain("completed_bags"),
        "simulated_time_gain_fraction": higher_gain("simulated_time"),
        "current_backlog_reduction_fraction": lower_gain("current_backlog"),
        "events_per_completed_bag_reduction_fraction": lower_gain(
            "events_per_completed_bag"
        ),
    }
    comparison_available = all(value is not None for value in improvements.values())
    threshold_passes = {
        name: value is not None and value >= 0.10
        for name, value in improvements.items()
    }
    gates = {
        "four_abba_runs_present": len(runs) == 4,
        "two_runs_per_arm": all(len(rows_for_arm) == 2 for rows_for_arm in by_arm.values()),
        "all_four_status_safety_and_failure_checks_pass": all(
            bool(check["pass"]) for check in run_checks
        ),
        "comparison_metrics_available": comparison_available,
        "at_least_one_10pct_improvement": any(threshold_passes.values()),
    }
    extend = all(gates.values())
    status = "EXTEND_180S_PENDING" if extend else "NO_EXTEND"
    reason = "ABBA_10PCT_GATE_PASS_PENDING_180S" if extend else "ABBA_FINAL_GATE_FAILED"
    selection = _publish_final_selection(
        candidate_id=None,
        artifact=None,
        scale_status=status,
        reason=reason,
        policy_output=policy_output,
        selection_output=selection_output,
    )
    payload = {
        "schema": SCHEMA,
        "stage": "4X_ABBA",
        "status": status,
        "reason": reason,
        "candidate_id": winner,
        "winner": winner,
        "active_policy": selection["active_policy"],
        "runs": runs,
        "run_checks": run_checks,
        "medians": medians,
        "improvements": improvements,
        "threshold_passes": threshold_passes,
        "gates": gates,
        "selection": selection,
    }
    _write_json(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("collect", "screen", "evaluate", "scale", "all"))
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--release-csv", type=Path, required=True)
    parser.add_argument("--bounded-wall-seconds", type=float, default=60.0)
    parser.add_argument(
        "--s4-already-beats-fresh-hca",
        action="store_true",
        help=(
            "Allow the preregistered 1x non-obvious-regression route only after "
            "fresh HCA evidence has independently established that S4 wins"
        ),
    )
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    release_csv = args.release_csv.resolve(strict=True)
    work = args.work if args.work.is_absolute() else ROOT / args.work
    result: Mapping[str, Any] | None = None
    if args.phase in {"collect", "all"}:
        result = collect(binary=binary, work=work, release_csv=release_csv)
    if args.phase in {"screen", "all"}:
        result = screen(binary=binary, work=work, release_csv=release_csv)
    if args.phase in {"evaluate", "all"}:
        result = evaluate(
            binary=binary,
            work=work,
            release_csv=release_csv,
            s4_already_beats_fresh_hca=args.s4_already_beats_fresh_hca,
        )
    if args.phase in {"scale", "all"}:
        result = scale_abba(
            binary=binary,
            work=work,
            bounded_wall_seconds=args.bounded_wall_seconds,
        )
    print(json.dumps({"phase": args.phase, "status": result.get("status", result.get("stage")) if result else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

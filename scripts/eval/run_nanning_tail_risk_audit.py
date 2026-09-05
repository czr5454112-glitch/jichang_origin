#!/usr/bin/env python3
"""Audit the frozen Nanning 2x P0D0/P1D1 tail-risk contrast.

The archived random-robustness cells intentionally contain aggregate metrics,
not their 57,012 raw-bag outcomes.  ``audit`` therefore never invents bag or
node identities.  It produces the strongest seed-level diagnosis available
from those cells and emits an explicit unavailable row/figure until detailed
reruns exist.

``rerun-cell`` replays one frozen seed/arm with the same random-robustness
preparation code and protected binary.  It validates the replay against the
archived aggregate before retaining raw-bag detail.  A subsequent ``audit``
turns the validated details into worst-1%, worst-100, maximum-bag and OD/node
views.  This is an evidence path only; it changes no routing policy or tuning.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import run_cie_random_robustness as random_runner  # noqa: E402


SCHEMA = "czr005.nanning_2x_tail_risk_audit.v1"
DETAIL_SCHEMA = "czr005.nanning_2x_tail_risk_detail.v1"
FIXED_HORIZON = 98_259.0
MAP_NAME = "nanning"
LOAD_FACTOR = 2.0
ARMS = ("P0D0", "P1D1")
EXPECTED_SEEDS = random_runner.EXPECTED_PAIRED_SEEDS

DEFAULT_INPUT_ROOT = (
    ROOT / "outputs/runtime/cie_revision/random_robustness/nanning_2p00x"
)
DEFAULT_SUMMARY = ROOT / "outputs/tables/cie_random_robustness_summary.csv"
DEFAULT_DETAIL_ROOT = (
    ROOT / "outputs/runtime/cie_revision/nanning_2x_tail_audit/details"
)
DEFAULT_WORST_CSV = ROOT / "outputs/tables/nanning_2x_worst_bags.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/nanning_2x_tail_risk_audit.md"
DEFAULT_FIGURE = ROOT / "outputs/figures/nanning_2x_tail_od_node_heatmap.png"

REFERENCE_MEAN_DELTA = 2_555.10
REFERENCE_CI_LOW = 1_027.27
REFERENCE_CI_HIGH = 4_083.66
REFERENCE_WORSE_SEEDS = 9

WORST_FIELDS = (
    "schema",
    "evidence_status",
    "seed",
    "arm",
    "rank_in_cell",
    "in_worst_one_percent",
    "in_worst_100",
    "is_max_bag",
    "task_id",
    "original_start",
    "original_goal",
    "routing_class",
    "segment_count",
    "completed_segment_count",
    "admitted_segment_count",
    "raw_complete",
    "original_entry_time",
    "std",
    "first_release_time",
    "fully_admitted_time",
    "finish_time",
    "fixed_horizon_tardiness_lower_bound_seconds",
    "segment_source_queue_wait_sum_seconds",
    "segment_post_admission_observed_sum_seconds",
    "total_local_wait_sum_seconds",
    "junction_queue_wait_sum_seconds",
    "merge_grant_wait_sum_seconds",
    "edge_travel_sum_seconds",
    "node_service_sum_seconds",
    "loop_extra_sum_seconds",
    "unadmitted_segment_count",
    "incomplete_segment_count",
    "terminal_history_nodes",
    "failure_reasons",
    "decomposition_is_not_additive_raw_bag_latency",
)


class TailAuditError(RuntimeError):
    """Raised when evidence identity or the frozen contrast is inconsistent."""


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TailAuditError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise TailAuditError(f"{label} must be finite")
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TailAuditError(f"JSON root must be an object: {path}")
    return value


def _nested(root: Mapping[str, Any], *keys: str) -> Any:
    value: Any = root
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise TailAuditError(f"missing field: {'.'.join(keys)}")
        value = value[key]
    return value


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORST_FIELDS)
        writer.writeheader()
        for row in materialized:
            writer.writerow({field: row.get(field, "") for field in WORST_FIELDS})
    temporary.replace(path)


def load_archived_cells(input_root: Path) -> dict[tuple[int, str], dict[str, Any]]:
    """Load and validate the 20 frozen aggregate-only Nanning 2x cells."""

    cells: dict[tuple[int, str], dict[str, Any]] = {}
    resolved_root = input_root.resolve(strict=True)
    # This archive now also contains the complementary P1D0/P0D1 factorial
    # cells.  They are valid sibling evidence but outside this two-arm tail
    # audit, so select the two frozen arms by filename instead of treating
    # every same-directory JSON artifact as an input.
    for expected_arm in ARMS:
        for path in sorted(resolved_root.glob(f"*_{expected_arm}.json")):
            data = _json(path)
            if data.get("map") != MAP_NAME or float(data.get("load_factor", -1)) != 2.0:
                continue
            seed = int(data.get("seed", -1))
            arm = str(data.get("arm", ""))
            if seed not in EXPECTED_SEEDS or arm != expected_arm:
                raise TailAuditError(f"foreign seed/arm in {path}")
            key = (seed, arm)
            if key in cells:
                raise TailAuditError(f"duplicate archived cell: {key}")
            if data.get("status") != "COMPLETE":
                raise TailAuditError(f"archived cell is not COMPLETE: {path}")
            if _nested(data, "population", "raw_bag_count") != 57_012:
                raise TailAuditError(f"wrong raw-bag denominator: {path}")
            timing = _nested(data, "paper_subjects", "full_population_raw_bag_timing")
            if not isinstance(timing, Mapping) or timing.get("status") != (
                "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
            ):
                raise TailAuditError(f"2x THT protocol was changed: {path}")
            if timing.get("metrics_seconds") is not None:
                raise TailAuditError(f"2x survivor timing was retained: {path}")
            cells[key] = {"path": path, "data": data}
    expected = {(seed, arm) for seed in EXPECTED_SEEDS for arm in ARMS}
    if set(cells) != expected:
        missing = sorted(expected - set(cells))
        extra = sorted(set(cells) - expected)
        raise TailAuditError(f"archive is not the frozen 20-cell set: {missing=}, {extra=}")
    for seed in EXPECTED_SEEDS:
        left = cells[(seed, "P0D0")]["data"]
        right = cells[(seed, "P1D1")]["data"]
        for key in (
            "combined_realization_sha256",
            "randomized_arrival_schedule_sha256",
            "randomized_node_service_profile_sha256",
        ):
            if _nested(left, "perturbation", key) != _nested(
                right, "perturbation", key
            ):
                raise TailAuditError(f"paired perturbation mismatch: seed={seed}, {key}")
    return cells


def _cell_metric(data: Mapping[str, Any], metric: str) -> float:
    if metric == "max_tardiness":
        return _finite(
            _nested(
                data,
                "paper_subjects",
                "fixed_denominator_business",
                "tardiness_seconds",
                "fixed_horizon_all_population_lower_bound",
                "max",
            ),
            metric,
        )
    if metric == "completed_max_tardiness":
        return _finite(
            _nested(
                data,
                "paper_subjects",
                "fixed_denominator_business",
                "tardiness_seconds",
                "completed_population_only_diagnostic",
                "max",
            ),
            metric,
        )
    if metric == "completed":
        return _finite(
            _nested(
                data,
                "paper_subjects",
                "fixed_denominator_business",
                "completed_raw_bag_count",
            ),
            metric,
        )
    if metric == "max_wait":
        return _finite(_nested(data, "runtime", "native_summary", "max_individual_wait"), metric)
    raise AssertionError(metric)


def seed_rows(cells: Mapping[tuple[int, str], Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in EXPECTED_SEEDS:
        left = cells[(seed, "P0D0")]["data"]
        right = cells[(seed, "P1D1")]["data"]
        p0_max = _cell_metric(left, "max_tardiness")
        p1_max = _cell_metric(right, "max_tardiness")
        p0_wait = _cell_metric(left, "max_wait")
        p1_wait = _cell_metric(right, "max_wait")
        rows.append(
            {
                "seed": seed,
                "p0d0_max_tardiness": p0_max,
                "p1d1_max_tardiness": p1_max,
                "max_tardiness_delta": p1_max - p0_max,
                "p0d0_completed": int(_cell_metric(left, "completed")),
                "p1d1_completed": int(_cell_metric(right, "completed")),
                "p0d0_max_wait": p0_wait,
                "p1d1_max_wait": p1_wait,
                "max_wait_delta": p1_wait - p0_wait,
                "p0d0_max_is_completed_tail": math.isclose(
                    p0_max,
                    _cell_metric(left, "completed_max_tardiness"),
                    abs_tol=1.0e-7,
                ),
                "p1d1_max_is_completed_tail": math.isclose(
                    p1_max,
                    _cell_metric(right, "completed_max_tardiness"),
                    abs_tol=1.0e-7,
                ),
            }
        )
    return rows


def load_reference_summary(path: Path) -> dict[str, Any]:
    with path.resolve(strict=True).open("r", encoding="utf-8", newline="") as handle:
        candidates = [
            row
            for row in csv.DictReader(handle)
            if row.get("map") == MAP_NAME
            and math.isclose(float(row.get("load_factor", -1)), LOAD_FACTOR)
            and row.get("metric") == "tardiness_max_seconds"
        ]
    if len(candidates) != 1:
        raise TailAuditError("summary must contain one Nanning 2x max-tardiness row")
    row = candidates[0]
    observed = {
        "mean_delta": float(row["mean_delta_p1d1_minus_p0d0"]),
        "ci_low": float(row["bootstrap_ci_low"]),
        "ci_high": float(row["bootstrap_ci_high"]),
        # For a lower-is-better metric, the summary's loss count is P1D1 worse.
        "worse_seeds": int(row["seed_loss_count"]),
        "better_seeds": int(row["seed_win_count"]),
        "tie_seeds": int(row["seed_tie_count"]),
        "status": row["status"],
    }
    checks = {
        "mean_delta": math.isclose(
            observed["mean_delta"], REFERENCE_MEAN_DELTA, abs_tol=0.01
        ),
        "ci_low": math.isclose(observed["ci_low"], REFERENCE_CI_LOW, abs_tol=0.01),
        "ci_high": math.isclose(
            observed["ci_high"], REFERENCE_CI_HIGH, abs_tol=0.01
        ),
        "worse_seeds": observed["worse_seeds"] == REFERENCE_WORSE_SEEDS,
        "complete": observed["status"] == "COMPLETE_FROZEN_PAIRED_SEEDS",
    }
    if not all(checks.values()):
        raise TailAuditError(f"published aggregate reference drifted: {checks}")
    return observed


def archive_has_bag_evidence(data: Mapping[str, Any]) -> bool:
    bags = data.get("bags")
    return isinstance(bags, list) and bool(bags)


def _result_float(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    if value in (None, ""):
        return default
    return _finite(value, key)


def summarize_raw_bags(
    input_rows: Sequence[Mapping[str, Any]],
    result_rows: Sequence[Mapping[str, Any]],
    *,
    fixed_horizon: float = FIXED_HORIZON,
) -> list[dict[str, Any]]:
    """Return honest raw-bag tail detail from a completed native replay."""

    horizon = _finite(fixed_horizon, "fixed horizon")
    inputs_by_segment: dict[str, Mapping[str, Any]] = {}
    inputs_by_task: dict[int, list[Mapping[str, Any]]] = {}
    for row in input_rows:
        segment_id = str(row.get("segment_id", ""))
        if not segment_id or segment_id in inputs_by_segment:
            raise TailAuditError("input segment identities must be unique")
        inputs_by_segment[segment_id] = row
        inputs_by_task.setdefault(int(row["task_id"]), []).append(row)
    results_by_segment: dict[str, Mapping[str, Any]] = {}
    for row in result_rows:
        segment_id = str(row.get("segment_id", ""))
        if segment_id not in inputs_by_segment or segment_id in results_by_segment:
            raise TailAuditError("runtime segment identity is missing, duplicate, or foreign")
        results_by_segment[segment_id] = row
    if set(results_by_segment) != set(inputs_by_segment):
        raise TailAuditError("native replay did not return every protected segment")

    raw: list[dict[str, Any]] = []
    for task_id, inputs in sorted(inputs_by_task.items()):
        results = [results_by_segment[str(row["segment_id"])] for row in inputs]
        completed = [bool(row.get("completed", False)) for row in results]
        admissions = [
            _result_float(row, "admitted_time", -1.0) for row in results
        ]
        finishes = [_result_float(row, "finish_time", -1.0) for row in results]
        raw_complete = all(completed)
        fully_admitted = max(admissions) if all(value >= 0.0 for value in admissions) else None
        finish = max(finishes) if raw_complete else None
        std = min(_finite(row["std"], "STD") for row in inputs)
        endpoint = finish if finish is not None else horizon
        histories: list[int] = []
        for result in results:
            history = result.get("short_history", ())
            if isinstance(history, Sequence) and not isinstance(history, (str, bytes)):
                histories.extend(int(node) for node in history)
        failures = sorted(
            {
                str(result.get("failure_reason", ""))
                for result in results
                if str(result.get("failure_reason", ""))
            }
        )
        ebs = any(bool(row.get("early_bag_split", False)) for row in inputs)
        original_starts = {int(row.get("original_start", row["start"])) for row in inputs}
        original_goals = {int(row.get("original_goal", row["goal"])) for row in inputs}
        source_wait = 0.0
        post_admission = 0.0
        for result in results:
            release = _result_float(
                result, "release_time", _result_float(result, "arrival_time", 0.0)
            )
            admitted = _result_float(result, "admitted_time", -1.0)
            segment_finish = _result_float(result, "finish_time", -1.0)
            if admitted >= 0.0:
                source_wait += max(0.0, admitted - release)
                observed_finish = segment_finish if bool(result.get("completed")) else horizon
                post_admission += max(0.0, observed_finish - admitted)
            else:
                source_wait += max(0.0, horizon - release)
        raw.append(
            {
                "task_id": task_id,
                "original_start": min(original_starts),
                "original_goal": min(original_goals),
                "routing_class": "EBS_SPLIT" if ebs else "DIRECT",
                "segment_count": len(results),
                "completed_segment_count": sum(completed),
                "admitted_segment_count": sum(value >= 0.0 for value in admissions),
                "raw_complete": raw_complete,
                "original_entry_time": min(
                    _finite(
                        row.get("original_entry_time", row.get("pass_time")),
                        "original entry",
                    )
                    for row in inputs
                ),
                "std": std,
                "first_release_time": min(
                    _result_float(
                        row, "release_time", _result_float(row, "arrival_time", 0.0)
                    )
                    for row in results
                ),
                "fully_admitted_time": fully_admitted,
                "finish_time": finish,
                "fixed_horizon_tardiness_lower_bound_seconds": max(0.0, endpoint - std),
                "segment_source_queue_wait_sum_seconds": source_wait,
                "segment_post_admission_observed_sum_seconds": post_admission,
                "total_local_wait_sum_seconds": sum(
                    _result_float(row, "total_local_wait") for row in results
                ),
                "junction_queue_wait_sum_seconds": sum(
                    _result_float(row, "junction_queue_wait_seconds") for row in results
                ),
                "merge_grant_wait_sum_seconds": sum(
                    _result_float(row, "merge_grant_wait_seconds") for row in results
                ),
                "edge_travel_sum_seconds": sum(
                    _result_float(row, "edge_travel_time_seconds") for row in results
                ),
                "node_service_sum_seconds": sum(
                    _result_float(row, "node_service_time_seconds") for row in results
                ),
                "loop_extra_sum_seconds": sum(
                    _result_float(row, "loop_extra_time_seconds") for row in results
                ),
                "unadmitted_segment_count": sum(value < 0.0 for value in admissions),
                "incomplete_segment_count": len(results) - sum(completed),
                "terminal_history_nodes": ";".join(str(node) for node in histories),
                "failure_reasons": ";".join(failures),
                "decomposition_is_not_additive_raw_bag_latency": True,
            }
        )
    raw.sort(
        key=lambda row: (
            -float(row["fixed_horizon_tardiness_lower_bound_seconds"]),
            int(row["task_id"]),
        )
    )
    worst_one_percent = math.ceil(len(raw) * 0.01)
    for index, row in enumerate(raw, 1):
        row["rank_in_cell"] = index
        row["in_worst_one_percent"] = index <= worst_one_percent
        row["in_worst_100"] = index <= 100
        row["is_max_bag"] = index == 1
    return raw


def _detail_paths(detail_root: Path, seed: int, arm: str) -> tuple[Path, Path]:
    stem = f"{seed}_{arm}"
    return detail_root / f"{stem}.csv", detail_root / f"{stem}.meta.json"


def resolve_nanning_task_dir(
    requested: Path | None, archived: Mapping[str, Any]
) -> Path:
    """Resolve the exact archived workload bundle before an expensive replay."""

    if requested is None:
        canonical = Path(_nested(archived, "provenance", "workload_path"))
        if not canonical.is_absolute():
            canonical = ROOT / canonical
        canonical = canonical.resolve(strict=True)
    else:
        task_dir = requested if requested.is_absolute() else ROOT / requested
        canonical = (task_dir / "nanning_2x_canonical.jsonl").resolve(strict=True)
    expected_sha = str(_nested(archived, "provenance", "workload_sha256"))
    if _sha256(canonical) != expected_sha:
        raise TailAuditError(
            "Nanning 2x canonical workload differs from the archived cell"
        )
    task_dir = canonical.parent
    manifest = task_dir / "nanning_2x_manifest.json"
    if not manifest.is_file():
        raise TailAuditError(f"Nanning 2x workload manifest is missing: {manifest}")
    return task_dir


def _run_namespace(args: argparse.Namespace, archived: Mapping[str, Any]) -> argparse.Namespace:
    binary = Path(args.binary) if args.binary is not None else Path(
        _nested(archived, "provenance", "binary_path")
    )
    nanning_task_dir = resolve_nanning_task_dir(args.nanning_task_dir, archived)
    return argparse.Namespace(
        map=MAP_NAME,
        load_factor=LOAD_FACTOR,
        arm=args.arm,
        seed=args.seed,
        binary=binary,
        output=Path("unused-by-tail-audit.json"),
        revision_manifest=args.revision_manifest,
        canonical_workload=None,
        load_manifest=random_runner.activation.DEFAULT_LOAD_MANIFEST,
        nanning_task_dir=nanning_task_dir,
        nanning_map_profile=args.nanning_map_profile,
        nanning_hca_root=args.nanning_hca_root,
        map2_workload_1x=random_runner.factorial.g35.map2_native.DEFAULT_WORKLOAD_1X,
        map2_workload_2x=random_runner.factorial.g35.map2_native.DEFAULT_WORKLOAD_2X,
        map2_hca_case_root=None,
        dry_run=False,
        force=True,
    )


def _validate_replay(
    replay: Mapping[str, Any], archived: Mapping[str, Any], raw_rows: Sequence[Mapping[str, Any]]
) -> dict[str, bool]:
    replay_business = _nested(replay, "paper_subjects", "fixed_denominator_business")
    archive_business = _nested(archived, "paper_subjects", "fixed_denominator_business")
    replay_max = _nested(
        replay_business,
        "tardiness_seconds",
        "fixed_horizon_all_population_lower_bound",
        "max",
    )
    archive_max = _nested(
        archive_business,
        "tardiness_seconds",
        "fixed_horizon_all_population_lower_bound",
        "max",
    )
    detail_max = max(
        float(row["fixed_horizon_tardiness_lower_bound_seconds"]) for row in raw_rows
    )
    checks = {
        "status_complete": replay.get("status") == "COMPLETE",
        "binary_sha256": _nested(replay, "provenance", "binary_sha256")
        == _nested(archived, "provenance", "binary_sha256"),
        "workload_sha256": _nested(replay, "provenance", "workload_sha256")
        == _nested(archived, "provenance", "workload_sha256"),
        "combined_realization_sha256": _nested(
            replay, "perturbation", "combined_realization_sha256"
        )
        == _nested(archived, "perturbation", "combined_realization_sha256"),
        "completed_raw_bag_count": replay_business.get("completed_raw_bag_count")
        == archive_business.get("completed_raw_bag_count"),
        "max_tardiness": math.isclose(
            float(replay_max), float(archive_max), abs_tol=1.0e-7
        ),
        "detail_denominator": len(raw_rows) == 57_012,
        "detail_max": math.isclose(float(replay_max), detail_max, abs_tol=1.0e-7),
        "two_x_timing_na": _nested(
            replay, "paper_subjects", "full_population_raw_bag_timing", "status"
        )
        == "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
    }
    if not all(checks.values()):
        raise TailAuditError(f"detailed replay does not match archived cell: {checks}")
    return checks


def rerun_cell(args: argparse.Namespace) -> tuple[Path, Path]:
    cells = load_archived_cells(args.input_root)
    archived_entry = cells[(args.seed, args.arm)]
    archived = archived_entry["data"]
    namespace = _run_namespace(args, archived)
    captured: dict[str, Any] = {}

    def executor(**request: Any) -> Mapping[str, Any]:
        payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
        captured["payload"] = payload
        return payload

    replay = random_runner.execute_run(namespace, executor=executor)
    payload = captured.get("payload")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("bags"), list):
        raise TailAuditError("native replay did not expose per-segment bag outcomes")
    _case, workload, _request, _release, _prepared = (
        random_runner.prepare_randomized_cell(
            namespace, random_runner.load_random_contract(namespace.revision_manifest)
        )
    )
    raw_rows = summarize_raw_bags(workload.rows, payload["bags"])
    checks = _validate_replay(replay, archived, raw_rows)
    csv_path, meta_path = _detail_paths(args.detail_root, args.seed, args.arm)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = csv_path.with_suffix(".csv.tmp")
    detail_fields = tuple(raw_rows[0])
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        writer.writerows(raw_rows)
    temporary.replace(csv_path)
    metadata = {
        "schema": DETAIL_SCHEMA,
        "status": "VALIDATED_AGAINST_ARCHIVED_CELL",
        "map": MAP_NAME,
        "load_factor": LOAD_FACTOR,
        "seed": args.seed,
        "arm": args.arm,
        "archived_cell": str(archived_entry["path"]),
        "archived_cell_sha256": _sha256(archived_entry["path"]),
        "detail_csv": str(csv_path.resolve()),
        "detail_csv_sha256": _sha256(csv_path),
        "validation": checks,
        "trace_evidence": {
            "available": False,
            "first_p0d0_p1d1_divergence": "NOT_IDENTIFIED_NO_TRACE_REPLAY",
        },
        "policy_or_parameter_changed": False,
        "two_x_formal_tht": "N/A",
    }
    _write_text(meta_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return csv_path, meta_path


def load_validated_details(detail_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in EXPECTED_SEEDS:
        for arm in ARMS:
            csv_path, meta_path = _detail_paths(detail_root, seed, arm)
            if not csv_path.exists() and not meta_path.exists():
                continue
            if not csv_path.exists() or not meta_path.exists():
                raise TailAuditError(f"partial detail artifact for {seed}/{arm}")
            metadata = _json(meta_path)
            checks = metadata.get("validation")
            if metadata.get("status") != "VALIDATED_AGAINST_ARCHIVED_CELL" or not (
                isinstance(checks, Mapping) and all(checks.values())
            ):
                raise TailAuditError(f"unvalidated detail artifact: {meta_path}")
            if metadata.get("detail_csv_sha256") != _sha256(csv_path):
                raise TailAuditError(f"detail digest mismatch: {csv_path}")
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                cell_rows = list(csv.DictReader(handle))
            if len(cell_rows) != 57_012:
                raise TailAuditError(f"wrong detail denominator: {csv_path}")
            for row in cell_rows:
                if row.get("in_worst_one_percent") != "True":
                    continue
                rows.append(
                    {
                        "schema": SCHEMA,
                        "evidence_status": "VALIDATED_DETAILED_REPLAY",
                        "seed": seed,
                        "arm": arm,
                        **row,
                    }
                )
    return rows


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    numerator = math.fsum(
        (x - mean_left) * (y - mean_right) for x, y in zip(left, right)
    )
    denominator = math.sqrt(
        math.fsum((x - mean_left) ** 2 for x in left)
        * math.fsum((y - mean_right) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def _render_figure(path: Path, details: Sequence[Mapping[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    if not details:
        figure, axis = plt.subplots(figsize=(10, 5.5))
        axis.axis("off")
        axis.text(
            0.5,
            0.58,
            "Nanning 2x OD/node tail heatmap unavailable",
            ha="center",
            va="center",
            fontsize=16,
            weight="bold",
        )
        axis.text(
            0.5,
            0.40,
            "The 20 frozen cells retain aggregate metrics only.\n"
            "No bag ID, OD, terminal-node history, or decision trace is archived.\n"
            "Run the validated rerun-cell interface, then regenerate this audit.",
            ha="center",
            va="center",
            fontsize=11,
        )
        figure.tight_layout()
        figure.savefig(path, dpi=180)
        plt.close(figure)
        return

    starts = sorted({int(row["original_start"]) for row in details})
    goals = sorted({int(row["original_goal"]) for row in details})
    start_index = {value: index for index, value in enumerate(starts)}
    goal_index = {value: index for index, value in enumerate(goals)}
    od = np.zeros((len(starts), len(goals)), dtype=float)
    node_counts: dict[tuple[str, int], int] = {}
    for row in details:
        od[start_index[int(row["original_start"])], goal_index[int(row["original_goal"])]] += 1
        for token in str(row.get("terminal_history_nodes", "")).split(";"):
            if token:
                key = (str(row["arm"]), int(token))
                node_counts[key] = node_counts.get(key, 0) + 1
    top_nodes = sorted(
        {node for _arm, node in node_counts},
        key=lambda node: -sum(node_counts.get((arm, node), 0) for arm in ARMS),
    )[:30]
    figure, axes = plt.subplots(2, 1, figsize=(12, 9), constrained_layout=True)
    image = axes[0].imshow(od, aspect="auto", interpolation="nearest", cmap="magma")
    axes[0].set_title("Worst-1% raw-bag OD incidence (validated detailed reruns)")
    axes[0].set_xlabel("Original goal")
    axes[0].set_ylabel("Original start")
    axes[0].set_xticks(range(len(goals)), labels=goals, rotation=90, fontsize=6)
    axes[0].set_yticks(range(len(starts)), labels=starts, fontsize=6)
    figure.colorbar(image, ax=axes[0], label="bag-cell records")
    if top_nodes:
        node_matrix = np.array(
            [[node_counts.get((arm, node), 0) for node in top_nodes] for arm in ARMS],
            dtype=float,
        )
        node_image = axes[1].imshow(
            node_matrix, aspect="auto", interpolation="nearest", cmap="viridis"
        )
        axes[1].set_title("Terminal short-history node incidence")
        axes[1].set_yticks(range(len(ARMS)), labels=ARMS)
        axes[1].set_xticks(range(len(top_nodes)), labels=top_nodes, rotation=90)
        figure.colorbar(node_image, ax=axes[1], label="history occurrences")
    else:
        axes[1].axis("off")
        axes[1].text(
            0.5,
            0.5,
            "Validated bag outcomes contain no terminal short-history nodes.",
            ha="center",
            va="center",
        )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _detail_diagnosis(details: Sequence[Mapping[str, Any]]) -> list[str]:
    """Summarize only measurements present in validated per-bag reruns."""

    if not details:
        return [
            "Validated per-bag evidence is unavailable; no OD or wait-source "
            "classification is made."
        ]

    def truthy(value: Any) -> bool:
        return value is True or str(value).lower() == "true"

    maximum_rows = [row for row in details if truthy(row["is_max_bag"])]
    direct_maxima = sum(row["routing_class"] == "DIRECT" for row in maximum_rows)
    zero_source_maxima = sum(
        math.isclose(
            float(row["segment_source_queue_wait_sum_seconds"]),
            0.0,
            abs_tol=1.0e-9,
        )
        for row in maximum_rows
    )
    junction_shares = [
        float(row["junction_queue_wait_sum_seconds"])
        / float(row["total_local_wait_sum_seconds"])
        for row in maximum_rows
        if float(row["total_local_wait_sum_seconds"]) > 0.0
    ]
    merge_shares = [
        float(row["merge_grant_wait_sum_seconds"])
        / float(row["segment_post_admission_observed_sum_seconds"])
        for row in maximum_rows
        if float(row["segment_post_admission_observed_sum_seconds"]) > 0.0
    ]

    arm_fragments: list[str] = []
    for arm in ARMS:
        arm_rows = [row for row in details if row["arm"] == arm]
        od_counts = Counter(
            (int(row["original_start"]), int(row["original_goal"]))
            for row in arm_rows
        )
        top_five = sum(count for _od, count in od_counts.most_common(5))
        direct = sum(row["routing_class"] == "DIRECT" for row in arm_rows)
        complete = sum(truthy(row["raw_complete"]) for row in arm_rows)
        arm_fragments.append(
            f"{arm}: {len(od_counts)} ODs, top-five OD share "
            f"{100.0 * top_five / len(arm_rows):.1f}%, direct share "
            f"{100.0 * direct / len(arm_rows):.2f}%, completed share "
            f"{100.0 * complete / len(arm_rows):.1f}%"
        )

    return [
        f"All-population maximum bags are direct in {direct_maxima}/"
        f"{len(maximum_rows)} validated arm-seed cells, and source-queue wait is "
        f"zero in {zero_source_maxima}/{len(maximum_rows)}.",
        "For those maximum bags, junction-queue wait accounts for "
        f"{100.0 * min(junction_shares):.3f}%–"
        f"{100.0 * max(junction_shares):.3f}% of recorded local wait; merge-grant "
        f"wait is at most {100.0 * max(merge_shares):.3f}% of their observed "
        "post-admission interval.",
        "The worst-one-percent cohort is distributed rather than confined to one "
        "OD (" + "; ".join(arm_fragments) + ").",
        "Decision: `EXPECTED_CAPACITY_TRADEOFF_WITH_JUNCTION_WAIT_DOMINATED_TAIL`. "
        "`PRIORITY_STARVATION` and `ROUTE_OSCILLATION_OR_HOLD` remain "
        "`NOT_IDENTIFIED_NO_TRACE_REPLAY`; the per-bag result replay does not "
        "contain the first policy divergence or scorer decomposition.",
    ]


def _report(
    path: Path,
    *,
    seeds: Sequence[Mapping[str, Any]],
    reference: Mapping[str, Any],
    details: Sequence[Mapping[str, Any]],
    archived_has_bags: bool,
    figure_path: Path,
    worst_path: Path,
) -> None:
    deltas = [float(row["max_tardiness_delta"]) for row in seeds]
    wait_deltas = [float(row["max_wait_delta"]) for row in seeds]
    sign_match = sum(
        (delta > 0) == (wait > 0) and (delta < 0) == (wait < 0)
        for delta, wait in zip(deltas, wait_deltas)
    )
    correlation = _correlation(deltas, wait_deltas)
    completed_tail_cells = sum(
        bool(row[f"{arm.lower()}_max_is_completed_tail"])
        for row in seeds
        for arm in ARMS
    )
    detailed_cells = len({(row["seed"], row["arm"]) for row in details})
    evidence = (
        "VALIDATED_DETAILED_REPLAYS_PARTIAL_OR_COMPLETE"
        if details
        else "AGGREGATE_ONLY_DETAIL_RERUN_REQUIRED"
    )
    lines = [
        "# Nanning 2x tail-risk audit",
        "",
        f"Schema: `{SCHEMA}`  ",
        f"Evidence status: `{evidence}`  ",
        "Formal 2x full-population THT: `N/A` (unchanged protocol; no survivor timing).",
        "",
        "## Frozen paired result",
        "",
        f"P1D1 - P0D0 maximum tardiness is **+{reference['mean_delta']:.2f} s** "
        f"with paired-bootstrap 95% CI **[{reference['ci_low']:.2f}, "
        f"{reference['ci_high']:.2f}] s**. P1D1 is worse in "
        f"**{reference['worse_seeds']}/10** seeds, better in "
        f"{reference['better_seeds']}/10, and tied in {reference['tie_seeds']}/10.",
        "",
        "| Seed | P0D0 max tardiness (s) | P1D1 max tardiness (s) | Delta (s) | "
        "P0D0 completed | P1D1 completed | Max-wait delta (s) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in seeds:
        lines.append(
            f"| {row['seed']} | {_fmt(row['p0d0_max_tardiness'])} | "
            f"{_fmt(row['p1d1_max_tardiness'])} | "
            f"{_fmt(row['max_tardiness_delta'])} | {row['p0d0_completed']} | "
            f"{row['p1d1_completed']} | {_fmt(row['max_wait_delta'])} |"
        )
    corr_text = "N/A" if correlation is None else f"{correlation:.3f}"
    detail_diagnosis = _detail_diagnosis(details)
    lines.extend(
        [
            "",
            "## Strongest supported diagnosis",
            "",
            "- P1D1 completes more raw bags than P0D0 in all 10 seeds, yet its maximum "
            "tardiness is worse in 9. This is a genuine extreme-tail trade-off, not a "
            "claim of overall 2x timing improvement.",
            f"- The sign of the seed-level maximum-wait change matches the sign of the "
            f"maximum-tardiness change in {sign_match}/10 seeds; their Pearson correlation "
            f"is {corr_text}. This supports a congestion/wait-tail co-movement diagnosis at "
            "seed level, but does not prove that both maxima belong to the same bag.",
            f"- In {completed_tail_cells}/20 arm-seed cells, the all-population maximum "
            "equals the completed-population diagnostic maximum. Therefore the observed "
            "effect cannot be dismissed as only a fixed-horizon penalty on incomplete bags.",
            "- No new scorer, guard, mode, parameter, or routing rule was introduced by this "
            "audit.",
            "",
            "## Validated per-bag diagnosis",
            "",
            *[f"- {line}" for line in detail_diagnosis],
            "",
            "## Per-bag and trace identifiability",
            "",
            f"Archived cells contain bag evidence: `{archived_has_bags}`. The archived native "
            "summaries report `trace_limit=0`, `event_trace_limit=0`, "
            "`decision_trace_stored_count=0`, and `hold_trace_stored_count=0`. Consequently "
            "the original worst bag IDs, OD concentration, direct/EBS split, wait "
            "decomposition, and first P0D0/P1D1 decision divergence are not recoverable "
            "from the aggregate JSON alone.",
            "",
            f"Validated detailed rerun cells currently available: `{detailed_cells}/20`. "
            f"See `{worst_path.as_posix()}` and `{figure_path.as_posix()}`. When no validated "
            "detail exists, the CSV and figure carry explicit unavailable evidence rather "
            "than invented task or node identities.",
            "",
            "## Reproducible detail path",
            "",
            "Run one frozen cell (about the cost of the original cell), then rerun `audit`:",
            "",
            "```powershell",
            "python scripts/eval/run_nanning_tail_risk_audit.py rerun-cell "
            "--seed 104729 --arm P0D0",
            "python scripts/eval/run_nanning_tail_risk_audit.py rerun-cell "
            "--seed 104729 --arm P1D1",
            "python scripts/eval/run_nanning_tail_risk_audit.py audit",
            "```",
            "",
            "Each detailed cell is accepted only if binary SHA, workload SHA, paired "
            "realization SHA, completion count, fixed-horizon maximum tardiness, denominator, "
            "and 2x-THT-N/A contract all match its archived cell. The retained per-bag "
            "decomposition reports release/admission/completion and runtime wait components, "
            "but marks segment sums as non-additive across EBS legs.",
            "",
            "The first policy divergence remains `NOT_IDENTIFIED_NO_TRACE_REPLAY`; bag-result "
            "reruns do not masquerade as decision traces.",
        ]
    )
    _write_text(path, "\n".join(lines) + "\n")


def audit(args: argparse.Namespace) -> dict[str, Any]:
    cells = load_archived_cells(args.input_root)
    seeds = seed_rows(cells)
    reference = load_reference_summary(args.summary_csv)
    observed_mean = statistics.fmean(
        float(row["max_tardiness_delta"]) for row in seeds
    )
    observed_worse = sum(float(row["max_tardiness_delta"]) > 0.0 for row in seeds)
    if not math.isclose(observed_mean, reference["mean_delta"], abs_tol=1.0e-9):
        raise TailAuditError("seed cells and frozen paired summary disagree")
    if observed_worse != reference["worse_seeds"]:
        raise TailAuditError("seed-level worse count and frozen summary disagree")
    details = load_validated_details(args.detail_root)
    if details:
        _write_csv(args.worst_bags_csv, details)
    else:
        _write_csv(
            args.worst_bags_csv,
            [
                {
                    "schema": SCHEMA,
                    "evidence_status": (
                        "UNAVAILABLE_ARCHIVE_AGGREGATE_ONLY_REQUIRES_VALIDATED_RERUN"
                    ),
                    "decomposition_is_not_additive_raw_bag_latency": True,
                }
            ],
        )
    _render_figure(args.figure, details)
    has_bags = all(
        archive_has_bag_evidence(entry["data"]) for entry in cells.values()
    )
    _report(
        args.report,
        seeds=seeds,
        reference=reference,
        details=details,
        archived_has_bags=has_bags,
        figure_path=args.figure,
        worst_path=args.worst_bags_csv,
    )
    return {
        "schema": SCHEMA,
        "status": "COMPLETE_AGGREGATE_AUDIT"
        if not details
        else "COMPLETE_WITH_VALIDATED_DETAIL",
        "paired_seed_count": len(seeds),
        "validated_detail_cell_count": len(
            {(row["seed"], row["arm"]) for row in details}
        ),
        "mean_max_tardiness_delta_seconds": observed_mean,
        "worse_seed_count": observed_worse,
        "report": str(args.report.resolve()),
        "worst_bags_csv": str(args.worst_bags_csv.resolve()),
        "figure": str(args.figure.resolve()),
    }


def _common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument(
        "--revision-manifest", type=Path, default=random_runner.REVISION_MANIFEST
    )
    parser.add_argument("--detail-root", type=Path, default=DEFAULT_DETAIL_ROOT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    audit_parser = commands.add_parser("audit", help="audit archives/details")
    _common_paths(audit_parser)
    audit_parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY)
    audit_parser.add_argument("--worst-bags-csv", type=Path, default=DEFAULT_WORST_CSV)
    audit_parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    audit_parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)

    rerun = commands.add_parser("rerun-cell", help="retain one validated detail cell")
    _common_paths(rerun)
    rerun.add_argument("--seed", type=int, choices=EXPECTED_SEEDS, required=True)
    rerun.add_argument("--arm", choices=ARMS, required=True)
    rerun.add_argument("--binary", type=Path)
    rerun.add_argument(
        "--nanning-task-dir",
        type=Path,
        default=None,
        help=(
            "workload bundle override; by default use the exact canonical path "
            "recorded in the selected archived cell"
        ),
    )
    rerun.add_argument(
        "--nanning-map-profile",
        type=Path,
        default=random_runner.factorial.g35.nanning_native.DEFAULT_MAP_PROFILE,
    )
    rerun.add_argument(
        "--nanning-hca-root",
        type=Path,
        default=random_runner.factorial.g35.nanning_paired.DEFAULT_HCA_ROOT,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "rerun-cell":
        csv_path, meta_path = rerun_cell(args)
        result = {
            "status": "VALIDATED_AGAINST_ARCHIVED_CELL",
            "detail_csv": str(csv_path.resolve()),
            "metadata": str(meta_path.resolve()),
        }
    else:
        result = audit(args)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TailAuditError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Nanning tail-risk audit failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

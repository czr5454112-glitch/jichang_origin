#!/usr/bin/env python3
"""Run a minimal executable BOLT-P proposal/counterfactual path.

This runner deliberately keeps the parallel boundary outside the mutable
event runtime.  Independent proposal groups are evaluated in isolated
processes, then a coordinator consumes their results in canonical plan order.
For the native executor, each group calls G4IRSF15's exact same-state
checkpoint/clone counterfactual entry point.  The coordinator commits compact
evidence to its output; it does *not* claim to commit actions into one shared
simulator instance.

The built-in synthetic executor exists only to test scheduling, deterministic
aggregation, conflicts, stale snapshots, and worker failures without loading
the large native workload.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import multiprocessing
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    _text = str(_bootstrap)
    if _text not in sys.path:
        sys.path.insert(0, _text)

SCHEMA = "czr005.g4irsf19.bolt_p_execution.v1"
EXECUTION_BOUNDARY = (
    "PROCESS_ISOLATED_PURE_GROUP_EXECUTION_WITH_CANONICAL_EVIDENCE_AGGREGATION"
)
NATIVE_FUNCTION = "g4irsf15_run_causal_target_pairs_from_records"


class BoltPError(RuntimeError):
    """Raised when the small BOLT-P execution contract is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BoltPError(message)


def _plain(value: Any) -> Any:
    """Convert pybind/container values to JSON-compatible plain values."""

    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@dataclass(frozen=True)
class ProposalGroup:
    group_id: str
    order: int
    frontier: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    snapshot: tuple[tuple[str, int], ...]
    payload: dict[str, Any]

    @property
    def snapshot_map(self) -> dict[str, int]:
        return dict(self.snapshot)


def _normalize_keys(value: Any, *, field: str) -> tuple[str, ...]:
    _require(isinstance(value, list), f"{field}_MUST_BE_LIST")
    keys = tuple(str(item) for item in value)
    _require(all(keys), f"{field}_HAS_EMPTY_KEY")
    _require(len(set(keys)) == len(keys), f"{field}_HAS_DUPLICATES")
    return keys


def _group_from_mapping(value: Mapping[str, Any], index: int) -> ProposalGroup:
    group_id = value.get("group_id", f"group-{index:04d}")
    _require(isinstance(group_id, str) and group_id, "GROUP_ID_INVALID")
    order = value.get("order", index)
    _require(isinstance(order, int) and order >= 0, f"GROUP_ORDER_INVALID:{group_id}")
    frontier = value.get("frontier", "replica")
    _require(isinstance(frontier, str) and frontier, f"FRONTIER_INVALID:{group_id}")

    has_explicit_footprint = "reads" in value or "writes" in value
    if has_explicit_footprint:
        reads = _normalize_keys(value.get("reads", []), field="READS")
        writes = _normalize_keys(value.get("writes", []), field="WRITES")
    else:
        reads = ()
        writes = (f"aggregate:{group_id}",)

    snapshot_value = value.get("snapshot")
    if snapshot_value is None and not has_explicit_footprint:
        snapshot_value = {writes[0]: 0}
    _require(isinstance(snapshot_value, Mapping), f"SNAPSHOT_INVALID:{group_id}")
    snapshot: dict[str, int] = {}
    for key, version in snapshot_value.items():
        _require(
            isinstance(key, str)
            and bool(key)
            and isinstance(version, int)
            and version >= 0,
            f"SNAPSHOT_ENTRY_INVALID:{group_id}",
        )
        snapshot[key] = version
    missing = sorted((set(reads) | set(writes)) - set(snapshot))
    _require(not missing, f"SNAPSHOT_KEYS_MISSING:{group_id}:{missing}")

    payload = value.get("payload", {})
    _require(isinstance(payload, Mapping), f"PAYLOAD_INVALID:{group_id}")
    return ProposalGroup(
        group_id=group_id,
        order=order,
        frontier=frontier,
        reads=reads,
        writes=writes,
        snapshot=tuple(sorted(snapshot.items())),
        payload=dict(payload),
    )


def load_plan(
    path: Path, *, limit_groups: int | None = None
) -> tuple[list[ProposalGroup], dict[str, int], str]:
    """Load either a small BOLT-P plan or an existing G15 shard plan."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoltPError(f"PLAN_LOAD_FAILED:{path}:{type(exc).__name__}") from exc
    _require(isinstance(raw, dict), "PLAN_MUST_BE_OBJECT")

    source_kind: str
    group_values: list[Mapping[str, Any]]
    initial_versions: dict[str, int] = {}
    if isinstance(raw.get("groups"), list):
        source_kind = "G4IRSF19_BOLT_P_PLAN"
        group_values = raw["groups"]
        versions = raw.get("initial_versions", {})
        _require(isinstance(versions, Mapping), "INITIAL_VERSIONS_INVALID")
        for key, version in versions.items():
            _require(
                isinstance(key, str)
                and bool(key)
                and isinstance(version, int)
                and version >= 0,
                "INITIAL_VERSION_ENTRY_INVALID",
            )
            initial_versions[key] = version
    elif isinstance(raw.get("shards"), list):
        # G15 shards are independent deterministic replica replays.  Their
        # aggregate slots are disjoint by construction; the native targets are
        # passed through without reinterpreting the causal protocol.
        source_kind = "G4IRSF15_CAUSAL_SHARD_PLAN"
        group_values = []
        for position, shard in enumerate(raw["shards"]):
            _require(isinstance(shard, Mapping), "G15_SHARD_INVALID")
            shard_index = shard.get("shard_index", position)
            targets = shard.get("targets")
            _require(
                isinstance(shard_index, int) and isinstance(targets, list),
                f"G15_SHARD_FIELDS_INVALID:{position}",
            )
            group_id = f"g15-shard-{shard_index:04d}"
            key = f"aggregate:{group_id}"
            group_values.append(
                {
                    "group_id": group_id,
                    "order": shard_index,
                    "frontier": "independent-counterfactual-replicas",
                    "reads": [],
                    "writes": [key],
                    "snapshot": {key: 0},
                    "payload": {"targets": targets},
                }
            )
    else:
        raise BoltPError("PLAN_HAS_NEITHER_GROUPS_NOR_G15_SHARDS")

    if limit_groups is not None:
        _require(limit_groups > 0, "LIMIT_GROUPS_MUST_BE_POSITIVE")
        group_values = group_values[:limit_groups]
    _require(bool(group_values), "PLAN_HAS_NO_GROUPS")
    groups = [_group_from_mapping(value, i) for i, value in enumerate(group_values)]
    ids = [group.group_id for group in groups]
    _require(len(ids) == len(set(ids)), "GROUP_IDS_MUST_BE_UNIQUE")
    groups.sort(key=lambda group: (group.order, group.group_id))
    return groups, initial_versions, source_kind


_WORKER_KIND: str | None = None
_WORKER_NATIVE_ARGS: list[Any] | None = None
_WORKER_NATIVE_FUNCTION: Any = None


def _initialize_executor(
    executor_kind: str, root_text: str, binary_text: str | None
) -> None:
    global _WORKER_KIND, _WORKER_NATIVE_ARGS, _WORKER_NATIVE_FUNCTION

    _WORKER_KIND = executor_kind
    _WORKER_NATIVE_ARGS = None
    _WORKER_NATIVE_FUNCTION = None
    if executor_kind == "synthetic":
        return
    _require(executor_kind == "native-g15", f"UNKNOWN_EXECUTOR:{executor_kind}")
    _require(binary_text is not None, "NATIVE_BINARY_REQUIRED")
    root = Path(root_text).resolve()
    binary = Path(binary_text).resolve(strict=True)
    from scripts.eval import g4irsf15_causal_campaign as g15

    native_args, _, _ = g15._native_arguments(root)
    module = g15._load_exact_module(binary)
    function = getattr(module, NATIVE_FUNCTION, None)
    _require(callable(function), f"NATIVE_FUNCTION_MISSING:{NATIVE_FUNCTION}")
    _WORKER_NATIVE_ARGS = native_args
    _WORKER_NATIVE_FUNCTION = function


def _compact_native_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary_fields = (
        "schema",
        "evidence_scope",
        "input_request_count",
        "target_count",
        "action_changing_pair_count",
        "applied_action_changing_pair_count",
        "false_positive_pair_count",
        "complete_action_changing_h_bag_count",
        "applied_action_changing_h_system_count",
        "complete_h_system_hard_gate_pass_count",
    )
    compact = {field: _plain(payload.get(field)) for field in summary_fields}
    pair_fields = (
        "descriptor_id",
        "target_address_id",
        "kind",
        "event_ordinal",
        "horizon",
        "pair_status",
        "action_changed",
        "horizon_complete",
        "pair_complete",
        "live_safety_pass",
        "formal_hard_gate_pass",
        "hard_gate_fail_reasons",
        "committed_action_certificate",
    )
    pairs = payload.get("pairs", [])
    _require(isinstance(pairs, list), "NATIVE_PAIRS_MISSING")
    compact["pairs"] = [
        {field: _plain(pair.get(field)) for field in pair_fields}
        for pair in pairs
        if isinstance(pair, Mapping)
    ]
    return compact


def _execute_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if _WORKER_KIND == "synthetic":
        operation = payload.get("operation", "scale")
        if operation == "fail":
            raise BoltPError(str(payload.get("message", "SYNTHETIC_FAILURE")))
        delay_ms = payload.get("delay_ms", 0)
        _require(
            isinstance(delay_ms, (int, float)) and 0 <= delay_ms <= 10_000,
            "SYNTHETIC_DELAY_INVALID",
        )
        if delay_ms:
            time.sleep(float(delay_ms) / 1000.0)
        value = payload.get("value", 0)
        factor = payload.get("factor", 1)
        _require(
            isinstance(value, (int, float))
            and isinstance(factor, (int, float)),
            "SYNTHETIC_NUMERIC_INPUT_INVALID",
        )
        return {
            "operation": "scale",
            "value": value * factor,
            "tag": _plain(payload.get("tag")),
        }

    _require(_WORKER_KIND == "native-g15", "WORKER_NOT_INITIALIZED")
    _require(
        _WORKER_NATIVE_ARGS is not None and callable(_WORKER_NATIVE_FUNCTION),
        "NATIVE_WORKER_NOT_INITIALIZED",
    )
    targets = payload.get("targets")
    _require(isinstance(targets, list) and targets, "NATIVE_TARGETS_REQUIRED")
    result = _WORKER_NATIVE_FUNCTION(*_WORKER_NATIVE_ARGS, targets)
    _require(isinstance(result, Mapping), "NATIVE_RESULT_NOT_OBJECT")
    return _compact_native_payload(result)


def _worker_entry(group: ProposalGroup) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        proposal = _execute_payload(group.payload)
        return {
            "group_id": group.group_id,
            "worker_status": "PROPOSED",
            "proposal": proposal,
            "worker_pid": os.getpid(),
            "worker_seconds": time.perf_counter() - started,
        }
    except Exception as exc:  # worker failures are evidence, not fatal orchestration
        return {
            "group_id": group.group_id,
            "worker_status": "FAILED",
            "error": f"{type(exc).__name__}:{exc}",
            "worker_pid": os.getpid(),
            "worker_seconds": time.perf_counter() - started,
        }


def _compute(
    groups: Sequence[ProposalGroup],
    *,
    workers: int,
    executor_kind: str,
    root: Path,
    binary: Path | None,
) -> tuple[dict[str, dict[str, Any]], float]:
    _require(workers >= 1, "WORKERS_MUST_BE_POSITIVE")
    started = time.perf_counter()
    results: dict[str, dict[str, Any]] = {}
    binary_text = str(binary.resolve()) if binary is not None else None
    if workers == 1:
        _initialize_executor(executor_kind, str(root.resolve()), binary_text)
        for group in groups:
            results[group.group_id] = _worker_entry(group)
    else:
        # Spawn provides real process isolation on every platform and avoids
        # inheriting a loaded pybind runtime through fork.
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=context,
            initializer=_initialize_executor,
            initargs=(executor_kind, str(root.resolve()), binary_text),
        ) as pool:
            future_to_group = {
                pool.submit(_worker_entry, group): group for group in groups
            }
            for future in as_completed(future_to_group):
                group = future_to_group[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "group_id": group.group_id,
                        "worker_status": "FAILED",
                        "error": f"{type(exc).__name__}:{exc}",
                        "worker_pid": None,
                        "worker_seconds": 0.0,
                    }
                results[group.group_id] = result
    return results, time.perf_counter() - started


def _conflict_keys(
    group: ProposalGroup,
    prior: Sequence[ProposalGroup],
) -> list[str]:
    reads = set(group.reads)
    writes = set(group.writes)
    conflicts: set[str] = set()
    for earlier in prior:
        earlier_reads = set(earlier.reads)
        earlier_writes = set(earlier.writes)
        conflicts.update(writes & (earlier_reads | earlier_writes))
        conflicts.update(reads & earlier_writes)
    return sorted(conflicts)


def _aggregate(
    groups: Sequence[ProposalGroup],
    computed: Mapping[str, Mapping[str, Any]],
    initial_versions: Mapping[str, int],
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    versions = dict(initial_versions)
    rows: list[dict[str, Any]] = []
    committed_by_frontier: dict[str, list[ProposalGroup]] = {}
    proposal_count = 0
    committed_count = 0
    failure_count = 0
    stale_count = 0
    conflict_count = 0

    for group in groups:
        committed_in_frontier = committed_by_frontier.setdefault(
            group.frontier, []
        )
        worker = computed[group.group_id]
        row: dict[str, Any] = {
            "group_id": group.group_id,
            "order": group.order,
            "frontier": group.frontier,
            "reads": list(group.reads),
            "writes": list(group.writes),
            "worker_status": worker.get("worker_status"),
            "worker_pid": worker.get("worker_pid"),
            "worker_seconds": worker.get("worker_seconds"),
            "conflict_keys": [],
            "stale_keys": [],
        }
        if worker.get("worker_status") != "PROPOSED":
            row["aggregation_status"] = "WORKER_FAILED"
            row["error"] = worker.get("error", "UNKNOWN_WORKER_FAILURE")
            failure_count += 1
            rows.append(row)
            continue

        proposal_count += 1
        conflicts = _conflict_keys(group, committed_in_frontier)
        snapshot = group.snapshot_map
        stale = sorted(
            key
            for key in set(group.reads) | set(group.writes)
            if snapshot[key] != versions.get(key, 0)
        )
        row["conflict_keys"] = conflicts
        row["stale_keys"] = stale
        row["proposal"] = _plain(worker.get("proposal"))
        if conflicts or stale:
            row["aggregation_status"] = (
                "CONFLICT_STALE_REJECTED" if conflicts else "STALE_REJECTED"
            )
            if conflicts:
                conflict_count += 1
            if stale:
                stale_count += 1
            rows.append(row)
            continue

        # This is an evidence/plan commit only.  No mutable native runtime is
        # shared by workers or changed here.
        row["aggregation_status"] = "EVIDENCE_COMMITTED"
        for key in group.writes:
            versions[key] = versions.get(key, 0) + 1
        committed_in_frontier.append(group)
        committed_count += 1
        rows.append(row)

    aggregate_seconds = time.perf_counter() - started
    return (
        {
            "group_count": len(groups),
            "proposal_count": proposal_count,
            "evidence_commit_count": committed_count,
            "worker_failure_count": failure_count,
            "stale_rejection_count": stale_count,
            "conflict_rejection_count": conflict_count,
            "final_versions": dict(sorted(versions.items())),
            "groups": rows,
        },
        aggregate_seconds,
    )


def _semantic_projection(run: Mapping[str, Any]) -> dict[str, Any]:
    projected_rows: list[dict[str, Any]] = []
    for row in run["groups"]:
        projected_rows.append(
            {
                "group_id": row["group_id"],
                "order": row["order"],
                "frontier": row["frontier"],
                "worker_status": row["worker_status"],
                "aggregation_status": row["aggregation_status"],
                "conflict_keys": row["conflict_keys"],
                "stale_keys": row["stale_keys"],
                "error": row.get("error"),
                "proposal": row.get("proposal"),
            }
        )
    return {
        "proposal_count": run["proposal_count"],
        "evidence_commit_count": run["evidence_commit_count"],
        "worker_failure_count": run["worker_failure_count"],
        "stale_rejection_count": run["stale_rejection_count"],
        "conflict_rejection_count": run["conflict_rejection_count"],
        "final_versions": run["final_versions"],
        "groups": projected_rows,
    }


def _one_run(
    groups: Sequence[ProposalGroup],
    initial_versions: Mapping[str, int],
    *,
    workers: int,
    executor_kind: str,
    root: Path,
    binary: Path | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    computed, compute_seconds = _compute(
        groups,
        workers=workers,
        executor_kind=executor_kind,
        root=root,
        binary=binary,
    )
    aggregate, aggregate_seconds = _aggregate(groups, computed, initial_versions)
    aggregate.update(
        {
            "workers": workers,
            "compute_wall_seconds": compute_seconds,
            "aggregate_wall_seconds": aggregate_seconds,
            "total_wall_seconds": time.perf_counter() - started,
            "worker_process_count_observed": len(
                {
                    row["worker_pid"]
                    for row in aggregate["groups"]
                    if row.get("worker_pid") is not None
                }
            ),
        }
    )
    return aggregate


def run_campaign(
    groups: Sequence[ProposalGroup],
    initial_versions: Mapping[str, int],
    *,
    worker_counts: Sequence[int] = (1, 2, 4, 8),
    executor_kind: str = "synthetic",
    root: Path = ROOT,
    binary: Path | None = None,
    plan_source: str = "IN_MEMORY_PLAN",
) -> dict[str, Any]:
    counts = list(dict.fromkeys(worker_counts))
    _require(counts and all(count >= 1 for count in counts), "WORKER_COUNTS_INVALID")
    if 1 not in counts:
        counts.insert(0, 1)
    _require(executor_kind in {"synthetic", "native-g15"}, "EXECUTOR_INVALID")
    if executor_kind == "native-g15":
        _require(binary is not None and binary.is_file(), "NATIVE_BINARY_REQUIRED")

    serial = _one_run(
        groups,
        initial_versions,
        workers=1,
        executor_kind=executor_kind,
        root=root,
        binary=binary,
    )
    serial_replay = _one_run(
        groups,
        initial_versions,
        workers=1,
        executor_kind=executor_kind,
        root=root,
        binary=binary,
    )
    serial_projection = _semantic_projection(serial)
    p1_parity = serial_projection == _semantic_projection(serial_replay)
    serial["serial_parity_pass"] = p1_parity

    runs = [serial]
    for workers in counts:
        if workers == 1:
            continue
        run = _one_run(
            groups,
            initial_versions,
            workers=workers,
            executor_kind=executor_kind,
            root=root,
            binary=binary,
        )
        run["serial_parity_pass"] = (
            _semantic_projection(run) == serial_projection
        )
        runs.append(run)

    all_worker_runs = [serial, serial_replay, *runs[1:]]
    all_runs_worker_failure_free = all(
        run["worker_failure_count"] == 0 for run in all_worker_runs
    )
    all_parallel_runs_match_p1 = p1_parity and all(
        run["serial_parity_pass"] for run in runs
    )
    return {
        "schema": SCHEMA,
        "status": (
            "COMPLETE"
            if all_runs_worker_failure_free and all_parallel_runs_match_p1
            else "INCOMPLETE_OR_NONDETERMINISTIC"
        ),
        "execution_boundary": EXECUTION_BOUNDARY,
        "simulator_internal_parallel_commit": False,
        "commit_semantics": "CANONICAL_COMPACT_EVIDENCE_AGGREGATION_ONLY",
        "executor_kind": executor_kind,
        "plan_source": plan_source,
        "group_count": len(groups),
        "requested_worker_counts": counts,
        "p1_deterministic_parity_pass": p1_parity,
        "p1_replay_worker_failure_count": serial_replay[
            "worker_failure_count"
        ],
        "p1_replay_wall_seconds": serial_replay["total_wall_seconds"],
        "all_runs_worker_failure_free": all_runs_worker_failure_free,
        "all_parallel_runs_match_p1": all_parallel_runs_match_p1,
        "runs": runs,
        "claim_boundary": (
            "Workers execute independent pure proposal/counterfactual groups in "
            "separate processes. Results are aggregated in plan order. This is "
            "not parallel mutation or commit inside one event-runtime instance."
        ),
    }


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_outputs(
    report: Mapping[str, Any],
    *,
    json_path: Path,
    csv_path: Path,
    markdown_path: Path,
) -> None:
    _atomic_text(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )

    buffer = io.StringIO(newline="")
    fields = (
        "workers",
        "group_count",
        "proposal_count",
        "evidence_commit_count",
        "worker_failure_count",
        "stale_rejection_count",
        "conflict_rejection_count",
        "worker_process_count_observed",
        "compute_wall_seconds",
        "aggregate_wall_seconds",
        "total_wall_seconds",
        "serial_parity_pass",
    )
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for run in report["runs"]:
        writer.writerow({field: run[field] for field in fields})
    _atomic_text(csv_path, buffer.getvalue())

    lines = [
        "# G4IRSF19 minimal executable BOLT-P path",
        "",
        f"Status: **{report['status']}**.",
        "",
        report["claim_boundary"],
        "",
        f"P=1 deterministic replay parity: **{report['p1_deterministic_parity_pass']}**.",
        f"All requested process counts match P=1: **{report['all_parallel_runs_match_p1']}**.",
        "",
        "| P | groups | proposed | evidence commits | failures | stale | conflicts | worker processes | wall seconds | P=1 parity |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for run in report["runs"]:
        lines.append(
            "| {workers} | {group_count} | {proposal_count} | "
            "{evidence_commit_count} | {worker_failure_count} | "
            "{stale_rejection_count} | {conflict_rejection_count} | "
            "{worker_process_count_observed} | {total_wall_seconds:.6f} | "
            "{serial_parity_pass} |".format(**run)
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The native mode reuses G15's exact in-memory checkpoint/clone pair runner. "
            "Because checkpoints are not serialized, each worker deterministically replays "
            "the prefix for its independent group. Canonical aggregation is executable and "
            "measured; shared-runtime parallel discrete-event commit remains future work.",
            "",
        ]
    )
    _atomic_text(markdown_path, "\n".join(lines))


def _parse_workers(value: str) -> list[int]:
    try:
        counts = [int(token.strip()) for token in value.split(",") if token.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("workers must be comma-separated integers") from exc
    if not counts or any(count < 1 for count in counts):
        raise argparse.ArgumentTypeError("workers must be positive")
    return counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--executor", choices=("synthetic", "native-g15"), default="native-g15"
    )
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--workers", type=_parse_workers, default=[1, 2, 4, 8])
    parser.add_argument("--limit-groups", type=int)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("outputs/tables/g4irsf19_bolt_p.json"),
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=Path("outputs/tables/g4irsf19_bolt_p.csv"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("outputs/reports/g4irsf19_bolt_p.md"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    plan_path = args.plan if args.plan.is_absolute() else root / args.plan
    groups, initial_versions, plan_source = load_plan(
        plan_path, limit_groups=args.limit_groups
    )
    binary = args.binary
    if binary is not None and not binary.is_absolute():
        binary = root / binary
    report = run_campaign(
        groups,
        initial_versions,
        worker_counts=args.workers,
        executor_kind=args.executor,
        root=root,
        binary=binary,
        plan_source=plan_source,
    )

    def rooted(path: Path) -> Path:
        return path if path.is_absolute() else root / path

    write_outputs(
        report,
        json_path=rooted(args.json_output),
        csv_path=rooted(args.csv_output),
        markdown_path=rooted(args.markdown_output),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "group_count": report["group_count"],
                "p1_deterministic_parity_pass": report[
                    "p1_deterministic_parity_pass"
                ],
                "all_parallel_runs_match_p1": report[
                    "all_parallel_runs_match_p1"
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

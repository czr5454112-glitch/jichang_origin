from __future__ import annotations

"""Run an honest matched-system screen of local G2 merge rules.

This pilot compares the native E4 destination-merge rules M1--M6 on the
same protected input prefixes.  It is useful system evidence, but it is not
the G17 same-state causal intervention described in the mainline plan.  The
analysis can therefore shortlist a rule for a later causal pilot; it can
never authorize promotion by itself.

The runtime manipulation is deliberately narrow: every arm uses the frozen
G16/G14 E4 controls with the supervisor off, and only ``merge_grant_rule``
changes.  Opportunity telemetry is passive and is never an online feature.
"""

import argparse
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


SCHEMA_PLAN = "czr005.g4irsf17.g2_matched_pilot_plan.v1"
SCHEMA_RESULT = "czr005.g4irsf17.g2_matched_pilot_result.v1"
SCHEMA_RUN = "czr005.g4irsf17.g2_matched_pilot_run.v1"
SCHEMA_ANALYSIS = "czr005.g4irsf17.g2_matched_pilot_analysis.v1"

DEFAULT_SEGMENTS = (144, 512)
ALLOWED_SEGMENTS = (144, 512, 2_048, 8_192)
RULES = ("M1", "M2", "M3", "M4", "M5", "M6")
RULE_NAMES: Mapping[str, str] = {
    "M1": "fifo",
    "M2": "earliest_projected_arrival",
    "M3": "deadline_aging",
    "M4": "fairness_progress",
    "M5": "local_externality",
    "M6": "thesis_local",
}

DEFAULT_PLAN = ROOT / "artifacts/manifests/g4irsf17_g2_matched_pilot_plan.json"
DEFAULT_RESULTS_DIR = ROOT / "outputs/runtime/g4irsf17_g2_matched_pilot"
DEFAULT_ANALYSIS = ROOT / "outputs/tables/g4irsf17_g2_matched_pilot.json"
DEFAULT_OPPORTUNITY_TRACE_LIMIT = 250_000
DEFAULT_BOOTSTRAP_REPLICATES = 2_000
DEFAULT_BOOTSTRAP_SEED = 17_017

EVIDENCE_KIND = "MATCHED_SYSTEM_LOCAL_RULE_SCREEN_NOT_SAME_STATE_CAUSAL"
CAUSAL_LIMITATION = (
    "Each rule is a separate end-to-end native execution. Runtime state may "
    "diverge after the first changed grant, so this artifact is not a "
    "same-checkpoint, one-opportunity causal comparison and cannot authorize "
    "a G2 policy for the closed-loop ladder."
)


class G2MatchedPilotError(RuntimeError):
    """Raised when matched G2 evidence cannot be constructed honestly."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise G2MatchedPilotError(message)


def _resolve(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise G2MatchedPilotError(f"cannot read JSON artifact {path}: {exc}") from exc
    _require(isinstance(value, dict), f"JSON artifact is not an object: {path}")
    return value


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


@dataclass(frozen=True)
class PilotJob:
    job_id: str
    segments: int
    rule: str
    rule_name: str
    bootstrap_seed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "segments": self.segments,
            "rule": self.rule,
            "rule_name": self.rule_name,
            "bootstrap_seed": self.bootstrap_seed,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PilotJob":
        segments = value.get("segments")
        rule = value.get("rule")
        seed = value.get("bootstrap_seed")
        _require(type(segments) is int and segments in ALLOWED_SEGMENTS, "invalid job segments")
        _require(isinstance(rule, str) and rule in RULES, "invalid G2 rule")
        _require(type(seed) is int and seed >= 0, "invalid bootstrap seed")
        expected_id = f"g2_s{segments}_{rule.lower()}"
        _require(value.get("job_id") == expected_id, "job ID does not match segments/rule")
        _require(value.get("rule_name") == RULE_NAMES[rule], "job rule name drifted")
        return cls(expected_id, segments, rule, RULE_NAMES[rule], seed)


def build_plan(
    *,
    segments: Sequence[int] = DEFAULT_SEGMENTS,
    rules: Sequence[str] = RULES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    opportunity_trace_limit: int = DEFAULT_OPPORTUNITY_TRACE_LIMIT,
) -> dict[str, Any]:
    """Build a deterministic plan; no timestamp or machine identity is embedded."""

    normalized_segments = tuple(int(value) for value in segments)
    normalized_rules = tuple(str(value).upper() for value in rules)
    _require(bool(normalized_segments), "at least one segment prefix is required")
    _require(len(set(normalized_segments)) == len(normalized_segments), "duplicate segment prefix")
    _require(all(value in ALLOWED_SEGMENTS for value in normalized_segments), "unsupported segment prefix")
    _require(bool(normalized_rules) and normalized_rules[0] == "M1", "M1 FIFO must be the first baseline rule")
    _require(len(set(normalized_rules)) == len(normalized_rules), "duplicate G2 rule")
    _require(all(value in RULES for value in normalized_rules), "unsupported G2 rule")
    _require(type(bootstrap_seed) is int and bootstrap_seed >= 0, "bootstrap seed must be non-negative")
    _require(
        type(bootstrap_replicates) is int and bootstrap_replicates >= 100,
        "bootstrap replicates must be at least 100",
    )
    _require(
        type(opportunity_trace_limit) is int and opportunity_trace_limit > 0,
        "opportunity trace limit must be positive",
    )

    jobs: list[dict[str, Any]] = []
    for segment_count in normalized_segments:
        for rule_index, rule in enumerate(normalized_rules):
            job = PilotJob(
                job_id=f"g2_s{segment_count}_{rule.lower()}",
                segments=segment_count,
                rule=rule,
                rule_name=RULE_NAMES[rule],
                bootstrap_seed=bootstrap_seed + segment_count * 10 + rule_index,
            )
            jobs.append(job.as_dict())

    segment_token = "_".join(str(value) for value in normalized_segments)
    rule_token = "_".join(value.lower() for value in normalized_rules)
    return {
        "schema": SCHEMA_PLAN,
        "plan_id": f"g4irsf17_g2_matched_{segment_token}_{rule_token}_v1",
        "evidence_kind": EVIDENCE_KIND,
        "causal_authorization": {
            "authorized": False,
            "same_state_causal_opportunity_count": 0,
            "reason": CAUSAL_LIMITATION,
        },
        "design": {
            "input_protocol": "protected_first_n_file_order",
            "event_semantics": "E4_batch_plus_destination_merge_request",
            "supervisor_mode": "off",
            "matched_baseline_rule": "M1",
            "manipulated_control": "merge_grant_rule",
            "fixed_control_source": "g4irsf14_opportunity_census.FROZEN_RUNTIME_CONTROLS",
            "passive_opportunity_telemetry": True,
            "native_runtime_stochastic": False,
            "bootstrap_seed_is_analysis_only": True,
        },
        "segments": list(normalized_segments),
        "rules": list(normalized_rules),
        "bootstrap_replicates": bootstrap_replicates,
        "opportunity_trace_limit": opportunity_trace_limit,
        "jobs": jobs,
    }


def validate_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    _require(value.get("schema") == SCHEMA_PLAN, "unsupported G2 matched plan schema")
    _require(value.get("evidence_kind") == EVIDENCE_KIND, "plan evidence kind drifted")
    causal = value.get("causal_authorization")
    _require(isinstance(causal, Mapping), "plan causal limitation is missing")
    _require(causal.get("authorized") is False, "matched-system plan cannot authorize causality")
    _require(causal.get("same_state_causal_opportunity_count") == 0, "matched plan cannot claim same-state labels")
    jobs_raw = value.get("jobs")
    _require(isinstance(jobs_raw, list) and jobs_raw, "plan jobs are missing")
    jobs = [PilotJob.from_mapping(row) for row in jobs_raw if isinstance(row, Mapping)]
    _require(len(jobs) == len(jobs_raw), "plan contains a non-object job")
    _require(len({job.job_id for job in jobs}) == len(jobs), "duplicate plan job ID")
    segments = value.get("segments")
    rules = value.get("rules")
    _require(isinstance(segments, list) and isinstance(rules, list), "plan inventory is missing")
    expected = [(int(segment), str(rule)) for segment in segments for rule in rules]
    actual = [(job.segments, job.rule) for job in jobs]
    _require(actual == expected, "plan job order/inventory drifted")
    _require(rules and rules[0] == "M1", "plan lacks M1 FIFO baseline")
    replicates = value.get("bootstrap_replicates")
    trace_limit = value.get("opportunity_trace_limit")
    _require(type(replicates) is int and replicates >= 100, "invalid bootstrap replicates")
    _require(type(trace_limit) is int and trace_limit > 0, "invalid opportunity trace limit")
    return dict(value)


def build_native_request(
    *,
    job: PilotJob,
    binary: Path,
    node_records: Sequence[Any],
    edge_records: Sequence[Any],
    heuristic_time: Sequence[Any],
    bag_records: Sequence[Any],
    root: Path = ROOT,
    opportunity_trace_limit: int = DEFAULT_OPPORTUNITY_TRACE_LIMIT,
) -> dict[str, Any]:
    """Materialize one public-wrapper request with a one-control manipulation."""

    from scripts.eval.g4irsf14_opportunity_census import FROZEN_RUNTIME_CONTROLS, MODEL_PATH

    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=list(node_records),
        edge_records=list(edge_records),
        heuristic_time=list(heuristic_time),
        bag_records=list(bag_records),
        fault_windows=(),
        scenario=f"g4irsf17_g2_matched_s{job.segments}_{job.rule.lower()}",
        summary_only=False,
        trace_limit=0,
        event_trace_limit=0,
        trace_shard_count=1,
        trace_shard_index=0,
        enable_opportunity_telemetry=True,
        opportunity_trace_limit=opportunity_trace_limit,
        scorer_model_path=(root / MODEL_PATH).resolve(),
        expected_binary_path=binary.resolve(),
        search_path=binary.resolve().parent,
        g4irsf16_supervisor_mode="off",
        merge_grant_rule=job.rule,
    )
    return request


def _telemetry_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload.summary is missing")
    rows = payload.get("merge_request_visibility")
    _require(isinstance(rows, list), "native merge visibility telemetry is missing")

    total = _integer(summary.get("merge_visibility_total_count"))
    stored = _integer(summary.get("merge_visibility_stored_count"))
    dropped = _integer(summary.get("merge_visibility_dropped_count"))
    exact_competitive = _integer(
        summary.get("g4irsf14_i2_live_eligible_multi_request_boundary_count")
    )
    count_identity = (
        total is not None
        and stored is not None
        and dropped is not None
        and total == stored + dropped
        and stored == len(rows)
    )
    row_competitive = 0
    by_destination: Counter[int] = Counter()
    malformed_row_count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            malformed_row_count += 1
            continue
        known = _integer(row.get("known_competing_request_count"))
        later = _integer(row.get("later_same_time_competitor_count"))
        destination = _integer(row.get("destination_node"))
        if known is None or later is None or destination is None or known < 0 or later < 0:
            malformed_row_count += 1
            continue
        if known > 0 or later > 0:
            row_competitive += 1
            by_destination[destination] += 1

    telemetry_enabled = summary.get("opportunity_telemetry_enabled") is True
    telemetry_complete = (
        telemetry_enabled
        and count_identity
        and dropped == 0
        and malformed_row_count == 0
    )
    exact_counter_available = exact_competitive is not None and exact_competitive >= 0
    return {
        "telemetry_enabled": telemetry_enabled,
        "merge_visibility_total_count": total,
        "merge_visibility_stored_count": stored,
        "merge_visibility_dropped_count": dropped,
        "merge_visibility_count_identity": count_identity,
        "merge_visibility_malformed_row_count": malformed_row_count,
        "merge_visibility_competitive_row_count": row_competitive,
        "exact_live_eligible_multi_request_boundary_count": exact_competitive,
        "exact_competitive_counter_available": exact_counter_available,
        "telemetry_complete": telemetry_complete,
        "top_competitive_destinations": [
            {"destination_node": node, "visibility_row_count": count}
            for node, count in sorted(
                by_destination.items(), key=lambda item: (-item[1], item[0])
            )[:10]
        ],
        "counter_semantics": (
            "The exact counter increments at each post-expiry destination "
            "arbitration boundary with at least two live eligible requests. "
            "Visibility-row counts are descriptive and are not substituted "
            "for that support denominator."
        ),
    }


def _raw_bag_evidence(
    input_rows: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
    *,
    segments: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from scripts.eval import g4irsf12_reproducible_harness as g12

    runtime_bags = payload.get("bags")
    _require(isinstance(runtime_bags, list), "native payload.bags is missing")
    rows = [dict(row) for row in g12.aggregate_raw_bag_timings(input_rows, runtime_bags)]
    entry_by_task: dict[int, float] = {}
    for row in input_rows:
        task_id = int(row["task_id"])
        entry = float(row.get("original_entry_time", row["pass_time"]))
        entry_by_task[task_id] = min(entry, entry_by_task.get(task_id, entry))
    for row in rows:
        task_id = int(row["task_id"])
        row["tth_seconds"] = row["original_entry_time_tth_seconds"]
        row["original_entry_time"] = entry_by_task[task_id]
        row["time_block"] = int(math.floor(entry_by_task[task_id] / 3_600.0))
    timing = g12.summarize_raw_bag_timings(rows, selected_segment_count=segments)
    return rows, timing


def _hard_safety(summary: Mapping[str, Any], *, segments: int, rule: str) -> dict[str, Any]:
    from scripts.eval import run_g4irsf16_closed_loop_canary as g16

    evidence = g16._hard_gates(summary, segments, "off")
    gates = dict(evidence["gates"])
    gates.update(
        {
            "e4_event_semantics_echo": summary.get("event_semantics_echo")
            == "E4_batch_plus_destination_merge_request",
            "merge_rule_echo": summary.get("merge_grant_rule") == rule
            and summary.get("merge_grant_rule_echo") == rule,
            "opportunity_telemetry_passive_enabled": summary.get(
                "opportunity_telemetry_enabled"
            )
            is True,
        }
    )
    evidence["gates"] = gates
    evidence["safety_pass"] = all(value is True for value in gates.values())
    evidence["rule"] = rule
    return evidence


def _summary_projection(summary: Mapping[str, Any]) -> dict[str, Any]:
    names = (
        "requested_count",
        "completed_count",
        "failed_count",
        "event_count",
        "decision_count",
        "event_semantics_echo",
        "merge_grant_rule",
        "merge_grant_rule_echo",
        "destination_merge_arbitration_event_count",
        "g4irsf14_i2_live_eligible_multi_request_boundary_count",
        "merge_grant_request_count",
        "merge_grant_contended_loser_retry_count",
        "merge_grant_queue_capacity_block_count",
        "merge_grant_peak_pending_requests",
        "merge_visibility_total_count",
        "merge_visibility_stored_count",
        "merge_visibility_dropped_count",
        "merge_grant_lifecycle_transition_count",
        "merge_grant_lifecycle_stored_count",
        "merge_grant_lifecycle_dropped_count",
        "reservation_conflicts",
        "physical_fault_edge_entry_violation_count",
        "unresolved_deadlock_count",
        "runtime_full_astar_calls",
        "global_reservation_scan_count",
        "priority_global_scan_count",
        "scorer_runtime_global_scan_count",
        "microphase_runtime_global_scan_count",
        "first_edge_credit_global_scan_count",
        "event_limit_reached",
        "time_limit_reached",
        "runtime_seconds",
        "cpp_internal_accounted_bytes",
    )
    return {name: summary.get(name) for name in names}


def execute_native_job(
    job: PilotJob,
    *,
    binary: Path,
    root: Path = ROOT,
    opportunity_trace_limit: int = DEFAULT_OPPORTUNITY_TRACE_LIMIT,
) -> dict[str, Any]:
    """Execute one real native arm through the public Python wrapper."""

    from scripts.eval import g4irsf12_reproducible_harness as g12
    from scripts.eval.g4irsf11_fixed_map import assert_canonical_map, canonical_graph_records
    from czr005.cpp_backend import g4irsf11_event_runtime_from_records

    resolved_binary = binary.resolve(strict=True)
    prefix = g12.load_input_prefix(job.segments, root=root)
    input_rows = [dict(row) for row in prefix.rows]
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    request = build_native_request(
        job=job,
        binary=resolved_binary,
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=g12.binding_bag_records(prefix),
        root=root,
        opportunity_trace_limit=opportunity_trace_limit,
    )

    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    payload = g4irsf11_event_runtime_from_records(**request)
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    _require(isinstance(payload, Mapping), "native wrapper returned a non-object payload")
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload.summary is missing")
    raw_bags, timing = _raw_bag_evidence(input_rows, payload, segments=job.segments)
    telemetry = _telemetry_audit(payload)
    safety = _hard_safety(summary, segments=job.segments, rule=job.rule)
    status = "COMPLETE" if safety["safety_pass"] and timing["comparison_eligible"] else "HARD_GATE_FAILED"

    return {
        "schema": SCHEMA_RESULT,
        "evidence_kind": EVIDENCE_KIND,
        "job": job.as_dict(),
        "status": status,
        "causal_authorization": {
            "authorized": False,
            "same_state_causal_opportunity_count": 0,
            "reason": CAUSAL_LIMITATION,
        },
        "input_protocol": {
            "name": "protected_first_n_file_order",
            "selected_segment_count": job.segments,
            "topology_changed": False,
        },
        "runtime_control": {
            "event_semantics": request["event_semantics"],
            "supervisor_mode": request["g4irsf16_supervisor_mode"],
            "merge_grant_rule": job.rule,
            "manipulated_control": "merge_grant_rule",
            "passive_opportunity_telemetry": True,
        },
        "binary_path": str(resolved_binary),
        "resources": {
            "worker_wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
        },
        "hard_safety": safety,
        "telemetry_audit": telemetry,
        "raw_bag_summary": timing,
        "raw_bags": raw_bags,
        "runtime_summary": _summary_projection(summary),
    }


JobExecutor = Callable[..., dict[str, Any]]


def _result_path(results_dir: Path, job: PilotJob) -> Path:
    return results_dir / f"{job.job_id}.json"


def _terminal_result(path: Path, job: PilotJob) -> bool:
    if not path.exists():
        return False
    try:
        value = _read_json(path)
    except G2MatchedPilotError:
        return False
    return (
        value.get("schema") == SCHEMA_RESULT
        and value.get("evidence_kind") == EVIDENCE_KIND
        and value.get("job") == job.as_dict()
        and value.get("status") in {"COMPLETE", "HARD_GATE_FAILED"}
        and isinstance(value.get("causal_authorization"), Mapping)
        and value["causal_authorization"].get("authorized") is False
    )


def run_plan(
    plan: Mapping[str, Any],
    *,
    binary: Path,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    root: Path = ROOT,
    force: bool = False,
    executor: JobExecutor = execute_native_job,
) -> dict[str, Any]:
    """Execute/resume every arm; errors are checkpointed and remain rerunnable."""

    validated = validate_plan(plan)
    jobs = [PilotJob.from_mapping(row) for row in validated["jobs"]]
    results_dir.mkdir(parents=True, exist_ok=True)
    executed: list[str] = []
    resumed: list[str] = []
    failed: list[str] = []
    for job in jobs:
        path = _result_path(results_dir, job)
        if not force and _terminal_result(path, job):
            resumed.append(job.job_id)
            existing = _read_json(path)
            if existing.get("status") != "COMPLETE":
                failed.append(job.job_id)
            continue
        try:
            result = executor(
                job,
                binary=binary,
                root=root,
                opportunity_trace_limit=int(validated["opportunity_trace_limit"]),
            )
            _require(result.get("schema") == SCHEMA_RESULT, "job executor returned wrong schema")
            _require(result.get("job") == job.as_dict(), "job executor returned wrong job identity")
            causal = result.get("causal_authorization")
            _require(
                isinstance(causal, Mapping)
                and causal.get("authorized") is False
                and causal.get("same_state_causal_opportunity_count") == 0,
                "matched job executor attempted causal authorization",
            )
        except Exception as exc:  # explicit checkpoint; the next run retries it
            result = {
                "schema": SCHEMA_RESULT,
                "evidence_kind": EVIDENCE_KIND,
                "job": job.as_dict(),
                "status": "ERROR",
                "causal_authorization": {
                    "authorized": False,
                    "same_state_causal_opportunity_count": 0,
                    "reason": CAUSAL_LIMITATION,
                },
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "retryable": True,
                },
            }
        _atomic_write_json(path, result)
        executed.append(job.job_id)
        if result.get("status") != "COMPLETE":
            failed.append(job.job_id)

    return {
        "schema": SCHEMA_RUN,
        "plan_id": validated["plan_id"],
        "evidence_kind": EVIDENCE_KIND,
        "result_directory": _relative(results_dir, root),
        "job_count": len(jobs),
        "executed_job_ids": executed,
        "resumed_job_ids": resumed,
        "failed_job_ids": failed,
        "complete": not failed,
        "causal_authorization": {
            "authorized": False,
            "same_state_causal_opportunity_count": 0,
            "reason": CAUSAL_LIMITATION,
        },
    }


def _load_results(
    plan: Mapping[str, Any], results_dir: Path
) -> tuple[dict[tuple[int, str], dict[str, Any]], list[str], list[str]]:
    results: dict[tuple[int, str], dict[str, Any]] = {}
    missing: list[str] = []
    failed: list[str] = []
    for row in plan["jobs"]:
        job = PilotJob.from_mapping(row)
        path = _result_path(results_dir, job)
        if not path.exists():
            missing.append(job.job_id)
            continue
        result = _read_json(path)
        if result.get("schema") != SCHEMA_RESULT or result.get("job") != job.as_dict():
            failed.append(job.job_id)
            continue
        if result.get("status") != "COMPLETE":
            failed.append(job.job_id)
            continue
        causal = result.get("causal_authorization")
        _require(
            isinstance(causal, Mapping) and causal.get("authorized") is False,
            f"matched result attempts causal authorization: {job.job_id}",
        )
        results[(job.segments, job.rule)] = result
    return results, missing, failed


def _comparison_status(
    *,
    safety_pass: bool,
    support_count: int | None,
    telemetry_complete: bool,
    mean_delta: float | None,
    ci_upper: float | None,
) -> str:
    if not safety_pass:
        return "HARD_GATE_FAILED"
    if support_count is None or support_count < 64:
        return "INSUFFICIENT_MATCHED_CONTENTION"
    if not telemetry_complete:
        return "MATCHED_SIGNAL_TELEMETRY_TRUNCATED"
    if mean_delta is None:
        return "INCOMPLETE_PAIRED_DENOMINATOR"
    if ci_upper is not None and ci_upper < 0.0:
        return "STATISTICALLY_SUPPORTED_MATCHED_SIGNAL_ONLY"
    if mean_delta < 0.0:
        return "DIRECTIONAL_MATCHED_SIGNAL_ONLY"
    return "NO_MATCHED_IMPROVEMENT"


def analyse_plan(
    plan: Mapping[str, Any],
    *,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Pair every candidate with M1 and produce a non-authorizing screen."""

    from scripts.eval.run_g4irsf17_system_campaign import paired_performance

    validated = validate_plan(plan)
    results, missing, failed = _load_results(validated, results_dir)
    comparisons: list[dict[str, Any]] = []
    for segment_count in validated["segments"]:
        baseline = results.get((int(segment_count), "M1"))
        for rule in validated["rules"]:
            if rule == "M1":
                continue
            candidate = results.get((int(segment_count), str(rule)))
            if baseline is None or candidate is None:
                continue
            baseline_rows = baseline.get("raw_bags")
            candidate_rows = candidate.get("raw_bags")
            _require(isinstance(baseline_rows, list), "M1 raw-bag rows are missing")
            _require(isinstance(candidate_rows, list), f"{rule} raw-bag rows are missing")
            performance = paired_performance(
                baseline_rows,
                candidate_rows,
                bootstrap_replicates=int(validated["bootstrap_replicates"]),
                bootstrap_seed=int(candidate["job"]["bootstrap_seed"]),
            )
            baseline_telemetry = baseline.get("telemetry_audit")
            candidate_telemetry = candidate.get("telemetry_audit")
            _require(isinstance(baseline_telemetry, Mapping), "M1 telemetry audit is missing")
            _require(isinstance(candidate_telemetry, Mapping), f"{rule} telemetry audit is missing")
            baseline_support = _integer(
                baseline_telemetry.get("exact_live_eligible_multi_request_boundary_count")
            )
            candidate_support = _integer(
                candidate_telemetry.get("exact_live_eligible_multi_request_boundary_count")
            )
            conservative_support = (
                min(baseline_support, candidate_support)
                if baseline_support is not None and candidate_support is not None
                else None
            )
            baseline_safety = baseline.get("hard_safety")
            candidate_safety = candidate.get("hard_safety")
            safety_pass = (
                isinstance(baseline_safety, Mapping)
                and baseline_safety.get("safety_pass") is True
                and isinstance(candidate_safety, Mapping)
                and candidate_safety.get("safety_pass") is True
            )
            telemetry_complete = (
                baseline_telemetry.get("telemetry_complete") is True
                and candidate_telemetry.get("telemetry_complete") is True
            )
            source_delta = _finite(performance.get("source_wait_delta_mean_seconds"))
            network_delta = _finite(performance.get("network_time_delta_mean_seconds"))
            tth_delta = _finite(performance.get("mean_tth_delta_seconds"))
            decomposition_error = (
                tth_delta - source_delta - network_delta
                if tth_delta is not None
                and source_delta is not None
                and network_delta is not None
                else None
            )
            bootstrap = performance.get("bootstrap")
            ci_upper = (
                _finite(bootstrap.get("ci95_upper_seconds"))
                if isinstance(bootstrap, Mapping)
                else None
            )
            screen_status = _comparison_status(
                safety_pass=safety_pass,
                support_count=conservative_support,
                telemetry_complete=telemetry_complete,
                mean_delta=tth_delta,
                ci_upper=ci_upper,
            )
            comparisons.append(
                {
                    "segments": int(segment_count),
                    "baseline_rule": "M1",
                    "candidate_rule": str(rule),
                    "candidate_rule_name": RULE_NAMES[str(rule)],
                    "evidence_kind": EVIDENCE_KIND,
                    "hard_safety_pass": safety_pass,
                    "telemetry_complete": telemetry_complete,
                    "baseline_exact_competitive_boundary_count": baseline_support,
                    "candidate_exact_competitive_boundary_count": candidate_support,
                    "conservative_matched_support_count": conservative_support,
                    "matched_support_gate_64_pass": (
                        conservative_support is not None and conservative_support >= 64
                    ),
                    "performance": performance,
                    "timing_decomposition_error_seconds": decomposition_error,
                    "timing_decomposition_reconciles": (
                        decomposition_error is not None and abs(decomposition_error) <= 1.0e-7
                    ),
                    "p95_not_over_m1_plus_2_seconds": (
                        _finite(performance.get("p95_tth_delta_seconds")) is not None
                        and float(performance["p95_tth_delta_seconds"]) <= 2.0
                    ),
                    "p99_not_over_m1_plus_4_seconds": (
                        _finite(performance.get("p99_tth_delta_seconds")) is not None
                        and float(performance["p99_tth_delta_seconds"]) <= 4.0
                    ),
                    "screen_status": screen_status,
                    "promotion_authorized": False,
                    "same_state_causal_opportunity_count": 0,
                }
            )

    by_rule: dict[str, list[dict[str, Any]]] = {}
    for row in comparisons:
        by_rule.setdefault(str(row["candidate_rule"]), []).append(row)
    shortlist_rows: list[dict[str, Any]] = []
    for rule, rows in by_rule.items():
        safety_all = all(row["hard_safety_pass"] is True for row in rows)
        supported = [row for row in rows if row["matched_support_gate_64_pass"] is True]
        negative = [
            row
            for row in supported
            if _finite(row["performance"].get("mean_tth_delta_seconds")) is not None
            and float(row["performance"]["mean_tth_delta_seconds"]) < 0.0
        ]
        if safety_all and negative:
            largest = max(negative, key=lambda row: int(row["segments"]))
            shortlist_rows.append(
                {
                    "rule": rule,
                    "rule_name": RULE_NAMES[rule],
                    "largest_supported_segments": largest["segments"],
                    "largest_supported_mean_tth_delta_seconds": largest["performance"][
                        "mean_tth_delta_seconds"
                    ],
                    "purpose": "same_state_causal_followup_only",
                    "promotion_authorized": False,
                }
            )
    shortlist_rows.sort(
        key=lambda row: (
            float(row["largest_supported_mean_tth_delta_seconds"]),
            str(row["rule"]),
        )
    )

    status = "COMPLETE_MATCHED_SCREEN" if not missing and not failed else "INCOMPLETE_MATCHED_SCREEN"
    return {
        "schema": SCHEMA_ANALYSIS,
        "plan_id": validated["plan_id"],
        "status": status,
        "evidence_kind": EVIDENCE_KIND,
        "results_directory": _relative(results_dir, root),
        "missing_job_ids": missing,
        "failed_job_ids": failed,
        "comparison_count": len(comparisons),
        "comparisons": comparisons,
        "recommended_for_same_state_causal_followup": shortlist_rows,
        "causal_authorization": {
            "authorized": False,
            "same_state_causal_opportunity_count": 0,
            "reason": CAUSAL_LIMITATION,
        },
        "scientific_boundary": {
            "can_support": [
                "end-to-end matched rule screening",
                "raw-bag TTH/source-wait/network decomposition",
                "hard-safety and local-runtime invariant checks",
                "identification of rules worth a same-state causal pilot",
            ],
            "cannot_support": [
                "one-opportunity causal effect",
                "G2 closed-loop promotion authorization",
                "full-scale or fault robustness without the later campaign ladder",
            ],
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="write the deterministic M1--M6 plan")
    plan.add_argument("--root", type=Path, default=ROOT)
    plan.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    plan.add_argument("--segments", nargs="+", type=int, default=list(DEFAULT_SEGMENTS))
    plan.add_argument("--bootstrap-replicates", type=int, default=DEFAULT_BOOTSTRAP_REPLICATES)
    plan.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    plan.add_argument("--opportunity-trace-limit", type=int, default=DEFAULT_OPPORTUNITY_TRACE_LIMIT)

    run = subparsers.add_parser("run", help="execute or resume the real native arms")
    run.add_argument("--root", type=Path, default=ROOT)
    run.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    run.add_argument("--force", action="store_true")

    analyse = subparsers.add_parser("analyse", help="pair M2--M6 against M1")
    analyse.add_argument("--root", type=Path, default=ROOT)
    analyse.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    analyse.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    analyse.add_argument("--output", type=Path, default=DEFAULT_ANALYSIS)

    all_command = subparsers.add_parser("all", help="plan, run, and analyse in one command")
    all_command.add_argument("--root", type=Path, default=ROOT)
    all_command.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    all_command.add_argument("--binary", type=Path, required=True)
    all_command.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    all_command.add_argument("--output", type=Path, default=DEFAULT_ANALYSIS)
    all_command.add_argument("--segments", nargs="+", type=int, default=list(DEFAULT_SEGMENTS))
    all_command.add_argument("--bootstrap-replicates", type=int, default=DEFAULT_BOOTSTRAP_REPLICATES)
    all_command.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    all_command.add_argument("--opportunity-trace-limit", type=int, default=DEFAULT_OPPORTUNITY_TRACE_LIMIT)
    all_command.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = arguments.root.resolve()
    try:
        if arguments.command in {"plan", "all"}:
            plan_value = build_plan(
                segments=arguments.segments,
                bootstrap_seed=arguments.bootstrap_seed,
                bootstrap_replicates=arguments.bootstrap_replicates,
                opportunity_trace_limit=arguments.opportunity_trace_limit,
            )
            plan_path = _resolve(root, arguments.plan if arguments.command == "all" else arguments.output)
            _atomic_write_json(plan_path, plan_value)
        else:
            plan_path = _resolve(root, arguments.plan)
            plan_value = validate_plan(_read_json(plan_path))

        run_value: dict[str, Any] | None = None
        if arguments.command in {"run", "all"}:
            run_value = run_plan(
                plan_value,
                binary=_resolve(root, arguments.binary),
                results_dir=_resolve(root, arguments.results_dir),
                root=root,
                force=arguments.force,
            )
            _atomic_write_json(
                _resolve(root, arguments.results_dir) / "g4irsf17_g2_matched_pilot.run.json",
                run_value,
            )

        analysis: dict[str, Any] | None = None
        if arguments.command in {"analyse", "all"}:
            analysis = analyse_plan(
                plan_value,
                results_dir=_resolve(root, arguments.results_dir),
                root=root,
            )
            _atomic_write_json(_resolve(root, arguments.output), analysis)

        projection = {
            "plan": _relative(plan_path, root),
            "run_complete": run_value.get("complete") if run_value else None,
            "analysis_status": analysis.get("status") if analysis else None,
            "causal_authorized": False,
        }
        print(json.dumps(projection, ensure_ascii=False, sort_keys=True))
        if run_value is not None and run_value["failed_job_ids"]:
            return 2
        if analysis is not None and analysis["status"] != "COMPLETE_MATCHED_SCREEN":
            return 2
        return 0
    except (G2MatchedPilotError, OSError, ValueError) as exc:
        print(f"G2 matched pilot failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

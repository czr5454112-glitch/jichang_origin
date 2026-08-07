#!/usr/bin/env python3
"""Run a resumable real-native J7 merge coverage ladder against matched J2.

Every learned rung uses the same protected prefix and native binary as its J2
control.  A proposal is not ownership: the report counts only native applied
actions and feature-distinct mutations.  This driver can authorize a fixed
research workload, but it never sets a production grant or offline promotion
gate and never describes the resulting artifact as production-ready.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.eval import run_g4irsf18_jit_campaign as jit  # noqa: E402


SCHEMA_PLAN = "czr005.g4irsf18.learned_closed_loop_plan.v1"
SCHEMA_RESULT = "czr005.g4irsf18.learned_closed_loop_result.v1"
SCHEMA_ANALYSIS = "czr005.g4irsf18.learned_closed_loop_analysis.v1"

DEFAULT_ARTIFACT = ROOT / "artifacts/models/g4irsf18_j7_teacher_cf_affine.json"
DEFAULT_PLAN = ROOT / "artifacts/manifests/g4irsf18_learned_closed_loop_plan.json"
DEFAULT_RESULTS = ROOT / "outputs/runtime/g4irsf18_learned_closed_loop"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf18_learned_closed_loop.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf18_learned_closed_loop.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf18_learned_closed_loop.md"

J2_VARIANT_ID = "J2_F2_JIT_FAIR_AGING_DEADLINE"
J7_ARM_ID = "J7_TEACHER_CF_AFFINE"
MAX_OVERRIDES_PER_SEGMENT = 2
EVIDENCE_TRACE_LIMIT = 200_000
RESEARCH_DEPLOYMENT_STATUS = "research_fixed_workload_only_not_promoted"

# 144 deliberately runs at full research coverage: the protected smoke prefix
# previously exposed no multi-candidate opportunity, so the cap cannot broaden
# ownership there.  It still validates artifact loading and fail-closed paths.
COVERAGE_LADDER: Mapping[int, tuple[float, ...]] = {
    144: (1.0,),
    512: (0.10,),
    2_048: (0.05, 0.25, 0.50, 0.80, 1.0),
    8_192: (1.0,),
    43_603: (1.0,),
}

G18_COUNTERS = (
    "g4irsf18_merge_model_opportunity_count",
    "g4irsf18_merge_model_eligible_count",
    "g4irsf18_merge_model_proposal_count",
    "g4irsf18_merge_model_applied_count",
    "g4irsf18_merge_model_ownership_count",
    "g4irsf18_merge_distinct_action_mutation_count",
    "g4irsf18_merge_model_ood_count",
    "g4irsf18_merge_model_invalid_count",
    "g4irsf18_merge_model_fallback_count",
    "g4irsf18_merge_j2_fallback_count",
    "g4irsf18_merge_tie_fifo_fallback_count",
    "g4irsf18_merge_shadow_fallback_count",
    "g4irsf18_merge_authorization_fallback_count",
    "g4irsf18_merge_coverage_cap_fallback_count",
    "g4irsf18_merge_override_cap_fallback_count",
    "g4irsf18_merge_starvation_guard_fallback_count",
    "g4irsf18_merge_kill_switch_trip_count",
    "g4irsf18_merge_kill_switch_fallback_count",
    "g4irsf18_merge_coverage_eligible_seen_count",
    "g4irsf18_merge_runtime_global_scan_count",
    "g4irsf18_merge_future_route_input_count",
    "g4irsf18_merge_future_schedule_input_count",
    "g4irsf18_merge_full_astar_call_count",
)

FALLBACK_COUNTERS = (
    "g4irsf18_merge_model_ood_count",
    "g4irsf18_merge_model_invalid_count",
    "g4irsf18_merge_model_fallback_count",
    "g4irsf18_merge_j2_fallback_count",
    "g4irsf18_merge_tie_fifo_fallback_count",
    "g4irsf18_merge_shadow_fallback_count",
    "g4irsf18_merge_authorization_fallback_count",
    "g4irsf18_merge_coverage_cap_fallback_count",
    "g4irsf18_merge_override_cap_fallback_count",
    "g4irsf18_merge_starvation_guard_fallback_count",
    "g4irsf18_merge_kill_switch_fallback_count",
)


class G18LearnedClosedLoopError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise G18LearnedClosedLoopError(message)


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _portable(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON_NOT_OBJECT:{path}")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _coverage_tag(value: float) -> str:
    return f"c{int(round(value * 100)):03d}"


@dataclass(frozen=True)
class ClosedLoopJob:
    job_id: str
    prefix_segments: int
    kind: str
    coverage_cap: float

    @property
    def telemetry_mode(self) -> str:
        return "evidence_trace" if self.prefix_segments <= 8_192 else "capacity"

    @classmethod
    def create(
        cls, prefix_segments: int, kind: str, coverage_cap: float = 0.0
    ) -> "ClosedLoopJob":
        _require(prefix_segments in COVERAGE_LADDER, "UNSUPPORTED_PREFIX")
        _require(kind in {"control", "learned"}, "UNKNOWN_JOB_KIND")
        if kind == "control":
            _require(coverage_cap == 0.0, "CONTROL_COVERAGE_MUST_BE_ZERO")
            job_id = f"j2_control__s{prefix_segments}"
        else:
            _require(
                coverage_cap in COVERAGE_LADDER[prefix_segments],
                "COVERAGE_NOT_IN_FROZEN_LADDER",
            )
            smoke = "__smoke" if prefix_segments == 144 else ""
            job_id = (
                f"j7_learned__s{prefix_segments}{smoke}__"
                f"{_coverage_tag(coverage_cap)}"
            )
        return cls(job_id, prefix_segments, kind, float(coverage_cap))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ClosedLoopJob":
        prefix = value.get("prefix_segments")
        kind = value.get("kind")
        coverage = value.get("coverage_cap")
        _require(type(prefix) is int, "PREFIX_NOT_INTEGER")
        _require(isinstance(kind, str), "KIND_NOT_STRING")
        _require(
            not isinstance(coverage, bool) and isinstance(coverage, (int, float)),
            "COVERAGE_NOT_NUMERIC",
        )
        expected = cls.create(int(prefix), str(kind), float(coverage))
        _require(value.get("job_id") == expected.job_id, "JOB_IDENTITY_DRIFT")
        _require(
            value.get("telemetry_mode") == expected.telemetry_mode,
            "JOB_TELEMETRY_MODE_DRIFT",
        )
        return expected

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "prefix_segments": self.prefix_segments,
            "kind": self.kind,
            "coverage_cap": self.coverage_cap,
            "telemetry_mode": self.telemetry_mode,
            "matched_control_job_id": (
                None
                if self.kind == "control"
                else f"j2_control__s{self.prefix_segments}"
            ),
        }


def _load_artifact(path: Path) -> dict[str, Any]:
    value = _read_json(path.resolve(strict=True))
    _require(
        value.get("schema")
        == "czr005.g4irsf18.teacher_counterfactual_linear_merge.v1",
        "J7_ARTIFACT_SCHEMA_MISMATCH",
    )
    _require(
        value.get("family")
        == "teacher_warm_start_counterfactual_advantage_affine",
        "J7_ARTIFACT_FAMILY_MISMATCH",
    )
    _require(
        value.get("feature_contract") == "MERGE_TRACE_LOCAL_V1",
        "J7_FEATURE_CONTRACT_MISMATCH",
    )
    _require(
        value.get("production_closed_loop_authorized") is False,
        "J7_ARTIFACT_MUST_NOT_AUTHORIZE_PRODUCTION",
    )
    _require(value.get("ood_fallback") == "J2", "J7_OOD_FALLBACK_MISMATCH")
    return value


def build_plan(
    *,
    root: Path = ROOT,
    artifact_path: Path = DEFAULT_ARTIFACT,
) -> dict[str, Any]:
    resolved_artifact = _resolve(root, artifact_path)
    jobs: list[dict[str, Any]] = []
    for prefix, coverages in COVERAGE_LADDER.items():
        jobs.append(ClosedLoopJob.create(prefix, "control").as_dict())
        jobs.extend(
            ClosedLoopJob.create(prefix, "learned", coverage).as_dict()
            for coverage in coverages
        )
    return {
        "schema": SCHEMA_PLAN,
        "artifact_path": _portable(resolved_artifact, root),
        "design": {
            "control": J2_VARIANT_ID,
            "learned": J7_ARM_ID,
            "fixed_research_workload": True,
            "production_closed_loop_authorized": False,
            "offline_production_gate_passed": False,
            "max_overrides_per_segment": MAX_OVERRIDES_PER_SEGMENT,
            "score_only_is_not_ownership": True,
            "paired_on_same_prefix_and_native_binary": True,
        },
        "telemetry_contract": {
            "evidence_trace_prefixes": [144, 512, 2_048, 8_192],
            "capacity_prefixes": [43_603],
            "evidence_trace_limit": EVIDENCE_TRACE_LIMIT,
            "capacity_opportunity_telemetry_enabled": False,
            "core_native_counters_retained_in_both_modes": True,
        },
        "jobs": jobs,
    }


def validate_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    _require(value.get("schema") == SCHEMA_PLAN, "PLAN_SCHEMA_MISMATCH")
    design = value.get("design")
    _require(isinstance(design, Mapping), "PLAN_DESIGN_MISSING")
    _require(
        design.get("production_closed_loop_authorized") is False,
        "PLAN_MUST_KEEP_PRODUCTION_FALSE",
    )
    _require(
        design.get("offline_production_gate_passed") is False,
        "PLAN_MUST_KEEP_OFFLINE_GATE_FALSE",
    )
    artifact = value.get("artifact_path")
    _require(isinstance(artifact, str) and artifact, "PLAN_ARTIFACT_PATH_MISSING")
    raw_jobs = value.get("jobs")
    _require(isinstance(raw_jobs, list), "PLAN_JOBS_MISSING")
    jobs = [
        ClosedLoopJob.from_mapping(row)
        for row in raw_jobs
        if isinstance(row, Mapping)
    ]
    _require(len(jobs) == len(raw_jobs), "PLAN_JOB_NOT_OBJECT")
    expected = build_plan(root=ROOT, artifact_path=Path(str(artifact)))["jobs"]
    _require(
        [job.as_dict() for job in jobs] == expected,
        "PLAN_COVERAGE_LADDER_DRIFT",
    )
    return dict(value)


def native_policy_controls(
    job: ClosedLoopJob,
    *,
    artifact_path: Path,
) -> dict[str, Any]:
    if job.kind == "control":
        return {}
    return {
        "g4irsf18_merge_policy_mode": "research_closed_loop",
        "g4irsf18_merge_policy_artifact": artifact_path,
        "g4irsf18_merge_research_closed_loop_authorized": True,
        "g4irsf18_merge_fixed_research_workload": True,
        "g4irsf18_merge_production_closed_loop_authorized": False,
        "g4irsf18_merge_offline_gate_passed": False,
        "g4irsf18_merge_coverage_cap": job.coverage_cap,
        "g4irsf18_merge_max_overrides_per_segment": MAX_OVERRIDES_PER_SEGMENT,
        "g4irsf18_merge_kill_switch": False,
    }


def _runtime_metrics(
    rows: Sequence[Mapping[str, Any]],
    descriptor: Mapping[str, Any],
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = jit._raw_bags(rows, payload, str(descriptor["tth_denominator"]))
    completed = [row for row in raw if row["complete"]]
    all_complete = len(completed) == len(raw)
    tth = [float(row["tth_seconds"]) for row in completed]
    source = [float(row["source_wait_seconds"]) for row in completed]
    merge = [float(row["merge_grant_wait_seconds"]) for row in completed]
    network = [float(row["network_time_seconds"]) for row in completed]
    event_count = _integer(summary.get("event_count"))
    return (
        {
            "requested_segments": len(rows),
            "complete_raw_bags": len(completed),
            "raw_bag_count": len(raw),
            "mean_tth_seconds": statistics.fmean(tth) if all_complete else None,
            "p95_tth_seconds": jit._quantile(tth, 0.95) if all_complete else None,
            "p99_tth_seconds": jit._quantile(tth, 0.99) if all_complete else None,
            "source_wait_mean_seconds": statistics.fmean(source) if all_complete else None,
            "merge_grant_wait_mean_seconds": statistics.fmean(merge) if all_complete else None,
            "network_time_mean_seconds": statistics.fmean(network) if all_complete else None,
            "event_count": event_count,
            "events_per_requested_segment": (
                event_count / len(rows) if event_count is not None and rows else None
            ),
        },
        raw,
    )


def execute_job(
    job: ClosedLoopJob,
    *,
    binary: Path,
    artifact_path: Path,
    root: Path = ROOT,
    runtime_call: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    from scripts.eval.g4irsf11_fixed_map import (
        assert_canonical_map,
        canonical_graph_records,
    )
    from scripts.eval.g4irsf14_opportunity_census import (
        FROZEN_RUNTIME_CONTROLS,
        MODEL_PATH,
    )

    if runtime_call is None:
        from czr005.cpp_backend import g4irsf11_event_runtime_from_records

        runtime_call = g4irsf11_event_runtime_from_records
    resolved_binary = binary.resolve(strict=True)
    resolved_artifact = artifact_path.resolve(strict=True)
    artifact = _load_artifact(resolved_artifact)
    j2_job = jit.Job.create(
        J2_VARIANT_ID,
        prefix_segments=job.prefix_segments,
        scale=1,
    )
    rows, descriptor = jit._load_input(j2_job, root)
    descriptor = {**descriptor, "telemetry_mode": job.telemetry_mode}
    _require(descriptor["topology_changed"] is False, "TOPOLOGY_CHANGED")
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    request = dict(FROZEN_RUNTIME_CONTROLS)
    telemetry_enabled = job.telemetry_mode == "evidence_trace"
    telemetry_limit = EVIDENCE_TRACE_LIMIT if telemetry_enabled else 0
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=jit._binding_rows(rows),
        fault_windows=(),
        scenario=f"g4irsf18_learned_closed_loop_{job.job_id}",
        summary_only=False,
        trace_limit=0,
        event_trace_limit=0,
        enable_opportunity_telemetry=telemetry_enabled,
        opportunity_trace_limit=telemetry_limit,
        scorer_model_path=(root / MODEL_PATH).resolve(strict=True),
        expected_binary_path=resolved_binary,
        search_path=resolved_binary.parent,
        g4irsf16_supervisor_mode="off",
        merge_grant_rule="M3",
        merge_grant_timing_mode="jit_fair_aging_deadline",
    )
    request.update(
        native_policy_controls(job, artifact_path=resolved_artifact)
    )
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    payload = runtime_call(**request)
    resources = {
        "wall_seconds": time.perf_counter() - wall_start,
        "cpu_seconds": time.process_time() - cpu_start,
    }
    _require(isinstance(payload, Mapping), "NATIVE_PAYLOAD_NOT_OBJECT")
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "NATIVE_SUMMARY_MISSING")
    _require(
        summary.get("merge_grant_timing_mode") == "jit_fair_aging_deadline",
        "NATIVE_TIMING_MODE_MISMATCH",
    )
    metrics, raw_bags = _runtime_metrics(rows, descriptor, payload, summary)
    opportunity_rows = payload.get("merge_service_opportunities", [])
    _require(
        isinstance(opportunity_rows, list),
        "NATIVE_OPPORTUNITY_TRACE_NOT_LIST",
    )
    stored_opportunities = _integer(
        summary.get("merge_grant_opportunity_trace_stored_count")
    )
    _require(
        stored_opportunities is None
        or stored_opportunities == len(opportunity_rows),
        "NATIVE_OPPORTUNITY_STORED_COUNT_MISMATCH",
    )
    if not telemetry_enabled:
        _require(
            not opportunity_rows,
            "CAPACITY_MODE_UNEXPECTEDLY_RETAINED_OPPORTUNITY_ROWS",
        )
    hard_safety = jit._hard_safety(summary, len(rows))
    counters = {
        name: summary.get(name)
        for name in dict.fromkeys((*jit.COUNTERS, *G18_COUNTERS))
    }
    if job.kind == "learned":
        contract_gates = {
            "mode_echo": summary.get("g4irsf18_merge_policy_mode")
            == "research_closed_loop",
            "artifact_valid": summary.get("g4irsf18_merge_artifact_valid") is True,
            "schema_echo": summary.get("g4irsf18_merge_policy_schema")
            == artifact["schema"],
            "family_echo": summary.get("g4irsf18_merge_policy_family")
            == artifact["family"],
            "feature_contract_echo": summary.get("g4irsf18_merge_feature_contract")
            == artifact["feature_contract"],
            "research_grant_echo": summary.get(
                "g4irsf18_merge_research_closed_loop_authorized"
            )
            is True,
            "fixed_workload_echo": summary.get(
                "g4irsf18_merge_fixed_research_workload"
            )
            is True,
            "coverage_echo": abs(
                float(summary.get("g4irsf18_merge_coverage_cap", -1.0))
                - job.coverage_cap
            )
            <= 1.0e-12,
            "production_false": summary.get(
                "g4irsf18_merge_production_closed_loop_authorized"
            )
            is False,
            "offline_gate_false": summary.get(
                "g4irsf18_merge_offline_gate_passed"
            )
            is False,
            "deployment_status_research_only": summary.get(
                "g4irsf18_merge_deployment_status"
            )
            == RESEARCH_DEPLOYMENT_STATUS,
            "production_promotion_false": summary.get(
                "g4irsf18_merge_production_promotion_authorized"
            )
            is False,
            "kill_switch_not_tripped": summary.get(
                "g4irsf18_merge_kill_switch_tripped"
            )
            is False,
        }
    else:
        contract_gates = {
            "policy_disabled": not bool(
                summary.get("g4irsf18_merge_policy_mode")
            ),
            "production_false": summary.get(
                "g4irsf18_merge_production_closed_loop_authorized", False
            )
            is False,
            "production_promotion_false": summary.get(
                "g4irsf18_merge_production_promotion_authorized", False
            )
            is False,
        }
    contract_pass = all(contract_gates.values())
    complete = metrics["complete_raw_bags"] == metrics["raw_bag_count"]
    status = (
        "COMPLETE"
        if hard_safety["pass"] and contract_pass and complete
        else "HARD_OR_NATIVE_CONTRACT_FAILED"
    )
    return {
        "schema": SCHEMA_RESULT,
        "job": job.as_dict(),
        "status": status,
        "artifact": {
            "path": _portable(resolved_artifact, root),
            "schema": artifact["schema"],
            "family": artifact["family"],
            "feature_contract": artifact["feature_contract"],
            "production_closed_loop_authorized": False,
        },
        "input": descriptor,
        "native_controls": {
            "timing_mode": "jit_fair_aging_deadline",
            "merge_rule": "M3",
            "policy_mode": (
                "off" if job.kind == "control" else "research_closed_loop"
            ),
            "coverage_cap": job.coverage_cap,
            "production_closed_loop_authorized": False,
            "offline_gate_passed": False,
            "production_promotion_authorized": summary.get(
                "g4irsf18_merge_production_promotion_authorized", False
            ),
            "deployment_status": summary.get(
                "g4irsf18_merge_deployment_status",
                "off" if job.kind == "control" else None,
            ),
        },
        "telemetry": {
            "mode": job.telemetry_mode,
            "enabled": telemetry_enabled,
            "trace_limit": telemetry_limit,
            "total_count": summary.get(
                "merge_grant_opportunity_trace_total_count"
            ),
            "stored_count": stored_opportunities,
            "dropped_count": summary.get(
                "merge_grant_opportunity_trace_dropped_count"
            ),
            "core_native_counters_retained": True,
        },
        "resources": resources,
        "hard_safety": hard_safety,
        "native_contract": {"pass": contract_pass, "gates": contract_gates},
        "metrics": metrics,
        "counters": counters,
        "fallbacks": {
            name: summary.get(name) for name in FALLBACK_COUNTERS
        },
        "kill_switch_reason": summary.get(
            "g4irsf18_merge_kill_switch_reason", ""
        ),
        "raw_bags": raw_bags,
        **({"_opportunity_rows": opportunity_rows} if telemetry_enabled else {}),
    }


def _result_path(results_dir: Path, job: ClosedLoopJob) -> Path:
    return results_dir / f"{job.job_id}.json"


def _result_job_matches(value: Any, job: ClosedLoopJob) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected = job.as_dict()
    if dict(value) == expected:
        return True
    # Results from the first 10-job run predate the explicit telemetry field.
    # Retain them for analysis, but learned rows still require the new native
    # deployment/promotion echoes before they can be resumed as validated.
    legacy = dict(expected)
    legacy.pop("telemetry_mode")
    return dict(value) == legacy


def _legacy_research_only_proof(value: Mapping[str, Any]) -> bool:
    """Revalidate pre-echo results from persisted inputs and native gates.

    The native binding computes promotion as artifact-production AND runtime-
    production AND offline-gate, and selects the research-only deployment
    status whenever the artifact production bit is false.  The first 10-job
    result schema persisted all three inputs but not those two derived summary
    fields, so this proof avoids an otherwise identical rerun while recording
    its derivation source in analysis.
    """

    artifact = value.get("artifact", {})
    controls = value.get("native_controls", {})
    gates = value.get("native_contract", {}).get("gates", {})
    return (
        artifact.get("production_closed_loop_authorized") is False
        and controls.get("production_closed_loop_authorized") is False
        and controls.get("offline_gate_passed") is False
        and gates.get("artifact_valid") is True
        and gates.get("production_false") is True
        and gates.get("offline_gate_false") is True
    )


def _resume_result_valid(value: Mapping[str, Any], job: ClosedLoopJob) -> bool:
    if value.get("schema") != SCHEMA_RESULT or not _result_job_matches(
        value.get("job"), job
    ):
        return False
    if value.get("status") != "COMPLETE":
        return True
    if job.kind == "control":
        return True
    gates = value.get("native_contract", {}).get("gates", {})
    controls = value.get("native_controls", {})
    return _legacy_research_only_proof(value) or (
        gates.get("deployment_status_research_only") is True
        and gates.get("production_promotion_false") is True
        and controls.get("deployment_status") == RESEARCH_DEPLOYMENT_STATUS
        and controls.get("production_promotion_authorized") is False
    )


def run_plan(
    plan: Mapping[str, Any],
    *,
    binary: Path,
    results_dir: Path,
    root: Path = ROOT,
    job_ids: Sequence[str] = (),
    force: bool = False,
    executor: Callable[..., dict[str, Any]] = execute_job,
) -> dict[str, Any]:
    validated = validate_plan(plan)
    jobs = [ClosedLoopJob.from_mapping(row) for row in validated["jobs"]]
    selected = set(job_ids)
    unknown = selected - {job.job_id for job in jobs}
    _require(not unknown, "UNKNOWN_SELECTED_JOB:" + ",".join(sorted(unknown)))
    if selected:
        jobs = [job for job in jobs if job.job_id in selected]
    artifact_path = _resolve(root, str(validated["artifact_path"]))
    results_dir.mkdir(parents=True, exist_ok=True)
    executed: list[str] = []
    resumed: list[str] = []
    failed: list[str] = []
    for job in jobs:
        path = _result_path(results_dir, job)
        if not force and path.is_file():
            existing = _read_json(path)
            if _resume_result_valid(existing, job):
                resumed.append(job.job_id)
                if existing.get("status") != "COMPLETE":
                    failed.append(job.job_id)
                continue
        try:
            result = executor(
                job,
                binary=binary,
                artifact_path=artifact_path,
                root=root,
            )
        except Exception as exc:
            result = {
                "schema": SCHEMA_RESULT,
                "job": job.as_dict(),
                "status": "ERROR",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "production_closed_loop_authorized": False,
            }
        opportunity_rows = result.pop("_opportunity_rows", None)
        if isinstance(opportunity_rows, list):
            try:
                from scripts.eval.run_g4irsf18_system_campaign import (
                    _write_opportunity_trace,
                )

                opportunity_path, codec = _write_opportunity_trace(
                    path, opportunity_rows
                )
            except Exception as exc:
                result["status"] = "TRACE_PERSISTENCE_ERROR"
                result.setdefault("telemetry", {})["artifact_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            else:
                result.setdefault("telemetry", {}).update(
                    artifact=_portable(opportunity_path, root),
                    artifact_codec=codec,
                )
        _atomic_json(path, result)
        executed.append(job.job_id)
        if result.get("status") != "COMPLETE":
            failed.append(job.job_id)
    return {
        "executed": executed,
        "resumed": resumed,
        "failed": failed,
        "complete": not failed,
    }


def _paired_deltas(
    control: Mapping[str, Any], learned: Mapping[str, Any]
) -> dict[str, Any]:
    left = {
        int(row["task_id"]): row
        for row in control.get("raw_bags", [])
        if row.get("complete") is True
    }
    right = {
        int(row["task_id"]): row
        for row in learned.get("raw_bags", [])
        if row.get("complete") is True
    }
    common = sorted(set(left) & set(right))
    tth_deltas = [
        float(right[key]["tth_seconds"]) - float(left[key]["tth_seconds"])
        for key in common
    ]
    control_metrics = control.get("metrics", {})
    learned_metrics = learned.get("metrics", {})

    def delta(name: str) -> float | None:
        left_value = _finite(control_metrics.get(name))
        right_value = _finite(learned_metrics.get(name))
        return (
            right_value - left_value
            if left_value is not None and right_value is not None
            else None
        )

    control_events = _integer(control.get("counters", {}).get("event_count"))
    learned_events = _integer(learned.get("counters", {}).get("event_count"))
    return {
        "paired_complete_bag_count": len(common),
        "paired_tth_improved_count": sum(value < -1.0e-9 for value in tth_deltas),
        "paired_tth_harmed_count": sum(value > 1.0e-9 for value in tth_deltas),
        "paired_tth_unchanged_count": sum(abs(value) <= 1.0e-9 for value in tth_deltas),
        "mean_tth_delta_seconds": delta("mean_tth_seconds"),
        "p95_tth_delta_seconds": delta("p95_tth_seconds"),
        "p99_tth_delta_seconds": delta("p99_tth_seconds"),
        "source_wait_mean_delta_seconds": delta("source_wait_mean_seconds"),
        "merge_grant_wait_mean_delta_seconds": delta(
            "merge_grant_wait_mean_seconds"
        ),
        "network_time_mean_delta_seconds": delta("network_time_mean_seconds"),
        "event_count_delta": (
            learned_events - control_events
            if learned_events is not None and control_events is not None
            else None
        ),
        "events_per_requested_segment_delta": delta(
            "events_per_requested_segment"
        ),
    }


def _analysis_row(
    job: ClosedLoopJob,
    result: Mapping[str, Any],
    control: Mapping[str, Any] | None,
) -> dict[str, Any]:
    counters = result.get("counters", {})
    metrics = result.get("metrics", {})
    native_contract = result.get("native_contract", {})
    contract_gates = native_contract.get("gates", {})
    native_controls = result.get("native_controls", {})
    telemetry = result.get("telemetry", {})
    legacy_research_only_proof = (
        job.kind == "learned" and _legacy_research_only_proof(result)
    )
    opportunity = _integer(counters.get("g4irsf18_merge_model_opportunity_count"))
    eligible = _integer(counters.get("g4irsf18_merge_model_eligible_count"))
    proposal = _integer(counters.get("g4irsf18_merge_model_proposal_count"))
    applied = _integer(counters.get("g4irsf18_merge_model_applied_count"))
    ownership = _integer(counters.get("g4irsf18_merge_model_ownership_count"))
    mutation = _integer(
        counters.get("g4irsf18_merge_distinct_action_mutation_count")
    )
    eligible_sufficient = (
        eligible is not None
        and eligible > 0
        and math.floor(eligible * job.coverage_cap + 1.0e-12) >= 1
    )
    counter_identity = (
        None
        if None in {opportunity, eligible, proposal, applied, ownership, mutation}
        else (
            0 <= mutation <= applied <= proposal <= eligible <= opportunity
            and ownership == applied
        )
    )
    direct_deployment_status_pass = (
        True
        if job.kind == "control"
        else contract_gates.get("deployment_status_research_only") is True
        and native_controls.get("deployment_status")
        == RESEARCH_DEPLOYMENT_STATUS
    )
    direct_production_promotion_false_pass = (
        contract_gates.get("production_promotion_false") is True
        if job.kind == "learned"
        else native_controls.get("production_promotion_authorized", False)
        is False
    )
    deployment_status_pass = (
        direct_deployment_status_pass or legacy_research_only_proof
    )
    production_promotion_false_pass = (
        direct_production_promotion_false_pass or legacy_research_only_proof
    )
    deployment_validation_source = (
        "policy_off_control"
        if job.kind == "control"
        else (
            "native_summary_echo"
        if direct_deployment_status_pass
        and direct_production_promotion_false_pass
        else (
            "deterministic_native_formula_from_persisted_inputs"
            if legacy_research_only_proof
            else "missing_or_failed"
        )
        )
    )
    production_promotion = native_controls.get(
        "production_promotion_authorized"
    )
    if (
        production_promotion is None
        and native_controls.get("production_closed_loop_authorized") is False
        and native_controls.get("offline_gate_passed") is False
    ):
        production_promotion = False
    row = {
        "job_id": job.job_id,
        "prefix_segments": job.prefix_segments,
        "kind": job.kind,
        "coverage_cap": job.coverage_cap,
        "telemetry_mode": job.telemetry_mode,
        "telemetry_enabled": telemetry.get("enabled"),
        "opportunity_trace_total_count": telemetry.get("total_count"),
        "opportunity_trace_stored_count": telemetry.get("stored_count"),
        "opportunity_trace_dropped_count": telemetry.get("dropped_count"),
        "status": result.get("status"),
        "eligible_sufficient_for_one_applied_action": eligible_sufficient,
        "model_opportunity_count": opportunity,
        "model_eligible_count": eligible,
        "model_proposal_count": proposal,
        "model_applied_count": applied,
        "model_ownership_count": ownership,
        "distinct_action_mutation_count": mutation,
        "realized_coverage": (
            applied / eligible
            if applied is not None and eligible not in {None, 0}
            else None
        ),
        "counter_order_identity_pass": counter_identity,
        "hard_safety_pass": result.get("hard_safety", {}).get("pass"),
        "native_contract_pass": (
            native_contract.get("pass") is True
            and deployment_status_pass
            and production_promotion_false_pass
        ),
        "deployment_status_research_only_pass": deployment_status_pass,
        "production_promotion_false_pass": production_promotion_false_pass,
        "deployment_status": native_controls.get(
            "deployment_status",
            RESEARCH_DEPLOYMENT_STATUS if legacy_research_only_proof else None,
        ),
        "deployment_validation_source": deployment_validation_source,
        "production_closed_loop_authorized": result.get(
            "native_controls", {}
        ).get(
            "production_closed_loop_authorized",
            result.get("production_closed_loop_authorized"),
        ),
        "production_promotion_authorized": production_promotion,
        "mean_tth_seconds": metrics.get("mean_tth_seconds"),
        "p95_tth_seconds": metrics.get("p95_tth_seconds"),
        "p99_tth_seconds": metrics.get("p99_tth_seconds"),
        "source_wait_mean_seconds": metrics.get("source_wait_mean_seconds"),
        "merge_grant_wait_mean_seconds": metrics.get(
            "merge_grant_wait_mean_seconds"
        ),
        "network_time_mean_seconds": metrics.get("network_time_mean_seconds"),
        "event_count": counters.get("event_count"),
        **{
            name.removeprefix("g4irsf18_merge_"): counters.get(name)
            for name in FALLBACK_COUNTERS
        },
        "kill_switch_trip_count": counters.get(
            "g4irsf18_merge_kill_switch_trip_count"
        ),
        "kill_switch_reason": result.get("kill_switch_reason", ""),
    }
    if control is None or not (
        control.get("status") == "COMPLETE" and result.get("status") == "COMPLETE"
    ):
        row.update(
            {
                name: None
                for name in (
                    "paired_complete_bag_count",
                    "paired_tth_improved_count",
                    "paired_tth_harmed_count",
                    "paired_tth_unchanged_count",
                    "mean_tth_delta_seconds",
                    "p95_tth_delta_seconds",
                    "p99_tth_delta_seconds",
                    "source_wait_mean_delta_seconds",
                    "merge_grant_wait_mean_delta_seconds",
                    "network_time_mean_delta_seconds",
                    "event_count_delta",
                    "events_per_requested_segment_delta",
                )
            }
        )
    else:
        row.update(_paired_deltas(control, result))
    return row


def _write_outputs(
    analysis: Mapping[str, Any], *, root: Path
) -> None:
    csv_path = root / DEFAULT_CSV.relative_to(ROOT)
    report_path = root / DEFAULT_REPORT.relative_to(ROOT)
    rows = list(analysis.get("rows", []))
    fields = (
        "job_id", "prefix_segments", "kind", "coverage_cap",
        "telemetry_mode", "telemetry_enabled",
        "opportunity_trace_total_count", "opportunity_trace_stored_count",
        "opportunity_trace_dropped_count", "status",
        "eligible_sufficient_for_one_applied_action", "model_opportunity_count",
        "model_eligible_count", "model_proposal_count", "model_applied_count",
        "model_ownership_count", "distinct_action_mutation_count",
        "realized_coverage", "counter_order_identity_pass", "hard_safety_pass",
        "native_contract_pass", "deployment_status_research_only_pass",
        "production_promotion_false_pass", "deployment_status",
        "deployment_validation_source",
        "production_closed_loop_authorized",
        "production_promotion_authorized",
        "model_ood_count", "model_invalid_count", "model_fallback_count",
        "j2_fallback_count", "tie_fifo_fallback_count", "shadow_fallback_count",
        "authorization_fallback_count", "coverage_cap_fallback_count",
        "override_cap_fallback_count", "starvation_guard_fallback_count",
        "kill_switch_fallback_count", "kill_switch_trip_count", "kill_switch_reason",
        "mean_tth_seconds", "p95_tth_seconds", "p99_tth_seconds",
        "source_wait_mean_seconds", "merge_grant_wait_mean_seconds",
        "network_time_mean_seconds", "event_count", "paired_complete_bag_count",
        "paired_tth_improved_count", "paired_tth_harmed_count",
        "paired_tth_unchanged_count", "mean_tth_delta_seconds",
        "p95_tth_delta_seconds", "p99_tth_delta_seconds",
        "source_wait_mean_delta_seconds", "merge_grant_wait_mean_delta_seconds",
        "network_time_mean_delta_seconds", "event_count_delta",
        "events_per_requested_segment_delta",
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = csv_path.with_name(f".{csv_path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, csv_path)
    report = [
        "# G4IRSF18 learned merge closed-loop coverage ladder",
        "",
        f"Decision: **`{analysis['decision']}`**.",
        "",
        "Every learned row is paired with a same-prefix J2 control. Proposal is not ownership: only native applied decisions count, and a mutation additionally requires a feature-distinct action. Production authorization is false for every job and for this report.",
        "",
        "| Prefix | Telemetry | Coverage | Eligible | Proposal | Applied/ownership | Distinct mutation | Fallback J2/coverage/override/starvation | Safety | TTH mean delta | P95 delta | P99 delta | Source delta | Merge delta | Network delta | Event delta |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        if row["kind"] != "learned":
            continue

        def show(name: str) -> str:
            value = row.get(name)
            return "—" if value is None else str(value)

        report.append(
            f"| {row['prefix_segments']} | {row['telemetry_mode']} | {row['coverage_cap']:.0%} | {show('model_eligible_count')} | {show('model_proposal_count')} | {show('model_applied_count')}/{show('model_ownership_count')} | {show('distinct_action_mutation_count')} | {show('j2_fallback_count')}/{show('coverage_cap_fallback_count')}/{show('override_cap_fallback_count')}/{show('starvation_guard_fallback_count')} | {show('hard_safety_pass')} | {show('mean_tth_delta_seconds')} | {show('p95_tth_delta_seconds')} | {show('p99_tth_delta_seconds')} | {show('source_wait_mean_delta_seconds')} | {show('merge_grant_wait_mean_delta_seconds')} | {show('network_time_mean_delta_seconds')} | {show('event_count_delta')} |"
        )
    report.extend(
        [
            "",
            "All fallback counters are retained in the CSV/JSON, including OOD, invalid artifact, score tie, authorization, coverage, per-segment override, starvation, and kill-switch paths. An insufficient eligible denominator is reported rather than converted into a zero-effect success.",
            "",
            "This is fixed-workload research evidence only. Both `production_closed_loop_authorized` and native `production_promotion_authorized` remain `false` regardless of ladder outcome.",
            "",
        ]
    )
    _atomic_text(report_path, "\n".join(report))


def analyse_plan(
    plan: Mapping[str, Any],
    *,
    results_dir: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    validated = validate_plan(plan)
    jobs = [ClosedLoopJob.from_mapping(row) for row in validated["jobs"]]
    results: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for job in jobs:
        path = _result_path(results_dir, job)
        if not path.is_file():
            missing.append(job.job_id)
            continue
        value = _read_json(path)
        if value.get("schema") == SCHEMA_RESULT:
            results[job.job_id] = value
    controls = {
        job.prefix_segments: results[job.job_id]
        for job in jobs
        if job.kind == "control" and job.job_id in results
    }
    rows = [
        _analysis_row(job, results[job.job_id], controls.get(job.prefix_segments))
        for job in jobs
        if job.job_id in results
    ]
    learned_rows = [row for row in rows if row["kind"] == "learned"]
    completed_learned_rows = [
        row for row in learned_rows if row["status"] == "COMPLETE"
    ]
    production_false = all(
        row["production_closed_loop_authorized"] is False
        and row["production_promotion_authorized"] is False
        for row in rows
    )
    safety_pass = all(
        row["hard_safety_pass"] is True for row in completed_learned_rows
    )
    contract_pass = all(
        row["native_contract_pass"] is True
        and row["counter_order_identity_pass"] is True
        for row in completed_learned_rows
    )
    ownership = sum(
        int(row["model_ownership_count"] or 0) for row in learned_rows
    )
    mutations = sum(
        int(row["distinct_action_mutation_count"] or 0) for row in learned_rows
    )
    if not production_false:
        decision = "INVALID_PRODUCTION_AUTHORIZATION"
    elif not safety_pass or not contract_pass:
        decision = "HARD_SAFETY_OR_NATIVE_CONTRACT_FAILED"
    elif not learned_rows:
        decision = "NO_LEARNED_RESULTS"
    elif missing:
        decision = "INCREMENTAL_PENDING_FULL"
    elif ownership == 0 or mutations == 0:
        decision = "NO_REAL_LEARNED_OWNERSHIP_YET"
    else:
        decision = "RESEARCH_LADDER_EVIDENCE_ONLY_PRODUCTION_FALSE"
    analysis = {
        "schema": SCHEMA_ANALYSIS,
        "status": "COMPLETE" if not missing else "INCREMENTAL",
        "decision": decision,
        "missing_job_ids": missing,
        "artifact_path": validated["artifact_path"],
        "production_closed_loop_authorized": False,
        "production_promotion_authorized": False,
        "expected_research_deployment_status": RESEARCH_DEPLOYMENT_STATUS,
        "hard_safety_pass": safety_pass,
        "native_contract_pass": contract_pass,
        "total_model_ownership_count": ownership,
        "total_distinct_action_mutation_count": mutations,
        "rows": rows,
    }
    _write_outputs(analysis, root=root)
    return analysis


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--root", type=Path, default=ROOT)
    plan.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    plan.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    run = sub.add_parser("run")
    run.add_argument("--root", type=Path, default=ROOT)
    run.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    run.add_argument("--job-id", action="append", default=[])
    run.add_argument("--force", action="store_true")
    analyse = sub.add_parser("analyse")
    analyse.add_argument("--root", type=Path, default=ROOT)
    analyse.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    analyse.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    analyse.add_argument("--output", type=Path, default=DEFAULT_JSON)
    all_parser = sub.add_parser("all")
    all_parser.add_argument("--root", type=Path, default=ROOT)
    all_parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    all_parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    all_parser.add_argument("--binary", type=Path, required=True)
    all_parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    all_parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    all_parser.add_argument("--job-id", action="append", default=[])
    all_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command in {"plan", "all"}:
            artifact = _resolve(root, args.artifact)
            plan_value = build_plan(root=root, artifact_path=artifact)
            plan_path = _resolve(root, args.output if args.command == "plan" else args.plan)
            _atomic_json(plan_path, plan_value)
        else:
            plan_path = _resolve(root, args.plan)
            plan_value = validate_plan(_read_json(plan_path))
        run_value = None
        if args.command in {"run", "all"}:
            run_value = run_plan(
                plan_value,
                binary=_resolve(root, args.binary),
                results_dir=_resolve(root, args.results_dir),
                root=root,
                job_ids=args.job_id,
                force=args.force,
            )
        analysis = None
        if args.command in {"analyse", "all"}:
            analysis = analyse_plan(
                plan_value,
                results_dir=_resolve(root, args.results_dir),
                root=root,
            )
            _atomic_json(_resolve(root, args.output), analysis)
        print(
            json.dumps(
                {
                    "plan": _portable(plan_path, root),
                    "executed": run_value["executed"] if run_value else [],
                    "resumed": run_value["resumed"] if run_value else [],
                    "failed": run_value["failed"] if run_value else [],
                    "analysis_status": analysis["status"] if analysis else None,
                    "decision": analysis["decision"] if analysis else None,
                    "production_closed_loop_authorized": False,
                },
                sort_keys=True,
            )
        )
        if run_value is not None and run_value["failed"]:
            return 2
        return 0
    except (G18LearnedClosedLoopError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G18 learned closed-loop campaign failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

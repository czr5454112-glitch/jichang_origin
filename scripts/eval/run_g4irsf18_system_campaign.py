#!/usr/bin/env python3
"""Run the incremental G18 ladder, scale-capacity, and fault campaign.

This is an orchestration layer over the real native event runtime.  It reuses
the G18 JIT arm definitions and metrics, G10's fixed-map scale generator, and
G17's protected real-map fault catalogue.  It does not implement a simulator.

The built-in arms are J0/J1/J2.  A learned merge arm is a reserved, explicit
configuration input: absence or failed research authorization excludes it
from the plan instead of silently substituting a rule or claiming availability.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import gzip
import inspect
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_g4irsf18_jit_campaign as jit


SCHEMA_PLAN = "czr005.g4irsf18.system_campaign_plan.v1"
SCHEMA_RESULT = "czr005.g4irsf18.system_campaign_result.v1"
SCHEMA_ANALYSIS = "czr005.g4irsf18.system_campaign_analysis.v1"
SCHEMA_LEARNED_ARM = "czr005.g4irsf18.learned_merge_arm.v1"

LADDER_SEGMENTS = (144, 512, 2_048, 8_192, 43_603)
FULL_SCALE_FACTORS = (1, 2, 4, 8, 16)
OPTIONAL_SMOKE_SCALE = 32
DEFAULT_32X_SMOKE_SEGMENTS = 8_192
DEFAULT_FAULT_PREFIX = 8_192
EVIDENCE_TRACE_LIMIT = 500_000
PENDING_FAULT_SCENARIO_ID = "pending_inflight_repair"
INFLIGHT_FAULT_SCENARIO_ID = "inflight_exact_lease_repair"
INFLIGHT_CALIBRATED_ONSET = 16_966.01816

DEFAULT_PLAN = ROOT / "artifacts/manifests/g4irsf18_system_campaign_plan.json"
DEFAULT_RESULTS = ROOT / "outputs/runtime/g4irsf18_system_campaign"
DEFAULT_JIT_RESULTS = ROOT / "outputs/runtime/g4irsf18_jit_campaign"
DEFAULT_ANALYSIS = ROOT / "outputs/tables/g4irsf18_system_campaign.json"

LADDER_TABLE = ROOT / "outputs/tables/g4irsf18_closed_loop_ladder.csv"
LADDER_REPORT = ROOT / "outputs/reports/g4irsf18_closed_loop_ladder.md"
SCALE_TABLE = ROOT / "outputs/tables/g4irsf18_scale_capacity.csv"
SCALE_REPORT = ROOT / "outputs/reports/g4irsf18_scale_capacity.md"
FAULT_TABLE = ROOT / "outputs/tables/g4irsf18_fault_campaign.csv"
FAULT_REPORT = ROOT / "outputs/reports/g4irsf18_fault_campaign.md"


class G18SystemCampaignError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise G18SystemCampaignError(message)


def _resolve(root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON is not an object: {path}")
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


def _write_opportunity_trace(
    result_path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[Path, str]:
    """Persist evidence rows without making zstandard a campaign dependency."""
    try:
        import zstandard  # noqa: F401
    except ImportError:
        path = result_path.with_suffix(".opportunities.jsonl.gz")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with gzip.open(temporary, "wt", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
        os.replace(temporary, path)
        return path, "gzip"

    path = result_path.with_suffix(".opportunities.jsonl.zst")
    jit._write_jsonl_zst(path, rows)
    return path, "zstd"


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _fmt(value: Any, digits: int = 6) -> str:
    number = _finite(value)
    return "—" if number is None else f"{number:.{digits}f}"


@dataclass(frozen=True)
class Arm:
    arm_id: str
    timing_mode: str
    merge_rule: str
    learned: bool = False
    native_controls: Mapping[str, Any] | None = None
    research_closed_loop_authorized: bool = False
    production_closed_loop_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["native_controls"] = dict(self.native_controls or {})
        return value


BUILTIN_ARMS: tuple[Arm, ...] = tuple(
    Arm(variant.variant_id, variant.timing_mode, variant.merge_rule)
    for variant in jit.VARIANTS
)
BUILTIN_ARM_BY_ID = {arm.arm_id: arm for arm in BUILTIN_ARMS}


def load_learned_arm(path: Path | None) -> tuple[Arm | None, dict[str, Any]]:
    if path is None:
        return None, {
            "arm_id": "JX_LEARNED_MERGE_RESERVED",
            "reason": "NO_EXPLICIT_LEARNED_ARM_CONFIG",
        }
    value = _read_json(path)
    _require(value.get("schema") == SCHEMA_LEARNED_ARM, "learned arm schema mismatch")
    arm_id = value.get("arm_id")
    _require(isinstance(arm_id, str) and arm_id, "learned arm_id is required")
    controls = value.get("native_controls")
    _require(isinstance(controls, Mapping), "learned native_controls must be an object")
    enabled = value.get("enabled") is True
    research = value.get("research_closed_loop_authorized") is True
    fixed = value.get("fixed_research_workload") is True
    production = value.get("production_closed_loop_authorized") is True
    if not enabled:
        return None, {"arm_id": arm_id, "reason": "LEARNED_ARM_DISABLED"}
    if not research or not fixed:
        return None, {
            "arm_id": arm_id,
            "reason": "RESEARCH_CLOSED_LOOP_OR_FIXED_WORKLOAD_GRANT_MISSING",
        }
    _require(not production, "research learned arm must not assert production authorization")
    timing_mode = value.get("timing_mode", "jit_fifo")
    merge_rule = value.get("merge_rule", "M1")
    _require(
        timing_mode in {"jit_fifo", "jit_fair_aging_deadline"},
        "learned arm must use a JIT timing boundary",
    )
    _require(isinstance(merge_rule, str), "learned merge_rule must be a string")
    return (
        Arm(
            arm_id=arm_id,
            timing_mode=str(timing_mode),
            merge_rule=merge_rule,
            learned=True,
            native_controls=dict(controls),
            research_closed_loop_authorized=True,
            production_closed_loop_authorized=False,
        ),
        {"arm_id": arm_id, "reason": "INCLUDED_RESEARCH_ONLY"},
    )


@dataclass(frozen=True)
class SystemJob:
    job_id: str
    stage: str
    arm_id: str
    prefix_segments: int | None = None
    scale: int = 1
    max_segments: int = -1
    fault_scenario: Mapping[str, Any] | None = None
    telemetry_mode: str = "capacity"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SystemJob":
        stage = str(value["stage"])
        prefix_segments = _integer(value.get("prefix_segments"))
        default_telemetry = (
            "evidence_trace"
            if stage == "fault"
            or (stage == "ladder" and prefix_segments is not None and prefix_segments <= 8_192)
            else "capacity"
        )
        job = cls(
            job_id=str(value["job_id"]),
            stage=stage,
            arm_id=str(value["arm_id"]),
            prefix_segments=prefix_segments,
            scale=int(value.get("scale", 1)),
            max_segments=int(value.get("max_segments", -1)),
            fault_scenario=(
                dict(value["fault_scenario"])
                if isinstance(value.get("fault_scenario"), Mapping)
                else None
            ),
            telemetry_mode=str(value.get("telemetry_mode", default_telemetry)),
        )
        _require(job.stage in {"ladder", "scale", "fault"}, "unknown system stage")
        _require(
            job.telemetry_mode in {"evidence_trace", "capacity"},
            "unknown telemetry mode",
        )
        _require(job.scale in (*FULL_SCALE_FACTORS, OPTIONAL_SMOKE_SCALE), "bad scale")
        if job.stage == "ladder":
            _require(job.prefix_segments in LADDER_SEGMENTS, "bad ladder prefix")
            _require(job.scale == 1 and job.max_segments == -1, "ladder scope drift")
            _require(
                job.telemetry_mode
                == ("evidence_trace" if job.prefix_segments <= 8_192 else "capacity"),
                "ladder telemetry scope drift",
            )
        elif job.stage == "scale":
            _require(job.prefix_segments is None, "scale job cannot use prefix input")
            _require(
                (job.scale in FULL_SCALE_FACTORS and job.max_segments == -1)
                or (job.scale == OPTIONAL_SMOKE_SCALE and job.max_segments > 0),
                "scale full/smoke scope drift",
            )
            _require(job.telemetry_mode == "capacity", "scale telemetry must be off")
        else:
            _require(job.prefix_segments == DEFAULT_FAULT_PREFIX, "fault prefix drift")
            _require(isinstance(job.fault_scenario, Mapping), "fault scenario missing")
            _require(
                job.telemetry_mode == "evidence_trace",
                "fault regression requires evidence trace",
            )
        return job


def _fault_scenario(root: Path) -> dict[str, Any]:
    from scripts.eval import run_g4irsf17_system_campaign as g17

    source = next(
        scenario
        for scenario in g17.default_fault_scenarios(root=root)
        if scenario.scenario_id == "noncritical_edge"
    )
    value = source.as_dict()
    value.update(
        scenario_id="pending_inflight_repair",
        duration_seconds=300.0,
        notes=(
            "Narrow G18 regression over the G17 reachability-preserving edge: "
            "fault plus repair must preserve pending requests and any exact "
            "physically in-flight destination lease."
        ),
    )
    return value


def _fault_scenarios(root: Path) -> tuple[dict[str, Any], ...]:
    pending = _fault_scenario(root)
    calibrated = {
        **pending,
        "scenario_id": INFLIGHT_FAULT_SCENARIO_ID,
        "validation_target": "inflight_exact_lease",
        "onset_time": INFLIGHT_CALIBRATED_ONSET,
        "notes": (
            "Evidence-directed exact-lease regression on edge (6,12). The "
            "fault onset is the midpoint of the observed J1 request-2081 "
            "flight window [16961.01816, 16971.01816]."
        ),
        "calibration": {
            "source_scenario_id": PENDING_FAULT_SCENARIO_ID,
            "source_arm_id": "J1_F2_JIT_FIFO",
            "source_opportunity_id": 2081,
            "source_candidate_request_id": 2081,
            "upstream_node": 6,
            "destination_node": 12,
            "observed_event_time": 16_961.01816,
            "observed_projected_arrival": 16_971.01816,
            "selection": "observed_flight_window_midpoint",
            "attempt": 1,
            "maximum_attempts": 3,
        },
    }
    return pending, calibrated


def _job_id(
    arm: Arm,
    stage: str,
    *,
    prefix: int | None = None,
    scale: int = 1,
    smoke_segments: int = -1,
    scenario_id: str = "",
) -> str:
    base = arm.arm_id.lower()
    if stage == "ladder":
        return f"{base}__s{prefix}"
    if stage == "scale":
        suffix = f"{scale}x_full" if smoke_segments < 0 else f"{scale}x_smoke{smoke_segments}"
        return f"{base}__{suffix}"
    return f"{base}__fault__{scenario_id}__s{prefix}"


def build_plan(
    *,
    root: Path = ROOT,
    learned_arm: Arm | None = None,
    learned_note: Mapping[str, Any] | None = None,
    smoke_32x_segments: int = DEFAULT_32X_SMOKE_SEGMENTS,
    fault_prefix: int = DEFAULT_FAULT_PREFIX,
) -> dict[str, Any]:
    _require(smoke_32x_segments > 0, "32x smoke size must be positive")
    _require(fault_prefix == DEFAULT_FAULT_PREFIX, "fault prefix is frozen at 8192")
    arms = list(BUILTIN_ARMS)
    if learned_arm is not None:
        _require(learned_arm.learned, "optional learned arm must be marked learned")
        _require(
            learned_arm.arm_id not in BUILTIN_ARM_BY_ID,
            "learned arm collides with a built-in arm",
        )
        arms.append(learned_arm)
    faults = _fault_scenarios(root)
    jobs: list[SystemJob] = []
    for segments in LADDER_SEGMENTS:
        for arm in arms:
            jobs.append(
                SystemJob(
                    _job_id(arm, "ladder", prefix=segments),
                    "ladder",
                    arm.arm_id,
                    prefix_segments=segments,
                    telemetry_mode=(
                        "evidence_trace" if segments <= 8_192 else "capacity"
                    ),
                )
            )
    for scale in (*FULL_SCALE_FACTORS, OPTIONAL_SMOKE_SCALE):
        limit = smoke_32x_segments if scale == OPTIONAL_SMOKE_SCALE else -1
        for arm in arms:
            jobs.append(
                SystemJob(
                    _job_id(arm, "scale", scale=scale, smoke_segments=limit),
                    "scale",
                    arm.arm_id,
                    scale=scale,
                    max_segments=limit,
                    telemetry_mode="capacity",
                )
            )
    for fault in faults:
        for arm in arms:
            jobs.append(
                SystemJob(
                    _job_id(
                        arm,
                        "fault",
                        prefix=fault_prefix,
                        scenario_id=str(fault["scenario_id"]),
                    ),
                    "fault",
                    arm.arm_id,
                    prefix_segments=fault_prefix,
                    fault_scenario=fault,
                    telemetry_mode="evidence_trace",
                )
            )
    ids = [job.job_id for job in jobs]
    _require(len(ids) == len(set(ids)), "system plan has duplicate job IDs")
    return {
        "schema": SCHEMA_PLAN,
        "input_contract": {
            "ladder": "protected_first_n_file_order",
            "scale": "g4irsf10_distribution_preserving_fixed_map_resample",
            "fault": "protected_8192_prefix_plus_real_map_fault_repair_window",
        },
        "telemetry_contract": {
            "evidence_trace": "ladder prefixes <=8192 and narrow fault regression",
            "capacity": "43603 ladder plus every full-scale and 32x smoke job",
            "evidence_trace_limit": EVIDENCE_TRACE_LIMIT,
            "capacity_opportunity_telemetry_enabled": False,
        },
        "arms": [arm.as_dict() for arm in arms],
        "learned_arm": dict(
            learned_note
            or {
                "arm_id": "JX_LEARNED_MERGE_RESERVED",
                "reason": "NO_EXPLICIT_LEARNED_ARM_CONFIG",
            }
        ),
        "ladder_segments": list(LADDER_SEGMENTS),
        "full_scale_factors": list(FULL_SCALE_FACTORS),
        "smoke_scale": OPTIONAL_SMOKE_SCALE,
        "smoke_32x_segments": smoke_32x_segments,
        "fault_prefix_segments": fault_prefix,
        "fault_scenarios": list(faults),
        "jobs": [job.as_dict() for job in jobs],
    }


def validate_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    _require(value.get("schema") == SCHEMA_PLAN, "system plan schema mismatch")
    arms = value.get("arms")
    jobs = value.get("jobs")
    _require(isinstance(arms, list) and arms, "system plan has no arms")
    _require(isinstance(jobs, list) and jobs, "system plan has no jobs")
    arm_ids = [str(row.get("arm_id")) for row in arms if isinstance(row, Mapping)]
    _require(len(arm_ids) == len(arms), "non-object arm")
    _require(len(arm_ids) == len(set(arm_ids)), "duplicate arm")
    parsed = [SystemJob.from_mapping(row) for row in jobs if isinstance(row, Mapping)]
    _require(len(parsed) == len(jobs), "non-object job")
    _require(all(job.arm_id in arm_ids for job in parsed), "job references unknown arm")
    _require(len({job.job_id for job in parsed}) == len(parsed), "duplicate job ID")
    _require(value.get("ladder_segments") == list(LADDER_SEGMENTS), "ladder contract drift")
    _require(
        value.get("full_scale_factors") == list(FULL_SCALE_FACTORS),
        "full-scale contract drift",
    )
    _require(value.get("smoke_scale") == OPTIONAL_SMOKE_SCALE, "smoke scale drift")
    smoke_segments = _integer(value.get("smoke_32x_segments"))
    _require(smoke_segments is not None and smoke_segments > 0, "smoke size missing")
    for arm_id in arm_ids:
        arm_jobs = [job for job in parsed if job.arm_id == arm_id]
        _require(
            {job.prefix_segments for job in arm_jobs if job.stage == "ladder"}
            == set(LADDER_SEGMENTS),
            f"incomplete ladder cross-product for {arm_id}",
        )
        _require(
            {(job.scale, job.max_segments) for job in arm_jobs if job.stage == "scale"}
            == {
                *((scale, -1) for scale in FULL_SCALE_FACTORS),
                (OPTIONAL_SMOKE_SCALE, smoke_segments),
            },
            f"incomplete scale cross-product for {arm_id}",
        )
        fault_jobs = [job for job in arm_jobs if job.stage == "fault"]
        _require(
            {
                str(job.fault_scenario.get("scenario_id"))
                for job in fault_jobs
                if job.fault_scenario is not None
            }
            == {PENDING_FAULT_SCENARIO_ID, INFLIGHT_FAULT_SCENARIO_ID},
            f"fault regression cross-product drift for {arm_id}",
        )
    return dict(value)


def _arm_map(plan: Mapping[str, Any]) -> dict[str, Arm]:
    result: dict[str, Arm] = {}
    for row in plan["arms"]:
        result[str(row["arm_id"])] = Arm(
            arm_id=str(row["arm_id"]),
            timing_mode=str(row["timing_mode"]),
            merge_rule=str(row["merge_rule"]),
            learned=bool(row.get("learned", False)),
            native_controls=dict(row.get("native_controls", {})),
            research_closed_loop_authorized=bool(
                row.get("research_closed_loop_authorized", False)
            ),
            production_closed_loop_authorized=bool(
                row.get("production_closed_loop_authorized", False)
            ),
        )
    return result


def _load_jsonl(path: Path, *, limit: int = -1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                _require(isinstance(value, dict), f"non-object JSONL row: {path}")
                rows.append(value)
                if limit > 0 and len(rows) >= limit:
                    break
    _require(bool(rows), f"empty input: {path}")
    return rows


def _load_input(job: SystemJob, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if job.stage in {"ladder", "fault"}:
        from scripts.eval import g4irsf12_reproducible_harness as g12

        assert job.prefix_segments is not None
        prefix = g12.load_input_prefix(job.prefix_segments, root=root)
        return [dict(row) for row in prefix.rows], {
            "protocol": "protected_first_n_file_order",
            "segments": job.prefix_segments,
            "scale": 1,
            "smoke_capped": False,
            "topology_changed": False,
            "tth_denominator": "original_entry_time_tth",
        }

    from scripts.eval import run_g4irsf10_v2_safe_scale_hardcase_training as g10

    path, metadata = g10.ensure_source_queue_for_case(
        scale=job.scale,
        rolling_days=1,
        time_compression=1.0,
        label=f"g4irsf18_system_{job.scale}x",
    )
    rows = _load_jsonl(path, limit=job.max_segments)
    return rows, {
        "protocol": "g4irsf10_distribution_preserving_fixed_map_resample",
        "segments": len(rows),
        "scale": job.scale,
        "smoke_capped": job.max_segments > 0,
        "topology_changed": bool(metadata.get("topology_changed", False)),
        "tth_denominator": "java_release_time_tth",
    }


def _fault_windows(
    scenario: Mapping[str, Any] | None,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[tuple[int, int, float, float, float, bool]], dict[str, Any]]:
    if scenario is None:
        return [], {"scenario_id": "no_fault", "fault_onset": None, "repair_time": None}
    edges = scenario.get("edges", [])
    _require(isinstance(edges, Sequence) and bool(edges), "fault edges missing")
    release = [float(row["pass_time"]) for row in rows]
    first, last = min(release), max(release)
    explicit_onset = _finite(scenario.get("onset_time"))
    onset = (
        explicit_onset
        if explicit_onset is not None
        else first
        + float(scenario.get("onset_fraction", 0.35)) * max(1.0, last - first)
    )
    _require(first <= onset <= last, "fault onset falls outside the input horizon")
    repair = onset + float(scenario.get("duration_seconds", 300.0))
    windows = [
        (
            int(edge[0]),
            int(edge[1]),
            onset,
            repair,
            float(scenario.get("message_delay_seconds", 0.0)),
            bool(scenario.get("notification_dropped", False)),
        )
        for edge in edges
    ]
    return windows, {**dict(scenario), "fault_onset": onset, "repair_time": repair}


EXTENDED_COUNTERS = tuple(
    dict.fromkeys(
        (*jit.COUNTERS,
         "declared_max_events",
         "max_source_queue_length",
         "max_source_queue_delay",
         "max_junction_queue_length",
         "fault_event_count",
         "repair_event_count",
         "fault_notification_drop_count",
         "fault_affected_bag_count",
         "fault_affected_completed_count",
         "fault_target_edge_candidate_exposure_count",
         "fault_target_edge_attempt_count",
         "fault_recovery_seconds_available",
         "fault_recovery_seconds",
         "physical_fault_interlock_rejection_count",
         "physical_fault_interlock_hold_count",
         "physical_fault_interlock_reroute_count",
         "local_fault_policy_action_count",
         "local_fault_policy_hold_count",
         "local_fault_policy_reroute_count",
         "congestion_beacon_update_event_count",
         "merge_grant_issued_count",
         "merge_grant_prepared_count",
         "merge_grant_committed_count",
         "merge_grant_consumed_count",
         "merge_grant_inflight_fault_generation_recovery_count",
         "merge_grant_expired_count",
         "merge_grant_revoked_count",
         "merge_grant_revoked_fault_count",
         "merge_grant_revoked_stale_state_count",
         "merge_grant_rolled_back_count",
         "merge_grant_post_commit_revoked_count",
         "merge_grant_post_commit_expired_count",
         "merge_grant_post_commit_rollback_count",
         "merge_grant_terminal_request_count",
         "merge_grant_outstanding_request_count",
         "merge_grant_lifecycle_transition_count",
         "merge_grant_lifecycle_dropped_count",
         "g4irsf18_merge_policy_mode",
         "g4irsf18_merge_artifact_valid",
         "g4irsf18_merge_artifact_production_closed_loop_authorized",
         "g4irsf18_merge_production_promotion_authorized",
         "g4irsf18_merge_deployment_status",
         "g4irsf18_merge_model_opportunity_count",
         "g4irsf18_merge_model_eligible_count",
         "g4irsf18_merge_model_proposal_count",
         "g4irsf18_merge_model_applied_count",
         "g4irsf18_merge_model_ownership_count",
         "g4irsf18_merge_model_ownership_rate",
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
         "g4irsf18_merge_coverage_eligible_seen_count")
    )
)


def _algorithmic_safety(hard_safety: Mapping[str, Any]) -> bool:
    gates = hard_safety.get("gates", {})
    if not isinstance(gates, Mapping):
        return False
    capacity = {
        "all_segments_completed",
        "failed_zero",
        "event_limit_not_reached",
        "time_limit_not_reached",
    }
    selected = [value for name, value in gates.items() if name not in capacity]
    return bool(selected) and all(value is True for value in selected)


def _capacity_attribution(result: Mapping[str, Any]) -> dict[str, Any]:
    counters = result.get("counters", {})
    metrics = result.get("metrics", {})
    input_descriptor = result.get("input", {})
    requested = _integer(metrics.get("requested_segments"))
    if requested is None and isinstance(input_descriptor, Mapping):
        requested = _integer(input_descriptor.get("segments"))
    completed = _integer(counters.get("completed_count"))
    event_limited = counters.get("event_limit_reached") is True
    time_limited = counters.get("time_limit_reached") is True
    pending_peak = _integer(counters.get("merge_grant_peak_pending_requests"))
    if result.get("status") == "WORKER_TIMEOUT_CENSORED":
        cause = "WORKER_WALL_TIMEOUT"
        completed = None
    elif event_limited:
        cause = "EVENT_LIMIT"
    elif time_limited:
        cause = "SIMULATION_TIME_LIMIT"
    elif completed is None or requested is None or completed < requested:
        cause = "INCOMPLETE_WITHOUT_DECLARED_CAP"
    else:
        cause = "COMPLETE_NO_CAPACITY_CENSORING"
    return {
        "capacity_censored": cause != "COMPLETE_NO_CAPACITY_CENSORING",
        "primary_cause": cause,
        "requested_segments": requested,
        "completed_segments": completed,
        "completion_rate": (
            completed / requested
            if completed is not None and requested not in (None, 0)
            else None
        ),
        "event_count": counters.get("event_count"),
        "declared_max_events": counters.get("declared_max_events"),
        "pending_peak": pending_peak,
    }


def execute_job(
    job: SystemJob,
    arm: Arm,
    *,
    binary: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    from czr005 import cpp_backend
    from scripts.eval.g4irsf11_fixed_map import assert_canonical_map, canonical_graph_records
    from scripts.eval.g4irsf14_opportunity_census import FROZEN_RUNTIME_CONTROLS, MODEL_PATH

    rows, descriptor = _load_input(job, root)
    descriptor = {**descriptor, "telemetry_mode": job.telemetry_mode}
    _require(descriptor["topology_changed"] is False, "scale input changed topology")
    fault_windows, fault_descriptor = _fault_windows(job.fault_scenario, rows)
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    resolved_binary = binary.resolve(strict=True)
    telemetry_enabled = job.telemetry_mode == "evidence_trace"
    telemetry_limit = EVIDENCE_TRACE_LIMIT if telemetry_enabled else 0
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=jit._binding_rows(rows),
        fault_windows=fault_windows,
        scenario=f"g4irsf18_system_{job.job_id}",
        summary_only=False,
        trace_limit=0,
        event_trace_limit=0,
        enable_opportunity_telemetry=telemetry_enabled,
        opportunity_trace_limit=telemetry_limit,
        scorer_model_path=(root / MODEL_PATH).resolve(strict=True),
        search_path=resolved_binary.parent,
        g4irsf16_supervisor_mode="off",
        merge_grant_rule=arm.merge_rule,
        merge_grant_timing_mode=arm.timing_mode,
    )
    controls = dict(arm.native_controls or {})
    forbidden = {
        "node_records", "edge_records", "heuristic_time", "bag_records",
        "fault_windows", "scenario", "search_path", "expected_binary_path",
        "merge_grant_timing_mode", "merge_grant_rule",
    }
    _require(not (set(controls) & forbidden), "learned arm overrides frozen job identity")
    if arm.learned:
        _require(arm.research_closed_loop_authorized, "learned research grant missing")
        _require(not arm.production_closed_loop_authorized, "production learned arm not allowed here")
    signature = inspect.signature(cpp_backend.g4irsf11_event_runtime_from_records)
    unsupported = sorted(set(controls) - set(signature.parameters))
    _require(not unsupported, f"native wrapper lacks learned controls: {unsupported}")
    request.update(controls)

    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    cpu_seconds = time.process_time() - cpu_start
    wall_seconds = time.perf_counter() - wall_start
    _require(isinstance(payload, Mapping), "native payload is not an object")
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    _require(summary.get("merge_grant_timing_mode") == arm.timing_mode, "timing echo drift")

    raw = jit._raw_bags(rows, payload, str(descriptor["tth_denominator"]))
    completed = [row for row in raw if row["complete"]]
    tth = [float(row["tth_seconds"]) for row in completed]
    source = [float(row["source_wait_seconds"]) for row in completed]
    merge = [float(row["merge_grant_wait_seconds"]) for row in completed]
    network = [float(row["network_time_seconds"]) for row in completed]
    counters = {name: summary.get(name) for name in EXTENDED_COUNTERS}
    opportunity_rows = payload.get("merge_service_opportunities", [])
    _require(isinstance(opportunity_rows, list), "native opportunity trace is not a list")
    stored_opportunities = _integer(
        summary.get("merge_grant_opportunity_trace_stored_count")
    )
    _require(
        stored_opportunities is None or stored_opportunities == len(opportunity_rows),
        "native opportunity stored-count identity failed",
    )
    if not telemetry_enabled:
        _require(not opportunity_rows, "capacity mode unexpectedly retained trace rows")
    safety = jit._hard_safety(summary, len(rows))
    event_count = _integer(summary.get("event_count"))
    service_count = _integer(summary.get("merge_grant_service_opportunity_count"))
    raw_count = len(raw)
    all_complete = len(completed) == raw_count
    if safety["pass"] and all_complete:
        status = "COMPLETE"
    elif summary.get("event_limit_reached") is True:
        status = "CAPACITY_CENSORED_EVENT_LIMIT"
    elif summary.get("time_limit_reached") is True:
        status = "CAPACITY_CENSORED_SIMULATION_TIME"
    else:
        status = "HARD_GATE_FAILED"
    result: dict[str, Any] = {
        "schema": SCHEMA_RESULT,
        "job": job.as_dict(),
        "arm": arm.as_dict(),
        "status": status,
        "input": descriptor,
        "telemetry": {
            "mode": job.telemetry_mode,
            "enabled": telemetry_enabled,
            "trace_limit": telemetry_limit,
            "total_count": summary.get("merge_grant_opportunity_trace_total_count"),
            "stored_count": stored_opportunities,
            "dropped_count": summary.get("merge_grant_opportunity_trace_dropped_count"),
            "core_counters_retained": True,
        },
        "fault": fault_descriptor,
        "resources": {"wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds},
        "hard_safety": safety,
        "algorithmic_safety_pass": _algorithmic_safety(safety),
        "metrics": {
            "requested_segments": len(rows),
            "raw_bag_count": raw_count,
            "complete_raw_bag_count": len(completed),
            "mean_tth_seconds": statistics.fmean(tth) if all_complete and tth else None,
            "p95_tth_seconds": jit._quantile(tth, 0.95) if all_complete else None,
            "p99_tth_seconds": jit._quantile(tth, 0.99) if all_complete else None,
            "source_wait_mean_seconds": statistics.fmean(source) if all_complete and source else None,
            "merge_grant_wait_mean_seconds": statistics.fmean(merge) if all_complete and merge else None,
            "network_time_mean_seconds": statistics.fmean(network) if all_complete and network else None,
            "events_per_requested_segment": event_count / len(rows) if event_count is not None else None,
            "events_per_raw_bag": event_count / raw_count if event_count is not None and raw_count else None,
            "wakeups_per_service_opportunity": (
                _integer(summary.get("merge_grant_wakeup_scheduled_count")) / service_count
                if service_count not in (None, 0)
                and _integer(summary.get("merge_grant_wakeup_scheduled_count")) is not None
                else None
            ),
        },
        "counters": counters,
    }
    if telemetry_enabled:
        result["_opportunity_rows"] = opportunity_rows
    result["capacity"] = _capacity_attribution(result)
    return result


def _result_path(results_dir: Path, job: SystemJob) -> Path:
    return results_dir / f"{job.job_id}.json"


def _fallback_jit_path(root: Path, job: SystemJob) -> Path | None:
    if job.stage != "ladder" or job.arm_id not in BUILTIN_ARM_BY_ID:
        return None
    return root / DEFAULT_JIT_RESULTS.relative_to(ROOT) / f"{job.job_id}.json"


def _existing_result_path(results_dir: Path, root: Path, job: SystemJob) -> Path | None:
    primary = _result_path(results_dir, job)
    if primary.is_file():
        value = _read_json(primary)
        if value.get("schema") == SCHEMA_RESULT and value.get("job") == job.as_dict():
            return primary
    fallback = _fallback_jit_path(root, job)
    return fallback if fallback is not None and fallback.is_file() else None


def record_timeout_observation(
    plan: Mapping[str, Any],
    *,
    job_id: str,
    results_dir: Path,
    wrapper_wall_limit_seconds: float,
    observed_cpu_lower_bound_seconds: float,
    observed_rss_bytes: int,
    observed_pid: int,
    started_at_local: str,
    observation_window_return_seconds: float | None = None,
    root: Path = ROOT,
    force: bool = False,
) -> dict[str, Any]:
    validated = validate_plan(plan)
    jobs = [SystemJob.from_mapping(row) for row in validated["jobs"]]
    matches = [job for job in jobs if job.job_id == job_id]
    _require(len(matches) == 1, f"unknown timeout job: {job_id}")
    job = matches[0]
    _require(job.stage == "scale" and job.scale == 4, "timeout record is frozen to 4x scale")
    _require(wrapper_wall_limit_seconds > 0.0, "wall limit must be positive")
    _require(observed_cpu_lower_bound_seconds >= 0.0, "CPU lower bound is negative")
    _require(observed_rss_bytes > 0, "observed RSS must be positive")
    _require(observed_pid > 0, "observed PID must be positive")
    _require(bool(started_at_local.strip()), "process start observation is required")
    path = _result_path(results_dir, job)
    _require(force or not path.exists(), f"timeout result already exists: {path}")
    requested = 43_603 * job.scale
    arm = _arm_map(validated)[job.arm_id]
    result: dict[str, Any] = {
        "schema": SCHEMA_RESULT,
        "job": job.as_dict(),
        "arm": arm.as_dict(),
        "status": "WORKER_TIMEOUT_CENSORED",
        "input": {
            "protocol": "g4irsf10_distribution_preserving_fixed_map_resample",
            "segments": requested,
            "scale": job.scale,
            "smoke_capped": False,
            "topology_changed": False,
            "tth_denominator": "java_release_time_tth",
            "telemetry_mode": job.telemetry_mode,
        },
        "telemetry": {
            "mode": job.telemetry_mode,
            "enabled": False,
            "trace_limit": 0,
            "core_counters_retained": False,
            "reason": "NATIVE_CALL_DID_NOT_RETURN_BEFORE_EXTERNAL_WALL_LIMIT",
        },
        "external_observation": {
            "measurement_source": "verified_windows_process_snapshot",
            "wrapper_wall_limit_seconds": wrapper_wall_limit_seconds,
            "observation_window_return_seconds": observation_window_return_seconds,
            "observed_cpu_lower_bound_seconds": observed_cpu_lower_bound_seconds,
            "observed_rss_bytes": observed_rss_bytes,
            "observed_pid": observed_pid,
            "started_at_local": started_at_local,
            "native_result_returned": False,
            "native_event_cap_observed": False,
            "process_termination_verified": True,
        },
        "resources": {
            "wall_seconds": None,
            "cpu_seconds": None,
            "wrapper_wall_limit_seconds": wrapper_wall_limit_seconds,
            "observed_cpu_lower_bound_seconds": observed_cpu_lower_bound_seconds,
            "observed_rss_bytes": observed_rss_bytes,
            "observed_rss_mb": observed_rss_bytes / (1024.0 * 1024.0),
        },
        "hard_safety": {
            "pass": None,
            "status": "NOT_EVALUABLE_NO_NATIVE_RETURN",
            "gates": {},
        },
        "algorithmic_safety_pass": None,
        "metrics": {"requested_segments": requested},
        "counters": {},
    }
    result["capacity"] = _capacity_attribution(result)
    results_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(path, result)
    return result


def _four_x_wall_boundary_triggered(
    jobs: Sequence[SystemJob],
    *,
    results_dir: Path,
    root: Path,
) -> bool:
    four_x = [job for job in jobs if job.stage == "scale" and job.scale == 4]
    if not four_x:
        return False
    statuses: list[str] = []
    for job in four_x:
        path = _existing_result_path(results_dir, root, job)
        if path is None:
            return False
        statuses.append(str(_read_json(path).get("status")))
    return all(status == "WORKER_TIMEOUT_CENSORED" for status in statuses)


def run_stage(
    plan: Mapping[str, Any],
    *,
    stage: str,
    binary: Path,
    results_dir: Path,
    root: Path = ROOT,
    force: bool = False,
    only_job: str | None = None,
    stop_after: int = 0,
) -> dict[str, Any]:
    validated = validate_plan(plan)
    _require(stage in {"ladder", "scale", "fault", "all"}, "bad stage")
    arms = _arm_map(validated)
    jobs = [SystemJob.from_mapping(row) for row in validated["jobs"]]
    selected = [job for job in jobs if stage == "all" or job.stage == stage]
    if only_job is not None:
        selected = [job for job in selected if job.job_id == only_job]
        _require(bool(selected), f"job not found in selected stage: {only_job}")
    progression_blocked: list[str] = []
    if _four_x_wall_boundary_triggered(jobs, results_dir=results_dir, root=root):
        progression_blocked = [
            job.job_id
            for job in selected
            if job.stage == "scale" and job.scale in {8, 16, OPTIONAL_SMOKE_SCALE}
        ]
        if only_job is not None and progression_blocked:
            raise G18SystemCampaignError(
                f"job blocked by matched 4x external wall boundary: {only_job}"
            )
        blocked = set(progression_blocked)
        selected = [job for job in selected if job.job_id not in blocked]
    results_dir.mkdir(parents=True, exist_ok=True)
    executed: list[str] = []
    resumed: list[str] = []
    failed: list[str] = []
    censored: list[str] = []
    for job in selected:
        existing = _existing_result_path(results_dir, root, job)
        if existing is not None and not force:
            resumed.append(job.job_id)
            existing_status = _read_json(existing).get("status")
            if existing_status == "WORKER_TIMEOUT_CENSORED":
                censored.append(job.job_id)
            elif existing_status not in {
                "COMPLETE",
                "CAPACITY_CENSORED_EVENT_LIMIT",
                "CAPACITY_CENSORED_SIMULATION_TIME",
            }:
                failed.append(job.job_id)
            continue
        if stop_after > 0 and len(executed) >= stop_after:
            break
        try:
            result = execute_job(job, arms[job.arm_id], binary=binary, root=root)
        except Exception as exc:
            result = {
                "schema": SCHEMA_RESULT,
                "job": job.as_dict(),
                "arm": arms[job.arm_id].as_dict(),
                "status": "ERROR",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        opportunity_rows = result.pop("_opportunity_rows", None)
        if isinstance(opportunity_rows, list):
            try:
                opportunity_path, codec = _write_opportunity_trace(
                    _result_path(results_dir, job), opportunity_rows
                )
            except Exception as exc:
                result["status"] = "TRACE_PERSISTENCE_ERROR"
                result["telemetry"]["artifact_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            else:
                result["telemetry"].update(
                    artifact=_relative(opportunity_path, root),
                    artifact_codec=codec,
                )
        _atomic_json(_result_path(results_dir, job), result)
        executed.append(job.job_id)
        if result.get("status") not in {
            "COMPLETE",
            "CAPACITY_CENSORED_EVENT_LIMIT",
            "CAPACITY_CENSORED_SIMULATION_TIME",
        }:
            failed.append(job.job_id)
    return {
        "stage": stage,
        "selected_count": len(selected),
        "executed": executed,
        "resumed": resumed,
        "failed": failed,
        "censored": censored,
        "progression_blocked": progression_blocked,
        "incremental_complete": len(executed) + len(resumed) == len(selected),
    }


def _normalize_result(result: Mapping[str, Any], job: SystemJob) -> dict[str, Any]:
    metrics = dict(result.get("metrics", {}))
    counters = dict(result.get("counters", {}))
    hard = result.get("hard_safety", {})
    algorithmic = result.get("algorithmic_safety_pass")
    if "algorithmic_safety_pass" not in result and isinstance(hard, Mapping):
        algorithmic = _algorithmic_safety(hard)
    if "events_per_requested_segment" not in metrics:
        metrics["events_per_requested_segment"] = metrics.get(
            "events_per_completed_segment"
        )
    if "events_per_raw_bag" not in metrics:
        events = _integer(counters.get("event_count"))
        raw_count = _integer(metrics.get("raw_bag_count"))
        metrics["events_per_raw_bag"] = (
            events / raw_count if events is not None and raw_count else None
        )
    capacity = result.get("capacity")
    if not isinstance(capacity, Mapping):
        proxy = {**dict(result), "metrics": metrics, "counters": counters}
        capacity = _capacity_attribution(proxy)
    return {
        "job": job,
        "status": result.get("status"),
        "metrics": metrics,
        "counters": counters,
        "hard_safety_pass": hard.get("pass") if isinstance(hard, Mapping) else None,
        "algorithmic_safety_pass": algorithmic,
        "capacity": dict(capacity),
        "resources": dict(result.get("resources", {})),
        "fault": dict(result.get("fault", {})),
        "telemetry": dict(
            result.get(
                "telemetry",
                {
                    "mode": job.telemetry_mode,
                    "enabled": job.telemetry_mode == "evidence_trace",
                    "trace_limit": (
                        EVIDENCE_TRACE_LIMIT
                        if job.telemetry_mode == "evidence_trace"
                        else 0
                    ),
                    "core_counters_retained": True,
                },
            )
        ),
    }


def _mean_delta(row: Mapping[str, Any], baseline: Mapping[str, Any] | None) -> float | None:
    if baseline is None:
        return None
    left = _finite(baseline["metrics"].get("mean_tth_seconds"))
    right = _finite(row["metrics"].get("mean_tth_seconds"))
    return right - left if left is not None and right is not None else None


def _fault_regression(
    row: Mapping[str, Any], control: Mapping[str, Any] | None
) -> dict[str, Any]:
    counters = row["counters"]
    pending = (
        (_integer(counters.get("merge_grant_peak_pending_requests")) or 0) >= 2
        and (_integer(counters.get("merge_grant_multi_candidate_opportunity_count")) or 0) > 0
    )
    inflight = (
        _integer(counters.get("merge_grant_inflight_fault_generation_recovery_count"))
        or 0
    ) > 0
    fault_repair = (
        (_integer(counters.get("fault_event_count")) or 0) > 0
        and (_integer(counters.get("repair_event_count")) or 0) > 0
    )
    exposure = (_integer(counters.get("fault_affected_bag_count")) or 0) > 0
    no_outstanding = _integer(counters.get("merge_grant_outstanding_request_count")) == 0
    job = row["job"]
    scenario = job.fault_scenario or {}
    target_value = scenario.get("validation_target")
    if target_value is None and scenario.get("scenario_id") == PENDING_FAULT_SCENARIO_ID:
        target_value = "pending_wait"
    target = str(target_value or "combined")
    common = (
        exposure,
        fault_repair,
        no_outstanding,
        row["hard_safety_pass"] is True,
    )
    if job.arm_id == "J0_F2_EAGER":
        required_gate = "control_fault_safety"
        passed = all(common)
    elif target == "pending_wait":
        required_gate = "pending_wait"
        passed = all((*common, pending))
    elif target == "inflight_exact_lease":
        required_gate = "inflight_exact_lease"
        passed = all((*common, inflight))
    else:
        required_gate = "combined_pending_and_inflight"
        passed = all((*common, pending, inflight))
    return {
        "validation_target": target,
        "required_gate": required_gate,
        "informative_fault_exposure": exposure,
        "pending_competition_observed": pending,
        "inflight_exact_lease_recovery_observed": inflight,
        "fault_and_repair_events_observed": fault_repair,
        "no_outstanding_merge_request_at_end": no_outstanding,
        "hard_safety_pass": row["hard_safety_pass"] is True,
        "pass": passed,
        "mean_tth_delta_vs_no_fault_seconds": _mean_delta(row, control),
    }


def analyse_campaign(
    plan: Mapping[str, Any],
    *,
    results_dir: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    validated = validate_plan(plan)
    jobs = [SystemJob.from_mapping(row) for row in validated["jobs"]]
    available: dict[str, dict[str, Any]] = {}
    missing: dict[str, list[str]] = {"ladder": [], "scale": [], "fault": []}
    for job in jobs:
        path = _existing_result_path(results_dir, root, job)
        if path is None:
            missing[job.stage].append(job.job_id)
            continue
        result = _read_json(path)
        if result.get("schema") not in {SCHEMA_RESULT, jit.SCHEMA_RESULT}:
            missing[job.stage].append(job.job_id)
            continue
        available[job.job_id] = _normalize_result(result, job)

    scale_arm_ids = {
        job.arm_id for job in jobs if job.stage == "scale" and job.scale == 4
    }
    timed_out_4x_arm_ids = {
        row["job"].arm_id
        for row in available.values()
        if row["job"].stage == "scale"
        and row["job"].scale == 4
        and row["status"] == "WORKER_TIMEOUT_CENSORED"
    }
    wall_boundary_triggered = bool(scale_arm_ids) and timed_out_4x_arm_ids == scale_arm_ids
    blocked_scale_job_ids = [
        job.job_id
        for job in jobs
        if wall_boundary_triggered
        and job.stage == "scale"
        and job.scale in {8, 16, OPTIONAL_SMOKE_SCALE}
    ]
    if blocked_scale_job_ids:
        blocked = set(blocked_scale_job_ids)
        missing["scale"] = [job_id for job_id in missing["scale"] if job_id not in blocked]

    ladder: list[dict[str, Any]] = []
    scale: list[dict[str, Any]] = []
    fault: list[dict[str, Any]] = []
    for job in jobs:
        row = available.get(job.job_id)
        if row is None:
            continue
        baseline: dict[str, Any] | None = None
        fifo_baseline: dict[str, Any] | None = None
        if job.arm_id != "J0_F2_EAGER":
            candidates = [
                value
                for value in available.values()
                if value["job"].stage == job.stage
                and value["job"].arm_id == "J0_F2_EAGER"
                and value["job"].prefix_segments == job.prefix_segments
                and value["job"].scale == job.scale
            ]
            baseline = candidates[0] if candidates else None
        if job.arm_id == "J2_F2_JIT_FAIR_AGING_DEADLINE":
            fifo_candidates = [
                value
                for value in available.values()
                if value["job"].stage == job.stage
                and value["job"].arm_id == "J1_F2_JIT_FIFO"
                and value["job"].prefix_segments == job.prefix_segments
                and value["job"].scale == job.scale
                and (
                    value["job"].fault_scenario or {}
                ).get("scenario_id")
                == (job.fault_scenario or {}).get("scenario_id")
            ]
            fifo_baseline = fifo_candidates[0] if fifo_candidates else None
        common = {
            "job_id": job.job_id,
            "arm_id": job.arm_id,
            "status": row["status"],
            "hard_safety_pass": row["hard_safety_pass"],
            "algorithmic_safety_pass": row["algorithmic_safety_pass"],
            "telemetry_mode": row["telemetry"].get("mode", job.telemetry_mode),
            "telemetry_enabled": row["telemetry"].get("enabled"),
            "mean_tth_delta_vs_j0_seconds": _mean_delta(row, baseline),
            "mean_tth_delta_vs_j1_seconds": _mean_delta(row, fifo_baseline),
            "wall_seconds": row["resources"].get("wall_seconds"),
            "cpu_seconds": row["resources"].get("cpu_seconds"),
            "wrapper_wall_limit_seconds": row["resources"].get(
                "wrapper_wall_limit_seconds"
            ),
            "observed_cpu_lower_bound_seconds": row["resources"].get(
                "observed_cpu_lower_bound_seconds"
            ),
            "observed_rss_mb": row["resources"].get("observed_rss_mb"),
            **row["metrics"],
            "event_count": row["counters"].get("event_count"),
            "service_opportunity_count": row["counters"].get(
                "merge_grant_service_opportunity_count"
            ),
            "multi_candidate_opportunity_count": row["counters"].get(
                "merge_grant_multi_candidate_opportunity_count"
            ),
            "order_mutation_count": row["counters"].get(
                "merge_grant_order_mutation_count"
            ),
            "wakeup_scheduled_count": row["counters"].get(
                "merge_grant_wakeup_scheduled_count"
            ),
            "wakeup_coalesced_count": row["counters"].get(
                "merge_grant_wakeup_coalesced_count"
            ),
            "stale_wakeup_count": row["counters"].get(
                "merge_grant_stale_wakeup_count"
            ),
            "pending_peak": row["counters"].get(
                "merge_grant_peak_pending_requests"
            ),
        }
        if job.stage == "ladder":
            ladder.append({"segments": job.prefix_segments, **common})
        elif job.stage == "scale":
            scale.append(
                {
                    "scale": job.scale,
                    "smoke_capped": job.max_segments > 0,
                    **common,
                    **{f"capacity_{key}": value for key, value in row["capacity"].items()},
                }
            )
        else:
            control_id = _job_id(
                _arm_map(validated)[job.arm_id],
                "ladder",
                prefix=job.prefix_segments,
            )
            control = available.get(control_id)
            regression = _fault_regression(row, control)
            fault.append(
                {
                    "segments": job.prefix_segments,
                    "scenario_id": job.fault_scenario.get("scenario_id") if job.fault_scenario else None,
                    **common,
                    **{f"fault_{key}": value for key, value in regression.items()},
                    **{
                        name: row["counters"].get(name)
                        for name in EXTENDED_COUNTERS
                        if name.startswith("fault_")
                        or name.startswith("repair_")
                        or name.startswith("merge_grant_inflight")
                        or name == "merge_grant_outstanding_request_count"
                    },
                }
            )

    stage_status = {
        stage: {
            "expected_job_count": sum(job.stage == stage for job in jobs),
            "available_job_count": sum(row["job"].stage == stage for row in available.values()),
            "missing_job_ids": missing[stage],
            "blocked_job_ids": blocked_scale_job_ids if stage == "scale" else [],
            "blocked_reason": (
                "BLOCKED_BY_4X_WALL_BOUNDARY"
                if stage == "scale" and blocked_scale_job_ids
                else None
            ),
            "status": (
                "INCREMENTAL"
                if missing[stage]
                else (
                    "BLOCKED_BY_4X_WALL_BOUNDARY"
                    if stage == "scale" and blocked_scale_job_ids
                    else "COMPLETE"
                )
            ),
        }
        for stage in ("ladder", "scale", "fault")
    }
    analysis = {
        "schema": SCHEMA_ANALYSIS,
        "status": (
            "INCREMENTAL"
            if any(missing.values())
            else (
                "BLOCKED_BY_4X_WALL_BOUNDARY"
                if blocked_scale_job_ids
                else "COMPLETE"
            )
        ),
        "learned_arm": validated.get("learned_arm"),
        "fault_design": validated.get("fault_scenarios", []),
        "stages": stage_status,
        "ladder_rows": sorted(ladder, key=lambda row: (row["segments"], row["arm_id"])),
        "scale_rows": sorted(scale, key=lambda row: (row["scale"], row["arm_id"])),
        "fault_rows": sorted(fault, key=lambda row: (row["scenario_id"], row["arm_id"])),
    }
    _write_outputs(analysis, root=root)
    return analysis


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _missing_section(stage: Mapping[str, Any]) -> list[str]:
    missing = list(stage.get("missing_job_ids", []))
    blocked = list(stage.get("blocked_job_ids", []))
    lines: list[str] = []
    if missing:
        preview = ", ".join(f"`{value}`" for value in missing[:12])
        suffix = f" and {len(missing) - 12} more" if len(missing) > 12 else ""
        lines.extend(
            [
                f"Unrun/missing: {len(missing)} job(s): {preview}{suffix}.",
                "No row or metric is synthesized for these jobs.",
            ]
        )
    if blocked:
        preview = ", ".join(f"`{value}`" for value in blocked[:12])
        suffix = f" and {len(blocked) - 12} more" if len(blocked) > 12 else ""
        lines.extend(
            [
                f"Progression-blocked: {len(blocked)} job(s): {preview}{suffix}.",
                "The matched 4x arms exhausted the external wall boundary without a native return; 8x/16x full and 32x smoke are intentionally not launched and have no synthesized metrics.",
            ]
        )
    return lines or ["All preregistered jobs for this stage have a result artifact."]


def _write_outputs(analysis: Mapping[str, Any], *, root: Path) -> None:
    ladder = list(analysis["ladder_rows"])
    scale = list(analysis["scale_rows"])
    fault = list(analysis["fault_rows"])
    ladder_fields = (
        "segments", "arm_id", "status", "telemetry_mode", "telemetry_enabled",
        "hard_safety_pass", "algorithmic_safety_pass",
        "mean_tth_seconds", "p95_tth_seconds", "p99_tth_seconds",
        "source_wait_mean_seconds", "merge_grant_wait_mean_seconds",
        "network_time_mean_seconds", "mean_tth_delta_vs_j0_seconds",
        "mean_tth_delta_vs_j1_seconds", "wall_seconds", "cpu_seconds",
        "wrapper_wall_limit_seconds", "observed_cpu_lower_bound_seconds",
        "observed_rss_mb",
        "events_per_requested_segment", "events_per_raw_bag",
        "wakeups_per_service_opportunity", "pending_peak",
        "service_opportunity_count", "multi_candidate_opportunity_count",
        "order_mutation_count",
    )
    scale_fields = (
        "scale", "smoke_capped", "arm_id", "status", "telemetry_mode",
        "telemetry_enabled", "hard_safety_pass",
        "algorithmic_safety_pass", "capacity_capacity_censored",
        "capacity_primary_cause", "capacity_requested_segments",
        "capacity_completed_segments", "capacity_completion_rate",
        "capacity_declared_max_events", "mean_tth_delta_vs_j0_seconds",
        "mean_tth_delta_vs_j1_seconds", "wall_seconds", "cpu_seconds",
        "wrapper_wall_limit_seconds", "observed_cpu_lower_bound_seconds",
        "observed_rss_mb",
        "mean_tth_seconds", "p95_tth_seconds", "p99_tth_seconds",
        "source_wait_mean_seconds", "merge_grant_wait_mean_seconds",
        "network_time_mean_seconds", "events_per_requested_segment",
        "events_per_raw_bag", "wakeups_per_service_opportunity", "pending_peak",
        "event_count", "wakeup_scheduled_count", "wakeup_coalesced_count",
        "stale_wakeup_count",
    )
    fault_fields = (
        "segments", "scenario_id", "arm_id", "status", "telemetry_mode",
        "telemetry_enabled", "hard_safety_pass",
        "fault_validation_target", "fault_required_gate",
        "fault_informative_fault_exposure", "fault_pending_competition_observed",
        "fault_inflight_exact_lease_recovery_observed",
        "fault_fault_and_repair_events_observed",
        "fault_no_outstanding_merge_request_at_end", "fault_pass",
        "fault_mean_tth_delta_vs_no_fault_seconds",
        "fault_event_count", "repair_event_count", "fault_affected_bag_count",
        "fault_affected_completed_count",
        "merge_grant_inflight_fault_generation_recovery_count",
        "merge_grant_outstanding_request_count", "pending_peak",
        "mean_tth_seconds", "p95_tth_seconds", "events_per_raw_bag",
    )
    _write_csv(root / LADDER_TABLE.relative_to(ROOT), ladder, ladder_fields)
    _write_csv(root / SCALE_TABLE.relative_to(ROOT), scale, scale_fields)
    _write_csv(root / FAULT_TABLE.relative_to(ROOT), fault, fault_fields)

    ladder_stage = analysis["stages"]["ladder"]
    ladder_lines = [
        "# G4IRSF18 closed-loop ladder",
        "",
        f"Status: **`{ladder_stage['status']}`** "
        f"({ladder_stage['available_job_count']}/{ladder_stage['expected_job_count']} jobs).",
        "",
        "J0/J1/J2 are real native arms. Prefixes through 8,192 use evidence-trace mode; 43,603 uses capacity mode with opportunity rows disabled. A learned row appears only after an explicit research-only arm configuration passes validation.",
        "",
        "| Segments | Arm | Mode | Status | Hard safety | Mean TTH s | P95 s | Source s | Merge s | Network s | Events/bag | Wakeups/opportunity | Pending peak | Mutations |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in ladder:
        ladder_lines.append(
            f"| {row['segments']} | {row['arm_id']} | {row['telemetry_mode']} | {row['status']} | {row['hard_safety_pass']} | "
            f"{_fmt(row.get('mean_tth_seconds'))} | {_fmt(row.get('p95_tth_seconds'))} | "
            f"{_fmt(row.get('source_wait_mean_seconds'))} | {_fmt(row.get('merge_grant_wait_mean_seconds'))} | "
            f"{_fmt(row.get('network_time_mean_seconds'))} | {_fmt(row.get('events_per_raw_bag'))} | "
            f"{_fmt(row.get('wakeups_per_service_opportunity'))} | {row.get('pending_peak', '—')} | "
            f"{row.get('order_mutation_count', '—')} |"
        )
    ladder_lines.extend(["", "## Incremental boundary", "", *_missing_section(ladder_stage)])
    _atomic_text(root / LADDER_REPORT.relative_to(ROOT), "\n".join(ladder_lines) + "\n")

    scale_stage = analysis["stages"]["scale"]
    scale_lines = [
        "# G4IRSF18 scale capacity",
        "",
        f"Status: **`{scale_stage['status']}`** "
        f"({scale_stage['available_job_count']}/{scale_stage['expected_job_count']} jobs).",
        "",
        "1x–16x use the complete G10 distribution-preserving stream. 32x is an explicit 8,192-segment smoke. Every launched scale row uses capacity mode (opportunity rows disabled). A wall-censored row is a resource-boundary observation: it is never ranked as a performance win and does not adjudicate algorithm safety.",
        "",
        "| Scale | Arm | Scope | Status | Capacity cause | Completed | Algorithm safety | Mean TTH s | Δ vs J0 s | Δ vs J1 s | Events/bag | Pending peak | Wall s | Wall cap s | CPU lower bound s | RSS MB |",
        "|---:|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in scale:
        scope = "smoke" if row["smoke_capped"] else "full"
        completed_value = row.get("capacity_completed_segments")
        completed = (
            f"{completed_value}/{row.get('capacity_requested_segments')}"
            if completed_value is not None
            else f"—/{row.get('capacity_requested_segments')}"
        )
        scale_lines.append(
            f"| {row['scale']}x | {row['arm_id']} | {scope} | {row['status']} | "
            f"{row.get('capacity_primary_cause')} | {completed} | {row['algorithmic_safety_pass']} | "
            f"{_fmt(row.get('mean_tth_seconds'))} | {_fmt(row.get('mean_tth_delta_vs_j0_seconds'))} | "
            f"{_fmt(row.get('mean_tth_delta_vs_j1_seconds'))} | {_fmt(row.get('events_per_raw_bag'))} | "
            f"{row.get('pending_peak') if row.get('pending_peak') is not None else '—'} | "
            f"{_fmt(row.get('wall_seconds'), 3)} | {_fmt(row.get('wrapper_wall_limit_seconds'), 3)} | "
            f"{_fmt(row.get('observed_cpu_lower_bound_seconds'), 3)} | {_fmt(row.get('observed_rss_mb'), 3)} |"
        )
    scale_lines.extend(["", "## Incremental boundary", "", *_missing_section(scale_stage)])
    _atomic_text(root / SCALE_REPORT.relative_to(ROOT), "\n".join(scale_lines) + "\n")

    fault_stage = analysis["stages"]["fault"]
    fault_lines = [
        "# G4IRSF18 fault/repair campaign",
        "",
        f"Status: **`{fault_stage['status']}`** "
        f"({fault_stage['available_job_count']}/{fault_stage['expected_job_count']} jobs).",
        "",
        "The 35% window validates pending-wait preservation. A second, evidence-directed window targets the midpoint of an observed edge-(6,12) grant flight and validates exact-lease recovery. J0 is the fault-safety control; J1/J2 carry the mechanism gates.",
        "",
        "| Scenario | Arm | Gate | Status | Exposure | Pending | In-flight lease | Fault+repair | Outstanding=0 | Hard safety | Regression | TTH delta vs no-fault s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---:|",
    ]
    for row in fault:
        fault_lines.append(
            f"| {row['scenario_id']} | {row['arm_id']} | {row.get('fault_required_gate')} | "
            f"{row['status']} | {row.get('fault_informative_fault_exposure')} | "
            f"{row.get('fault_pending_competition_observed')} | "
            f"{row.get('fault_inflight_exact_lease_recovery_observed')} | "
            f"{row.get('fault_fault_and_repair_events_observed')} | "
            f"{row.get('fault_no_outstanding_merge_request_at_end')} | "
            f"{row.get('hard_safety_pass')} | {row.get('fault_pass')} | "
            f"{_fmt(row.get('fault_mean_tth_delta_vs_no_fault_seconds'))} |"
        )
    fault_lines.extend(["", "## Incremental boundary", "", *_missing_section(fault_stage)])
    _atomic_text(root / FAULT_REPORT.relative_to(ROOT), "\n".join(fault_lines) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--root", type=Path, default=ROOT)
    plan.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    plan.add_argument("--learned-arm", type=Path)
    plan.add_argument("--smoke-32x-segments", type=int, default=DEFAULT_32X_SMOKE_SEGMENTS)
    run = sub.add_parser("run")
    run.add_argument("--root", type=Path, default=ROOT)
    run.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    run.add_argument("--stage", choices=("ladder", "scale", "fault", "all"), required=True)
    run.add_argument("--only-job")
    run.add_argument("--stop-after", type=int, default=0)
    run.add_argument("--force", action="store_true")
    timeout = sub.add_parser("record-timeout")
    timeout.add_argument("--root", type=Path, default=ROOT)
    timeout.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    timeout.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    timeout.add_argument("--job", required=True)
    timeout.add_argument("--wrapper-wall-limit-seconds", type=float, required=True)
    timeout.add_argument("--observed-cpu-lower-bound-seconds", type=float, required=True)
    timeout.add_argument("--observed-rss-bytes", type=int, required=True)
    timeout.add_argument("--observed-pid", type=int, required=True)
    timeout.add_argument("--started-at-local", required=True)
    timeout.add_argument("--observation-window-return-seconds", type=float)
    timeout.add_argument("--force", action="store_true")
    report = sub.add_parser("report")
    report.add_argument("--root", type=Path, default=ROOT)
    report.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    report.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    report.add_argument("--output", type=Path, default=DEFAULT_ANALYSIS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "plan":
            learned, note = load_learned_arm(
                _resolve(root, args.learned_arm) if args.learned_arm else None
            )
            value = build_plan(
                root=root,
                learned_arm=learned,
                learned_note=note,
                smoke_32x_segments=args.smoke_32x_segments,
            )
            output = _resolve(root, args.output)
            _atomic_json(output, value)
            print(json.dumps({"plan": _relative(output, root), "jobs": len(value["jobs"])}))
            return 0

        plan = validate_plan(_read_json(_resolve(root, args.plan)))
        if args.command == "record-timeout":
            result = record_timeout_observation(
                plan,
                job_id=args.job,
                results_dir=_resolve(root, args.results_dir),
                wrapper_wall_limit_seconds=args.wrapper_wall_limit_seconds,
                observed_cpu_lower_bound_seconds=args.observed_cpu_lower_bound_seconds,
                observed_rss_bytes=args.observed_rss_bytes,
                observed_pid=args.observed_pid,
                started_at_local=args.started_at_local,
                observation_window_return_seconds=args.observation_window_return_seconds,
                root=root,
                force=args.force,
            )
            print(
                json.dumps(
                    {
                        "job": args.job,
                        "status": result["status"],
                        "capacity_cause": result["capacity"]["primary_cause"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "run":
            result = run_stage(
                plan,
                stage=args.stage,
                binary=_resolve(root, args.binary),
                results_dir=_resolve(root, args.results_dir),
                root=root,
                force=args.force,
                only_job=args.only_job,
                stop_after=args.stop_after,
            )
            print(json.dumps(result, sort_keys=True))
            return 2 if result["failed"] else 0

        analysis = analyse_campaign(
            plan,
            results_dir=_resolve(root, args.results_dir),
            root=root,
        )
        output = _resolve(root, args.output)
        _atomic_json(output, analysis)
        print(
            json.dumps(
                {
                    "analysis": _relative(output, root),
                    "status": analysis["status"],
                    "stage_status": {
                        key: value["status"] for key, value in analysis["stages"].items()
                    },
                },
                sort_keys=True,
            )
        )
        return 0
    except (G18SystemCampaignError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G18 system campaign failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

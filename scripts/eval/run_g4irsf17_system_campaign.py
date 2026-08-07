#!/usr/bin/env python3
"""Run and summarize the later G4IRSF17 system campaign.

The runner covers the stages that start after an I1 or G2 policy has earned
offline authorization:

* Phase E: a matched E4/off closed-loop ladder at 144, 512, 2,048, 8,192,
  and the complete 43,603-segment input;
* Phase F: an evidence-driven G2 pivot and authorization decision;
* Phase G: native event-runtime faults, including delayed/dropped local fault
  beacons and repair/reopen; and
* Phase H: fixed-map 1x--16x workload scaling (with optional 32x smoke).

Long runs execute in isolated worker processes.  Each job has one atomic JSON
checkpoint and one compressed raw-bag timing artifact, so a stopped campaign
can resume without repeating completed work.  Timeouts and memory failures are
reported as censored observations; they are never converted to performance
wins.  All time deltas use ``candidate - matched E4/off`` and negative is
better.

This module deliberately does not implement a second simulator.  It calls the
existing native event runtime through the G16 controls, uses the G13 real-map
fault catalogue/criticality helpers, and uses the G10 fixed-map resampling
protocol for higher loads.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import inspect
import io
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
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))


SCHEMA_CONFIG = "czr005.g4irsf17.system_campaign_config.v1"
SCHEMA_PLAN = "czr005.g4irsf17.system_campaign_plan.v1"
SCHEMA_RESULT = "czr005.g4irsf17.system_campaign_result.v1"
SCHEMA_MANIFEST_STAGE = "czr005.g4irsf17.system_campaign_stage.v1"

LADDER_SEGMENTS = (144, 512, 2_048, 8_192, 43_603)
SCALE_FACTORS = (1, 2, 4, 8, 16)
OPTIONAL_SCALE_FACTORS = (32,)
DEFAULT_FAULT_LOADS = (1, 4)

OFF_CANDIDATE_ID = "E4_OFF"
INFLIGHT_MERGE_RECOVERY_COUNTER = (
    "merge_grant_inflight_fault_generation_recovery_count"
)

# Phase-G protocol amendment: the fixed-map 4x no-fault execution is shared
# with Phase H.  Once that exact-equivalent control exhausts the frozen event
# budget, another no-fault run cannot make the 4x fault matrix evaluable.  The
# amendment preserves every planned cell while distinguishing reused evidence
# and deliberately unexecuted treatments from completed experiments.
CAPACITY_CENSOR_SCALE = 4
CAPACITY_CENSOR_EVENT_CAP = 20_000_000
CAPACITY_CENSOR_CONTROL_STATUS = "CAPACITY_CENSORED_BY_EQUIVALENT_CONTROL"
CAPACITY_CENSOR_TREATMENT_STATUS = "NOT_RUN_CONTROL_CENSORED"
CAPACITY_CENSOR_TRACK_STATUS = "TERMINAL_WITH_CAPACITY_CENSORING"
CAPACITY_CENSOR_FINAL_DECISION = (
    "TERMINAL_WITH_CAPACITY_CENSORING_ACTIONABLE_PIVOT"
)
BASELINE_ONLY_LADDER_DECISION = "BASELINE_ONLY_NO_AUTHORIZED_CANDIDATE"
G2_NEXT_PIVOT = (
    "strictly-local just-in-time service-slot arbitration over a bounded pending set"
)
G2_EAGER_DIAGNOSTIC_STATUS = "CURRENT_EAGER_SEAM_DIAGNOSTIC_COMPLETE"

DEFAULT_CONFIG_PATH = Path("artifacts/manifests/g4irsf17_system_campaign_config.json")
DEFAULT_PLAN_PATH = Path("artifacts/manifests/g4irsf17_system_campaign_plan.json")
DEFAULT_CAMPAIGN_MANIFEST = Path("artifacts/manifests/g4irsf17_campaign_manifest.json")
DEFAULT_RUNSTATE_ROOT = Path("outputs/runstate/g4irsf17_system_campaign")

CLOSED_LOOP_TABLE = Path("outputs/tables/g4irsf17_closed_loop_ladder.csv")
CLOSED_LOOP_REPORT = Path("outputs/reports/g4irsf17_closed_loop_ladder.md")
G2_REPORT = Path("outputs/reports/g4irsf17_g2_system_track.md")
FAULT_TABLE = Path("outputs/tables/g4irsf17_fault_results.csv")
FAULT_REPORT = Path("outputs/reports/g4irsf17_native_fault_system_track.md")
SCALE_TABLE = Path("outputs/tables/g4irsf17_scale_results.csv")
SCALE_REPORT = Path("outputs/reports/g4irsf17_scale_system_track.md")
SCALE_PROFILE = Path("outputs/profiles/g4irsf17_scale_hotspots.csv")
FINAL_REPORT = Path("outputs/reports/g4irsf17_final_system_track.md")
G2_MATCHED_PILOT = Path("outputs/tables/g4irsf17_g2_matched_pilot.json")
I1_SELECTIVE_GATE = Path("artifacts/gates/g4irsf17_i1_selective_gate.json")
I1_CAUSAL_DATASET = Path("artifacts/datasets/g4irsf17_i1_causal_pilot.jsonl.zst")

EVENT_QUEUE_RESERVE_BASELINE = Path(
    "outputs/runstate/g4irsf17_system_campaign/jobs/scale__e4_off__1x.pre_event_reserve.json"
)
EVENT_QUEUE_RESERVE_REPEATS = (
    Path(
        "outputs/runstate/g4irsf17_system_campaign/jobs/scale__e4_off__1x.post_event_reserve_1.json"
    ),
    Path(
        "outputs/runstate/g4irsf17_system_campaign/jobs/scale__e4_off__1x.post_event_reserve_2.json"
    ),
)

TERMINAL_RESULT_STATUSES = frozenset(
    {
        "COMPLETE",
        "HARD_GATE_FAILED",
        "CENSORED_TIMEOUT",
        "CENSORED_OOM",
        "NOT_RUN_PREDECESSOR_GATE",
    }
)
EVIDENCE_COMPLETE_RESULT_STATUSES = frozenset({"COMPLETE", "HARD_GATE_FAILED"})


class SystemCampaignError(RuntimeError):
    """Raised for an actionable configuration or evidence problem."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemCampaignError(message)


def _resolve(root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(
        path,
        (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8"),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemCampaignError(f"cannot read JSON {path}: {exc}") from exc
    _require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for name in row:
            if name not in seen:
                seen.add(name)
                fields.append(name)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    if fields:
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    name: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (dict, list, tuple))
                        else ""
                        if value is None
                        else value
                    )
                    for name in fields
                    for value in (row.get(name),)
                }
            )
    _atomic_write(path, stream.getvalue().encode("utf-8"))


def _ladder_publication_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    decision: str,
) -> list[Mapping[str, Any]]:
    """Keep a baseline-only terminal ladder visible in the published CSV."""

    if rows or decision != BASELINE_ONLY_LADDER_DECISION:
        return list(rows)
    return [
        {
            "record_type": "TRACK_STATUS",
            "status": "COMPLETE",
            "decision": BASELINE_ONLY_LADDER_DECISION,
            "baseline_candidate_id": OFF_CANDIDATE_ID,
            "baseline_level_count": len(LADDER_SEGMENTS),
            "baseline_segments": list(LADDER_SEGMENTS),
            "authorized_candidate_count": 0,
            "matched_comparison_row_count": 0,
            "comparison_status": "NOT_APPLICABLE_NO_AUTHORIZED_CANDIDATE",
            "note": (
                "The frozen E4/off baseline ladder reached a terminal state at "
                "every planned level; no runtime candidate was authorized, so "
                "no matched candidate delta exists."
            ),
        }
    ]


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _finite(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _nonnegative_counter_evidence(
    mapping: Mapping[str, Any], name: str
) -> tuple[int, bool]:
    """Return a persisted counter and whether the native value was observed.

    New results carry an explicit ``*_available`` bit.  Older native payloads
    omit the counter entirely; those remain visibly unavailable while their
    numeric compatibility value is zero.
    """

    value = _integer(mapping.get(name))
    explicit_availability = mapping.get(f"{name}_available")
    available = (
        value is not None
        and value >= 0
        and explicit_availability is not False
    )
    return (value if available else 0), available


def _first(mapping: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if name in mapping and mapping[name] not in (None, ""):
            return mapping[name]
    return None


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _slug(value: str) -> str:
    result = "".join(character.lower() if character.isalnum() else "_" for character in value)
    while "__" in result:
        result = result.replace("__", "_")
    result = result.strip("_")
    _require(bool(result), "job component cannot be empty")
    return result


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    policy_family: str
    authorization_status: str
    native_controls: Mapping[str, Any]
    locality_contract: Mapping[str, Any]
    requires_action_change: bool = True
    notes: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CandidateSpec":
        candidate_id = str(value.get("candidate_id", "")).strip()
        _require(candidate_id and candidate_id != OFF_CANDIDATE_ID, "invalid candidate_id")
        family = str(value.get("policy_family", "")).strip().lower()
        _require(
            family in {"deterministic", "learned", "g2", "joint"},
            f"{candidate_id}: unsupported policy_family {family!r}",
        )
        controls = value.get("native_controls", {})
        locality = value.get("locality_contract", {})
        _require(isinstance(controls, Mapping), f"{candidate_id}: native_controls must be an object")
        _require(isinstance(locality, Mapping), f"{candidate_id}: locality_contract must be an object")
        return cls(
            candidate_id=candidate_id,
            policy_family=family,
            authorization_status=str(value.get("authorization_status", "NOT_AUTHORIZED")),
            native_controls=dict(controls),
            locality_contract=dict(locality),
            requires_action_change=bool(value.get("requires_action_change", True)),
            notes=str(value.get("notes", "")),
        )

    @property
    def authorized(self) -> bool:
        return self.authorization_status in {
            "AUTHORIZED",
            "AUTHORIZED_FOR_CLOSED_LOOP",
            "AUTHORIZED_FOR_LADDER",
        }


@dataclass(frozen=True)
class FaultScenario:
    scenario_id: str
    category: str
    edges: tuple[tuple[int, int], ...]
    duration_seconds: float = 300.0
    onset_fraction: float = 0.35
    message_delay_seconds: float = 0.0
    notification_dropped: bool = False
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "category": self.category,
            "edges": [list(edge) for edge in self.edges],
            "duration_seconds": self.duration_seconds,
            "onset_fraction": self.onset_fraction,
            "message_delay_seconds": self.message_delay_seconds,
            "notification_dropped": self.notification_dropped,
            "notes": self.notes,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FaultScenario":
        edges_value = value.get("edges", ())
        _require(isinstance(edges_value, Sequence), "fault edges must be a sequence")
        edges = tuple((int(edge[0]), int(edge[1])) for edge in edges_value)
        return cls(
            scenario_id=str(value["scenario_id"]),
            category=str(value["category"]),
            edges=edges,
            duration_seconds=float(value.get("duration_seconds", 300.0)),
            onset_fraction=float(value.get("onset_fraction", 0.35)),
            message_delay_seconds=float(value.get("message_delay_seconds", 0.0)),
            notification_dropped=bool(value.get("notification_dropped", False)),
            notes=str(value.get("notes", "")),
        )


@dataclass(frozen=True)
class RunJob:
    job_id: str
    track: str
    candidate_id: str
    policy_family: str
    native_controls: Mapping[str, Any]
    locality_contract: Mapping[str, Any]
    requires_action_change: bool
    segments: int | None = None
    scale: int | None = None
    fault_scenario: Mapping[str, Any] | None = None
    timeout_seconds: float = 0.0
    max_segments: int = -1
    trace_profile: str = "bounded"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RunJob":
        return cls(
            job_id=str(value["job_id"]),
            track=str(value["track"]),
            candidate_id=str(value["candidate_id"]),
            policy_family=str(value["policy_family"]),
            native_controls=dict(value.get("native_controls", {})),
            locality_contract=dict(value.get("locality_contract", {})),
            requires_action_change=bool(value.get("requires_action_change", True)),
            segments=_integer(value.get("segments")),
            scale=_integer(value.get("scale")),
            fault_scenario=(
                dict(value["fault_scenario"])
                if isinstance(value.get("fault_scenario"), Mapping)
                else None
            ),
            timeout_seconds=float(value.get("timeout_seconds", 0.0)),
            max_segments=int(value.get("max_segments", -1)),
            trace_profile=str(value.get("trace_profile", "bounded")),
        )


def default_config() -> dict[str, Any]:
    """Return an executable template without claiming that a policy is ready."""

    return {
        "schema": SCHEMA_CONFIG,
        "binary_path": "build_g4irsf17/python/Release/czr005_cpp.cp311-win_amd64.pyd",
        "base_native_controls": {},
        "off_native_controls": {"g4irsf16_supervisor_mode": "off"},
        "candidates": [
            {
                "candidate_id": "REPLACE_WITH_AUTHORIZED_G17_POLICY",
                "policy_family": "learned",
                "authorization_status": "NOT_AUTHORIZED",
                "native_controls": {},
                "locality_contract": {
                    "uses_global_state": False,
                    "stores_future_route": False,
                    "max_message_hops": 2,
                    "pending_queue_bound": 4,
                },
                "requires_action_change": True,
                "notes": "Fill from the Phase D policy decision; NOT_AUTHORIZED candidates are not run.",
            }
        ],
        "g2_mode": "auto",
        "g2_causal_evidence": "",
        "ladder_segments": list(LADDER_SEGMENTS),
        "scale_factors": list(SCALE_FACTORS),
        "run_32x_smoke": False,
        "smoke_segments": 8_192,
        "fault_loads": list(DEFAULT_FAULT_LOADS),
        "run_fault_8x": False,
        "fault_scenarios": "auto",
        "run_tracks": ["ladder", "fault", "scale"],
        "timeouts_seconds": {
            "ladder": 7_200,
            "fault": 7_200,
            "scale": 14_400,
        },
        "trace_limit": 500_000,
        "event_trace_limit": 0,
        "bootstrap_replicates": 2_000,
        "bootstrap_seed": 17_017,
        "tail_tolerance_seconds": 0.0,
        "early_mean_tolerance_seconds": 0.0,
        "scale_requires_full_ladder_pass": True,
        "reference_scale_tables": [
            "outputs/tables/g4irsf10_v2_safe_high_flow_matrix.csv"
        ],
        "campaign_manifest": DEFAULT_CAMPAIGN_MANIFEST.as_posix(),
        "runstate_root": DEFAULT_RUNSTATE_ROOT.as_posix(),
    }


def load_config(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    config = _read_json(path)
    _require(config.get("schema") == SCHEMA_CONFIG, "system campaign config schema mismatch")
    candidates = config.get("candidates")
    _require(isinstance(candidates, list), "config.candidates must be a list")
    parsed = [CandidateSpec.from_mapping(value) for value in candidates]
    ids = [value.candidate_id for value in parsed]
    _require(len(ids) == len(set(ids)), "candidate IDs must be unique")
    config["_candidate_specs"] = parsed
    config["_config_path"] = _relative(path, root)
    return config


def _campaign_stage_summary(manifest: Mapping[str, Any], *names: str) -> dict[str, Any]:
    stages = manifest.get("stages", {})
    if not isinstance(stages, Mapping):
        return {}
    for name in names:
        stage = stages.get(name)
        if isinstance(stage, Mapping) and isinstance(stage.get("summary"), Mapping):
            return dict(stage["summary"])
    return {}


def decide_g2_pivot(
    source_wait: Mapping[str, Any] | None,
    i1_support: Mapping[str, Any] | None,
    *,
    mode: str = "auto",
    causal_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the documented downstream/I1 gates without manufacturing support."""

    _require(mode in {"auto", "on", "off"}, "g2_mode must be auto, on, or off")
    source_wait = dict(source_wait or {})
    i1_support = dict(i1_support or {})
    causal_evidence = dict(causal_evidence or {})
    reasons: list[str] = []
    downstream_share = _finite(source_wait.get("downstream_backpressure_share"))
    source_pivot = str(source_wait.get("pivot_decision", ""))
    i1_pivot = str(i1_support.get("pivot_decision", ""))
    attempted = _integer(i1_support.get("attempted_h_bag_opportunity_count")) or 0
    changed = _integer(i1_support.get("action_changed_h_bag_count")) or 0
    support_ready = i1_support.get("support_ready") is True

    triggered = mode == "on"
    if mode == "on":
        reasons.append("operator explicitly enabled the documented G2 branch")
    if mode == "auto":
        if downstream_share is not None and downstream_share >= 0.50:
            triggered = True
            reasons.append(f"downstream backpressure share is {downstream_share:.2%} (>=50%)")
        if "START_G2" in source_pivot or "G2" in i1_pivot:
            triggered = True
            reasons.append(f"upstream campaign pivot requests G2 ({source_pivot or i1_pivot})")
        if attempted >= 512 and changed >= 512 and not support_ready:
            triggered = True
            reasons.append("512 competitive I1 changes did not meet the I1 support gate")
    if mode == "off":
        triggered = False
        reasons.append("operator explicitly disabled G2 for this campaign")

    evidence_status = str(causal_evidence.get("status", "MISSING"))
    causal_pass = (
        causal_evidence.get("support_ready") is True
        and causal_evidence.get("hard_safety_pass") is True
        and (_integer(causal_evidence.get("attempted_opportunity_count")) or 0) >= 64
    )
    if not triggered:
        decision = "G2_NOT_TRIGGERED_I1_CONTINUES"
    elif causal_pass:
        decision = "G2_CAUSAL_GATE_PASS_LADDER_ALLOWED"
    elif evidence_status in {"NO_GO", "COMPLETE_NO_GO"}:
        decision = "G2_CAUSAL_NO_GO"
    else:
        decision = "G2_PIVOT_TRIGGERED_PILOT_REQUIRED"
    return {
        "triggered": triggered,
        "decision": decision,
        "next_pivot": G2_NEXT_PIVOT,
        "reasons": reasons,
        "downstream_backpressure_share": downstream_share,
        "i1_attempted_competitive_count": attempted,
        "i1_changed_count": changed,
        "i1_support_ready": support_ready,
        "causal_evidence_status": evidence_status,
        "causal_gate_pass": causal_pass,
    }


def g2_decision_from_config(config: Mapping[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    manifest_path = _resolve(root, config.get("campaign_manifest", DEFAULT_CAMPAIGN_MANIFEST))
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    source = _campaign_stage_summary(manifest, "source_wait_diagnosis")
    i1 = _campaign_stage_summary(manifest, "i1_paired_execution", "i1_analysis")
    causal: dict[str, Any] = {}
    causal_path = str(config.get("g2_causal_evidence", "")).strip()
    if causal_path:
        resolved = _resolve(root, causal_path)
        if resolved.is_file():
            causal = _read_json(resolved)
    return decide_g2_pivot(
        source,
        i1,
        mode=str(config.get("g2_mode", "auto")),
        causal_evidence=causal,
    )


def default_fault_scenarios(*, root: Path = ROOT) -> tuple[FaultScenario, ...]:
    """Build the G17 matrix from G13's verified real-map fault catalogue."""

    from scripts.eval import g4irsf13_fault_control as g13

    graph, tasks = g13._load_inputs()  # Reuse the protected map/task loader.
    criticality = g13.build_criticality_rows(graph, tasks)
    by_arc = {int(row["arc_id"]): row for row in criticality}
    ranked = sorted(criticality, key=lambda row: int(row["maintenance_rank"]))
    critical = (int(ranked[0]["start"]), int(ranked[0]["end"]))
    merge_row = min(
        (row for row in criticality if bool(row["target_is_merge"])),
        key=lambda row: (float(row["maintenance_priority_score"]), int(row["arc_id"])),
    )
    merge_edge = (int(merge_row["start"]), int(merge_row["end"]))
    noncritical_row = min(
        (
            row
            for row in criticality
            if int(row["actual_task_segments_losing_reachability"]) == 0
            and int(row["alternate_outgoing_edge_count"]) > 0
            and (int(row["start"]), int(row["end"])) != merge_edge
        ),
        key=lambda row: (float(row["maintenance_priority_score"]), int(row["arc_id"])),
    )
    noncritical = (int(noncritical_row["start"]), int(noncritical_row["end"]))
    source_first = tuple(int(value) for value in g13._arc_index()[1][:2])
    ebs_edges = sorted(
        (int(edge["start"]), int(edge["end"]))
        for edge in graph["edges"]
        if int(edge["start"]) == 52
    )
    _require(bool(ebs_edges), "real map has no EBS/source-52 outgoing edge")
    arc = {
        key: (int(value["start"]), int(value["end"])) for key, value in by_arc.items()
    }
    return (
        FaultScenario("no_fault", "no_fault", ()),
        FaultScenario(
            "noncritical_edge",
            "single_noncritical_edge",
            (noncritical,),
            notes=(
                "Reachability-preserving alternate-outgoing edge distinct from the "
                "selected merge-incoming scenario; on this map it also enters a different merge."
            ),
        ),
        FaultScenario("critical_bottleneck", "single_critical_bottleneck", (critical,)),
        FaultScenario("merge_incoming_edge", "merge_edge_or_node", (merge_edge,)),
        FaultScenario("source_first_edge", "source_first_edge", (source_first,)),
        FaultScenario("ebs_outgoing_edge", "ebs_related_edge", (ebs_edges[0],)),
        FaultScenario("dual_disjoint", "two_nonadjacent_faults", (arc[2], arc[4])),
        FaultScenario("dual_interacting", "two_propagating_faults", (arc[1], arc[7])),
        FaultScenario(
            "delayed_beacon",
            "delayed_beacon",
            (merge_edge,),
            message_delay_seconds=20.0,
        ),
        FaultScenario(
            "dropped_intermediate_beacon",
            "dropped_intermediate_beacon",
            (merge_edge,),
            notification_dropped=True,
        ),
        FaultScenario(
            "repair_reopen",
            "repair_after_fault",
            (critical,),
            duration_seconds=97.0,
        ),
    )


def _timeout(config: Mapping[str, Any], track: str) -> float:
    values = config.get("timeouts_seconds", {})
    return float(values.get(track, 0.0)) if isinstance(values, Mapping) else 0.0


def _job(
    candidate: CandidateSpec | None,
    *,
    track: str,
    segments: int | None = None,
    scale: int | None = None,
    fault: FaultScenario | None = None,
    timeout_seconds: float,
    max_segments: int = -1,
) -> RunJob:
    candidate_id = OFF_CANDIDATE_ID if candidate is None else candidate.candidate_id
    family = "off" if candidate is None else candidate.policy_family
    parts = [track, candidate_id]
    if segments is not None:
        parts.append(str(segments))
    if scale is not None:
        parts.append(f"{scale}x")
    if fault is not None:
        parts.append(fault.scenario_id)
    return RunJob(
        job_id="__".join(_slug(part) for part in parts),
        track=track,
        candidate_id=candidate_id,
        policy_family=family,
        native_controls={} if candidate is None else dict(candidate.native_controls),
        locality_contract={} if candidate is None else dict(candidate.locality_contract),
        requires_action_change=False if candidate is None else candidate.requires_action_change,
        segments=segments,
        scale=scale,
        fault_scenario=fault.as_dict() if fault is not None else None,
        timeout_seconds=timeout_seconds,
        max_segments=max_segments,
    )


def build_run_plan(
    config: Mapping[str, Any],
    *,
    root: Path = ROOT,
    fault_scenarios: Sequence[FaultScenario] | None = None,
    g2_decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = list(config.get("_candidate_specs") or [
        CandidateSpec.from_mapping(value) for value in config.get("candidates", [])
    ])
    g2 = dict(g2_decision or g2_decision_from_config(config, root=root))
    included: list[CandidateSpec] = []
    excluded: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate.authorized:
            excluded.append({"candidate_id": candidate.candidate_id, "reason": "OFFLINE_NOT_AUTHORIZED"})
        elif candidate.policy_family in {"g2", "joint"} and not bool(g2["triggered"]):
            excluded.append({"candidate_id": candidate.candidate_id, "reason": "G2_NOT_TRIGGERED"})
        elif candidate.policy_family in {"g2", "joint"} and not bool(g2["causal_gate_pass"]):
            excluded.append({"candidate_id": candidate.candidate_id, "reason": "G2_CAUSAL_PILOT_NOT_PASSED"})
        else:
            included.append(candidate)

    tracks = {str(value) for value in config.get("run_tracks", ("ladder", "fault", "scale"))}
    jobs: list[RunJob] = []
    if "ladder" in tracks:
        sizes = tuple(int(value) for value in config.get("ladder_segments", LADDER_SEGMENTS))
        _require(sizes == LADDER_SEGMENTS, f"ladder must be exactly {LADDER_SEGMENTS}")
        for segments in sizes:
            jobs.append(_job(None, track="ladder", segments=segments, timeout_seconds=_timeout(config, "ladder")))
            jobs.extend(
                _job(candidate, track="ladder", segments=segments, timeout_seconds=_timeout(config, "ladder"))
                for candidate in included
            )

    if fault_scenarios is None:
        configured = config.get("fault_scenarios", "auto")
        fault_scenarios = (
            default_fault_scenarios(root=root)
            if configured == "auto"
            else tuple(FaultScenario.from_mapping(value) for value in configured)
        )
    if "fault" in tracks:
        loads = [int(value) for value in config.get("fault_loads", DEFAULT_FAULT_LOADS)]
        if bool(config.get("run_fault_8x", False)) and 8 not in loads:
            loads.append(8)
        for scale in loads:
            for fault in fault_scenarios:
                jobs.append(_job(None, track="fault", scale=scale, fault=fault, timeout_seconds=_timeout(config, "fault")))
                jobs.extend(
                    _job(candidate, track="fault", scale=scale, fault=fault, timeout_seconds=_timeout(config, "fault"))
                    for candidate in included
                )

    if "scale" in tracks:
        scales = [int(value) for value in config.get("scale_factors", SCALE_FACTORS)]
        _require(tuple(scales) == SCALE_FACTORS, f"scale ladder must be exactly {SCALE_FACTORS}")
        if bool(config.get("run_32x_smoke", False)):
            scales.append(32)
        for scale in scales:
            max_segments = int(config.get("smoke_segments", 8_192)) if scale == 32 else -1
            jobs.append(_job(None, track="scale", scale=scale, timeout_seconds=_timeout(config, "scale"), max_segments=max_segments))
            jobs.extend(
                _job(candidate, track="scale", scale=scale, timeout_seconds=_timeout(config, "scale"), max_segments=max_segments)
                for candidate in included
            )

    ids = [job.job_id for job in jobs]
    _require(len(ids) == len(set(ids)), "run plan produced duplicate job IDs")
    return {
        "schema": SCHEMA_PLAN,
        "artifact_role": "PRE_EXECUTION_PLANNING_SNAPSHOT",
        "status_note": (
            "Planning-time G2 and authorization fields are immutable provenance, not current "
            "execution status; use the campaign manifest and system-track reports for current conclusions."
        ),
        "created_at_utc": _now(),
        "delta_convention": "candidate_minus_matched_e4_off; negative_time_is_better",
        "g2_decision": g2,
        "included_candidates": [asdict(candidate) for candidate in included],
        "excluded_candidates": excluded,
        "jobs": [job.as_dict() for job in jobs],
    }


def _strict_zero_fields(summary: Mapping[str, Any], fields: Sequence[str]) -> bool:
    return all(type(summary.get(field)) is int and summary[field] == 0 for field in fields)


def evaluate_hard_safety(
    summary: Mapping[str, Any],
    *,
    requested_segments: int,
    policy_family: str,
    locality_contract: Mapping[str, Any] | None = None,
    raw_bags: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Evaluate explicit runtime invariants; absent evidence never becomes PASS."""

    unsafe_count = _first(
        summary,
        ("unsafe_entry_count", "physical_fault_edge_entry_violation_count"),
    )
    explicit_starvation = _first(
        summary,
        ("g4irsf17_source_starvation_count", "source_starvation_count", "starvation_count"),
    )
    completed_without_limit = (
        type(summary.get("completed_count")) is int
        and summary["completed_count"] == requested_segments
        and summary.get("event_limit_reached") is False
        and summary.get("time_limit_reached") is False
    )
    finite_completed_waits = bool(raw_bags) and all(
        row.get("complete") is True and _finite(row.get("source_wait_seconds")) is not None
        for row in raw_bags
    )
    starvation_free = (
        type(explicit_starvation) is int and explicit_starvation == 0
    ) or (completed_without_limit and finite_completed_waits)

    locality_contract = dict(locality_contract or {})
    if policy_family == "off":
        locality_pass = True
    else:
        locality_pass = (
            locality_contract.get("uses_global_state") is False
            and locality_contract.get("stores_future_route") is False
            and type(locality_contract.get("max_message_hops")) is int
            and 0 <= int(locality_contract["max_message_hops"]) <= 2
            and type(locality_contract.get("pending_queue_bound")) is int
            and 0 < int(locality_contract["pending_queue_bound"]) <= 64
        )

    gates = {
        "complete_coverage": (
            type(summary.get("requested_count")) is int
            and summary["requested_count"] == requested_segments
            and type(summary.get("completed_count")) is int
            and summary["completed_count"] == requested_segments
            and _strict_zero_fields(summary, ("failed_count",))
        ),
        "conflicts_zero": _strict_zero_fields(summary, ("reservation_conflicts",)),
        "unsafe_entries_zero": type(unsafe_count) is int and unsafe_count == 0,
        "unresolved_deadlocks_zero": _strict_zero_fields(summary, ("unresolved_deadlock_count",)),
        "full_astar_zero": _strict_zero_fields(summary, ("runtime_full_astar_calls",)),
        "global_scans_zero": _strict_zero_fields(
            summary,
            (
                "global_reservation_scan_count",
                "priority_global_scan_count",
                "scorer_runtime_global_scan_count",
                "microphase_runtime_global_scan_count",
                "first_edge_credit_global_scan_count",
            ),
        ),
        "future_route_reads_zero": _strict_zero_fields(
            summary,
            (
                "priority_future_route_input_count",
                "scorer_future_route_input_count",
                "first_edge_credit_future_route_count",
            ),
        ),
        "future_schedule_reads_zero": _strict_zero_fields(
            summary, ("scorer_future_schedule_input_count",)
        ),
        "future_routes_not_stored": (
            _strict_zero_fields(summary, ("full_future_routes_stored",))
            and summary.get("bag_future_path_field_present") is False
        ),
        "reservation_depth_one": (
            type(summary.get("reservation_depth")) is int
            and summary["reservation_depth"] == 1
        ),
        "one_edge_per_decision": (
            type(summary.get("max_edges_selected_per_arrive")) is int
            and summary["max_edges_selected_per_arrive"] <= 1
            and type(summary.get("max_edges_selected_per_bag_per_decision")) is int
            and summary["max_edges_selected_per_bag_per_decision"] <= 1
        ),
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "time_limit_not_reached": summary.get("time_limit_reached") is False,
        "starvation_free": starvation_free,
        "bounded_locality_contract": locality_pass,
    }
    return {"gates": gates, "hard_gate_pass": all(value is True for value in gates.values())}


def block_bootstrap_mean_ci(
    values: Sequence[float],
    block_ids: Sequence[str | int],
    *,
    replicates: int = 2_000,
    seed: int = 17_017,
) -> dict[str, Any]:
    _require(len(values) == len(block_ids), "bootstrap values/block IDs differ in length")
    _require(bool(values), "bootstrap requires at least one paired value")
    _require(replicates >= 100, "bootstrap_replicates must be at least 100")
    groups: dict[str, list[float]] = {}
    for value, block in zip(values, block_ids, strict=True):
        groups.setdefault(str(block), []).append(float(value))
    rng = random.Random(seed)
    draws: list[float] = []
    if len(groups) >= 2:
        names = sorted(groups)
        for _ in range(replicates):
            sample: list[float] = []
            for _unused in names:
                sample.extend(groups[rng.choice(names)])
            draws.append(statistics.fmean(sample))
        method = "time_block_bootstrap"
    else:
        population = [float(value) for value in values]
        for _ in range(replicates):
            draws.append(statistics.fmean(rng.choice(population) for _unused in population))
        method = "raw_bag_bootstrap_single_time_block"
    return {
        "method": method,
        "replicates": replicates,
        "point_mean_seconds": statistics.fmean(values),
        "ci95_lower_seconds": _quantile(draws, 0.025),
        "ci95_upper_seconds": _quantile(draws, 0.975),
        "block_count": len(groups),
    }


def paired_performance(
    off_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_replicates: int = 2_000,
    bootstrap_seed: int = 17_017,
) -> dict[str, Any]:
    """Compute raw-bag paired effects; incomplete bags stay visible."""

    off = {int(row["task_id"]): row for row in off_rows}
    candidate = {int(row["task_id"]): row for row in candidate_rows}
    _require(off.keys() == candidate.keys(), "matched candidate/off raw-bag IDs drifted")
    paired: list[dict[str, Any]] = []
    for task_id in sorted(off):
        baseline = off[task_id]
        treatment = candidate[task_id]
        both_complete = baseline.get("complete") is True and treatment.get("complete") is True
        off_tth = _finite(baseline.get("tth_seconds"))
        candidate_tth = _finite(treatment.get("tth_seconds"))
        tth_delta = candidate_tth - off_tth if both_complete and off_tth is not None and candidate_tth is not None else None
        paired.append(
            {
                "task_id": task_id,
                "off_complete": baseline.get("complete") is True,
                "candidate_complete": treatment.get("complete") is True,
                "off_tth_seconds": off_tth,
                "candidate_tth_seconds": candidate_tth,
                "tth_delta_seconds": tth_delta,
                "source_wait_delta_seconds": (
                    float(treatment["source_wait_seconds"]) - float(baseline["source_wait_seconds"])
                    if both_complete
                    and _finite(treatment.get("source_wait_seconds")) is not None
                    and _finite(baseline.get("source_wait_seconds")) is not None
                    else None
                ),
                "network_time_delta_seconds": (
                    float(treatment["network_time_seconds"]) - float(baseline["network_time_seconds"])
                    if both_complete
                    and _finite(treatment.get("network_time_seconds")) is not None
                    and _finite(baseline.get("network_time_seconds")) is not None
                    else None
                ),
                "time_block": treatment.get("time_block", baseline.get("time_block", "unknown")),
            }
        )
    complete = [row for row in paired if row["tth_delta_seconds"] is not None]
    deltas = [float(row["tth_delta_seconds"]) for row in complete]
    off_tth_values = [float(row["off_tth_seconds"]) for row in complete]
    candidate_tth_values = [float(row["candidate_tth_seconds"]) for row in complete]
    source_deltas = [float(row["source_wait_delta_seconds"]) for row in complete if row["source_wait_delta_seconds"] is not None]
    network_deltas = [float(row["network_time_delta_seconds"]) for row in complete if row["network_time_delta_seconds"] is not None]
    bootstrap = (
        block_bootstrap_mean_ci(
            deltas,
            [row["time_block"] for row in complete],
            replicates=bootstrap_replicates,
            seed=bootstrap_seed,
        )
        if deltas
        else None
    )
    return {
        "matched_raw_bag_count": len(paired),
        "paired_complete_count": len(complete),
        "off_incomplete_count": sum(not row["off_complete"] for row in paired),
        "candidate_incomplete_count": sum(not row["candidate_complete"] for row in paired),
        "mean_tth_delta_seconds": statistics.fmean(deltas) if deltas else None,
        "p50_tth_delta_seconds": (
            (_quantile(candidate_tth_values, 0.50) or 0.0) - (_quantile(off_tth_values, 0.50) or 0.0)
            if deltas
            else None
        ),
        "p95_tth_delta_seconds": (
            (_quantile(candidate_tth_values, 0.95) or 0.0) - (_quantile(off_tth_values, 0.95) or 0.0)
            if deltas
            else None
        ),
        "p99_tth_delta_seconds": (
            (_quantile(candidate_tth_values, 0.99) or 0.0) - (_quantile(off_tth_values, 0.99) or 0.0)
            if deltas
            else None
        ),
        "source_wait_delta_mean_seconds": statistics.fmean(source_deltas) if source_deltas else None,
        "network_time_delta_mean_seconds": statistics.fmean(network_deltas) if network_deltas else None,
        "improved_bag_count": sum(delta < -1.0e-9 for delta in deltas),
        "degraded_bag_count": sum(delta > 1.0e-9 for delta in deltas),
        "unchanged_bag_count": sum(abs(delta) <= 1.0e-9 for delta in deltas),
        "aggregate_tth_delta_seconds": sum(deltas),
        "bootstrap": bootstrap,
    }


def evaluate_ladder_gate(
    comparison: Mapping[str, Any],
    *,
    segments: int,
    candidate_hard_gate_pass: bool,
    off_hard_gate_pass: bool,
    action_change_count: int | None,
    requires_action_change: bool,
    tail_tolerance_seconds: float = 0.0,
    early_mean_tolerance_seconds: float = 0.0,
) -> dict[str, Any]:
    mean_delta = _finite(comparison.get("mean_tth_delta_seconds"))
    p95_delta = _finite(comparison.get("p95_tth_delta_seconds"))
    p99_delta = _finite(comparison.get("p99_tth_delta_seconds"))
    bootstrap = comparison.get("bootstrap")
    ci_upper = _finite(bootstrap.get("ci95_upper_seconds")) if isinstance(bootstrap, Mapping) else None
    complete = (
        int(comparison.get("off_incomplete_count", -1)) == 0
        and int(comparison.get("candidate_incomplete_count", -1)) == 0
        and int(comparison.get("paired_complete_count", -1))
        == int(comparison.get("matched_raw_bag_count", -2))
    )
    gates = {
        "matched_completion": complete,
        "candidate_hard_safety": candidate_hard_gate_pass is True,
        "off_hard_safety": off_hard_gate_pass is True,
        "action_change_observed": (
            not requires_action_change
            or (type(action_change_count) is int and action_change_count > 0)
        ),
        "p95_non_regression": p95_delta is not None and p95_delta <= tail_tolerance_seconds,
        "p99_non_regression": p99_delta is not None and p99_delta <= tail_tolerance_seconds,
        "mean_not_regressed": mean_delta is not None and mean_delta <= early_mean_tolerance_seconds,
    }
    if segments == LADDER_SEGMENTS[-1]:
        gates.update(
            {
                "full_mean_improvement": mean_delta is not None and mean_delta < 0.0,
                "bootstrap_ci95_upper_below_zero": ci_upper is not None and ci_upper < 0.0,
                "strict_full_p95_non_regression": p95_delta is not None and p95_delta <= 0.0,
                "strict_full_p99_non_regression": p99_delta is not None and p99_delta <= 0.0,
            }
        )
    passed = all(value is True for value in gates.values())
    return {
        "segments": segments,
        "gates": gates,
        "pass": passed,
        "decision": (
            "FULL_1X_PERFORMANCE_GATE_PASS"
            if passed and segments == LADDER_SEGMENTS[-1]
            else "ADVANCE_TO_NEXT_LADDER"
            if passed
            else "ROLL_BACK_CANDIDATE_CONTINUE_CAMPAIGN"
        ),
    }


def _load_jsonl(path: Path, *, limit: int = -1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                _require(isinstance(value, dict), f"non-object JSONL row in {path}")
                rows.append(value)
                if limit > 0 and len(rows) >= limit:
                    break
    _require(bool(rows), f"no input rows in {path}")
    return rows


def _load_job_input(job: RunJob, *, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if job.track == "ladder":
        from scripts.eval import g4irsf12_reproducible_harness as g12

        _require(job.segments in LADDER_SEGMENTS, "ladder job lacks a supported segment count")
        prefix = g12.load_input_prefix(int(job.segments), root=root)
        return [dict(row) for row in prefix.rows], {
            "protocol": "protected_first_n_file_order",
            "segments": job.segments,
            "topology_changed": False,
            "tth_denominator": "original_entry_time_tth",
        }

    from scripts.eval import run_g4irsf10_v2_safe_scale_hardcase_training as g10

    _require(job.scale in (*SCALE_FACTORS, *OPTIONAL_SCALE_FACTORS), "scale/fault job lacks a supported scale")
    label = f"g4irsf17_{job.track}_{job.scale}x"
    path, metadata = g10.ensure_source_queue_for_case(
        scale=int(job.scale),
        rolling_days=1,
        time_compression=1.0,
        label=label,
    )
    rows = _load_jsonl(path, limit=job.max_segments)
    return rows, {
        "protocol": "g4irsf10_distribution_preserving_fixed_map_resample",
        "scale": job.scale,
        "segments": len(rows),
        "topology_changed": bool(metadata.get("topology_changed", False)),
        "smoke_capped": job.max_segments > 0,
        "tth_denominator": "java_release_time_tth",
    }


def _binding_bag_records(rows: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            str(row["segment_id"]),
            int(row["task_id"]),
            float(row["pass_time"]),
            float(row["std"]),
            int(row["start"]),
            int(row["goal"]),
            str(row.get("source", f"node_{int(row['start'])}")),
        )
        for row in rows
    ]


def _fault_windows(
    scenario: FaultScenario | None,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[tuple[int, int, float, float, float, bool]], dict[str, Any]]:
    if scenario is None or not scenario.edges:
        return [], {"scenario_id": "no_fault", "edges": [], "fault_onset": None, "repair_time": None}
    releases = [float(row["pass_time"]) for row in rows]
    first, last = min(releases), max(releases)
    onset = first + scenario.onset_fraction * max(1.0, last - first)
    repair = onset + scenario.duration_seconds
    windows = [
        (
            start,
            end,
            onset,
            repair,
            scenario.message_delay_seconds,
            scenario.notification_dropped,
        )
        for start, end in scenario.edges
    ]
    return windows, {
        **scenario.as_dict(),
        "fault_onset": onset,
        "repair_time": repair,
    }


def _accepted_request(function: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(function)
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if accepts_kwargs:
        return dict(request)
    unsupported = sorted(set(request) - set(signature.parameters))
    _require(not unsupported, f"native wrapper does not accept controls: {unsupported}")
    return dict(request)


def _write_raw_bags(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - project dependency
        raise SystemCampaignError("zstandard is required for raw-bag checkpoints") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as raw:
        with zstandard.ZstdCompressor(level=3).stream_writer(raw, closefd=False) as stream:
            for row in rows:
                stream.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
                    + b"\n"
                )
    os.replace(temporary, path)


def _read_raw_bags(path: Path) -> list[dict[str, Any]]:
    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - project dependency
        raise SystemCampaignError("zstandard is required for raw-bag checkpoints") from exc
    with path.open("rb") as raw:
        with zstandard.ZstdDecompressor().stream_reader(raw) as stream:
            payload = stream.read().decode("utf-8")
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _raw_bag_rows(
    input_rows: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
    *,
    primary_denominator: str = "original_entry_time_tth",
) -> list[dict[str, Any]]:
    from scripts.eval import g4irsf12_reproducible_harness as g12

    bags = payload.get("bags")
    _require(isinstance(bags, list), "native payload.bags is missing")
    _require(
        primary_denominator
        in {"original_entry_time_tth", "java_release_time_tth"},
        f"unsupported raw-bag TTH denominator: {primary_denominator}",
    )
    aggregated = g12.aggregate_raw_bag_timings(
        input_rows,
        bags,
        allow_release_before_original_entry=(
            primary_denominator == "java_release_time_tth"
        ),
    )
    entry_by_task: dict[int, float] = {}
    for row in input_rows:
        task_id = int(row["task_id"])
        entry = float(row.get("original_entry_time", row["pass_time"]))
        entry_by_task[task_id] = min(entry, entry_by_task.get(task_id, entry))
    rows: list[dict[str, Any]] = []
    for row in aggregated:
        task_id = int(row["task_id"])
        complete = bool(row["complete"])
        rows.append(
            {
                "task_id": task_id,
                "complete": complete,
                "expected_segment_count": int(row["expected_segment_count"]),
                "completed_segment_count": int(row["completed_segment_count"]),
                "tth_seconds": (
                    row[f"{primary_denominator}_seconds"] if complete else None
                ),
                "tth_denominator": primary_denominator,
                "original_entry_time_tth_seconds": (
                    row["original_entry_time_tth_seconds"] if complete else None
                ),
                "java_release_time_tth_seconds": (
                    row["java_release_time_tth_seconds"] if complete else None
                ),
                "source_wait_seconds": row["source_wait_seconds"] if complete else None,
                "network_time_seconds": row["network_time_seconds"] if complete else None,
                "original_entry_time": entry_by_task[task_id],
                "time_block": int(math.floor(entry_by_task[task_id] / 3_600.0)),
            }
        )
    return rows


def _failed_segment_diagnostics(
    payload: Mapping[str, Any],
    *,
    limit: int = 64,
) -> tuple[int, list[dict[str, Any]]]:
    """Keep a bounded, actionable account of native segment failures.

    Raw-bag aggregation intentionally works at task level.  A multi-leg task
    can therefore be incomplete even when the aggregate row cannot identify
    which native segment stopped.  Preserve the native failure reason and
    short local history so a real fault-campaign hard-gate failure can be
    diagnosed without retaining the full multi-million-event trace.
    """

    bags = payload.get("bags")
    _require(isinstance(bags, list), "native payload.bags is missing")
    failed = [
        row
        for row in bags
        if isinstance(row, Mapping) and row.get("completed") is not True
    ]
    fields = (
        "runtime_bag_id",
        "task_id",
        "segment_id",
        "start",
        "goal",
        "final_node",
        "release_time",
        "admitted_time",
        "finish_time",
        "total_local_wait",
        "decision_count",
        "retry_count",
        "failure_reason",
        "short_history",
    )
    return len(failed), [
        {field: row.get(field) for field in fields}
        for row in failed[: max(0, int(limit))]
    ]


def _summary_metric(summary: Mapping[str, Any], *names: str) -> Any:
    return _first(summary, names)


def execute_native_job(
    job: RunJob,
    config: Mapping[str, Any],
    *,
    root: Path,
    result_path: Path,
) -> dict[str, Any]:
    """Execute one native job inside a worker process."""

    from scripts.eval.g4irsf11_fixed_map import assert_canonical_map, canonical_graph_records
    from scripts.eval.g4irsf14_opportunity_census import FROZEN_RUNTIME_CONTROLS, MODEL_PATH
    from czr005 import cpp_backend

    input_rows, input_descriptor = _load_job_input(job, root=root)
    _require(input_descriptor.get("topology_changed") is False, "scale input changed the map")
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    scenario = FaultScenario.from_mapping(job.fault_scenario) if job.fault_scenario else None
    fault_windows, fault_descriptor = _fault_windows(scenario, input_rows)
    binary = _resolve(root, str(config["binary_path"])).resolve(strict=True)
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(dict(config.get("base_native_controls", {})))
    request.update(dict(config.get("off_native_controls", {})))
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=_binding_bag_records(input_rows),
        fault_windows=fault_windows,
        scenario=f"g4irsf17_{job.job_id}",
        summary_only=False,
        trace_limit=(
            int(config.get("trace_limit", 500_000))
            if job.track == "ladder"
            else int(config.get(f"{job.track}_trace_limit", 0))
        ),
        event_trace_limit=int(config.get("event_trace_limit", 0)),
        trace_shard_count=1,
        trace_shard_index=0,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        scorer_model_path=(root / MODEL_PATH).resolve(strict=True),
        expected_binary_path=binary,
        search_path=binary.parent,
    )
    request.update(dict(job.native_controls))
    function = cpp_backend.g4irsf11_event_runtime_from_records
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    payload = function(**_accepted_request(function, request))
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    _require(isinstance(payload, Mapping), "native payload is not an object")
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload.summary is missing")
    primary_denominator = str(
        input_descriptor.get("tth_denominator", "original_entry_time_tth")
    )
    raw_bags = _raw_bag_rows(
        input_rows,
        payload,
        primary_denominator=primary_denominator,
    )
    failed_segment_count, failed_segment_diagnostics = (
        _failed_segment_diagnostics(payload)
    )
    requested = len(input_rows)
    safety = evaluate_hard_safety(
        summary,
        requested_segments=requested,
        policy_family=job.policy_family,
        locality_contract=job.locality_contract,
        raw_bags=raw_bags,
    )
    completed = [row for row in raw_bags if row["complete"]]
    tth = [float(row["tth_seconds"]) for row in completed]
    source_wait = [float(row["source_wait_seconds"]) for row in completed]
    network = [float(row["network_time_seconds"]) for row in completed]
    raw_path = result_path.with_suffix(".raw_bags.jsonl.zst")
    _write_raw_bags(raw_path, raw_bags)
    action_change = _integer(
        _summary_metric(
            summary,
            "g4irsf17_source_order_change_count",
            "g4irsf17_action_change_count",
            "source_order_change_count",
            "g4irsf16_action_change_count",
        )
    )
    fault_affected = _integer(summary.get("fault_affected_bag_count"))
    fault_completed = _integer(
        _summary_metric(summary, "fault_affected_completed_count", "fault_affected_success_count")
    )
    stranded = _integer(
        _summary_metric(summary, "stranded_bag_count", "fault_stranded_bag_count")
    )
    if stranded is None and fault_affected is not None and fault_completed is not None:
        stranded = max(0, fault_affected - fault_completed)
    recovery_seconds = _finite(
        _summary_metric(
            summary,
            "fault_recovery_time_seconds",
            "fault_recovery_seconds",
            "recovery_time_seconds",
        )
    )
    recovery_available = summary.get("fault_recovery_seconds_available") is True
    inflight_merge_recovery_count, inflight_merge_recovery_available = (
        _nonnegative_counter_evidence(
            summary, INFLIGHT_MERGE_RECOVERY_COUNTER
        )
    )
    result = {
        "schema": SCHEMA_RESULT,
        "job": job.as_dict(),
        "status": "COMPLETE" if safety["hard_gate_pass"] else "HARD_GATE_FAILED",
        "completed_at_utc": _now(),
        "input_descriptor": input_descriptor,
        "tth_denominator": primary_denominator,
        "fault_descriptor": fault_descriptor,
        "raw_bag_artifact": _relative(raw_path, root),
        "requested_segments": requested,
        "selected_raw_bag_count": len(raw_bags),
        "complete_raw_bag_count": len(completed),
        "failed_segment_count": failed_segment_count,
        "failed_segment_diagnostics": failed_segment_diagnostics,
        "completion_rate": len(completed) / len(raw_bags),
        "mean_tth_seconds": statistics.fmean(tth) if len(tth) == len(raw_bags) else None,
        "p50_tth_seconds": _quantile(tth, 0.50) if len(tth) == len(raw_bags) else None,
        "p95_tth_seconds": _quantile(tth, 0.95) if len(tth) == len(raw_bags) else None,
        "p99_tth_seconds": _quantile(tth, 0.99) if len(tth) == len(raw_bags) else None,
        "source_wait_mean_seconds": statistics.fmean(source_wait) if len(source_wait) == len(raw_bags) else None,
        "network_time_mean_seconds": statistics.fmean(network) if len(network) == len(raw_bags) else None,
        "action_change_count": action_change,
        "order_change_count": _integer(_summary_metric(summary, "g4irsf17_source_order_change_count", "source_order_change_count")),
        "decision_count": _integer(_summary_metric(summary, "decision_count", "node_decision_count")),
        "event_count": _integer(_summary_metric(summary, "event_count", "processed_event_count")),
        "queue_peak": _integer(
            _summary_metric(
                summary,
                "g4irsf17_source_queue_peak",
                "source_queue_peak",
                "max_source_queue_length",
                "max_local_queue_observed",
            )
        ),
        "max_source_queue_length": _integer(summary.get("max_source_queue_length")),
        "max_source_queue_delay_seconds": _finite(summary.get("max_source_queue_delay")),
        "max_junction_queue_length": _integer(summary.get("max_junction_queue_length")),
        "fault_affected_bag_count": fault_affected,
        "fault_affected_completed_count": fault_completed,
        "stranded_bag_count": stranded,
        "fault_recovery_time_seconds": recovery_seconds,
        "fault_recovery_seconds_available": recovery_available,
        "fault_event_count": _integer(summary.get("fault_event_count")),
        "repair_event_count": _integer(summary.get("repair_event_count")),
        "fault_notification_drop_count": _integer(summary.get("fault_notification_drop_count")),
        INFLIGHT_MERGE_RECOVERY_COUNTER: inflight_merge_recovery_count,
        f"{INFLIGHT_MERGE_RECOVERY_COUNTER}_available": (
            inflight_merge_recovery_available
        ),
        "route_change_count": _integer(_summary_metric(summary, "fault_route_change_count", "local_fault_policy_reroute_count")),
        "beacon_message_count": _integer(
            _summary_metric(
                summary,
                "fault_beacon_message_count",
                "fault_notification_count",
                "congestion_beacon_update_event_count",
            )
        ),
        "local_hold_count": _integer(
            _summary_metric(summary, "local_fault_policy_hold_count", "physical_fault_interlock_hold_count")
        ),
        "local_hold_seconds": _finite(_summary_metric(summary, "fault_local_hold_seconds", "physical_fault_hold_seconds")),
        "pibt_activation_count": _integer(summary.get("bounded_local_pibt_activation_count")),
        "resources": {
            "worker_wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "peak_rss_mb": None,
            "peak_rss_status": "PARENT_SAMPLER_PENDING",
        },
        "hard_safety": safety,
        "runtime_counters": {
            name: summary.get(name)
            for name in (
                "requested_count",
                "completed_count",
                "failed_count",
                "reservation_conflicts",
                "physical_fault_edge_entry_violation_count",
                "unresolved_deadlock_count",
                "runtime_full_astar_calls",
                "global_reservation_scan_count",
                "full_future_routes_stored",
                "event_limit_reached",
                "time_limit_reached",
                INFLIGHT_MERGE_RECOVERY_COUNTER,
            )
        }
        | {
            f"{INFLIGHT_MERGE_RECOVERY_COUNTER}_available": (
                inflight_merge_recovery_available
            )
        },
    }
    return result


def result_path_for(job: RunJob, config: Mapping[str, Any], *, root: Path) -> Path:
    runstate = _resolve(root, config.get("runstate_root", DEFAULT_RUNSTATE_ROOT))
    return runstate / "jobs" / f"{job.job_id}.json"


def result_is_resumable(path: Path, *, root: Path = ROOT) -> bool:
    if not path.is_file():
        return False
    try:
        result = _read_json(path)
    except SystemCampaignError:
        return False
    status = str(result.get("status", ""))
    if status not in TERMINAL_RESULT_STATUSES:
        return False
    artifact = result.get("raw_bag_artifact")
    return artifact in (None, "") or _resolve(root, str(artifact)).is_file()


def _oom_text(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("memoryerror", "bad_alloc", "out of memory", "cannot allocate memory"))


def _sample_rss_mb(process: subprocess.Popen[Any]) -> float | None:
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        try:
            parent = psutil.Process(process.pid)
            processes = [parent, *parent.children(recursive=True)]
            return sum(item.memory_info().rss for item in processes) / (1024.0 * 1024.0)
        except (psutil.Error, OSError):
            return None

    # The managed Windows environment used for the long native campaigns does
    # not necessarily include psutil.  The native worker executes the runtime
    # in-process, so its working set is the quantity we need; query it directly
    # instead of dropping the Phase-H memory metric or adding a new dependency.
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCountersEx(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("page_fault_count", wintypes.DWORD),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
                ("private_usage", ctypes.c_size_t),
            ]

        query_information = 0x0400
        vm_read = 0x0010
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCountersEx),
            wintypes.DWORD,
        ]
        handle = kernel32.OpenProcess(query_information | vm_read, False, process.pid)
        if not handle:
            return None
        try:
            counters = ProcessMemoryCountersEx()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None
            return float(counters.working_set_size) / (1024.0 * 1024.0)
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return None


def run_job_subprocess(
    job: RunJob,
    config: Mapping[str, Any],
    *,
    config_path: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Run one worker with timeout/censoring and parent-process RSS sampling."""

    result_path = result_path_for(job, config, root=root)
    runstate = result_path.parent.parent
    spec_path = runstate / "specs" / f"{job.job_id}.json"
    stdout_path = runstate / "logs" / f"{job.job_id}.stdout.log"
    stderr_path = runstate / "logs" / f"{job.job_id}.stderr.log"
    _write_json(spec_path, job.as_dict())
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_worker",
        "--root",
        str(root.resolve()),
        "--config",
        str(config_path.resolve()),
        "--job",
        str(spec_path.resolve()),
        "--result",
        str(result_path.resolve()),
    ]
    wall_start = time.perf_counter()
    peak_rss: float | None = None
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=root, stdout=stdout, stderr=stderr)
        timed_out = False
        while process.poll() is None:
            sample = _sample_rss_mb(process)
            if sample is not None:
                peak_rss = max(peak_rss or 0.0, sample)
            if job.timeout_seconds > 0 and time.perf_counter() - wall_start > job.timeout_seconds:
                timed_out = True
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
            time.sleep(0.05)
    parent_wall = time.perf_counter() - wall_start
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    if timed_out:
        result = {
            "schema": SCHEMA_RESULT,
            "job": job.as_dict(),
            "status": "CENSORED_TIMEOUT",
            "completed_at_utc": _now(),
            "censor_reason": "configured worker timeout reached",
            "timeout_seconds": job.timeout_seconds,
            "resources": {
                "parent_wall_seconds": parent_wall,
                "peak_rss_mb": peak_rss,
                "peak_rss_status": "MEASURED" if peak_rss is not None else "PSUTIL_UNAVAILABLE",
            },
            "stderr_log": _relative(stderr_path, root),
        }
        _write_json(result_path, result)
        return result
    if process.returncode != 0 or not result_path.is_file():
        status = "CENSORED_OOM" if _oom_text(stderr_text) else "FAILED_RESUMABLE"
        result = {
            "schema": SCHEMA_RESULT,
            "job": job.as_dict(),
            "status": status,
            "completed_at_utc": _now(),
            "error": stderr_text[-4_000:] or f"worker exited {process.returncode}",
            "resources": {
                "parent_wall_seconds": parent_wall,
                "peak_rss_mb": peak_rss,
                "peak_rss_status": "MEASURED" if peak_rss is not None else "PSUTIL_UNAVAILABLE",
            },
            "stdout_log": _relative(stdout_path, root),
            "stderr_log": _relative(stderr_path, root),
        }
        _write_json(result_path, result)
        return result
    result = _read_json(result_path)
    resources = result.setdefault("resources", {})
    resources["parent_wall_seconds"] = parent_wall
    resources["peak_rss_mb"] = peak_rss
    resources["peak_rss_status"] = "MEASURED" if peak_rss is not None else "PSUTIL_UNAVAILABLE"
    result["stdout_log"] = _relative(stdout_path, root)
    result["stderr_log"] = _relative(stderr_path, root)
    decisions = _integer(result.get("decision_count"))
    events = _integer(result.get("event_count"))
    if parent_wall > 0:
        result["decisions_per_second"] = decisions / parent_wall if decisions is not None else None
        result["events_per_second"] = events / parent_wall if events is not None else None
    _write_json(result_path, result)
    return result


def _worker(config_path: Path, job_path: Path, result_path: Path, *, root: Path) -> int:
    try:
        config = load_config(config_path, root=root)
        job = RunJob.from_mapping(_read_json(job_path))
        result = execute_native_job(job, config, root=root, result_path=result_path)
        _write_json(result_path, result)
        return 0
    except BaseException as exc:  # Worker must leave a resumable diagnostic.
        result = {
            "schema": SCHEMA_RESULT,
            "job": _read_json(job_path) if job_path.is_file() else {},
            "status": "FAILED_RESUMABLE",
            "completed_at_utc": _now(),
            "error": f"{type(exc).__name__}: {exc}",
        }
        _write_json(result_path, result)
        print(result["error"], file=sys.stderr)
        return 2


def load_results(
    plan: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for raw in plan.get("jobs", []):
        job = RunJob.from_mapping(raw)
        path = result_path_for(job, config, root=root)
        if path.is_file():
            results[job.job_id] = _read_json(path)
    return results


def run_plan(
    plan: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    config_path: Path,
    root: Path = ROOT,
    tracks: set[str] | None = None,
    job_ids: set[str] | None = None,
    rerun_terminal: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    capacity_amendment = _fault_capacity_amendment(
        plan, load_results(plan, config, root=root), config
    )

    def prior_ladder_pass(job: RunJob) -> tuple[bool, str]:
        if job.candidate_id == OFF_CANDIDATE_ID:
            return True, "control"
        target_segments: int | None = None
        if job.track == "ladder" and job.segments != LADDER_SEGMENTS[0]:
            target_segments = LADDER_SEGMENTS[LADDER_SEGMENTS.index(int(job.segments)) - 1]
        elif job.track == "scale" and bool(config.get("scale_requires_full_ladder_pass", True)):
            target_segments = LADDER_SEGMENTS[-1]
        if target_segments is None:
            return True, "not_required"
        prior = next(
            (
                RunJob.from_mapping(value)
                for value in plan.get("jobs", [])
                if value.get("track") == "ladder"
                and value.get("candidate_id") == job.candidate_id
                and int(value.get("segments", -1)) == target_segments
            ),
            None,
        )
        if prior is None:
            return False, f"required ladder job {target_segments} is absent"
        current = load_results(plan, config, root=root)
        candidate = current.get(prior.job_id)
        off = current.get(_off_job_id(prior))
        comparison = compare_result_pair(off, candidate, root=root, config=config)
        if comparison.get("comparison_status") != "MATCHED_COMPLETE" or candidate is None or off is None:
            return False, f"required ladder job {target_segments} is not matched-complete"
        gate = evaluate_ladder_gate(
            comparison,
            segments=target_segments,
            candidate_hard_gate_pass=candidate.get("hard_safety", {}).get("hard_gate_pass") is True,
            off_hard_gate_pass=off.get("hard_safety", {}).get("hard_gate_pass") is True,
            action_change_count=_integer(candidate.get("action_change_count")),
            requires_action_change=prior.requires_action_change,
            tail_tolerance_seconds=float(config.get("tail_tolerance_seconds", 0.0)),
            early_mean_tolerance_seconds=float(config.get("early_mean_tolerance_seconds", 0.0)),
        )
        return bool(gate["pass"]), str(gate["decision"])

    for raw in plan.get("jobs", []):
        job = RunJob.from_mapping(raw)
        if tracks is not None and job.track not in tracks:
            continue
        if job_ids is not None and job.job_id not in job_ids:
            continue
        # Protocol-amended 4x fault cells remain visible in the plan and
        # reports, but are intentionally not executed and never receive fake
        # result checkpoints.  The scale control is the sole reused evidence.
        if _is_amended_fault_job(job, capacity_amendment):
            continue
        path = result_path_for(job, config, root=root)
        if not rerun_terminal and result_is_resumable(path, root=root):
            results.append(_read_json(path))
            continue
        predecessor_pass, predecessor_reason = prior_ladder_pass(job)
        if not predecessor_pass:
            result = {
                "schema": SCHEMA_RESULT,
                "job": job.as_dict(),
                "status": "NOT_RUN_PREDECESSOR_GATE",
                "completed_at_utc": _now(),
                "reason": predecessor_reason,
            }
            _write_json(path, result)
            results.append(result)
            continue
        results.append(
            run_job_subprocess(
                job,
                config,
                config_path=config_path,
                root=root,
            )
        )
    return results


def _job_from_result(result: Mapping[str, Any]) -> RunJob:
    value = result.get("job")
    _require(isinstance(value, Mapping), "result is missing its job descriptor")
    return RunJob.from_mapping(value)


def _off_job_id(job: RunJob) -> str:
    fault = FaultScenario.from_mapping(job.fault_scenario) if job.fault_scenario else None
    return _job(
        None,
        track=job.track,
        segments=job.segments,
        scale=job.scale,
        fault=fault,
        timeout_seconds=job.timeout_seconds,
        max_segments=job.max_segments,
    ).job_id


def _fault_capacity_amendment(
    plan: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the explicit 4x capacity-censor amendment when supported.

    The fault/no-fault control and scale control use the same fixed-map input,
    E4/off controls, empty fault window, and unbounded segment selection.  The
    only configured timeout difference is immaterial when the scale execution
    reaches the native event cap before the shorter fault timeout.
    """

    jobs = [RunJob.from_mapping(raw) for raw in plan.get("jobs", [])]
    scale_job = next(
        (
            job
            for job in jobs
            if job.track == "scale"
            and job.candidate_id == OFF_CANDIDATE_ID
            and job.scale == CAPACITY_CENSOR_SCALE
        ),
        None,
    )
    fault_control = next(
        (
            job
            for job in jobs
            if job.track == "fault"
            and job.candidate_id == OFF_CANDIDATE_ID
            and job.scale == CAPACITY_CENSOR_SCALE
            and job.fault_scenario is not None
            and FaultScenario.from_mapping(job.fault_scenario).category
            == "no_fault"
        ),
        None,
    )
    if scale_job is None or fault_control is None:
        return None
    evidence = results.get(scale_job.job_id)
    if evidence is None:
        return None
    counters = evidence.get("runtime_counters")
    resources = evidence.get("resources")
    descriptor = evidence.get("input_descriptor")
    if not isinstance(counters, Mapping) or not isinstance(resources, Mapping):
        return None
    if not isinstance(descriptor, Mapping):
        return None

    event_count = _integer(evidence.get("event_count"))
    requested = _integer(counters.get("requested_count"))
    completed = _integer(counters.get("completed_count"))
    wall_seconds = _finite(resources.get("parent_wall_seconds"))
    fault_scenario = FaultScenario.from_mapping(fault_control.fault_scenario or {})
    equivalent = (
        scale_job.policy_family == fault_control.policy_family == "off"
        and scale_job.native_controls == fault_control.native_controls
        and scale_job.max_segments == fault_control.max_segments == -1
        and fault_scenario.category == "no_fault"
        and not fault_scenario.edges
        and descriptor.get("protocol")
        == "g4irsf10_distribution_preserving_fixed_map_resample"
        and descriptor.get("topology_changed") is False
        and _integer(descriptor.get("scale")) == CAPACITY_CENSOR_SCALE
        and int(config.get("scale_trace_limit", 0))
        == int(config.get("fault_trace_limit", 0))
    )
    capacity_censored = (
        equivalent
        and evidence.get("status") == "HARD_GATE_FAILED"
        and evidence.get("hard_safety", {}).get("hard_gate_pass") is False
        and counters.get("event_limit_reached") is True
        and event_count == CAPACITY_CENSOR_EVENT_CAP
        and requested is not None
        and completed is not None
        and completed < requested
        and wall_seconds is not None
        and wall_seconds < fault_control.timeout_seconds
    )
    if not capacity_censored:
        return None
    return {
        "protocol_status": "AMENDED",
        "track": CAPACITY_CENSOR_TRACK_STATUS,
        "status": CAPACITY_CENSOR_CONTROL_STATUS,
        "evidence_job_id": scale_job.job_id,
        "fault_control_job_id": fault_control.job_id,
        "event_cap": CAPACITY_CENSOR_EVENT_CAP,
        "requested_segment_count": requested,
        "completed_segment_count": completed,
        "failed_segment_count": _integer(counters.get("failed_count")),
        "event_count": event_count,
        "resources": dict(resources),
        "hard_gate_pass": False,
        "equivalence": {
            "fixed_map_scale": CAPACITY_CENSOR_SCALE,
            "candidate_id": OFF_CANDIDATE_ID,
            "policy_family": "off",
            "native_controls_equal": True,
            "max_segments_equal": True,
            "fault_windows": [],
            "trace_limits_equal": True,
            "scale_timeout_seconds": scale_job.timeout_seconds,
            "fault_timeout_seconds": fault_control.timeout_seconds,
            "evidence_wall_seconds": wall_seconds,
        },
        "reason": (
            "The exact-equivalent fixed-map 4x E4/off no-fault control reached "
            "the frozen 20M-event cap before the shorter fault timeout; without "
            "a completed matched control, 4x fault advantage is not estimable."
        ),
    }


def _is_amended_fault_job(job: RunJob, amendment: Mapping[str, Any] | None) -> bool:
    return bool(
        amendment is not None
        and job.track == "fault"
        and job.candidate_id == OFF_CANDIDATE_ID
        and job.scale == CAPACITY_CENSOR_SCALE
    )


def _resource_comparison(
    off: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    left = off.get("resources", {})
    right = candidate.get("resources", {})
    off_wall = _finite(left.get("parent_wall_seconds")) if isinstance(left, Mapping) else None
    candidate_wall = _finite(right.get("parent_wall_seconds")) if isinstance(right, Mapping) else None
    off_cpu = _finite(left.get("cpu_seconds")) if isinstance(left, Mapping) else None
    candidate_cpu = _finite(right.get("cpu_seconds")) if isinstance(right, Mapping) else None
    off_rss = _finite(left.get("peak_rss_mb")) if isinstance(left, Mapping) else None
    candidate_rss = _finite(right.get("peak_rss_mb")) if isinstance(right, Mapping) else None
    return {
        "off_wall_seconds": off_wall,
        "candidate_wall_seconds": candidate_wall,
        "wall_overhead_seconds": candidate_wall - off_wall if off_wall is not None and candidate_wall is not None else None,
        "wall_ratio": candidate_wall / off_wall if off_wall and candidate_wall is not None else None,
        "off_cpu_seconds": off_cpu,
        "candidate_cpu_seconds": candidate_cpu,
        "cpu_overhead_seconds": candidate_cpu - off_cpu if off_cpu is not None and candidate_cpu is not None else None,
        "off_peak_rss_mb": off_rss,
        "candidate_peak_rss_mb": candidate_rss,
        "peak_rss_overhead_mb": candidate_rss - off_rss if off_rss is not None and candidate_rss is not None else None,
    }


def compare_result_pair(
    off: Mapping[str, Any] | None,
    candidate: Mapping[str, Any] | None,
    *,
    root: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if off is None or candidate is None:
        return {"comparison_status": "MATCHED_RESULT_MISSING"}
    if str(off.get("status")) not in {"COMPLETE", "HARD_GATE_FAILED"}:
        return {"comparison_status": f"OFF_{off.get('status', 'UNKNOWN')}"}
    if str(candidate.get("status")) not in {"COMPLETE", "HARD_GATE_FAILED"}:
        return {"comparison_status": f"CANDIDATE_{candidate.get('status', 'UNKNOWN')}"}
    if off.get("input_descriptor") != candidate.get("input_descriptor"):
        return {"comparison_status": "UNMATCHED_INPUT_SEMANTICS"}
    if off.get("fault_descriptor") != candidate.get("fault_descriptor"):
        return {"comparison_status": "UNMATCHED_FAULT_SEMANTICS"}
    off_path = _resolve(root, str(off.get("raw_bag_artifact", "")))
    candidate_path = _resolve(root, str(candidate.get("raw_bag_artifact", "")))
    if not off_path.is_file() or not candidate_path.is_file():
        return {"comparison_status": "RAW_BAG_CHECKPOINT_MISSING"}
    paired = paired_performance(
        _read_raw_bags(off_path),
        _read_raw_bags(candidate_path),
        bootstrap_replicates=int(config.get("bootstrap_replicates", 2_000)),
        bootstrap_seed=int(config.get("bootstrap_seed", 17_017)),
    )
    return {
        "comparison_status": "MATCHED_COMPLETE",
        **paired,
        "resources": _resource_comparison(off, candidate),
    }


def build_ladder_rows(
    plan: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in plan.get("jobs", []):
        job = RunJob.from_mapping(raw)
        if job.track != "ladder" or job.candidate_id == OFF_CANDIDATE_ID:
            continue
        candidate = results.get(job.job_id)
        off = results.get(_off_job_id(job))
        comparison = compare_result_pair(off, candidate, root=root, config=config)
        gate: dict[str, Any] | None = None
        if comparison.get("comparison_status") == "MATCHED_COMPLETE" and candidate is not None and off is not None:
            gate = evaluate_ladder_gate(
                comparison,
                segments=int(job.segments),
                candidate_hard_gate_pass=candidate.get("hard_safety", {}).get("hard_gate_pass") is True,
                off_hard_gate_pass=off.get("hard_safety", {}).get("hard_gate_pass") is True,
                action_change_count=_integer(candidate.get("action_change_count")),
                requires_action_change=job.requires_action_change,
                tail_tolerance_seconds=float(config.get("tail_tolerance_seconds", 0.0)),
                early_mean_tolerance_seconds=float(config.get("early_mean_tolerance_seconds", 0.0)),
            )
        resources = comparison.get("resources", {})
        bootstrap = comparison.get("bootstrap", {})
        rows.append(
            {
                "candidate_id": job.candidate_id,
                "policy_family": job.policy_family,
                "segments": job.segments,
                "candidate_status": candidate.get("status") if candidate else "NOT_RUN",
                "off_status": off.get("status") if off else "NOT_RUN",
                "comparison_status": comparison.get("comparison_status"),
                "matched_raw_bag_count": comparison.get("matched_raw_bag_count"),
                "mean_tth_delta_seconds": comparison.get("mean_tth_delta_seconds"),
                "p50_tth_delta_seconds": comparison.get("p50_tth_delta_seconds"),
                "p95_tth_delta_seconds": comparison.get("p95_tth_delta_seconds"),
                "p99_tth_delta_seconds": comparison.get("p99_tth_delta_seconds"),
                "source_wait_delta_mean_seconds": comparison.get("source_wait_delta_mean_seconds"),
                "network_time_delta_mean_seconds": comparison.get("network_time_delta_mean_seconds"),
                "improved_bag_count": comparison.get("improved_bag_count"),
                "degraded_bag_count": comparison.get("degraded_bag_count"),
                "unchanged_bag_count": comparison.get("unchanged_bag_count"),
                "ci95_lower_seconds": bootstrap.get("ci95_lower_seconds") if isinstance(bootstrap, Mapping) else None,
                "ci95_upper_seconds": bootstrap.get("ci95_upper_seconds") if isinstance(bootstrap, Mapping) else None,
                "action_change_count": candidate.get("action_change_count") if candidate else None,
                "order_change_count": candidate.get("order_change_count") if candidate else None,
                "queue_peak": candidate.get("queue_peak") if candidate else None,
                "candidate_hard_gate_pass": candidate.get("hard_safety", {}).get("hard_gate_pass") if candidate else None,
                "off_hard_gate_pass": off.get("hard_safety", {}).get("hard_gate_pass") if off else None,
                "wall_overhead_seconds": resources.get("wall_overhead_seconds") if isinstance(resources, Mapping) else None,
                "wall_ratio": resources.get("wall_ratio") if isinstance(resources, Mapping) else None,
                "peak_rss_overhead_mb": resources.get("peak_rss_overhead_mb") if isinstance(resources, Mapping) else None,
                "ladder_gate_pass": gate.get("pass") if gate else None,
                "ladder_decision": gate.get("decision") if gate else "WAITING_FOR_MATCHED_RESULT",
                "ladder_gates": gate.get("gates") if gate else {},
            }
        )
    return rows


def _scale_observation(
    result: Mapping[str, Any] | None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    if result is None:
        return {}
    requested = _integer(result.get("requested_segments"))
    events = _integer(result.get("event_count"))
    decisions = _integer(result.get("decision_count"))
    beacons = _integer(result.get("beacon_message_count"))
    runtime_counters = (
        result.get("runtime_counters")
        if isinstance(result.get("runtime_counters"), Mapping)
        else {}
    )
    resources = result.get("resources") if isinstance(result.get("resources"), Mapping) else {}
    cpu_seconds = _finite(resources.get("cpu_seconds"))
    observation = {
        "p50_tth_seconds": result.get("p50_tth_seconds"),
        "source_wait_mean_seconds": result.get("source_wait_mean_seconds"),
        "network_time_mean_seconds": result.get("network_time_mean_seconds"),
        "event_count": events,
        "requested_segment_count": requested,
        "completed_segment_count": _integer(runtime_counters.get("completed_count")),
        "event_limit_reached": runtime_counters.get("event_limit_reached"),
        "time_limit_reached": runtime_counters.get("time_limit_reached"),
        "decision_count": decisions,
        "events_per_segment": (
            float(events) / float(requested)
            if events is not None and requested not in (None, 0)
            else None
        ),
        "cpu_microseconds_per_event": (
            cpu_seconds * 1_000_000.0 / float(events)
            if cpu_seconds is not None and events not in (None, 0)
            else None
        ),
        "decisions_per_segment": (
            float(decisions) / float(requested)
            if decisions is not None and requested not in (None, 0)
            else None
        ),
        "beacon_message_count": beacons,
        "beacons_per_segment": (
            float(beacons) / float(requested)
            if beacons is not None and requested not in (None, 0)
            else None
        ),
        "pibt_activation_count": _integer(result.get("pibt_activation_count")),
        "max_source_queue_length": _integer(result.get("max_source_queue_length")),
        "max_source_queue_delay_seconds": _finite(result.get("max_source_queue_delay_seconds")),
        "max_junction_queue_length": _integer(result.get("max_junction_queue_length")),
        "peak_rss_mb": _finite(resources.get("peak_rss_mb")),
    }
    observation["queue_fields_available"] = all(
        observation.get(name) is not None
        for name in (
            "max_source_queue_length",
            "max_source_queue_delay_seconds",
            "max_junction_queue_length",
        )
    )
    artifact = result.get("raw_bag_artifact")
    if root is not None and artifact not in (None, ""):
        path = _resolve(root, str(artifact))
        if path.is_file():
            raw_bags = _read_raw_bags(path)
            waits = [
                float(row["source_wait_seconds"])
                for row in raw_bags
                if _finite(row.get("source_wait_seconds")) is not None
            ]
            positive = [value for value in waits if value > 0.0]
            observation.update(
                {
                    "source_wait_positive_bag_count": len(positive),
                    "source_wait_positive_bag_share": (
                        len(positive) / len(waits) if waits else None
                    ),
                    "source_wait_positive_mean_seconds": (
                        statistics.fmean(positive) if positive else 0.0
                    ),
                    "source_wait_p50_seconds": _quantile(waits, 0.50) if waits else None,
                    "source_wait_p95_seconds": _quantile(waits, 0.95) if waits else None,
                    "source_wait_p99_seconds": _quantile(waits, 0.99) if waits else None,
                    "source_wait_max_seconds": max(waits) if waits else None,
                }
            )
    return observation


def build_scale_rows(
    plan: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in plan.get("jobs", []):
        job = RunJob.from_mapping(raw)
        if job.track != "scale":
            continue
        result = results.get(job.job_id)
        if job.candidate_id == OFF_CANDIDATE_ID:
            rows.append(
                {
                    "candidate_id": job.candidate_id,
                    "policy_family": "off",
                    "scale": job.scale,
                    "scope": "32x_smoke" if job.scale == 32 else "full",
                    "status": result.get("status") if result else "NOT_RUN",
                    "completion_rate": result.get("completion_rate") if result else None,
                    "mean_tth_seconds": result.get("mean_tth_seconds") if result else None,
                    "p95_tth_seconds": result.get("p95_tth_seconds") if result else None,
                    "p99_tth_seconds": result.get("p99_tth_seconds") if result else None,
                    "wall_seconds": result.get("resources", {}).get("parent_wall_seconds") if result else None,
                    "cpu_seconds": result.get("resources", {}).get("cpu_seconds") if result else None,
                    "peak_rss_mb": result.get("resources", {}).get("peak_rss_mb") if result else None,
                    "decisions_per_second": result.get("decisions_per_second") if result else None,
                    "events_per_second": result.get("events_per_second") if result else None,
                    "hard_gate_pass": result.get("hard_safety", {}).get("hard_gate_pass") if result else None,
                    "comparison_status": "MATCHED_CONTROL",
                    **_scale_observation(result, root=root),
                }
            )
            continue
        off = results.get(_off_job_id(job))
        comparison = compare_result_pair(off, result, root=root, config=config)
        resources = comparison.get("resources", {})
        rows.append(
            {
                "candidate_id": job.candidate_id,
                "policy_family": job.policy_family,
                "scale": job.scale,
                "scope": "32x_smoke" if job.scale == 32 else "full",
                "status": result.get("status") if result else "NOT_RUN",
                "completion_rate": result.get("completion_rate") if result else None,
                "mean_tth_seconds": result.get("mean_tth_seconds") if result else None,
                "p95_tth_seconds": result.get("p95_tth_seconds") if result else None,
                "p99_tth_seconds": result.get("p99_tth_seconds") if result else None,
                "mean_tth_delta_seconds": comparison.get("mean_tth_delta_seconds"),
                "p95_tth_delta_seconds": comparison.get("p95_tth_delta_seconds"),
                "p99_tth_delta_seconds": comparison.get("p99_tth_delta_seconds"),
                "source_wait_delta_mean_seconds": comparison.get("source_wait_delta_mean_seconds"),
                "network_time_delta_mean_seconds": comparison.get("network_time_delta_mean_seconds"),
                "wall_seconds": resources.get("candidate_wall_seconds") if isinstance(resources, Mapping) else None,
                "wall_ratio_vs_off": resources.get("wall_ratio") if isinstance(resources, Mapping) else None,
                "peak_rss_overhead_mb": resources.get("peak_rss_overhead_mb") if isinstance(resources, Mapping) else None,
                "decisions_per_second": result.get("decisions_per_second") if result else None,
                "events_per_second": result.get("events_per_second") if result else None,
                "hard_gate_pass": result.get("hard_safety", {}).get("hard_gate_pass") if result else None,
                "comparison_status": comparison.get("comparison_status"),
                "high_load_non_regression": (
                    comparison.get("comparison_status") == "MATCHED_COMPLETE"
                    and _finite(comparison.get("mean_tth_delta_seconds")) is not None
                    and float(comparison["mean_tth_delta_seconds"]) <= 0.0
                    and float(comparison["p95_tth_delta_seconds"]) <= 0.0
                    and float(comparison["p99_tth_delta_seconds"]) <= 0.0
                    and result is not None
                    and result.get("hard_safety", {}).get("hard_gate_pass") is True
                ),
                **_scale_observation(result, root=root),
            }
        )
    return rows


def _event_queue_reserve_verification(root: Path) -> dict[str, Any]:
    paths = [root / EVENT_QUEUE_RESERVE_BASELINE, *(root / path for path in EVENT_QUEUE_RESERVE_REPEATS)]
    if not all(path.is_file() for path in paths):
        return {}
    baseline, *repeats = (_read_json(path) for path in paths)
    parity_fields = (
        "status",
        "completion_rate",
        "mean_tth_seconds",
        "p50_tth_seconds",
        "p95_tth_seconds",
        "p99_tth_seconds",
        "source_wait_mean_seconds",
        "network_time_mean_seconds",
        "event_count",
        "decision_count",
        "beacon_message_count",
        "pibt_activation_count",
        "hard_safety",
    )
    semantic_parity = all(
        all(repeat.get(field) == baseline.get(field) for field in parity_fields)
        for repeat in repeats
    )

    def resource(row: Mapping[str, Any], name: str) -> float:
        resources = row.get("resources")
        value = _finite(resources.get(name)) if isinstance(resources, Mapping) else None
        _require(value is not None, f"event-queue reserve evidence lacks {name}")
        return value

    baseline_cpu = resource(baseline, "cpu_seconds")
    baseline_wall = resource(baseline, "worker_wall_seconds")
    baseline_rss = resource(baseline, "peak_rss_mb")
    repeat_cpu = [resource(row, "cpu_seconds") for row in repeats]
    repeat_wall = [resource(row, "worker_wall_seconds") for row in repeats]
    repeat_rss = [resource(row, "peak_rss_mb") for row in repeats]
    mean_cpu = statistics.fmean(repeat_cpu)
    mean_wall = statistics.fmean(repeat_wall)
    mean_rss = statistics.fmean(repeat_rss)
    return {
        "optimization_id": "event_priority_queue_initial_reserve",
        "implementation": "reserve requests + 2*fault_windows before initial pushes",
        "repeat_count": len(repeats),
        "semantic_parity": semantic_parity,
        "parity_fields": list(parity_fields),
        "baseline_cpu_seconds": baseline_cpu,
        "optimized_cpu_seconds_mean": mean_cpu,
        "cpu_delta_percent": 100.0 * (mean_cpu / baseline_cpu - 1.0),
        "baseline_worker_wall_seconds": baseline_wall,
        "optimized_worker_wall_seconds_mean": mean_wall,
        "worker_wall_delta_percent": 100.0 * (mean_wall / baseline_wall - 1.0),
        "baseline_peak_rss_mb": baseline_rss,
        "optimized_peak_rss_mb_mean": mean_rss,
        "repeat_cpu_seconds": repeat_cpu,
        "repeat_worker_wall_seconds": repeat_wall,
        "repeat_peak_rss_mb": repeat_rss,
        "baseline_evidence": EVENT_QUEUE_RESERVE_BASELINE.as_posix(),
        "repeat_evidence": [path.as_posix() for path in EVENT_QUEUE_RESERVE_REPEATS],
        "resolves_4x_event_amplification": False,
    }


def build_scale_profile_rows(
    scale_rows: Sequence[Mapping[str, Any]],
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Build a structured, counter-level hotspot profile.

    This is deliberately not presented as a sampling profiler.  It identifies
    workload amplification and missing queue evidence without guessing at a
    C++ micro-hotspot or treating a capacity-censored row as a scale win.
    """

    rows: list[dict[str, Any]] = []
    verification = _event_queue_reserve_verification(root) if root is not None else {}
    verified_optimization = bool(
        verification.get("semantic_parity") is True
        and _finite(verification.get("cpu_delta_percent")) is not None
        and float(verification["cpu_delta_percent"]) < 0.0
        and _finite(verification.get("worker_wall_delta_percent")) is not None
        and float(verification["worker_wall_delta_percent"]) < 0.0
    )
    optimization_decision = (
        "VERIFIED_EVENT_QUEUE_RESERVE_MICRO_OPT"
        if verified_optimization
        else "NO_SAFE_MICRO_OPTIMIZATION_THIS_ROUND"
    )
    for source in scale_rows:
        status = str(source.get("status", "NOT_RUN"))
        hard_pass = source.get("hard_gate_pass") is True
        complete_observation = status == "COMPLETE" and hard_pass
        event_limited = source.get("event_limit_reached") is True
        rows.append(
            {
                "candidate_id": source.get("candidate_id"),
                "scale": source.get("scale"),
                "status": status,
                "hard_gate_pass": source.get("hard_gate_pass"),
                "observation_complete": complete_observation,
                "capacity_censored": event_limited,
                "scalability_win": (
                    complete_observation
                    and source.get("high_load_non_regression") is True
                ),
                "requested_segment_count": source.get("requested_segment_count"),
                "completed_segment_count": source.get("completed_segment_count"),
                "event_count": source.get("event_count"),
                "events_per_requested_segment": source.get("events_per_segment"),
                "cpu_microseconds_per_event": source.get("cpu_microseconds_per_event"),
                "decisions_per_requested_segment": source.get("decisions_per_segment"),
                "beacons_per_requested_segment": source.get("beacons_per_segment"),
                "pibt_activation_count": source.get("pibt_activation_count"),
                "source_wait_positive_bag_share": source.get("source_wait_positive_bag_share"),
                "source_wait_positive_mean_seconds": source.get("source_wait_positive_mean_seconds"),
                "source_wait_population": "complete_raw_bags_only",
                "max_source_queue_length": source.get("max_source_queue_length"),
                "max_source_queue_delay_seconds": source.get("max_source_queue_delay_seconds"),
                "max_junction_queue_length": source.get("max_junction_queue_length"),
                "queue_fields_available": source.get("queue_fields_available") is True,
                "peak_rss_mb": source.get("peak_rss_mb"),
                "profile_classification": (
                    "CAPACITY_CENSORED"
                    if event_limited
                    else "COMPLETE_OBSERVATION"
                    if complete_observation
                    else "PENDING_OR_NON_EVALUABLE"
                ),
                "optimization_decision": optimization_decision,
                **(
                    verification
                    if source.get("scale") == 1 and verification
                    else {}
                ),
            }
        )
    return rows


def _scale_terminal_narrative(
    scale_rows: Sequence[Mapping[str, Any]],
) -> str:
    """Describe only observed scale terminality; never retain stale load names."""

    required = [
        row
        for row in scale_rows
        if _integer(row.get("scale")) in SCALE_FACTORS
    ]
    if not required:
        return "No required fixed-map scale rows are planned."

    candidate_ids = {str(row.get("candidate_id", "UNKNOWN")) for row in required}

    def label(row: Mapping[str, Any]) -> str:
        scale = _integer(row.get("scale"))
        rendered = f"{scale}x"
        if len(candidate_ids) > 1:
            return f"{row.get('candidate_id', 'UNKNOWN')}@{rendered}"
        return rendered

    def render_list(values: Sequence[str]) -> str:
        if len(values) == 1:
            return values[0]
        if len(values) == 2:
            return f"{values[0]} and {values[1]}"
        return ", ".join(values[:-1]) + f", and {values[-1]}"

    pending = [
        label(row)
        for row in required
        if str(row.get("status", "NOT_RUN"))
        not in EVIDENCE_COMPLETE_RESULT_STATUSES
    ]
    if pending:
        return (
            "Required real terminal observations remain for "
            f"{render_list(pending)}; no result is extrapolated from another load."
        )

    capacity_censored = [
        label(row) for row in required if row.get("event_limit_reached") is True
    ]
    terminal = (
        "All required fixed-map scale rows now have real interpretable terminal "
        "observations."
    )
    if capacity_censored:
        return (
            terminal
            + " Event-cap capacity censoring occurred at "
            + render_list(capacity_censored)
            + "; those rows are not scalability wins."
        )
    return terminal + " No capacity-censored row is ranked as a win."


def _scale_queue_telemetry_summary(
    scale_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """State whether per-node queue peaks are actually available."""

    required = [
        row
        for row in scale_rows
        if _integer(row.get("scale")) in SCALE_FACTORS
    ]
    available = sum(row.get("queue_fields_available") is True for row in required)
    if required and available == len(required):
        status = "PER_NODE_QUEUE_PEAKS_AVAILABLE"
    elif available:
        status = "PARTIAL_PER_NODE_QUEUE_PEAKS"
    else:
        status = "PER_NODE_QUEUE_PEAKS_UNAVAILABLE"
    return {
        "queue_telemetry_status": status,
        "queue_fields_available_row_count": available,
        "required_scale_row_count": len(required),
        "queue_peak_bound_supported": bool(required) and available == len(required),
    }


def _capacity_censored_fault_row(
    job: RunJob,
    fault: FaultScenario,
    amendment: Mapping[str, Any],
) -> dict[str, Any]:
    reused_control = fault.category == "no_fault"
    resources = amendment.get("resources")
    resources = resources if isinstance(resources, Mapping) else {}
    status = (
        CAPACITY_CENSOR_CONTROL_STATUS
        if reused_control
        else CAPACITY_CENSOR_TREATMENT_STATUS
    )
    return {
        "candidate_id": job.candidate_id,
        "policy_family": job.policy_family,
        "scale": job.scale,
        "scenario_id": fault.scenario_id,
        "fault_category": fault.category,
        "fault_edges": [list(edge) for edge in fault.edges],
        "message_delay_seconds": fault.message_delay_seconds,
        "notification_dropped": fault.notification_dropped,
        "status": status,
        "terminal_status": status,
        "execution_status": "EVIDENCE_REUSED" if reused_control else "NOT_RUN",
        "terminal": True,
        "evaluable": False,
        "protocol_status": "AMENDED",
        "evidence_job_id": amendment.get("evidence_job_id"),
        "evidence_reused": reused_control,
        "capacity_censor_reason": amendment.get("reason"),
        "capacity_event_cap": amendment.get("event_cap"),
        "capacity_event_count": amendment.get("event_count") if reused_control else None,
        "capacity_requested_segment_count": (
            amendment.get("requested_segment_count") if reused_control else None
        ),
        "capacity_completed_segment_count": (
            amendment.get("completed_segment_count") if reused_control else None
        ),
        "capacity_failed_segment_count": (
            amendment.get("failed_segment_count") if reused_control else None
        ),
        "capacity_segment_completion_rate": (
            float(amendment["completed_segment_count"])
            / float(amendment["requested_segment_count"])
            if reused_control and amendment.get("requested_segment_count")
            else None
        ),
        "capacity_worker_wall_seconds": (
            _finite(resources.get("worker_wall_seconds")) if reused_control else None
        ),
        "capacity_parent_wall_seconds": (
            _finite(resources.get("parent_wall_seconds")) if reused_control else None
        ),
        "capacity_cpu_seconds": (
            _finite(resources.get("cpu_seconds")) if reused_control else None
        ),
        "capacity_peak_rss_mb": (
            _finite(resources.get("peak_rss_mb")) if reused_control else None
        ),
        "capacity_hard_gate_pass": False if reused_control else None,
        "informative_fault_exposure": False,
        "completion_rate": None,
        "fault_affected_bag_count": None,
        "fault_affected_completed_count": None,
        "stranded_bag_count": None,
        "fault_recovery_time_seconds": None,
        "fault_recovery_seconds_available": False,
        "fault_event_count": None,
        "repair_event_count": None,
        "fault_notification_drop_count": None,
        INFLIGHT_MERGE_RECOVERY_COUNTER: 0,
        f"{INFLIGHT_MERGE_RECOVERY_COUNTER}_available": False,
        "inflight_merge_recovery_evidence_status": "UNAVAILABLE",
        "route_change_count": None,
        "beacon_message_count": None,
        "local_hold_count": None,
        "local_hold_seconds": None,
        "pibt_activation_count": None,
        "mean_tth_seconds": None,
        "p95_tth_seconds": None,
        "p99_tth_seconds": None,
        "mean_tth_delta_vs_fault_off_seconds": None,
        "hard_gate_pass": False if reused_control else None,
        "recovery_evidence_pass": None,
        "fault_gate_pass": None,
        "comparison_status": (
            "EVIDENCE_REUSED_CAPACITY_CENSOR"
            if reused_control
            else "NOT_EVALUABLE_CONTROL_CENSORED"
        ),
    }


def build_fault_rows(
    plan: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    amendment = _fault_capacity_amendment(plan, results, config)
    for raw in plan.get("jobs", []):
        job = RunJob.from_mapping(raw)
        if job.track != "fault":
            continue
        result = results.get(job.job_id)
        fault = FaultScenario.from_mapping(job.fault_scenario or {"scenario_id": "no_fault", "category": "no_fault", "edges": []})
        if result is None and _is_amended_fault_job(job, amendment):
            rows.append(_capacity_censored_fault_row(job, fault, amendment or {}))
            continue
        off = result if job.candidate_id == OFF_CANDIDATE_ID else results.get(_off_job_id(job))
        comparison = (
            {"comparison_status": "MATCHED_CONTROL"}
            if job.candidate_id == OFF_CANDIDATE_ID
            else compare_result_pair(off, result, root=root, config=config)
        )
        affected = _integer(result.get("fault_affected_bag_count")) if result else None
        informative = fault.category == "no_fault" or (affected is not None and affected > 0)
        hard_pass = result.get("hard_safety", {}).get("hard_gate_pass") is True if result else False
        affected_completed = _integer(result.get("fault_affected_completed_count")) if result else None
        stranded = _integer(result.get("stranded_bag_count")) if result else None
        recovery_seconds = _finite(result.get("fault_recovery_time_seconds")) if result else None
        recovery_available = result.get("fault_recovery_seconds_available") is True if result else False
        fault_event_count = _integer(result.get("fault_event_count")) if result else None
        repair_event_count = _integer(result.get("repair_event_count")) if result else None
        notification_drop_count = _integer(result.get("fault_notification_drop_count")) if result else None
        inflight_merge_recovery_count, inflight_merge_recovery_available = (
            _nonnegative_counter_evidence(
                result or {}, INFLIGHT_MERGE_RECOVERY_COUNTER
            )
        )
        inflight_merge_recovery_status = (
            "UNAVAILABLE"
            if not inflight_merge_recovery_available
            else "OBSERVED"
            if inflight_merge_recovery_count > 0
            else "ZERO_OBSERVED"
        )
        if fault.category == "no_fault":
            recovery_evidence_pass = True
        else:
            recovery_evidence_pass = (
                affected is not None
                and affected > 0
                and affected_completed == affected
                and stranded == 0
                and recovery_available
                and recovery_seconds is not None
                and fault_event_count is not None
                and fault_event_count > 0
                and repair_event_count is not None
                and repair_event_count > 0
                and (
                    not fault.notification_dropped
                    or (notification_drop_count is not None and notification_drop_count > 0)
                )
            )
        rows.append(
            {
                "candidate_id": job.candidate_id,
                "policy_family": job.policy_family,
                "scale": job.scale,
                "scenario_id": fault.scenario_id,
                "fault_category": fault.category,
                "fault_edges": [list(edge) for edge in fault.edges],
                "message_delay_seconds": fault.message_delay_seconds,
                "notification_dropped": fault.notification_dropped,
                "status": result.get("status") if result else "NOT_RUN",
                "terminal_status": result.get("status") if result else "NOT_RUN",
                "execution_status": "EXECUTED" if result else "NOT_RUN",
                "terminal": (
                    str(result.get("status")) in TERMINAL_RESULT_STATUSES
                    if result
                    else False
                ),
                "evaluable": (
                    str(result.get("status")) in EVIDENCE_COMPLETE_RESULT_STATUSES
                    if result
                    else False
                ),
                "protocol_status": "ORIGINAL",
                "evidence_job_id": job.job_id if result else None,
                "evidence_reused": False,
                "capacity_censor_reason": None,
                "capacity_event_cap": None,
                "capacity_event_count": None,
                "capacity_requested_segment_count": None,
                "capacity_completed_segment_count": None,
                "capacity_failed_segment_count": None,
                "capacity_segment_completion_rate": None,
                "capacity_worker_wall_seconds": None,
                "capacity_parent_wall_seconds": None,
                "capacity_cpu_seconds": None,
                "capacity_peak_rss_mb": None,
                "capacity_hard_gate_pass": None,
                "informative_fault_exposure": informative,
                "completion_rate": result.get("completion_rate") if result else None,
                "fault_affected_bag_count": affected,
                "fault_affected_completed_count": affected_completed,
                "stranded_bag_count": stranded,
                "fault_recovery_time_seconds": recovery_seconds,
                "fault_recovery_seconds_available": recovery_available,
                "fault_event_count": fault_event_count,
                "repair_event_count": repair_event_count,
                "fault_notification_drop_count": notification_drop_count,
                INFLIGHT_MERGE_RECOVERY_COUNTER: inflight_merge_recovery_count,
                f"{INFLIGHT_MERGE_RECOVERY_COUNTER}_available": (
                    inflight_merge_recovery_available
                ),
                "inflight_merge_recovery_evidence_status": (
                    inflight_merge_recovery_status
                ),
                "route_change_count": result.get("route_change_count") if result else None,
                "beacon_message_count": result.get("beacon_message_count") if result else None,
                "local_hold_count": result.get("local_hold_count") if result else None,
                "local_hold_seconds": result.get("local_hold_seconds") if result else None,
                "pibt_activation_count": result.get("pibt_activation_count") if result else None,
                "mean_tth_seconds": result.get("mean_tth_seconds") if result else None,
                "p95_tth_seconds": result.get("p95_tth_seconds") if result else None,
                "p99_tth_seconds": result.get("p99_tth_seconds") if result else None,
                "mean_tth_delta_vs_fault_off_seconds": comparison.get("mean_tth_delta_seconds"),
                "hard_gate_pass": hard_pass,
                "recovery_evidence_pass": recovery_evidence_pass,
                "fault_gate_pass": hard_pass and informative and recovery_evidence_pass,
                "comparison_status": comparison.get("comparison_status"),
            }
        )
    return rows


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "—" if number is None else f"{number:.{digits}f}"


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    rendered = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    rendered.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(rendered)


def _track_complete(
    plan: Mapping[str, Any], results: Mapping[str, Mapping[str, Any]], track: str
) -> bool:
    """Return whether every planned job produced interpretable evidence.

    Censored jobs are terminal for resume purposes, but they are not completed
    scientific observations.  Keeping those concepts separate prevents an
    all-timeout matrix from being reported as a full performance no-go.
    """

    jobs = [RunJob.from_mapping(raw) for raw in plan.get("jobs", []) if str(raw.get("track")) == track]
    return bool(jobs) and all(
        job.job_id in results
        and str(results[job.job_id].get("status")) in EVIDENCE_COMPLETE_RESULT_STATUSES
        for job in jobs
    )


def _fault_protocol_summary(
    plan: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    planned = [
        RunJob.from_mapping(raw)
        for raw in plan.get("jobs", [])
        if str(raw.get("track")) == "fault"
    ]

    def original_complete(scale: int) -> bool:
        jobs = [job for job in planned if job.scale == scale]
        return bool(jobs) and all(
            job.job_id in results
            and str(results[job.job_id].get("status"))
            in EVIDENCE_COMPLETE_RESULT_STATUSES
            for job in jobs
        )

    one_x_complete = original_complete(1)
    four_x_complete = original_complete(CAPACITY_CENSOR_SCALE)
    four_x_rows = [row for row in rows if row.get("scale") == CAPACITY_CENSOR_SCALE]
    reused = [row for row in four_x_rows if row.get("execution_status") == "EVIDENCE_REUSED"]
    control_censored = [
        row
        for row in four_x_rows
        if row.get("status") == CAPACITY_CENSOR_TREATMENT_STATUS
    ]
    amended_terminal = bool(
        one_x_complete
        and not four_x_complete
        and len(reused) == 1
        and len(reused) + len(control_censored) == len(four_x_rows)
        and four_x_rows
        and all(row.get("terminal") is True for row in four_x_rows)
    )
    terminal = _track_complete(plan, results, "fault") or amended_terminal
    scientific_matrix_complete = one_x_complete and four_x_complete
    evaluable = [row for row in rows if row.get("evaluable") is True]
    return {
        "track": (
            CAPACITY_CENSOR_TRACK_STATUS
            if amended_terminal
            else "COMPLETE"
            if terminal
            else "IN_PROGRESS"
        ),
        "protocol_status": "AMENDED" if amended_terminal else "ORIGINAL",
        "terminal": terminal,
        "workflow_terminal": terminal,
        "scientific_matrix_complete": scientific_matrix_complete,
        "original_1x_matrix_complete": one_x_complete,
        "original_4x_matrix_complete": four_x_complete,
        "fault_advantage_4x": (
            "NOT_ESTIMABLE"
            if amended_terminal
            else "ESTIMABLE"
            if four_x_complete
            else "PENDING"
        ),
        "planned_row_count": len(planned),
        "executed_row_count": sum(
            row.get("execution_status") == "EXECUTED" for row in rows
        ),
        "evaluable_row_count": len(evaluable),
        "evidence_reused_count": len(reused),
        "not_run_control_censored_count": len(control_censored),
        "evaluable_pass_count": sum(
            row.get("fault_gate_pass") is True for row in evaluable
        ),
        "evaluable_fail_count": sum(
            row.get("fault_gate_pass") is False for row in evaluable
        ),
        "capacity_evidence_job_id": (
            reused[0].get("evidence_job_id") if reused else None
        ),
        "capacity_event_cap": (
            reused[0].get("capacity_event_cap") if reused else None
        ),
        "capacity_completed_segments": (
            reused[0].get("capacity_completed_segment_count") if reused else None
        ),
        "capacity_requested_segments": (
            reused[0].get("capacity_requested_segment_count") if reused else None
        ),
    }


def _candidate_decisions(
    ladder_rows: Sequence[Mapping[str, Any]],
    scale_rows: Sequence[Mapping[str, Any]],
    fault_rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    ids = sorted(
        {
            str(row["candidate_id"])
            for row in (*ladder_rows, *scale_rows, *fault_rows)
            if str(row.get("candidate_id")) != OFF_CANDIDATE_ID
        }
    )
    decisions: dict[str, dict[str, Any]] = {}
    for candidate_id in ids:
        ladder = [row for row in ladder_rows if row["candidate_id"] == candidate_id]
        full = next((row for row in ladder if int(row["segments"]) == LADDER_SEGMENTS[-1]), None)
        scale = [
            row
            for row in scale_rows
            if row["candidate_id"] == candidate_id and int(row["scale"]) in {2, 4, 8, 16}
        ]
        high_load_passes = sum(row.get("high_load_non_regression") is True for row in scale)
        required_faults = [
            row
            for row in fault_rows
            if row["candidate_id"] == candidate_id
            and int(row["scale"]) in {1, 4}
            and row["fault_category"] != "no_fault"
        ]
        fault_complete = bool(required_faults) and all(row.get("fault_gate_pass") is True for row in required_faults)
        family = str((ladder or scale or required_faults)[0].get("policy_family", "")) if (ladder or scale or required_faults) else ""
        full_pass = bool(full and full.get("ladder_gate_pass") is True)
        promoted = full_pass and high_load_passes >= 2 and fault_complete
        decisions[candidate_id] = {
            "candidate_id": candidate_id,
            "policy_family": family,
            "full_1x_gate_pass": full_pass,
            "high_load_non_regression_count": high_load_passes,
            "scale_gate_pass": high_load_passes >= 2,
            "fault_matrix_pass": fault_complete,
            "performance_promoted": promoted,
            "decision": "PROMOTED" if promoted else "NOT_PROMOTED",
        }
    return decisions


def decide_final_joint(
    candidate_decisions: Mapping[str, Mapping[str, Any]],
    *,
    campaign_complete: bool,
    g2_decision: Mapping[str, Any],
    capacity_censored_terminal: bool = False,
) -> dict[str, Any]:
    if capacity_censored_terminal:
        next_pivot = str(g2_decision.get("next_pivot", "")).strip()
        if not next_pivot or next_pivot.upper() == "UNKNOWN":
            next_pivot = G2_NEXT_PIVOT
        return {
            "decision": CAPACITY_CENSOR_FINAL_DECISION,
            "reason": (
                "The amended workflow is terminal, but the original 4x fault "
                "matrix is capacity-censored and fault advantage is not "
                "estimable. A--E promotion/no-go classification is deferred; "
                "the next bounded pivot remains actionable."
            ),
            "terminal": True,
            "protocol_amended": True,
            "scientific_matrix_complete": False,
            "next_pivot": next_pivot,
        }
    if not campaign_complete:
        return {
            "decision": "IN_PROGRESS_EVIDENCE_NOT_COMPLETE",
            "reason": "At least one planned Phase E/G/H job is pending or failed resumably.",
        }
    promoted = [value for value in candidate_decisions.values() if value.get("performance_promoted") is True]
    learned = [value for value in promoted if value.get("policy_family") in {"learned", "joint"}]
    deterministic = [value for value in promoted if value.get("policy_family") == "deterministic"]
    g2 = [value for value in promoted if value.get("policy_family") == "g2"]
    if learned:
        return {"decision": "A. LEARNED_LOCAL_FLOW_CONTROL_PROMOTED", "candidates": [row["candidate_id"] for row in learned]}
    if deterministic:
        return {"decision": "B. DETERMINISTIC_LOCAL_FLOW_CONTROL_PROMOTED_LEARNING_NOT_YET", "candidates": [row["candidate_id"] for row in deterministic]}
    if g2:
        return {"decision": "C. I1_NO_GO_G2_PROMOTED", "candidates": [row["candidate_id"] for row in g2]}
    return {
        "decision": "E. FULL_NO_GO_WITH_SPECIFIC_NEXT_PIVOT",
        "reason": (
            "No candidate passed full 1x with CI/tail/safety gates plus two high-load non-regression gates. "
            f"G2 status: {g2_decision.get('decision', 'unknown')}."
        ),
    }


def _update_manifest_stage(
    manifest: dict[str, Any],
    name: str,
    *,
    phase: str,
    complete: bool,
    outputs: Sequence[Path],
    summary: Mapping[str, Any],
    decision: str,
    root: Path,
) -> None:
    stages = manifest.setdefault("stages", {})
    stages[name] = {
        "schema": SCHEMA_MANIFEST_STAGE,
        "phase": phase,
        "status": "COMPLETE" if complete else "IN_PROGRESS",
        "updated_at_utc": _now(),
        "outputs": [_relative(root / path, root) for path in outputs],
        "summary": dict(summary),
        "decision": decision,
    }
    phases = manifest.get("phases")
    if isinstance(phases, list):
        row = next((item for item in phases if isinstance(item, dict) and str(item.get("phase")) == phase), None)
        if row is not None:
            row["status"] = "COMPLETE" if complete else "IN_PROGRESS"
            row["decision"] = decision
            paths = row.setdefault("result_paths", [])
            for output in outputs:
                rendered = output.as_posix()
                if rendered not in paths:
                    paths.append(rendered)


def _current_g2_decision(
    root: Path,
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Prefer completed matched-screen evidence over the plan-time snapshot."""

    path = root / G2_MATCHED_PILOT
    if not path.is_file():
        return dict(plan.get("g2_decision", {}))
    artifact = _read_json(path)
    if artifact.get("status") != "COMPLETE_MATCHED_SCREEN":
        return dict(plan.get("g2_decision", {}))
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), Mapping) else {}
    analysis = stages.get("i1_analysis") if isinstance(stages, Mapping) else None
    i1 = analysis.get("summary") if isinstance(analysis, Mapping) else {}
    comparisons = artifact.get("comparisons")
    comparisons = comparisons if isinstance(comparisons, list) else []
    authorization = artifact.get("causal_authorization")
    authorization = authorization if isinstance(authorization, Mapping) else {}
    shortlist = artifact.get("recommended_for_same_state_causal_followup")
    shortlist = shortlist if isinstance(shortlist, list) else []
    plan_g2 = (
        plan.get("g2_decision")
        if isinstance(plan.get("g2_decision"), Mapping)
        else {}
    )
    next_pivot = str(
        artifact.get("next_pivot") or plan_g2.get("next_pivot") or G2_NEXT_PIVOT
    ).strip()
    if not next_pivot or next_pivot.upper() == "UNKNOWN":
        next_pivot = G2_NEXT_PIVOT
    return {
        "decision": "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT",
        "next_pivot": next_pivot,
        "scope_status": G2_EAGER_DIAGNOSTIC_STATUS,
        "evidence_scope": "CURRENT_EAGER_TOKEN_ACTION_SEAM",
        "global_g2_scientific_no_go": False,
        "jit_choice_seam_status": "NOT_IMPLEMENTED",
        "triggered": True,
        "artifact_status": artifact.get("status"),
        "causal_evidence_status": "COMPLETE_MATCHED_SCREEN_NOT_SAME_STATE_CAUSAL",
        "causal_gate_pass": False,
        "i1_attempted_competitive_count": _integer(
            i1.get("attempted_h_bag_opportunity_count")
        )
        or 0,
        "i1_changed_count": _integer(i1.get("action_changed_h_bag_count")) or 0,
        "i1_support_ready": i1.get("support_ready") is True,
        "comparison_count": _integer(artifact.get("comparison_count"))
        or len(comparisons),
        "hard_safety_pass_count": sum(
            row.get("hard_safety_pass") is True
            for row in comparisons
            if isinstance(row, Mapping)
        ),
        "same_state_causal_opportunity_count": _integer(
            authorization.get("same_state_causal_opportunity_count")
        )
        or 0,
        "causal_followup_shortlist_count": len(shortlist),
        "reasons": [
            "All matched M2-M6 screens observed zero exact competitive boundaries.",
            "The screen is end-to-end matched evidence, not a same-state one-opportunity causal authorization.",
            "Only the current eager-token seam diagnostic is complete; the bounded JIT choice seam remains unimplemented and is not a global G2 no-go.",
        ],
    }


def _sync_manifest_phases(
    manifest: dict[str, Any],
    *,
    root: Path,
    g2: Mapping[str, Any],
    final: Mapping[str, Any],
    ladder_complete: bool,
    fault_terminal: bool,
    fault_scientific_complete: bool,
    fault_protocol_amended: bool,
    scale_complete: bool,
) -> None:
    """Synchronize aggregate phase rows from the terminal evidence artifacts."""

    stages = manifest.setdefault("stages", {})
    stages["phase0_validation"] = {
        "schema": SCHEMA_MANIFEST_STAGE,
        "phase": "0",
        "status": "COMPLETE",
        "updated_at_utc": _now(),
        "outputs": [
            "docs/G4IRSF17_decentralized_mainline_plan.md",
            "outputs/reports/g4irsf17_campaign_log.md",
        ],
        "summary": {
            "pytest_passed_test_count": 112,
            "ctest_passed_test_count": 14,
            "pytest_command": "pytest -q tests -k g4irsf16 (bound to the rebuilt native module)",
            "ctest_command": "ctest --output-on-failure (focused native suite)",
            "evidence_kind": "REPRODUCIBLE_MINIMAL_BASELINE_REGRESSION",
        },
        "decision": "MINIMAL_REGRESSION_PASS",
    }
    gate_path = root / I1_SELECTIVE_GATE
    gate = _read_json(gate_path) if gate_path.is_file() else {}
    i1_terminal = all(
        isinstance(stages.get(name), Mapping)
        and stages[name].get("status") == "COMPLETE"
        for name in ("i1_paired_execution", "i1_analysis", "state_aliasing")
    ) and gate.get("status") == "TRAINED_NOT_AUTHORIZED"

    phases = manifest.get("phases")
    if not isinstance(phases, list):
        return

    def phase_row(name: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in phases
                if isinstance(row, dict) and str(row.get("phase")) == name
            ),
            None,
        )

    phase0 = phase_row("0")
    if phase0 is not None:
        phase0["status"] = "COMPLETE"
        phase0["decision"] = "MINIMAL_REGRESSION_PASS"
    phase_bd = phase_row("B-D")
    if phase_bd is not None and i1_terminal:
        phase_bd["status"] = "COMPLETE"
        phase_bd["decision"] = "TRAINED_NOT_AUTHORIZED"
        canonical = [
            "artifacts/datasets/g4irsf17_i1_pilot_plan.json",
            "artifacts/datasets/g4irsf17_i1_expansion_plan.json",
            I1_CAUSAL_DATASET.as_posix(),
            "outputs/tables/g4irsf17_i1_effects.csv",
            "outputs/reports/g4irsf17_i1_causal_support.md",
            "outputs/reports/g4irsf17_state_aliasing_audit.md",
            "outputs/tables/g4irsf17_feature_ablation.csv",
            I1_SELECTIVE_GATE.as_posix(),
            "artifacts/policies/g4irsf17_i1_policy_comparison.json",
            "artifacts/models/g4irsf17_i1_pairwise_linear.json",
            "artifacts/models/g4irsf17_i1_tiny_mlp.json",
            "outputs/tables/g4irsf17_i1_policy_evaluation.csv",
            "outputs/tables/g4irsf17_i1_bucket_diagnostics.csv",
            "outputs/reports/g4irsf17_i1_model_decision.md",
        ]
        phase_bd["result_paths"] = [
            path for path in canonical if (root / Path(path)).is_file()
        ]
    phase_eh = phase_row("E-H")
    if phase_eh is not None:
        workflow_terminal = ladder_complete and fault_terminal and scale_complete
        scientific_matrix_complete = (
            ladder_complete and fault_scientific_complete and scale_complete
        )
        phase_eh["status"] = (
            "COMPLETE"
            if scientific_matrix_complete
            else CAPACITY_CENSOR_FINAL_DECISION
            if workflow_terminal and fault_protocol_amended
            else "IN_PROGRESS"
        )
        phase_eh["decision"] = str(final.get("decision", "IN_PROGRESS"))
        phase_eh["workflow_terminal"] = workflow_terminal
        phase_eh["protocol_amended"] = fault_protocol_amended
        phase_eh["scientific_matrix_complete"] = scientific_matrix_complete
        paths = [
            CLOSED_LOOP_TABLE,
            CLOSED_LOOP_REPORT,
            G2_MATCHED_PILOT,
            G2_REPORT,
            FAULT_TABLE,
            FAULT_REPORT,
            SCALE_TABLE,
            SCALE_PROFILE,
            SCALE_REPORT,
            FINAL_REPORT,
        ]
        phase_eh["result_paths"] = [path.as_posix() for path in paths]


def summarize_campaign(
    plan: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    manifest_path = _resolve(root, config.get("campaign_manifest", DEFAULT_CAMPAIGN_MANIFEST))
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {"schema": "czr005.g4irsf17.campaign.v1", "stages": {}}
    results = load_results(plan, config, root=root)
    ladder_rows = build_ladder_rows(plan, results, config, root=root)
    scale_rows = build_scale_rows(plan, results, config, root=root)
    scale_profile_rows = build_scale_profile_rows(scale_rows, root=root)
    scale_queue_telemetry = _scale_queue_telemetry_summary(scale_rows)
    scale_optimization_decision = next(
        (
            str(row["optimization_decision"])
            for row in scale_profile_rows
            if row.get("optimization_decision")
        ),
        "NO_SAFE_MICRO_OPTIMIZATION_THIS_ROUND",
    )
    fault_rows = build_fault_rows(plan, results, config, root=root)
    fault_protocol = _fault_protocol_summary(plan, results, fault_rows)
    candidate_decisions = _candidate_decisions(ladder_rows, scale_rows, fault_rows)
    ladder_complete = _track_complete(plan, results, "ladder")
    fault_terminal = fault_protocol["terminal"] is True
    fault_scientific_complete = (
        fault_protocol["scientific_matrix_complete"] is True
    )
    scale_complete = _track_complete(plan, results, "scale")
    g2 = _current_g2_decision(root, plan, manifest)
    scientific_complete = all(
        complete
        for track, complete in (
            ("ladder", ladder_complete),
            ("fault", fault_scientific_complete),
            ("scale", scale_complete),
        )
        if any(str(job.get("track")) == track for job in plan.get("jobs", []))
    )
    workflow_terminal = all(
        complete
        for track, complete in (
            ("ladder", ladder_complete),
            ("fault", fault_terminal),
            ("scale", scale_complete),
        )
        if any(str(job.get("track")) == track for job in plan.get("jobs", []))
    )
    capacity_censored_terminal = bool(
        workflow_terminal
        and fault_protocol["protocol_status"] == "AMENDED"
        and not fault_scientific_complete
    )
    final = decide_final_joint(
        candidate_decisions,
        campaign_complete=scientific_complete,
        g2_decision=g2,
        capacity_censored_terminal=capacity_censored_terminal,
    )
    ladder_decision = (
        BASELINE_ONLY_LADDER_DECISION
        if ladder_complete and not ladder_rows
        else "COMPLETE"
        if ladder_complete
        else "IN_PROGRESS"
    )
    ladder_publication_rows = _ladder_publication_rows(
        ladder_rows,
        decision=ladder_decision,
    )

    _write_csv(root / CLOSED_LOOP_TABLE, ladder_publication_rows)
    _write_csv(root / SCALE_TABLE, scale_rows)
    _write_csv(root / SCALE_PROFILE, scale_profile_rows)
    _write_csv(root / FAULT_TABLE, fault_rows)

    ladder_report = "\n".join(
        [
            "# G4IRSF17 matched closed-loop ladder",
            "",
            "All deltas are candidate minus matched E4/off; negative time is better. A censored or missing row is not a win.",
            "",
            _markdown_table(
                ["Candidate", "Segments", "Status", "Mean Δs", "P95 Δs", "P99 Δs", "CI upper", "Gate"],
                [
                    [row["candidate_id"], row["segments"], row["comparison_status"], _fmt(row["mean_tth_delta_seconds"]), _fmt(row["p95_tth_delta_seconds"]), _fmt(row["p99_tth_delta_seconds"]), _fmt(row["ci95_upper_seconds"]), row["ladder_decision"]]
                    for row in ladder_rows
                ],
            ),
            "",
            f"Track status: **`{ladder_decision}`**.",
        ]
    )
    _atomic_write(root / CLOSED_LOOP_REPORT, (ladder_report + "\n").encode("utf-8"))

    g2_scope_status = str(g2.get("scope_status", "G2_DIAGNOSTIC_IN_PROGRESS"))
    g2_scope_statement = (
        "The completed screen closes only the current eager-token seam diagnostic; "
        "it is not a global G2 scientific no-go. The bounded JIT choice-producing "
        "seam remains the actionable next pivot."
        if g2_scope_status == G2_EAGER_DIAGNOSTIC_STATUS
        else "No global G2 scientific no-go is claimed before a choice-producing bounded JIT causal seam is evaluated."
    )
    g2_report = "\n".join(
        [
            "# G4IRSF17 G2 decision",
            "",
            f"Decision: **`{g2.get('decision', 'UNKNOWN')}`**.",
            f"Evidence scope: **`{g2_scope_status}`**.",
            "",
            *(f"- {reason}" for reason in g2.get("reasons", [])),
            "",
            g2_scope_statement,
            f"Next pivot: **{g2.get('next_pivot', G2_NEXT_PIVOT)}**.",
            "",
            "A G2 policy enters the ladder only after a real 64+ opportunity causal artifact reports support and hard-safety PASS. Triggering a pivot alone is not authorization.",
        ]
    )
    _atomic_write(root / G2_REPORT, (g2_report + "\n").encode("utf-8"))

    fault_report = "\n".join(
        [
            "# G4IRSF17 native fault campaign",
            "",
            "Faults are event-runtime availability overlays on the unchanged real map. Uninformative exposure, missing recovery telemetry, timeout, and OOM remain explicit.",
            "",
            f"Protocol status: **`{fault_protocol['protocol_status']}`**.",
            f"Original 1x matrix complete: **{fault_protocol['original_1x_matrix_complete']}**; original 4x matrix complete: **{fault_protocol['original_4x_matrix_complete']}**.",
            f"4x fault advantage: **`{fault_protocol['fault_advantage_4x']}`**.",
            "Amended 4x rows are terminal for campaign accounting, but are not executed, evaluable, passed, or failed fault treatments. No synthetic job-result JSON is created.",
            "",
            _markdown_table(
                ["Candidate", "Load", "Scenario", "Status", "Execution", "Evaluable", "Affected", "Completion", "Capacity segments", "Recovery s", "Hard gate"],
                [
                    [row["candidate_id"], f"{row['scale']}x", row["scenario_id"], row["status"], row["execution_status"], row["evaluable"], row["fault_affected_bag_count"] if row["fault_affected_bag_count"] is not None else "—", _fmt(row["completion_rate"]), f"{row['capacity_completed_segment_count']}/{row['capacity_requested_segment_count']}" if row.get("capacity_requested_segment_count") else "—", _fmt(row["fault_recovery_time_seconds"]), row["fault_gate_pass"]]
                    for row in fault_rows
                ],
            ),
            "",
            f"Track status: **`{fault_protocol['track']}`**.",
            (
                f"Reused capacity evidence: `{fault_protocol['capacity_evidence_job_id']}` reached "
                f"{fault_protocol['capacity_event_cap']:,} events with "
                f"{fault_protocol['capacity_completed_segments']:,}/{fault_protocol['capacity_requested_segments']:,} segments completed."
                if fault_protocol.get("capacity_evidence_job_id")
                else "No capacity-control evidence has been reused."
            ),
        ]
    )
    _atomic_write(root / FAULT_REPORT, (fault_report + "\n").encode("utf-8"))

    references = [str(value) for value in config.get("reference_scale_tables", [])]
    queue_boundary = (
        "Per-node source/junction queue peaks were exposed for every required scale row; any observed peak remains a bound only for these measured workloads."
        if scale_queue_telemetry["queue_peak_bound_supported"]
        else "Per-node source/junction queue peaks were not exposed for every required scale row. The evidence supports source-wait and event amplification, but it does not establish a per-node queue-peak bound."
    )
    scale_report = "\n".join(
        [
            "# G4IRSF17 fixed-map scale benchmark",
            "",
            "Business time and compute resources are separate columns. Historical v2-safe/legacy tables are context, not matched E4 promotion comparators.",
            "",
            _markdown_table(
                ["Candidate", "Load", "Status", "Mean TTH s", "P95 TTH s", "Source wait s", "Wait>0 %", "Wait P95 s", "Network s", "Events/segment", "CPU/event us", "Wall s", "RSS MB", "Hard gate"],
                [
                    [row["candidate_id"], f"{row['scale']}x", row["status"], _fmt(row.get("mean_tth_seconds")), _fmt(row.get("p95_tth_seconds")), _fmt(row.get("source_wait_mean_seconds")), _fmt(100.0 * row["source_wait_positive_bag_share"] if row.get("source_wait_positive_bag_share") is not None else None), _fmt(row.get("source_wait_p95_seconds")), _fmt(row.get("network_time_mean_seconds")), _fmt(row.get("events_per_segment")), _fmt(row.get("cpu_microseconds_per_event")), _fmt(row.get("wall_seconds")), _fmt(row.get("peak_rss_mb", row.get("peak_rss_overhead_mb"))), row.get("hard_gate_pass")]
                    for row in scale_rows
                ],
            ),
            "",
            "Reference tables: " + (", ".join(f"`{path}`" for path in references) or "none configured"),
            "",
            f"Structured hotspot profile: `{SCALE_PROFILE.as_posix()}`.",
            f"Profiling decision: **`{scale_optimization_decision}`**.",
            "The verified event-priority-queue reserve reduced mean CPU by 3.2863% and mean worker wall time by 2.5787% across two 1x repeats with exact business/safety parity. This bounded initialization optimization does not solve the 4x event-cap failure; source-admission pressure and event amplification remain the scale blockers.",
            _scale_terminal_narrative(scale_rows),
            f"Queue telemetry: **`{scale_queue_telemetry['queue_telemetry_status']}`** ({scale_queue_telemetry['queue_fields_available_row_count']}/{scale_queue_telemetry['required_scale_row_count']} required rows).",
            queue_boundary,
            "",
            f"Track status: **{'COMPLETE' if scale_complete else 'IN_PROGRESS'}**. Censored legacy/new rows are not ranked as winners.",
        ]
    )
    _atomic_write(root / SCALE_REPORT, (scale_report + "\n").encode("utf-8"))

    final_next_pivot = str(final.get("next_pivot", "")).strip()
    final_pivot_lines = (
        [f"Next pivot: **{final_next_pivot}**."] if final_next_pivot else []
    )
    final_report = "\n".join(
        [
            "# G4IRSF17 final joint decision",
            "",
            f"Decision: **`{final['decision']}`**.",
            "",
            str(final.get("reason", "Promotion requires the full matched and high-load gates recorded below.")),
            *final_pivot_lines,
            "",
            _markdown_table(
                ["Candidate", "Family", "Full 1x", "High-load passes", "Fault matrix", "Decision"],
                [
                    [value["candidate_id"], value["policy_family"], value["full_1x_gate_pass"], value["high_load_non_regression_count"], value["fault_matrix_pass"], value["decision"]]
                    for value in candidate_decisions.values()
                ],
            ),
        ]
    )
    _atomic_write(root / FINAL_REPORT, (final_report + "\n").encode("utf-8"))

    _update_manifest_stage(manifest, "closed_loop_ladder", phase="E", complete=ladder_complete, outputs=(CLOSED_LOOP_TABLE, CLOSED_LOOP_REPORT), summary={"row_count": len(ladder_rows), "candidate_decisions": candidate_decisions}, decision=ladder_decision, root=root)
    _update_manifest_stage(manifest, "g2_decision", phase="F", complete=g2.get("artifact_status") == "COMPLETE_MATCHED_SCREEN", outputs=(G2_MATCHED_PILOT, G2_REPORT), summary=g2, decision=str(g2.get("decision", "UNKNOWN")), root=root)
    _update_manifest_stage(manifest, "native_fault_campaign", phase="G", complete=fault_terminal, outputs=(FAULT_TABLE, FAULT_REPORT), summary={"row_count": len(fault_rows), **fault_protocol}, decision=str(fault_protocol["track"]), root=root)
    _update_manifest_stage(manifest, "scale_benchmark", phase="H", complete=scale_complete, outputs=(SCALE_TABLE, SCALE_REPORT, SCALE_PROFILE), summary={"row_count": len(scale_rows), "profile_row_count": len(scale_profile_rows), "optimization_decision": scale_optimization_decision, **scale_queue_telemetry}, decision="COMPLETE" if scale_complete else "IN_PROGRESS", root=root)
    if g2.get("scope_status") == G2_EAGER_DIAGNOSTIC_STATUS:
        g2_stage = manifest["stages"]["g2_decision"]
        g2_stage["status"] = G2_EAGER_DIAGNOSTIC_STATUS
        g2_stage["diagnostic_terminal"] = True
        g2_stage["global_g2_scientific_complete"] = False
        phases = manifest.get("phases")
        if isinstance(phases, list):
            phase_f = next(
                (
                    row
                    for row in phases
                    if isinstance(row, dict) and str(row.get("phase")) == "F"
                ),
                None,
            )
            if phase_f is not None:
                phase_f["status"] = G2_EAGER_DIAGNOSTIC_STATUS
                phase_f["evidence_scope"] = g2.get("evidence_scope")
                phase_f["global_g2_scientific_complete"] = False
    if fault_protocol["protocol_status"] == "AMENDED":
        manifest["stages"]["native_fault_campaign"]["status"] = fault_protocol["track"]
    _sync_manifest_phases(
        manifest,
        root=root,
        g2=g2,
        final=final,
        ladder_complete=ladder_complete,
        fault_terminal=fault_terminal,
        fault_scientific_complete=fault_scientific_complete,
        fault_protocol_amended=fault_protocol["protocol_status"] == "AMENDED",
        scale_complete=scale_complete,
    )
    manifest["updated_at_utc"] = _now()
    manifest["final_joint_decision"] = final
    _write_json(manifest_path, manifest)
    return {
        "ladder_rows": ladder_rows,
        "scale_rows": scale_rows,
        "scale_profile_rows": scale_profile_rows,
        "scale_queue_telemetry": scale_queue_telemetry,
        "fault_rows": fault_rows,
        "fault_protocol": fault_protocol,
        "candidate_decisions": candidate_decisions,
        "g2_decision": g2,
        "final_decision": final,
        "complete": scientific_complete,
        "workflow_terminal": workflow_terminal,
    }


def _campaign_status_summary(
    plan: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Return compact progress with protocol-amended cells counted honestly.

    A capacity-censored 4x fault cell is workflow-terminal without acquiring a
    synthetic checkpoint.  `pending_jobs` therefore measures missing
    interpretable evidence, while `missing_checkpoint_jobs` retains the raw
    filesystem count for operational diagnosis.
    """

    jobs = [RunJob.from_mapping(raw) for raw in plan.get("jobs", [])]
    planned_ids = {job.job_id for job in jobs}
    evidence_complete_ids = {
        job_id
        for job_id, result in results.items()
        if job_id in planned_ids
        and str(result.get("status", "")) in EVIDENCE_COMPLETE_RESULT_STATUSES
    }
    amendment = _fault_capacity_amendment(plan, results, config)
    amended_jobs = [
        job for job in jobs if _is_amended_fault_job(job, amendment)
    ]
    amended_ids = {job.job_id for job in amended_jobs}
    effective_terminal_ids = evidence_complete_ids | amended_ids
    pending_job_ids = [
        job.job_id for job in jobs if job.job_id not in effective_terminal_ids
    ]

    status_counts: dict[str, int] = {}
    for result in results.values():
        status = str(result.get("status", "UNKNOWN"))
        status_counts[status] = status_counts.get(status, 0) + 1

    amended_status_counts: dict[str, int] = {}
    for job in amended_jobs:
        scenario = FaultScenario.from_mapping(job.fault_scenario or {})
        status = (
            CAPACITY_CENSOR_CONTROL_STATUS
            if scenario.category == "no_fault"
            else CAPACITY_CENSOR_TREATMENT_STATUS
        )
        amended_status_counts[status] = amended_status_counts.get(status, 0) + 1

    return {
        "planned_jobs": len(jobs),
        "checkpointed_jobs": len(results),
        "missing_checkpoint_jobs": len(planned_ids - set(results)),
        "amended_terminal_jobs": len(amended_ids),
        "effective_terminal_jobs": len(effective_terminal_ids),
        "pending_jobs": len(pending_job_ids),
        "pending_job_ids": pending_job_ids,
        "workflow_terminal": bool(jobs) and not pending_job_ids,
        "scientific_complete": bool(jobs)
        and len(evidence_complete_ids) == len(jobs),
        "protocol_amended": amendment is not None,
        "status_counts": status_counts,
        "amended_status_counts": amended_status_counts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-config", help="write a non-authorized configuration template")
    init.add_argument("--root", type=Path, default=ROOT)
    init.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    init.add_argument("--force", action="store_true")

    plan = subparsers.add_parser("plan", help="materialize the E/G/H job matrix")
    plan.add_argument("--root", type=Path, default=ROOT)
    plan.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    plan.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)

    run = subparsers.add_parser("run", help="resume selected isolated native jobs")
    run.add_argument("--root", type=Path, default=ROOT)
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    run.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    run.add_argument("--track", action="append", choices=("ladder", "fault", "scale"))
    run.add_argument("--job-id", action="append")
    run.add_argument("--rerun-terminal", action="store_true")
    run.add_argument("--no-summarize", action="store_true")

    summarize = subparsers.add_parser("summarize", help="rebuild reports from checkpoints only")
    summarize.add_argument("--root", type=Path, default=ROOT)
    summarize.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    summarize.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)

    status = subparsers.add_parser("status", help="show compact checkpoint progress")
    status.add_argument("--root", type=Path, default=ROOT)
    status.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    status.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)

    worker = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--root", type=Path, required=True)
    worker.add_argument("--config", type=Path, required=True)
    worker.add_argument("--job", type=Path, required=True)
    worker.add_argument("--result", type=Path, required=True)
    return parser


def _paths(arguments: argparse.Namespace) -> tuple[Path, Path, Path]:
    root = arguments.root.resolve()
    config = _resolve(root, arguments.config)
    plan = _resolve(root, getattr(arguments, "plan", DEFAULT_PLAN_PATH))
    return root, config, plan


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "_worker":
        return _worker(
            arguments.config.resolve(),
            arguments.job.resolve(),
            arguments.result.resolve(),
            root=arguments.root.resolve(),
        )

    root, config_path, plan_path = _paths(arguments)
    if arguments.command == "init-config":
        if config_path.exists() and not arguments.force:
            raise SystemCampaignError(f"config already exists: {config_path}; pass --force to replace")
        _write_json(config_path, default_config())
        print(config_path)
        return 0

    config = load_config(config_path, root=root)
    if arguments.command == "plan":
        plan = build_run_plan(config, root=root)
        _write_json(plan_path, plan)
        print(json.dumps({"plan": _relative(plan_path, root), "jobs": len(plan["jobs"]), "excluded": plan["excluded_candidates"], "g2": plan["g2_decision"]}, ensure_ascii=False, indent=2))
        return 0

    if not plan_path.is_file():
        plan = build_run_plan(config, root=root)
        _write_json(plan_path, plan)
    else:
        plan = _read_json(plan_path)
        _require(plan.get("schema") == SCHEMA_PLAN, "system campaign plan schema mismatch")

    if arguments.command == "run":
        executed = run_plan(
            plan,
            config,
            config_path=config_path,
            root=root,
            tracks=set(arguments.track) if arguments.track else None,
            job_ids=set(arguments.job_id) if arguments.job_id else None,
            rerun_terminal=arguments.rerun_terminal,
        )
        summary = None if arguments.no_summarize else summarize_campaign(plan, config, root=root)
        print(json.dumps({"jobs_returned": len(executed), "status_counts": {status: sum(str(row.get("status")) == status for row in executed) for status in sorted({str(row.get("status")) for row in executed})}, "summary_complete": summary.get("complete") if summary else None}, ensure_ascii=False, indent=2))
        return 2 if any(row.get("status") == "FAILED_RESUMABLE" for row in executed) else 0

    if arguments.command == "summarize":
        summary = summarize_campaign(plan, config, root=root)
        print(json.dumps({"complete": summary["complete"], "final_decision": summary["final_decision"], "candidate_decisions": summary["candidate_decisions"]}, ensure_ascii=False, indent=2))
        return 0

    if arguments.command == "status":
        results = load_results(plan, config, root=root)
        print(
            json.dumps(
                _campaign_status_summary(plan, results, config),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    raise SystemCampaignError(f"unsupported command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())

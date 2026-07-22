"""Frozen experiment definitions for the G4IRSF11 event runtime.

The protocol is intentionally separate from execution and reporting.  A small
or failed run therefore cannot silently rewrite the formal matrix into a PASS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from scripts.eval.g4irsf11_workloads import FORMAL_WORKLOAD_MODES, FRONTIER_SCALES


PROTOCOL_SCHEMA = "czr005.g4irsf11.event_runtime_protocol.v4"
PROTOCOL_VERSION = "g4irsf11-formal-2026-07-22-v4"
EXTENSION_PROTOCOL_SCHEMA = "czr005.g4irsf11.system_extension_protocol.v3"
EXTENSION_PROTOCOL_VERSION = "g4irsf11-system-extension-2026-07-22-v3"

# These thresholds are declared before looking at G4IRSF11 outcomes.  They are
# engineering SLOs, not a claim that they reproduce an unstated paper SLO.
CAPACITY_SLO = {
    # Queue stability means non-increasing long-run backlog.  A positive
    # engineering allowance would turn a slowly diverging queue into a false
    # capacity PASS; only machine-scale regression tolerance is applied by the
    # metric implementation.
    "max_backlog_slope_fraction": 0.0,
    "max_drain_seconds": 1800.0,
    "max_p95_service_seconds": 600.0,
    "max_p99_service_seconds": 900.0,
    "max_deadline_miss_rate": 0.0,
    "starvation_seconds": 1800.0,
}
FAULT_SLO = {"max_fault_recovery_seconds": 1800.0}
FAULT_WINDOW_SECONDS = 3600.0


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    category: str
    workload_mode: str
    scale: float
    segment_limit: int | None = None
    queue_discipline: str = "aging"
    enable_source_admission: bool = True
    enable_backpressure: bool = True
    enable_pibt_lite: bool = True
    enable_deadlock_escape: bool = True
    enable_fault_policy: bool = True
    diagnostic_hops: int = 2
    fault_profile: str = "no_fault"
    trace_complete: bool = False
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "workload_mode": self.workload_mode,
            "scale": self.scale,
            "segment_limit": self.segment_limit,
            "queue_discipline": self.queue_discipline,
            "enable_source_admission": self.enable_source_admission,
            "enable_backpressure": self.enable_backpressure,
            "enable_pibt_lite": self.enable_pibt_lite,
            "enable_deadlock_escape": self.enable_deadlock_escape,
            "enable_fault_policy": self.enable_fault_policy,
            "diagnostic_hops": self.diagnostic_hops,
            "fault_profile": self.fault_profile,
            "trace_complete": self.trace_complete,
            "notes": self.notes,
            "tags": list(self.tags),
        }


def formal_cases() -> tuple[CaseSpec, ...]:
    cases: list[CaseSpec] = []

    for size in (144, 512, 1024):
        cases.append(
            CaseSpec(
                case_id=f"real_map_size_{size}",
                category="size_ladder",
                workload_mode="time_compressed",
                scale=1.0,
                segment_limit=size,
                notes="deterministic timeline-spanning segment sample; not paper-full evidence",
                tags=("real_map", "correctness"),
            )
        )
    cases.append(
        CaseSpec(
            case_id="real_map_paper_full",
            category="size_ladder",
            workload_mode="time_compressed",
            scale=1.0,
            notes="all 43,603 source-queue segments",
            tags=("real_map", "paper_full"),
        )
    )

    for mode in FORMAL_WORKLOAD_MODES:
        for scale in FRONTIER_SCALES:
            scale_token = str(scale).replace(".", "p")
            cases.append(
                CaseSpec(
                    case_id=f"frontier_{mode}_{scale_token}x",
                    category="capacity_frontier",
                    workload_mode=mode,
                    scale=scale,
                    tags=("fractional_frontier", mode),
                )
            )

    ablations: tuple[tuple[str, Mapping[str, Any], str], ...] = (
        ("aging_full", {}, "reference event heuristic + local shield"),
        ("queue_fifo", {"queue_discipline": "fifo"}, "FIFO local queue"),
        ("queue_deadline", {"queue_discipline": "deadline"}, "deadline/slack local queue"),
        ("source_admission_off", {"enable_source_admission": False}, "source admission A/B"),
        ("backpressure_off", {"enable_backpressure": False}, "local backpressure A/B"),
        ("pibt_lite_off", {"enable_pibt_lite": False}, "PIBT-lite handoff A/B"),
        ("deadlock_escape_off", {"enable_deadlock_escape": False}, "local deadlock escape A/B"),
        ("diagnostic_one_hop", {"diagnostic_hops": 1}, "one-hop pressure diagnostic"),
        (
            "diagnostic_two_hop",
            {"diagnostic_hops": 2},
            "read-only two-hop pressure; reservation depth remains one",
        ),
    )
    for name, overrides, notes in ablations:
        cases.append(
            CaseSpec(
                case_id=f"ablation_{name}",
                category="system_ablation",
                workload_mode="empirical_interarrival_jitter",
                scale=2.5,
                notes=notes,
                tags=("ablation",),
                **dict(overrides),
            )
        )

    for profile, notes in (
        ("single_immediate", "one temporal fault/repair window, zero message delay"),
        ("single_delayed_30s", "one temporal window with stale local state"),
        ("sensor_loss", "fault and repair notifications explicitly dropped"),
        ("repeated_delayed_5s", "two physical fault/repair cycles"),
        (
            "fault_policy_off",
            "local advertised-fault policy disabled; non-disableable physical interlock remains active",
        ),
    ):
        cases.append(
            CaseSpec(
                case_id=f"fault_{profile}",
                category="temporal_fault",
                workload_mode="empirical_interarrival_jitter",
                scale=2.5,
                fault_profile=profile,
                enable_fault_policy=profile != "fault_policy_off",
                notes=notes,
                tags=("temporal_fault",),
            )
        )

    # Complete bounded traces are data-collection runs only.  They do not stand
    # in for the paper-full or capacity-frontier cases above.
    for name, scale, profile in (
        ("highflow_2p5", 2.5, "no_fault"),
        ("highflow_4p0", 4.0, "no_fault"),
        ("fault_delayed", 2.5, "single_delayed_30s"),
    ):
        cases.append(
            CaseSpec(
                case_id=f"trace_{name}",
                category="decision_trace",
                workload_mode="empirical_interarrival_jitter",
                scale=scale,
                segment_limit=1024,
                fault_profile=profile,
                trace_complete=True,
                notes="bounded complete trace for stratified decision data; not full-run evidence",
                tags=("decision_trace",),
            )
        )

    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise AssertionError("formal G4IRSF11 case IDs must be unique")
    return tuple(cases)


def system_extension_cases() -> tuple[CaseSpec, ...]:
    """Exact, non-smoke continuity and extreme-stress cases.

    These runs are deliberately outside the frozen 84-case frontier matrix:
    they answer the system-level 2/7-day and 8x/16x requirements without
    changing the predeclared fractional-frontier population after execution
    has begun.  Their inputs are still exact, hashed, and isolated-process
    measurements; no segment limit is permitted.
    """

    cases = (
        CaseSpec(
            case_id="extension_rolling_2day_full",
            category="continuity_extension",
            workload_mode="rolling_multiday_carryover",
            scale=2.0,
            notes="two exact full-day replicas with no runtime reset or segment truncation",
            tags=("rolling_2day_full", "no_smoke_substitution"),
        ),
        CaseSpec(
            case_id="extension_rolling_7day_full",
            category="continuity_extension",
            workload_mode="rolling_multiday_carryover",
            scale=7.0,
            notes="seven exact full-day replicas with carry-over and no segment truncation",
            tags=("rolling_7day_full", "no_smoke_substitution"),
        ),
        CaseSpec(
            case_id="extension_synchronized_8x_full",
            category="extreme_stress_extension",
            workload_mode="synchronized_replica_worst_case",
            scale=8.0,
            notes="exact 8x synchronized stress; completion is not capacity success",
            tags=("8x_full", "extreme_stress", "no_smoke_substitution"),
        ),
        CaseSpec(
            case_id="extension_synchronized_16x_full",
            category="extreme_stress_extension",
            workload_mode="synchronized_replica_worst_case",
            scale=16.0,
            notes="exact 16x synchronized extreme stress; completion is not capacity success",
            tags=("16x_full", "extreme_stress", "no_smoke_substitution"),
        ),
        CaseSpec(
            case_id="extension_fault_delayed_16x_full",
            category="extreme_fault_extension",
            workload_mode="empirical_interarrival_jitter",
            scale=16.0,
            fault_profile="single_delayed_30s",
            notes="exact 16x temporal fault/repair stress with delayed local notification",
            tags=("16x_full", "temporal_fault", "no_smoke_substitution"),
        ),
    )
    if any(case.segment_limit is not None for case in cases):
        raise AssertionError("system extension cases must never use smoke segment limits")
    return cases


def fault_windows(
    profile: str,
    *,
    minimum_release: float,
    maximum_release: float,
) -> list[dict[str, Any]]:
    """Materialise fault windows without inspecting runtime outcomes."""

    if profile == "no_fault":
        return []
    span = max(1.0, maximum_release - minimum_release)
    anchor = minimum_release + 0.45 * span
    base = {
        # 22->24 is a high-use branch of node 22 (alternative 22->26 remains
        # available), so a local active-fault *committed* decision can be
        # observed.  A single-outgoing edge would produce holds only and must
        # not be mislabelled as action-training coverage.
        "start": 22,
        "end": 24,
        "fault_time": anchor,
        "repair_time": anchor + FAULT_WINDOW_SECONDS,
        "message_delay": 0.0,
        "drop_notification": False,
    }
    if profile in {"single_immediate", "fault_policy_off"}:
        return [base]
    if profile in {"single_delayed_30s", "sensor_loss"}:
        row = dict(base)
        row["message_delay"] = 30.0 if profile == "single_delayed_30s" else 0.0
        row["drop_notification"] = profile == "sensor_loss"
        return [row]
    if profile == "repeated_delayed_5s":
        first = dict(base, repair_time=anchor + 1800.0, message_delay=5.0)
        second = dict(
            base,
            fault_time=anchor + 3600.0,
            repair_time=anchor + 5400.0,
            message_delay=5.0,
        )
        return [first, second]
    raise ValueError(f"unknown fault profile: {profile}")


def protocol_manifest() -> dict[str, Any]:
    cases = formal_cases()
    return {
        "schema": PROTOCOL_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "capacity_slo": dict(CAPACITY_SLO),
        "fault_slo": dict(FAULT_SLO),
        "formal_workload_modes": list(FORMAL_WORKLOAD_MODES),
        "frontier_scales": list(FRONTIER_SCALES),
        "case_count": len(cases),
        "cases": [case.as_dict() for case in cases],
        "runtime_contract": {
            "reservation_depth": 1,
            "diagnostic_hops_maximum": 2,
            "diagnostic_hops_are_read_only": True,
            "source_admission": (
                "enabled policy reads only bounded one-hop congestion beacons and "
                "local physical edge state before source service; disabled policy "
                "bypasses the downstream gate but retains source-local service safety"
            ),
            "source_wait_in_total_system_time": True,
            "runtime_full_astar_allowed": False,
        },
        "claim_boundaries": {
            "size_samples": "never substitute for real_map_paper_full",
            "trace_samples": "decision-data collection only; never capacity evidence",
            "load_modes": "reported separately; no pooled capacity threshold",
            "service_slo": "engineering threshold declared before outcomes, not a paper SLO",
        },
    }


def system_extension_manifest() -> dict[str, Any]:
    cases = system_extension_cases()
    return {
        "schema": EXTENSION_PROTOCOL_SCHEMA,
        "protocol_version": EXTENSION_PROTOCOL_VERSION,
        "capacity_slo": dict(CAPACITY_SLO),
        "fault_slo": dict(FAULT_SLO),
        "case_count": len(cases),
        "cases": [case.as_dict() for case in cases],
        "runtime_contract": {
            "reservation_depth": 1,
            "diagnostic_hops_maximum": 2,
            "diagnostic_hops_are_read_only": True,
            "source_admission": (
                "enabled policy reads only bounded one-hop congestion beacons and "
                "local physical edge state before source service; disabled policy "
                "bypasses the downstream gate but retains source-local service safety"
            ),
            "source_wait_in_total_system_time": True,
            "runtime_full_astar_allowed": False,
        },
        "claim_boundaries": {
            "independence": "supplements rather than rewrites the frozen 84-case formal matrix",
            "continuity": "full generated workload, no first-N truncation, no runtime reset at day boundaries",
            "stress": "8x/16x are stress evidence; safe completion alone is never capacity PASS",
        },
    }

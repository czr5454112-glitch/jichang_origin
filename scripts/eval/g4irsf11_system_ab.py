"""Fail-closed system-level A/B inventory for G4IRSF11.

The inventory is intentionally wider than the event-runtime frontier.  A row
that has not been run by the named system remains blocked; evidence from a
different policy, a smoke prefix, or a static-fault proxy is never borrowed.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.eval.g4irsf11_experiment_protocol import (
    formal_cases,
    protocol_manifest,
    system_extension_manifest,
)
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_SHA256,
    canonical_map_protocol_identity,
)
from scripts.eval.g4irsf11_result_validation import canonical_manifest_sha256


PARTIAL = "PARTIAL_WITH_EXPLICIT_BLOCKER"
VARIANTS = (
    "v2_safe_legacy_full_route_replay",
    "event_rule_only",
    "event_static_potential_heuristic",
    "event_v3_model_only",
    "event_v3_plus_local_shield",
    "event_v3_plus_local_shield_plus_source_admission",
    "event_fault_policy",
)
FIXED_MAP_ENGINEERING_SCENARIOS = (
    "fixed_map_load_heldout",
    "fixed_map_peak_pattern",
    "fixed_map_fault_recovery",
)
SCENARIOS = (
    "paper_main_2_5",
    "speed_sweep",
    "dynamic_heterogeneous_speed_events",
    "fault_16",
    "fractional_frontier_2_to_4",
    "stress_8x_full",
    "extreme_16x_full",
    "rolling_2day_full",
    "rolling_7day_full",
    *FIXED_MAP_ENGINEERING_SCENARIOS,
)


def _bound_protocol_digest(*, extension: bool = False) -> str:
    manifest = system_extension_manifest() if extension else protocol_manifest()
    manifest["fixed_real_map_only"] = True
    manifest["canonical_map"] = canonical_map_protocol_identity()
    return canonical_manifest_sha256(manifest)


def _rows_bound_to_fixed_map(
    rows: list[Mapping[str, Any]], protocol_digest: str
) -> bool:
    return bool(rows) and all(
        row.get("protocol_manifest_sha256") == protocol_digest
        and row.get("map_sha256") == CANONICAL_MAP_SHA256
        for row in rows
    )


def _rows_bound_to_completion(
    rows: list[Mapping[str, Any]], completion: Mapping[str, Any]
) -> bool:
    producer = (
        completion.get("producer")
        if isinstance(completion.get("producer"), Mapping)
        else {}
    )
    cohort = (
        producer.get("measurement_cohort")
        if isinstance(producer.get("measurement_cohort"), Mapping)
        else {}
    )
    implementation = str(producer.get("implementation_sha256") or "")
    cohort_name = str(cohort.get("name") or "")
    worker_target = str(cohort.get("declared_concurrent_worker_target") or "")
    return bool(rows) and bool(implementation) and bool(cohort_name) and all(
        str(row.get("implementation_sha256") or "") == implementation
        and str(row.get("measurement_cohort") or "") == cohort_name
        and str(row.get("declared_concurrent_worker_target") or "") == worker_target
        for row in rows
    )


def _legacy_rows_bound_to_fixed_map(rows: list[Mapping[str, Any]]) -> bool:
    return bool(rows) and all(
        _truth(row.get("fixed_real_map_only"))
        and row.get("map_sha256") == CANONICAL_MAP_SHA256
        for row in rows
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _truth(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "pass", "executed"}


def _default_row(variant: str, scenario: str) -> dict[str, Any]:
    return {
        "variant": variant,
        "scenario": scenario,
        "execution_status": PARTIAL,
        "safe_execution_pass": "",
        "queue_stability_pass": "",
        "service_level_pass": "",
        "capacity_pass": "",
        "fixed_real_map_only": True,
        "canonical_map_sha256": CANONICAL_MAP_SHA256,
        "evidence_protocol_manifest_sha256": "",
        "evidence_paths": "[]",
        "metrics": "{}",
        "blocker": "this exact variant/scenario cell has not been executed",
    }


def _set(
    index: dict[tuple[str, str], dict[str, Any]],
    variant: str,
    scenario: str,
    *,
    status: str,
    evidence: list[str],
    blocker: str = "",
    metrics: Mapping[str, Any] | None = None,
    safe: Any = "",
    queue: Any = "",
    service: Any = "",
    capacity: Any = "",
    protocol_digest: str = "",
) -> None:
    index[(variant, scenario)] = {
        "variant": variant,
        "scenario": scenario,
        "execution_status": status,
        "safe_execution_pass": safe,
        "queue_stability_pass": queue,
        "service_level_pass": service,
        "capacity_pass": capacity,
        "fixed_real_map_only": True,
        "canonical_map_sha256": CANONICAL_MAP_SHA256,
        "evidence_protocol_manifest_sha256": protocol_digest,
        "evidence_paths": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
        "metrics": json.dumps(dict(metrics or {}), ensure_ascii=False, sort_keys=True),
        "blocker": blocker,
    }


def _build_system_ab_matrix_unlocked(root: Path) -> list[dict[str, Any]]:
    from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
        formal_completion_validation_errors,
    )
    from scripts.eval.run_g4irsf11_system_extensions import (
        extension_completion_validation_errors,
    )

    index = {(variant, scenario): _default_row(variant, scenario) for variant in VARIANTS for scenario in SCENARIOS}
    tables = root / "outputs" / "tables"
    reports = root / "outputs" / "reports"
    legacy_path = tables / "g4irsf10_v2_safe_high_flow_matrix.csv"
    paper_path = tables / "g4irsf10_v2_safe_paper_protocol_repeat.csv"
    event_path = tables / "g4irsf11_event_runtime_case_ledger.csv"
    frontier_path = tables / "g4irsf11_capacity_frontier.csv"
    extension_path = tables / "g4irsf11_system_extension_matrix.csv"
    fault_path = tables / "g4irsf11_temporal_fault_repair.csv"
    v3_path = reports / "g4irsf11_v3_training_status.json"
    formal_completion_path = (
        root / "artifacts" / "gates" / "g4irsf11_event_runtime_completion.json"
    )
    extension_completion_path = (
        root / "artifacts" / "gates" / "g4irsf11_system_extension_completion.json"
    )

    legacy = _read_csv(legacy_path)
    paper = _read_csv(paper_path)
    event = _read_csv(event_path)
    frontier = _read_csv(frontier_path)
    extensions = _read_csv(extension_path)
    faults = _read_csv(fault_path)
    v3 = _read_json(v3_path)
    formal_completion = _read_json(formal_completion_path)
    extension_completion = _read_json(extension_completion_path)
    formal_publication_ok = not formal_completion_validation_errors(root)
    extension_publication_ok = not extension_completion_validation_errors(root)
    formal_protocol_digest = _bound_protocol_digest()
    extension_protocol_digest = _bound_protocol_digest(extension=True)
    formal_case_ids = {case.case_id for case in formal_cases()}
    frontier_case_ids = {
        case.case_id for case in formal_cases() if case.category == "capacity_frontier"
    }
    fault_case_ids = {
        case.case_id for case in formal_cases() if case.category == "temporal_fault"
    }
    legacy_by_id = {row.get("scenario", ""): row for row in legacy}
    event_by_id = {row.get("case_id", ""): row for row in event}
    ext_by_id = {row.get("case_id", ""): row for row in extensions}

    if (
        len(paper) == 5
        and _legacy_rows_bound_to_fixed_map(paper)
        and all(row.get("failed_segments") == "0" for row in paper)
    ):
        _set(
            index,
            "v2_safe_legacy_full_route_replay",
            "paper_main_2_5",
            status="EXECUTED",
            evidence=[paper_path.relative_to(root).as_posix()],
            safe=True,
            metrics={"repeat_count": 5, "runtime_full_astar_calls": 0},
        )
    speed_rows = [row for row in legacy if row.get("scenario", "").startswith("speed_deviation_")]
    if len(speed_rows) == 3 and _legacy_rows_bound_to_fixed_map(speed_rows):
        _set(
            index,
            "v2_safe_legacy_full_route_replay",
            "speed_sweep",
            status="EXECUTED_WITH_BOUNDARY",
            evidence=[legacy_path.relative_to(root).as_posix()],
            blocker="uniform fixed-speed diagnostics are not dynamic heterogeneous speed events",
            safe=all(row.get("failed_segments") == "0" for row in speed_rows),
            metrics={"diagnostic_rows": len(speed_rows)},
        )
    for scenario, source_id in (
        ("stress_8x_full", "high_flow_no_fault_8x"),
        ("extreme_16x_full", "high_flow_no_fault_16x"),
        ("rolling_2day_full", "rolling_2_day_1x"),
    ):
        source = legacy_by_id.get(source_id)
        if source and _legacy_rows_bound_to_fixed_map([source]):
            capacity = False if scenario in {"stress_8x_full", "extreme_16x_full"} else ""
            _set(
                index,
                "v2_safe_legacy_full_route_replay",
                scenario,
                status="EXECUTED_WITH_NEGATIVE_EVIDENCE" if capacity is False else "EXECUTED",
                evidence=[legacy_path.relative_to(root).as_posix()],
                safe=source.get("failed_segments") == "0",
                capacity=capacity,
                metrics={
                    "segments": source.get("task_count", ""),
                    "mean_tth_minutes": source.get("mean_tth", ""),
                    "p99_tth_minutes": source.get("p99_tth", ""),
                    "max_source_queue_delay_seconds": source.get("max_source_queue_delay", ""),
                },
            )
    _set(
        index,
        "v2_safe_legacy_full_route_replay",
        "fractional_frontier_2_to_4",
        status=PARTIAL,
        evidence=[legacy_path.relative_to(root).as_posix()] if legacy_path.is_file() else [],
        blocker="legacy evidence has 2x and 4x anchors, not the exact nine-point fractional frontier",
    )
    _set(
        index,
        "v2_safe_legacy_full_route_replay",
        "rolling_7day_full",
        status=PARTIAL,
        evidence=[legacy_path.relative_to(root).as_posix()] if legacy_path.is_file() else [],
        blocker="legacy rolling-7-day evidence is a first-32768 prefix and is not full continuity proof",
    )
    _set(
        index,
        "v2_safe_legacy_full_route_replay",
        "fault_16",
        status=PARTIAL,
        evidence=[legacy_path.relative_to(root).as_posix()] if legacy_path.is_file() else [],
        blocker="legacy fault rows are 8x static-removal proxies, not a 16x temporal repair window",
    )

    paper_event = event_by_id.get("real_map_paper_full")
    if (
        paper_event
        and formal_publication_ok
        and _rows_bound_to_fixed_map([paper_event], formal_protocol_digest)
        and _rows_bound_to_completion([paper_event], formal_completion)
    ):
        _set(
            index,
            "event_static_potential_heuristic",
            "paper_main_2_5",
            status=paper_event.get("execution_status", PARTIAL),
            evidence=[event_path.relative_to(root).as_posix()],
            blocker="" if _truth(paper_event.get("completion_pass")) else "paper-full execution did not complete all 43,603 segments",
            safe=paper_event.get("safe_execution_pass", ""),
            queue=paper_event.get("queue_stability_pass", ""),
            service=paper_event.get("service_level_pass", ""),
            capacity=paper_event.get("capacity_pass", ""),
            metrics={
                "completed_segments": paper_event.get("completed_segment_count", ""),
                "requested_segments": paper_event.get("workload_segment_count", ""),
            },
            protocol_digest=formal_protocol_digest,
        )
    elif paper_event:
        _set(
            index,
            "event_static_potential_heuristic",
            "paper_main_2_5",
            status=PARTIAL,
            evidence=[event_path.relative_to(root).as_posix()],
            blocker=(
                "event evidence is not bound to a COMPLETE atomic fixed-map formal publication"
            ),
        )
    if (
        formal_publication_ok
        and
        len(frontier) == 63
        and {row.get("case_id", "") for row in frontier} == frontier_case_ids
        and _rows_bound_to_fixed_map(frontier, formal_protocol_digest)
        and _rows_bound_to_completion(frontier, formal_completion)
        and all(row.get("execution_status") == "EXECUTED" for row in frontier)
    ):
        _set(
            index,
            "event_static_potential_heuristic",
            "fractional_frontier_2_to_4",
            status="EXECUTED",
            evidence=[frontier_path.relative_to(root).as_posix()],
            safe=all(_truth(row.get("safe_execution_pass")) for row in frontier),
            queue=all(_truth(row.get("queue_stability_pass")) for row in frontier),
            service=all(_truth(row.get("service_level_pass")) for row in frontier),
            capacity=all(_truth(row.get("capacity_pass")) for row in frontier),
            metrics={"exact_case_count": 63, "capacity_pass_count": sum(_truth(row.get("capacity_pass")) for row in frontier)},
            protocol_digest=formal_protocol_digest,
        )
    for scenario, source_id in (
        ("stress_8x_full", "extension_synchronized_8x_full"),
        ("extreme_16x_full", "extension_synchronized_16x_full"),
        ("rolling_2day_full", "extension_rolling_2day_full"),
        ("rolling_7day_full", "extension_rolling_7day_full"),
    ):
        source = ext_by_id.get(source_id)
        if (
            source
            and extension_publication_ok
            and _rows_bound_to_fixed_map([source], extension_protocol_digest)
            and _rows_bound_to_completion([source], extension_completion)
        ):
            qualified = (
                source.get("execution_status") == "EXECUTED"
                and _truth(source.get("no_smoke_substitution_pass"))
            )
            _set(
                index,
                "event_static_potential_heuristic",
                scenario,
                status="EXECUTED" if qualified else PARTIAL,
                evidence=[extension_path.relative_to(root).as_posix()],
                blocker="" if _truth(source.get("no_smoke_substitution_pass")) else "exact full-input/day-boundary audit did not pass",
                safe=source.get("safe_execution_pass", ""),
                queue=source.get("queue_stability_pass", ""),
                service=source.get("service_level_pass", ""),
                capacity=source.get("capacity_pass", ""),
                metrics={
                    "segments": source.get("workload_segment_count", ""),
                    "day_boundaries": source.get("observed_full_day_boundaries", ""),
                },
                protocol_digest=extension_protocol_digest,
            )
        elif source:
            _set(
                index,
                "event_static_potential_heuristic",
                scenario,
                status=PARTIAL,
                evidence=[extension_path.relative_to(root).as_posix()],
                blocker=(
                    "exact full-input evidence is not bound to a COMPLETE atomic "
                    "system-extension publication"
                ),
            )

    fault16 = ext_by_id.get("extension_fault_delayed_16x_full")
    if (
        fault16
        and extension_publication_ok
        and _rows_bound_to_fixed_map([fault16], extension_protocol_digest)
        and _rows_bound_to_completion([fault16], extension_completion)
    ):
        qualified = (
            fault16.get("execution_status") == "EXECUTED"
            and _truth(fault16.get("no_smoke_substitution_pass"))
        )
        recovery_pass = _truth(fault16.get("fault_recovery_pass"))
        negative_recovery = qualified and not recovery_pass
        unrecovered_count = int(
            fault16.get("fault_recovery_unobserved_count") or 0
        )
        negative_recovery_blocker = (
            "temporal fault did not recover by run end; exact negative evidence retained"
            if unrecovered_count > 0
            else "temporal fault recovery gate failed; exact negative evidence retained"
        )
        _set(
            index,
            "event_fault_policy",
            "fault_16",
            status=(
                "EXECUTED_WITH_NEGATIVE_EVIDENCE"
                if negative_recovery
                else "EXECUTED" if qualified else PARTIAL
            ),
            evidence=[extension_path.relative_to(root).as_posix()],
            blocker=(
                negative_recovery_blocker
                if negative_recovery
                else ""
                if _truth(fault16.get("no_smoke_substitution_pass"))
                else "exact 16x temporal-fault input audit did not pass"
            ),
            safe=fault16.get("safe_execution_pass", ""),
            queue=fault16.get("queue_stability_pass", ""),
            service=fault16.get("service_level_pass", ""),
            capacity=fault16.get("capacity_pass", ""),
            metrics={
                "fault_recovery_pass": fault16.get("fault_recovery_pass", ""),
                "fault_recovery_unobserved_count": fault16.get(
                    "fault_recovery_unobserved_count", ""
                ),
                "fault_recovery_times_seconds_json": fault16.get(
                    "fault_recovery_times_seconds_json", ""
                ),
                "fault_backlog_before_fault_json": fault16.get(
                    "fault_backlog_before_fault_json", ""
                ),
                "fault_backlog_at_repair_json": fault16.get(
                    "fault_backlog_at_repair_json", ""
                ),
                "fault_recovery_gate_failures": fault16.get(
                    "fault_recovery_gate_failures", ""
                ),
            },
            protocol_digest=extension_protocol_digest,
        )
    elif fault16:
        _set(
            index,
            "event_fault_policy",
            "fault_16",
            status=PARTIAL,
            evidence=[extension_path.relative_to(root).as_posix()],
            blocker=(
                "exact 16x temporal-fault evidence is not bound to a COMPLETE atomic "
                "system-extension publication"
            ),
        )
    if (
        formal_publication_ok
        and
        len(faults) == 5
        and {row.get("case_id", "") for row in faults} == fault_case_ids
        and _rows_bound_to_fixed_map(faults, formal_protocol_digest)
        and _rows_bound_to_completion(faults, formal_completion)
        and all(row.get("execution_status") == "EXECUTED" for row in faults)
    ):
        # This is useful adjacent evidence, but it cannot replace the exact 16x
        # cell above and is therefore stored only in the metrics when present.
        target = index[("event_fault_policy", "fault_16")]
        metrics = json.loads(str(target["metrics"]))
        metrics["fractional_temporal_fault_cases"] = 5
        metrics["fractional_fault_recovery_pass_count"] = sum(_truth(row.get("fault_recovery_pass")) for row in faults)
        target["metrics"] = json.dumps(metrics, ensure_ascii=False, sort_keys=True)

    for scenario in SCENARIOS:
        row = index[("event_rule_only", scenario)]
        row["blocker"] = "a separately identified event rule-only executable was not implemented or run; heuristic evidence is not reused"
    model_count = int(v3.get("trained_model_count", 0) or 0)
    gate_status = str(v3.get("status", v3.get("overall_status", PARTIAL)))
    for variant in (
        "event_v3_model_only",
        "event_v3_plus_local_shield",
        "event_v3_plus_local_shield_plus_source_admission",
    ):
        for scenario in SCENARIOS:
            row = index[(variant, scenario)]
            row["evidence_paths"] = json.dumps([v3_path.relative_to(root).as_posix()] if v3_path.is_file() else [])
            row["blocker"] = f"v3 training gate status={gate_status}; trained_model_count={model_count}"
    engineering_blockers = {
        "fixed_map_load_heldout": (
            "the exact fixed-map held-out-load engineering cell has not been "
            "executed for this variant; paper/frontier evidence is not reused"
        ),
        "fixed_map_peak_pattern": (
            "the exact fixed-map peak-pattern engineering cell has not been "
            "executed for this variant; aggregate-load evidence is not reused"
        ),
        "fixed_map_fault_recovery": (
            "the exact fixed-map fault-recovery engineering cell has not been "
            "executed for this variant; another fault profile is not reused"
        ),
    }
    for variant in VARIANTS:
        for scenario, blocker in engineering_blockers.items():
            row = index[(variant, scenario)]
            row["execution_status"] = PARTIAL
            row["blocker"] = blocker

    return [index[(variant, scenario)] for variant in VARIANTS for scenario in SCENARIOS]


def build_system_ab_matrix(root: Path) -> list[dict[str, Any]]:
    from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
        CONSOLIDATION_LOCK as FORMAL_LOCK,
        ROOT as RUNNER_ROOT,
        _acquire_case_lock,
        _release_case_lock,
    )
    from scripts.eval.run_g4irsf11_system_extensions import (
        CONSOLIDATION_LOCK as EXTENSION_LOCK,
    )

    formal_token = _acquire_case_lock(
        root / FORMAL_LOCK.relative_to(RUNNER_ROOT),
        "system_ab_formal_reader_snapshot",
        wait_seconds=60.0,
    )
    if formal_token is None:
        raise RuntimeError(
            "formal publication is being consolidated; system A/B has no stable reader snapshot"
        )
    extension_token = _acquire_case_lock(
        root / EXTENSION_LOCK.relative_to(RUNNER_ROOT),
        "system_ab_extension_reader_snapshot",
        wait_seconds=60.0,
    )
    if extension_token is None:
        _release_case_lock(formal_token)
        raise RuntimeError(
            "extension publication is being consolidated; system A/B has no stable reader snapshot"
        )
    try:
        return _build_system_ab_matrix_unlocked(root)
    finally:
        _release_case_lock(extension_token)
        _release_case_lock(formal_token)


def write_system_ab_artifacts(root: Path, rows: list[Mapping[str, Any]]) -> tuple[Path, Path]:
    table = root / "outputs" / "tables" / "g4irsf11_system_ab_matrix.csv"
    report = root / "outputs" / "reports" / "g4irsf11_system_ab_report.md"
    table.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    executed = sum(
        str(row["execution_status"]).startswith("EXECUTED") for row in rows
    )
    negative = sum(
        row["execution_status"] == "EXECUTED_WITH_NEGATIVE_EVIDENCE"
        for row in rows
    )
    qualified = sum(
        row["execution_status"] == "EXECUTED" and not row["blocker"]
        for row in rows
    )
    report.write_text(
        "\n".join(
            [
                "# G4IRSF11 System A/B Boundary",
                "",
                f"Exact executed cells: **{executed}/{len(rows)}** (negative-evidence outcomes: **{negative}**).",
                f"Positive/qualified cells: **{qualified}/{len(rows)}**. Every non-executed cell retains an explicit blocker; executed negative-evidence cells retain an outcome explanation.",
                "",
                "This matrix never borrows a heuristic result for rule-only or v3, never treats a prefix as full continuity, and never treats safe completion as capacity success.",
                "",
                "Engineering cells are restricted to held-out load, peak-pattern, and fault-recovery tests on the canonical fixed map. No topology-generalization claim is made.",
                "",
                "G4J remains closed: the Java/CIE track is reported separately and is not promoted by Python/C++ evidence.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return table, report

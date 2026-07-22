from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.eval.g4irsf11_system_ab import (
    PARTIAL,
    SCENARIOS,
    VARIANTS,
    _bound_protocol_digest,
    build_system_ab_matrix,
)
from scripts.eval.g4irsf11_fixed_map import CANONICAL_MAP_SHA256


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_matrix_is_complete_and_fails_closed_when_evidence_is_absent(tmp_path: Path) -> None:
    rows = build_system_ab_matrix(tmp_path)
    assert len(rows) == len(VARIANTS) * len(SCENARIOS) == 70
    assert all(row["execution_status"] == PARTIAL for row in rows)
    assert all(row["blocker"] for row in rows)
    assert all(row["fixed_real_map_only"] is True for row in rows)
    assert {row["canonical_map_sha256"] for row in rows} == {CANONICAL_MAP_SHA256}


def test_legacy_smoke_is_never_promoted_to_rolling_seven_day_full(tmp_path: Path) -> None:
    _csv(
        tmp_path / "outputs" / "tables" / "g4irsf10_v2_safe_high_flow_matrix.csv",
        [
            {
                "scenario": "rolling_7_day_1x_smoke",
                "task_count": 32768,
                "failed_segments": 0,
                "mean_tth": 1,
                "p99_tth": 2,
                "max_source_queue_delay": 3,
            }
        ],
    )
    rows = build_system_ab_matrix(tmp_path)
    row = next(
        row for row in rows
        if row["variant"] == "v2_safe_legacy_full_route_replay" and row["scenario"] == "rolling_7day_full"
    )
    assert row["execution_status"] == PARTIAL
    assert "first-32768" in row["blocker"]


def test_v3_and_rule_only_do_not_borrow_event_heuristic_results(tmp_path: Path) -> None:
    report = tmp_path / "outputs" / "reports" / "g4irsf11_v3_training_status.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"status": PARTIAL, "trained_model_count": 0}), encoding="utf-8")
    rows = build_system_ab_matrix(tmp_path)
    for row in rows:
        if row["variant"] == "event_rule_only" or row["variant"].startswith("event_v3"):
            assert row["execution_status"] == PARTIAL
            assert row["blocker"]


def test_event_csv_without_atomic_completion_cannot_be_promoted(tmp_path: Path) -> None:
    _csv(
        tmp_path / "outputs" / "tables" / "g4irsf11_event_runtime_case_ledger.csv",
        [
            {
                "case_id": "real_map_paper_full",
                "execution_status": "EXECUTED",
                "completion_pass": True,
                "map_sha256": CANONICAL_MAP_SHA256,
                "protocol_manifest_sha256": _bound_protocol_digest(),
                "implementation_sha256": "a" * 64,
                "measurement_cohort": "fixture",
                "declared_concurrent_worker_target": 8,
            }
        ],
    )

    rows = build_system_ab_matrix(tmp_path)
    row = next(
        row
        for row in rows
        if row["variant"] == "event_static_potential_heuristic"
        and row["scenario"] == "paper_main_2_5"
    )
    assert row["execution_status"] == PARTIAL
    assert "COMPLETE atomic" in row["blocker"]


def test_extension_without_exact_input_audit_is_not_counted_as_executed(
    tmp_path: Path,
) -> None:
    _csv(
        tmp_path / "outputs" / "tables" / "g4irsf11_system_extension_matrix.csv",
        [
            {
                "case_id": "extension_synchronized_8x_full",
                "execution_status": "EXECUTED",
                "no_smoke_substitution_pass": False,
                "map_sha256": CANONICAL_MAP_SHA256,
                "protocol_manifest_sha256": _bound_protocol_digest(extension=True),
            }
        ],
    )

    rows = build_system_ab_matrix(tmp_path)
    row = next(
        row
        for row in rows
        if row["variant"] == "event_static_potential_heuristic"
        and row["scenario"] == "stress_8x_full"
    )
    assert row["execution_status"] == PARTIAL
    assert "exact full-input" in row["blocker"]

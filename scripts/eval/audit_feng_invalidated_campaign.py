"""Record exclusions without changing any pre-repair native result or status."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "outputs/runtime/cie_external_baseline_robustness"
SOURCE = "99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8"
INVALID = "INVALIDATED_ZERO_THROUGH_STATE_MACHINE_BUG"
METHOD = "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"


def evidence(path: Path) -> dict:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest,
            "size_bytes": path.stat().st_size}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    cells = []
    checkpoint = OLD / "checkpoints/nanning_dh_16_of_30_20260905T0935.json"
    checkpoint_cells = {(r["load"], r["seed"]): r for r in json.loads(checkpoint.read_text())["cells"]}
    for cell in sorted(OLD.glob("nanning_*x/seed_*")):
        native = cell / "feng_env_dh"
        status_path = native / "runner_status.json"
        status = json.loads(status_path.read_text())
        identity = status["identity"]
        assert identity["reconstruction_java_source_aggregate_sha256"] == SOURCE, cell
        external = identity["external_workload_identity"]
        normalized_path = cell / f"{METHOD}.json"
        normalized = json.loads(normalized_path.read_text()) if normalized_path.exists() else None
        row = {"map": "nanning", "load_factor": external["load_factor"],
               "seed": external["seed"], "directory": cell.relative_to(ROOT).as_posix(),
               "scientific_validity": INVALID, "formal_comparison_eligible": False,
               "corrected_matrix_reusable": False,
               "source_sha256": SOURCE, "raw_bag_count": external["raw_bag_count"],
               "segment_count": external["segment_count"],
               "original_runner_status": status["status"],
               "original_returncode": status.get("returncode"),
               "original_normalized_status": normalized.get("status") if normalized else None,
               "original_native_simulation_status": None,
               "execution_disposition": "TERMINAL_FILES_PRESERVED" if normalized else "INTERRUPTED_PARTIAL_FILES_PRESERVED",
               "normalized_evidence": evidence(normalized_path) if normalized else None,
               "native_files": [evidence(path) for path in sorted(native.iterdir()) if path.is_file()]}
        summary_path = native / "summary.csv"
        if summary_path.exists() and summary_path.stat().st_size:
            with summary_path.open(encoding="utf-8-sig", newline="") as stream:
                summary = next(csv.DictReader(stream), {})
            row["original_native_simulation_status"] = summary.get("status")
        if normalized:
            previous = checkpoint_cells[(external["load_factor"], external["seed"])]
            assert row["normalized_evidence"]["sha256"] == previous["normalized_sha256"], cell
            assert evidence(status_path)["sha256"] == previous["runner_status_sha256"], cell
            row["matches_immutable_16_cell_checkpoint"] = True
            row["completed_raw_bags_observation_only"] = normalized["metrics"]["completed_raw_bag_count"]
        cells.append(row)

    counts = Counter(row["original_runner_status"] for row in cells)
    assert len(cells) == 30 and counts == {"complete": 16, "failed": 12, "running": 2}, counts
    source_csv = ROOT / "outputs/tables/cie_external_baseline_robustness.csv"
    with source_csv.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        aggregate_rows = list(reader)
    retained = [row for row in aggregate_rows
                if not (row["map"] == "nanning" and "CIE_DH" in row["comparison"])]
    valid_csv = ROOT / "outputs/tables/cie_external_baseline_robustness_valid_20260905.csv"
    with valid_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(retained)

    sidecar = {"schema": "czr005.cie_external_baseline_scientific_validity.v1",
               "created_at": datetime.now(timezone.utc).isoformat(),
               "audit_basis": "Feng_CIE_DH_baseline_audit_and_repair_20260905.md; source-matched zero-through intermediate-node defect",
               "scientific_validity": INVALID,
               "scope": "All pre-repair Nanning independent Java DH cells with the identified source, including superseded 14/30 and 16/30 checkpoints; no G31/HCA or map2 cell is invalidated here.",
               "execution_status_is_not_scientific_validity": True,
               "native_or_normalized_files_modified": False,
               "old_campaign_restart_allowed": False,
               "corrected_results_directory": "outputs/runtime/feng_cie_dh_zero_through_repair_20260905",
               "controlled_stop_commit": "05f3edc6b14791dd87f79c143d1bd4084b24954b",
               "recorded_stop_process_audit": "2026-09-05T10:08:23+08:00; zero matching campaign processes",
               "current_process_audit": "outputs/runtime/feng_cie_dh_zero_through_repair_20260905/process_audit.json",
               "native_status_counts_preserved": dict(counts),
               "normalized_cells_preserved_but_excluded": 16,
               "interrupted_cells_not_normalizable": 14,
               "never_started_coordinates_at_final_stop": 0,
               "retained_versioned_map2_native_cells": 90,
               "unaffected_nanning_hca_g31_native_cells": 60,
               "map2_reuse_condition": "Corrected-source full 28506-bag/43603-segment per-bag regression; no mechanical rerun solely because source SHA changes.",
               "old_aggregate_csv": evidence(source_csv),
               "filtered_formal_aggregate_csv": evidence(valid_csv),
               "old_aggregate_rows": len(aggregate_rows),
               "retained_aggregate_rows": len(retained),
               "excluded_aggregate_rows": len(aggregate_rows) - len(retained),
               "immutable_checkpoint": evidence(checkpoint),
               "arithmetic_ratios_observation_only": {
                   "route_decisions_nanning_over_map2": 834.18,
                   "simulator_wall_seconds_nanning_over_map2": 582.73,
                   "g31_speedup": False,
                   "normal_congestion_scaling_interpretation": "WITHDRAWN",
                   "fraction_of_completion_or_runtime_deficit_caused_by_bug": "NOT_QUANTIFIED"},
               "cells": cells}
    write_json(OLD / "scientific_validity_20260905.json", sidecar)
    print(json.dumps({"native_status_counts_preserved": counts,
                      "terminal_hash_matches": 16,
                      "retained_aggregate_rows": len(retained),
                      "excluded_aggregate_rows": len(aggregate_rows) - len(retained)}))


if __name__ == "__main__":
    main()

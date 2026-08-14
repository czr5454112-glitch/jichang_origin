"""Small G23 contract for the two required historical baselines.

This module deliberately reads only committed repository artifacts.  It does
not launch the legacy Java project, read the thesis outside the repository, or
turn the historical HCA* result into a synthetic 2x/4x baseline.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]

PAPER_DOI = "10.1016/j.cie.2022.108802"
PAPER_URL = f"https://doi.org/{PAPER_DOI}"
PAPER_TITLE = (
    "Internet-of-Things-augmented dynamic route planning approach to the "
    "airport baggage handling system"
)

F2_PATH = Path("artifacts/policies/g4irsf13_f2_frozen_baseline.json")
DENOMINATOR_PATH = Path(
    "artifacts/policies/g4irsf12_denominator_reconciliation.json"
)
PROTOCOL_PATH = Path("outputs/tables/g4irsf5_paper_experiment_protocol.csv")
METRICS_PATH = Path("outputs/tables/g4irsf5_paper_metrics_inventory.csv")
BASELINE_INVENTORY_PATH = Path(
    "outputs/tables/g4irsf5_paper_baseline_inventory.csv"
)
BASELINE_RESULT_PATH = Path("outputs/tables/g4irsf5_baseline_protocol_results.csv")
DENOMINATOR_TABLE_PATH = Path(
    "outputs/tables/g4irsf8_tth_denominator_comparison.csv"
)


class BaselineEvidenceError(ValueError):
    """Raised when committed baseline evidence is incomplete or contradictory."""


def _read_json(root: Path, relative: Path) -> dict[str, Any]:
    payload = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BaselineEvidenceError(f"{relative} must contain a JSON object")
    return payload


def _read_csv(root: Path, relative: Path) -> list[dict[str, str]]:
    # The oldest protocol tables were written with a UTF-8 BOM.  utf-8-sig
    # consumes it when present and remains compatible with the later tables.
    with (root / relative).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _one(
    rows: Iterable[Mapping[str, str]],
    field: str,
    value: str,
    *,
    source: Path,
) -> Mapping[str, str]:
    matches = [row for row in rows if row.get(field) == value]
    if len(matches) != 1:
        raise BaselineEvidenceError(
            f"{source} must contain exactly one {field}={value!r} row"
        )
    return matches[0]


def _number(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise BaselineEvidenceError(f"{label} must be numeric") from exc


def _parse_assignments(value: str, expected: tuple[str, ...]) -> dict[str, float]:
    parsed = {
        key: float(number)
        for key, number in re.findall(
            r"([a-z_]+)\s*=\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", value
        )
    }
    if set(parsed) != set(expected):
        raise BaselineEvidenceError(
            f"expected assignments {expected!r}, observed {tuple(parsed)!r}"
        )
    return parsed


def _paper_protocol(
    protocol_rows: list[dict[str, str]],
    metric_rows: list[dict[str, str]],
    baseline_rows: list[dict[str, str]],
) -> dict[str, Any]:
    topology_row = _one(
        protocol_rows,
        "protocol_item",
        "case_topology",
        source=PROTOCOL_PATH,
    )
    topology = json.loads(topology_row["paper_value"])
    daily = _one(
        protocol_rows,
        "protocol_item",
        "daily_baggage_count",
        source=PROTOCOL_PATH,
    )
    primary_speed = _one(
        protocol_rows,
        "protocol_item",
        "primary_speed",
        source=PROTOCOL_PATH,
    )

    speeds: list[dict[str, Any]] = []
    for speed in (1.5, 2.0, 2.5, 3.0):
        row = _one(
            metric_rows,
            "metric_id",
            f"paper_t5_2_speed_{speed:.1f}",
            source=METRICS_PATH,
        )
        speeds.append(
            {
                "speed_mps": speed,
                **_parse_assignments(row["paper_value"], ("min", "avg", "max")),
                "source": row["source"],
            }
        )

    dynamic_static: list[dict[str, Any]] = []
    for speed in (1.5, 2.0, 2.5, 3.0):
        for deviation in (10, 20, 30):
            row = _one(
                metric_rows,
                "metric_id",
                f"paper_t5_4_speed_{speed:.1f}_dev_{deviation}%",
                source=METRICS_PATH,
            )
            dynamic_static.append(
                {
                    "speed_mps": speed,
                    "speed_deviation_percent": deviation,
                    **_parse_assignments(
                        row["paper_value"], ("dynamic", "static", "improvement")
                    ),
                    "source": row["source"],
                }
            )

    table_5_3_rows: list[dict[str, Any]] = []
    for metric_id, method, unit in (
        ("paper_t5_3_分散启发式方法", "dispersed_heuristic", "minutes"),
        ("paper_t5_3_IoT-DRPA", "iot_drpa_hca_star", "minutes"),
        ("paper_t5_3_效率提高", "improvement", "percent"),
    ):
        row = _one(
            metric_rows,
            "metric_id",
            metric_id,
            source=METRICS_PATH,
        )
        table_5_3_rows.append(
            {
                "method": method,
                **_parse_assignments(row["paper_value"], ("min", "avg", "max")),
                "unit": unit,
                "source": row["source"],
            }
        )

    fault_rows = [
        row for row in metric_rows if row.get("metric_id", "").startswith("paper_t5_5_")
    ]
    faults: list[dict[str, Any]] = []
    for row in fault_rows:
        arc_suffix = row["metric_id"].removeprefix("paper_t5_5_")
        arc_ids = [int(part) for part in arc_suffix.replace(",", "，").split("，")]
        parsed = _parse_assignments(row["paper_value"], ("affected", "success_rate"))
        faults.append(
            {
                "arc_ids": arc_ids,
                "affected_conveyors": int(parsed["affected"]),
                "baggage_success_rate": parsed["success_rate"],
                "source": row["source"],
                "evidence_status": "PAPER_REPORTED_ONLY",
            }
        )
    if len(faults) != 16:
        raise BaselineEvidenceError("paper Table 5.5 must contain 16 fault rows")

    dispersed = _one(
        baseline_rows,
        "baseline_id",
        "paper_dispersed_heuristic",
        source=BASELINE_INVENTORY_PATH,
    )
    static_lra = _one(
        baseline_rows,
        "baseline_id",
        "paper_static_lra_star",
        source=BASELINE_INVENTORY_PATH,
    )

    return {
        "title": PAPER_TITLE,
        "doi": PAPER_DOI,
        "url": PAPER_URL,
        "primary_method": "centralized IoT-DRPA / HCA*",
        "one_x": {
            "duration_hours": 24,
            "raw_bag_count": int(daily["paper_value"]),
            "processed_segment_count": 43_603,
            "primary_speed_mps": 2.5,
            "loading_stations": int(topology["装载站数量"]),
            "unloading_stations": int(topology["卸载站数量"]),
            "junctions": int(topology["交叉点数量"]),
            "paper_conveyors": int(topology["输送线数量"]),
            "ebs_count": int(topology["EBS数量"]),
            "main_metrics": ["bag-level THT min/mean/max", "complete bags / TH"],
            "tth_aggregation": "sum split-segment travel times by original bag",
            "primary_speed_evidence": primary_speed["evidence"],
        },
        "table_5_2_speed_sweep": speeds,
        "table_5_3_iot_drpa_vs_dispersed_heuristic": {
            "status": dispersed["replay_status"].upper(),
            "boundary": dispersed["notes"],
            "rows": table_5_3_rows,
        },
        "table_5_4_dynamic_iot_drpa_vs_static_lra_star": {
            "baseline_status": static_lra["replay_status"].upper(),
            "boundary": static_lra["notes"],
            "rows": dynamic_static,
        },
        "table_5_5_faults": faults,
    }


def _f2_baseline(f2: Mapping[str, Any]) -> dict[str, Any]:
    if f2.get("candidate_id") != "G4IRSF13_F2_FROZEN":
        raise BaselineEvidenceError("unexpected frozen F2 candidate")
    inputs = f2["protected_inputs"]
    metrics = f2["metrics"]
    gates = f2["hard_gates"]
    return {
        "baseline_id": "G4IRSF13_F2_FROZEN",
        "role": "decentralized frozen framework baseline",
        "evidence_status": "COMMITTED_FROZEN_CONTROL",
        "configuration": dict(f2["configuration"]),
        "one_x": {
            "raw_bag_count": int(inputs["raw_bag_count"]),
            "processed_segment_count": int(inputs["segment_count"]),
            "complete_raw_bags": int(gates["complete_raw_bags"]),
            "completed_segments": int(gates["completed_segments"]),
            "failed_segments": int(gates["failed_segments"]),
            "conflicts": int(gates["conflicts"]),
            "runtime_full_astar_calls": int(gates["runtime_full_astar_calls"]),
            "global_reservation_scans": int(gates["global_reservation_scans"]),
            "original_entry_mean_minutes": _number(
                metrics["original_entry_mean_minutes"], "F2 original-entry mean"
            ),
            "pass_time_anchored_mean_minutes": _number(
                metrics["decision_sensitive_mean_minutes"],
                "F2 pass-time-anchored mean",
            ),
            "original_entry_p95_seconds": _number(
                metrics["original_entry_p95_seconds"], "F2 p95"
            ),
            "original_entry_p99_seconds": _number(
                metrics["original_entry_p99_seconds"], "F2 p99"
            ),
        },
        "scale_availability": {
            "1x": "COMMITTED_FROZEN_CONTROL",
            "2x": "FRESH_MATCHED_RUN_REQUIRED",
            "4x": "FRESH_MATCHED_RUN_REQUIRED_IF_UNLOCKED",
        },
        "evidence": str(F2_PATH).replace("\\", "/"),
    }


def _hca_baseline(
    result_rows: list[dict[str, str]],
    denominator_rows: list[dict[str, str]],
    reconciliation: Mapping[str, Any],
) -> dict[str, Any]:
    result = _one(
        result_rows,
        "baseline_id",
        "original_project_iot_drpa_text_2_5",
        source=BASELINE_RESULT_PATH,
    )
    if result["status"] != "PASS":
        raise BaselineEvidenceError("committed original-project HCA* result is unavailable")

    denominator_metrics: dict[str, Mapping[str, str]] = {}
    for denominator in (
        "processed_segment_attempt_time_tth",
        "java_release_time_tth",
        "original_entry_time_tth",
    ):
        matches = [
            row
            for row in denominator_rows
            if row.get("variant") == "original_project_text_result"
            and row.get("tth_denominator") == denominator
        ]
        if len(matches) != 1:
            raise BaselineEvidenceError(
                f"missing original-project denominator row {denominator}"
            )
        denominator_metrics[denominator] = matches[0]

    processed = denominator_metrics["processed_segment_attempt_time_tth"]
    java_release = denominator_metrics["java_release_time_tth"]
    legacy_mislabeled = denominator_metrics["original_entry_time_tth"]
    corrected = reconciliation["corrected_targets"]

    return {
        "baseline_id": "original_project_iot_drpa_hca_star",
        "role": "original centralized IoT-DRPA / HCA* baseline",
        "evidence_status": "HISTORICAL_PARSED_ORIGINAL_PROJECT_OUTPUT",
        "fresh_java_rerun": False,
        "one_x": {
            "raw_bag_count": int(result["raw_bag_count"]),
            "complete_raw_bags": int(result["complete_bag_count"]),
            "speed_mps": 2.5,
            "processed_segment_attempt_time_tth": {
                "min_minutes": _number(processed["min_tht"], "HCA processed min"),
                "mean_minutes": _number(processed["mean_tht"], "HCA processed mean"),
                "max_minutes": _number(processed["max_tht"], "HCA processed max"),
            },
            "java_release_time_tth_mean_minutes": _number(
                java_release["mean_tht"], "HCA Java-release mean"
            ),
            "java_release_time_tth_min_minutes": _number(
                java_release["min_tht"], "HCA Java-release min"
            ),
            "java_release_time_tth_max_minutes": _number(
                java_release["max_tht"], "HCA Java-release max"
            ),
            "legacy_mislabeled_original_entry_mean_minutes": _number(
                legacy_mislabeled["mean_tht"], "HCA legacy pass-time field"
            ),
            "legacy_mislabeled_original_entry_min_minutes": _number(
                legacy_mislabeled["min_tht"], "HCA legacy pass-time field min"
            ),
            "legacy_mislabeled_original_entry_max_minutes": _number(
                legacy_mislabeled["max_tht"], "HCA legacy pass-time field max"
            ),
            "matched_raw_entry_time_tth_mean_minutes": _number(
                corrected["historical_hca_raw_entry_target_minutes"],
                "HCA corrected raw-entry target",
            ),
        },
        "scale_availability": {
            "1x": "HISTORICAL_PARSED_ORIGINAL_PROJECT_OUTPUT",
            "2x": "N/A_NOT_IN_PAPER_PROTOCOL",
            "4x": "N/A_NOT_IN_PAPER_PROTOCOL",
        },
        "claim_boundary": (
            "The 1x values are parsed historical original-project evidence, "
            "not a fresh Java/HCA* rerun. Static A*, v2-safe, and a copied 1x "
            "number are not substitutes for HCA* at 2x or 4x."
        ),
        "evidence": [
            str(BASELINE_RESULT_PATH).replace("\\", "/"),
            str(DENOMINATOR_TABLE_PATH).replace("\\", "/"),
            str(DENOMINATOR_PATH).replace("\\", "/"),
        ],
    }


def build_paper_baseline_summary(root: Path = ROOT) -> dict[str, Any]:
    """Return the G23 paper protocol and required dual-baseline contract."""

    root = root.resolve()
    f2 = _read_json(root, F2_PATH)
    reconciliation = _read_json(root, DENOMINATOR_PATH)
    protocol_rows = _read_csv(root, PROTOCOL_PATH)
    metric_rows = _read_csv(root, METRICS_PATH)
    baseline_rows = _read_csv(root, BASELINE_INVENTORY_PATH)
    result_rows = _read_csv(root, BASELINE_RESULT_PATH)
    denominator_rows = _read_csv(root, DENOMINATOR_TABLE_PATH)

    return {
        "schema": "czr005.g4irsf23.paper_dual_baseline.v1",
        "paper": _paper_protocol(protocol_rows, metric_rows, baseline_rows),
        "required_baselines": {
            "frozen_f2": _f2_baseline(f2),
            "original_hca_star": _hca_baseline(
                result_rows, denominator_rows, reconciliation
            ),
        },
        "comparison_contract": {
            "matched_dimensions": [
                "map and task population",
                "raw-bag grouping",
                "speed and scenario",
                "THT denominator",
                "completion and safety scope",
            ],
            "denominators_to_report_separately": [
                "processed_segment_attempt_time_tth",
                "java_release_time_tth",
                "original_entry_time_tth",
            ],
            "cross_denominator_winner_claim_allowed": False,
            "paper_main_scope": "1x / 28,506 raw bags / 2.5 m/s",
            "hca_2x": "N/A_NOT_IN_PAPER_PROTOCOL",
            "hca_4x": "N/A_NOT_IN_PAPER_PROTOCOL",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    rendered = json.dumps(
        build_paper_baseline_summary(args.root),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

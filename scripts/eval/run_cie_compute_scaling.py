#!/usr/bin/env python3
"""Extract descriptive compute-scaling evidence from explicit formal JSONs.

This tool never starts an algorithm.  Inputs are supplied as repeated
``--input label=path`` arguments and are identity-checked before resource
measurements are admitted.  Per-completion costs are within-run descriptive
normalizations, not cross-protocol complexity estimates.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))


NM = "N/M"
LABELS = (
    "hca_java",
    "g31_native",
    "cie_dh_common_executor",
    "tarau_common_executor",
)
LABEL_ALIASES = {
    "hca": "hca_java",
    "feng_hca_java": "hca_java",
    "g31": "g31_native",
    "cie_dh": "cie_dh_common_executor",
    "cie_dh_common": "cie_dh_common_executor",
    "tarau": "tarau_common_executor",
    "tarau_common": "tarau_common_executor",
}

FIELDS = (
    "input_label",
    "source_file",
    "source_subrun_id",
    "schema",
    "identity_status",
    "identity_reasons",
    "baseline_family",
    "configuration",
    "reproduction_or_adaptation_label",
    "executor",
    "language",
    "release_protocol",
    "coordination_protocol",
    "map",
    "load_factor",
    "population_raw_bag_count",
    "population_segment_count",
    "completed_raw_bag_count",
    "completed_raw_bag_count_reason",
    "completed_segment_count",
    "completed_segment_count_reason",
    "wall_seconds",
    "wall_seconds_reason",
    "cpu_seconds",
    "cpu_seconds_reason",
    "peak_rss_bytes",
    "peak_rss_bytes_reason",
    "event_count",
    "event_count_reason",
    "decision_count",
    "decision_count_reason",
    "wall_seconds_per_completed_raw_bag",
    "wall_seconds_per_completed_raw_bag_reason",
    "cpu_seconds_per_completed_raw_bag",
    "cpu_seconds_per_completed_raw_bag_reason",
    "events_per_completed_raw_bag",
    "events_per_completed_raw_bag_reason",
    "decisions_per_completed_raw_bag",
    "decisions_per_completed_raw_bag_reason",
    "survivor_timing_used",
    "survivor_timing_used_reason",
    "cross_protocol_complexity_claim_permitted",
)


class ComputeScalingError(RuntimeError):
    """Raised when an explicit input cannot be parsed safely."""


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return int(value) if isinstance(value, int) else numeric


def _normalise_label(label: str) -> str:
    value = label.strip().lower().replace("-", "_").replace(" ", "_")
    value = LABEL_ALIASES.get(value, value)
    if value not in LABELS:
        raise ComputeScalingError(
            f"unsupported input label {label!r}; expected one of {', '.join(LABELS)}"
        )
    return value


def parse_input_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise ComputeScalingError("--input must use label=path")
    label, raw_path = spec.split("=", 1)
    if not raw_path.strip():
        raise ComputeScalingError("--input path cannot be empty")
    path = Path(raw_path.strip())
    if not path.is_absolute():
        path = ROOT / path
    return _normalise_label(label), path.resolve(strict=True)


def _load(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComputeScalingError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ComputeScalingError(f"JSON object required: {path}")
    return value


def _explicit_survivor(data: Mapping[str, Any]) -> tuple[bool | str, str]:
    candidates = (
        _nested(data, "provenance", "survivor_timing_used"),
        _nested(data, "identity_contract", "survivor_timing_used"),
        _nested(
            data,
            "paper_subjects",
            "full_population_raw_bag_timing",
            "survivor_or_common_cohort_used",
        ),
        _nested(data, "full_population_timing", "survivor_or_common_cohort_used"),
    )
    explicit = [value for value in candidates if isinstance(value, bool)]
    if not explicit:
        return NM, "SOURCE_FIELD_ABSENT_NO_SURVIVOR_INFERENCE"
    if len(set(explicit)) != 1:
        return NM, "CONFLICTING_EXPLICIT_SURVIVOR_FIELDS"
    return explicit[0], "EXPLICIT_SOURCE_FIELD"


def _common_runtime(data: Mapping[str, Any]) -> Mapping[str, Any]:
    runtime = data.get("runtime")
    return runtime if isinstance(runtime, Mapping) else {}


def _common_native_summary(data: Mapping[str, Any]) -> Mapping[str, Any]:
    runtime = _common_runtime(data)
    native = runtime.get("native_summary")
    if isinstance(native, Mapping):
        return native
    summary = runtime.get("summary")
    return summary if isinstance(summary, Mapping) else runtime


def _common_population(data: Mapping[str, Any]) -> tuple[Any, Any, Any, Any]:
    population = data.get("population")
    population = population if isinstance(population, Mapping) else {}
    raw_population = _number(
        population.get("raw_bag_count", population.get("raw_bag_denominator"))
    )
    segment_population = _number(population.get("segment_count"))
    completed_raw = _number(
        _nested(data, "paper_subjects", "fixed_horizon_capacity", "completed_raw_bag_count")
    )
    if completed_raw is None:
        completed_raw = _number(
            _nested(
                data,
                "fixed_denominator_business",
                "detailed",
                "completed_raw_bag_count",
            )
        )
    native = _common_native_summary(data)
    completed_segments = _number(native.get("completed_count"))
    return raw_population, segment_population, completed_raw, completed_segments


def _common_executor(data: Mapping[str, Any]) -> str | None:
    explicit = _nested(data, "provenance", "executor_identity")
    if isinstance(explicit, str) and explicit:
        return explicit
    runtime = _common_runtime(data)
    loaded = runtime.get("loaded_cpp_binary_path")
    if not loaded:
        loaded = _nested(runtime, "native_summary", "loaded_cpp_binary_path")
    return "COMMON_CPP_EVENT_EXECUTOR" if isinstance(loaded, str) and loaded else None


def _common_identity(
    label: str, data: Mapping[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    algorithm = data.get("algorithm")
    algorithm = algorithm if isinstance(algorithm, Mapping) else {}
    family = algorithm.get(
        "baseline_family", _nested(data, "provenance", "baseline_family")
    )
    if family is None and label == "g31_native":
        scorer = algorithm.get(
            "scorer_mode", _nested(data, "request_contract", "scorer_mode")
        )
        family = "G31_S4_NATIVE" if scorer == "S4_queue_aware_rule_only" else None
    executor = _common_executor(data)
    coordination = algorithm.get(
        "coordination_protocol",
        _nested(data, "provenance", "coordination_protocol"),
    )
    release = _nested(data, "release_protocol", "mode")
    if release is None:
        release = _nested(data, "provenance", "release_protocol")
    reproduction = algorithm.get(
        "reproduction_or_adaptation_label",
        algorithm.get(
            "label", _nested(data, "provenance", "reproduction_or_adaptation_label")
        ),
    )
    load_factor = _number(data.get("scale"))
    if load_factor is None:
        load_factor = _number(data.get("nominal_load_factor"))
    reasons: list[str] = []
    if data.get("status") != "COMPLETE":
        reasons.append("ARTIFACT_STATUS_NOT_COMPLETE")
    if _nested(data, "execution_integrity", "pass") is not True:
        reasons.append("EXECUTION_INTEGRITY_NOT_PASSING")
    if executor is None or "CPP" not in executor.upper():
        reasons.append("COMMON_CPP_EXECUTOR_NOT_VERIFIED")
    if release is None:
        reasons.append("RELEASE_PROTOCOL_NOT_REPORTED")
    if coordination is None:
        reasons.append("COORDINATION_PROTOCOL_NOT_REPORTED")
    if data.get("map") not in {"map2", "nanning"}:
        reasons.append("REGISTERED_MAP_IDENTITY_NOT_VERIFIED")
    if load_factor is None:
        reasons.append("LOAD_FACTOR_NOT_REPORTED")

    if label == "g31_native":
        if family not in {"G31_S4", "G31_S4_NATIVE"}:
            reasons.append("BASELINE_FAMILY_NOT_G31_S4")
        scorer = algorithm.get(
            "scorer_mode", _nested(data, "request_contract", "scorer_mode")
        )
        if scorer is not None and scorer != "S4_queue_aware_rule_only":
            reasons.append("SCORER_NOT_G31_S4")
    elif label == "cie_dh_common_executor":
        if family != "CIE_DH_2009_COMMON_EXECUTOR_ADAPTATION":
            reasons.append("BASELINE_FAMILY_NOT_CIE_DH_COMMON_ADAPTATION")
        text = str(reproduction or "").upper()
        if "ADAPT" not in text or "NATIVE" in text and "NOT_FENG_NATIVE" not in text:
            reasons.append("ADAPTATION_NOT_EXPLICITLY_IDENTIFIED")
    else:
        if not isinstance(family, str) or not family.startswith("TARAU_"):
            reasons.append("BASELINE_FAMILY_NOT_TARAU")
        text = str(reproduction or "").upper()
        if "ADAPT" not in text and "NOT_EXACT" not in text:
            reasons.append("TARAU_ADAPTATION_NOT_EXPLICITLY_IDENTIFIED")
        if coordination != "neutral_fifo":
            reasons.append("TARAU_COORDINATION_NOT_NEUTRAL_FIFO")

    return reasons, {
        "baseline_family": family or NM,
        "configuration": algorithm.get(
            "cell_id",
            _nested(data, "request_contract", "static_potential")
            or algorithm.get("label")
            or family
            or NM,
        ),
        "reproduction_or_adaptation_label": reproduction or NM,
        "executor": executor or NM,
        "language": "C++_PYTHON_BINDING",
        "release_protocol": release or NM,
        "coordination_protocol": coordination or NM,
        "map": data.get("map", NM),
        "load_factor": load_factor if load_factor is not None else NM,
    }


def _measurement(value: Any, absent_reason: str) -> tuple[int | float | str, str]:
    numeric = _number(value)
    if numeric is not None:
        return numeric, "MEASURED"
    if isinstance(value, str) and "NOT_MEASURED" in value.upper():
        return NM, "SOURCE_EXPLICITLY_NOT_MEASURED"
    return NM, absent_reason


def _per_completed(
    numerator: int | float | str,
    numerator_reason: str,
    completed: int | float | str,
) -> tuple[float | str, str]:
    value = _number(numerator)
    denominator = _number(completed)
    if value is None:
        return NM, f"NUMERATOR_NOT_MEASURED:{numerator_reason}"
    if denominator is None:
        return NM, "COMPLETED_RAW_BAG_DENOMINATOR_NOT_MEASURED"
    if denominator <= 0:
        return NM, "COMPLETED_RAW_BAG_DENOMINATOR_NONPOSITIVE"
    return float(value) / float(denominator), "DERIVED_WITHIN_RUN"


def _redact_unverified(row: dict[str, Any]) -> None:
    measured = (
        "completed_raw_bag_count",
        "completed_segment_count",
        "wall_seconds",
        "cpu_seconds",
        "peak_rss_bytes",
        "event_count",
        "decision_count",
    )
    derived = (
        "wall_seconds_per_completed_raw_bag",
        "cpu_seconds_per_completed_raw_bag",
        "events_per_completed_raw_bag",
        "decisions_per_completed_raw_bag",
    )
    for field in measured:
        row[field] = NM
        row[f"{field}_reason"] = "IDENTITY_NOT_VERIFIED"
    for field in derived:
        row[field] = NM
        row[f"{field}_reason"] = "IDENTITY_NOT_VERIFIED"


def _common_row(label: str, path: Path, data: Mapping[str, Any]) -> dict[str, Any]:
    reasons, identity = _common_identity(label, data)
    runtime = _common_runtime(data)
    native = _common_native_summary(data)
    raw_population, segment_population, completed_raw, completed_segments = (
        _common_population(data)
    )
    wall, wall_reason = _measurement(runtime.get("wall_seconds"), "SOURCE_FIELD_ABSENT")
    cpu, cpu_reason = _measurement(runtime.get("cpu_seconds"), "SOURCE_FIELD_ABSENT")
    rss_source = runtime.get("peak_rss_bytes")
    if rss_source is None:
        rss_source = _nested(data, "provenance", "peak_rss_bytes")
    rss, rss_reason = _measurement(rss_source, "SOURCE_FIELD_ABSENT")
    event, event_reason = _measurement(native.get("event_count"), "SOURCE_FIELD_ABSENT")
    decision, decision_reason = _measurement(
        native.get("decision_count"), "SOURCE_FIELD_ABSENT"
    )
    completed_raw_value, completed_raw_reason = _measurement(
        completed_raw, "COMPLETED_RAW_BAG_FIELD_ABSENT"
    )
    completed_segment_value, completed_segment_reason = _measurement(
        completed_segments, "COMPLETED_SEGMENT_FIELD_ABSENT"
    )
    survivor, survivor_reason = _explicit_survivor(data)
    row: dict[str, Any] = {
        "input_label": label,
        "source_file": str(path),
        "source_subrun_id": NM,
        "schema": data.get("schema", NM),
        "identity_status": "VERIFIED" if not reasons else "REJECTED",
        "identity_reasons": "PASS" if not reasons else ";".join(reasons),
        **identity,
        "population_raw_bag_count": raw_population if raw_population is not None else NM,
        "population_segment_count": (
            segment_population if segment_population is not None else NM
        ),
        "completed_raw_bag_count": completed_raw_value,
        "completed_raw_bag_count_reason": completed_raw_reason,
        "completed_segment_count": completed_segment_value,
        "completed_segment_count_reason": completed_segment_reason,
        "wall_seconds": wall,
        "wall_seconds_reason": wall_reason,
        "cpu_seconds": cpu,
        "cpu_seconds_reason": cpu_reason,
        "peak_rss_bytes": rss,
        "peak_rss_bytes_reason": rss_reason,
        "event_count": event,
        "event_count_reason": event_reason,
        "decision_count": decision,
        "decision_count_reason": decision_reason,
        "survivor_timing_used": survivor,
        "survivor_timing_used_reason": survivor_reason,
        "cross_protocol_complexity_claim_permitted": False,
    }
    for field, numerator, reason in (
        ("wall_seconds_per_completed_raw_bag", wall, wall_reason),
        ("cpu_seconds_per_completed_raw_bag", cpu, cpu_reason),
        ("events_per_completed_raw_bag", event, event_reason),
        ("decisions_per_completed_raw_bag", decision, decision_reason),
    ):
        value, derived_reason = _per_completed(
            numerator, reason, completed_raw_value
        )
        row[field] = value
        row[f"{field}_reason"] = derived_reason
    if reasons:
        _redact_unverified(row)
    return row


def _hca_rows(path: Path, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    contract = data.get("identity_contract")
    contract = contract if isinstance(contract, Mapping) else {}
    regression = data.get("hca_regression")
    regression = regression if isinstance(regression, Mapping) else {}
    reasons: list[str] = []
    if data.get("schema") != "czr005.cie_revision.feng_native_cie_dh_audit.v1":
        reasons.append("HCA_AUDIT_SCHEMA_MISMATCH")
    if contract.get("baseline_family") != "FENG_NATIVE_HCA":
        reasons.append("BASELINE_FAMILY_NOT_FENG_NATIVE_HCA")
    if contract.get("executor_identity") != "FENG_NATIVE_JAVA_HCA_SCHEDULER":
        reasons.append("JAVA_HCA_EXECUTOR_NOT_VERIFIED")
    if contract.get("coordination_protocol") != "CENTRALIZED_ASTAR_RESERVATION":
        reasons.append("HCA_COORDINATION_IDENTITY_MISMATCH")
    if contract.get("release_protocol") != "ORIGINAL_JAVA_TASK_RELEASE":
        reasons.append("HCA_RELEASE_IDENTITY_MISMATCH")
    if regression.get("pass") is not True:
        reasons.append("HCA_REGRESSION_NOT_PASSING")
    runs = regression.get("runs")
    if not isinstance(runs, list) or not runs:
        runs = [{}]
        reasons.append("HCA_RUN_OBSERVATION_ABSENT")

    rows: list[dict[str, Any]] = []
    for run in runs:
        run = run if isinstance(run, Mapping) else {}
        observed = run.get("observed")
        observed = observed if isinstance(observed, Mapping) else {}
        run_reasons = list(reasons)
        if run.get("pass") is not True:
            run_reasons.append("HCA_SUBRUN_NOT_PASSING")
        if observed.get("survivor_only") is not False:
            run_reasons.append("HCA_FULL_POPULATION_NOT_VERIFIED")
        wall, wall_reason = _measurement(
            observed.get("wall_seconds"), "HCA_WALL_FIELD_ABSENT"
        )
        cpu, cpu_reason = _measurement(
            observed.get("cpu_seconds"), "HCA_CPU_NOT_INSTRUMENTED"
        )
        rss, rss_reason = _measurement(
            observed.get("peak_rss_bytes"), "HCA_PEAK_RSS_NOT_INSTRUMENTED"
        )
        event, event_reason = _measurement(
            observed.get("event_count"), "JAVA_HCA_EVENT_COUNT_NOT_INSTRUMENTED"
        )
        decision, decision_reason = _measurement(
            observed.get("decision_count"),
            "JAVA_HCA_DECISION_COUNT_NOT_INSTRUMENTED",
        )
        completed_raw, completed_raw_reason = _measurement(
            observed.get("complete_raw_bag_count"),
            "HCA_COMPLETED_RAW_BAG_FIELD_ABSENT",
        )
        completed_segments, completed_segments_reason = _measurement(
            observed.get("completed_segment_count"),
            "HCA_COMPLETED_SEGMENT_FIELD_ABSENT",
        )
        row: dict[str, Any] = {
            "input_label": "hca_java",
            "source_file": str(path),
            "source_subrun_id": run.get("run_id", NM),
            "schema": data.get("schema", NM),
            "identity_status": "VERIFIED" if not run_reasons else "REJECTED",
            "identity_reasons": "PASS" if not run_reasons else ";".join(run_reasons),
            "baseline_family": "FENG_NATIVE_HCA",
            "configuration": "FENG_NATIVE_HCA_REGRESSION",
            "reproduction_or_adaptation_label": contract.get(
                "reproduction_or_adaptation_label", NM
            ),
            "executor": contract.get("executor_identity", NM),
            "language": "JAVA",
            "release_protocol": contract.get("release_protocol", NM),
            "coordination_protocol": contract.get("coordination_protocol", NM),
            "map": "map2",
            "load_factor": 1,
            "population_raw_bag_count": observed.get("raw_bag_count", NM),
            "population_segment_count": observed.get("segment_count", NM),
            "completed_raw_bag_count": completed_raw,
            "completed_raw_bag_count_reason": completed_raw_reason,
            "completed_segment_count": completed_segments,
            "completed_segment_count_reason": completed_segments_reason,
            "wall_seconds": wall,
            "wall_seconds_reason": wall_reason,
            "cpu_seconds": cpu,
            "cpu_seconds_reason": cpu_reason,
            "peak_rss_bytes": rss,
            "peak_rss_bytes_reason": rss_reason,
            "event_count": event,
            "event_count_reason": event_reason,
            "decision_count": decision,
            "decision_count_reason": decision_reason,
            "survivor_timing_used": observed.get("survivor_only", NM),
            "survivor_timing_used_reason": "EXPLICIT_SOURCE_FIELD",
            "cross_protocol_complexity_claim_permitted": False,
        }
        for field, numerator, reason in (
            ("wall_seconds_per_completed_raw_bag", wall, wall_reason),
            ("cpu_seconds_per_completed_raw_bag", cpu, cpu_reason),
            ("events_per_completed_raw_bag", event, event_reason),
            ("decisions_per_completed_raw_bag", decision, decision_reason),
        ):
            value, derived_reason = _per_completed(
                numerator, reason, completed_raw
            )
            row[field] = value
            row[f"{field}_reason"] = derived_reason
        if run_reasons:
            _redact_unverified(row)
        rows.append(row)
    return rows


def extract_rows(label: str, path: Path) -> list[dict[str, Any]]:
    data = _load(path)
    if label == "hca_java":
        return _hca_rows(path, data)
    return [_common_row(label, path, data)]


def collect(specs: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        label, path = parse_input_spec(spec)
        rows.extend(extract_rows(label, path))
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: NM if row.get(field) is None else row.get(field, NM)
                    for field in FIELDS
                }
            )
    os.replace(temporary, path)


def _display(value: Any) -> str:
    numeric = _number(value)
    if numeric is None:
        return str(value)
    if isinstance(numeric, int):
        return str(numeric)
    return f"{numeric:.6g}"


def _write_report(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    verified = sum(row.get("identity_status") == "VERIFIED" for row in rows)
    lines = [
        "# CIE compute-scaling audit",
        "",
        f"Explicit observations: **{len(rows)}**; identity VERIFIED: **{verified}**.",
        "",
        "This is a read-only extraction of already-produced formal JSON. It did not start, rerun, or tune any algorithm.",
        "",
        "Wall time, CPU time, RSS, event count and decision count are reported only when the source measured them. `N/M` means not measured and is accompanied by a reason in the CSV. Per-completed-bag values are within-observation descriptive normalizations only.",
        "",
        "**Cross-language and cross-executor wall-time multiples are not causal algorithm effects.** Java versus C++/Python-binding runtime includes language, VM, instrumentation, executor, release and coordination differences. These rows cannot establish pure algorithmic complexity or a cross-protocol speedup.",
        "",
        "The 2× THT rule is outside this compute table. Survivor/common-cohort use is never inferred: it is copied only from an explicit source field, otherwise `N/M`.",
        "",
        "## Observations",
        "",
        "| label / configuration | executor/language | release | coordination | map/load | identity | completed bags | wall (s) | CPU (s) | RSS | events | decisions | wall/bag |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {label} | {executor} / {language} | {release} | {coord} | {map} / {load}× | {identity} | {completed} | {wall} | {cpu} | {rss} | {events} | {decisions} | {per} |".format(
                label=f"{row['input_label']} / {row['configuration']}",
                executor=row["executor"],
                language=row["language"],
                release=row["release_protocol"],
                coord=row["coordination_protocol"],
                map=row["map"],
                load=row["load_factor"],
                identity=row["identity_status"],
                completed=_display(row["completed_raw_bag_count"]),
                wall=_display(row["wall_seconds"]),
                cpu=_display(row["cpu_seconds"]),
                rss=_display(row["peak_rss_bytes"]),
                events=_display(row["event_count"]),
                decisions=_display(row["decision_count"]),
                per=_display(row["wall_seconds_per_completed_raw_bag"]),
            )
        )
        if row["identity_status"] != "VERIFIED":
            lines.append(
                f"  - Rejected `{row['input_label']}` identity: `{row['identity_reasons']}`. Measurements are redacted to `N/M`."
            )
    lines.extend(
        [
            "",
            "No cross-row ratios, asymptotic exponents, or survivor-derived performance values are produced.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def aggregate(
    *, specs: Sequence[str], table: Path, report: Path
) -> tuple[int, int]:
    if not specs:
        raise ComputeScalingError("at least one explicit --input label=path is required")
    rows = collect(specs)
    _write_csv(table, rows)
    _write_report(report, rows)
    return len(rows), sum(row["identity_status"] == "VERIFIED" for row in rows)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help=(
            "Explicit label=JSON path; repeatable. Labels: " + ", ".join(LABELS)
        ),
    )
    parser.add_argument(
        "--table",
        type=Path,
        default=Path("outputs/tables/cie_compute_scaling.csv"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("outputs/reports/cie_compute_scaling_audit.md"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        count, verified = aggregate(
            specs=args.input,
            table=args.table,
            report=args.report,
        )
    except (OSError, ComputeScalingError) as exc:
        raise SystemExit(f"compute-scaling extraction failed: {exc}") from exc
    print(f"observations={count} identity_verified={verified}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

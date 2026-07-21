from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from czr005.datasets.decision_trace import (
    CANDIDATE_ORDERING,
    MODEL_SCORE_SEMANTICS,
    SCHEMA_ID,
    SamplingConfig,
    decision_source_links,
    decision_trace_schema,
    feature_lineage_rows,
    load_adjacency,
    load_jsonl,
    outcome_rows_by_decision,
    source_identity_audit,
    source_release_mapping,
    stratified_reservoir_sample,
    validate_decision_rows,
    validate_feature_lineage,
    validate_outcome_decision_identities,
    validate_runtime_bag_identity,
)


DATASET_DIR = ROOT / "artifacts" / "datasets"
TABLE_DIR = ROOT / "outputs" / "tables"
REPORT_DIR = ROOT / "outputs" / "reports"

TRACE_SCHEMA = DATASET_DIR / "g4irsf11_decision_trace_schema.json"
TRACE_MANIFEST = DATASET_DIR / "g4irsf11_decision_trace_manifest.json"
TRACE_SAMPLE = DATASET_DIR / "g4irsf11_decision_trace_sample.jsonl"
OUTCOME_SAMPLE = DATASET_DIR / "g4irsf11_decision_outcome_sample.jsonl"
HARD_CASE_INDEX = TABLE_DIR / "g4irsf11_stratified_hard_case_index.csv"
SAMPLING_BALANCE = TABLE_DIR / "g4irsf11_sampling_balance.csv"
SAMPLING_REPORT = REPORT_DIR / "g4irsf11_sampling_balance_report.md"
LINEAGE_TABLE = TABLE_DIR / "g4irsf11_feature_lineage_audit.csv"
LINEAGE_REPORT = REPORT_DIR / "g4irsf11_feature_lineage_audit.md"
SOURCE_RELEASE_TABLE = TABLE_DIR / "g4irsf11_source_release_decision_mapping.csv"
SOURCE_IDENTITY_TABLE = TABLE_DIR / "g4irsf11_source_identity_audit.csv"
SOURCE_IDENTITY_REPORT = REPORT_DIR / "g4irsf11_source_identity_audit.md"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    payload = path.read_bytes()
    # Git normalises committed text to LF while Windows working trees may use
    # CRLF.  Dataset bindings must describe semantic text bytes identically on
    # both platforms; binary artifacts remain byte-exact.
    if path.suffix.lower() in {".csv", ".json", ".jsonl", ".md", ".py", ".txt", ".yml", ".yaml"}:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    digest.update(payload)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _json_scalar(value: Any) -> Any:
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _json_scalar(row.get(name)) for name in fieldnames})


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            count += 1
    return count


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def _read_trace(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read JSONL rows or a C++ runtime payload JSON object."""

    if path.suffix.lower() == ".jsonl":
        return load_jsonl(path), {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        if not all(isinstance(row, dict) for row in payload):
            raise ValueError(f"{path}: trace array contains a non-object row")
        return list(payload), {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: trace payload must be an object or array")
    rows = payload.get(
        "decisions",
        payload.get("decision_trace", payload.get("decision_rows", payload.get("trace"))),
    )
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: no decisions/decision_trace/decision_rows/trace array")
    context = payload.get("trace_context", payload.get("metadata", {}))
    if not isinstance(context, dict):
        raise ValueError(f"{path}: trace_context must be an object")
    result_context = dict(context)
    summary = payload.get("summary")
    if summary is not None:
        if not isinstance(summary, dict):
            raise ValueError(f"{path}: summary must be an object")
        result_context["_runtime_summary"] = dict(summary)
    return list(rows), result_context


def _merge_metadata(
    row: Mapping[str, Any], defaults: Mapping[str, Any], payload_context: Mapping[str, Any], shard_id: str
) -> dict[str, Any]:
    merged = dict(defaults)
    # Payload context also contains invariant audit flags such as
    # ``bag_future_path_field_present=false``.  Those belong in the shard
    # manifest, not inside a runtime decision row where even the field name
    # would violate the fail-closed no-future-route schema.
    row_context_keys = {
        "scenario",
        "scale",
        "fault_mode",
        "run_id",
        "model_score_semantics",
        "candidate_ordering",
        "reservation_depth",
        "diagnostic_hops",
        "trace_shard_count",
        "trace_shard_index",
    }
    merged.update({key: value for key, value in payload_context.items() if key in row_context_keys})
    row_metadata = row.get("metadata") or {}
    if not isinstance(row_metadata, Mapping):
        raise ValueError("decision metadata must be an object")
    merged.update(row_metadata)
    merged.setdefault("trace_shard", shard_id)
    result = dict(row)
    result["metadata"] = merged
    return result


def _read_all_traces(
    paths: list[Path], defaults: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    shards: list[dict[str, Any]] = []
    for path in paths:
        shard_rows, context = _read_trace(path)
        rows.extend(_merge_metadata(row, defaults, context, path.stem) for row in shard_rows)
        runtime_summary = context.pop("_runtime_summary", {})
        shards.append(
            {
                "path": _relative(path),
                "sha256": _sha256(path),
                "decision_count": len(shard_rows),
                "context": context,
                "runtime_summary": runtime_summary,
            }
        )
    return rows, shards


def _trace_completeness_group(
    group_key: str, shards: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Validate one logical run's declared decision shards fail-closed."""

    blockers: list[str] = []
    declared_counts: set[int] = set()
    observed_index_values: list[int] = []
    observed_indices: set[int] = set()
    global_seen_counts: set[int] = set()
    shard_seen_sum = 0
    stored_sum = 0
    hold_stored_sum = 0
    for shard in shards:
        context = shard.get("context") or {}
        summary = shard.get("runtime_summary") or {}
        count_raw = context.get("trace_shard_count", summary.get("trace_shard_count"))
        index_raw = context.get("trace_shard_index", summary.get("trace_shard_index"))
        if count_raw is None or index_raw is None:
            blockers.append(f"missing_shard_metadata:{shard.get('path')}")
        else:
            declared_counts.add(int(count_raw))
            observed_index_values.append(int(index_raw))
            observed_indices.add(int(index_raw))
        required_summary = {
            "decision_trace_seen_count",
            "decision_trace_shard_seen_count",
            "decision_trace_stored_count",
            "hold_trace_stored_count",
            "decision_trace_truncated",
        }
        missing_summary = sorted(required_summary - set(summary))
        if missing_summary:
            blockers.append(
                f"missing_trace_summary:{shard.get('path')}:{','.join(missing_summary)}"
            )
            continue
        global_seen_counts.add(int(summary["decision_trace_seen_count"]))
        shard_seen_sum += int(summary["decision_trace_shard_seen_count"])
        stored = int(summary["decision_trace_stored_count"])
        hold_stored = int(summary["hold_trace_stored_count"])
        stored_sum += stored
        hold_stored_sum += hold_stored
        if bool(summary["decision_trace_truncated"]):
            blockers.append(f"decision_trace_truncated:{shard.get('path')}")
        if stored != int(shard.get("decision_count", -1)):
            blockers.append(f"stored_count_mismatch:{shard.get('path')}")
        if not bool(summary["decision_trace_truncated"]):
            shard_seen = int(summary["decision_trace_shard_seen_count"])
            if stored + hold_stored != shard_seen:
                blockers.append(
                    f"stored_plus_hold_mismatch:{shard.get('path')}:"
                    f"stored={stored},hold={hold_stored},shard_seen={shard_seen}"
                )
    declared_count = next(iter(declared_counts)) if len(declared_counts) == 1 else 0
    expected_indices = set(range(declared_count)) if declared_count > 0 else set()
    if len(declared_counts) != 1:
        blockers.append("inconsistent_or_missing_trace_shard_count")
    if len(observed_index_values) != len(observed_indices):
        blockers.append(f"duplicate_trace_shard_index:{sorted(observed_index_values)}")
    if observed_indices != expected_indices:
        blockers.append(
            f"incomplete_trace_shard_indices:observed={sorted(observed_indices)},expected={sorted(expected_indices)}"
        )
    if len(global_seen_counts) != 1:
        blockers.append("inconsistent_or_missing_global_decision_seen_count")
    global_seen = next(iter(global_seen_counts)) if len(global_seen_counts) == 1 else 0
    if len(global_seen_counts) == 1 and shard_seen_sum != global_seen:
        blockers.append(
            f"shard_seen_sum_mismatch:sum={shard_seen_sum},global={global_seen}"
        )
    return {
        "group_key": group_key,
        "status": "PASS" if not blockers else "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "input_file_count": len(shards),
        "declared_shard_count": declared_count,
        "observed_shard_indices": sorted(observed_indices),
        "expected_shard_indices": sorted(expected_indices),
        "global_decision_seen_count": global_seen,
        "shard_seen_count_sum": shard_seen_sum,
        "stored_decision_count_sum": stored_sum,
        "stored_hold_count_sum": hold_stored_sum,
        "blockers": blockers,
    }


def _trace_completeness(shards: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate every logical run independently, then aggregate exact totals.

    Independent high-flow/fault scenarios commonly each declare
    ``trace_shard_count=1`` and ``trace_shard_index=0``.  Treating all input
    files as one run would falsely report duplicate/mismatched shards, so the
    grouping identity is the available ``(context.run_id, context.scenario)``
    pair.  Using both prevents a reused run label from merging independent
    scenarios.  Inputs with neither identifier remain together in one explicit
    unspecified group and will still fail if their shard metadata is incomplete.
    """

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for shard in shards:
        context = shard.get("context") or {}
        run_id = str(context.get("run_id") or "").strip()
        scenario = str(context.get("scenario") or "").strip()
        if run_id and scenario:
            group_key = "run_id:" + run_id + "|scenario:" + scenario
        elif run_id:
            group_key = "run_id:" + run_id
        elif scenario:
            group_key = "scenario:" + scenario
        else:
            group_key = "unspecified_run"
        grouped.setdefault(group_key, []).append(shard)

    groups = [
        _trace_completeness_group(group_key, grouped[group_key])
        for group_key in sorted(grouped)
    ]
    blockers = [
        f"{group['group_key']}:{blocker}"
        for group in groups
        for blocker in group["blockers"]
    ]
    return {
        "status": "PASS" if groups and not blockers else "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "run_group_count": len(groups),
        "declared_shard_count": sum(int(group["declared_shard_count"]) for group in groups),
        "observed_shard_indices": (
            groups[0]["observed_shard_indices"] if len(groups) == 1 else []
        ),
        "expected_shard_indices": (
            groups[0]["expected_shard_indices"] if len(groups) == 1 else []
        ),
        "global_decision_seen_count": sum(
            int(group["global_decision_seen_count"]) for group in groups
        ),
        "shard_seen_count_sum": sum(int(group["shard_seen_count_sum"]) for group in groups),
        "stored_decision_count_sum": sum(
            int(group["stored_decision_count_sum"]) for group in groups
        ),
        "stored_hold_count_sum": sum(int(group["stored_hold_count_sum"]) for group in groups),
        "groups": groups,
        "blockers": blockers or ([] if groups else ["no_trace_run_groups"]),
    }


def _read_task_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return load_jsonl(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"{path}: task input must be JSONL or an array of objects")
    return payload


def _hard_case_fieldnames() -> list[str]:
    return [
        "case_id",
        "decision_id",
        "runtime_bag_id",
        "task_id",
        "segment_id",
        "event_time",
        "scenario",
        "scenario_observed",
        "scale",
        "source_node",
        "goal_node",
        "junction_node",
        "fault_bucket",
        "reason_bucket",
        "tail_bucket",
        "why_hard",
        "candidate_next_nodes",
        "candidate_records",
        "candidate_order_digest",
        "model_prediction",
        "model_score_semantics",
        "model_margin",
        "risk_gate_triggered",
        "fallback_selected_next",
        "selected_next",
        "model_fallback_disagreement",
        "decision_source",
        "rule_reason",
        "local_snapshot",
        "short_history",
        "full_astar_used",
        "original_arrival_time",
        "java_arrival_epoch",
        "release_time",
        "source_queue_delay_seconds",
        "outcome_ref",
        "stratum_id",
        "stratum_total_count_before_dedupe",
        "stratum_unique_total_count",
        "stratum_quota",
        "total_count",
        "unique_total_count",
        "quota",
        "sample_weight",
        "deterministic_repeat_count",
        "semantic_fingerprint",
    ]


def _balance_fieldnames() -> list[str]:
    return [
        "stratum_id",
        "scenario",
        "scale",
        "source",
        "goal",
        "junction",
        "fault",
        "reason",
        "tail",
        "total_count_before_dedupe",
        "unique_total_count",
        "deterministic_repeats_removed",
        "requested_minimum_quota",
        "effective_quota",
        "maximum_quota",
        "minimum_quota_satisfied",
        "sample_weight",
    ]


def _source_fieldnames() -> list[str]:
    return [
        "decision_id",
        "runtime_bag_id",
        "task_id",
        "segment_id",
        "source_node",
        "goal_node",
        "original_arrival_time",
        "java_arrival_epoch",
        "release_time",
        "source_queue_delay_seconds",
        "raw_arrival_to_release_delta_seconds",
        "source_queue_rank",
        "mapping_source",
    ]


def _source_identity_fieldnames() -> list[str]:
    return [
        "source_task_path",
        "processed_segment_count",
        "unique_original_task_id_count",
        "repeated_original_task_id_count",
        "extra_segments_sharing_original_task_id",
        "max_segments_per_original_task_id",
        "original_task_ids_rewritten",
        "runtime_internal_identity_required",
        "runtime_validation_status",
        "observed_decision_count",
        "observed_runtime_identity_count",
        "observed_original_segment_identity_count",
        "runtime_identity_alias_count",
    ]


def _runtime_sample_rows(
    decisions: list[dict[str, Any]], sample_rows: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    wanted = {str(row["decision_id"]) for row in sample_rows}
    return [row for row in decisions if str(row["decision_id"]) in wanted]


def _outcome_sample_rows(
    sample_rows: Iterable[Mapping[str, Any]], outcomes: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for sample in sample_rows:
        decision_id = str(sample["decision_id"])
        if decision_id in outcomes:
            result.append(dict(outcomes[decision_id]))
    return result


def _artifact_entry(path: Path, row_count: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": _relative(path), "sha256": _sha256(path)}
    if row_count is not None:
        result["row_count"] = row_count
    return result


def write_artifacts(
    *,
    trace_paths: list[Path],
    task_path: Path,
    map_path: Path,
    outcome_path: Path | None,
    scenario: str,
    scale: str,
    fault_mode: str,
    config: SamplingConfig,
    include_routine: bool = False,
) -> dict[str, Any]:
    """Validate source data and write all G4IRSF11-B artifacts."""

    defaults = {"scenario": scenario, "scale": scale, "fault_mode": fault_mode}
    raw_rows, trace_shards = _read_all_traces(trace_paths, defaults)
    trace_completeness = _trace_completeness(trace_shards)
    if not raw_rows:
        raise ValueError("decision trace is empty; an empty trace cannot satisfy the G4IRSF11 data gate")
    adjacency = load_adjacency(map_path)
    decisions = validate_decision_rows(raw_rows, adjacency)
    task_rows = _read_task_rows(task_path)
    source_identity = source_identity_audit(task_rows)
    runtime_identity = validate_runtime_bag_identity(decisions)
    source_mappings = source_release_mapping(task_rows)
    source_links = decision_source_links(decisions, source_mappings)
    outcomes = outcome_rows_by_decision(load_jsonl(outcome_path)) if outcome_path else {}
    unknown_outcomes = sorted(set(outcomes) - {str(row["decision_id"]) for row in decisions})
    if unknown_outcomes:
        raise ValueError(f"outcome file references unknown decision_id(s): {unknown_outcomes[:10]}")
    validate_outcome_decision_identities(outcomes, decisions)

    sample = stratified_reservoir_sample(
        decisions,
        source_links,
        outcomes=outcomes,
        config=config,
        include_routine=include_routine,
    )
    if not sample.rows:
        raise ValueError(
            "no eligible decision-level hard cases were sampled; provide outcome/hard decisions or use "
            "--include-routine only for an explicitly diagnostic dataset"
        )
    lineage = feature_lineage_rows()
    validate_feature_lineage(lineage)

    for path in (DATASET_DIR, TABLE_DIR, REPORT_DIR):
        path.mkdir(parents=True, exist_ok=True)
    TRACE_SCHEMA.write_text(
        json.dumps(decision_trace_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(LINEAGE_TABLE, lineage, list(lineage[0]))
    _write_csv(HARD_CASE_INDEX, sample.rows, _hard_case_fieldnames())
    _write_csv(SAMPLING_BALANCE, sample.balance_rows, _balance_fieldnames())
    _write_csv(SOURCE_RELEASE_TABLE, source_links, _source_fieldnames())
    source_identity_row = {
        "source_task_path": _relative(task_path),
        **source_identity,
        "runtime_validation_status": runtime_identity["status"],
        "observed_decision_count": runtime_identity["decision_count"],
        "observed_runtime_identity_count": runtime_identity["runtime_identity_count"],
        "observed_original_segment_identity_count": runtime_identity[
            "original_segment_identity_count"
        ],
        "runtime_identity_alias_count": runtime_identity["runtime_identity_alias_count"],
    }
    _write_csv(SOURCE_IDENTITY_TABLE, [source_identity_row], _source_identity_fieldnames())
    runtime_sample = _runtime_sample_rows(decisions, sample.rows)
    runtime_sample_count = _write_jsonl(TRACE_SAMPLE, runtime_sample)
    outcome_sample = _outcome_sample_rows(sample.rows, outcomes)
    outcome_sample_count = _write_jsonl(OUTCOME_SAMPLE, outcome_sample)

    stats = sample.statistics
    minimum_status = "PASS" if int(stats["strata_below_requested_minimum"]) == 0 else "EXPLICIT_SHORTFALL"
    dimension_counts: dict[str, dict[str, int]] = {}
    for dimension in ("scenario", "scale", "source", "goal", "junction", "fault", "reason", "tail"):
        counts: dict[str, int] = {}
        for row in sample.balance_rows:
            value = str(row[dimension])
            counts[value] = counts.get(value, 0) + int(row["total_count_before_dedupe"])
        dimension_counts[dimension] = dict(sorted(counts.items()))
    high_flow_covered = any(
        value not in {"1", "1x", "1.0", "unspecified"}
        for value in dimension_counts["scale"]
    ) or any("high_flow" in value.lower() for value in dimension_counts["scenario"])
    # A scenario-level fault flag is not evidence that any online decision saw
    # an active/stale local fault.  Only a decision whose local snapshot
    # reports an advertised fault exercises the fault branch; otherwise the
    # trace remains useful negative evidence but cannot satisfy fault coverage.
    fault_covered = int(dimension_counts["fault"].get("fault_local_active", 0)) > 0
    tail_covered = any(
        value in {"p95_tail", "p99_tail", "failed"} for value in dimension_counts["tail"]
    )
    content_coverage_pass = high_flow_covered and fault_covered and tail_covered
    coverage_status = (
        "PASS"
        if content_coverage_pass and trace_completeness["status"] == "PASS"
        else "PARTIAL_WITH_EXPLICIT_BLOCKER"
    )
    top_balance = sorted(
        sample.balance_rows,
        key=lambda row: (-int(row["total_count_before_dedupe"]), str(row["stratum_id"])),
    )[:20]
    SAMPLING_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF11 Decision-Level Stratified Sampling Balance",
                "",
                f"Generated: `{date.today().isoformat()}`.",
                f"Schema: `{SCHEMA_ID}`.",
                f"Candidate order: `{CANDIDATE_ORDERING}`.",
                f"Model score semantics: `{MODEL_SCORE_SEMANTICS}` (prediction=min cost; margin=second_min-min).",
                "Reservoir: `order_independent_bounded_sha256_priority_reservoir`.",
                "",
                "## Population and sampling",
                "",
                _markdown_table(
                    ["Metric", "Value"],
                    [[name, value] for name, value in stats.items() if name != "individual_reason_counts_before_dedupe"],
                ),
                "",
                f"Minimum-quota status: `{minimum_status}`. A shortfall is never converted to PASS.",
                f"High-flow/fault/tail coverage status: `{coverage_status}` (high_flow={high_flow_covered}, fault_local_active={fault_covered}, tail={tail_covered}).",
                f"Fault action coverage requires at least one committed `fault_local_active` decision; observed={int(dimension_counts['fault'].get('fault_local_active', 0))}. Scenario metadata alone never satisfies this gate.",
                f"Trace shard completeness: `{trace_completeness['status']}` (stored={trace_completeness['stored_decision_count_sum']}, seen={trace_completeness['global_decision_seen_count']}).",
                "",
                "## Hard-case reason coverage before deduplication",
                "",
                _markdown_table(
                    ["Reason", "Count"],
                    [[name, count] for name, count in stats["individual_reason_counts_before_dedupe"].items()],
                ),
                "",
                "## Largest strata",
                "",
                _markdown_table(
                    ["Scenario", "Scale", "Source", "Goal", "Junction", "Fault", "Reason", "Tail", "Total", "Unique", "Quota", "Weight"],
                    [
                        [
                            row["scenario"],
                            row["scale"],
                            row["source"],
                            row["goal"],
                            row["junction"],
                            row["fault"],
                            row["reason"],
                            row["tail"],
                            row["total_count_before_dedupe"],
                            row["unique_total_count"],
                            row["effective_quota"],
                            f"{float(row['sample_weight']):.6g}",
                        ]
                        for row in top_balance
                    ],
                ),
                "",
                "The hard-case CSV is a balanced decision index, not a first-50k prefix. `sample_weight` is the unique stratum population divided by its effective quota. Exact pre-deduplication counts are retained separately.",
                "",
                "Original arrival, Java arrival epoch, Java source release, and queue delay are linked to every decision in the source-release mapping table; backlog is not represented only by a scenario-level matrix.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    by_lineage: dict[str, int] = {}
    for row in lineage:
        by_lineage[str(row["lineage"])] = by_lineage.get(str(row["lineage"]), 0) + 1
    LINEAGE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF11 Feature Lineage Audit",
                "",
                f"Generated: `{date.today().isoformat()}`.",
                "",
                _markdown_table(["Lineage", "Field declarations"], [[name, count] for name, count in sorted(by_lineage.items())]),
                "",
                "Status: `PASS`.",
                "",
                "Runtime observations, experiment/task metadata, and post-hoc labels have explicit lineage. Label rows are stored in a separate outcome artifact and are never merged into the decision trace. Full/future path suffixes, teacher fields, and post-hoc success fields are recursively rejected.",
                "",
                "`short_history` is bounded to at most eight already-visited nodes. It cannot contain a future route suffix.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    SOURCE_IDENTITY_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF11 Source and Runtime Identity Audit",
                "",
                f"Generated: `{date.today().isoformat()}`.",
                "",
                _markdown_table(
                    ["Metric", "Value"],
                    [
                        ["Processed source segments", source_identity["processed_segment_count"]],
                        ["Unique original task IDs", source_identity["unique_original_task_id_count"]],
                        ["Original task IDs shared by multiple segments", source_identity["repeated_original_task_id_count"]],
                        ["Extra segments sharing an original task ID", source_identity["extra_segments_sharing_original_task_id"]],
                        ["Maximum segments per original task ID", source_identity["max_segments_per_original_task_id"]],
                        ["Observed runtime identities", runtime_identity["runtime_identity_count"]],
                        ["Observed original segment identities", runtime_identity["original_segment_identity_count"]],
                        ["Runtime identity aliases", runtime_identity["runtime_identity_alias_count"]],
                    ],
                ),
                "",
                "Status: `PASS`.",
                "",
                "Original `task_id` values are preserved exactly and are never rewritten to hide repeated IDs. "
                "The event runtime uses `metadata.runtime_bag_id` as an internal identity scoped to one run; "
                "the audit rejects either one internal ID aliasing two original `(task_id, segment_id)` pairs "
                "or one original segment changing internal IDs.",
                "",
                "The source counts cover the complete input task file. Runtime identity counts cover every "
                "committed decision present in the validated trace shards; trace shard completeness is reported "
                "separately and cannot be inferred from this PASS.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    artifacts = {
        "schema": _artifact_entry(TRACE_SCHEMA),
        "trace_sample": _artifact_entry(TRACE_SAMPLE, runtime_sample_count),
        "outcome_sample": _artifact_entry(OUTCOME_SAMPLE, outcome_sample_count),
        "hard_case_index": _artifact_entry(HARD_CASE_INDEX, len(sample.rows)),
        "sampling_balance": _artifact_entry(SAMPLING_BALANCE, len(sample.balance_rows)),
        "sampling_report": _artifact_entry(SAMPLING_REPORT),
        "feature_lineage_table": _artifact_entry(LINEAGE_TABLE, len(lineage)),
        "feature_lineage_report": _artifact_entry(LINEAGE_REPORT),
        "source_release_mapping": _artifact_entry(SOURCE_RELEASE_TABLE, len(source_links)),
        "source_identity_table": _artifact_entry(SOURCE_IDENTITY_TABLE, 1),
        "source_identity_report": _artifact_entry(SOURCE_IDENTITY_REPORT),
    }
    manifest = {
        "schema_id": SCHEMA_ID,
        "artifact_hash_semantics": "sha256 of UTF-8 text after CRLF/CR newline normalization to LF",
        "generated_date": date.today().isoformat(),
        "trace_shards": trace_shards,
        "source_task": {
            "path": _relative(task_path),
            "sha256": _sha256(task_path),
            "task_segment_count": len(source_mappings),
            "identity_audit": source_identity,
        },
        "graph": {"path": _relative(map_path), "sha256": _sha256(map_path)},
        "outcome_source": (
            {"path": _relative(outcome_path), "sha256": _sha256(outcome_path), "row_count": len(outcomes)}
            if outcome_path
            else None
        ),
        "validation": {
            "status": "PASS",
            "decision_count": len(decisions),
            "candidate_graph_membership": "PASS",
            "candidate_equals_true_outgoing_set": "PASS",
            "selected_in_candidates": "PASS",
            "model_fallback_disagreement_action_semantics": "PASS",
            "model_score_semantics": "PASS",
            "model_prediction_min_cost": "PASS",
            "model_margin_second_min_minus_min": "PASS",
            "model_margin_finite_non_null": "PASS",
            "candidate_order_reproducible": "PASS",
            "future_route_suffix_absent": "PASS",
            "runtime_full_astar_zero": "PASS",
            "source_release_mapping_complete": "PASS",
            "source_original_identity_preserved": "PASS",
            "runtime_bag_identity": runtime_identity,
            "feature_lineage": "PASS",
        },
        "trace_completeness": trace_completeness,
        "coverage": {
            "status": coverage_status,
            "high_flow_covered": high_flow_covered,
            "fault_covered": fault_covered,
            "fault_coverage_requirement": "at_least_one_fault_local_active_committed_decision",
            "fault_local_active_decision_count_before_dedupe": int(
                dimension_counts["fault"].get("fault_local_active", 0)
            ),
            "tail_covered": tail_covered,
            "dimension_counts_before_dedupe": dimension_counts,
            "blockers": [
                name
                for name, covered in (
                    ("missing_high_flow_decisions", high_flow_covered),
                    ("missing_fault_decisions", fault_covered),
                    ("missing_p95_p99_or_failed_tail_labels", tail_covered),
                )
                if not covered
            ] + list(trace_completeness["blockers"]),
        },
        "sampling": stats,
        "model_score_semantics": MODEL_SCORE_SEMANTICS,
        "sampling_minimum_quota_status": minimum_status,
        "artifacts": artifacts,
        "claim_boundary": (
            "Decision-level data infrastructure only. This manifest does not promote v3 training, capacity, "
            "fault recovery, paper-full runtime, or G4J."
        ),
    }
    TRACE_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["manifest"] = _artifact_entry(TRACE_MANIFEST)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate G4IRSF11 decision traces and build a deterministic stratified hard-case sample."
    )
    parser.add_argument("--trace", type=Path, action="append", required=True, help="Decision trace JSON/JSONL; repeat for shards")
    parser.add_argument("--tasks", type=Path, required=True, help="Source-release task JSONL")
    parser.add_argument("--map", dest="map_path", type=Path, default=ROOT / "data" / "processed" / "maps" / "map2.json")
    parser.add_argument("--outcomes", type=Path, help="Separate post-hoc decision outcome JSONL")
    parser.add_argument("--scenario", default="g4irsf11_event_runtime")
    parser.add_argument("--scale", default="1x")
    parser.add_argument("--fault-mode", default="no_fault")
    parser.add_argument("--limit", type=int, default=50_000)
    parser.add_argument("--minimum-per-stratum", type=int, default=1)
    parser.add_argument("--maximum-per-stratum", type=int, default=64)
    parser.add_argument("--seed", default="czr005-g4irsf11-stratified-reservoir-v1")
    parser.add_argument("--include-routine", action="store_true", help="Include non-hard decisions in a routine stratum")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = write_artifacts(
        trace_paths=[path.resolve() for path in args.trace],
        task_path=args.tasks.resolve(),
        map_path=args.map_path.resolve(),
        outcome_path=args.outcomes.resolve() if args.outcomes else None,
        scenario=args.scenario,
        scale=args.scale,
        fault_mode=args.fault_mode,
        config=SamplingConfig(
            limit=args.limit,
            minimum_per_stratum=args.minimum_per_stratum,
            maximum_per_stratum=args.maximum_per_stratum,
            seed=args.seed,
        ),
        include_routine=args.include_routine,
    )
    print(
        "g4irsf11 decision data",
        f"validated={manifest['validation']['decision_count']}",
        f"sampled={manifest['sampling']['sample_count']}",
        f"strata={manifest['sampling']['stratum_count']}",
        f"quota_status={manifest['sampling_minimum_quota_status']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the compact, publication-facing G4IRSF24 tables and reports.

Fresh HCA and native-race inputs are required.  DLP collection, screening,
closed-loop, and scale inputs are optional: absent measurements are emitted as
``NOT_MEASURED`` instead of being guessed.  This script only summarizes saved
results; it never runs a planner or native experiment.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
NOT_MEASURED = "NOT_MEASURED"
PROTOCOL_ID = "G4IRSF24_EXACT_HCA_RELEASE_1X_NO_FAULT"

DEFAULT_WORK = ROOT / "build" / "g4irsf24_dlp_campaign"
DEFAULT_HCA = ROOT / "build" / "g4irsf24_fresh_hca_full" / "fresh_hca_summary.json"
DEFAULT_NATIVE = ROOT / "outputs" / "tables" / "g4irsf24_native_fresh_race.json"
DEFAULT_SCREEN = ROOT / "outputs" / "tables" / "g4irsf24_dlp_screen.json"
DEFAULT_LADDER = ROOT / "outputs" / "tables" / "g4irsf24_dlp_native_ladder.json"
DEFAULT_SCALE = ROOT / "outputs" / "tables" / "g4irsf24_dlp_4x_abba.json"
DEFAULT_GITHUB_STATUS = ROOT / "outputs" / "tables" / "g4irsf24_github_baseline.json"
DEFAULT_CORRIDOR_CAMPAIGN = ROOT / "outputs" / "tables" / "g4irsf24_reconvergent_corridor.json"
CORRIDOR_SCHEMA = "czr005.g4irsf24.reconvergent_corridor.v1"
CORRIDOR_CAMPAIGN_SCHEMA = "czr005.g4irsf24.reconvergent_corridor_campaign.v1"
DLP_ARTIFACT_SCHEMA = "czr005.g4irsf24.dlp.v1"
LADDER_NO_GO_STATUSES = {"NO_GO_KEEP_S4", "DLP_LADDER_NO_GO_KEEP_S4"}

TABLES = {
    "fresh": ROOT / "outputs/tables/g4irsf24_fresh_hca_race.csv",
    "transition": ROOT / "outputs/tables/g4irsf24_transition_summary.csv",
    "ablation": ROOT / "outputs/tables/g4irsf24_dlp_ablation.csv",
    "closed": ROOT / "outputs/tables/g4irsf24_closed_loop.csv",
    "scale": ROOT / "outputs/tables/g4irsf24_scale.csv",
    "decision": ROOT / "outputs/tables/g4irsf24_decision_summary.json",
}
REPORTS = {
    "fresh": ROOT / "outputs/reports/g4irsf24_fresh_hca_race.md",
    "transition": ROOT / "outputs/reports/g4irsf24_dense_transition_data.md",
    "ewma": ROOT / "outputs/reports/g4irsf24_dlp_ewma.md",
    "td": ROOT / "outputs/reports/g4irsf24_dlp_td.md",
    "closed": ROOT / "outputs/reports/g4irsf24_native_closed_loop.md",
    "reconvergent": ROOT / "outputs/reports/g4irsf24_reconvergent_corridor.md",
    "scale": ROOT / "outputs/reports/g4irsf24_scale.md",
    "causal": ROOT / "outputs/reports/g4irsf24_causal_explanation.md",
    "final": ROOT / "outputs/reports/g4irsf24_final_joint_decision.md",
}
NEW_IDEAS = ROOT / "docs/g4irsf24_new_ideas.md"
TRANSITION_EVIDENCE = ROOT / "artifacts/datasets/g4irsf24_transition_compact.jsonl"
RELEASE_EVIDENCE = ROOT / "artifacts/datasets/g4irsf24_release_compact.csv"
POLICY_EVIDENCE = {
    "ewma": ROOT / "artifacts/policies/g4irsf24_dlp_ewma.json",
    "td": ROOT / "artifacts/policies/g4irsf24_dlp_td.json",
    "corridor": ROOT / "artifacts/policies/g4irsf24_dlp_corridor.json",
}

DECISION_QUESTIONS = [
    "PR #8 与 Run #71 是否保持绿色？",
    "原始 Java HCA* 实际入口在哪里？",
    "fresh HCA* 是否完整运行？",
    "HCA* 是否与 S4 使用完全相同任务？",
    "三种起算口径是否由同一 parser 输出？",
    "fresh HCA* processed-attempt min/mean/max 以及额外 p95/p99 是多少？",
    "fresh S4 processed-attempt min/mean/max 以及额外 p95/p99 是多少？",
    "当前框架是否已经严格超过 HCA*？",
    "超过多少秒、多少百分比？",
    "是否达到 paper mean 3.96 min？",
    "是否达到 paper min/mean/max range win？",
    "HCA* 与 S4 的 wall/CPU/RSS 分别是多少？",
    "HCA* 在 2×/4× 是否还能完成规划？",
    "dense transition 有多少条？",
    "覆盖多少 edge/node/goal？",
    "train/validation/test 如何按时间隔离？",
    "P1 学到的 edge delay 与静态时间差多少？",
    "P1 改变多少真实动作？",
    "P1 的 1×/2× 业务收益多少？",
    "P2 的 TD value 是否收敛稳定？",
    "P2 的支持度覆盖多少决策？",
    "P2 改变多少真实动作？",
    "fallback 到 S4 的比例是多少？",
    "哪些物理分支贡献最大？",
    "是否出现绕路或循环？",
    "detour guard 拦截多少？",
    "1× mean/p95/p99 如何？",
    "2× mean/p95/p99 如何？",
    "source wait 与 network time 如何变化？",
    "相对 S4-v2 gap 关闭多少？",
    "4× 60s completed/progress/backlog 如何？",
    "是否解锁 180s/full？",
    "DLP 的每动作 CPU 成本多少？",
    "是否仍为 O(out-degree)？",
    "是否读取任何非相邻状态？",
    "64–128 个 changed actions 的 H_system 是否支持闭环收益？",
    "DLP no-go 时，reconvergent corridor 是否有收益？",
    "fault 下是否保持安全？",
    "最终 active candidate 是什么？",
    "下一阶段最窄、最有价值的问题是什么？",
]

FRESH_FIELDS = [
    "protocol_id",
    "arm",
    "repeat",
    "denominator",
    "status",
    "segment_count",
    "raw_bag_count",
    "completed_segments",
    "completed_raw_bags",
    "failed_segments",
    "comparison_eligible",
    "safety_pass",
    "min_s",
    "p50_s",
    "mean_s",
    "p95_s",
    "p99_s",
    "max_s",
    "mean_improvement_vs_hca_pct",
    "p95_improvement_vs_hca_pct",
    "p99_improvement_vs_hca_pct",
    "max_improvement_vs_hca_pct",
    "source_wait_mean_s",
    "network_time_mean_s",
    "deadline_miss_count",
    "release_protocol",
    "release_trace",
    "end_to_end_wall_s",
    "core_wall_s",
    "cpu_s",
    "event_count",
    "decision_count",
    "centralized_full_route",
    "runtime_astar",
    "global_reservation",
    "learning",
    "resource_semantics",
    "scorer",
    "pibt",
    "event_semantics",
    "merge_timing",
    "hotpath",
]


class ReportingError(RuntimeError):
    """Raised for a missing required result or an unsupported required schema."""


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def _display(path: Path | str | None) -> str:
    if path is None:
        return NOT_MEASURED
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return str(candidate)


def _read_required(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReportingError(f"required input is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReportingError(f"required input is not a JSON object: {path}")
    return value


def _read_optional(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReportingError(f"optional input is not a JSON object: {path}")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _number(value: Any) -> float | str:
    if isinstance(value, bool):
        return NOT_MEASURED
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return NOT_MEASURED
    return result if math.isfinite(result) else NOT_MEASURED


def _integer(value: Any) -> int | str:
    number = _number(value)
    return int(number) if isinstance(number, float) else NOT_MEASURED


def _bool(value: Any) -> bool | str:
    return value if isinstance(value, bool) else NOT_MEASURED


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return str(value if value not in (None, "") else NOT_MEASURED)


def _md_table(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[tuple[str, str, int | None]]
) -> str:
    def cell(value: Any, digits: int | None) -> str:
        return _fmt(value, 3 if digits is None else digits).replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(label for label, _key, _digits in columns) + " |"
    rule = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append(
            "| "
            + " | ".join(
                cell(row.get(key, NOT_MEASURED), digits)
                for _label, key, digits in columns
            )
            + " |"
        )
    return "\n".join([header, rule, *body])


def _numeric_values(rows: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)]


def _fresh_run(
    rows: Sequence[Mapping[str, Any]], arm: str, *, repeat: int = 1
) -> Mapping[str, Any] | None:
    return next(
        (
            row
            for row in rows
            if row.get("arm") == arm
            and row.get("denominator") == "processed_attempt"
            and row.get("repeat") == repeat
        ),
        None,
    )


def _candidate_modes(state: Mapping[str, Any] | None) -> dict[str, str]:
    return {
        str(row.get("id")): str(row.get("mode"))
        for row in _rows(state.get("candidates"))
    } if state else {}


def _is_ladder_no_go(status: Any) -> bool:
    return isinstance(status, str) and status in LADDER_NO_GO_STATUSES


def _arm_contract(arm: str) -> dict[str, str]:
    if arm == "HCA":
        return {
            "centralized_full_route": "yes",
            "runtime_astar": "yes",
            "global_reservation": "yes",
            "learning": "no",
        }
    if arm == "F2":
        return {
            "centralized_full_route": "no",
            "runtime_astar": "no",
            "global_reservation": "no",
            "learning": "frozen_local_adapter",
        }
    return {
        "centralized_full_route": "no",
        "runtime_astar": "no",
        "global_reservation": "no",
        "learning": "no",
    }


def _fresh_rows(hca: Mapping[str, Any], native: Mapping[str, Any]) -> list[dict[str, Any]]:
    protocol = _mapping(native.get("protocol"))
    release = _mapping(protocol.get("release_alignment"))
    aligned_count = _integer(release.get("aligned_segment_count"))
    protocol_segment_count = _integer(protocol.get("segment_count"))
    release_protocol = (
        "exact_hca_release_epoch"
        if isinstance(aligned_count, int)
        and isinstance(protocol_segment_count, int)
        and aligned_count == protocol_segment_count
        else NOT_MEASURED
    )
    release_trace = "artifacts/datasets/g4irsf24_release_compact.csv"
    result: list[dict[str, Any]] = []

    for index, run in enumerate(_rows(hca.get("runs")), start=1):
        denominators = _mapping(run.get("denominators"))
        components = _mapping(run.get("components"))
        source_wait = _mapping(_mapping(components.get("source_wait")).get("seconds"))
        network = _mapping(_mapping(components.get("network_time")).get("seconds"))
        completed = _integer(run.get("completed_segment_count"))
        released = _integer(run.get("released_segment_count"))
        failed = released - completed if isinstance(released, int) and isinstance(completed, int) else NOT_MEASURED
        for denominator in ("processed_attempt", "java_release", "raw_entry"):
            seconds = _mapping(_mapping(denominators.get(denominator)).get("seconds"))
            result.append(
                {
                    "protocol_id": PROTOCOL_ID,
                    "arm": "HCA",
                    "repeat": index,
                    "denominator": denominator,
                    "status": run.get("status", NOT_MEASURED),
                    "segment_count": released,
                    "raw_bag_count": _integer(run.get("released_raw_bag_count")),
                    "completed_segments": completed,
                    "completed_raw_bags": _integer(run.get("complete_raw_bag_count")),
                    "failed_segments": failed,
                    "comparison_eligible": _bool(run.get("comparison_eligible")),
                    # The legacy export proves drainage and reservation-based
                    # planning, but it does not expose a collision counter.
                    "safety_pass": NOT_MEASURED,
                    "min_s": _number(seconds.get("min")),
                    "p50_s": _number(seconds.get("p50")),
                    "mean_s": _number(seconds.get("mean")),
                    "p95_s": _number(seconds.get("p95")),
                    "p99_s": _number(seconds.get("p99")),
                    "max_s": _number(seconds.get("max")),
                    "source_wait_mean_s": _number(source_wait.get("mean")),
                    "network_time_mean_s": _number(network.get("mean")),
                    "deadline_miss_count": NOT_MEASURED,
                    "release_protocol": release_protocol,
                    "release_trace": release_trace,
                    "end_to_end_wall_s": _number(run.get("wall_seconds")),
                    "core_wall_s": NOT_MEASURED,
                    "cpu_s": NOT_MEASURED,
                    "event_count": NOT_MEASURED,
                    "decision_count": NOT_MEASURED,
                    "resource_semantics": "legacy_java_hca_global_reservation",
                    "scorer": "HCA_star",
                    "pibt": "no",
                    "event_semantics": "legacy_integer_epoch",
                    "merge_timing": NOT_MEASURED,
                    "hotpath": "no",
                    **_arm_contract("HCA"),
                }
            )

    native_denominators = {
        "processed_attempt": "processed_attempt",
        "java_release": "java_release",
        "original_entry": "raw_entry",
    }
    for run in _rows(native.get("runs")):
        arm = str(run.get("arm", NOT_MEASURED))
        timing = _mapping(run.get("timing"))
        runtime = _mapping(run.get("runtime"))
        safety = _mapping(run.get("safety"))
        runtime_tuple = _mapping(run.get("runtime_tuple"))
        java_mean = _number(_mapping(timing.get("java_release")).get("mean_seconds"))
        processed_mean = _number(_mapping(timing.get("processed_attempt")).get("mean_seconds"))
        source_wait_mean = (
            java_mean - processed_mean
            if isinstance(java_mean, float) and isinstance(processed_mean, float)
            else NOT_MEASURED
        )
        segments = _integer(run.get("segments"))
        bags = _integer(run.get("raw_bags"))
        safety_pass = _bool(safety.get("pass"))
        for native_name, common_name in native_denominators.items():
            values = _mapping(timing.get(native_name))
            result.append(
                {
                    "protocol_id": PROTOCOL_ID,
                    "arm": arm,
                    "repeat": _integer(run.get("repeat")) + 1 if isinstance(_integer(run.get("repeat")), int) else NOT_MEASURED,
                    "denominator": common_name,
                    "status": run.get("status", NOT_MEASURED),
                    "segment_count": segments,
                    "raw_bag_count": bags,
                    "completed_segments": segments if safety_pass is True else NOT_MEASURED,
                    "completed_raw_bags": bags if safety_pass is True else NOT_MEASURED,
                    "failed_segments": 0 if safety_pass is True else NOT_MEASURED,
                    "comparison_eligible": safety_pass,
                    "safety_pass": safety_pass,
                    "min_s": _number(values.get("min_seconds")),
                    "p50_s": _number(values.get("median_seconds")),
                    "mean_s": _number(values.get("mean_seconds")),
                    "p95_s": _number(values.get("p95_seconds")),
                    "p99_s": _number(values.get("p99_seconds")),
                    "max_s": _number(values.get("max_seconds")),
                    "source_wait_mean_s": source_wait_mean,
                    "network_time_mean_s": processed_mean,
                    "deadline_miss_count": NOT_MEASURED,
                    "release_protocol": release_protocol,
                    "release_trace": release_trace,
                    "end_to_end_wall_s": NOT_MEASURED,
                    "core_wall_s": _number(runtime.get("wall_seconds")),
                    "cpu_s": _number(runtime.get("cpu_seconds")),
                    "event_count": _integer(runtime.get("event_count")),
                    "decision_count": _integer(runtime.get("decision_count")),
                    "resource_semantics": runtime_tuple.get("resource_semantics", NOT_MEASURED),
                    "scorer": runtime_tuple.get("scorer", NOT_MEASURED),
                    "pibt": runtime_tuple.get("pibt", NOT_MEASURED),
                    "event_semantics": runtime_tuple.get("event_semantics") or NOT_MEASURED,
                    "merge_timing": runtime_tuple.get("merge_timing") or NOT_MEASURED,
                    "hotpath": runtime_tuple.get("hotpath", NOT_MEASURED),
                    **_arm_contract(arm),
                }
            )

    hca_reference: dict[str, dict[str, float]] = {}
    for denominator in ("processed_attempt", "java_release", "raw_entry"):
        rows = [row for row in result if row["arm"] == "HCA" and row["denominator"] == denominator]
        hca_reference[denominator] = {
            field: statistics.fmean(float(row[field]) for row in rows)
            for field in ("mean_s", "p95_s", "p99_s", "max_s")
            if rows and all(isinstance(row[field], float) for row in rows)
        }
    for row in result:
        reference = hca_reference.get(str(row["denominator"]), {})
        for field, output in (
            ("mean_s", "mean_improvement_vs_hca_pct"),
            ("p95_s", "p95_improvement_vs_hca_pct"),
            ("p99_s", "p99_improvement_vs_hca_pct"),
            ("max_s", "max_improvement_vs_hca_pct"),
        ):
            before = reference.get(field)
            after = row.get(field)
            row[output] = (
                100.0 * (before - float(after)) / before
                if before is not None and before > 0.0 and isinstance(after, float)
                else NOT_MEASURED
            )
    return result


def _fresh_decision(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_arm = {
        arm: {
            _integer(row.get("repeat")): row
            for row in rows
            if row.get("arm") == arm
            and row.get("denominator") == "processed_attempt"
            and isinstance(_integer(row.get("repeat")), int)
        }
        for arm in ("HCA", "S4")
    }
    repeats = sorted(set(by_arm["HCA"]) & set(by_arm["S4"]))
    required = ("mean_s", "p95_s", "p99_s", "max_s")
    if (
        not repeats
        or set(by_arm["HCA"]) != set(by_arm["S4"])
        or not all(
            isinstance(by_arm[arm][repeat].get(name), float)
            for arm in ("HCA", "S4")
            for repeat in repeats
            for name in required
        )
    ):
        return {"status": NOT_MEASURED}
    aggregate = {
        arm: {
            name: statistics.fmean(
                float(by_arm[arm][repeat][name]) for repeat in repeats
            )
            for name in required
        }
        for arm in ("HCA", "S4")
    }
    hca, s4 = aggregate["HCA"], aggregate["S4"]
    repeat_checks = []
    for repeat in repeats:
        hca_row, s4_row = by_arm["HCA"][repeat], by_arm["S4"][repeat]
        complete = (
            s4_row.get("completed_segments") == hca_row.get("completed_segments")
            and s4_row.get("completed_raw_bags") == hca_row.get("completed_raw_bags")
        )
        repeat_checks.append(
            {
                "repeat": repeat,
                "completion_match": complete,
                "s4_safety_pass": s4_row.get("safety_pass") is True,
                "mean_win": float(s4_row["mean_s"]) < float(hca_row["mean_s"]),
                "p95_nonregression": float(s4_row["p95_s"]) <= float(hca_row["p95_s"]),
            }
        )
    strict = all(all(value is True for key, value in check.items() if key != "repeat") for check in repeat_checks)
    repeat_metric_consistent = all(
        math.isclose(
            float(by_arm[arm][repeat][name]),
            float(by_arm[arm][repeats[0]][name]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
        for arm in ("HCA", "S4")
        for repeat in repeats
        for name in required
    )
    mean_gain = 100.0 * (hca["mean_s"] - s4["mean_s"]) / hca["mean_s"]
    return {
        "status": "FRESH_HCA_CLEAR_WIN" if strict and mean_gain >= 5.0 else "FRESH_HCA_STRICT_WIN" if strict else "FRESH_HCA_NOT_BEATEN",
        "FRESH_HCA_STRICT_WIN": strict,
        "FRESH_HCA_CLEAR_WIN": strict and mean_gain >= 5.0,
        "PAPER_TABLE_MEAN_WIN": s4["mean_s"] / 60.0 < 3.96,
        "PAPER_TABLE_RANGE_WIN": s4["mean_s"] / 60.0 < 3.96 and s4["max_s"] / 60.0 <= 5.98,
        "processed_mean_improvement_pct": mean_gain,
        "processed_p95_improvement_pct": 100.0 * (hca["p95_s"] - s4["p95_s"]) / hca["p95_s"],
        "processed_p99_improvement_pct": 100.0 * (hca["p99_s"] - s4["p99_s"]) / hca["p99_s"],
        "processed_max_improvement_pct": 100.0 * (hca["max_s"] - s4["max_s"]) / hca["max_s"],
        "hca_processed_mean_s": hca["mean_s"],
        "s4_processed_mean_s": s4["mean_s"],
        "hca_processed_max_s": hca["max_s"],
        "s4_processed_max_s": s4["max_s"],
        "repeat_count": len(repeats),
        "repeat_metric_consistent": repeat_metric_consistent,
        "repeat_checks": repeat_checks,
        "completion_nonregression_all_repeats": all(check["completion_match"] for check in repeat_checks),
        "s4_safety_pass_all_repeats": all(check["s4_safety_pass"] for check in repeat_checks),
    }


TRANSITION_FIELDS = [
    "section", "item", "scale", "repeat", "status", "transition_count",
    "train_count", "validation_count", "test_count", "stored_decisions",
    "completed_segments", "trace_complete", "safety_pass", "mode", "coverage",
    "mae_s", "static_mae_s", "runtime_lookup_coverage",
    "td_bellman_coverage", "td_bellman_mae_s", "td_zero_value_mae_s",
    "test_runtime_lookup_coverage", "test_mae_s", "test_static_mae_s",
    "test_td_bellman_coverage", "test_td_bellman_mae_s", "test_td_zero_value_mae_s",
    "edge_residual_count", "value_residual_count",
]


def _transition_rows(state: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if state is None:
        return [{"section": "campaign", "item": "dense_transition", "status": NOT_MEASURED}]
    split = _mapping(state.get("split_counts"))
    result = [
        {
            "section": "campaign",
            "item": "all",
            "status": state.get("stage", NOT_MEASURED),
            "transition_count": _integer(state.get("transition_count")),
            "train_count": _integer(split.get("train")),
            "validation_count": _integer(split.get("validation")),
            "test_count": _integer(split.get("test")),
        }
    ]
    for source in _rows(state.get("sources")):
        safety = _mapping(source.get("safety"))
        result.append(
            {
                "section": "source",
                "item": f"{source.get('scale', NOT_MEASURED)}x_r{source.get('repeat', NOT_MEASURED)}",
                "scale": source.get("scale", NOT_MEASURED),
                "repeat": source.get("repeat", NOT_MEASURED),
                "status": "PASS" if source.get("trace_complete") is True and safety.get("pass") is True else "FAIL",
                "transition_count": _integer(source.get("transition_count")),
                "stored_decisions": _integer(source.get("stored_decisions")),
                "completed_segments": _integer(source.get("completed_segments")),
                "trace_complete": _bool(source.get("trace_complete")),
                "safety_pass": _bool(safety.get("pass")),
            }
        )
    candidates = {str(row.get("id")): row for row in _rows(state.get("candidates"))}
    held_out = {
        str(row.get("candidate_id")): row for row in _rows(state.get("offline_test"))
    }
    for validation in _rows(state.get("offline_validation")):
        candidate_id = str(validation.get("candidate_id", NOT_MEASURED))
        candidate = _mapping(candidates.get(candidate_id))
        test = _mapping(held_out.get(candidate_id))
        result.append(
            {
                "section": "candidate",
                "item": candidate_id,
                "status": "MEASURED",
                "mode": validation.get("mode", candidate.get("mode", NOT_MEASURED)),
                "coverage": _number(validation.get("coverage")),
                "runtime_lookup_coverage": _number(validation.get("runtime_lookup_coverage")),
                "mae_s": _number(validation.get("mae_seconds_with_s4_fallback")),
                "static_mae_s": _number(validation.get("static_zero_residual_mae_seconds")),
                "td_bellman_coverage": _number(validation.get("td_bellman_coverage")),
                "td_bellman_mae_s": _number(validation.get("td_bellman_mae_seconds")),
                "td_zero_value_mae_s": _number(validation.get("td_zero_value_mae_seconds")),
                "test_runtime_lookup_coverage": _number(test.get("runtime_lookup_coverage")),
                "test_mae_s": _number(test.get("mae_seconds_with_s4_fallback")),
                "test_static_mae_s": _number(test.get("static_zero_residual_mae_seconds")),
                "test_td_bellman_coverage": _number(test.get("td_bellman_coverage")),
                "test_td_bellman_mae_s": _number(test.get("td_bellman_mae_seconds")),
                "test_td_zero_value_mae_s": _number(test.get("td_zero_value_mae_seconds")),
                "edge_residual_count": _integer(candidate.get("edge_residual_count")),
                "value_residual_count": _integer(candidate.get("value_residual_count")),
            }
        )
    return result


ABLATION_FIELDS = [
    "candidate_id", "mode", "alpha", "beta", "min_support", "margin_s",
    "detour_allowance_s", "edge_residual_count", "value_residual_count",
    "offline_coverage", "offline_mae_s", "static_mae_s",
    "runtime_lookup_coverage", "td_bellman_coverage", "td_bellman_mae_s",
    "td_zero_value_mae_s",
    "test_runtime_lookup_coverage", "test_mae_s", "test_static_mae_s",
    "test_td_bellman_coverage", "test_td_bellman_mae_s", "test_td_zero_value_mae_s",
    "screen_mean_relative_delta", "screen_committed_mutations", "screen_safety_pass",
    "screen_selected", "status",
]


def _ablation_rows(
    state: Mapping[str, Any] | None, screen: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    if state is None:
        return [{"candidate_id": NOT_MEASURED, "status": NOT_MEASURED}]
    offline = {
        str(row.get("candidate_id")): row for row in _rows(state.get("offline_validation"))
    }
    held_out = {
        str(row.get("candidate_id")): row for row in _rows(state.get("offline_test"))
    }
    ranking = {
        str(row.get("candidate_id")): row for row in _rows(screen.get("ranking"))
    } if screen else {}
    selected = {str(value) for value in screen.get("selected_candidate_ids", [])} if screen else set()
    result = []
    for candidate in _rows(state.get("candidates")):
        candidate_id = str(candidate.get("id", NOT_MEASURED))
        validation = _mapping(offline.get(candidate_id))
        test = _mapping(held_out.get(candidate_id))
        ranked = _mapping(ranking.get(candidate_id))
        native_ran = bool(ranked)
        mutations = _integer(ranked.get("committed_mutation_count"))
        if candidate_id in selected:
            status = "SCREEN_SELECTED"
        elif native_ran and mutations == 0:
            status = "SCREEN_NO_MUTATION"
        elif native_ran:
            status = "SCREEN_REJECTED"
        else:
            status = "OFFLINE_NOT_SELECTED_NATIVE_NOT_RUN"
        result.append(
            {
                "candidate_id": candidate_id,
                "mode": candidate.get("mode", NOT_MEASURED),
                "alpha": _number(candidate.get("alpha")),
                "beta": _number(candidate.get("beta")),
                "min_support": _integer(candidate.get("min_support")),
                "margin_s": _number(candidate.get("margin_seconds")),
                "detour_allowance_s": _number(candidate.get("detour_allowance_seconds")),
                "edge_residual_count": _integer(candidate.get("edge_residual_count")),
                "value_residual_count": _integer(candidate.get("value_residual_count")),
                "offline_coverage": _number(validation.get("coverage")),
                "offline_mae_s": _number(validation.get("mae_seconds_with_s4_fallback")),
                "static_mae_s": _number(validation.get("static_zero_residual_mae_seconds")),
                "runtime_lookup_coverage": _number(validation.get("runtime_lookup_coverage")),
                "td_bellman_coverage": _number(validation.get("td_bellman_coverage")),
                "td_bellman_mae_s": _number(validation.get("td_bellman_mae_seconds")),
                "td_zero_value_mae_s": _number(validation.get("td_zero_value_mae_seconds")),
                "test_runtime_lookup_coverage": _number(test.get("runtime_lookup_coverage")),
                "test_mae_s": _number(test.get("mae_seconds_with_s4_fallback")),
                "test_static_mae_s": _number(test.get("static_zero_residual_mae_seconds")),
                "test_td_bellman_coverage": _number(test.get("td_bellman_coverage")),
                "test_td_bellman_mae_s": _number(test.get("td_bellman_mae_seconds")),
                "test_td_zero_value_mae_s": _number(test.get("td_zero_value_mae_seconds")),
                "screen_mean_relative_delta": _number(ranked.get("mean_relative_delta")),
                "screen_committed_mutations": _integer(ranked.get("committed_mutation_count")),
                "screen_safety_pass": _bool(ranked.get("safety_pass")),
                "screen_selected": candidate_id in selected if native_ran else NOT_MEASURED,
                "status": status,
            }
        )
    return result or [{"candidate_id": NOT_MEASURED, "status": NOT_MEASURED}]


def _screen_action_rows(screen: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for run in _rows(screen.get("runs")) if screen else []:
        candidate_id = str(run.get("candidate_id", NOT_MEASURED))
        if candidate_id == "S4":
            continue
        dlp = _mapping(run.get("dlp"))
        result.append(
            {
                "candidate_id": candidate_id,
                "prefix": _integer(run.get("size", run.get("segments"))),
                "status": run.get("status", NOT_MEASURED),
                "safety": _bool(_mapping(run.get("safety")).get("pass")),
                "route_evaluations": _integer(dlp.get("g4irsf24_dlp_route_evaluation_count")),
                "eligible_candidates": _integer(dlp.get("g4irsf24_dlp_eligible_candidate_count")),
                "supported_candidates": _integer(dlp.get("g4irsf24_dlp_supported_candidate_count")),
                "proposals": _integer(dlp.get("g4irsf24_dlp_proposal_count")),
                "mutations": _integer(dlp.get("g4irsf24_dlp_committed_mutation_count")),
                "fallback_s4": _integer(dlp.get("g4irsf24_dlp_fallback_s4_count")),
                "unsupported": _integer(dlp.get("g4irsf24_dlp_unsupported_fallback_count")),
                "low_support": _integer(dlp.get("g4irsf24_dlp_low_support_fallback_count")),
                "margin": _integer(dlp.get("g4irsf24_dlp_margin_fallback_count")),
                "detour": _integer(dlp.get("g4irsf24_dlp_detour_fallback_count")),
                "shield_fault": _integer(dlp.get("g4irsf24_dlp_shield_fault_fallback_count")),
            }
        )
    return result


CLOSED_FIELDS = [
    "campaign", "margin_s", "strongest_no_go_evidence", "scale", "candidate_id",
    "status", "segments", "raw_bags", "safety_pass",
    "processed_mean_s", "processed_p50_s", "processed_p95_s", "processed_p99_s",
    "processed_max_s", "events_per_completed", "deadline_miss_count",
    "proposals", "committed_mutations", "fallback_s4", "mean_delta_s",
    "p95_delta_s", "p99_delta_s", "max_delta_s",
    "events_relative_increase", "candidate_eligible", "active_policy",
]


def _closed_rows(
    ladder: Mapping[str, Any] | None,
    corridor_campaigns: Sequence[Mapping[str, Any]],
    strongest_corridor_margin: float | str,
) -> list[dict[str, Any]]:
    decisions = {
        str(row.get("candidate_id")): row for row in _rows(ladder.get("decisions"))
    } if ladder else {}
    result = []
    for run in _rows(ladder.get("runs")) if ladder else []:
        scale = _integer(run.get("scale"))
        candidate_id = str(run.get("candidate_id", NOT_MEASURED))
        decision = _mapping(decisions.get(candidate_id))
        index = scale - 1 if isinstance(scale, int) and scale in (1, 2) else None
        timing = _mapping(_mapping(run.get("timing")).get("processed_attempt"))
        dlp = _mapping(run.get("dlp"))

        def indexed(name: str) -> Any:
            values = decision.get(name)
            return values[index] if index is not None and isinstance(values, list) and len(values) > index else NOT_MEASURED

        result.append(
            {
                "campaign": "DLP_LADDER",
                "margin_s": NOT_MEASURED,
                "strongest_no_go_evidence": False,
                "scale": scale,
                "candidate_id": candidate_id,
                "status": run.get("status", NOT_MEASURED),
                "segments": _integer(run.get("segments")),
                "raw_bags": _integer(run.get("raw_bags")),
                "safety_pass": _bool(_mapping(run.get("safety")).get("pass")),
                "processed_mean_s": _number(timing.get("mean_seconds")),
                "processed_p50_s": _number(timing.get("median_seconds")),
                "processed_p95_s": _number(timing.get("p95_seconds")),
                "processed_p99_s": _number(timing.get("p99_seconds")),
                "processed_max_s": _number(timing.get("max_seconds")),
                "events_per_completed": _number(run.get("events_per_completed")),
                "deadline_miss_count": _integer(run.get("deadline_miss_count")),
                "committed_mutations": _integer(dlp.get("g4irsf24_dlp_committed_mutation_count", 0 if candidate_id == "S4" else None)),
                "proposals": _integer(dlp.get("g4irsf24_dlp_proposal_count", 0 if candidate_id == "S4" else None)),
                "fallback_s4": _integer(dlp.get("g4irsf24_dlp_fallback_s4_count", 0 if candidate_id == "S4" else None)),
                "mean_delta_s": _number(indexed("mean_delta_seconds")),
                "p95_delta_s": _number(indexed("p95_delta_seconds")),
                "p99_delta_s": _number(indexed("p99_delta_seconds")),
                "events_relative_increase": _number(indexed("events_per_completed_relative_increase")),
                "candidate_eligible": _bool(decision.get("eligible")),
                "active_policy": ladder.get("active_policy", NOT_MEASURED) if ladder else NOT_MEASURED,
            }
        )
    for campaign in corridor_campaigns:
        if campaign.get("schema") != CORRIDOR_CAMPAIGN_SCHEMA:
            continue
        margin = _number(_mapping(campaign.get("artifact_contract")).get("margin_seconds"))
        comparisons = {
            _integer(row.get("scale")): row for row in _rows(campaign.get("comparisons"))
        }
        campaign_runs = _rows(campaign.get("runs"))
        baseline_by_scale = {
            _integer(run.get("scale")): run
            for run in campaign_runs
            if run.get("arm") == "S4"
        }
        for run in campaign_runs:
            if run.get("arm") != "CORRIDOR":
                continue
            scale_value = _integer(run.get("scale"))
            comparison = _mapping(comparisons.get(scale_value))
            timing = _mapping(_mapping(run.get("timing")).get("processed_attempt"))
            baseline_timing = _mapping(
                _mapping(_mapping(baseline_by_scale.get(scale_value)).get("timing")).get("processed_attempt")
            )
            dlp = _mapping(run.get("dlp"))
            strongest = (
                isinstance(margin, float)
                and isinstance(strongest_corridor_margin, float)
                and math.isclose(margin, strongest_corridor_margin, rel_tol=0.0, abs_tol=1.0e-12)
            )
            result.append(
                {
                    "campaign": "RECONVERGENT_CORRIDOR",
                    "margin_s": margin,
                    "strongest_no_go_evidence": strongest,
                    "scale": scale_value,
                    "candidate_id": f"CORRIDOR_MARGIN_{_fmt(margin, 3)}",
                    "status": campaign.get("status", NOT_MEASURED),
                    "segments": _integer(run.get("segments")),
                    "raw_bags": _integer(run.get("raw_bags")),
                    "safety_pass": _bool(_mapping(run.get("safety")).get("pass")),
                    "processed_mean_s": _number(timing.get("mean_seconds")),
                    "processed_p50_s": _number(timing.get("median_seconds")),
                    "processed_p95_s": _number(timing.get("p95_seconds")),
                    "processed_p99_s": _number(timing.get("p99_seconds")),
                    "processed_max_s": _number(timing.get("max_seconds")),
                    "events_per_completed": _number(run.get("events_per_completed")),
                    "deadline_miss_count": _integer(run.get("deadline_miss_count")),
                    "committed_mutations": _integer(dlp.get("g4irsf24_dlp_committed_mutation_count")),
                    "proposals": _integer(dlp.get("g4irsf24_dlp_proposal_count")),
                    "fallback_s4": _integer(dlp.get("g4irsf24_dlp_fallback_s4_count")),
                    "mean_delta_s": _number(comparison.get("mean_delta_seconds")),
                    "p95_delta_s": _number(comparison.get("p95_delta_seconds")),
                    "p99_delta_s": _number(comparison.get("p99_delta_seconds")),
                    "max_delta_s": (
                        float(timing["max_seconds"]) - float(baseline_timing["max_seconds"])
                        if isinstance(_number(timing.get("max_seconds")), float)
                        and isinstance(_number(baseline_timing.get("max_seconds")), float)
                        else NOT_MEASURED
                    ),
                    "events_relative_increase": _number(comparison.get("events_per_completed_relative_increase")),
                    "candidate_eligible": False,
                    "active_policy": campaign.get("active_policy", "S4"),
                }
            )
    return result or [{
        "status": ladder.get("status", NOT_MEASURED) if ladder else NOT_MEASURED,
        "active_policy": ladder.get("active_policy", "S4") if ladder else "S4",
    }]


SCALE_FIELDS = [
    "ordinal", "arm", "status", "released_bags", "completed_bags", "failed_bags",
    "backlog", "simulated_time_s", "events_per_completed", "events_per_wall_s",
    "core_wall_s", "cpu_s", "committed_mutations", "safety_pass", "run_check_pass",
    "campaign_status", "active_policy",
]


def _scale_rows(scale: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if scale is None:
        return [{"status": NOT_MEASURED, "campaign_status": NOT_MEASURED, "active_policy": "S4"}]
    checks = {int(row.get("ordinal", -1)): row for row in _rows(scale.get("run_checks"))}
    result = []
    for run in _rows(scale.get("runs")):
        ordinal = _integer(run.get("ordinal"))
        progress = _mapping(run.get("progress"))
        metrics = _mapping(run.get("metrics"))
        resources = _mapping(run.get("resources"))
        dlp = _mapping(run.get("dlp"))
        check = _mapping(checks.get(ordinal if isinstance(ordinal, int) else -1))
        result.append(
            {
                "ordinal": ordinal,
                "arm": run.get("arm", NOT_MEASURED),
                "status": run.get("status", NOT_MEASURED),
                "released_bags": _integer(progress.get("released_bags")),
                "completed_bags": _integer(progress.get("completed_bags")),
                "failed_bags": _integer(progress.get("failed_bags")),
                "backlog": _integer(progress.get("current_backlog")),
                "simulated_time_s": _number(progress.get("simulated_time")),
                "events_per_completed": _number(metrics.get("events_per_completed_bag")),
                "events_per_wall_s": _number(metrics.get("events_per_wall_second")),
                "core_wall_s": _number(resources.get("native_wall_seconds")),
                "cpu_s": _number(resources.get("native_process_cpu_seconds")),
                "committed_mutations": _integer(dlp.get("g4irsf24_dlp_committed_mutation_count", 0 if run.get("arm") == "S4" else None)),
                "safety_pass": _bool(_mapping(run.get("hard_safety")).get("pass")),
                "run_check_pass": _bool(check.get("pass")),
                "campaign_status": scale.get("status", NOT_MEASURED),
                "active_policy": scale.get("active_policy", NOT_MEASURED),
            }
        )
    return result or [{"status": scale.get("status", NOT_MEASURED), "campaign_status": scale.get("status", NOT_MEASURED), "active_policy": scale.get("active_policy", "S4")}]


def _release_evidence(source: Path) -> int | str:
    RELEASE_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    fields = ["segment_id", "task_id", "start", "goal", "release_epoch"]
    if source.resolve() == RELEASE_EVIDENCE.resolve():
        if not source.is_file():
            raise ReportingError(f"release evidence is missing: {source}")
        with source.open("r", encoding="utf-8", newline="") as input_handle:
            reader = csv.DictReader(input_handle)
            if reader.fieldnames != fields:
                raise ReportingError(
                    f"release evidence fields mismatch: expected {fields}, got {reader.fieldnames}"
                )
            segment_ids: set[str] = set()
            count = 0
            for row_number, row in enumerate(reader, start=2):
                for field in fields:
                    if not str(row.get(field) or "").strip():
                        raise ReportingError(
                            f"release evidence field {field!r} is empty at row {row_number}"
                        )
                segment_id = str(row["segment_id"]).strip()
                if segment_id in segment_ids:
                    raise ReportingError(
                        f"release evidence has duplicate segment_id {segment_id!r}"
                    )
                segment_ids.add(segment_id)
                count += 1
        if count == 0:
            raise ReportingError("release evidence has no data rows")
        return count
    if not source.is_file():
        _write_csv(RELEASE_EVIDENCE, fields, [{"segment_id": NOT_MEASURED}])
        return NOT_MEASURED
    with source.open("r", encoding="utf-8", newline="") as input_handle, RELEASE_EVIDENCE.open(
        "w", encoding="utf-8", newline=""
    ) as output_handle:
        reader = csv.DictReader(input_handle)
        writer = csv.DictWriter(output_handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        count = 0
        for row in reader:
            writer.writerow(row)
            count += 1
    return count


def _transition_evidence(state: Mapping[str, Any] | None) -> dict[str, Any]:
    TRANSITION_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    source_value = state.get("transition_path") if state else None
    if not isinstance(source_value, str):
        TRANSITION_EVIDENCE.write_text(
            json.dumps({"schema": "czr005.g4irsf24.transition_compact.v1", "status": NOT_MEASURED}) + "\n",
            encoding="utf-8",
        )
        return {"status": NOT_MEASURED, "compact_group_count": NOT_MEASURED}
    source = _path(Path(source_value))
    if not source.is_file():
        TRANSITION_EVIDENCE.write_text(
            json.dumps({"schema": "czr005.g4irsf24.transition_compact.v1", "status": NOT_MEASURED, "source": _display(source)}) + "\n",
            encoding="utf-8",
        )
        return {
            "status": NOT_MEASURED,
            "compact_group_count": NOT_MEASURED,
            "reason": f"transition source is missing: {_display(source)}",
        }
    groups: dict[tuple[int, int, int], dict[str, float]] = defaultdict(
        lambda: {"count": 0.0, "duration_sum": 0.0, "residual_sum": 0.0, "duration_min": math.inf, "duration_max": -math.inf}
    )
    transition_count = 0
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, Mapping):
                continue
            key = (int(row["current"]), int(row["selected"]), int(row["goal"]))
            duration = float(row["duration"])
            residual = duration - float(row["travel_time"])
            summary = groups[key]
            summary["count"] += 1.0
            summary["duration_sum"] += duration
            summary["residual_sum"] += residual
            summary["duration_min"] = min(summary["duration_min"], duration)
            summary["duration_max"] = max(summary["duration_max"], duration)
            transition_count += 1
    with TRANSITION_EVIDENCE.open("w", encoding="utf-8") as handle:
        for (current, selected, goal), summary in sorted(groups.items()):
            count = int(summary["count"])
            handle.write(
                json.dumps(
                    {
                        "schema": "czr005.g4irsf24.transition_compact.v1",
                        "current": current,
                        "selected": selected,
                        "goal": goal,
                        "support": count,
                        "duration_mean_s": summary["duration_sum"] / count,
                        "duration_min_s": summary["duration_min"],
                        "duration_max_s": summary["duration_max"],
                        "residual_mean_s": summary["residual_sum"] / count,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    edges = {(current, selected) for current, selected, _goal in groups}
    nodes = {node for current, selected, _goal in groups for node in (current, selected)}
    goals = {goal for _current, _selected, goal in groups}
    top_groups = []
    for (current, selected, goal), summary in groups.items():
        support = int(summary["count"])
        residual_mean = summary["residual_sum"] / support
        top_groups.append(
            {
                "current": current,
                "selected": selected,
                "goal": goal,
                "support": support,
                "residual_mean_s": residual_mean,
                "observed_abs_residual_mass_s": abs(summary["residual_sum"]),
            }
        )
    top_groups.sort(
        key=lambda row: (
            -float(row["observed_abs_residual_mass_s"]),
            int(row["current"]),
            int(row["selected"]),
            int(row["goal"]),
        )
    )
    return {
        "status": "MEASURED",
        "transition_count": transition_count,
        "compact_group_count": len(groups),
        "edge_count": len(edges),
        "node_count": len(nodes),
        "goal_count": len(goals),
        # Descriptive residual mass is not a causal contribution estimate.
        "top_observed_residual_groups": top_groups[:5],
    }


def _artifact_summaries(state: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if state is None or not isinstance(state.get("artifacts"), Mapping):
        return {}
    modes = _candidate_modes(state)
    summaries: dict[str, dict[str, Any]] = {}
    for candidate_id, source_value in state["artifacts"].items():
        if not isinstance(source_value, str):
            continue
        source = _path(Path(source_value))
        try:
            artifact = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(artifact, Mapping):
            continue
        edges = _rows(artifact.get("edge_residuals"))
        pairs: list[tuple[float, int]] = []
        for row in edges:
            residual = _number(row.get("residual_seconds"))
            support = _integer(row.get("support"))
            if isinstance(residual, float) and isinstance(support, int) and support > 0:
                pairs.append((residual, support))
        if pairs:
            total_support = sum(support for _residual, support in pairs)
            summaries[str(candidate_id)] = {
                "mode": modes.get(str(candidate_id), artifact.get("mode", NOT_MEASURED)),
                "schema": artifact.get("schema", NOT_MEASURED),
                "edge_residual_count": len(pairs),
                "support": total_support,
                "residual_min_s": min(residual for residual, _support in pairs),
                "residual_mean_s": sum(residual for residual, _support in pairs) / len(pairs),
                "residual_support_weighted_mean_s": (
                    sum(residual * support for residual, support in pairs) / total_support
                ),
                "residual_max_s": max(residual for residual, _support in pairs),
                "path": _display(source),
            }
    return summaries


def _publish_offline_policy_evidence(
    state: Mapping[str, Any] | None,
    corridor_artifact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "evidence_only": True,
        "activation_source": "registered scale/selection result, never these copies",
    }
    modes = _candidate_modes(state)
    artifact_paths = _mapping(state.get("artifacts")) if state else {}
    selected_ids = state.get("native_candidate_ids", []) if state else []
    selected = [str(value) for value in selected_ids] if isinstance(selected_ids, list) else []
    for mode in ("ewma", "td"):
        candidate_id = next((value for value in selected if modes.get(value) == mode), None)
        source_value = artifact_paths.get(candidate_id) if candidate_id else None
        row: dict[str, Any] = {
            "status": NOT_MEASURED,
            "candidate_id": candidate_id or NOT_MEASURED,
            "path": _display(POLICY_EVIDENCE[mode]),
        }
        if isinstance(source_value, str):
            source = _path(Path(source_value))
            try:
                artifact = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                artifact = None
            if isinstance(artifact, Mapping) and artifact.get("schema") == DLP_ARTIFACT_SCHEMA:
                _write_json(POLICY_EVIDENCE[mode], artifact)
                row.update(
                    status="PUBLISHED_EVIDENCE_ONLY",
                    source=_display(POLICY_EVIDENCE[mode]),
                    source_scope="published copy of the local raw experiment artifact",
                )
            else:
                row["reason"] = "selected offline artifact is missing or has an incompatible ABI"
        else:
            row["reason"] = "state has no offline-selected artifact for this family"
        result[mode] = row
    corridor_row: dict[str, Any] = {
        "status": NOT_MEASURED,
        "path": _display(POLICY_EVIDENCE["corridor"]),
    }
    if corridor_artifact is not None:
        if corridor_artifact.get("schema") == DLP_ARTIFACT_SCHEMA:
            _write_json(POLICY_EVIDENCE["corridor"], corridor_artifact)
            corridor_row["status"] = "PUBLISHED_EVIDENCE_ONLY"
        else:
            corridor_row["reason"] = "corridor artifact has an incompatible ABI"
    else:
        corridor_row["reason"] = "no corridor artifact was supplied"
    result["corridor"] = corridor_row
    return result


def _corridor_summary(
    report: Mapping[str, Any] | None,
    artifact: Mapping[str, Any] | None,
    report_path: Path | None,
    artifact_path: Path | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": NOT_MEASURED,
        "closed_loop_benefit_status": NOT_MEASURED,
        "reason": "no reconvergent-corridor diagnostic was supplied",
        "report_path": _display(REPORTS["reconvergent"]),
        "artifact_path": _display(POLICY_EVIDENCE["corridor"]),
        "source_scope": "published summary and evidence-only policy copy; local raw build inputs are not committed",
    }
    if report is not None:
        if report.get("schema") != CORRIDOR_SCHEMA:
            result.update(
                status="UNSUPPORTED_SCHEMA",
                reason=f"expected {CORRIDOR_SCHEMA}; received {report.get('schema', NOT_MEASURED)}",
            )
        else:
            corridors = _rows(report.get("corridors"))
            residual_rows = [
                row for row in corridors if isinstance(_number(row.get("residual_seconds")), float)
            ]
            residuals = [float(row["residual_seconds"]) for row in residual_rows]
            supports = [int(row["support"]) for row in residual_rows if isinstance(_integer(row.get("support")), int)]
            grouped: dict[tuple[int, int], list[float]] = defaultdict(list)
            static_grouped: dict[tuple[int, int], list[float]] = defaultdict(list)
            for row in residual_rows:
                branch, rejoin = _integer(row.get("from")), _integer(row.get("reconvergence"))
                if isinstance(branch, int) and isinstance(rejoin, int):
                    grouped[(branch, rejoin)].append(float(row["residual_seconds"]))
                    static_duration = _number(row.get("static_duration_seconds"))
                    if isinstance(static_duration, float):
                        static_grouped[(branch, rejoin)].append(static_duration)
            spans = [max(values) - min(values) for values in grouped.values() if len(values) >= 2]
            static_spans = [
                max(values) - min(values)
                for values in static_grouped.values()
                if len(values) >= 2
            ]
            result.update(
                status="OFFLINE_DIAGNOSTIC_MEASURED",
                reason="corridors were fitted from chronological training transitions; no closed-loop corridor run is implied",
                schema=report.get("schema"),
                max_hops=_integer(report.get("max_hops")),
                min_support=_integer(report.get("min_support")),
                corridor_count=_integer(report.get("corridor_count")),
                branch_count=len({int(row["from"]) for row in corridors if isinstance(_integer(row.get("from")), int)}),
                reconvergence_count=len({int(row["reconvergence"]) for row in corridors if isinstance(_integer(row.get("reconvergence")), int)}),
                supported_row_count=len(residual_rows),
                support_min=min(supports) if supports else NOT_MEASURED,
                residual_min_s=min(residuals) if residuals else NOT_MEASURED,
                residual_mean_s=statistics.fmean(residuals) if residuals else NOT_MEASURED,
                residual_max_s=max(residuals) if residuals else NOT_MEASURED,
                max_branch_residual_span_s=max(spans) if spans else NOT_MEASURED,
                max_static_arm_gap_s=max(static_spans) if static_spans else NOT_MEASURED,
                corridors=[dict(row) for row in corridors],
            )
    if artifact is not None:
        edges = _rows(artifact.get("edge_residuals"))
        result["artifact_schema"] = artifact.get("schema", NOT_MEASURED)
        result["projected_edge_count"] = len(edges)
        result["artifact_runtime_compatible"] = artifact.get("schema") == DLP_ARTIFACT_SCHEMA
        if report is None:
            result.update(
                status="OFFLINE_ARTIFACT_MEASURED",
                reason="a runtime-compatible corridor projection was supplied without its corridor report; closed-loop benefit is not measured",
            )
    return result


def _corridor_campaign_summary(
    campaigns: Sequence[Mapping[str, Any]], paths: Sequence[Path]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for campaign, path in zip(campaigns, paths):
        if campaign.get("schema") != CORRIDOR_CAMPAIGN_SCHEMA:
            continue
        contract = _mapping(campaign.get("artifact_contract"))
        runs = _rows(campaign.get("runs"))
        run_index = {
            (_integer(run.get("scale")), str(run.get("arm"))): run
            for run in runs
        }
        comparisons = []
        for source in _rows(campaign.get("comparisons")):
            comparison = dict(source)
            scale_value = _integer(source.get("scale"))
            candidate = _mapping(run_index.get((scale_value, "CORRIDOR")))
            baseline = _mapping(run_index.get((scale_value, "S4")))
            candidate_timing = _mapping(_mapping(candidate.get("timing")).get("processed_attempt"))
            baseline_timing = _mapping(_mapping(baseline.get("timing")).get("processed_attempt"))
            dlp = _mapping(candidate.get("dlp"))
            comparison.update(
                proposal_count=_integer(dlp.get("g4irsf24_dlp_proposal_count")),
                fallback_s4_count=_integer(dlp.get("g4irsf24_dlp_fallback_s4_count")),
                max_delta_seconds=(
                    float(candidate_timing["max_seconds"])
                    - float(baseline_timing["max_seconds"])
                    if isinstance(_number(candidate_timing.get("max_seconds")), float)
                    and isinstance(_number(baseline_timing.get("max_seconds")), float)
                    else NOT_MEASURED
                ),
            )
            comparisons.append(comparison)
        rows.append(
            {
                "path": _display(path),
                "status": campaign.get("status", NOT_MEASURED),
                "active_policy": campaign.get("active_policy", NOT_MEASURED),
                "margin_s": _number(contract.get("margin_seconds")),
                "beta": _number(contract.get("beta")),
                "detour_allowance_s": _number(contract.get("detour_allowance_seconds")),
                "comparisons": comparisons,
                "gates": dict(_mapping(campaign.get("gates"))),
                "run_count": len(runs),
            }
        )
    if not rows:
        return {
            "status": NOT_MEASURED,
            "closed_loop_benefit_status": NOT_MEASURED,
            "reason": "no compatible reconvergent-corridor closed-loop campaign was supplied",
        }

    def scale_comparison(row: Mapping[str, Any], scale_value: int) -> Mapping[str, Any]:
        return next(
            (
                item for item in _rows(row.get("comparisons"))
                if _integer(item.get("scale")) == scale_value
            ),
            {},
        )

    no_go = [row for row in rows if "NO_GO" in str(row.get("status"))]
    strongest = max(
        no_go,
        key=lambda row: (
            float(_number(scale_comparison(row, 2).get("mean_improvement_fraction")))
            if isinstance(_number(scale_comparison(row, 2).get("mean_improvement_fraction")), float)
            else -math.inf,
            -float(_number(scale_comparison(row, 2).get("p95_delta_seconds")))
            if isinstance(_number(scale_comparison(row, 2).get("p95_delta_seconds")), float)
            else -math.inf,
            -float(_number(scale_comparison(row, 2).get("p99_delta_seconds")))
            if isinstance(_number(scale_comparison(row, 2).get("p99_delta_seconds")), float)
            else -math.inf,
        ),
    ) if no_go else None
    strongest_evidence = (
        {
            **dict(strongest),
            "designation": "STRONGEST_NO_GO_EVIDENCE",
            "reason": "largest measured 2x processed-attempt mean improvement among supplied no-go margins; the 1x gate still fails",
        }
        if strongest else NOT_MEASURED
    )
    all_no_go = len(no_go) == len(rows)
    return {
        "status": "CLOSED_LOOP_MEASURED_NO_GO" if all_no_go else "CLOSED_LOOP_MEASURED",
        "closed_loop_benefit_status": "MEASURED_NO_GO" if all_no_go else "MEASURED",
        "active_policy": "S4" if all_no_go else rows[0].get("active_policy", NOT_MEASURED),
        "campaign_count": len(rows),
        "campaigns": rows,
        "strongest_no_go_evidence": strongest_evidence,
        "strongest_no_go_margin_s": strongest.get("margin_s", NOT_MEASURED) if strongest else NOT_MEASURED,
        "reason": "all supplied corridor pivots remain no-go" if all_no_go else "at least one supplied corridor campaign is not no-go",
    }


def _merge_corridor_evidence(
    offline: Mapping[str, Any], campaign: Mapping[str, Any]
) -> dict[str, Any]:
    result = dict(offline)
    result["offline_status"] = offline.get("status", NOT_MEASURED)
    result["closed_loop"] = dict(campaign)
    if campaign.get("status") != NOT_MEASURED:
        result["status"] = campaign.get("status")
        result["reason"] = campaign.get("reason", result.get("reason", NOT_MEASURED))
        result["closed_loop_benefit_status"] = campaign.get(
            "closed_loop_benefit_status", NOT_MEASURED
        )
        result["strongest_no_go_evidence"] = campaign.get(
            "strongest_no_go_evidence", NOT_MEASURED
        )
        result["strongest_no_go_margin_s"] = campaign.get(
            "strongest_no_go_margin_s", NOT_MEASURED
        )
    return result


def _question_answers(
    fresh_rows: Sequence[Mapping[str, Any]],
    fresh: Mapping[str, Any],
    native: Mapping[str, Any],
    state: Mapping[str, Any] | None,
    screen: Mapping[str, Any] | None,
    ladder: Mapping[str, Any] | None,
    scale: Mapping[str, Any] | None,
    transition: Mapping[str, Any],
    corridor: Mapping[str, Any],
    final: Mapping[str, Any],
    github_status: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []

    def add(status: str, answer: str, evidence: str) -> None:
        answers.append({"status": status, "answer": answer, "evidence": evidence})

    def metric(row: Mapping[str, Any] | None, name: str, digits: int = 6) -> str:
        return _fmt(row.get(name, NOT_MEASURED), digits) if row else NOT_MEASURED

    def candidate_mode(candidate_id: str) -> str:
        mode = _candidate_modes(state).get(candidate_id)
        if mode:
            return mode
        upper = candidate_id.upper()
        return "ewma" if "EWMA" in upper else "td" if "TD" in upper else NOT_MEASURED

    def mode_rows(source: Mapping[str, Any] | None, key: str, mode: str) -> list[Mapping[str, Any]]:
        return [
            row
            for row in (_rows(source.get(key)) if source else [])
            if candidate_mode(str(row.get("candidate_id", ""))) == mode
        ]

    def screen_diag(mode: str) -> list[str]:
        by_candidate: dict[str, Mapping[str, Any]] = {}
        for row in mode_rows(screen, "runs", mode):
            candidate_id = str(row.get("candidate_id", NOT_MEASURED))
            previous = by_candidate.get(candidate_id)
            size = _integer(row.get("size", row.get("segments")))
            previous_size = _integer(previous.get("size", previous.get("segments"))) if previous else -1
            if not isinstance(previous_size, int) or (isinstance(size, int) and size > previous_size):
                by_candidate[candidate_id] = row
        result = []
        for candidate_id, row in sorted(by_candidate.items()):
            dlp = _mapping(row.get("dlp"))
            fallback = _integer(dlp.get("g4irsf24_dlp_fallback_s4_count"))
            evaluations = _integer(dlp.get("g4irsf24_dlp_route_evaluation_count"))
            ratio = 100.0 * fallback / evaluations if isinstance(fallback, int) and isinstance(evaluations, int) and evaluations > 0 else NOT_MEASURED
            result.append(
                f"{candidate_id}: fallback={_fmt(fallback, 0)}/{_fmt(evaluations, 0)} route decisions ({_fmt(ratio, 3)}%), "
                f"detour={_fmt(_integer(dlp.get('g4irsf24_dlp_detour_fallback_count')), 0)}, "
                f"eligible_candidates={_fmt(_integer(dlp.get('g4irsf24_dlp_eligible_candidate_count')), 0)}"
            )
        return result

    def ladder_scale_text(scale_value: int) -> str | None:
        rows = [row for row in (_rows(ladder.get("runs")) if ladder else []) if _integer(row.get("scale")) == scale_value]
        if not rows:
            return None
        parts = []
        for row in rows:
            timing = _mapping(_mapping(row.get("timing")).get("processed_attempt"))
            parts.append(
                f"{row.get('candidate_id', NOT_MEASURED)} mean={_fmt(_number(timing.get('mean_seconds')), 6)}s, "
                f"p95={_fmt(_number(timing.get('p95_seconds')), 6)}s, "
                f"p99={_fmt(_number(timing.get('p99_seconds')), 6)}s"
            )
        return "; ".join(parts)

    hca = _fresh_run(fresh_rows, "HCA")
    s4 = _fresh_run(fresh_rows, "S4")
    hca_processed = [row for row in fresh_rows if row.get("arm") == "HCA" and row.get("denominator") == "processed_attempt"]
    s4_processed = [row for row in fresh_rows if row.get("arm") == "S4" and row.get("denominator") == "processed_attempt"]
    release = _mapping(_mapping(native.get("protocol")).get("release_alignment"))

    github_pr = _mapping(github_status.get("pull_request")) if github_status else {}
    github_run = _mapping(github_status.get("workflow_run")) if github_status else {}
    github_green = (
        github_pr.get("state") == "open"
        and github_pr.get("draft") is True
        and github_pr.get("mergeable") is True
        and github_run.get("status") == "completed"
        and github_run.get("conclusion") == "success"
    )
    add(
        "MEASURED" if github_status else NOT_MEASURED,
        (
            f"{'YES' if github_green else 'NO'} — PR #8 state={github_pr.get('state', NOT_MEASURED)}, draft={github_pr.get('draft', NOT_MEASURED)}, mergeable={github_pr.get('mergeable', NOT_MEASURED)}; Run #71 status={github_run.get('status', NOT_MEASURED)}, conclusion={github_run.get('conclusion', NOT_MEASURED)}."
            if github_status else
            "NOT_MEASURED — reporting inputs contain no GitHub PR/check metadata."
        ),
        (
            f"Connector snapshot checked at {github_status.get('checked_at', NOT_MEASURED)}; PR={github_pr.get('url', NOT_MEASURED)}, run id={github_run.get('id', NOT_MEASURED)}."
            if github_status else
            "Requires a separate PR #8 / Actions Run #71 query; no status is inferred from local files."
        ),
    )
    add(
        "MEASURED",
        "Original entry: legacy/jichang_origin_readonly/src/RUN/Main.java; reproducible headless entry: benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java.",
        "RUN.Main.main and LegacyIcsNoFaultWindowBenchmark.main.",
    )
    hca_complete = (
        len(hca_processed) >= 2
        and all(row.get("comparison_eligible") is True for row in hca_processed)
        and all(row.get("completed_segments") == row.get("segment_count") for row in hca_processed)
    )
    add(
        "MEASURED",
        f"{'YES' if hca_complete else 'NO'} — {len(hca_processed)} eligible repeat(s), "
        f"{metric(hca, 'completed_segments', 0)} segments and {metric(hca, 'completed_raw_bags', 0)} raw bags per reported repeat.",
        "fresh_hca_summary.json normalized processed-attempt rows.",
    )
    aligned = _integer(release.get("aligned_segment_count"))
    same_tasks = isinstance(aligned, int) and hca is not None and s4 is not None and aligned == hca.get("segment_count") == s4.get("segment_count")
    add(
        "MEASURED",
        f"{'YES' if same_tasks else 'NO'} — exact release-aligned segment count={_fmt(aligned, 0)}; HCA and S4 segment counts are {_fmt(hca.get('segment_count') if hca else NOT_MEASURED, 0)} and {_fmt(s4.get('segment_count') if s4 else NOT_MEASURED, 0)}.",
        "native-race protocol.release_alignment plus unified fresh rows.",
    )
    add(
        "MEASURED",
        "NO, not one raw parser. Java HCA lifecycle and native records are produced separately, then this reporter maps both into the same three named denominator definitions and one long-table schema.",
        "g4irsf24_fresh_hca_race.csv denominator={original_entry, java_release, processed_attempt}; producer separation remains explicit.",
    )
    add(
        "MEASURED" if hca else NOT_MEASURED,
        f"min={metric(hca, 'min_s')}s, mean={metric(hca, 'mean_s')}s, max={metric(hca, 'max_s')}s, p95={metric(hca, 'p95_s')}s, p99={metric(hca, 'p99_s')}s." if hca else "NOT_MEASURED — no eligible HCA processed-attempt row.",
        "Fresh HCA repeat 1; repeat 2 is checked separately for determinism.",
    )
    add(
        "MEASURED" if s4 else NOT_MEASURED,
        f"min={metric(s4, 'min_s')}s, mean={metric(s4, 'mean_s')}s, max={metric(s4, 'max_s')}s, p95={metric(s4, 'p95_s')}s, p99={metric(s4, 'p99_s')}s." if s4 else "NOT_MEASURED — no eligible S4 processed-attempt row.",
        "Fresh S4 repeat 1; repeat 2 is checked separately for determinism.",
    )
    strict = fresh.get("FRESH_HCA_STRICT_WIN")
    add(
        "MEASURED",
        f"{'YES under the registered gate' if strict is True else 'NO'} — FRESH_HCA_STRICT_WIN={_fmt(strict)}, completion match across repeats={_fmt(fresh.get('completion_nonregression_all_repeats'))}, S4 native safety pass={_fmt(fresh.get('s4_safety_pass_all_repeats'))}. This is not all-tail dominance: max changes from {metric(hca, 'max_s')}s to {metric(s4, 'max_s')}s.",
        "The registered gate uses processed mean, p95, completion, and S4 native safety. HCA safety, common wall-time speedup, and max nonregression are not claimed.",
    )
    mean_delta = float(hca["mean_s"]) - float(s4["mean_s"]) if hca and s4 and isinstance(hca.get("mean_s"), float) and isinstance(s4.get("mean_s"), float) else NOT_MEASURED
    add(
        "MEASURED" if isinstance(mean_delta, float) else NOT_MEASURED,
        f"Processed-attempt mean improves by {_fmt(mean_delta, 6)}s ({_fmt(fresh.get('processed_mean_improvement_pct'), 6)}%)." if isinstance(mean_delta, float) else "NOT_MEASURED — comparable means are absent.",
        "Fresh HCA minus fresh S4, same task/release protocol.",
    )
    add(
        "MEASURED",
        f"{'YES' if fresh.get('PAPER_TABLE_MEAN_WIN') is True else 'NO'} — S4 mean={_fmt(float(s4['mean_s']) / 60.0, 6) if s4 and isinstance(s4.get('mean_s'), float) else NOT_MEASURED} min versus 3.96 min.",
        "PAPER_TABLE_MEAN_WIN; paper number is a historical target, not a fresh re-run.",
    )
    add(
        "MEASURED",
        f"{'YES' if fresh.get('PAPER_TABLE_RANGE_WIN') is True else 'NO'} — S4 min/mean/max="
        f"{_fmt(float(s4['min_s']) / 60.0, 6) if s4 and isinstance(s4.get('min_s'), float) else NOT_MEASURED}/"
        f"{_fmt(float(s4['mean_s']) / 60.0, 6) if s4 and isinstance(s4.get('mean_s'), float) else NOT_MEASURED}/"
        f"{_fmt(float(s4['max_s']) / 60.0, 6) if s4 and isinstance(s4.get('max_s'), float) else NOT_MEASURED} min; the registered range gate requires mean<3.96 and max≤5.98 min.",
        "PAPER_TABLE_RANGE_WIN.",
    )
    hca_walls = _numeric_values(hca_processed, "end_to_end_wall_s")
    s4_walls = _numeric_values(s4_processed, "core_wall_s")
    s4_cpu = _numeric_values(s4_processed, "cpu_s")
    add(
        "PARTIAL",
        f"HCA end-to-end child wall={','.join(_fmt(value, 6) for value in hca_walls) or NOT_MEASURED}s; "
        f"S4 core-only wall={','.join(_fmt(value, 6) for value in s4_walls) or NOT_MEASURED}s; "
        f"S4 CPU={','.join(_fmt(value, 6) for value in s4_cpu) or NOT_MEASURED}s; HCA CPU={NOT_MEASURED}; both RSS={NOT_MEASURED}.",
        "Wall scopes differ and are not a computational speedup comparison.",
    )
    add(
        NOT_MEASURED,
        "NOT_MEASURED — no fresh HCA 2× or 4× planning run is present.",
        "Native S4/DLP scale evidence cannot be substituted for centralized HCA scale evidence.",
    )
    transition_count = _integer(state.get("transition_count")) if state else _integer(transition.get("transition_count"))
    add(
        "MEASURED" if isinstance(transition_count, int) else NOT_MEASURED,
        f"{_fmt(transition_count, 0)} dense transitions." if isinstance(transition_count, int) else "NOT_MEASURED — collection state/transition file is absent.",
        "state.transition_count; compact grouping does not change the raw denominator.",
    )
    coverage_measured = all(isinstance(_integer(transition.get(key)), int) for key in ("edge_count", "node_count", "goal_count"))
    add(
        "MEASURED" if coverage_measured else NOT_MEASURED,
        f"edge={_fmt(transition.get('edge_count'), 0)}, node={_fmt(transition.get('node_count'), 0)}, goal={_fmt(transition.get('goal_count'), 0)}, edge-goal groups={_fmt(transition.get('compact_group_count'), 0)}." if coverage_measured else "NOT_MEASURED — compact transition evidence was not available.",
        "Counts are unique physical (current,selected), endpoint nodes, goal nodes, and (current,selected,goal) groups.",
    )
    split = _mapping(state.get("split_counts")) if state else {}
    split_ok = all(isinstance(_integer(split.get(key)), int) for key in ("train", "validation", "test"))
    add(
        "MEASURED" if split_ok else NOT_MEASURED,
        f"Chronological contiguous split: train={_fmt(_integer(split.get('train')), 0)}, validation={_fmt(_integer(split.get('validation')), 0)}, test={_fmt(_integer(split.get('test')), 0)}; no shuffle across time boundaries." if split_ok else "NOT_MEASURED — split counts/state are absent.",
        "g4irsf24_dlp_learning.chronological_split and state.split_counts.",
    )
    artifacts = _artifact_summaries(state)
    ewma_artifacts = [(candidate_id, row) for candidate_id, row in artifacts.items() if row.get("mode") == "ewma"]
    add(
        "MEASURED" if ewma_artifacts else NOT_MEASURED,
        "; ".join(
            f"{candidate_id}: edge residual observed-minus-static min/mean/support-weighted-mean/max="
            f"{_fmt(row.get('residual_min_s'), 6)}/{_fmt(row.get('residual_mean_s'), 6)}/"
            f"{_fmt(row.get('residual_support_weighted_mean_s'), 6)}/{_fmt(row.get('residual_max_s'), 6)}s"
            for candidate_id, row in ewma_artifacts
        ) if ewma_artifacts else "NOT_MEASURED — no readable P1 artifact was supplied by state.json.",
        "Frozen P1 edge_residuals; this is an offline residual distribution, not closed-loop benefit.",
    )
    ewma_rank = mode_rows(screen, "ranking", "ewma")
    add(
        "MEASURED" if ewma_rank else NOT_MEASURED,
        "; ".join(f"{row.get('candidate_id')}: {_fmt(_integer(row.get('committed_mutation_count')), 0)} committed actions" for row in ewma_rank) if ewma_rank else "NOT_MEASURED — no P1 native screen ranking.",
        "Screen mutation count is summed across registered 144/512 prefixes.",
    )
    ewma_decisions = mode_rows(ladder, "decisions", "ewma")
    add(
        "MEASURED" if ewma_decisions else NOT_MEASURED,
        "; ".join(
            f"{row.get('candidate_id')}: 1×/2× mean benefit="
            + "/".join(_fmt(-float(value), 6) if isinstance(value, (int, float)) else NOT_MEASURED for value in row.get("mean_delta_seconds", []))
            + "s (positive means faster)"
            for row in ewma_decisions
        ) if ewma_decisions else "NOT_MEASURED — P1 was not promoted into the 1×/2× ladder (zero screen mutations is not business benefit).",
        "ladder.decisions.mean_delta_seconds versus paired S4.",
    )
    add(
        NOT_MEASURED,
        "NOT_MEASURED — one chronological TD(0) fit and offline validation do not provide a convergence/stability trace across epochs or seeds.",
        "No convergence criterion or repeated TD trajectory is present in state/screen/ladder.",
    )
    td_validation = [row for row in (_rows(state.get("offline_validation")) if state else []) if candidate_mode(str(row.get("candidate_id", ""))) == "td"]
    td_test = {
        str(row.get("candidate_id")): row
        for row in (_rows(state.get("offline_test")) if state else [])
        if candidate_mode(str(row.get("candidate_id", ""))) == "td"
    }
    add(
        "MEASURED" if td_validation else NOT_MEASURED,
        "; ".join(
            f"{row.get('candidate_id')}: validation runtime/Bellman coverage="
            f"{_fmt(_number(row.get('runtime_lookup_coverage')), 6)}/"
            f"{_fmt(_number(row.get('td_bellman_coverage')), 6)}, test runtime/Bellman coverage="
            f"{_fmt(_number(_mapping(td_test.get(str(row.get('candidate_id')))).get('runtime_lookup_coverage')), 6)}/"
            f"{_fmt(_number(_mapping(td_test.get(str(row.get('candidate_id')))).get('td_bellman_coverage')), 6)}"
            for row in td_validation
        ) if td_validation else "NOT_MEASURED — no P2 offline validation row.",
        "Runtime lookup treats terminal V(goal,goal)=0; Bellman coverage separately requires the frozen current-state and downstream values. Test is the held-out chronological tail.",
    )
    td_rank = mode_rows(screen, "ranking", "td")
    add(
        "MEASURED" if td_rank else NOT_MEASURED,
        "; ".join(f"{row.get('candidate_id')}: {_fmt(_integer(row.get('committed_mutation_count')), 0)} committed actions" for row in td_rank) if td_rank else "NOT_MEASURED — no P2 native screen ranking.",
        "Screen mutation count is summed across registered 144/512 prefixes.",
    )
    fallback_lines = screen_diag("ewma") + screen_diag("td")
    add(
        "MEASURED" if fallback_lines else NOT_MEASURED,
        "; ".join(fallback_lines) if fallback_lines else "NOT_MEASURED — no native DLP diagnostics.",
        "Largest supplied screen prefix per candidate; ratio=fallback_s4_count/route_evaluation_count (both are decision counts).",
    )
    top_groups = _rows(transition.get("top_observed_residual_groups"))
    add(
        "PARTIAL_DIAGNOSTIC" if top_groups else NOT_MEASURED,
        "; ".join(
            f"{row.get('current')}->{row.get('selected')} goal={row.get('goal')} support={row.get('support')} observed-abs-residual-mass={_fmt(row.get('observed_abs_residual_mass_s'), 3)}s"
            for row in top_groups[:3]
        ) if top_groups else "NOT_MEASURED — no transition groups.",
        "Descriptive observed residual mass only; causal branch contribution remains NOT_MEASURED without intervention.",
    )
    add(
        NOT_MEASURED,
        "NOT_MEASURED — supplied safety gates include unresolved-deadlock checks but no dedicated route-loop or path-detour counter.",
        "Zero unresolved deadlocks must not be relabeled as zero loops.",
    )
    detour_lines = []
    for mode in ("ewma", "td"):
        detour_lines.extend(screen_diag(mode))
    add(
        "MEASURED" if detour_lines else NOT_MEASURED,
        "; ".join(line.split(", route_evaluations=")[0] for line in detour_lines) if detour_lines else "NOT_MEASURED — no detour fallback counter.",
        "g4irsf24_dlp_detour_fallback_count on the largest supplied screen prefix; it is a fallback count, not a causal benefit.",
    )
    one_x = ladder_scale_text(1)
    add(
        "MEASURED" if one_x else NOT_MEASURED,
        one_x or "NOT_MEASURED — no 1× ladder run.",
        "processed-attempt timing; all available candidate and S4 rows are shown.",
    )
    two_x = ladder_scale_text(2)
    add(
        "MEASURED" if two_x else NOT_MEASURED,
        two_x or "NOT_MEASURED — no 2× ladder run.",
        "processed-attempt timing; all available candidate and S4 rows are shown.",
    )
    wait_lines = []
    for row in _rows(ladder.get("runs")) if ladder else []:
        java = _mapping(_mapping(row.get("timing")).get("java_release"))
        processed = _mapping(_mapping(row.get("timing")).get("processed_attempt"))
        java_mean, network_mean = _number(java.get("mean_seconds")), _number(processed.get("mean_seconds"))
        if isinstance(java_mean, float) and isinstance(network_mean, float):
            wait_lines.append(
                f"{row.get('candidate_id')}@{row.get('scale')}× source-wait mean={_fmt(java_mean - network_mean, 6)}s, network mean={_fmt(network_mean, 6)}s"
            )
    add(
        "MEASURED" if wait_lines else NOT_MEASURED,
        "; ".join(wait_lines) if wait_lines else "NOT_MEASURED — ladder lacks both java-release and processed-attempt means.",
        "source wait is java-release mean minus processed-attempt mean; distributions are not subtracted percentile-by-percentile.",
    )
    add(
        NOT_MEASURED,
        "NOT_MEASURED — no S4-v2 reference value or gap definition is supplied in fresh/state/screen/ladder/scale inputs.",
        "Fresh HCA improvement is reported separately and is not substituted for S4-v2 gap closure.",
    )
    scale_progress = []
    for row in _rows(scale.get("runs")) if scale else []:
        progress = _mapping(row.get("progress"))
        scale_progress.append(
            f"#{row.get('ordinal')} {row.get('arm')}: completed={_fmt(_integer(progress.get('completed_bags')), 0)}, "
            f"released={_fmt(_integer(progress.get('released_bags')), 0)}, backlog={_fmt(_integer(progress.get('current_backlog')), 0)}, "
            f"simulated={_fmt(_number(progress.get('simulated_time')), 3)}s, status={row.get('status', NOT_MEASURED)}"
        )
    if scale_progress:
        add(
            "MEASURED",
            "; ".join(scale_progress),
            "scale.runs.progress; completed is progress within the bounded run, not full completion unless status says COMPLETE.",
        )
    elif scale:
        add(
            "NOT_APPLICABLE",
            f"NOT_APPLICABLE — 4× 60s was not unlocked or run; completed/progress/backlog have no denominator. reason={scale.get('reason', NOT_MEASURED)}.",
            "scale.status may be NO_EXTEND as a gate decision with runs=[], which is not a completed 4× experiment.",
        )
    else:
        add(
            NOT_MEASURED,
            "NOT_MEASURED — no 4× gate decision was supplied.",
            "No scale result file was available.",
        )
    scale_status = scale.get("status", NOT_MEASURED) if scale else NOT_MEASURED
    scale_was_run = bool(scale_progress)
    add(
        "MEASURED" if scale else NOT_MEASURED,
        (
            "180s is unlocked; full is NOT_APPLICABLE until the 180s gate succeeds."
            if scale_status == "EXTEND_180S_PENDING" and scale_was_run
            else (
                "NO — 4× itself was not unlocked/run, so 180s and full are also not unlocked."
                if not scale_was_run
                else "NO — 4× ran but did not unlock 180s or full."
            )
        ) if scale else "NOT_MEASURED — 4× gate was not supplied.",
        f"scale.status={scale_status}, run_count={len(_rows(scale.get('runs'))) if scale else NOT_MEASURED}; EXTEND_180S_PENDING authorizes only the next bounded stage and does not activate DLP.",
    )
    add(
        NOT_MEASURED,
        "NOT_MEASURED — reported CPU is whole-run process CPU, not incremental DLP CPU; dividing it by actions would overstate precision.",
        "A paired profiler or baseline-subtracted action timer is required.",
    )
    add(
        "IMPLEMENTATION_EVIDENCE",
        "YES by implementation structure: each decision scans the local candidate vector a constant number of times and performs frozen residual lookups; empirical asymptotic timing is NOT_MEASURED.",
        "cpp/ics_core/runtime/event_driven_junction.hpp::apply_g4irsf24_dlp_residual.",
    )
    dlp_runs = [row for row in (_rows(screen.get("runs")) if screen else []) if str(row.get("candidate_id")) != "S4"]
    local_gates = (
        "bag_future_path_field_present_false",
        "full_future_routes_stored_zero",
        "runtime_full_astar_calls_zero",
        "scorer_runtime_global_scan_count_zero",
        "priority_global_scan_count_zero",
        "first_edge_credit_global_scan_count_zero",
        "scorer_future_route_input_count_zero",
        "scorer_future_schedule_input_count_zero",
    )
    local_counter_pass = bool(dlp_runs) and all(
        all(_mapping(_mapping(row.get("safety")).get("gates")).get(name) is True for name in local_gates)
        for row in dlp_runs
    )
    add(
        "MEASURED" if local_counter_pass else NOT_MEASURED,
        "NO dynamic non-neighbor/future-route scan was observed in supplied DLP screen runs; the scorer uses current/goal IDs, local candidates, and frozen keyed residuals." if local_counter_pass else "NOT_MEASURED — local-state counters were not supplied or did not all pass.",
        "Future-route storage and runtime global-scan safety gates; this does not claim that precomputed static potentials are dynamic neighbor state.",
    )
    add(
        NOT_MEASURED,
        "NOT_MEASURED — no supplied candidate simultaneously identifies an H_system cohort of 64–128 changed actions and its paired closed-loop benefit.",
        "Mutation counts outside that explicit cohort are not reinterpreted as H_system evidence.",
    )
    corridor_closed = _mapping(corridor.get("closed_loop"))
    strongest_corridor = _mapping(corridor_closed.get("strongest_no_go_evidence"))
    if strongest_corridor:
        by_scale = {
            _integer(row.get("scale")): row
            for row in _rows(strongest_corridor.get("comparisons"))
        }
        one, two = _mapping(by_scale.get(1)), _mapping(by_scale.get(2))
        other_margins = ", ".join(
            f"margin={_fmt(row.get('margin_s'), 3)}s:{row.get('status', NOT_MEASURED)}"
            for row in _rows(corridor_closed.get("campaigns"))
            if row.get("margin_s") != strongest_corridor.get("margin_s")
        ) or "none"
        add(
            "MEASURED_NO_GO",
            f"Overall NO-GO, so active remains S4. Strongest no-go evidence is margin={_fmt(strongest_corridor.get('margin_s'), 3)}s: "
            f"1× proposals/mutations={_fmt(_integer(one.get('proposal_count')), 0)}/{_fmt(_integer(one.get('committed_mutations')), 0)}, mean delta={_fmt(_number(one.get('mean_delta_seconds')), 6)}s, "
            f"p95/p99/max delta={_fmt(_number(one.get('p95_delta_seconds')), 6)}/{_fmt(_number(one.get('p99_delta_seconds')), 6)}/{_fmt(_number(one.get('max_delta_seconds')), 6)}s; "
            f"2× proposals/mutations={_fmt(_integer(two.get('proposal_count')), 0)}/{_fmt(_integer(two.get('committed_mutations')), 0)}, mean delta={_fmt(_number(two.get('mean_delta_seconds')), 6)}s, "
            f"p95/p99/max delta={_fmt(_number(two.get('p95_delta_seconds')), 6)}/{_fmt(_number(two.get('p99_delta_seconds')), 6)}/{_fmt(_number(two.get('max_delta_seconds')), 6)}s. "
            f"Other supplied pivots: {other_margins}.",
            "Negative delta is faster. These are paired counterfactuals on the same exogenous task stream, not new-stream generalization. The 2× central-quantile gain coexists with a max-tail regression and a failed 1× gate; it is strongest no-go evidence, not an active-policy win.",
        )
    elif corridor.get("status") in {"OFFLINE_DIAGNOSTIC_MEASURED", "OFFLINE_ARTIFACT_MEASURED"}:
        corridor_detail = (
            f"Offline diagnostic: corridors={_fmt(corridor.get('corridor_count'), 0)}, branches={_fmt(corridor.get('branch_count'), 0)}, "
            f"projected edges={_fmt(corridor.get('projected_edge_count'), 0)}, max within-branch residual span={_fmt(corridor.get('max_branch_residual_span_s'), 6)}s."
        )
        add(
            NOT_MEASURED,
            f"NOT_MEASURED — {corridor_detail} No corridor artifact has a paired native closed-loop business result yet.",
            "Offline reconvergence is diagnostic evidence, not realized or causal benefit.",
        )
    else:
        add(
            NOT_MEASURED,
            "NOT_MEASURED — no reconvergent-corridor diagnostic and no paired native closed-loop result were supplied.",
            str(corridor.get("reason", NOT_MEASURED)),
        )
    add(
        NOT_MEASURED,
        "NOT_MEASURED — the fresh race is explicitly no-fault and no dedicated injected-fault campaign was supplied.",
        "Ordinary-run safety/fallback counters do not establish fault-condition safety.",
    )
    add(
        "MEASURED",
        f"Active candidate={final.get('active_policy', 'S4')}; decision status={final.get('status', NOT_MEASURED)}; learning activated={_fmt(final.get('learning_policy_activated'))}.",
        "Final policy stays S4 unless the registered closed-loop and scale gates promote a DLP artifact.",
    )
    if scale_status == "EXTEND_180S_PENDING":
        next_question = "Can the promoted candidate preserve its 4× ABBA advantage and safety in the registered 180s bounded run?"
    elif ladder and not _is_ladder_no_go(ladder.get("status")):
        next_question = "Can the ladder winner pass one 4× 60s ABBA gate without losing safety or increasing backlog?"
    elif strongest_corridor:
        next_question = "Can one existing local congestion threshold abstain exactly to S4 at 1× while retaining the measured margin-0.5 corridor gain at 2×, without adding another model or planner?"
    elif corridor.get("status") in {"OFFLINE_DIAGNOSTIC_MEASURED", "OFFLINE_ARTIFACT_MEASURED"}:
        next_question = "Can one frozen reconvergent-corridor artifact create more than zero safe committed mutations in the existing 144/512 screen?"
    else:
        next_question = "Do supported reconvergent branches exist, and can one frozen first-edge projection create more than zero safe mutations in the existing small screen?"
    add(
        "DECISION",
        next_question,
        "This is the narrowest next gate selected from current no-go/scale/corridor evidence; it adds no new framework layer.",
    )

    if len(answers) != len(DECISION_QUESTIONS):
        raise ReportingError(f"question answer count mismatch: {len(answers)} != {len(DECISION_QUESTIONS)}")
    return [
        {"number": index, "question": question, **answer}
        for index, (question, answer) in enumerate(zip(DECISION_QUESTIONS, answers), start=1)
    ]


def _fresh_report(rows: Sequence[Mapping[str, Any]], decision: Mapping[str, Any], native: Mapping[str, Any]) -> str:
    first_runs = [row for row in rows if row.get("repeat") == 1]
    table_rows = []
    for row in first_runs:
        item = dict(row)
        for field in ("min_s", "p50_s", "mean_s", "p95_s", "p99_s", "max_s"):
            item[field.replace("_s", "_min")] = float(item[field]) / 60.0 if isinstance(item.get(field), float) else NOT_MEASURED
        table_rows.append(item)
    release = _mapping(_mapping(native.get("protocol")).get("release_alignment"))
    return f"""# G4IRSF24 Fresh HCA Race

Status: `{decision.get('status', NOT_MEASURED)}`.

All measured arms use 43,603 segments, 28,506 raw bags, no faults, and the exact fresh HCA release trace. All `{_fmt(decision.get('repeat_count'), 0)}` paired repeats pass the business/completion gates; exact repeat-metric consistency is `{_fmt(decision.get('repeat_metric_consistent'))}`.

{_md_table(table_rows, [
    ('Denominator', 'denominator', None), ('Arm', 'arm', None), ('Min (min)', 'min_min', 6),
    ('P50', 'p50_min', 6), ('Mean', 'mean_min', 6), ('P95', 'p95_min', 6),
    ('P99', 'p99_min', 6), ('Max', 'max_min', 6)
])}

## Decision

- S4 processed-attempt mean improvement versus fresh HCA: `{_fmt(decision.get('processed_mean_improvement_pct'))}%`.
- S4 processed-attempt p95 improvement: `{_fmt(decision.get('processed_p95_improvement_pct'))}%`.
- S4 processed-attempt max improvement: `{_fmt(decision.get('processed_max_improvement_pct'))}%`; a negative value is a tail regression.
- `FRESH_HCA_STRICT_WIN`: `{_fmt(decision.get('FRESH_HCA_STRICT_WIN'))}`.
- `FRESH_HCA_CLEAR_WIN`: `{_fmt(decision.get('FRESH_HCA_CLEAR_WIN'))}`.
- `PAPER_TABLE_MEAN_WIN`: `{_fmt(decision.get('PAPER_TABLE_MEAN_WIN'))}`.
- `PAPER_TABLE_RANGE_WIN`: `{_fmt(decision.get('PAPER_TABLE_RANGE_WIN'))}`.

## Protocol and measurement limits

- Inputs: `legacy/jichang_origin_readonly/map2.txt` and `legacy/jichang_origin_readonly/inputdata.txt`; the legacy Java HCA/A*/priority/reservation logic is unchanged. The compatibility patch only records each task's actual release epoch from the external benchmark wrapper.
- Java was compiled on JDK 18 with `javac --release 8`. Reproduce the two independent Java processes with `python scripts/eval/run_g4irsf24_fresh_hca.py run --profile full --output-root build/g4irsf24_fresh_hca_full`.
- Reproduce F2/S4 after the Java release trace exists with `python scripts/eval/run_g4irsf24_native_race.py`; both native arms must receive the same exact release CSV before comparison.
- Exact release alignment count: `{_fmt(release.get('aligned_segment_count'), 0)}`.
- Release minus canonical pass: mean `{_fmt(release.get('release_minus_canonical_pass_mean_seconds'))}` s, min `{_fmt(release.get('release_minus_canonical_pass_min_seconds'))}` s, max `{_fmt(release.get('release_minus_canonical_pass_max_seconds'))}` s.
- Java wall is end-to-end child-process wall; current native wall is core backend-call wall. A strict computational speedup is `NOT_MEASURED` until one common end-to-end timer is used.
- Fresh deadline misses, peak RSS, and HCA CPU are `NOT_MEASURED`.
"""


def _simple_report(title: str, status: Any, prose: Sequence[str], table: str | None = None) -> str:
    sections = [f"# {title}", "", f"Status: `{status}`.", ""]
    sections.extend(f"- {line}" for line in prose)
    if table:
        sections.extend(["", table])
    return "\n".join(sections)


def _decision_summary(
    fresh_rows: Sequence[Mapping[str, Any]], fresh: Mapping[str, Any],
    native: Mapping[str, Any], state: Mapping[str, Any] | None,
    screen: Mapping[str, Any] | None, ladder: Mapping[str, Any] | None,
    scale: Mapping[str, Any] | None, release_count: int | str,
    transition: Mapping[str, Any], corridor: Mapping[str, Any],
    policy_evidence: Mapping[str, Any], github_status: Mapping[str, Any] | None,
) -> dict[str, Any]:
    raw_ladder_status = ladder.get("status", NOT_MEASURED) if ladder else NOT_MEASURED
    ladder_status = (
        ladder.get("dlp_ladder_status", raw_ladder_status)
        if ladder else NOT_MEASURED
    )
    scale_status = scale.get("status", NOT_MEASURED) if scale else NOT_MEASURED
    if scale and isinstance(scale.get("active_policy"), str):
        active_policy = str(scale["active_policy"])
        final_status = scale_status
    elif _is_ladder_no_go(ladder_status) or _is_ladder_no_go(raw_ladder_status):
        active_policy = "S4"
        final_status = ladder_status
    elif ladder:
        # A 1x/2x winner is still a candidate until its scale gate runs.
        active_policy = "S4"
        final_status = "PENDING_4X_SCALE_KEEP_S4"
    else:
        active_policy = "S4"
        final_status = "PENDING_DLP_EVALUATION_KEEP_S4"
    decision: dict[str, Any] = {
        "schema": "czr005.g4irsf24.decision_summary.v1",
        "fresh_race": dict(fresh),
        "github_baseline": dict(github_status) if github_status else NOT_MEASURED,
        "transition": {
            "status": state.get("stage", NOT_MEASURED) if state else NOT_MEASURED,
            "transition_count": state.get("transition_count", NOT_MEASURED) if state else NOT_MEASURED,
            **dict(transition),
        },
        "dlp_screen": {
            "status": screen.get("stage", NOT_MEASURED) if screen else NOT_MEASURED,
            "selected_candidate_ids": screen.get("selected_candidate_ids", []) if screen else NOT_MEASURED,
        },
        "closed_loop": {
            "status": ladder_status,
            "raw_status": raw_ladder_status,
            "winner_candidate_id": ladder.get("winner_candidate_id", NOT_MEASURED) if ladder else NOT_MEASURED,
            "active_policy": ladder.get("active_policy", NOT_MEASURED) if ladder else NOT_MEASURED,
            "reconvergent_corridor": dict(_mapping(corridor.get("closed_loop"))),
        },
        "reconvergent_corridor": dict(corridor),
        "scale": {
            "status": scale_status,
            "active_policy": scale.get("active_policy", NOT_MEASURED) if scale else NOT_MEASURED,
            "reason": scale.get("reason", NOT_MEASURED) if scale else NOT_MEASURED,
            "run_count": len(_rows(scale.get("runs"))) if scale else NOT_MEASURED,
            "four_x_executed": bool(_rows(scale.get("runs"))) if scale else NOT_MEASURED,
        },
        "final": {
            "status": final_status,
            "outcome_summary": f"{fresh.get('status', NOT_MEASURED)}; {final_status}; active={active_policy}",
            "active_policy": active_policy,
            "fresh_hca_beaten": fresh.get("FRESH_HCA_STRICT_WIN", NOT_MEASURED),
            "learning_policy_activated": active_policy != "S4",
        },
        "evidence": {
            "release_compact_path": _display(RELEASE_EVIDENCE),
            "release_segment_count": release_count,
            "transition_compact_path": _display(TRANSITION_EVIDENCE),
            "offline_policy_copies": dict(policy_evidence),
        },
        "not_measured": [
            "fresh_deadline_miss",
            "common_end_to_end_runtime_wall",
            "fresh_peak_rss",
            "hca_cpu_time",
            *([] if state else ["dense_transition_and_dlp"]),
            *([] if scale and _rows(scale.get("runs")) else ["4x_scale_abba_not_run"]),
            "dedicated_fault_causal_campaign",
            *(
                []
                if corridor.get("closed_loop_benefit_status") == "MEASURED_NO_GO"
                else ["reconvergent_corridor_closed_loop_benefit"]
            ),
        ],
    }
    decision["questions"] = _question_answers(
        fresh_rows, fresh, native, state, screen, ladder, scale,
        transition, corridor, decision["final"], github_status,
    )
    return decision


def _write_reports(
    fresh_rows: Sequence[Mapping[str, Any]], fresh_decision: Mapping[str, Any],
    native: Mapping[str, Any], transition_rows: Sequence[Mapping[str, Any]],
    ablation_rows: Sequence[Mapping[str, Any]], closed_rows: Sequence[Mapping[str, Any]],
    scale_rows: Sequence[Mapping[str, Any]], decision: Mapping[str, Any],
    corridor: Mapping[str, Any], screen: Mapping[str, Any] | None,
) -> None:
    _write_text(REPORTS["fresh"], _fresh_report(fresh_rows, fresh_decision, native))
    transition_status = transition_rows[0].get("status", NOT_MEASURED)
    held_out_rows = [
        row for row in ablation_rows
        if isinstance(row.get("test_mae_s"), float)
        and isinstance(row.get("test_static_mae_s"), float)
    ]
    best_held_out = min(held_out_rows, key=lambda row: float(row["test_mae_s"])) if held_out_rows else None
    _write_text(
        REPORTS["transition"],
        _simple_report(
            "G4IRSF24 Dense Transition Data", transition_status,
            [
                "Transitions contain only local physical state and duration fields; task and decision identities are excluded.",
                "Absolute t0/t1 are used only for chronological ordering and split boundaries; no timestamp is stored in a runtime artifact or used as a model feature.",
                "Each dense source run stores one deterministic task-id shard. `trace_complete=true` means that requested shard was fully retained; paired complementary shards form the reported population, not one unsharded per-run trace.",
                "Validation selects at most one candidate per family; the chronological test tail is evaluated only after fitting and is reported separately.",
                (
                    f"Best learned held-out action-score proxy MAE is {_fmt(best_held_out.get('test_mae_s'), 6)}s versus its zero-residual S4 proxy {_fmt(best_held_out.get('test_static_mae_s'), 6)}s; this is negative non-stationarity evidence, not a learning win."
                    if best_held_out else
                    "Held-out chronological test metrics are NOT_MEASURED."
                ),
                f"Compact edge-goal evidence: `{_display(TRANSITION_EVIDENCE)}`.",
            ],
            _md_table(transition_rows, [
                ("Section", "section", None), ("Item", "item", None), ("Status", "status", None),
                ("Transitions", "transition_count", 0), ("Coverage", "coverage", 4), ("MAE (s)", "mae_s", 3)
            ]),
        ),
    )
    for mode, report_key, title in (("ewma", "ewma", "G4IRSF24 DLP EWMA"), ("td", "td", "G4IRSF24 DLP TD")):
        selected = [row for row in ablation_rows if row.get("mode") == mode]
        action_rows = [
            row for row in _screen_action_rows(screen)
            if ("EWMA" in str(row.get("candidate_id"))) == (mode == "ewma")
        ]
        status = "MEASURED" if selected else NOT_MEASURED
        if mode == "ewma":
            metric_summary = "; ".join(
                f"{row.get('candidate_id')}: validation edge learned/static={_fmt(row.get('offline_mae_s'), 6)}/{_fmt(row.get('static_mae_s'), 6)}s, "
                f"held-out edge learned/static={_fmt(row.get('test_mae_s'), 6)}/{_fmt(row.get('test_static_mae_s'), 6)}s"
                for row in selected
            ) or "No offline metric rows were supplied."
            offline_columns = [
                ("Candidate", "candidate_id", None), ("Val runtime coverage", "runtime_lookup_coverage", 4),
                ("Val edge MAE", "offline_mae_s", 3), ("Val zero residual", "static_mae_s", 3),
                ("Test edge MAE", "test_mae_s", 3), ("Test zero residual", "test_static_mae_s", 3),
                ("Mutations", "screen_committed_mutations", 0), ("Status", "status", None),
            ]
        else:
            metric_summary = "; ".join(
                f"{row.get('candidate_id')}: validation runtime/Bellman coverage={_fmt(row.get('runtime_lookup_coverage'), 6)}/{_fmt(row.get('td_bellman_coverage'), 6)}, "
                f"Bellman learned/zero-current={_fmt(row.get('td_bellman_mae_s'), 6)}/{_fmt(row.get('td_zero_value_mae_s'), 6)}s; "
                f"held-out runtime/Bellman coverage={_fmt(row.get('test_runtime_lookup_coverage'), 6)}/{_fmt(row.get('test_td_bellman_coverage'), 6)}, "
                f"Bellman learned/zero-current={_fmt(row.get('test_td_bellman_mae_s'), 6)}/{_fmt(row.get('test_td_zero_value_mae_s'), 6)}s"
                for row in selected
            ) or "No offline metric rows were supplied."
            offline_columns = [
                ("Candidate", "candidate_id", None), ("Val runtime cov", "runtime_lookup_coverage", 4),
                ("Val Bellman cov", "td_bellman_coverage", 4), ("Val Bellman MAE", "td_bellman_mae_s", 3),
                ("Val zero-current", "td_zero_value_mae_s", 3), ("Test runtime cov", "test_runtime_lookup_coverage", 4),
                ("Test Bellman cov", "test_td_bellman_coverage", 4), ("Test Bellman MAE", "test_td_bellman_mae_s", 3),
                ("Test zero-current", "test_td_zero_value_mae_s", 3),
                ("Mutations", "screen_committed_mutations", 0), ("Status", "status", None),
            ]
        report_tables = "\n\n".join(
            [
                "## Offline validation and held-out test\n\n" + _md_table(
                    selected or [{"candidate_id": NOT_MEASURED}], offline_columns
                ),
                "## Native 144/512 action accounting\n\n" + _md_table(action_rows or [{"candidate_id": NOT_MEASURED}], [
                    ("Candidate", "candidate_id", None), ("Prefix", "prefix", 0),
                    ("Route decisions", "route_evaluations", 0), ("Eligible", "eligible_candidates", 0),
                    ("Supported", "supported_candidates", 0), ("Proposals", "proposals", 0),
                    ("Mutations", "mutations", 0), ("Fallback", "fallback_s4", 0),
                    ("Unsupported", "unsupported", 0), ("Low support", "low_support", 0),
                    ("Margin", "margin", 0), ("Detour", "detour", 0),
                    ("Shield/fault", "shield_fault", 0), ("Safe", "safety", None),
                ]),
            ]
        )
        _write_text(
            REPORTS[report_key],
            _simple_report(
                title, status,
                [
                    "S4 remains the exact fallback for unsupported states.",
                    "A candidate needs real native mutations and closed-loop business improvement before activation.",
                    (
                        "TD Bellman zero-current is a baseline against the same frozen downstream target; the edge-score proxy cancels that downstream and is not presented as a clean S4/static comparison."
                        if mode == "td" else
                        "EWMA learned edge residual is compared directly with the zero-residual S4 proxy on chronological validation and held-out test."
                    ),
                    metric_summary,
                ],
                report_tables,
            ),
        )
    closed_status = decision["closed_loop"]["status"]
    _write_text(
        REPORTS["closed"],
        _simple_report(
            "G4IRSF24 Native Closed Loop", closed_status,
            [
                f"Active policy after the 1x/2x ladder and corridor pivots: `{decision['final']['active_policy']}`.",
                f"Corridor pivot status: `{_mapping(decision['closed_loop'].get('reconvergent_corridor')).get('status', NOT_MEASURED)}`; strongest no-go margin: `{_fmt(_mapping(decision['closed_loop'].get('reconvergent_corridor')).get('strongest_no_go_margin_s'), 3)}` s.",
            ],
            _md_table(closed_rows, [
                ("Campaign", "campaign", None), ("Margin", "margin_s", 3),
                ("Scale", "scale", None), ("Candidate", "candidate_id", None), ("Status", "status", None),
                ("Mean (s)", "processed_mean_s", 3), ("P95 (s)", "processed_p95_s", 3),
                ("P99 (s)", "processed_p99_s", 3), ("Max (s)", "processed_max_s", 3),
                ("Proposals", "proposals", 0), ("Mutations", "committed_mutations", 0),
                ("Fallback", "fallback_s4", 0),
                ("Mean Δ (s)", "mean_delta_s", 6), ("P95 Δ (s)", "p95_delta_s", 6),
                ("P99 Δ (s)", "p99_delta_s", 6), ("Max Δ (s)", "max_delta_s", 6),
                ("Eligible", "candidate_eligible", None),
                ("Strongest no-go", "strongest_no_go_evidence", None),
            ]),
        ),
    )
    _write_text(
        REPORTS["scale"],
        _simple_report(
            "G4IRSF24 Scale", decision["scale"]["status"],
            [
                f"Scale decision active policy: `{decision['scale']['active_policy']}`.",
                f"4× executed: `{decision['scale']['four_x_executed']}`; run count: `{decision['scale']['run_count']}`. A `NO_EXTEND` gate with zero runs means 4× was not unlocked, not that a 4× run finished.",
            ],
            _md_table(scale_rows, [
                ("Order", "ordinal", None), ("Arm", "arm", None), ("Status", "status", None),
                ("Completed", "completed_bags", 0), ("Backlog", "backlog", 0),
                ("Events/completed", "events_per_completed", 3), ("Mutations", "committed_mutations", 0)
            ]),
        ),
    )
    corridor_campaign_rows = []
    corridor_closed = _mapping(corridor.get("closed_loop"))
    strongest_margin = corridor_closed.get("strongest_no_go_margin_s", NOT_MEASURED)
    for campaign_row in _rows(corridor_closed.get("campaigns")):
        for comparison in _rows(campaign_row.get("comparisons")):
            detail = next(
                (
                    row for row in closed_rows
                    if row.get("campaign") == "RECONVERGENT_CORRIDOR"
                    and row.get("margin_s") == campaign_row.get("margin_s")
                    and row.get("scale") == comparison.get("scale")
                ),
                {},
            )
            corridor_campaign_rows.append(
                {
                    "margin_s": campaign_row.get("margin_s", NOT_MEASURED),
                    "status": campaign_row.get("status", NOT_MEASURED),
                    "strongest": (
                        isinstance(strongest_margin, (int, float))
                        and isinstance(campaign_row.get("margin_s"), (int, float))
                        and math.isclose(float(strongest_margin), float(campaign_row["margin_s"]), rel_tol=0.0, abs_tol=1.0e-12)
                    ),
                    **dict(comparison),
                    "proposals": detail.get("proposals", NOT_MEASURED),
                    "fallback_s4": detail.get("fallback_s4", NOT_MEASURED),
                    "max_delta_seconds": detail.get("max_delta_s", NOT_MEASURED),
                }
            )
    corridor_tables = "\n\n".join(
        [
            "## Closed-loop pivot\n\n" + _md_table(
                corridor_campaign_rows or [{"margin_s": NOT_MEASURED}],
                [
                    ("Margin (s)", "margin_s", 3), ("Scale", "scale", 0),
                    ("Proposals", "proposals", 0), ("Mutations", "committed_mutations", 0),
                    ("Fallback", "fallback_s4", 0),
                    ("Mean delta (s)", "mean_delta_seconds", 6),
                    ("P95 delta (s)", "p95_delta_seconds", 6),
                    ("P99 delta (s)", "p99_delta_seconds", 6),
                    ("Max delta (s)", "max_delta_seconds", 6),
                    ("Safe", "complete_and_safe", None),
                    ("Overall", "status", None), ("Strongest no-go", "strongest", None),
                ],
            ),
            "## Offline corridor structure\n\n" + _md_table(
                _rows(corridor.get("corridors")) or [{"from": NOT_MEASURED}],
                [
                    ("Branch", "from", 0), ("First edge", "to", 0),
                    ("Rejoin", "reconvergence", 0), ("Hops", "hops", 0),
                    ("Support", "support", 0), ("Residual (s)", "residual_seconds", 6),
                ],
            ),
        ]
    )
    _write_text(
        REPORTS["reconvergent"],
        _simple_report(
            "G4IRSF24 Reconvergent Corridor", corridor.get("status", NOT_MEASURED),
            [
                str(corridor.get("reason", "No dedicated reconvergent-corridor diagnostic was supplied.")),
                f"Corridors={_fmt(corridor.get('corridor_count'), 0)}, branches={_fmt(corridor.get('branch_count'), 0)}, reconvergence nodes={_fmt(corridor.get('reconvergence_count'), 0)}, projected runtime edges={_fmt(corridor.get('projected_edge_count'), 0)}.",
                f"Closed-loop status: `{corridor.get('closed_loop_benefit_status', NOT_MEASURED)}`; strongest no-go margin: `{_fmt(corridor.get('strongest_no_go_margin_s'), 3)}` s. Mixed 1×/2× results do not activate the policy.",
                "Closed-loop arms reuse the same deterministic exogenous task stream as paired S4 counterfactuals; they do not establish generalization to a new day, seed, or order stream.",
                "Corridor support is the minimum marginal directed-edge support along a fitted path, and corridor duration is the sum of edge-level means—not a joint per-bag corridor trajectory count or duration.",
                f"The 6s detour guard is the single rounded-up bound over the measured maximum static arm gap of {_fmt(corridor.get('max_static_arm_gap_s'), 3)}s; the 2s margin run was one recorded sensitivity check, not a parameter sweep.",
                f"Published summary: `{corridor.get('report_path', NOT_MEASURED)}`; evidence-only artifact: `{corridor.get('artifact_path', NOT_MEASURED)}`.",
                "Campaign inputs: " + (", ".join(f"`{row.get('path')}`" for row in _rows(corridor_closed.get("campaigns"))) or NOT_MEASURED) + ".",
            ],
            corridor_tables,
        ),
    )
    causal_strongest = _mapping(corridor_closed.get("strongest_no_go_evidence"))
    causal_by_scale = {
        _integer(row.get("scale")): row
        for row in _rows(causal_strongest.get("comparisons"))
    }
    causal_one = _mapping(causal_by_scale.get(1))
    causal_two = _mapping(causal_by_scale.get(2))
    generic_actions = _screen_action_rows(screen)
    generic_mutations = sum(
        int(row["mutations"])
        for row in generic_actions
        if isinstance(row.get("mutations"), int)
    )
    generic_proposals = sum(
        int(row["proposals"])
        for row in generic_actions
        if isinstance(row.get("proposals"), int)
    )
    _write_text(
        REPORTS["causal"],
        _simple_report(
            "G4IRSF24 Causal Explanation",
            "MEASURED_LIMITED" if causal_strongest else NOT_MEASURED,
            [
                "The exact-release fresh race establishes the arm-level S4 business effect, but it does not attribute that effect to an individual local feature.",
                f"The selected generic EWMA/TD screen arms produced {generic_proposals} proposals and {generic_mutations} committed mutations across 144/512. Offline lookup/Bellman coverage and held-out errors are reported separately; coverage alone is not treated as a win.",
                f"The reconvergent projection changed {_fmt(_integer(causal_one.get('committed_mutations')), 0)} actions at 1× and {_fmt(_integer(causal_two.get('committed_mutations')), 0)} at 2×. Its strongest setting had mean/p95/p99 deltas of {_fmt(_number(causal_one.get('mean_delta_seconds')), 3)}/{_fmt(_number(causal_one.get('p95_delta_seconds')), 3)}/{_fmt(_number(causal_one.get('p99_delta_seconds')), 3)} seconds at 1× and {_fmt(_number(causal_two.get('mean_delta_seconds')), 3)}/{_fmt(_number(causal_two.get('p95_delta_seconds')), 3)}/{_fmt(_number(causal_two.get('p99_delta_seconds')), 3)} seconds at 2× (negative is faster), showing a load-dependent effect rather than a deployable general win.",
                "No 64–128-action H_system intervention or dedicated injected-fault campaign was run because no learning candidate passed the registered 1×/2× gate.",
            ],
        ),
    )
    final = decision["final"]
    _write_text(
        REPORTS["final"],
        _simple_report(
            "G4IRSF24 Final Joint Decision", final.get("outcome_summary", final["status"]),
            [
                f"Fresh HCA beaten: `{final['fresh_hca_beaten']}`.",
                f"Active policy: `{final['active_policy']}`.",
                f"Learning policy activated: `{final['learning_policy_activated']}`.",
                "Fixed EWMA/TD/corridor ABI copies under artifacts/policies are evidence only; they never select or activate a policy.",
                "Missing measurements remain explicit in the decision-summary JSON and are not converted to zero.",
                "Re-running this reporter from raw evidence requires the local ignored HCA lifecycle and dense-transition build outputs; committed compact datasets and reports are publication evidence, not substitutes for a fresh experiment run.",
            ],
            _md_table(_rows(decision.get("questions")), [
                ("#", "number", 0), ("Question", "question", None),
                ("Status", "status", None), ("Answer", "answer", None),
                ("Evidence / limit", "evidence", None),
            ]),
        ),
    )
    release = _mapping(_mapping(native.get("protocol")).get("release_alignment"))
    _write_text(
        NEW_IDEAS,
        f"""# G4IRSF24 New Ideas

These are bounded follow-ups exposed by measured G24 results. They do not add a second framework.

1. **Keep S4 as the deployment baseline.** It already beats fresh centralized HCA on processed mean by `{_fmt(fresh_decision.get('processed_mean_improvement_pct'))}%`; any DLP candidate must beat S4, not merely HCA.
2. **Keep the corridor pivot as no-go evidence.** Strongest supplied corridor margin is `{_fmt(corridor.get('strongest_no_go_margin_s'), 3)}` s with status `{corridor.get('closed_loop_benefit_status', NOT_MEASURED)}`. Its mixed 1×/2× result does not activate DLP; at most test one existing local congestion threshold, then stop if 1× still regresses.
3. **Treat release alignment as protocol, not bookkeeping.** Exact release minus canonical pass reaches `{_fmt(release.get('release_minus_canonical_pass_max_seconds'))}` seconds, so future 1x comparisons must reuse `{_display(RELEASE_EVIDENCE)}`.
4. **Use real mutations as the learning gate.** Zero-mutation or unsafe DLP candidates stop after screening; no extra selector layer is warranted.
5. **Separate business time from computation time.** Add one parent-observed end-to-end timer before claiming a Java/native runtime speedup; keep core wall as a diagnostic.

Current DLP/scale status: `{decision['final']['status']}`. Missing experiments remain `NOT_MEASURED`.
""",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--hca-summary", type=Path, default=DEFAULT_HCA)
    parser.add_argument("--native-race", type=Path, default=DEFAULT_NATIVE)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--screen", type=Path, default=DEFAULT_SCREEN)
    parser.add_argument("--ladder", type=Path, default=DEFAULT_LADDER)
    parser.add_argument("--scale", type=Path, default=DEFAULT_SCALE)
    parser.add_argument("--github-status", type=Path, default=DEFAULT_GITHUB_STATUS)
    parser.add_argument("--corridor-report", type=Path)
    parser.add_argument("--corridor-artifact", type=Path)
    parser.add_argument(
        "--corridor-campaign", type=Path, default=DEFAULT_CORRIDOR_CAMPAIGN,
        help="closed-loop corridor campaign; an adjacent *_margin2.json is summarized when present",
    )
    parser.add_argument("--release-lifecycle", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    work = _path(args.work)
    hca_path = _path(args.hca_summary)
    native_path = _path(args.native_race)
    state_path = _path(args.state) if args.state else work / "state.json"
    screen_path = _path(args.screen)
    ladder_path = _path(args.ladder)
    scale_path = _path(args.scale)
    github_status_path = _path(args.github_status)
    corridor_report_path = _path(args.corridor_report) if args.corridor_report else None
    corridor_artifact_path = _path(args.corridor_artifact) if args.corridor_artifact else None
    corridor_campaign_path = _path(args.corridor_campaign) if args.corridor_campaign else None
    release_lifecycle = (
        _path(args.release_lifecycle)
        if args.release_lifecycle
        else hca_path.parent / "run_01" / "segment_lifecycle.csv"
    )

    hca = _read_required(hca_path)
    native = _read_required(native_path)
    state = _read_optional(state_path)
    screen = _read_optional(screen_path)
    ladder = _read_optional(ladder_path)
    scale = _read_optional(scale_path)
    github_status = _read_optional(github_status_path)
    corridor_report = _read_optional(corridor_report_path) if corridor_report_path else None
    corridor_artifact = _read_optional(corridor_artifact_path) if corridor_artifact_path else None
    corridor_campaigns: list[Mapping[str, Any]] = []
    corridor_campaign_paths: list[Path] = []
    if corridor_campaign_path:
        primary_campaign = _read_optional(corridor_campaign_path)
        if primary_campaign is not None:
            corridor_campaigns.append(primary_campaign)
            corridor_campaign_paths.append(corridor_campaign_path)
        margin2_path = corridor_campaign_path.with_name(
            f"{corridor_campaign_path.stem}_margin2{corridor_campaign_path.suffix}"
        )
        margin2_campaign = _read_optional(margin2_path)
        if margin2_campaign is not None:
            corridor_campaigns.append(margin2_campaign)
            corridor_campaign_paths.append(margin2_path)
    if corridor_artifact is None and corridor_campaigns:
        campaign_artifact_value = corridor_campaigns[0].get("artifact_path")
        if isinstance(campaign_artifact_value, str):
            campaign_artifact_path = _path(Path(campaign_artifact_value))
            campaign_artifact = _read_optional(campaign_artifact_path)
            if campaign_artifact is not None:
                corridor_artifact_path = campaign_artifact_path
                corridor_artifact = campaign_artifact

    fresh_rows = _fresh_rows(hca, native)
    fresh_decision = _fresh_decision(fresh_rows)
    transition_rows = _transition_rows(state)
    ablation_rows = _ablation_rows(state, screen)
    scale_rows = _scale_rows(scale)
    release_count = _release_evidence(release_lifecycle)
    transition = _transition_evidence(state)
    corridor_offline = _corridor_summary(
        corridor_report, corridor_artifact, corridor_report_path, corridor_artifact_path
    )
    corridor_campaign = _corridor_campaign_summary(
        corridor_campaigns, corridor_campaign_paths
    )
    corridor = _merge_corridor_evidence(corridor_offline, corridor_campaign)
    closed_rows = _closed_rows(
        ladder, corridor_campaigns, corridor_campaign.get("strongest_no_go_margin_s", NOT_MEASURED)
    )
    policy_evidence = _publish_offline_policy_evidence(state, corridor_artifact)
    decision = _decision_summary(
        fresh_rows, fresh_decision, native, state, screen, ladder, scale,
        release_count, transition, corridor, policy_evidence, github_status,
    )

    _write_csv(TABLES["fresh"], FRESH_FIELDS, fresh_rows)
    _write_csv(TABLES["transition"], TRANSITION_FIELDS, transition_rows)
    _write_csv(TABLES["ablation"], ABLATION_FIELDS, ablation_rows)
    _write_csv(TABLES["closed"], CLOSED_FIELDS, closed_rows)
    _write_csv(TABLES["scale"], SCALE_FIELDS, scale_rows)
    _write_json(TABLES["decision"], decision)
    _write_reports(
        fresh_rows, fresh_decision, native, transition_rows, ablation_rows,
        closed_rows, scale_rows, decision, corridor, screen,
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "fresh_race": _display(TABLES["fresh"]),
                "decision": _display(TABLES["decision"]),
                "active_policy": decision["final"]["active_policy"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ReportingError) as exc:
        print(f"G4IRSF24 reporting failed: {exc}")
        raise SystemExit(2) from exc

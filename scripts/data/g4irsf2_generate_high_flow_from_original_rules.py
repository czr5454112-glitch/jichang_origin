from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ICS_ROOT = Path(r"C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目")
GOVERNANCE_DOC = ROOT / "docs" / "czr005_project_governance.md"
MAP_SOURCE = ROOT / "data" / "processed" / "maps" / "map2.json"
DEFAULT_TASK_OUTPUT = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_tasks.jsonl"
DEFAULT_MANIFEST = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_manifest.json"
AUDIT_REPORT = ROOT / "outputs" / "reports" / "g4irsf2_high_flow_generation_report.md"
OD_AUDIT = ROOT / "outputs" / "tables" / "g4irsf2_od_distribution_audit.csv"
TIME_AUDIT = ROOT / "outputs" / "tables" / "g4irsf2_time_distribution_audit.csv"
SOURCE_GOAL_AUDIT = ROOT / "outputs" / "tables" / "g4irsf2_source_goal_distribution_audit.csv"
LEG_AUDIT = ROOT / "outputs" / "tables" / "g4irsf2_leg_distribution_audit.csv"

VALID_LEVELS = {
    "original_project_generated",
    "original_rule_replay",
    "distribution_preserving_resample",
    "diagnostic_synthetic_only",
}


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return value


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _sha(value: Any) -> str:
    encoded = json.dumps(_jsonable(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Counter):
        return {str(key): item for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_ics_root(value: str | None = None) -> Path:
    candidates: list[Path] = []
    if value:
        candidates.append(Path(value))
    env_value = os.environ.get("ICS_ORIGIN_ROOT")
    if env_value:
        candidates.append(Path(env_value))
    candidates.append(DEFAULT_ICS_ROOT)
    study_parent = Path(r"C:\STUDY\民航二所项目相关")
    if study_parent.exists():
        candidates.extend(
            path
            for path in study_parent.rglob("ICS项目")
            if "代码-ICSsimulation" in {child.name for child in path.iterdir() if child.is_dir()}
        )
    for path in candidates:
        if (path / "代码-ICSsimulation" / "inputdata.txt").exists():
            return path
    return candidates[0]


def legacy_input_path(ics_origin_root: Path) -> Path:
    return ics_origin_root / "代码-ICSsimulation" / "inputdata.txt"


def _load_original_expanded(ics_origin_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _prepare_imports()
    from czr005.io.legacy_tasks import expand_tasks, parse_legacy_tasks, summarize_tasks

    input_path = legacy_input_path(ics_origin_root)
    header, raw_tasks = parse_legacy_tasks(input_path)
    expanded = [task.to_dict() for task in expand_tasks(raw_tasks)]
    return expanded, {
        "header": header,
        "raw_task_count": len(raw_tasks),
        "expanded_task_count": len(expanded),
        "summary": summarize_tasks(raw_tasks, expand_tasks(raw_tasks)),
        "input_sha256": _file_sha(input_path),
    }


def _main_claim_allowed(level: str) -> bool:
    return level in {"original_project_generated", "original_rule_replay", "distribution_preserving_resample"}


def _claim_scope(level: str) -> str:
    if level in {"original_project_generated", "original_rule_replay"}:
        return "main_claim"
    if level == "distribution_preserving_resample":
        return "limited_main_claim_with_drift_audit"
    return "debug_only_no_main_claim"


def generate_tasks(
    original: list[dict[str, Any]],
    *,
    generation_level: str,
    flow_scale: int,
    time_compression: float,
    rolling_days: int,
    seed: int,
) -> list[dict[str, Any]]:
    if generation_level not in VALID_LEVELS:
        raise ValueError(f"unknown generation level: {generation_level}")
    if generation_level in {"original_project_generated", "original_rule_replay"}:
        raise ValueError(
            f"{generation_level} is not claimed by this generator; use distribution_preserving_resample after audit"
        )
    if flow_scale < 1 or rolling_days < 1:
        raise ValueError("flow_scale and rolling_days must be positive")
    if time_compression <= 0:
        raise ValueError("time_compression must be positive")

    pass_times = [float(row["pass_time"]) for row in original]
    base_time = min(pass_times)
    max_time = max(pass_times)
    day_span = max(86400.0, max_time - base_time + 3600.0)
    id_span = max(int(row["task_id"]) for row in original) + 1
    rows: list[dict[str, Any]] = []
    copy_count = flow_scale * rolling_days
    for day in range(rolling_days):
        day_offset = day * day_span
        for replica in range(flow_scale):
            copy_index = day * flow_scale + replica
            micro_offset = replica * 0.01 + (seed % 997) * 1.0e-7
            for row in original:
                new_task_id = int(row["task_id"]) + copy_index * id_span
                pass_time = base_time + (float(row["pass_time"]) - base_time) * time_compression + day_offset + micro_offset
                std = base_time + (float(row["std"]) - base_time) * time_compression + day_offset + micro_offset
                generated = dict(row)
                generated.update(
                    {
                        "task_id": new_task_id,
                        "pallet_id": new_task_id,
                        "segment_id": f"{new_task_id}:{row['leg']}:g4irsf2_c{copy_index}",
                        "pass_time": pass_time,
                        "std": std,
                        "original_entry_time": base_time
                        + (float(row["original_entry_time"]) - base_time) * time_compression
                        + day_offset
                        + micro_offset,
                        "source_line": int(row["source_line"]),
                        "generation_level": generation_level,
                        "generation_copy_index": copy_index,
                        "topology_changed": False,
                    }
                )
                rows.append(generated)
    rows.sort(key=lambda item: (float(item["pass_time"]), int(item["task_id"]), str(item["segment_id"])))
    if len(rows) != len(original) * copy_count:
        raise AssertionError("generated task count mismatch")
    return rows


def _counter(rows: list[dict[str, Any]], key_fn: Any) -> Counter[Any]:
    return Counter(key_fn(row) for row in rows)


def _dist_rows(original: Counter[Any], generated: Counter[Any], *, dimension: str) -> list[dict[str, Any]]:
    original_total = sum(original.values())
    generated_total = sum(generated.values())
    keys = sorted(set(original) | set(generated), key=str)
    rows = []
    for key in keys:
        original_share = original[key] / original_total if original_total else 0.0
        generated_share = generated[key] / generated_total if generated_total else 0.0
        rows.append(
            {
                "dimension": dimension,
                "bucket": key,
                "original_count": original[key],
                "generated_count": generated[key],
                "original_share": original_share,
                "generated_share": generated_share,
                "abs_delta": abs(original_share - generated_share),
                "claim_level": "distribution_preserving_resample",
            }
        )
    return rows


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def _ks_statistic(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    left_sorted = sorted(left)
    right_sorted = sorted(right)
    i = j = 0
    max_delta = 0.0
    while i < len(left_sorted) and j < len(right_sorted):
        value = min(left_sorted[i], right_sorted[j])
        while i < len(left_sorted) and left_sorted[i] <= value:
            i += 1
        while j < len(right_sorted) and right_sorted[j] <= value:
            j += 1
        max_delta = max(max_delta, abs(i / len(left_sorted) - j / len(right_sorted)))
    return max_delta


def write_distribution_audits(original: list[dict[str, Any]], generated: list[dict[str, Any]], generation_level: str) -> dict[str, Any]:
    od_rows = _dist_rows(_counter(original, lambda row: (row["start"], row["goal"])), _counter(generated, lambda row: (row["start"], row["goal"])), dimension="start_goal")
    leg_rows = _dist_rows(_counter(original, lambda row: row["leg"]), _counter(generated, lambda row: row["leg"]), dimension="leg")
    source_rows = _dist_rows(_counter(original, lambda row: row["start"]), _counter(generated, lambda row: row["start"]), dimension="source")
    goal_rows = _dist_rows(_counter(original, lambda row: row["goal"]), _counter(generated, lambda row: row["goal"]), dimension="goal")
    original_rel = [float(row["pass_time"]) - min(float(item["pass_time"]) for item in original) for row in original]
    generated_rel = [float(row["pass_time"]) % 86400.0 for row in generated]
    original_mod = [float(row["pass_time"]) % 86400.0 for row in original]
    time_rows = [
        {
            "metric": "original_count",
            "original_value": len(original),
            "generated_value": len(generated),
            "claim_level": generation_level,
        },
        {
            "metric": "pass_time_min",
            "original_value": min(float(row["pass_time"]) for row in original),
            "generated_value": min(float(row["pass_time"]) for row in generated),
            "claim_level": generation_level,
        },
        {
            "metric": "pass_time_max",
            "original_value": max(float(row["pass_time"]) for row in original),
            "generated_value": max(float(row["pass_time"]) for row in generated),
            "claim_level": generation_level,
        },
        {
            "metric": "pass_time_p50_mod_day",
            "original_value": statistics.median(original_mod),
            "generated_value": statistics.median(generated_rel),
            "claim_level": generation_level,
        },
        {
            "metric": "pass_time_p95_mod_day",
            "original_value": _quantile(original_mod, 0.95),
            "generated_value": _quantile(generated_rel, 0.95),
            "claim_level": generation_level,
        },
        {
            "metric": "ks_statistic_mod_day",
            "original_value": 0.0,
            "generated_value": _ks_statistic(original_mod, generated_rel),
            "claim_level": generation_level,
        },
        {
            "metric": "relative_time_span",
            "original_value": max(original_rel) - min(original_rel),
            "generated_value": max(generated_rel) - min(generated_rel),
            "claim_level": generation_level,
        },
    ]
    _write_csv(OD_AUDIT, od_rows, ["dimension", "bucket", "original_count", "generated_count", "original_share", "generated_share", "abs_delta", "claim_level"])
    _write_csv(SOURCE_GOAL_AUDIT, source_rows + goal_rows, ["dimension", "bucket", "original_count", "generated_count", "original_share", "generated_share", "abs_delta", "claim_level"])
    _write_csv(LEG_AUDIT, leg_rows, ["dimension", "bucket", "original_count", "generated_count", "original_share", "generated_share", "abs_delta", "claim_level"])
    _write_csv(TIME_AUDIT, time_rows, ["metric", "original_value", "generated_value", "claim_level"])
    return {
        "od_max_abs_distribution_delta": max((float(row["abs_delta"]) for row in od_rows), default=0.0),
        "source_goal_max_abs_distribution_delta": max((float(row["abs_delta"]) for row in source_rows + goal_rows), default=0.0),
        "leg_max_abs_distribution_delta": max((float(row["abs_delta"]) for row in leg_rows), default=0.0),
        "time_ks_mod_day": next(row["generated_value"] for row in time_rows if row["metric"] == "ks_statistic_mod_day"),
    }


def write_manifest(
    *,
    path: Path,
    output: Path,
    ics_origin_root: Path,
    generation_level: str,
    flow_scale: int,
    time_compression: float,
    rolling_days: int,
    generated: list[dict[str, Any]],
    original_meta: dict[str, Any],
    drift: dict[str, Any],
) -> dict[str, Any]:
    manifest = {
        "topology_changed": False,
        "map_source": str(MAP_SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "governance_doc": str(GOVERNANCE_DOC.relative_to(ROOT)).replace("\\", "/"),
        "ics_origin_root": str(ics_origin_root),
        "generation_level": generation_level,
        "flow_scale": flow_scale,
        "time_compression": time_compression,
        "rolling_days": rolling_days,
        "source_rules_audit": "outputs/reports/g4irsf2_original_ics_data_generation_audit.md",
        "synthetic_flow": generation_level == "diagnostic_synthetic_only",
        "main_claim_allowed": _main_claim_allowed(generation_level),
        "claim_scope": _claim_scope(generation_level),
        "task_output": str(output.relative_to(ROOT)).replace("\\", "/"),
        "task_count": len(generated),
        "raw_original_task_count": original_meta["raw_task_count"],
        "expanded_original_task_count": original_meta["expanded_task_count"],
        "original_input_sha256": original_meta["input_sha256"],
        "task_output_sha256": _file_sha(output),
        "od_distribution_hash": _sha(_counter(generated, lambda row: (row["start"], row["goal"]))),
        "time_distribution_hash": _sha(
            {
                "min": min(float(row["pass_time"]) for row in generated),
                "max": max(float(row["pass_time"]) for row in generated),
                "p50": statistics.median(float(row["pass_time"]) for row in generated),
                "p95": _quantile([float(row["pass_time"]) for row in generated], 0.95),
            }
        ),
        "input_schema_hash": _sha(sorted(generated[0].keys()) if generated else []),
        "drift_audit": {
            "od_distribution_audit": str(OD_AUDIT.relative_to(ROOT)).replace("\\", "/"),
            "time_distribution_audit": str(TIME_AUDIT.relative_to(ROOT)).replace("\\", "/"),
            "source_goal_distribution_audit": str(SOURCE_GOAL_AUDIT.relative_to(ROOT)).replace("\\", "/"),
            "leg_distribution_audit": str(LEG_AUDIT.relative_to(ROOT)).replace("\\", "/"),
            **drift,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def write_report(manifest: dict[str, Any]) -> None:
    AUDIT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF2 High-Flow Generation Report",
                "",
                f"governance_doc: {manifest['governance_doc']}",
                "topology_changed: false",
                f"data_generation_rule_source: {manifest['generation_level']}",
                "",
                "## Decision",
                "",
                f"Generation level is `{manifest['generation_level']}` with claim scope `{manifest['claim_scope']}`.",
                "This generator does not invent new OD pairs or random pass_time/std distributions. It reuses the audited original `inputdata.txt` distribution and records drift tables.",
                "",
                "## Manifest",
                "",
                f"Task output: `{manifest['task_output']}`",
                f"Task count: `{manifest['task_count']}`",
                f"Main claim allowed: `{manifest['main_claim_allowed']}`",
                "",
                "Level C remains limited: it can support fixed-map high-flow stress claims only with the drift caveat, not a paper-grade original-generator claim.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_generation(args: argparse.Namespace) -> dict[str, Any]:
    ics_origin_root = resolve_ics_root(args.ics_origin_root)
    if not legacy_input_path(ics_origin_root).exists():
        raise FileNotFoundError(f"original ICS inputdata.txt is missing under {ics_origin_root}")
    original, meta = _load_original_expanded(ics_origin_root)
    generated = generate_tasks(
        original,
        generation_level=args.generation_level,
        flow_scale=args.flow_scale,
        time_compression=args.time_compression,
        rolling_days=args.rolling_days,
        seed=args.seed,
    )
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    _write_jsonl(output, generated)
    drift = write_distribution_audits(original, generated, args.generation_level)
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest = write_manifest(
        path=manifest_path,
        output=output,
        ics_origin_root=ics_origin_root,
        generation_level=args.generation_level,
        flow_scale=args.flow_scale,
        time_compression=args.time_compression,
        rolling_days=args.rolling_days,
        generated=generated,
        original_meta=meta,
        drift=drift,
    )
    write_report(manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate G4IRSF2 high-flow tasks from audited original ICS rules.")
    parser.add_argument("--ics-origin-root", default=None)
    parser.add_argument("--generation-level", choices=sorted(VALID_LEVELS), default="distribution_preserving_resample")
    parser.add_argument("--flow-scale", type=int, choices=[1, 2, 4, 8, 16, 32, 64, 128], default=8)
    parser.add_argument("--time-compression", type=float, choices=[1.0, 0.75, 0.5, 0.25, 0.1, 0.05], default=1.0)
    parser.add_argument("--rolling-days", type=int, choices=[1, 2, 4, 7, 14], default=1)
    parser.add_argument("--seed", type=int, default=20260703)
    parser.add_argument("--output", default=str(DEFAULT_TASK_OUTPUT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    return parser


def main() -> None:
    manifest = run_generation(build_parser().parse_args())
    print(
        "g4irsf2 high-flow generation complete: "
        f"level={manifest['generation_level']} tasks={manifest['task_count']} "
        f"main_claim_allowed={manifest['main_claim_allowed']}"
    )


if __name__ == "__main__":
    main()

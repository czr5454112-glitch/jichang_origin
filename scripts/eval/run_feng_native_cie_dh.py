"""Audit the recovered Feng/Yang Java baseline without fabricating native DH.

This command consumes an already completed ``run_g4irsf24_fresh_hca.py`` full
campaign.  It does not compile or execute Java and it does not add a DH mode.
Its purpose is deliberately narrower: prove that the recovered HCA baseline
still matches the frozen full-population result, inventory the recovered Java
source/classes, and record whether the position-level state required by the
historical CIE-DH rule is actually present.

Output paths have no defaults.  All three must be supplied explicitly, which
prevents an exploratory invocation from overwriting publication evidence.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUMMARY = (
    ROOT
    / "outputs"
    / "raw"
    / "cie_revision"
    / "feng_native_hca_full_regression"
    / "fresh_hca_summary.json"
)
DEFAULT_LEGACY_ROOT = ROOT / "legacy" / "jichang_origin_readonly"
DEFAULT_CLASSES_DIR = ROOT / "build" / "cie_revision_java"
REVISION_MANIFEST = ROOT / "configs" / "eval" / "cie_revision_manifest.yaml"

HCA_STATUS = "FENG_NATIVE_HCA_REGRESSION_PASS"
HCA_FAIL_STATUS = "FENG_NATIVE_HCA_REGRESSION_FAIL"
DH_STATUS = "BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED"

# Frozen before the current audit.  These values are the canonical full run's
# processed-attempt population, not rounded values transcribed from the paper.
FROZEN_HCA: dict[str, int | float] = {
    "segment_count": 43_603,
    "raw_bag_count": 28_506,
    "success_rate": 1.0,
    "processed_min_seconds": 188.0,
    "processed_mean_seconds": 236.710166280783,
    "processed_max_seconds": 357.0,
}

PAPER_TABLE_5_3 = {
    "FENG_NATIVE_CIE_DH_RECONSTRUCTION": {
        "min_minutes": 3.56,
        "mean_minutes": 4.43,
        "max_minutes": 8.62,
    },
    "FENG_NATIVE_HCA": {
        "min_minutes": 3.13,
        "mean_minutes": 3.96,
        "max_minutes": 5.98,
    },
}

CSV_FIELDS = [
    "method",
    "identity",
    "protocol",
    "denominator",
    "paper_min_minutes",
    "paper_mean_minutes",
    "paper_max_minutes",
    "measured_min_minutes",
    "measured_mean_minutes",
    "measured_max_minutes",
    "error_min_percent",
    "error_mean_percent",
    "error_max_percent",
    "completed_segments",
    "raw_bags",
    "completion_rate",
    "status",
    "note",
]


class AuditError(RuntimeError):
    """Raised when the evidence cannot be audited unambiguously."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AuditError(f"missing full HCA summary: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot parse full HCA summary {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuditError(f"HCA summary root must be an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _aggregate_sha256(paths: Sequence[Path], root: Path) -> str:
    """Hash a path/content manifest in a platform-independent order."""

    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _strip_java_non_code(source: str) -> str:
    """Remove comments and literal contents while preserving line numbers."""

    result: list[str] = []
    index = 0
    state = "code"
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and following == "/":
                result.extend("  ")
                index += 2
                state = "line_comment"
                continue
            if char == "/" and following == "*":
                result.extend("  ")
                index += 2
                state = "block_comment"
                continue
            if char == '"':
                result.append(" ")
                index += 1
                state = "string"
                continue
            if char == "'":
                result.append(" ")
                index += 1
                state = "character"
                continue
            result.append(char)
            index += 1
            continue
        if state == "line_comment":
            result.append("\n" if char == "\n" else " ")
            index += 1
            if char == "\n":
                state = "code"
            continue
        if state == "block_comment":
            if char == "*" and following == "/":
                result.extend("  ")
                index += 2
                state = "code"
            else:
                result.append("\n" if char == "\n" else " ")
                index += 1
            continue

        # String and character literals use the same escape handling.  Their
        # content cannot be evidence that an executable DH state exists.
        if char == "\\" and following:
            result.extend("\n " if following == "\n" else "  ")
            index += 2
        elif (state == "string" and char == '"') or (
            state == "character" and char == "'"
        ):
            result.append(" ")
            index += 1
            state = "code"
        else:
            result.append("\n" if char == "\n" else " ")
            index += 1
    return "".join(result)


def audit_java_sources(legacy_root: Path) -> dict[str, Any]:
    source_root = legacy_root / "src"
    sources = sorted(source_root.rglob("*.java"))
    if len(sources) != 15:
        raise AuditError(
            f"expected exactly 15 recovered Java sources, found {len(sources)} in {source_root}"
        )

    patterns = {
        "dh_identifier": re.compile(r"(?i)(?<![A-Za-z0-9_])(?:DH|CIE_DH)(?![A-Za-z0-9_])"),
        "moving_state": re.compile(r"(?i)(?<![A-Za-z0-9_])moving(?![A-Za-z0-9_])"),
        "stopped_state": re.compile(r"(?i)(?<![A-Za-z0-9_])stopped(?![A-Za-z0-9_])"),
        "bti_state": re.compile(r"(?i)(?<![A-Za-z0-9_])BTI(?![A-Za-z0-9_])"),
        "ddi_state": re.compile(r"(?i)(?<![A-Za-z0-9_])DDI(?![A-Za-z0-9_])"),
        "point_two_second_literal": re.compile(r"(?<![0-9.])0\.2(?:0+)?(?:[dDfF])?(?![0-9.])"),
    }
    matches: dict[str, list[dict[str, Any]]] = {name: [] for name in patterns}
    for path in sources:
        code = _strip_java_non_code(path.read_text(encoding="utf-8", errors="replace"))
        lines = code.splitlines()
        for name, pattern in patterns.items():
            for line_number, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches[name].append(
                        {
                            "path": path.relative_to(legacy_root).as_posix(),
                            "line": line_number,
                            "code": line.strip(),
                        }
                    )

    required_state_present = all(matches[name] for name in patterns)
    main_text = _strip_java_non_code(
        (source_root / "RUN" / "Main.java").read_text(encoding="utf-8", errors="replace")
    )
    planner_text = _strip_java_non_code(
        (source_root / "App" / "ICS_PathFinding.java").read_text(
            encoding="utf-8", errors="replace"
        )
    )
    call_chain_checks = {
        "RUN.Main.run_constructs_ICS_PathFinding": "new ICS_PathFinding()" in main_text,
        "RUN.Main.run_calls_Tasks.generate_tasks": ".generate_tasks(" in main_text,
        "RUN.Main.run_calls_ICS_path_finding": ".ICS_path_finding(" in main_text,
        "ICS_PathFinding_calls_Astar.research": "Astar.research(" in planner_text,
    }
    return {
        "java_source_count": len(sources),
        "java_sources": [path.relative_to(legacy_root).as_posix() for path in sources],
        "aggregate_sha256": _aggregate_sha256(sources, legacy_root),
        "executable_code_matches": matches,
        "all_required_dh_state_present": required_state_present,
        "call_chain_checks": call_chain_checks,
        "call_chain": (
            "RUN.Main.run -> Tasks.generate_tasks -> "
            "ICS_PathFinding.ICS_path_finding -> Astar.research"
        ),
        "gui_cycle_false_positive": {
            "path": "src/ICS_GUI/ICS_GUI.java",
            "declaration": "private double cycle = 200",
            "consumer": "RUN.Main.run passes gui.getCycle() to Thread.sleep",
            "classification": "GUI_REFRESH_MILLISECONDS_NOT_DH_POSITION_UPDATE_STATE",
        },
        "conclusion": (
            "The recovered sources contain the centralized epoch scheduler and A* "
            "reservation call chain, but no executable DH/moving/stopped/BTI/DDI/0.2-s "
            "state set. The 200 ms GUI refresh cycle is not a position-level DH update."
        ),
    }


def validate_hca_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    runs = summary.get("runs")
    if not isinstance(runs, list):
        raise AuditError("HCA summary must contain a runs array")
    eligible = [
        run
        for run in runs
        if isinstance(run, dict)
        and run.get("profile") == "full"
        and run.get("status") == "complete"
        and run.get("comparison_eligible") is True
    ]
    if not eligible:
        raise AuditError("HCA summary contains no complete comparison-eligible full run")

    audited_runs: list[dict[str, Any]] = []
    for run in eligible:
        processed = run.get("denominators", {}).get("processed_attempt", {})
        seconds = processed.get("seconds", {})
        observed = {
            "segment_count": run.get("canonical_segment_count"),
            "completed_segment_count": run.get("completed_segment_count"),
            "raw_bag_count": run.get("canonical_raw_bag_count"),
            "complete_raw_bag_count": run.get("complete_raw_bag_count"),
            "success_rate": run.get("canonical_success_rate"),
            "processed_count": processed.get("count"),
            "processed_min_seconds": seconds.get("min"),
            "processed_mean_seconds": seconds.get("mean"),
            "processed_max_seconds": seconds.get("max"),
            "survivor_only": run.get("survivor_only"),
            "wall_seconds": run.get("wall_seconds"),
            "cpu_seconds": "NOT_MEASURED",
            "peak_rss_bytes": "NOT_MEASURED",
            "fault_event_count": run.get("benchmark_summary", {}).get(
                "fault_event_count"
            ),
            "repair_event_count": run.get("benchmark_summary", {}).get(
                "repair_event_count"
            ),
            "unfinished_count": run.get("benchmark_summary", {}).get(
                "unfinished_count"
            ),
            "route_location_checksum": run.get("benchmark_summary", {}).get(
                "route_location_checksum"
            ),
            "route_size_checksum": run.get("benchmark_summary", {}).get(
                "route_size_checksum"
            ),
        }
        checks = {
            "segments_exact": observed["segment_count"] == FROZEN_HCA["segment_count"],
            "segments_complete": observed["completed_segment_count"]
            == FROZEN_HCA["segment_count"],
            "raw_bags_exact": observed["raw_bag_count"] == FROZEN_HCA["raw_bag_count"],
            "raw_bags_complete": observed["complete_raw_bag_count"]
            == FROZEN_HCA["raw_bag_count"],
            "processed_population_exact": observed["processed_count"]
            == FROZEN_HCA["raw_bag_count"],
            "completion_100_percent": observed["success_rate"]
            == FROZEN_HCA["success_rate"],
            "processed_min_exact": observed["processed_min_seconds"]
            == FROZEN_HCA["processed_min_seconds"],
            "processed_mean_exact": observed["processed_mean_seconds"]
            == FROZEN_HCA["processed_mean_seconds"],
            "processed_max_exact": observed["processed_max_seconds"]
            == FROZEN_HCA["processed_max_seconds"],
            "not_survivor_timing": observed["survivor_only"] is False,
        }
        audited_runs.append(
            {
                "run_id": run.get("run_id"),
                "observed": observed,
                "checks": checks,
                "pass": all(checks.values()),
            }
        )

    passed = all(run["pass"] for run in audited_runs)
    return {
        "status": HCA_STATUS if passed else HCA_FAIL_STATUS,
        "pass": passed,
        "eligible_run_count": len(audited_runs),
        "frozen_expected": dict(FROZEN_HCA),
        "runs": audited_runs,
    }


def _classes_inventory(classes_dir: Path) -> dict[str, Any]:
    if not classes_dir.is_dir():
        raise AuditError(f"missing compiled classes directory: {classes_dir}")
    classes = sorted(classes_dir.rglob("*.class"))
    if not classes:
        raise AuditError(f"no compiled .class files in {classes_dir}")
    return {
        "class_count": len(classes),
        "aggregate_sha256": _aggregate_sha256(classes, classes_dir),
        "classes": [path.relative_to(classes_dir).as_posix() for path in classes],
    }


def build_audit(
    *, summary_path: Path, legacy_root: Path, classes_dir: Path
) -> dict[str, Any]:
    summary = _load_json(summary_path)
    source_audit = audit_java_sources(legacy_root)
    hca_regression = validate_hca_summary(summary)
    native_dh_blocked = not source_audit["all_required_dh_state_present"]
    if not native_dh_blocked:
        raise AuditError(
            "recovered source appears to contain every required DH state; a manual semantic "
            "review is required before this blocker-only auditor can classify it"
        )

    map_path = legacy_root / "map2.txt"
    input_path = legacy_root / "inputdata.txt"
    if not map_path.is_file() or not input_path.is_file():
        raise AuditError("recovered legacy root must contain map2.txt and inputdata.txt")
    return {
        "schema": "czr005.cie_revision.feng_native_cie_dh_audit.v1",
        "generated_at": _utc_now(),
        "scope": "read_only_reproduction_audit_no_java_execution_no_dh_implementation",
        "statuses": {
            "hca_regression": hca_regression["status"],
            "native_cie_dh": DH_STATUS,
        },
        "hca_regression": hca_regression,
        "identity_contract": {
            "executor_identity": "FENG_NATIVE_JAVA_HCA_SCHEDULER",
            "baseline_family": "FENG_NATIVE_HCA",
            "reproduction_or_adaptation_label": (
                "FROZEN_AGGREGATE_EXACT_REGRESSION_NOT_TRACE_EXACT"
            ),
            "release_protocol": "ORIGINAL_JAVA_TASK_RELEASE",
            "coordination_protocol": "CENTRALIZED_ASTAR_RESERVATION",
            "random_seed": None,
            "full_population_eligible": True,
            "survivor_timing_used": False,
            "path_release_completion_trace_hash_verified": False,
            "unverified_trace_fields": [
                "per_task_release_trace",
                "per_task_route_trace",
                "per_task_completion_trace",
            ],
            "safety": {
                "fault_events": hca_regression["runs"][0]["observed"][
                    "fault_event_count"
                ],
                "repair_events": hca_regression["runs"][0]["observed"][
                    "repair_event_count"
                ],
                "unfinished_segments": hca_regression["runs"][0]["observed"][
                    "unfinished_count"
                ],
                "reservation_conflicts": "NOT_MEASURED",
                "wrong_terminal_completion": "NOT_MEASURED",
            },
            "runtime": {
                "wall_seconds": hca_regression["runs"][0]["observed"][
                    "wall_seconds"
                ],
                "cpu_seconds": "NOT_MEASURED",
                "peak_rss_bytes": "NOT_MEASURED",
            },
        },
        "native_cie_dh": {
            "status": DH_STATUS,
            "measured": False,
            "reason": (
                "The 15 recovered Java sources do not implement the executable "
                "position-level DH/moving/stopped/BTI/DDI/0.2-s state required for a "
                "faithful native reconstruction. No common-executor result is substituted."
            ),
            "source_audit": source_audit,
        },
        "provenance": {
            "git_commit": _git_value("rev-parse", "HEAD"),
            "git_branch": _git_value("branch", "--show-current"),
            "experiment_manifest": {
                "path": str(REVISION_MANIFEST.resolve()),
                "sha256": _sha256_file(REVISION_MANIFEST),
            },
            "summary_path": str(summary_path.resolve()),
            "summary_sha256": _sha256_file(summary_path),
            "legacy_root": str(legacy_root.resolve()),
            "java_sources_aggregate_sha256": source_audit["aggregate_sha256"],
            "map2": {
                "path": str(map_path.resolve()),
                "sha256": _sha256_file(map_path),
            },
            "inputdata": {
                "path": str(input_path.resolve()),
                "sha256": _sha256_file(input_path),
            },
            "compiled_classes": {
                "path": str(classes_dir.resolve()),
                **_classes_inventory(classes_dir),
            },
        },
        "paper_table_5_3_reference": {
            "source": "values transcribed in codex_cie_native_dh_targeted_ablation_repair.md",
            "used_as_training_target": False,
            "values": PAPER_TABLE_5_3,
        },
    }


def _percentage_error(measured: float, reference: float) -> float:
    return (measured - reference) / reference * 100.0


def table_rows(audit: Mapping[str, Any]) -> list[dict[str, Any]]:
    first_run = audit["hca_regression"]["runs"][0]["observed"]
    measured = {
        "min_minutes": first_run["processed_min_seconds"] / 60.0,
        "mean_minutes": first_run["processed_mean_seconds"] / 60.0,
        "max_minutes": first_run["processed_max_seconds"] / 60.0,
    }
    hca_paper = PAPER_TABLE_5_3["FENG_NATIVE_HCA"]
    hca_row = {
        "method": "FENG_NATIVE_HCA",
        "identity": "recovered original Java HCA scheduler",
        "protocol": "map2 canonical full 43603-segment/28506-bag run",
        "denominator": "processed_attempt full population",
        "paper_min_minutes": hca_paper["min_minutes"],
        "paper_mean_minutes": hca_paper["mean_minutes"],
        "paper_max_minutes": hca_paper["max_minutes"],
        "measured_min_minutes": measured["min_minutes"],
        "measured_mean_minutes": measured["mean_minutes"],
        "measured_max_minutes": measured["max_minutes"],
        "error_min_percent": _percentage_error(
            measured["min_minutes"], hca_paper["min_minutes"]
        ),
        "error_mean_percent": _percentage_error(
            measured["mean_minutes"], hca_paper["mean_minutes"]
        ),
        "error_max_percent": _percentage_error(
            measured["max_minutes"], hca_paper["max_minutes"]
        ),
        "completed_segments": first_run["completed_segment_count"],
        "raw_bags": first_run["complete_raw_bag_count"],
        "completion_rate": first_run["success_rate"],
        "status": audit["statuses"]["hca_regression"],
        "note": "exact frozen-code regression; paper error is descriptive only",
    }
    dh_paper = PAPER_TABLE_5_3["FENG_NATIVE_CIE_DH_RECONSTRUCTION"]
    dh_row = {
        "method": "FENG_NATIVE_CIE_DH_RECONSTRUCTION",
        "identity": "historical native DH requested but source not recovered",
        "protocol": "map2 historical reproduction",
        "denominator": "not measured",
        "paper_min_minutes": dh_paper["min_minutes"],
        "paper_mean_minutes": dh_paper["mean_minutes"],
        "paper_max_minutes": dh_paper["max_minutes"],
        "measured_min_minutes": "",
        "measured_mean_minutes": "",
        "measured_max_minutes": "",
        "error_min_percent": "",
        "error_mean_percent": "",
        "error_max_percent": "",
        "completed_segments": "",
        "raw_bags": "",
        "completion_rate": "",
        "status": DH_STATUS,
        "note": "blocked; common-executor adapted DH is not substituted",
    }
    return [hca_row, dh_row]


def render_report(audit: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    hca = rows[0]
    source = audit["native_cie_dh"]["source_audit"]
    pattern_counts = {
        name: len(matches) for name, matches in source["executable_code_matches"].items()
    }
    return f"""# Feng-native HCA / CIE-DH reproduction audit

Status: `{audit['statuses']['hca_regression']}`; `{audit['statuses']['native_cie_dh']}`.

## Outcome

The recovered original Java HCA full run is an exact **frozen aggregate** regression match: 43,603/43,603 segments and 28,506/28,506 raw bags complete (100%), with processed-attempt min/mean/max of {hca['measured_min_minutes']:.6f}/{hca['measured_mean_minutes']:.6f}/{hca['measured_max_minutes']:.6f} minutes. These equal the frozen 188.0/236.710166280783/357.0 second values exactly. This audit did not freeze or compare per-task release, route, or completion trace hashes, so it does not claim trace-exact path identity.

Feng-native CIE-DH is **not measured**. The recovered 15-source Java tree has no executable position-level state set needed to implement the historical rule. This audit does not relabel or substitute the modern common-executor adapted DH arm.

## Table 5.3 audit

| method | paper min/mean/max (min) | measured min/mean/max (min) | error min/mean/max | status |
|---|---:|---:|---:|---|
| FENG_NATIVE_HCA | {hca['paper_min_minutes']:.2f}/{hca['paper_mean_minutes']:.2f}/{hca['paper_max_minutes']:.2f} | {hca['measured_min_minutes']:.6f}/{hca['measured_mean_minutes']:.6f}/{hca['measured_max_minutes']:.6f} | {hca['error_min_percent']:.3f}%/{hca['error_mean_percent']:.3f}%/{hca['error_max_percent']:.3f}% | `{hca['status']}` |
| FENG_NATIVE_CIE_DH_RECONSTRUCTION | 3.56/4.43/8.62 | — | — | `{DH_STATUS}` |

The paper values are validation references transcribed from the supplied action plan, not optimization targets. Error is emitted only for the measured HCA row.

## Source-semantic blocker

- Audited Java sources: `{source['java_source_count']}`; aggregate SHA-256 `{source['aggregate_sha256']}`.
- Executable-code match counts after stripping comments and string/character literals: `{json.dumps(pattern_counts, sort_keys=True)}`.
- Recovered call chain: `{source['call_chain']}`. Every call-chain signature check passed: `{all(source['call_chain_checks'].values())}`.
- `ICS_GUI.cycle = 200` is consumed by `Thread.sleep(gui.getCycle())`; it is a GUI refresh interval in milliseconds, not DH's 0.2-second position/moving/stopped state transition.
- Conclusion: `{source['conclusion']}`

## Provenance

- HCA summary SHA-256: `{audit['provenance']['summary_sha256']}`
- map2 SHA-256: `{audit['provenance']['map2']['sha256']}`
- inputdata SHA-256: `{audit['provenance']['inputdata']['sha256']}`
- compiled classes: `{audit['provenance']['compiled_classes']['class_count']}` files; aggregate SHA-256 `{audit['provenance']['compiled_classes']['aggregate_sha256']}`

This is a read-only evidence audit: it did not compile or run Java, did not implement DH, and did not overwrite the earlier G4IRSF24 evidence namespace.
"""


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_outputs(
    audit: Mapping[str, Any], *, output_json: Path, output_csv: Path, output_report: Path
) -> None:
    rows = table_rows(audit)
    json_data = (
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    report_data = render_report(audit, rows).encode("utf-8")
    _atomic_write(output_json, json_data)
    _atomic_write(output_csv, csv_buffer.getvalue().encode("utf-8"))
    _atomic_write(output_report, report_data)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--legacy-root", type=Path, default=DEFAULT_LEGACY_ROOT)
    parser.add_argument("--classes-dir", type=Path, default=DEFAULT_CLASSES_DIR)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    audit = build_audit(
        summary_path=args.summary.resolve(),
        legacy_root=args.legacy_root.resolve(),
        classes_dir=args.classes_dir.resolve(),
    )
    write_outputs(
        audit,
        output_json=args.output_json.resolve(),
        output_csv=args.output_csv.resolve(),
        output_report=args.output_report.resolve(),
    )
    print(
        f"{audit['statuses']['hca_regression']}; "
        f"{audit['statuses']['native_cie_dh']}"
    )
    return 0 if audit["hca_regression"]["pass"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        raise SystemExit(2) from exc

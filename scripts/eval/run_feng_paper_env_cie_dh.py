"""Compile, run, and aggregate the Feng-paper-environment CIE-DH reconstruction.

Python is deliberately limited to orchestration and aggregation.  The routing
state machine is implemented by ``App.FengDhBenchmark`` in Java.  Every run
reads the frozen legacy ``map2.txt`` and ``inputdata.txt`` directly; this module
does not translate either input through the current C++ executor or map adapter.

The primary coefficient pair is derived from the physical headway time.  The
``sensitivity`` command executes the complete pre-frozen 3x3 envelope and never
selects a cell from its outcome.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "configs" / "eval" / "feng_cie_dh_reconstruction_manifest.yaml"
JAVA_SOURCE_DIR = ROOT / "benchmarks" / "java" / "feng_cie_dh" / "App"
MAIN_CLASS = "App.FengDhBenchmark"
SENSITIVITY_TABLE = ROOT / "outputs" / "tables" / "feng_cie_dh_sensitivity_envelope.csv"
SENSITIVITY_FIGURE = ROOT / "outputs" / "figures" / "feng_cie_dh_sensitivity_envelope.png"
FIXED_EXTERNAL_HORIZON_SECONDS = 98_259.0
COMPILE_IDENTITY_NAME = "feng_cie_dh_compile_identity.json"

EXPECTED_MAP_SHA256 = "55f578cb4b8fcc61f5b13963fcb8546aca91e517ea6f8ff4a7361670f1b03f8f"
EXPECTED_INPUT_SHA256 = "0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87"
EXPECTED_TABLE53_SCHEDULE_SHA256 = (
    "a3db0d3f495870437414af0b46a0a140f7cafe8111b40222ca59fcd78e7d4d86"
)
EXPECTED_TABLE53_SCHEDULE_ROWS = 43_603
EXPECTED_LEGACY_SOURCE_AGGREGATE_SHA256 = (
    "b0c7545abad1705eba9255527d39a864007bd576c9edbc9cb872a51e6acc9c25"
)

KNOWN_RUN_FILES = (
    "summary.csv",
    "bags.csv",
    "segments.csv",
    "trace.csv",
    "event_summary.csv",
    "stdout.txt",
    "stderr.txt",
    "runner_status.json",
)


class FengDhRunError(RuntimeError):
    """Raised when reconstruction identity or output is not unambiguous."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _aggregate_sha256(paths: Iterable[Path], root: Path) -> str:
    digest = hashlib.sha256()
    ordered = sorted(paths, key=lambda path: path.relative_to(root).as_posix())
    for path in ordered:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FengDhRunError(f"missing Java output: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise FengDhRunError(f"missing reconstruction manifest: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FengDhRunError(f"manifest root must be a mapping: {path}")
    if payload.get("schema") != "czr005.feng_paper_env_cie_dh_reconstruction.v1":
        raise FengDhRunError(f"unexpected reconstruction manifest schema: {path}")
    return payload


def verify_legacy_identity(
    *,
    map_path: Path,
    input_path: Path,
    legacy_root: Path,
    require_original_input: bool = True,
    expected_map_sha256: str | None = None,
    expected_input_sha256: str | None = None,
) -> dict[str, Any]:
    """Fail closed if the old map, demand, or frozen source mirror drifted."""

    if not map_path.is_file() or not input_path.is_file():
        raise FengDhRunError("the frozen Feng map and inputdata files must exist")
    source_root = legacy_root / "src"
    sources = sorted(source_root.rglob("*.java"))
    if len(sources) != 15:
        raise FengDhRunError(
            f"expected 15 frozen Feng Java sources, found {len(sources)} in {source_root}"
        )
    observed = {
        "map_sha256": _sha256_file(map_path),
        "input_sha256": _sha256_file(input_path),
        "legacy_java_source_count": len(sources),
        "legacy_java_source_aggregate_sha256": _aggregate_sha256(sources, legacy_root),
    }
    expected = {
        "map_sha256": expected_map_sha256 or EXPECTED_MAP_SHA256,
        "legacy_java_source_aggregate_sha256": EXPECTED_LEGACY_SOURCE_AGGREGATE_SHA256,
    }
    if require_original_input:
        expected["input_sha256"] = expected_input_sha256 or EXPECTED_INPUT_SHA256
    elif expected_input_sha256 is not None:
        expected["input_sha256"] = expected_input_sha256
    drift = [key for key, value in expected.items() if observed.get(key) != value]
    if drift:
        raise FengDhRunError(f"frozen Feng identity drift: {', '.join(drift)}")
    return observed


def verify_table53_schedule_identity(schedule_path: Path) -> dict[str, Any]:
    """Verify the recovered workbook D schedule before a historical run."""

    if not schedule_path.is_file():
        raise FengDhRunError(f"missing frozen Table 5.3 schedule: {schedule_path}")
    with schedule_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise FengDhRunError("frozen Table 5.3 schedule is empty") from exc
        expected_header = [
            "raw_bag_id",
            "segment_id",
            "start",
            "goal",
            "scheduled_release_seconds",
        ]
        if header != expected_header:
            raise FengDhRunError("unexpected frozen Table 5.3 schedule header")
        row_count = sum(1 for row in reader if row)
    observed = {
        "path": str(schedule_path.resolve()),
        "sha256": _sha256_file(schedule_path),
        "row_count": row_count,
        "start_semantics": "FROZEN_SHARED_SCHEDULE_D",
    }
    if observed["sha256"] != EXPECTED_TABLE53_SCHEDULE_SHA256:
        raise FengDhRunError("frozen Table 5.3 schedule identity drift")
    if observed["row_count"] != EXPECTED_TABLE53_SCHEDULE_ROWS:
        raise FengDhRunError("frozen Table 5.3 schedule row-count drift")
    return observed


def read_map_physics(map_path: Path) -> dict[str, float | int]:
    try:
        first = map_path.read_text(encoding="utf-8").splitlines()[0].split()
        vertex_count = int(first[0])
        agv_length_m = float(first[1])
        safe_length_m = float(first[2])
    except (OSError, IndexError, ValueError) as exc:
        raise FengDhRunError(f"cannot read Feng map header: {map_path}") from exc
    speed_mps = 2.5
    tick_seconds = 0.2
    movement_per_tick_m = speed_mps * tick_seconds
    headway_seconds = (agv_length_m + safe_length_m) / speed_mps
    footprint_cells = math.ceil((agv_length_m + safe_length_m) / movement_per_tick_m)
    if headway_seconds <= 0.0 or footprint_cells < 1:
        raise FengDhRunError("map header yields a non-physical carrier footprint")
    return {
        "vertex_count": vertex_count,
        "agv_length_m": agv_length_m,
        "safe_length_m": safe_length_m,
        "speed_mps": speed_mps,
        "tick_seconds": tick_seconds,
        "movement_per_tick_m": movement_per_tick_m,
        "headway_seconds": headway_seconds,
        "footprint_cells": footprint_cells,
    }


def coefficient_seconds(
    map_path: Path, *, alpha_scale: float, beta_over_alpha: float
) -> tuple[float, float]:
    if not math.isfinite(alpha_scale) or alpha_scale < 0.0:
        raise FengDhRunError("alpha scale must be finite and non-negative")
    if not math.isfinite(beta_over_alpha) or beta_over_alpha <= 1.0:
        raise FengDhRunError("beta/alpha must be finite and greater than one")
    headway = float(read_map_physics(map_path)["headway_seconds"])
    alpha = alpha_scale * headway
    beta = beta_over_alpha * alpha
    if beta <= alpha:
        raise FengDhRunError("stopped penalty must be greater than moving penalty")
    return alpha, beta


def java_sources(source_dir: Path = JAVA_SOURCE_DIR) -> list[Path]:
    required = {
        "FengDhBagState.java",
        "FengDhEdgeLattice.java",
        "FengDhPolicy.java",
        "FengDhSimulator.java",
        "FengDhBenchmark.java",
    }
    sources = sorted(source_dir.glob("*.java"))
    names = {path.name for path in sources}
    missing = sorted(required - names)
    if missing:
        raise FengDhRunError(f"missing reconstruction Java sources: {', '.join(missing)}")
    return sources


def compile_command(*, javac: str, classes_dir: Path) -> list[str]:
    return [
        javac,
        "--release",
        "8",
        "-Xlint:all",
        "-encoding",
        "UTF-8",
        "-d",
        str(classes_dir.resolve()),
        *[str(path.resolve()) for path in java_sources()],
    ]


def compile_java(*, javac: str, classes_dir: Path) -> None:
    classes_dir.mkdir(parents=True, exist_ok=True)
    command = compile_command(javac=javac, classes_dir=classes_dir)
    subprocess.run(command, cwd=ROOT, check=True)
    class_files = sorted(classes_dir.rglob("*.class"))
    if not class_files or not (classes_dir / "App" / "FengDhBenchmark.class").is_file():
        raise FengDhRunError("Java compilation did not produce the reconstruction entry class")
    _write_json(
        classes_dir / COMPILE_IDENTITY_NAME,
        {
            "schema": "czr005.feng_paper_env_cie_dh.compile.v1",
            "source_aggregate_sha256": _aggregate_sha256(
                java_sources(), JAVA_SOURCE_DIR.parent
            ),
            "class_aggregate_sha256": _aggregate_sha256(class_files, classes_dir),
            "class_count": len(class_files),
            "command": command,
        },
    )


def verify_compiled_java_identity(
    *, classes_dir: Path, expected_source_sha256: str
) -> dict[str, Any]:
    identity_path = classes_dir / COMPILE_IDENTITY_NAME
    if not identity_path.is_file():
        raise FengDhRunError(
            "compiled Java identity is missing; run the compile command before --skip-compile"
        )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if identity.get("schema") != "czr005.feng_paper_env_cie_dh.compile.v1":
        raise FengDhRunError("unexpected compiled Java identity schema")
    if identity.get("source_aggregate_sha256") != expected_source_sha256:
        raise FengDhRunError(
            "compiled Java classes do not match the current reconstruction sources"
        )
    class_files = sorted(classes_dir.rglob("*.class"))
    if int(identity.get("class_count", -1)) != len(class_files) or identity.get(
        "class_aggregate_sha256"
    ) != _aggregate_sha256(class_files, classes_dir):
        raise FengDhRunError("compiled Java class identity drift")
    return identity


def microtest_command(*, java: str, classes_dir: Path, output_jsonl: Path) -> list[str]:
    return [
        java,
        "-Djava.awt.headless=true",
        "-cp",
        str(classes_dir.resolve()),
        MAIN_CLASS,
        "microtests",
        "--json-out",
        str(output_jsonl.resolve()),
    ]


def load_microtest_results(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FengDhRunError(f"microtest JSONL was not produced: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FengDhRunError(f"invalid microtest JSONL line {line_number}: {path}") from exc
        if not isinstance(row, dict):
            raise FengDhRunError(f"microtest line {line_number} is not an object: {path}")
        rows.append(row)
    expected_ids = {f"T{index}" for index in range(1, 11)}
    observed_ids = {str(row.get("case_id")) for row in rows}
    if len(rows) != 10 or observed_ids != expected_ids:
        raise FengDhRunError(
            f"microtests must contain exactly T1-T10; observed {sorted(observed_ids)}"
        )
    required = {
        "case_id",
        "input",
        "expected",
        "actual",
        "expected_tick_trace",
        "actual_tick_trace",
        "pass",
    }
    for row in rows:
        missing = required - set(row)
        if missing:
            raise FengDhRunError(
                f"microtest {row.get('case_id')} misses fields: {sorted(missing)}"
            )
        if row["pass"] is not True:
            raise FengDhRunError(f"microtest failed: {row['case_id']}")
    return rows


def java_run_command(
    *,
    java: str,
    classes_dir: Path,
    map_path: Path,
    input_path: Path,
    output_dir: Path,
    alpha_seconds: float,
    beta_seconds: float,
    max_raw_bags: int,
    workload_scale: float,
    seed: int,
    horizon_seconds: float,
    trace_sample_modulo: int,
    formal_timing_eligible: bool = True,
    schedule_path: Path | None = None,
    storage_in_goal: int = 47,
    storage_out_start: int = 52,
) -> list[str]:
    if max_raw_bags < 0 or horizon_seconds < 0.0 or trace_sample_modulo < 0:
        raise FengDhRunError("limits, horizon, and trace modulo must be non-negative")
    if not math.isfinite(workload_scale) or workload_scale <= 0.0:
        raise FengDhRunError("workload scale must be finite and positive")
    command = [
        java,
        "-Djava.awt.headless=true",
        "-cp",
        str(classes_dir.resolve()),
        MAIN_CLASS,
        "run",
        "--map",
        str(map_path.resolve()),
        "--input",
        str(input_path.resolve()),
        "--output",
        str(output_dir.resolve()),
        "--alpha",
        format(alpha_seconds, ".17g"),
        "--beta",
        format(beta_seconds, ".17g"),
        "--limit",
        str(max_raw_bags),
        "--workload-scale",
        format(workload_scale, ".17g"),
        "--seed",
        str(seed),
        "--horizon-seconds",
        format(horizon_seconds, ".17g"),
        "--trace-sample-modulo",
        str(trace_sample_modulo),
        "--formal-timing-eligible",
        "true" if formal_timing_eligible else "false",
        "--storage-in-goal",
        str(storage_in_goal),
        "--storage-out-start",
        str(storage_out_start),
    ]
    if schedule_path is not None:
        command.extend(["--schedule", str(schedule_path.resolve())])
    return command


def _completed(
    output_dir: Path, *, command: Sequence[str], identity: Mapping[str, Any]
) -> bool:
    status_path = output_dir / "runner_status.json"
    if not status_path.is_file() or not (output_dir / "summary.csv").is_file():
        return False
    status = json.loads(status_path.read_text(encoding="utf-8"))
    return (
        status.get("status") == "complete"
        and status.get("returncode") == 0
        and status.get("command") == list(command)
        and status.get("identity") == dict(identity)
    )


def _prepare_output(output_dir: Path, *, force: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = [output_dir / name for name in KNOWN_RUN_FILES if (output_dir / name).exists()]
    if existing and not force:
        names = ", ".join(path.name for path in existing)
        raise FengDhRunError(f"output exists ({names}); use --force for this exact run directory")
    for path in existing:
        path.unlink()


def execute_java_run(
    *,
    command: Sequence[str],
    output_dir: Path,
    identity: Mapping[str, Any],
    force: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    if _completed(output_dir, command=command, identity=identity) and not force:
        return json.loads((output_dir / "runner_status.json").read_text(encoding="utf-8"))
    _prepare_output(output_dir, force=force)
    status: dict[str, Any] = {
        "schema": "czr005.feng_paper_env_cie_dh.run.v1",
        "status": "running",
        "started_at": _utc_now(),
        "command": list(command),
        "identity": dict(identity),
    }
    _write_json(output_dir / "runner_status.json", status)
    started = time.perf_counter()
    try:
        result = subprocess.run(
            list(command),
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds or None,
            check=False,
        )
        status["returncode"] = result.returncode
        status["status"] = "complete" if result.returncode == 0 else "failed"
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        status["returncode"] = None
        status["status"] = "timeout"
        stdout = (exc.stdout or b"")
        stderr = (exc.stderr or b"")
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
    status["wall_seconds"] = time.perf_counter() - started
    status["finished_at"] = _utc_now()
    (output_dir / "stdout.txt").write_text(str(stdout), encoding="utf-8")
    (output_dir / "stderr.txt").write_text(str(stderr), encoding="utf-8")
    _write_json(output_dir / "runner_status.json", status)
    if status["status"] != "complete":
        raise FengDhRunError(f"Java reconstruction run ended with {status['status']}")
    summary = _read_csv(output_dir / "summary.csv")
    if len(summary) != 1:
        raise FengDhRunError("summary.csv must contain exactly one data row")
    return status


def _variant_id(alpha_scale: float, beta_over_alpha: float) -> str:
    def token(value: float) -> str:
        return format(Decimal(str(value)).normalize(), "f").replace("-", "m").replace(".", "p")

    return f"alpha_{token(alpha_scale)}__beta_ratio_{token(beta_over_alpha)}"


def aggregate_runs(output_root: Path) -> dict[str, Any]:
    if not output_root.is_dir():
        raise FengDhRunError(f"campaign output root does not exist: {output_root}")
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in output_root.iterdir() if path.is_dir()):
        status_path = run_dir / "runner_status.json"
        summary_path = run_dir / "summary.csv"
        if not status_path.is_file() or not summary_path.is_file():
            continue
        status = json.loads(status_path.read_text(encoding="utf-8"))
        summary_rows = _read_csv(summary_path)
        if len(summary_rows) != 1:
            raise FengDhRunError(f"expected one summary row in {summary_path}")
        rows.append(
            {
                "run_id": run_dir.name,
                "runner_status": status.get("status"),
                "wall_seconds": status.get("wall_seconds"),
                "identity": status.get("identity", {}),
                "summary": summary_rows[0],
            }
        )
    return {
        "schema": "czr005.feng_paper_env_cie_dh.campaign.v1",
        "generated_at": _utc_now(),
        "run_count": len(rows),
        "complete_run_count": sum(row["runner_status"] == "complete" for row in rows),
        "runs": rows,
    }


def export_sensitivity_envelope(
    campaign: Mapping[str, Any], *, table_path: Path, figure_path: Path
) -> list[dict[str, Any]]:
    """Export all frozen coefficient cells without ranking or selecting one."""

    runs = campaign.get("runs")
    if not isinstance(runs, list) or len(runs) != 9:
        raise FengDhRunError("sensitivity export requires all nine frozen cells")
    rows: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, Mapping) or run.get("runner_status") != "complete":
            raise FengDhRunError("sensitivity export requires nine complete runs")
        identity = run.get("identity")
        summary = run.get("summary")
        if not isinstance(identity, Mapping) or not isinstance(summary, Mapping):
            raise FengDhRunError("sensitivity campaign row lacks identity or summary")
        population = int(summary["raw_bag_count"])
        completed = int(summary["completed_raw_bags"])
        if population != 28_506 or completed != population:
            raise FengDhRunError("sensitivity cell is not the complete original population")
        if summary.get("table53_timing_eligible", "").lower() != "true":
            raise FengDhRunError("sensitivity cell is not eligible for Table 5.3 timing")
        schedule_identity = identity.get("table53_schedule")
        if not isinstance(schedule_identity, Mapping) or schedule_identity.get(
            "sha256"
        ) != EXPECTED_TABLE53_SCHEDULE_SHA256:
            raise FengDhRunError("sensitivity cell does not use the frozen shared D schedule")
        row: dict[str, Any] = {
            "variant_id": str(run["run_id"]),
            "alpha_scale": float(identity["alpha_scale"]),
            "beta_over_alpha": float(identity["beta_over_alpha"]),
            "alpha_move_seconds": float(summary["alpha_move_seconds"]),
            "beta_stop_seconds": float(summary["beta_stop_seconds"]),
            "raw_bag_population": population,
            "completed_raw_bags": completed,
            "segment_population": int(summary["segment_count"]),
            "completed_segments": int(summary["completed_segments"]),
            "partial_reconstruction_table53_min_seconds": float(
                summary["table53_scheduled_interval_min_seconds"]
            ),
            "partial_reconstruction_table53_mean_seconds": float(
                summary["table53_scheduled_interval_mean_seconds"]
            ),
            "partial_reconstruction_table53_p95_seconds": float(
                summary["table53_scheduled_interval_p95_seconds"]
            ),
            "partial_reconstruction_table53_p99_seconds": float(
                summary["table53_scheduled_interval_p99_seconds"]
            ),
            "partial_reconstruction_table53_max_seconds": float(
                summary["table53_scheduled_interval_max_seconds"]
            ),
            "historical_workbook_exact_dh_mean_seconds": 265.592131481,
            "historical_workbook_exact_dh_max_seconds": 517.2,
            "paper_printed_dh_mean_minutes": 4.43,
            "paper_printed_dh_max_minutes": 8.62,
            "wall_seconds": float(run.get("wall_seconds") or 0.0),
            "full_population": True,
            "post_result_selected": False,
        }
        row["mean_delta_vs_historical_workbook_exact_dh_seconds"] = (
            row["partial_reconstruction_table53_mean_seconds"]
            - row["historical_workbook_exact_dh_mean_seconds"]
        )
        rows.append(row)
    rows.sort(key=lambda row: (row["alpha_scale"], row["beta_over_alpha"]))

    table_path.parent.mkdir(parents=True, exist_ok=True)
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - formal workstation dependency
        raise FengDhRunError("matplotlib is required for the sensitivity figure") from exc

    alpha_values = sorted({float(row["alpha_scale"]) for row in rows})
    beta_values = sorted({float(row["beta_over_alpha"]) for row in rows})
    lookup = {
        (float(row["alpha_scale"]), float(row["beta_over_alpha"])): row
        for row in rows
    }
    mean_grid = [
        [
            lookup[(alpha, beta)]["partial_reconstruction_table53_mean_seconds"]
            / 60.0
            for beta in beta_values
        ]
        for alpha in alpha_values
    ]
    max_grid = [
        [
            lookup[(alpha, beta)]["partial_reconstruction_table53_max_seconds"]
            / 60.0
            for beta in beta_values
        ]
        for alpha in alpha_values
    ]
    figure, axes = plt.subplots(1, 2, figsize=(9.2, 3.8), constrained_layout=True)
    for axis, grid, title in (
        (axes[0], mean_grid, "Partial-reconstruction mean THT (min)"),
        (axes[1], max_grid, "Partial-reconstruction maximum THT (min)"),
    ):
        image = axis.imshow(grid, cmap="viridis_r", aspect="auto")
        axis.set_xticks(range(len(beta_values)), [str(value) for value in beta_values])
        axis.set_yticks(range(len(alpha_values)), [str(value) for value in alpha_values])
        axis.set_xlabel("beta / alpha")
        axis.set_ylabel("alpha / physical headway")
        axis.set_title(title)
        for row_index, values in enumerate(grid):
            for column_index, value in enumerate(values):
                axis.text(column_index, row_index, f"{value:.3f}", ha="center", va="center", fontsize=8)
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.suptitle(
        "Semantically partial CIE-DH reconstruction: frozen 3x3 coefficient envelope"
    )
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(figure_path, dpi=180)
    plt.close(figure)
    return rows


def _base_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    return args.map_path.resolve(), args.input_path.resolve(), args.legacy_root.resolve()


def _run_one(args: argparse.Namespace, *, alpha_scale: float, beta_ratio: float, output: Path) -> None:
    map_path, input_path, legacy_root = _base_paths(args)
    external_identity: dict[str, Any] | None = None
    external_identity_path: Path | None = None
    if args.allow_external_workload:
        if args.external_workload_identity is None:
            raise FengDhRunError(
                "--allow-external-workload requires --external-workload-identity"
            )
        external_identity_path = args.external_workload_identity.resolve(strict=True)
        external_identity = json.loads(external_identity_path.read_text(encoding="utf-8"))
        if external_identity.get("schema") != "czr005.cie_external_baseline_workload.v1":
            raise FengDhRunError("unexpected external workload identity schema")
        if Path(str(external_identity.get("raw_path", ""))).resolve() != input_path:
            raise FengDhRunError("external identity raw_path differs from --input-path")
        if Path(str(external_identity.get("map_path", ""))).resolve() != map_path:
            raise FengDhRunError("external identity map_path differs from --map-path")
        if int(external_identity.get("seed", -1)) != args.seed:
            raise FengDhRunError("external identity seed differs from --seed")
        if args.workload_scale != 1.0:
            raise FengDhRunError(
                "external workload is already materialized; --workload-scale must be 1"
            )
        if not math.isclose(
            args.horizon_seconds,
            FIXED_EXTERNAL_HORIZON_SECONDS,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise FengDhRunError(
                "external workload runs require the fixed absolute 98259-second horizon"
            )
        if not math.isclose(
            float(external_identity.get("fixed_horizon_seconds", math.nan)),
            FIXED_EXTERNAL_HORIZON_SECONDS,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise FengDhRunError(
                "external workload identity does not freeze the 98259-second horizon"
            )
    elif args.external_workload_identity is not None:
        raise FengDhRunError(
            "--external-workload-identity requires --allow-external-workload"
        )

    schedule_identity: dict[str, Any] | None = None
    schedule_path: Path | None = None
    use_historical_schedule = (
        not args.allow_external_workload
        and math.isclose(args.workload_scale, 1.0, rel_tol=0.0, abs_tol=1.0e-12)
        and args.max_raw_bags == 0
    )
    if use_historical_schedule:
        schedule_path = args.schedule_path.resolve()
        schedule_identity = verify_table53_schedule_identity(schedule_path)
    provenance = verify_legacy_identity(
        map_path=map_path,
        input_path=input_path,
        legacy_root=legacy_root,
        require_original_input=not args.allow_external_workload,
        expected_map_sha256=(
            str(external_identity["map_sha256"])
            if external_identity is not None
            else EXPECTED_MAP_SHA256
        ),
        expected_input_sha256=(
            str(external_identity["raw_sha256"])
            if external_identity is not None
            else EXPECTED_INPUT_SHA256
        ),
    )
    workload_config = _load_manifest()["paper_environment"]["workload"]
    storage_in_goal = int(
        external_identity["storage_in_goal"]
        if external_identity is not None
        else workload_config["storage_in_goal"]
    )
    storage_out_start = int(
        external_identity["storage_out_start"]
        if external_identity is not None
        else workload_config["storage_out_start"]
    )
    alpha, beta = coefficient_seconds(
        map_path, alpha_scale=alpha_scale, beta_over_alpha=beta_ratio
    )
    reconstruction_source_sha256 = _aggregate_sha256(
        java_sources(), JAVA_SOURCE_DIR.parent
    )
    compiled_identity = (
        None
        if args.dry_run
        else verify_compiled_java_identity(
            classes_dir=args.classes_dir.resolve(),
            expected_source_sha256=reconstruction_source_sha256,
        )
    )
    # The 2x no-THT rule belongs to the experiment protocol, not only to the
    # external-workload wrapper.  A direct ``--workload-scale 2`` fixed-horizon
    # run must therefore receive the same reporting gate as a materialized 2x
    # workload carrying an external identity.
    effective_load_factor = (
        float(external_identity.get("load_factor", math.nan))
        if external_identity is not None
        else float(args.workload_scale)
    )
    formal_timing_eligible = not (
        args.horizon_seconds > 0.0
        and math.isclose(
            effective_load_factor,
            2.0,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
    )
    identity = {
        "method": "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION",
        "manifest_sha256": _sha256_file(MANIFEST_PATH),
        "map_sha256": provenance["map_sha256"],
        "input_sha256": provenance["input_sha256"],
        "legacy_java_source_aggregate_sha256": provenance[
            "legacy_java_source_aggregate_sha256"
        ],
        "reconstruction_java_source_aggregate_sha256": reconstruction_source_sha256,
        "compiled_java_class_aggregate_sha256": (
            None if compiled_identity is None else compiled_identity["class_aggregate_sha256"]
        ),
        "map_physics": read_map_physics(map_path),
        "alpha_scale": alpha_scale,
        "beta_over_alpha": beta_ratio,
        "alpha_seconds": alpha,
        "beta_seconds": beta,
        "workload_scale": args.workload_scale,
        "seed": args.seed,
        "max_raw_bags": args.max_raw_bags,
        "horizon_seconds": args.horizon_seconds,
        "trace_sample_modulo": args.trace_sample_modulo,
        "formal_timing_eligible": formal_timing_eligible,
        "storage_in_goal": storage_in_goal,
        "storage_out_start": storage_out_start,
        "table53_schedule": schedule_identity,
        "external_workload_identity": (
            {
                "path": str(external_identity_path),
                "sha256": _sha256_file(external_identity_path),
                "map": external_identity.get("map"),
                "map_sha256": external_identity.get("map_sha256"),
                "load_factor": external_identity.get("load_factor"),
                "seed": external_identity.get("seed"),
                "raw_bag_count": external_identity.get("raw_bag_count"),
                "segment_count": external_identity.get("segment_count"),
                "storage_in_goal": external_identity.get("storage_in_goal"),
                "storage_out_start": external_identity.get("storage_out_start"),
            }
            if external_identity is not None
            else None
        ),
    }
    command = java_run_command(
        java=args.java,
        classes_dir=args.classes_dir,
        map_path=map_path,
        input_path=input_path,
        output_dir=output,
        alpha_seconds=alpha,
        beta_seconds=beta,
        max_raw_bags=args.max_raw_bags,
        workload_scale=args.workload_scale,
        seed=args.seed,
        horizon_seconds=args.horizon_seconds,
        trace_sample_modulo=args.trace_sample_modulo,
        formal_timing_eligible=formal_timing_eligible,
        schedule_path=schedule_path,
        storage_in_goal=storage_in_goal,
        storage_out_start=storage_out_start,
    )
    if args.dry_run:
        print(subprocess.list2cmdline(command))
        return
    execute_java_run(
        command=command,
        output_dir=output,
        identity=identity,
        force=args.force,
        timeout_seconds=args.timeout_seconds,
    )


def _add_shared_run_arguments(parser: argparse.ArgumentParser) -> None:
    manifest = _load_manifest()
    environment = manifest["paper_environment"]
    runner = manifest["runner"]
    parser.add_argument("--map-path", type=Path, default=ROOT / environment["map"]["path"])
    parser.add_argument("--input-path", type=Path, default=ROOT / environment["workload"]["path"])
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=ROOT / environment["workload"]["table53_schedule_path"],
    )
    parser.add_argument("--legacy-root", type=Path, default=ROOT / environment["legacy_mirror"])
    parser.add_argument("--classes-dir", type=Path, default=ROOT / runner["classes_dir"])
    parser.add_argument("--java", default=shutil.which("java") or "java")
    parser.add_argument("--javac", default=shutil.which("javac") or "javac")
    parser.add_argument("--max-raw-bags", type=int, default=int(runner["max_raw_bags"]))
    parser.add_argument("--workload-scale", type=float, default=float(runner["workload_scale"]))
    parser.add_argument("--seed", type=int, default=int(runner["seed"]))
    parser.add_argument("--horizon-seconds", type=float, default=float(runner["horizon_seconds"]))
    parser.add_argument(
        "--trace-sample-modulo", type=int, default=int(runner["trace_sample_modulo"])
    )
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-external-workload", action="store_true")
    parser.add_argument("--external-workload-identity", type=Path)


def _parser() -> argparse.ArgumentParser:
    manifest = _load_manifest()
    runner = manifest["runner"]
    coefficients = manifest["routing"]["coefficients"]
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--javac", default=shutil.which("javac") or "javac")
    compile_parser.add_argument("--classes-dir", type=Path, default=ROOT / runner["classes_dir"])

    micro = subparsers.add_parser("microtests")
    micro.add_argument("--java", default=shutil.which("java") or "java")
    micro.add_argument("--javac", default=shutil.which("javac") or "javac")
    micro.add_argument("--classes-dir", type=Path, default=ROOT / runner["classes_dir"])
    micro.add_argument(
        "--output-jsonl",
        type=Path,
        default=ROOT / "outputs" / "runtime" / "feng_cie_dh_reconstruction" / "microtests.jsonl",
    )
    micro.add_argument("--skip-compile", action="store_true")

    run = subparsers.add_parser("run")
    _add_shared_run_arguments(run)
    run.add_argument(
        "--alpha-scale", type=float, default=float(coefficients["primary"]["alpha_scale"])
    )
    run.add_argument(
        "--beta-over-alpha",
        type=float,
        default=float(coefficients["primary"]["beta_over_alpha"]),
    )
    run.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / runner["output_root"] / "primary",
    )

    sensitivity = subparsers.add_parser("sensitivity")
    _add_shared_run_arguments(sensitivity)
    sensitivity.add_argument(
        "--output-root", type=Path, default=ROOT / runner["output_root"] / "sensitivity"
    )

    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument(
        "--output-root", type=Path, default=ROOT / runner["output_root"] / "sensitivity"
    )
    aggregate.add_argument("--output-json", type=Path)
    aggregate.add_argument("--output-csv", type=Path, default=SENSITIVITY_TABLE)
    aggregate.add_argument("--figure", type=Path, default=SENSITIVITY_FIGURE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "compile":
        compile_java(javac=args.javac, classes_dir=args.classes_dir.resolve())
        print(args.classes_dir.resolve())
        return 0
    if args.command == "microtests":
        if not args.skip_compile:
            compile_java(javac=args.javac, classes_dir=args.classes_dir.resolve())
        else:
            verify_compiled_java_identity(
                classes_dir=args.classes_dir.resolve(),
                expected_source_sha256=_aggregate_sha256(
                    java_sources(), JAVA_SOURCE_DIR.parent
                ),
            )
        args.output_jsonl.resolve().parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            microtest_command(
                java=args.java,
                classes_dir=args.classes_dir.resolve(),
                output_jsonl=args.output_jsonl.resolve(),
            ),
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
        load_microtest_results(args.output_jsonl.resolve())
        print("microtests=10/10")
        return 0
    if args.command == "run":
        if not args.skip_compile and not args.dry_run:
            compile_java(javac=args.javac, classes_dir=args.classes_dir.resolve())
        _run_one(
            args,
            alpha_scale=args.alpha_scale,
            beta_ratio=args.beta_over_alpha,
            output=args.output_dir.resolve(),
        )
        return 0
    if args.command == "sensitivity":
        if not args.skip_compile and not args.dry_run:
            compile_java(javac=args.javac, classes_dir=args.classes_dir.resolve())
        coefficients = _load_manifest()["routing"]["coefficients"]["sensitivity"]
        for alpha_scale in coefficients["alpha_scales"]:
            for beta_ratio in coefficients["beta_over_alpha"]:
                run_dir = args.output_root.resolve() / _variant_id(alpha_scale, beta_ratio)
                _run_one(
                    args,
                    alpha_scale=float(alpha_scale),
                    beta_ratio=float(beta_ratio),
                    output=run_dir,
                )
        if not args.dry_run:
            aggregate = aggregate_runs(args.output_root.resolve())
            expected_cells = len(coefficients["alpha_scales"]) * len(
                coefficients["beta_over_alpha"]
            )
            if aggregate["run_count"] != expected_cells or aggregate[
                "complete_run_count"
            ] != expected_cells:
                raise FengDhRunError(
                    "sensitivity envelope is incomplete: "
                    f"{aggregate['complete_run_count']}/{expected_cells} complete"
                )
            _write_json(args.output_root.resolve() / "campaign_summary.json", aggregate)
            export_sensitivity_envelope(
                aggregate,
                table_path=SENSITIVITY_TABLE,
                figure_path=SENSITIVITY_FIGURE,
            )
            print(f"complete={aggregate['complete_run_count']}/{aggregate['run_count']}")
        return 0

    campaign = aggregate_runs(args.output_root.resolve())
    output = args.output_json or args.output_root.resolve() / "campaign_summary.json"
    _write_json(output.resolve(), campaign)
    export_sensitivity_envelope(
        campaign,
        table_path=args.output_csv.resolve(),
        figure_path=args.figure.resolve(),
    )
    print(f"complete={campaign['complete_run_count']}/{campaign['run_count']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FengDhRunError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

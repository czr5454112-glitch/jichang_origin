from __future__ import annotations

from pathlib import Path
import csv
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from scripts.eval import run_feng_paper_env_cie_dh as runner


def test_microtest_skip_compile_rejects_stale_source_identity(tmp_path: Path) -> None:
    classes = tmp_path / "classes"
    classes.mkdir()
    (classes / runner.COMPILE_IDENTITY_NAME).write_text(
        json.dumps(
            {
                "schema": "czr005.feng_paper_env_cie_dh.compile.v1",
                "source_aggregate_sha256": "stale-source",
                "class_aggregate_sha256": "unused",
                "class_count": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(runner.FengDhRunError, match="do not match"):
        runner.main(
            [
                "microtests",
                "--classes-dir",
                str(classes),
                "--output-jsonl",
                str(tmp_path / "microtests.jsonl"),
                "--skip-compile",
            ]
        )


def test_java_microcases_t1_through_t10_are_complete_and_deterministic(
    tmp_path: Path,
) -> None:
    java = shutil.which("java")
    javac = shutil.which("javac")
    assert java is not None, "java is required for the Feng reconstruction gate"
    assert javac is not None, "javac is required for the Feng reconstruction gate"

    classes = tmp_path / "classes"
    runner.compile_java(javac=javac, classes_dir=classes)

    first = tmp_path / "microtests_first.jsonl"
    first_run = subprocess.run(
        runner.microtest_command(java=java, classes_dir=classes, output_jsonl=first),
        cwd=runner.ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert first_run.returncode == 0, first_run.stderr or first_run.stdout
    rows = runner.load_microtest_results(first)
    assert [row["case_id"] for row in rows] == [f"T{index}" for index in range(1, 11)]
    assert all(isinstance(row["input"], dict) and row["input"] for row in rows)
    assert all(isinstance(row["expected"], dict) and row["expected"] for row in rows)
    assert all(isinstance(row["actual"], dict) and row["actual"] for row in rows)
    assert all(
        isinstance(row["expected_tick_trace"], str) and row["expected_tick_trace"]
        for row in rows
    )
    assert all(
        isinstance(row["actual_tick_trace"], str) and row["actual_tick_trace"]
        for row in rows
    )
    assert all(row["pass"] is True for row in rows)

    second = tmp_path / "microtests_second.jsonl"
    second_run = subprocess.run(
        runner.microtest_command(java=java, classes_dir=classes, output_jsonl=second),
        cwd=runner.ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert second_run.returncode == 0, second_run.stderr or second_run.stdout
    runner.load_microtest_results(second)
    assert first.read_bytes() == second.read_bytes()


def _write_timing_fixture(tmp_path: Path) -> tuple[Path, Path]:
    map_path = tmp_path / "map.txt"
    map_path.write_text(
        "\n".join(
            [
                "3 1.0 0.0 2",
                "0 1 0.0 0 0 1",
                "1 5 1.0 0 1 2",
                "2 2 0.0 0 2",
                "0 0 0",
                "0 0 0",
                "0 0 0",
                "0 1 0.5 2.5",
                "1 2 0.5 2.5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    input_path = tmp_path / "input.txt"
    input_path.write_text(
        "TaskID EntryTime STD Start End Unloader Loader\n"
        "0 0 100 0 2 U L\n"
        "1 100 200 0 2 U L\n",
        encoding="utf-8",
    )
    return map_path, input_path


def _summary(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    return rows[0]


def test_formal_timing_gate_blanks_complete_2x_and_incomplete_population(
    tmp_path: Path,
) -> None:
    java = shutil.which("java")
    javac = shutil.which("javac")
    assert java is not None
    assert javac is not None
    classes = tmp_path / "classes"
    runner.compile_java(javac=javac, classes_dir=classes)
    map_path, input_path = _write_timing_fixture(tmp_path)

    complete_2x = tmp_path / "complete_2x"
    complete_command = runner.java_run_command(
        java=java,
        classes_dir=classes,
        map_path=map_path,
        input_path=input_path,
        output_dir=complete_2x,
        alpha_seconds=0.4,
        beta_seconds=0.8,
        max_raw_bags=1,
        workload_scale=1.0,
        seed=0,
        horizon_seconds=0.0,
        trace_sample_modulo=0,
        formal_timing_eligible=False,
    )
    completed = subprocess.run(
        complete_command,
        cwd=runner.ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    complete_row = _summary(complete_2x / "summary.csv")
    assert complete_row["status"] == "COMPLETE"
    assert complete_row["full_population_timing_eligible"] == "false"
    assert complete_row["table53_scheduled_interval_mean_seconds"] == "N/A"
    assert complete_row["diagnostic_first_admission_to_completion_mean_seconds"] == "N/A"
    assert complete_row["table53_timing_eligible"] == "false"

    incomplete = tmp_path / "incomplete"
    incomplete_command = runner.java_run_command(
        java=java,
        classes_dir=classes,
        map_path=map_path,
        input_path=input_path,
        output_dir=incomplete,
        alpha_seconds=0.4,
        beta_seconds=0.8,
        max_raw_bags=0,
        workload_scale=1.0,
        seed=0,
        horizon_seconds=5.0,
        trace_sample_modulo=0,
        formal_timing_eligible=True,
    )
    truncated = subprocess.run(
        incomplete_command,
        cwd=runner.ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert truncated.returncode == 0, truncated.stderr or truncated.stdout
    incomplete_row = _summary(incomplete / "summary.csv")
    assert incomplete_row["status"] == "HORIZON_REACHED"
    assert int(incomplete_row["completed_raw_bags"]) < 2
    assert incomplete_row["raw_bag_count"] == "2"
    assert incomplete_row["full_population_timing_eligible"] == "false"
    assert incomplete_row["table53_scheduled_interval_mean_seconds"] == "N/A"
    assert incomplete_row["diagnostic_first_admission_to_completion_mean_seconds"] == "N/A"
    assert incomplete_row["table53_timing_eligible"] == "false"
    assert incomplete_row["diagnostic_survivor_raw_bag_count"] == "0"


def test_direct_fixed_horizon_2x_run_disables_formal_timing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy = runner.ROOT / "legacy" / "jichang_origin_readonly"
    args = SimpleNamespace(
        map_path=legacy / "map2.txt",
        input_path=legacy / "inputdata.txt",
        legacy_root=legacy,
        allow_external_workload=False,
        external_workload_identity=None,
        seed=0,
        workload_scale=2.0,
        horizon_seconds=runner.FIXED_EXTERNAL_HORIZON_SECONDS,
        max_raw_bags=0,
        trace_sample_modulo=0,
        classes_dir=tmp_path / "unused_classes",
        java="java",
        force=False,
        timeout_seconds=0,
        dry_run=True,
    )

    runner._run_one(
        args,
        alpha_scale=1.0,
        beta_ratio=2.0,
        output=tmp_path / "direct_2x",
    )

    command = capsys.readouterr().out
    assert "--formal-timing-eligible false" in command

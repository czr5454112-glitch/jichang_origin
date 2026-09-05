from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from scripts.eval import run_feng_paper_env_cie_dh as runner


def test_zero_through_state_machine_and_synchronous_commit(tmp_path: Path) -> None:
    java = shutil.which("java")
    javac = shutil.which("javac")
    assert java is not None and javac is not None
    classes = tmp_path / "classes"
    harness = tmp_path / "harness"
    harness.mkdir()
    runner.compile_java(javac=javac, classes_dir=classes)
    subprocess.run(
        [
            javac,
            "-encoding",
            "UTF-8",
            "-cp",
            str(classes),
            "-d",
            str(harness),
            str(runner.ROOT / "tests/java/App/ZeroThroughAudit.java"),
        ],
        check=True,
        cwd=runner.ROOT,
    )
    expected = [
        "Z1_zero_intermediate",
        "Z2_positive_control",
        "Z3_following",
        "Z4_one_cell_footprint",
        "Z5_simultaneous_competition",
        "Z6_downstream_blocked_then_release",
        "Z7_finite_service_not_deadlock",
        "Z8_no_path_deadlock",
        "Z9_duplicate_service_rejected",
        "Z10_zero_goal",
        "Z11_real_nanning_130_57_58",
        "Z12_same_commit_source_entry",
    ]
    runs: list[tuple[str, dict[str, bytes]]] = []
    for name in ("first", "repeat"):
        output = tmp_path / name
        run = subprocess.run(
            [
                java,
                "-cp",
                os.pathsep.join((str(harness), str(classes))),
                "App.ZeroThroughAudit",
                "--gate",
                str(output),
                str(runner.ROOT / "data/processed/maps/nanning_legacy.txt"),
            ],
            cwd=runner.ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert run.returncode == 0, run.stderr or run.stdout
        rows = [json.loads(line) for line in run.stdout.splitlines()]
        assert [row["case_id"] for row in rows] == expected
        assert all(row["pass"] is True for row in rows)
        traces = {path.name: path.read_bytes() for path in output.glob("*.tsv")}
        assert len(traces) == 11  # Duplicate-service assertion has no physical trajectory.
        runs.append((run.stdout, traces))
    assert runs[0] == runs[1]

from __future__ import annotations

import csv
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.eval import run_g4irsf24_fresh_hca as fresh_hca


def _write_small_map(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "4 1.0 0 4",
                "0 1 0 0 0 1",
                "1 4 0 0 1 2",
                "2 7 0 0 2 3",
                "3 2 0 0 3",
                "0 1 2 3",
                "0 0 1 2",
                "0 0 0 1",
                "0 0 0 0",
                "0 1 1",
                "1 2 1",
                "2 3 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_early_bag(path: Path) -> None:
    path.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "1 1 10 0 3 1 TEST\n",
        encoding="utf-8",
    )


def test_map_role_tail_is_optional_and_fills_positional_defaults() -> None:
    root = Path("g4irsf31_hca_role_command")
    run_dir = root / "run_01"
    historical = fresh_hca.java_run_command(
        java="java",
        classes_dir=root / "classes",
        map_path=root / "map.txt",
        input_path=root / "tasks.txt",
        start_epoch=1,
        max_epochs=20,
        max_new_tasks=0,
        run_dir=run_dir,
    )
    selected = fresh_hca.java_run_command(
        java="java",
        classes_dir=root / "classes",
        map_path=root / "map.txt",
        input_path=root / "tasks.txt",
        start_epoch=1,
        max_epochs=20,
        max_new_tasks=0,
        run_dir=run_dir,
        storage_in_goal=2,
        storage_out_start=2,
        early_threshold_seconds=5.0,
        storage_lead_seconds=2.0,
    )

    assert historical[-1].endswith("release.csv")
    assert selected[-5:] == ["2.5", "2", "2", "5.0", "2.0"]


@pytest.mark.skipif(
    shutil.which("java") is None or shutil.which("javac") is None,
    reason="Java toolchain is required for the legacy HCA smoke",
)
def test_type7_storage_node_can_be_selected_as_release_source(tmp_path: Path) -> None:
    map_path = tmp_path / "small_map.txt"
    input_path = tmp_path / "inputdata.txt"
    classes_dir = tmp_path / "classes"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_small_map(map_path)
    _write_early_bag(input_path)

    fresh_hca.compile_java(shutil.which("javac") or "javac", classes_dir)
    command = fresh_hca.java_run_command(
        java=shutil.which("java") or "java",
        classes_dir=classes_dir,
        map_path=map_path,
        input_path=input_path,
        start_epoch=1,
        max_epochs=20,
        max_new_tasks=0,
        run_dir=run_dir,
        storage_in_goal=2,
        storage_out_start=2,
        early_threshold_seconds=5.0,
        storage_lead_seconds=2.0,
    )
    completed = subprocess.run(
        command,
        cwd=run_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    with (run_dir / "release.csv").open(encoding="utf-8", newline="") as handle:
        releases = list(csv.DictReader(handle))
    assert [(row["start"], row["goal"]) for row in releases] == [("0", "2"), ("2", "3")]
    assert (run_dir / "output.txt").read_text(encoding="utf-8").count("\n") == 2

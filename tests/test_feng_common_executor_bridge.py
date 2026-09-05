from __future__ import annotations

import csv
from pathlib import Path
import shutil
import subprocess

from czr005.io.legacy_map import parse_legacy_map
from scripts.eval import run_feng_common_executor_bridge as bridge
from scripts.eval import run_g4irsf28_service_potential as potential


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_java_static_control_matches_common_hff_for_every_reachable_od(
    tmp_path: Path,
) -> None:
    java = shutil.which("java")
    javac = shutil.which("javac")
    assert java is not None
    assert javac is not None

    classes = tmp_path / "classes"
    bridge.feng_runner.compile_java(javac=javac, classes_dir=classes)
    output = tmp_path / "feng_static_od.csv"
    completed = subprocess.run(
        [
            java,
            "-Djava.awt.headless=true",
            "-cp",
            str(classes),
            bridge.feng_runner.MAIN_CLASS,
            "static-bridge",
            "--map",
            str(bridge.MAP_PATH),
            "--csv-out",
            str(output),
        ],
        cwd=bridge.ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    rows = _rows(output)
    assert len(rows) == 1510
    assert all(
        row[
            "observed_matches_edge_plus_post_admission_node_service_quantization"
        ]
        == "true"
        for row in rows
    )

    parsed = parse_legacy_map(bridge.MAP_PATH)
    nodes, edges = bridge._map_records(parsed)
    hff, contract = potential.free_flow_potential(nodes, edges)
    assert contract["node_service_time_included"] is False
    for row in rows:
        path = bridge.shared_hff_path(
            parsed, hff, int(row["start_node"]), int(row["goal_node"])
        )
        assert ">".join(str(node) for node in path) == row["node_path"]
        assert abs(float(row["quantization_bias_seconds"])) <= 1.0e-12
        assert abs(
            float(row["edge_plus_post_admission_node_service_quantized_seconds"])
            - float(row["edge_quantized_seconds"])
            - float(row["post_admission_node_service_seconds"])
        ) <= 1.0e-12


def test_bridge_label_does_not_claim_causal_executor_subtraction() -> None:
    source = bridge.__doc__ or ""
    assert "never as a causal subtraction" in source
    paired = bridge._paired_od_rows(
        [
            {
                "start_node": "0",
                "goal_node": "1",
                "node_path": "0>1",
                "origin_equal_score_candidates": "1",
                "ideal_free_flow_seconds": "1.2",
                "edge_quantized_seconds": "1.2",
                "legacy_path_node_service_seconds": "0.0",
                "post_admission_node_service_seconds": "0.0",
                "edge_plus_post_admission_node_service_quantized_seconds": "1.2",
                "observed_single_bag_seconds": "1.2",
                "quantization_bias_seconds": "0.0",
            }
        ],
        [
            {
                "start_node": 0,
                "goal_node": 1,
                "common_path": "0>1",
                "common_edge_travel_seconds": 1.2,
                "common_node_service_seconds": 0.001,
                "common_single_bag_tht_seconds": 1.201,
                "common_source_queue_delay_seconds": 0.0,
                "common_local_wait_seconds": 0.0,
                "common_retry_count": 0,
            }
        ],
    )
    assert paired[0]["path_match"] is True
    assert paired[0]["empty_network_gate"] is True
    assert abs(
        paired[0]["single_bag_mechanical_gap_common_minus_feng_seconds"] - 0.001
    ) < 1.0e-12


def test_full_bridge_reads_explicit_final_admission_diagnostic_fields() -> None:
    feng = {
        "status": "COMPLETE",
        "raw_bag_count": "1",
        "completed_raw_bags": "1",
        "segment_count": "1",
        "completed_segments": "1",
        "diagnostic_first_admission_to_completion_min_seconds": "10",
        "diagnostic_first_admission_to_completion_mean_seconds": "11",
        "diagnostic_first_admission_to_completion_p95_seconds": "12",
        "diagnostic_first_admission_to_completion_p99_seconds": "13",
        "diagnostic_first_admission_to_completion_max_seconds": "14",
    }
    common = {
        "status": "COMPLETE",
        "population": {"raw_bag_count": 1, "segment_count": 1},
        "runtime": {"native_summary": {"completed_count": 1}},
        "paper_subjects": {
            "fixed_horizon_capacity": {"completed_raw_bag_count": 1},
            "full_population_raw_bag_timing": {
                "metrics_seconds": {
                    "paper_network_from_admission": {
                        "min": 20,
                        "mean": 21,
                        "p95": 22,
                        "p99": 23,
                        "max": 24,
                    }
                }
            },
        },
    }

    rows = bridge._full_rows(feng, common)

    assert rows[0]["tht_mean_seconds"] == 11.0
    assert "first-admission" in rows[0]["metric_definition"]

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.eval import run_g4irsf5_original_protocol_comparative_validation as g5


def test_segment_duration_summary_groups_split_bags_and_rejects_incomplete() -> None:
    rows = [
        (1, 0.0, 60.0),
        (1, 100.0, 220.0),
        (2, 5.0, 65.0),
    ]
    summary = g5.summarize_segment_duration_rows(rows, expected_counts={1: 2, 2: 1, 3: 1})

    assert summary.row_count == 3
    assert summary.raw_bag_count == 3
    assert summary.complete_bag_count == 2
    assert summary.failed_bag_count == 1
    assert summary.min_minutes == 1.0
    assert summary.mean_minutes == 2.0
    assert summary.max_minutes == 3.0


def test_parse_original_project_result_uses_segment_sum_tth() -> None:
    result_dir = ROOT / ".pytest_cache" / "czr005"
    result_dir.mkdir(parents=True, exist_ok=True)
    result_file = result_dir / "g4irsf5_original_project_result_sample.txt"
    result_file.write_text(
        "\n".join(
            [
                "0 3 0 60",
                "0 52 100 220",
                "1 4 10 130",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = g5.parse_original_project_result(result_file)

    assert summary is not None
    assert summary.row_count == 3
    assert summary.raw_bag_count == 2
    assert summary.complete_bag_count == 2
    assert summary.mean_minutes == 2.5


def test_paper_fault_scenarios_cover_all_table_5_5_rows() -> None:
    scenarios = g5._paper_fault_scenarios()

    assert len(scenarios) == 16
    assert scenarios[0] == ("paper_fault_arc_1", (1,), 1.0)
    assert scenarios[-1] == ("paper_fault_arcs_4_6_7", (4, 6, 7), 0.26)

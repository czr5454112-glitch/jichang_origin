from __future__ import annotations

from pathlib import Path

import pytest

from scripts.eval import g4irsf23_paper_baselines as baselines


@pytest.fixture(scope="module")
def summary() -> dict:
    return baselines.build_paper_baseline_summary()


def test_paper_identity_and_original_one_x_protocol_are_fixed(summary: dict) -> None:
    paper = summary["paper"]
    assert paper["doi"] == "10.1016/j.cie.2022.108802"
    assert paper["url"] == "https://doi.org/10.1016/j.cie.2022.108802"
    assert paper["primary_method"] == "centralized IoT-DRPA / HCA*"
    assert paper["one_x"]["raw_bag_count"] == 28_506
    assert paper["one_x"]["processed_segment_count"] == 43_603
    assert paper["one_x"]["primary_speed_mps"] == 2.5
    assert paper["one_x"]["loading_stations"] == 7
    assert paper["one_x"]["unloading_stations"] == 22
    assert paper["one_x"]["junctions"] == 44
    assert paper["one_x"]["paper_conveyors"] == 72


def test_all_paper_comparison_panels_are_retained(summary: dict) -> None:
    paper = summary["paper"]
    speeds = paper["table_5_2_speed_sweep"]
    assert [row["speed_mps"] for row in speeds] == [1.5, 2.0, 2.5, 3.0]
    assert next(row for row in speeds if row["speed_mps"] == 2.5) == {
        "speed_mps": 2.5,
        "min": 3.13,
        "avg": 3.96,
        "max": 5.98,
        "source": "表5.2",
    }
    table_5_3 = paper["table_5_3_iot_drpa_vs_dispersed_heuristic"]
    assert table_5_3["status"] == "PAPER_REPORTED_ONLY"
    assert table_5_3["rows"] == [
        {
            "method": "dispersed_heuristic",
            "min": 3.56,
            "avg": 4.43,
            "max": 8.62,
            "unit": "minutes",
            "source": "表5.3",
        },
        {
            "method": "iot_drpa_hca_star",
            "min": 3.13,
            "avg": 3.96,
            "max": 5.98,
            "unit": "minutes",
            "source": "表5.3",
        },
        {
            "method": "improvement",
            "min": 12.1,
            "avg": 10.6,
            "max": 30.6,
            "unit": "percent",
            "source": "表5.3",
        },
    ]
    dynamic = paper["table_5_4_dynamic_iot_drpa_vs_static_lra_star"]
    assert dynamic["baseline_status"] == "PAPER_REPORTED_ONLY"
    assert len(dynamic["rows"]) == 12
    assert len(paper["table_5_5_faults"]) == 16
    assert all(
        row["evidence_status"] == "PAPER_REPORTED_ONLY"
        for row in paper["table_5_5_faults"]
    )


def test_frozen_f2_and_original_hca_are_distinct_required_baselines(
    summary: dict,
) -> None:
    required = summary["required_baselines"]
    f2 = required["frozen_f2"]
    hca = required["original_hca_star"]
    assert f2["baseline_id"] == "G4IRSF13_F2_FROZEN"
    assert f2["one_x"]["complete_raw_bags"] == 28_506
    assert f2["one_x"]["failed_segments"] == 0
    assert f2["one_x"]["runtime_full_astar_calls"] == 0
    assert f2["one_x"]["original_entry_mean_minutes"] == pytest.approx(
        41.514218717973414
    )

    assert hca["baseline_id"] == "original_project_iot_drpa_hca_star"
    assert hca["fresh_java_rerun"] is False
    assert hca["one_x"]["processed_segment_attempt_time_tth"][
        "mean_minutes"
    ] == pytest.approx(3.96712271)
    assert hca["one_x"]["java_release_time_tth_mean_minutes"] == pytest.approx(
        5.19722515
    )
    assert hca["one_x"]["java_release_time_tth_min_minutes"] == pytest.approx(
        3.13333333
    )
    assert hca["one_x"]["java_release_time_tth_max_minutes"] == pytest.approx(
        24.31666667
    )
    assert hca["one_x"][
        "legacy_mislabeled_original_entry_min_minutes"
    ] == pytest.approx(3.11684817)
    assert hca["one_x"][
        "legacy_mislabeled_original_entry_max_minutes"
    ] == pytest.approx(27.14962583)
    assert hca["one_x"][
        "matched_raw_entry_time_tth_mean_minutes"
    ] == pytest.approx(43.13593828041816)


def test_hca_is_not_fabricated_beyond_the_paper_one_x_scope(summary: dict) -> None:
    hca = summary["required_baselines"]["original_hca_star"]
    assert hca["scale_availability"] == {
        "1x": "HISTORICAL_PARSED_ORIGINAL_PROJECT_OUTPUT",
        "2x": "N/A_NOT_IN_PAPER_PROTOCOL",
        "4x": "N/A_NOT_IN_PAPER_PROTOCOL",
    }
    contract = summary["comparison_contract"]
    assert contract["hca_2x"] == "N/A_NOT_IN_PAPER_PROTOCOL"
    assert contract["hca_4x"] == "N/A_NOT_IN_PAPER_PROTOCOL"
    assert contract["cross_denominator_winner_claim_allowed"] is False


def test_summary_reads_only_committed_repository_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = baselines.ROOT.resolve()
    observed: list[Path] = []
    original_open = Path.open
    original_read_text = Path.read_text

    def checked_open(path: Path, *args: object, **kwargs: object):
        resolved = path.resolve()
        assert resolved.is_relative_to(root)
        observed.append(resolved)
        return original_open(path, *args, **kwargs)

    def checked_read_text(path: Path, *args: object, **kwargs: object) -> str:
        resolved = path.resolve()
        assert resolved.is_relative_to(root)
        observed.append(resolved)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", checked_open)
    monkeypatch.setattr(Path, "read_text", checked_read_text)
    baselines.build_paper_baseline_summary(root)
    assert set(observed) == {
        (root / relative).resolve()
        for relative in (
            baselines.F2_PATH,
            baselines.DENOMINATOR_PATH,
            baselines.PROTOCOL_PATH,
            baselines.METRICS_PATH,
            baselines.BASELINE_INVENTORY_PATH,
            baselines.BASELINE_RESULT_PATH,
            baselines.DENOMINATOR_TABLE_PATH,
        )
    }


def test_cli_can_write_compact_committed_summary(tmp_path: Path) -> None:
    output = tmp_path / "paper_baselines.json"
    assert baselines.main(["--output", str(output)]) == 0
    payload = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "czr005.g4irsf23.paper_dual_baseline.v1"

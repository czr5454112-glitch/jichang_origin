from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.eval import render_cie_activation_figures as renderer


def _write_activation_csv(path: Path) -> None:
    row: dict[str, object] = {
        "map": "map2",
        "nominal_load_factor": "1.00",
    }
    for component, opportunities, changes in (
        ("q", 100, 5), ("i", 80, 0), ("wc", 50, 2), ("ws", 0, 0)
    ):
        row[f"{component}_decision_any_candidate_nonzero_count"] = opportunities
        row[f"{component}_counterfactual_raw_argmin_change_count"] = changes
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def _write_runtime_json(path: Path, *, fixed_denominator: bool = True) -> None:
    denominator = 10
    completed = 8
    payload = {
        "schema": renderer.SCHEMA_RUN,
        "native_execution_started": True,
        "map": "map2",
        "nominal_load_factor": 1.0,
        "population": {"raw_bag_denominator": denominator},
        "fixed_denominator_business": {
            "detailed": {
                "denominator_raw_bags": denominator,
                "completed_raw_bag_count": completed,
                "completion_rate": completed / denominator,
                "on_time_raw_bag_count": 7,
                "on_time_rate": 0.7,
                "fixed_denominator": fixed_denominator,
                "survivor_or_common_cohort_used": False,
                "backlog": {
                    "raw_bag_total": {
                        "arrival_count": denominator,
                        "departure_count": completed,
                        "peak_backlog": 6,
                        "backlog_at_last_arrival": 4,
                        "end_backlog": 2,
                    }
                },
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_render_figures_keeps_missing_cells_na_and_writes_nonempty_pngs(
    tmp_path: Path,
) -> None:
    activation_csv = tmp_path / "activation.csv"
    runtime_root = tmp_path / "runtime"
    figure_root = tmp_path / "figures"
    runtime_root.mkdir()
    _write_activation_csv(activation_csv)
    _write_runtime_json(runtime_root / "map2_1x.json")

    result = renderer.render_figures(
        activation_csv=activation_csv,
        runtime_root=runtime_root,
        figure_root=figure_root,
    )

    assert result["observed_fixed_denominator_cell_count"] == 1
    assert len(result["missing_fixed_denominator_cells"]) == 9
    assert result["pre_feasibility_raw_argmin_is_final_action"] is False
    for output in result["outputs"].values():
        content = Path(output).read_bytes()
        assert content.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(content) > 1_000


def test_runtime_curve_rejects_non_fixed_denominator_payload(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    _write_runtime_json(runtime_root / "invalid.json", fixed_denominator=False)

    with pytest.raises(renderer.ActivationFigureError, match="fixed-denominator flag"):
        renderer._runtime_points(runtime_root)

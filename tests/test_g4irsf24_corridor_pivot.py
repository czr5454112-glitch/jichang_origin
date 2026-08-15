from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import run_g4irsf24_corridor_pivot as pivot


def _artifact(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "czr005.g4irsf24.dlp.v1",
                "mode": "ewma",
                "beta": 1.0,
                "min_support": 8,
                "margin_seconds": 0.5,
                "detour_allowance_seconds": 2.0,
                "edge_residuals": [],
                "value_residuals": [],
            }
        ),
        encoding="utf-8",
    )


def _patch_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pivot.capacity,
        "load_g18_scale_input",
        lambda scale, root: ([{"segment_id": f"bag-{scale}"}], {}),
    )
    monkeypatch.setattr(
        pivot.campaign,
        "_exact_release_rows",
        lambda rows, release_csv: rows,
    )


def test_incomplete_arm_fails_closed_without_metric_arithmetic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.json"
    _artifact(artifact)
    _patch_inputs(monkeypatch)

    def failed_run(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": "FAILED_ARM",
            "safety": {"pass": False},
            "timing": {},
            "dlp": {},
            "events_per_completed": None,
            "deadline_miss_count": None,
        }

    monkeypatch.setattr(pivot.campaign, "_run_complete", failed_run)
    output = tmp_path / "corridor.json"
    result = pivot.run_campaign(
        binary=tmp_path / "native.pyd",
        release_csv=tmp_path / "release.csv",
        artifact_path=artifact,
        output=output,
    )

    assert result["status"] == "CORRIDOR_NO_GO_KEEP_S4"
    assert result["active_policy"] == "S4"
    assert result["gates"]["all_comparison_metrics_available"] is False
    assert all(row["metrics_available"] is False for row in result["comparisons"])
    assert all(row["mean_delta_seconds"] is None for row in result["comparisons"])
    assert output.exists()


def test_hold_plus_two_x_win_requires_explicit_fresh_hca_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.json"
    _artifact(artifact)
    _patch_inputs(monkeypatch)

    timings = {
        (1, "S4"): (100.0, 120.0, 130.0),
        (1, "CORRIDOR"): (100.0, 120.0, 130.0),
        (2, "S4"): (200.0, 220.0, 230.0),
        (2, "CORRIDOR"): (190.0, 210.0, 220.0),
    }

    def passing_run(**kwargs: Any) -> dict[str, Any]:
        case_id = str(kwargs["case_id"])
        scale = int(case_id.split("_")[1][0])
        arm = case_id.rsplit("_", 1)[-1]
        mean, p95, p99 = timings[(scale, arm)]
        return {
            "status": "PASS",
            "safety": {"pass": True},
            "timing": {
                "processed_attempt": {
                    "mean_seconds": mean,
                    "p95_seconds": p95,
                    "p99_seconds": p99,
                }
            },
            "dlp": {
                "g4irsf24_dlp_committed_mutation_count": (
                    20 if arm == "CORRIDOR" else 0
                )
            },
            "events_per_completed": 10.0,
            "deadline_miss_count": 0,
        }

    monkeypatch.setattr(pivot.campaign, "_run_complete", passing_run)
    common = {
        "binary": tmp_path / "native.pyd",
        "release_csv": tmp_path / "release.csv",
        "artifact_path": artifact,
    }

    unverified = pivot.run_campaign(
        **common,
        output=tmp_path / "unverified.json",
    )
    verified = pivot.run_campaign(
        **common,
        output=tmp_path / "verified.json",
        s4_already_beats_fresh_hca=True,
    )

    assert unverified["status"] == "CORRIDOR_NO_GO_KEEP_S4"
    assert verified["status"] == "CORRIDOR_GO"
    assert verified["active_policy"] == "CORRIDOR"
    gate = "one_x_business_win_or_hold_with_two_x_win"
    assert unverified["gates"][gate] is False
    assert verified["gates"][gate] is True

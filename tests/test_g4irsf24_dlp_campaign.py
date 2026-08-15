from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.eval import run_g4irsf24_dlp_campaign as campaign


def _binding(binary: Path, work: Path, release_csv: Path) -> dict[str, str]:
    return campaign._campaign_binding(
        binary=binary,
        work=work,
        release_csv=release_csv,
    )


def test_scale_rejects_ladder_from_a_different_campaign(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "native.pyd"
    work = tmp_path / "work"
    release_csv = tmp_path / "release.csv"
    binding = _binding(binary, work, release_csv)
    campaign._write_json(
        work / "state.json",
        {
            "schema": campaign.SCHEMA,
            "stage": "COLLECTED_AND_FIT",
            **binding,
        },
    )
    ladder_path = tmp_path / "ladder.json"
    campaign._write_json(
        ladder_path,
        {
            "schema": campaign.SCHEMA,
            "stage": "NATIVE_1X_2X",
            "status": "NO_GO_KEEP_S4",
            "winner_candidate_id": None,
            **binding,
            "exact_1x_release_csv": str(tmp_path / "different_release.csv"),
        },
    )

    with pytest.raises(campaign.DLPCampaignError, match="campaign binding mismatch"):
        campaign.scale_abba(
            binary=binary,
            work=work,
            ladder_path=ladder_path,
            output=tmp_path / "scale.json",
        )


def test_sixty_second_scale_pass_is_pending_and_keeps_s4_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "native.pyd"
    work = tmp_path / "work"
    release_csv = tmp_path / "release.csv"
    binding = _binding(binary, work, release_csv)
    winner = "DLP_EWMA_A"
    artifact_path = tmp_path / "artifact.json"
    artifact = {
        "schema": "czr005.g4irsf24.dlp.v1",
        "mode": "ewma",
        "beta": 1.0,
        "min_support": 8,
        "margin_seconds": 0.5,
        "detour_allowance_seconds": 2.0,
        "edge_residuals": [],
        "value_residuals": [],
    }
    campaign._write_json(artifact_path, artifact)
    campaign._write_json(
        work / "state.json",
        {
            "schema": campaign.SCHEMA,
            "stage": "COLLECTED_AND_FIT",
            "artifacts": {winner: str(artifact_path)},
            **binding,
        },
    )
    ladder_path = tmp_path / "ladder.json"
    campaign._write_json(
        ladder_path,
        {
            "schema": campaign.SCHEMA,
            "stage": "NATIVE_1X_2X",
            "status": "GO",
            "winner_candidate_id": winner,
            **binding,
        },
    )
    monkeypatch.setattr(
        campaign.capacity,
        "load_g18_scale_input",
        lambda scale, root: ([{"segment_id": "bag"}], {}),
    )
    monkeypatch.setattr(
        campaign.hotpath,
        "build_native_request",
        lambda *args, **kwargs: {},
    )

    def fake_native(**request: Any) -> dict[str, Any]:
        candidate = "g4irsf24_dlp_artifact" in request
        summary: dict[str, Any] = {}
        if candidate:
            summary = {
                "g4irsf24_dlp_mode": "ewma",
                "g4irsf24_dlp_edge_residual_count": 0,
                "g4irsf24_dlp_value_residual_count": 0,
                "g4irsf24_dlp_committed_mutation_count": 1,
            }
        return {"candidate": candidate, "summary": summary}

    def fake_bounded(
        native: dict[str, Any], **kwargs: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        candidate = bool(native["candidate"])
        return (
            {
                "status": "COMPLETE",
                "progress": {
                    "failed_bags": 0,
                    "completed_bags": 120 if candidate else 100,
                    "released_bags": 150,
                    "current_backlog": 80 if candidate else 100,
                    "simulated_time": 120 if candidate else 100,
                },
                "metrics": {
                    "events_per_completed_bag": 8 if candidate else 10,
                    "events_per_wall_second": 100,
                },
                "resources": {
                    "native_wall_seconds": 1,
                    "native_process_cpu_seconds": 1,
                },
                "hard_safety": {"pass": True},
            },
            {},
        )

    monkeypatch.setattr(
        campaign.cpp_backend,
        "g4irsf11_event_runtime_from_records",
        fake_native,
    )
    monkeypatch.setattr(campaign.hotpath, "_bounded_result", fake_bounded)
    policy_output = tmp_path / "selected_policy.json"
    campaign._write_json(policy_output, {"stale": True})
    selection_output = tmp_path / "selection.json"

    result = campaign.scale_abba(
        binary=binary,
        work=work,
        ladder_path=ladder_path,
        output=tmp_path / "scale.json",
        policy_output=policy_output,
        selection_output=selection_output,
    )

    assert result["status"] == "EXTEND_180S_PENDING"
    assert result["candidate_id"] == winner
    assert result["active_policy"] == "S4"
    assert result["selection"]["selected_candidate_id"] is None
    assert result["selection"]["stale_policy_removed"] is True
    assert not policy_output.exists()

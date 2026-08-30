from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf32_v3r12_nanning_p0_canary as canary


def _external(index: int, *, source_line: int | None = None) -> dict:
    task_id = 10_000 + index
    return {
        "segment_id": f"{task_id}:storage_out",
        "task_id": task_id,
        "start": 53,
        "goal": 49,
        "leg": "storage_out",
        "pass_time": canary.EXTERNAL_RELEASE,
        "std": 80_000.0,
        "source_line": task_id if source_line is None else source_line,
    }


def _local(*, release: float = 68_459.64183, source_line: int = 25_197) -> dict:
    return {
        "segment_id": canary.LOCAL_SEGMENT_ID,
        "task_id": canary.LOCAL_TASK_ID,
        "start": 49,
        "goal": 71,
        "leg": "direct",
        "pass_time": release,
        "std": 72_000.0,
        "source_line": source_line,
    }


def _pool(*, source_line_offset: int = 0) -> list[dict]:
    rows = [
        _external(index, source_line=source_line_offset + index)
        for index in range(65)
    ]
    rows.extend(
        [
            _local(source_line=source_line_offset + 100),
            {
                **_local(release=canary.LOCAL_WINDOW_CLOSE + 1.0),
                "segment_id": "30000:direct",
                "task_id": 30_000,
            },
        ]
    )
    return list(reversed(rows))


def test_fixed_selector_is_transparently_outcome_informed() -> None:
    cohort, selected = canary.select_engineering_canary(_pool())

    assert len(selected) == 62
    assert [row["segment_id"] for row in selected[:61]] == [
        f"{10_000 + index}:storage_out" for index in range(61)
    ]
    assert selected[-1]["segment_id"] == "25195:direct"
    assert cohort["selection_basis"] == "outcome_informed_engineering_canary"
    assert cohort["selection_role"] == (
        "ENGINEERING_EXISTENCE_CANARY_NOT_EFFECT_ESTIMATE"
    )
    assert cohort["selection_outcome_blind"] is False
    assert cohort["formal_inference_eligible"] is False
    assert cohort["engineering_canary_only"] is True
    assert cohort["external_commit_rank"] == 60
    assert cohort["local_window_open"] < cohort["local_release"] < cohort[
        "local_window_close"
    ]


def test_two_scale_selection_ignores_nonidentity_source_line_numbering() -> None:
    _, one = canary.select_engineering_canary(_pool(source_line_offset=0))
    _, two = canary.select_engineering_canary(_pool(source_line_offset=50_000))

    assert canary._selected_identity(one) == canary._selected_identity(two)
    assert [row["source_line"] for row in one] != [
        row["source_line"] for row in two
    ]


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([_external(index) for index in range(60)] + [_local()], "fewer than 61"),
        (
            [_external(index) for index in range(61)]
            + [_local(release=canary.LOCAL_WINDOW_OPEN)],
            "has no local row",
        ),
        (
            [_external(index) for index in range(61)]
            + [
                {
                    **_local(),
                    "segment_id": "25196:direct",
                    "task_id": 25_196,
                }
            ],
            "is not 25195:direct",
        ),
    ],
)
def test_selector_rejects_incomplete_boundary_or_wrong_local(
    rows: list[dict], message: str
) -> None:
    with pytest.raises(canary.SelectionError, match=message):
        canary.select_engineering_canary(rows)


def test_g31_request_is_exact_off_and_uses_active_scenario(monkeypatch) -> None:
    class FakeAuditor:
        NS = "source_aware_destination_service_"
        REQUEST_PROJECTION = {"retry_interval": 0.25, "fault_windows": []}
        REQUEST_DATA_KEYS = frozenset(
            {
                "node_records",
                "edge_records",
                "heuristic_time",
                "bag_records",
                "scenario",
                "storage_source_nodes",
                "source_aware_destination_service_mode",
            }
        )
        REQUEST_BINARY_LOCATOR_KEYS = frozenset(
            {"expected_binary_path", "search_path"}
        )

    def fake_build(_profile, rows, *, binary, scenario, **_kwargs):
        return (
            {
                "retry_interval": 0.25,
                "node_records": [[49, 1], [53, 7]],
                "edge_records": [],
                "heuristic_time": {},
                "bag_records": [[index] for index, _row in enumerate(rows)],
                "scenario": scenario,
                "storage_source_nodes": [53],
                "expected_binary_path": binary,
                "search_path": binary.parent,
            },
            {"pass": True},
        )

    monkeypatch.setattr(canary.map_adapter, "load_map_profile", lambda *_a, **_k: object())
    monkeypatch.setattr(canary.map_adapter, "build_s4_request", fake_build)
    binary = Path("C:/tmp/fake/czr005_cpp.pyd")
    rows = [_external(index) for index in range(61)] + [_local()]

    request, potential = canary.build_g31_control_request(
        2, rows, binary=binary, auditor=FakeAuditor()
    )

    assert request["scenario"] == "g4irsf32_v3r12_nanning_p0_canary_2x"
    assert request["storage_source_nodes"] == [53]
    assert request["fault_windows"] == []
    assert not any(key.startswith(FakeAuditor.NS) for key in request)
    assert potential == {"pass": True}


def _prerequisite(binary_sha: str) -> dict:
    auditor = canary.historical._v3_auditor()
    return {
        "synthetic_revision_id": canary.PREREQUISITE_SYNTHETIC_REVISION_ID,
        "campaign_revision_id": canary.PREREQUISITE_CAMPAIGN_REVISION_ID,
        "historical_control_revision_id": canary.HISTORICAL_CONTROL_REVISION_ID,
        "status": auditor.SYNTHETIC_PASS,
        "decision": auditor.SYNTHETIC_PASS,
        "synthetic_pass": True,
        "implementation_head": "a" * 40,
        "g32_binary_sha256": binary_sha,
        "artifact_content_sha256": "b" * 64,
    }


def test_active_control_and_historical_prerequisite_are_distinct() -> None:
    binary_sha = "c" * 64
    assert canary.CONTROL_REVISION_ID != canary.HISTORICAL_CONTROL_REVISION_ID
    validated = canary._validate_prerequisite(
        _prerequisite(binary_sha), expected_g32_binary_sha256=binary_sha
    )
    assert validated["historical_control_revision_id"] == (
        canary.historical.CONTROL_REVISION_ID
    )

    contaminated = deepcopy(validated)
    contaminated["historical_control_revision_id"] = canary.CONTROL_REVISION_ID
    with pytest.raises(canary.SelectionError, match="binding is invalid"):
        canary._validate_prerequisite(
            contaminated, expected_g32_binary_sha256=binary_sha
        )


def test_registered_control_path_matches_v3r12_addendum() -> None:
    assert canary.OUTPUT_PATH == (
        canary.ROOT
        / "outputs/tables/g4irsf32_v3r12_nanning_p0_control_selection.json"
    )

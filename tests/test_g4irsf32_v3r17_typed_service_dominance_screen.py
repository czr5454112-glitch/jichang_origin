from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import (
    run_g4irsf32_v3r17_typed_service_dominance_screen as runner,
)


def _binary(tmp_path: Path, build: str = "build_g32_v3r17") -> Path:
    path = tmp_path / build / "python" / "Release" / "czr005_cpp.fake.pyd"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fixture")
    return path.resolve()


def _case_slice(case_id: str) -> tuple[Mapping[str, Any], runner.WorkloadSlice]:
    registration = runner._read_preregistration()
    case = next(row for row in registration["cases"] if row["case_id"] == case_id)
    slices = runner._load_workload_slices(registration)
    return case, slices[(str(case["map_id"]), int(case["scale"]))]


def test_fixed_three_arms_change_only_the_candidate_scorer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_map2_1x_stable_2p5")
    requests, _runtime_rows, _rejected = runner._build_arm_requests(
        case, workload, binary=binary
    )
    mode_key = runner.stage2.stage01.NS + "mode"

    assert tuple(requests) == runner.ARMS
    assert requests["off"]["scorer_mode"] == runner.OLD_SCORER
    assert mode_key not in requests["off"]
    assert requests["candidate_a"][mode_key] == runner.HISTORICAL_MODE
    assert requests["candidate_a_dominance"][mode_key] == runner.HISTORICAL_MODE
    assert requests["candidate_a_dominance"]["scorer_mode"] == (
        runner.CANDIDATE_SCORER
    )
    different = {
        key
        for key in requests["candidate_a"]
        if requests["candidate_a"].get(key)
        != requests["candidate_a_dominance"].get(key)
    }
    assert different == {"scorer_mode"}

    calls: list[tuple[str, str]] = []

    def execute(_executor: Any, request: Mapping[str, Any], **kwargs: Any) -> dict:
        calls.append((kwargs["arm"], str(request["scorer_mode"])))
        return {"arm": kwargs["arm"]}

    def evaluate(_case: Any, _workload: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "arms": kwargs["arms"],
            "primary": kwargs["primary_arm"],
            "attribution": kwargs["attribution_arm"],
        }

    monkeypatch.setattr(runner, "_execute_arm", execute)
    monkeypatch.setattr(runner.shared, "_evaluate_three_arm_case", evaluate)
    result = runner._run_case(
        case, workload, executor=lambda **_request: {}, binary=binary
    )

    assert calls == [
        ("off", runner.OLD_SCORER),
        ("candidate_a", runner.OLD_SCORER),
        ("candidate_a_dominance", runner.CANDIDATE_SCORER),
    ]
    assert result["primary"] == "candidate_a_dominance"
    assert result["attribution"] == "candidate_a"


def test_core_pass_is_measurement_required_and_never_stage3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _binary(tmp_path)
    registration = {
        "cases": [
            {
                "case_id": f"case-{index}",
                "map_id": (
                    runner.stage2.nanning_native.MAP_ID
                    if index < 6
                    else runner.stage2.map2_native.MAP_ID
                ),
                "scale": 1,
            }
            for index in range(10)
        ]
    }
    sentinel = object()
    monkeypatch.setattr(runner, "_read_preregistration", lambda: registration)
    monkeypatch.setattr(
        runner,
        "_load_workload_slices",
        lambda _registration: {
            (runner.stage2.nanning_native.MAP_ID, 1): sentinel,
            (runner.stage2.map2_native.MAP_ID, 1): sentinel,
        },
    )
    monkeypatch.setattr(
        runner,
        "_run_case",
        lambda case, _workload, **_kwargs: {
            "case_id": case["case_id"],
            "map_id": case["map_id"],
            "pass": True,
        },
    )

    result = runner.run_screen(
        executor=lambda **_request: pytest.fail("native executor called"),
        binary=binary,
    )

    assert result["status"] == runner.MEASUREMENT_REQUIRED
    assert result["core_screen_pass"] is True
    assert result["measurement_only_support_required"] is True
    assert result["formal_measurement_pass"] is None
    assert result["stage3_authorized"] is False
    assert result["execution_count"] == 30
    assert result["arms"] == list(runner.ARMS)
    assert result["primary_comparison"] == "candidate_a_dominance/off"


def test_v3r17_binary_binding_and_append_only_output(tmp_path: Path) -> None:
    binary = _binary(tmp_path)
    assert runner._resolve_binary(binary) == binary
    with pytest.raises(runner.TypedServiceDominanceScreenError, match="v3r17"):
        runner._resolve_binary(_binary(tmp_path, "build_g32_v3r16"))

    json_path = tmp_path / "out" / "screen.json"
    markdown_path = tmp_path / "out" / "screen.md"
    result = {
        "status": runner.NO_GO,
        "core_screen_pass": False,
        "gates": {"all_nanning_core_gates": False},
        "cases": [],
    }
    runner.write_evidence(
        result, json_path=json_path, markdown_path=markdown_path
    )

    assert json.loads(json_path.read_text(encoding="utf-8")) == result
    assert "V3R17 typed service-dominance" in markdown_path.read_text(
        encoding="utf-8"
    )
    with pytest.raises(FileExistsError, match="append-only"):
        runner.write_evidence(
            result, json_path=json_path, markdown_path=markdown_path
        )

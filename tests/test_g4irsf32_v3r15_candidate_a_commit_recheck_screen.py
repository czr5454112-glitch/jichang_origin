from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import (
    run_g4irsf32_v3r15_candidate_a_commit_recheck_screen as runner,
)


def _binary(tmp_path: Path) -> Path:
    path = (
        tmp_path
        / "build_g32_v3r15"
        / "python"
        / "Release"
        / "czr005_cpp.fake.pyd"
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fixture")
    return path.resolve()


def _case_slice(case_id: str) -> tuple[Mapping[str, Any], runner.WorkloadSlice]:
    registration = runner._read_preregistration()
    case = next(row for row in registration["cases"] if row["case_id"] == case_id)
    slices = runner._load_workload_slices(registration)
    return case, slices[(str(case["map_id"]), int(case["scale"]))]


def _arm(request: Mapping[str, Any]) -> str:
    mode = request.get(runner.stage2.stage01.NS + "mode")
    if mode is None:
        return "off"
    if mode == runner.HISTORICAL_MODE:
        return "candidate_a"
    if mode == runner.RECHECK_MODE:
        return "candidate_a_recheck"
    raise AssertionError(f"unexpected injected mode: {mode}")


def _summary(
    request: Mapping[str, Any],
    *,
    recheck_action_count: int = 0,
) -> dict[str, Any]:
    completed = len(request["bag_records"])
    value: dict[str, Any] = {
        key: 0 for key in runner.stage2.stage01.SAFETY_ZERO_KEYS
    }
    value.update({key: 0 for key in runner.stage2.stage01.MODEL_ZERO_KEYS})
    value.update(
        requested_count=completed,
        completed_count=completed,
        failed_count=0,
        event_count=completed * 10,
        safe_execution_pass=True,
        max_edges_selected_per_bag_per_decision=1,
        event_limit_reached=False,
        time_limit_reached=False,
        artificial_batch_delay_seconds=0.0,
        merge_grant_conservation_holds=True,
        merge_grant_active_bijection_holds=True,
        merge_grant_protocol_integrity_pass=True,
        event_trace_truncated=False,
        full_future_routes_stored=0,
        starvation_count=0,
        bag_future_path_field_present=False,
        full_cie_astar_runtime_fallback=False,
        max_source_queue_length=10,
        max_junction_queue_length=4,
        merge_grant_peak_pending_requests=3,
        scorer_mode_echo=runner.OLD_SCORER,
        scorer_id=runner.OLD_SCORER,
    )
    arm = _arm(request)
    if arm != "off":
        action_count = recheck_action_count if arm == "candidate_a_recheck" else 0
        value.update(
            {
                runner.stage2.stage01.NS + "mode": request[
                    runner.stage2.stage01.NS + "mode"
                ],
                runner.stage2.stage01.NS + "action_change_count": action_count,
                runner.stage2.stage01.NS + "calendar_mutation_count": action_count,
                runner.stage2.stage01.NS + "future_release_read_count": 0,
                runner.stage2.stage01.NS + "global_scan_count": 0,
            }
        )
    return value


def _payload(
    request: Mapping[str, Any],
    *,
    recheck_latency: float = 100.0,
    recheck_action_count: int = 0,
) -> dict[str, Any]:
    latency = recheck_latency if _arm(request) == "candidate_a_recheck" else 100.0
    bags = []
    for record in request["bag_records"]:
        segment_id, task_id, release, _deadline, start, _goal, _source = record
        source_wait = 10.0 if int(start) == 49 else 5.0
        bags.append(
            {
                "segment_id": segment_id,
                "task_id": task_id,
                "release_time": release,
                "admitted_time": release + source_wait,
                "finish_time": release + latency,
                "completed": True,
            }
        )
    return {
        "summary": _summary(
            request, recheck_action_count=recheck_action_count
        ),
        "bags": bags,
        "events": [],
        "junction_state": [],
        "resource_metrics": {
            "measurement_scope": "isolated_worker_process",
            "wall_seconds": 1.0,
        },
    }


def test_exact_three_arms_change_only_extension_mode_and_do_not_write_or_run_native(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_map2_1x_stable_2p5")
    calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(
        runner,
        "cpp_executor",
        lambda **_request: pytest.fail("injected screen loaded native code"),
    )
    monkeypatch.setattr(
        runner,
        "write_evidence",
        lambda *_args, **_kwargs: pytest.fail("in-memory screen wrote evidence"),
    )

    def executor(**request: Any) -> Mapping[str, Any]:
        calls.append(
            (
                _arm(request),
                str(request["scorer_mode"]),
                request.get(runner.stage2.stage01.NS + "mode"),
            )
        )
        assert request["expected_binary_path"] == binary
        assert request["event_trace_limit"] == 0
        return _payload(request)

    result = runner._run_case(
        case, workload, executor=executor, binary=binary
    )

    assert calls == [
        ("off", runner.OLD_SCORER, None),
        ("candidate_a", runner.OLD_SCORER, runner.HISTORICAL_MODE),
        ("candidate_a_recheck", runner.OLD_SCORER, runner.RECHECK_MODE),
    ]
    assert list(result["arms"]) == list(runner.ARMS)
    assert result["primary_comparison"]["candidate"] == "candidate_a_recheck"
    assert result["attribution_only_comparison"] == {
        **result["attribution_only_comparison"],
        "candidate": "candidate_a_recheck",
        "control": "candidate_a",
        "gate_bearing": False,
    }
    assert result["pass"] is True
    assert not runner.OUTPUT_JSON.exists()
    assert not runner.OUTPUT_MD.exists()


def test_nanning_target_p95_miss_is_no_go(tmp_path: Path) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_nanning_1x_stable_2p5")

    result = runner._run_case(
        case,
        workload,
        executor=lambda **request: _payload(request),
        binary=binary,
    )

    assert result["pass"] is False
    assert result["performance_ratios"]["target_p95"] == pytest.approx(1.0)
    assert result["gates"]["nanning_target_p95_improves_2pct"] is False
    assert all(
        passed
        for name, passed in result["gates"].items()
        if name != "nanning_target_p95_improves_2pct"
    )


def test_map2_recheck_action_is_a_hard_no_go(tmp_path: Path) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_map2_1x_stable_2p5")

    result = runner._run_case(
        case,
        workload,
        executor=lambda **request: _payload(
            request, recheck_action_count=1
        ),
        binary=binary,
    )

    safety = result["arms"]["candidate_a_recheck"]["safety"]
    assert safety["action_count"] == safety["calendar_mutation_count"] == 1
    assert safety["gates"]["map2_structural_negative_no_action"] is False
    assert result["gates"]["hard_safety"] is False
    assert result["pass"] is False


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("scorer_mode_echo", "wrong-scorer", "native scorer identity"),
        (
            runner.stage2.stage01.NS + "mode",
            runner.HISTORICAL_MODE,
            "native extension mode echo",
        ),
    ],
)
def test_native_identity_echo_must_match_recheck_request(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_map2_1x_stable_2p5")

    def executor(**request: Any) -> Mapping[str, Any]:
        payload = _payload(request)
        if _arm(request) == "candidate_a_recheck":
            payload["summary"][field] = replacement
        return payload

    with pytest.raises(runner.CandidateARecheckScreenError, match=message):
        runner._run_case(case, workload, executor=executor, binary=binary)


def test_core_pass_requires_measurement_but_never_authorizes_stage3(
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
    assert result["stage3_authorized"] is False
    assert result["execution_count"] == 30

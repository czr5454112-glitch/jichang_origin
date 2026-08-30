from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf32_v3r14_candidate_b_screen as runner


def _binary(tmp_path: Path) -> Path:
    path = (
        tmp_path
        / "build_g32_v3r14"
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
    if runner.stage2.stage01.NS + "mode" not in request:
        return "off"
    if request["scorer_mode"] == runner.CANDIDATE_B_SCORER:
        return "candidate_a_b"
    return "candidate_a"


def _summary(
    request: Mapping[str, Any], *, events_per_completed: int = 10
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
        event_count=completed * events_per_completed,
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
        scorer_mode_echo=str(request["scorer_mode"]),
        scorer_id=str(request["scorer_mode"]),
    )
    if _arm(request) != "off":
        value.update(
            {
                runner.stage2.stage01.NS + "mode": "closed_loop",
                runner.stage2.stage01.NS + "action_change_count": 0,
                runner.stage2.stage01.NS + "calendar_mutation_count": 0,
                runner.stage2.stage01.NS + "future_release_read_count": 0,
                runner.stage2.stage01.NS + "global_scan_count": 0,
            }
        )
    return value


def _payload(
    request: Mapping[str, Any],
    *,
    candidate_a_b_latency: float = 100.0,
) -> dict[str, Any]:
    latency = candidate_a_b_latency if _arm(request) == "candidate_a_b" else 100.0
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
        "summary": _summary(request),
        "bags": bags,
        "events": [],
        "junction_state": [],
        # Deliberately no RSS value: it is not a core-screen gate.
        "resource_metrics": {
            "measurement_scope": "isolated_worker_process",
            "wall_seconds": 1.0,
        },
    }


def test_exact_three_arms_share_one_prepared_request_and_do_not_write_or_run_native(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_map2_1x_stable_2p5")
    calls: list[tuple[str, str, int]] = []

    monkeypatch.setattr(
        runner,
        "cpp_executor",
        lambda **_request: pytest.fail("injected screen loaded the native executor"),
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
                id(request["bag_records"]),
            )
        )
        assert request["expected_binary_path"] == binary
        assert request["event_trace_limit"] == 0
        return _payload(request)

    result = runner._run_case(case, workload, executor=executor, binary=binary)

    assert [(arm, scorer) for arm, scorer, _records in calls] == [
        ("off", runner.OLD_SCORER),
        ("candidate_a", runner.OLD_SCORER),
        ("candidate_a_b", runner.CANDIDATE_B_SCORER),
    ]
    assert list(result["arms"]) == list(runner.ARMS)
    assert result["pass"] is True
    assert result["diagnostics"]["rss_status"].startswith("NOT_REQUIRED")
    assert result["diagnostics"][
        "start49_source_wait_proxy_is_formal_mixed_integral"
    ] is False


def test_nanning_target_p95_miss_is_a_core_no_go(tmp_path: Path) -> None:
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


def test_map2_regression_over_half_percent_is_a_core_no_go(tmp_path: Path) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_map2_1x_stable_2p5")

    result = runner._run_case(
        case,
        workload,
        executor=lambda **request: _payload(
            request, candidate_a_b_latency=200.0
        ),
        binary=binary,
    )

    assert result["pass"] is False
    assert result["performance_ratios"]["mean"] > 1.005
    assert result["gates"]["map2_mean_regression_at_most_0p5pct"] is False
    assert result["gates"]["map2_p95_regression_at_most_0p5pct"] is False
    assert result["gates"]["map2_p99_regression_at_most_0p5pct"] is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("scorer_mode_echo", "wrong-scorer"), ("scorer_id", None)],
)
def test_native_scorer_identity_must_match_request(
    tmp_path: Path, field: str, replacement: str | None
) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_map2_1x_stable_2p5")

    def executor(**request: Any) -> Mapping[str, Any]:
        payload = _payload(request)
        summary = payload["summary"]
        if _arm(request) == "candidate_a_b":
            if replacement is None:
                summary.pop(field)
            else:
                summary[field] = replacement
        return payload

    with pytest.raises(runner.CandidateBScreenError, match="native scorer identity"):
        runner._run_case(case, workload, executor=executor, binary=binary)


def test_candidate_a_attribution_safety_is_not_a_candidate_b_core_gate(
    tmp_path: Path,
) -> None:
    binary = _binary(tmp_path)
    case, workload = _case_slice("g4irsf32_s2_map2_1x_stable_2p5")

    def executor(**request: Any) -> Mapping[str, Any]:
        payload = _payload(request)
        if _arm(request) == "candidate_a":
            payload["summary"]["reservation_conflicts"] = 1
        return payload

    result = runner._run_case(case, workload, executor=executor, binary=binary)

    assert result["pass"] is True
    assert result["gates"]["hard_safety"] is True
    assert result["diagnostics"]["candidate_a_attribution_safety_pass"] is False

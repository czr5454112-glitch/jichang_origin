from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf32_v3r13_closed_loop_stage01 as runner


def _case_from_scenario(scenario: str) -> runner.ActionCase:
    matches = [case for case in runner.registered_cases() if case.scenario == scenario]
    assert len(matches) == 1
    return matches[0]


def _fake_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    case = _case_from_scenario(str(request["scenario"]))
    mode = str(request.get("source_aware_destination_service_mode", "off"))
    records = list(request["bag_records"])
    by_task = {int(record[1]): (owner, record) for owner, record in enumerate(records)}

    blockers = [int(record[1]) for record in records if "blocker" in str(record[0])]
    local = [int(record[1]) for record in records if str(record[6]) == "local"]
    external = [
        int(record[1])
        for record in records
        if str(record[6]) == "external" and int(record[1]) not in blockers
    ]
    changed = [task for task in external if "changed" in str(by_task[task][1][0])]
    contenders = [task for task in external if task not in changed]

    if case.expected_action and mode == "closed_loop":
        order = blockers + local + contenders + changed
    elif case.control_kind == "reverse_priority":
        order = blockers + [int(case.priority_external_task_id)] + [int(case.local_task_id)]
    elif case.case_id == "immediately_available":
        order = local + external
    else:
        order = blockers + contenders + local + changed
        if not blockers and not contenders and not changed:
            order = local
        if not local:
            order = external

    start_by_owner: dict[int, float] = {}
    cursor = 0.0
    for task_id in order:
        owner, record = by_task[task_id]
        release = float(record[2])
        transit = 0.0 if str(record[6]) == "local" else 0.05
        start = max(cursor, release + transit)
        start_by_owner[owner] = start
        cursor = start + runner.SERVICE_SECONDS

    bags = []
    events = []
    action_owner = None
    if case.expected_action and mode == "closed_loop":
        action_owner = by_task[int(case.local_task_id)][0]
    for owner, record in enumerate(records):
        segment_id, task_id, release, deadline, start_node, goal, source = record
        service_start = start_by_owner[owner]
        bags.append(
            {
                "runtime_bag_id": owner,
                "segment_id": segment_id,
                "task_id": task_id,
                "release_time": release,
                "deadline": deadline,
                "start": start_node,
                "goal": goal,
                "source": source,
                "admitted_time": service_start,
                "completed": True,
                "finish_time": service_start + runner.SERVICE_SECONDS + 0.1,
            }
        )
        if source == "local":
            events.append(
                {
                    "event": "LOCAL_QUEUE_UPDATE",
                    "runtime_bag_id": owner,
                    "task_id": task_id,
                    "segment_id": segment_id,
                    "node": runner.SERVICE_NODE,
                    "time": service_start,
                    "reason": (
                        runner.ACTION_REASON
                        if owner == action_owner
                        else "source_dequeue"
                    ),
                }
            )
        events.append(
            {
                "event": "JUNCTION_SERVICE_COMPLETE",
                "runtime_bag_id": owner,
                "task_id": task_id,
                "segment_id": segment_id,
                "node": runner.SERVICE_NODE,
                "from_node": -1 if source == "local" else start_node,
                "to_node": runner.SERVICE_NODE,
                "time": service_start + runner.SERVICE_SECONDS,
                "reason": "junction_service_complete",
            }
        )
    events.sort(key=lambda row: (float(row["time"]), str(row["event"]), int(row["runtime_bag_id"])))
    for seq, event in enumerate(events, start=1):
        event["seq"] = seq

    summary = {
        key: 0 for key in runner.SAFETY_ZERO_KEYS + runner.MODEL_ZERO_KEYS
    }
    summary.update(
        {
            "requested_count": len(records),
            "completed_count": len(records),
            "failed_count": 0,
            "event_count": len(events),
            "final_active_bag_count": 0,
            "safe_execution_pass": True,
            "max_edges_selected_per_bag_per_decision": 1,
            "event_limit_reached": False,
            "time_limit_reached": False,
            "artificial_batch_delay_seconds": 0.0,
            "merge_grant_conservation_holds": True,
            "merge_grant_active_bijection_holds": True,
            "merge_grant_protocol_integrity_pass": True,
            "cpp_internal_accounted_bytes": 512,
            "internal_state_bytes": 512,
            "runtime_seconds": 0.1,
        }
    )
    trace_context: dict[str, Any] = {"schema_id": "ordinary.v1"}
    payload: dict[str, Any] = {
        "summary": summary,
        "trace_context": trace_context,
        "bags": bags,
        "events": events,
        "decisions": [],
        "hold_attempts": [],
        "merge_grant_lifecycle": [],
        "junction_state": [
            {
                "node": runner.SERVICE_NODE,
                "service_reservation_count": len(records),
                "final_source_queue_length": 0,
                "final_junction_queue_length": 0,
                "scheduled_incoming": 0,
                "peak_local_state_accounted_bytes": 100,
            }
        ],
    }
    if mode in {"shadow", "closed_loop"}:
        count = 1 if action_owner is not None else 0
        summary.update(
            {
                runner.NS + "mode": mode,
                runner.NS + "action_change_count": count,
                runner.NS + "calendar_mutation_count": count,
                runner.NS + "future_release_read_count": 0,
                runner.NS + "global_scan_count": 0,
            }
        )
        trace_context[runner.NS + "mode"] = mode
    if mode == "shadow":
        payload[runner.NS + "shadow"] = []
    return payload


def test_registered_small_population_and_request_arms_are_frozen() -> None:
    cases = runner.registered_cases()

    assert len(cases) == 8
    assert [case.control_kind for case in cases].count("reverse_priority") == 1
    assert {case.control_kind for case in cases} >= {
        "no_local",
        "no_external",
        "immediately_available",
        "future_release_base",
        "future_release_perturbed",
    }
    for case in cases:
        if case.j2:
            releases = {row[0]: row[2] for row in case.rows}
            local_release = next(
                release for segment, release in releases.items() if "local" in segment
            )
            pending_release = next(
                release
                for segment, release in releases.items()
                if "external" in segment
            )
            assert pending_release < local_release
    assert runner.OUTPUT_JSON == (
        runner.ROOT / "outputs/tables/g4irsf32_v3r13_closed_loop_stage01.json"
    )
    assert runner.OUTPUT_MD == (
        runner.ROOT / "outputs/reports/g4irsf32_v3r13_closed_loop_stage01.md"
    )

    for case in cases:
        requests = {
            mode: runner.build_case_request(case, mode=mode) for mode in runner.MODES
        }
        assert runner._without_extension(requests["off"]) == runner._without_extension(
            requests["shadow"]
        ) == runner._without_extension(requests["closed_loop"])
        assert runner.NS + "mode" not in requests["off"]
        assert requests["shadow"][runner.NS + "mode"] == "shadow"
        assert requests["closed_loop"][runner.NS + "mode"] == "closed_loop"
        assert len(requests["off"]["bag_records"]) <= 4


def test_injected_campaign_passes_all_action_control_and_resource_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def executor(**request: Any) -> Mapping[str, Any]:
        calls.append(
            (
                str(request["scenario"]),
                str(request.get(runner.NS + "mode", "off")),
            )
        )
        return _fake_payload(request)

    monkeypatch.setattr(
        runner,
        "write_evidence",
        lambda *_args, **_kwargs: pytest.fail("in-memory campaign attempted to write"),
    )
    result = runner.run_campaign(executor=executor)

    assert result["status"] == runner.PASS
    assert result["stage2_authorized"] is True
    assert result["execution_count"] == 24
    assert len(calls) == 24
    assert Counter(mode for _scenario, mode in calls) == {
        "off": 8,
        "shadow": 8,
        "closed_loop": 8,
    }
    indexed = {case["case_id"]: case for case in result["cases"]}
    assert indexed["direct_mixed_contention"]["action"]["action_count"] == 1
    assert indexed["j2_mixed_contention"]["action"]["action_count"] == 1
    assert indexed["j2_reverse_priority_external"]["action"]["action_count"] == 0
    for name in ("no_local", "no_external", "immediately_available"):
        assert indexed[name]["action"]["action_count"] == 0
        assert indexed[name]["checks"]["registered_noop_exact"] is True
    assert result["gates"]["future_release_perturbation_exact"] is True


def _wrapped_executor(mutator):
    def execute(**request: Any) -> Mapping[str, Any]:
        payload = _fake_payload(request)
        mutator(payload, request)
        return payload

    return execute


def test_shadow_ordinary_mutation_is_rejected() -> None:
    def mutate(payload: dict[str, Any], request: Mapping[str, Any]) -> None:
        if (
            request["scenario"].endswith("direct_mixed_contention")
            and request.get(runner.NS + "mode") == "shadow"
        ):
            payload["bags"][0]["finish_time"] += 0.25

    result = runner.run_campaign(executor=_wrapped_executor(mutate))
    direct = result["cases"][0]

    assert result["status"] == runner.NO_GO
    assert direct["checks"]["shadow_action_inert_exact"] is False


def test_action_and_calendar_counters_must_match_the_ordinary_action_event() -> None:
    def mutate(payload: dict[str, Any], request: Mapping[str, Any]) -> None:
        if (
            request["scenario"].endswith("direct_mixed_contention")
            and request.get(runner.NS + "mode") == "closed_loop"
        ):
            payload["summary"][runner.NS + "calendar_mutation_count"] = 0

    result = runner.run_campaign(executor=_wrapped_executor(mutate))
    direct = result["cases"][0]

    assert result["pass"] is False
    assert direct["action"]["checks"]["counter_event_exact"] is False


def test_reverse_priority_requires_external_service_before_local() -> None:
    def mutate(payload: dict[str, Any], request: Mapping[str, Any]) -> None:
        if (
            request["scenario"].endswith("j2_reverse_priority_external")
            and request.get(runner.NS + "mode") == "closed_loop"
        ):
            case = _case_from_scenario(str(request["scenario"]))
            task_to_bag = {int(bag["task_id"]): bag for bag in payload["bags"]}
            local = task_to_bag[int(case.local_task_id)]
            external = task_to_bag[int(case.priority_external_task_id)]
            local_start = float(local["admitted_time"])
            external_start = float(external["admitted_time"])
            local["admitted_time"], external["admitted_time"] = (
                external_start,
                local_start,
            )
            for event in payload["events"]:
                task = int(event["task_id"])
                if task == int(case.local_task_id):
                    event["time"] -= local_start - external_start
                elif task == int(case.priority_external_task_id):
                    event["time"] += local_start - external_start

    result = runner.run_campaign(executor=_wrapped_executor(mutate))
    reverse = next(
        case
        for case in result["cases"]
        if case["case_id"] == "j2_reverse_priority_external"
    )

    assert result["pass"] is False
    assert reverse["checks"]["reverse_priority_external_wins"] is False


def test_future_release_perturbation_must_preserve_action_and_slot() -> None:
    def mutate(payload: dict[str, Any], request: Mapping[str, Any]) -> None:
        if (
            request["scenario"].endswith("future_release_perturbed")
            and request.get(runner.NS + "mode") == "closed_loop"
        ):
            for bag in payload["bags"]:
                bag["admitted_time"] += 10.0
                bag["finish_time"] += 10.0
            for event in payload["events"]:
                event["time"] += 10.0

    result = runner.run_campaign(executor=_wrapped_executor(mutate))

    assert result["pass"] is False
    assert result["gates"]["future_release_perturbation_exact"] is False


def test_event_or_local_memory_ratio_over_1p10_is_rejected() -> None:
    def mutate(payload: dict[str, Any], request: Mapping[str, Any]) -> None:
        if (
            request["scenario"].endswith("direct_mixed_contention")
            and request.get(runner.NS + "mode") == "closed_loop"
        ):
            payload["junction_state"][0]["peak_local_state_accounted_bytes"] = 111

    result = runner.run_campaign(executor=_wrapped_executor(mutate))
    direct = result["cases"][0]

    assert result["pass"] is False
    assert direct["checks"]["resources_within_1p10"] is False
    assert direct["resource_ratios"]["closed_loop"][
        "junction_local_accounted_bytes"
    ] == pytest.approx(1.11)


def test_write_evidence_is_append_only_but_not_used_by_injected_runner(
    tmp_path: Path,
) -> None:
    result = runner.run_campaign(executor=lambda **request: _fake_payload(request))
    json_path = tmp_path / "stage01.json"
    md_path = tmp_path / "stage01.md"

    assert not json_path.exists() and not md_path.exists()
    runner.write_evidence(result, json_path=json_path, markdown_path=md_path)
    assert json_path.exists() and md_path.exists()
    with pytest.raises(FileExistsError, match="append-only"):
        runner.write_evidence(result, json_path=json_path, markdown_path=md_path)

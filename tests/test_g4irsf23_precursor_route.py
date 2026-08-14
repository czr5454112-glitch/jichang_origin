from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf23_precursor_route as runner


def _requests() -> list[dict[str, object]]:
    return [
        {
            "task_id": 10,
            "segment_id": "10:storage_in",
            "leg": "storage_in",
            "pass_time": 100.0,
            "start": 4,
            "goal": 47,
        },
        {
            "task_id": 11,
            "segment_id": "11:storage_in",
            "leg": "storage_in",
            "pass_time": 110.0,
            "start": 4,
            "goal": 47,
        },
        {
            "task_id": 10,
            "segment_id": "10:storage_out",
            "leg": "storage_out",
            "pass_time": 7 * 3600.0 + 20.0,
            "start": 52,
            "goal": 49,
        },
        {
            "task_id": 11,
            "segment_id": "11:storage_out",
            "leg": "storage_out",
            "pass_time": 8 * 3600.0 + 20.0,
            "start": 52,
            "goal": 49,
        },
    ]


def _anchor(
    task_id: int,
    runtime_bag_id: int,
    *,
    block: int,
    ordinal: int,
    event_time: float | None = None,
) -> dict[str, object]:
    return {
        "schema": "czr005.g4irsf23.source_pilot_group.v1",
        "source_group_id": f"source-{ordinal}-{runtime_bag_id}",
        "event_ordinal": ordinal,
        "event_seq": ordinal + 100,
        "event_time": float(block * 3600 + 40 if event_time is None else event_time),
        "runtime_bag_id": runtime_bag_id,
        "front_runtime_bag_id": runtime_bag_id,
        "task_id": task_id,
        "segment_id": f"{task_id}:storage_out",
        "leg": "storage_out",
        "node": 52,
        "release_block": block,
        # These post-action fields must never survive anchor normalization.
        "effect_label": "FAIR_SYSTEM_BENEFICIAL",
        "system_mean_delta_seconds": -999.0,
    }


def _candidate(node: int, event_time: float) -> dict[str, float]:
    return {
        "target_queue_length": float(node),
        "target_scheduled_incoming": 1.0,
        "priority_local_contention": 2.0,
        "target_next_available": event_time + 5.0,
        "travel_time": 1.0,
        "static_potential": 10.0,
        "priority_slack_seconds": 100.0,
        "event_time": event_time,
    }


def _route_event(
    ordinal: int,
    runtime_bag_id: int,
    event_time: float,
    *,
    node: int = 28,
    legal: list[int] | None = None,
    wait_available: bool = True,
) -> dict[str, object]:
    edges = legal or [30, 31]
    return {
        "schema_id": "czr005.g4irsf22.route_census.v1",
        "kind": "I3_NEXT_EDGE",
        "population_group_id": f"group-{ordinal}",
        "population_selection_id": f"selection-{ordinal}",
        "event_ordinal": ordinal,
        "event_seq": ordinal + 1,
        "event_time": event_time,
        "runtime_bag_id": runtime_bag_id,
        "current_node": node,
        "baseline_next_node": edges[0],
        "legal_next_edges": edges,
        "wait_available": wait_available,
        "candidate_next_nodes": edges,
        "candidate_observations": [_candidate(edge, event_time) for edge in edges],
        "baseline_candidate_index": 0,
        "normal_flow": True,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _execution_contract_targets(
    *, group_count: int = 512, system_group_count: int = 256
) -> list[dict[str, object]]:
    """Build the small wire subset needed to test sharding, not simulation."""

    targets: list[dict[str, object]] = []
    for group_index in range(group_count):
        horizons = (
            ("H_bag", "H_system")
            if group_index < system_group_count
            else ("H_bag",)
        )
        for horizon in horizons:
            for action_kind, selected_next_node in (
                ("NEXT_EDGE", 100 + group_index),
                ("WAIT", None),
            ):
                targets.append(
                    {
                        "schema": runner.g22.TARGET_SCHEMA,
                        "research_profile": runner.RESEARCH_PROFILE,
                        "population_group_id": f"group-{group_index:04d}",
                        "population_selection_id": f"selection-{group_index:04d}",
                        "event_ordinal": group_index,
                        "runtime_bag_id": 10_000 + group_index,
                        "horizon": horizon,
                        "action_kind": action_kind,
                        "selected_next_node": selected_next_node,
                    }
                )
    return targets


def _complete_pair(target: dict[str, object]) -> dict[str, object]:
    pair = {
        **target,
        "pair_status": "ACTION_CHANGED_HORIZON_COMPLETE",
        "same_state_start": True,
        "action_changed": True,
        "pair_complete": True,
        "live_safety_pass": True,
        "hard_gate_pass": True,
    }
    if target["horizon"] == "H_system":
        pair.update(
            formal_hard_gate_evaluated=True,
            formal_hard_gate_pass=True,
            affected_bag_deltas=[
                {
                    "runtime_bag_id": target["runtime_bag_id"],
                    "completion_delta_seconds": 0.0,
                }
            ],
        )
    return pair


def _compact_groups(
    *, group_count: int = 2, system_group_count: int = 2
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    targets = _execution_contract_targets(
        group_count=group_count, system_group_count=system_group_count
    )
    groups: list[dict[str, object]] = []
    for group_index in range(group_count):
        groups.append(
            {
                "population_group_id": f"group-{group_index:04d}",
                "population_selection_id": f"selection-{group_index:04d}",
                "event_ordinal": group_index,
                "runtime_bag_id": 10_000 + group_index,
                "current_node": 28 if group_index % 2 == 0 else 39,
                "release_block": 7 if group_index % 2 == 0 else 8,
                "selection_stratum": f"stratum-{group_index}",
                "event_time": 1000.0 + group_index,
                "baseline_candidate_index": 0,
                "candidate_observations": [
                    _candidate(30, 1000.0 + group_index),
                    _candidate(31, 1000.0 + group_index),
                ],
            }
        )
    return groups, targets


def _effect_pair(
    target: dict[str, object],
    *,
    mean_delta_seconds: float = -0.02,
    direct_delta_seconds: float = 0.0,
    tail_delta_seconds: float = 0.0,
    deadline_delta: int = 0,
) -> dict[str, object]:
    pair = _complete_pair(target)
    pair["committed_action_certificate"] = {
        "valid": True,
        "changed_action_count": 1,
        "pre_action_snapshots_match": True,
        "post_commit_verified": True,
        "committed_action_type": "EDGE_COMMIT",
    }
    pair["affected_bag_deltas"] = [
        {
            "runtime_bag_id": target["runtime_bag_id"],
            "completion_delta_seconds": direct_delta_seconds,
        }
    ]
    if target["horizon"] == "H_system":
        baseline = {
            "comparison_eligible": True,
            "original_entry_mean_minutes": 40.0,
            "source_wait_mean_minutes": 2.0,
            "network_time_mean_minutes": 6.0,
            "original_entry_p95_seconds": 3000.0,
            "original_entry_p99_seconds": 4000.0,
            "original_entry_max_seconds": 5000.0,
            "deadline_miss_raw_bag_count": 0,
        }
        treatment = {
            **baseline,
            "original_entry_mean_minutes": 40.0 + mean_delta_seconds / 60.0,
            "source_wait_mean_minutes": 2.0 - 0.01 / 60.0,
            "network_time_mean_minutes": 6.0 + 0.005 / 60.0,
            "original_entry_p95_seconds": 3000.0 + tail_delta_seconds,
            "original_entry_p99_seconds": 4000.0 + tail_delta_seconds,
            "original_entry_max_seconds": 5000.0 + tail_delta_seconds,
            "deadline_miss_raw_bag_count": deadline_delta,
        }
        pair["baseline"] = {"raw_bag_cohort_metrics": baseline}
        pair["treatment"] = {
            "raw_bag_cohort_metrics": treatment,
            "affected_bag_outcomes": [
                {
                    "runtime_bag_id": target["runtime_bag_id"],
                    "completed": True,
                    "failed": False,
                    "finish_time": 1500.0,
                    "deadline": 2000.0,
                }
            ],
        }
    return pair


def test_lifecycle_join_uses_preceding_storage_in_runtime_segment() -> None:
    anchors = [_anchor(10, 2, block=7, ordinal=1000)]
    links, audit = runner.link_lifecycle_anchors(anchors, _requests())

    assert audit == {
        "input_anchor_count": 1,
        "out_of_scope_release_block_count": 0,
        "unique_storage_out_anchor_count": 1,
        "lifecycle_linked_anchor_count": 1,
        "lifecycle_unmatched_anchor_count": 0,
    }
    assert links[0]["storage_out_runtime_bag_id"] == 2
    assert links[0]["predecessor_runtime_bag_id"] == 0
    assert links[0]["predecessor_segment_id"] == "10:storage_in"
    assert links[0]["task_id"] == 10
    assert "effect_label" not in links[0]["anchor_address"]
    assert "system_mean_delta_seconds" not in links[0]["anchor_address"]


def test_explicit_runtime_ids_allow_compact_request_descriptor_input() -> None:
    requests = [
        {
            "runtime_bag_id": 40,
            "task_id": 10,
            "segment_id": "10:storage_in",
            "leg": "storage_in",
            "pass_time": 100.0,
        },
        {
            "runtime_bag_id": 90,
            "task_id": 10,
            "segment_id": "10:storage_out",
            "leg": "storage_out",
            "pass_time": 7 * 3600.0 + 20.0,
        },
    ]
    anchor = _anchor(10, 90, block=7, ordinal=1000)

    links, audit = runner.link_lifecycle_anchors([anchor], requests)

    assert audit["lifecycle_linked_anchor_count"] == 1
    assert links[0]["predecessor_runtime_bag_id"] == 40
    assert links[0]["storage_out_runtime_bag_id"] == 90


def test_repeated_source_opportunities_collapse_to_first_address() -> None:
    late = _anchor(10, 2, block=7, ordinal=200, event_time=25_300.0)
    early = _anchor(10, 2, block=7, ordinal=100, event_time=25_250.0)

    links, audit = runner.link_lifecycle_anchors([late, early], _requests())

    assert len(links) == 1
    assert links[0]["anchor_address"]["event_ordinal"] == 100
    assert audit["input_anchor_count"] == 2
    assert audit["unique_storage_out_anchor_count"] == 1


def test_full_source_census_can_include_adjacent_blocks() -> None:
    outside = _anchor(10, 2, block=6, ordinal=50)
    inside = _anchor(10, 2, block=7, ordinal=100)

    links, audit = runner.link_lifecycle_anchors([outside, inside], _requests())

    assert len(links) == 1
    assert links[0]["release_block"] == 7
    assert audit["input_anchor_count"] == 2
    assert audit["out_of_scope_release_block_count"] == 1


def test_streaming_join_selects_latest_route_before_storage_out_release(
    tmp_path: Path,
) -> None:
    links, _ = runner.link_lifecycle_anchors(
        [_anchor(10, 2, block=7, ordinal=1000)], _requests()
    )
    release = float(links[0]["storage_out_release_time"])
    census = tmp_path / "route.jsonl"
    _write_jsonl(
        census,
        [
            _route_event(10, 0, release - 20.0),
            _route_event(11, 1, release - 2.0),  # another task
            _route_event(12, 0, release),  # release-time Route is still before node-52 admission
            _route_event(13, 0, release + 1.0),  # too late
        ],
    )

    groups, audit = runner.stream_lifecycle_precursors(links, census)

    assert len(groups) == 1
    group = groups[0]
    assert group["runtime_bag_id"] == 0
    assert group["event_ordinal"] == 12
    assert group["timing_stage"] == "precursor"
    assert group["lifecycle_address"]["storage_out_runtime_bag_id"] == 2
    assert group["lifecycle_address"]["predecessor_runtime_bag_id"] == 0
    assert group["precursor_time_gap_seconds"] == 0.0
    assert group["outcome_free"] is True
    assert group["absolute_ids_are_trace_only"] is True
    assert audit["route_census_row_count"] == 4
    assert audit["route_census_relevant_row_count"] == 3


def test_exact_actions_reuse_g21_target_contract_with_implicit_s4() -> None:
    group = _route_event(12, 0, 100.0, legal=[30, 31, 32])
    group.update(
        schema=runner.GROUP_SCHEMA,
        timing_stage="precursor",
        anchor_event_identity=_anchor(10, 2, block=7, ordinal=1000),
        assigned_horizons=["H_bag", "H_system"],
    )

    actions = runner.g22.enumerate_legal_actions(group)
    targets = runner.build_precursor_targets([group])

    assert actions == [
        {"action_kind": "NEXT_EDGE", "selected_next_node": 30, "is_baseline": True},
        {"action_kind": "NEXT_EDGE", "selected_next_node": 31, "is_baseline": False},
        {"action_kind": "NEXT_EDGE", "selected_next_node": 32, "is_baseline": False},
        {"action_kind": "WAIT", "selected_next_node": None, "is_baseline": False},
    ]
    assert len(targets) == 6
    assert {target["horizon"] for target in targets} == {"H_bag", "H_system"}
    assert all(target["schema"] == runner.g22.TARGET_SCHEMA for target in targets)
    assert all(target["research_profile"] == "G22_S4_J2_E2" for target in targets)
    assert all(target["runtime_bag_id"] == 0 for target in targets)
    assert not any(target.get("selected_next_node") == 30 for target in targets)


def test_plan_reports_explicit_no_go_when_block_quota_is_short(tmp_path: Path) -> None:
    requests = _requests()
    anchors = [
        _anchor(10, 2, block=7, ordinal=1000),
        _anchor(11, 3, block=8, ordinal=2000),
    ]
    census = tmp_path / "route.jsonl"
    _write_jsonl(
        census,
        [
            _route_event(10, 0, 1000.0),
            _route_event(20, 1, 2000.0, node=39),
        ],
    )

    plan = runner.build_precursor_plan(
        requests,
        anchors,
        census,
        block_group_targets={7: 2, 8: 1},
        block_h_system_targets={7: 1, 8: 1},
    )

    assert plan["selection"]["status"] == "NO_GO_INSUFFICIENT_PRECURSOR_SUPPORT"
    assert plan["selection"]["blocks"]["7"]["group_shortfall"] == 1
    assert plan["selection"]["blocks"]["8"]["group_shortfall"] == 0
    assert plan["selection"]["absolute_ids_used_as_model_features"] is False
    assert plan["counts"]["group_count"] == 2
    # Two legal edges + WAIT gives two treatments at both horizons.
    assert plan["counts"]["target_count"] == 8


def test_cli_is_plan_only_and_keeps_partial_no_go_outputs(tmp_path: Path) -> None:
    requests_path = tmp_path / "requests.json"
    requests_path.write_text(json.dumps(_requests()), encoding="utf-8")
    anchors_path = tmp_path / "anchors.jsonl"
    _write_jsonl(anchors_path, [_anchor(10, 2, block=7, ordinal=1000)])
    census_path = tmp_path / "route.jsonl"
    _write_jsonl(census_path, [_route_event(10, 0, 1000.0)])
    groups_path = tmp_path / "groups.jsonl"
    targets_path = tmp_path / "targets.jsonl"
    summary_path = tmp_path / "summary.json"
    manifest_path = tmp_path / "pair-shards.json"

    assert runner.main(
        [
            "--route-census",
            str(census_path),
            "--anchors",
            str(anchors_path),
            "--requests",
            str(requests_path),
            "--groups-output",
            str(groups_path),
            "--targets-output",
            str(targets_path),
            "--summary-output",
            str(summary_path),
            "--shard-manifest-output",
            str(manifest_path),
            "--allow-shortfall",
        ]
    ) == 0

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["selection"]["status"] == "NO_GO_INSUFFICIENT_PRECURSOR_SUPPORT"
    assert summary["route_census_reused_in_place"] is True
    assert summary["raw_census_copied"] is False
    assert groups_path.read_text(encoding="utf-8").count("\n") == 1
    # The first block-7 group is also in the H_system prefix: two treatments
    # (other edge and WAIT) at each of H_bag and H_system.
    assert targets_path.read_text(encoding="utf-8").count("\n") == 4
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["execution_default"] == "PLAN_ONLY_DO_NOT_START_PROCESSES"
    assert manifest["planned_target_count"] == 4
    assert manifest["expected_execution_target_count"] == 2
    assert manifest["h_system_subsumed_h_bag_target_count"] == 2
    assert manifest["shard_count"] == 1
    assert manifest["shards"][0]["target_count"] == 2
    assert summary["pair_shards"]["expected_execution_target_count"] == 2


def test_formal_cli_retains_the_pilot_h_system_prefix_contract() -> None:
    arguments = runner.parse_args(
        [
            "--route-census",
            "route.jsonl",
            "--anchors",
            "anchors.jsonl",
            "--mode",
            "formal",
            "--groups-output",
            "groups.jsonl",
            "--targets-output",
            "targets.jsonl",
            "--summary-output",
            "summary.json",
        ]
    )

    assert arguments.mode == "formal"
    assert sum(runner.DEFAULT_H_SYSTEM_BLOCK_GROUPS.values()) == 256


def test_pilot_manifest_subsumes_system_groups_h_bag_and_runs_1024_targets() -> None:
    targets = _execution_contract_targets()

    manifest = runner.build_pair_shard_manifest(targets)
    executed = runner.execution_targets(targets, manifest)

    assert len(targets) == 1536
    assert manifest["planned_target_count"] == 1536
    assert manifest["expected_execution_target_count"] == 1024
    assert manifest["h_system_subsumed_h_bag_target_count"] == 512
    assert manifest["system_group_count"] == 256
    assert manifest["h_bag_only_group_count"] == 256
    assert len(executed) == 1024
    assert sum(row["horizon"] == "H_system" for row in executed) == 512
    assert sum(row["horizon"] == "H_bag" for row in executed) == 512
    # No H_bag duplicate is replayed for a group whose identical action is
    # already observed through its longer H_system pair.
    assert not any(
        row["horizon"] == "H_bag" and int(row["event_ordinal"]) < 256
        for row in executed
    )


def test_pilot_manifest_has_24_complete_group_shards_16_system_plus_8_bag() -> None:
    manifest = runner.build_pair_shard_manifest(_execution_contract_targets())

    shards = manifest["shards"]
    system = [row for row in shards if row["panel"] == "SYSTEM_AND_BAG"]
    h_bag = [row for row in shards if row["panel"] == "H_BAG_ONLY"]
    assert manifest["shard_count"] == 24
    assert len(system) == 16
    assert len(h_bag) == 8
    assert all(row["group_count"] == 16 for row in system)
    assert all(row["target_count"] == 32 for row in system)
    assert all(row["horizon_target_counts"] == {"H_bag": 0, "H_system": 32} for row in system)
    assert all(row["group_count"] == 32 for row in h_bag)
    assert all(row["target_count"] == 64 for row in h_bag)
    assert all(row["horizon_target_counts"] == {"H_bag": 64, "H_system": 0} for row in h_bag)


def test_manifest_shard_selection_is_an_exact_target_allow_list() -> None:
    targets = _execution_contract_targets(group_count=4, system_group_count=2)
    manifest = runner.build_pair_shard_manifest(
        targets, system_shard_groups=1, h_bag_shard_groups=1
    )

    selected = runner.select_manifest_shard(targets, manifest, "system-001")

    shard = next(row for row in manifest["shards"] if row["shard_id"] == "system-001")
    assert [runner.precursor_target_id(row) for row in selected] == shard["target_ids"]
    assert {row["event_ordinal"] for row in selected} == {1}
    assert {row["horizon"] for row in selected} == {"H_system"}
    assert {row["action_kind"] for row in selected} == {"NEXT_EDGE", "WAIT"}
    with pytest.raises(runner.PrecursorRouteError, match="must match exactly once"):
        runner.select_manifest_shard(targets, manifest, "missing")

    tampered = json.loads(json.dumps(manifest))
    tampered["shards"][0]["target_ids"][0] += "|unknown"
    with pytest.raises(runner.PrecursorRouteError, match="unknown targets"):
        runner.select_manifest_shard(targets, tampered, "system-000")


def test_pair_merge_rejects_unknown_and_conflicting_native_pairs() -> None:
    targets = _execution_contract_targets(group_count=2, system_group_count=1)
    expected = runner.execution_targets(targets, runner.build_pair_shard_manifest(
        targets, system_shard_groups=1, h_bag_shard_groups=1
    ))
    first = _complete_pair(expected[0])

    unknown = dict(first, selected_next_node=999_999)
    with pytest.raises(runner.PrecursorRouteError, match="unexpected native pair"):
        runner.merge_pair_payloads([{"pairs": [unknown]}], expected)

    conflict = dict(first, pair_complete=False)
    with pytest.raises(runner.PrecursorRouteError, match="conflicting duplicate"):
        runner.merge_pair_payloads(
            [{"pairs": [first]}, {"pairs": [conflict]}], expected
        )

    merged = runner.merge_pair_payloads(
        [{"pairs": [first]}, {"pairs": [dict(first)]}], expected
    )
    assert merged["duplicate_pair_count"] == 1
    assert merged["coverage_complete"] is False


def test_partial_execution_coverage_is_an_explicit_no_go() -> None:
    targets = _execution_contract_targets(group_count=2, system_group_count=1)
    expected = runner.execution_targets(targets, runner.build_pair_shard_manifest(
        targets, system_shard_groups=1, h_bag_shard_groups=1
    ))

    gate = runner.exact_pair_gate({"pairs": [_complete_pair(expected[0])]}, expected)

    assert gate["status"] == "NO_GO_EXACT_PAIR_GATE"
    assert gate["pass"] is False
    assert gate["coverage_complete"] is False
    assert gate["expected_target_count"] == 4
    assert gate["observed_target_count"] == 1


def test_h_system_gate_requires_formal_and_affected_bag_evidence() -> None:
    targets = _execution_contract_targets(group_count=1, system_group_count=1)
    expected = runner.execution_targets(targets, runner.build_pair_shard_manifest(
        targets, system_shard_groups=1, h_bag_shard_groups=1
    ))
    complete = [_complete_pair(target) for target in expected]

    passed = runner.exact_pair_gate({"pairs": complete}, expected)
    assert passed["status"] == "PASS_EXACT_PAIR_GATE"
    assert passed["pass"] is True

    missing_evidence = [dict(pair) for pair in complete]
    missing_evidence[0]["affected_bag_deltas"] = []
    failed = runner.exact_pair_gate({"pairs": missing_evidence}, expected)
    assert failed["status"] == "NO_GO_EXACT_PAIR_GATE"
    assert "AFFECTED_BAG_COMPLETION_NOT_PRESERVED" in failed["failures"][0]["reasons"]

    missing_formal = [dict(pair) for pair in complete]
    missing_formal[0]["formal_hard_gate_evaluated"] = False
    failed = runner.exact_pair_gate({"pairs": missing_formal}, expected)
    reasons = failed["failures"][0]["reasons"]
    assert "FORMAL_HARD_GATE_NOT_EVALUATED" in reasons


def test_compactor_subsumes_same_action_h_bag_and_selects_best_eligible() -> None:
    groups, targets = _compact_groups(group_count=1, system_group_count=1)
    h_system = [target for target in targets if target["horizon"] == "H_system"]
    pairs = [
        _effect_pair(target, mean_delta_seconds=-0.02 if target["action_kind"] == "NEXT_EDGE" else -0.06)
        for target in h_system
    ]

    compact = runner.compact_precursor_pilot(
        {"pairs": pairs},
        groups,
        targets,
        required_h_bag_groups=1,
        required_h_system_groups=1,
        required_fair_promotion_groups=1,
        required_block8_promotion_groups=0,
        required_promotion_strata=1,
    )

    summary = compact["summary"]
    assert summary["status"] == "PASS_PRECURSOR_PILOT_SUPPORT"
    assert summary["h_bag_complete_group_count"] == 1
    assert summary["h_system_complete_group_count"] == 1
    assert len(compact["actions"]) == 2
    assert all(row["h_bag_subsumed_by_h_system"] for row in compact["actions"])
    assert all(row["gates"]["promotion_eligible"] for row in compact["actions"])
    selected = [row for row in compact["actions"] if row["selected_by_group"]]
    assert len(selected) == 1
    assert selected[0]["action_kind"] == "WAIT"
    assert selected[0]["effect_tier"] == "strong"


def test_h_system_effect_summary_separates_full_panel_and_promotions() -> None:
    fields = {
        "raw_bag_source_wait_mean_delta_seconds": -0.1,
        "raw_bag_network_time_mean_delta_seconds": 0.2,
        "raw_bag_p95_delta_seconds": 0.0,
        "raw_bag_p99_delta_seconds": 0.0,
        "raw_bag_max_delta_seconds": 0.0,
        "deadline_headroom_seconds": 80.0,
    }
    rows = [
        {
            "group_id": "g7",
            "release_block": 7,
            "h_system_planned": True,
            "evidence_horizon": "H_system",
            "evidence_status": "COMPLETE",
            "raw_bag_mean_delta_seconds": -0.04,
            "current_bag_cost_seconds": 4.0,
            "gates": {"promotion_eligible": True},
            **fields,
        },
        {
            "group_id": "g8",
            "release_block": 8,
            "h_system_planned": True,
            "evidence_horizon": "H_system",
            "evidence_status": "COMPLETE",
            "raw_bag_mean_delta_seconds": 0.02,
            "current_bag_cost_seconds": 10.0,
            "gates": {"promotion_eligible": False},
            **{**fields, "deadline_headroom_seconds": 120.0},
        },
        {
            "group_id": "bag-only",
            "release_block": 8,
            "h_system_planned": False,
            "evidence_horizon": "H_bag",
            "evidence_status": "COMPLETE",
        },
    ]

    summary = runner.summarize_h_system_action_effects(rows)

    assert summary["planned_h_system_action_count"] == 2
    assert summary["complete_h_system_action_count"] == 2
    assert summary["panel"]["release_block_action_counts"] == {"7": 1, "8": 1}
    mean_delta = summary["panel"]["metrics"]["raw_bag_mean_delta_seconds"]
    assert mean_delta["min"] == pytest.approx(-0.04)
    assert mean_delta["mean"] == pytest.approx(-0.01)
    assert mean_delta["median"] == pytest.approx(-0.01)
    assert mean_delta["max"] == pytest.approx(0.02)
    cost = summary["panel"]["metrics"]["current_bag_cost_seconds"]
    assert cost["mean"] == pytest.approx(7.0)
    headroom = summary["panel"]["metrics"]["deadline_headroom_seconds"]
    assert headroom["median"] == pytest.approx(100.0)
    assert summary["fair_promotions"]["action_count"] == 1
    assert summary["fair_promotions"]["group_count"] == 1
    assert summary["fair_promotions"]["metrics"][
        "current_bag_cost_seconds"
    ]["max"] == pytest.approx(4.0)


def test_compactor_fails_tail_deadline_and_coverage_gates_but_retains_direct_diagnostic() -> None:
    groups, targets = _compact_groups(group_count=2, system_group_count=2)
    first_group = targets[:4]
    # Supply only one group's two H_system branches.  Both are deliberately
    # unsafe for promotion while retaining exact action-change evidence.
    pairs = [
        _effect_pair(
            target,
            mean_delta_seconds=-0.10,
            direct_delta_seconds=0.002,
            tail_delta_seconds=0.002,
            deadline_delta=1,
        )
        for target in first_group
        if target["horizon"] == "H_system"
    ]

    compact = runner.compact_precursor_pilot(
        {"pairs": pairs},
        groups,
        targets,
        required_h_bag_groups=2,
        required_h_system_groups=2,
        required_fair_promotion_groups=1,
        required_block8_promotion_groups=1,
        required_promotion_strata=1,
    )

    summary = compact["summary"]
    assert summary["status"] == "NO_GO_PRECURSOR_PILOT_SUPPORT"
    assert summary["h_bag_complete_group_count"] == 1
    assert summary["h_system_complete_group_count"] == 1
    assert summary["fair_promotion_group_count"] == 0
    assert summary["gates"]["h_bag_group_coverage"] is False
    assert summary["gates"]["h_system_group_coverage"] is False
    observed = [row for row in compact["actions"] if row["evidence_status"] == "COMPLETE"]
    assert observed
    assert all(row["gates"]["tail"] is False for row in observed)
    assert all(row["gates"]["direct_cost"] is False for row in observed)
    assert all(row["gates"]["strict_no_delay"] is False for row in observed)
    assert all(row["gates"]["deadline"] is False for row in observed)


def test_system_beneficial_costly_within_headroom_is_fair_and_not_hidden() -> None:
    groups, targets = _compact_groups(group_count=1, system_group_count=1)
    h_system = [target for target in targets if target["horizon"] == "H_system"]
    pairs = [
        _effect_pair(target, mean_delta_seconds=-0.02, direct_delta_seconds=5.0)
        for target in h_system
    ]

    compact = runner.compact_precursor_pilot(
        {"pairs": pairs},
        groups,
        targets,
        required_h_bag_groups=1,
        required_h_system_groups=1,
        required_fair_promotion_groups=1,
        required_block8_promotion_groups=0,
        required_promotion_strata=1,
    )

    assert compact["summary"]["status"] == "PASS_PRECURSOR_PILOT_SUPPORT"
    assert compact["summary"]["system_beneficial_but_costly_action_count"] == 2
    assert compact["summary"]["fair_promotion_group_count"] == 1
    for row in compact["actions"]:
        assert row["deadline_headroom_seconds"] == pytest.approx(85.0)
        assert row["system_beneficial"] is True
        assert row["system_beneficial_but_costly"] is True
        assert row["strict_no_delay"] is False
        assert row["individual_cost_within_headroom"] is True
        assert row["individual_fair"] is True
        assert row["benefit_fairness_label"] == (
            "SYSTEM_BENEFICIAL_BUT_COSTLY_WITHIN_HEADROOM_FAIR"
        )
        assert row["gates"]["promotion_eligible"] is True


@pytest.mark.parametrize("missing", ["pre_action", "treatment_outcome"])
def test_individual_fairness_missing_evidence_fails_closed(missing: str) -> None:
    groups, targets = _compact_groups(group_count=1, system_group_count=1)
    h_system = [target for target in targets if target["horizon"] == "H_system"]
    pairs = [_effect_pair(target, direct_delta_seconds=5.0) for target in h_system]
    if missing == "pre_action":
        del groups[0]["candidate_observations"][0]["static_potential"]
    else:
        for pair in pairs:
            del pair["treatment"]["affected_bag_outcomes"]

    compact = runner.compact_precursor_pilot(
        {"pairs": pairs},
        groups,
        targets,
        required_h_bag_groups=1,
        required_h_system_groups=1,
        required_fair_promotion_groups=1,
        required_block8_promotion_groups=0,
        required_promotion_strata=1,
    )

    assert compact["summary"]["status"] == "NO_GO_PRECURSOR_PILOT_SUPPORT"
    assert compact["summary"]["system_beneficial_action_count"] == 2
    assert compact["summary"]["fair_promotion_group_count"] == 0
    for row in compact["actions"]:
        assert row["system_beneficial"] is True
        assert row["individual_fair_evidence_complete"] is False
        assert row["individual_fair"] is False
        assert row["gates"]["promotion_eligible"] is False
        assert row["benefit_fairness_label"] == (
            "SYSTEM_BENEFICIAL_FAIRNESS_EVIDENCE_MISSING"
        )


def test_max_regression_is_separate_diagnostic_not_tail_hard_gate() -> None:
    groups, targets = _compact_groups(group_count=1, system_group_count=1)
    h_system = [target for target in targets if target["horizon"] == "H_system"]
    pairs = [_effect_pair(target, tail_delta_seconds=0.0) for target in h_system]
    for pair in pairs:
        pair["treatment"]["raw_bag_cohort_metrics"][
            "original_entry_max_seconds"
        ] += 10.0

    compact = runner.compact_precursor_pilot(
        {"pairs": pairs},
        groups,
        targets,
        required_h_bag_groups=1,
        required_h_system_groups=1,
        required_fair_promotion_groups=1,
        required_block8_promotion_groups=0,
        required_promotion_strata=1,
    )

    assert compact["summary"]["status"] == "PASS_PRECURSOR_PILOT_SUPPORT"
    assert all(row["gates"]["tail"] is True for row in compact["actions"])
    assert all(row["gates"]["max_diagnostic"] is False for row in compact["actions"])
    assert all(row["gates"]["promotion_eligible"] is True for row in compact["actions"])


def test_compact_csv_and_report_are_small_auditable_outputs(tmp_path: Path) -> None:
    groups, targets = _compact_groups(group_count=1, system_group_count=1)
    pairs = [
        _effect_pair(target)
        for target in targets
        if target["horizon"] == "H_system"
    ]
    compact = runner.compact_precursor_pilot(
        {"pairs": pairs},
        groups,
        targets,
        required_h_bag_groups=1,
        required_h_system_groups=1,
        required_fair_promotion_groups=1,
        required_block8_promotion_groups=0,
        required_promotion_strata=1,
    )
    csv_path = tmp_path / "actions.csv"
    runner.write_compact_action_csv(csv_path, compact["actions"])
    report = runner.render_compact_report(compact["summary"])

    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 3
    assert "raw_bag_mean_delta_seconds" in rows[0]
    assert "affected_bag_deltas" not in rows[0]
    assert "PASS_PRECURSOR_PILOT_SUPPORT" in report
    assert "no duplicate replay or new planner" in report
    assert "H_system effect distribution" in report
    assert "fair promotion actions/groups: 2 / 1" in report


def test_cli_pair_merge_writes_compact_csv_json_and_report(tmp_path: Path) -> None:
    requests_path = tmp_path / "requests.json"
    requests_path.write_text(json.dumps(_requests()), encoding="utf-8")
    anchors_path = tmp_path / "anchors.jsonl"
    _write_jsonl(anchors_path, [_anchor(10, 2, block=7, ordinal=1000)])
    census_path = tmp_path / "route.jsonl"
    _write_jsonl(census_path, [_route_event(10, 0, 1000.0)])
    plan = runner.build_precursor_plan(
        _requests(),
        [_anchor(10, 2, block=7, ordinal=1000)],
        census_path,
        block_group_targets={7: 1, 8: 0},
        block_h_system_targets={7: 1, 8: 0},
    )
    execution = runner.execution_targets(
        plan["targets"], runner.build_pair_shard_manifest(plan["targets"])
    )
    pair_path = tmp_path / "pairs.json"
    pair_path.write_text(
        json.dumps({"pairs": [_effect_pair(target) for target in execution]}),
        encoding="utf-8",
    )
    paths = {
        name: tmp_path / filename
        for name, filename in (
            ("groups", "groups.jsonl"),
            ("targets", "targets.jsonl"),
            ("summary", "summary.json"),
            ("merged", "merged.json"),
            ("gate", "gate.json"),
            ("actions", "actions.csv"),
            ("compact", "compact.json"),
            ("report", "report.md"),
        )
    }

    assert runner.main(
        [
            "--route-census", str(census_path),
            "--anchors", str(anchors_path),
            "--requests", str(requests_path),
            "--groups-output", str(paths["groups"]),
            "--targets-output", str(paths["targets"]),
            "--summary-output", str(paths["summary"]),
            "--pair-result", str(pair_path),
            "--merged-pairs-output", str(paths["merged"]),
            "--gate-output", str(paths["gate"]),
            "--compact-actions-output", str(paths["actions"]),
            "--compact-result-output", str(paths["compact"]),
            "--compact-report-output", str(paths["report"]),
            "--allow-shortfall",
        ]
    ) == 0

    assert paths["actions"].is_file()
    assert paths["compact"].is_file()
    assert paths["report"].is_file()
    compact = json.loads(paths["compact"].read_text(encoding="utf-8"))
    assert compact["summary"]["status"] == "NO_GO_PRECURSOR_PILOT_SUPPORT"
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["precursor_pilot"]["h_system_complete_group_count"] == 1


def test_cli_partial_pair_merge_writes_no_go_artifacts_and_returns_nonzero(
    tmp_path: Path,
) -> None:
    requests_path = tmp_path / "requests.json"
    requests_path.write_text(json.dumps(_requests()), encoding="utf-8")
    anchors_path = tmp_path / "anchors.jsonl"
    _write_jsonl(anchors_path, [_anchor(10, 2, block=7, ordinal=1000)])
    census_path = tmp_path / "route.jsonl"
    _write_jsonl(census_path, [_route_event(10, 0, 1000.0)])
    plan = runner.build_precursor_plan(
        _requests(),
        [_anchor(10, 2, block=7, ordinal=1000)],
        census_path,
        block_group_targets={7: 1, 8: 0},
        block_h_system_targets={7: 1, 8: 0},
    )
    execution = runner.execution_targets(
        plan["targets"], runner.build_pair_shard_manifest(plan["targets"])
    )
    pair_path = tmp_path / "partial-pairs.json"
    pair_path.write_text(
        json.dumps({"pairs": [_effect_pair(execution[0])]}),
        encoding="utf-8",
    )
    paths = {
        name: tmp_path / filename
        for name, filename in (
            ("groups", "groups.jsonl"),
            ("targets", "targets.jsonl"),
            ("summary", "summary.json"),
            ("merged", "merged.json"),
            ("gate", "gate.json"),
            ("actions", "actions.csv"),
            ("compact", "compact.json"),
            ("report", "report.md"),
        )
    }

    assert runner.main(
        [
            "--route-census", str(census_path),
            "--anchors", str(anchors_path),
            "--requests", str(requests_path),
            "--groups-output", str(paths["groups"]),
            "--targets-output", str(paths["targets"]),
            "--summary-output", str(paths["summary"]),
            "--pair-result", str(pair_path),
            "--merged-pairs-output", str(paths["merged"]),
            "--gate-output", str(paths["gate"]),
            "--compact-actions-output", str(paths["actions"]),
            "--compact-result-output", str(paths["compact"]),
            "--compact-report-output", str(paths["report"]),
            "--allow-shortfall",
        ]
    ) == 2

    gate = json.loads(paths["gate"].read_text(encoding="utf-8"))
    assert gate["status"] == "NO_GO_EXACT_PAIR_GATE"
    assert gate["coverage_complete"] is False
    assert gate["expected_target_count"] == 2
    assert gate["observed_target_count"] == 1
    assert paths["actions"].is_file()
    assert paths["compact"].is_file()
    assert paths["report"].is_file()
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["exact_pair_gate"]["pass"] is False

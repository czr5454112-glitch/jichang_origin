from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf23_externality_neighborhood as runner


def _candidate(
    event_time: float, *, target_queue: float, two_hop: float
) -> dict[str, float | bool]:
    return {
        "advertised_fault": False,
        "event_time": event_time,
        "target_queue_length": target_queue,
        "target_scheduled_incoming": 1.0,
        "target_next_available": event_time + 3.0,
        "travel_time": 2.0,
        "static_potential": 10.0,
        "priority_slack_seconds": 100.0,
        "priority_local_contention": two_hop,
        "two_hop_queue_pressure": two_hop,
    }


def _event(
    ordinal: int,
    runtime_bag_id: int,
    block: int,
    *,
    target_queue: float = 20.0,
    two_hop: float = 32.0,
    current_node: int = 16,
    baseline_next_node: int = 17,
    alternate_next_node: int = 21,
) -> dict[str, object]:
    event_time = block * 900.0 + ordinal / 1000.0
    nodes = [baseline_next_node, alternate_next_node]
    return {
        "kind": "I3_NEXT_EDGE",
        "population_group_id": f"group-{ordinal}",
        "population_selection_id": f"selection-{ordinal}",
        "event_ordinal": ordinal,
        "event_seq": ordinal + 100,
        "event_time": event_time,
        "runtime_bag_id": runtime_bag_id,
        "current_node": current_node,
        "baseline_next_node": baseline_next_node,
        "legal_next_edges": nodes,
        "wait_available": True,
        "candidate_next_nodes": nodes,
        "candidate_observations": [
            _candidate(event_time, target_queue=4.0, two_hop=4.0),
            _candidate(event_time, target_queue=target_queue, two_hop=two_hop),
        ],
        "baseline_candidate_index": 0,
        "normal_flow": True,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _historical_payload(
    *, ordinal: int = 9000, runtime_bag_id: int = 99
) -> dict[str, object]:
    return {
        "pairs": [
            {
                "horizon": "H_system",
                "population_group_id": f"history-group-{ordinal}",
                "population_selection_id": f"history-selection-{ordinal}",
                "event_ordinal": ordinal,
                "resolved_execution_descriptor": {
                    "runtime_bag_id": runtime_bag_id,
                },
            }
        ]
    }


def _history_file(tmp_path: Path, *, runtime_bag_id: int = 99) -> Path:
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps(_historical_payload(runtime_bag_id=runtime_bag_id)),
        encoding="utf-8",
    )
    return path


def _planned_groups(count: int = 32) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    groups: list[dict[str, object]] = []
    for index in range(count):
        block = 22 + index % 8
        event = _event(index, 10_000 + index, block)
        event.update(
            timing_stage="current",
            time_block=block,
            pressure_bin="q16_23",
            selection_cell=f"block_{block}|q16_23",
        )
        groups.append(event)
    return groups, runner.build_targets(groups)


def _complete_pair(
    target: dict[str, object],
    *,
    mean_delta_seconds: float = -0.02,
    tail_delta_seconds: float = 0.0,
    max_delta_seconds: float | None = None,
    direct_delta_seconds: float = 5.0,
    deadline_delta: int = 0,
    current_bag_completed: bool = True,
    current_bag_failed: bool = False,
    current_bag_finish_time: float = 80.0,
    current_bag_deadline: float = 100.0,
) -> dict[str, object]:
    baseline = {
        "comparison_eligible": True,
        "original_entry_mean_minutes": 40.0,
        "source_wait_mean_minutes": 2.0,
        "network_time_mean_minutes": 5.0,
        "original_entry_p95_seconds": 3000.0,
        "original_entry_p99_seconds": 4000.0,
        "original_entry_max_seconds": 5000.0,
        "deadline_miss_raw_bag_count": 0,
    }
    treatment = {
        **baseline,
        "original_entry_mean_minutes": 40.0 + mean_delta_seconds / 60.0,
        "source_wait_mean_minutes": 2.0,
        "network_time_mean_minutes": 5.0 + mean_delta_seconds / 60.0,
        "original_entry_p95_seconds": 3000.0 + tail_delta_seconds,
        "original_entry_p99_seconds": 4000.0 + tail_delta_seconds,
        "original_entry_max_seconds": 5000.0 + (
            tail_delta_seconds if max_delta_seconds is None else max_delta_seconds
        ),
        "deadline_miss_raw_bag_count": deadline_delta,
    }
    return {
        **target,
        "pair_status": "ACTION_CHANGED_HORIZON_COMPLETE",
        "same_state_start": True,
        "action_changed": True,
        "pair_complete": True,
        "horizon_complete": True,
        "live_safety_pass": True,
        "hard_gate_pass": True,
        "formal_hard_gate_evaluated": True,
        "formal_hard_gate_pass": True,
        "committed_action_certificate": {
            "valid": True,
            "changed_action_count": 1,
            "pre_action_snapshots_match": True,
            "post_commit_verified": True,
            "committed_action_type": "EDGE_COMMIT",
        },
        "affected_bag_deltas": [
            {
                "runtime_bag_id": target["runtime_bag_id"],
                "completion_delta_seconds": direct_delta_seconds,
            }
        ],
        "resolved_execution_descriptor": {
            "node": 16,
            "baseline_next_node": 17,
            "selected_next_node": 21,
            "runtime_bag_id": target["runtime_bag_id"],
        },
        "baseline": {"raw_bag_cohort_metrics": baseline},
        "treatment": {
            "raw_bag_cohort_metrics": treatment,
            "affected_bag_outcomes": [
                {
                    "runtime_bag_id": target["runtime_bag_id"],
                    "completed": current_bag_completed,
                    "failed": current_bag_failed,
                    "finish_time": current_bag_finish_time,
                    "deadline": current_bag_deadline,
                }
            ],
        },
    }


def _guard_abstain_pair(target: dict[str, object]) -> dict[str, object]:
    return {
        **target,
        "pair_status": "SCREENING_FALSE_POSITIVE",
        "same_state_start": True,
        "action_changed": False,
        "false_positive_reason": "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED",
        "committed_action_certificate": {
            "valid": False,
            "changed_action_count": 0,
            "pre_action_snapshots_match": True,
            "post_commit_verified": False,
            "application_reason": "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED",
        },
        "resolved_execution_descriptor": {
            "node": 16,
            "baseline_next_node": 17,
            "selected_next_node": 21,
            "runtime_bag_id": target["runtime_bag_id"],
        },
        "affected_bag_deltas": [],
    }


def test_one_hop_filter_and_round_robin_ignore_two_hop_telemetry(
    tmp_path: Path,
) -> None:
    census = tmp_path / "census.jsonl"
    rows = [
        _event(1, 99, 22),  # historical runtime bag: excluded
        _event(2, 102, 22, target_queue=15.0),
        _event(3, 103, 22, two_hop=0.0),  # eligible: two-hop is not a selector
        _event(4, 104, 22, current_node=15),
        _event(5, 105, 22, baseline_next_node=18),
        _event(6, 106, 22, alternate_next_node=20),
    ]
    ordinal = 100
    for block in runner.TARGET_BLOCKS:
        for queue in (20.0, 28.0, 32.0):
            for _ in range(3):
                rows.append(_event(ordinal, 1000 + ordinal, block, target_queue=queue))
                ordinal += 1
    _write_jsonl(census, rows)

    plan = runner.build_plan(
        census,
        [_history_file(tmp_path)],
        target_count=24,
        expected_historical_groups=1,
    )

    assert plan["status"] == "COMPLETE"
    assert plan["counts"] == {
        "group_count": 24,
        "target_count": 24,
        "h_system_target_count": 24,
        "h_bag_target_count": 0,
        "next_edge_21_target_count": 24,
        "wait_target_count": 0,
        "unique_runtime_bag_count": 24,
        "historical_group_overlap_count": 0,
        "historical_runtime_bag_overlap_count": 0,
    }
    assert {row["time_block"] for row in plan["groups"]} == set(runner.TARGET_BLOCKS)
    assert 103 in {row["runtime_bag_id"] for row in plan["groups"]}
    assert all(row["outcome_fields_used_for_selection"] is False for row in plan["groups"])
    assert all(
        row["selection_scope"] == "ONE_HOP_ALTERNATE_TARGET_QUEUE_ONLY"
        and row["two_hop_queue_pressure_used_for_selection"] is False
        for row in plan["groups"]
    )
    assert set(plan["selection"]["cells"]) <= {
        f"block_{block}|{bucket}"
        for block in runner.TARGET_BLOCKS
        for bucket in runner.ONE_HOP_PRESSURE_BINS
    }
    assert plan["protocol"]["one_hop_pressure_bins"] == [
        "q16_23",
        "q24_31",
        "q32_plus",
    ]
    assert plan["protocol"]["two_hop_queue_pressure_used"] is False
    assert "minimum_alternate_two_hop_pressure" not in plan["protocol"]
    assert all(row["horizon"] == "H_system" for row in plan["targets"])
    assert all(row["action_kind"] == "NEXT_EDGE" for row in plan["targets"])
    assert all(row["selected_next_node"] == 21 for row in plan["targets"])


def test_same_runtime_bag_is_selected_only_once_across_events_and_cells() -> None:
    candidates: list[dict[str, object]] = []
    for ordinal, block, queue in ((1, 22, 20.0), (2, 23, 28.0), (3, 24, 32.0)):
        row = _event(ordinal, 42, block, target_queue=queue)
        row.update(
            time_block=block,
            pressure_bin=runner.pressure_bin(queue),
        )
        candidates.append(row)
    for index in range(3):
        block = 22 + index
        row = _event(10 + index, 100 + index, block)
        row.update(
            time_block=block,
            pressure_bin=runner.pressure_bin(20.0),
        )
        candidates.append(row)

    selected, audit = runner.select_round_robin_groups(candidates, target_count=4)

    assert audit["selected_group_count"] == 4
    assert len({row["runtime_bag_id"] for row in selected}) == 4
    assert sum(row["runtime_bag_id"] == 42 for row in selected) == 1


def test_selection_requires_every_preregistered_block() -> None:
    candidates: list[dict[str, object]] = []
    for index in range(8):
        row = _event(index, 100 + index, 22)
        row.update(
            time_block=22,
            pressure_bin=runner.pressure_bin(20.0),
        )
        candidates.append(row)

    selected, audit = runner.select_round_robin_groups(candidates, target_count=8)

    assert len(selected) == 8
    assert audit["all_target_blocks_covered"] is False
    assert audit["status"] == "NO_GO_INSUFFICIENT_NEIGHBORHOOD"


def test_manifest_has_only_h_system_next_edge_and_exact_partition() -> None:
    _, targets = _planned_groups(256)

    manifest = runner.build_shard_manifest(targets)

    assert manifest["execution_default"] == "PLAN_ONLY_DO_NOT_START_PROCESSES"
    assert manifest["group_count"] == 256
    assert manifest["shard_count"] == 64
    assert manifest["horizon_target_counts"] == {"H_bag": 0, "H_system": 256}
    assert manifest["action_target_counts"] == {"NEXT_EDGE": 256, "WAIT": 0}
    assert manifest["selection_scope"] == "ONE_HOP_ALTERNATE_TARGET_QUEUE_ONLY"
    assert manifest["one_hop_pressure_bins"] == ["q16_23", "q24_31", "q32_plus"]
    assert manifest["two_hop_queue_pressure_used"] is False
    ids = [target_id for shard in manifest["shards"] for target_id in shard["target_ids"]]
    assert len(ids) == len(set(ids)) == 256
    assert all(shard["target_count"] == 4 for shard in manifest["shards"])


def test_manifest_shard_selection_is_an_exact_allow_list() -> None:
    _, targets = _planned_groups(9)
    manifest = runner.build_shard_manifest(targets, shard_groups=4)

    selected = runner.select_manifest_shard(targets, manifest, "system-001")

    expected_ids = manifest["shards"][1]["target_ids"]
    assert [runner.externality_target_id(row) for row in selected] == expected_ids
    with pytest.raises(runner.ExternalityNeighborhoodError):
        runner.select_manifest_shard(targets, manifest, "system-999")


def test_merge_rejects_unknown_and_conflicting_pairs() -> None:
    _, targets = _planned_groups(2)
    pair = _complete_pair(targets[0])
    unknown = {**pair, "population_group_id": "unknown"}
    with pytest.raises(runner.ExternalityNeighborhoodError):
        runner.merge_pair_payloads([{"pairs": [unknown]}], targets)

    conflict = {**pair, "live_safety_pass": False}
    with pytest.raises(runner.ExternalityNeighborhoodError):
        runner.merge_pair_payloads([{"pairs": [pair]}, {"pairs": [conflict]}], targets)

    merged = runner.merge_pair_payloads([{"pairs": [pair]}, {"pairs": [pair]}], targets)
    assert merged["duplicate_pair_count"] == 1
    assert merged["missing_target_count"] == 1


def test_execution_gate_separates_coverage_guard_abstain_and_action_change() -> None:
    _, targets = _planned_groups(2)
    pairs = [_complete_pair(target) for target in targets]

    passed = runner.exact_pair_gate({"pairs": pairs}, targets)
    assert passed["pass"] is True
    assert passed["execution_coverage_count"] == 2
    assert passed["action_applied_count"] == 2
    assert passed["guard_abstain_count"] == 0

    pairs[0]["formal_hard_gate_pass"] = False
    failed = runner.exact_pair_gate({"pairs": pairs}, targets)
    assert failed["pass"] is False
    assert "FORMAL_PASS" in failed["failures"][0]["reasons"]

    pairs = [_complete_pair(target) for target in targets]
    pairs[0]["resolved_execution_descriptor"]["selected_next_node"] = 20
    failed = runner.exact_pair_gate({"pairs": pairs}, targets)
    assert "RESOLVED_TREATMENT_EDGE" in failed["failures"][0]["reasons"]

    guarded = [_guard_abstain_pair(targets[0]), _complete_pair(targets[1])]
    accepted = runner.exact_pair_gate(
        {"pairs": guarded}, targets, required_action_change_rate=0.50
    )
    assert accepted["execution_coverage_pass"] is True
    assert accepted["recognized_execution_outcomes_pass"] is True
    assert accepted["action_applied_count"] == 1
    assert accepted["guard_abstain_count"] == 1
    assert accepted["action_changing_rate"] == 0.5
    assert accepted["guard_abstain_reasons"] == {
        "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED": 1
    }
    assert accepted["pass"] is True

    rate_failed = runner.exact_pair_gate(
        {"pairs": guarded}, targets, required_action_change_rate=0.80
    )
    assert rate_failed["action_changing_rate_pass"] is False
    assert rate_failed["pass"] is False


def test_compactor_requires_fair_system_support_for_continuation() -> None:
    groups, targets = _planned_groups(32)
    pairs = [_complete_pair(target, direct_delta_seconds=5.0) for target in targets]
    merged = runner.merge_pair_payloads([{"pairs": pairs}], targets)

    compact = runner.compact_externality_neighborhood(
        merged,
        groups,
        targets,
        required_group_count=32,
        required_system_beneficial=20,
        required_fair_beneficial_cells=3,
        signature_min_support=8,
    )

    summary = compact["summary"]
    assert summary["status"] == "PASS_EXTERNALITY_NEIGHBORHOOD_SUPPORT"
    assert summary["system_beneficial_count"] == 32
    assert summary["fair_system_beneficial_count"] == 32
    assert summary["system_beneficial_but_costly_count"] == 32
    assert summary["system_beneficial_but_unfair_count"] == 0
    assert summary["individual_direct_beneficial_count"] == 0
    assert summary["individual_fairness_evaluated"] is True
    assert summary["post_hoc_individual_cost_cap_applied"] is False
    assert all(row["system_beneficial"] is True for row in compact["actions"])
    assert all(row["individual_fair"] is True for row in compact["actions"])
    assert all(row["fair_system_beneficial"] is True for row in compact["actions"])
    assert all(row["individual_direct_cost_seconds"] == 5.0 for row in compact["actions"])


def test_compactor_counts_guard_abstain_but_excludes_it_from_effects() -> None:
    groups, targets = _planned_groups(5)
    pairs = [_complete_pair(target) for target in targets]
    pairs[0] = _guard_abstain_pair(targets[0])

    compact = runner.compact_externality_neighborhood(
        runner.merge_pair_payloads([{"pairs": pairs}], targets),
        groups,
        targets,
        required_group_count=5,
        required_system_beneficial=1,
        required_fair_beneficial_cells=1,
        signature_min_support=1,
        required_action_change_rate=0.80,
    )

    summary = compact["summary"]
    assert summary["attempted_group_count"] == 5
    assert summary["execution_coverage_count"] == 5
    assert summary["action_applied_count"] == 4
    assert summary["guard_abstain_count"] == 1
    assert summary["action_changing_rate"] == 0.8
    assert summary["effect_complete_count"] == 4
    assert summary["raw_bag_max_delta_seconds_diagnostic"]["count"] == 4
    assert summary["gates"]["execution_coverage"] is True
    assert summary["gates"]["recognized_execution_outcomes"] is True
    assert summary["gates"]["action_changing_rate"] is True
    abstain = compact["actions"][0]
    assert abstain["execution_observed"] is True
    assert abstain["action_applied"] is False
    assert abstain["guard_abstain"] is True
    assert abstain["effect_evidence_complete"] is False
    assert abstain["system_beneficial"] is False
    assert abstain["individual_fair_evidence_complete"] is False


def test_system_beneficial_but_unfair_does_not_satisfy_continuation() -> None:
    groups, targets = _planned_groups(32)
    pairs = [
        _complete_pair(target, current_bag_finish_time=101.0)
        for target in targets
    ]

    compact = runner.compact_externality_neighborhood(
        runner.merge_pair_payloads([{"pairs": pairs}], targets),
        groups,
        targets,
        required_group_count=32,
        required_system_beneficial=20,
        required_fair_beneficial_cells=3,
        signature_min_support=8,
    )

    summary = compact["summary"]
    assert summary["system_beneficial_count"] == 32
    assert summary["fair_system_beneficial_count"] == 0
    assert summary["system_beneficial_but_unfair_count"] == 32
    assert summary["continuation_pass"] is False
    assert all(
        row["benefit_fairness_label"]
        == "SYSTEM_BENEFICIAL_BUT_INDIVIDUAL_OUTCOME_UNSAFE"
        for row in compact["actions"]
    )


def test_unfair_system_benefit_in_other_cells_cannot_fake_fair_cell_coverage() -> None:
    groups, targets = _planned_groups(32)
    pairs = [
        _complete_pair(
            target,
            current_bag_finish_time=(80.0 if group["time_block"] == 22 else 101.0),
        )
        for group, target in zip(groups, targets, strict=True)
    ]

    compact = runner.compact_externality_neighborhood(
        runner.merge_pair_payloads([{"pairs": pairs}], targets),
        groups,
        targets,
        required_group_count=32,
        required_system_beneficial=1,
        required_fair_beneficial_cells=3,
        signature_min_support=8,
    )

    summary = compact["summary"]
    assert summary["system_beneficial_cell_count"] == 8
    assert summary["fair_system_beneficial_cell_count"] == 1
    assert summary["gates"]["heldout_local_signature"] is True
    assert summary["gates"]["fair_system_beneficial_count"] is True
    assert (
        summary["gates"]["fair_system_beneficial_block_pressure_cell_count"]
        is False
    )
    assert summary["continuation_pass"] is False


def test_fair_system_benefit_across_three_cells_satisfies_fair_cell_coverage() -> None:
    groups, targets = _planned_groups(32)
    pairs = [
        _complete_pair(
            target,
            current_bag_finish_time=(
                80.0 if group["time_block"] in {22, 23, 24} else 101.0
            ),
        )
        for group, target in zip(groups, targets, strict=True)
    ]

    compact = runner.compact_externality_neighborhood(
        runner.merge_pair_payloads([{"pairs": pairs}], targets),
        groups,
        targets,
        required_group_count=32,
        required_system_beneficial=1,
        required_fair_beneficial_cells=3,
        signature_min_support=8,
    )

    summary = compact["summary"]
    assert summary["fair_system_beneficial_cell_count"] == 3
    assert (
        summary["gates"]["fair_system_beneficial_block_pressure_cell_count"]
        is True
    )
    assert summary["continuation_pass"] is True


def test_fairness_evidence_missing_fails_closed_without_hiding_system_benefit() -> None:
    groups, targets = _planned_groups(1)
    del groups[0]["candidate_observations"][0]["static_potential"]
    pair = _complete_pair(targets[0])
    del pair["treatment"]["affected_bag_outcomes"]

    compact = runner.compact_externality_neighborhood(
        runner.merge_pair_payloads([{"pairs": [pair]}], targets),
        groups,
        targets,
        required_group_count=1,
        required_system_beneficial=1,
        required_fair_beneficial_cells=1,
        signature_min_support=1,
    )

    row = compact["actions"][0]
    assert row["system_beneficial"] is True
    assert row["individual_fair_evidence_complete"] is False
    assert row["individual_fair"] is False
    assert row["fair_system_beneficial"] is False
    assert row["system_beneficial_but_unfair"] is True
    assert compact["summary"]["continuation_pass"] is False


def test_system_beneficial_gate_rejects_tail_or_deadline_regression() -> None:
    groups, targets = _planned_groups(2)
    pairs = [
        _complete_pair(targets[0], tail_delta_seconds=0.002),
        _complete_pair(targets[1], deadline_delta=1),
    ]
    merged = runner.merge_pair_payloads([{"pairs": pairs}], targets)

    compact = runner.compact_externality_neighborhood(
        merged,
        groups,
        targets,
        required_group_count=2,
        required_system_beneficial=1,
        required_fair_beneficial_cells=1,
        signature_min_support=1,
    )

    assert compact["summary"]["system_safe_count"] == 0
    assert compact["summary"]["system_beneficial_count"] == 0
    assert compact["summary"]["continuation_pass"] is False


def test_raw_bag_max_regression_is_diagnostic_not_a_system_gate() -> None:
    groups, targets = _planned_groups(8)
    pairs = [
        _complete_pair(
            target,
            tail_delta_seconds=0.0,
            max_delta_seconds=5.0,
        )
        for target in targets
    ]

    compact = runner.compact_externality_neighborhood(
        runner.merge_pair_payloads([{"pairs": pairs}], targets),
        groups,
        targets,
        required_group_count=8,
        required_system_beneficial=1,
        required_fair_beneficial_cells=1,
        signature_min_support=2,
    )

    summary = compact["summary"]
    assert summary["system_safe_count"] == 8
    assert summary["system_beneficial_count"] == 8
    assert summary["continuation_pass"] is True
    assert summary["thresholds"]["system_p95_p99_delta_seconds_max"] == 0.001
    assert "system_p95_p99_max_delta_seconds_max" not in summary["thresholds"]
    assert summary["system_tail_hard_gate_metrics"] == [
        "raw_bag_p95_delta_seconds",
        "raw_bag_p99_delta_seconds",
    ]
    assert summary["raw_bag_max_delta_is_diagnostic_only"] is True
    assert summary["raw_bag_max_delta_seconds_diagnostic"] == {
        "role": "DIAGNOSTIC_ONLY_NOT_A_SYSTEM_HARD_GATE",
        "count": 8,
        "min": 5.0,
        "mean": 5.0,
        "median": 5.0,
        "max": 5.0,
    }
    assert all(row["raw_bag_max_delta_seconds"] == 5.0 for row in compact["actions"])


def test_heldout_signature_uses_pressure_only_and_requires_support_and_direction() -> None:
    rows: list[dict[str, object]] = []
    for block in runner.DISCOVERY_BLOCKS:
        for _ in range(2):
            rows.append(
                {
                    "time_block": block,
                    "pressure_bin": "candidate",
                    "effect_evidence_complete": True,
                    "system_beneficial": True,
                    "fair_system_beneficial": True,
                    "raw_bag_mean_delta_seconds": -0.02,
                }
            )
    for block in runner.HELDOUT_BLOCKS:
        for _ in range(2):
            rows.append(
                {
                    "time_block": block,
                    "pressure_bin": "candidate",
                    "effect_evidence_complete": True,
                    "system_beneficial": block == 26,
                    "fair_system_beneficial": block == 26,
                    "raw_bag_mean_delta_seconds": -0.01,
                }
            )

    signature = runner.heldout_local_signature(rows, min_support=8)

    assert signature["feature"] == "one_hop_target_queue_bin"
    assert signature["selected_pressure_bin"] == "candidate"
    assert signature["pass"] is True
    assert signature["individual_fairness_claimed"] is False
    assert signature["system_benefit_scope"] == "SYSTEM_BENEFICIAL_ONLY"
    assert signature["individual_fairness_used"] is False

    for row in rows:
        if row["time_block"] in runner.HELDOUT_BLOCKS:
            row["raw_bag_mean_delta_seconds"] = 0.01
    assert runner.heldout_local_signature(rows, min_support=8)["pass"] is False


def test_signature_selection_is_by_discovery_beneficial_rate_before_mean() -> None:
    rows: list[dict[str, object]] = []
    for bucket, beneficial_count, mean in (("higher_rate", 6, 0.01), ("lower_rate", 5, -0.20)):
        for index in range(8):
            rows.append(
                {
                    "time_block": runner.DISCOVERY_BLOCKS[index % 4],
                    "pressure_bin": bucket,
                    "effect_evidence_complete": True,
                    "system_beneficial": index < beneficial_count,
                    "fair_system_beneficial": index < beneficial_count,
                    "raw_bag_mean_delta_seconds": mean,
                }
            )
        for index in range(8):
            rows.append(
                {
                    "time_block": runner.HELDOUT_BLOCKS[index % 4],
                    "pressure_bin": bucket,
                    "effect_evidence_complete": True,
                    "system_beneficial": True,
                    "fair_system_beneficial": True,
                    "raw_bag_mean_delta_seconds": -0.01,
                }
            )

    signature = runner.heldout_local_signature(rows, min_support=8)

    assert signature["selected_pressure_bin"] == "higher_rate"
    assert signature["pass"] is True


def test_csv_and_report_keep_system_and_individual_columns_separate(tmp_path: Path) -> None:
    groups, targets = _planned_groups(8)
    pairs = [_complete_pair(target) for target in targets]
    compact = runner.compact_externality_neighborhood(
        runner.merge_pair_payloads([{"pairs": pairs}], targets),
        groups,
        targets,
        required_group_count=8,
        required_system_beneficial=1,
        required_fair_beneficial_cells=1,
        signature_min_support=2,
    )
    csv_path = tmp_path / "actions.csv"

    runner.write_action_csv(csv_path, compact["actions"])
    report = runner.render_report(compact["summary"])

    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert "system_beneficial" in header
    assert "fair_system_beneficial" in header
    assert "individual_fair" in header
    assert "deadline_headroom_seconds" in header
    assert "individual_direct_cost_seconds" in header
    assert "raw_bag_max_delta_seconds" in header
    assert "execution_observed" in header
    assert "action_applied" in header
    assert "guard_abstain_reason" in header
    assert "effect_evidence_complete" in header
    assert "Individual fairness" in report
    assert "Attempted H_system groups" in report
    assert "Action-changing rate >= 0.80" in report
    assert "At least 20 fair system-beneficial actions" in report
    assert "At least 3 fair system-beneficial block x one-hop queue cells" in report
    assert "system benefit only" in report
    assert "No WAIT, H_bag, planner, or learned model" in report
    assert "Raw-bag max delta, diagnostic only" in report
    assert "system tail hard gate uses p95/p99 only" in report

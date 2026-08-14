from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf23_source_pilot as pilot


def _opportunity(
    index: int,
    *,
    block: int,
    bag: int | None = None,
    queue: float = 20.0,
    downstream: float = 4.0,
    service_gap: float = 2.0,
) -> dict[str, object]:
    runtime_bag_id = index if bag is None else bag
    return {
        "schema": pilot.CENSUS_SCHEMA,
        "kind": "SOURCE_ADMISSION",
        "descriptor_id": f"source-group-{index}",
        "event_ordinal": index,
        "event_seq": 10_000 + index,
        "event_time": float(block * 3600 + index % 300),
        "runtime_bag_id": runtime_bag_id,
        "source_ready_order": [runtime_bag_id, 900_000 + index],
        "node": 52,
        "segment_id": f"{runtime_bag_id}:storage_out",
        "release_block": block,
        "baseline_action": f"SOURCE_ADMIT_RUNTIME_BAG_ID={runtime_bag_id}",
        "baseline_release": True,
        "baseline_admit_legal": True,
        "fault_active": False,
        "stale_generation": False,
        "task_id": runtime_bag_id,
        "source_context": {
            "source_queue_length": queue,
            "source_queue_capacity": 32.0,
            "source_queue_utilization": min(1.0, queue / 32.0),
            "release_count_30s": queue + 3.0,
            "admission_count_30s": queue,
            "queue_slope_30s": (index % 3) - 1.0,
            "target_queue_length": downstream,
            "target_scheduled_incoming": float(index % 6),
            "time_to_next_service_opportunity_seconds": service_gap,
            "estimated_service_rate_60s": 0.25,
            "candidate_deadline_slack_seconds": 60.0,
            "candidate_wait_age_seconds": 3.0,
            "two_hop_ttl_pressure": 999_999.0,
        },
        # Selection must be unchanged if these post-action values change.
        "raw_bag_mean_tth_delta_seconds": -1_000_000.0 + index,
        "effect_label": "FAIR_SYSTEM_BENEFICIAL",
    }


def test_normalization_keeps_only_same_front_local_source_contract() -> None:
    row = _opportunity(1, block=7)
    normalized = pilot.normalize_source_opportunity(row)

    assert normalized["leg"] == "storage_out"
    assert normalized["node"] == 52
    assert normalized["runtime_bag_id"] == normalized["front_runtime_bag_id"]
    assert normalized["baseline_action"] == "ADMIT_NOW"
    assert normalized["treatment_action"] == "HOLD_ONE_NATURAL_OPPORTUNITY"
    assert "peer_runtime_bag_id" not in normalized
    assert "raw_bag_mean_tth_delta_seconds" not in normalized
    assert "two_hop_ttl_pressure" not in normalized["outcome_free_context"]


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"node": 51}, "node 52"),
        ({"segment_id": "1:storage_in"}, "storage_out"),
        ({"release_block": 6}, "block"),
        ({"fault_active": True}, "fault-active"),
        ({"stale_generation": True}, "stale"),
        ({"baseline_admit_legal": False}, "ADMIT"),
        ({"baseline_release": False}, "baseline_release"),
        ({"schema": "czr005.g4irsf15.causal_skeleton.v1"}, "native G23"),
        ({"source_ready_order": [99, 1]}, "current source front"),
    ],
)
def test_normalization_rejects_ineligible_source_states(
    update: dict[str, object], message: str
) -> None:
    row = _opportunity(1, block=7)
    row.update(update)
    with pytest.raises(pilot.SourcePilotError, match=message):
        pilot.normalize_source_opportunity(row)


def test_census_normalization_allows_non_target_release_block() -> None:
    row = _opportunity(1, block=6)

    census_row = pilot.normalize_source_opportunity(row, require_target_block=False)
    assert census_row["release_block"] == 6
    with pytest.raises(pilot.SourcePilotError, match="release block"):
        pilot.normalize_source_opportunity(census_row)


def test_selection_ignores_legal_rows_outside_target_blocks() -> None:
    rows = [_opportunity(0, block=6), _opportunity(1, block=7)]

    selected, audit = pilot.select_source_pilot_groups(
        rows,
        block_group_targets={7: 1},
        block_h_system_targets={7: 0},
        require_complete=True,
    )

    assert [row["release_block"] for row in selected] == [7]
    assert audit["out_of_scope_release_block_count"] == 1
    assert audit["rejected_row_count"] == 0


def test_full_pilot_selects_exact_block_and_horizon_quotas() -> None:
    rows = [
        _opportunity(
            index,
            block=7,
            queue=float(5 + index % 60),
            downstream=float(index % 24),
            service_gap=float(index % 9),
        )
        for index in range(220)
    ]
    rows.extend(
        _opportunity(
            1_000 + index,
            block=8,
            queue=float(5 + index % 60),
            downstream=float(index % 24),
            service_gap=float(index % 9),
        )
        for index in range(80)
    )
    # A duplicate high-scoring event must not duplicate a runtime bag.
    duplicate = _opportunity(9_999, block=8, bag=3, queue=10_000.0)
    rows.append(duplicate)

    plan = pilot.build_source_pilot_plan(rows, require_complete=True)

    assert plan["counts"] == {
        "group_count": 256,
        "h_bag_group_count": 256,
        "h_system_group_count": 176,
        "target_count": 432,
    }
    groups = plan["groups"]
    assert sum(row["release_block"] == 7 for row in groups) == 192
    assert sum(row["release_block"] == 8 for row in groups) == 64
    assert len({row["runtime_bag_id"] for row in groups}) == 256
    assert sum(
        row["release_block"] == 7 and "H_system" in row["assigned_horizons"]
        for row in groups
    ) == 128
    assert sum(
        row["release_block"] == 8 and "H_system" in row["assigned_horizons"]
        for row in groups
    ) == 48
    assert plan["selection"]["status"] == "COMPLETE"


def test_selection_is_outcome_free() -> None:
    rows = [_opportunity(index, block=7) for index in range(20)]
    left, _ = pilot.select_source_pilot_groups(
        rows,
        block_group_targets={7: 8},
        block_h_system_targets={7: 4},
    )
    changed = copy.deepcopy(rows)
    for index, row in enumerate(changed):
        row["raw_bag_mean_tth_delta_seconds"] = float(index * 1_000_000)
        row["effect_label"] = "HARMFUL" if index % 2 else "BENEFICIAL"
    right, _ = pilot.select_source_pilot_groups(
        changed,
        block_group_targets={7: 8},
        block_h_system_targets={7: 4},
    )
    assert [row["event_ordinal"] for row in left] == [
        row["event_ordinal"] for row in right
    ]


def test_target_contract_is_admit_vs_same_front_one_opportunity_hold() -> None:
    group = pilot.normalize_source_opportunity(_opportunity(5, block=7))
    group["assigned_horizons"] = ["H_bag", "H_system"]
    targets = pilot.build_source_targets([group])

    assert {row["horizon"] for row in targets} == {"H_bag", "H_system"}
    for target in targets:
        assert target["schema"] == pilot.TARGET_SCHEMA
        assert target["kind"] == "SOURCE_ADMISSION"
        assert target["intervention_kind"] == "SOURCE_HOLD_ONE_NATURAL_OPPORTUNITY"
        assert target["baseline_action"] == "ADMIT_NOW"
        assert target["treatment_action"] == "HOLD_ONE_NATURAL_OPPORTUNITY"
        assert target["runtime_bag_id"] == target["front_runtime_bag_id"]
        assert target["max_hold_opportunities"] == 1
        assert target["force_a0_after_hold"] is True
        assert target["outcome_free_context"] == group["outcome_free_context"]
        assert target["task_group_id"] == group["task_id"]
        assert target["contiguous_block_id"] == int(group["event_time"] // 900)
        assert target["pressure_episode_id"] == pilot.outcome_free_stratum(group)
        assert "peer_runtime_bag_id" not in target


def test_native_wrapper_only_forwards_new_contract_to_exact_api() -> None:
    class Backend:
        def __init__(self) -> None:
            self.call: tuple[object, ...] | None = None

        def g4irsf15_run_causal_target_pairs_from_records(self, *args: object) -> dict[str, object]:
            self.call = args
            return {"pairs": []}

    target = {"schema": pilot.TARGET_SCHEMA, "kind": "SOURCE_ADMISSION"}
    backend = Backend()
    result = pilot.run_native_exact_pairs(backend, ["native-input"], [target])

    assert result == {"pairs": []}
    assert backend.call == ("native-input", [target], pilot.RESEARCH_PROFILE)


def test_pair_target_slice_filters_before_offset_and_limit() -> None:
    targets = [
        {"target_id": "a:H_bag", "horizon": "H_bag"},
        {"target_id": "a:H_system", "horizon": "H_system"},
        {"target_id": "b:H_bag", "horizon": "H_bag"},
        {"target_id": "c:H_bag", "horizon": "H_bag"},
        {"target_id": "b:H_system", "horizon": "H_system"},
    ]

    assert pilot.select_pair_targets(targets, horizon="H_bag", offset=1, limit=2) == [
        targets[2],
        targets[3],
    ]
    assert pilot.select_pair_targets(targets, horizon="H_system", offset=1) == [
        targets[4]
    ]
    assert pilot.select_pair_targets(targets) == targets


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"horizon": "bad"}, "pair horizon"),
        ({"offset": -1}, "pair offset"),
        ({"limit": 0}, "pair limit"),
    ],
)
def test_pair_target_slice_rejects_invalid_bounds(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(pilot.SourcePilotError, match=message):
        pilot.select_pair_targets([], **kwargs)  # type: ignore[arg-type]


def test_manifest_shard_selection_preserves_ids_and_order() -> None:
    targets = [
        {"target_id": "a:H_bag", "horizon": "H_bag"},
        {"target_id": "b:H_system", "horizon": "H_system"},
        {"target_id": "c:H_system", "horizon": "H_system"},
    ]
    manifest = {
        "schema": pilot.PAIR_SHARD_MANIFEST_SCHEMA,
        "shards": [
            {
                "shard_id": "h_system-000",
                "horizon": "H_system",
                "target_count": 2,
                "target_ids": ["c:H_system", "b:H_system"],
            }
        ],
    }

    selected = pilot.select_pair_manifest_shard(
        targets, manifest, "h_system-000"
    )

    assert [target["target_id"] for target in selected] == [
        "c:H_system",
        "b:H_system",
    ]


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (
            {"schema": "wrong", "shards": []},
            "wrong schema",
        ),
        (
            {"schema": pilot.PAIR_SHARD_MANIFEST_SCHEMA, "shards": []},
            "match exactly once",
        ),
        (
            {
                "schema": pilot.PAIR_SHARD_MANIFEST_SCHEMA,
                "shards": [
                    {"shard_id": "s", "target_ids": []},
                ],
            },
            "no valid target_ids",
        ),
        (
            {
                "schema": pilot.PAIR_SHARD_MANIFEST_SCHEMA,
                "shards": [
                    {"shard_id": "s", "target_ids": ["a", "a"]},
                ],
            },
            "duplicate target_ids",
        ),
        (
            {
                "schema": pilot.PAIR_SHARD_MANIFEST_SCHEMA,
                "shards": [
                    {"shard_id": "s", "target_ids": ["missing"]},
                ],
            },
            "unknown target_ids",
        ),
    ],
)
def test_manifest_shard_selection_fails_closed(
    manifest: dict[str, object], message: str
) -> None:
    with pytest.raises(pilot.SourcePilotError, match=message):
        pilot.select_pair_manifest_shard(
            [{"target_id": "a", "horizon": "H_bag"}], manifest, "s"
        )


def test_pair_slice_cli_defaults_are_backward_compatible() -> None:
    arguments = pilot.parse_args(
        [
            "--groups-output",
            "groups.jsonl",
            "--targets-output",
            "targets.jsonl",
            "--summary-output",
            "summary.json",
        ]
    )

    assert arguments.pair_horizon == "all"
    assert arguments.pair_offset == 0
    assert arguments.pair_limit is None
    assert arguments.pair_results is None
    assert arguments.pair_shard_manifest is None
    assert arguments.pair_shard_id is None


def test_main_persists_census_before_planner_failure(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path  # pytest supplies pathlib.Path; keep fixture annotation portable.
    binary = output_dir / "czr005_cpp.test.pyd"  # type: ignore[operator]
    binary.write_bytes(b"fixture")
    census_output = output_dir / "census.jsonl"  # type: ignore[operator]
    monkeypatch.setattr(pilot, "load_native_backend", lambda path: object())
    monkeypatch.setattr(
        pilot,
        "build_2x_native_arguments",
        lambda root: (["native"], [], {"scale": "2x"}),
    )
    monkeypatch.setattr(
        pilot,
        "scan_native_source_opportunities",
        lambda backend, arguments: [
            pilot.normalize_source_opportunity(
                _opportunity(1, block=6), require_target_block=False
            )
        ],
    )

    exit_code = pilot.main(
        [
            "--binary",
            str(binary),
            "--census-output",
            str(census_output),
            "--groups-output",
            str(output_dir / "groups.jsonl"),  # type: ignore[operator]
            "--targets-output",
            str(output_dir / "targets.jsonl"),  # type: ignore[operator]
            "--summary-output",
            str(output_dir / "summary.json"),  # type: ignore[operator]
        ]
    )

    assert exit_code == 2
    rows = pilot._read_jsonl(census_output)
    assert len(rows) == 1
    assert rows[0]["release_block"] == 6
    assert not (output_dir / ".census.jsonl.tmp").exists()  # type: ignore[operator]


def test_native_census_wrapper_requires_dedicated_complete_payload() -> None:
    class Backend:
        def __init__(self) -> None:
            self.call: tuple[object, ...] | None = None

        def g4irsf23_scan_source_admission_opportunities_from_records(
            self, *args: object
        ) -> dict[str, object]:
            self.call = args
            return {"census_complete": True, "opportunities": [_opportunity(7, block=7)]}

    backend = Backend()
    rows = pilot.scan_native_source_opportunities(backend, ["2x-native-input"])

    assert len(rows) == 1
    assert rows[0]["baseline_action"] == "ADMIT_NOW"
    assert backend.call == ("2x-native-input", pilot.RESEARCH_PROFILE)


def test_native_census_wrapper_preserves_legal_non_target_blocks() -> None:
    class Backend:
        def g4irsf23_scan_source_admission_opportunities_from_records(
            self, *args: object
        ) -> dict[str, object]:
            return {
                "census_complete": True,
                "opportunities": [
                    _opportunity(6, block=6),
                    _opportunity(7, block=7),
                ],
            }

    rows = pilot.scan_native_source_opportunities(Backend(), ["2x-native-input"])

    assert [row["release_block"] for row in rows] == [6, 7]


def test_build_2x_native_arguments_is_a_thin_g22_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.eval import run_g4irsf22_action_timing as g22

    expected = (["native"], [{"task_id": 1}], {"scale": "2x"})
    monkeypatch.setattr(g22, "build_2x_native_arguments", lambda root: expected)

    assert pilot.build_2x_native_arguments(pilot.ROOT) == expected


def _pair(
    *,
    mean: float,
    p95: float = 0.0,
    p99: float = 0.0,
    cost: float = 1.0,
    opportunity: float = 1.0,
    deadline: int = 0,
    certificate: dict[str, object] | None = None,
) -> dict[str, object]:
    valid_certificate: dict[str, object] = {
        "action_changed": True,
        "changed_action_count": 1,
        "front_bag_unchanged": True,
    }
    if certificate:
        valid_certificate.update(certificate)
    return {
        "target_id": "group:H_system",
        "source_group_id": "group",
        "horizon": "H_system",
        "runtime_bag_id": 7,
        "release_block": 8,
        "selection_stratum": "pressure-a",
        "system_mean_delta_seconds": mean,
        "system_p95_delta_seconds": p95,
        "system_p99_delta_seconds": p99,
        "current_bag_cost_seconds": cost,
        "natural_opportunity_seconds": opportunity,
        "deadline_miss_delta": deadline,
        "action_change_certificate": valid_certificate,
        "hold_opportunity_count_observed": 1,
        "forced_a0_after_hold_observed": True,
        "repeated_hold_count_observed": 0,
        "horizon_complete": True,
        "hard_gate_pass": True,
    }


def _component_pair(
    block: int,
    *,
    source_wait_delta_seconds: float,
    network_delta_seconds: float,
    scheduled_delta_seconds: float,
) -> dict[str, object]:
    baseline = {
        "comparison_eligible": True,
        "source_wait_mean_minutes": 2.0,
        "network_time_mean_minutes": 6.0,
        "scheduled_pre_release_wait_mean_minutes": 30.0,
    }
    treatment = {
        **baseline,
        "source_wait_mean_minutes": 2.0 + source_wait_delta_seconds / 60.0,
        "network_time_mean_minutes": 6.0 + network_delta_seconds / 60.0,
        "scheduled_pre_release_wait_mean_minutes": (
            30.0 + scheduled_delta_seconds / 60.0
        ),
    }
    return {
        "horizon": "H_system",
        "release_block": block,
        "pair_complete": True,
        "horizon_complete": True,
        "baseline": {"raw_bag_cohort_metrics": baseline},
        "treatment": {"raw_bag_cohort_metrics": treatment},
    }


def test_h_system_component_deltas_are_recomputed_per_raw_bag_and_block() -> None:
    payload = {
        "pairs": [
            _component_pair(
                7,
                source_wait_delta_seconds=-1.0,
                network_delta_seconds=2.0,
                scheduled_delta_seconds=0.0,
            ),
            _component_pair(
                8,
                source_wait_delta_seconds=3.0,
                network_delta_seconds=4.0,
                scheduled_delta_seconds=-2.0,
            ),
        ]
    }

    summary = pilot.summarize_h_system_component_mean_deltas(payload)

    assert summary["unit"] == "seconds_per_complete_raw_bag"
    assert summary["h_system_pair_count"] == 2
    assert summary["release_block_pair_counts"] == {"7": 1, "8": 1}
    source = summary["all"]["metrics"][
        "raw_bag_source_wait_mean_delta_seconds"
    ]
    assert source["min"] == pytest.approx(-1.0)
    assert source["mean"] == pytest.approx(1.0)
    assert source["median"] == pytest.approx(1.0)
    assert source["max"] == pytest.approx(3.0)
    assert summary["by_release_block"]["7"]["metrics"][
        "raw_bag_network_time_mean_delta_seconds"
    ]["mean"] == pytest.approx(2.0)
    assert summary["by_release_block"]["8"]["metrics"][
        "raw_bag_scheduled_pre_release_wait_mean_delta_seconds"
    ]["mean"] == pytest.approx(-2.0)


def test_fair_label_separates_system_gain_individual_fairness_and_tail() -> None:
    fair = pilot.compact_fair_label(_pair(mean=-0.02))
    unfair = pilot.compact_fair_label(_pair(mean=-0.02, cost=2.0))
    harmful = pilot.compact_fair_label(_pair(mean=-0.02, p99=0.01))
    neutral = pilot.compact_fair_label(_pair(mean=-0.0005))

    assert fair["label"] == "FAIR_SYSTEM_BENEFICIAL"
    assert fair["effect_tier"] == "usable"
    assert fair["gates"]["promotion_strength"] is True
    assert unfair["label"] == "SYSTEM_BENEFICIAL_BUT_UNFAIR"
    assert unfair["gates"]["individual_cost"] is False
    assert unfair["gates"]["promotion_strength"] is False
    assert harmful["label"] == "HARMFUL"
    assert harmful["gates"]["tail"] is False
    assert neutral["label"] == "NEUTRAL"


def test_compact_labels_strictly_join_authoritative_target_context() -> None:
    group = pilot.normalize_source_opportunity(_opportunity(7, block=8))
    group["assigned_horizons"] = ["H_system"]
    target = pilot.build_source_targets([group])[0]
    pair = {
        **_pair(mean=-0.02),
        **{
            field: target[field]
            for field in (
                "target_id",
                "source_group_id",
                "horizon",
                "event_ordinal",
                "runtime_bag_id",
                "release_block",
                "selection_stratum",
            )
        },
        "action_changed": True,
        "pair_complete": True,
    }

    labels = pilot.compact_fair_labels({"pairs": [pair]}, [target])

    assert len(labels) == 1
    label = labels[0]
    assert label["outcome_free_context"] == target["outcome_free_context"]
    assert label["task_id"] == target["task_id"]
    assert label["segment_id"] == target["segment_id"]
    assert label["event_time"] == target["event_time"]
    assert label["task_group_id"] == target["task_group_id"]
    assert label["contiguous_block_id"] == target["contiguous_block_id"]
    assert label["pressure_episode_id"] == target["pressure_episode_id"]


def test_compact_labels_fail_closed_without_or_against_target_join() -> None:
    group = pilot.normalize_source_opportunity(_opportunity(8, block=8))
    group["assigned_horizons"] = ["H_system"]
    target = pilot.build_source_targets([group])[0]
    pair = {
        **_pair(mean=-0.02),
        **{
            field: target[field]
            for field in (
                "target_id",
                "source_group_id",
                "horizon",
                "event_ordinal",
                "runtime_bag_id",
                "release_block",
                "selection_stratum",
            )
        },
        "action_changed": True,
        "pair_complete": True,
    }

    with pytest.raises(pilot.SourcePilotError, match="no matching target"):
        pilot.compact_fair_labels({"pairs": [pair]})

    conflict = dict(pair, runtime_bag_id=int(target["runtime_bag_id"]) + 1)
    with pytest.raises(pilot.SourcePilotError, match="runtime_bag_id"):
        pilot.compact_fair_labels({"pairs": [conflict]}, [target])

    missing_context = dict(target)
    del missing_context["outcome_free_context"]
    with pytest.raises(pilot.SourcePilotError, match="outcome_free_context"):
        pilot.compact_fair_labels({"pairs": [pair]}, [missing_context])


def test_pilot_gate_summary_requires_block8_and_diverse_fair_support() -> None:
    labels: list[dict[str, object]] = []
    for index in range(16):
        labels.append(
            {
                "label": "FAIR_SYSTEM_BENEFICIAL",
                "effect_tier": "usable",
                "release_block": 8 if index < 4 else 7,
                "selection_stratum": f"s{index % 3}",
                "gates": {"promotion_strength": True},
            }
        )
    summary = pilot.summarize_pilot_labels(
        labels,
        attempted_group_count=20,
        action_changed_group_count=16,
        execution_coverage={
            "coverage_complete": True,
            "observed_h_system_by_block": {7: 12, 8: 4},
        },
        required_h_system_by_block={7: 12, 8: 4},
    )
    assert summary["pilot_support_pass"] is True
    assert all(summary["gates"].values())


def test_action_changing_rate_uses_complete_h_bag_groups_not_h_system_labels() -> None:
    pairs: list[dict[str, object]] = []
    for index in range(5):
        pairs.append(
            {
                "source_group_id": f"g{index}",
                "horizon": "H_bag",
                "action_changed": index < 4,
                "pair_complete": index < 4,
                "action_change_certificate": {
                    "valid": index < 4,
                    "changed_action_count": 1,
                },
            }
        )
    # H_system coverage is deliberately smaller and must not cap the rate.
    pairs.append({"source_group_id": "g0", "horizon": "H_system"})
    payload = {"pairs": pairs}

    assert pilot.action_changed_source_group_count(payload) == 4
    assert pilot.compact_fair_labels(payload) == []
    summary = pilot.summarize_pilot_labels(
        [],
        attempted_group_count=5,
        action_changed_group_count=pilot.action_changed_source_group_count(payload),
    )
    assert summary["action_changed_rate"] == pytest.approx(0.8)
    assert summary["gates"]["action_changing_rate"] is True
    assert summary["pilot_support_pass"] is False
    assert summary["gates"]["execution_coverage_complete"] is False


def test_partial_execution_can_never_report_pilot_support() -> None:
    labels = [
        {
            "label": "FAIR_SYSTEM_BENEFICIAL",
            "effect_tier": "strong",
            "release_block": 8 if index < 4 else 7,
            "selection_stratum": f"s{index % 3}",
            "gates": {"promotion_strength": True},
        }
        for index in range(16)
    ]

    summary = pilot.summarize_pilot_labels(
        labels,
        attempted_group_count=256,
        action_changed_group_count=205,
        execution_coverage={
            "coverage_complete": False,
            "observed_h_system_by_block": {7: 128, 8: 47},
        },
    )

    assert summary["action_changed_rate"] >= 0.8
    assert summary["gates"]["action_changing_rate"] is True
    assert summary["gates"]["execution_coverage_complete"] is False
    assert summary["gates"]["h_system_coverage"] is False
    assert summary["pilot_support_pass"] is False


def test_weak_diagnostic_fair_rows_do_not_count_as_promotion_support() -> None:
    weak = [
        {
            "label": "FAIR_SYSTEM_BENEFICIAL",
            "effect_tier": "weak_diagnostic",
            "release_block": 8 if index < 4 else 7,
            "selection_stratum": f"s{index % 3}",
            "gates": {"promotion_strength": False},
        }
        for index in range(16)
    ]

    summary = pilot.summarize_pilot_labels(
        weak,
        attempted_group_count=20,
        action_changed_group_count=20,
        execution_coverage={
            "coverage_complete": True,
            "observed_h_system_by_block": {7: 12, 8: 4},
        },
        required_h_system_by_block={7: 12, 8: 4},
    )

    assert summary["label_counts"]["FAIR_SYSTEM_BENEFICIAL"] == 16
    assert summary["promotion_eligible_fair_positive_count"] == 0
    assert summary["gates"]["fair_system_positive_count"] is False
    assert summary["pilot_support_pass"] is False


def test_h_system_certificate_also_counts_in_action_changing_denominator() -> None:
    pair = {
        "source_group_id": "g0",
        "horizon": "H_system",
        "action_changed": True,
        "pair_complete": True,
        "action_change_certificate": {
            "valid": True,
            "changed_action_count": 1,
        },
    }

    assert pilot.action_changed_source_group_count({"pairs": [pair]}) == 1


def _merge_target(group: str, horizon: str, ordinal: int) -> dict[str, object]:
    return {
        "target_id": f"{group}:{horizon}",
        "source_group_id": group,
        "horizon": horizon,
        "event_ordinal": ordinal,
        "runtime_bag_id": ordinal,
    }


def _merge_pair(group: str, horizon: str, ordinal: int) -> dict[str, object]:
    return {
        **_merge_target(group, horizon, ordinal),
        "action_changed": True,
        "pair_complete": True,
        "action_change_certificate": {
            "valid": True,
            "changed_action_count": 1,
        },
    }


def test_merge_pair_payloads_is_resumable_and_counts_system_certificates() -> None:
    expected = [
        _merge_target("a", "H_system", 20),
        _merge_target("b", "H_bag", 10),
    ]
    first = _merge_pair("a", "H_system", 20)
    second = _merge_pair("b", "H_bag", 10)

    merged = pilot.merge_pair_payloads(
        [{"pairs": [first]}, {"pairs": [first, second]}], expected
    )

    assert [row["target_id"] for row in merged["pairs"]] == [
        "a:H_system",
        "b:H_bag",
    ]
    assert merged["duplicate_pair_count"] == 1
    assert merged["coverage_complete"] is True
    assert merged["missing_target_ids"] == []
    assert merged["expected_horizon_counts"] == {"H_bag": 1, "H_system": 1}
    assert merged["observed_unique_group_count"] == 2
    assert merged["action_changed_unique_group_count"] == 2


def test_merge_pair_payloads_partial_coverage_and_conflicts_fail_closed() -> None:
    expected = [
        _merge_target("a", "H_system", 20),
        _merge_target("b", "H_bag", 10),
    ]
    first = _merge_pair("a", "H_system", 20)
    partial = pilot.merge_pair_payloads([{"pairs": [first]}], expected)

    assert partial["coverage_complete"] is False
    assert partial["missing_target_ids"] == ["b:H_bag"]

    conflict = copy.deepcopy(first)
    conflict["pair_complete"] = False
    with pytest.raises(pilot.SourcePilotError, match="conflicting duplicate"):
        pilot.merge_pair_payloads(
            [{"pairs": [first]}, {"pairs": [conflict]}], expected
        )
    unexpected = _merge_pair("c", "H_bag", 30)
    with pytest.raises(pilot.SourcePilotError, match="unexpected pair"):
        pilot.merge_pair_payloads([{"pairs": [unexpected]}], expected)


def test_formal_execution_coverage_audits_manifest_not_partial_payload_claims() -> None:
    targets = [
        {
            **_merge_target("a", "H_bag", 10),
            "release_block": 7,
        },
        {
            **_merge_target("a", "H_system", 10),
            "release_block": 7,
        },
        {
            **_merge_target("b", "H_bag", 20),
            "release_block": 8,
        },
    ]
    partial_pair = {
        **_merge_pair("a", "H_system", 10),
        "release_block": 7,
        "horizon_complete": True,
    }

    coverage = pilot.pair_execution_coverage(
        {"pairs": [partial_pair], "coverage_complete": False}, targets
    )

    assert coverage["coverage_complete"] is False
    assert coverage["expected_execution_target_count"] == 2
    assert coverage["observed_execution_target_count"] == 1
    assert coverage["missing_execution_target_count"] == 1
    assert coverage["observed_h_system_by_block"] == {7: 1, 8: 0}


def test_pair_shard_manifest_runs_176_system_plus_only_80_bag_groups() -> None:
    targets: list[dict[str, object]] = []
    for index in range(256):
        group = f"g{index:03d}"
        ordinal = 10_000 + ((index * 37) % 1_000)
        targets.append(_merge_target(group, "H_bag", ordinal))
        if index < 176:
            targets.append(_merge_target(group, "H_system", ordinal))

    manifest = pilot.build_pair_shard_manifest(targets)

    assert manifest["execution_default"] == "PLAN_ONLY_DO_NOT_START_PROCESSES"
    assert manifest["max_workers"] == 4
    assert manifest["h_system_group_count"] == 176
    assert manifest["h_bag_remainder_group_count"] == 80
    assert manifest["covered_unique_group_count"] == 256
    assert manifest["expected_execution_target_count"] == 256
    system = [row for row in manifest["shards"] if row["horizon"] == "H_system"]
    remainder = [row for row in manifest["shards"] if row["horizon"] == "H_bag"]
    assert len(system) == 22
    assert {row["target_count"] for row in system} == {8}
    assert len(remainder) == 4
    assert {row["target_count"] for row in remainder} == {20}
    assert all(row["min_event_ordinal"] <= row["max_event_ordinal"] for row in manifest["shards"])
    assert all(row["event_ordinal_contiguous_slice"] is True for row in manifest["shards"])
    assert all(
        slice_row["pair_horizon"] == shard["horizon"]
        and slice_row["pair_limit"] == 1
        for shard in manifest["shards"]
        for slice_row in shard["cli_slices"]
    )


def test_repeated_pair_results_cli_and_manifest_are_plan_only() -> None:
    arguments = pilot.parse_args(
        [
            "--groups-output",
            "groups.jsonl",
            "--targets-output",
            "targets.jsonl",
            "--summary-output",
            "summary.json",
            "--pair-results",
            "shard0.json",
            "--pair-results",
            "shard1.json",
            "--shard-manifest-output",
            "manifest.json",
        ]
    )

    assert arguments.pair_results == [Path("shard0.json"), Path("shard1.json")]
    assert arguments.run_pairs is False
    assert arguments.shard_manifest_output == Path("manifest.json")


def test_main_manifest_shard_executes_one_exact_call_with_whole_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    census = tmp_path / "census.jsonl"
    pilot._write_jsonl(
        census,
        [_opportunity(index, block=7) for index in range(220)]
        + [_opportunity(1000 + index, block=8) for index in range(80)],
    )
    plan = pilot.build_source_pilot_plan(pilot._read_jsonl(census), require_complete=True)
    manifest = pilot.build_pair_shard_manifest(plan["targets"])
    manifest_path = tmp_path / "manifest.json"
    pilot._write_json(manifest_path, manifest)
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"fixture")
    calls: list[list[dict[str, object]]] = []
    monkeypatch.setattr(pilot, "load_native_backend", lambda path: object())
    monkeypatch.setattr(
        pilot,
        "build_2x_native_arguments",
        lambda root: (["native"], [], {"scale": "2x"}),
    )

    def fake_run(
        backend: object,
        native_arguments: list[object],
        targets: list[dict[str, object]],
    ) -> dict[str, object]:
        calls.append(targets)
        return {"pairs": []}

    monkeypatch.setattr(pilot, "run_native_exact_pairs", fake_run)
    shard = manifest["shards"][0]

    assert pilot.main(
        [
            "--census",
            str(census),
            "--binary",
            str(binary),
            "--groups-output",
            str(tmp_path / "groups.jsonl"),
            "--targets-output",
            str(tmp_path / "targets.jsonl"),
            "--summary-output",
            str(tmp_path / "summary.json"),
            "--run-pairs",
            "--pair-shard-manifest",
            str(manifest_path),
            "--pair-shard-id",
            str(shard["shard_id"]),
            "--pairs-output",
            str(tmp_path / "pairs.json"),
            "--labels-output",
            str(tmp_path / "labels.jsonl"),
        ]
    ) == 0

    assert len(calls) == 1
    assert [target["target_id"] for target in calls[0]] == shard["target_ids"]
    assert len(calls[0]) == 8
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["pair_slice"]["selection_kind"] == "MANIFEST_SHARD"
    assert summary["pair_slice"]["selected_target_ids"] == shard["target_ids"]


@pytest.mark.parametrize(
    "extra",
    [
        ["--pair-shard-manifest", "manifest.json"],
        ["--pair-shard-id", "h_system-000"],
        [
            "--pair-shard-manifest",
            "manifest.json",
            "--pair-shard-id",
            "h_system-000",
            "--pair-offset",
            "1",
        ],
        [
            "--pair-shard-manifest",
            "manifest.json",
            "--pair-shard-id",
            "h_system-000",
            "--pair-limit",
            "8",
        ],
    ],
)
def test_main_rejects_partial_or_mixed_manifest_shard_cli(
    tmp_path: Path, extra: list[str]
) -> None:
    census = tmp_path / "census.jsonl"
    pilot._write_jsonl(census, [_opportunity(1, block=7)])
    common = [
        "--census",
        str(census),
        "--groups-output",
        str(tmp_path / "groups.jsonl"),
        "--targets-output",
        str(tmp_path / "targets.jsonl"),
        "--summary-output",
        str(tmp_path / "summary.json"),
        "--allow-shortfall",
    ]

    assert pilot.main([*common, *extra]) == 2

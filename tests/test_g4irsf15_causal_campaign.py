from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import pytest

from scripts.eval import g4irsf15_causal_campaign as campaign


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_process_memory_snapshot_uses_real_supported_sampler() -> None:
    snapshot = campaign._process_memory_snapshot()
    assert snapshot["sampler"] in {
        "WINDOWS_PSAPI_GET_PROCESS_MEMORY_INFO",
        "GETRUSAGE_RUSAGE_SELF",
    }
    assert isinstance(snapshot["peak_resident_bytes"], int)
    assert snapshot["peak_resident_bytes"] > 0
    if snapshot["resident_bytes"] is not None:
        assert isinstance(snapshot["resident_bytes"], int)
        assert 0 < snapshot["resident_bytes"] <= snapshot[
            "peak_resident_bytes"
        ]


def _target_address_skeleton(index: int, kind: str) -> dict[str, object]:
    skeleton_id = _sha(f"target-address-skeleton:{index}")
    return {
        "schema": campaign.SKELETON_SCHEMA,
        "skeleton_id": skeleton_id,
        "skeleton_selection_sha256": skeleton_id,
        "population_group_sha256": _sha(
            f"target-address-population:{index}"
        ),
        "kind": kind,
        "event_ordinal": 11,
        "event_seq": 19,
        "event_time_bits": 23,
        "node": 7,
        "runtime_bag_id": index,
        "peer_runtime_bag_id": index + 1,
        "baseline_next_node": 8,
        "selected_next_node": 9,
        "baseline_release": True,
        "selected_boolean": False,
        "source_ready_order": [index, index + 1],
        "legal_next_edges": [8, 9],
        "baseline_action": f"BASELINE:{index}",
        "intervention_action": f"TREATMENT:{index}",
        "expected_action_change_type": "LOCAL_ACTION_CHANGE",
        "outcome_free": True,
        "runtime_state_sha256": None,
        "boundary_sha256": None,
        "sampling": {
            "sampling_stratum_id": f"{kind}|BODY|NO_DIVERGENCE|LOW",
            "N_h": 10,
            "n_h": 2,
            "pi_h": 0.2,
            "analysis_weight": 5.0,
        },
        "offline_sampling_metadata": {
            "runtime_only": False,
            "must_not_enter_policy_features": True,
        },
    }


def test_target_address_frame_defers_full_seals_deterministically() -> None:
    cohort_sha256 = _sha("target-address-cohort")
    skeletons = [
        _target_address_skeleton(1, "I1"),
        _target_address_skeleton(2, "I3"),
    ]
    protected = {
        "task": {"input_runtime_cohort_sha256": cohort_sha256}
    }

    first = campaign._materialize_target_address_frame(
        skeletons, protected=protected
    )
    second = campaign._materialize_target_address_frame(
        skeletons, protected=protected
    )

    assert first == second
    assert len(first) == len(skeletons)
    assert {row["schema"] for row in first} == {
        campaign.TARGET_ADDRESS_SCHEMA
    }
    assert all(
        row["descriptor_id"]
        == row["target_address_id"]
        == row["skeleton_id"]
        == row["population_selection_sha256"]
        for row in first
    )
    assert all(
        row["input_runtime_cohort_sha256"] == cohort_sha256
        and row["runtime_state_sha256"] is None
        and row["boundary_sha256"] is None
        and row["full_state_seal"] == "DEFERRED_TO_EXECUTED_PAIR"
        for row in first
    )
    assert first[0]["prepop_event_group_sha256"] == first[1][
        "prepop_event_group_sha256"
    ]
    for row in first:
        assert row["target_address_sha256_by_horizon"] == {
            horizon: campaign._target_address_horizon_sha256(
                str(row["target_address_id"]), horizon
            )
            for horizon in ("H_bag", "H_system")
        }
        assert row["sampling"]["cluster_id"] == row[
            "prepop_event_group_sha256"
        ]
        assert row["sampling"]["cluster_bootstrap_unit"] == (
            "prepop_event_group_sha256"
        )

    eager = dict(skeletons[0])
    eager["runtime_state_sha256"] = _sha("forbidden-eager-seal")
    with pytest.raises(
        campaign.CampaignError,
        match="TARGET_ADDRESS_SOURCE_SKELETON_NOT_OUTCOME_FREE",
    ):
        campaign._materialize_target_address_frame(
            [eager], protected=protected
        )


def _population() -> list[dict[str, object]]:
    counts = {"I1": 3072, "I3": 2560, "I4": 2560}
    rows: list[dict[str, object]] = []
    ordinal = 0
    for kind, count in counts.items():
        for index in range(count):
            descriptor = _sha(f"descriptor:{kind}:{index}")
            tail = index % 8 == 0
            divergence = index % 3 == 0
            contention = "HIGH" if index % 2 else "LOW"
            tags = [
                "top_tail" if tail else "non_tail",
                "route_divergence" if divergence else "no_divergence",
                ("entry_early", "entry_normal", "entry_late")[index % 3],
                "slack_tight" if index % 2 else "slack_ample",
                "storage" if index % 4 == 0 else "direct",
                f"goal_{48 + index % 3}",
                "hour_6" if index % 5 == 0 else "hour_other",
                "source_0_1_2_53" if index % 2 else "source_3_4_5",
                "node_52" if index % 7 == 0 else "node_19_22",
                "high_contention" if contention == "HIGH" else "low_contention",
            ]
            if index % 101 == 0:
                tags.append("p2_prefilter_candidate")
            rows.append(
                {
                    "schema": campaign.DESCRIPTOR_SCHEMA,
                    "descriptor_id": descriptor,
                    "sample_sha256": descriptor,
                    "kind": kind,
                    "clone_group_id": _sha(f"clone:{kind}:{index}"),
                    "event_ordinal": ordinal // 2,
                    "event_seq": ordinal,
                    "event_time_bits": ordinal,
                    "node": index % 54,
                    "runtime_state_sha256": _sha(f"state:{kind}:{index}"),
                    "boundary_sha256": _sha(f"boundary:{kind}:{index}"),
                    "runtime_bag_id": index,
                    "peer_runtime_bag_id": index + 1 if kind == "I1" else -1,
                    "baseline_next_node": index % 54,
                    "selected_next_node": (index + 1) % 54 if kind == "I3" else -1,
                    "baseline_release": True,
                    "selected_boolean": False,
                    "baseline_action": f"baseline:{kind}:{index}",
                    "intervention_action": f"treatment:{kind}:{index}",
                    "horizon": "H_bag",
                    "intervention_sha256": descriptor,
                    "intervention_sha256_by_horizon": {
                        "H_bag": descriptor,
                        "H_system": _sha(f"h-system:{kind}:{index}"),
                    },
                    "sampling_stratum_id": "|".join(
                        (
                            kind,
                            "TAIL" if tail else "BODY",
                            "DIVERGENCE" if divergence else "NO_DIVERGENCE",
                            contention,
                        )
                    ),
                    "coverage_tags": tags,
                    "offline_sampling_metadata": {
                        "runtime_only": False,
                        "must_not_enter_policy_features": True,
                        "task_id": index,
                    },
                }
            )
            ordinal += 1
    return rows


@pytest.fixture(scope="module")
def descriptor_pool() -> list[dict[str, object]]:
    selected, coverage, design = campaign.select_descriptor_pool(
        _population(), pool_size=campaign.DEFAULT_DESCRIPTOR_POOL
    )
    assert coverage
    assert design["pool_sha256"]
    return selected


def test_descriptor_pool_is_deterministic_weighted_min_hash() -> None:
    population = _population()
    first, coverage, _ = campaign.select_descriptor_pool(
        population, pool_size=campaign.DEFAULT_DESCRIPTOR_POOL
    )
    second, _, _ = campaign.select_descriptor_pool(
        population, pool_size=campaign.DEFAULT_DESCRIPTOR_POOL
    )

    assert [row["descriptor_id"] for row in first] == [
        row["descriptor_id"] for row in second
    ]
    assert len(first) == campaign.DEFAULT_DESCRIPTOR_POOL
    assert all(
        Counter(row["kind"] for row in first)[kind]
        >= campaign.FORMAL_ATTEMPT_TARGETS[kind] + 128
        for kind in campaign.KINDS
    )
    assert {row["coverage_status"] for row in coverage} == {"COVERED"}
    for row in first:
        sampling = row["sampling"]
        assert sampling["pi_h"] == sampling["n_h"] / sampling["N_h"]
        assert sampling["analysis_weight"] == pytest.approx(
            1.0 / sampling["pi_h"]
        )
        assert sampling["selection_panel"] in {
            "POPULATION_MIN_HASH",
            "ENRICHED_TAIL_MIN_HASH",
            "STRATIFIED_MIN_HASH_FILL",
        }


def test_pilot_rounds_are_disjoint_and_exact(
    descriptor_pool: list[dict[str, object]],
) -> None:
    round_one = campaign.select_pilot_targets(
        descriptor_pool, round_index=1
    )
    round_two = campaign.select_pilot_targets(
        descriptor_pool, round_index=2
    )
    assert Counter(row["kind"] for row in round_one) == Counter(
        {kind: 64 for kind in campaign.KINDS}
    )
    assert all(row["horizon"] == "H_bag" for row in round_one + round_two)
    assert not (
        {row["target_key"] for row in round_one}
        & {row["target_key"] for row in round_two}
    )


def test_formal_plan_uses_4096_attempts_and_unique_h_system_groups(
    descriptor_pool: list[dict[str, object]],
) -> None:
    targets, preregistration = campaign.preregister_formal_targets(
        descriptor_pool,
        pilot_complete_by_kind={kind: 30 for kind in campaign.KINDS},
    )
    assert preregistration["method"] == (
        "TARGET_DIVIDED_BY_TWO_SIDED_95_PERCENT_WILSON_LOWER_"
        "ENDPOINT_CAPPED_AT_LOCAL_TARGET_ADDRESS_FRAME"
    )
    assert len(targets) >= 4096
    assert Counter(row["kind"] for row in targets) == Counter(
        {
            kind: preregistration["per_kind"][kind][
                "preregistered_attempts"
            ]
            for kind in campaign.KINDS
        }
    )
    pilot_ids = {
        row["descriptor_id"]
        for round_index in (1, 2)
        for row in campaign.select_pilot_targets(
            descriptor_pool, round_index=round_index
        )
    }
    assert not ({row["descriptor_id"] for row in targets} & pilot_ids)
    h_system = [row for row in targets if row["horizon"] == "H_system"]
    assert len(h_system) == preregistration[
        "h_system_preregistration"
    ]["preregistered_attempts"]
    assert len({row["clone_group_id"] for row in h_system}) == len(h_system)
    for row in targets:
        assert row["intervention_sha256"] == row[
            "intervention_sha256_by_horizon"
        ][row["horizon"]]


def test_shards_do_not_split_an_event_ordinal(
    descriptor_pool: list[dict[str, object]],
) -> None:
    targets = campaign.select_formal_targets(descriptor_pool)
    shards = campaign.build_contiguous_shards(targets, shard_size=256)
    ordinal_to_shard: dict[int, int] = {}
    prior_end = -1
    for shard in shards:
        assert shard["event_ordinal_start"] > prior_end
        prior_end = shard["event_ordinal_end"]
        for row in shard["targets"]:
            ordinal = row["event_ordinal"]
            assert ordinal_to_shard.setdefault(
                ordinal, shard["shard_index"]
            ) == shard["shard_index"]


def _metrics() -> dict[str, object]:
    return {
        "cohort_size": 2,
        "known_count": 2,
        "completed_count": 2,
        "failed_count": 0,
        "deadline_miss_count": 0,
        "completion_mean_seconds": 10.0,
        "completion_p95_seconds": 11.0,
        "completion_p99_seconds": 11.0,
        "source_wait_mean_seconds": 1.0,
        "total_local_wait_mean_seconds": 2.0,
        "junction_wait_mean_seconds": 1.0,
        "merge_wait_mean_seconds": 0.0,
        "edge_travel_mean_seconds": 5.0,
        "node_service_mean_seconds": 3.0,
        "loop_extra_mean_seconds": 0.0,
        "path_length_hops_total": 20.0,
        "path_length_hops_mean": 10.0,
    }


def _branch(*, h_system: bool) -> dict[str, object]:
    invariants = {
        "requested_count": (
            campaign.FULL_SEGMENT_COUNT if h_system else 2
        ),
        "unsafe_entry_count": 0,
        "reservation_conflict_count": 0,
        "runtime_full_astar_call_count": 0,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "teacher_input_count": 0,
        "max_selected_edges_per_bag": 1,
        "two_step_reservation_count": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "merge_grant_stale_arbitration_count": 0,
        "stale_arbitration_event_count": 0,
        "merge_grant_conservation_holds": True,
        "merge_grant_active_bijection_holds": True,
        "merge_grant_runtime_owned_capability": True,
        "merge_grant_exact_slot_no_future_shift": True,
        "merge_grant_outstanding_request_count": 0,
        "merge_grant_final_active_unconsumed": 0,
        "artificial_batch_delay_seconds": 0.0,
        "live_safety_pass": True,
        "formal_hard_gate_evaluated": h_system,
        "formal_hard_gate_pass": h_system,
        "hard_gate_fail_reasons": [],
        "completed_count": campaign.FULL_SEGMENT_COUNT if h_system else 2,
        "failed_segment_count": 0,
    }
    return {
        "finalized": h_system,
        "horizon_complete": True,
        "blocked": False,
        "affected_bag_outcomes": [
            {
                "runtime_bag_id": 1,
                "segment_id": "1:direct",
                "completed": True,
                "failed": False,
                "finish_time": 20.0,
                "completion_seconds": 10.0,
                "source_wait_seconds": 1.0,
                "total_local_wait_seconds": 2.0,
                "junction_wait_seconds": 1.0,
                "merge_wait_seconds": 0.0,
                "edge_travel_seconds": 5.0,
                "node_service_seconds": 3.0,
                "loop_extra_seconds": 0.0,
                "decision_count": 2,
                "retry_count": 0,
                "loop_count": 0,
            }
        ],
        "cohort_metrics": _metrics(),
        "invariants": invariants,
    }


def _target(horizon: str) -> dict[str, object]:
    descriptor = _sha("label-target")
    return {
        "target_key": f"{descriptor}:{horizon}",
        "descriptor_id": descriptor,
        "kind": "I3",
        "clone_group_id": _sha("label-clone"),
        "event_ordinal": 12,
        "horizon": horizon,
        "sampling": {
            "sampling_stratum_id": "I3|BODY|DIVERGENCE|HIGH",
            "N_h": 100,
            "n_h": 10,
            "pi_h": 0.1,
            "analysis_weight": 10.0,
        },
        "coverage_tags": ["non_tail"],
        "offline_sampling_metadata": {
            "runtime_only": False,
            "must_not_enter_policy_features": True,
            "task_id": 4,
        },
    }


def _pair(horizon: str) -> dict[str, object]:
    state = _sha("same-state")
    return {
        "descriptor_id": _target(horizon)["descriptor_id"],
        "kind": "I3",
        "horizon": horizon,
        "pair_status": "ACTION_CHANGED_HORIZON_COMPLETE",
        "horizon_complete": True,
        "action_changed": True,
        "same_state_start": True,
        "source_checkpoint_state_sha256": state,
        "baseline_start_state_sha256": state,
        "treatment_start_state_sha256": state,
        "affected_runtime_bag_ids": [1],
        "committed_action_certificate": {
            "valid": True,
            "changed_action_count": 1,
            "baseline_action": "EDGE:1",
            "treatment_action": "EDGE:2",
        },
        "baseline": _branch(h_system=horizon == "H_system"),
        "treatment": _branch(h_system=horizon == "H_system"),
        "h_system_cohort_size": (
            campaign.FULL_SEGMENT_COUNT if horizon == "H_system" else 0
        ),
        "h_system_cohort_is_all_input_runtime_ids": horizon == "H_system",
    }


def test_h_system_fails_closed_without_realized_affected_set() -> None:
    branch = _branch(h_system=True)
    passed, blockers = campaign._branch_gate(
        branch,
        "H_system",
        terminal_evidence_complete=True,
        protected_full_1x_shape=True,
    )
    assert passed
    assert blockers == []

    branch["invariants"]["merge_grant_stale_arbitration_count"] = 1
    with pytest.raises(
        campaign.CampaignError,
        match="BRANCH_INVARIANT_GATE_DERIVATION_DRIFT",
    ):
        campaign._branch_gate(
            branch,
            "H_system",
            terminal_evidence_complete=True,
            protected_full_1x_shape=True,
        )


def test_zstd_round_trip_is_canonical() -> None:
    pytest.importorskip("zstandard")
    rows = [{"a": 1}, {"b": "二"}]
    compressed = campaign._zstd_compress(campaign._jsonl_bytes(rows))
    assert campaign._zstd_decompress_jsonl(compressed) == rows
    assert campaign._canonical_sequence_sha256(
        rows
    ) == campaign._canonical_sha256(rows)


def test_split_connects_all_direct_affected_raw_tasks() -> None:
    def row(index: int, tasks: list[int]) -> dict[str, object]:
        outcomes = [
            {"runtime_bag_id": index * 10 + offset, "task_id": task}
            for offset, task in enumerate(tasks)
        ]
        return {
            "target_key": _sha(f"split-target:{index}"),
            "clone_group_id": _sha(f"split-clone:{index}"),
            "offline_sampling_metadata": {"task_id": tasks[0]},
            "baseline_affected_bag_outcomes": outcomes,
            "treatment_affected_bag_outcomes": [
                dict(item) for item in outcomes
            ],
        }

    split = campaign._split_groups(
        [
            row(1, [10, 20]),
            row(2, [20, 20, 30]),
        ]
    )
    assert split["split_contamination_count"] == 0
    assert split["group_count"] == 1
    assert split["groups"][0]["raw_task_ids"] == [10, 20, 30]


def test_same_state_must_bind_sealed_target_runtime_state() -> None:
    target = {
        "target_key": _sha("same-state-target"),
        "descriptor_id": _sha("same-state-descriptor"),
        "event_ordinal": 17,
        "kind": "I3",
        "clone_group_id": _sha("same-state-clone"),
        "runtime_state_sha256": _sha("sealed-state"),
        "horizon": "H_bag",
        "sampling": {},
        "coverage_tags": [],
    }
    replay_state = _sha("different-replay-state")
    pair = {
        "horizon": "H_bag",
        "pair_status": "SCREENING_FALSE_POSITIVE",
        "same_state_start": True,
        "source_checkpoint_state_sha256": replay_state,
        "baseline_start_state_sha256": replay_state,
        "treatment_start_state_sha256": replay_state,
        "baseline": None,
        "treatment": None,
    }
    label = campaign._label_pair(pair, target)
    assert label["same_state_start"] is False
    assert label["eligible_causal_label"] is False


def test_finalize_cli_requires_repeatable_orchestrator_profiles() -> None:
    base = [
        "finalize",
        "--campaign",
        "pilot",
        "--binary",
        "binary.pyd",
        "--build-manifest",
        "build.json",
    ]
    with pytest.raises(SystemExit):
        campaign._parser().parse_args(base)
    parsed = campaign._parser().parse_args(
        [
            *base,
            "--orchestrator-profile",
            "profile-1.json",
            "--orchestrator-profile",
            "profile-2.json",
        ]
    )
    assert parsed.orchestrator_profiles == [
        Path("profile-1.json"),
        Path("profile-2.json"),
    ]


def test_source_bundle_freezes_orchestrator_implementation() -> None:
    assert campaign.ORCHESTRATOR_PATH in campaign.SOURCE_PATHS

from __future__ import annotations

import numpy as np
import pytest

from czr005.g4irsf20.features import (
    EXCLUDED_UNAVAILABLE_PLANNED_FEATURES,
    F4_FEATURES,
    F5_FEATURES,
    FEATURE_GROUP_DIMENSIONS,
    RouteFeatureError,
    RouteFeatureGroup,
    native_route_candidate_mapping,
    project_rich_route_v2,
    project_rich_route_v2_mapping,
)
from czr005.g4irsf20.models import (
    PairwiseResidualScorer,
    SetCandidateScorer,
    TinyResidualScorer,
    grouped_split_indices,
    offline_route_metrics,
    route_model_summary,
    s4_costs_to_scores,
)


def _native_rows() -> tuple[dict[str, object], dict[str, object]]:
    decision: dict[str, object] = {
        "decision_id": "scenario:101:7",
        "task_id": 101,
        "current_node": 41,
        "goal_node": 99,
        "event_time": 10.0,
        "selected_next": 42,
        "metadata": {
            "priority_slack_seconds": 75.0,
            "priority_age_seconds": 12.0,
            "priority_local_contention": 6,
            "scorer_raw_prediction": 1,
        },
        "local_snapshot": {
            "junction_queue_length": 4,
            "next_available_time": 13.0,
            "downstream_pressure": 50,
        },
        "short_history": [37, 41],
    }
    candidate: dict[str, object] = {
        "next_node": 42,
        "model_score": 123.0,
        "scorer_raw_score": 456.0,
        "shield_allowed": True,
        "features": {
            "target_queue_length": 3,
            "target_scheduled_incoming": 2,
            "corridor_next_available": 14.0,
            "target_next_available": 18.0,
            "travel_time": 5.0,
            "static_potential": 21.0,
            "recent_visit_count": 1,
            "current_goal_queue_length": 5,
            "target_goal_queue_length": 7,
            "target_goal_scheduled_incoming": 4,
            "current_goal_max_wait": 8.0,
            "goal_conditioned_differential": -2.0,
            "estimated_service_rate": 0.75,
            "service_weighted_pressure": 14.5,
            "advertised_fault": False,
            "fault_message_age_seconds": 1.5,
            "two_hop_queue_pressure": 9,
            # Existing source-admission values are intentionally ignored.
            "first_edge_credit_required": False,
            "first_edge_credit_matches": False,
            "first_edge_credit_valid": False,
            "first_edge_credit_slack_seconds": 0.0,
        },
    }
    return decision, candidate


def _flat_native() -> dict[str, object]:
    decision, candidate = _native_rows()
    return native_route_candidate_mapping(decision, candidate)


def test_rich_route_v2_has_fixed_minimal_groups_and_native_projection() -> None:
    assert FEATURE_GROUP_DIMENSIONS == {
        RouteFeatureGroup.F0: 6,
        RouteFeatureGroup.F1: 9,
        RouteFeatureGroup.F2: 9,
        RouteFeatureGroup.F3: 16,
        RouteFeatureGroup.F4: 22,
        RouteFeatureGroup.F5: 21,
    }
    raw = _flat_native()
    f0 = project_rich_route_v2_mapping(raw, RouteFeatureGroup.F0)
    assert f0 == {
        "target_queue_length": 3.0,
        "target_scheduled_incoming": 2.0,
        "corridor_wait_seconds": 4.0,
        "target_wait_after_travel_seconds": 3.0,
        "edge_travel_time_seconds": 5.0,
        "static_potential_seconds": 21.0,
    }
    assert project_rich_route_v2(raw, "F4").shape == (22,)
    assert "candidate_two_hop_queue_pressure" in F4_FEATURES
    assert "candidate_two_hop_queue_pressure" not in F5_FEATURES
    assert "eta_bins_0s_5s_15s_30s_60s" in (
        EXCLUDED_UNAVAILABLE_PLANNED_FEATURES["candidate_downstream"]
    )


@pytest.mark.parametrize(
    "leaked_name",
    [
        "task_id",
        "absolute_source_id",
        "future_route_cost",
        "realized_outcome",
        "global_queue_length",
        "oracle_action",
    ],
)
def test_projection_rejects_identity_future_outcome_and_global_leakage(
    leaked_name: str,
) -> None:
    raw = _flat_native()
    raw[leaked_name] = 1
    with pytest.raises(RouteFeatureError, match="FORBIDDEN_FEATURE"):
        project_rich_route_v2(raw, RouteFeatureGroup.F4)


def test_projection_fails_fast_when_a_required_native_field_is_missing() -> None:
    raw = _flat_native()
    del raw["estimated_service_rate"]
    with pytest.raises(
        RouteFeatureError,
        match="NATIVE_FEATURES_MISSING:estimated_service_rate",
    ):
        project_rich_route_v2(raw, RouteFeatureGroup.F3)


def test_grouped_split_never_contaminates_choice_groups() -> None:
    group_ids = [
        "map:a",
        "map:a",
        "map:b",
        "map:c",
        "map:c",
        "map:d",
        "map:e",
        "map:e",
        "map:f",
        "map:g",
    ]
    split = grouped_split_indices(
        group_ids,
        train_fraction=0.6,
        validation_fraction=0.2,
        seed=20,
    )
    partitions = (split.train, split.validation, split.audit)
    group_sets = [
        {group_ids[index] for index in partition}
        for partition in partitions
    ]
    assert group_sets[0].isdisjoint(group_sets[1])
    assert group_sets[0].isdisjoint(group_sets[2])
    assert group_sets[1].isdisjoint(group_sets[2])
    assert sorted(index for partition in partitions for index in partition) == list(
        range(len(group_ids))
    )


def _training_groups() -> tuple[list[np.ndarray], list[np.ndarray], list[int]]:
    rng = np.random.default_rng(20)
    candidate_sets: list[np.ndarray] = []
    utility_sets: list[np.ndarray] = []
    s4_indices: list[int] = []
    for group_index in range(24):
        candidate_count = 2 + group_index % 3
        features = rng.normal(size=(candidate_count, 6))
        utility = (
            1.8 * features[:, 0]
            - 1.1 * features[:, 1]
            + 0.6 * features[:, 2]
            + 0.2 * features[:, 0] * features[:, 3]
        )
        candidate_sets.append(features)
        utility_sets.append(utility)
        s4_indices.append(group_index % candidate_count)
    return candidate_sets, utility_sets, s4_indices


def test_three_reused_model_families_train_score_and_explain_themselves() -> None:
    candidate_sets, utility_sets, s4_indices = _training_groups()
    feature_names = (
        "target_queue_length",
        "target_scheduled_incoming",
        "corridor_wait_seconds",
        "target_wait_after_travel_seconds",
        "edge_travel_time_seconds",
        "static_potential_seconds",
    )
    flattened = np.concatenate(candidate_sets, axis=0)
    flattened_utility = np.concatenate(utility_sets, axis=0)

    pairwise = PairwiseResidualScorer.fit(
        candidate_sets,
        utility_sets,
        s4_indices,
        feature_names=feature_names,
        epochs=140,
    )
    tiny = TinyResidualScorer.fit(
        flattened,
        flattened_utility,
        feature_names=feature_names,
        hidden_dim=8,
        epochs=180,
        learning_rate=0.03,
        seed=20,
    )
    set_model = SetCandidateScorer.fit(
        candidate_sets,
        utility_sets,
        feature_names=feature_names,
        hidden_dim=8,
        epochs=180,
        learning_rate=0.03,
        seed=20,
    )

    zero_baselines = [np.zeros(group.shape[0]) for group in candidate_sets]
    score_sets = {
        "pairwise": [
            pairwise.scores(group, baseline, s4_index)
            for group, baseline, s4_index in zip(
                candidate_sets,
                zero_baselines,
                s4_indices,
                strict=True,
            )
        ],
        "tiny": [
            tiny.scores(group, baseline)
            for group, baseline in zip(candidate_sets, zero_baselines, strict=True)
        ],
        "set": [set_model.scores(group) for group in candidate_sets],
    }
    models = (pairwise, tiny, set_model)
    summaries = [route_model_summary(model) for model in models]
    assert len({summary["family"] for summary in summaries}) == 3
    assert all(summary["feature_names"] == list(feature_names) for summary in summaries)
    assert all(summary["identity_features_used"] is False for summary in summaries)
    assert all(summary["outcome_features_used"] is False for summary in summaries)
    assert [summary["consumes_s4_scores"] for summary in summaries] == [True, True, False]

    for scores in score_sets.values():
        metrics = offline_route_metrics(scores, utility_sets, s4_indices)
        assert metrics.group_count == len(candidate_sets)
        assert metrics.pairwise_comparisons > 0
        assert 0.0 <= metrics.beneficial_precision <= 1.0
        assert 0.0 <= metrics.harmful_applied_rate <= 1.0
        assert np.isfinite(metrics.mean_regret)
        assert metrics.to_dict()["max_regret"] >= 0.0

    assert np.array_equal(s4_costs_to_scores([4.0, 7.5]), [-4.0, -7.5])

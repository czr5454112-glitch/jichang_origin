from __future__ import annotations

import pytest

from czr005.g4irsf17 import (
    CANONICAL_OBSERVATION_FEATURES,
    CANDIDATE_FEATURES,
    CONTEXT_FEATURES,
    LEGACY_29_FEATURES,
    PAIRWISE_FEATURES,
    BoundedTemporalCounter,
    LocalFeatureError,
    SourceTemporalCounters,
    assert_strictly_local_feature_names,
    canonical_feature_vector,
    canonical_source_front_observation,
    chronological_time_split,
    deterministic_group_split,
    group_overlap_count,
    make_diagnostic_splits,
    pairwise_feature_vector,
    rows_for_split,
)
from czr005.g4irsf17.features import (
    CANDIDATE_FEATURE_SPECS,
    CONTEXT_FEATURE_SPECS,
)


def _valid(specs):
    return {
        spec.name: spec.lower if spec.lower == spec.upper else (spec.lower + spec.upper) / 2.0
        for spec in specs
    }


def test_canonical_schema_is_exact_bounded_local_and_id_free() -> None:
    candidate = _valid(CANDIDATE_FEATURE_SPECS)
    context = _valid(CONTEXT_FEATURE_SPECS)
    observation = canonical_source_front_observation(candidate, context)

    assert len(LEGACY_29_FEATURES) == 29
    assert tuple(observation) == CANONICAL_OBSERVATION_FEATURES
    assert canonical_feature_vector(observation).shape == (
        len(CANONICAL_OBSERVATION_FEATURES),
    )
    with pytest.raises(LocalFeatureError, match="FEATURES_EXTRA"):
        canonical_feature_vector({**observation, "task_id": 7})
    assert len(PAIRWISE_FEATURES) == len(CANONICAL_OBSERVATION_FEATURES)
    assert not any(name.endswith("_id") for name in CANONICAL_OBSERVATION_FEATURES)
    assert not any("future" in name or "global" in name for name in CANONICAL_OBSERVATION_FEATURES)

    with pytest.raises(LocalFeatureError, match="NONLOCAL_OR_ID_FEATURE"):
        assert_strictly_local_feature_names(["candidate_wait_age_seconds", "task_id"])
    broken = dict(candidate)
    broken["candidate_local_rank"] = 4
    with pytest.raises(LocalFeatureError, match="FEATURE_OUT_OF_BOUNDS"):
        canonical_source_front_observation(broken, context)
    clipped = canonical_source_front_observation(broken, context, clip=True)
    assert clipped["candidate_local_rank"] == 3.0


def test_pairwise_vector_has_candidate_deltas_and_unchanged_context() -> None:
    left = _valid(CANDIDATE_FEATURE_SPECS)
    right = dict(left)
    left["candidate_wait_age_seconds"] = 20.0
    right["candidate_wait_age_seconds"] = 7.0
    context = _valid(CONTEXT_FEATURE_SPECS)

    left_right = pairwise_feature_vector(left, right, context)
    right_left = pairwise_feature_vector(right, left, context)
    candidate_count = len(CANDIDATE_FEATURES)
    wait_index = CANDIDATE_FEATURES.index("candidate_wait_age_seconds")
    assert left_right[wait_index] == 13.0
    assert right_left[wait_index] == -13.0
    assert (left_right[:candidate_count] == -right_left[:candidate_count]).all()
    assert (left_right[candidate_count:] == right_left[candidate_count:]).all()


def test_temporal_counters_use_inclusive_10_30_60_second_windows() -> None:
    counter = BoundedTemporalCounter(max_events=20)
    counter.extend([0.0, 30.0, 50.0, 60.0])
    assert counter.snapshot(60.0) == {10: 2, 30: 3, 60: 4}
    assert counter.snapshot(61.0) == {10: 1, 30: 2, 60: 3}

    source = SourceTemporalCounters(max_events=20)
    for timestamp in (50.0, 55.0, 60.0):
        source.record_release(timestamp)
    source.record_admission(58.0)
    snapshot = source.snapshot(60.0)
    assert snapshot["release_count_10s"] == 3.0
    assert snapshot["admission_count_10s"] == 1.0
    assert snapshot["queue_slope_10s"] == 2.0
    with pytest.raises(ValueError, match="MONOTONIC"):
        source.record_release(40.0)


def test_split_views_are_group_hard_deterministic_and_seal_final_audit() -> None:
    task_groups = [f"task-{index // 2}" for index in range(40)]
    sources = [f"source-{index % 10}" for index in range(40)]
    timestamps = [float(index * 3_600) for index in range(40)]
    first = deterministic_group_split(task_groups, seed=91)
    second = deterministic_group_split(task_groups, seed=91)
    assert first == second
    assert group_overlap_count(task_groups, first) == 0

    views = make_diagnostic_splits(
        sources,
        timestamps,
        task_groups,
        seed=91,
        model_feature_names=CANONICAL_OBSERVATION_FEATURES,
    )
    assert group_overlap_count(task_groups, views.task_group) == 0
    assert group_overlap_count(sources, views.source_held_out) == 0
    time_blocks = [int(timestamp // 3_600) for timestamp in timestamps]
    assert group_overlap_count(time_blocks, views.time_held_out) == 0
    assert views.to_dict()["split_keys_are_model_inputs"] is False
    assert "final_audit" in chronological_time_split(timestamps)

    rows = [{"value": index} for index in range(40)]
    with pytest.raises(ValueError, match="SEALED"):
        rows_for_split(rows, views.task_group, "final_audit")

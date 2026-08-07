from __future__ import annotations

import numpy as np
import pytest

from czr005.g4irsf17.features import (
    CANDIDATE_FEATURE_SPECS,
    CONTEXT_FEATURE_SPECS,
)
from czr005.g4irsf18 import (
    F2_OLD_22_FEATURES,
    FEATURE_GROUP_CONTRACTS,
    G17_LOCAL_39_FEATURES,
    LEGACY_29_FEATURES,
    LEGACY_PLUS_RICH_FEATURES,
    RICH_LOCAL_V1_ADDITIONAL_SPECS,
    RICH_LOCAL_V1_FEATURES,
    RICH_LOCAL_V1_NATIVE_PROVENANCE,
    DecisionHead,
    FeatureAblationGroup,
    LocalFeatureError,
    ablation_feature_vector,
    assert_deployable_g18_feature_names,
    build_candidate_action_observation,
)


def _valid(specs):
    return {
        spec.name: spec.lower if spec.lower == spec.upper else (spec.lower + spec.upper) / 2.0
        for spec in specs
    }


def _observation(head: DecisionHead = DecisionHead.ROUTE):
    return build_candidate_action_observation(
        head,
        _valid(CANDIDATE_FEATURE_SPECS),
        _valid(CONTEXT_FEATURE_SPECS),
        _valid(RICH_LOCAL_V1_ADDITIONAL_SPECS),
    )


def test_rich_local_v1_is_one_exact_contract_for_all_three_heads() -> None:
    observations = [_observation(head) for head in DecisionHead]

    assert len(G17_LOCAL_39_FEATURES) == 39
    assert len(RICH_LOCAL_V1_FEATURES) == 60
    assert {observation.head for observation in observations} == set(DecisionHead)
    assert all(observation.values == observations[0].values for observation in observations)
    assert tuple(observations[0].as_mapping()) == RICH_LOCAL_V1_FEATURES
    assert set(RICH_LOCAL_V1_NATIVE_PROVENANCE) == set(RICH_LOCAL_V1_FEATURES)
    assert "EventCandidateRecord.advertised_fault" in RICH_LOCAL_V1_NATIVE_PROVENANCE[
        "candidate_advertised_fault"
    ]
    assert observations[0].vector().shape == (60,)
    assert observations[0].vector(FeatureAblationGroup.G17_LOCAL_39).shape == (39,)
    assert np.array_equal(
        observations[0].vector(FeatureAblationGroup.G17_LOCAL_39),
        observations[0].vector()[:39],
    )


def test_four_ablation_groups_are_explicit_and_historical_f2_is_quarantined() -> None:
    contracts = FEATURE_GROUP_CONTRACTS
    assert set(contracts) == set(FeatureAblationGroup)
    assert contracts[FeatureAblationGroup.F2_OLD_22].dimension == 22
    assert contracts[FeatureAblationGroup.G17_LOCAL_39].dimension == 39
    assert contracts[FeatureAblationGroup.RICH_LOCAL_V1].dimension == 60
    assert contracts[FeatureAblationGroup.LEGACY_PLUS_RICH].dimension == 89
    assert contracts[FeatureAblationGroup.F2_OLD_22].strictly_local is False
    assert contracts[FeatureAblationGroup.F2_OLD_22].runtime_deployable is False
    assert contracts[FeatureAblationGroup.LEGACY_PLUS_RICH].ablation_only is True
    assert contracts[FeatureAblationGroup.RICH_LOCAL_V1].runtime_deployable is True
    assert len(LEGACY_PLUS_RICH_FEATURES) == len(set(LEGACY_PLUS_RICH_FEATURES))

    observation = _observation()
    f2 = {name: float(index) for index, name in enumerate(F2_OLD_22_FEATURES)}
    legacy = {name: float(index) for index, name in enumerate(LEGACY_29_FEATURES)}
    assert ablation_feature_vector("F2_OLD_22", observation, f2_old_22=f2).shape == (22,)
    combined = ablation_feature_vector(
        "LEGACY_PLUS_RICH",
        observation,
        legacy_29=legacy,
    )
    assert combined.shape == (89,)
    assert np.array_equal(combined[:29], np.arange(29, dtype=np.float64))
    assert np.array_equal(combined[29:], observation.vector())


def test_feature_builders_reject_ids_future_outcomes_and_schema_drift() -> None:
    assert not any(name.endswith("_id") for name in RICH_LOCAL_V1_FEATURES)
    assert not any(
        token in name
        for name in RICH_LOCAL_V1_FEATURES
        for token in ("future_", "outcome", "teacher", "global_reservation")
    )
    assert "candidate_local_availability_announcement" not in RICH_LOCAL_V1_FEATURES
    with pytest.raises(LocalFeatureError, match="NONLOCAL_OR_ID_FEATURE"):
        assert_deployable_g18_feature_names(("local_wait", "task_id"))
    with pytest.raises(LocalFeatureError, match="NONLOCAL_OR_ID_FEATURE"):
        assert_deployable_g18_feature_names(("current_node_scaled",))
    with pytest.raises(LocalFeatureError, match="NONLOCAL_OR_ID_FEATURE"):
        assert_deployable_g18_feature_names(("realized_outcome_seconds",))

    rich = _valid(RICH_LOCAL_V1_ADDITIONAL_SPECS)
    with pytest.raises(LocalFeatureError, match="FEATURES_EXTRA"):
        build_candidate_action_observation(
            DecisionHead.MERGE,
            _valid(CANDIDATE_FEATURE_SPECS),
            _valid(CONTEXT_FEATURE_SPECS),
            {**rich, "teacher_label": 1.0},
        )
    broken = dict(rich)
    broken["legal_action_count"] = 0.0
    with pytest.raises(LocalFeatureError, match="FEATURE_OUT_OF_BOUNDS"):
        build_candidate_action_observation(
            DecisionHead.SOURCE,
            _valid(CANDIDATE_FEATURE_SPECS),
            _valid(CONTEXT_FEATURE_SPECS),
            broken,
        )
    clipped = build_candidate_action_observation(
        DecisionHead.SOURCE,
        _valid(CANDIDATE_FEATURE_SPECS),
        _valid(CONTEXT_FEATURE_SPECS),
        broken,
        clip=True,
    )
    assert clipped.as_mapping()["legal_action_count"] == 1.0


def test_external_ablation_inputs_must_be_exact_not_whole_scientific_rows() -> None:
    observation = _observation()
    f2 = {name: 0.0 for name in F2_OLD_22_FEATURES}
    with pytest.raises(LocalFeatureError, match="FEATURES_EXTRA"):
        ablation_feature_vector(
            FeatureAblationGroup.F2_OLD_22,
            observation,
            f2_old_22={**f2, "completion_outcome": 10.0},
        )
    with pytest.raises(LocalFeatureError, match="FEATURES_REQUIRED"):
        ablation_feature_vector(FeatureAblationGroup.LEGACY_PLUS_RICH, observation)

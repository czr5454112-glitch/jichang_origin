from __future__ import annotations

import numpy as np

from czr005.g4irsf17 import (
    compare_state_aliasing,
    feature_ablation,
    feature_group_ablation,
    run_state_aliasing_audit,
)


def _aliased_panel() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    legacy_rows: list[list[float]] = []
    augmented_rows: list[list[float]] = []
    outcomes: list[float] = []
    for group in range(12):
        legacy_state = [float(group), float(group % 3)]
        for hidden, outcome in ((1.0, 2.0), (1.0, 2.0), (-1.0, -2.0), (-1.0, -2.0)):
            legacy_rows.append(legacy_state)
            augmented_rows.append([*legacy_state, hidden])
            outcomes.append(outcome)
    return (
        np.asarray(legacy_rows),
        np.asarray(augmented_rows),
        np.asarray(outcomes),
    )


def test_augmented_temporal_state_removes_opposite_outcome_aliasing() -> None:
    legacy, augmented, outcomes = _aliased_panel()
    audit = compare_state_aliasing(
        legacy,
        augmented,
        outcomes,
        neighbor_count=3,
        max_standardized_distance=0.20,
    )

    assert audit["legacy"]["coverage"] == 1.0
    assert audit["augmented"]["coverage"] == 1.0
    assert audit["legacy"]["sign_disagreement_rate"] > 0.5
    assert audit["augmented"]["sign_disagreement_rate"] == 0.0
    assert audit["augmented"]["conditional_variance"] == 0.0
    assert audit["improvement"]["conditional_variance_reduction"] > 0.0


def test_row_hook_reads_top_level_or_nested_features() -> None:
    legacy, augmented, outcomes = _aliased_panel()
    rows = []
    for index in range(len(outcomes)):
        row = {
            "legacy_a": legacy[index, 0],
            "features": {
                "legacy_b": legacy[index, 1],
                "local_temporal_signal": augmented[index, 2],
            },
            "system_utility": outcomes[index],
        }
        rows.append(row)
    result = run_state_aliasing_audit(
        rows,
        legacy_feature_names=("legacy_a", "legacy_b"),
        augmented_feature_names=("legacy_a", "legacy_b", "local_temporal_signal"),
        neighbor_count=3,
        max_standardized_distance=0.20,
    )
    assert result["schema"].endswith(".v1")
    assert result["outcome"] == "system_utility"
    assert result["improvement"]["sign_disagreement_reduction"] > 0.5


def test_feature_ablation_identifies_the_disambiguating_group() -> None:
    _, augmented, outcomes = _aliased_panel()
    rows = [
        {
            "legacy_a": augmented[index, 0],
            "legacy_b": augmented[index, 1],
            "local_temporal_signal": augmented[index, 2],
            "system_utility": outcomes[index],
        }
        for index in range(len(outcomes))
    ]
    ablation = feature_ablation(
        rows,
        feature_names=("legacy_a", "legacy_b", "local_temporal_signal"),
        feature_groups={"temporal": ("local_temporal_signal",)},
        neighbor_count=3,
        max_standardized_distance=0.20,
    )
    assert len(ablation) == 1
    assert ablation[0]["ablated_group"] == "temporal"
    assert ablation[0]["conditional_variance_delta_vs_full"] > 0.0
    assert ablation[0]["sign_disagreement_delta_vs_full"] > 0.5


def test_array_ablation_rejects_unknown_feature_group() -> None:
    _, augmented, outcomes = _aliased_panel()
    try:
        feature_group_ablation(
            augmented,
            outcomes,
            ("legacy_a", "legacy_b", "local_temporal_signal"),
            {"bad": ("not_a_feature",)},
        )
    except ValueError as error:
        assert "ABLATION_UNKNOWN_FEATURE" in str(error)
    else:
        raise AssertionError("unknown ablation feature was accepted")

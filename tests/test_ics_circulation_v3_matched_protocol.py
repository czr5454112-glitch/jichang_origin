import pytest

from scripts.experiments.ics_circulation_v3.run_matched_phase3 import load_selectors
from scripts.experiments.ics_circulation_v3.scene_configuration import CONFIGURATION_IDS, SceneSelector


def test_selector_bundle_metadata_is_not_treated_as_another_policy():
    fixed = SceneSelector("best_fixed", None, None, CONFIGURATION_IDS[0], CONFIGURATION_IDS[0], {})
    payload = {name: fixed.to_dict() for name in ("best_fixed", "stump", "validation_selected")}
    payload["validation_gate"] = {"mean_cost": 42, "selected": "best_fixed"}
    result = load_selectors(payload)
    assert set(result) == {"best_fixed", "stump", "validation_selected"}
    assert all(selector == fixed for selector in result.values())


def test_missing_selected_policy_cannot_fall_back_to_arbitrary_bundle_entry():
    with pytest.raises(ValueError, match="all three"):
        load_selectors({"validation_gate": {"selected": "best_fixed"}})

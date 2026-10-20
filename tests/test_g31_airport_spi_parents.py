import copy
import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_spi_parents as parents
from scripts.experiments.g31_ics_circulation import foundation_airport_calendar_forecast as calendar


def test_whole_group_shift_preserves_business_population_and_relative_times():
    data, parent, evidence = parents.make_parent(1101)
    original, _ = parents.historical_input(0, 22)
    assert len(data["jobs"]) == len(original["jobs"]) == 28506
    crosswalk = evidence["private_business_group_crosswalk"]
    assert len(evidence["group_counts"]) == 360
    assert data["trays"] == original["trays"]
    for before, after, membership in zip(original["jobs"], data["jobs"], crosswalk):
        assert before["business_bag_id"] == after["business_bag_id"] == membership["business_bag_id"]
        delta = evidence["group_shifts"][membership["flight_ref"]]
        assert after["arrival"] - before["arrival"] == pytest.approx(delta, abs=1e-8)
        assert after["deadline"] - before["deadline"] == pytest.approx(delta, abs=1e-8)
        if before["storage_node"] >= 0:
            assert after["storage_release_at"] - before["storage_release_at"] == pytest.approx(delta, abs=1e-8)
        else:
            assert after["storage_release_at"] == before["storage_release_at"]
    assert parents.validate_public_parent(parent)["parent_seed"] == 1101
    with pytest.raises(ValueError, match="test_locked"):
        parents.make_parent(1301)


def test_new_inference_plan_keeps_original_training_parameter_identity():
    _, parent, _ = parents.make_parent(1101)
    binding = calendar.load_calendar_binding(parent)
    checkpoint, manifest = calendar._validate_binding(binding)
    assert manifest["inference_plan_domain"]["target_plan_is_new_inference_schedule"]
    assert manifest["source_model_id"] == calendar.SOURCE_MODEL_ID
    assert manifest["inference_plan_domain"]["training_parameters_unchanged"]
    changed = copy.deepcopy(binding)
    changed["absolute_plan_template"]["entries"][0]["scheduled_event_at"] += 600
    changed["producer_manifest"]["target_plan_template_sha256"] = calendar.digest(changed["absolute_plan_template"])
    changed["binding_sha256"] = calendar.digest({k: v for k, v in changed.items() if k != "binding_sha256"})
    with pytest.raises(ValueError, match="inverse_binding"):
        calendar._validate_binding(changed)


def test_predeclared_plan_does_not_require_future_actual_counts():
    _, parent, _ = parents.make_parent(1101)
    binding = calendar.load_calendar_binding(parent)
    prediction = calendar.predict(binding, now=7200., owner="owner:standard", horizon_seconds=1800)
    assert prediction["calendar_provenance"]["observed_future_counts_used"] is False
    assert prediction["calendar_provenance"]["actual_callback_consumption"] is False

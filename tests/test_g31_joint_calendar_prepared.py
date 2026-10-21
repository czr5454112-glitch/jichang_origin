"""Pure joint-calendar integration; fake receipts are fixtures, not run evidence."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_joint_calendar as calendar
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_calendar_prepared as prepared
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_parents as parents
from scripts.experiments.g31_ics_circulation import foundation_airport_loader_mapping as mapping
from scripts.experiments.g31_ics_circulation import foundation_airport_calendar_forecast as old_calendar
from test_g31_circulation_calendar_prepared import observation


@pytest.fixture(scope="module")
def inputs():
    parent = parents._expected_registration(2101, 0)
    binding = calendar.load_calendar_binding(parent)
    receipts = calendar.record_controller_preload(binding, SimpleNamespace(physical_time=0.), owners=["A", "B"])
    return parent, binding, receipts


def fit(inputs, *, available_offset=-1.):
    parent = inputs[0]
    start = parent["calendar_start_epoch_seconds"]
    rows = [{"label_id": "fixture-entry-"+str(i), "parent_id": "prior_train_parent", "split": "train",
        "region": "legacy_start_0", "loader": 0, "observed_at_epoch_seconds": start-100.-i,
        "provenance_kind": "observed_entry"} for i in range(8)]
    return mapping.fit_loader_mapping(rows, train_parent_ids=["prior_train_parent"],
        training_labels_closed_at_epoch_seconds=start-50., model_available_at_epoch_seconds=start+available_offset,
        input_domain={"split": "train", "labels_kind": "observed_entry_labels", "uses_future_crosswalk": False,
                      "evidence_scope": "unit_test_fixture_not_native_training"})


@pytest.mark.parametrize("now,owner", [(0., "A"), (7200., "A"), (7260.25, "B"), (57600., "B")])
def test_default_v2_prepared_is_exactly_equal_to_unprepared_joint_calendar(inputs, now, owner):
    parent, binding, receipts = inputs
    provider = prepared.prepare_forecast_provider(binding, receipts)
    obs = observation(now, owner)
    expected = calendar.make_forecast_evidence(binding, obs, plan_receipt=receipts[owner])
    actual = provider(observation=obs, parent=parent)
    assert actual == expected
    assert actual["forecast"]["airport_mapping_version"] == calendar.airport.MAPPING_VERSION
    assert actual["forecast"]["calendar_provenance"]["observed_future_counts_used"] is False


def test_joint_parent_and_training_model_domain_are_separate_from_legacy(inputs):
    parent, binding, receipts = inputs
    checkpoint, manifest = calendar._validate_binding(binding)
    assert parent["plan_family_id"] == parents.FAMILY
    assert manifest["inference_plan_domain"]["target_plan_is_new_inference_schedule"]
    assert manifest["source_model_id"] == calendar.SOURCE_MODEL_ID
    assert manifest["inference_plan_domain"]["training_parameters_unchanged"]
    assert checkpoint["static_plan_sha256"] == manifest["original_model_static_plan_sha256"]
    with pytest.raises(ValueError):
        old_calendar.load_calendar_binding(parent)
    with pytest.raises(ValueError, match="test_locked"):
        parents.make_parent(2301)
    revised = parents._expected_registration(2101, 1)
    assert revised["plan_group_shifts_sha256"] == parent["plan_group_shifts_sha256"]
    assert revised["calendar_start_epoch_seconds"] == parent["calendar_start_epoch_seconds"]+20*86400.
    assert revised["split"] == parent["split"] == "train"


def test_trained_mapping_uses_identical_regional_B1_and_preserves_mass(inputs):
    parent, binding, receipts = inputs
    trained = fit(inputs)
    obs = observation()
    provider = prepared.prepare_forecast_provider(binding, receipts, loader_mapping=trained)
    actual = provider(observation=obs, parent=parent)
    start = parent["calendar_start_epoch_seconds"]
    plan = copy.deepcopy(binding["absolute_plan_template"])
    plan.update(owner_scope=obs["owner_id"], received_at=start)
    regional = calendar.arrays.predict(plan, binding["checkpoint"], now=start+obs["now"], owner=obs["owner_id"],
                                      observed_counts=None, horizon_seconds=1800)
    expected = mapping.project_forecast(regional, trained, now=start+obs["now"], owner=obs["owner_id"])
    for key in ("new_demand_mean_by_region", "missing_mask_by_region", "uncertainty_by_region", "projection_audit"):
        assert actual["forecast"][key] == expected[key]
    old = prepared.prepare_forecast_provider(binding, receipts)(observation=obs, parent=parent)
    assert actual["forecast"]["source_regional_forecast_sha256"] == old["forecast"]["source_regional_forecast_sha256"]
    assert actual["forecast"]["airport_mapping_sha256"] == trained["sha256"]
    assert actual["forecast"]["new_demand_mean_by_region"] != old["forecast"]["new_demand_mean_by_region"]
    audit = actual["forecast"]["projection_audit"]
    assert audit["mapped_known_mass_per_bin"] == pytest.approx(audit["raw_known_mass_per_bin"])
    assert all(value is None for value in actual["forecast"]["uncertainty_by_region"].values())


def test_trained_mapping_availability_checked_at_each_callback(inputs):
    parent, binding, receipts = inputs
    provider = prepared.prepare_forecast_provider(binding, receipts, loader_mapping=fit(inputs, available_offset=8000.))
    with pytest.raises(ValueError, match="not_yet_available"):
        provider(observation=observation(7200.), parent=parent)
    assert provider(observation=observation(8100.), parent=parent)["forecast"]["forecast_origin"] == 8100.


@pytest.mark.parametrize("mutation", ["owner", "parent", "future_job", "past_clock"])
def test_trained_mapping_does_not_bypass_current_receipt_or_public_boundary(inputs, mutation):
    parent, binding, receipts = inputs
    provider = prepared.prepare_forecast_provider(binding, receipts, loader_mapping=fit(inputs))
    obs, actual_parent = observation(), copy.deepcopy(parent)
    if mutation == "owner":
        obs["owner_id"] = "unknown_owner"
    elif mutation == "parent":
        actual_parent = parents._expected_registration(2102, 0)
    elif mutation == "future_job":
        obs["jobs"] = [{"business_bag_id": "future", "arrival": 7201., "status": "waiting"}]
    else:
        obs["now"] = -1.
    with pytest.raises(ValueError):
        provider(observation=obs, parent=actual_parent)


def test_trained_inputs_and_outputs_are_detached(inputs):
    parent, binding, receipts = copy.deepcopy(inputs)
    trained = fit(inputs)
    provider = prepared.prepare_forecast_provider(binding, receipts, loader_mapping=trained)
    expected = provider(observation=observation(), parent=parent)
    trained["regions"]["legacy_start_0"]["weights"][0] = 999.
    binding["checkpoint"]["parameters"].clear()
    receipts["A"]["model_id"] = "wrong"
    first = provider(observation=observation(), parent=parent)
    first["forecast"]["new_demand_mean_by_region"].clear()
    assert provider(observation=observation(), parent=parent) == expected


def test_partial_missing_region_bin_propagates_through_prepared_trained_path(inputs, monkeypatch):
    parent, binding, receipts = inputs
    original = prepared._regional
    def one_missing_bin(*args, **kwargs):
        value = original(*args, **kwargs)
        value["new_demand_mean_by_region"]["legacy_start_0"][0] = None
        value["missing_mask_by_region"]["legacy_start_0"] = [True]+[False]*29
        return value
    monkeypatch.setattr(prepared, "_regional", one_missing_bin)
    provider = prepared.prepare_forecast_provider(binding, receipts, loader_mapping=fit(inputs))
    forecast = provider(observation=observation(), parent=parent)["forecast"]
    assert forecast["new_demand_mean_by_region"]["airport_node_0"][0] is None
    assert forecast["new_demand_mean_by_region"]["airport_node_0"][1] is not None
    assert not any(forecast["missing_mask_by_region"]["airport_node_134"])
    assert forecast["projection_audit"]["missing_mass_imputed_as_zero"] is False


def test_prepared_provider_rejects_owner_reassigned_startup_receipt(inputs):
    parent, binding, receipts = copy.deepcopy(inputs)
    receipts["A"]["owner_id"] = "B"
    receipts["A"]["receipt_sha256"] = calendar.public_digest({k: v for k, v in receipts["A"].items() if k != "receipt_sha256"})
    with pytest.raises(ValueError, match="owner_parent_model"):
        prepared.prepare_forecast_provider(binding, receipts, loader_mapping=fit(inputs))

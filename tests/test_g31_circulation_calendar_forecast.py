"""Pure calendar/provenance tests; no native constructors or training jobs."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_calendar_forecast as calendar
from scripts.experiments.g31_ics_circulation import foundation_flight_forecaster_arrays as arrays
from scripts.experiments.g31_ics_circulation import foundation_action_value as value

OWNER = "owner:system_domestic"


def parent(seed=701):
    day = datetime.fromisoformat(calendar.SOURCE_CALENDAR_START) + timedelta(days=calendar.PARENT_SEEDS.index(seed) + 1)
    return dict(parent_seed=seed, split="train" if seed < 800 else "dev" if seed < 900 else "test",
        parent_group=f"conditional_timing_parent_{seed}", synthetic=True,
        common_historical_template_sha256=calendar.TEMPLATE_SHA256,
        sampling="sha256(seed:business_identity), uniform[-120,120], clip_zero",
        calendar_start=day.isoformat(), calendar_start_epoch_seconds=day.timestamp())


@pytest.fixture(scope="module")
def binding():
    return calendar.load_calendar_binding(parent())


def rehash(binding):
    binding["binding_sha256"] = calendar.digest({k: v for k, v in binding.items() if k != "binding_sha256"})
    return binding


def test_prior_day_model_is_available_at_target_early_clock_with_unchanged_parameters(binding):
    before = {name: hashlib.sha256((calendar.SOURCE / name).read_bytes()).hexdigest()
              for name in calendar.PINNED_FILES}
    forecast = calendar.predict(binding, now=7200., owner=OWNER)
    assert forecast["forecast_origin"] == 7200.
    assert forecast["absolute_bin_edges"] == list(np.arange(7200., 9001., 60.))
    assert forecast["remaining_support_until"] == 9000.
    assert forecast["information_cutoffs"] == {
        "training_labels_closed_at": -43200., "model_frozen_at": -43200.,
        "plan_received_at": 0., "observed_arrivals_through": None}
    assert not forecast["observed_count_update"] and not forecast["predicted_inventory_is_actual"]
    assert forecast["projection_audit"]["mean_mass_conserved"]
    assert "airport_node_92" not in forecast["new_demand_mean_by_region"]
    assert forecast["calendar_provenance"]["parameter_reuse_not_new_fit"]
    assert before == {name: hashlib.sha256((calendar.SOURCE / name).read_bytes()).hexdigest()
                      for name in calendar.PINNED_FILES}


def test_parameter_reuse_has_distinct_model_and_source_receipt_identity(binding):
    manifest = binding["producer_manifest"]
    original = json.loads((calendar.SOURCE / "flight_forecaster_checkpoint.json").read_text())
    assert binding["checkpoint"]["parameters"] == original["parameters"]
    assert manifest["model_id"] != original["model_sha256"]
    assert manifest["source_model_id"] == original["model_sha256"]
    assert manifest["original_checkpoint_sha256"] == calendar.PINNED_FILES["flight_forecaster_checkpoint.json"]
    assert manifest["original_training_receipt_sha256"] == calendar.PINNED_FILES["receipt.json"]
    assert manifest["new_fit_performed"] is False
    assert manifest["synthetic_common_template_limits"]["source_and_target_share_historical_template"]
    assert not manifest["synthetic_common_template_limits"]["independent_real_airport_days"]


def test_absolute_and_original_legal_late_forecasts_have_equivalent_mass(binding):
    original = json.loads((calendar.SOURCE / "flight_forecaster_checkpoint.json").read_text())
    plan = json.loads((calendar.SOURCE / "public/static_flight_plan.json").read_text())
    plan["owner_scope"] = OWNER
    old = arrays.predict(plan, original, now=57600., owner=OWNER, observed_counts=None)
    expected = calendar.airport.project_forecast(old, binding["mapping"], now=57600., owner=OWNER)
    actual = calendar.predict(binding, now=57600., owner=OWNER)
    for region in actual["new_demand_mean_by_region"]:
        np.testing.assert_allclose(actual["new_demand_mean_by_region"][region],
                                   expected["new_demand_mean_by_region"][region], rtol=1e-10, atol=1e-9)
    with pytest.raises(ValueError, match="model_not_yet_frozen"):
        arrays.predict(plan, original, now=7200., owner=OWNER, observed_counts=None)


def test_plan_keeps_missing_publication_and_shifts_STD_and_receipt(binding):
    original = json.loads((calendar.SOURCE / "public/static_flight_plan.json").read_text())
    projected = binding["absolute_plan_template"]
    start = parent()["calendar_start_epoch_seconds"]
    assert projected["published_at"] is None
    assert projected["received_at"] == start
    assert projected["validity_policy"] == original["validity_policy"]
    assert len(projected["entries"]) == len(original["entries"])
    for old, new in zip(original["entries"], projected["entries"], strict=True):
        assert new["scheduled_event_at"] == old["scheduled_event_at"] + start
        assert "available_bag_count_estimate" not in new


def test_forecast_evidence_binds_public_current_and_absolute_provenance(binding):
    observation = {"now": 7200., "owner_id": OWNER, "trays": [], "node_contracts": []}
    evidence = calendar.make_forecast_evidence(binding, observation)
    manifest = evidence["producer_manifest"]
    assert evidence["schema"] == "g31.foundation.airport_pair_absolute_forecast.v1"
    assert evidence["public_state_sha256"] == calendar.public_digest(observation)
    assert evidence["forecast_sha256"] == calendar.public_digest(evidence["forecast"])
    assert evidence["provenance_sha256"] == calendar.public_digest(manifest)
    assert evidence["observed_at_epoch_seconds"] == parent()["calendar_start_epoch_seconds"] + 7200.
    assert evidence["training_labels_closed_at_epoch_seconds"] <= evidence["model_available_at_epoch_seconds"] < evidence["observed_at_epoch_seconds"]
    assert evidence["plan_received_at_epoch_seconds"] is None
    assert evidence["forecast_provenance"] == "offline_reconstruction_from_predeclared_static_schedule"
    assert evidence["actual_callback_consumption"] is False
    assert manifest["source_calendar_start_epoch_seconds"] + 43200. == evidence["model_available_at_epoch_seconds"]
    assert value.number(evidence["forecast"]["information_cutoffs"]["model_frozen_at"]) < 0


def test_separate_controller_receipt_required_for_actual_callback_provenance(binding):
    # Pure unit fixture; this test is never evidence of real native consumption.
    receipts = calendar.record_controller_preload(binding, SimpleNamespace(physical_time=0.), owners=[OWNER])
    observation = {"now": 7200., "owner_id": OWNER, "comment": "实际公开观察"}
    evidence = calendar.make_forecast_evidence(binding, observation, plan_receipt=receipts[OWNER])
    assert evidence["forecast_provenance"] == "actual_callback_received"
    assert evidence["actual_callback_consumption"] is True
    assert evidence["plan_received_at_epoch_seconds"] == parent()["calendar_start_epoch_seconds"]
    assert evidence["public_state_sha256"] == calendar.public_digest(observation)
    assert evidence["public_state_sha256"] != calendar.digest(observation)
    wrong = deepcopy(receipts[OWNER])
    wrong["owner_id"] = "another_owner"
    wrong["receipt_sha256"] = calendar.public_digest({k: v for k, v in wrong.items() if k != "receipt_sha256"})
    with pytest.raises(ValueError, match="plan_receipt_owner_parent_model"):
        calendar.make_forecast_evidence(binding, observation, plan_receipt=wrong)
    with pytest.raises(ValueError, match="preload_requires_actual_initial_session_clock"):
        calendar.record_controller_preload(binding, SimpleNamespace(physical_time=7200.), owners=[OWNER])


@pytest.mark.parametrize("change,reason", [
    ({"synthetic": False}, "registered_synthetic_parent"),
    ({"calendar_start": "2026-09-01T00:00:00+08:00"}, "registered_target_calendar"),
    ({"calendar_start_epoch_seconds": 0.}, "calendar_epoch_consistency"),
    ({"split": "test"}, "parent_lineage"),
    ({"common_historical_template_sha256": "changed"}, "common_template_binding"),
])
def test_parent_renaming_or_clock_edits_do_not_bypass_source_calendar(change, reason):
    with pytest.raises(ValueError, match=reason):
        calendar.load_calendar_binding(parent() | change)


def test_refuses_rehashed_later_training_dates(binding):
    wrong = deepcopy(binding)
    wrong["producer_manifest"]["source_calendar_start_epoch_seconds"] += 86400 * 20
    with pytest.raises(ValueError, match="fixed_source_calendar"):
        calendar.predict(rehash(wrong), now=7200., owner=OWNER)


def test_refuses_rehashed_changed_source_parameters(binding):
    wrong = deepcopy(binding)
    wrong["checkpoint"]["parameters"]["legacy_start_0"]["shape"] += 1
    wrong["checkpoint"]["model_sha256"] = calendar.digest({k: v for k, v in wrong["checkpoint"].items()
                                                            if k != "model_sha256"})
    wrong["producer_manifest"]["model_id"] = wrong["checkpoint"]["model_sha256"]
    wrong["producer_manifest"]["parameter_sha256"] = calendar.digest(wrong["checkpoint"]["parameters"])
    with pytest.raises(ValueError, match="inverse_binding_must_recover_frozen_source_model"):
        calendar.predict(rehash(wrong), now=7200., owner=OWNER)


def test_refuses_rehashed_future_plan_change_or_observed_count_enrichment(binding):
    wrong = deepcopy(binding)
    wrong["absolute_plan_template"]["entries"][0]["scheduled_event_at"] += 60
    wrong["producer_manifest"]["target_plan_template_sha256"] = calendar.digest(wrong["absolute_plan_template"])
    with pytest.raises(ValueError, match="inverse_binding_must_recover_frozen_public_plan"):
        calendar.predict(rehash(wrong), now=7200., owner=OWNER)
    with pytest.raises(TypeError, match="observed_counts"):
        calendar.predict(binding, now=7200., owner=OWNER, observed_counts={})


def test_next_target_day_keeps_same_parameters_and_earlier_source_clock():
    first, last = calendar.load_calendar_binding(parent()), calendar.load_calendar_binding(parent(902))
    assert first["checkpoint"] == last["checkpoint"]
    assert first["binding_sha256"] != last["binding_sha256"]
    forecast = calendar.predict(last, now=7200., owner=OWNER)
    assert forecast["information_cutoffs"]["model_frozen_at"] == 43200. - 6 * 86400.

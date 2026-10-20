"""Prepared calendar pure equivalence and causality checks; no native starts."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_calendar_forecast as calendar
from scripts.experiments.g31_ics_circulation import foundation_airport_calendar_prepared as prepared
from scripts.experiments.g31_ics_circulation.foundation_airport_pair_ranker import _forecast
from test_g31_circulation_calendar_forecast import parent


def observation(now=7200., owner="A"):
    return {"schema": "g31.owner_protocol_observation.v1", "observation_scope": "controller_policy",
        "now": now, "owner_id": owner, "node_contracts": [{"node": 0, "resource_owner": "A"}],
        "trays": [], "jobs": [], "client_transfer_ledger": [], "transfers": []}


@pytest.fixture(scope="module")
def inputs():
    binding = calendar.load_calendar_binding(parent())
    # Fixture only: this records no native session or live callback receipt.
    receipts = calendar.record_controller_preload(binding, SimpleNamespace(physical_time=0.), owners=["A", "B"])
    return binding, receipts


@pytest.mark.parametrize("now,owner", [(0., "A"), (7200., "A"), (7200.5, "B"), (57600., "B")])
def test_prepared_matches_original_entire_evidence_and_ranker_boundary(inputs, now, owner):
    binding, receipts = inputs
    provider = prepared.prepare_forecast_provider(binding, receipts)
    obs = observation(now, owner)
    expected = calendar.make_forecast_evidence(binding, obs, plan_receipt=receipts[owner])
    actual = provider(observation=obs, parent=parent())
    assert actual == expected
    assert _forecast({"observation": obs, "parent": parent(), "forecast_evidence": actual}) == actual["forecast"]


def test_static_inputs_detached_outputs_detached_and_clock_fresh(inputs):
    binding, receipts = copy.deepcopy(inputs)
    provider = prepared.prepare_forecast_provider(binding, receipts)
    first = provider(observation=observation(), parent=parent())
    expected = copy.deepcopy(first)
    binding["checkpoint"]["parameters"].clear()
    receipts["A"]["model_id"] = "mutated"
    first["producer_manifest"].clear()
    first["forecast"]["new_demand_mean_by_region"].clear()
    assert provider(observation=observation(), parent=parent()) == expected
    later = provider(observation=observation(7260.), parent=parent())
    assert later["observed_at_epoch_seconds"] == expected["observed_at_epoch_seconds"]+60
    assert later["forecast"]["forecast_origin"] == 7260.
    assert later["forecast_sha256"] != expected["forecast_sha256"]


def test_static_validators_not_repeated_after_prepare(inputs, monkeypatch):
    binding, receipts = inputs
    provider = prepared.prepare_forecast_provider(binding, receipts)
    def forbidden(*args, **kwargs):
        raise AssertionError("static validation repeated")
    monkeypatch.setattr(calendar, "_validate_binding", forbidden)
    monkeypatch.setattr(calendar.original, "validate_checkpoint", forbidden)
    monkeypatch.setattr(calendar.contexts, "adapt_context", forbidden)
    assert provider(observation=observation(), parent=parent())["actual_callback_consumption"] is True


@pytest.mark.parametrize("mutation", ["future_job", "owner", "parent", "clock"])
def test_current_validation_not_bypassed(inputs, mutation):
    provider = prepared.prepare_forecast_provider(*inputs)
    obs, current_parent = observation(), parent()
    if mutation == "future_job":
        obs["jobs"] = [{"business_bag_id": "future", "arrival": 7201., "status": "waiting"}]
    elif mutation == "owner":
        obs["owner_id"] = "unregistered"
    elif mutation == "parent":
        current_parent = parent(702)
    else:
        obs["now"] = 86401.
    with pytest.raises(ValueError):
        provider(observation=obs, parent=current_parent)


def test_no_offline_reconstruction_or_reassigned_receipt(inputs):
    binding, receipts = copy.deepcopy(inputs)
    with pytest.raises(ValueError, match="actual_owner_receipts"):
        prepared.prepare_forecast_provider(binding, {})
    receipts["A"]["owner_id"] = "B"
    with pytest.raises(ValueError, match="actual_plan_receipt"):
        prepared.prepare_forecast_provider(binding, receipts)


def test_prepared_numpy_parameters_cannot_be_made_writeable():
    values = prepared._readonly_array([0., 1.])
    with pytest.raises(ValueError):
        values.setflags(write=True)

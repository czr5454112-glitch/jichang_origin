"""Pure demand representation and prepared B1 checks; no native starts."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_forecast as demand
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_calendar as calendar
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_calendar_prepared as prepared
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_parents as parents
from test_g31_circulation_calendar_prepared import observation


def forecast():
    return {"forecast_origin": 120.25, "owner_scope": "A", "native_execution_authority": False,
        "bin_edges_seconds": demand.bin_edges("60"),
        "new_demand_mean_by_region": {"airport_node_0": [float(i+1) for i in range(30)]},
        "missing_mask_by_region": {"airport_node_0": False},
        "uncertainty_by_region": {"airport_node_0": {"lower": [0.]*30, "upper": [99.]*30}},
        "window_summaries_by_region": {"airport_node_0": {"60": {"mean": 9999.}}}}


@pytest.mark.parametrize("mode,nbins", [("60", 30), ("300", 6), ("600", 3), ("near_fine", 10)])
def test_representation_conserves_mass_and_returns_only_visible_bin_features(mode, nbins):
    source = forecast()
    result = demand.rebin_forecast(source, bin_edges_seconds=demand.bin_edges(mode))
    assert len(result["new_demand_mean_by_region"]["airport_node_0"]) == nbins
    assert sum(result["new_demand_mean_by_region"]["airport_node_0"]) == pytest.approx(465.)
    assert result["absolute_bin_edges"][0] == 120.25
    assert result["absolute_bin_edges"][-1] == 1920.25
    assert result["uncertainty_by_region"]["airport_node_0"] is None
    for window in (300, 900, 1800):
        summary = result["window_summaries_by_region"]["airport_node_0"][str(window)]
        assert summary["mean"] == demand.expected_arrivals(result, 120.25, 120.25+window, owner="A", station=0)
        assert summary["variance"] is None
    assert source == forecast()


def test_coarse_interval_uses_coarse_uniform_mass_without_hidden_fine_information():
    source = forecast()
    result = demand.rebin_forecast(source, bin_edges_seconds=demand.bin_edges("600"))
    # First 60 seconds contained one arrival; the coarse actor sees 55/600 per second.
    assert demand.expected_arrivals(source, 120.25, 180.25, owner="A", station=0) == 1.
    assert demand.expected_arrivals(result, 120.25, 180.25, owner="A", station=0) == 5.5
    assert result["window_summaries_by_region"]["airport_node_0"]["60"]["mean"] == 5.5


def test_explicit_partial_edges_and_unknown_coverage_are_not_rounded_or_zero_filled():
    edges = demand.bin_edges("300", horizon_seconds=1000., first_bin_seconds=90.)
    assert edges == [0., 90., 390., 690., 990., 1000.]
    source = forecast()
    result = demand.rebin_forecast(source, bin_edges_seconds=[0., 37.5, 555.5, 1793., 1800.])
    assert sum(result["new_demand_mean_by_region"]["airport_node_0"]) == pytest.approx(465.)
    assert demand.expected_arrivals(result, 120.25, 120.25, owner="A", station=0) == 0.
    assert demand.expected_arrivals(result, 120.24, 130., owner="A", station=0) is None
    assert demand.expected_arrivals(result, 120.25, 2000., owner="A", station=0) is None
    with pytest.raises(ValueError, match="owner_scope"):
        demand.expected_arrivals(result, 120.25, 130., owner="B", station=0)


def test_partial_missing_bin_does_not_poison_unrelated_bins_or_become_zero():
    source = forecast()
    source["new_demand_mean_by_region"]["airport_node_0"][0] = None
    source["missing_mask_by_region"]["airport_node_0"] = [True]+[False]*29
    result = demand.rebin_forecast(source, bin_edges_seconds=demand.bin_edges("300"))
    assert result["new_demand_mean_by_region"]["airport_node_0"][0] is None
    assert result["new_demand_mean_by_region"]["airport_node_0"][1] == 40.
    assert demand.expected_arrivals(result, 120.25, 420.25, owner="A", station=0) is None
    assert demand.expected_arrivals(result, 420.25, 720.25, owner="A", station=0) == 40.


@pytest.mark.parametrize("edges", [[0, 300, 300, 1800], [1, 1800], [0, float('nan'), 1800], [0, 900]])
def test_invalid_or_changed_horizon_rejected(edges):
    with pytest.raises(ValueError):
        demand.rebin_forecast(forecast(), bin_edges_seconds=edges)


def test_prepared_custom_CDF_grid_and_partial_horizon_keep_default_exact():
    parent = parents._expected_registration(2101, 0)
    binding = calendar.load_calendar_binding(parent)
    receipts = calendar.record_controller_preload(binding, SimpleNamespace(physical_time=0.), owners=["A"])
    obs = observation(7200.25)
    provider = prepared.prepare_forecast_provider(binding, receipts)
    original = calendar.make_forecast_evidence(binding, obs, plan_receipt=receipts["A"])
    assert provider(observation=obs, parent=parent) == original
    fine = original["forecast"]
    coarse = provider(observation=obs, parent=parent, bin_edges_seconds=demand.bin_edges("300"))["forecast"]
    for station in fine["new_demand_mean_by_region"]:
        assert sum(fine["new_demand_mean_by_region"][station]) == pytest.approx(sum(coarse["new_demand_mean_by_region"][station]))
    partial = prepared.prepare_forecast_provider(binding, receipts, horizon_seconds=1001,
        bin_edges_seconds=demand.bin_edges("300", horizon_seconds=1001))
    result = partial(observation=obs, parent=parent)["forecast"]
    assert result["bin_edges_seconds"] == [0., 300., 600., 900., 1001.]
    assert result["remaining_support_until"] == 8201.25


def test_shared_Gamma_intensity_cumulative_variance_is_not_sum_of_marginals():
    import json
    import numpy as np
    template = {"new_demand_mean_by_region": {}, "uncertainty_by_region": {},
                "missing_mask_by_region": {}, "window_summaries_by_region": {}}
    context = SimpleNamespace(entries=[SimpleNamespace(plan_status="scheduled", scheduled_event_at=300.)])
    parameters = [("region", 4., 1., np.asarray([-300., 0.]), np.asarray([0., 1.]))]
    result = prepared._regional(json.dumps(template).encode(), parameters, context,
        np.asarray([0., 150., 300.]), np.asarray(calendar.original.WINDOWS), 0., 300.)
    # One flight: both bins share uncertain intensity. The model's cumulative
    # interval includes the positive covariance term that marginals omit.
    assert sum(result["uncertainty_by_region"]["region"]["variance"]) == 6.
    assert result["window_summaries_by_region"]["region"]["300"]["variance"] == 8.
    assert demand.rebin_forecast(forecast(), bin_edges_seconds=[0., 1800.])["uncertainty_by_region"]["airport_node_0"] is None

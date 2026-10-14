from dataclasses import replace

import numpy as np
import pytest

from scripts.experiments.ics_circulation_v3.feedback_scenarios import feedback_scene
from scripts.experiments.ics_circulation_v3.model import Bag, Leg, Reservation, RouteCandidate, Tray
from scripts.experiments.ics_circulation_v3.nonlinear_learning import (
    FULL_FEATURE_NAMES, PHYSICAL_FEATURE_NAMES, MLPConfig, MLPValueModel)
from scripts.experiments.ics_circulation_v3.role_features import physical_features


def arrived_state():
    state = feedback_scene(shared_travel=2).initial.clone()
    state.bags = {"b": Bag("b", "B", "C", 0, 20)}
    state.trays = {"t": Tray("t", "C", "loaded", "b")}
    state.load_times = {"b": 0}
    stop = RouteCandidate("stop", "b", "t", (), 1, 1, 0, "stop", True)
    loop = RouteCandidate("loop", "b", "t",
                          (Leg("CS", 0, 1), Leg("SX", 1, 3), Leg("XG", 3, 5), Leg("GC", 5, 7)),
                          8, 8, 0, "stop")
    return state, stop, loop


def test_arrival_and_retained_suffix_are_distinguished_by_executable_prefix():
    state, stop, loop = arrived_state()
    unload = physical_features(state, stop, 20)
    detour = physical_features(state, loop, 20)
    assert set(unload) == set(PHYSICAL_FEATURE_NAMES)
    assert unload["current_at_destination"] == detour["current_at_destination"] == 1
    assert unload["prefix_completes_delivery"] == 1
    assert detour["prefix_completes_delivery"] == detour["prefix_end_at_destination"] == 0
    assert unload["prefix_remaining_shortest_ticks"] == 0
    assert detour["prefix_remaining_shortest_ticks"] > 0
    assert detour["prefix_travel_ticks"] == 1  # CS only; later suffix is conditional.
    assert physical_features(state, loop, 20, route_mode="whole_route")["prefix_completes_delivery"] == 1


def test_occupancy_uses_other_trays_half_open_prefix_slots_and_capacity():
    state, _, loop = arrived_state()
    edges = dict(state.network.edges)
    edges["CS"] = replace(edges["CS"], capacity=2)
    state.network = replace(state.network, edges=edges)
    state.reservations = (
        Reservation("edge:CS", 0, 1, "other"),
        Reservation("edge:CS", 0, 1, "other"),  # identity, not row count
        Reservation("edge:CS", 1, 2, "later"),
        Reservation("edge:SX", 1, 3, "conditional_suffix_other"),
        Reservation("node:S", 1, 3, "other"),
        Reservation("node:S", 0, 1, "already_departed"),
        Reservation("node:S", 1, 4, "t"),
    )
    values = physical_features(state, loop, 20)
    assert values["prefix_edge_occupied_fraction"] == .5
    assert values["prefix_end_headroom"] == 1


def training_rows():
    state, stop, loop = arrived_state()
    features = [physical_features(state, c, 20) for c in (stop, loop)]
    return [{"source_group": "g", "split": "train", "is_baseline": i == 0,
             "features": f, "cost_mean": i * 3., "delta_mean": i * 3.,
             "timed_delta": f["timed_analytic_absolute"] - features[0]["timed_analytic_absolute"]}
            for i, f in enumerate(features)]


def test_explicit_schema_serializes_and_old_defaults_remain_exactly_23_features():
    rows = training_rows()
    config = MLPConfig(epochs=8, seed=17)
    old = MLPValueModel.fit(rows, "paired_direct", config)
    selected = MLPValueModel.fit([
        dict(r, features={k: r["features"][k] for k in FULL_FEATURE_NAMES}) for r in rows],
        "paired_direct", config)
    assert old.to_dict() == selected.to_dict()
    assert old.parameter_count == 801 and old.feature_names == FULL_FEATURE_NAMES
    new = MLPValueModel.fit(rows, "paired_direct", config, feature_names=PHYSICAL_FEATURE_NAMES)
    assert new.parameter_count == 1057
    restored = MLPValueModel.from_dict(new.to_dict())
    assert restored.to_dict() == new.to_dict()
    assert new.score_features(rows[0]["features"], rows[0]["features"]) == 0
    with pytest.raises(ValueError, match="schema mismatch"):
        new.predict_value({k: rows[0]["features"][k] for k in FULL_FEATURE_NAMES})


def test_new_schema_preserves_paired_direct_residual_equivalence_when_analytic_zero():
    rows = training_rows()
    for row in rows:
        row["features"]["timed_analytic_absolute"] = 0.
        row["timed_delta"] = 0.
    config = MLPConfig(epochs=8, seed=43)
    a = MLPValueModel.fit(rows, "paired_direct", config, feature_names=PHYSICAL_FEATURE_NAMES)
    b = MLPValueModel.fit(rows, "residual", config, feature_names=PHYSICAL_FEATURE_NAMES)
    for name in a.parameters:
        np.testing.assert_array_equal(a.parameters[name], b.parameters[name])


def test_unpublished_information_is_rejected_by_feature_gate():
    state, _, loop = arrived_state()
    future = replace(feedback_scene().forecasts[0], published_at=1)
    with pytest.raises(ValueError, match="Unpublished"):
        physical_features(state, loop, 20, (future,))

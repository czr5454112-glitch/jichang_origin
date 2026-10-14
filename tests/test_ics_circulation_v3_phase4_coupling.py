from dataclasses import replace
from pathlib import Path
import json

import pytest

from scripts.experiments.ics_circulation_v3 import phase4_control as control
from scripts.experiments.ics_circulation_v3.phase4_coupled_scenarios import coupling_scene
from scripts.experiments.ics_circulation_v3.run_phase4_coupling import _run_case, mechanism_comparison, run
from scripts.experiments.ics_circulation_v3.runtime import Simulation, assert_invariants


def test_burnin_is_actually_admitted_finite_buffer_and_recirculating():
    for kind in ("scarce", "sufficient", "reversal"):
        scene = coupling_scene(kind)
        assert scene.initial.now == 1
        assert scene.initial.plans["warm_tray"].bag_id == "warm"
        assert scene.initial.trays["warm_tray"].mode == "in_transit"
        assert len(scene.initial.trays) > scene.initial.network.nodes["A"].capacity
        assert not scene.initial.network.nodes["J"].can_wait
        assert not scene.initial.network.nodes["K"].can_wait
        assert {edge.target for edge in scene.initial.network.edges.values()} == set(scene.initial.network.nodes)
        assert_invariants(scene.initial)


def test_same_builder_contract_for_label_and_deployment_does_not_hash_truth():
    scene = coupling_scene()
    spec = control.ControlSpec()
    label = control.build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    changed_truth = tuple(replace(bag, arrival=bag.arrival + 1) for bag in scene.future_bags)
    deployment = control.build_engine(scene.initial, scene.forecasts, changed_truth, spec)
    assert label.control_contract == deployment.control_contract
    assert label._generator.dynamic_local and deployment._generator.dynamic_local
    assert label.slow_controller.controller.generator_factory.spec == spec
    changed = control.build_engine(scene.initial, scene.forecasts, scene.future_bags, replace(spec, slow_period=3))
    assert changed.control_contract["continuation_sha256"] != label.control_contract["continuation_sha256"]
    assert changed.control_contract["information_sha256"] == label.control_contract["information_sha256"]


def test_dynamic_reference_dependency_changes_the_continuation_contract(monkeypatch):
    from scripts.experiments.ics_circulation_v3.run_phase4_coupling import SOURCES
    scene = coupling_scene()
    spec = control.ControlSpec()
    before = control.control_contract(spec, scene.forecasts, start_tick=scene.initial.now)
    assert "routing_reference.py" in SOURCES
    read = Path.read_bytes
    def changed_dependency(path):
        contents = read(path)
        return contents + b"\n# dependency-change-probe\n" if path.name == "routing_reference.py" else contents
    monkeypatch.setattr(Path, "read_bytes", changed_dependency)
    after = control.control_contract(spec, scene.forecasts, start_tick=scene.initial.now)
    assert before["continuation"]["implementation_sha256"]["routing_reference.py"] != after["continuation"]["implementation_sha256"]["routing_reference.py"]
    assert before["continuation_sha256"] != after["continuation_sha256"]
    assert before["contract_sha256"] != after["contract_sha256"]
    assert before["information_sha256"] == after["information_sha256"]


def test_slow_period_counts_real_triggers_and_checkpoint_restores_phase():
    scene = coupling_scene()
    engine = control.build_engine(scene.initial, scene.forecasts, scene.future_bags, control.ControlSpec(slow_period=3))
    engine.advance(8)
    assert engine.slow_controller.trigger_times == [1, 4, 7]
    assert engine.policy_stats["slow_calls"] == len(engine.slow_controller.callback_times) == 7
    restored = Simulation.from_checkpoint(engine.checkpoint())
    assert engine.advance(44) == restored.advance(44)
    assert engine.slow_controller.trigger_times == restored.slow_controller.trigger_times
    assert engine.slow_controller.trigger_times == list(range(1, 44, 3))
    assert engine.route_selector.contract == restored.route_selector.contract


@pytest.mark.parametrize("routing", ("timed", "conditional_timed"))
def test_later_publications_never_reach_scorer_early(routing):
    scene = coupling_scene("reversal")
    engine = control.build_engine(scene.initial, scene.forecasts, scene.future_bags, control.ControlSpec(routing=routing))
    engine.advance(scene.horizon)
    for call in engine.route_selector.selector.publication_history:
        assert all(row["published_at"] <= call["time"] for row in call["published"])
    for call in engine.slow_controller.history:
        assert all(row["published_at"] <= call["trigger_time"] for row in call["diagnostics"]["accepted_forecasts"])
    assert any(row.published_at > scene.initial.now for row in scene.forecasts)


@pytest.mark.parametrize("routing", ("baseline", "timed", "conditional_timed"))
def test_scarce_predispatch_releases_shared_edge_and_changes_loaded_witness(routing):
    scene = coupling_scene("scarce")
    baseline = _run_case(scene, control.ControlSpec(routing=routing, predictive=False))
    predicted = _run_case(scene, control.ControlSpec(routing=routing, predictive=True))
    comparison = mechanism_comparison(baseline, predicted)
    assert comparison["all_scheduled_bags_complete_in_both"]
    assert comparison["earlier_predispatch_clears_shared_edge"]
    assert comparison["predictive_minus_reactive"] < 0
    assert comparison["B10_load_times"]["predictive"] == 10
    assert comparison["B10_load_times"]["reactive"] > 10
    b = comparison["A12_route_witnesses"]["reactive"][0]["chosen"]
    p = comparison["A12_route_witnesses"]["predictive"][0]["chosen"]
    assert p["unload_complete"] < b["unload_complete"]
    for result in (baseline, predicted):
        assert result["metrics"]["tray_identity_preserved"]
        assert result["metrics"]["trays_serving_multiple_bags"] >= 2
        assert result["metrics"]["physical_nodes_observed_at_capacity"]
        assert result["final_snapshot"]["completed"]["warm"] <= 8


def test_sufficient_stock_control_never_predispatches_and_has_no_gain():
    scene = coupling_scene("sufficient")
    baseline = _run_case(scene, control.ControlSpec(predictive=False))
    predicted = _run_case(scene, control.ControlSpec(predictive=True))
    assert baseline["metrics"]["total_cost"] == predicted["metrics"]["total_cost"] == 0
    assert predicted["metrics"]["accepted_slow_transfers"] == 0
    assert predicted["metrics"]["completed"] == predicted["metrics"]["all_bag_denominator"] == 8


def test_forecast_reversal_keeps_entered_transfer_and_reports_harm():
    scene = coupling_scene("reversal")
    baseline = _run_case(scene, control.ControlSpec(predictive=False))
    predicted = _run_case(scene, control.ControlSpec(predictive=True))
    comparison = mechanism_comparison(baseline, predicted)
    assert comparison["all_scheduled_bags_complete_in_both"]
    assert comparison["predictive_minus_reactive"] > 0
    action = comparison["accepted_empty_transfers_before_B10"][0]
    long_leg = next(leg for leg in action["legs"] if leg["edge_id"] == "J-B")
    assert long_leg["depart"] < 7 < long_leg["arrive"]  # Cancellation arrives during the entered edge.
    assert any(event["event"] == "depart" and event["tray_id"] == action["tray_id"] and event["edge_id"] == "J-B"
               and event["time"] == long_leg["depart"] for event in predicted["event_trace"])


def test_external_selector_needs_identity_and_cannot_receive_engine_truth():
    scene = coupling_scene()
    class ObservableSelector:
        def __call__(self, state, candidates):
            assert not hasattr(state, "future_bags") and not hasattr(state, "_arrivals")
            return candidates[0]
    with pytest.raises(ValueError, match="selector_manifest"):
        control.build_engine(scene.initial, scene.forecasts, scene.future_bags,
                             control.ControlSpec(routing="external"), route_selector=ObservableSelector())
    engine = control.build_engine(scene.initial, scene.forecasts, scene.future_bags,
                                 control.ControlSpec(routing="external"), route_selector=ObservableSelector(),
                                 selector_manifest={"implementation": "test_observable_selector", "artifact_sha256": "test_only"})
    assert len(engine.advance(scene.horizon).completed) == 8


def test_new_runner_also_refuses_existing_evidence(tmp_path):
    marker = tmp_path / "prior"
    marker.write_text("original")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        run(tmp_path)
    assert marker.read_text() == "original"


def test_late_failure_after_predispatch_keeps_summary_denominator_and_nonzero_exit(tmp_path, monkeypatch):
    from scripts.experiments.ics_circulation_v3 import run_phase4_coupling as runner
    original = runner.build_engine
    def late_failure_engine(initial, forecasts, future_bags, spec, **kwargs):
        engine = original(initial, forecasts, future_bags, spec, **kwargs)
        advance = engine.advance
        if spec.routing == "baseline" and spec.predictive:
            def fail_after_mechanism(horizon):
                advance(20)  # Retain accepted early actions and the time12 resource observations.
                raise RuntimeError("injected late rollout failure")
            engine.advance = fail_after_mechanism
        return engine
    monkeypatch.setattr(runner, "build_engine", late_failure_engine)
    assert runner.main(["--output", str(tmp_path)]) == 1
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["run_count"] == 18 and summary["failed_run_count"] == 3
    assert summary["scheduled_bag_denominator_across_runs"] == 144
    assert summary["cost_available_comparison_count"] == 6
    assert len(summary["cost_unavailable_comparisons"]) == 3
    comparisons = json.loads((tmp_path / "mechanism_comparisons.json").read_text())
    scarce = next(row for row in comparisons if row["scene"] == "scarce" and row["routing"] == "baseline")
    reversal = next(row for row in comparisons if row["scene"] == "reversal" and row["routing"] == "baseline")
    assert scarce["earlier_predispatch_clears_shared_edge"] and scarce["predictive_minus_reactive"] is None
    assert reversal["accepted_empty_transfers_before_B10"] and reversal["predictive_minus_reactive"] is None
    assert summary["mechanism_checks"]["scarce_predispatch_changes_shared_resource_and_reduces_cost"] is False
    assert summary["mechanism_checks"]["forecast_reversal_negative_effect_retained"] is False
    detail = json.loads((tmp_path / "scarce__baseline__predictive_True.json").read_text())
    assert detail["failure"]["message"] == "injected late rollout failure"
    assert detail["metrics"]["total_cost"] is None and len(detail["bag_ledger"]) == 8

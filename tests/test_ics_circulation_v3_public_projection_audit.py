"""Independent boundary check: public projection versus exact engine continuation.

The oracle here is a test-only engine checkpoint. Both branches receive only
the same currently published proxy tape and fixed timed continuation. Online
code never receives that checkpoint. Prior accrued costs may be a constant;
the action differences and final physical ledger must agree.
"""
from dataclasses import asdict

import pytest

from scripts.experiments.ics_circulation_v3.joint_feedback import published_proxy
from scripts.experiments.ics_circulation_v3.label_stability import sustained_scenes
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, PublishedRoutingSelector
from scripts.experiments.ics_circulation_v3.role_coverage import (
    CursorSimulation, branch_role_decision, collect_role_decisions)


@pytest.mark.parametrize("order", ["route_then_prebalance", "prebalance_then_route"])
def test_public_projection_keeps_later_actual_decision_action_differences(order):
    scene = sustained_scenes()[0]
    spec = ControlSpec(planning_horizon=20, slow_period=2, coordination_order=order)
    collection = collect_role_decisions(scene, spec)
    sample = next(s for s in collection.samples if s["source_node"] == "B" and s["time"] > 0)
    checkpoint = sample["checkpoint"].clone()
    state = checkpoint.state
    visible = tuple(f for f in scene.forecasts if f.published_at <= state.now)
    horizon = state.now + spec.planning_horizon
    tape = published_proxy(state, visible, horizon)
    # The public model deliberately freezes publications unknown at this
    # decision. Match that condition in the private test-only reference.
    checkpoint.base.slow_controller.forecast_publications = visible
    context = CursorSimulation.from_checkpoint(checkpoint).visible_decision_context()
    manifest = {"implementation": "PublishedRoutingSelector", "spec": asdict(spec),
                "test_scope": "same visible publications only"}
    exact_costs, public_costs = [], []
    assert len(sample["pool"]) > 1
    for candidate in sample["pool"]:
        exact = branch_role_decision(checkpoint, candidate, tape, horizon,
            continuation_selector=PublishedRoutingSelector(spec, visible), selector_manifest=manifest)
        public = CursorSimulation.from_visible(state, context, tape, spec, visible)
        public.choose_pending(candidate)
        projected = public.advance(horizon)
        assert projected.final_snapshot == exact.final_snapshot
        assert projected.completed == exact.completed
        exact_costs.append(exact.total_cost)
        public_costs.append(projected.total_cost)
    assert [v - exact_costs[0] for v in exact_costs] == pytest.approx(
        [v - public_costs[0] for v in public_costs])

import pytest

from scripts.experiments.ics_circulation_v3.runtime import Simulation
from scripts.experiments.ics_circulation_v3.storage_lifecycle import mechanism, lifecycle_report


@pytest.mark.parametrize("case", ["reuse", "unprotected_reuse"])
@pytest.mark.parametrize("mode", ["whole_route", "next_edge"])
def test_one_real_carrier_completes_two_early_tasks_then_direct_with_two_returns(case, mode):
    engine = mechanism(case, mode)
    result = engine.advance(40)
    assert result.completed == {"early1": 9, "early2": 18, "direct": 24}
    report = lifecycle_report(engine, ("early1", "early2", "direct"))
    assert report["carrier_service_order"] == {"t0": ["early1", "early2", "direct"]}
    assert report["carrier_reuses"] == 2 and report["transport_drained"]
    assert result.cost_components["empty_distance"] == 4
    assert report["task_rows"]["early2"]["storage"]["arrived_at"] == 15


@pytest.mark.parametrize("mode", ["whole_route", "next_edge"])
def test_short_planning_horizon_is_not_declared_storage_infeasibility(mode):
    engine = mechanism("long_release", mode)
    partial = engine.advance(10)
    assert not partial.completed
    assert partial.uncompleted_bag_ids == ("direct", "early1", "early2")
    assert engine.state.trays["t0"].bag_id == "early1"
    assert engine._generator.last_search_status == "storage_horizon_or_deadline_bound"
    resumed = Simulation.from_checkpoint(engine.checkpoint())
    result = engine.advance(160)
    assert result == resumed.advance(160)
    assert result.completed == {"early1": 103, "early2": 112, "direct": 118}
    assert lifecycle_report(engine, ("early1", "early2", "direct"))["transport_drained"]


@pytest.mark.parametrize("case", ["deadline_before_release", "closed_ingress", "closed_return"])
def test_censored_tasks_keep_the_complete_business_denominator(case):
    engine = mechanism(case)
    engine.advance(40)
    report = lifecycle_report(engine, ("early1", "early2", "direct"))
    assert report["expected_business_tasks"] == 3
    assert not report["transport_drained"]
    assert all(row["observed"] for row in report["task_rows"].values())
    assert len(engine.state.trays) == 1

from scripts.experiments.ics_circulation_v3.run_multi_load_feedback import scenes
from scripts.experiments.ics_circulation_v3.runtime import Simulation, assert_invariants


def test_multi_load_grid_has_legal_finite_initial_state_and_no_shared_mutation():
    cases = scenes()
    assert len(cases) == 24
    assert len({s.name for s in cases}) == 24
    for scene in cases:
        state = Simulation(scene.initial, scene.future_bags).observe()
        assert_invariants(state)
        assert len(state.trays) == scene.factors['loaded_count'] + scene.factors['donor_count']
        assert len(scene.future_bags) == 2
        assert len({f.unit_ids[0] for f in scene.forecasts}) == 2
    cases[0].initial.network.nodes.clear()
    assert cases[1].initial.network.nodes

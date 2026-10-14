"""Independent conditional-law and private-checkpoint contracts for Round8."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3 import same_zone_stability as stability
from scripts.experiments.ics_circulation_v3 import same_zone_labels as labels
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_role_labels import SearchBudget, bind_accounting
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation
from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache
from scripts.experiments.ics_circulation_v3.same_zone_experiment import install_supply_policy


def state():
    nodes = {n: Node(n, 'zone', 'owner:' + n, 5) for n in ('A', 'B', 'C')}
    edges = [Edge(a + b, a, b, 2) for a, b in [('A', 'B'), ('B', 'C'), ('A', 'C'), ('C', 'A')]]
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
        {'tray': Tray('tray', 'A', 'loaded', 'seen')}, {'seen': Bag('seen', 'A', 'C', 0, 50)})


def tasks():
    return (Bag('soft', 'B', 'C', 2, 30), Bag('protected', 'C', 'A', 7, 45, protected=True))


def captured():
    forecasts = (RoutingDemandForecast('soft', 'B', 'C', 2, 30, published_at=0, unit_ids=('soft',)),)
    base = build_engine(state(), forecasts, tasks(),
        ControlSpec(routing='timed', predictive=True, planning_horizon=20, slow_period=2))
    enable_replay_cache(base)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    install_supply_policy(engine, labels.METHOD)
    bind_accounting(engine, SearchBudget(100, 100000, 30))
    records = []

    def capture(current, tray, pool):
        cp = current.checkpoint().clone()
        records.append(({'checkpoint': cp, 'pool': tuple(pool), 'future': labels.pending_future(current)},
                        labels.checkpoint_metadata(cp)))

    engine._decision_callback = capture
    engine.advance(1)
    assert records and records[0][0]['pool']
    return records[0]


def test_conditioned_integer_mass_removes_at_now_outcome_without_clipping():
    soft = tasks()[0]
    support = stability.conditional_support(soft, 0)
    assert support['total_mass'] == 17
    assert support['outcomes'] == [{'cancel': True, 'jitter': None, 'mass': 3},
        {'cancel': False, 'jitter': 0, 'mass': 7}, {'cancel': False, 'jitter': 2, 'mass': 7}]
    later = stability.conditional_support(replace(soft, arrival=3), 0)
    assert later['total_mass'] == 24 and [v['mass'] for v in later['outcomes']] == [3, 7, 7, 7]
    exact = stability.conditional_support(tasks()[1], 0)
    assert exact['total_mass'] == 1 and exact['outcomes'] == [{'cancel': False, 'jitter': 0, 'mass': 1}]


def test_sampler_implements_every_integer_mass_without_extra_protected_draws(monkeypatch):
    draws = []

    class CountingRandom:
        def __init__(self, seed):
            self.i = 0

        def randrange(self, upper):
            assert upper == 17
            draws.append(upper)
            value, self.i = self.i, self.i + 1
            return value

    monkeypatch.setattr(stability.random, 'Random', CountingRandom)
    tapes = stability.sample_conditional_futures(state(), tasks(), 7, 17)
    assert len(draws) == 17
    assert all(tasks()[1] in tape for tape in tapes)
    arrivals = [next((b.arrival for b in tape if b.bag_id == 'soft'), None) for tape in tapes]
    assert arrivals == [None] * 3 + [2] * 7 + [4] * 7


def test_nested_samples_are_exact_prefixes_and_degenerate_tapes_keep_multiplicity():
    full = stability.sample_conditional_futures(state(), tasks(), 123, 32)
    assert stability.sample_conditional_futures(state(), tasks(), 123, 2) == full[:2]
    assert stability.sample_conditional_futures(state(), tasks(), 123, 8) == full[:8]
    protected = (tasks()[1],)
    assert stability.sample_conditional_futures(state(), protected, 123, 32) == (protected,) * 32
    assert stability.sample_conditional_futures(state(), (), 123, 32) == ((),) * 32


@pytest.mark.parametrize('invalid', ['now', 'past', 'observed', 'duplicate'])
def test_original_pending_errors_reject_whole_request_instead_of_filtering(invalid):
    soft, protected = tasks()
    value = {'now': replace(soft, arrival=0), 'past': replace(soft, arrival=-1),
             'observed': replace(soft, bag_id='seen'), 'duplicate': protected}[invalid]
    with pytest.raises(ValueError):
        stability.sample_conditional_futures(state(), (protected, value), 2, 2)


@pytest.mark.parametrize('change', ['delete_protected', 'shift_protected', 'od', 'slack', 'new_id', 'duplicate', 'at_now', 'jitter1'])
def test_sampled_tape_cannot_change_protection_identity_od_slack_or_support(change):
    soft, protected = tasks()
    values = {
        'delete_protected': (soft,), 'shift_protected': (soft, replace(protected, arrival=9, deadline=47)),
        'od': (replace(soft, destination='A'), protected),
        'slack': (replace(soft, deadline=31), protected),
        'new_id': (replace(soft, bag_id='new'), protected),
        'duplicate': (soft, soft, protected),
        'at_now': (replace(soft, arrival=0, deadline=28), protected),
        'jitter1': (replace(soft, arrival=3, deadline=31), protected)}
    with pytest.raises(ValueError):
        stability.validate_sampled_future(state(), tasks(), values[change])


def test_replacement_changes_only_unobserved_event_queue_and_keeps_public_ghost_forecast():
    payload, metadata = captured()
    original_payload = deepcopy(payload)
    before = labels.restore_matching_continuation(payload, metadata)
    protected = tuple(b for b in payload['future'] if b.protected)
    engine, binding = stability.restore_sampled_continuation(payload, metadata, protected)
    assert all(binding['unchanged'].values())
    assert stability.continuation_observation(engine) == stability.continuation_observation(before)
    assert labels.pending_future(engine) == protected
    # This loaded cursor precedes the slow stage: publication schedule is live,
    # but the controller has not yet consumed it into its accepted list.
    assert [f.forecast_id for f in engine.slow_controller.forecast_publications] == ['soft']
    assert engine.slow_controller.controller.forecasts == before.slow_controller.controller.forecasts
    assert asdict(payload['checkpoint'].state) == asdict(original_payload['checkpoint'].state)
    assert labels.pending_future(labels.restore_matching_continuation(payload, metadata)) == payload['future']
    assert engine.instant_physical_ticks == []


def test_restoration_revalidates_private_clock_cache_and_forecast_binding():
    payload, metadata = captured()
    changed = deepcopy(payload)
    changed['checkpoint'].base.slow_controller.next_trigger_at += 1
    with pytest.raises(ValueError):
        stability.restore_sampled_continuation(changed, metadata, payload['future'])
    with pytest.raises(ValueError, match='protected'):
        stability.restore_sampled_continuation(payload, metadata, ())


def test_memo_identity_binds_state_action_exact_tape_continuation_and_evaluation(monkeypatch):
    args = ['checkpoint', 0, 'action', tasks(), 'continuation']
    baseline = stability.memo_key(*args)
    assert stability.memo_key(*args[:3], tuple(reversed(tasks())), args[4]) == baseline
    for index, value in [(0, 'other-checkpoint'), (1, 1), (2, 'other-action'),
                         (3, (tasks()[1],)), (4, 'other-controller')]:
        changed = list(args)
        changed[index] = value
        assert stability.memo_key(*changed) != baseline
    monkeypatch.setattr(stability, 'EVALUATION_CONTRACT', {**stability.EVALUATION_CONTRACT, 'tail_cap': 721})
    assert stability.memo_key(*args) != baseline


def test_stratification_uses_first_attempt_even_zero_and_is_outcome_invariant():
    rows = {scene: [{'decision_index': 0, 'time': 0, 'role': 'origin', 'candidate_count': 0, 'cost': 999},
        {'decision_index': 1, 'time': 1, 'role': 'origin', 'candidate_count': 4, 'cost': -999},
        {'decision_index': 2, 'time': 40, 'role': 'continuation', 'candidate_count': 4, 'cost': 2},
        {'decision_index': 3, 'time': 90, 'role': 'continuation', 'candidate_count': 0, 'cost': -200}]
        for scene in stability.SCENE_SEEDS}
    result = stability.select_strata(rows)
    assert result['counts']['attempts'] == 12 and result['counts']['zero'] == 6
    assert result['counts']['selected_nonempty'] == 3
    assert all(r['decision_index'] != 1 for r in result['selected'])
    for attempts in rows.values():
        for row in attempts:
            row['cost'] = -row['cost']
    repeated = stability.select_strata(rows)
    assert [r['state_key'] for r in result['selected']] == [r['state_key'] for r in repeated['selected']]
    assert result['cells'] == repeated['cells']

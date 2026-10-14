from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.label_stability import sustained_scenes
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.role_coverage import (
    CursorSimulation, RoleQuota, branch_role_decision, checkpoint_fingerprint,
    collect_role_decisions, label_role_decision, sample_artifact)
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator, Simulation


def assert_physical_equal(a, b):
    assert a.final_snapshot == b.final_snapshot
    assert a.trace == b.trace
    assert a.cost_components == b.cost_components
    assert a.total_cost == b.total_cost
    assert a.invariant_checks == b.invariant_checks
    assert {k: v for k, v in a.policy_stats.items() if not k.endswith('_ms')} == {
        k: v for k, v in b.policy_stats.items() if not k.endswith('_ms')}


@pytest.mark.parametrize('order', ['route_then_prebalance', 'prebalance_then_route'])
def test_cursor_dispatch_matches_frozen_runtime_and_every_actual_decision_replays(order):
    scene = sustained_scenes()[0]
    spec = ControlSpec(planning_horizon=20, coordination_order=order)
    reference = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    base = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    checkpoints = []
    engine._decision_callback = lambda current, tray, options: checkpoints.append(current.checkpoint())
    expected = reference.advance(30)
    actual = engine.advance(30)
    assert_physical_equal(actual, expected)
    assert len(checkpoints) >= 4
    for checkpoint in checkpoints:
        restored = CursorSimulation.from_checkpoint(checkpoint)
        assert_physical_equal(restored.advance(30), actual)
        assert restored.slow_controller.trigger_times == engine.slow_controller.trigger_times
        assert restored.route_selector.history == engine.route_selector.history


class LaterCommitGenerator:
    def __init__(self, horizon=20):
        self.generator = CandidateGenerator(horizon=horizon)
        self.calls = []

    def generate(self, state, bag_id, tray_id, k=4):
        self.calls.append((state.now, tray_id))
        if tray_id == 'a' and 'b' not in state.plans:
            return ()
        return self.generator.generate(state, bag_id, tray_id, k=k)

    def generate_empty(self, *args, **kwargs):
        return ()


class CountingSlow:
    def __init__(self):
        self.next_trigger_at = 0
        self.calls = []

    def __call__(self, state):
        self.calls.append(state.now)
        self.next_trigger_at = state.now + 1
        return ()


def two_loaded():
    return Snapshot(0, Network({'A': Node('A', 'z', 'p', 4), 'B': Node('B', 'z', 'p', 4)},
                               {'AB': Edge('AB', 'A', 'B', 3, 2)}),
        {i: Tray(i, 'A', 'loaded', i) for i in ('a', 'b')},
        {i: Bag(i, 'A', 'B', 0, 30) for i in ('a', 'b')}, module=FixedLocalModule())


@pytest.mark.parametrize('order', ['route_then_prebalance', 'prebalance_then_route'])
def test_mid_loop_restore_never_retries_earlier_zero_tray_or_repeats_slow(order):
    base = Simulation(two_loaded(), generator_factory=LaterCommitGenerator,
        route_selector=lambda snapshot, options: options[0], slow_controller=CountingSlow(),
        reactive_empty_dispatch=False, coordination_order=order)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint())
    checkpoints = []
    engine._decision_callback = lambda current, tray, options: checkpoints.append(current.checkpoint())
    expected = engine.advance(1)
    zero, pending_b = checkpoints
    assert zero.cursor.pending_options == ()
    assert pending_b.cursor.route_index == 1 and pending_b.cursor.pending_tray_id == 'b'
    for checkpoint in checkpoints:
        restored = CursorSimulation.from_checkpoint(checkpoint)
        assert_physical_equal(restored.advance(1), expected)
        assert restored._generator.calls == [(0, 'a'), (0, 'b')]
        assert restored.slow_controller.calls == [0]
        assert 'a' not in restored.state.plans


def test_mid_loop_checkpoint_preserves_earlier_same_tick_commit_and_no_reselection():
    base = Simulation(two_loaded(), route_selector=lambda state, options: options[0],
                      reactive_empty_dispatch=False)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint())
    checkpoints = []
    engine._decision_callback = lambda current, tray, options: checkpoints.append(current.checkpoint())
    expected = engine.advance(1)
    second = checkpoints[1]
    assert 'a' in second.state.plans
    restored = CursorSimulation.from_checkpoint(second)
    assert_physical_equal(restored.advance(1), expected)
    assert len([e for e in restored._trace if e['event'] == 'route_commit']) == 2


def test_regular_pause_between_ticks_keeps_event_phase_and_future_arrival():
    scene = sustained_scenes()[0]
    base = build_engine(scene.initial, scene.forecasts, scene.future_bags, ControlSpec(planning_horizon=20))
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint())
    engine.advance(19)
    checkpoint = engine.checkpoint()
    restored = CursorSimulation.from_checkpoint(checkpoint)
    assert_physical_equal(restored.advance(30), engine.advance(30))
    assert 'round1:loaded' in restored.state.bags


def test_all_actual_roles_include_zero_and_single_without_replacing_failures():
    scene = sustained_scenes()[0]
    broken = scene.initial.clone()
    broken.network.edges.clear()
    failed = collect_role_decisions(replace(scene, initial=broken, future_bags=(), forecasts=(), horizon=3),
        ControlSpec(planning_horizon=20, predictive=False, reactive=False), quota=RoleQuota(bands=(0,)))
    assert len(failed.opportunities) == 3 and len(failed.samples) == 1
    assert failed.samples[0]['pool'] == ()
    assert failed.metadata['candidate_denominator'] == {'zero': 3}
    single = collect_role_decisions(scene, ControlSpec(planning_horizon=20, candidate_count=1))
    assert single.metadata['candidate_denominator'] == {'single': len(single.opportunities)}
    assert {'S', 'B'} <= set(single.metadata['observed_nodes'])
    assert single.metadata['empty_nodes'] == ['C', 'G']


def test_round_robin_quota_is_declared_and_features_do_not_look_at_future_tape():
    scene = sustained_scenes()[0]
    spec = ControlSpec(planning_horizon=20)
    quota = RoleQuota(max_samples=3, selection_rule='node_role_round_robin')
    found = collect_role_decisions(scene, spec, quota=quota)
    assert [(s['source_node'], s['band']) for s in found.samples] == [('S', 0), ('B', 0), ('S', 20)]
    changed_truth = replace(scene, future_bags=())
    other = collect_role_decisions(changed_truth, spec, quota=quota)
    first, changed = found.samples[0], other.samples[0]
    assert first['features'] == changed['features']
    assert first['features_physical'] == changed['features_physical']
    assert len(first['features'][0]) == 23 and len(first['features_physical'][0]) == 31
    assert first['checkpoint_sha256'] != changed['checkpoint_sha256']
    assert 'checkpoint' not in sample_artifact(first)


def test_pending_choice_commits_once_and_public_context_has_no_future_or_policy():
    scene = sustained_scenes()[0]
    spec = ControlSpec(planning_horizon=20)
    sample = collect_role_decisions(scene, spec).samples[0]
    engine = CursorSimulation.from_checkpoint(sample['checkpoint'])
    context = engine.visible_decision_context()
    assert set(asdict(context)) == {'cursor', 'next_slow_trigger_at', 'cache_contract'}
    assert context.cache_contract is None
    assert not hasattr(context, 'pending_arrivals')
    forecast_only = CursorSimulation.from_visible(sample['checkpoint'].state, context, (), spec, ())
    forecast_only.choose_pending(sample['pool'][0])
    with pytest.raises(ValueError, match='already set'):
        forecast_only.choose_pending(sample['pool'][0])
    result = forecast_only.advance(1)
    assert len([e for e in result.trace if e['event'] == 'route_commit']) == 1
    future_publication = replace(scene.forecasts[0], published_at=1)
    with pytest.raises(ValueError, match='unpublished'):
        CursorSimulation.from_visible(sample['checkpoint'].state, context, (), spec, (future_publication,))


def test_common_future_labels_keep_normal_k4_pairing_and_nominal_is_separate():
    scene = sustained_scenes()[0]
    sample = collect_role_decisions(scene, ControlSpec(planning_horizon=20)).samples[0]
    before = checkpoint_fingerprint(sample['checkpoint'])
    label = label_role_decision(sample, scene.future_bags, groups=2, futures_per_group=2)
    assert not label['failures']
    assert len(label['raw_branches']) == 2 * 4 * 2
    for group in range(2):
        for future in range(2):
            assert len({b['future_sha256'] for b in label['raw_branches']
                        if b['group'] == group and b['future_index'] == future}) == 1
    assert checkpoint_fingerprint(sample['checkpoint']) == before
    nominal = label_role_decision(sample, scene.future_bags, regime='nominal')
    assert nominal['groups'] == nominal['futures_per_group'] == 1
    assert nominal['horizon_ticks'] == 20
    with pytest.raises(ValueError, match='planning horizon'):
        label_role_decision(sample, scene.future_bags, horizon_ticks=24)


def test_offline_future_validation_and_explicit_continuation_override():
    scene = sustained_scenes()[0]
    sample = collect_role_decisions(scene, ControlSpec(planning_horizon=20)).samples[0]
    with pytest.raises(ValueError, match='unobserved later'):
        branch_role_decision(sample['checkpoint'], sample['pool'][0], tuple(scene.initial.bags.values()), 20)
    with pytest.raises(ValueError, match='manifest'):
        branch_role_decision(sample['checkpoint'], sample['pool'][0], scene.future_bags, 20,
                             continuation_selector=lambda state, options: options[0])


class OneObservedDetour:
    def __init__(self):
        self.used = False

    def __call__(self, state, options):
        bag = state.bags[options[0].bag_id]
        tray = state.trays[options[0].tray_id]
        if not self.used and tray.node == bag.origin == 'B':
            alternatives = [candidate for candidate in options if len(candidate.legs) > 1]
            if alternatives:
                self.used = True
                return alternatives[-1]
        return options[0]


def test_external_policy_captures_actual_arrival_at_destination_role_after_prefix():
    scene = sustained_scenes()[0]
    found = collect_role_decisions(scene, ControlSpec(routing='external', planning_horizon=20),
        route_selector=OneObservedDetour(), selector_manifest={'test_policy': 'one_observed_B_detour'},
        quota=RoleQuota(max_samples=9, selection_rule='node_role_round_robin'))
    received = [s for s in found.samples if s['source_node'] == 'C' and s['role'] == 'arrival_at_destination']
    assert received
    checkpoint = received[0]['checkpoint']
    assert any(e['event'] == 'prefix_arrive' and e.get('node') == 'C' for e in checkpoint.base.trace)
    assert checkpoint.state.trays[received[0]['tray_id']].bag_id == received[0]['bag_id']
    assert found.metadata['route_history']


def test_noise_gate_keeps_unstable_ranking_on_four_groups():
    from scripts.experiments.ics_circulation_v3.run_role_coverage import noise_gate, noise_record
    stable = {'identity': 'stable', 'source_node': 'B', 'role': 'origin', 'candidate_count': 2,
              'failures': [], 'paired_costs': [[[0.] * 8, [2.] * 8] for _ in range(4)]}
    result = noise_gate([noise_record(stable)])
    assert result['recommended_R1_groups'] == 2
    unstable = {**stable, 'paired_costs': [[[0.] * 8, [2.] * 8], [[0.] * 8, [2.] * 8],
                                          [[4.] * 8, [0.] * 8], [[4.] * 8, [0.] * 8]]}
    result = noise_gate([noise_record(unstable)])
    assert result['recommended_R1_groups'] == 4
    assert result['B_states']['two_groups_heldout_mean_regret'] > .1

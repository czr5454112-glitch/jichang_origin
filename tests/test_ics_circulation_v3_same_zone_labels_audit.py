"""Independent real-cursor and failure-boundary checks for round-seven labels."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
import pickle
from types import SimpleNamespace

import pytest

from scripts.experiments.ics_circulation_v3 import same_zone_labels as labels
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_role_labels import SearchBudget, bind_accounting
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation, checkpoint_fingerprint
from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache, routing_cache_state
from scripts.experiments.ics_circulation_v3.same_zone_experiment import install_supply_policy
from scripts.experiments.ics_circulation_v3.same_zone_supply import SameZoneSupplyPrebalancer


def _engine(*, disconnected=False, future=True):
    nodes = {node: Node(node, 'zone', 'owner:' + node, 4) for node in 'ABC'}
    edges = [Edge('AB', 'A', 'B', 2), Edge('BA', 'B', 'A', 2)]
    if not disconnected:
        edges += [Edge('BC', 'B', 'C', 2), Edge('CA', 'C', 'A', 2), Edge('AC', 'A', 'C', 5)]
    state = Snapshot(0, Network(nodes, {edge.edge_id: edge for edge in edges}),
                     {'tray': Tray('tray', 'A', 'loaded', 'seen')},
                     {'seen': Bag('seen', 'A', 'C', 0, 30)})
    tape = (Bag('not-yet-observed', 'C', 'A', 12, 50),) if future else ()
    spec = ControlSpec(routing='timed', predictive=True, planning_horizon=20, slow_period=2)
    base = build_engine(state, (), tape, spec)
    enable_replay_cache(base)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    install_supply_policy(engine, labels.METHOD)
    return engine


def _captured(*, disconnected=False):
    engine = _engine(disconnected=disconnected, future=not disconnected)
    owner = bind_accounting(engine, SearchBudget(100, 100000, 30))
    captures = []

    def capture(current, tray, options):
        checkpoint = current.checkpoint().clone()
        metadata = labels.checkpoint_metadata(checkpoint)
        metadata.update(search_prefix_count=len(owner.rows),
                        selector_prefix_count=len(current.route_selector.history),
                        trace_prefix_count=len(current._trace))
        captures.append((dict(checkpoint=checkpoint, pool=tuple(options),
                              future=labels.pending_future(current)), metadata))

    engine._decision_callback = capture
    engine.advance(1)
    assert captures
    return captures[0]


def _generator(checkpoint):
    generator = checkpoint.base.generator
    while hasattr(generator, 'generator'):
        generator = generator.generator
    return generator


@pytest.mark.parametrize('mutation', [
    'clock', 'cursor', 'state', 'pending_pool', 'cache', 'slow_parameter',
    'factory', 'future', 'publication',
])
def test_exact_binding_rejects_each_private_or_public_checkpoint_mutation(mutation):
    payload, metadata = _captured()
    checkpoint = payload['checkpoint'].clone()
    if mutation == 'clock':
        checkpoint.base.slow_controller.next_trigger_at += 1
    elif mutation == 'cursor':
        checkpoint.cursor.route_index += 1
    elif mutation == 'state':
        checkpoint.state.version += 1
    elif mutation == 'pending_pool':
        checkpoint.cursor.pending_options = checkpoint.cursor.pending_options[:-1]
    elif mutation == 'cache':
        _generator(checkpoint)._owned_topology_cache.capacity += 1
    elif mutation == 'slow_parameter':
        checkpoint.base.slow_controller.controller.max_same_zone_candidates += 1
    elif mutation == 'factory':
        factory = checkpoint.base.generator_factory
        while hasattr(factory, 'inner_factory'):
            factory = factory.inner_factory
        changed = replace(factory, expansion_limit=factory.expansion_limit + 1)
        checkpoint.base.generator_factory = changed
    elif mutation == 'future':
        checkpoint.base.pending_arrivals.clear()
    else:
        checkpoint.base.slow_controller.forecast_publications += (
            RoutingDemandForecast('added', 'A', 'C', 10, 40, published_at=0),)
    with pytest.raises(ValueError):
        labels.validate_checkpoint_binding(checkpoint, metadata)


@pytest.mark.parametrize('mutation', ['clock', 'active_continuation', 'cache_digest', 'future_digest', 'candidate_key',
                                     'search_prefix_count', 'selector_prefix_count', 'trace_prefix_count'])
def test_metadata_must_describe_actual_instance_not_just_public_state(mutation):
    payload, metadata = _captured()
    metadata = deepcopy(metadata)
    if mutation == 'clock':
        metadata['next_slow_trigger_at'] += 1
    elif mutation == 'active_continuation':
        metadata['active_continuation']['controller_scalars']['max_same_zone_candidates'] = 0
    elif mutation == 'cache_digest':
        metadata['routing_cache']['fast_cache_sha256'] = 'forged'
    elif mutation == 'future_digest':
        metadata['future_sha256'] = 'forged'
    elif mutation == 'candidate_key':
        metadata['candidate_keys'][0] = 'forged'
    else:
        metadata[mutation] += 1
    with pytest.raises(ValueError):
        labels.restore_matching_continuation(payload, metadata)


@pytest.mark.parametrize('mutation', ['pool', 'future'])
def test_payload_cannot_replace_original_pool_or_future_even_with_correct_checkpoint(mutation):
    payload, metadata = _captured()
    payload = dict(payload)
    payload[mutation] = ()
    with pytest.raises(ValueError):
        labels.restore_matching_continuation(payload, metadata)


def test_restore_keeps_exact_cache_clock_method_and_rebinds_only_search_owner():
    payload, metadata = _captured()
    checkpoint = payload['checkpoint']
    fingerprint = checkpoint_fingerprint(checkpoint)
    restored = labels.restore_matching_continuation(payload, metadata)
    before_cache = routing_cache_state(restored)
    assert type(restored.slow_controller.controller) is SameZoneSupplyPrebalancer
    assert restored.slow_controller.next_trigger_at == metadata['next_slow_trigger_at']
    assert asdict(restored._cursor) == metadata['cursor']
    assert set(restored.state.bags) == {'seen'}
    assert tuple(b.bag_id for b in labels.pending_future(restored)) == ('not-yet-observed',)
    old_owner = restored._generator.owner
    old_rows = deepcopy(old_owner.rows)
    new_owner = bind_accounting(restored, SearchBudget(90, 90000, 30))
    assert new_owner is not old_owner and new_owner.rows == [] and new_owner.work == 0
    assert restored._generator.owner is new_owner
    assert restored.generator_factory.owner is new_owner
    assert restored.slow_controller.controller.generator_factory.owner is new_owner
    assert routing_cache_state(restored) == before_cache
    assert old_owner.rows == old_rows
    restored.state.module.hold_by_node['A'] = 999
    restored.slow_controller.next_trigger_at += 10
    assert checkpoint_fingerprint(checkpoint) == fingerprint


def test_zero_candidate_cursor_is_real_and_never_accepts_an_invented_forced_action():
    payload, metadata = _captured(disconnected=True)
    assert payload['pool'] == ()
    assert metadata['candidates'] == []
    assert labels.validate_checkpoint_binding(payload['checkpoint'], metadata)
    outcome = labels.run_label_branch(payload, metadata, forced_index=0, minimum_observation_at=2)
    assert outcome['status'] == 'execution_failure'
    assert outcome['forced_intervention'] is None
    assert outcome['initial_cursor']['pending_options'] == ()
    assert outcome['expected_task_ids'] == ['seen']
    assert outcome['search_calls'] == 0


def test_capture_failure_retains_the_actual_generation_attempt_including_zero():
    engine = _engine(disconnected=True, future=False)

    def fail_capture(*_):
        raise OSError('injected checkpoint write failure')

    outcome = labels.run_cycle(engine, engine.state.bags, minimum_observation_at=2, capture=fail_capture)
    assert outcome['status'] == 'execution_failure'
    assert outcome['failure']['message'] == 'injected checkpoint write failure'
    assert outcome['search_calls'] == 1
    assert len(outcome['opportunities']) == 1
    attempt = outcome['opportunities'][0]
    assert attempt['candidate_count'] == 0 and attempt['candidates'] == []
    assert attempt['time'] == 0 and attempt['bag_id'] == 'seen'


def test_normal_and_forced_chosen_branch_share_physics_but_record_selector_intervention():
    payload, metadata = _captured()
    before = checkpoint_fingerprint(payload['checkpoint'])
    normal = labels.run_label_branch(payload, metadata, minimum_observation_at=80)
    chosen = normal['selector_history_suffix'][0]['chosen']
    chosen_index = metadata['candidates'].index(chosen)
    forced = labels.run_label_branch(payload, metadata, forced_index=chosen_index, minimum_observation_at=80)
    assert normal['status'] == forced['status'] == 'controller_quiescent'
    assert normal['result']['final_snapshot'] == forced['result']['final_snapshot']
    assert normal['result']['trace'] == forced['result']['trace']
    assert normal['result']['cost_components'] == forced['result']['cost_components']
    assert normal['searches'] == forced['searches']
    assert normal['cache_before'] == forced['cache_before']
    assert normal['cache_after'] == forced['cache_after']
    assert normal['actual_slow_trigger_times'] == forced['actual_slow_trigger_times']
    assert normal['result']['policy_stats']['selection_calls'] == forced['result']['policy_stats']['selection_calls'] + 1
    assert normal['selector_history_suffix'][1:] == forced['selector_history_suffix']
    assert forced['forced_intervention']['candidate_index'] == chosen_index
    assert checkpoint_fingerprint(payload['checkpoint']) == before


def test_budget_censor_keeps_unobserved_original_future_in_whole_task_ledger():
    payload, metadata = _captured()
    result = labels.run_label_branch(payload, metadata, forced_index=0,
        budget=SearchBudget(1, 100000, 30), minimum_observation_at=80)
    assert result['status'] == 'budget_censored'
    assert result['expected_task_ids'] == ['not-yet-observed', 'seen']
    assert result['last_cycle_state']['task_complete'] is False
    assert 'not-yet-observed' in result['last_cycle_state']['unobserved_task_ids']
    assert result['budget_stop'] is not None


class _NoncopyableObserverPayload:
    def __deepcopy__(self, memo):
        raise AssertionError('observer sink must not enter checkpoint deepcopy')

    def __reduce__(self):
        raise AssertionError('observer sink must not enter checkpoint pickle')


@pytest.mark.parametrize('copy_mode', ['deepcopy', 'pickle'])
def test_probe_copy_removes_only_observation_and_preserves_shared_budget_owner_and_cache(copy_mode):
    from scripts.experiments.ics_circulation_v3 import same_zone_query_probe as probe
    engine = _engine()
    owner = bind_accounting(engine, SearchBudget(100, 100000, 30))
    sink = []
    probe.install_query_probe(engine, sink)
    original_generator = engine._generator
    options = engine._generator.generate(engine.state, 'seen', 'tray', k=4)
    assert options and len(sink) == 1 and sink[0]['phase'] == 'returned'
    assert set(sink[0]['snapshot'].bags) == {'seen'}
    assert not hasattr(sink[0]['snapshot'], '_arrivals')
    before_cache = routing_cache_state(engine)
    sink.append(_NoncopyableObserverPayload())
    graph = dict(generator=engine._generator, factory=engine.generator_factory,
                 slow_factory=engine.slow_controller.controller.generator_factory)
    copied = deepcopy(graph) if copy_mode == 'deepcopy' else pickle.loads(pickle.dumps(graph))
    assert not isinstance(copied['generator'], probe.QueryProbeGenerator)
    assert not isinstance(copied['factory'], probe.QueryProbeFactory)
    assert copied['generator'].owner is copied['factory'].owner is copied['slow_factory'].owner
    assert copied['generator'].owner is not owner
    assert copied['generator'].owner.rows == owner.rows
    assert copied['generator'].generator._owned_topology_cache.export() == before_cache['fast_cache']
    assert engine._generator is original_generator and original_generator.sink is sink
    assert len(sink) == 2 and len(owner.rows) == 1
    sink[0]['snapshot'].trays.clear()
    assert engine.state.trays
    assert routing_cache_state(engine) == before_cache


@pytest.mark.parametrize('recovery_fails', [False, True])
def test_label_serialization_failure_retains_physical_outcome_or_explicit_recovery_error(tmp_path, monkeypatch, recovery_fails):
    from scripts.experiments.ics_circulation_v3 import run_same_zone_labels as runner
    (tmp_path / 'pilot').mkdir()
    marker = {'status': 'controller_quiescent', 'result': {'actual_physics': 'must retain'},
              'searches': [{'time': 4, 'work': 17}], 'cpu_seconds': 0.125}
    row = dict(request_key='independent_fault', scene='cross_cycle', candidate=0,
               mode='forced', cohort='new_policy_onpolicy')
    monkeypatch.setattr(runner, 'verify', lambda *_: {})
    monkeypatch.setattr(runner, 'load_payload', lambda *_: ({}, {'bound': 'metadata'}))
    monkeypatch.setattr(runner, 'run_label_branch', lambda *args, **kwargs: marker)
    write_json = runner.write_new_json

    def broken_raw(path, *_):
        path.write_bytes(b'partial gzip retained')
        raise OSError('injected raw serialization failure')

    def maybe_broken_recovery(path, value):
        if recovery_fails and '.recovery.' in path.name:
            raise OSError('injected recovery serialization failure')
        return write_json(path, value)

    monkeypatch.setattr(runner, 'write_gzip', broken_raw)
    monkeypatch.setattr(runner, 'write_new_json', maybe_broken_recovery)
    result = runner.evaluate(tmp_path, 'pilot', row)
    assert result['status'] == 'invocation_failure'
    assert result['actual_physical_call'] is True
    assert result['physical_result_status'] == 'controller_quiescent'
    assert result['invocation_cpu_seconds'] >= 0
    assert (tmp_path / 'pilot/independent_fault.json.gz').read_bytes() == b'partial gzip retained'
    if recovery_fails:
        assert result['recovery_error']['message'] == 'injected recovery serialization failure'
    else:
        recovery = json.loads((tmp_path / result['recovered_outcome_file']).read_text())
        assert recovery['outcome'] == marker
    failures = list((tmp_path / 'pilot').glob('*.failure.json'))
    assert len(failures) == 1 and json.loads(failures[0].read_text())['status'] == 'invocation_failure'


def test_query_partial_pickle_is_not_retried_and_cannot_block_completed_collection_recovery(tmp_path, monkeypatch):
    from scripts.experiments.ics_circulation_v3 import run_same_zone_labels as runner
    from scripts.experiments.ics_circulation_v3 import same_zone_query_probe as probe
    engine = _engine(future=False)
    scene = SimpleNamespace(name='cross_cycle', initial=engine.state.clone(),
                            forecasts=(), future_bags=(), horizon=2)
    marker = {'status': 'controller_quiescent', 'result': {'actual_physics': 'finished'},
              'searches': [{'time': 0, 'work': 23}], 'cpu_seconds': 0.25}
    monkeypatch.setattr(runner, 'verify', lambda *_: {})
    monkeypatch.setattr(runner, 'exact_original_scene', lambda *_: scene)
    monkeypatch.setattr(runner, 'run_cycle', lambda *args, **kwargs: marker)
    monkeypatch.setattr(probe, 'install_query_probe', lambda engine, sink: sink.append({'raw_query': 'retain'}))
    original_dump, attempted_paths = runner.pickle.dump, []

    def partial_query_dump(value, stream, **kwargs):
        attempted_paths.append(stream.name)
        if str(stream.name).endswith('q00000.pkl'):
            stream.write(b'partial query retained')
            raise OSError('injected first query pickle failure')
        return original_dump(value, stream, **kwargs)

    monkeypatch.setattr(runner.pickle, 'dump', partial_query_dump)
    result = runner.collect_scene(tmp_path, 'cross_cycle')
    assert result['status'] == 'invocation_failure' and result['actual_physical_call'] is True
    partial = tmp_path / 'collections/cross_cycle/queries/q00000.pkl'
    assert partial.read_bytes() == b'partial query retained'
    assert attempted_paths.count(str(partial)) == 1
    recovery = json.loads((tmp_path / result['recovered_outcome_file']).read_text())
    assert recovery['outcome'] == marker
    with (tmp_path / result['recovered_queries_file']).open('rb') as stream:
        assert pickle.load(stream) == [{'raw_query': 'retain'}]
    assert result['recovery_errors'] == [] and result['invocation_cpu_seconds'] >= 0

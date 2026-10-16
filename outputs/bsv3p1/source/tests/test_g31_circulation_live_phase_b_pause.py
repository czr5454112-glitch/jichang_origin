"""Small fake-state checks only; no native or full physical-model evaluation."""
import copy
from types import FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import public_live_obligation_phase_b_pause as module
from scripts.experiments.g31_ics_circulation import live_obligation_phase_b_support as support


def private_decide(function):
    return FunctionType(function.__code__, {
        **function.__globals__, 'policy': SimpleNamespace(local_target=lambda *_: None),
    }, function.__name__, function.__defaults__, function.__closure__)


class Fake(module.Projection):
    def __init__(self, *, phase='first_reuse_route', known=True, retry=False, recorder=None):
        self._phase_b_recorder = recorder
        self.time = 8.69
        self.owner = 'B' if phase == 'first_reuse_route' else 'A'
        pending = {'phase': phase, 'at': 8.65, 'deadline': 8.73, 'request_id': 'r',
                   'root': 'phase-root', 'trigger_tray': {'tray_id': 'L'},
                   'peer_message': 'peer', 'recollection_index': 0, 'policy_quiet_since': 8.65}
        self.owner_state = {self.owner: {'pending': pending, 'quiet': 0.}}
        row = {'ack': {'status': 'delivered'}, 'request': {'request_id': 'r'}}
        self.client_rows = {'r': row}
        self.events = [(9., 6, 1, 'projected_message_ack', (row,))]
        self.sequence = 1
        self.world = SimpleNamespace(engine=self, entries={'L': {'at': 8.1}})
        self.collection_trace = []
        self.unknown_phases = []
        self.action = {'return_delay': 7.84, 'later_action': 'prefer_8'}
        self.returns = 0
        self.jobs = {'reuse1': {'origin': 7}}
        self.demand_inbox = {self.owner: ('reuse1',)}
        self.choice_jobs = set()
        self.nodes = {8: {'capacity': 1}}
        self.actions = []
        self.collect_calls = []
        self.information = {'status': 'conditional_validated_later_v3_data' if known else 'unknown',
                            'bundle': {'trays': {'L': {'service_ready_at': 8.75}}}}
        self.screen = {'status': 'conditional_retry_admissible' if retry else 'not_admitted',
                       'retained_own_service_bound': 8.75}
        self.view = {'owner_id': self.owner, 'now': self.time, 'trays': [{'tray_id': 'L'}]}

    def collect(self, owner, pending):
        self.collect_calls.append((owner, pending['request_id']))
        return self.information, self.screen, self.view

    def publish(self, owner, phase):
        self.actions.append(('publish', owner, phase))
        return {'request': {'request_id': 'fresh'}}

    def schedule(self, *args):
        self.sequence += 1
        self.events.append(args)

    def request(self, *args):
        self.actions.append(('request', args, self.action['return_delay']))

    def occupancy(self, node):
        return 0

    def submit_preference(self, *args):
        self.actions.append(('preference', args))


def visible(engine):
    return {key: value for key, value in engine.__dict__.items()
            if key not in ('_phase_b_recorder', 'world')}


@pytest.mark.parametrize('phase,known,retry', [
    ('first_return', True, False), ('first_return', False, False),
    ('first_reuse_route', True, False), ('first_reuse_route', False, False),
    ('first_return', False, True), ('first_reuse_route', False, True),
])
def test_original_decide_and_hook_have_same_normal_effects(phase, known, retry):
    recorder = module.PointRecorder()
    left = Fake(phase=phase, known=known, retry=retry)
    right = Fake(phase=phase, known=known, retry=retry, recorder=recorder)
    private_decide(module.lazy.original.Projection.decide)(left, left.owner)
    private_decide(module.Projection.decide)(right, right.owner)
    assert visible(left) == visible(right)
    assert left.world.entries == right.world.entries
    assert len(recorder.points) == 1
    point = recorder.points[0]
    snapshot, pending, info, screen, view = point.copied_state()
    assert pending is snapshot.owner_state[right.owner]['pending']
    assert snapshot.world.engine is snapshot
    assert snapshot.events[0][4][0] is snapshot.client_rows['r']
    assert snapshot._phase_b_recorder is None
    assert snapshot.collection_trace == [] and snapshot.actions == []
    assert snapshot.collect_calls == [(right.owner, 'r')]
    assert info is snapshot.information and screen is snapshot.screen and view is snapshot.view
    assert point.description()['resumable'] is False
    with pytest.raises(ValueError, match='resume_not_implemented'):
        point.resume()


def test_snapshot_and_returned_copies_do_not_mutate_live_graph_or_each_other():
    recorder = module.PointRecorder()
    engine = Fake(recorder=recorder)
    private_decide(module.Projection.decide)(engine, engine.owner)
    snapshot, pending, info, _, _ = recorder.points[0].copied_state()
    pending['at'] = -1.
    snapshot.client_rows['r']['ack']['status'] = 'fabricated'
    info['status'] = 'fabricated'
    snapshot.world.entries['L']['at'] = -2.
    again = recorder.points[0].copied_state()
    assert again[1]['at'] == 8.65
    assert again[0].client_rows['r']['ack']['status'] == 'delivered'
    assert engine.client_rows['r']['ack']['status'] == 'delivered'
    assert again[2]['status'] == engine.information['status'] == 'conditional_validated_later_v3_data'
    assert engine.world.entries['L']['at'] == 8.1


def test_prior_snapshots_are_not_recursively_cloned():
    recorder = module.PointRecorder()
    engine = Fake(recorder=recorder)
    class CannotCopy:
        def __deepcopy__(self, memo):
            raise AssertionError('prior snapshot copied')
    recorder._points.append(CannotCopy())
    private_decide(module.Projection.decide)(engine, engine.owner)
    assert len(recorder.points) == 2
    assert recorder.points[1].copied_state()[0]._phase_b_recorder is None


@pytest.mark.parametrize('condition', ['no_pending', 'quiet', 'awaiting_delivery'])
def test_no_hook_before_original_collect(condition):
    recorder = module.PointRecorder()
    engine = Fake(recorder=recorder)
    if condition == 'no_pending':
        engine.owner_state[engine.owner]['pending'] = None
    elif condition == 'quiet':
        engine.owner_state[engine.owner]['quiet'] = 9.
    else:
        engine.client_rows['r']['ack'] = None
    private_decide(module.Projection.decide)(engine, engine.owner)
    assert recorder.points == () and engine.collect_calls == []


def test_no_recorder_is_original_effects_without_copies():
    left, right = Fake(), Fake()
    private_decide(module.lazy.original.Projection.decide)(left, left.owner)
    private_decide(module.Projection.decide)(right, right.owner)
    assert visible(left) == visible(right)


def test_source_proof_and_original_run_are_unchanged():
    proof = module.source_proof()
    assert proof['inserted_statements'] == 1 and proof['inverse_AST_exact']
    assert proof['numeric_expressions_added'] == 0
    assert module.Projection.run is module.lazy.Projection.run
    assert module.Projection.collect is module.lazy.Projection.collect
    proof['inverse_AST_exact'] = False
    assert module.source_proof()['inverse_AST_exact']


def test_pending_copy_cannot_masquerade_as_live_pending():
    recorder = module.PointRecorder()
    engine = Fake(recorder=recorder)
    with pytest.raises(ValueError, match='pending_alias'):
        recorder._capture(engine, engine.owner, copy.deepcopy(engine.owner_state[engine.owner]['pending']),
                          engine.information, engine.screen, engine.view)


def test_inventory_rejects_forged_context_label():
    assert support.inspect_supplied_context({'status': 'conditional_validated_later_v3_data'})['status'] == 'unknown'


def test_inventory_still_unknown_restart_even_when_original_guards_accept(monkeypatch):
    # Stub only the prior guard for this inventory-shape unit test; this is not
    # native acceptance or a claim that the supplied synthetic body passed it.
    validated = {'status': 'conditional_validated_later_v3_data', 'bundle': {
        'jobs': {'loaded': {}}, 'trays': {'L': {}}, 'resources': {'0': {}},
        'completed_prefix': {'loaded': 6.},
    }}
    monkeypatch.setattr(support.context, 'revalidate', lambda _: copy.deepcopy(validated))
    class Context:
        def audit_copy(self):
            return {'sha256': 'unit-test-only', 'payload': {
                'phase': 'first_reuse_route', 'owner': 'B', 'at': 8.69}}
    result = support.inspect_supplied_context(Context())
    assert result['restart_status'] == 'unknown_missing_model_history'
    assert not result['native_delivery_verified'] and not result['model_history_coverage_certified']
    assert any('opaque IDs' in item for item in result['future_filter_requirements'])

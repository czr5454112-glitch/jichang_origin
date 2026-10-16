"""Source splits and tiny fake-state control-flow tests; no real prediction."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_conditional_continuation as c
from test_g31_circulation_live_phase_b_pause import Fake, private_decide, visible


def test_source_splits_and_complete_defining_globals():
    proof = c.source_proof()
    assert all(proof[key] for key in ('decide_inverse_AST', 'activate_inverse_AST', 'run_inverse_AST',
                                     'accepted_lazy_code_shape', 'accepted_generated_run_code_shape',
                                     'complete_defining_globals'))
    assert not proof['physical_handler_statements_changed']
    original = c.lazy.original.Projection.decide.__globals__
    for name in ('decide_prefix', 'decide_tail'):
        assert all(c.PARTS[name].__globals__[key] is value for key, value in original.items())
    proof['same_action_only'] = False
    assert c.source_proof()['same_action_only']


@pytest.mark.parametrize('phase,known,retry', [
    ('first_return', True, False), ('first_return', False, False), ('first_return', False, True),
    ('first_reuse_route', True, False), ('first_reuse_route', False, False), ('first_reuse_route', False, True),
])
def test_actual_decide_split_matches_unsplit_on_small_fake_state(phase, known, retry):
    a, b = Fake(phase=phase, known=known, retry=retry), Fake(phase=phase, known=known, retry=retry)
    private_decide(c.lazy.original.Projection.decide)(a, a.owner)
    state = private_decide(c.PARTS['decide_prefix'])(b, b.owner)
    assert state is not None
    assert b.collection_trace == [] and b.actions == []
    private_decide(c.PARTS['decide_tail'])(b, b.owner, *state)
    assert visible(a) == visible(b)


class Engine:
    def __init__(self, events):
        self.time = .11
        self.action = {'same_action': 1}
        self.events = list(events)
        self.trace = []
        self.activation_trace = []
        self.activated_boundaries = set()
        self.completed = {'job': 1.}
        self.client_rows = {'r': {'terminal': False}}
        self.world = SimpleNamespace(e=self)
        self.owner_state = {o: {'pending': {'owner': o}} for o in ('A', 'B')}
        self.info = {o: {'owner': o} for o in ('A', 'B')}
        self.view = {o: {'owner': o} for o in ('A', 'B')}
        self.initializations = 0

    def before_event(self, kind, args): self.trace.append(('before', kind))
    def protocol_event(self, kind, args):
        self.trace.append(('protocol', kind))
        return kind == 'projected_dummy'
    def after_event(self, kind, args): self.trace.append(('after', kind))


@pytest.fixture
def small(monkeypatch):
    original = dict(c.PARTS)
    def initialize(engine):
        engine.initializations += 1
        return 0
    def prefix(engine, owner):
        identity = (engine.time, owner)
        if identity in engine.activated_boundaries: return None
        engine.activated_boundaries.add(identity)
        engine.trace.append(('activate_prefix', owner))
        return (engine.owner_state[owner],)
    def decide(engine, owner):
        engine.trace.append(('collect', owner))
        s = engine.owner_state[owner]
        if s['pending'] is None: return None
        return s, s['pending'], engine.info[owner], {'status': 'unit_only'}, engine.view[owner]
    def decision_tail(engine, owner, s, p, info, screen, view):
        assert s is engine.owner_state[owner] and p is s['pending']
        assert info is engine.info[owner] and view is engine.view[owner]
        engine.trace.append(('decision_tail', owner)); s['pending'] = None
    def activation_tail(engine, owner, s):
        assert s is engine.owner_state[owner]
        engine.trace.append(('activate_tail', owner))
    def final(engine, count):
        engine.trace.append(('finish', count))
        return {'status': 'unit_finished', 'count': count, 'time': engine.time, 'trace': copy.deepcopy(engine.trace)}
    monkeypatch.setattr(c, 'Projection', Engine)
    monkeypatch.setattr(c, 'PARTS', {**original, 'initialize': initialize, 'activate_prefix': prefix,
        'decide_prefix': decide, 'decide_tail': decision_tail, 'activate_tail': activation_tail,
        'physical': lambda e, k, a: e.trace.append(('physical', k)), 'final': final})
    def make(events, count=0):
        engine = Engine(events)
        frames = {'pc': 'next_event', 'run': {'initialized': True, 'count': count, 'event': None,
                  'handler_pc': 'next_event'}, 'tick': None, 'activate': None, 'decide': None}
        return c.Continuation(engine, frames, c.lazy.original.context.encoded(engine.action))
    return make


def complete(state):
    value = c.advance_to_collection_or_terminal(state)
    for _ in range(10):
        if type(value) is not c.Continuation: return value
        value = c.resume_same_action(value)
    raise AssertionError('tiny fixture did not finish')


def test_a_then_b_remainders_finish_before_next_heap_pop(small):
    initial = small([(1., 99, 1, 'tick', ()), (1., 100, 2, 'projected_dummy', ())])
    a = c.advance_to_collection_or_terminal(initial)
    assert a._frames['tick'] == {'owners': ('A', 'B'), 'index': 0}
    assert a._frames['run']['count'] == 1 and len(a._engine.events) == 1
    b = c.resume_same_action(a)
    assert b._frames['tick']['index'] == 1 and b._frames['decide']['owner'] == 'B'
    assert b._frames['run']['count'] == 1 and len(b._engine.events) == 1
    result = c.resume_same_action(b)
    assert result['trace'] == [('before', 'tick'), ('protocol', 'tick'), ('activate_prefix', 'A'),
        ('collect', 'A'), ('decision_tail', 'A'), ('activate_tail', 'A'), ('activate_prefix', 'B'),
        ('collect', 'B'), ('decision_tail', 'B'), ('activate_tail', 'B'), ('after', 'tick'),
        ('before', 'projected_dummy'), ('protocol', 'projected_dummy'), ('after', 'projected_dummy'), ('finish', 2)]


def test_single_owner_activation_appends_once_and_tick_dedup_remains(small):
    state = small([(1., 99, 1, 'owner_activation', ('A', 'ready')), (1., 99, 2, 'tick', ())])
    engine = state._engine
    result = complete(state)
    assert engine.activation_trace == [{'at': 1., 'owner': 'A', 'reason': 'ready'}]
    assert result['trace'].count(('activate_prefix', 'A')) == 1
    assert result['trace'].count(('decision_tail', 'A')) == 1
    assert result['trace'].count(('decision_tail', 'B')) == 1
    assert result['count'] == 2


def test_same_timestamp_priority_and_sequence_are_not_regenerated(small):
    state = small([(1., 99, 1, 'tick', ()), (1., 99, 2, 'owner_activation', ('A', 'a')),
                   (1., 100, 3, 'owner_activation', ('B', 'b'))])
    engine = state._engine; result = complete(state)
    assert engine.activation_trace == [{'at': 1., 'owner': 'A', 'reason': 'a'}, {'at': 1., 'owner': 'B', 'reason': 'b'}]
    assert result['trace'].count(('decision_tail', 'A')) == result['trace'].count(('decision_tail', 'B')) == 1
    assert result['count'] == 3


def test_current20000_allowed_next20001_bypasses_hooks_and_finish(small):
    state = small([(1., 99, 1, 'tick', ()), (2., 99, 2, 'projected_dummy', ())], count=19999)
    engine = state._engine; result = complete(state)
    assert result == {'status': 'unknown_event_budget', 'completion': {'job': 1.}}
    assert engine.time == 2. and engine.events == []
    assert ('after', 'tick') in engine.trace
    assert not any(row[0] == 'finish' or row == ('before', 'projected_dummy') for row in engine.trace)


def test_horizon_event_processed_next_event_popped_without_count_or_hook(small):
    state = small([(40., 99, 1, 'tick', ()), (40.0001, 99, 2, 'projected_dummy', ())])
    engine = state._engine; result = complete(state)
    assert result['count'] == 1 and result['time'] == 40.0001 and engine.events == []
    assert ('before', 'projected_dummy') not in result['trace']


def test_empty_heap_finishes_without_reinitialization(small):
    state = small([])
    assert c.advance_to_collection_or_terminal(state)['count'] == 0
    assert state._engine.initializations == 0


def test_initialization_occurs_once_only(monkeypatch, small):
    engine = Engine([(1., 99, 1, 'tick', ())])
    monkeypatch.setattr(c, '_build_engine', lambda *_: engine)
    state = c.start_conditional(object(), {'unit': 'unused'})
    assert engine.initializations == 1
    complete(state)
    assert engine.initializations == 1


def test_fork_preserves_frame_heap_client_and_world_aliases(small):
    state = small([(1., 99, 1, 'tick', ())])
    shared = state._engine.client_rows['r']
    state._engine.events.append((2., 99, 2, 'projected_dummy', (shared,)))
    point = c.advance_to_collection_or_terminal(state)
    fork = c.fork_conditional(point)
    engine, frame = fork._engine, fork._frames
    assert engine.world.e is engine
    assert frame['decide']['s'] is frame['activate']['s'] is engine.owner_state['A']
    assert frame['decide']['p'] is engine.owner_state['A']['pending']
    assert frame['decide']['info'] is engine.info['A']
    assert engine.events[0][4][0] is engine.client_rows['r']
    engine.client_rows['r']['terminal'] = True
    assert not point._engine.client_rows['r']['terminal']
    assert point._consumed is False


def test_consumed_wrong_pc_and_changed_action_reject(small):
    state = small([(1., 99, 1, 'tick', ())])
    with pytest.raises(ValueError, match='wrong_entry_program_counter'): c.resume_same_action(state)
    point = c.advance_to_collection_or_terminal(state)
    with pytest.raises(ValueError, match='consumed'): c.advance_to_collection_or_terminal(state)
    with pytest.raises(ValueError, match='consumed'): c.fork_conditional(state)
    point._engine.action['same_action'] = 2
    with pytest.raises(ValueError, match='changed_action'): c.resume_same_action(point)


def test_unknown_program_counter_rejects(small):
    state = small([]); state._frames['pc'] = 'inside_grant'
    with pytest.raises(ValueError, match='unsupported_program_counter'): c.advance_to_collection_or_terminal(state)


def test_original_caught_exception_scope_and_consumed_failure(monkeypatch, small):
    state = small([(1., 99, 1, 'tick', ())]); point = c.advance_to_collection_or_terminal(state)
    def fail(*_): raise ValueError('unit_guard')
    monkeypatch.setitem(c.PARTS, 'decide_tail', fail)
    result = c.resume_same_action(point)
    assert result['status'] == 'unknown' and result['reasons'] == ['conditional_projection:unit_guard']
    assert not any(row[0] == 'finish' for row in point._engine.trace)
    with pytest.raises(ValueError, match='consumed'): c.resume_same_action(point)


def test_uncaught_exception_is_not_silently_promoted(monkeypatch, small):
    point = c.advance_to_collection_or_terminal(small([(1., 99, 1, 'tick', ())]))
    def fail(*_): raise RuntimeError('unit_uncaught')
    monkeypatch.setitem(c.PARTS, 'decide_tail', fail)
    with pytest.raises(RuntimeError, match='unit_uncaught'): c.resume_same_action(point)
    assert point._consumed

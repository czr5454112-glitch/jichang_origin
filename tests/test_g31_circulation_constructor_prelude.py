"""Unexecuted focused synthetic tests; no C/native/model/raw or bare helpers."""
import ast
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import constructor_prelude_instrumentation as p


class Clock:
    def __init__(self, bad_at=None):
        self.count = 0
        self.bad_at = bad_at
    def __call__(self):
        self.count += 1
        if self.count == self.bad_at:
            raise RuntimeError('synthetic diagnostic clock')
        return self.count * 10


def fixture(*, constructor_error=None, boundary_error=None, clock=None):
    calls, original_rows, diagnostic_rows = [], [], []
    class Exact:
        def __init__(self, *args):
            calls.append(args)
            if constructor_error is not None:
                raise constructor_error
    class Boundary:
        calls = 0
        def check(self):
            self.calls += 1
            if boundary_error is not None:
                raise boundary_error
    root = SimpleNamespace(request_id='synthetic', started_ns=1, deadline_ns=100000001, cutoff_ns=60000001)
    timer = p.original.ConstructorTimer(Exact, original_rows, clock or Clock())
    timer.boundary = Boundary()
    bound = p.bind_timer(timer, diagnostic_rows)
    args = (object(), object(), root, {})
    return bound, args, calls, original_rows, diagnostic_rows, Exact


def test_complete_inverse_original_clocks_and_full_namespace():
    value, _, _, _, _, _ = fixture()
    proof = p.source_proof(value)
    assert proof['complete_inverse_AST_exact']
    assert p._dump(p._inverse(p._transformed())) == p._dump(p._original_tree())
    assert value.function.__defaults__ is p._CALL.__defaults__
    assert value.function.__kwdefaults__ is p._CALL.__kwdefaults__
    assert value.function.__closure__ is p._CALL.__closure__
    assert value.function.__code__.co_freevars == p._CALL.__code__.co_freevars
    assert set(value.function.__globals__) == set(p._CALL.__globals__) | set(p._HOOKS)
    assert all(value.function.__globals__[k] is v for k, v in p._CALL.__globals__.items())
    assert value.function.__globals__['_prelude_finish'].__self__ is value.probe
    assert not proof['Provider_or_campaign_integration']


def test_minimum_intervals_original_exact_result_and_explicit_extra_guard():
    bound, args, calls, original, diagnostic, exact = fixture()
    result = bound.call(*args)
    assert type(result) is exact and calls == [args]
    assert bound.timer.boundary.calls == 1
    assert original == [{'ordinal': 0, 'root': vars(args[2]).copy(), 'status': 'constructor_returned',
        'error_type': None, 'started_ns': 60, 'finished_ns': 70}]
    row = diagnostic[0]
    assert row['status'] == 'complete_scalar_intervals'
    assert (row['binding_started_ns'], row['binding_finished_ns']) == (10, 20)
    assert (row['boundary_started_ns'], row['boundary_finished_ns'], row['metadata_finished_ns']) == (30, 40, 50)
    assert row['constructor_started_ns'] == original[0]['started_ns']
    assert row['constructor_finished_ns'] == original[0]['finished_ns']
    assert row['diagnostic_finished_ns'] == 80
    assert row['intervals_ns'] == dict.fromkeys(('original_boundary_check', 'root_fields_row_and_append',
        'metadata_to_original_clock_gap', 'existing_exact_constructor', 'post_constructor_diagnostic_tail'), 10)
    assert sum(row['intervals_ns'].values()) == 80 - 30
    assert not bound.probe.failed and not bound.probe.errors


def test_sidecar_owns_only_scalar_metadata_not_any_runtime_reference():
    bound, args, _, original, diagnostic, _ = fixture()
    bound.call(*args)
    args[2].request_id = 'later mutation'
    original[0]['root']['request_id'] = 'other mutation'
    assert diagnostic[0]['root']['request_id'] == 'synthetic'
    forbidden = [*args, bound.timer, original[0], original[0]['root']]
    def walk(value):
        assert all(value is not item for item in forbidden)
        assert type(value) in (dict, list, str, int, bool, type(None))
        if type(value) is dict:
            for k, v in value.items(): walk(k); walk(v)
        elif type(value) is list:
            for item in value: walk(item)
    walk(diagnostic)


def test_multiple_calls_keep_original_and_diagnostic_ordinals():
    bound, args, calls, original, diagnostic, _ = fixture()
    bound.call(*args); bound.call(*args)
    assert len(calls) == len(original) == len(diagnostic) == 2
    assert [r['ordinal'] for r in diagnostic] == [0, 1]
    assert [r['original_constructor_ordinal'] for r in diagnostic] == [0, 1]
    assert p.source_proof(bound)['complete_inverse_AST_exact']


def test_original_boundary_error_wins_before_metadata_and_constructor():
    error = ValueError('original boundary refused')
    bound, args, calls, original, diagnostic, _ = fixture(boundary_error=error)
    with pytest.raises(ValueError) as caught:
        bound.call(*args)
    assert caught.value is error and calls == original == []
    row = diagnostic[0]
    assert row['original_exception_type'] == 'ValueError'
    assert row['boundary_finished_ns'] is row['metadata_finished_ns'] is row['root'] is None
    assert row['intervals_ns'] is None and row['status'] != 'complete_scalar_intervals'


def test_original_constructor_error_and_exact_interval_are_retained():
    error = RuntimeError('original exact constructor')
    bound, args, calls, original, diagnostic, _ = fixture(constructor_error=error)
    with pytest.raises(RuntimeError) as caught:
        bound.call(*args)
    assert caught.value is error and len(calls) == 1
    assert original[0]['status'] == 'constructor_raised'
    assert (original[0]['started_ns'], original[0]['finished_ns']) == (60, 70)
    assert diagnostic[0]['original_exception_type'] == 'RuntimeError'
    assert diagnostic[0]['intervals_ns']['existing_exact_constructor'] == 10
    assert diagnostic[0]['status'] != 'complete_scalar_intervals'


def test_wrong_exact_return_type_still_rejected():
    class Foreign:
        def __new__(cls, *args): return object()
    rows, output = [], []
    timer = p.original.ConstructorTimer(Foreign, rows, Clock())
    bound = p.bind_timer(timer, output)
    with pytest.raises(ValueError, match='constructor_wrong_return_type'):
        bound.call(None, None, object(), {})
    assert rows[0]['failure_stage'] == 'exact_return_type'
    assert output[0]['original_exception_type'] == 'ValueError'
    assert output[0]['status'] != 'complete_scalar_intervals'


def test_original_metadata_append_error_prevents_constructor():
    error = MemoryError('original append')
    class RefusingRows(list):
        def append(self, row): raise error
    calls, output = [], []
    class Exact:
        def __init__(self, *args): calls.append(args)
    original = RefusingRows()
    timer = p.original.ConstructorTimer(Exact, original, Clock())
    bound = p.bind_timer(timer, output)
    with pytest.raises(MemoryError) as caught:
        bound.call(None, None, object(), {})
    assert caught.value is error and not calls and not original
    assert output[0]['metadata_finished_ns'] is None
    assert output[0]['original_exception_type'] == 'MemoryError'


@pytest.mark.parametrize('bad_at', [1, 2, 3, 4, 5, 8])
def test_extra_clock_failure_does_not_replace_original_result_or_invent_zero(bad_at):
    bound, args, calls, original, diagnostic, exact = fixture(clock=Clock(bad_at))
    assert type(bound.call(*args)) is exact
    assert len(calls) == len(original) == 1 and bound.probe.failed
    assert diagnostic[0]['status'] != 'complete_scalar_intervals'
    assert any(v is None for k, v in diagnostic[0].items() if k.endswith('_ns') and k != 'intervals_ns')


def test_final_clock_failure_does_not_mask_original_constructor_exception():
    error = LookupError('original failure')
    bound, args, _, _, diagnostic, _ = fixture(constructor_error=error, clock=Clock(8))
    with pytest.raises(LookupError) as caught:
        bound.call(*args)
    assert caught.value is error and bound.probe.failed
    assert diagnostic[0]['original_exception_type'] == 'LookupError'


def test_sidecar_allocation_failure_keeps_primary_exception_private_hook_only():
    # Exercise a failure in the hook itself. Deliberately bypass the outer
    # binding boundary after injecting a fake sink; this is not a live binder.
    error = RuntimeError('original constructor error')
    bound, args, _, _, _, _ = fixture(constructor_error=error)
    class Refuse(list):
        def append(self, row): raise MemoryError('synthetic sidecar allocation')
    bound.probe.rows = Refuse()
    with pytest.raises(RuntimeError) as caught:
        bound.function(bound.timer, *args)
    assert caught.value is error and bound.probe.failed
    assert bound.probe.errors[-1]['phase'] == 'final_scalar_sidecar'


@pytest.mark.parametrize('which', ['clock', 'exact_class', 'original_boundary', 'new_function',
    'probe_rows', 'private_hook', 'old_global'])
def test_warm_new_binding_rejects_mutation_before_original_path(which):
    bound, args, calls, original, diagnostic, _ = fixture()
    if which == 'clock': bound.timer.clock = Clock()
    elif which == 'exact_class': bound.timer.exact_class = object
    elif which == 'original_boundary': bound.timer.boundary = object()
    elif which == 'new_function': bound.call.function = lambda *args: object()
    elif which == 'probe_rows': bound.probe.rows = []
    elif which == 'private_hook': bound.function.__globals__['_prelude_finish'] = lambda *args: None
    else: bound.function.__globals__['_root_fields'] = lambda root: {}
    with pytest.raises(ValueError, match='static_'):
        bound.call(*args)
    assert not calls and not original
    assert all(r['status'] == 'unknown_instrumentation_binding_rejected' for r in diagnostic)


@pytest.mark.parametrize('kind', ['extra_statement', 'moved_original_clock', 'changed_raise', 'changed_hook'])
def test_inverse_proof_rejects_other_edits(kind):
    tree = p._transformed()
    outer = tree.body[0].body[-1]
    if kind == 'extra_statement': outer.body.append(ast.Pass())
    elif kind == 'moved_original_clock': outer.body[6], outer.body[7] = outer.body[7], outer.body[6]
    elif kind == 'changed_raise': outer.handlers[0].body[-1] = ast.Pass()
    else: outer.finalbody[0].value.func.id = 'other_hook'
    with pytest.raises(ValueError): p._inverse(tree)


def test_no_original_program_or_timer_mutation_by_binding():
    bound, args, _, _, _, _ = fixture()
    original_code = p.original.ConstructorTimer.__call__.__code__
    before = {k: id(v) for k, v in p._CALL.__globals__.items()}
    boundary = bound.timer.boundary
    bound.call(*args)
    assert p.original.ConstructorTimer.__call__.__code__ is original_code
    assert {k: id(v) for k, v in p._CALL.__globals__.items()} == before
    assert bound.timer.boundary is boundary
    assert not set(p._HOOKS).intersection(p._CALL.__globals__)


def test_new_binding_boundary_replacement_rejected():
    bound, args, calls, original, diagnostic, _ = fixture()
    bound.call.boundary = SimpleNamespace(check=lambda: None)
    with pytest.raises(ValueError, match='instrumentation_boundary_identity'):
        bound.call(*args)
    assert not calls and not original
    assert diagnostic[0]['status'] == 'unknown_instrumentation_binding_rejected'


def test_underlying_hook_code_change_rejected_before_original(monkeypatch):
    bound, args, calls, original, diagnostic, _ = fixture()
    def replacement(self, timer, start, boundary_end, metadata_end, row, primary):
        return None
    monkeypatch.setattr(p._Probe.finish, '__code__', replacement.__code__)
    with pytest.raises(ValueError, match='static_function_changed'):
        bound.call(*args)
    assert not calls and not original
    assert diagnostic[0]['status'] == 'unknown_instrumentation_binding_rejected'


def test_real_bound_chain_classcell_and_dynamic_fake_session_rejection_stay_original():
    # The provider is explicitly Python-only. No C identity or native session
    # is synthesized, and the real constructor must reject the fake session.
    runtime = p.original
    publisher = runtime.static.owned.publisher
    functions = publisher.reference._bind_provider(publisher.owned.normalization.normalize)
    live = runtime.static.owned._compose(publisher._compose(functions))
    accepted = runtime.compose(live, {'constructors': []})
    before_class = accepted.static_binding.ActualAdvanceChain
    before_closure = before_class.__init__.__closure__
    before_drain = accepted.static_binding._actual_root_drain
    bound = p.bind_timer(accepted.constructor_timer, [])
    root = object.__new__(accepted.static_binding.CapturedRequest)
    root.session, root.client, root.native, root.accepted = object(), object(), object(), {}
    root.request_id, root.started_ns = 'synthetic', 1
    root.deadline_ns, root.cutoff_ns = 100000001, 60000001
    with pytest.raises(ValueError, match='missing_actual_accepted_session'):
        bound.call(root.session, root.client, root, {})
    assert bound.timer.exact_class is before_class
    assert before_class.__init__.__closure__ is before_closure
    assert before_drain.__globals__['ActualAdvanceChain'] is before_class
    assert bound.probe.rows[0]['original_exception_type'] == 'ValueError'
    assert bound.probe.rows[0]['status'] != 'complete_scalar_intervals'


@pytest.mark.parametrize('rows', [None, (), {}, [1]])
def test_new_sidecar_requires_fresh_builtin_list(rows):
    with pytest.raises(ValueError, match='fresh_exact_diagnostic_rows'):
        p.bind_timer(p.original.ConstructorTimer(object, [], Clock()), rows)


def test_declared_stub_does_not_load_or_install_provider():
    bound, _, _, _, _, _ = fixture()
    proof = p.source_proof(bound)
    assert proof['actual_native_C_or_model_execution'] is False
    assert proof['Provider_or_campaign_integration'] is False
    assert proof['per_root_disk_write'] is False
    assert proof['complete100ms_certified'] is False

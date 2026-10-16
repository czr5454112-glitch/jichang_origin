"""Unexecuted synthetic composition tests; no C/model/native/raw authority."""
from types import FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import single_capture_constructor_prelude_runtime as r


def _run_source(session, client, root, policies):
    return ActualAdvanceChain(session, client, root, policies)


def _branch_source(session, client, root, policies):
    return run_continuation(session, client, root, policies)


class Clock:
    def __init__(self): self.value = 0
    def __call__(self):
        self.value += 100
        return self.value


def synthetic(monkeypatch, error=None):
    """Explicitly fake accepted-composition seam, never a verified provider."""
    calls, accepted_values = [], []
    clock = Clock()
    def fake_compose(live, record, *, clock):
        class Exact:
            def __init__(self, *args):
                calls.append(args)
                if error is not None: raise error
        timer = r.previous.ConstructorTimer(Exact, record['constructors'], clock)
        run = FunctionType(_run_source.__code__, {**globals(),
            'ActualAdvanceChain': timer, 'publish_root': object()}, 'run')
        run._source_proof = {'synthetic': True}
        branch = FunctionType(_branch_source.__code__, {**globals(),
            'run_continuation': run}, 'branch')
        value = SimpleNamespace(static_binding=live, constructor_timer=timer,
            run_continuation=run, run_branch=branch, original_branch=branch)
        timer.boundary = r.previous.static._ProgramBoundary(
            functions=(run, branch), classes=(r.previous.ConstructorTimer,),
            locations=((timer, 'exact_class'), (timer, 'rows'), (timer, 'clock')),
            containers=(vars(value),))
        accepted_values.append(value)
        return value
    def fake_proof(value):
        value.constructor_timer.boundary.check()
        return {'synthetic_not_native_or_C': True}
    monkeypatch.setattr(r.previous, 'compose', fake_compose)
    monkeypatch.setattr(r.previous, 'composition_proof', fake_proof)
    original, diagnostic = {'constructors': []}, {'rows': []}
    value = r.compose(SimpleNamespace(), original, diagnostic, clock=clock)
    root = SimpleNamespace(request_id='synthetic', started_ns=0,
        deadline_ns=100000000, cutoff_ns=60000000)
    args = (object(), object(), root, {})
    return value, args, calls, original, diagnostic, accepted_values


def test_private_paths_keep_original_timer_boundary_code_and_full_globals(monkeypatch):
    value, _, _, _, record, originals = synthetic(monkeypatch)
    accepted = originals[0]
    assert value.accepted is accepted
    assert value.constructor_timer is accepted.constructor_timer
    assert value.original_timer_boundary is accepted.constructor_timer.boundary
    assert value.run_continuation.__code__ is accepted.run_continuation.__code__
    assert value.run_branch.__code__ is accepted.run_branch.__code__
    r.previous.static.owned._delta(accepted.run_continuation, value.run_continuation,
        {'ActualAdvanceChain': value.prelude.call})
    r.previous.static.owned._delta(accepted.run_branch, value.run_branch,
        {'run_continuation': value.run_continuation})
    assert record['cold_status'] == 'returned'
    proof = r.composition_proof(value)
    assert proof['original_timer_boundary_identity_preserved']
    assert proof['third_warm_program_check_added'] is False
    assert proof['actual18_or_C_execution_established'] is False


@pytest.mark.parametrize('entry', ['run_continuation', 'run_branch'])
def test_both_actual_private_paths_reach_original_exact_constructor_and_diagnostics(monkeypatch, entry):
    value, args, calls, original, diagnostic, _ = synthetic(monkeypatch)
    result = getattr(value, entry)(*args)
    assert type(result) is value.constructor_timer.exact_class
    assert calls == [args]
    assert len(original['constructors']) == len(diagnostic['rows']) == 1
    before, after = original['constructors'][0], diagnostic['rows'][0]
    assert before['started_ns'] == after['constructor_started_ns']
    assert before['finished_ns'] == after['constructor_finished_ns']
    assert after['status'] == 'complete_scalar_intervals'
    assert r.composition_proof(value)['complete_new_guard_snapshot_prefix_by_identity']


@pytest.mark.parametrize('name', r._FIELDS)
def test_new_boundary_keeps_every_original_record_and_rejects_one_removed(monkeypatch, name):
    value, _, _, _, _, _ = synthetic(monkeypatch)
    merged, original, extra = value.guard.merged, value.guard.original, value.guard.extra
    r._snapshot_prefix(merged, original, extra)
    # At least one original or extension record exists in every snapshot kind.
    records = getattr(merged, name)
    assert records
    setattr(merged, name, records[1:])
    with pytest.raises(ValueError, match='complete_snapshot_prefix'):
        r.composition_proof(value)


@pytest.mark.parametrize('entry,key', [
    ('run_continuation', 'publish_root'), ('run_branch', 'run_continuation')])
def test_changed_new_function_globals_rejected_by_existing_new_binding_check(monkeypatch, entry, key):
    value, args, calls, original, diagnostic, _ = synthetic(monkeypatch)
    getattr(value, entry).__globals__[key] = object()
    # Directly exercise the exact installed constructor callable: arbitrary
    # hostile replacement of the caller itself is not a new sandbox promise.
    with pytest.raises(ValueError, match='static_defining_globals_changed'):
        value.prelude.call(*args)
    assert calls == original['constructors'] == []
    assert diagnostic['rows'][0]['status'] == 'unknown_instrumentation_binding_rejected'


def test_original_timer_boundary_replacement_cannot_pass_new_binding(monkeypatch):
    value, args, calls, _, _, _ = synthetic(monkeypatch)
    value.constructor_timer.boundary = r.previous.static._ProgramBoundary()
    with pytest.raises(ValueError, match='static_dependency_location_changed'):
        value.prelude.call(*args)
    assert not calls


def test_original_constructor_exception_and_old_rows_are_preserved(monkeypatch):
    error = RuntimeError('original synthetic constructor')
    value, args, calls, original, diagnostic, _ = synthetic(monkeypatch, error)
    with pytest.raises(RuntimeError) as caught:
        value.run_branch(*args)
    assert caught.value is error and len(calls) == 1
    assert original['constructors'][0]['status'] == 'constructor_raised'
    assert diagnostic['rows'][0]['original_exception_type'] == 'RuntimeError'
    assert diagnostic['rows'][0]['status'] != 'complete_scalar_intervals'


@pytest.mark.parametrize('bad', [None, {}, {'rows': ()}, {'rows': [1]}])
def test_only_fresh_exact_diagnostic_rows_are_accepted(bad):
    with pytest.raises(ValueError, match='prelude_fresh_lifetime_rows'):
        r.compose(None, {}, bad)


def test_new_failure_clock_cannot_replace_original_setup_exception(monkeypatch):
    error = LookupError('original setup')
    def fail(*args, **kwargs): raise error
    monkeypatch.setattr(r.previous, 'compose', fail)
    calls = []
    def clock():
        calls.append(None)
        if len(calls) > 1: raise RuntimeError('diagnostic clock')
        return 0
    with pytest.raises(LookupError) as caught:
        r.compose(None, {}, {'rows': []}, clock=clock)
    assert caught.value is error


def test_provider_keeps_original_close_failure_and_no_C_load_on_source_proof():
    assert r.Provider.close is r.previous.Provider.close
    assert r.Provider.failed is r.previous.Provider.failed
    proof = r.source_proof()
    assert proof['new_campaign_and_saved_verifier_supplied'] is False
    assert proof['C_native_model_or_actual18_execution'] is False
    assert proof['complete100ms_or_speed_claim'] is False

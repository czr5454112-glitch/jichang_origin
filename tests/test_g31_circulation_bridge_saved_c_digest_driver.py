"""Source/fixture-only driver draft. No C load or saved stream is opened."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import audit_bridge_saved_c_digest as d


def test_exact_old_flow_inverse_and_four_changes():
    source, proof = d.audit_source()
    assert proof['inverse_original_text_and_AST_exact'] is True
    assert proof['explicit_modifications'] == 4
    assert source.count('authority.begin(') == source.count('authority.finish(') == 1
    assert 'core.bind(plan, redirect, progress, candidate)' in source
    assert "result['replay']['api_rows'] == 37270" in source
    assert "result['same_policy_old001_complete_prefix']['rows'] == 27218" in source


def test_generated_audit_has_all_defining_globals_and_progress_identity():
    function = d.audit_function()
    original_globals = d.flow.audit.__globals__
    assert set(original_globals) <= set(function.__globals__)
    for name in ('Path', 'time', 'prior', 'r', 'base', 'require'):
        assert function.__globals__[name] is original_globals[name]
    assert function.__globals__['authority'] is d.authority
    assert d.audit_core().Progress is d.digest_core.previous.Progress
    assert d.audit_core().bind is d.digest_core.bind
    assert d.namespace()['MODULE'] == d.MODULE
    assert d.namespace()['LIMIT'] == 600.


def fixture(failure=None, counts=(37270, 27218)):
    events, exports = [], {}
    candidate = object()
    plan = {'source_before': {str(d.ROOT / 'example.py'): 'abc'}}

    def step(name):
        events.append(name)
        if failure == name:
            raise MemoryError(name)

    class Progress:
        def __init__(self, output):
            self.path = output / 'progress.jsonl'

        @contextmanager
        def stage(self, name):
            events.append(('stage_start', name))
            try:
                yield
            finally:
                events.append(('stage_end', name))

        def close(self): events.append('progress_close')
        def emit(self, *args, **kwargs): events.append(('emit', args, kwargs))

    class Redirect:
        def __init__(self, source, output): events.append(('redirect', source, output))
        def map_result(self, result):
            step('map_result')
            return result, {'exact': True}

    def write(path, value):
        assert path not in exports
        exports[path] = value
        events.append(('write', path.name))

    def verify(output, expected):
        step('verify_plan')
        assert expected == 'plan_sha'
        return plan

    def begin(pins):
        step('C_begin')
        assert pins == {'example.py': 'abc'}
        return candidate, {'complete_toolchain_and_runtime_entry_check': True}

    def finish(actual, pins):
        step('C_finish')
        assert actual is candidate and pins == {'example.py': 'abc'}
        return {'complete_toolchain_and_runtime_exit_check': True}

    def bind(actual_plan, redirect, progress, actual_candidate):
        step('bind')
        assert actual_plan is plan and actual_candidate is candidate
        def checker(directory):
            step('full_checker')
            assert directory == Path('saved_producer') / 'bridge'
            return {'replay': {'api_rows': counts[0]},
                    'same_policy_old001_complete_prefix': {'rows': counts[1]}}, {'unchanged_checks': True}
        return checker

    def runtime(value):
        step('runtime')
        assert value is plan
        return ['example.py']

    private_prior = SimpleNamespace(SOURCE=Path('saved_producer'), write_new=write,
        check_runtime=runtime, DerivedOutput=Redirect,
        current_cost_metadata=lambda result: (result, {'historical_budget_retained': True}))
    source, _ = d.audit_source()
    ns = {**d.namespace(), 'prior': private_prior, 'verify_plan': verify,
        'core': SimpleNamespace(Progress=Progress, bind=bind),
        'authority': SimpleNamespace(begin=begin, finish=finish),
        'base': SimpleNamespace(sha=lambda path: 'progress_sha')}
    exec(compile(source, '<synthetic_C_audit_flow>', 'exec'), ns)
    return ns['audit'], events, exports


def test_complete_mock_flow_C_identity_around_unchanged_checks(tmp_path):
    function, events, exports = fixture()
    function(tmp_path, 'plan_sha')
    assert [e for e in events if type(e) is str] == [
        'verify_plan', 'runtime', 'C_begin', 'bind', 'full_checker', 'map_result',
        'C_finish', 'verify_plan', 'runtime', 'progress_close']
    report = exports[tmp_path / 'report.json']
    assert report['status'] == 'passed_complete_saved_audit'
    assert report['result']['replay']['api_rows'] == 37270
    assert report['result']['same_policy_old001_complete_prefix']['rows'] == 27218
    assert report['C_encoder']['entry'] is exports[tmp_path / 'C_encoder_entry.json']
    assert report['C_encoder']['exit'] is exports[tmp_path / 'C_encoder_exit.json']
    assert report['C_encoder']['actual_direct_and_fallback_counts'] == 'not_instrumented_unknown'
    assert report['native_calls'] == report['predictions'] == 0
    assert report['original_campaign_status'] == 'timeout_preserved'


@pytest.mark.parametrize('stage', ['C_begin', 'bind', 'full_checker', 'C_finish'])
def test_resource_failure_is_not_retry_or_success(tmp_path, stage):
    function, events, exports = fixture(stage)
    with pytest.raises(MemoryError, match=stage): function(tmp_path, 'plan_sha')
    assert events.count(stage) == 1
    assert tmp_path / 'report.json' not in exports
    assert 'progress_close' in events
    if stage == 'C_begin': assert tmp_path / 'C_encoder_entry.json' not in exports
    if stage == 'C_finish': assert tmp_path / 'C_encoder_entry.json' in exports


@pytest.mark.parametrize('counts', [(37269, 27218), (37270, 27217)])
def test_both_original_denominators_still_fail_closed(tmp_path, counts):
    function, events, exports = fixture(counts=counts)
    with pytest.raises(ValueError, match='linear_actual_denominators'):
        function(tmp_path, 'plan_sha')
    assert tmp_path / 'report.json' not in exports
    assert 'C_finish' not in events
    assert 'progress_close' in events


def test_pure_mode_cannot_accidentally_reuse_legacy60_gate():
    with pytest.raises(ValueError, match='no_registered_pure_launcher'):
        d.namespace()['pure'](Path('unused'))


def test_source_union_requires_canonical_absolute_paths():
    with pytest.raises(ValueError, match='canonical_source'):
        d.relative_sources({'source_before': {'relative.py': 'a'}})
    with pytest.raises(ValueError, match='canonical_source'):
        d.relative_sources({'source_before': {str(d.ROOT.parent / 'outside.py'): 'a'}})


def test_fresh_namespace_does_not_modify_original_module():
    before = dict(vars(d.prior))
    one, two = d.namespace(), d.namespace()
    one['SCHEMA'] = 'mutated_private_only'
    assert two['SCHEMA'] == d.SCHEMA
    assert set(vars(d.prior)) == set(before)
    assert all(vars(d.prior)[name] is value for name, value in before.items())

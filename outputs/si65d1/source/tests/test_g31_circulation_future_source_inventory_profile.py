"""Synthetic original-call profiling only; never import/run the real model."""
import copy
import gc
import json
from pathlib import Path
import pstats
from types import ModuleType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import profile_future_source_inventory as subject


def harness(tmp_path, function, expected=None, **kwargs):
    saved, ledgers = [], []
    if expected is None:
        expected = {'proof': True}
    def save(ordinal, raw):
        saved.append((ordinal, raw))
        return {'ordinal': ordinal, 'bytes': len(raw)}
    def persist(rows):
        ledgers.append(copy.deepcopy(rows))
    options = {'raw_profile_path': tmp_path/'proof.pstats', 'save_proof': save, 'persist_rows': persist}
    options.update(kwargs)
    report = subject.profile_series(function, subject.encoded(expected), **options)
    return report, saved, ledgers


def test_exact65_calls_original_identity_and_nested_stats(tmp_path):
    calls = []
    def nested():
        return {'proof': True}
    def original():
        calls.append(len(calls))
        return nested()
    code, globals_, closure = original.__code__, original.__globals__, original.__closure__
    report, saved, ledgers = harness(tmp_path, original)
    assert report['status'] == 'exact65_original_source_proofs_profiled'
    assert calls == list(range(65)) and len(saved) == len(ledgers) == 65
    assert report['exact_proofs'] == report['actual_calls'] == 65
    assert report['unknown_rows'] == report['unexecuted_rows'] == 0
    assert original.__code__ is code and original.__globals__ is globals_ and original.__closure__ is closure
    stats = pstats.Stats(report['pstats']['path']).stats
    assert sum(row[1] for key, row in stats.items() if key[2] == 'original') == 65
    assert sum(row[1] for key, row in stats.items() if key[2] == 'nested') == 65
    assert report['statistics']['cumulative_times_overlap_do_not_sum'] is True
    assert report['cache_used'] is report['runtime_globals_replaced'] is False


@pytest.mark.parametrize('count', [0, 64, 66, True, 65.0])
def test_strict_fixed_denominator_before_any_call(tmp_path, count):
    calls = []
    def original():
        calls.append(1)
        return {'proof': True}
    with pytest.raises(ValueError, match='fixed65'):
        harness(tmp_path, original, count=count)
    assert calls == []


def test_original_failure_retains_65_denominator_and_profile(tmp_path):
    calls = []
    def original():
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError('original-sentinel')
        return {'proof': True}
    report, saved, _ = harness(tmp_path, original)
    assert len(report['rows']) == 65 and report['actual_calls'] == 3 and report['exact_proofs'] == 2
    assert report['unexecuted_rows'] == 62 and report['unknown_rows'] == 63
    assert len(saved) == 2 and 'original-sentinel' in report['rows'][2]['original_error']['message']
    assert Path(report['pstats']['path']).is_file()


def test_mismatch_saves_actual_return_before_comparison_and_stops(tmp_path):
    def original():
        return {'proof': False}
    report, saved, _ = harness(tmp_path, original)
    assert saved == [(0, b'{"proof":false}')]
    assert report['actual_calls'] == 1 and report['rows'][0]['status'] == 'unknown_proof_mismatch'
    assert report['unknown_rows'] == 65 and report['unexecuted_rows'] == 64


@pytest.mark.parametrize('returned,target', [
    ({'x': 0.0}, {'x': -0.0}),
    ({'x': 1}, {'x': 1.0}),
    ({'b': 2, 'a': 1}, {'a': 1, 'b': 2}),
])
def test_order_types_float_bits_are_not_collapsed(tmp_path, returned, target):
    def original():
        return returned
    report, _, _ = harness(tmp_path, original, expected=target)
    assert report['exact_proofs'] == 0 and report['rows'][0]['status'] == 'unknown_proof_mismatch'


def test_original_exception_identity_survives_monitor_failure():
    sentinel = RuntimeError('exact-object')
    def original():
        raise sentinel
    class Profiler:
        def enable(self):
            pass
        def disable(self):
            raise OSError('monitor-close')
    times = iter((10, 20))
    _, error, monitoring, timing, invoked = subject.one_original_call(original, Profiler(), lambda: next(times))
    assert error is sentinel and invoked and len(monitoring) == 1 and timing['elapsed_ns'] == 10


def test_end_clock_failure_preserves_successful_return_as_unknown(tmp_path):
    times = iter((10, True))
    def original():
        return {'proof': True}
    report, saved, _ = harness(tmp_path, original, clock=lambda: next(times))
    assert report['actual_calls'] == 1 and report['exact_proofs'] == 0 and len(saved) == 1
    assert report['rows'][0]['status'] == 'unknown_original_or_monitor_failure'


@pytest.mark.parametrize('first', [True, -1, 1.0])
def test_invalid_start_clock_does_not_invoke_original(tmp_path, first):
    calls = []
    def original():
        calls.append(1)
        return {'proof': True}
    times = iter((first, 20))
    report, _, _ = harness(tmp_path, original, clock=lambda: next(times))
    assert calls == [] and report['actual_calls'] == 0 and report['unexecuted_rows'] == 65


def test_backwards_clock_is_unknown(tmp_path):
    times = iter((20, 10))
    def original():
        return {'proof': True}
    report, _, _ = harness(tmp_path, original, clock=lambda: next(times))
    assert report['exact_proofs'] == 0 and report['rows'][0]['timing']['elapsed_ns'] is None


def test_required_ledger_export_failure_does_not_pass_saved_proof(tmp_path):
    def original():
        return {'proof': True}
    def fail(_):
        raise OSError('ledger-unwritable')
    report, saved, _ = harness(tmp_path, original, persist_rows=fail)
    assert len(saved) == 1 and report['exact_proofs'] == 0
    assert report['rows'][0]['status'] == 'unknown_required_export_failure'
    assert report['failure']['message'] == 'ledger-unwritable'


def test_proof_export_failure_retains_invoked_unknown(tmp_path):
    def original():
        return {'proof': True}
    def fail(*_):
        raise OSError('proof-unwritable')
    report, _, _ = harness(tmp_path, original, save_proof=fail)
    assert report['actual_calls'] == 1 and report['exact_proofs'] == 0
    assert report['rows'][0]['status'] == 'unknown_return_encoding_or_export_failure'
    assert Path(report['pstats']['path']).is_file()


def test_profile_factory_failure_retains_unexecuted_denominator(tmp_path):
    def original():
        return {'proof': True}
    def factory():
        raise RuntimeError('profile-factory')
    report, _, _ = harness(tmp_path, original, profiler_factory=factory)
    assert report['actual_calls'] == 0 and report['unexecuted_rows'] == report['unknown_rows'] == 65
    assert report['failure']['message'] == 'profile-factory'


def test_profile_export_failure_is_whole_run_unknown(tmp_path):
    class Profiler:
        def enable(self):
            pass
        def disable(self):
            pass
        def dump_stats(self, _):
            raise OSError('stats-unwritable')
    def original():
        return {'proof': True}
    report, _, _ = harness(tmp_path, original, profiler_factory=Profiler)
    assert report['exact_proofs'] == 65 and report['status'] == 'unknown_incomplete'
    assert report['profile_export_error']['message'] == 'stats-unwritable'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), object(), (1, 2)])
def test_nonfinite_or_custom_return_is_unknown(tmp_path, value):
    def original():
        return {'proof': value}
    report, saved, _ = harness(tmp_path, original)
    assert report['actual_calls'] == 1 and report['exact_proofs'] == 0 and saved == []
    assert report['status'] == 'unknown_incomplete'


def test_reject_existing_profile_before_call(tmp_path):
    path = tmp_path/'proof.pstats'
    path.write_bytes(b'preserve')
    calls = []
    def original():
        calls.append(1)
        return {'proof': True}
    with pytest.raises(ValueError, match='output_exists'):
        harness(tmp_path, original)
    assert path.read_bytes() == b'preserve' and calls == []


def test_gc_change_is_not_reported_as_success(tmp_path):
    def original():
        gc.disable()
        return {'proof': True}
    try:
        report, _, _ = harness(tmp_path, original)
        assert report['default_GC_changed'] and report['status'] == 'unknown_incomplete'
    finally:
        gc.enable()


def test_bind_original_requires_actual_defining_module_and_identity():
    module = ModuleType('synthetic_original')
    exec('def source_proof():\n    return {"proof": True}\n', vars(module))
    original = module.source_proof
    assert subject.bind_original(module, original) is original
    with pytest.raises(ValueError, match='defining_globals'):
        subject.bind_original(SimpleNamespace(source_proof=original), original)
    module.source_proof = lambda: {'proof': True}
    with pytest.raises(ValueError, match='identity'):
        subject.bind_original(module, original)


def test_target_only_reaches_comparison_not_original(tmp_path):
    arguments = []
    def original(*args, **kwargs):
        arguments.append((args, kwargs))
        return {'proof': True}
    report, _, _ = harness(tmp_path, original)
    assert report['exact_proofs'] == 65 and arguments == [((), {})]*65

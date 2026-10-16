import gc
import json
import pstats
import sys
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import profile_live_lazy_six as p


def test_same_fixed_six_denominator():
    p.check_rows({key: {} for key in p.ORDER})
    assert len(p.ORDER) == 6 and p.ORDER[-1] == 'insufficient_advance/vector_17'


@pytest.mark.parametrize('keys', [p.ORDER[:-1], tuple(reversed(p.ORDER))])
def test_missing_or_reordered_rows_rejected(keys):
    with pytest.raises(ValueError, match='six_fixed_rows'): p.check_rows({key: {} for key in keys})


def test_whole_budget_includes_parent_elapsed():
    assert p.remaining(10.) == 109.
    with pytest.raises(TimeoutError): p.remaining(119.)
    for x in (True, -1., float('nan'), float('inf')):
        with pytest.raises(ValueError): p.remaining(x)


def test_semantics_preserve_float_type_and_key_order():
    assert not p.exact({'a': -0.}, {'a': 0.})
    assert not p.exact({'a': 1}, {'a': True})
    assert not p.exact({'a': 1, 'b': 2}, {'b': 2, 'a': 1})
    assert not p.exact([1], [1.])


def test_bytes_and_semantics_are_separate_required_checks():
    checks = p.compare_full(b'{"a": 1}', b'{"a":1}')
    assert checks == {'full_bytes_exact': False, 'full_ordered_types_and_float_semantics_exact': True}
    assert all(p.compare_full(b'{"a": 1}', b'{"a": 1}').values())


def test_profile_calls_callback_once_and_saves_pstats(tmp_path):
    calls = []
    def callback(): calls.append(1); return {'v': [1, 2]}
    original_code = callback.__code__
    value, report = p.profiled_call(tmp_path/'one.pstats', callback)
    assert calls == [1] and value == {'v': [1, 2]} and callback.__code__ is original_code
    assert report['status'] == 'returned' and report['callback_count'] == 1
    assert pstats.Stats(report['pstats']['path']).total_calls > 0
    assert report['statistics']['cumulative_times_overlap_do_not_sum'] is True


def test_callback_failure_preserves_profile_and_error_without_retry(tmp_path):
    calls = []
    def callback(): calls.append(1); raise ValueError('deliberate')
    value, report = p.profiled_call(tmp_path/'failure.pstats', callback)
    assert value is None and calls == [1] and report['status'] == 'unknown_callback_error'
    assert 'deliberate' in report['error'] and pstats.Stats(report['pstats']['path']).total_calls > 0


def test_compact_stats_do_not_sum_overlapping_cumulative():
    rows = [{'file': 'x', 'line': 1, 'function': 'outer', 'primitive_calls': 1, 'total_calls': 1,
             'self_seconds': 1., 'cumulative_seconds': 9.},
            {'file': 'x', 'line': 2, 'function': 'deepcopy', 'primitive_calls': 1, 'total_calls': 10,
             'self_seconds': 8., 'cumulative_seconds': 8.}]
    report = p.compact_stats(rows, 9., 11, 2)
    assert report['total_self_seconds'] == 9. and 'cumulative_sum' not in report
    assert report['top_cumulative'][0]['function'] == 'outer'
    assert report['top_self'][0]['function'] == report['top_total_calls'][0]['function'] == 'deepcopy'


def test_initial_context_keeps_independent_owner_guard():
    class Context:
        def __init__(self, value): self.value = value
    functions = SimpleNamespace(SuppliedContext=Context, initial_context=lambda value: Context(value),
        initial_projection_bundle=lambda c: {key: c.value for key in ('jobs', 'trays', 'contract', 'now')},
        encoded=lambda value: json.dumps(value).encode())
    prior = SimpleNamespace(context=functions)
    public = {'initial_owners': {'A': {'value': 1}, 'B': {'value': 1}}, 'action': {}}
    assert type(p.build_initial(public, prior)) is Context
    public['initial_owners']['B']['value'] = 2
    with pytest.raises(ValueError, match='independent_owner_facts'): p.build_initial(public, prior)


def test_profile_does_not_disable_default_GC(tmp_path):
    before = gc.isenabled(); p.profiled_call(tmp_path/'gc.pstats', lambda: [1, 2, 3])
    assert before is True and gc.isenabled() is True


def test_data_C_extension_is_never_loaded(monkeypatch):
    p.no_execution_extensions()
    monkeypatch.setitem(sys.modules, '_g31_complete_tree_normalizer', object())
    with pytest.raises(ValueError, match='forbidden_extension_loaded'): p.no_execution_extensions()

import copy
import gzip
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import validate_live_conditional_continuation as d


def expected(n):
    return [{'owner': 'A' if i % 2 == 0 else 'B', 'at': float(i+1),
        'phase': 'first_return' if i % 2 == 0 else 'first_reuse_route', 'recollection_index': i//2,
        'information_status': 'unknown' if n == 4 and i % 2 == 0 else 'conditional',
        'retry_admission': {'status': 'admissible' if n == 4 and i % 2 == 0 else 'not_needed'}} for i in range(n)]


@pytest.fixture
def harness(monkeypatch, tmp_path):
    class State:
        def __init__(self, engine, frames): self._engine, self._frames = engine, frames
    def make(n, *, fail_after=None, stop_after=None):
        model = SimpleNamespace(Continuation=State, starts=0, advances=0, resumes=0, forks=0)
        def start(context, action):
            assert context == 'initial_only'
            model.starts += 1
            return State({'action': copy.deepcopy(action), 'log': []}, {'index': -1})
        def advance(state):
            model.advances += 1; state._engine['log'].append('initialize_once'); state._frames['index'] = 0
            return State(state._engine, state._frames)
        def resume(state):
            model.resumes += 1; index = state._frames['index']
            if fail_after is not None and index == fail_after: raise RuntimeError('deliberate_path_failure')
            state._engine['log'].append(('before', index)); state._engine['log'].append(('action', index))
            state._engine['log'].append(('after', index)); state._frames['index'] += 1
            if state._frames['index'] < (n if stop_after is None else stop_after):
                return State(state._engine, state._frames)
            return {'status': 'conditional_prediction', 'all_events': copy.deepcopy(state._engine['log']),
                    'completion': {str(i): float(i) for i in range(5)}}
        def fork(state): model.forks += 1; return copy.deepcopy(state)
        model.start_conditional, model.advance_to_collection_or_terminal = start, advance
        model.resume_same_action, model.fork_conditional = resume, fork
        def point(state, _):
            e = expected(n)[min(state._frames['index'], n-1)]
            return {**{k: v for k, v in e.items() if k != 'retry_admission'},
                    'retry_status': e['retry_admission']['status']}
        monkeypatch.setattr(d, 'point_description', point)
        monkeypatch.setattr(d, 'graph', lambda state, _: d.bytes_of([state._engine, state._frames]))
        monkeypatch.setattr(d, 'terminal_description', lambda state, _: {'index': state._frames['index']})
        monkeypatch.setattr(d, 'mutate_finished_copy', lambda state: state._engine.update(mutated=True))
        saved = {}
        def save(label, prediction):
            path = tmp_path/(label+'.json.gz'); path.write_bytes(gzip.compress(d.bytes_of(prediction)))
            saved[label] = d.ref(path); return saved[label]
        return model, save, saved
    return make


def test_fixed_six_and_fourteen_plan():
    rows = {key: {'expected_collections': expected(n)} for key, n in zip(d.ORDER, d.CUT_COUNTS, strict=True)}
    d.check_domain(rows)
    assert sum(d.CUT_COUNTS) == 14 and sum(n*(n+1)//2 for n in d.CUT_COUNTS) == 25


@pytest.mark.parametrize('keys', [d.ORDER[:-1], tuple(reversed(d.ORDER))])
def test_missing_or_reordered_domain_reject(keys):
    with pytest.raises(ValueError, match='six_ordered_rows'):
        d.check_domain({key: {'expected_collections': expected(2)} for key in keys})


def test_shared_budget_counts_parent_setup():
    assert d.remaining(12.) == 107.
    with pytest.raises(TimeoutError): d.remaining(119.)
    for v in (True, -1, float('nan'), float('inf')):
        with pytest.raises(ValueError): d.remaining(v)


def test_two_cut_same_action_no_prefix_reexecution(harness):
    model, save, saved = harness(2)
    result = d.run_case('initial_only', {'fixed': 1}, 2, model, save)
    target = gzip.decompress(__import__('pathlib').Path(saved['main']['path']).read_bytes())
    d.audit_case(result, expected(2), target)
    assert result['status'] == 'exact_main_and_all_same_action_suffixes'
    assert (model.starts, model.advances, model.resumes, model.forks) == (1, 1, 5, 4)


def test_four_cut_fresh_paths_and_exact_ten_suffix_resumes(harness):
    model, save, saved = harness(4)
    result = d.run_case('initial_only', {'fixed': 2}, 4, model, save)
    target = gzip.decompress(__import__('pathlib').Path(saved['main']['path']).read_bytes())
    d.audit_case(result, expected(4), target)
    assert [r['resume_calls'] for r in result['suffixes'].values()] == [4, 3, 2, 1]
    assert model.starts == 1 and model.advances == 1 and model.resumes == 14


def test_full_six_has_thirtynine_resumes_and_twenty_eight_forks(harness):
    totals = [0, 0, 0, 0]
    for n in d.CUT_COUNTS:
        model, save, _ = harness(n); d.run_case('initial_only', {'fixed': 1}, n, model, save)
        totals = [a+b for a, b in zip(totals, [model.starts, model.advances, model.resumes, model.forks], strict=True)]
    assert totals == [6, 6, 39, 28]


def test_extra_cut_stops_and_preserves_unknown(harness):
    model, save, _ = harness(3)
    result = d.run_case('initial_only', {'fixed': 1}, 2, model, save)
    assert result['main']['status'] == 'unknown_error'
    assert 'unexpected_extra_cut' in result['main']['error']
    assert len(result['suffixes']) == 2


def test_main_exception_keeps_retained_suffix_denominator(harness):
    model, save, _ = harness(4, fail_after=1)
    result = d.run_case('initial_only', {'fixed': 1}, 4, model, save)
    assert result['main']['status'] == 'unknown_error'
    assert len(result['points']) == 2 and len(result['suffixes']) == 4
    assert [r['status'] for r in result['suffixes'].values()] == ['unknown_error', 'unknown_error', 'unknown_unexecuted', 'unknown_unexecuted']


def test_early_terminal_does_not_pass_missing_cuts(harness):
    model, save, _ = harness(4, stop_after=1)
    result = d.run_case('initial_only', {'fixed': 1}, 4, model, save)
    assert result['main']['status'] == 'returned'
    with pytest.raises(ValueError, match='complete_hook_count'): d.audit_case(result, expected(4), b'{}')


def test_output_compare_preserves_float_bits_and_order():
    assert d.bytes_of({'x': -0.}) != d.bytes_of({'x': 0.})
    assert d.bytes_of({'a': 1, 'b': 2}) != d.bytes_of({'b': 2, 'a': 1})


def test_bad_fork_aliases_fail_closed(harness):
    model, save, _ = harness(2)
    model.fork_conditional = lambda state: state
    result = d.run_case('initial_only', {'fixed': 1}, 2, model, save)
    assert all(r['status'] == 'unknown_error' for r in result['suffixes'].values())
    assert any('retained_unchanged_after_mainline' in r['error'] for r in result['suffixes'].values())


def test_returned_outputs_saved_before_target_read_failure(harness):
    model, save, saved = harness(2)
    result = d.run_case('initial_only', {'fixed': 1}, 2, model, save)
    assert tuple(saved) == ('main', 'cut_00', 'cut_01')
    with pytest.raises(ValueError, match='whole_prediction_difference'): d.audit_case(result, expected(2), b'bad target')
    assert all(__import__('pathlib').Path(r['path']).exists() for r in saved.values())


def test_changed_saved_prediction_rejects_before_comparison(harness):
    model, save, saved = harness(2)
    result = d.run_case('initial_only', {'fixed': 1}, 2, model, save)
    __import__('pathlib').Path(saved['main']['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='prediction_artifact'): d.audit_case(result, expected(2), b'{}')


def test_terminal_hidden_model_graph_difference_is_not_ignored(harness):
    model, save, saved = harness(2)
    result = d.run_case('initial_only', {'fixed': 1}, 2, model, save)
    result['suffixes']['cut_00']['terminal_full_graph_equals_main'] = False
    target = gzip.decompress(__import__('pathlib').Path(saved['main']['path']).read_bytes())
    with pytest.raises(ValueError, match='complete_suffix_state'): d.audit_case(result, expected(2), target)


def test_missing_suffix_and_resume_count_never_certify(harness):
    model, save, _ = harness(2)
    result = d.run_case('initial_only', {'fixed': 1}, 2, model, save)
    result['counts']['suffix_resumes'] -= 1
    with pytest.raises(ValueError, match='complete_execution_counts'): d.audit_case(result, expected(2), b'{}')
    del result['suffixes']['cut_01']
    with pytest.raises(ValueError, match='suffix_denominator'): d.audit_case(result, expected(2), b'{}')

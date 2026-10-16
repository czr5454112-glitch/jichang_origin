"""Synthetic worker wiring only: no actual projection, native or benchmark."""
from __future__ import annotations
import copy
import gzip
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import measure_scoped_public_inputs_v2_six as m


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding='utf8')


@pytest.fixture
def fixture(tmp_path):
    output = tmp_path/'run'; output.mkdir()
    prediction = {'status': 'conditional_model_prediction', 'completion': {'j': 1.0}, 'projected_collections': []}
    encoded = m.frozen.base.bytes_of(prediction); rows = {}; targets = set(); v1targets = set()
    for key in m.ORDER:
        public = tmp_path/'inputs'/f'{key}.json'; write(public, {'action': {'kind': 'synthetic'}, 'initial_owners': {}})
        target = tmp_path/'targets'/f'{key}.gz'; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gzip.compress(encoded, mtime=0)); targets.add(target)
        v1target = tmp_path/'v1'/f'{key}.gz'; v1target.parent.mkdir(parents=True, exist_ok=True)
        v1target.write_bytes(gzip.compress(encoded, mtime=0)); v1targets.add(v1target)
        rows[key] = {'input': m.ref(public), 'action': {'kind': 'synthetic'},
            'comparison_only_saved_prediction': m.ref(target), 'comparison_only_v1_prediction': m.ref(v1target),
            'expected_collections': []}
    plan = {'declaration': m.frozen.declaration(), 'maximum_model_calls': 24,
        'hard_application_seconds': 120., 'rows': rows}
    write(output/'plan.json', plan)
    return SimpleNamespace(output=output, plan=plan, prediction=prediction, targets=targets, v1targets=v1targets)


def fake_worker(fixture, *, fail_at=None, fail_setup=None, gc_enabled=True):
    calls = []; reads = []; contexts = []; setup = []
    def build_initial(public, prior):
        index = len(setup); setup.append(public)
        if index == fail_setup: raise ValueError('synthetic setup failure')
        context = object(); contexts.append(context); return context
    def predict(arm):
        def call(context, action):
            calls.append((arm, context, copy.deepcopy(action)))
            if len(calls)-1 == fail_at: raise ValueError('synthetic prediction failure')
            return copy.deepcopy(fixture.prediction)
        return call
    class TargetRead:
        def __init__(self, path): self.path = path
        def read_bytes(self):
            ledger = m.read(fixture.output/'ledger.json')
            # The original worker performs both immediate and final readback.
            pending = [i for i, item in enumerate(ledger) if item['status'] == 'returned_audit_pending']
            if pending:
                index = max(pending)
                assert Path(ledger[index]['raw']['path']).exists()
            reads.append((str(self.path), len(calls)))
            return self.path.read_bytes()
    def path(value):
        value = Path(value)
        return TargetRead(value) if value in fixture.targets else value
    original = m.worker_function()
    fakebase = SimpleNamespace(**vars(m.frozen.base))
    fakebase.build_initial = build_initial
    fakebase.loaded_sources = lambda *args: {}
    ns = {**original.__globals__, 'base': fakebase, 'pins_now': lambda *args: {},
        'lazy': SimpleNamespace(predict=predict('A')), 'candidate': SimpleNamespace(predict=predict('B')),
        'gc': SimpleNamespace(isenabled=lambda: gc_enabled), 'Path': path}
    function = FunctionType(original.__code__, ns, original.__name__, original.__defaults__, original.__closure__)
    return function, calls, reads, contexts, setup


def test_source_inverse_and_version_binding():
    proof = m.source_proof(); function = m.worker_function()
    assert proof['worker_inverse_AST_exact_except_final_saved_v1_check']
    assert function.__globals__['lazy'] is m.v1
    assert function.__globals__['candidate'] is m.v2
    assert function.__globals__['base'].build_initial is m.frozen.base.build_initial


def test_no_frozen_global_or_function_changes():
    before = dict(m.frozen.worker.__globals__); code = m.frozen.worker.__code__
    m.worker_function(); m.source_proof()
    assert m.frozen.worker.__code__ is code
    assert set(before) == set(m.frozen.worker.__globals__)
    assert all(m.frozen.worker.__globals__[k] is v for k,v in before.items())


def test_fake_full_worker_24_all_outputs_and_arm_order(fixture):
    function, calls, reads, contexts, setup = fake_worker(fixture)
    function(fixture.output, m.sha(fixture.output/'plan.json'))
    report = m.read(fixture.output/'report.json'); ledger = m.read(fixture.output/'ledger.json')
    assert report['exact'] == 24 and report['unknown'] == 0
    assert report['A_version'] == 'scoped_v1' and report['B_version'] == 'scoped_v2'
    assert ''.join(c[0] for c in calls) == 'ABBA'*6
    assert len(setup) == len(contexts) == 6 and len(reads) == 48
    assert all(calls[i][1] is contexts[i//4] for i in range(24))
    assert all(c[2] == {'kind': 'synthetic'} for c in calls)
    assert report['summary_ms']['A']['count'] == report['summary_ms']['B']['count'] == 12
    assert len(report['v1_full_output_checks']) == len(ledger) == 24
    assert all(r['status'] == 'exact_v1_full_output' for r in report['v1_full_output_checks'])
    assert report['complete_request100ms_certified'] is False
    assert report['per_sample_cycle_cleanup_certified'] is False
    assert all(m.ref(r['raw']['path']) == r['raw'] for r in ledger)


@pytest.mark.parametrize('failure_index', [0, 1, 12, 23])
def test_prediction_failure_keeps_full_denominator_and_continues(fixture, failure_index):
    function, calls, _, _, _ = fake_worker(fixture, fail_at=failure_index)
    function(fixture.output, m.sha(fixture.output/'plan.json'))
    report = m.read(fixture.output/'report.json'); ledger = m.read(fixture.output/'ledger.json')
    assert len(calls) == len(ledger) == 24
    assert report['exact'] == 23 and report['unknown'] == 1
    assert report['status'] == 'unknowns_preserved' and report['summary_ms'] == {}
    assert ledger[failure_index]['status'] == 'unknown_error'
    assert 'elapsed_ns' in ledger[failure_index]


@pytest.mark.parametrize('setup_index', [0, 3, 5])
def test_setup_failure_keeps_four_unknowns_without_fake_prediction(fixture, setup_index):
    function, calls, _, _, setup = fake_worker(fixture, fail_setup=setup_index)
    function(fixture.output, m.sha(fixture.output/'plan.json'))
    report = m.read(fixture.output/'report.json'); ledger = m.read(fixture.output/'ledger.json')
    assert len(calls) == 20 and len(setup) == 6 and len(ledger) == 24
    assert report['exact'] == 20 and report['unknown'] == 4
    assert all(r['status'] == 'unknown_setup_error' for r in ledger[setup_index*4:setup_index*4+4])


def test_disabled_gc_never_evaluates_and_is_not_pass(fixture):
    function, calls, *_ = fake_worker(fixture, gc_enabled=False)
    with pytest.raises(ValueError, match='fixed_scope'):
        function(fixture.output, m.sha(fixture.output/'plan.json'))
    assert not calls


def test_plan_drift_rejected_before_prediction(fixture):
    function, calls, *_ = fake_worker(fixture)
    with pytest.raises(ValueError, match='plan'):
        function(fixture.output, '0'*64)
    assert not calls


@pytest.mark.parametrize('change', ['type', 'signed_zero', 'key_order', 'extra_field', 'list_order'])
def test_saved_v1_full_fields_are_not_ignored(fixture, change):
    value = copy.deepcopy(fixture.prediction)
    if change == 'type': value['completion']['j'] = 1
    elif change == 'signed_zero': value['completion']['j'] = -0.0
    elif change == 'key_order': value = dict(reversed(list(value.items())))
    elif change == 'extra_field': value['extra'] = None
    else: value['projected_collections'] = [2, 1]
    key = m.ORDER[0]; target = Path(fixture.plan['rows'][key]['comparison_only_v1_prediction']['path'])
    target.write_bytes(gzip.compress(m.frozen.base.bytes_of(value), mtime=0))
    fixture.plan['rows'][key]['comparison_only_v1_prediction'] = m.ref(target)
    write(fixture.output/'plan.json', fixture.plan)
    function, calls, *_ = fake_worker(fixture)
    function(fixture.output, m.sha(fixture.output/'plan.json'))
    report = m.read(fixture.output/'report.json')
    assert len(calls) == 24 and report['exact'] == 20 and report['unknown'] == 4
    assert report['status'] == 'unknowns_preserved' and report['summary_ms'] == {}
    assert all(x['status'] == 'unknown_saved_v1_error' for x in report['v1_full_output_checks'][:4])


def test_v1_target_hash_drift_keeps_returned_prediction(fixture):
    target = Path(fixture.plan['rows'][m.ORDER[0]]['comparison_only_v1_prediction']['path'])
    target.write_bytes(b'corrupt')
    function, calls, *_ = fake_worker(fixture)
    function(fixture.output, m.sha(fixture.output/'plan.json'))
    report = m.read(fixture.output/'report.json')
    assert len(calls) == 24 and report['unknown'] == 4
    assert all('raw' in r for r in m.read(fixture.output/'ledger.json'))


@pytest.mark.parametrize('mutation', ['remove', 'reverse', 'arm'])
def test_extend_report_rejects_denominator_tamper(fixture, mutation):
    ledger = [{**d, 'status': 'unknown_unexecuted'} for d in m.frozen.declaration()]
    if mutation == 'remove': ledger.pop()
    elif mutation == 'reverse': ledger.reverse()
    else: ledger[0]['arm'] = 'B'
    with pytest.raises(ValueError, match='full_ledger'):
        m._extend_report(fixture.output, fixture.plan, ledger, {})


def test_unexecuted_rows_stay_unknown(fixture):
    ledger = [{**d, 'status': 'unknown_unexecuted'} for d in m.frozen.declaration()]
    report = m._extend_report(fixture.output, fixture.plan, ledger, {'exact': 24, 'unknown': 0})
    assert report['exact'] == 0 and report['unknown'] == 24 and report['summary_ms'] == {}


@pytest.mark.parametrize('elapsed', [-1, float('nan'), 119.0, 120.0])
def test_original_owned_remaining_bound(elapsed):
    with pytest.raises((ValueError, TimeoutError)): m.frozen.base.remaining(elapsed)


def test_same_owned_120_budget():
    assert m.LIMIT == m.frozen.LIMIT == m.frozen.base.LIMIT == 120.
    assert m.frozen.base.remaining(0) == 119.


def test_v1_v2_predictors_both_construct_per_call_source():
    import ast, inspect, textwrap
    for module in (m.v1, m.v2):
        body = ast.parse(textwrap.dedent(inspect.getsource(module.predict))).body[0].body
        if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body = body[1:]
        assert isinstance(body[0], ast.Assign)
        assert isinstance(body[0].value, ast.Call) and body[0].value.func.id == 'PublicInputScope'
        assert isinstance(body[1], ast.Return) and body[1].value.func.attr == 'predict'


def test_original_predictor_inputs_only_context_action():
    import ast, inspect, textwrap
    function = ast.parse(textwrap.dedent(inspect.getsource(m.frozen.worker))).body[0]
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'function']
    assert len(calls) == 1 and len(calls[0].args) == 2 and calls[0].keywords == []
    assert ast.unparse(calls[0]) == "function(context, public['action'])"


def test_initial_context_caller_not_privately_rebound():
    function = m.worker_function()
    assert function.__globals__['base'] is m.frozen.base
    assert function.__globals__['prior'] is m.frozen.prior


def test_new_saved_check_runs_only_after_original_all_model_loop():
    import ast, inspect, textwrap
    original = ast.parse(textwrap.dedent(inspect.getsource(m.frozen.worker))).body[0]
    top_for_positions = [i for i,n in enumerate(original.body) if isinstance(n, ast.For)]
    report_write = [i for i,n in enumerate(original.body) if isinstance(n, ast.Expr) and "write(output / 'report.json'" in ast.unparse(n)]
    assert len(report_write) == 1 and max(top_for_positions) < report_write[0]


def test_output_save_failure_keeps_unknown_not_fabricated_prediction(fixture):
    function, calls, *_ = fake_worker(fixture)
    class FailedGzip:
        @staticmethod
        def compress(*args, **kwargs): raise OSError('synthetic export failure')
    ns = {**function.__globals__, 'gzip': FailedGzip}
    FunctionType(function.__code__, ns)(fixture.output, m.sha(fixture.output/'plan.json'))
    report = m.read(fixture.output/'report.json')
    assert len(calls) == 24 and report['exact'] == 0 and report['unknown'] == 24
    assert all('raw' not in x for x in m.read(fixture.output/'ledger.json'))

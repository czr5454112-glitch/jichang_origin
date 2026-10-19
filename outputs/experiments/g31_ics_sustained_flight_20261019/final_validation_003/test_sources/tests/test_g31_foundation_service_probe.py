import copy
import gzip
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from scripts.experiments import g31_ics_circulation as package
from scripts.experiments.g31_ics_circulation import foundation_service_probe as probe


ACTIONS = {'first_return': ('return_now', 'return_not_before_7_84'),
    'first_reuse_route': ('native_default', 'prefer_8')}


def seed(evidence):
    return {'status': 'conditional_current_seed', 'evidence': copy.deepcopy(evidence)}


def prediction(action):
    return {'status': 'conditional_prediction', 'action_id': action,
        'completion': {'loaded': 1., 'receiver': 2., 'reuse1': 3., 'reuse2': 4., 'blocker': 5.},
        'full_detail': {'bool_value': False, 'int_value': 0, 'float_value': 0.}}


def report(evidence, actions):
    return {'status': 'conditional_current_seed', 'seed': seed(evidence),
        'candidate_results': {action: prediction(action) for action in actions}}


def test_legacy_uses_old_build_and_each_candidate_predict_not_evaluate():
    calls = []

    def build(evidence):
        calls.append(('build', evidence))
        return seed(evidence)

    def predict(current, action):
        calls.append(('predict', action))
        return prediction(action)

    def forbidden(*args):
        raise AssertionError('legacy must not invoke shared evaluate')

    evidence = {'phase': 'first_return'}
    result = probe.legacy(SimpleNamespace(build_seed=build, predict=predict, evaluate=forbidden),
        evidence, ACTIONS['first_return'])
    assert [item[0] for item in calls] == ['build', 'predict', 'predict']
    assert probe.known_report(result, ACTIONS['first_return'])


@pytest.mark.parametrize('mutation', [
    lambda item: item.update(status='unknown'),
    lambda item: item['seed'].update(status='unknown'),
    lambda item: item['candidate_results'].pop('prefer_8'),
    lambda item: item['candidate_results'].update(unrequested=prediction('unrequested')),
    lambda item: item['candidate_results']['native_default'].update(status='unknown'),
    lambda item: item['candidate_results']['native_default'].update(completion=[]),
    lambda item: item['candidate_results']['native_default']['completion'].pop('blocker'),
    lambda item: item['candidate_results']['native_default']['completion'].update(loaded=True),
    lambda item: item['candidate_results']['native_default']['completion'].update(loaded=-1.),
    lambda item: item['candidate_results']['native_default']['completion'].update(loaded=float('nan')),
    lambda item: item['candidate_results']['native_default']['completion'].update(loaded=float('inf')),
])
def test_known_report_rejects_unknown_incomplete_or_invalid_completion(mutation):
    item = report({'phase': 'first_reuse_route'}, ACTIONS['first_reuse_route'])
    mutation(item)
    assert probe.known_report(item, ACTIONS['first_reuse_route']) is False


@pytest.mark.parametrize('left,right', [(False, 0), (0, 0.), (0., -0.)])
def test_full_comparison_preserves_numeric_types_and_negative_zero(left, right):
    original = report({'phase': 'first_return'}, ACTIONS['first_return'])
    changed = copy.deepcopy(original)
    original['candidate_results']['return_now']['full_detail']['probe'] = left
    changed['candidate_results']['return_now']['full_detail']['probe'] = right
    assert probe.encoding(probe.comparable(original)) != probe.encoding(probe.comparable(changed))


@pytest.fixture
def saved_worker_fixture(tmp_path, monkeypatch):
    calls = []
    model = ModuleType(package.__name__ + '.foundation_later_seed')
    model.ACTIONS = ACTIONS

    def build(evidence):
        assert set(evidence) == {'owner', 'phase', 'at', 'current_only'}
        calls.append(('build', evidence['owner']))
        return seed(evidence)

    def predict(current, action):
        calls.append(('predict', action))
        return prediction(action)

    def evaluate(evidence, actions):
        assert set(evidence) == {'owner', 'phase', 'at', 'current_only'}
        calls.append(('evaluate', evidence['owner']))
        return {**report(evidence, actions), 'evaluation': {'shared_validation': True}}

    model.build_seed, model.predict, model.evaluate = build, predict, evaluate
    monkeypatch.setitem(sys.modules, model.__name__, model)
    monkeypatch.setattr(package, 'foundation_later_seed', model, raising=False)
    monkeypatch.setattr(probe.campaign, 'source_pins', lambda: {})
    sources = []
    for name, owners in (('default', ('A', 'B')), ('delayed', ('B',))):
        transitions = []
        for owner in owners:
            phase = 'first_return' if owner == 'A' else 'first_reuse_route'
            evidence = {'owner': owner, 'phase': phase, 'at': 8. if owner == 'A' else 10.,
                'current_only': name}
            transitions.append({'owner': owner, 'model_report': report(evidence, ACTIONS[phase]),
                'terminal_completion': {'forbidden_future': 999.},
                'actual_physical_effect': {'forbidden_privileged': True}})
        raw_path = tmp_path / (name + '.json.gz')
        raw_path.write_bytes(gzip.compress(json.dumps({'later_transitions': transitions}).encode()))
        receipt_path = tmp_path / (name + '.receipt.json')
        receipt_path.write_text('{}', encoding='utf-8')
        sources.append({'name': name, 'owners': list(owners), 'raw': probe.campaign.reference(raw_path),
            'receipt': probe.campaign.reference(receipt_path)})
    output = tmp_path / 'worker'
    output.mkdir()
    plan = {'schema': probe.SCHEMA, 'hard_seconds': 60, 'order': list(probe.ORDER),
        'automatic_retries': 0, 'source_pins': {}, 'inputs': sources}
    probe.campaign.write_new(output / 'plan.json', plan)
    return output, plan, model, calls


def test_worker_24_reports_48_predictions_only_receive_detached_evidence(saved_worker_fixture):
    output, plan, model, calls = saved_worker_fixture
    result = probe.worker(output, probe.campaign.sha(output / 'plan.json'))
    assert result['status'] == 'completed_exact_saved_comparison'
    assert len(result['rows']) == 24
    assert len(result['contexts']) == 3
    assert sum(kind == 'build' for kind, _ in calls) == 12
    assert sum(kind == 'predict' for kind, _ in calls) == 24
    assert sum(kind == 'evaluate' for kind, _ in calls) == 12
    assert all(row['saved_full_seed_and_predictions_exact'] for row in result['rows'])
    assert result['native_executions'] == 0 and result['complete_request_100ms_certified'] is False
    for context in result['contexts']:
        rows = [row for row in result['rows'] if row['context'] == context['context']]
        assert tuple(row['method'] for row in rows) == probe.ORDER
    assert len(probe.campaign.read(output / 'report.json')['rows']) == 24


def test_worker_unknown_prediction_is_preserved_then_fails_closed(saved_worker_fixture):
    output, plan, model, calls = saved_worker_fixture

    def unknown(evidence, actions):
        item = report(evidence, actions)
        item['candidate_results'][actions[0]] = {'status': 'unknown', 'completion': {},
            'reasons': ['fixture_incomplete_current_resource']}
        return item

    model.evaluate = unknown
    result = probe.worker(output, probe.campaign.sha(output / 'plan.json'))
    assert result['status'] == 'unknown'
    assert 'known_current_predictions_required' in result['exception']
    assert len(result['rows']) == 2
    artifact = result['rows'][-1]['artifact']['path']
    failed = json.loads(gzip.decompress(Path(artifact).read_bytes()))
    assert failed['candidate_results']['return_now']['reasons'] == ['fixture_incomplete_current_resource']


def test_worker_known_prediction_type_change_keeps_failure_artifact(saved_worker_fixture):
    output, plan, model, calls = saved_worker_fixture

    def changed(evidence, actions):
        item = report(evidence, actions)
        item['candidate_results'][actions[0]]['full_detail']['bool_value'] = 0
        return item

    model.evaluate = changed
    result = probe.worker(output, probe.campaign.sha(output / 'plan.json'))
    assert result['status'] == 'unknown'
    assert 'complete_saved_prediction_parity' in result['exception']
    assert len(result['rows']) == 2
    assert result['rows'][-1]['saved_full_seed_and_predictions_exact'] is False
    assert Path(result['rows'][-1]['artifact']['path']).is_file()


def test_saved_bytes_changed_are_rejected_before_model_work(saved_worker_fixture):
    output, plan, model, calls = saved_worker_fixture
    raw_path = plan['inputs'][0]['raw']['path']
    with open(raw_path, 'ab') as stream:
        stream.write(b'changed')
    result = probe.worker(output, probe.campaign.sha(output / 'plan.json'))
    assert result['status'] == 'unknown'
    assert 'saved_input_bytes_changed' in result['exception']
    assert calls == [] and result['rows'] == []

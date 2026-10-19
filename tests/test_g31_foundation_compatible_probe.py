import copy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_compatible_probe as subject
from test_g31_foundation_budgeted_provider import provider_fixture


def test_predeclared_five_variants_have_separate_prefix_and_candidate_budgets():
    rows = subject.variant_specifications()
    assert tuple(rows) == ('compatible8', 'rule4', 'prefix_cost4', 'linear4', 'mlp4')
    assert rows['compatible8']['candidate_budget'] == 8
    assert rows['compatible8']['prefix_budget'] == 4
    assert all(rows[kind]['candidate_budget'] == 4 and rows[kind]['prefix_budget'] == 2
        for kind in subject.ORDER[1:])
    assert rows['prefix_cost4']['ranking_policy'] == 'marginal_prefix_cost'
    assert subject.HARD_SECONDS == 150


@pytest.fixture
def complete_fixture_probe(provider_fixture, monkeypatch, tmp_path):
    decision, request, events, _ = provider_fixture
    original_bind = subject.provider.binding.bind_request

    def bind():
        request.uses, request.closed = 0, False
        return original_bind()

    monkeypatch.setattr(subject.provider.binding, 'bind_request', bind)
    monkeypatch.setattr(subject.ranker, 'score_candidates', lambda observation, candidates, model_version:
        [float(index) for index in range(len(candidates))])
    monkeypatch.setattr(subject.previous, 'shared_rule', lambda observation, candidates, model_version:
        [-float(index) for index in range(len(candidates))])
    callback = subject.make_callback({'linear': 'linear_fixture', 'mlp': 'mlp_fixture'}, tmp_path)(decision)
    assert events.count('bind') == 5
    measured = subject.provider.evaluate_budgeted(decision, budget=32, candidate_indices=list(range(32)))
    teacher = {'selection': {'provider_evidence': measured['batch'].audit_copy(),
        'accounting': {'provider_measured_through_seal_seconds': measured['compute_wall_ms'] / 1000}}}
    return callback, teacher


def test_callback_complete_before_teacher_and_full_strict_assessment(complete_fixture_probe):
    callback, teacher = complete_fixture_probe
    result = subject.assess_variants(callback, teacher)
    assert callback['status'] == 'complete_advice_only'
    assert not callback['teacher_available_to_actor']
    assert not callback['native_authority']
    assert result['all_variants_passed']
    assert result['compatible8_regret_s'] == 0
    assert result['variants']['compatible8']['actual_prefix_count'] == 4
    assert result['variants']['compatible8']['source_proof_uses'] == 17
    for kind in subject.ORDER[1:]:
        row = result['variants'][kind]
        assert row['actual_prefix_count'] == 2 and row['source_proof_uses'] == 9
        assert row['total_domain_not_requested'] == 28
        assert row['legal_domain_not_requested'] == 4
        assert row['allocation']['scoring_row_count'] == 8


@pytest.mark.parametrize('field,value', [('evaluated_prefix_count', 3), ('candidate_budget', 7)])
def test_incorrect_variant_counters_not_assessed_as_passed(complete_fixture_probe, field, value):
    callback, teacher = complete_fixture_probe
    changed = copy.deepcopy(callback)
    if field == 'candidate_budget':
        changed['variants']['rule4']['report']['allocation'][field] = value
    else:
        changed['variants']['rule4']['report'][field] = value
    result = subject.assess_variants(changed, teacher)
    assert not result['all_variants_passed']
    assert not result['variants']['rule4']['declared_budgets_and_structure_passed']


def test_bool_int_corruption_is_not_upgraded_by_final_assessor(complete_fixture_probe):
    callback, teacher = complete_fixture_probe
    callback['variants']['rule4']['report']['rows'][4]['prediction']['typed_receipt_sequence'] = True
    teacher['selection']['provider_evidence']['rows'][4]['prediction']['typed_receipt_sequence'] = 1
    result = subject.assess_variants(callback, teacher)
    assert not result['all_variants_passed']
    assert not result['variants']['rule4']['all_requested_prediction_parity']


def test_callback_stops_on_first_unknown_before_next_method(provider_fixture, monkeypatch, tmp_path):
    decision, _, events, _ = provider_fixture
    monkeypatch.setattr(subject.provider, 'execute_selected_prefix', lambda *args: (_ for _ in ()).throw(ValueError('fixture_unknown')))
    with pytest.raises(ValueError, match='incomplete_compatible8'):
        subject.make_callback({'linear': 'unused', 'mlp': 'unused'}, tmp_path)(decision)
    partial = json.loads((tmp_path / 'callback_partial.json').read_bytes())
    assert list(partial['variants']) == ['compatible8']
    assert partial['status'] == 'unknown_variant'
    assert events.count('bind') == 1
    assert not (tmp_path / 'callback_complete.json').exists()


@pytest.mark.parametrize('status,exitcode', [('hard_timeout', 0), ('exited', 1), ('exited', 0)])
def test_process_and_child_completion_both_required(tmp_path, monkeypatch, status, exitcode):
    subject.previous.write(tmp_path / 'plan.json', {})
    subject.previous.write(tmp_path / 'worker_report.json', {'status': 'complete_compatible_domain_advice_probe'})
    monkeypatch.setattr(subject, 'check_pins', lambda plan: None)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs['timeout']))
        return {'status': status, 'exitcode': exitcode}

    monkeypatch.setattr(subject.previous.bounded_windows_job, 'run', run)
    result = subject.launch(tmp_path)
    assert (result['status'] == 'complete_compatible_domain_advice_probe') == (status == 'exited' and exitcode == 0)
    assert len(calls) == 1 and calls[0][1] == 150
    assert '--plan-sha256' in calls[0][0]
    with pytest.raises(ValueError, match='one_launch_only'):
        subject.launch(tmp_path)


def test_worker_rejects_changed_plan_before_native_import_work(tmp_path):
    subject.previous.write(tmp_path / 'plan.json', {})
    with pytest.raises(ValueError, match='parent_frozen_plan'):
        subject.worker(tmp_path, 'not-the-plan-hash')
    assert not (tmp_path / 'native').exists()


def test_model_pin_rejects_modified_model(tmp_path):
    path = tmp_path / 'model.json'
    path.write_text('{}')
    plan = {'source_sha256': {}, 'artifact_pins': [subject.previous.reference(path)]}
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='artifact_changed'):
        subject.check_pins(plan)

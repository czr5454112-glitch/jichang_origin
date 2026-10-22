"""Synthetic guards only; no frozen helper import and no native artifact read."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

path = Path(__file__).with_name('strong_baseline_service_audit_005.py')
spec = importlib.util.spec_from_file_location('strong_baseline_driver', path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def roster():
    rows = {(p, m): dict(plan=dict(task_id=f'P{p}_{m}', parent=p, method=m),
                         directory=Path(f'P{p}_{m}')) for p in audit.PARENTS for m in audit.METHODS}
    status = dict(status='ready', pending=[], registered_runs=28, expected_runs=28,
                  all_four_parents_share_one_historical_template=True)
    return rows, status

def result(parent=2201):
    counts = dict(exact_harmed=1, reference_only_finished=0, exact_equal=5,
                  exact_improved=0, candidate_only_finished=0,
                  both_arrived_unfinished=20000, both_not_yet_arrived=8500)
    return dict(reference_method='C10', candidate_method='TF-B1-60',
        reference_task=f'P{parent}_C10', candidate_task=f'P{parent}_TF-B1-60',
        physical_contract=dict(parent=dict(parent_seed=parent)), population=28506,
        population_exclusions=0, per_bag=[dict(business_bag_id=f'bag{i}') for i in range(28506)],
        cost_window=[7200., 59400.], completion_times_imputed=False,
        both_unfinished_never_declared_equal=True, completion_direction=dict(categories=counts,
            population=28506, known_direction_harm=1), strict_per_bag_nonharm_certified=False,
        test_unlocked=False, evidence=[], gain_bag_seconds=1., known_lateness_harm=1,
        completed_delta=1, on_time_delta=0, existing_observed_service_gate_passed=False)

def test_pending_rejected_before_any_io_or_output(tmp_path):
    with pytest.raises(ValueError, match='all_28_closed_required'):
        audit.execute({}, dict(status='pending'), {}, {}, [], {}, None, {}, [], tmp_path/'result')
    assert not (tmp_path/'result').exists()

def test_exact_roster_required():
    rows, status = roster()
    audit.require_ready(rows, status)
    rows.pop((2204, 'TF-predictor'))
    with pytest.raises(ValueError, match='exact_28_run_roster'):
        audit.require_ready(rows, status)

@pytest.mark.parametrize('field,value,reason', [
    ('reference_method', 'C00', 'fixed_pair_required'),
    ('population_exclusions', 1, 'complete_28506_population'),
    ('completion_times_imputed', True, 'censoring_contract'),
    ('both_unfinished_never_declared_equal', False, 'censoring_contract'),
    ('test_unlocked', True, 'no_automatic_promotion'),
])
def test_pair_contract_rejections(field, value, reason):
    rows, _ = roster(); value_row = result(); value_row[field] = value
    with pytest.raises(ValueError, match=reason):
        audit.validate_result(value_row, 2201, rows)

def test_complete_unique_bags_and_known_harm_definition():
    rows, _ = roster(); value = result()
    audit.validate_result(value, 2201, rows)
    value['per_bag'][-1] = value['per_bag'][0]
    with pytest.raises(ValueError, match='unique_complete_per_bag_rows'):
        audit.validate_result(value, 2201, rows)
    value = result(); value['completion_direction']['known_direction_harm'] = 20001
    with pytest.raises(ValueError, match='completion_harm_definition'):
        audit.validate_result(value, 2201, rows)

def test_collect_inputs_binds_logs_and_rejects_changed_parent_input(tmp_path):
    shared = audit.load_shared()
    root = tmp_path/'run'; root.mkdir()
    parent = shared.fresh(root/'input.json', {'synthetic': True})
    plan = shared.fresh(root/'plan.json', {'method':'C10', 'input':parent})
    for name in ('receipt.json', 'worker_report.json', 'trajectory.json.gz', 'terminal_evidence.json.gz'):
        shared.fresh(root/name, {'synthetic': True})
    block = shared.fresh(tmp_path/'block.json', {'task_plans':[plan]})
    refs = audit.collect_inputs([block['path']], shared)
    assert {Path(ref['path']).name for ref in refs.values()} == {
        'block.json', 'plan.json', 'input.json', 'receipt.json', 'worker_report.json',
        'trajectory.json.gz', 'terminal_evidence.json.gz'}
    (root/'input.json').write_text('{}', encoding='utf8')
    with pytest.raises(ValueError, match='registered_binding_changed'):
        audit.collect_inputs([block['path']], shared)

def execution_fixture(tmp_path, monkeypatch, *, mutate=False):
    shared = audit.load_shared(); rows, status = roster()
    producer = tmp_path/'producer.py'; producer.write_text('# synthetic producer', encoding='utf8')
    producer_ref = shared.bind(producer)
    source = shared.fresh(tmp_path/'source.json', {'synthetic':True})
    workflow = shared.fresh(tmp_path/'workflow.json', {'synthetic':True})
    monkeypatch.setattr(shared, 'verify_sources', lambda ref: tmp_path)
    monkeypatch.setattr(shared, 'inspect_blocks', lambda *args: (rows, status))
    calls = []
    def compare(left, right):
        parent = int(left.name[1:5]); calls.append(parent)
        if mutate:
            producer.write_text('# changed synthetic producer', encoding='utf8')
        return result(parent)
    helpers = dict(campaign=SimpleNamespace(comparison_contract=lambda plan: dict(
        source='same', parent=plan['parent'], allocator=plan['method'])),
        service=SimpleNamespace(compare_runs=compare))
    output = tmp_path/'supplement'
    return (rows, status, source, workflow, [], helpers, shared, {}, [producer_ref], output), calls

def test_four_parent_synthetic_completion_and_no_automatic_promotion(tmp_path, monkeypatch):
    arguments, calls = execution_fixture(tmp_path, monkeypatch)
    audit.execute(*arguments)
    assert calls == list(audit.PARENTS)
    complete = json.loads((arguments[-1]/'COMPLETE.json').read_text())
    report = arguments[6].bound_read(complete['final_report'])
    assert complete['scientific_per_bag_pairs'] == len(report['pair_summaries']) == 4
    assert report['original_final_science_24_pairs_unchanged'] is True
    assert report['aggregate']['mean_gain_bag_seconds'] == 1.
    assert report['aggregate']['all_parent_observed_service_gates_passed'] is False
    assert report['promotion_approved'] is report['test_unlocked'] is False

def test_changed_producer_refuses_complete_marker(tmp_path, monkeypatch):
    arguments, _ = execution_fixture(tmp_path, monkeypatch, mutate=True)
    with pytest.raises(ValueError, match='input_or_producer_changed_during_audit'):
        audit.execute(*arguments)
    assert (arguments[-1]/'pending.json').exists()
    assert not (arguments[-1]/'COMPLETE.json').exists()

def test_wrong_pair_axis_refused_before_output(tmp_path, monkeypatch):
    arguments, _ = execution_fixture(tmp_path, monkeypatch)
    arguments[5]['campaign'].comparison_contract = lambda plan: dict(source=plan['method'])
    with pytest.raises(ValueError, match='unregistered_pair_axis'):
        audit.execute(*arguments)
    assert not arguments[-1].exists()

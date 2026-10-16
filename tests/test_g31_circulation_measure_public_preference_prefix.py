"""A shorter candidate list cannot count as an exact faster computation."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import measure_public_preference_prefix as measure


def test_exact_outputs_rejects_missing_extra_and_semantically_changed_rows():
    rows = [{'status': 'conditional_prediction', 'completion': {'job': float(i)}} for i in range(32)]
    assert measure.exact_outputs(rows, copy.deepcopy(rows), 32)
    assert not measure.exact_outputs(rows, rows[:-1], 32)
    assert not measure.exact_outputs(rows, rows + rows[:1], 32)
    assert not measure.exact_outputs([], [], 32)
    changed = copy.deepcopy(rows); changed[3]['completion']['job'] += 1.
    assert not measure.exact_outputs(rows, changed, 32)
    assert not measure.exact_outputs(rows[:4], rows[:3], 4)


def example():
    rows = {f'case{c}/vector_{v:02}': {'raw_artifact': f'case{c}_{v}.gz', 'raw_sha256': str(v),
            'status_retained': 'unknown' if v < 3 else 'assessed'} for c in range(6) for v in range(32)}
    audit = {'status': 'saved192_revalidated_no_new_native', 'rows': rows}
    plan = {'schema': 'g31.public_preference_prefix_pair.v1', 'initial_candidate_denominator': 192,
            'later_candidate_denominator': 48, 'hard_timeout_seconds': 120., 'native_calls': 0,
            'historical_native_status_counts': {'unknown': 18, 'assessed': 174},
            'cases': [{'case': f'case{c}', 'initial_source_key': f'case{c}/vector_00',
                'input': f'case{c}.input.json', 'raw_path': f'case{c}_0.gz', 'raw_sha256': '0',
                'batch_order': ['A', 'B', 'B', 'A'] if c % 2 == 0 else ['B', 'A', 'A', 'B']} for c in range(6)]}
    return plan, audit


@pytest.mark.parametrize('fault', ['short_cases', 'duplicate_case', 'changed_reference', 'order', 'unknown_count', 'budget', 'short_audit'])
def test_plan_rejects_denominator_order_reference_or_budget_changes(fault):
    plan, audit = example(); measure.check_plan(plan, audit)
    if fault == 'short_cases': plan['cases'].pop()
    elif fault == 'duplicate_case': plan['cases'][1] = copy.deepcopy(plan['cases'][0])
    elif fault == 'changed_reference': plan['cases'][0]['raw_path'] = 'other.gz'
    elif fault == 'order': plan['cases'][0]['batch_order'] = ['A', 'A', 'B', 'B']
    elif fault == 'unknown_count': plan['historical_native_status_counts'] = {'assessed': 192}
    elif fault == 'budget': plan['hard_timeout_seconds'] = 121.
    elif fault == 'short_audit': audit['rows'].pop(next(iter(audit['rows'])))
    with pytest.raises(ValueError): measure.check_plan(plan, audit)


def test_prior_run_is_not_overwritten(tmp_path):
    (tmp_path / 'failure.json').write_text('{}')
    with pytest.raises(ValueError, match='refuse_to_overwrite'):
        measure.launch(tmp_path)

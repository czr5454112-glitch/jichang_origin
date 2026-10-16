"""Missing candidates/references cannot masquerade as faster exact batches."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import measure_public_preference_quiet as measure


def example():
    rows = {f'case{c}/vector_{v:02}': {'raw_artifact': f'case{c}_{v}.gz', 'raw_sha256': str(v),
            'status_retained': 'unknown' if v < 3 else 'assessed'} for c in range(6) for v in range(32)}
    audit = {'status': 'saved192_revalidated_no_new_native', 'rows': rows}
    plan = {'schema': measure.SCHEMA, 'candidate_denominator': 192, 'later_candidate_denominator': 0,
        'hard_timeout_seconds': 120., 'native_calls': 0,
        'historical_native_status_counts': {'unknown': 18, 'assessed': 174},
        'cases': [{'case': f'case{c}', 'source_key': f'case{c}/vector_00', 'input': f'case{c}.input.json',
            'raw_path': f'case{c}_0.gz', 'raw_sha256': '0',
            'order': ['A', 'B', 'B', 'A'] if c % 2 == 0 else ['B', 'A', 'A', 'B']} for c in range(6)]}
    return plan, audit


def test_exact_output_cannot_drop_duplicate_or_change_candidates():
    rows = [{'completion': {'job': float(i)}, 'status': 'conditional_prediction'} for i in range(32)]
    assert measure.exact32(rows, copy.deepcopy(rows))
    assert not measure.exact32(rows, rows[:-1])
    assert not measure.exact32(rows, rows + rows[:1])
    assert not measure.exact32([], [])
    changed = copy.deepcopy(rows); changed[8]['status'] = 'unknown'
    assert not measure.exact32(rows, changed)


@pytest.mark.parametrize('fault', ['missing_case', 'later_claim', 'changed_order', 'raw_substitution', 'promoted_unknown', 'time_budget'])
def test_plan_preserves_denominator_order_and_raw_scope(fault):
    plan, audit = example(); measure.check_plan(plan, audit)
    if fault == 'missing_case': plan['cases'].pop()
    elif fault == 'later_claim': plan['later_candidate_denominator'] = 48
    elif fault == 'changed_order': plan['cases'][0]['order'] = ['A', 'A', 'B', 'B']
    elif fault == 'raw_substitution': plan['cases'][0]['raw_path'] = 'other.gz'
    elif fault == 'promoted_unknown': plan['historical_native_status_counts'] = {'assessed': 192}
    else: plan['hard_timeout_seconds'] = 121.
    with pytest.raises(ValueError): measure.check_plan(plan, audit)


def test_prior_failure_is_preserved(tmp_path):
    (tmp_path / 'failure.json').write_text('{}')
    with pytest.raises(ValueError, match='refuse_prior_execution'):
        measure.launch(tmp_path)

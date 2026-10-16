import copy
import sys

import pytest

from scripts.experiments.g31_ics_circulation import review_complete_root_c_publisher_saved as r


def record():
    return {'value': {'evidence': {'root_started_ns': 10, 'root_deadline_ns': 10000,
            'state': 'closed_native_default_first_hop', 'events': [{'at': 3., 'original_ns': 42}]},
        'body_finished_ns': 600, 'body_elapsed_ns': 590, 'outside_return_tail_required': True},
        'ledger': {'complete': True}, 'return_codec': {'strict': True}, 'finalization_started_ns': 200,
        'outside_return_ns': 800, 'warm_caller_elapsed_ns': 790, 'closed': True,
        'within_100ms_observed': True, 'complete_100ms_certificate': False}


def clock(): return {'started_ns': 100, 'finished_ns': 1000, 'elapsed_ns': 900, 'gzip_hash_elapsed_ns': 50}


def samples():
    keys = [f'root{i:02d}' for i in range(18)]
    rows = [{'key': key, 'arm': arm, 'position': i, 'elapsed_ms': 2. if arm == 'A' else 1.}
        for key in keys for i, arm in enumerate('ABBA')]
    return keys, rows


def test_complete_record_and_current_clock_pass():
    r.row_clock(clock()); r.compare_record(record(), record(), clock())


def test_only_regenerated_clock_fields_may_change():
    changed = record(); changed['value']['body_finished_ns'] = 650; changed['value']['body_elapsed_ns'] = 640
    changed['outside_return_ns'] = 850; changed['warm_caller_elapsed_ns'] = 840
    r.compare_record(changed, record(), clock())


@pytest.mark.parametrize('where', ['deadline', 'event', 'ledger'])
def test_historical_deadline_event_and_ledger_are_not_excluded(where):
    changed = record()
    if where == 'deadline': changed['value']['evidence']['root_deadline_ns'] += 1
    elif where == 'event': changed['value']['evidence']['events'][0]['original_ns'] += 1
    else: changed['ledger']['complete'] = False
    with pytest.raises(ValueError, match='complete_semantics_changed'): r.compare_record(changed, record(), clock())


def test_regenerated_clock_formula_not_skipped():
    changed = record(); changed['warm_caller_elapsed_ns'] += 1
    with pytest.raises(ValueError, match='mock_historical_elapsed_formula'): r.compare_record(changed, record(), clock())


def test_clock_exact_int_and_export_order():
    value = clock(); value['started_ns'] = True
    with pytest.raises(ValueError, match='exact_nonnegative_clock'): r.row_clock(value)
    value = clock(); value['gzip_hash_elapsed_ns'] = -1
    with pytest.raises(ValueError, match='exact_nonnegative_clock'): r.row_clock(value)
    with pytest.raises(ValueError, match='sample_and_export_chronology'): r.row_clock(clock(), clock())
    r.row_clock({'started_ns': 1050, 'finished_ns': 1060, 'elapsed_ns': 10, 'gzip_hash_elapsed_ns': 0}, clock())


def test_all72_ABBA_and36_per_arm_statistics():
    keys, rows = samples(); result = r.summarize(rows, keys)
    assert result['summary_ms']['A'] == {'count': 36, 'min': 2., 'median': 2., 'max': 2., 'sum': 72.}
    assert result['negative_or_equal_root_medians'] == [] and len(result['per_root_median_ms']) == 18


def test_missing_or_reordered_samples_fail_closed():
    keys, rows = samples()
    with pytest.raises(ValueError, match='statistics_denominator'): r.summarize(rows[:-1], keys)
    rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(ValueError, match='statistics_ABBA_order'): r.summarize(rows, keys)


def test_negative_equal_cases_remain_in_paired_denominator():
    keys, rows = samples()
    for row in rows[:4]: row['elapsed_ms'] = 2.
    for row in rows[4:8]: row['elapsed_ms'] = 3. if row['arm'] == 'B' else 2.
    assert r.summarize(rows, keys)['negative_or_equal_root_medians'] == keys[:2]


def test_direct_support_is_shape_and_source_statement_only():
    row = {'direct_C_supported': True, 'exact_and_new_owned_tree': True,
           'raw_normalization_bytes_sha256': 'a'*64, 'containers': 3}
    r.check_support({'key': row}, ['key'])
    bad = copy.deepcopy(row); bad['containers'] = True
    with pytest.raises(ValueError, match='direct_support_record'): r.check_support({'key': bad}, ['key'])
    with pytest.raises(ValueError, match='direct_support_denominator'): r.check_support({'key': row}, ['key', 'missing'])


def test_import_does_not_load_data_C_or_native_extension(monkeypatch):
    r.no_execution_modules()
    monkeypatch.setitem(sys.modules, '_g31_complete_tree_normalizer', object())
    with pytest.raises(ValueError, match='forbidden_extension_loaded'): r.no_execution_modules()


def test_budget_is_shared_with_parent_imports():
    assert r.remaining(20.) == 99.
    for value in (True, -1., float('nan'), float('inf')):
        with pytest.raises(ValueError): r.remaining(value)
    with pytest.raises(TimeoutError): r.remaining(119.)


def test_float_and_key_order_are_not_normalized_away():
    assert not r.exact({'a': -0.}, {'a': 0.})
    assert not r.exact({'a': 1, 'b': 2}, {'b': 2, 'a': 1})

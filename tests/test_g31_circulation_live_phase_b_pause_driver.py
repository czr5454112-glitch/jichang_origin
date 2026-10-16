import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import validate_live_phase_b_pause as driver


def test_fixed_six_cases_and_actions_order():
    driver.check_order({key: {} for key in driver.ORDER})
    assert len(driver.ORDER) == 6
    assert {key.split('/')[0] for key in driver.ORDER} == {'mechanism', 'no_overlap', 'insufficient_advance'}


@pytest.mark.parametrize('rows', [{key: {} for key in driver.ORDER[:-1]},
                                  {key: {} for key in reversed(driver.ORDER)}])
def test_missing_or_reordered_rows_reject(rows):
    with pytest.raises(ValueError, match='six_ordered_rows'): driver.check_order(rows)


def test_budget_includes_parent_elapsed_and_reserve():
    assert driver.remaining(10.) == 109.
    with pytest.raises(TimeoutError): driver.remaining(119.)
    for value in (True, -1., float('nan'), float('inf')):
        with pytest.raises(ValueError): driver.remaining(value)


def test_graph_preserves_cycle_alias_and_copy():
    shared = {'x': [1, 2]}; graph = [shared, shared]; shared['root'] = graph
    assert driver.graph_bytes(graph) == driver.graph_bytes(copy.deepcopy(graph))


def test_graph_detects_alias_loss_with_equal_values():
    shared = {'x': 1}
    assert driver.graph_bytes([shared, shared]) != driver.graph_bytes([{'x': 1}, {'x': 1}])


def test_graph_preserves_float_bits_and_scalar_types():
    assert driver.graph_bytes([0.]) != driver.graph_bytes([-0.])
    assert driver.graph_bytes([True]) != driver.graph_bytes([1])
    assert driver.graph_bytes({'x': {('A', 1), ('B', 2)}}) == driver.graph_bytes({'x': {('B', 2), ('A', 1)}})


def test_graph_rejects_custom_objects_and_unsupported_sets():
    with pytest.raises(ValueError, match='unsupported_graph_object'): driver.graph_bytes(SimpleNamespace(x=1))
    with pytest.raises(ValueError, match='unsupported_set_element'): driver.graph_bytes({frozenset({1})})


def test_hook_count_and_exact_chronology_required():
    expected = [{'owner': 'B', 'at': 8.69, 'phase': 'first_reuse_route', 'recollection_index': 0,
                 'information_status': 'unknown', 'retry_admission': {'status': 'conditional_retry_admissible'}}]
    actual = [{k: v for k, v in expected[0].items() if k != 'retry_admission'}]
    actual[0]['retry_status'] = 'conditional_retry_admissible'
    driver.check_points(actual, expected)
    with pytest.raises(ValueError, match='complete_hook_count'): driver.check_points([], expected)
    actual[0]['at'] = 8.690000000000001
    with pytest.raises(ValueError, match='point_chronology'): driver.check_points(actual, expected)


def test_full_prediction_encoding_preserves_order_fields_and_float_difference():
    assert driver.bytes_of({'a': 1, 'b': 2}) != driver.bytes_of({'b': 2, 'a': 1})
    assert driver.bytes_of({'at': 0.}) != driver.bytes_of({'at': -0.})
    assert driver.bytes_of({'a': 1, 'b': 2}) != driver.bytes_of({'a': 1})

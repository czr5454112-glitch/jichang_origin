"""Pure diagnostic alignment regressions; no map simulation required."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.experiments.ics_circulation_v3.run_cursor_original_map import compare_cases, normalized_opportunities


def fixture(kind):
    rows = [dict(time=1, node='A', role='origin', bag_id='served', tray_id='a', protected=False,
                 candidate_count=2 if kind == 'cursor' else 4),
            dict(time=1, node='B', role='origin', bag_id='blocked', tray_id='b', protected=False,
                 candidate_count=0)]
    return {'metrics': {'engine': kind}, 'opportunities': rows,
            'searches': [dict(time=1, origin='A', bag_id='served', tray_id='a', candidate_count=4),
                         dict(time=1, origin='B', bag_id='blocked', tray_id='b', candidate_count=0)],
            'route_history': [dict(time=1, node='A', bag_id='served', tray_id='a', candidate_count=2)],
            'result': {'physical_tick': 2, 'generation_ms': 2 if kind == 'cursor' else 4},
            'slow_history': [], 'slow_trigger_times': [1], 'slow_next_trigger_at': 3,
            'observer_boundaries': [{'time': 1}]}


def test_four_generated_two_authorized_and_zero_attempt_are_separate_and_equal():
    left, right = fixture('original'), fixture('cursor')
    before = deepcopy(left)
    rows = normalized_opportunities(left)
    assert rows == normalized_opportunities(right)
    assert [(r['generated_candidate_count'], r['authorized_candidate_count']) for r in rows] == [(4, 2), (0, 0)]
    assert left == before
    assert all(compare_cases(left, right).values())


def test_nonzero_generated_but_no_authorized_selector_is_retained_as_zero():
    case = fixture('original')
    case['searches'][1]['candidate_count'] = 4
    case['opportunities'][1]['candidate_count'] = 4
    row = normalized_opportunities(case)[1]
    assert row['generated_candidate_count'] == 4 and row['authorized_candidate_count'] == 0


@pytest.mark.parametrize('mutation', ['missing_call', 'wrong_node', 'too_many', 'duplicate_identity'])
def test_diagnostic_identity_or_authorization_mismatch_is_not_silently_equal(mutation):
    case = fixture('cursor')
    if mutation == 'missing_call':
        case['route_history'].clear()
    elif mutation == 'wrong_node':
        case['route_history'][0]['node'] = 'wrong'
    elif mutation == 'too_many':
        case['route_history'][0]['candidate_count'] = 5
    else:
        case['route_history'].append(deepcopy(case['route_history'][0]))
    with pytest.raises(ValueError):
        normalized_opportunities(case)


@pytest.mark.parametrize('scene', ['cross_cycle', 'counterflow', 'near_full'])
def test_saved_original_map_raw_records_match_under_common_authorized_denominator(scene):
    root = Path(__file__).resolve().parents[1]
    folder = root / 'outputs/experiments/ics_circulation_v3/phase4_w3_cursor_original_map_20261009'
    left = json.loads((folder / (scene + '_original.json')).read_text(encoding='utf-8'))
    right = json.loads((folder / (scene + '_cursor.json')).read_text(encoding='utf-8'))
    assert all(compare_cases(left, right).values())
    rows = normalized_opportunities(right)
    if scene == 'near_full':
        assert sum(r['authorized_candidate_count'] == 0 for r in rows) == 6
    assert len(rows) == right['metrics']['loaded_attempt_count']

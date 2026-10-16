import copy
import math

import pytest

from scripts.experiments.g31_ics_circulation import public_live_obligation_projection as old
from scripts.experiments.g31_ics_circulation import public_live_obligation_event_projection_v2 as revised


def engine():
    data = old.inputs()['no_overlap']
    return revised.Projection(old.assemble(data, old.declared_captures(data)), old.actions()[28])


def test_leg_start_publishes_every_outgoing_node_even_if_snapshot_unchanged():
    e = engine()
    e.time = 8.649999999999995
    e.trays['L'].update(node=7, job='reuse1', mode='loaded')
    e.begin_leg('L', 6)
    assert sorted(row[4][0] for row in e.events if row[3] == 'beacon') == sorted(e.outgoing[7])
    assert all(row[0] == e.time for row in e.events if row[3] == 'beacon')


def test_calendar_change_wakes_without_queue_or_incoming_change():
    e = engine()
    e.time = 8.55
    e.calendars[3] = [(8.55, 8.65)]
    e.beacon(3)
    e.waiting['E'] = 1
    e.ranking_subscriptions['E'] = {3}
    e.wait_targets['E'] = (3, 'receiving_full')
    e.time = 8.649999999999995
    before = e.beacon_state[3]
    e.beacon(3)
    assert before[:2] == e.beacon_state[3][:2]
    assert e.calendars[3] == []
    assert e.phase_trace[-1]['phase'] == 'resource_wake'
    assert e.phase_trace[-1]['next_arbitration'] == e.time


def test_current_calendar_only_change_without_future_reservation_does_not_wake():
    e = engine()
    e.time = 8.
    e.beacon(3)
    e.waiting['E'] = 1
    e.ranking_subscriptions['E'] = {3}
    e.time = 9.
    e.beacon(3)
    assert e.phase_trace[-1]['phase'] == 'beacon_snapshot'
    assert not e.phase_trace[-1]['ranking_notification']
    assert 'E' in e.ranking_subscriptions


@pytest.mark.parametrize('gap,delayed', [(0., True), (5e-10, True), (2e-9, False)])
def test_recovery_timestamp_rule_is_separate_from_exact_event_order(gap, delayed):
    e = engine()
    e.time = 8.65
    e.trays['E']['node'] = 1
    e.waiting['E'] = 1
    e.last_arbitration[1] = e.time - gap
    e.wake_one('E', 'candidate_score_state_changed')
    assert e.phase_trace[-1]['next_arbitration'] == e.time + (.001 if delayed else 0.)
    assert revised.Projection.try_depart is old.Projection.try_depart


def test_no_protection_tolerance_or_calendar_rounded_output():
    before = math.nextafter(8.65, -math.inf)
    assert before < 8.65 and before != 8.65
    assert revised.same_recovery_timestamp(before, 8.65)
    assert 8.651 - 8.65 > 0.
    assert revised.Projection.candidate_rows is old.Projection.candidate_rows


@pytest.mark.parametrize('mutation', ['pending', 'population', 'clock', 'occupation', 'protocol'])
def test_closed_input_validation_still_rejects_mutations(mutation):
    data = old.inputs()['mechanism']
    bundle = old.assemble(data, old.declared_captures(data))
    if mutation == 'pending':
        bundle['owner_pending_tray_requests'] = ['pending']
    elif mutation == 'population':
        bundle['trays'].pop('P')
    elif mutation == 'clock':
        bundle['now'] = math.nextafter(bundle['now'], math.inf)
    elif mutation == 'occupation':
        bundle['resources'][3]['occupancy'] = 1
    else:
        bundle['protocol']['message_delay'] = 0.
    result = revised.predict(bundle, old.actions()[0])
    assert result['status'].startswith('unknown_')
    assert not result['native_protection_certified']


def test_private_predict_namespace_preserves_old_model():
    revised.check_sources()
    assert old.predict.__globals__['Projection'] is old.Projection
    assert old.predict.__globals__['VERSION'] == old.VERSION
    assert revised._predict.__globals__['Projection'] is revised.Projection

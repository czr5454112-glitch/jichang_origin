"""Plan visibility/identity tests; these do not invoke native or train a model."""
import copy
from dataclasses import FrozenInstanceError

import pytest

from scripts.experiments.g31_ics_circulation import foundation_flight_context as flight


BASIS = {'unit': 'seconds', 'origin': 'synthetic_episode_start',
    'timezone': 'Asia/Shanghai', 'conversion_version': 'fixture_identity_v1'}


def plan(*, version=1, published=1., received=2., owner='A'):
    return {'schema_version': flight.SCHEMA, 'source_id': 'synthetic_plan_feed',
        'version': version, 'published_at': published, 'received_at': received,
        'owner_scope': owner, 'time_basis': copy.deepcopy(BASIS),
        'availability_basis': 'source_publication', 'static_assumption': None,
        'validity_policy': {'mode': 'until_superseded', 'valid_until': None},
        'entries': [{'flight_ref': 'synthetic-flight-001', 'identity_kind': 'real_flight',
            'scheduled_event_type': 'STD', 'scheduled_event_at': 3600.}]}


def adapt(payload=None, *, now=10., owner='A'):
    return flight.adapt_context(payload, owner=owner, now=now, expected_time_basis=BASIS)


def select(history=None, *, now=10., owner='A'):
    return flight.select_context(history, source_id='synthetic_plan_feed',
        owner=owner, now=now, expected_time_basis=BASIS)


def test_missing_plan_preserves_none_without_fabricating_zero_demand():
    assert adapt() is None
    assert select() is None
    assert select([]) is None
    entry = adapt(plan()).entries[0]
    assert entry.available_bag_count_estimate is None
    assert entry.planned_injection_region is None


def test_future_plan_event_is_allowed_but_publication_receipt_are_not_future():
    payload = plan(published=10., received=10.)
    payload['entries'][0].update(estimated_event_type='ETD', estimated_event_at=3800.)
    context = adapt(payload)
    assert context.entries[0].scheduled_event_at == 3600.
    assert context.entries[0].estimated_event_at == 3800.
    assert context.published_at == context.received_at == 10.
    assert adapt(context.to_dict()) == context


@pytest.mark.parametrize('field,value,reason', [
    ('published_at', None, 'published_at_finite_number_required'),
    ('published_at', 3., 'publication_after_receipt'),
    ('received_at', 11., 'not_yet_received'),
    ('received_at', None, 'received_at_finite_number_required'),
    ('received_at', float('nan'), 'received_at_finite_number_required'),
    ('version', True, 'positive_integer_version'),
    ('owner_scope', 'B', 'owner_scope'),
    ('schema_version', 'legacy', 'schema_version'),
])
def test_invalid_visibility_or_identity_fails_closed(field, value, reason):
    payload = plan()
    payload[field] = value
    with pytest.raises(ValueError, match=reason):
        adapt(payload)


def test_owner_receipt_is_independent_and_newest_visible_version_is_selected():
    first = plan()
    second_a = plan(version=2, published=4., received=5.)
    second_b = plan(version=2, published=4., received=12., owner='B')
    first_b = plan(owner='B')
    history = [second_b, first_b, second_a, first]
    assert select(history).version == 2
    assert select(history, owner='B').version == 1
    assert select(history, now=12., owner='B').version == 2
    assert select(history, now=1.9) is None


def test_late_old_version_and_duplicate_receipt_cannot_roll_back_or_renew_plan():
    latest = plan(version=2, published=4., received=5.)
    old_late = plan(received=9.)
    retransmission = copy.deepcopy(latest)
    retransmission['received_at'] = 9.
    context = select([old_late, retransmission, latest])
    assert context.version == 2
    assert context.received_at == 5.


def test_future_and_foreign_payloads_are_not_parsed_or_used():
    future = plan(version=2, published=11., received=12.)
    future['entries'] = [{'unknown_future_label': 'must_not_be_read'}]
    foreign = plan(version=3, published=5., received=6., owner='B')
    foreign['entries'] = object()
    assert select([plan(), future, foreign]).version == 1
    with pytest.raises(ValueError, match='entry_schema'):
        select([plan(), future], now=12.)


def test_same_version_cannot_silently_change_content():
    conflicting = plan()
    conflicting['entries'][0]['scheduled_event_at'] += 1.
    with pytest.raises(ValueError, match='conflicting_same_version'):
        select([plan(), conflicting])


def test_publisher_version_cannot_move_back_in_publication_time():
    with pytest.raises(ValueError, match='publication_version_regression'):
        select([plan(published=3., received=3.), plan(version=2, published=2., received=4.)])


def test_expired_latest_does_not_resurrect_older_or_missing_plan():
    newest = plan(version=2, published=4., received=5.)
    newest['validity_policy'] = {'mode': 'expires_at', 'valid_until': 7.}
    assert select([plan(), newest], now=6.).version == 2
    assert select([plan(), newest], now=7.) is None
    newest['received_at'] = 9.
    assert select([plan(), newest], now=10.) is None
    assert adapt(newest) is None


def test_explicit_static_assumption_keeps_missing_publication_and_actual_receipt():
    payload = plan(published=None)
    payload.update(availability_basis='static_predeclared',
        static_assumption='Synthetic timetable provided to A before this episode; not historical replay.')
    context = adapt(payload)
    assert context.published_at is None
    assert context.received_at == 2.
    assert context.availability_basis == 'static_predeclared'
    assert select([payload]) == context
    payload['static_assumption'] = None
    with pytest.raises(ValueError, match='static_assumption_text_required'):
        adapt(payload)


def test_static_assumption_cannot_be_presented_as_a_measured_publication():
    payload = plan()
    payload.update(availability_basis='static_predeclared', static_assumption='Explicit synthetic assumption.')
    with pytest.raises(ValueError, match='static_publication_must_remain_missing'):
        adapt(payload)


@pytest.mark.parametrize('field,value,reason', [
    ('raw_bag_count', 100, 'entry_schema'),
    ('first_entry_time', 80, 'entry_schema'),
    ('last_entry_time', 400, 'entry_schema'),
    ('actual_departure_at', 3700, 'entry_schema'),
    ('source_counts', {'A': 20}, 'entry_schema'),
    ('estimated_event_type', 'ETA', 'estimated_event_pair'),
    ('planned_injection_region', 'A', 'mapping_version_required'),
    ('available_bag_count_estimate', 20, 'estimate_provenance_required'),
])
def test_label_and_unqualified_field_inputs_are_rejected(field, value, reason):
    payload = plan()
    payload['entries'][0][field] = value
    with pytest.raises(ValueError, match=reason):
        adapt(payload)


def test_event_semantics_and_final_total_are_not_relabelled_as_estimates():
    payload = plan()
    payload['entries'][0].update(estimated_event_type='ETA', estimated_event_at=3800.)
    with pytest.raises(ValueError, match='estimated_event_semantics'):
        adapt(payload)
    payload = plan()
    payload['entries'][0].update(available_bag_count_estimate=20.,
        estimate_source='offline_full_day_summary', estimate_kind='final_actual_total')
    with pytest.raises(ValueError, match='estimate_kind'):
        adapt(payload)


def test_new_mapping_and_cancellation_are_context_only_and_snapshot_replaces():
    first = plan()
    first['entries'][0].update(identity_kind='historical_group',
        available_bag_count_estimate=20., estimate_source='frozen_training_day_baseline_v1',
        estimate_kind='forecast', planned_injection_region='A', mapping_version='map_v1')
    second = copy.deepcopy(first)
    second.update(version=2, published_at=4., received_at=5.)
    second['entries'][0].update(planned_injection_region='B', mapping_version='map_v2',
        plan_status='cancelled')
    before, after = select([first, second], now=3.), select([first, second])
    assert before.entries[0].planned_injection_region == 'A'
    assert after.entries[0].planned_injection_region == 'B'
    assert after.entries[0].plan_status == 'cancelled'
    assert after.entries[0].available_bag_count_estimate == 20.
    assert after.entries[0].identity_kind == 'historical_group'
    assert not {'jobs', 'trays', 'inventory', 'native_execution_authority'} & set(after.to_dict())
    second['entries'] = []
    assert select([first, second]).entries == ()


def test_context_and_output_are_detached_from_input():
    payload = plan()
    frozen = copy.deepcopy(payload)
    context = adapt(payload)
    assert payload == frozen
    payload['entries'][0]['scheduled_event_at'] = 0.
    payload['time_basis']['origin'] = 'wrong_clock'
    output = context.to_dict()
    output['entries'][0]['scheduled_event_at'] = 0.
    assert context.entries[0].scheduled_event_at == 3600.
    assert context.time_basis.origin == BASIS['origin']
    with pytest.raises(FrozenInstanceError):
        context.version = 99


@pytest.mark.parametrize('field,value', [('unit', 'milliseconds'), ('origin', 'other_day'),
    ('timezone', 'UTC'), ('conversion_version', 'other_mapping')])
def test_time_basis_must_match_declared_actor_clock(field, value):
    payload = plan()
    payload['time_basis'][field] = value
    with pytest.raises(ValueError, match='time_'):
        adapt(payload)


def test_unknown_top_level_fields_and_duplicate_flights_are_rejected():
    payload = plan()
    payload['jobs'] = [{'arrival': 99.}]
    with pytest.raises(ValueError, match='context_schema'):
        adapt(payload)
    payload = plan()
    payload['entries'].append(copy.deepcopy(payload['entries'][0]))
    with pytest.raises(ValueError, match='duplicate_flight_identity'):
        adapt(payload)

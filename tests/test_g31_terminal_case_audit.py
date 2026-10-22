"""Real-case display counts unique trays and keeps failures out of censoring."""
import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_batch_patch import digest
from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_case_audit import case_row, source_ceiling


def fixture(status="departed"):
    action = dict(tray_id="tray", source=0, destination=2, source_actual_unpledged=2, source_fifo_reserved=0)
    decision = dict(requested_action=action, selection=dict(flow_plan=dict(chosen=[action],
        station_table=[dict(node=0, actual_empty=2), dict(node=2, actual_empty=0)])),
        catalog=dict(candidates=[dict(action, kind="transfer"), dict(action, kind="transfer", destination=3)]),
        features_current=dict(destination_waiting=0))
    chain = dict(order_id="order", plan_id="plan", request_id="request", decision_id="decision", proposed_at=10.,
        classification="extra_reposition", exact_first_action_verification=dict(exact_net_gain=3.,
            exact_projection=dict(destination_without_move=dict(ending_backlog=.5, first_shortage_offset=0.))),
        native_transfer_at_export=dict(status=status, received_at=-1., departed_at=12., delivered_at=12.),
        planned_dispatch=dict(dispatch_slot=0, submit_at=10., earliest_departure=12., estimated_arrival=50.),
        requested_order=dict(target_by=30.), actual_submission=dict(expiry=90.), accepted=True)
    return decision, chain


def test_distinct_destinations_do_not_duplicate_source_legal_tray_count():
    result = case_row(*fixture(), cutoff=100.)
    assert result["source_actual_empty"] == 2
    assert result["source_legal_unique_trays"] == 1
    assert result["all_legal_unique_trays"] == 1
    assert result["in_transit_seconds_lower_bound"] == 88.
    assert result["eta_error_lower_bound_seconds"] == 50.
    assert result["native_received_at"] is None


def test_failed_native_request_is_not_reported_as_censored_inflight():
    result = case_row(*fixture("failed"), cutoff=100.)
    assert result["native_failed"]
    assert not result["received_censored"]
    assert result["in_transit_seconds_lower_bound"] is None
    assert result["eta_error_lower_bound_seconds"] is None


def test_two_individually_legal_trays_still_have_one_tray_total_source_cap():
    decision, _ = fixture()
    observation = dict(node_contracts=[dict(node=0, export_min_stock=0)])
    action = dict(decision['requested_action'], kind='transfer', source_category='loader_optional')
    decision['catalog'].update(public_state_digest=digest(observation),
        candidates=[action, dict(action, tray_id='other')])
    decision['public_observation_ref'] = digest(observation)
    result = source_ceiling(decision, observation)
    assert result['source_offer_eligible_unique_trays'] == 2
    assert result['source_hard_minimum_reserve'] == 1
    assert result['source_cap'] == result['selected_quantity_from_source'] == 1
    decision['selection']['flow_plan']['chosen'].append(dict(action, tray_id='other'))
    with pytest.raises(ValueError, match='plan_respects_recomputed_source_cap'):
        source_ceiling(decision, observation)

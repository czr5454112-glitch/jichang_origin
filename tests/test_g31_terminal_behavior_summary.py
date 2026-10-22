"""Observed coverage keeps plan, request, cache and source samples distinct."""
from copy import deepcopy

from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_behavior_summary import (
    decision_coverage, reverse_requests, source_windows,
)


def test_cached_multi_item_plan_is_one_plan_and_one_actual_dispatch():
    action=dict(kind='transfer',tray_id='tray',source=1,destination=2,source_category='ordinary_return')
    plan=dict(plan_id='plan',chosen=[action,dict(action,tray_id='other',destination=3)],
              dispatch_profile=[dict(dispatch_slot=0),dict(dispatch_slot=1)],shared_witness_edges=[{}])
    decisions=[dict(decision_id='a',catalog=dict(candidates=[action]),selection=dict(flow_plan=plan)),
               dict(decision_id='b',catalog=dict(candidates=[action]),selection=dict(flow_plan=deepcopy(plan)))]
    rows=[dict(decision_id='a',requested_action=action,actual_submission={},request_id='request',
              ack=[dict(status='received')],received_event={},physical_failure=False,
              flow_cache=dict(hit=False,invalidation_reason='initial',plan_age_seconds=0.)),
          dict(decision_id='b',requested_action=dict(kind='noop'),request_id=None,
               flow_cache=dict(hit=True,invalidation_reason=None,plan_age_seconds=60.))]
    result=decision_coverage(decisions,rows)
    assert result['plan_counts']['unique_plan_ids']==1
    assert result['plan_counts']['multi_item_plans']==1
    assert result['plan_counts']['multi_item_plans_with_two_actual_requests']==0
    assert result['plan_counts']['later_dispatch_slot_suggestions']==1
    assert result['decision_counts']['cache_hits']==1
    assert result['selected_by_source_category']['ordinary_return']['received']==1


def test_reversal_attempts_keep_received_and_intervening_load_denominators():
    def call(rid,at,source,dest):
        return dict(kind='transfer',retry=False,at=at,request=dict(request_id=rid,tray_id='tray',source=source,destination=dest))
    calls=[call('a',0.,1,2),call('b',30.,2,1),call('c',60.,1,2)]
    terminal=dict(transfers=[dict(request_id='a',received_at=10.,departed_at=1.,status='received'),
        dict(request_id='b',received_at=40.,departed_at=31.,status='received'),
        dict(request_id='c',received_at=-1.,departed_at=-1.,status='rejected')],
        receipts=[dict(event='LOAD_START',tray_id='tray',time=20.)])
    result=reverse_requests(calls,terminal,selected_request_ids=['a'])
    assert result['same_tray_reverse_requests']==2
    assert result['reverse_actually_received']==result['reverse_actually_departed']==1
    assert result['reverse_without_intervening_load']==1
    assert result['optional_involved_reverse_without_intervening_load']==0
    assert result['rows'][0]['intervening_load_start_count']==1


def test_source_shortage_is_sampled_association_with_missing_coverage_retained():
    selected=[dict(request_id='request',decision_time=100.,requested_action=dict(source=1,source_actual_unpledged=2))]
    samples={1:[dict(at=160.,stock=1,waiting=0),dict(at=400.,stock=0,waiting=2)]}
    result=source_windows(selected,samples,cutoff=500.)
    assert result['followed_by_observed_waiting_and_zero_stock']==1
    assert result['complete_60s_sample_windows']==0
    assert result['rows'][0]['right_censored']
    assert result['rows'][0]['maximum_sample_gap_seconds']==240.
    assert not result['rows'][0]['causal_depletion_or_service_harm_proven']

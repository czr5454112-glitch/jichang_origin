"""Functional proof boundaries only; no native, predictor or timing campaign."""
from copy import deepcopy
import pytest
from scripts.experiments.g31_ics_circulation.initial_owner_route_observation_gate import RootObservationGate


def args(now=.11, before=.11, cursor=None, notices=None, calls=4):
    return dict(before=before, now=now, horizon=now,
        response={'status':'notified' if notices else 'horizon_reached',
                  'physical_time':now, 'timestamp_complete':True,
                  'horizon_complete':True, 'notifications':notices or {}},
        cursor_before=cursor or {'A':0,'B':0}, protocol_call_count=calls,
        outbox={'a':{'kind':'route','request':{'request_id':'a','owner_id':'A'},
                     'terminal':False,'next_retry':.61}},
        root_state='pending_first_hop_and_ack', all_native_advances_observed=True)


def ready():
    gate=RootObservationGate()
    decision=gate.decide(**args())
    assert not decision['skip'] and decision['reason']=='initial_or_unproven_chain'
    assert gate.after_step(now=.11, protocol_call_count=4, original_admission_retained=True,
                           full_root_observation_and_drain_completed=True)['chain_continues']
    return gate


def test_unchanged_tick_is_skippable_without_rewriting_observation_time():
    gate=ready(); data=args(.16,.11); original=deepcopy(data)
    proof=gate.decide(**data)
    assert proof['skip'] and data==original
    assert proof['retained_observation_time_unchanged'] and not proof['actual_native_authority']
    assert gate.after_step(now=.16, protocol_call_count=4, original_admission_retained=True,
                          full_root_observation_and_drain_completed=False)['chain_continues']


def test_foreign_notice_same_timestamp_multiple_event_increments():
    gate=ready(); notice={'B':{'sequence':7,'observed_at':.12,'change_mask':18}}
    proof=gate.decide(**args(.12,.11,notices=notice))
    assert proof['skip'] and proof['cursor_after']=={'A':0,'B':7}
    gate.after_step(now=.12,protocol_call_count=4,original_admission_retained=True,
                    full_root_observation_and_drain_completed=False)
    assert gate.decide(**args(.16,.12,cursor={'A':0,'B':7}))['skip']


@pytest.mark.parametrize('mask',[1,2,4,8,16,32,64,128,255])
def test_every_A_notice_forces_full_original_path(mask):
    proof=ready().decide(**args(.12,.11,notices={'A':{
        'sequence':3,'observed_at':.12,'change_mask':mask}}))
    assert not proof['skip'] and proof['reason']=='actual_A_notification'


@pytest.mark.parametrize('change,reason',[
    ({'cursor_before':{'A':1,'B':0}},'native_clock_or_cursor_gap'),
    ({'before':.10},'native_clock_or_cursor_gap'),
    ({'protocol_call_count':5},'protocol_submission_since_previous_step'),
    ({'all_native_advances_observed':False},'unobserved_native_advance_or_mutation'),
    ({'root_state':'closed'},'root_not_pending'),
    ({'outbox':None},'missing_complete_outbox')])
def test_unproven_or_changed_input_falls_back(change,reason):
    data=args(.16,.11); data.update(change)
    proof=ready().decide(**data)
    assert not proof['skip'] and proof['reason']==reason


@pytest.mark.parametrize('bad',[
    {'sequence':1,'observed_at':.11,'change_mask':2},
    {'sequence':0,'observed_at':.16,'change_mask':2},
    {'sequence':1,'observed_at':.16,'change_mask':256},
    {'sequence':True,'observed_at':.16,'change_mask':2},
    {'sequence':1,'observed_at':float('nan'),'change_mask':2}])
def test_stale_lost_or_unknown_notice_never_authorizes_skip(bad):
    proof=ready().decide(**args(.16,.11,notices={'B':bad}))
    assert not proof['skip']


@pytest.mark.parametrize('retry',[.16,.15,None,float('nan'),True])
def test_due_or_unknown_retry_keeps_original_refresh(retry):
    data=args(.16,.11);data['outbox']['a']['next_retry']=retry
    assert not ready().decide(**data)['skip']


def test_received_terminal_no_longer_has_retry_but_ACK_event_forces_read():
    data=args(.16,.11);data['outbox']['a']['terminal']=True
    del data['outbox']['a']['next_retry']
    assert ready().decide(**data)['skip']
    data['response'].update(status='notified',notifications={'A':{
        'sequence':4,'observed_at':.16,'change_mask':16}})
    assert not ready().decide(**data)['skip']


@pytest.mark.parametrize('change',[
    {'timestamp_complete':False}, {'status':'budget_exhausted'},
    {'physical_time':.15}, {'horizon_complete':1},
    {'status':'notified','notifications':{}},
    {'notifications':{'C':{'sequence':1,'observed_at':.16,'change_mask':2}}}])
def test_incomplete_or_malformed_boundary_falls_back(change):
    data=args(.16,.11);data['response'].update(change)
    assert not ready().decide(**data)['skip']


def test_no_step_completion_breaks_chain():
    gate=ready();assert gate.decide(**args(.16,.11))['skip']
    proof=gate.decide(**args(.21,.16))
    assert not proof['skip'] and proof['reason']=='previous_step_completion_missing'


@pytest.mark.parametrize('changes',[
    {'now':.17}, {'protocol_call_count':5}, {'original_admission_retained':False},
    {'full_root_observation_and_drain_completed':True}])
def test_skipped_step_cannot_hide_mutation_admission_loss_or_extra_work(changes):
    gate=ready();assert gate.decide(**args(.16,.11))['skip']
    kw=dict(now=.16,protocol_call_count=4,original_admission_retained=True,
            full_root_observation_and_drain_completed=False);kw.update(changes)
    assert not gate.after_step(**kw)['chain_continues']
    assert not gate.decide(**args(.21,.16))['skip']


def test_missing_drain_after_full_path_never_primes_skip():
    gate=RootObservationGate();gate.decide(**args())
    assert not gate.after_step(now=.11,protocol_call_count=4,original_admission_retained=True,
        full_root_observation_and_drain_completed=False)['chain_continues']
    assert not gate.decide(**args(.16,.11))['skip']


def test_record_aliases_do_not_mutate_the_retained_chain():
    gate=ready();proof=gate.decide(**args(.16,.11))
    proof['cursor_after']['A']=999
    proof['skip']=False
    gate.after_step(now=.16,protocol_call_count=4,original_admission_retained=True,
                    full_root_observation_and_drain_completed=False)
    assert gate.decide(**args(.21,.16))['skip']


def test_fallback_record_cannot_be_mutated_into_skip_permission():
    gate=RootObservationGate();proof=gate.decide(**args());proof['skip']=True
    assert not gate.after_step(now=.11,protocol_call_count=4,original_admission_retained=True,
        full_root_observation_and_drain_completed=False)['chain_continues']

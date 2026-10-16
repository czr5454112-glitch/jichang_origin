"""Saved-data-only mock binding; never constructs or calls a native session."""
from __future__ import annotations
import gzip
import json
from types import FunctionType,SimpleNamespace,MethodType
from . import single_root_evidence as candidate

old=candidate.old
CAMPAIGN_SHA='e5459ab579d76e65c76ee41b0a4bc5f06224f3be0796ace6636ec4d0a2f7b46d'
SOURCE=old.OUT/'initial_owner_route_campaign_v3_prepare_001'
RECORD_KEYS=('value','ledger','return_codec','finalization_started_ns','outside_return_ns',
    'warm_caller_elapsed_ns','closed','within_100ms_observed','complete_100ms_certificate')
VALUE_KEYS=('evidence','body_finished_ns','body_elapsed_ns','outside_return_tail_required')


def clone(fn,**changes):
    result=FunctionType(fn.__code__,{**fn.__globals__,**changes},fn.__name__,fn.__defaults__,fn.__closure__)
    result.__kwdefaults__=fn.__kwdefaults__
    return result


def functions(arm,clock):
    """Freeze only body/publication clocks in pure tests, without global patching."""
    if arm=='A':
        core=clone(old.request.InitialOwnerRequest.evidence,time=clock)
        facade=SimpleNamespace(**vars(old.request))
        facade.InitialOwnerRequest=SimpleNamespace(evidence=core)
        method=clone(old.CapturedRequest.evidence,time=clock,request=facade)
        finish=clone(old.finish_root,time=clock)
    elif arm=='B':
        method=clone(candidate.evidence,time=clock)
        finish=clone(candidate.finish_root,time=clock)
    else:raise ValueError('mock_arm')
    publish=clone(old.publish_root,time=clock,finish_root=finish)
    return method,publish


def root_from_evidence(value,method):
    root=SimpleNamespace(request_id=value['root_id'],state=value['state'],
        started_ns=value['root_started_ns'],deadline_ns=value['root_deadline_ns'],
        cutoff_ns=value['decision_cutoff_ns'],choice=value['choice'],command_id=value['command_id'],
        hop=value['hop'],events=value['events'],initial_endpoint_records=value['initial_endpoint_records']['A'],
        B_endpoint_records=value['initial_endpoint_records']['B'])
    root.evidence=MethodType(method,root)
    return root


def load_inputs():
    old.require(old.sha(SOURCE/'campaign.json')==CAMPAIGN_SHA,'mock_original_campaign_changed')
    plan=old.read(SOURCE/'campaign.json');ledger=old.read(SOURCE/'branch_ledger.json')
    old.require(list(ledger)==plan['row_order'] and len(ledger)==18,'mock_original_denominator')
    values=[]
    for key in plan['row_order']:
        path=SOURCE/'raw'/(key+'.json.gz')
        old.require(ledger[key]['status']=='raw_saved' and ledger[key]['raw']==old.reference(path),
                    'mock_original_raw_hash')
        with gzip.open(path,'rt',encoding='utf8') as stream:raw=json.load(stream)
        old.require(len(raw['root_records'])==1,'mock_root_count')
        values.append((key,raw['root_records'][0]))
    return values


def semantic_record(record):
    """Only regenerated outer/body clocks are excluded; original event clocks stay."""
    old.require(type(record) is dict and tuple(record)==RECORD_KEYS and
        type(record['value']) is dict and tuple(record['value'])==VALUE_KEYS,
        'mock_record_topology')
    return {'evidence':record['value']['evidence'],
        'outside_return_tail_required':record['value']['outside_return_tail_required'],
        'ledger':record['ledger'],'return_codec':record['return_codec'],
        'closed':record['closed'],'complete_100ms_certificate':record['complete_100ms_certificate']}


def current_clock_bounds(record,started,finished):
    old.require(all(type(x) is int and x>=0 for x in (started,finished,record['finalization_started_ns'],
        record['value']['body_finished_ns'],record['outside_return_ns'])) and
        started<=record['finalization_started_ns']<=record['value']['body_finished_ns']<=
        record['outside_return_ns']<=finished,'mock_current_clock_bound')
    # The retained request/event/deadline times belong to the old experiment.
    # No generated warm_caller_elapsed_ns is reported as a new native root cost.
    old.require(record['complete_100ms_certificate'] is False,
                'historical_mock_promoted')
    semantic_record(record)
    evidence=record['value']['evidence']
    old.require(type(record['value']['body_elapsed_ns']) is int and
        record['value']['body_elapsed_ns']==record['value']['body_finished_ns']-evidence['root_started_ns'] and
        type(record['warm_caller_elapsed_ns']) is int and
        record['warm_caller_elapsed_ns']==record['outside_return_ns']-evidence['root_started_ns'],
        'mock_historical_elapsed_formula')
    closed=evidence['state'] in ('closed_native_default_first_hop','closed_delivered_terminal_failure',
        'closed_updated_and_requested_first_hop','closed_updated_but_other_first_hop')
    old.require(record['closed'] is closed and record['within_100ms_observed'] is
        (closed and record['outside_return_ns']<=evidence['root_deadline_ns']),
        'mock_historical_status_formula')

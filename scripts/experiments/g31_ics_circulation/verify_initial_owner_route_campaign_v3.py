"""Exact old endpoint/physical verifier plus explicitly retained failure paths."""
from __future__ import annotations
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
from types import FunctionType, SimpleNamespace
from . import initial_owner_route_campaign_v3 as c
from . import verify_initial_owner_route_campaign as old
from . import native_preexisting_initial_adapter as initial

require = c.require
for _name in ('exact','endpoint_replay','immutable_calls','rpc_replay','verify_branch','pair_comparison'):
    _function = getattr(old,_name)
    globals()[_name] = FunctionType(_function.__code__,globals(),_function.__name__,_function.__defaults__,_function.__closure__)


def clocks(value, keys, reason):
    """Monotonic-clock readings are exact nonnegative builtin integers."""
    require(type(value) is dict and all(type(value.get(k)) is int and value[k]>=0 for k in keys), reason)
    return [value[k] for k in keys]


def root_replay(raw):
    if raw['root_records']:
        result = old.root_replay(raw)
        root = raw['root_records'][0]['value']['evidence']
        attempts = [e for e in root['events'] if e['stage']=='RPC_attempt']
        require(len(attempts) <= 1, 'RPC_attempt_denominator')
        for event in attempts:
            v = event['value']
            clocks(v, ('started_ns','finished_ns'), 'RPC_attempt_clock_type')
            require(raw['specification']['method']=='budget_two' and
                root['root_started_ns'] <= v['started_ns'] <= v['finished_ns'] <= event['wall_ns'] and
                type(v['closed_before']) is bool and type(v['closed_after']) is bool and
                type(v['sequence_before']) is int and type(v['sequence_after']) is int and
                v['sequence_after'] in (v['sequence_before'],v['sequence_before']+1), 'RPC_attempt_clock')
        return {**result,'RPC_attempts':len(attempts)}
    value = raw.get('failed_root_admission')
    require(raw['failure'] and type(value) is dict and value['status']=='unknown_root_failure'
        and value['closed'] is False and value['root_id']==raw['key'].replace('/',':'), 'missing_failed_root_evidence')
    keys = ('attempt_started_ns','root_started_ns','outside_return_ns','elapsed_ns')
    require(all(type(value[k]) is int and value[k]>=0 for k in keys) and
        value['attempt_started_ns'] <= value['root_started_ns'] <= value['outside_return_ns'] and
        value['elapsed_ns']==value['outside_return_ns']-value['root_started_ns'], 'failed_root_clock')
    encoded = c.image.artifact_encode({k:v for k,v in value.items() if k not in
        ('encoded_sha256','encoded_bytes','outside_return_ns','elapsed_ns')})
    require(c.image.sha_bytes(encoded)==value['encoded_sha256'] and len(encoded)==value['encoded_bytes'],
            'failed_root_codec')
    return {'status':'unknown_root_failure','closed':False,'warm_ms':value['elapsed_ns']/1e6,
            'RPC_attempts':0,'observed_within_100ms':False,'full32_or_universal_100ms_certificate':False}


def predictor_lifetime(life, plan):
    clocks(life, tuple(k for k in ('worker_setup_started_ns','construction_attempt_started_ns',
        'started_ns','ready_ns','close_attempt_started_ns','cleanup_finished_ns') if k in life),
        'predictor_lifetime_clock_type')
    clocks(life, ('worker_setup_started_ns','cleanup_finished_ns'), 'predictor_lifetime_clock_type')
    require(life['worker_setup_started_ns']<=life['cleanup_finished_ns'], 'predictor_setup_clock')
    if 'construction_attempt_started_ns' in life:
        clocks(life, ('construction_attempt_started_ns',), 'predictor_construction_clock_type')
        require(life['worker_setup_started_ns']<=life['construction_attempt_started_ns']<=life['cleanup_finished_ns'],
                'predictor_construction_clock')
    if 'ready' in life:
        require({k:life['ready'][k] for k in plan['expected_READY']}==plan['expected_READY'],'saved_READY_changed')
        require(life['ready']['version']==plan['image']['version'] and life['ready']['mode']=='initial_A_two',
                'saved_READY_identity')
    else:
        require(life['status']=='unknown_predictor_construction' and not life['ledger'] and
            type(life.get('worker_setup_or_loop_failure')) is str and life['worker_setup_or_loop_failure'],
            'missing_READY_promoted')
        return False
    clocks(life, ('construction_attempt_started_ns','started_ns','ready_ns','close_attempt_started_ns'),
           'predictor_lifetime_clock_type')
    require(life['construction_attempt_started_ns']<=life['started_ns'], 'predictor_construction_clock')
    require(life['started_ns']<=life['ready_ns']<=life['close_attempt_started_ns']<=life['cleanup_finished_ns'],
            'predictor_lifetime_clock')
    if 'close' in life:
        clocks(life['close'], ('close_admitted_ns','close_finished_ns'), 'predictor_close_clock_type')
        require(life['close_attempt_started_ns']<=life['close']['close_admitted_ns']<=
            life['close']['close_finished_ns']<=life['cleanup_finished_ns'], 'predictor_close_clock')
    if life['status']=='closed_protocol':
        close=life['close']
        require(close['reply']['source_unchanged'] is True and close['process_exit_code']==0 and
            close['reply']['requests']==len(life['ledger']) and life['process_exit_code']==0 and
            life['close_attempt_started_ns']<=close['close_admitted_ns']<=close['close_finished_ns']<=life['cleanup_finished_ns'],
            'predictor_closed_protocol')
        return True
    require(life['status'] in ('unknown_already_aborted','unknown_close_failure','unknown_cleanup_failure') and
        (life.get('closed_before_close') is True or life.get('error') or life.get('abort_error')),
        'unexplained_predictor_failure')
    return False


def branch_attempt(row, life):
    """Branch envelope includes setup/export; it is never a missing root clock."""
    if row['status']=='unknown_unexecuted':
        require(not any(k in row for k in ('attempt_started_ns','attempt_finished_ns',
                                          'export_started_ns','export_finished_ns')), 'unexecuted_has_attempt_clock')
        return {'status':'not_attempted','elapsed_ms':None,'root_elapsed_ms':None}
    started,finished=clocks(row, ('attempt_started_ns','attempt_finished_ns'), 'branch_attempt_clock_type')
    require('ready' in life and life['ready_ns']<=started<=finished<=life['close_attempt_started_ns'],
            'branch_attempt_clock')
    if row['status']=='raw_saved':
        export_start,export_end=clocks(row, ('export_started_ns','export_finished_ns'), 'branch_export_clock_type')
        require(started<=export_start<=export_end<=finished, 'branch_export_clock')
    return {'status':'recorded_branch_attempt','started_ns':started,'finished_ns':finished,
            'elapsed_ms':(finished-started)/1e6,
            'scope':'Actual branch attempt including native setup and available export; not root computation or cold startup.'}


def verify_saved(output,expected):
    output=Path(output).resolve();plan=c.verify_plan(output,expected)
    ledger=c.read(output/'branch_ledger.json')
    require(list(ledger)==plan['row_order'],'branch_denominator_or_order')
    accepted=c.read(output/'run_acceptance.json')
    require(accepted['status']=='closed_run_acceptance_passed' and accepted['active'] is False and
        accepted['invalid']==[] and accepted['branch_keys']==sorted(plan['rows']) and
        accepted['run_reference']==c.reference(output/'campaign.json'),'run_not_closed')
    require(all(c.sha(p)==h for p,h in accepted['evidence_sha256'].items()),'accepted_file_drift')
    life=c.read(output/'predictor_lifetime.json');samples={s['request_id']:s for s in life['ledger']}
    require(len(samples)==len(life['ledger']) and [s['sequence'] for s in life['ledger']]==list(range(1,len(samples)+1)),
            'RPC_denominator_or_sequence')
    lifecycle_closed=predictor_lifetime(life,plan)
    used,results=set(),{}
    previous_attempt_end=None
    for key in plan['row_order']:
        row=ledger[key]
        require(all(row[f]==plan['rows'][key][f] for f in ('case','method','fault')),'row_specification')
        attempt=branch_attempt(row,life)
        if attempt['status']=='recorded_branch_attempt':
            require(previous_attempt_end is None or previous_attempt_end<=attempt['started_ns'],
                    'branch_attempt_order')
            previous_attempt_end=attempt['finished_ns']
        if row['status']!='raw_saved':
            require(row['status'] in ('unknown_unexecuted','unknown_failed') and
                (row['status']=='unknown_unexecuted' or row.get('exception')),'unexplained_missing_raw')
            results[key]={'root':{'status':row['status'],'closed':False,'warm_ms':None},
                          'business':{'status':'unknown_missing_raw'},'failure':row.get('exception'),
                          'branch_attempt':attempt}
            continue
        path=output/'raw'/(key+'.json.gz');require(row['raw']==c.reference(path),'raw_hash')
        with gzip.open(path,'rt',encoding='utf8') as stream:raw=json.load(stream)
        results[key]=verify_branch(raw,plan['rows'][key],key)
        results[key]['branch_attempt']=attempt
        identity=key.replace('/',':')
        events=raw['root_records'][0]['value']['evidence']['events'] if raw['root_records'] else []
        if identity in samples:
            require(plan['rows'][key]['method']=='budget_two','RPC_in_fixed_control')
            results[key]['prediction_counts']=rpc_replay(samples[identity],raw);used.add(identity)
        else:
            require(not any(e['stage']=='two_choice_reply' for e in events),'missing_actual_RPC_sample')
    require(used==set(samples) and len(samples)<=9,'unaccounted_RPC_or_failed_prefix')
    pairs={key:pair_comparison(results[key.rsplit('/',1)[0]+'/fixed_default'],results[key])
        for key,row in plan['rows'].items() if row['method']=='budget_two'}
    return {'schema':c.SCHEMA,'status':'passed_saved_finite_endpoint_and_physical_audit',
        'campaign_sha256':expected,'rows':results,'pairs':pairs,'branches':18,
        'closed_roots':sum(r['root']['closed'] for r in results.values()),
        'open_or_unknown_roots':sum(not r['root']['closed'] for r in results.values()),
        'predictor_protocol_closed':lifecycle_closed,'predictor_failure_status':None if lifecycle_closed else life['status'],
        'predictor_requests':len(samples),'prediction_counts':{f:sum(r.get('prediction_counts',{}).get(f,0)
            for r in results.values()) for f in ('baseline_evaluation_calls','complete_baselines','additional_candidate_calls')},
        'predictor_startup_ms':(life['ready_ns']-life['started_ns'])/1e6 if 'ready' in life else None,
        'predictor_close_with_cleanup_ms':(life['cleanup_finished_ns']-life['close_attempt_started_ns'])/1e6 if 'ready' in life else None,
        'cold_charge':'All failures/startup/native setup/shutdown/export/verification retained without amortization.',
        'scope':'Exact original endpoint/physical checks; retained closed-process and root-codec failures remain unknown. No native replay/full32/100ms certificate.'}

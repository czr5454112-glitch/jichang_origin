"""Bounded actual airport behavior-data readiness; never trains or runs native."""
from __future__ import annotations

import sys
TOKEN = 'g31_airport_behavior_readiness_v1'
if __name__ == '__main__' and '--run' in sys.argv and sys.stdin.readline().strip() != TOKEN:
    raise SystemExit('airport_behavior_readiness:bounded_parent_admission_required')

import argparse
from collections import Counter
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import time
import traceback

from . import foundation_airport_behavior_evidence as evidence
from . import foundation_airport_behavior_reader as independent_reader

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = 'g31.foundation.airport_behavior_readiness.v1'
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_airport_behavior_readiness'
require, digest = evidence.require, evidence.digest
MINIMUM = {'unique_executed_requests':12, 'disjoint_300s_windows':4, 'source_destination_pairs':2,
           'nonconstant_targets':True}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def ref(path):
    return {'path':str(Path(path).resolve()),'sha256':sha(path)}


def read(path):
    path=Path(path)
    if path.suffix=='.gz':
        with gzip.open(path,'rt',encoding='utf8') as stream:return json.load(stream)
    return json.loads(path.read_bytes())


def write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,allow_nan=False)


def executed_sources():
    return {str(Path(path).resolve()):sha(path)for path in (__file__,evidence.__file__,independent_reader.__file__)}


def resource_budget(revision, *, collection, preregistration):
    """One explicit resource-only revision; the original criteria never change."""
    if revision is None:return 180,210
    require(revision['scope']=='read_only_wall_budget_only' and revision['soft_wall_seconds']==660
        and revision['hard_wall_seconds']==720 and revision['automatic_retries']==0
        and revision['criterion_unchanged'] is True and revision['fit_calls']==revision['native_branches']==0,
        'fixed_resource_only_revision')
    for item in revision['evidence'].values():require(ref(item['path'])==item,'resource_evidence_bytes')
    previous=read(revision['evidence']['previous_plan']['path'])
    failed=read(revision['evidence']['previous_receipt']['path'])
    require(previous['collection']==str(Path(collection).resolve()) and previous['minimum']==MINIMUM
        and previous['training_contract']==evidence.training_contract(Path(collection).name)
        and previous['inputs']['preregistration']==preregistration and previous['soft_wall_seconds']==180
        and failed['plan']==revision['evidence']['previous_plan']
        and failed['status']=='failed_behavior_readiness' and failed['fit_calls']==failed['native_branches']==0
        and failed['exception'].rstrip().endswith('ValueError: airport_behavior_evidence:readiness_wall_budget'),
        'same_collection_contract_and_only_prior_budget_failure')
    return 660,720


def prepare(collection,output,*,development_only=False,preregistration=None,implementation_freeze=None):
    collection=Path(collection).resolve();output=Path(output).resolve()
    require(collection.is_relative_to(ROOT) and output.is_relative_to(ROOT) and not output.exists(),'workspace_closed_collection_and_fresh_output')
    prereg_ref=freeze_ref=None;revision=None
    if not development_only:
        require(preregistration is not None,'immutable_preregistration_required_before_actual_results')
        prereg_ref=ref(preregistration);prereg=read(preregistration)
        require(prereg['collection_plan']==ref(collection/'plan.json') and prereg['minimum']==MINIMUM
            and prereg['contract']==evidence.training_contract(collection.name)
            and prereg['new_collection_results_read'] is False and prereg['new_collection_labels_read'] is False,
            'preregistered_exact_collection_and_fixed_criterion')
        require(implementation_freeze is not None,'source_freeze_required_before_actual_results')
        freeze_ref=ref(implementation_freeze);freeze=read(implementation_freeze)
        require(freeze['source_sha256']==executed_sources() and freeze['preregistration']==prereg_ref,
            'frozen_implementation_matches_unchanged_preregistration')
        if freeze['new_collection_results_read'] is not False:
            repair=freeze['implementation_repair']
            require(repair['criterion_unchanged'] is True
                and repair['scope']=='public_conditional_release_submission_source_binding_only',
                'only_declared_implementation_repair_after_failed_readiness')
            for item in repair['evidence'].values():require(ref(item['path'])==item,'repair_evidence_bytes')
            previous=read(repair['evidence']['previous_freeze']['path'])
            failed=read(repair['evidence']['failed_readiness_receipt']['path'])
            require(previous['preregistration']==prereg_ref and previous['new_collection_results_read'] is False
                and failed['status']=='failed_behavior_readiness'
                and 'actual_pre_submit_tray_source' in failed['exception'],'specific_preserved_failure_and_prior_contract')
        revision=freeze.get('resource_revision')
    soft_seconds,hard_seconds=resource_budget(revision,collection=collection,preregistration=prereg_ref)
    receipt=read(collection/'receipt.json');plan=read(collection/'plan.json')
    require(receipt['process']['status']=='exited' and receipt['process']['exitcode']==0
        and receipt['plan_sha256_at_launch']==sha(collection/'plan.json'),'collection_process_closed_with_bound_plan')
    require(plan['offered_business_count']==28506 and plan['physical_start']==0.
        and plan['same_live_session_across_boundaries'] is True and plan['reset_at_window_boundary'] is False
        and plan['all_unfinished_preserved'] is True,'full_population_continuous_physical_run')
    rawref=receipt['worker_report']['raw'];require(ref(rawref['path'])==rawref,'closed_raw_bytes')
    raw=read(rawref['path']);directory=Path(rawref['path']).parent
    require(raw['offered_count']==28506 and raw['session_instance_count']==1 and raw['physical_reset_count']==0
        and raw['input_sha256']==plan['protocol_input_semantic_sha256'],'raw_full_flow_identity')
    observed=read(directory/'policy_observation_receipt.json')
    require(raw['policy_observations']==observed and observed['contains_true_conditional_outcome_labels'] is False,'exact_actual_callback_receipt')
    inputs={'collection_receipt':ref(collection/'receipt.json'),'collection_plan':ref(collection/'plan.json'),
        'raw':rawref,'observation_receipt':ref(directory/'policy_observation_receipt.json'),
        'trace':observed['artifact'],'client_calls':ref(directory/'client_calls.json.gz'),
        'ack_views':ref(directory/'delivered_ack_views.json.gz')}
    if prereg_ref is not None:inputs['preregistration']=prereg_ref
    if freeze_ref is not None:inputs['implementation_freeze']=freeze_ref
    if freeze_ref is not None and freeze.get('implementation_repair') is not None:
        inputs.update({'repair_'+key:value for key,value in freeze['implementation_repair']['evidence'].items()})
    if revision is not None:
        inputs.update({'resource_'+key:value for key,value in revision['evidence'].items()})
    if 'blobs' in observed:inputs['blobs']=observed['blobs']
    segments=[]
    for segment in raw['segments']:
        inputs['segment_'+str(segment['index'])]=segment['raw']
        segments.append({key:segment[key] for key in ('index','start_at','actual_clock','status','raw')})
    archives={}
    for original,relative in plan['source_archive'].items():
        archived=collection/relative
        require(sha(archived)==plan['source_sha256'][original],'actual_collection_source_archive')
        archives[str(archived)]=sha(archived)
    sources=executed_sources()
    for item in inputs.values():require(ref(item['path'])==item,'registered_input_bytes')
    contract=evidence.training_contract(collection.name)
    audit_plan={'schema':SCHEMA,'status':'prepared_not_executed','collection':str(collection),'output':str(output),
        'inputs':inputs,'source_sha256':sources,'historical_source_sha256':archives,'segments':segments,
        'expected_record_count':observed['record_count'],'training_contract':contract,'minimum':MINIMUM,
        'development_only':bool(development_only),'fit_calls':0,'native_branches':0,'soft_wall_seconds':soft_seconds,
        'resource_revision':revision,
        'raw_global_truth_scope':'offline_action_and_reward_evidence_only_never_actor_input',
        'private_parent_flight_join':False,'same_trajectory_train_only':True}
    output.mkdir(parents=True);write(output/'plan.json',audit_plan)
    task={'task_id':output.name,'module':MODULE,'args':['--run','--output',str(output)],'native_branches':0,
        'hard_seconds':hard_seconds,'inner_admission':TOKEN,'sources':[*sources,*archives,*(r['path']for r in inputs.values()),str(output/'plan.json')],
        'requires':[],'assessment':{'path':str(output/'receipt.json'),'allowed_statuses':['completed_behavior_readiness']},
        'next_action':'Review exclusion counts and actual evidence; fit only under a separately registered train-only plan if minimum passes.'}
    write(output.parent/(output.name+'_task.json'),task)
    return audit_plan


def validate(plan):
    soft_seconds,_=resource_budget(plan.get('resource_revision'),collection=plan['collection'],
        preregistration=plan['inputs'].get('preregistration'))
    require(plan['schema']==SCHEMA and plan['fit_calls']==plan['native_branches']==0
        and plan['minimum']==MINIMUM and plan['soft_wall_seconds']==soft_seconds,'registered_readiness_scope')
    require(plan['training_contract']==evidence.training_contract(Path(plan['collection']).name),'fixed_train_only_contract')
    for path,expected in {**plan['source_sha256'],**plan['historical_source_sha256']}.items():
        require(sha(path)==expected,'readiness_source_pin')
    for item in plan['inputs'].values():require(ref(item['path'])==item,'readiness_input_pin')


def records(plan):
    if 'blobs' in plan['inputs']:
        yield from independent_reader.read_records(plan['inputs']['trace']['path'],plan['inputs']['blobs']['path'])
    else:
        with gzip.open(plan['inputs']['trace']['path'],'rt',encoding='utf8') as stream:
            for line in stream:yield json.loads(line)


def disjoint_count(starts):
    previous_end=-float('inf');count=0
    for start in sorted(set(starts)):
        if start>=previous_end:
            count+=1;previous_end=start+evidence.WINDOW_SECONDS
    return count


def run(output):
    output=Path(output);plan=read(output/'plan.json');validate(plan)
    started=time.monotonic();deadline=started+plan['soft_wall_seconds'];counts=Counter();classes=Counter()
    report={'schema':SCHEMA,'status':'failed_behavior_readiness','plan':ref(output/'plan.json'),'fit_calls':0,'native_branches':0}
    try:
        def budget():require(time.monotonic()<deadline,'readiness_wall_budget')
        raw=read(plan['inputs']['raw']['path']);index=evidence.snapshot_index(raw['final_result'])
        calls=read(plan['inputs']['client_calls']['path']);acks=read(plan['inputs']['ack_views']['path'])
        control={};archived_calls=[];complete_segment_refs=[]
        for segment in plan['segments']:
            budget();content=read(segment['raw']['path'])
            archived_calls.extend(content['client_calls'])
            # A soft stop is eligible only if the timestamp and complete
            # control records are saved. A truncated event timestamp is not.
            continuation=content.get('control_continuation',{})
            complete=(content['result'] is not None
                and content['result']['advance']['status']=='reached'
                and content['result']['advance']['horizon_complete'] is True
                and (continuation.get('timestamp_complete') is True or
                     content['status']=='reached' and continuation['requested_horizon']==segment['actual_clock']))
            if not complete:
                counts['excluded_incomplete_segments']+=1;continue
            require(content['result']['physical_clock']==segment['actual_clock'],'segment_snapshot_clock')
            complete_segment_refs.append(segment['raw'])
            for tick in content['control_records']:
                for decision in tick['owner_decisions']:
                    key=(tick['at'],decision['owner_id'])
                    require(key not in control,'unique_actual_control_owner_tick')
                    control[key]=decision
        require(archived_calls==calls,'saved_segment_calls_equal_final_archive')
        eligible_starts=[];pairs=set();targets=[];eligible_ids=set();seen_controls=set();sequence=0
        excluded_path=output/'classifications.jsonl.gz';rows_path=output/'eligible_behavior_rows.jsonl.gz'
        with gzip.open(excluded_path,'xt',encoding='utf8') as classifications,gzip.open(rows_path,'xt',encoding='utf8') as eligible:
            for key,group in itertools.groupby(records(plan),key=lambda row:(row['now'],row['owner_id'])):
                budget();callbacks=list(group)
                for row in callbacks:
                    require(row['sequence']==sequence,'complete_callback_sequence');sequence+=1
                counts['callback_records']+=len(callbacks);counts['callback_groups']+=1
                now,owner=key
                if key not in control:
                    classifications.write(json.dumps({'at':now,'owner':owner,'status':'missing_complete_control_tick','callbacks':len(callbacks)})+'\n')
                    classes['missing_complete_control_tick']+=len(callbacks);continue
                require(key not in seen_controls,'one_callback_group_per_owner_tick');seen_controls.add(key)
                submitted=evidence.bind_submissions(callbacks,control[key],calls,at=now)
                counts['exact_submitted_actions']+=len(submitted)
                callback_index={row['sequence']:row for row in callbacks}
                for action in submitted:
                    classified={'request_id':action['actual_request']['request_id'],'at':now,'owner':owner,
                        'callback_sequence':action['callback_sequence'],'target_value':None}
                    if now<evidence.FORECAST_FROZEN_AT or now+evidence.WINDOW_SECONDS>min(evidence.LABELS_CLOSED_AT,index['clock']):
                        classified['status']='outside_closed_training_label_window'
                    else:
                        actual=evidence.execution_asof(action,index,acks[owner],label_end=now+evidence.WINDOW_SECONDS)
                        classified['status']=actual['status']
                        if actual['status']=='actual_execution_and_delivered_ack_bound':
                            label=evidence.realized_return(index,start=now)
                            identity=action['actual_request']['request_id'];require(identity not in eligible_ids,'unique_training_action')
                            eligible_ids.add(identity);eligible_starts.append(now);targets.append(label['target_value'])
                            pairs.add((action['actual_request']['source'],action['actual_request']['destination']))
                            row={'schema':SCHEMA,'split':'train','parent_group':plan['training_contract']['parent_group'],
                                'callback_record':callback_index[action['callback_sequence']],'submission':action,'execution':actual,
                                'behavior_label':label,'target_value':label['target_value'],
                                'forecast_and_action_features_not_yet_materialized':True,'native_execution_authority':False}
                            eligible.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
                            classified['target_value']=label['target_value']
                    classes[classified['status']]+=1
                    classifications.write(json.dumps(classified,separators=(',',':'),allow_nan=False)+'\n')
        require(counts['callback_records']==plan['expected_record_count'],'all_registered_callback_records_read')
        require(all(key in seen_controls for key in control if 43200.<=key[0]<=59400.),'all_recorded_window_control_ticks_have_callback_group')
        metrics={'unique_executed_requests':len(eligible_ids),'disjoint_300s_windows':disjoint_count(eligible_starts),
                 'source_destination_pairs':len(pairs),'nonconstant_targets':len(set(targets))>1}
        enough=all(metrics[key]>=threshold for key,threshold in MINIMUM.items())
        validate(plan)
        report.update(status='completed_behavior_readiness',counts=dict(counts),classifications=dict(classes),
            metrics=metrics,minimum=MINIMUM,minimum_passed=enough,
            eligible_for_separate_training_plan=enough and not plan['development_only'],
            development_only=plan['development_only'],fit_calls=0,complete_segment_count=len(complete_segment_refs),
            eligible_rows=ref(rows_path),classification_artifact=ref(excluded_path),source_exit_pins_passed=True,
            independent_test=False,counterfactual_labels=False,full_day_completion_established=False,
            native_population_deleted=0,private_parent_flight_join=False,
            claim='Same-trajectory actual behavior evidence only; forecasts/features and any fitting require a separate frozen task.')
    except Exception:
        report.update(exception=traceback.format_exc(),counts=dict(counts),classifications=dict(classes))
    report['wall_seconds']=time.monotonic()-started;write(output/'receipt.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--collection',type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--preregistration',type=Path)
    parser.add_argument('--implementation-freeze',type=Path)
    parser.add_argument('--development-only',action='store_true');args=parser.parse_args()
    result=prepare(args.collection,args.output,development_only=args.development_only,preregistration=args.preregistration,
        implementation_freeze=args.implementation_freeze) if args.prepare else run(args.output)
    print(json.dumps({'status':result['status'],'fit_calls':0,'native_branches':0}))
    return 0 if result['status'] in ('prepared_not_executed','completed_behavior_readiness') else 1


if __name__=='__main__':raise SystemExit(main())

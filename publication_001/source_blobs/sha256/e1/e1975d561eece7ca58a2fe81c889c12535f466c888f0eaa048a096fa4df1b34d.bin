"""Bounded independent audit of actual airport behavior labels and weights.

No fitting or native execution. Saved callback descriptor preimages, physical
receipts and full-population returns are checked independently. Numerical
forwards use a stdlib MLP; the frozen public feature validator is reused.
"""
from __future__ import annotations
import sys
TOKEN='g31_airport_actual_behavior_review_v1'
if __name__=='__main__' and '--run' in sys.argv and sys.stdin.readline().strip()!=TOKEN:
    raise SystemExit('airport_behavior_review:bounded_parent_admission_required')
import argparse
from collections import Counter,defaultdict
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'
MODULE='scripts.experiments.g31_ics_circulation.foundation_airport_behavior_review'
SEEDS=[17,29,43]
POSITIVE={'accepted','granted','dispatching','departed','in_transit','received'}


def require(ok,reason):
    if not ok:raise ValueError('airport_behavior_review:'+reason)


def digest(value,*,sorted_keys=True):
    return hashlib.sha256(json.dumps(value,sort_keys=sorted_keys,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()


def read(path):
    if str(path).endswith('.gz'):
        with gzip.open(path,'rt',encoding='utf8')as f:return json.load(f)
    return json.loads(Path(path).read_bytes())


def lines(path):
    with gzip.open(path,'rt',encoding='utf8')as f:
        for line in f:yield json.loads(line)


def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}


def write(path,value):
    with Path(path).open('x',encoding='utf8')as f:json.dump(value,f,indent=2,allow_nan=False)


def prepare(output):
    output=Path(output).resolve();require(output.is_relative_to(BASE) and not output.exists(),'fresh_output')
    train=BASE/'B2_behavior_training_001';tr=read(train/'receipt.json');tp=read(train/'plan.json')
    ready=Path(tp['inputs']['readiness_receipt']['path']).parent;rr=read(ready/'receipt.json');rp=read(ready/'plan.json')
    require(tr['status']=='completed_train_only_behavior_pretraining' and tr['training_rows']==81,'actual_training_closed')
    registrations=list((BASE/'attempts').glob('B2_behavior_training_001_*/registration.json'))
    require(len(registrations)==1,'unique_training_attempt')
    inputs={**tp['inputs'],**{'physical_'+k:rp['inputs'][k] for k in ('raw','client_calls','ack_views','trace','blobs')},
        'training_receipt':ref(train/'receipt.json'),'training_plan':ref(train/'plan.json'),
        'training_registration':ref(registrations[0]),'training_outer_receipt':ref(registrations[0].with_name('receipt.json')),
        'materialization':tr['materialization'],'materialized_rows':ref(train/'materialized_training_rows.jsonl.gz'),
        'diagnostic':tr['forecast_action_diagnostic'],'fixed_pairs':ref(train/'fixed_diagnostic_pairs.json'),
        'classifications':rr['classification_artifact']}
    inputs.update({'model_'+str(m['seed']):m['checkpoint']for m in tr['models']})
    for original,item in tp['executed_readiness_source_archive'].items():inputs['ready_source_'+Path(original).name]=item
    sources={**tp['source_sha256'],str(Path(__file__).resolve()):sha(__file__)}
    consumer=Path(__file__).with_name('foundation_airport_behavior_consumer.py');sources[str(consumer)]=sha(consumer)
    plan={'schema':'g31.actual_airport_behavior_review.v1','status':'prepared_not_executed','inputs':inputs,
        'sources':sources,'soft_wall_seconds':60,'native_branches':0,'fit_calls':0,'expected_rows':81,
        'scope':'Independent 81 descriptor/physical/label joins and stdlib model forwards; no counterfactual outcomes or native benefit claim.'}
    output.mkdir();write(output/'plan.json',plan)
    task={'task_id':output.name,'module':MODULE,'args':['--run','--output',str(output)],'native_branches':0,
        'hard_seconds':90,'inner_admission':TOKEN,'sources':[*sources,*(v['path']for v in inputs.values()),str(output/'plan.json')],
        'requires':['B2_behavior_training_001'],'assessment':{'path':str(output/'receipt.json'),'allowed_statuses':['completed_independent_actual_behavior_review']},
        'next_action':'Review exact label/weight evidence before a separately registered score-only native shadow diagnostic.'}
    write(output.parent/(output.name+'_task.json'),task);return plan


def descriptor_preimage(descriptor,actual):
    kind=descriptor['kind']
    if kind=='inline':require(descriptor=={'kind':'inline','value':actual},'inline_preimage')
    elif kind=='value':require(descriptor=={'kind':'value','sha256':digest(actual,sorted_keys=False)},'value_preimage')
    elif kind=='list':
        require(type(actual)is list and descriptor=={'kind':'list','length':len(actual),
            'chunks':[digest(actual[i:i+64],sorted_keys=False)for i in range(0,len(actual),64)]},'ordered_list_preimages')
    elif kind=='object':
        require(set(descriptor)=={'kind','fields'} and type(actual)is dict and set(descriptor['fields'])==set(actual),'object_domain')
        for key,item in descriptor['fields'].items():descriptor_preimage(item,actual[key])
    else:raise ValueError('unsupported_descriptor')


def standard_forward(model,features):
    p=model['parameters'];names=model['feature_names']
    require(sorted(features)==names,'exact_feature_names')
    x=[(features[k]-c)/s for k,c,s in zip(names,p['center'],p['scale'],strict=True)]
    for index,layer in enumerate(p['layers']):
        require(all(len(row)==len(x)for row in layer['weight']),'actual_layer_dimensions')
        x=[math.fsum(a*b for a,b in zip(row,x,strict=True))+bias for row,bias in zip(layer['weight'],layer['bias'],strict=True)]
        if index<len(p['layers'])-1:x=[math.tanh(v)for v in x]
    require(len(x)==1,'scalar_actual_output')
    return x[0]*p['target_scale']+p['target_center']


def close(a,b):return math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-6)


def run(output):
    output=Path(output);p=read(output/'plan.json');started=time.monotonic();deadline=started+60
    result={'schema':p['schema'],'status':'failed_independent_actual_behavior_review','plan':ref(output/'plan.json'),
        'fit_calls':0,'native_branches':0,'checks':{}}
    checks=result['checks']
    def budget():require(time.monotonic()<deadline,'review_wall_budget')
    def bound(key):
        item=p['inputs'][key];require(sha(item['path'])==item['sha256'],'input_'+key);return read(item['path'])
    try:
        require(p['soft_wall_seconds']==60 and p['expected_rows']==81 and p['native_branches']==p['fit_calls']==0,'fixed_audit_scope')
        for path,expected in p['sources'].items():require(sha(path)==expected,'source_pin')
        for item in p['inputs'].values():budget();require(sha(item['path'])==item['sha256'],'input_pin')
        tr=bound('training_receipt');tp=bound('training_plan');rr=bound('readiness_receipt');rp=bound('readiness_plan')
        require(tr['plan']==p['inputs']['training_plan'] and rr['plan']==p['inputs']['readiness_plan'],'closed_inner_plans')
        for prefix,receipt,planref,sourcepins in (('training',tr,p['inputs']['training_plan'],tp['source_sha256']),
                ('readiness',rr,p['inputs']['readiness_plan'],rp['source_sha256'])):
            registration=bound(prefix+'_registration');outer=bound(prefix+'_outer_receipt')
            require(outer['status']=='completed' and outer['process']['status']=='exited' and outer['process']['exitcode']==0
                and outer['source_changed']==[] and outer['assessment']==receipt,'closed_outer_'+prefix)
            require(registration['source_pins'].get(planref['path'])==planref['sha256'] and registration['native_branches']==0,'registered_plan_'+prefix)
            archived={};base=Path(p['inputs'][prefix+'_registration']['path']).parent
            for index,(path,expected)in enumerate(registration['source_pins'].items()):
                if path in sourcepins:
                    a=base/'source'/(f'{index:04d}'+Path(path).suffix)
                    require(expected==sourcepins[path]==sha(a),'executed_source_'+prefix);archived[path]=expected
            require(archived==sourcepins,'complete_source_archive_'+prefix)
        require(rr['minimum']=={'unique_executed_requests':12,'disjoint_300s_windows':4,'source_destination_pairs':2,'nonconstant_targets':True}
            and rr['minimum_passed'] is True and rr['eligible_for_separate_training_plan'] is True and rr['development_only'] is False,'fixed_readiness_gate')
        require(tp['training_contract']==rp['training_contract']==bound('preregistration')['contract'],'original_training_contract')
        require(tp['seeds']==SEEDS and tp['epochs']==100 and tp['observed_counts'] is None and tr['fit_calls_completed']==3,'actual_fixed_three_fits')
        checks['sources_registration_and_outer_assessments']=True
        eligible=list(lines(p['inputs']['eligible_rows']['path']));require(len(eligible)==81,'complete_eligible_rows')
        byseq={r['callback_record']['sequence']:r for r in eligible};require(len(byseq)==81,'unique_eligible_callbacks')
        found=set();trace_count=0
        for encoded in lines(p['inputs']['physical_trace']['path']):
            budget();require(encoded['sequence']==trace_count,'complete_source_trace_sequence');trace_count+=1
            if encoded['sequence']not in byseq:continue
            original=byseq[encoded['sequence']]['callback_record'];require(set(encoded)==set(original),'callback_field_domain')
            for key in encoded:
                if key in ('observation','decision','policy_options'):descriptor_preimage(encoded[key],original[key])
                else:require(encoded[key]==original[key],'callback_scalar_identity')
            found.add(encoded['sequence'])
        require(found==set(byseq) and trace_count==rr['counts']['callback_records']==2717,'all_actual_callback_preimages')
        checks['actual_callback_descriptor_preimages']=len(found)
        raw=bound('physical_raw');physical=raw['final_result'];jobs={j['business_bag_id']:j for j in physical['jobs']}
        require(len(jobs)==len(physical['jobs'])==28506 and raw['session_instance_count']==1 and raw['physical_reset_count']==0,'full_physical_population')
        require(physical['advance']['status']=='reached' and physical['advance']['horizon_complete'] is True,'closed_physical_snapshot')
        arrivals={};completions={};receipts=defaultdict(list);requests=defaultdict(list)
        for event in physical['receipts']:
            require(0<=event['time']<=physical['physical_clock'],'physical_event_clock')
            if event['event']in('BAG_ARRIVAL','UNLOAD_COMPLETE'):
                d=arrivals if event['event']=='BAG_ARRIVAL' else completions;k=event['business_bag_id']
                require(k in jobs and k not in d,'unique_business_event');d[k]=event['time']
            if event.get('transport_leg_id'):receipts[event['transport_leg_id']].append(event)
            if event['event']in('EXPORT_GRANTED','EMPTY_RECEIVED','MODULE_REQUEST_DELIVERED'):requests[event['reason']].append(event)
        for identity,job in jobs.items():
            require((identity in arrivals)==(job['status']!='unreleased'),'actual_arrival_status')
            require((identity in completions)==(job['status']=='completed')==(job['completed_at']>=0),'actual_completion_status')
            if identity in completions:require(arrivals[identity]<=completions[identity]==job['completed_at'],'actual_completion_time')
        calls=defaultdict(list)
        for call in bound('physical_client_calls'):
            if call['kind']=='transfer' and call['retry'] is False:calls[call['request']['request_id']].append(call)
        acks=bound('physical_ack_views');legs=defaultdict(list)
        for leg in physical['leg_identities']:legs[leg['transport_leg_id']].append(leg)
        transfers={t['request_id']:t for t in physical['transfers']};rows=[];seen=set();pairs=set();starts=[];targets=[]
        for item in eligible:
            budget();cb=item['callback_record'];sub=item['submission'];ex=item['execution'];label=item['behavior_label'];req=sub['actual_request']
            now=cb['now'];end=now+300;identity=req['request_id'];require(identity not in seen,'unique_actual_request');seen.add(identity)
            require(item['split']=='train' and item['parent_group']==tp['training_contract']['parent_group'],'same_trajectory_only')
            require(sub['callback_sha256']==digest(cb) and sub['callback_sequence']==cb['sequence'] and sub['at']==now,'callback_submission_binding')
            expected=copy.deepcopy(cb['decision']['intents'][0]);expected.pop('expected_version',None);expected.update(request_id=identity,owner_id=cb['owner_id'])
            require(req==expected and len(calls[identity])==1,'first_actual_nonretry_payload')
            call=calls[identity][0];require(call['request']==req and call['reply']==sub['submission_reply'] and call['at']==now and digest(call)==sub['call_sha256'],'actual_call_bytes')
            leg=ex['native_leg'];lid=identity+':empty_return:'+str(leg['runtime_id']);require(leg['transport_leg_id']==lid and legs[lid]==[leg] and leg['job']==-1,'unique_actual_request_leg')
            transfer=transfers[identity];require(leg['tray']==transfer['tray'] and physical['trays'][leg['tray']]['tray_id']==req['tray_id'],'real_tray_index')
            edges=sorted((r for r in receipts[lid]if r['event']=='EDGE_ENTER'),key=lambda r:r['time']);edge=edges[0]
            require(edge==ex['first_edge'] and edge['from']==req['source'] and edge['tray_id']==req['tray_id']
                and edge['time']==transfer['departed_at'] and len([r for r in edges if r['time']==edge['time']])==1,'actual_unique_first_edge')
            require(max(now+req['message_delay'],req['earliest_departure'])<=edge['time']<=end,'execution_inside_label_window')
            for collection,event in ((requests[identity],'EXPORT_GRANTED'),(receipts[lid],'LEG_START')):
                actual=[r for r in collection if r['event']==event and now<=r['time']<=edge['time']]
                require(len(actual)==1 and actual[0]['from']==req['source'] and actual[0]['to']==req['destination'] and actual[0]['tray_id']==req['tray_id'],'real_export_and_leg_start')
            delivered=[a for a in acks[cb['owner_id']]['delivered_transfer_acks']if a['request_id']==identity and a['delivered_at']<=end]
            require(ex['positive_ack'] in delivered and ex['positive_ack']['status']in POSITIVE
                and now<=ex['positive_ack']['observed_at']<=ex['positive_ack']['delivered_at']<=end,'actual_owner_delivered_ack')
            require(not any(a['status']in('rejected','expired')for a in delivered),'no_rejected_execution_label')
            require(43200<=now and end<=min(57600,physical['physical_clock']) and label['physical_population']==28506,'original_label_scope')
            target=-math.fsum(max(0.,min(end,completions.get(k,end))-max(now,at))for k,at in arrivals.items()if at<end)
            require(target==label['target_value']==item['target_value'] and label['label_start']==now and label['label_end']==end,'independent_full_population_integral')
            pairs.add((req['source'],req['destination']));starts.append(now);targets.append(target)
            rows.append({'sequence':cb['sequence'],'request_id':identity,'source':req['source'],'destination':req['destination'],
                'at':now,'target_value':target,'first_edge_time':edge['time'],'ack_delivered_at':ex['positive_ack']['delivered_at']})
        boundary=-1;disjoint=0
        for t in sorted(set(starts)):
            if t>=boundary:disjoint+=1;boundary=t+300
        metrics={'unique_executed_requests':len(seen),'disjoint_300s_windows':disjoint,'source_destination_pairs':len(pairs),'nonconstant_targets':len(set(targets))>1}
        require(metrics==rr['metrics'],'independent_minimum_metrics')
        classified=list(lines(p['inputs']['classifications']['path']));classes=Counter(c['status']for c in classified)
        require(dict(classes)==rr['classifications'] and len(classified)==2349,'complete_actual_classifications')
        require(all((c['target_value']is not None)==(c['status']=='actual_execution_and_delivered_ack_bound')for c in classified),'unexecuted_unknown_not_zero_labels')
        checks.update(physical_label_rows=len(rows),full_population=28506,metrics=metrics,classifications=dict(classes))
        write(output/'independent_label_bindings.json',rows)
        del raw,physical,calls,acks,receipts,requests,legs,transfers
        from . import foundation_action_value as value
        from . import foundation_airport_behavior_consumer as consumer
        material=bound('materialization');mrows=list(lines(p['inputs']['materialized_rows']['path']));require(len(mrows)==81,'complete_materialized_rows')
        vectors=[];original_rows=[];bysequence={}
        for item,mat,meta in zip(eligible,mrows,material['records'],strict=True):
            budget();row=mat['row'];obs=row['observation'];cb=item['callback_record']
            require(row['target_value']==item['target_value'] and row['split']=='train' and obs['base_observation']==cb['observation'],'no_postdecision_state_or_label_leak')
            require(mat['evidence']==meta and meta['input_evidence_sha256']==digest(item)
                and meta['normalization']['original_record_sha256']==digest(cb),'materialized_actual_evidence_binding')
            require(obs['information_variant']=='static_plan' and meta['observed_counts'] is None,'public_prior_only')
            features=value.features(obs,row['action']);require(digest(features)==meta['feature_sha256'],'all_actual_features_exact')
            require(all(math.isfinite(v)for v in features.values()),'finite_features_and_masks')
            vectors.append(features);original_rows.append(row);bysequence[cb['sequence']]=(cb,obs)
        fixed=bound('fixed_pairs');diagnostic=bound('diagnostic');require(fixed['selected_before_fitting']is True and len(fixed['pairs'])<=3,'fixed_diagnostic_selection')
        from . import foundation_airport_learning_public as public
        expected_pairs=[]
        for item,mat in zip(eligible,mrows,strict=True):
            if len(expected_pairs)==3:break
            cb=copy.deepcopy(item['callback_record']);cb['schema']='g31.foundation.airport_policy_observation.v1'
            candidates=public.proposal_actions(cb);first=candidates[0]
            other=next((c for c in candidates[1:]if c['semantic']!=first['semantic']),None)
            if other:expected_pairs.append((item['callback_record']['sequence'],[first,other]))
        require([r['callback_sequence']for r in fixed['pairs']]==[r[0]for r in expected_pairs],'first_real_distinct_pairs_only')
        for pair,(_,actual)in zip(fixed['pairs'],expected_pairs,strict=True):
            require(pair['actions']==[c['semantic']for c in actual] and pair['proposal_sha256']==[c['source_proposal_sha256']for c in actual]
                and pair['observation']==bysequence[pair['callback_sequence']][1],'diagnostic_original_public_pair')
        model_reports=[]
        require([m['seed']for m in tr['models']]==SEEDS and diagnostic['all_fixed_seeds']==SEEDS,'all_fixed_models_and_diagnostics')
        for modelrow,diag in zip(tr['models'],diagnostic['results'],strict=True):
            budget();model=bound('model_'+str(modelrow['seed']))
            require(digest(model)==modelrow['content_sha256'] and model['epochs']==100 and model['seed']==modelrow['seed']
                and model['training_row_count']==81 and model['training_rows_sha256']==digest(original_rows),'actual_model_and_training_data_bytes')
            require([r['epoch']for r in model['training_curve']]==list(range(0,101,10))
                and all(math.isfinite(r['mse']) and r['mse']>=0 for r in model['training_curve']),'all_100_epoch_curve')
            scores=[standard_forward(model,f)for f in vectors];mse=math.fsum((s-y)**2 for s,y in zip(scores,targets,strict=True))/81
            require(close(mse,modelrow['training_mse']),'independent_actual_forward_training_MSE')
            descriptor={**modelrow['checkpoint'],'training_receipt':p['inputs']['training_receipt']}
            try:consumer.validate_behavior_checkpoint({'now':57599.999},descriptor)
            except ValueError as error:require('unavailable_before_registered_57600' in str(error),'early_gate_reason')
            else:raise ValueError('early_model_use_not_rejected')
            gate_obs={'now':57600.,'schema':value.OBSERVATION_SCHEMA,'mapping_version':model['mapping_version'],'information_variant':'static_plan'}
            require(consumer.validate_behavior_checkpoint(gate_obs,descriptor)==model,'actual_checkpoint_cutoff_gate')
            gap_results=[]
            for pair,saved in zip(fixed['pairs'],diag['pairs'],strict=True):
                gaps={}
                for name in ('actual_forecast','forecast_values_masked','zero_new_demand'):
                    observation=copy.deepcopy(pair['observation']);forecast=observation['demand_forecast']
                    if name!='actual_forecast':
                        for region,missing in list(forecast['missing_mask_by_region'].items()):
                            if missing:continue
                            forecast['new_demand_mean_by_region'][region]=[None if name=='forecast_values_masked' else 0. for _ in forecast['new_demand_mean_by_region'][region]]
                            forecast['missing_mask_by_region'][region]=name=='forecast_values_masked'
                            forecast['uncertainty_by_region'][region]=None
                        forecast['window_summaries_by_region']={}
                    actual=[standard_forward(model,value.features(observation,a))for a in pair['actions']]
                    require(all(close(a,b)for a,b in zip(actual,saved['scores'][name],strict=True)),'independent_diagnostic_scores')
                    gaps[name]=actual[0]-actual[1]
                    require(close(gaps[name],saved['chosen_minus_other_score'][name]),'independent_action_score_gap')
                deltas={key:gaps[key]-gaps['actual_forecast']for key in gaps if key!='actual_forecast'}
                require(all(close(delta,saved['gap_change_from_actual_forecast'][key])for key,delta in deltas.items()),'independent_nonadditive_gap_change')
                gap_results.append({'sequence':pair['callback_sequence'],'gap_changes':deltas,'numerical_nonadditivity':any(abs(d)>1e-8 for d in deltas.values())})
            model_reports.append({'seed':model['seed'],'epochs':100,'checkpoint':modelrow['checkpoint'],'training_mse_stdlib':mse,
                'initial_curve_mse':model['training_curve'][0]['mse'],'final_curve_mse':model['training_curve'][-1]['mse'],
                'early_gate_rejected':True,'at_cutoff_checkpoint_validation_passed':True,'diagnostics':gap_results})
        checks.update(materialized_features_verified=81,stdlib_training_forwards=243,models=model_reports)
        budget()
        for path,expected in p['sources'].items():require(sha(path)==expected,'source_exit_pin')
        result.update(status='completed_independent_actual_behavior_review',sources_unchanged=True,
            full_source_trace_decoded_again=False,descriptor_preimage_proof_scope='All 81 embedded callback values independently hash to their actual v2 trace descriptors; the complete blob artifact bytes are pinned, not re-decoded.',
            native_benefit_or_independent_test_established=False,model_selection_performed=False,
            availability_probe_scope='Actual checkpoint metadata gate at 57600 only, not a fabricated live observation or native consumption.',
            label_binding_artifact=ref(output/'independent_label_bindings.json'))
    except Exception:result['exception']=traceback.format_exc()
    result['wall_seconds']=time.monotonic()-started;write(output/'receipt.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--run',action='store_true');parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();r=prepare(args.output)if args.prepare else run(args.output)
    print(json.dumps({'status':r['status'],'native_branches':0,'fit_calls':0}))
    raise SystemExit(0 if r['status']in('prepared_not_executed','completed_independent_actual_behavior_review')else 1)

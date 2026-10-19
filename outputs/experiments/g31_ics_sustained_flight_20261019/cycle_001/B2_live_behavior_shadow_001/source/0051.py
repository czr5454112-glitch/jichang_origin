"""Two registered live public shadow scores; original baseline retains authority.

This independently versioned entry point preserves the completed baseline's
input and full continuous window. Preparation requires real final weights.
The existing 107 source files and all old attempts remain unchanged.
"""
from __future__ import annotations

import sys
if __name__ == '__main__' and '--worker' in sys.argv:
    _index = sys.argv.index('--admission') if '--admission' in sys.argv else -1
    _token = sys.argv[_index+1] if 0 <= _index < len(sys.argv)-1 else None
    if not _token or _token.startswith('--') or sys.stdin.readline().strip() != _token:
        raise SystemExit('airport_shadow:missing_parent_job_admission')

import argparse
import copy
import json
from pathlib import Path
import time

from . import foundation_airport_recorded_budget_campaign as budget
from . import foundation_airport_recorded_campaign as delegate
from .foundation_airport_shadow_planner import ShadowPlanner

MODULE = 'scripts.experiments.g31_ics_circulation.foundation_airport_shadow_campaign'
SCHEMA = 'g31.foundation.airport_live_behavior_shadow_campaign.v1'
ROOT = delegate.ROOT
CYCLE = ROOT / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'
BASELINE = CYCLE / 'C00_receiver_recorded_budget_002'
SELECTION = CYCLE / 'C00_receiver_recorded_budget_002_review_001/shadow_callback_selection_300.json'
SCORER_FREEZE = CYCLE / 'B2_behavior_shadow_scorer_freeze_001.json'
SCORER_FREEZE_SHA = '31545bfdedf4ab01e80dde26894f5d3b1a78fb246dc8daad2031972cd3957d40'
BASELINE_PLAN_SHA = 'acd87e90e9e06d143a67e18eba74907620a0a832e3be196f60eb04327d37392e'
TARGETS = [('owner:system_international',57840.,3582,0,'live:26:owner:system_international:transfer:1942'),
           ('owner:system_domestic',57900.,3585,0,'live:21:owner:system_domestic:transfer:9017')]
_BASE_CHECK = delegate.check_pins
_configured = False
read,sha,reference,write_new,require = delegate.read,delegate.sha,delegate.reference,delegate.write_new,delegate.require


def bound(ref):
    require(sha(ref['path'])==ref['sha256'],'shadow_artifact_bytes:'+ref['path'])
    return read(ref['path'])


def contract():
    return {'schema':SCHEMA,'maximum_callbacks':2,'fixed_seeds':[17,29,43],
        'target_selection':'posthoc seen baseline; both first edge and positive delivered ACK within300s',
        'purpose':'train-trajectory live mechanism diagnostic only',
        'scores_select_action':False,'baseline_decision_object_returned':True,
        'extra_native_queries':0,'extra_native_commands':0,'model_fit_calls':0,
        'automatic_retries':0,'native_branches':1,'soft_seconds':600,'inner_hard_seconds':660,'outer_hard_seconds':720,
        'candidate_guard_or_execution_authority':False,'policy_gain_established':False,
        'complete_request_100ms_certified':False,'same_baseline_input_warmup_and_window':True,
        'runtime_binding_requires_separate_closed_submit_ACK_edge_audit':True}


def validate_resources(resources, mapping):
    require(resources['contract']==contract(),'shadow_fixed_contract')
    selection=bound(resources['selection'])
    require(selection['schema']=='g31.airport_reference_selected_shadow_callbacks.v2'
        and selection['positive_ACK_within300_required'] is True
        and selection['scores_select_or_modify_native_action'] is False
        and selection['future_receipts_used_only_offline_for_witness_selection'] is True
        and selection['selected_count']==2,'shadow_selection_contract')
    actual=[(r['callback']['owner_id'],r['callback']['now'],r['callback']['sequence'],
             r['callback']['residual_index'],r['actual_request']['request_id']) for r in selection['selected']]
    require(actual==TARGETS and all(0<=r[k]<=300 for r in selection['selected']
        for k in ('first_edge_delay_seconds','first_positive_ack_delay_seconds')),'shadow_exact_targets')
    require(selection['reference_plan']==resources['baseline_plan'],'shadow_selection_baseline')
    old=bound(resources['baseline_plan']);receipt=bound(resources['baseline_receipt'])
    require(resources['baseline_plan']['sha256']==BASELINE_PLAN_SHA and old['branch']=='C00'
        and receipt['plan_sha256_at_launch']==BASELINE_PLAN_SHA
        and receipt['status']=='requested_calibration_end_reached'
        and receipt['worker_report']['acceptance_status']=='closed_run_acceptance_passed',
        'shadow_closed_reference')
    require(selection['reference_raw']==receipt['worker_report']['raw'],'shadow_reference_raw')
    require(sha(selection['reference_raw']['path'])==selection['reference_raw']['sha256'],'shadow_reference_raw_bytes')
    freeze=bound(resources['scorer_freeze'])
    require(resources['scorer_freeze']['sha256']==SCORER_FREEZE_SHA,'shadow_registered_scorer_freeze')
    for path,expected in freeze['source_sha256'].items():require(sha(path)==expected,'shadow_frozen_scorer_source')
    descriptors=bound(resources['model_manifest'])
    require(descriptors['schema']=='g31.airport_behavior_shadow_models.v1'
        and [r['seed'] for r in descriptors['model_descriptors']]==[17,29,43],'shadow_all_fixed_seeds')
    training={key:bound(descriptors[key]) for key in
        ('training_receipt','training_plan','training_registration','training_outer_receipt')}
    registered,outer=training['training_registration'],training['training_outer_receipt']
    require(training['training_receipt']['plan']==descriptors['training_plan']
        and registered['source_pins'][descriptors['training_plan']['path']]==descriptors['training_plan']['sha256']
        and outer['status']=='completed' and outer['source_changed']==[]
        and outer['assessment']==training['training_receipt']
        and Path(descriptors['training_registration']['path']).parent==Path(descriptors['training_outer_receipt']['path']).parent,
        'shadow_closed_registered_training_chain')
    from .foundation_airport_behavior_consumer import validate_behavior_checkpoint
    from .foundation_airport_learning_public import VERSION as PUBLIC_VERSION
    availability={'now':57660.,'schema':'g31.foundation.flight_aware_observation.v2',
                  'mapping_version':mapping['version']+'+'+PUBLIC_VERSION,'information_variant':'static_plan'}
    for row in descriptors['model_descriptors']:
        require(row['training_receipt']==descriptors['training_receipt'],'shadow_common_closed_training_receipt')
        model=validate_behavior_checkpoint(availability,row)
        require(model['seed']==row['seed'],'shadow_actual_weight_seed')
    from .foundation_flight_forecaster import validate_checkpoint
    checkpoint=validate_checkpoint(bound(resources['forecast_checkpoint']))
    require(checkpoint['frozen_at']==43200. and checkpoint['training_labels_closed_at']<=43200.,'shadow_B1_cutoff')
    context=bound(resources['flight_context'])
    require(context['availability_basis']=='static_predeclared' and context['received_at']==0.
        and all(row['planned_injection_region'] is None for row in context['entries']),'shadow_public_plan_scope')
    return selection,descriptors,context,checkpoint


def configure():
    global _configured
    if _configured:return delegate
    budget.configure()
    delegate.MODULE,delegate.SCHEMA=MODULE,SCHEMA
    delegate.SOURCE_ROOTS=(MODULE,*delegate.SOURCE_ROOTS)
    delegate.check_pins=check_pins
    delegate.execute_continuous=execute_continuous
    _configured=True
    return delegate


def check_pins(plan):
    _BASE_CHECK(plan)
    require(plan['branch']=='C00' and plan['scope']==contract()['purpose'],'shadow_baseline_branch_only')
    resources=plan['behavior_shadow']
    validate_resources(resources,read(plan['mapping']['path']))
    old=bound(resources['baseline_plan'])
    # Only these administrative/dependency/diagnostic fields may differ.
    allowed={'schema','status','output','source_sha256','source_archive','source_dependency_roots',
             'input','input_file_sha256','scope','behavior_shadow'}
    require(set(plan)==set(old)|{'behavior_shadow'},'shadow_no_unknown_plan_fields')
    for key in set(old)-allowed:require(plan[key]==old[key],'shadow_same_baseline_field:'+key)
    require(Path(plan['input']['path']).read_bytes()==Path(old['input']['path']).read_bytes(),'shadow_same_input_bytes')
    for source,expected in old['source_sha256'].items():
        require(plan['source_sha256'].get(source)==expected,'shadow_original107_source_bytes')


def prepare(output, *, model_manifest, selection=SELECTION,
            checkpoint=delegate.legacy.FORECAST_DIR/'flight_forecaster_checkpoint.json',
            flight_plan=delegate.legacy.FORECAST_DIR/'public/static_flight_plan.json'):
    configure()
    output=Path(output).resolve()
    require(output.is_relative_to(ROOT) and output!=ROOT and not output.exists(),'shadow_fresh_output')
    old=read(BASELINE/'plan.json')
    resources={'contract':contract(),'baseline_plan':reference(BASELINE/'plan.json'),
        'baseline_receipt':reference(BASELINE/'receipt.json'),'selection':reference(selection),
        'scorer_freeze':reference(SCORER_FREEZE),'model_manifest':reference(model_manifest),
        'forecast_checkpoint':reference(checkpoint),'flight_context':reference(flight_plan)}
    validate_resources(resources,read(old['mapping']['path']))
    pins=delegate.source_pins()
    for path,expected in old['source_sha256'].items():require(pins.get(path)==expected,'shadow_original_sources_unchanged')
    output.mkdir(parents=True);(output/'inputs').mkdir();(output/'source').mkdir()
    target=output/'inputs/C00.json';target.write_bytes(Path(old['input']['path']).read_bytes())
    archive={}
    for i,path in enumerate(pins):
        archived=output/'source'/f'{i:04d}.py';archived.write_bytes(Path(path).read_bytes())
        archive[path]=str(archived.relative_to(output))
    plan=copy.deepcopy(old)
    plan.update(schema=SCHEMA,status='prepared_not_executed',output=str(output),source_sha256=pins,
        source_archive=archive,source_dependency_roots=list(delegate.SOURCE_ROOTS),input=reference(target),
        input_file_sha256={'C00':sha(target)},scope=contract()['purpose'],behavior_shadow=resources)
    check_pins(plan);write_new(output/'plan.json',plan)
    return plan


def timed_recorded_callback(recorder,shadow,*,clock=time.perf_counter):
    recorded=recorder.wrap(shadow)
    def callback(observation,**options):
        start=clock();before=len(shadow.results)
        result=recorded(observation,**options)
        if len(shadow.results)>before:
            shadow.results[-1]['entire_recorded_callback_elapsed_including_all_storage_seconds']=clock()-start
            shadow.results[-1]['full_callback_scope']='outer Recorder capture through original baseline, shadow score/event storage and Recorder reference/blob storage before return'
        return result
    return callback


def execute_continuous(session,data,plan,directory):
    from functools import partial
    from .foundation_airport_protocol_v2 import run_airport_bounded_protocol_control
    from .foundation_airport_behavior_shadow import score_record
    resources=plan['behavior_shadow']
    selection,models,context,checkpoint=validate_resources(resources,read(plan['mapping']['path']))
    mapping=read(plan['mapping']['path'])
    # Offline receipts only select exact callback identities; they are never
    # arguments to the scorer. No model affects the original policy decision.
    scorer=partial(score_record,model_descriptors=models['model_descriptors'],flight_context=context,
        forecast_checkpoint=checkpoint,mapping=mapping,episode_id='C00_budget002_train_trajectory_shadow',episode_end=59400.)
    shadow=ShadowPlanner(delegate.registered_planner(plan),scorer,selections=selection['selected'],
        branch='C00',business_version=delegate.domain.VERSION,path=directory/'behavior_shadow_events.jsonl')
    recorder=delegate.Recorder(directory/'policy_observations.jsonl.gz',branch='C00',business_version=delegate.domain.VERSION)
    controller=partial(run_airport_bounded_protocol_control,planner=timed_recorded_callback(recorder,shadow),
        planner_identity='airport_live_behavior_shadow_v1:C00:'+delegate.domain.VERSION+':'+plan['mapping']['sha256'])
    try:raw=delegate.execute_bounded_continuous(session,data,plan,directory,controller=controller)
    finally:
        recorder.close();shadow.close()
    observed=recorder.summary();diagnostic=shadow.summary()
    write_new(directory/'policy_observation_receipt.json',observed)
    write_new(directory/'behavior_shadow_receipt.json',diagnostic)
    raw.update(business_contract_version=delegate.domain.VERSION,business_semantic_sha256=delegate.domain.BUSINESS_SHA,
        non_business_semantic_sha256=delegate.POLICY_NONBUSINESS_SHA,old_C00_C10_repaired_or_relabelled=False,
        policy_observations=observed,behavior_shadow=diagnostic)
    return raw


def main():
    sys.path.insert(0,str(ROOT/'src'))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    modes=parser.add_mutually_exclusive_group(required=True)
    for name in ('prepare','launch','worker'):modes.add_argument('--'+name,action='store_true')
    parser.add_argument('--admission');parser.add_argument('--plan-sha256')
    parser.add_argument('--model-manifest',type=Path)
    args=parser.parse_args();configure()
    if args.prepare:
        require(args.model_manifest is not None,'actual_model_manifest_required_no_placeholders')
        result=prepare(args.output,model_manifest=args.model_manifest)
    elif args.launch:result=delegate.launch(args.output)
    else:result=delegate.worker(args.output,args.plan_sha256)
    print(json.dumps({'status':result['status'],'output':str(args.output.resolve())}))
    if args.worker and result['status'].startswith('unknown'):raise SystemExit(1)


if __name__=='__main__':main()

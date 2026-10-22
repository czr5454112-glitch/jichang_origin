"""Streaming same-observation bin sensitivity; check-only unless --execute.

Requires all four full DEV TF-B1-60 runs registered in frozen workflow005.
Uses the frozen offline_granularity algorithm and frozen projection/optimizer.
Never starts native, reads full owner ACK exports, fits, or selects parameters.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib
import importlib.util
import json
import math
from pathlib import Path
import sys

MODES=('60','300','600','near_fine')
PARENTS=(2201,2202,2203,2204)
EVIDENCE_FILES=('plan.json','receipt.json','worker_report.json','trajectory.json.gz',
    'decisions.json.gz','observations.json.gz','arrival_support_contract.json','arrival_support_receipts.json')

def need(ok, reason):
    if not ok:raise ValueError('streaming_granularity:'+reason)

def bind(path):
    path=Path(path).resolve();sha=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):sha.update(chunk)
    return dict(path=str(path),sha256=sha.hexdigest())

def load_support():
    path=Path(__file__).with_name('final_science_audit_004.py');ref=bind(path)
    spec=importlib.util.spec_from_file_location('granularity_final_science_support',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    need(bind(path)==ref,'support_changed_during_import')
    return module,ref

def load_helpers(root,audit):
    h=audit.load_helpers(root)
    package='scripts.experiments.g31_ics_circulation.'
    for key,name in dict(r0='foundation_airport_inventory_rule',opportunities='foundation_airport_joint_opportunities',
                        forecast='foundation_airport_terminal_forecast',control='foundation_airport_transport_control').items():
        h[key]=importlib.import_module(package+name)
    for name,module in list(sys.modules.items()):
        if name.startswith('scripts.') and getattr(module,'__file__',None):
            need(Path(module.__file__).resolve().is_relative_to(root),'nonfrozen_import:'+name)
    return h

def validate_plan(plan,source_ref,h):
    need(plan['source_bundle']==source_ref,'run_source_binding')
    parent=plan['parent']
    need(parent['split']=='dev' and parent['synthetic'] is True and parent['parent_seed'] in PARENTS,'four_dev_parents_only')
    need(plan['method']=='TF-B1-60' and plan['activation']==7200. and plan['horizon']==59400.,'full_fine_run_required')
    need(not h['campaign'].method_contract_errors(plan),'registered_method_contract')
    need(plan['forecast_bin_edges_seconds']==h['forecast'].bin_edges('60')
        and plan['forecast_horizon_seconds']==1800. and plan['projection_horizon_seconds']==600.
        and plan['recompute_period_seconds']==60. and plan['supply_mode']=='committed_only','fixed_horizon_grid_and_control')
    need(plan['demand_model'] is None and plan['model'] is None,'uncalibrated_B1_only')
    need(plan['controller']['control_period']==60. and plan['controller']['command_delay']==2.,'fixed_command_timing')

def inspect_runs(workflow_path,source_ref,audit,h):
    paths,workflow_ref=audit.workflow_blocks(workflow_path,source_ref)
    bridge=paths[0]
    if not bridge.exists():
        return {},dict(status='pending',registered_runs=0,expected_runs=4,
            pending=[dict(block=str(bridge),status='not_registered')],workflow=workflow_ref,bridge=None)
    bridge_ref=bind(bridge);block=audit.bound_read(bridge_ref)
    need(block['phase']=='bridge' and block['source_bundle']==source_ref,'registered_bridge_source')
    need(tuple(block['methods'])==audit.PHASES['bridge'] and set(block['parents'])==set(PARENTS)
        and len(block['parents'])==4,'registered_full_bridge_matrix')
    h['campaign']._validate_block_manifest(block)
    rows={};pending=[]
    for ref in block['task_plans']:
        plan=audit.bound_read(ref)
        if plan['method']!='TF-B1-60':continue
        validate_plan(plan,source_ref,h)
        parent=plan['parent']['parent_seed'];need(parent not in rows,'duplicate_parent')
        directory=Path(ref['path']).parent
        rows[parent]=dict(plan=plan,plan_binding=ref,directory=directory)
        if not (directory/'receipt.json').exists():
            pending.append(dict(parent=parent,status='receipt_missing'));continue
        receipt=audit.read(directory/'receipt.json')
        if receipt.get('worker',{}).get('scientific_status')!='closed':
            pending.append(dict(parent=parent,status=receipt.get('worker',{}).get('scientific_status','unknown')));continue
        h['flow'].closed_run(directory)
    need(set(rows)==set(PARENTS),'all_four_registered_fine_runs_required')
    values=list(rows.values());first=values[0]['plan']
    for row in values[1:]:
        for key in ('source_bundle','binary','mapping','controller','transport_config','supply_mode',
                    'forecast_bin_edges_seconds','forecast_horizon_seconds','projection_horizon_seconds','recompute_period_seconds'):
            need(row['plan'][key]==first[key],'different_fixed_four_parent_contract:'+key)
        need(row['plan']['parent']['common_historical_template_sha256']==first['parent']['common_historical_template_sha256'],
            'historical_template_changed')
    return rows,dict(status='pending' if pending else 'ready',registered_runs=4,expected_runs=4,
        pending=pending,workflow=workflow_ref,bridge=bridge_ref)

def stats():
    return dict(opportunities=Counter(),modes={mode:Counter() for mode in MODES},
        eta={mode:dict(count=0,total=0.,maximum=None) for mode in MODES[1:]},mass_checks=Counter(),examples=[])

def add_mass(bucket,value):
    need(math.isfinite(value) and value>=0,'finite_absolute_mass_difference')
    bucket['count']+=1;bucket['total']+=value
    bucket['maximum']=value if bucket['maximum'] is None else max(bucket['maximum'],value)

def allocation(selection):
    return Counter((row['source'],row['destination']) for row in selection['flow_plan']['chosen'])

def allocation_rows(counts):
    return [dict(source=source,destination=destination,quantity=n) for (source,destination),n in sorted(counts.items())]

def choice_signature(candidate):
    return [candidate.get(key) for key in ('action_type','source','destination','tray_id')]

def validate_forecast(decision,plan,h):
    binding=decision.get('forecast_binding')
    if not binding or 'forecast' not in binding:return None
    forecast=binding['forecast'];now=decision['decision_time'];absolute=plan['parent']['calendar_start_epoch_seconds']+now
    need(forecast['bin_edges_seconds']==h['forecast'].bin_edges('60'),'saved_fine_forecast_required')
    need(forecast['forecast_origin']==now and forecast['owner_scope']==decision['owner_id'],'forecast_time_owner_binding')
    need(binding['forecast_sha256']==h['digest'].digest(forecast),'exact_actor_forecast_digest')
    need(binding['public_state_sha256']==decision['public_observation_ref'],'forecast_public_observation_binding')
    need(binding['observed_at_epoch_seconds']==absolute and binding['actual_callback_consumption'] is True
        and binding['forecast_provenance']=='actual_callback_received','actual_callback_forecast_required')
    need(binding['training_labels_closed_at_epoch_seconds']<=binding['model_available_at_epoch_seconds']<absolute
        and binding['plan_received_at_epoch_seconds']<=absolute,'forecast_available_at_callback')
    transform=binding['forecast_transform']
    need(transform['actor_forecast_sha256']==binding['forecast_sha256']
        and transform['source_forecast_sha256']==binding['source_forecast_sha256']
        and transform['demand_model_sha256'] is None,'uncalibrated_transformed_B1_identity')
    return forecast

def replay(decision,observation,forecast,plan,support,support_receipts,h,result):
    """Same pure equations/order as frozen campaign.offline_granularity's loop.

    New fields distinguish total quantity from OD allocation. No policy parameter
    is fitted or changed. Each mode starts from an empty replay policy state.
    """
    counts=result['opportunities'];saved=decision['selection']['flow_plan']
    need(type(saved.get('receiver_claims_deducted')) is dict,'receiver_claim_evidence_required')
    claims=saved['receiver_claims_deducted']
    need(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in claims.values()),'receiver_claim_counts_invalid')
    if any(claims.values()):
        counts['excluded_uncredited_claim_opportunities']+=1;return
    need(saved['config']==plan['transport_config'],'saved_optimizer_config_binding')
    baseline=h['r0'].r0_priority_planner(observation)
    if baseline['intents']:
        counts['excluded_priority_not_exhausted']+=1;return
    prepared=h['opportunities'].prepare_current(observation,baseline,message_delay=2.)
    catalog=h['opportunities'].build_joint_catalog(prepared)
    need(catalog['catalog_id']==decision['legal_catalog_ref'],'rebuilt_legal_catalog_differs')
    counts['replayed_opportunities']+=1
    selections={};projections={}
    for mode in MODES:
        representation=h['forecast'].rebin_forecast(forecast,bin_edges_seconds=h['forecast'].bin_edges(mode))
        projection=h['projection'].prepare_inventory_projection(observation,forecast=representation,
            prepared_current=prepared,supply_mode='committed_only',horizon_seconds=600.,
            arrival_support_contract=support,arrival_support_receipt=support_receipts[decision['owner_id']])
        projections[mode]=projection
        selections[mode]=h['control'].TransportPolicy(config=saved['config'],recompute_period_seconds=60.).select(
            prepared,catalog,projection,policy_state={},decision_context=dict(decision_id=decision['decision_id'],tick=0))
        result['modes'][mode]['nonzero_plan_opportunities']+=bool(selections[mode]['flow_plan']['chosen'])
        result['modes'][mode]['selected_transfers']+=selections[mode]['action_id']!='a_noop'
    reference=selections['60'];candidates={row['action_id']:row for row in catalog['candidates']}
    reference_action=choice_signature(candidates[reference['action_id']]);reference_allocation=allocation(reference)
    od={}
    for candidate in catalog['candidates']:
        if candidate['action_type']=='transfer':od[candidate['source'],candidate['destination']]=candidate
    for mode in MODES[1:]:
        choice=selections[mode];alternative_action=choice_signature(candidates[choice['action_id']])
        changed=alternative_action!=reference_action;alt_allocation=allocation(choice)
        quantity_changed=len(choice['flow_plan']['chosen'])!=len(reference['flow_plan']['chosen'])
        allocation_changed=alt_allocation!=reference_allocation
        mode_counts=result['modes'][mode]
        mode_counts['first_action_changes_vs_60']+=changed
        mode_counts['quantity_changes_vs_60']+=quantity_changed  # Preserve old helper's exact meaning.
        mode_counts['total_quantity_changes_vs_60']+=quantity_changed
        mode_counts['quantity_allocation_changes_vs_60']+=allocation_changed
        if (changed or allocation_changed) and len(result['examples'])<20:
            result['examples'].append(dict(parent=plan['parent']['parent_seed'],decision_time=observation['now'],
                owner_id=observation['owner_id'],mode=mode,reference_action=reference_action,alternative_action=alternative_action,
                reference_allocation=allocation_rows(reference_allocation),alternative_allocation=allocation_rows(alt_allocation),
                first_action_changed=changed,total_quantity_changed=quantity_changed,quantity_allocation_changed=allocation_changed,
                native_service_change_measured=False))
        for node in projections['60'].loaders:
            for horizon in (600.,1800.):
                a=h['projection'].demand_mass(projections['60'],node,0.,horizon)
                b=h['projection'].demand_mass(projections[mode],node,0.,horizon)
                need((a is None)==(b is None),'common_horizon_mass_knownness_changed')
                if a is not None:
                    need(abs(a-b)<=1e-9,'coarsening_changed_common_horizon_mass')
                    result['mass_checks']['known_equal_'+str(int(horizon))]+=1
                else:result['mass_checks']['both_unknown_'+str(int(horizon))]+=1
        for candidate in od.values():
            at=min(600.,candidate['nominal_arrival_time']-projections[mode].now)
            a=h['projection'].demand_mass(projections['60'],candidate['destination'],0.,at)
            b=h['projection'].demand_mass(projections[mode],candidate['destination'],0.,at)
            if a is not None and b is not None:add_mass(result['eta'][mode],abs(a-b))

def summary(result):
    return dict(opportunities=dict(result['opportunities']),modes={k:dict(v) for k,v in result['modes'].items()},
        eta_cumulative_demand_sensitivity={mode:dict(count=v['count'],
            mean_absolute_mass_difference=v['total']/v['count'] if v['count'] else None,
            maximum_absolute_mass_difference=v['maximum']) for mode,v in result['eta'].items()},
        common_horizon_mass_checks=dict(result['mass_checks']),first_action_or_allocation_change_examples=result['examples'])

def audit_run(row,audit,h):
    directory=row['directory'];evidence={name:bind(directory/name) for name in EVIDENCE_FILES}
    plan,receipt,trajectory=h['flow'].closed_run(directory)
    need(evidence['plan.json']['sha256']==row['plan_binding']['sha256'],'registered_plan_changed')
    support=audit.read(directory/'arrival_support_contract.json');receipts=audit.read(directory/'arrival_support_receipts.json')
    decisions=audit.DecisionJoin(trajectory['rows'],plan['activation'],plan['horizon'])
    observations=audit.ObservationJoin(directory,[],h,plan['horizon']);result=stats()
    try:
        for decision in h['stream'].iter_json_array_gz(directory/'decisions.json.gz'):
            result['opportunities']['recorded_decisions']+=1
            if not decisions.accept(decision):
                result['opportunities']['excluded_outside_registered_window']+=1;continue
            observation=observations.get(decision)
            result['opportunities']['validated_in_window_decisions']+=1
            forecast=validate_forecast(decision,plan,h)
            if forecast is None:
                result['opportunities']['missing_consumed_forecast']+=1;continue
            replay(decision,observation,forecast,plan,support,receipts,h,result)
        decisions.finish()
    finally:observations.finish()
    return result,dict(parent=plan['parent']['parent_seed'],task_id=plan['task_id'],evidence=evidence,
        evidence_bound_before_consumption=True,observations_read=observations.count,
        all_trajectory_decisions_digest_time_owner_checked=True,**summary(result))

def merge(target,source):
    target['opportunities'].update(source['opportunities']);target['mass_checks'].update(source['mass_checks'])
    for mode in MODES:target['modes'][mode].update(source['modes'][mode])
    for mode in MODES[1:]:
        a,b=target['eta'][mode],source['eta'][mode]
        a['count']+=b['count'];a['total']+=b['total']
        if b['maximum'] is not None:a['maximum']=b['maximum'] if a['maximum'] is None else max(a['maximum'],b['maximum'])
    target['examples'].extend(source['examples'][:max(0,20-len(target['examples']))])

def execute(rows,status,source_ref,producer_refs,audit,h,output):
    need(status['status']=='ready' and set(rows)==set(PARENTS),'all_four_closed_before_execute')
    audit.verify_bindings(producer_refs,'granularity_producer_changed')
    audit.verify_sources(source_ref);audit.bound_read(status['workflow']);audit.bound_read(status['bridge'])
    output=Path(output);need(not output.exists(),'fresh_output_directory_required');output.mkdir(parents=True)
    audit.fresh(output/'pending.json',dict(status='in_progress',analysis_producers=producer_refs,source_bundle=source_ref))
    total=stats();refs=[]
    for parent,row in sorted(rows.items()):
        print(json.dumps(dict(stage='streaming_granularity',parent=parent)),flush=True)
        result,report=audit_run(row,audit,h);merge(total,result)
        refs.append(audit.fresh(output/f'P{parent}_granularity.json',report))
    end_rows,end_status=inspect_runs(status['workflow']['path'],source_ref,audit,h)
    need(end_status==status and set(end_rows)==set(rows),'closure_or_registration_changed_during_audit')
    audit.verify_sources(source_ref)
    for row in rows.values():
        for ref in row['plan'].values():
            if isinstance(ref,dict) and {'path','sha256'}<=set(ref):audit.verify_bindings([ref],'plan_dependency_changed')
    for ref in refs:
        report=audit.bound_read(ref);audit.verify_bindings(report['evidence'].values(),'run_evidence_changed_during_audit')
    audit.verify_bindings(producer_refs,'granularity_producer_changed')
    report=dict(schema='g31.terminal_flow.streaming_granularity.v1',status='complete',source_bundle=source_ref,
        workflow=status['workflow'],bridge=status['bridge'],analysis_producers=producer_refs,runs=refs,**summary(total),
        frozen_algorithm='foundation_airport_transport_campaign.offline_granularity',
        fixed_projection_horizon_seconds=600.,fixed_forecast_horizon_seconds=1800.,fixed_recompute_period_seconds=60.,
        fixed_command_delay_seconds=2.,decision_window_left_closed_right_open=[7200.,59400.],
        quantity_changes_legacy_meaning='len(chosen); total quantity, not OD allocation',
        quantity_allocation_comparison='Counter((source,destination) for each chosen eligible physical tray)',
        comparison_ignores_plan_order_ids_and_other_metadata=True,
        source_tray_eligibility_and_catalog_fixed_across_modes=True,
        receiver_claims_nonzero_explicitly_excluded=True,missing_receiver_claim_evidence_is_error=True,
        native_starts=0,full_owner_ack_export_opened=False,native_service_gain_measured=False,
        no_finer_CDF_access=True,model_fits=0,parameters_selected=False,TEST_read=False,
        old_422_opportunity_result_unchanged_and_not_pooled=True,
        observations_from_original_policy_not_counterfactual_closed_loop=True,
        repeated_opportunities_not_independent_airport_days=True,
        information='recorded public observations and exact consumed frozen B1 fine forecasts only',
        interpretation='Common 600/1800 mass is conserved; ETA partial-bin integrals and choices may differ. '
            'Offline sensitivity alone is not native service improvement or automatic authority to skip a native arm.')
    final_ref=audit.fresh(output/'granularity_report.json',report)
    audit.fresh(output/'COMPLETE.json',dict(status='complete',report=final_ref,
        producers_source_and_evidence_checked_at_start_and_end=True,native_starts=0))
    print(json.dumps(dict(report=final_ref,native_starts=0)),flush=True)

def main():
    producer_refs=[bind(__file__)];audit,support_ref=load_support();producer_refs.append(support_ref)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest',required=True,type=Path);parser.add_argument('--workflow',required=True,type=Path)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();source_ref=bind(args.source_manifest);root=audit.verify_sources(source_ref)
    need(root.name=='terminal_flow_runtime_005','frozen_source005_required')
    h=load_helpers(root,audit);rows,status=inspect_runs(args.workflow,source_ref,audit,h)
    if not args.execute:
        audit.verify_bindings(producer_refs,'granularity_producer_changed')
        print(json.dumps(dict(status,science_executed=False,native_starts=0,analysis_producers=producer_refs),indent=2));return
    need(args.output_dir is not None,'execute_requires_fresh_output_dir')
    execute(rows,status,source_ref,producer_refs,audit,h,args.output_dir)

if __name__=='__main__':main()

"""Eight fresh source006 audits and four same-source horizon-only per-bag pairs."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
DATA=Path(__file__).resolve().parent
CYCLE=ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
METHODS=('TF-B1-60','TF-B1-60-H1800')

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def inspect(a,u,source,workflow,h):
    reg=a.bound_read(workflow);done_ref=a.bind(Path(workflow['path']).with_name('completion.json'));done=a.bound_read(done_ref)
    a.need(reg['schema']=='g31.terminal_flow.projection_horizon_workflow.v1' and reg['source_bundle']==source,
        'horizon_workflow_source')
    a.need(done['registration']==workflow and done['all_registered_development_tasks_closed'] is True
        and done['TEST_unlocked'] is False and len(done['receipts'])==8,'eight_closed_native_required')
    block=a.bound_read(reg['block']);a.need(block['methods']==list(METHODS) and block['parents']==list(a.PARENTS)
        and len(block['task_plans'])==8 and block['source_bundle']==source,'fixed_horizon_block')
    manifest=a.bound_read(source);a.need(Path(manifest['root']).name=='terminal_flow_runtime_006'
        and manifest['worker_evidence_contract']==u.CONTRACT,'source006_compact_contract')
    rows={};refs=[workflow,done_ref,reg['block']]+list(reg['dependencies'].values())
    for ref,receipt_ref in zip(block['task_plans'],done['receipts']):
        plan=a.bound_read(ref);directory=Path(ref['path']).parent;key=plan['parent']['parent_seed'],plan['method']
        a.need(key not in rows and key in {(p,m) for p in a.PARENTS for m in METHODS},'fixed_unique_pair')
        a.need(plan['source_bundle']==source and plan['parent']['split']=='dev' and plan['batch']=='initial'
            and plan['horizon']==59400. and plan['activation']==7200.
            and not h['campaign'].method_contract_errors(plan),'registered_horizon_contract')
        a.need(a.bind(directory/'receipt.json')==receipt_ref,'receipt_binding');h['flow'].closed_run(directory)
        ack=directory/'delivered_ack_evidence.json.gz';worker=a.read(directory/'worker_report.json')
        a.need(plan['worker_evidence_contract']==u.CONTRACT and ack.is_file() and ack.stat().st_size<u.ACK_BYTES_LIMIT
            and worker['delivered_ack_evidence_scope']=='complete transfer ACK history and transfer ledger; owner protocol subset'
            and worker['delivered_ack_evidence']['gzip_bytes']==ack.stat().st_size,'compact_ack_closed_size_scope')
        rows[key]=dict(plan=plan,directory=directory);refs.extend([ref,receipt_ref])
    for parent in a.PARENTS:
        change=a.pair_contract(rows[parent,METHODS[0]]['plan'],rows[parent,METHODS[1]]['plan'],
            ('projection_horizon',),h['campaign'].comparison_contract)
        a.need(set(change['observed_differences'])=={'projection_horizon'},'actual_single_axis')
    return rows,refs

def execute(a,u,source,workflow,h,output):
    producers=[a.bind(__file__),a.bind(DATA/'final_science_audit_004.py'),a.bind(DATA/'unified_order_audit_005.py')]
    rows,refs=inspect(a,u,source,workflow,h)
    a.need(not output.exists(),'fresh_horizon_science');output.mkdir(parents=True)
    a.fresh(output/'STARTED.json',dict(status='in_progress',source_bundle=source,producers=producers))
    run_refs=[];unified_refs=[];reports={};request_violations=0
    for key,row in sorted(rows.items()):
        print(json.dumps(dict(stage='horizon_run_audit',parent=key[0],method=key[1])),flush=True)
        report=a.run_audit(row,h);reports[key]=report
        run_refs.append(a.fresh(output/f'P{key[0]}_{key[1]}_behavior_timing.json.gz',report))
        orders=u.run_audit(row,h,a)
        request_violations+=len(orders['frozen_unified_order_book']['violations'])+len(orders['full_request_audit']['violations'])
        unified_refs.append(a.fresh(output/f'P{key[0]}_{key[1]}_unified_orders.json.gz',orders))
    pairs=[];summaries=[]
    for parent in a.PARENTS:
        left,right=rows[parent,METHODS[0]],rows[parent,METHODS[1]]
        result=h['service'].compare_runs(left['directory'],right['directory'])
        a.need(result['population']==28506 and result['population_exclusions']==0,'complete_population')
        result['parent']=parent
        result['registered_pair_axis']=a.pair_contract(left['plan'],right['plan'],('projection_horizon',),h['campaign'].comparison_contract)
        result['actual_order_and_decision_changes']=a.compare_choices(reports[parent,METHODS[0]],reports[parent,METHODS[1]])
        result['local_service_by_original_input_node']=a.local_service(result['per_bag'],a.bound_read(left['plan']['input'])['jobs'])
        result['independent_airport_day_claim']=False
        pairs.append(a.fresh(output/f'P{parent}_600_to_1800_per_bag.json.gz',result))
        summaries.append({k:v for k,v in result.items() if k not in ('per_bag','physical_contract','evidence','physical_progress')})
    for report in reports.values():a.verify_bindings(report['evidence'].values(),'horizon_input_changed')
    for ref in unified_refs:a.verify_bindings(a.bound_read(ref)['evidence'].values(),'horizon_orders_input_changed')
    a.verify_sources(source);inspect(a,u,source,workflow,h)
    a.verify_bindings(refs+producers+run_refs+unified_refs+pairs,'horizon_binding_changed')
    final=dict(schema='g31.terminal_flow.horizon_science.v1',status='complete',source_bundle=source,workflow=workflow,
        dependencies=refs,analysis_producers=producers,runs=run_refs,unified_orders=unified_refs,
        unified_order_violations=request_violations,per_bag_pair_evidence=pairs,pair_summaries=summaries,
        aggregate=a.aggregate_pairs(summaries),new_native_runs=8,offline_native_starts=0,
        scientific_per_bag_pairs=4,same_source_baselines_rerun=True,all_inputs_rechecked=True,
        source_followup_window_seconds=600,source_followup_window_not_extended_with_projection=True,
        strict_per_bag_nonharm_certified=False,promotion_approved=False,TEST_unlocked=False,R1_enabled=False,
        sampling_scope='four same-template-derived DEV parents; no independent airport-day inference')
    ref=a.fresh(output/'horizon_science_report.json',final)
    a.fresh(output/'COMPLETE.json',dict(status='complete',final_report=ref));print(json.dumps(ref),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-manifest',type=Path,required=True);p.add_argument('--workflow',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--output-dir',type=Path)
    args=p.parse_args();a=load(DATA/'final_science_audit_004.py','horizon_original_science')
    a.need(a.bind(DATA/'final_science_audit_004.py')['sha256']=='fa3518b68ed3e0c6abea0293752ba58c922c53bc290bfe31ea1a1d9bf96ca6c2',
        'original_science_driver_unchanged')
    u=load(DATA/'unified_order_audit_005.py','horizon_original_unified')
    source=a.bind(args.source_manifest);root=a.verify_sources(source);workflow=a.bind(args.workflow);h=a.load_helpers(root)
    if args.execute:
        a.need(args.output_dir is not None,'explicit_output');execute(a,u,source,workflow,h,args.output_dir)
    else:rows,_=inspect(a,u,source,workflow,h);print(json.dumps(dict(status='ready',runs=len(rows),science_executed=False)))

if __name__=='__main__':main()
